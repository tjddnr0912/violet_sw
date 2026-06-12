//! Engine state: the net value table (+ previous-delta snapshot for edges),
//! VCD wiring, and the single net-write choke point with change detection.

use std::cell::Cell;
use std::io::Write;
use std::rc::Rc;

use diag::{Diagnostic, LogEvent, LogSink, MsgCode, Severity, TimeStamp};
use sim_ir::{BitPacked, Lvalue, NetKind, SelKind, SimIr};
use vcd_writer::{IdCode, VarType, VcdWriter};

use crate::eval::NetReader;
use crate::value::{nwords, top_mask, Value, Words};

/// A boxed `Write` sink for the VCD. v1 production uses a `File`; tests use an
/// in-memory buffer captured via an `Rc<RefCell<Vec<u8>>>` adapter.
pub(crate) type VcdSink = Box<dyn Write>;

/// One net's runtime storage. The current value occupies `array_len * width`
/// bits laid out word `w` at `[w*width .. w*width+width)`.
pub(crate) struct NetSlot {
    pub cur: BitPacked,
    pub prev: BitPacked,
    pub width: u32,
    pub array_len: u32,
    pub signed: bool,
    /// True for a `NetKind::Real` net — drives the real↔int assignment coercion
    /// in `write_lvalue` and the `is_real` flag on reads.
    pub is_real: bool,
    pub vcd_id: Option<IdCode>,
    /// Per-element VCD ids for an unpacked array (Phase-1.x ⑤): one id per
    /// word, declared as `mem[idx]` vars. EMPTY for scalars (vcd_id is used).
    pub vcd_word_ids: Vec<Option<IdCode>>,
}

/// One captured `$strobe`/`$monitor` argument list. Stores ExprIds (not values)
/// so the args are RE-EVALUATED at postponed-flush time, sampling settled
/// end-of-timestep net values. ExprIds index the immutable `ir.exprs` and remain
/// valid for the whole run, so no value snapshot or scope context is needed:
/// `EvalCtx` is rebuilt from `Scheduler::st` (ir / nets / now / wt) at flush.
#[derive(Clone)]
pub(crate) struct FmtCapture {
    /// `SysTask.fmt`: Option<ExprId> → a `Const{val}` whose `val` is the
    /// format-string ConstId. `None` ⇒ bare-args (space-joined decimals).
    pub fmt: Option<u32>,
    /// `SysTask.args`: the argument ExprIds, evaluated lazily in `format_args_str`.
    pub args: Vec<u32>,
    /// Time multiplier `M` of the process that REGISTERED this capture (snapshot of
    /// `cur_time_mult` at registration). The postponed flush renders `$time`/
    /// `$realtime` with THIS value, never the scheduler's live `cur_time_mult` —
    /// which by flush time holds whatever process ran LAST in the timestep, a
    /// DIFFERENT module's `M` under mixed `` `timescale ``s.
    pub time_mult: u64,
    /// Default radix for unformatted args (P1-5 b/o/h variants); `None` ⇒ decimal.
    pub radix: Option<u8>,
    /// `%m` scope of the registering process (P2-11) — snapshot, like `time_mult`.
    pub scope: String,
}

/// The single global `$monitor` record (IEEE 1364-2005: at most one active
/// monitor list in the entire simulation). A later `$monitor` REPLACES this.
pub(crate) struct MonitorState {
    pub cap: FmtCapture,
    /// Last evaluated 4-state VALUE list of `cap.args` (one `Value` per arg).
    /// `None` ⇒ never printed yet, so the next postponed flush prints
    /// unconditionally (establishment print). IEEE 1364-2005 §17.1 keys $monitor
    /// reprints off the *monitored expression VALUE* changing, NOT off the
    /// rendered string. `Value` derives `PartialEq`/`Eq` over the `(val, unk)`
    /// bit-planes, so equality is exactly 4-state-aware: an X/Z-collapsing format
    /// spec (`%d` rendering any-unknown to "x", `%h`/`%b` collapsing a
    /// partial-unknown group) can NEVER mask a genuine value transition the way a
    /// rendered-string diff would (e.g. `4'b00xx → 4'b0x00` under `%d`, both
    /// printing "x", is correctly detected as a change here).
    pub last_vals: Option<Vec<Value>>,
    /// `$monitoroff` clears this; `$monitoron` re-sets + resets `last_vals` to
    /// force a print. DEFERRED for the MVP (no SysTaskId bound) — field present,
    /// always `true`, so the flush logic is already on/off-aware when the tasks
    /// land.
    pub enabled: bool,
}

/// Per-timestep postponed-region queue + the global monitor singleton.
#[derive(Default)]
pub(crate) struct Postponed {
    /// FIFO of pending strobes for the CURRENT timestep. Drained-and-CLEARED at
    /// every postponed flush (one-shot-per-call semantics).
    pub strobes: Vec<FmtCapture>,
    /// The global monitor (replace-on-redefine). `None` until first `$monitor`.
    pub monitor: Option<MonitorState>,
}

