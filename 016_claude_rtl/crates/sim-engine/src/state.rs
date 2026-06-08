//! Engine state: the net value table (+ previous-delta snapshot for edges),
//! VCD wiring, and the single net-write choke point with change detection.

use std::cell::Cell;
use std::io::Write;
use std::rc::Rc;

use diag::{Diagnostic, LogEvent, LogSink, MsgCode, Severity};
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
                }
            })
            .collect();
        let wt = crate::width::WidthTable::build(ir); // single forward pass
        SimState {
            ir,
            now: 0,
            nets,
            wt,
            vcd: None,
            vcd_path: None,
            dump_pending_path: None,
            vcd_path_override,
            dumping: false,
            timescale_unit,
            vcd_date,
            net_names: Vec::new(),
            proc_multipliers: Vec::new(),
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
        if !crate::backend::is_codegen_able(&ir.stmts, &ir.processes[tmpl].body) {
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
    pub fn write_lvalue(&mut self, lhs: &Lvalue, value: Value, offsets: &[(u32, u32)]) -> bool {
        debug_assert_eq!(
            offsets.len(),
            lhs.chunks.len(),
            "one (offset,word) per chunk"
        );
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
                self.emit_vcd_change(net as u32);
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
            self.emit_vcd_change(net as u32);
        }
        changed
    }

    /// Emit a VCD value_change for a net that changed (array word 0 in v1 VCD).
    fn emit_vcd_change(&mut self, net: u32) {
        if !self.dumping {
            return;
        }
        let i = net as usize;
        let (id, width) = match self.nets[i].vcd_id {
            Some(id) => (id, self.nets[i].width),
            None => return,
        };
        let packed = slice_word(&self.nets[i].cur, width, 0);
        if let Some(w) = self.vcd.as_mut() {
            let _ = w.set_time(self.now);
            let _ = w.value_change(id, &packed, width);
        }
    }

    // ── edge support ─────────────────────────────────────────────────────

    /// Snapshot cur → prev for every net (called at start of each new time).
    pub fn snapshot_prev(&mut self) {
        for slot in &mut self.nets {
            slot.prev.clone_from(&slot.cur);
        }
    }

    // ── VCD lifecycle (driven by $dumpfile/$dumpvars) ────────────────────

    pub fn open_vcd(&mut self, sink: VcdSink) {
        self.vcd = Some(VcdWriter::new(sink));
    }

    pub fn finalize_vcd(&mut self) {
        if let Some(w) = self.vcd.as_mut() {
            let _ = w.flush();
        }
    }
}

impl<'a> NetReader for SimState<'a> {
    fn read_net(&self, net: u32, word: Option<u32>) -> Value {
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

/// NetKind → VCD VarType.
pub(crate) fn vcd_var_type(kind: NetKind) -> VarType {
    match kind {
        NetKind::Reg => VarType::Reg,
        NetKind::Integer => VarType::Integer,
        NetKind::Real => VarType::Real, // VCD `$var real`
        NetKind::Wire | NetKind::Logic => VarType::Wire,
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