pub(crate) struct SimState<'a> {
    pub ir: &'a SimIr,
    pub now: u64,
    pub nets: Vec<NetSlot>,
    /// Dirty-sweep list (scheduler R2): nets that took an ACTUAL bit change
    /// since the last `propagate_changes` sweep, in write order (`dirty_flag`
    /// dedups). Replaces the per-delta full O(nets) `cur != prev` scan — the
    /// sweep sorts this list, so the resulting changed-net order is identical
    /// to the old ascending scan (byte-identity).
    pub dirty: Vec<u32>,
    pub dirty_flag: Vec<bool>,
    /// Per-net `force` flag (IEEE §9.3.2): while set, EVERY normal write path
    /// (procedural, NBA commit, cont-assign settle, delayed CA) is a silent
    /// no-op for that net — only `force_write`/`release` touch it. Whole-net
    /// granularity (bit/part-select force targets are rejected at elaborate).
    pub forced: Vec<bool>,
    /// IEEE §9.3.2 continuous-force registry: net → (whole-net lvalue, rhs
    /// ExprId, forcing module's time multiplier). BTreeMap ⇒ deterministic
    /// re-evaluation order; empty unless a force is live (zero steady cost).
    pub active_forces: std::collections::BTreeMap<u32, (sim_ir::Lvalue, u32, u64, bool)>,
    /// Proc-assigns displaced by an overriding `force` (§9.3.1): net → the
    /// parked (lvalue, rhs ExprId, time-mult). `release` re-pins from here.
    pub latent_assigns: std::collections::BTreeMap<u32, (sim_ir::Lvalue, u32, u64)>,
    /// v5 (C): dynamic-storage heap, keyed by HANDLE NetId (deterministic —
    /// declaration order). A missing entry IS the empty object (lazy). Dyn
    /// objects never live in the flat BitPacked store.
    pub dyn_heap: std::collections::BTreeMap<u32, DynObj>,
    /// Warn-once latch for dyn degradations (X-size new[], OOB, …) — one
    /// W-RUN-DYN-DEGRADE per handle net, never a per-iteration spam. RefCell:
    /// the READ path (`read_net` is `&self`) must latch too.
    pub dyn_warned: std::cell::RefCell<std::collections::BTreeSet<u32>>,
    /// Per-net "is a dyn handle" bitmap (DynArray/Queue/Assoc), precomputed so
    /// the hot read/write funnels pay ONE Vec<bool> load — not an `ir.nets`
    /// kind match — per indexed access.
    pub dyn_is_handle: Vec<bool>,
    /// IEEE 1364-2005 self-width side table — built once, immutable for the run.
    pub wt: crate::width::WidthTable,

    // ── VCD ──
    pub vcd: Option<VcdWriter<VcdSink>>,
    pub vcd_path: Option<String>,
    pub dump_pending_path: Option<String>,
    pub vcd_path_override: Option<String>,
    pub dumping: bool,
    pub timescale_unit: String,
    pub vcd_date: String,
    /// Per-NetId hierarchical name (`"top.dut.q"`); empty ⇒ flat `n{i}` fallback.
    pub net_names: Vec<String>,
    /// Per-ProcId time multiplier (from `SimOpts.proc_multipliers`); empty ⇒ M=1.
    pub proc_multipliers: Vec<u32>,
    /// StmtId → severity for `$fatal`/`$error`/`$warning`/`$info` statements
    /// (from `SimOpts.severities`); empty ⇒ no severity tasks in the design.
    pub severities: crate::SeverityTable,
    /// StmtId → default radix (2/8/16) for b/o/h print variants (P1-5).
    pub radixes: crate::RadixTable,
    /// Assign-rank table (§9.3.1, from `SimOpts.assign_ranks`): StmtIds of
    /// Force/Release stmts that are procedural assign/deassign (weak rank).
    pub assign_ranks: crate::AssignRankTable,
    /// Bounded-queue bounds (v6 ③, from `SimOpts.queue_bounds`): handle
    /// NetId → N. Empty ⇒ every queue unbounded.
    pub queue_bounds: crate::QueueBoundTable,
    /// Per-ProcId instance path for `%m` (P2-11); empty ⇒ flat `top` fallback.
    pub proc_scopes: Vec<String>,
    /// Unpacked-array dims for per-element VCD naming (Phase-1.x ⑤, from
    /// `SimOpts.net_dims`); an absent array falls back to 1-D 0-based names.
    pub net_dims: crate::NetDimsTable,
    /// ⑤b: net ids selected by the FIRST `$dumpvars` call's depth/scope/net
    /// args. `None` ⇒ dump everything (bare `$dumpvars` / level-only forms).
    pub dump_filter: Option<std::collections::BTreeSet<u32>>,
    /// ⑤b: W4021 once-latch for second-and-later `$dumpvars` calls.
    pub dump_multi_warned: bool,
    /// v7 random state — `Cell`s so the read-phase eval (`&self`) can draw:
    /// each evaluation of `$random`/`$urandom` IS a new draw (matches
    /// iverilog; a re-rendered `$monitor` re-rolls). Net/heap purity (P7a)
    /// is untouched. `$random` seed 0 = the Annex N zero-substitution path
    /// (iverilog default); `$urandom` initial state 0 is the vitamin pin.
    pub rng: RngCells,
    /// v7 runtime plusargs (from `SimOpts.plusargs`, CLI order).
    pub plusargs: Vec<String>,
    /// v7 file I/O: fd-form table (`$fopen(name, mode)` → 0x8000_0003…).
    /// 0x8000_0000..=0x8000_0002 are reserved (stdin/stdout/stderr).
    pub files: std::collections::BTreeMap<u32, std::fs::File>,
    /// v7 MCD-form table (`$fopen(name)`): channel BIT index → file.
    /// Bit 0 is stdout; opens take bits from 1 (iverilog parity).
    pub mcd_files: std::collections::BTreeMap<u32, std::fs::File>,
    /// Next fd-form counter (low bits; the returned fd is 0x8000_0000|n).
    pub next_fd: u32,
    /// Next MCD channel bit.
    pub next_mcd_bit: u32,
    /// W4022 once-per-descriptor latch (bad/closed fd writes).
    pub bad_fd_warned: std::collections::BTreeSet<u32>,
    /// Instance path of the process CURRENTLY executing — set per `run_process`
    /// (like `cur_time_mult`), read by the `%m` format spec.
    pub cur_scope: String,
    /// Worker-thread budget (from `SimOpts.threads`); `≥2` ⇒ VCD writer thread.
    pub threads: u32,
    /// Process-body execution backend (from `SimOpts.backend`). Default
    /// `Interpreter`; read at the single `run()` body-dispatch seam.
    pub backend: crate::Backend,
    /// Out-of-band bytecode-VM compile cache (Stage C, P0a), one slot per template
    /// (`ir.processes`). Decides codegen-ability ONCE and memoizes the `CompiledBody`;
    /// fork children sharing a template share its compile. NEVER enters the frozen
    /// `SimIr`. Used only on the `Bytecode` backend (`Unchecked` is a no-cost default).
    pub vm_cache: Vec<crate::backend::VmSlot>,
    /// Multiplier of the process CURRENTLY executing — set per `run_process`, read by
    /// `$time`/`$realtime`. 1 outside any process (the 1ns/1ns base).
    pub cur_time_mult: u64,

    // ── stdout for $display/$write (boxed sink, deterministic) ──
    pub out: Box<dyn Write + 'a>,

    // ── status flags ──
    pub finished: bool,
    pub had_error: bool,
    pub had_fatal: bool,

    // ── runtime diagnostics ──
    /// Direct handle to the diagnostic sink (same `&dyn LogSink` the `out` writer
    /// wraps), so the engine can emit runtime diagnostics (E-RUN-RANGE) — not just
    /// `$display` text. Interior mutability: `emit` takes `&self`.
    pub sink: &'a dyn LogSink,
    /// Rate-limit counter for E-RUN-RANGE (an OOR access in a loop would spam).
    pub run_range_count: Cell<u32>,

    // ── postponed region ($strobe FIFO + global $monitor singleton) ──
    pub postponed: Postponed,
}

impl<'a> SimState<'a> {
    pub fn new(
        ir: &'a SimIr,
        out: Box<dyn Write + 'a>,
        sink: &'a dyn LogSink,
        timescale_unit: String,
        vcd_date: String,
        vcd_path_override: Option<String>,
    ) -> Self {
        let nets = ir
            .nets
            .iter()
            .map(|nv| {
                let alen = nv.array_len.max(1);
                let total = (nv.width as usize) * (alen as usize);
                let init = expand_init(&nv.init, nv.width, alen, total);
                NetSlot {
                    cur: init.clone(),
                    prev: init,
                    width: nv.width,
                    array_len: alen,
                    signed: nv.signed,
                    is_real: nv.kind == NetKind::Real,
                    vcd_id: None,
                    vcd_word_ids: Vec::new(),
                }
            })
            .collect();
        let wt = crate::width::WidthTable::build(ir); // single forward pass
        let nnets = ir.nets.len();
        SimState {
            ir,
            now: 0,
            nets,
            dirty: Vec::new(),
            dirty_flag: vec![false; nnets],
            forced: vec![false; nnets],
            active_forces: std::collections::BTreeMap::new(),
            latent_assigns: std::collections::BTreeMap::new(),
            dyn_heap: std::collections::BTreeMap::new(),
            dyn_warned: std::cell::RefCell::new(std::collections::BTreeSet::new()),
            dyn_is_handle: ir
                .nets
                .iter()
                .map(|nv| {
                    matches!(
                        nv.kind,
                        NetKind::DynArray
                            | NetKind::Queue
                            | NetKind::Assoc
                            | NetKind::AssocStr
                            | NetKind::String
                    )
                })
                .collect(),
            wt,
            vcd: None,
            vcd_path: None,
            dump_pending_path: None,
            vcd_path_override,
            dumping: false,
            timescale_unit,
            vcd_date,
            net_names: Vec::new(),
            net_dims: crate::NetDimsTable::new(),
            dump_filter: None,
            dump_multi_warned: false,
            rng: RngCells::default(),
            plusargs: Vec::new(),
            files: std::collections::BTreeMap::new(),
            mcd_files: std::collections::BTreeMap::new(),
            next_fd: 3,
            next_mcd_bit: 1,
            bad_fd_warned: std::collections::BTreeSet::new(),
            proc_multipliers: Vec::new(),
            severities: crate::SeverityTable::new(),
            radixes: crate::RadixTable::new(),
            assign_ranks: crate::AssignRankTable::new(),
            queue_bounds: crate::QueueBoundTable::new(),
            proc_scopes: Vec::new(),
            cur_scope: "top".to_string(),
            threads: 1,
            backend: crate::Backend::Interpreter,
            vm_cache: (0..ir.processes.len())
                .map(|_| crate::backend::VmSlot::Unchecked)
                .collect(),
            cur_time_mult: 1,
            out,
            finished: false,
            had_error: false,
            had_fatal: false,
            sink,
            run_range_count: Cell::new(0),
            postponed: Postponed::default(),
        }
    }

    /// Stage-C VM dispatch (P0a): return the cached `CompiledBody` for template `tmpl`
    /// if it is codegen-able, compiling + caching on first sight; `None` ⇒ interpret.
    /// The decision is made ONCE per template (the per-fire `is_codegen_able` scan is
    /// removed). The returned `Rc` is an OWNED handle (cloned out of the cache) so the
    /// caller can pass `&mut self` as the `Kernel` to `vm_exec` without aliasing the
    /// cache — the §2.3 borrow protocol.
    pub(crate) fn vm_compiled(&mut self, tmpl: usize) -> Option<Rc<crate::backend::CompiledBody>> {
        use crate::backend::VmSlot;
        match &self.vm_cache[tmpl] {
            VmSlot::Compiled(rc) => return Some(Rc::clone(rc)),
            VmSlot::NotCodegenable => return None,
            VmSlot::Unchecked => {}
        }
        // `self.ir` is a `&SimIr` field — copy the reference out so the immutable read
        // of the IR does not borrow `self` across the `self.vm_cache` write below.
        let ir: &SimIr = self.ir;
        if !crate::backend::is_codegen_able(&ir.stmts, &ir.exprs, &ir.processes[tmpl].body) {
            self.vm_cache[tmpl] = VmSlot::NotCodegenable;
            return None;
        }
        let compiled = Rc::new(crate::backend::compile_body(
            &ir.stmts,
            &ir.processes[tmpl].body,
            Some((ir, &self.wt)),
        ));
        self.vm_cache[tmpl] = VmSlot::Compiled(Rc::clone(&compiled));
        Some(compiled)
    }

    /// Emit a rate-limited `E-RUN-RANGE` (VITA-E4002) runtime diagnostic for an
    /// out-of-range array word / select. The OOR is RECOVERED (read X / drop write),
    /// so the run still finishes; this only surfaces it. Capped at `CAP` per run with
    /// a final "further suppressed" note so a loop of OOR accesses can't spam.
    pub fn warn_run_range(&self, what: &str) {
        const CAP: u32 = 8;
        let n = self.run_range_count.get();
        let msg = match n.cmp(&CAP) {
            std::cmp::Ordering::Less => {
                Some(format!("{what} (out of range; read X / write ignored)"))
            }
            std::cmp::Ordering::Equal => {
                Some("further out-of-range diagnostics suppressed".to_string())
            }
            std::cmp::Ordering::Greater => None,
        };
        if let Some(message) = msg {
            self.sink.emit(LogEvent::Diagnostic(Diagnostic {
                severity: Severity::Error,
                code: MsgCode::RunRange,
                message,
                location: None,
                context: Vec::new(),
                sim_time: Some(diag::TimeStamp { ticks: self.now }),
            }));
        }
        self.run_range_count.set(n.saturating_add(1));
    }

    // ── reads ────────────────────────────────────────────────────────────

    // ── writes (single choke point) ──────────────────────────────────────

    /// Write `value` (any width) into the LHS chunks of `lhs`, MSB-first source
    /// consumption (Verilog concat-LHS). Returns true if ANY bit changed.
    ///
    /// `offsets[i]` is the already-EVALUATED bit offset of `lhs.chunks[i]` — the
    /// runtime value of a dynamic index (`a[i]`) or the const for `a[3]`; ignored
    /// for a whole-net/`None` chunk. The caller resolves these at the correct
    /// sampling moment (statement time for blocking, SAMPLE time for NBA so
    /// `a[i] <= x; i = i+1;` uses the OLD `i`, settle time for cont-assign),
    /// because this `&mut self` path has no read-only `EvalCtx`.
    pub fn write_lvalue(
        &mut self,
        lhs: &Lvalue,
        value: Value,
        offsets: &crate::exec::Offsets,
    ) -> bool {
        // ── real↔int assignment coercion (IEEE 1364 §6.2) ──
        // Only a WHOLE-NET lvalue (single Bit chunk, no offset/width) can be a
        // real destination: a real is dimensionless and never bit/part-selected
        // (§6.2 makes r[i]/r[hi:lo] illegal at elaborate). Detect the whole-net
        // case and consult NetSlot.is_real.
        let dest_is_real = lhs.chunks.len() == 1
            && matches!(lhs.chunks[0].kind, SelKind::Bit)
            && lhs.chunks[0].offset.is_none()
            && lhs.chunks[0].width.is_none()
            && self.nets[lhs.chunks[0].net as usize].is_real;

        let value = match (dest_is_real, value.is_real) {
            // real net ← real value: store verbatim (already 64 IEEE bits).
            (true, true) => value,
            // real net ← integer value (int→real CONVERT): exact for ≤53-bit.
            (true, false) => Value::from_f64(value.to_f64().unwrap_or(0.0)),
            // integer net ← real value (real→int ASSIGNMENT: ROUND half-away).
            // A real RHS only legally targets a whole scalar int net (concat-LHS
            // of a real is illegal §6.2). Round to that net's width; for the rare
            // multi-chunk case round to the total LHS width.
            (false, true) => {
                let w = if lhs.chunks.len() == 1 {
                    self.nets[lhs.chunks[0].net as usize].width
                } else {
                    lhs.chunks.iter().map(|c| self.chunk_width(c)).sum()
                };
                let signed = lhs.chunks.len() == 1 && self.nets[lhs.chunks[0].net as usize].signed;
                crate::value::real_to_int_round(value.to_f64().unwrap_or(0.0), w.max(1), signed)
            }
            // integer net ← integer value: unchanged legacy path.
            (false, false) => value,
        };

        // ── v5 ⑤: assoc-element lane (single chunk, i64 key) ──
        // The key cannot ride the u32 pairs; `resolve_lvalue_offsets` claims
        // the shape and the funnel splits here, AFTER the real coercion (an
        // assoc element gets the same real→int rounding as a dyn element).
        if let crate::exec::Offsets::AssocKey(key) = offsets {
            if let Some(c) = lhs.chunks.first() {
                self.assoc_write(c.net, *key, &value);
            }
            return false; // dyn content never enters the dirty channel
        }
        // v6: the string-keyed twin lane.
        if let crate::exec::Offsets::AssocStrKey(key) = offsets {
            if let Some(c) = lhs.chunks.first() {
                self.assoc_str_write(c.net, key, &value);
            }
            return false;
        }
        let offsets = offsets.as_slice();
        debug_assert_eq!(
            offsets.len(),
            lhs.chunks.len(),
            "one (offset,word) per chunk"
        );

        // v7 P2-C: a STRING destination takes the WHOLE source value — its
        // net-table width is 0 (dynamic), so the total-width resize below
        // would chop the value to 1 bit; §6.16 conversion is dyn_write's
        // byte-strip, never a bit resize.
        if let [c] = lhs.chunks.as_slice() {
            if self.ir.nets[c.net as usize].kind == NetKind::String {
                let (raw_off, raw_word) = offsets.first().copied().unwrap_or((0, 0));
                return self.write_chunk(c, raw_off, raw_word, &value);
            }
        }
        // Total destination bit width = sum of chunk widths.
        let total: u32 = lhs.chunks.iter().map(|c| self.chunk_width(c)).sum();
        let src = value.resize(total.max(1));

        // Single-chunk LHS — the dominant case (a whole net, or a single bit-/part-
        // select). With one chunk, `take_lo == 0` and `cw == total`, so the sliced
        // "piece" IS `src` exactly; skip the per-bit slice entirely and hand `src`
        // straight to `write_chunk` (which word-writes the whole-net/aligned case). The
        // per-bit slice loop below is only for a multi-chunk concat LHS (`{a,b} = x`).
        if lhs.chunks.len() == 1 {
            let (raw_off, raw_word) = offsets.first().copied().unwrap_or((0, 0));
            return self.write_chunk(&lhs.chunks[0], raw_off, raw_word, &src);
        }

        let mut changed = false;
        let mut src_hi = total; // next source bit (exclusive top)
        for (idx, chunk) in lhs.chunks.iter().enumerate() {
            let cw = self.chunk_width(chunk);
            let take_lo = src_hi.saturating_sub(cw);
            // slice src[take_lo .. src_hi) → low-aligned chunk value
            let mut piece = Value::zeros(cw.max(1), false);
            piece.width = cw;
            for i in 0..cw {
                let (v, u) = src.get_vu(take_lo + i);
                piece.set_vu(i, v, u);
            }
            src_hi = take_lo;
            let (raw_off, raw_word) = offsets.get(idx).copied().unwrap_or((0, 0));
            changed |= self.write_chunk(chunk, raw_off, raw_word, &piece);
        }
        changed
    }

    /// Width (in bits) a single lvalue chunk writes.
    fn chunk_width(&self, c: &sim_ir::LvalChunk) -> u32 {
        match c.kind {
            // whole-net write: offset/width None.
            SelKind::Bit => {
                if c.offset.is_none() && c.width.is_none() {
                    self.nets[c.net as usize].width
                } else {
                    1
                }
            }
            SelKind::PartConst | SelKind::PartIdxUp | SelKind::PartIdxDown => {
                // `c.width` is an ExprId (frozen IR: a const-expr edge like
                // `Add(Sub(msb,lsb),1)`), NOT a literal — fold it to its value.
                c.width
                    .and_then(|eid| crate::width::const_u32_of_expr(self.ir, eid))
                    .unwrap_or_else(|| self.nets[c.net as usize].width)
            }
        }
    }

    /// Total destination bit-width of an lvalue (Σ chunk widths). Used to seed
    /// the RHS context width. Does NOT compute a sign — lhs sign never
    /// propagates (IEEE 1364-2005 assignment rule, §5.5).
    pub(crate) fn lvalue_width(&self, lhs: &Lvalue) -> u32 {
        lhs.chunks
            .iter()
            .map(|c| self.chunk_width(c))
            .sum::<u32>()
            .max(1)
    }

    /// Write a low-aligned `piece` into the destination chunk. `raw_off` is the
    /// already-EVALUATED `c.offset` (the runtime index for `a[i]`, the const for
    /// `a[3]`; ignored for a whole-net chunk). Returns changed.
    fn write_chunk(
        &mut self,
        c: &sim_ir::LvalChunk,
        raw_off: u32,
        raw_word: u32,
        piece: &Value,
    ) -> bool {
        let net = c.net as usize;
        // v5 (C)-3b: dyn-handle element write → heap (never the flat store).
        if self.dyn_is_handle[net] {
            return self.dyn_write(c, raw_word, piece);
        }
        // A forced net ignores every normal driver until release (§9.3.2).
        if self.forced[net] {
            return false;
        }
        // `c.word` is an ExprId; `raw_word` is the caller-evaluated array index
        // (the runtime `k` of `mem[k] = …`). None ⇒ index 0. An out-of-range word
        // write is IGNORED (spec E-RUN-RANGE) — clamping to the last element would
        // silently corrupt a valid neighbor.
        let word = if c.word.is_some() {
            if raw_word >= self.nets[net].array_len {
                self.warn_run_range("array word index");
                return false;
            }
            raw_word
        } else {
            0
        };
        let net_w = self.nets[net].width;
        let base = word * net_w; // bit offset of this array element

        // `c.width` is a const-expr edge (part-select bounds are constant); fold
        // it. `c.offset` was evaluated by the caller (dynamic-index capable) and
        // arrives as `raw_off`, symmetric with the runtime offset eval that
        // `eval_select` already does on the READ side.
        let ir = self.ir;
        let fold = |eid: u32| crate::width::const_u32_of_expr(ir, eid);
        let (off, width) = match c.kind {
            SelKind::Bit => {
                if c.offset.is_none() && c.width.is_none() {
                    (0, net_w) // whole net
                } else {
                    (raw_off, 1)
                }
            }
            SelKind::PartConst | SelKind::PartIdxUp => {
                (raw_off, c.width.and_then(fold).unwrap_or(net_w))
            }
            SelKind::PartIdxDown => {
                let w = c.width.and_then(fold).unwrap_or(net_w);
                (raw_off.saturating_sub(w.saturating_sub(1)), w)
            }
        };

        let slot = &mut self.nets[net];

        // WORD-PARALLEL fast path: a whole-element write to a 64-aligned destination
        // (every scalar whole-net assign, plus array elements whose width is a multiple
        // of 64). Copy `piece`'s words into the store with word-granular change detection
        // + a top-word mask, replacing the per-bit `set_bit` loop. Guard:
        // `array_len <= 1 || net_w % 64 == 0` guarantees the element occupies WHOLE store
        // words, so masking the top word cannot clobber a neighbouring element packed in
        // the same word. Everything else (part/bit-select, unaligned base, OOR) falls
        // through to the proven bit-serial path below — byte-identical by construction.
        if off == 0 && width == net_w && base % 64 == 0 && (slot.array_len <= 1 || net_w % 64 == 0)
        {
            let wbase = (base / 64) as usize;
            let nw = nwords(net_w).max(1);
            let m = top_mask(net_w);
            let mut changed = false;
            for k in 0..nw {
                let mut nv = piece.val.get(k).copied().unwrap_or(0);
                let mut nu = piece.unk.get(k).copied().unwrap_or(0);
                if k == nw - 1 {
                    nv &= m;
                    nu &= m;
                }
                let idx = wbase + k;
                if slot.cur.val.len() <= idx {
                    slot.cur.val.resize(idx + 1, 0);
                    slot.cur.unk.resize(idx + 1, 0);
                }
                if slot.cur.val[idx] != nv || slot.cur.unk[idx] != nu {
                    slot.cur.val[idx] = nv;
                    slot.cur.unk[idx] = nu;
                    changed = true;
                }
            }
            if changed {
                self.note_change(net as u32, word);
            }
            return changed;
        }

        let mut changed = false;
        for i in 0..width {
            // saturating: a `u32::MAX` sentinel offset (X/Z dynamic index) or any
            // out-of-range index drops the bit cleanly instead of overflowing.
            let dst = off.saturating_add(i);
            if dst >= net_w {
                continue; // out-of-range bit drop (v1 RunRange simplification)
            }
            let (v, u) = piece.get_vu(i);
            if set_bit(&mut slot.cur, base + dst, v, u) {
                changed = true;
            }
        }
        if changed {
            self.note_change(net as u32, word);
        }
        changed
    }

    /// Record an ACTUAL bit change on `net`: mark it for the next
    /// `propagate_changes` dirty sweep, then emit the VCD record. This is the
    /// single funnel both `write_chunk` exit paths use — any future mutation
    /// path MUST route through it or the sweep goes blind.
    fn note_change(&mut self, net: u32, word: u32) {
        let i = net as usize;
        if !self.dirty_flag[i] {
            self.dirty_flag[i] = true;
            self.dirty.push(net);
        }
        self.emit_vcd_change(net, word);
    }

    /// Emit a VCD value_change for the net word that changed. Arrays carry one
    /// id PER ELEMENT (Phase-1.x ⑤ — the v1 VCD only ever showed word 0);
    /// scalars keep the single `vcd_id`.
    fn emit_vcd_change(&mut self, net: u32, word: u32) {
        if !self.dumping {
            return;
        }
        let i = net as usize;
        let width = self.nets[i].width;
        let id = if self.nets[i].vcd_word_ids.is_empty() {
            match self.nets[i].vcd_id {
                Some(id) => id,
                None => return,
            }
        } else {
            match self.nets[i].vcd_word_ids.get(word as usize) {
                Some(Some(id)) => *id,
                _ => return,
            }
        };
        let packed = slice_word(&self.nets[i].cur, width, word);
        if let Some(w) = self.vcd.as_mut() {
            let _ = w.set_time(self.now);
            let _ = w.value_change(id, &packed, width);
        }
    }

    // ── edge support ─────────────────────────────────────────────────────

    // (R2) The former `snapshot_prev` full-net cur→prev copy at each time
    // advance was DELETED: at the settled point `prev == cur` holds for every
    // net by induction — the only `prev` writers are `propagate_changes`
    // step (c) and the constructor, both setting prev = cur — so the pass was
    // a provable no-op costing O(nets) per timestep. Byte-compare suites
    // (staged/threads/corpus/differential) pin the equivalence.

    // ── force / release (IEEE 1364 §9.3.2; expression forces re-evaluate
    //    continuously via the scheduler's active_forces registry) ─────────

    /// Apply `force lhs = value`: write THROUGH the force flag (a re-force on
    /// an already-forced net must land), then pin the net. `lhs` is a single
    /// whole-net chunk (elaborate-validated).
    pub fn force_write(&mut self, lhs: &Lvalue, value: Value) -> bool {
        let net = lhs.chunks[0].net as usize;
        self.forced[net] = false;
        let offs = crate::exec::Offsets::Inline {
            buf: [(0, 0); 2],
            len: 1,
        };
        let changed = self.write_lvalue(lhs, value, &offs);
        self.forced[net] = true;
        changed
    }

    /// `release lhs`: unpin. A NET target snaps back to its driver at the next
    /// cont-assign settle (same timestep — the run loop settles every delta);
    /// a VARIABLE keeps the forced value until the next procedural assignment
    /// (no settle entry exists for it) — both fall out of just clearing the flag.
    pub fn release(&mut self, lhs: &Lvalue) {
        self.forced[lhs.chunks[0].net as usize] = false;
    }

    // ── VCD lifecycle (driven by $dumpfile/$dumpvars) ────────────────────

    pub fn open_vcd(&mut self, sink: VcdSink) {
        self.vcd = Some(VcdWriter::new(sink));
    }

    pub fn finalize_vcd(&mut self) {
        if let Some(w) = self.vcd.as_mut() {
            // P2-2: a failed final flush means a truncated waveform — say so
            // (was: `let _ =` swallowed it; exit stayed 0 with no message).
            if let Err(e) = w.flush() {
                self.sink.emit(LogEvent::Diagnostic(Diagnostic {
                    severity: Severity::Warning,
                    code: MsgCode::RunVcdWriteFail,
                    message: format!("VCD flush failed: {e}"),
                    location: None,
                    context: Vec::new(),
                    sim_time: Some(diag::TimeStamp { ticks: self.now }),
                }));
            }
        }
    }
}

/// Shared element-count cap for dynamic storage (same hazard class as
/// elaborate's `MAX_ARRAY_LEN`, P2-6): a runtime OOM from `new[huge]` or a
/// runaway push loop is as silent-deadly as the t0 one. NO silent caps — every
/// clamp/drop warns (W4020, once per net).
pub(crate) const MAX_DYN_ELEMS: usize = 1 << 24;

/// v5 (C): one dynamic-storage object. Engine-internal RUNTIME state — never
/// serialized, never in the frozen IR (design doc 2026-06-10 §2).
#[derive(Debug, Clone)]
pub enum DynObj {
    /// `int d[]` — element values, length set only by `new[n]`/`delete()`.
    DynArray { elems: Vec<Value> },
    /// `int q[$]` — pushes/pops at both ends, `q[size] = v` appends (§7.10.1).
    Queue {
        elems: std::collections::VecDeque<Value>,
    },
    /// `int a[longint]` — signed-i64 key domain (⑥ elaborate casts the surface
    /// key type before the IR). BTree = deterministic order for any future
    /// iteration/dump surface (first/next land post-MVP for free).
    Assoc {
        map: std::collections::BTreeMap<i64, Value>,
    },
    /// v7 P2-C `string s` — raw bytes (a missing entry IS "" — lazy, like
    /// every dyn object).
    Str { bytes: Vec<u8> },
    /// `int a[string]` (v6) — raw-byte-string keys (leading-0x00-stripped
    /// packed ASCII). BTree byte order = IEEE lexicographic string compare,
    /// so first/next iterate in the §7.9.4 order for free.
    AssocStr {
        map: std::collections::BTreeMap<Vec<u8>, Value>,
    },
}

impl DynObj {
    pub fn len(&self) -> usize {
        match self {
            DynObj::DynArray { elems } => elems.len(),
            DynObj::Queue { elems } => elems.len(),
            DynObj::Assoc { map } => map.len(),
            DynObj::AssocStr { map } => map.len(),
            DynObj::Str { bytes } => bytes.len(),
        }
    }
    /// Clippy pairing for `len`.
    #[allow(dead_code)]
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

impl<'a> SimState<'a> {
    /// One W-RUN-DYN-DEGRADE per handle net, callable from `&self` (read path).
    pub(crate) fn dyn_warn_once_at(&self, net: u32, msg: &str) {
        if !self.dyn_warned.borrow_mut().insert(net) {
            return;
        }
        self.sink.emit(LogEvent::Diagnostic(Diagnostic {
            severity: Severity::Warning,
            code: MsgCode::RunDynDegrade,
            message: msg.to_string(),
            location: None,
            context: Vec::new(),
            sim_time: Some(TimeStamp { ticks: self.now }),
        }));
    }

    /// v5 (C)-3b: indexed READ of a dyn handle. `idx` is the caller-resolved
    /// word (X/Z or >u32 already mapped to the `u32::MAX` sentinel — the same
    /// rule as static arrays). OOB / X-index / empty / whole-handle reads are
    /// element-width X + warn-once (IEEE: the element default; our elements
    /// are 4-state).
    fn dyn_read(&self, net: u32, idx: Option<u32>) -> Value {
        let nv = &self.ir.nets[net as usize];
        let (w, signed) = (nv.width.max(1), nv.signed);
        let xs = || Value::xs(w, signed);
        let Some(i) = idx else {
            // v7 P2-C: a STRING handle's whole-value read IS its packed
            // materialization (8×len, is_str — context resizing bypassed).
            if nv.kind == NetKind::String {
                let bytes: &[u8] = match self.dyn_heap.get(&net) {
                    Some(DynObj::Str { bytes }) => bytes,
                    _ => &[],
                };
                return Value::from_str_bytes(bytes);
            }
            // a handle has no scalar value surface (elaborate guards at ⑥;
            // defensive here — e.g. a hand-built IR or future regression).
            self.dyn_warn_once_at(net, "dyn handle read without an index");
            return xs();
        };
        match self.dyn_heap.get(&net) {
            Some(DynObj::DynArray { elems }) if (i as usize) < elems.len() => {
                elems[i as usize].clone()
            }
            Some(DynObj::Queue { elems }) if (i as usize) < elems.len() => {
                elems[i as usize].clone()
            }
            _ => {
                self.dyn_warn_once_at(net, "dyn index out of range or X (read X)");
                xs()
            }
        }
    }

    /// v5 (C)-3b/④: indexed WRITE of a dyn handle. Shared rules: X-index /
    /// bit-select within an element → IGNORED + warn-once (clamping or
    /// auto-grow would silently corrupt). Kind split (iverilog live):
    /// dyn array — any OOB → IGNORED + warn; queue — `q[size] = v` is
    /// push_back-equivalent (IEEE §7.10.1, legal and SILENT, grows by one),
    /// beyond that → IGNORED + warn.
    /// Returns false ALWAYS: dyn content changes do not participate in the net
    /// dirty channel (design §4 — no sensitivity on handles, no VCD records).
    fn dyn_write(&mut self, c: &sim_ir::LvalChunk, raw_word: u32, piece: &Value) -> bool {
        let net = c.net;
        let w = self.ir.nets[net as usize].width.max(1);
        // v7 P2-C: STRING whole-handle assignment — strip leading NULs from
        // the packed value (§6.16) and store the bytes. The only legal
        // string lvalue shape; anything narrower falls to the loud arm.
        if self.ir.nets[net as usize].kind == NetKind::String
            && c.word.is_none()
            && c.offset.is_none()
            && c.width.is_none()
        {
            let bytes = piece.to_str_bytes();
            self.dyn_heap.insert(net, DynObj::Str { bytes });
            return false; // no net dirty channel (design §4, dyn precedent)
        }
        if c.word.is_none() || c.offset.is_some() || c.width.is_some() {
            self.dyn_warn_once_at(net, "unsupported dyn lvalue shape (write ignored)");
            return false;
        }
        // ⑤/v6: an assoc element on the u32 pair funnel = a shape the
        // AssocKey/AssocStrKey lane did not claim (a concat chunk, …) —
        // outside the MVP, IGNORED loud. The single-chunk lane
        // (`write_lvalue`) never reaches here.
        if matches!(
            self.ir.nets[net as usize].kind,
            NetKind::Assoc | NetKind::AssocStr
        ) {
            self.dyn_warn_once_at(
                net,
                "assoc element write in an unsupported lvalue shape (ignored)",
            );
            return false;
        }
        let i = raw_word as usize;
        if self.ir.nets[net as usize].kind == NetKind::Queue {
            // A missing entry IS the empty queue: the append lane must be
            // reachable on a never-touched handle (`q[0] = v` creates it).
            let DynObj::Queue { elems } =
                self.dyn_heap.entry(net).or_insert_with(|| DynObj::Queue {
                    elems: std::collections::VecDeque::new(),
                })
            else {
                return false; // kind-mismatched entry: unreachable by construction
            };
            let len = elems.len();
            match i.cmp(&len) {
                std::cmp::Ordering::Less => elems[i] = piece.clone().resize(w),
                // The u32::MAX X-sentinel can never land in the Equal arm:
                // len ≤ the cap, far below the sentinel.
                std::cmp::Ordering::Equal if len < MAX_DYN_ELEMS => {
                    elems.push_back(piece.clone().resize(w));
                    self.enforce_queue_bound(net); // v6 ③ (no-op when unbounded)
                }
                std::cmp::Ordering::Equal => self.dyn_warn_once_at(
                    net,
                    "queue exceeds the element cap (1<<24); write-append dropped",
                ),
                std::cmp::Ordering::Greater => {
                    self.dyn_warn_once_at(net, "queue index beyond size or X (write ignored)");
                }
            }
            return false;
        }
        match self.dyn_heap.get_mut(&net) {
            Some(DynObj::DynArray { elems }) if i < elems.len() => {
                elems[i] = piece.clone().resize(w);
                false
            }
            _ => {
                self.dyn_warn_once_at(net, "dyn index out of range or X (write ignored)");
                false
            }
        }
    }

    /// v5 ⑤: assoc-element WRITE (`a[k] = v`) — the `Offsets::AssocKey` lane.
    /// `None` key = X/Z (invalid index, IEEE §7.8.6): IGNORED + warn-once. A
    /// missing key CREATES the element (§7.8); the value is cast to the
    /// element type (the same `resize(w)` as every other dyn store). Inserts
    /// past the shared cap warn + drop (no silent caps).
    pub(crate) fn assoc_write(&mut self, net: u32, key: Option<i64>, value: &Value) {
        let w = self.ir.nets[net as usize].width.max(1);
        let Some(k) = key else {
            self.dyn_warn_once_at(net, "assoc key is X/Z (write ignored)");
            return;
        };
        // Cap BEFORE the entry borrow (the warn latch needs `&self` while the
        // map borrow holds `&mut self`); replacing an existing key is exempt.
        let (len, exists) = match self.dyn_heap.get(&net) {
            Some(DynObj::Assoc { map }) => (map.len(), map.contains_key(&k)),
            _ => (0, false),
        };
        if !exists && len >= MAX_DYN_ELEMS {
            self.dyn_warn_once_at(net, "assoc exceeds the element cap (1<<24); write dropped");
            return;
        }
        // A missing entry IS the empty assoc (lazy, like every dyn object).
        let entry = self.dyn_heap.entry(net).or_insert_with(|| DynObj::Assoc {
            map: std::collections::BTreeMap::new(),
        });
        if let DynObj::Assoc { map } = entry {
            map.insert(k, value.clone().resize(w));
        }
    }

    /// v6: string-keyed assoc WRITE — the `Offsets::AssocStrKey` lane (the
    /// byte-string twin of `assoc_write`; same X-key / cap / create rules).
    pub(crate) fn assoc_str_write(&mut self, net: u32, key: &Option<Vec<u8>>, value: &Value) {
        let w = self.ir.nets[net as usize].width.max(1);
        let Some(k) = key else {
            self.dyn_warn_once_at(net, "assoc key is X/Z (write ignored)");
            return;
        };
        let (len, exists) = match self.dyn_heap.get(&net) {
            Some(DynObj::AssocStr { map }) => (map.len(), map.contains_key(k)),
            _ => (0, false),
        };
        if !exists && len >= MAX_DYN_ELEMS {
            self.dyn_warn_once_at(net, "assoc exceeds the element cap (1<<24); write dropped");
            return;
        }
        let entry = self
            .dyn_heap
            .entry(net)
            .or_insert_with(|| DynObj::AssocStr {
                map: std::collections::BTreeMap::new(),
            });
        if let DynObj::AssocStr { map } = entry {
            map.insert(k.clone(), value.clone().resize(w));
        }
    }

    /// v6 ③: bounded-queue post-op rule (iverilog live, IEEE §7.10):
    /// whatever the op left beyond size N+1 falls off the TAIL — one rule
    /// reproduces push_back-on-full (= skip), push_front-on-full (back
    /// drops) and insert-on-full (back drops). Loud (W4020 once per net).
    pub(crate) fn enforce_queue_bound(&mut self, net: u32) {
        let Some(&b) = self.queue_bounds.get(&net) else {
            return;
        };
        let cap = b as usize + 1;
        let mut dropped = false;
        if let Some(DynObj::Queue { elems }) = self.dyn_heap.get_mut(&net) {
            while elems.len() > cap {
                elems.pop_back();
                dropped = true;
            }
        }
        if dropped {
            self.dyn_warn_once_at(
                net,
                "bounded queue exceeded its bound; tail element(s) dropped",
            );
        }
    }
}

impl<'a> NetReader for SimState<'a> {
    fn dyn_size(&self, net: u32) -> Option<u64> {
        // Only a dyn HANDLE answers; a missing heap entry IS the empty object
        // (size 0 — IEEE: a declared dynamic array/queue/assoc starts empty).
        // Assoc included: `size()` is the IEEE alias of `num()` (§7.9.1). Any
        // other net kind returns None → the eval arm X-poisons defensively.
        match self.ir.nets.get(net as usize).map(|n| n.kind) {
            Some(
                sim_ir::NetKind::DynArray
                | sim_ir::NetKind::Queue
                | sim_ir::NetKind::Assoc
                | sim_ir::NetKind::AssocStr,
            ) => Some(self.dyn_heap.get(&net).map(|o| o.len() as u64).unwrap_or(0)),
            _ => None,
        }
    }
    fn dyn_warn(&self, net: u32, msg: &str) {
        // The eval-side degradation hook (e.g. a pop outside its statement
        // intercept) — same W4020 once-per-net latch as every other lane.
        self.dyn_warn_once_at(net, msg);
    }
    fn is_assoc(&self, net: u32) -> bool {
        // Bitmap first: the static-array hot path short-circuits on one bit
        // load (the same budget `read_net` already pays), only real handles
        // pay the kind lookup.
        self.dyn_is_handle
            .get(net as usize)
            .copied()
            .unwrap_or(false)
            && matches!(
                self.ir.nets.get(net as usize).map(|n| n.kind),
                Some(sim_ir::NetKind::Assoc)
            )
    }
    fn assoc_read(&self, net: u32, key: Option<i64>) -> Value {
        let (w, signed) = self
            .ir
            .nets
            .get(net as usize)
            .map(|nv| (nv.width.max(1), nv.signed))
            .unwrap_or((1, false));
        let Some(k) = key else {
            // X/Z key = invalid index (IEEE §7.8.6): element-width X + warn.
            self.dyn_warn_once_at(net, "assoc key is X/Z (read X)");
            return Value::xs(w, signed);
        };
        match self.dyn_heap.get(&net) {
            Some(DynObj::Assoc { map }) => map.get(&k).cloned().unwrap_or_else(|| {
                self.dyn_warn_once_at(net, "assoc key not found (read X)");
                Value::xs(w, signed)
            }),
            // A missing entry IS the empty assoc — every key is "not found".
            _ => {
                self.dyn_warn_once_at(net, "assoc key not found (read X)");
                Value::xs(w, signed)
            }
        }
    }
    fn assoc_exists(&self, net: u32, key: Option<i64>) -> Option<bool> {
        if !self.is_assoc(net) {
            return None; // not an assoc handle → the eval arm X-poisons
        }
        let Some(k) = key else {
            // exists() with an X/Z key matches nothing — 0, but LOUD (the
            // same invalid-index family as read/write, policy pin).
            self.dyn_warn_once_at(net, "assoc key is X/Z (exists 0)");
            return Some(false);
        };
        Some(match self.dyn_heap.get(&net) {
            Some(DynObj::Assoc { map }) => map.contains_key(&k),
            _ => false,
        })
    }
    fn str_bytes(&self, net: u32) -> Option<Vec<u8>> {
        if self.ir.nets.get(net as usize).map(|n| n.kind) != Some(NetKind::String) {
            return None;
        }
        Some(match self.dyn_heap.get(&net) {
            Some(DynObj::Str { bytes }) => bytes.clone(),
            _ => Vec::new(),
        })
    }
    fn is_assoc_str(&self, net: u32) -> bool {
        self.dyn_is_handle
            .get(net as usize)
            .copied()
            .unwrap_or(false)
            && matches!(
                self.ir.nets.get(net as usize).map(|n| n.kind),
                Some(sim_ir::NetKind::AssocStr)
            )
    }
    fn assoc_str_read(&self, net: u32, key: &Option<Vec<u8>>) -> Value {
        let (w, signed) = self
            .ir
            .nets
            .get(net as usize)
            .map(|nv| (nv.width.max(1), nv.signed))
            .unwrap_or((1, false));
        let Some(k) = key else {
            self.dyn_warn_once_at(net, "assoc key is X/Z (read X)");
            return Value::xs(w, signed);
        };
        match self.dyn_heap.get(&net) {
            Some(DynObj::AssocStr { map }) => map.get(k).cloned().unwrap_or_else(|| {
                self.dyn_warn_once_at(net, "assoc key not found (read X)");
                Value::xs(w, signed)
            }),
            _ => {
                self.dyn_warn_once_at(net, "assoc key not found (read X)");
                Value::xs(w, signed)
            }
        }
    }
    fn assoc_str_exists(&self, net: u32, key: &Option<Vec<u8>>) -> Option<bool> {
        if !self.is_assoc_str(net) {
            return None;
        }
        let Some(k) = key else {
            self.dyn_warn_once_at(net, "assoc key is X/Z (exists 0)");
            return Some(false);
        };
        Some(match self.dyn_heap.get(&net) {
            Some(DynObj::AssocStr { map }) => map.contains_key(k),
            _ => false,
        })
    }
    fn read_net(&self, net: u32, word: Option<u32>) -> Value {
        // v5 (C)-3b: a dyn HANDLE never reads the flat store — its elements
        // live in the heap. One bitmap load on the hot path.
        if self.dyn_is_handle[net as usize] {
            return self.dyn_read(net, word);
        }
        let slot = &self.nets[net as usize];
        let width = slot.width;
        let w = word.unwrap_or(0);
        // Out-of-range array word reads all-X (spec E-RUN-RANGE) — NOT a clamp to the
        // last element (which would silently return a neighbour's value).
        if w >= slot.array_len {
            self.warn_run_range("array word index");
            let mut v = Value::xs(width.max(1), slot.signed);
            v.width = width;
            v.is_real = slot.is_real;
            return v;
        }
        // Read the element DIRECTLY into an inline `Value` — no transient `BitPacked`
        // Vec (the prior `net_word_packed → slice_word → BitPacked → from_packed` path
        // allocated two Vecs per read just to copy them into the inline planes). The
        // word-aligned fast path (every scalar net + 64-aligned array element) copies
        // whole store words; an unaligned base (non-64 array element) falls to bit-serial.
        let base = w * width;
        let n = nwords(width).max(1);
        let mut v = if base % 64 == 0 {
            let wbase = (base / 64) as usize;
            let mut val = Words::zeros(n);
            let mut unk = Words::zeros(n);
            for k in 0..n {
                val[k] = slot.cur.val.get(wbase + k).copied().unwrap_or(0);
                unk[k] = slot.cur.unk.get(wbase + k).copied().unwrap_or(0);
            }
            let m = top_mask(width);
            val[n - 1] &= m;
            unk[n - 1] &= m;
            Value {
                val,
                unk,
                width,
                signed: slot.signed,
                is_real: false,
                is_str: false,
            }
        } else {
            let mut tmp = Value::zeros(width.max(1), slot.signed);
            tmp.width = width;
            for i in 0..width {
                let (vv, uu) = bit_of(&slot.cur, base + i);
                tmp.set_vu(i, vv, uu);
            }
            tmp
        };
        v.is_real = slot.is_real; // flag the read-back as real (val[0] = IEEE bits)
        v
    }
}

// ── free helpers ───────────────────────────────────────────────────────────

/// v7 RNG state cells (see `SimState::rng`).
#[derive(Default)]
pub(crate) struct RngCells {
    /// `$random` Annex-N LCG seed (global generator, like iverilog's).
    pub random: std::cell::Cell<u32>,
    /// `$urandom` splitmix64 state (vitamin-pinned sequence).
    pub urandom: std::cell::Cell<u64>,
}

/// NetKind → VCD VarType.
pub(crate) fn vcd_var_type(kind: NetKind) -> VarType {
    match kind {
        NetKind::Reg => VarType::Reg,
        NetKind::Integer => VarType::Integer,
        NetKind::Real => VarType::Real, // VCD `$var real`
        NetKind::Wire | NetKind::Logic => VarType::Wire,
        // v5/v6/v7 dyn + string handles are NEVER declared to the VCD (design
        // doc: variable length has no $var form) — filtered upstream; defensive map.
        NetKind::DynArray
        | NetKind::Queue
        | NetKind::Assoc
        | NetKind::AssocStr
        | NetKind::String => VarType::Wire,
    }
}

/// Build a net's storage from its declared init. For scalars the init IS the
/// value; for arrays the init plane is replicated per word (elaborate emits one
/// init plane; v1 broadcasts it to every element).
fn expand_init(init: &BitPacked, width: u32, array_len: u32, total_bits: usize) -> BitPacked {
    let total_words = nwords(total_bits as u32).max(1);
    if array_len <= 1 {
        let mut val = init.val.clone();
        let mut unk = init.unk.clone();
        val.resize(total_words, 0);
        unk.resize(total_words, 0);
        return BitPacked { val, unk };
    }
    // broadcast the width-wide init to each element
    let mut out = BitPacked {
        val: vec![0; total_words],
        unk: vec![0; total_words],
    };
    let elem = Value::from_packed(init, width, false);
    for w in 0..array_len {
        let base = w * width;
        for i in 0..width {
            let (v, u) = elem.get_vu(i);
            set_bit(&mut out, base + i, v, u);
        }
    }
    out
}

/// Slice `width` bits starting at word `word`*width from a packed store.
fn slice_word(store: &BitPacked, width: u32, word: u32) -> BitPacked {
    let base = word * width;
    // WORD-PARALLEL fast path: a 64-aligned element read — copy whole store words and
    // mask the top partial word (which discards any neighbouring element's bits that
    // share that word). Covers every scalar net (base 0) and 64-aligned array elements;
    // an unaligned base (array element with a non-64-aligned offset) falls to bit-serial.
    if base % 64 == 0 {
        let n = nwords(width).max(1);
        let wbase = (base / 64) as usize;
        let mut val = vec![0u64; n];
        let mut unk = vec![0u64; n];
        for k in 0..n {
            val[k] = store.val.get(wbase + k).copied().unwrap_or(0);
            unk[k] = store.unk.get(wbase + k).copied().unwrap_or(0);
        }
        let m = top_mask(width);
        val[n - 1] &= m;
        unk[n - 1] &= m;
        return BitPacked { val, unk };
    }
    let mut tmp = Value::zeros(width.max(1), false);
    tmp.width = width;
    for i in 0..width {
        let (v, u) = bit_of(store, base + i);
        tmp.set_vu(i, v, u);
    }
    tmp.into_bitpacked(width)
}

#[inline]
fn bit_of(b: &BitPacked, i: u32) -> (u64, u64) {
    let w = (i / 64) as usize;
    let s = i % 64;
    let v = b.val.get(w).map_or(0, |x| (x >> s) & 1);
    let u = b.unk.get(w).map_or(0, |x| (x >> s) & 1);
    (v, u)
}

/// Set bit `i` of a packed store to (v,u); grow as needed; return true if changed.
#[inline]
fn set_bit(b: &mut BitPacked, i: u32, v: u64, u: u64) -> bool {
    let w = (i / 64) as usize;
    let s = i % 64;
    while b.val.len() <= w {
        b.val.push(0);
    }
    while b.unk.len() <= w {
        b.unk.push(0);
    }
    let ov = (b.val[w] >> s) & 1;
    let ou = (b.unk[w] >> s) & 1;
    if ov == v && ou == u {
        return false;
    }
    b.val[w] = (b.val[w] & !(1 << s)) | ((v & 1) << s);
    b.unk[w] = (b.unk[w] & !(1 << s)) | ((u & 1) << s);
    true
}

/// Scalar (bit0) 4-state of a net's current value — for edge detection.
pub(crate) fn scalar_bit0(b: &BitPacked) -> sim_ir::FourState {
    let v = b.val.first().copied().unwrap_or(0) & 1;
    let u = b.unk.first().copied().unwrap_or(0) & 1;
    match (v, u) {
        (0, 0) => sim_ir::FourState::Zero,
        (1, 0) => sim_ir::FourState::One,
        (0, 1) => sim_ir::FourState::X,
        _ => sim_ir::FourState::Z,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// P2-2: a VCD flush failure at finalize must surface as W-RUN-VCD-WRITE-FAIL
    /// (was: `let _ =` silently swallowed it — truncated VCD, zero diagnostics).
    #[test]
    fn finalize_vcd_flush_error_warns() {
        struct FailWriter;
        impl Write for FailWriter {
            fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
                Ok(buf.len()) // accept records...
            }
            fn flush(&mut self) -> std::io::Result<()> {
                Err(std::io::Error::other("disk full")) // ...but fail the flush
            }
        }
        #[derive(Default)]
        struct DiagSink(std::cell::RefCell<Vec<String>>);
        impl LogSink for DiagSink {
            fn emit(&self, e: LogEvent) {
                if let LogEvent::Diagnostic(d) = e {
                    self.0
                        .borrow_mut()
                        .push(format!("{}: {}", d.code.code_num(), d.message));
                }
            }
        }

        let (toks, _) = hdl_lexer::lex("module t; endmodule");
        let (su, _) = hdl_parser::parse(&toks, "module t; endmodule");
        let sink = DiagSink::default();
        let ir = elaborate::elaborate(&su.expect("unit"), &sink).expect("elaborate");
        let mut st = SimState::new(
            &ir,
            Box::new(std::io::sink()),
            &sink,
            "1ns".to_string(),
            "test".to_string(),
            None,
        );
        st.open_vcd(Box::new(FailWriter));
        st.finalize_vcd();
        let diags = sink.0.borrow();
        assert!(
            diags.iter().any(|d| d.starts_with("VITA-W4019")),
            "flush failure must emit W-RUN-VCD-WRITE-FAIL; got {diags:?}"
        );
    }
}
