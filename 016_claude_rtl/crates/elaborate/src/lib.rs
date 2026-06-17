//! elaborate — lowers a parsed hdl-ast `SourceUnit` into the frozen `sim-ir`.
//!
//! Pipeline position: preprocess → lex → parse → **ELABORATE** → sim-ir →
//! engine → VCD.
//!
//! ## v1 slice (this PR)
//! INPUT: a `SourceUnit` with ONE top `ModuleDecl`, no hierarchy/instances.
//! OUTPUT: a `SimIr` populated with `nets` (from decls), `consts`/`exprs` (from
//! lowered expressions), `cont_assigns` (lowered), and one self-`Instance` for
//! the top. `processes`/`stmts`/`blocks`/`funcs` stay EMPTY — procedural-block →
//! Process/BasicBlock lowering is the NEXT slice.
//!
//! ## What v1 lowers
//! - net/var declarations (wire/reg/logic/integer + ranges/signed/arrays)
//! - 4-state integer literals (see [`literal`])
//! - continuous `assign` statements (incl. concat-LHS, bit/part selects)
//!
//! ## Deferred (NOT v1 — error path + slot noted at each site)
//! - parameter override / module instances / hierarchy flattening
//! - procedural blocks (`always`/`initial`) → Process/SuspendState/BasicBlock
//! - width/type inference + context-determined sizing
//! - generate, function/task, user `Call`
//!
//! ## Determinism (feeds the velab golden hash — see module-level note §end)
//! Nets are appended in declaration order; exprs in a fixed post-order via the
//! single [`Elaborator::push_expr`] choke point; consts are deduped through a
//! lookup-only map that never reorders the arena. No HashMap iteration ever
//! feeds arena order.

mod literal;

use std::collections::{BTreeMap, BTreeSet};

use diag::{Diagnostic, LogEvent, LogSink, MsgCode, Severity};
use hdl_ast as ast;
use literal::{
    make_const_i64, make_const_u32, parse_int_literal, parse_real_f64, parse_real_literal,
    parse_str_literal, parse_str_literal_text,
};
use sim_ir as ir;

/// Const-bounded `repeat`/`for` are UNROLLED (the loop counter cannot live in a
/// `SuspendState.locals` slot — `Stmt`'s `Lvalue` only addresses nets, not
/// locals, and `Stmt` is frozen). This caps the unroll so a `repeat(1_000_000)`
/// in hostile input cannot explode the block arena. Above the cap → `ElabUnsupported`.
const REPEAT_UNROLL_CAP: u32 = 1024;

/// Hard cap on generate-for unroll iterations. A malformed/hostile
/// `for(i=0;i<HUGE;i=i+1)` cannot explode the arena: above this we emit
/// `ElabUnsupported` and stop unrolling. Mirrors `REPEAT_UNROLL_CAP`'s intent
/// (generate bodies can each contribute many nets, so the cap is conservative).
const GENERATE_UNROLL_CAP: u32 = 4096;

/// Hard cap on generate nesting depth (nested for/if/case/block). Guards against
/// pathological recursion; deep-nesting beyond this is deferred per PR scope.
const GENERATE_DEPTH_CAP: u32 = 32;

/// Hard cap on a single net's declared bit width. Above this we reject the decl
/// with `ElabUnsupported` rather than `vec![0u64; huge]` (which would OOM) or
/// overflow the `+1` width arithmetic. 2^20 bits = 16 KiB of planes per net —
/// generous for real RTL, hostile-input-safe. (COVERAGE verdict HIGH.)
const MAX_NET_WIDTH: u64 = 1 << 20;
/// P2-6: unpacked-array element cap (16M elements; with the 1 MiB-bit width cap
/// the worst legal net is still bounded far below an OOM-kill allocation).
const MAX_ARRAY_LEN: u64 = 1 << 24;

/// Poison NetId returned on an unresolvable reference. `u32::MAX` (not 0) so an
/// accidentally-surviving placeholder edge is detectable, never a silent alias
/// of the first real net. The whole IR is discarded on error anyway (had_error),
/// but a poison sentinel makes any future error-recovery path fail loud.
/// (COVERAGE verdict MEDIUM.)
const POISON_NET: u32 = u32::MAX;

/// Public entry point. Returns `Some(SimIr)` iff no hard error was emitted;
/// every error path still produces valid placeholder arena edges so the partial
/// IR is never structurally broken (the result is simply discarded on error).
pub fn elaborate(unit: &ast::SourceUnit, sink: &dyn LogSink) -> Option<ir::SimIr> {
    let (ir, _modes) = elaborate_with_modes(unit, sink);
    ir
}

/// Join mode for a `fork … join`/`join_any`/`join_none`. NOT part of `SimIr`
/// (the frozen `Terminator::Fork` carries no mode field): it rides out-of-band in
/// the [`ForkModeTable`] so the golden root stays byte-identical. The engine
/// consults it when executing the `Fork` terminator (total-or-fatal).
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum JoinMode {
    /// `join` — parent blocks until ALL children reach the join.
    All,
    /// `join_any` — parent unblocks at the FIRST child; surplus run on.
    Any,
    /// `join_none` — parent never blocks; children run as background activities.
    None,
}

/// Join-mode side table: `(template ProcId, join_bb)` → [`JoinMode`]. A
/// deterministic `BTreeMap` so it is 3-OS byte-stable when serialized; it NEVER
/// enters the golden `SimIr` root. The key is globally unique because each
/// process body is a private BB arena and `join_bb` is unique within it.
pub type ForkModeTable = std::collections::BTreeMap<(u32, u32), JoinMode>;

/// Per-NetId fully-qualified hierarchical name (`"top.dut.q"`), source order.
/// An engine-facing SIDE TABLE for the VCD writer — like [`ForkModeTable`] it
/// rides out-of-band in `SimOpts` and NEVER enters the frozen `SimIr` root (which
/// carries no name field). Threaded by the simulate path so `$dumpvars` emits real
/// hierarchical `$scope`/`$var` instead of a flat `top` + synthetic `n0..nN`.
pub type NetNameTable = Vec<String>;

/// Severity class of a lowered `$fatal`/`$error`/`$warning`/`$info` statement.
/// NOT part of `SimIr` (the frozen `SysTaskId` has no severity variants): a
/// severity task lowers to a plain `SysTaskId::Display` stmt, and this kind rides
/// out-of-band in the [`SeverityTable`] so the golden root stays byte-identical.
/// The engine consults it per-StmtId to route the text to the DIAGNOSTIC stream
/// (doc-13 tokens `fatal[VITA-F4004]`/`error[VITA-E4003]`/…) instead of stdout,
/// and to abort (`$fatal`) or flag the exit class (`$error`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum SeverityKind {
    /// `$info` — diagnostic only; exit class untouched.
    Info,
    /// `$warning` — diagnostic only; exit class untouched.
    Warning,
    /// `$error` — diagnostic + `ExitClass::HadErrors`; run continues.
    Error,
    /// `$fatal` — diagnostic + implicit `$finish` with `ExitClass::Fatal`.
    Fatal,
}

/// Severity side table: StmtId → [`SeverityKind`]. A deterministic `BTreeMap`
/// (3-OS byte-stable when serialized); like [`ForkModeTable`] it rides in
/// `SimOpts` / the `.velab` trailer and NEVER enters the golden `SimIr` root.
pub type SeverityTable = std::collections::BTreeMap<u32, SeverityKind>;

/// Default-radix side table (P1-5): StmtId → radix (2/8/16) for the
/// `$displayb/o/h`, `$writeb/o/h`, `$strobeb/o/h`, `$monitorb/o/h` variants —
/// the b/o/h changes only how UNFORMATTED arguments render (IEEE §17.1.1.1).
/// Out-of-band like the other tables; the frozen `SysTaskId` is unchanged.
pub type RadixTable = std::collections::BTreeMap<u32, u8>;

/// Maturation region of a deferred immediate assertion (IEEE 1800 §16.4 / §4.4),
/// mirrored at the engine. NOT part of `SimIr` and deliberately NOT
/// `sim_ir::RegionTag` (which is golden-reachable via `WakeKey`→`Process`→`SimIr`
/// and would flip the root hash) — a fresh out-of-band enum that rides `SimOpts`
/// and the `.velab` trailer like every other sidecar, so the golden root stays
/// byte-identical and `format_version` is unchanged.
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum DeferRegion {
    /// `assert #0` — matures in the Observed region.
    Observed,
    /// `assert final` — matures in the Reactive region.
    Reactive,
}

/// Deferred-assert FLUSH-MARKER side table (§16.4): the StmtId of the synthesized
/// no-op marker emitted just before each deferred assertion's `Branch` → its
/// region. The marker StmtId IS the assertion-instance identity; reaching it (in
/// the Active region) cancels any prior pending report for `(marker_sid,
/// activity)` — this is flush-on-re-reach, the defining deferred-assert
/// behavior. Out-of-band; the frozen IR is unchanged (the marker is an ordinary
/// `SysTaskId::Display` stmt the engine suppresses via this table).
pub type DeferMarkTable = std::collections::BTreeMap<u32, DeferRegion>;

/// Deferred-assert ACTION side table (§16.4): the StmtId of each pass/fail action
/// SysTask (the `$error`/`$display`/`$fatal`/… inside a deferred assert's arms) →
/// `(owning marker StmtId, region)`. Reaching the action ENQUEUES a report under
/// `(marker_sid, activity)` for region maturation instead of firing inline.
/// Out-of-band like the other tables.
pub type DeferActTable = std::collections::BTreeMap<u32, (u32, DeferRegion)>;

/// Assign-rank side table (IEEE 1364 §9.3.1): the StmtIds of `Stmt::Force` /
/// `Stmt::Release` statements that are really procedural `assign`/`deassign`
/// (the frozen `Stmt` has no Assign/Deassign variants — they reuse the force
/// machinery at a WEAKER rank: a real `force` overrides an active assign and
/// `release` hands control back to it). Out-of-band like the other tables.
pub type AssignRankTable = std::collections::BTreeSet<u32>;

/// Bounded-queue side table (v6 ③): HANDLE NetId → declared bound N
/// (`[$:N]`, max size N+1 — iverilog live). EMPTY by default (every queue
/// unbounded). Never enters the golden IR — rides `SimOpts` + a `.velab`
/// trailer segment like every other sidecar.
pub type QueueBoundTable = std::collections::BTreeMap<u32, u32>;

/// Unpacked-dimension side table (Phase-1.x ⑤): array NetId → per-dim
/// `(lo, size)` in declared order. SPARSE — exactly the elaborate-local
/// `array_dims` map, so a plain 0-based 1-D array is ABSENT and the engine
/// falls back to `[(0, array_len)]`. Drives per-element VCD naming
/// (`mem[4]`, `g[1][2]`). Out-of-band like every other sidecar.
pub type NetDimsTable = std::collections::BTreeMap<u32, Vec<(u32, u32)>>;

/// Frame-call metadata (B1, automatic/recursive functions), INDEX-ALIGNED to
/// `ir.funcs[i]` by construction (pushed in the same `lower_frame_func` that
/// writes `ir.funcs[idx]`). The frozen `FuncDef` carries only `entry/n_params/
/// locals_len/is_task`; everything the engine needs to ROUTE a frame call rides
/// here, out-of-band, so the golden `SimIr` root (and `schema_hash`/
/// `format_version`) is byte-unchanged. EMPTY by default ⇒ no frame functions ⇒
/// every existing design byte-identical.
///
/// SLOT LAYOUT (contiguous `ir.nets` ids from `base_net`, declaration order):
/// `[0..n_params)` = input formals (port order); `[n_params]` = the func-named
/// RETURN var (allocated at exactly the declared return range/sign); `[n_params+
/// 1..locals_len)` = `body_decls` (source order). All are REAL `ir.nets` entries
/// (so `width.rs`/`read_net`/lvalue lowering see correct width/signed); they are
/// flagged frame-local ONLY here (a `NetVar` has no spare bit).
///
/// CONTRACT (engine debug-asserts): `return_slot == n_params`, and
/// `ir.nets[base_net + return_slot].width == ret_width &&  .signed == ret_signed`
/// — the return-var net is allocated at exactly the declared width/sign so the
/// engine's read-slot-then-resize is idempotent.
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct FuncMeta {
    /// First `ir.nets` id of this function's frame window.
    pub base_net: u32,
    /// Number of input formals (== `FuncDef.n_params`).
    pub n_params: u32,
    /// LOCAL slot index (0..`locals_len`) of the func-named return var
    /// (== `n_params` by the layout convention above).
    pub return_slot: u32,
    /// Total frame slots (formals + return-var + body_decls; == `FuncDef.locals_len`).
    pub locals_len: u32,
    /// `true` ⇒ fresh window per call (push/pop). `false` ⇒ ONE shared static
    /// slab (no restore → the deepest write clobbers = the iverilog-faithful
    /// static-lifetime corruption). The only storage-policy discriminator.
    pub is_automatic: bool,
    /// Declared return self-width (`FunctionDef.range`; `integer` ⇒ 32, signed).
    /// Hoisted because `Expr::Call` has no net id of its own — `width.rs` sizes
    /// the call from this.
    pub ret_width: u32,
    /// Declared return signedness.
    pub ret_signed: bool,
}

/// Frame-call sidecar (B1): `Vec<FuncMeta>` index-aligned to `ir.funcs`.
/// `Default` (empty) ⇒ golden-neutral.
pub type FuncTable = Vec<FuncMeta>;

/// Engine-facing side tables produced by one elaboration — ALL out-of-band
/// (`SimOpts` fields / `.velab` trailers, each serialized as its OWN postcard
/// segment for append-only compatibility); none ever enters the golden `SimIr`.
#[derive(Debug, Clone, Default)]
pub struct Sidecars {
    pub fork_modes: ForkModeTable,
    pub net_names: NetNameTable,
    pub proc_multipliers: Vec<u32>,
    pub severities: SeverityTable,
    pub radixes: RadixTable,
    /// Per-ProcId hierarchical instance path (`"tb.u1"`) — drives `%m` (P2-11).
    /// Parallel to `processes`, like `proc_multipliers`.
    pub proc_scopes: Vec<String>,
    /// StmtIds of Force/Release stmts that are procedural assign/deassign.
    pub assign_ranks: AssignRankTable,
    /// Bounded-queue bounds (v6 ③): handle NetId → N.
    pub queue_bounds: QueueBoundTable,
    /// Unpacked-array dims for per-element VCD naming (Phase-1.x ⑤).
    pub net_dims: NetDimsTable,
    /// P2-E: ProcIds of `final` blocks (skip arming; run at end of sim).
    pub final_procs: std::collections::BTreeSet<u32>,
    /// §16.4 deferred-assert flush markers: marker StmtId → region.
    pub defer_marks: DeferMarkTable,
    /// §16.4 deferred-assert actions: action StmtId → (marker StmtId, region).
    pub defer_acts: DeferActTable,
    /// B1 frame-call metadata, index-aligned to `ir.funcs`. EMPTY ⇒ no
    /// automatic/recursive functions ⇒ golden-neutral.
    pub func_table: FuncTable,
}

/// Like [`elaborate`], but also returns the [`ForkModeTable`] the simulate path
/// threads into `SimOpts.fork_modes`. `elaborate` is a thin forwarder onto this
/// so the ~25 existing `elaborate(...)` callers keep compiling verbatim.
pub fn elaborate_with_modes(
    unit: &ast::SourceUnit,
    sink: &dyn LogSink,
) -> (Option<ir::SimIr>, ForkModeTable) {
    let (ir, modes, _names) = elaborate_with_sidecars(unit, sink);
    (ir, modes)
}

/// Like [`elaborate_with_modes`], but ALSO returns the [`NetNameTable`] for VCD
/// hierarchical naming. Both side tables ride in `SimOpts` and never perturb the
/// golden `SimIr`. Uses the `1ns/1ns` timescale base (no delay scaling).
pub fn elaborate_with_sidecars(
    unit: &ast::SourceUnit,
    sink: &dyn LogSink,
) -> (Option<ir::SimIr>, ForkModeTable, NetNameTable) {
    let (ir, sc) = elaborate_with_timescale(unit, sink, &std::collections::BTreeMap::new(), -9);
    (ir, sc.fork_modes, sc.net_names)
}

/// Full elaborate entry with the resolved timescale env from
/// `hdl_preprocess::resolve_module_timescales`. `mod_unit_exp` maps each module name
/// to its delay-unit exponent and `global_prec_exp` is the design-wide tick base;
/// `#delay` literals scale to `round(d × 10^(unit−prec))` ticks. Also returns the
/// per-process multiplier table for `SimOpts.proc_multipliers` (`$time`/`$realtime`
/// scaling) and the [`SeverityTable`] for `$fatal`/`$error`/`$warning`/`$info`.
/// All side tables ride out-of-band; the golden `SimIr` is unchanged.
pub fn elaborate_with_timescale(
    unit: &ast::SourceUnit,
    sink: &dyn LogSink,
    mod_unit_exp: &std::collections::BTreeMap<String, i8>,
    global_prec_exp: i8,
) -> (Option<ir::SimIr>, Sidecars) {
    elaborate_with_timescale_roots(unit, sink, mod_unit_exp, global_prec_exp, None)
}

/// [`elaborate_with_timescale`] with an explicit ROOT override (`--top`): when
/// `roots` is `Some`, exactly those units are elaborated as top instances (in
/// the given order) instead of the every-uninstantiated-module default — the
/// worklib/`--top` surface. An unknown name is a loud elaborate error.
pub fn elaborate_with_timescale_roots(
    unit: &ast::SourceUnit,
    sink: &dyn LogSink,
    mod_unit_exp: &std::collections::BTreeMap<String, i8>,
    global_prec_exp: i8,
    roots: Option<&[String]>,
) -> (Option<ir::SimIr>, Sidecars) {
    let mut el = Elaborator::new(sink);
    el.mod_unit_exp = mod_unit_exp.clone();
    el.global_prec_exp = global_prec_exp;
    el.root_override = roots.map(<[String]>::to_vec);
    el.run(unit);
    let sc = Sidecars {
        fork_modes: std::mem::take(&mut el.fork_modes),
        proc_multipliers: std::mem::take(&mut el.proc_multipliers),
        severities: std::mem::take(&mut el.severities),
        radixes: std::mem::take(&mut el.radixes),
        proc_scopes: std::mem::take(&mut el.proc_scopes),
        assign_ranks: std::mem::take(&mut el.assign_ranks),
        queue_bounds: std::mem::take(&mut el.queue_bounds),
        net_dims: el.array_dims.clone(), // the sparse decl map IS the table
        final_procs: el.final_procs.clone(),
        defer_marks: std::mem::take(&mut el.defer_marks),
        defer_acts: std::mem::take(&mut el.defer_acts),
        func_table: std::mem::take(&mut el.func_metas), // B1 (empty until frame funcs lower)
        net_names: el.net_name_table(),                 // BEFORE finish() consumes `el`
    };
    if el.had_error {
        (None, sc)
    } else {
        (Some(el.finish()), sc)
    }
}

/// Canonical dedup key for the const pool. Cloning the `Vec<u64>` planes keeps
/// the compare total and order-independent (used only for lookup, never to drive
/// arena order — see determinism note).
type ConstKey = (u32, bool, u8, Vec<u64>, Vec<u64>);

/// module-name → (decl, declaration index). `BTreeMap` so any iteration over the
/// map is deterministic; the decl index is the tie-break for top selection.
type ModuleMap<'a> = BTreeMap<&'a str, (&'a ast::ModuleDecl, usize)>;

/// How to find each child-port's connection expr, resolved in the PARENT scope.
/// Borrows directly from the `ast::ModuleInstance` so no per-port allocation.
enum PortBinding<'a> {
    None,                                // the top instance — no incoming bindings
    Named(&'a [ast::PortConn]),          // .p(expr)
    Positional(&'a [Option<ast::Expr>]), // (expr, expr, …) with skip slots
}

/// A parameter override resolved to a value IN THE PARENT SCOPE before it is
/// pushed into the child. `name` is `Some` for `.W(v)` (named) / `None` for a
/// positional `#(v)` (bound to the child's i-th param by position). `value` is
/// `None` when the override expr did not const-fold (caller warns; child keeps
/// its default). Resolving here — not in `bind_params` — is what lets
/// `child #(.W(PARENT_W))` see the parent's `PARENT_W` (Fix 1 / Finding M1).
struct ResolvedOverride {
    name: Option<String>,
    value: Option<i64>,
    is_named: bool,
}

/// Build the module-name map + the declaration-ordered list. First decl wins on a
/// duplicate name (caller warns). Deterministic: single pass over `unit.items`.
fn build_module_map(unit: &ast::SourceUnit) -> (ModuleMap<'_>, Vec<&ast::ModuleDecl>) {
    let mut map: ModuleMap<'_> = BTreeMap::new();
    let mut order: Vec<&ast::ModuleDecl> = Vec::new();
    for it in &unit.items {
        if let ast::TopItem::Module(m) = it {
            let idx = order.len();
            map.entry(m.name.name.as_str()).or_insert((m, idx));
            order.push(m);
        }
    }
    (map, order)
}

/// Collect every module name instantiated ANYWHERE in `order` — directly in a
/// module body OR nested inside a `generate` construct — restricted to names that
/// resolve to a known module (an unknown name is an instantiation error surfaced
/// later in the recursion). The set of modules NOT in here is the ROOT set.
/// Descending generates is load-bearing: a module instantiated ONLY inside a
/// `generate` is still instantiated, so it must not also be elaborated as a
/// spurious extra root (which would double-lower its body). Deterministic
/// (declaration-order walk into a `BTreeSet`).
fn collect_instantiated<'a>(
    map: &ModuleMap<'a>,
    order: &[&'a ast::ModuleDecl],
) -> std::collections::BTreeSet<&'a str> {
    fn from_item<'a>(
        item: &'a ast::ModuleItem,
        map: &ModuleMap<'a>,
        set: &mut std::collections::BTreeSet<&'a str>,
    ) {
        match item {
            ast::ModuleItem::Instance(inst) => {
                if map.contains_key(inst.module_name.name.as_str()) {
                    set.insert(inst.module_name.name.as_str());
                }
            }
            ast::ModuleItem::Generate(g) => {
                for gi in &g.items {
                    from_genitem(gi, map, set);
                }
            }
            _ => {}
        }
    }
    fn from_genitem<'a>(
        gi: &'a ast::GenItem,
        map: &ModuleMap<'a>,
        set: &mut std::collections::BTreeSet<&'a str>,
    ) {
        match gi {
            ast::GenItem::Item(boxed) => from_item(boxed, map, set),
            ast::GenItem::For { body, .. } => {
                for g in body {
                    from_genitem(g, map, set);
                }
            }
            ast::GenItem::Block { items, .. } => {
                for g in items {
                    from_genitem(g, map, set);
                }
            }
            ast::GenItem::If { then_b, else_b, .. } => {
                for g in then_b.iter().chain(else_b) {
                    from_genitem(g, map, set);
                }
            }
            ast::GenItem::Case { items, .. } => {
                for ci in items {
                    let body = match ci {
                        ast::GenCaseItem::Match { body, .. } => body,
                        ast::GenCaseItem::Default { body, .. } => body,
                    };
                    for g in body {
                        from_genitem(g, map, set);
                    }
                }
            }
        }
    }
    let mut set = std::collections::BTreeSet::new();
    for m in order {
        for item in &m.body {
            from_item(item, map, &mut set);
        }
    }
    set
}

/// Collect every design-unit name instantiated anywhere in `unit` — directly in
/// a module body or nested inside `generate` — WITHOUT resolving against a
/// module map (unresolved names are exactly what a worklib closure walk needs:
/// they may live in another compilation unit). Interface instances surface here
/// too (they parse as `ModuleItem::Instance`). Deterministic (decl-order walk
/// into a `BTreeSet`).
pub fn instantiated_names(unit: &ast::SourceUnit) -> std::collections::BTreeSet<String> {
    fn from_item(item: &ast::ModuleItem, set: &mut std::collections::BTreeSet<String>) {
        match item {
            ast::ModuleItem::Instance(inst) => {
                set.insert(inst.module_name.name.clone());
            }
            ast::ModuleItem::Generate(g) => {
                for gi in &g.items {
                    from_genitem(gi, set);
                }
            }
            _ => {}
        }
    }
    fn from_genitem(gi: &ast::GenItem, set: &mut std::collections::BTreeSet<String>) {
        match gi {
            ast::GenItem::Item(boxed) => from_item(boxed, set),
            ast::GenItem::For { body, .. } => {
                for g in body {
                    from_genitem(g, set);
                }
            }
            ast::GenItem::Block { items, .. } => {
                for g in items {
                    from_genitem(g, set);
                }
            }
            ast::GenItem::If { then_b, else_b, .. } => {
                for g in then_b.iter().chain(else_b) {
                    from_genitem(g, set);
                }
            }
            ast::GenItem::Case { items, .. } => {
                for ci in items {
                    let body = match ci {
                        ast::GenCaseItem::Match { body, .. } => body,
                        ast::GenCaseItem::Default { body, .. } => body,
                    };
                    for g in body {
                        from_genitem(g, set);
                    }
                }
            }
        }
    }
    let mut set = std::collections::BTreeSet::new();
    for it in &unit.items {
        let body = match it {
            ast::TopItem::Module(m) => &m.body,
            ast::TopItem::Interface(m) => &m.body,
            _ => continue,
        };
        for item in body {
            from_item(item, &mut set);
        }
    }
    set
}

/// Pick ALL TOP (root) modules: every module never instantiated by another, in
/// DECLARATION order (deterministic flat-IR layout). IEEE 1364 / iverilog
/// elaborate every uninstantiated module as an independent root, so two
/// independent top modules both simulate — the old single-pick dropped all but
/// the last-declared. A duplicate module name yields at most one root, resolved
/// to its canonical (first-declared) decl via `map` so a root never diverges from
/// how the same name is instantiated elsewhere. Degenerate (every module
/// instantiated — a cycle or a pure library, so the set is empty): fall back to
/// the last-declared single module so `run` still produces IR. Deterministic.
fn pick_roots<'a>(map: &ModuleMap<'a>, order: &[&'a ast::ModuleDecl]) -> Vec<&'a ast::ModuleDecl> {
    let instantiated = collect_instantiated(map, order);
    let canon = |name: &str, fallback: &'a ast::ModuleDecl| -> &'a ast::ModuleDecl {
        map.get(name).map(|(d, _)| *d).unwrap_or(fallback)
    };
    let mut roots: Vec<&ast::ModuleDecl> = Vec::new();
    let mut added: std::collections::BTreeSet<&str> = std::collections::BTreeSet::new();
    for m in order {
        let name = m.name.name.as_str();
        if instantiated.contains(name) || !added.insert(name) {
            continue;
        }
        roots.push(canon(name, m));
    }
    if roots.is_empty() {
        if let Some(m) = order.last() {
            roots.push(canon(m.name.name.as_str(), m));
        }
    }
    roots
}

/// A module's ports as `(local_name, dir)` in HEADER declaration order. ANSI
/// ports read dir inline; non-ANSI merges the body `PortDecl` directions over the
/// header name list (an undeclared header name defaults to Input + is rare).
/// Port wiring walks this in order, so a named connection list in any source
/// order produces a deterministic cont-assign sequence.
/// v5 ⑥ (D): the `IfaceRef` of an ANSI interface-typed port, by name.
fn ansi_iface_ref<'m>(module: &'m ast::ModuleDecl, pname: &str) -> Option<&'m ast::IfaceRef> {
    match &module.ports {
        ast::PortList::Ansi(list) => list
            .iter()
            .find(|p| p.name.name == pname)
            .and_then(|p| p.iface.as_ref()),
        _ => None,
    }
}

fn port_list_dirs(module: &ast::ModuleDecl) -> Vec<(String, ir::PortDir)> {
    match &module.ports {
        ast::PortList::Ansi(list) => list
            .iter()
            .map(|p| (p.name.name.clone(), map_port_dir(p.dir)))
            .collect(),
        ast::PortList::NonAnsi(names) => {
            // find each header name's direction in a body PortDecl.
            names
                .iter()
                .map(|n| {
                    let dir = module
                        .body
                        .iter()
                        .find_map(|it| match it {
                            ast::ModuleItem::PortDecl(pd)
                                if pd.names.iter().any(|x| x.name == n.name) =>
                            {
                                Some(map_port_dir(pd.dir))
                            }
                            _ => None,
                        })
                        .unwrap_or(ir::PortDir::Input);
                    (n.name.clone(), dir)
                })
                .collect()
        }
        ast::PortList::None => Vec::new(),
    }
}

/// A concurrent assertion (`assert property(@(clk) ante |-> cons)`) collected
/// during statement lowering and materialized AFTER the module's process loop as
/// a synthesized clocked checker (v8 SVA subset). It is a continuously-checking
/// background process, not a one-shot procedural statement, so it cannot be
/// lowered inline — see `materialize_sva_checkers`.
struct PendingSva {
    clock: ast::Sensitivity,
    /// `disable iff (expr)` reset condition (slice S12), if any.
    disable_iff: Option<ast::Expr>,
    ante: ast::Sequence,
    kind: ast::ImplicationKind,
    /// The consequent (slice S14: a `Sequence`; a boolean consequent is
    /// `Sequence::Boolean` and keeps the byte-identical lowering).
    cons: ast::Sequence,
    /// Action block (slice S11): `fail` (the `else` statement) replaces the
    /// default `$error` on a violation; `pass` runs on a non-vacuous success.
    pass: Option<Box<ast::Stmt>>,
    fail: Option<Box<ast::Stmt>>,
    /// Consequent clocking event (slice A3, multi-clock): `Some(c2)` selects the
    /// two-process handoff synthesis for `@(c1) ante |=> @(c2) cons`. Out-of-band
    /// (elaborate-internal, NOT serialized → golden-free).
    cons_clock: Option<ast::Sensitivity>,
    span: ast::Span,
}

/// Collected sampled-value state for one concurrent assertion: each distinct
/// sampled signal gets ONE prev-register (shared across `$past`/`$rose`/etc.),
/// plus the per-clock `prev <= signal` NBA updates that maintain them.
#[derive(Default)]
struct SvaRegs {
    /// signal name → prev-register name (dedup so `$rose(a)` + `$stable(a)` share).
    by_signal: Vec<(String, String)>,
    /// `prev <= signal;` NBA updates appended to the checker's clocked body.
    nbas: Vec<ast::Stmt>,
}

/// The cycle gap before a sequence term in a flattened alternative: a fixed
/// `##d` delay (`d` shift-register stages), or an unbounded `##[m:$]` (≥m — an
/// `m-1` fixed delay followed by a never-reset `armed` latch, so every later
/// term clock re-completes the match).
#[derive(Clone, Copy)]
enum SeqHop {
    Fixed(u32),
    AtLeast(u32),
}

/// A term in a flattened sequence alternative: a plain boolean, or a
/// goto/nonconsecutive repetition of a boolean (synthesized as an existence-
/// latch FSM rather than a fixed shift).
#[derive(Clone)]
enum SeqTerm {
    Bool(ast::Expr),
    /// `b[->n]` — completes on the n-th (gap-allowed) occurrence of `b`.
    Goto(ast::Expr, u32),
    /// `b[=n]` — n occurrences of `b`, match extends past the n-th until the next.
    Nonconsec(ast::Expr, u32),
    /// `b[*m:$]` — `b` true for ≥ m CONSECUTIVE clocks (slice S13). Synthesized as
    /// a gated run-latch (a chain of 1-bit regs that saturates at the count `m`)
    /// rather than a fixed shift, since the upper bound is unbounded.
    ConsecAtLeast(ast::Expr, u32),
}

/// One expanded sequence alternative: an ordered (term, hop) list plus an
/// optional already-reduced (1-bit) `throughout` guard that must hold at every
/// clock of the window.
type SeqAlt = (Vec<(SeqTerm, SeqHop)>, Option<ast::Expr>);

/// Build a `name <= rhs;` NBA to an already-named synthesized reg.
fn sva_nb(name: &str, rhs: ast::Expr, sp: ast::Span) -> ast::Stmt {
    ast::Stmt::NonBlocking {
        lhs: ast::Lvalue::Ident(ast::HierPath {
            segments: vec![ast::Ident {
                name: name.to_string(),
                span: sp,
            }],
            span: sp,
        }),
        delay: None,
        rhs,
        span: sp,
    }
}

/// The 1-bit constant `1'b1` — the activation for a leading goto/nonconsec term
/// (a counting thread starts every clock).
fn sva_one(sp: ast::Span) -> ast::Expr {
    ast::Expr {
        kind: ast::ExprKind::IntLit {
            kind: ast::IntLitKind::Sized,
            raw: "1'b1".to_string(),
        },
        span: sp,
    }
}

/// The 1-bit constant `1'b0` — a never-matching antecedent (e.g. a `within`
/// whose seq1 is longer than every seq2 window).
fn sva_zero(sp: ast::Span) -> ast::Expr {
    ast::Expr {
        kind: ast::ExprKind::IntLit {
            kind: ast::IntLitKind::Sized,
            raw: "1'b0".to_string(),
        },
        span: sp,
    }
}

/// Wrap an obligation NBA's RHS in `dis ? 1'b0 : rhs` so a `disable iff (dis)`
/// reset clears in-flight pipeline/pending state on the clock it is asserted
/// (slice S12). Only NonBlocking stmts occur in the obligation list; any other
/// stmt (none expected) passes through unchanged.
fn gate_nba_with_disable(stmt: ast::Stmt, dis: &ast::Expr, sp: ast::Span) -> ast::Stmt {
    match stmt {
        ast::Stmt::NonBlocking {
            lhs,
            delay,
            rhs,
            span,
        } => ast::Stmt::NonBlocking {
            lhs,
            delay,
            rhs: ast::Expr {
                kind: ast::ExprKind::Ternary {
                    cond: Box::new(dis.clone()),
                    then_e: Box::new(sva_zero(sp)),
                    else_e: Box::new(rhs),
                },
                span: sp,
            },
            span,
        },
        other => other,
    }
}

/// A single never-matching (`1'b0`) sequence alternative — the recovery value
/// substituted when a sequence form is rejected (e.g. a repetition count over
/// the cap). `1'b0` (rather than `1'b1`) so the errored design can never produce
/// a spurious assertion fire on the abort path.
fn sva_never_alt(seq: &ast::Sequence) -> Vec<SeqAlt> {
    vec![(
        vec![(SeqTerm::Bool(sva_zero(seq_span(seq))), SeqHop::Fixed(0))],
        None,
    )]
}

/// The clock-window length (in clocks) of a flattened bounded Bool-only
/// alternative: 1 (the seed clock) plus the sum of the inter-term `##d` delays.
fn window_len(terms: &[(SeqTerm, SeqHop)]) -> u32 {
    1 + terms
        .iter()
        .skip(1)
        .map(|(_, h)| match h {
            SeqHop::Fixed(d) => *d,
            SeqHop::AtLeast(_) => 0,
        })
        .sum::<u32>()
}

/// AND two optional (1-bit) `throughout` guards. The common (top-level
/// throughout) case has at most one guard, so no BinOp is built.
fn and_opt(a: Option<ast::Expr>, b: Option<ast::Expr>, sp: ast::Span) -> Option<ast::Expr> {
    match (a, b) {
        (None, x) | (x, None) => x,
        (Some(x), Some(y)) => Some(sva_binary(ast::BinOp::BitAnd, x, y, sp)),
    }
}

/// A representative span for a `Sequence` node (its first boolean leaf).
fn seq_span(seq: &ast::Sequence) -> ast::Span {
    match seq {
        ast::Sequence::Boolean(e) => e.span,
        ast::Sequence::Delay { lhs, .. } => seq_span(lhs),
        ast::Sequence::Repeat { seq, .. } => seq_span(seq),
        ast::Sequence::Throughout { cond, .. } => cond.span,
        ast::Sequence::Within { seq1, .. } => seq_span(seq1),
        ast::Sequence::Instance { span, .. } => *span,
    }
}

/// Substitute SVA formal identifiers with their bound actual expressions (slice A1).
/// `map` is `formal-name → actual-expr`; a single-segment `Ident` whose name is a
/// formal is replaced by a clone of the actual (carrying the actual's span). Every
/// other node is rebuilt structurally so the substitution reaches nested operands.
/// Pure AST rewrite — used to inline `sequence s(x,y); …` at `s(a,b)` (IR-0).
fn subst_expr(e: &ast::Expr, map: &BTreeMap<String, ast::Expr>) -> ast::Expr {
    use ast::ExprKind as K;
    // A formal occurrence (a bare single-segment name that is a key) → the actual.
    if let K::Ident(p) = &e.kind {
        if p.segments.len() == 1 {
            if let Some(actual) = map.get(&p.segments[0].name) {
                return actual.clone();
            }
        }
    }
    let sp = e.span;
    let kind = match &e.kind {
        K::Unary { op, operand } => K::Unary {
            op: *op,
            operand: Box::new(subst_expr(operand, map)),
        },
        K::Binary { op, lhs, rhs } => K::Binary {
            op: *op,
            lhs: Box::new(subst_expr(lhs, map)),
            rhs: Box::new(subst_expr(rhs, map)),
        },
        K::Ternary {
            cond,
            then_e,
            else_e,
        } => K::Ternary {
            cond: Box::new(subst_expr(cond, map)),
            then_e: Box::new(subst_expr(then_e, map)),
            else_e: Box::new(subst_expr(else_e, map)),
        },
        K::BitSelect { base, index } => K::BitSelect {
            base: Box::new(subst_expr(base, map)),
            index: Box::new(subst_expr(index, map)),
        },
        K::PartSelect { base, msb, lsb } => K::PartSelect {
            base: Box::new(subst_expr(base, map)),
            msb: Box::new(subst_expr(msb, map)),
            lsb: Box::new(subst_expr(lsb, map)),
        },
        K::IndexedPart {
            base,
            offset,
            width,
            dir,
        } => K::IndexedPart {
            base: Box::new(subst_expr(base, map)),
            offset: Box::new(subst_expr(offset, map)),
            width: Box::new(subst_expr(width, map)),
            dir: *dir,
        },
        K::Concat { parts } => K::Concat {
            parts: parts.iter().map(|x| subst_expr(x, map)).collect(),
        },
        K::Replicate { count, value } => K::Replicate {
            count: Box::new(subst_expr(count, map)),
            value: value.iter().map(|x| subst_expr(x, map)).collect(),
        },
        K::Call { name, args } => K::Call {
            name: name.clone(),
            args: args.iter().map(|x| subst_expr(x, map)).collect(),
        },
        K::SysCall { name, args } => K::SysCall {
            name: name.clone(),
            args: args.iter().map(|x| subst_expr(x, map)).collect(),
        },
        K::Paren { inner } => K::Paren {
            inner: Box::new(subst_expr(inner, map)),
        },
        K::MinTypMax { min, typ, max } => K::MinTypMax {
            min: Box::new(subst_expr(min, map)),
            typ: Box::new(subst_expr(typ, map)),
            max: Box::new(subst_expr(max, map)),
        },
        // literals, pkg-scoped, multi-segment ident, new, dollar, error: no formal
        // occurrence to rewrite — clone verbatim.
        _ => e.kind.clone(),
    };
    ast::Expr { kind, span: sp }
}

/// Substitute SVA formals (slice A1) through a `Sequence`, recursing into the
/// boolean leaves / guards. A nested named-sequence `Instance` whose NAME is itself
/// a formal bound to a bare-ident actual is renamed; its args are substituted too.
fn subst_sequence(seq: &ast::Sequence, map: &BTreeMap<String, ast::Expr>) -> ast::Sequence {
    use ast::Sequence as S;
    match seq {
        S::Boolean(e) => S::Boolean(subst_expr(e, map)),
        S::Delay { min, max, lhs, rhs } => S::Delay {
            min: *min,
            max: *max,
            lhs: Box::new(subst_sequence(lhs, map)),
            rhs: Box::new(subst_sequence(rhs, map)),
        },
        S::Repeat {
            seq,
            min,
            max,
            kind,
        } => S::Repeat {
            seq: Box::new(subst_sequence(seq, map)),
            min: *min,
            max: *max,
            kind: *kind,
        },
        S::Throughout { cond, seq } => S::Throughout {
            cond: Box::new(subst_expr(cond, map)),
            seq: Box::new(subst_sequence(seq, map)),
        },
        S::Within { seq1, seq2 } => S::Within {
            seq1: Box::new(subst_sequence(seq1, map)),
            seq2: Box::new(subst_sequence(seq2, map)),
        },
        S::Instance { name, args, span } => {
            let name = match map.get(&name.name) {
                Some(ast::Expr {
                    kind: ast::ExprKind::Ident(p),
                    ..
                }) if p.segments.len() == 1 => ast::Ident {
                    name: p.segments[0].name.clone(),
                    span: name.span,
                },
                _ => name.clone(),
            };
            S::Instance {
                name,
                args: args.iter().map(|a| subst_expr(a, map)).collect(),
                span: *span,
            }
        }
    }
}

/// Substitute SVA formals (slice A1) through a clocking event's expressions (a
/// formal may name the clock signal of a parameterized property).
fn subst_sensitivity(s: &ast::Sensitivity, map: &BTreeMap<String, ast::Expr>) -> ast::Sensitivity {
    match s {
        ast::Sensitivity::Star => ast::Sensitivity::Star,
        ast::Sensitivity::List(evs) => ast::Sensitivity::List(
            evs.iter()
                .map(|ev| ast::EventExpr {
                    edge: ev.edge,
                    expr: subst_expr(&ev.expr, map),
                    span: ev.span,
                })
                .collect(),
        ),
    }
}

/// Build the positional formal→actual substitution map for a parameterized SVA
/// instance (slice A1). The caller has already arity-checked.
fn sva_formal_map(formals: &[ast::Ident], actuals: &[ast::Expr]) -> BTreeMap<String, ast::Expr> {
    formals
        .iter()
        .map(|f| f.name.clone())
        .zip(actuals.iter().cloned())
        .collect()
}

/// Cap on the number of disjunctive ALTERNATIVES a bounded SVA sequence range
/// (`##[m:n]`/`[*m:n]`, possibly nested/producted) may expand to before a loud
/// reject — the range-blowup guard. Note the synthesized pipeline regs are NOT
/// prefix-shared across alternatives, so a single `[*1:N]` allocates ~N²/2 regs
/// (each `[*k]` alternative its own k-1 stage chain); the cap therefore bounds
/// the worst-case reg count quadratically (≈cap²/2), not linearly. That still
/// elaborates deterministically at the cap; prefix-sharing is a perf follow-on.
const SVA_SEQ_ALT_CAP: usize = 256;

/// Is `name` (incl. the leading `$`) an SVA sampled-value function we desugar?
fn is_sva_sampled_fn(name: &str) -> bool {
    matches!(name, "$past" | "$rose" | "$fell" | "$stable")
}

fn sva_ident_expr(name: &str, sp: ast::Span) -> ast::Expr {
    ast::Expr {
        kind: ast::ExprKind::Ident(ast::HierPath {
            segments: vec![ast::Ident {
                name: name.to_string(),
                span: sp,
            }],
            span: sp,
        }),
        span: sp,
    }
}

fn sva_binary(op: ast::BinOp, lhs: ast::Expr, rhs: ast::Expr, sp: ast::Span) -> ast::Expr {
    ast::Expr {
        kind: ast::ExprKind::Binary {
            op,
            lhs: Box::new(lhs),
            rhs: Box::new(rhs),
        },
        span: sp,
    }
}

fn sva_unary(op: ast::UnOp, operand: ast::Expr, sp: ast::Span) -> ast::Expr {
    ast::Expr {
        kind: ast::ExprKind::Unary {
            op,
            operand: Box::new(operand),
        },
        span: sp,
    }
}

/// The `(edge, signal-name)` of a single bare-identifier clocking event
/// (`@(posedge clk)`), or `None` for a multi-event / non-ident / `@(*)` clock. Used
/// to compare two clocks span-insensitively (the `Sensitivity` derive compares spans,
/// so two textually-identical `@(posedge clk)` at different locations are `!=`).
fn sva_clock_signal(s: &ast::Sensitivity) -> Option<(ast::Edge, String)> {
    match s {
        ast::Sensitivity::List(evs) if evs.len() == 1 => match &evs[0].expr.kind {
            ast::ExprKind::Ident(p) if p.segments.len() == 1 => {
                Some((evs[0].edge, p.segments[0].name.clone()))
            }
            _ => None,
        },
        _ => None,
    }
}

/// Wrap statements as a single synthesized clocked-checker body — the lone statement
/// directly, or a `Block` of several (slice A3 two-process synthesis).
fn sva_block_or_single(mut stmts: Vec<ast::Stmt>, sp: ast::Span) -> ast::Stmt {
    if stmts.len() == 1 {
        stmts.pop().unwrap()
    } else {
        ast::Stmt::Block {
            label: None,
            decls: Vec::new(),
            stmts,
            span: sp,
        }
    }
}

/// `e[0]` — the LSB, for `$rose`/`$fell` (IEEE 1800 §16.9.3 sample the LSB).
fn sva_bit0(e: ast::Expr, sp: ast::Span) -> ast::Expr {
    ast::Expr {
        kind: ast::ExprKind::BitSelect {
            base: Box::new(e),
            index: Box::new(ast::Expr {
                kind: ast::ExprKind::IntLit {
                    kind: ast::IntLitKind::Decimal,
                    raw: "0".to_string(),
                },
                span: sp,
            }),
        },
        span: sp,
    }
}

struct Elaborator<'s> {
    sink: &'s dyn LogSink,
    had_error: bool,

    // ── growing sim-ir arenas (insertion-ordered → deterministic) ──
    nets: Vec<ir::NetVar>,
    exprs: Vec<ir::Expr>,
    consts: Vec<ir::ConstVal>,
    cont_assigns: Vec<ir::ContAssign>,
    instances: Vec<ir::Instance>,

    // ── v2: procedural lowering arenas ──
    // `processes` is one Process per ProceduralBlock (module-body order).
    // `stmts` is the GLOBAL straight-line Stmt arena (SimIr.stmts); a
    // `BasicBlock.stmts` holds indices into it. The CFG basic blocks themselves
    // live INLINE in each `Process.body` (process-LOCAL indices; SimIr.blocks
    // stays empty — it is reserved for funcs, deferred past v2).
    processes: Vec<ir::Process>,
    stmts: Vec<ir::Stmt>,

    // ── lookup-only maps (NEVER feed arena order) ──
    symbols: BTreeMap<String, u32>, // fully-qualified net/var NAME → NetId
    const_dedup: BTreeMap<ConstKey, u32>,
    // NetId → per-dimension `(lo, size)` extents (source order) for unpacked arrays
    // whose addressing is NOT plain 0-based (`reg [7:0] g[0:1][0:2]` ⇒ [(0,2),(0,3)];
    // `mem[4:7]` ⇒ [(4,4)]). elaborate-LOCAL only — NEVER in the frozen sim-ir (NetVar
    // keeps a scalar `array_len`); a multi-index `g[i][j]` lowers to the row-major flat
    // word `(i-lo0)*s1 + (j-lo1)`, so the IR backbone is untouched. Plain 0-based 1-D
    // arrays are absent (the access path falls back to `[(0, array_len)]`).
    array_dims: BTreeMap<u32, Vec<(u32, u32)>>,
    /// v7 `$bits` prescan: name → (element bits, unpacked dim lengths) for the
    /// CURRENT module's body decls, recorded in declaration order during the
    /// body param-binding walk (3b) — a `localparam X = $bits(mem[0])` binds
    /// before nets lower, so the real net table can't serve it. Unfoldable
    /// decls are silently skipped (the `$bits` SITE goes loud instead).
    bits_prescan: BTreeMap<String, (u64, Vec<u64>)>,
    /// v7 P2-D: package name → its const symbols (params/localparams + enum
    /// labels), folded EAGERLY in declaration order at `run()` entry.
    pkg_consts: BTreeMap<String, BTreeMap<String, i64>>,
    /// v7 P2-D: package name → its function/task definitions (clones — the
    /// same inline-expansion tables modules use).
    pkg_funcs: BTreeMap<String, BTreeMap<String, ast::FunctionDef>>,
    pkg_tasks: BTreeMap<String, BTreeMap<String, ast::TaskDef>>,
    /// v7 P2-D: compilation-unit-scope `import` items — applied to every
    /// module elaboration (IEEE visibility is decl-order; TBs put them first).
    cu_imports: Vec<ast::ImportDecl>,
    /// P2-E: ProcIds of `final` blocks — engine side table (never the IR):
    /// skipped at arming, run once at end of simulation.
    pub final_procs: std::collections::BTreeSet<u32>,
    /// B1 frame-call metadata, index-aligned to `self.funcs`/`ir.funcs`. Pushed
    /// in `lower_frame_func`; drained into `Sidecars.func_table`. EMPTY until a
    /// frame (automatic/recursive) function lowers.
    func_metas: Vec<FuncMeta>,
    /// B1 frame-call: the GLOBAL `FuncDef` arena (→ `ir.funcs`). Accumulates
    /// across instances; index-aligned to `func_metas`. EMPTY for designs with
    /// no frame functions (golden-neutral: `ir.funcs` stays empty).
    funcs: Vec<ir::FuncDef>,
    /// B1 frame-call: the GLOBAL func-body block arena (→ `ir.blocks`). Each
    /// frame function's lowered CFG is appended here with its `Goto`/`Branch`
    /// targets rebased; `FuncDef.entry` is a global index into it.
    func_blocks: Vec<ir::BasicBlock>,
    /// B1 frame-call: names of functions that need a frame (automatic OR on a
    /// recursion cycle), and their reserved FuncId. PER-INSTANCE (saved/restored
    /// like `func_table`) so a sibling module never diverts to a stale id. The
    /// call-site divert (`inline_function`) consults this; empty ⇒ pure inline.
    frame_idx: BTreeMap<String, u32>,
    // NetId → per-unpacked-dimension DESCENDING flag (`mem[3:0]` ⇒ [true]).
    // Recorded only when some dim is descending (absent = all ascending);
    // array ASSIGNMENT pairs elements positionally left-to-right in DECLARED
    // index order (IEEE 1800 §7.6), so the copy expansion needs the declared
    // direction that `(lo, size)` extents erase. elaborate-LOCAL only.
    array_dim_desc: BTreeMap<u32, Vec<bool>>,
    // Every net DECLARED with static unpacked dims — including 1-element
    // arrays (`reg x [0:0]`), which `array_len > 1` cannot distinguish from
    // scalars (adversarial find #5). elaborate-LOCAL only.
    unpacked_array_nets: BTreeSet<u32>,
    // NetId → per-PACKED-dimension `(lo, width)` for multi-dim packed arrays
    // (`logic [3:0][7:0]` ⇒ [(0,4),(0,8)]). The net is a flat `product(width)`-bit
    // vector; a select `m[i]` is the bit-SLICE `[i*stride +: elem_width]` (vs the
    // unpacked word-select). elaborate-LOCAL — NEVER in the frozen sim-ir.
    packed_dims: BTreeMap<u32, Vec<(u32, u32)>>,
    // v5 ⑥: the active `$` substitution while lowering a QUEUE element index —
    // the ExprId of `size(handle)-1`. Save/restore around each queue index so
    // nested selects (`q[$ - r[$]]`) bind each `$` to ITS OWN queue. `None`
    // outside a queue index ⇒ a bare `$` is loud-rejected.
    dollar_subst: Option<u32>,
    // v5 ⑥ (D): interface declarations (OWNED clones — avoids threading the
    // unit lifetime) + the registry of elaborated interface INSTANCES
    // (FQ path → interface name) consulted by interface-port binding.
    ifaces: BTreeMap<String, ast::ModuleDecl>,
    iface_insts: BTreeMap<String, String>,
    /// v6 ②: symbol keys aliased through a modport whose direction is INPUT —
    /// writes through these names are loud (§25.5). Keyed at alias-copy time;
    /// empty unless a modport binding is live (zero steady cost).
    modport_readonly: BTreeSet<String>,

    // ── v3 hierarchy state ──
    // `cur_prefix` is the dotted instance path of the instance currently being
    // lowered ("tb", then "tb.dut", …). The symbol table is keyed by the FQ name
    // `cur_prefix + "." + local`, so `tb.q` and `tb.dut.q` never collide. Empty
    // only transiently (the top is always given its module name as the root path).
    cur_prefix: String,
    // FQ param-name → const value, visible while lowering an instance scope.
    // Re-points the v1 free `const_eval_u32` SLOT so `[W-1:0]` folds to a width.
    params: BTreeMap<String, i64>,
    // module names on the active instantiation path — the recursion cycle guard.
    inst_stack: Vec<String>,
    // Instance id of the instance whose body is currently being lowered. Set in
    // `elaborate_instance` step (2) (saved/restored like `cur_prefix`), so a
    // child instance created from *inside* a generate block (`elaborate_generate`
    // → `lower_gen_module_item`) can record the correct `Instance.parent` without
    // threading the id through every generate-walk call.
    cur_inst: u32,

    // ── user function/task inlining (SD2 inline path) ──
    // name → def (OWNED clone), populated per-module from ModuleItem::Func/Task in
    // `elaborate_instance` BEFORE lowering that module's logic. Cleared/restored
    // per instance scope so a child module never sees a parent's functions by bare
    // name (matches the per-instance net isolation of `walk_scopes`). Cloning the
    // small defs sidesteps threading an AST lifetime through the whole driver; the
    // tables are point-queried only (BTreeMap), never iterated into arena order.
    func_table: BTreeMap<String, ast::FunctionDef>,
    task_table: BTreeMap<String, ast::TaskDef>,
    // Named SVA declarations (Phase-3 named-SVA slice): bare name → decl, collected
    // per-instance like func_table/task_table (saved/restored so siblings don't
    // inherit). Kept SEPARATE from the net symbol table so a net and a sequence of
    // the same name coexist — only the assert-property-instance position and
    // `expand_sequence`'s bare-ident leaves consult these (the func/task-name
    // namespace precedent). Inlined at use sites → pure IR-0, golden untouched.
    seq_table: BTreeMap<String, ast::SeqDecl>,
    prop_table: BTreeMap<String, ast::PropDecl>,
    // Recursion guard for named-sequence inlining (separate from `inline_stack`,
    // which is empty by the time SVA checkers materialize, but a dedicated stack
    // keeps SVA correctness independent of func/task inline state).
    sva_inline_stack: Vec<String>,

    // Substitution scope: a formal-param NAME currently bound to an actual ExprId
    // (a function/task INPUT formal during inlining). `lower_expr`'s Ident arm
    // consults this FIRST: a bare single-segment Ident matching a key lowers to the
    // bound ExprId, not a net — exactly like `Paren` unwrapping (no new IR node). A
    // Vec used as a stack so nested inlining + shadowing resolve innermost-wins via
    // reverse linear scan. Empty in steady state (one `is_empty`/scan on the hot
    // path costs nothing).
    subst: Vec<(String, u32)>,
    // Output/inout task formal NAME → caller NetId. Consulted in BOTH `lower_expr`
    // (read) and `collect_lval_chunks` (write) so a formal resolves to the caller's
    // net in either position. Symmetric Vec stack with `subst`.
    out_subst: Vec<(String, u32)>,
    // Recursion guard: function/task names on the active inline-expansion stack. A
    // name found here when we try to inline it = direct or mutual recursion =
    // E-ELAB-UNSUPPORTED (SD2: recursive ⇒ frame-call, deferred). Mirrors
    // `inst_stack`.
    inline_stack: Vec<String>,

    // ── fork/join concurrency state (engine-facing side channel, NOT in SimIr) ──
    // `fork_modes` maps (cur_proc, join_bb) → JoinMode for every fork lowered; it
    // is threaded into the engine via SimOpts.fork_modes (never the golden root).
    fork_modes: ForkModeTable,
    // `cur_proc` is the ProcId the process currently being lowered WILL occupy when
    // the caller pushes it (== self.processes.len() at lower_proc_block entry). Any
    // record_fork_mode during that body is keyed by exactly this id, so the engine's
    // (template, join_bb) lookup is guaranteed to hit.
    cur_proc: u32,
    // Nesting guard: true while lowering a fork CHILD body. A `Stmt::Fork` seen with
    // `in_fork == true` is the nested case → hard ElabUnsupported error (v1 MVP cut).
    in_fork: bool,
    // `disable` lowering state: (label, exit-BB) per lexically-enclosing NAMED
    // begin-block of the statement being lowered. Exit BBs are allocated LAZILY
    // (pre-scan: only labels some `disable` in the block body actually targets),
    // so designs without disable lower to byte-identical CFGs (golden corpus
    // untouched). `disable_fork_floor` is the stack depth at the current
    // fork-child boundary: a child may only disable blocks INSIDE its own body —
    // a Goto across the fork boundary would bypass the join barrier.
    disable_stack: Vec<(String, BlockId)>,
    disable_fork_floor: usize,

    // ── timescale state (engine-facing side channel, NOT in SimIr) ──
    // module NAME → its delay-unit exponent (base-10 of seconds), and the design-wide
    // finest precision exponent (the global tick base). Both supplied by the glue from
    // `hdl_preprocess::resolve_module_timescales`. Empty/`-9` ⇒ the `1ns/1ns` base
    // (multiplier 1 everywhere → byte-identical to the pre-timescale lowering).
    mod_unit_exp: std::collections::BTreeMap<String, i8>,
    global_prec_exp: i8,
    // `--top` root override (worklib / multi-top selection): when `Some`, these
    // units are the roots — in the given order — instead of `pick_roots`.
    root_override: Option<Vec<String>>,
    // Delay multiplier `M = 10^(unit_exp − global_prec_exp)` of the module CURRENTLY
    // being lowered (saved/restored around each `elaborate_instance`, like cur_prefix).
    // `#delay` literals scale by this; `$time`/`$realtime` divide by it (per process).
    cur_time_mult: u64,
    // Per-ProcId multiplier table (parallel to `processes`), threaded to the engine via
    // `SimOpts.proc_multipliers` for `$time`/`$realtime` scaling. NEVER in the golden root.
    proc_multipliers: Vec<u32>,

    // ── severity-task state (engine-facing side channel, NOT in SimIr) ──
    // StmtId → SeverityKind for every `$fatal`/`$error`/`$warning`/`$info` lowered
    // (each as a `SysTaskId::Display` stmt). Threaded via `SimOpts.severities`.
    severities: SeverityTable,
    // StmtId → default radix (2/8/16) for the b/o/h print-task variants (P1-5).
    radixes: RadixTable,
    // StmtIds of Force/Release stmts that are procedural assign/deassign (§9.3.1
    // weak rank — see [`AssignRankTable`]).
    assign_ranks: AssignRankTable,
    // Bounded-queue bounds (v6 ③): handle NetId → N.
    queue_bounds: QueueBoundTable,
    // NetIds of named events (v5 batch B): each `event e` is a 64-bit counter
    // Reg (init 0). `->e` increments it; `@(e)` is plain AnyEdge sensitivity.
    // The set guards the VALUE surface — an event cannot be read or written.
    event_nets: std::collections::BTreeSet<u32>,
    // Per-ProcId instance path for `%m` (P2-11); lockstep with `processes`.
    proc_scopes: Vec<String>,
    // v8 SVA: concurrent assertions collected during statement lowering, drained
    // into synthesized clocked checker processes after each module's process loop.
    pending_sva: Vec<PendingSva>,
    // §16.4 deferred immediate asserts (out-of-band, engine-facing): marker
    // StmtId → region, and action StmtId → (marker StmtId, region). See
    // [`DeferMarkTable`]/[`DeferActTable`].
    defer_marks: DeferMarkTable,
    defer_acts: DeferActTable,
    // Set while lowering a deferred assert's pass/fail arms: (marker StmtId,
    // region). The `push_stmt` hook records every SysTask emitted under it into
    // `defer_acts`, path-independently (severity OR plain $display).
    cur_defer: Option<(u32, DeferRegion)>,
    // One-shot W-note: a deferred-assert arm contained no deferrable action
    // (only side-effecting statements), so it ran inline (evaluate-when-reached).
    defer_inline_warned: bool,
}

impl<'s> Elaborator<'s> {
    fn new(sink: &'s dyn LogSink) -> Self {
        Self {
            sink,
            had_error: false,
            nets: Vec::new(),
            exprs: Vec::new(),
            consts: Vec::new(),
            cont_assigns: Vec::new(),
            instances: Vec::new(),
            processes: Vec::new(),
            stmts: Vec::new(),
            symbols: BTreeMap::new(),
            const_dedup: BTreeMap::new(),
            array_dims: BTreeMap::new(),
            bits_prescan: BTreeMap::new(),
            pkg_consts: BTreeMap::new(),
            pkg_funcs: BTreeMap::new(),
            pkg_tasks: BTreeMap::new(),
            cu_imports: Vec::new(),
            final_procs: std::collections::BTreeSet::new(),
            func_metas: Vec::new(),
            funcs: Vec::new(),
            func_blocks: Vec::new(),
            frame_idx: BTreeMap::new(),
            array_dim_desc: BTreeMap::new(),
            unpacked_array_nets: BTreeSet::new(),
            packed_dims: BTreeMap::new(),
            dollar_subst: None,
            ifaces: BTreeMap::new(),
            iface_insts: BTreeMap::new(),
            modport_readonly: BTreeSet::new(),
            cur_prefix: String::new(),
            params: BTreeMap::new(),
            inst_stack: Vec::new(),
            cur_inst: 0,
            func_table: BTreeMap::new(),
            task_table: BTreeMap::new(),
            seq_table: BTreeMap::new(),
            prop_table: BTreeMap::new(),
            sva_inline_stack: Vec::new(),
            subst: Vec::new(),
            out_subst: Vec::new(),
            inline_stack: Vec::new(),
            fork_modes: ForkModeTable::new(),
            severities: SeverityTable::new(),
            radixes: RadixTable::new(),
            assign_ranks: AssignRankTable::new(),
            queue_bounds: QueueBoundTable::new(),
            event_nets: std::collections::BTreeSet::new(),
            proc_scopes: Vec::new(),
            pending_sva: Vec::new(),
            defer_marks: DeferMarkTable::new(),
            defer_acts: DeferActTable::new(),
            cur_defer: None,
            defer_inline_warned: false,
            cur_proc: 0,
            in_fork: false,
            disable_stack: Vec::new(),
            disable_fork_floor: 0,
            mod_unit_exp: BTreeMap::new(),
            root_override: None,
            global_prec_exp: -9, // 1ns base precision (no-timescale lock)
            cur_time_mult: 1,
            proc_multipliers: Vec::new(),
        }
    }

    /// Delay multiplier `M = 10^(unit_exp − global_prec_exp)` for module `name`
    /// (≥ 1, since every module's `unit_exp ≥ global_prec_exp`). A module absent from
    /// the map (the no-timescale base) defaults to `unit_exp = global_prec_exp` ⇒ M=1.
    /// The exponent is capped at 18 so `10u64.pow` never overflows on an absurd ratio.
    fn module_mult(&self, name: &str) -> u64 {
        let u = self
            .mod_unit_exp
            .get(name)
            .copied()
            .unwrap_or(self.global_prec_exp);
        let diff = (u - self.global_prec_exp).max(0) as u32;
        10u64.pow(diff.min(18))
    }

    /// Append a process AND its time multiplier in lockstep (invariant:
    /// `proc_multipliers.len() == processes.len()`). The engine reads the table from
    /// `SimOpts.proc_multipliers` to scale `$time`/`$realtime` per calling module.
    fn push_process(&mut self, p: ir::Process) {
        self.proc_multipliers
            .push(self.cur_time_mult.min(u32::MAX as u64) as u32);
        // `%m` scope: the instance path of the module being lowered ("tb.u1");
        // an empty prefix (single top) renders as the top module's own name —
        // but cur_prefix is ALWAYS the instance path incl. the top ("m" / "m.u1").
        self.proc_scopes.push(self.cur_prefix.clone());
        self.processes.push(p);
    }

    fn finish(self) -> ir::SimIr {
        ir::SimIr {
            instances: self.instances,
            nets: self.nets,
            processes: self.processes, // ← v2: procedural lowering
            cont_assigns: self.cont_assigns,
            // B1 frame-call: automatic/recursive functions lowered to the func
            // arena. EMPTY for every design with no frame functions (the inline
            // path is unchanged) → `ir.funcs`/`ir.blocks` stay empty, golden-neutral.
            funcs: self.funcs,
            exprs: self.exprs,
            stmts: self.stmts,        // ← v2: per-BB straight-line stmt arena
            blocks: self.func_blocks, // B1 frame-call: func-body CFGs (global, rebased)
            consts: self.consts,
        }
    }

    /// Per-NetId fully-qualified name table for the VCD writer, built by inverting
    /// the FQ-name → NetId `symbols` map (`"top.dut.q"`). A net with no symbol entry
    /// (anonymous/implicit) falls back to `n{id}`. BTreeMap iteration is sorted, so
    /// a net mapped by several aliases keeps the lexicographically smallest FQ name
    /// (its canonical declaration path). Order-independent of arena order → 3-OS
    /// stable. Computed before `finish()` (which moves `self.nets`/`self.symbols`).
    fn net_name_table(&self) -> Vec<String> {
        let mut names = vec![String::new(); self.nets.len()];
        for (fq, &id) in &self.symbols {
            if let Some(slot) = names.get_mut(id as usize) {
                if slot.is_empty() {
                    *slot = fq.clone();
                }
            }
        }
        for (i, n) in names.iter_mut().enumerate() {
            if n.is_empty() {
                *n = format!("n{i}");
            }
        }
        names
    }

    /// THE deterministic stmt append point (mirror of [`Self::push_expr`]).
    #[inline]
    fn push_stmt(&mut self, s: ir::Stmt) -> u32 {
        // §16.4: while lowering a deferred assert's pass/fail arm, every SysTask
        // emitted (the $error/$display/$fatal/… action — any lowering path) is
        // recorded as a deferred ACTION so the engine enqueues it under the
        // assertion's marker instead of firing it inline. Path-independent: both
        // `lower_severity_task` and the plain `$display` path funnel through here.
        if let Some((marker, region)) = self.cur_defer {
            if matches!(s, ir::Stmt::SysTask { .. }) {
                let id = self.stmts.len() as u32;
                self.defer_acts.insert(id, (marker, region));
            }
        }
        let id = self.stmts.len() as u32;
        self.stmts.push(s);
        id
    }

    // ── diagnostics ────────────────────────────────────────────────
    /// Emit an error-severity diagnostic and flag failure. v1 has no line table
    /// → `location: None`; the byte span (when relevant) goes into `message`.
    /// HOOK: when elaborate grows a span side-table, fill `SourceLoc` here.
    fn error(&mut self, code: MsgCode, msg: &str) {
        self.had_error = true;
        self.sink.emit(LogEvent::Diagnostic(Diagnostic {
            severity: Severity::Error,
            code,
            message: msg.to_string(),
            location: None,
            context: Vec::new(),
            sim_time: None,
        }));
    }

    /// Emit a WARNING-severity diagnostic and KEEP GOING — does NOT set
    /// `had_error`, so the SimIr survives and is returned. This is the lever that
    /// makes unsupported *procedural* constructs and unknown `$task`s degrade
    /// (skip / no-op) instead of discarding the whole module (COVERAGE M-A/M-B/M-D).
    /// Reuses `ElabWidthTrunc` (W-ELAB-WIDTH-TRUNC / VITA-W3008) as the generic
    /// "lowered with a documented approximation" warning channel until a dedicated
    /// W-ELAB-DEGRADED code is minted. The message carries the specifics.
    fn warn(&mut self, msg: &str) {
        // P2-10: the generic warn class is "legal construct accepted but
        // simplified" (W-ELAB-FEATURE-LIMIT) — it used to stamp EVERY warning
        // `W-ELAB-WIDTH-TRUNC`, breaking the doc-15 bijection/suppress routing.
        self.warn_code(MsgCode::ElabFeatureLimit, msg);
    }

    /// Emit a Warning with a SPECIFIC code (the generic [`Self::warn`] uses
    /// `W-ELAB-WIDTH-TRUNC`).
    fn warn_code(&mut self, code: MsgCode, msg: &str) {
        self.sink.emit(LogEvent::Diagnostic(Diagnostic {
            severity: Severity::Warning,
            code,
            message: msg.to_string(),
            location: None,
            context: Vec::new(),
            sim_time: None,
        }));
    }

    /// Emit a hard "construct not supported in this subset" error, reusing the
    /// EXISTING `ElabUnsupported` code (no new MsgCode minted → doc-15 bijection
    /// untouched). The `_span` is accepted for a future side-table; v1 has no line
    /// table so it carries no location (consistent with `error`).
    fn error_unsupported(&mut self, _span: ast::Span, msg: &str) {
        self.error(MsgCode::ElabUnsupported, msg);
    }

    /// Record a fork's join MODE into the side table, keyed by `(cur_proc,
    /// join_bb)`. The engine's lookup is total-or-fatal, so every fork MUST record.
    fn record_fork_mode(&mut self, join: ast::JoinKind, join_bb: u32) {
        let mode = match join {
            ast::JoinKind::Join => JoinMode::All,
            ast::JoinKind::JoinAny => JoinMode::Any,
            ast::JoinKind::JoinNone => JoinMode::None,
        };
        self.fork_modes.insert((self.cur_proc, join_bb), mode);
    }

    // ── v3 multi-module driver ─────────────────────────────────────
    /// Build the module-name map, pick the top, then recursively flatten the
    /// hierarchy into ONE SimIr. The v1 single-module path is now the special
    /// case `top instantiating nothing` (one Instance, parent None).
    fn run(&mut self, unit: &ast::SourceUnit) {
        let (map, order) = build_module_map(unit);
        // v5 ⑥ (D): interfaces live in their OWN map (they are never roots and
        // never modules); a name colliding with a module is a duplicate design
        // unit (single design-unit namespace, doc-15 E-DUP-UNIT).
        for it in &unit.items {
            if let ast::TopItem::Interface(i) = it {
                if map.contains_key(i.name.name.as_str())
                    || self.ifaces.insert(i.name.name.clone(), i.clone()).is_some()
                {
                    self.error(
                        MsgCode::DupUnit,
                        &format!("design unit `{}` declared more than once", i.name.name),
                    );
                }
            }
            // v7 P2-D: packages register into their own maps (never roots);
            // a name colliding with a module/interface/package is E-DUP-UNIT.
            if let ast::TopItem::Package(pm) = it {
                if map.contains_key(pm.name.name.as_str())
                    || self.ifaces.contains_key(&pm.name.name)
                    || self.pkg_consts.contains_key(&pm.name.name)
                {
                    self.error(
                        MsgCode::DupUnit,
                        &format!("design unit `{}` declared more than once", pm.name.name),
                    );
                } else {
                    self.elaborate_package(pm);
                }
            }
            if let ast::TopItem::Import(i) = it {
                self.cu_imports.push(i.clone());
            }
        }
        if order.is_empty() {
            // "no module at all" is a missing-construct condition, not a failed
            // *instance* resolution → ElabUnsupported reads truer.
            self.error(MsgCode::ElabUnsupported, "no top module to elaborate");
            return;
        }
        // Warn on duplicate module names (first-decl wins in the map).
        let mut seen: BTreeMap<&str, u32> = BTreeMap::new();
        for m in &order {
            *seen.entry(m.name.name.as_str()).or_insert(0) += 1;
        }
        for (name, n) in seen {
            if n > 1 {
                // P2-11: duplicate design-unit definition is an ERROR (doc-15
                // E-DUP-UNIT; iverilog parity) — was a warn + first-decl-wins.
                self.error(
                    MsgCode::DupUnit,
                    &format!("module `{name}` declared {n} times"),
                );
            }
        }

        let roots = match self.root_override.clone() {
            // `--top` override: the named units, in the given order. Unknown
            // names are loud — silently elaborating the default set instead
            // would be a silent-wrong root selection.
            Some(tops) => {
                let mut sel = Vec::new();
                for t in &tops {
                    match map.get(t.as_str()) {
                        Some((m, _)) => sel.push(*m),
                        None => {
                            self.error(
                                MsgCode::ElabUnsupported,
                                &format!("top module `{t}` not found in the design"),
                            );
                            return;
                        }
                    }
                }
                sel
            }
            None => pick_roots(&map, &order),
        };
        if roots.is_empty() {
            self.error(MsgCode::ElabUnsupported, "no top module to elaborate");
            return;
        }

        // Each root is its OWN top instance: parent None, path = its module name
        // (root VCD scope), no incoming port/param bindings. `elaborate_instance`
        // saves/restores all scope state (cur_prefix/cur_inst/cur_time_mult/params/
        // func_table/task_table/inst_stack), so roots are independent and the flat
        // arenas stay contiguous per instance. The common single-top design has one
        // root → byte-identical to the old single-pick path.
        for top in roots {
            let top_path = top.name.name.clone();
            self.elaborate_instance(top, &top_path, None, &[], PortBinding::None, &map);
        }

        // whole-net multidriver check over the WHOLE flat IR (instance-agnostic).
        self.check_whole_net_multidriver();
    }

    /// Recursively elaborate ONE module instance into the flat SimIr.
    ///
    /// Bookkeeping order is the load-bearing determinism contract:
    ///  (1) cycle guard; (2) reserve the Instance slot + record `first_net`;
    ///  (3) bind params (so width exprs fold); (4) create THIS instance's nets
    ///  (ANSI ports, then body NetVarDecls — declaration order); (5) patch
    ///  `net_count`; (6) wire ports (parent expr ↔ child port net) as cont-assigns;
    ///  (7) lower THIS body's cont-assigns + processes; (8) recurse into child
    ///  instances in body declaration order.
    ///
    /// Step (8) runs strictly AFTER (4), so the parent's `[first_net,
    /// first_net+net_count)` slice is a contiguous run with no child nets spliced
    /// in — the Instance slice invariant.
    fn elaborate_instance(
        &mut self,
        module: &ast::ModuleDecl,
        inst_path: &str,
        parent_inst: Option<u32>,
        param_overrides: &[ResolvedOverride],
        binding: PortBinding<'_>,
        map: &ModuleMap<'_>,
    ) {
        // (1) CYCLE GUARD — recursive instantiation is illegal (LRM). Bail this
        //     subtree WITHOUT creating any net/Instance so the arena stays valid.
        if self.inst_stack.iter().any(|m| m == &module.name.name) {
            self.error(
                MsgCode::ElabUnsupported,
                &format!(
                    "recursive module instantiation of `{}` (cycle: {} -> {})",
                    module.name.name,
                    self.inst_stack.join(" -> "),
                    module.name.name
                ),
            );
            return;
        }
        self.inst_stack.push(module.name.name.clone());

        // (2) reserve Instance slot + first_net cursor.
        let inst_id = self.instances.len() as u32;
        let first_net = self.nets.len() as u32;
        self.instances.push(ir::Instance {
            parent: parent_inst,
            module: 0, // sim-engine ignores this; 0 for v3 (no module table needed)
            first_net,
            net_count: 0, // patched in (5)
        });

        // Enter this instance's scope (restored before returning).
        let saved_prefix = std::mem::replace(&mut self.cur_prefix, inst_path.to_string());
        // Record this as the instance currently being lowered, so a child created
        // inside a generate block can set its `Instance.parent` to `inst_id`.
        let saved_inst = std::mem::replace(&mut self.cur_inst, inst_id);
        // This module's delay multiplier governs every `#delay` and process lowered
        // in its body (restored on the way out, like cur_prefix/cur_inst).
        let new_mult = self.module_mult(&module.name.name);
        let saved_mult = std::mem::replace(&mut self.cur_time_mult, new_mult);

        // (3) bind params (defaults, then overrides) — BEFORE nets so [W-1:0] folds.
        let mut saved_params = self.bind_params(module, param_overrides);

        // (3a.5) v7 P2-D imports — CONST symbols bind first so body params
        //        and ranges can use them; a later LOCAL declaration of the
        //        same name simply rebinds (local wins, iverilog-pinned).
        //        Function/task imports apply after (3.5) below.
        let import_list: Vec<ast::ImportDecl> = self
            .cu_imports
            .clone()
            .into_iter()
            .chain(module.body.iter().filter_map(|it| match it {
                ast::ModuleItem::Import(i) => Some(i.clone()),
                _ => None,
            }))
            .collect();
        for imp in &import_list {
            self.apply_import_consts(imp, &mut saved_params);
        }

        // (3b) BODY-level `parameter`/`localparam` (a `ModuleItem::Param`, NOT in
        //      the ANSI `#(...)` header that `bind_params` handles). Bind in decl
        //      order — a `localparam C = A*B+1` may reference an earlier param —
        //      BEFORE nets so `[W-1:0]` folds and runtime refs (`x = P`) resolve.
        //      Net decls in the SAME walk pre-register their widths (v7), so a
        //      decl-order `localparam X = $bits(mem[0])` folds too.
        let saved_prescan = std::mem::take(&mut self.bits_prescan);
        for item in &module.body {
            match item {
                ast::ModuleItem::Param(p) => {
                    // Unfoldable value = LOUD error (never a silent 0): a parameter
                    // bound to a wrong default poisons every downstream width with
                    // no trace (P0-5). 0 stays only as the post-error recovery value.
                    let v = self.const_eval_in_scope(&p.value).unwrap_or_else(|| {
                        self.error(
                            MsgCode::ElabUnsupported,
                            &format!(
                                "parameter `{}` value is not a foldable constant expression",
                                p.name.name
                            ),
                        );
                        0
                    });
                    let key = self.fq(&p.name.name);
                    saved_params.push((key.clone(), self.params.insert(key, v)));
                }
                ast::ModuleItem::NetVar(d) => self.prescan_net_bits(d),
                _ => {}
            }
        }

        // (3c) `typedef enum {…}` labels → integer constants (RED=0, GREEN=1, …),
        //      registered like localparams so a runtime `c = GREEN` folds. An
        //      explicit `LABEL = expr` resets the running counter (next = expr+1).
        for item in &module.body {
            if let ast::ModuleItem::Typedef(td) = item {
                #[allow(irrefutable_let_patterns)]
                if let ast::TypedefKind::Enum { labels, .. } = &td.kind {
                    let mut next: i64 = 0;
                    for lab in labels {
                        let v = match &lab.value {
                            Some(e) => self.const_eval_in_scope(e).unwrap_or_else(|| {
                                self.error(
                                    MsgCode::ElabUnsupported,
                                    &format!(
                                        "enum label `{}` value is not a foldable constant",
                                        lab.name.name
                                    ),
                                );
                                0
                            }),
                            None => next,
                        };
                        let key = self.fq(&lab.name.name);
                        saved_params.push((key.clone(), self.params.insert(key, v)));
                        next = v.wrapping_add(1);
                    }
                }
            }
        }

        // (3.5) collect THIS module's functions/tasks (bare name → def) for inline
        //       expansion at call sites (pass 7). Saved/restored so a sibling/parent
        //       instance of another module does not inherit them. Functions are not
        //       hierarchical in v1, so the bare name is the key.
        let saved_funcs = std::mem::take(&mut self.func_table);
        let saved_tasks = std::mem::take(&mut self.task_table);
        // B1 frame-call: the frame-func name→id map is module-local (a sibling
        // module's call must never divert to this module's func). The global
        // `funcs`/`func_blocks`/`func_metas` arenas are NOT saved (they accumulate).
        let saved_frame_idx = std::mem::take(&mut self.frame_idx);
        // Named SVA seq/prop decls collected in the SAME whole-body prescan, so an
        // `assert property(p)` BEFORE `property p; …` (forward reference) resolves —
        // identical mechanism to func/task. Saved/restored alongside.
        let saved_seqs = std::mem::take(&mut self.seq_table);
        let saved_props = std::mem::take(&mut self.prop_table);
        for item in &module.body {
            match item {
                ast::ModuleItem::Func(f) => {
                    if self
                        .func_table
                        .insert(f.name.name.clone(), f.clone())
                        .is_some()
                    {
                        self.warn(&format!(
                            "function `{}` redeclared; first declaration used",
                            f.name.name
                        ));
                    }
                }
                ast::ModuleItem::Task(t) => {
                    if self
                        .task_table
                        .insert(t.name.name.clone(), t.clone())
                        .is_some()
                    {
                        self.warn(&format!(
                            "task `{}` redeclared; first declaration used",
                            t.name.name
                        ));
                    }
                }
                // FIRST declaration wins (insert-if-absent), so the redeclaration
                // warning text is accurate (review 2026-06-16: `BTreeMap::insert`
                // would keep the LAST, contradicting "first declaration used").
                ast::ModuleItem::SequenceDecl(s) => self.register_seq_decl(s),
                ast::ModuleItem::PropertyDecl(p) => self.register_prop_decl(p),
                // SVA decls inside a `generate` block are module-global too (slice
                // A4): the prescan walks generate structurally (no const-eval / no
                // genvar binding) so a reference resolves regardless of loop trip
                // count or which branch the const-cond later selects.
                ast::ModuleItem::Generate(g) => self.collect_gen_sva_decls(&g.items),
                _ => {}
            }
        }
        // (3.6) v7 P2-D: imported functions/tasks — LOCAL definitions win
        // (skip-if-present, no spurious redeclare warning).
        for imp in &import_list {
            self.apply_import_routines(imp);
        }

        // (4) this instance's nets: ANSI ports, then body NetVarDecls (decl order).
        //     add_net now keys through `fq`, so names become inst_path-prefixed.
        self.elaborate_ports(&module.ports);
        for item in &module.body {
            if let ast::ModuleItem::NetVar(d) = item {
                self.elaborate_netvar_decl(d, &module.ports, &module.body);
            }
        }
        // Non-ANSI port nets: a body `input/output [w] name;` (a `PortDecl`)
        // declares the port net. `elaborate_ports` only builds ANSI header ports,
        // so without this a non-ANSI module's ports are undeclared. Skip a name a
        // separate `reg`/`wire` NetVarDecl already created (`output y; reg y;` —
        // that path merges the port direction itself).
        for item in &module.body {
            if let ast::ModuleItem::PortDecl(pd) = item {
                let kind = pd.net_or_var.unwrap_or(ast::NetVarKind::Wire);
                let (width, msb, lsb, signed) =
                    self.range_to_dims(kind, pd.range.as_ref(), pd.signed);
                let dir = map_port_dir(pd.dir);
                let init = default_init(kind, width);
                for name in &pd.names {
                    if self.symbols.contains_key(&self.fq(&name.name)) {
                        continue; // already created by a NetVarDecl
                    }
                    self.add_net(
                        &name.name,
                        ir::NetVar {
                            kind: map_net_kind_or_wire(kind),
                            width,
                            msb,
                            lsb,
                            signed,
                            array_len: 1,
                            dir,
                            init: init.clone(),
                        },
                    );
                }
            }
        }
        // Procedural block-local declarations (`begin: blk integer x; …`). v1 has
        // no per-process automatic frame, so a block-local flattens to a module-
        // scope net — created HERE (Nets phase) so it lands in this instance's net
        // slice and references inside the block resolve instead of erroring E3010.
        for item in &module.body {
            if let ast::ModuleItem::Proc(p) = item {
                self.hoist_block_local_nets(&p.body, &module.ports, &module.body);
            }
        }
        // Generate-block nets belong in THIS instance's contiguous net slice too:
        // unroll the generate, in the Nets phase only, right after the plain
        // body nets so they precede every cont-assign/process (pass 7) that may
        // reference them, and precede child-instance recursion (pass 8).
        for item in &module.body {
            if let ast::ModuleItem::Generate(g) = item {
                self.elaborate_generate(&g.items, GenPhase::Nets, 0, map);
            }
        }

        // (5) net_count = nets created for THIS instance only (not children).
        let net_count = self.nets.len() as u32 - first_net;
        self.instances[inst_id as usize].net_count = net_count;

        // (4c) v5 ⑥ (D): flatten DIRECT-body interface instances EARLY (nets
        // phase) — unlike module children (whose nets are per-instance
        // private), interface members ARE the parent-visible API (`i.sig` in
        // pass-7 bodies must resolve). Generate-nested ones flatten in the
        // late pass (8); the per-item registry guard makes both idempotent.
        for item in &module.body {
            if let ast::ModuleItem::Instance(mi) = item {
                if self.ifaces.contains_key(mi.module_name.name.as_str()) {
                    self.elaborate_iface_instances(mi, false);
                }
            }
        }

        // (6) port-connection cont-assigns (parent expr ↔ child port net).
        self.wire_ports(module, binding, &saved_prefix);

        // (6.5) B1 frame-call: RESERVE + LOWER every automatic/recursive function
        //       BEFORE the body lowering below, so a call site (step 7) can divert
        //       to a reserved FuncId. Runs AFTER the net_count freeze (5) so frame
        //       nets land OUTSIDE this Instance's [first_net, +net_count) slice;
        //       module scope is still active (module nets in `symbols`). No-op when
        //       the module declares no frame functions (frame_idx stays empty).
        self.lower_frame_funcs();

        // (7) lower THIS body: cont-assigns + processes (reuse v1/v2 helpers).
        for item in &module.body {
            match item {
                ast::ModuleItem::ContAssign(ca) => self.elaborate_cont_assign(ca),
                ast::ModuleItem::Proc(p) => {
                    let proc = self.lower_proc_block(p);
                    debug_assert_eq!(
                        self.processes.len() as u32,
                        self.cur_proc,
                        "ProcId mismatch: fork_modes keyed by cur_proc would miss"
                    );
                    self.push_process(proc);
                }
                // (8) handled in the second loop below.
                ast::ModuleItem::Instance(_) => {}
                // Generate: nets already created (pass 4 net-walk); here lower its
                // cont-assigns + processes (Logic phase). Child instances inside it
                // recurse in pass (8) below.
                ast::ModuleItem::Generate(g) => {
                    self.elaborate_generate(&g.items, GenPhase::Logic, 0, map);
                }
                // Func/Task are DEFINITIONS, not logic: collected in step (3.5)
                // and expanded at their call sites (inline). No-op here.
                ast::ModuleItem::Func(_) | ast::ModuleItem::Task(_) => {}
                ast::ModuleItem::Defparam(_) => {
                    self.error(MsgCode::ElabUnsupported, "construct deferred (defparam)");
                }
                // A NET declaration initializer (`wire x = expr;`) is an implicit
                // continuous assign — lower it as a driver here (the net itself was
                // created in pass 4). A variable initializer is a one-time value.
                ast::ModuleItem::NetVar(d) => self.elaborate_net_init_drivers(d),
                // Param/PortDecl/Genvar/Error: no-op here.
                _ => {}
            }
        }

        // (7.5) v8 SVA: materialize every concurrent assertion collected during
        //       the process loop above as a synthesized clocked checker process.
        //       Drained here (this instance's scope) so child instances start clean.
        self.materialize_sva_checkers();

        // (8) recurse into child instances, in body declaration order — including
        //     those nested inside a generate construct (Instances phase).
        for item in &module.body {
            match item {
                ast::ModuleItem::Instance(mi) => {
                    self.elaborate_child_instances(mi, inst_id, map);
                }
                ast::ModuleItem::Generate(g) => {
                    self.elaborate_generate(&g.items, GenPhase::Instances, 0, map);
                }
                _ => {}
            }
        }

        // restore scope/params so siblings + ancestors resolve correctly.
        self.restore_params(saved_params);
        self.bits_prescan = saved_prescan;
        self.func_table = saved_funcs;
        self.task_table = saved_tasks;
        self.frame_idx = saved_frame_idx;
        self.seq_table = saved_seqs;
        self.prop_table = saved_props;
        self.cur_prefix = saved_prefix;
        self.cur_inst = saved_inst;
        self.cur_time_mult = saved_mult;
        self.inst_stack.pop();
    }

    /// Resolve a `ModuleInstance` statement (which may name several instances),
    /// and recurse into each child. Connection exprs are resolved later, in the
    /// PARENT scope (still active here), inside the child's `wire_ports`.
    fn elaborate_child_instances(
        &mut self,
        mi: &ast::ModuleInstance,
        parent_inst: u32,
        map: &ModuleMap<'_>,
    ) {
        let child = match map.get(mi.module_name.name.as_str()) {
            Some(&(decl, _)) => decl,
            None => {
                // v5 ⑥ (D): `intf i();` — an interface instance flattens to
                // plain nets under the instance prefix (no ir::Instance row,
                // no new IR — spike 2026-06-10).
                if self.ifaces.contains_key(mi.module_name.name.as_str()) {
                    self.elaborate_iface_instances(mi, true);
                    return;
                }
                self.error(
                    MsgCode::ElabUnresolvedInstance,
                    &format!("unknown module `{}` instantiated", mi.module_name.name),
                );
                return;
            }
        };

        // Fix 1: const-eval EVERY override expr NOW, in the PARENT scope, so a
        // parent-param-dependent override (`#(.W(PARENT_W))`) resolves. A failure
        // to fold is recorded as value=None (child keeps default + warns), never
        // a silent 0 that explodes the child's width.
        let mut overrides: Vec<ResolvedOverride> = Vec::with_capacity(mi.param_overrides.len());
        for ov in &mi.param_overrides {
            match ov {
                ast::ParamConn::Positional(e) => {
                    let value = self.const_eval_in_scope(e);
                    if value.is_none() {
                        self.warn(
                            "parameter override expression is not a constant; child default kept",
                        );
                    }
                    overrides.push(ResolvedOverride {
                        name: None,
                        value,
                        is_named: false,
                    });
                }
                ast::ParamConn::Named { name, value, .. } => {
                    // `.W()` (value None) means "keep default" → record is_named with value None.
                    let v = value.as_ref().and_then(|e| {
                        let r = self.const_eval_in_scope(e);
                        if r.is_none() {
                            self.warn(&format!(
                                "override of parameter `{}` is not a constant; default kept",
                                name.name
                            ));
                        }
                        r
                    });
                    overrides.push(ResolvedOverride {
                        name: Some(name.name.clone()),
                        value: v,
                        is_named: true,
                    });
                }
            }
        }

        for item in &mi.instances {
            if !item.unpacked.is_empty() {
                // Instance array (`dff u[3:0](...)`, IEEE 1364 §12.1.2-3):
                // unroll into per-index children with sliced connections.
                self.elaborate_instance_array(child, item, &overrides, parent_inst, map);
                continue;
            }
            let child_path = self.child_prefix(&item.name.name);
            let binding = match &item.conns {
                ast::PortConnList::Named(v) => PortBinding::Named(v),
                ast::PortConnList::Positional(v) => PortBinding::Positional(v),
            };
            self.elaborate_instance(
                child,
                &child_path,
                Some(parent_inst),
                &overrides,
                binding,
                map,
            );
        }
    }

    /// Unroll an instance array `child u[L:R](conns)` (IEEE 1364-2005
    /// §12.1.2-3) into N = |L−R|+1 children named `u[idx]`, idx walking the
    /// DECLARED order L→R. Connection rule (iverilog-pinned live 2026-06-12):
    /// a conn whose width equals the child port width P fans out to every
    /// instance; width N×P slices into P-bit chunks with the FIRST-named
    /// index taking the MOST significant chunk (both `[3:0]` and `[0:3]`);
    /// any other width is a loud error.
    ///
    /// v1 cuts (all loud E3009): exactly one constant range; ANSI-port child
    /// (port widths must fold under the instance's param overrides);
    /// non-interface ports; sliced/shared conns must be plain identifiers
    /// (part-select synthesis needs the parent net's declared [msb:lsb]).
    fn elaborate_instance_array(
        &mut self,
        child: &ast::ModuleDecl,
        item: &ast::InstanceItem,
        overrides: &[ResolvedOverride],
        parent_inst: u32,
        map: &ModuleMap<'_>,
    ) {
        const INST_ARRAY_CAP: u64 = 4096;
        let iname = item.name.name.clone();
        // ── range: exactly one constant [msb:lsb] ──
        let range = match item.unpacked.as_slice() {
            [ast::Dim::Range(r)] => r,
            _ => {
                self.error(
                    MsgCode::ElabUnsupported,
                    &format!("instance array `{iname}` needs exactly one [msb:lsb] range"),
                );
                return;
            }
        };
        let (Some(left), Some(right)) = (
            self.const_eval_in_scope(&range.msb),
            self.const_eval_in_scope(&range.lsb),
        ) else {
            self.error(
                MsgCode::ElabUnsupported,
                &format!("instance array `{iname}` range is not a constant"),
            );
            return;
        };
        let n64 = left.abs_diff(right) + 1;
        if n64 > INST_ARRAY_CAP {
            self.error(
                MsgCode::ElabUnsupported,
                &format!("instance array `{iname}` has {n64} elements (cap {INST_ARRAY_CAP})"),
            );
            return;
        }
        let n = n64 as u32;

        // ── child port widths, folded in the CHILD param scope (Fix-1 recipe) ──
        let ast::PortList::Ansi(ports) = &child.ports else {
            self.error(
                MsgCode::ElabUnsupported,
                &format!(
                    "instance array `{iname}`: child `{}` has non-ANSI ports (v1: ANSI only)",
                    child.name.name
                ),
            );
            return;
        };
        if ports.iter().any(|p| p.iface.is_some()) {
            self.error(
                MsgCode::ElabUnsupported,
                &format!("instance array `{iname}`: interface-typed ports are unsupported"),
            );
            return;
        }
        let saved = self.bind_params(child, overrides);
        let mut port_widths: Vec<(String, u32)> = Vec::with_capacity(ports.len());
        let mut widths_ok = true;
        for p in ports {
            let mut w: u64 = match &p.range {
                Some(r) => {
                    match (
                        self.const_eval_in_scope(&r.msb),
                        self.const_eval_in_scope(&r.lsb),
                    ) {
                        (Some(m), Some(l)) => m.abs_diff(l) + 1,
                        _ => {
                            widths_ok = false;
                            0
                        }
                    }
                }
                None => 1,
            };
            for r in &p.packed {
                match (
                    self.const_eval_in_scope(&r.msb),
                    self.const_eval_in_scope(&r.lsb),
                ) {
                    (Some(m), Some(l)) => w = w.saturating_mul(m.abs_diff(l) + 1),
                    _ => widths_ok = false,
                }
            }
            port_widths.push((p.name.name.clone(), w.min(u32::MAX as u64) as u32));
        }
        self.restore_params(saved);
        if !widths_ok {
            self.error(
                MsgCode::ElabUnsupported,
                &format!("instance array `{iname}`: a child port width does not const-fold"),
            );
            return;
        }
        let port_w = |name: &str| -> Option<u32> {
            port_widths.iter().find(|(n, _)| n == name).map(|x| x.1)
        };

        // ── per-connection slice plan ──
        // Shared = same expr to every instance; Slice carries the parent net's
        // declared (msb, lsb) so chunk part-selects follow its direction.
        enum Plan {
            Open,
            Shared,
            Slice { p: u32, msb: i64, lsb: i64 },
        }
        let conns: Vec<(ast::Ident, Option<&ast::Expr>, ast::Span)> = match &item.conns {
            ast::PortConnList::Named(v) => v
                .iter()
                .map(|pc| (pc.name.clone(), pc.value.as_ref(), pc.span))
                .collect(),
            ast::PortConnList::Positional(v) => v
                .iter()
                .enumerate()
                .map(|(i, e)| {
                    let pname = ports.get(i).map(|p| p.name.clone()).unwrap_or(ast::Ident {
                        name: format!("<positional {i}>"),
                        span: item.span,
                    });
                    (pname, e.as_ref(), item.span)
                })
                .collect(),
        };
        let mut plans: Vec<Plan> = Vec::with_capacity(conns.len());
        for (pname, value, _) in &conns {
            let Some(expr) = value else {
                plans.push(Plan::Open);
                continue;
            };
            let Some(p) = port_w(&pname.name) else {
                self.error(
                    MsgCode::ElabUnsupported,
                    &format!(
                        "instance array `{iname}`: no port `{}` on child",
                        pname.name
                    ),
                );
                return;
            };
            // Width the connection ACTUALLY has: plain identifiers only (the
            // slice must be a part-select of a declared net).
            let net_id = match &expr.kind {
                ast::ExprKind::Ident(hp) if hp.segments.len() == 1 => {
                    match self.lookup_net_scoped(&hp.segments[0].name) {
                        Some(id) => id,
                        None => {
                            self.error(
                                MsgCode::ElabUnresolvedName,
                                &format!(
                                    "undeclared net/variable `{}`",
                                    self.fq(&hp.segments[0].name)
                                ),
                            );
                            return;
                        }
                    }
                }
                _ => {
                    self.error(
                        MsgCode::ElabUnsupported,
                        &format!(
                            "instance array `{iname}`: connection for port `{}` must be a \
                             plain identifier (v1)",
                            pname.name
                        ),
                    );
                    return;
                }
            };
            let nv = &self.nets[net_id as usize];
            let (w, nmsb, nlsb) = (nv.width, nv.msb as i64, nv.lsb as i64);
            if w == p {
                plans.push(Plan::Shared);
            } else if (w as u64) == (n as u64) * (p as u64) {
                plans.push(Plan::Slice {
                    p,
                    msb: nmsb,
                    lsb: nlsb,
                });
            } else {
                self.error(
                    MsgCode::ElabUnsupported,
                    &format!(
                        "instance array `{iname}`: port `{}` width {p} expects a connection \
                         of width {p} or {}, got {w}",
                        pname.name,
                        (n as u64) * (p as u64)
                    ),
                );
                return;
            }
        }

        // ── unroll, slicing MSB-first in declared order ──
        let dec_lit = |v: i64, span: ast::Span| ast::Expr {
            kind: ast::ExprKind::IntLit {
                kind: ast::IntLitKind::Decimal,
                raw: v.to_string(),
            },
            span,
        };
        for k in 0..n {
            let idx = if left >= right {
                left - k as i64
            } else {
                left + k as i64
            };
            let inst_conns: Vec<ast::PortConn> = conns
                .iter()
                .zip(&plans)
                .map(|((pname, value, span), plan)| {
                    let value = match plan {
                        Plan::Open => None,
                        Plan::Shared => value.map(|e| (*e).clone()),
                        Plan::Slice { p, msb, lsb } => {
                            let e = value.expect("Slice plan implies a conn expr");
                            // Chunk k (MSB-first): walk from the net's declared
                            // MSB end toward the LSB end, P bits at a time.
                            let (hi, lo) = if msb >= lsb {
                                let hi = msb - (k as i64) * (*p as i64);
                                (hi, hi - (*p as i64 - 1))
                            } else {
                                // ascending [0:7]: the LEFT index is the MSB.
                                let hi = msb + (k as i64) * (*p as i64);
                                (hi, hi + (*p as i64 - 1))
                            };
                            Some(ast::Expr {
                                kind: ast::ExprKind::PartSelect {
                                    base: Box::new((*e).clone()),
                                    msb: Box::new(dec_lit(hi, *span)),
                                    lsb: Box::new(dec_lit(lo, *span)),
                                },
                                span: *span,
                            })
                        }
                    };
                    ast::PortConn {
                        name: pname.clone(),
                        value,
                        span: *span,
                    }
                })
                .collect();
            let child_path = self.child_prefix(&format!("{iname}[{idx}]"));
            self.elaborate_instance(
                child,
                &child_path,
                Some(parent_inst),
                overrides,
                PortBinding::Named(&inst_conns),
                map,
            );
        }
    }

    /// v5 ⑥ (D), extended v6 ②: flatten interface instances (`intf i();`)
    /// into plain nets under `cur_prefix.i` — interface signals ARE nets
    /// (spike: no new IR). v6 adds `#(parameter)` overrides and ANSI header
    /// ports (`interface bus(input logic c)`). Header-port CONNECTIONS wire
    /// in the LATE pass only (`wire_phase` — pass 8, when every parent net
    /// exists); the early 4c pass flattens for parent-body visibility.
    /// Non-ANSI / interface-typed header ports stay loud.
    fn elaborate_iface_instances(&mut self, mi: &ast::ModuleInstance, wire_phase: bool) {
        let iface_name = mi.module_name.name.clone();
        let Some(decl) = self.ifaces.get(&iface_name).cloned() else {
            return;
        };
        // v6 ②: per-instance parameter overrides — resolved NOW, in the
        // PARENT scope, exactly like the module-instance path (Fix 1).
        let mut overrides: Vec<ResolvedOverride> = Vec::with_capacity(mi.param_overrides.len());
        for ov in &mi.param_overrides {
            match ov {
                ast::ParamConn::Positional(e) => {
                    let value = self.const_eval_in_scope(e);
                    if value.is_none() {
                        self.warn("parameter override expression is not a constant; default kept");
                    }
                    overrides.push(ResolvedOverride {
                        name: None,
                        value,
                        is_named: false,
                    });
                }
                ast::ParamConn::Named { name, value, .. } => {
                    let v = value.as_ref().and_then(|e| {
                        let r = self.const_eval_in_scope(e);
                        if r.is_none() {
                            self.warn(&format!(
                                "override of parameter `{}` is not a constant; default kept",
                                name.name
                            ));
                        }
                        r
                    });
                    overrides.push(ResolvedOverride {
                        name: Some(name.name.clone()),
                        value: v,
                        is_named: true,
                    });
                }
            }
        }
        let ports_ok = match &decl.ports {
            ast::PortList::None => true,
            ast::PortList::Ansi(v) => v.iter().all(|p| p.iface.is_none()),
            ast::PortList::NonAnsi(v) => v.is_empty(),
        };
        if !ports_ok {
            self.error(
                MsgCode::ElabUnsupported,
                "non-ANSI or interface-typed header ports on an interface are outside the MVP",
            );
            return;
        }
        for item in &mi.instances {
            if !item.unpacked.is_empty() {
                self.error(
                    MsgCode::ElabUnsupported,
                    "interface instance arrays are outside the MVP",
                );
                continue;
            }
            let path = self.child_prefix(&item.name.name);
            if !self.iface_insts.contains_key(&path) {
                let saved_prefix = std::mem::replace(&mut self.cur_prefix, path.clone());
                // params (header `#(...)` then body localparams) BEFORE nets
                // so `[W-1:0]` folds — mirroring module passes (3)/(3b).
                let mut saved_params = self.bind_params(&decl, &overrides);
                for it in &decl.body {
                    if let ast::ModuleItem::Param(pp) = it {
                        let v = self.const_eval_in_scope(&pp.value).unwrap_or_else(|| {
                            self.error(
                                MsgCode::ElabUnsupported,
                                &format!(
                                    "parameter `{}` value is not a foldable constant expression",
                                    pp.name.name
                                ),
                            );
                            0
                        });
                        let key = self.fq(&pp.name.name);
                        saved_params.push((key.clone(), self.params.insert(key, v)));
                    }
                }
                // ANSI header ports → nets (the iface body + `i.<port>` see them).
                self.elaborate_ports(&decl.ports);
                // nets first (declaration order), then logic — mirroring the
                // module body passes (4)/(7).
                for it in &decl.body {
                    if let ast::ModuleItem::NetVar(d) = it {
                        self.elaborate_netvar_decl(d, &decl.ports, &decl.body);
                    }
                }
                for it in &decl.body {
                    match it {
                        ast::ModuleItem::ContAssign(ca) => self.elaborate_cont_assign(ca),
                        ast::ModuleItem::Proc(pb) => {
                            let proc = self.lower_proc_block(pb);
                            self.push_process(proc);
                        }
                        ast::ModuleItem::NetVar(d) => self.elaborate_net_init_drivers(d),
                        ast::ModuleItem::Modport(_) => {} // binding enforces dirs
                        ast::ModuleItem::Error(_)
                        | ast::ModuleItem::Param(_)
                        | ast::ModuleItem::PortDecl(_)
                        | ast::ModuleItem::Genvar { .. } => {}
                        other => {
                            let what = match other {
                                ast::ModuleItem::Instance(_) => "nested instances",
                                ast::ModuleItem::Generate(_) => "generate blocks",
                                ast::ModuleItem::Func(_) | ast::ModuleItem::Task(_) => {
                                    "functions/tasks"
                                }
                                ast::ModuleItem::Typedef(_) => "typedefs",
                                ast::ModuleItem::Defparam(_) => "defparam",
                                _ => "this construct",
                            };
                            self.error(
                                MsgCode::ElabUnsupported,
                                &format!("{what} inside an interface are outside the MVP"),
                            );
                        }
                    }
                }
                self.iface_insts.insert(path.clone(), iface_name.clone());
                self.restore_params(saved_params);
                self.cur_prefix = saved_prefix;
            }
            // v6 ②: header-port connections wire LATE (all parent nets exist
            // by pass 8); the early 4c call leaves them for this pass.
            if wire_phase {
                let has_conns = match &item.conns {
                    ast::PortConnList::Named(v) => !v.is_empty(),
                    ast::PortConnList::Positional(v) => !v.is_empty(),
                };
                let has_ports = !matches!(&decl.ports, ast::PortList::None)
                    && !matches!(&decl.ports, ast::PortList::Ansi(v) if v.is_empty());
                if has_conns && !has_ports {
                    self.error(
                        MsgCode::ElabPortMismatch,
                        "connections on a portless interface instance",
                    );
                    continue;
                }
                if has_ports {
                    let binding = match &item.conns {
                        ast::PortConnList::Named(v) => PortBinding::Named(v),
                        ast::PortConnList::Positional(v) => PortBinding::Positional(v),
                    };
                    let saved_prefix = std::mem::replace(&mut self.cur_prefix, path.clone());
                    let parent = saved_prefix.clone();
                    self.wire_ports(&decl, binding, &parent);
                    self.cur_prefix = saved_prefix;
                }
            }
        }
    }

    /// v5 ⑥ (D): bind an interface-typed module port by SYMBOL ALIASING —
    /// every net under the connected interface instance becomes visible as
    /// `<child>.<port>.<sig>` (net creation 0; canonical VCD naming is the
    /// lexicographically-smallest FQ, the established multi-FQ rule).
    fn bind_iface_port(
        &mut self,
        iref: &ast::IfaceRef,
        pname: &str,
        conn_expr: &ast::Expr,
        parent_prefix: &str,
    ) {
        let inst_name = match &conn_expr.kind {
            ast::ExprKind::Ident(p) if p.segments.len() == 1 => p.segments[0].name.clone(),
            _ => {
                self.error(
                    MsgCode::ElabPortMismatch,
                    &format!(
                        "interface port `{pname}` must be connected to an interface instance name"
                    ),
                );
                return;
            }
        };
        // v6 ② (D): resolve the instance name with the SAME outward scope
        // walk nets use, so a child inside a generate block binds an iface
        // declared in the enclosing module body. The walk runs in the PARENT
        // scope (cur_prefix is the child's during port binding).
        let saved_for_lookup = std::mem::replace(&mut self.cur_prefix, parent_prefix.to_string());
        let found = self.walk_scopes_key(&inst_name, |k| self.iface_insts.contains_key(k));
        self.cur_prefix = saved_for_lookup;
        let Some(parent_fq) = found else {
            self.error(
                MsgCode::ElabPortMismatch,
                &format!(
                    "interface port `{pname}`: `{inst_name}` is not an interface instance in the parent scope"
                ),
            );
            return;
        };
        let actual = self.iface_insts[&parent_fq].clone();
        if actual != iref.iface.name {
            self.error(
                MsgCode::ElabPortMismatch,
                &format!(
                    "interface port `{pname}` is typed `{}` but `{inst_name}` is an instance of `{actual}`",
                    iref.iface.name
                ),
            );
            return;
        }
        // v6 ②: with a modport, only the LISTED members are visible through
        // the port (§25.5) and `input` members are read-only. Without one,
        // every member aliases with full access.
        let mp_dirs: Option<BTreeMap<String, ast::PortDir>> = match &iref.modport {
            Some(mp) => {
                let decl = self.ifaces.get(&actual).and_then(|d| {
                    d.body.iter().find_map(|it| match it {
                        ast::ModuleItem::Modport(m) if m.name.name == mp.name => Some(m.clone()),
                        _ => None,
                    })
                });
                let Some(m) = decl else {
                    self.error(
                        MsgCode::ElabPortMismatch,
                        &format!("interface `{actual}` has no modport `{}`", mp.name),
                    );
                    return;
                };
                Some(
                    m.ports
                        .iter()
                        .map(|(d, id)| (id.name.clone(), *d))
                        .collect(),
                )
            }
            None => None,
        };
        // Alias the visible symbols under the instance into the child port scope.
        let src_prefix = format!("{parent_fq}.");
        let dst_prefix = format!("{}.", self.fq(pname));
        let aliases: Vec<(String, u32, Option<ast::PortDir>)> = self
            .symbols
            .range(src_prefix.clone()..)
            .take_while(|(k, _)| k.starts_with(&src_prefix))
            .filter_map(|(k, &id)| {
                let suffix = &k[src_prefix.len()..];
                // The modport lists direct MEMBERS (single segment) — match on
                // the first path segment so any future nested suffix follows
                // its member's visibility.
                let member = suffix.split('.').next().unwrap_or(suffix);
                let dir = match &mp_dirs {
                    Some(dirs) => Some(*dirs.get(member)?), // unlisted → invisible
                    None => None,
                };
                Some((format!("{dst_prefix}{suffix}"), id, dir))
            })
            .collect();
        for (k, id, dir) in aliases {
            if matches!(dir, Some(ast::PortDir::Input)) {
                self.modport_readonly.insert(k.clone());
            }
            self.symbols.insert(k, id);
        }
    }

    /// v6 ②: error on a WRITE that resolves through a modport `input` alias.
    /// Called once per lvalue root; mirrors the symbol lookup exactly via
    /// [`Self::walk_scopes_key`], so name-level granularity is preserved (the
    /// same net stays writable through the parent or an `output` modport).
    fn check_modport_write(&mut self, path: &ast::HierPath) {
        if self.modport_readonly.is_empty() {
            return;
        }
        let joined = path
            .segments
            .iter()
            .map(|s| s.name.as_str())
            .collect::<Vec<_>>()
            .join(".");
        let key = self.walk_scopes_key(&joined, |k| self.symbols.contains_key(k));
        if let Some(k) = key {
            if self.modport_readonly.contains(&k) {
                self.error(
                    MsgCode::ElabPortMismatch,
                    &format!("cannot write `{joined}` through a modport `input` (read-only)"),
                );
            }
        }
    }

    // ── scope helpers (FQ-name keying) ─────────────────────────────
    /// Fully-qualified key of a LOCAL name within the current instance scope.
    fn fq(&self, local: &str) -> String {
        if self.cur_prefix.is_empty() {
            local.to_string()
        } else {
            format!("{}.{}", self.cur_prefix, local)
        }
    }
    /// Child prefix = current prefix + child instance name.
    fn child_prefix(&self, inst_name: &str) -> String {
        if self.cur_prefix.is_empty() {
            inst_name.to_string()
        } else {
            format!("{}.{}", self.cur_prefix, inst_name)
        }
    }

    // ── port wiring (parent expr ↔ child port net) ─────────────────
    /// Emit one cont-assign per CONNECTED port. Called from inside the child
    /// instance, where `self.cur_prefix == child_path`; the connection expr must
    /// be lowered in the PARENT scope, so we temporarily swap the prefix back to
    /// `parent_prefix` around each connection lowering.
    ///
    /// Direction wiring (doc-04):
    ///  - INPUT  : child port net DRIVEN by the parent expr  → `child_port = parent_expr`
    ///  - OUTPUT : child net DRIVES the parent lvalue         → `parent_lval = child_port`
    ///  - INOUT  : approximated child→parent (one-directional) + warn
    ///
    /// Unconnected ports: an INPUT floats (z, the net's time-0 default, no
    /// assign); an OUTPUT/INOUT is allowed + warns. Ports are walked in HEADER
    /// declaration order, so the cont-assign sequence is deterministic regardless
    /// of connection source order.
    fn wire_ports(
        &mut self,
        module: &ast::ModuleDecl,
        binding: PortBinding<'_>,
        parent_prefix: &str,
    ) {
        let ports = port_list_dirs(module);
        for (i, (pname, dir)) in ports.iter().enumerate() {
            // find the connection expr for this port (None ⇒ unconnected).
            let conn: Option<&ast::Expr> = match &binding {
                PortBinding::None => None,
                PortBinding::Positional(v) => v.get(i).and_then(|o| o.as_ref()),
                PortBinding::Named(v) => v
                    .iter()
                    .find(|c| &c.name.name == pname)
                    .and_then(|c| c.value.as_ref()),
            };
            // v5 ⑥ (D): interface-typed port → symbol aliasing, not wiring.
            if let Some(iref) = ansi_iface_ref(module, pname) {
                match conn {
                    Some(c) => self.bind_iface_port(iref, pname, c, parent_prefix),
                    None => self.error(
                        MsgCode::ElabPortMismatch,
                        &format!("interface port `{pname}` left unconnected"),
                    ),
                }
                continue;
            }
            let Some(conn_expr) = conn else {
                // unconnected port.
                match dir {
                    ir::PortDir::Output => {
                        self.warn(&format!("output port `{pname}` left unconnected"));
                    }
                    ir::PortDir::Inout => {
                        self.warn(&format!("inout port `{pname}` left unconnected"));
                    }
                    _ => {} // input floats silently (z = time-0 default)
                }
                continue;
            };

            // child port net id (current scope is the child).
            let child_id = {
                let key = self.fq(pname);
                *self.symbols.get(&key).unwrap_or(&POISON_NET)
            };
            let child_prefix = self.cur_prefix.clone();

            match dir {
                // INPUT: child_port = parent_expr  (rhs lowered in PARENT scope).
                ir::PortDir::Input | ir::PortDir::Inout => {
                    if matches!(dir, ir::PortDir::Inout) {
                        self.warn(&format!(
                            "inout port `{pname}` approximated as one-directional (parent→child)"
                        ));
                    }
                    self.cur_prefix = parent_prefix.to_string();
                    let rhs = self.lower_expr(conn_expr);
                    self.cur_prefix = child_prefix;
                    let lhs = whole_net_lvalue(child_id);
                    self.cont_assigns.push(ir::ContAssign {
                        lhs,
                        rhs,
                        delay: None,
                    });
                }
                // OUTPUT: parent_lval = child_port  (lval lowered in PARENT scope).
                ir::PortDir::Output => {
                    self.cur_prefix = parent_prefix.to_string();
                    let lhs = match expr_to_lvalue(conn_expr) {
                        Some(lv) => self.lower_lvalue(&lv),
                        None => {
                            self.error(
                                MsgCode::ElabPortMismatch,
                                &format!(
                                    "output port `{pname}` connected to a non-lvalue expression"
                                ),
                            );
                            ir::Lvalue {
                                chunks: vec![whole_net_chunk(POISON_NET)],
                            }
                        }
                    };
                    self.cur_prefix = child_prefix;
                    let rhs = self.push_expr(ir::Expr::Signal {
                        net: child_id,
                        word: None,
                    });
                    self.cont_assigns.push(ir::ContAssign {
                        lhs,
                        rhs,
                        delay: None,
                    });
                }
                ir::PortDir::Internal => {
                    // a non-port net in the header list — module-decl bug.
                    self.error(MsgCode::ElabPortMismatch, "connection to a non-port net");
                }
            }
        }

        // Fix 2 (Finding M2): detect connections that match NO declared port.
        // Symmetric with bind_params' surplus-positional / unknown-named checks.
        match &binding {
            PortBinding::None => {}
            PortBinding::Positional(v) => {
                if v.len() > ports.len() {
                    self.error(
                        MsgCode::ElabPortMismatch,
                        &format!(
                            "instance of `{}` has {} positional connection(s) but the module declares {} port(s)",
                            module.name.name,
                            v.len(),
                            ports.len()
                        ),
                    );
                }
            }
            PortBinding::Named(v) => {
                for c in v.iter() {
                    if !ports.iter().any(|(pname, _)| pname == &c.name.name) {
                        self.error(
                            MsgCode::ElabPortMismatch,
                            &format!(
                                "connection `.{}(...)` names no port of module `{}`",
                                c.name.name, module.name.name
                            ),
                        );
                    }
                }
            }
        }
    }

    // ── parameter binding (defaults + overrides; FQ-keyed) ──────────
    /// Bind a module's params for the current instance scope: each declared
    /// param's default (const-eval'd IN ORDER so a later param sees earlier ones),
    /// then overlay the instantiation overrides (positional by index, named by
    /// name). Localparams are NOT overridable. Params are keyed by FQ name so two
    /// instances with different `WIDTH` coexist. Returns the prior FQ→value
    /// entries so siblings/ancestors are restored on exit.
    ///
    /// The instantiation overrides are ALREADY resolved in the PARENT scope (Fix 1
    /// / Finding M1), so a `child #(.W(PARENT_W))` override carries the parent's
    /// `PARENT_W` value — no longer folds to 0 in the child scope.
    fn bind_params(
        &mut self,
        module: &ast::ModuleDecl,
        overrides: &[ResolvedOverride],
    ) -> Vec<(String, Option<i64>)> {
        // Build name→value from the resolved overrides. Positional binds to the
        // i-th declaration index (matches module.params order).
        let mut ovr_by_name: BTreeMap<&str, Option<i64>> = BTreeMap::new();
        let mut pos_i = 0usize;
        for ov in overrides {
            if ov.is_named {
                let Some(n) = ov.name.as_deref() else {
                    continue;
                };
                // Fix 2 (mirror): a named override naming no real param is an error.
                match module.params.iter().find(|p| p.name.name == n) {
                    Some(p) => {
                        if let Some(v) = ov.value {
                            ovr_by_name.insert(p.name.name.as_str(), Some(v));
                        }
                        // `.W()` with no value ⇒ keep default (no insert).
                    }
                    None => {
                        self.error(
                            MsgCode::ElabPortMismatch,
                            &format!("override of unknown parameter `{n}`"),
                        );
                    }
                }
            } else {
                match module.params.get(pos_i) {
                    Some(p) => {
                        ovr_by_name.insert(p.name.name.as_str(), ov.value);
                    }
                    None => {
                        self.error(
                            MsgCode::ElabPortMismatch,
                            "more positional parameter overrides than module parameters",
                        );
                    }
                }
                pos_i += 1;
            }
        }

        let mut saved = Vec::new();
        for p in &module.params {
            let chosen_val: Option<i64> = match ovr_by_name.get(p.name.name.as_str()) {
                // override present + param is overridable → use it (None = fold-fail
                // → fall back to the declared default).
                Some(ovr) if matches!(p.kind, ast::ParamKind::Parameter) => {
                    (*ovr).or_else(|| self.const_eval_in_scope(&p.value))
                }
                // override targeting a localparam → error, keep declared value.
                Some(_) => {
                    self.error(
                        MsgCode::ElabPortMismatch,
                        &format!("cannot override localparam `{}`", p.name.name),
                    );
                    self.const_eval_in_scope(&p.value)
                }
                None => self.const_eval_in_scope(&p.value),
            };
            // Unfoldable param value = LOUD error, never a silent 0 (P0-5);
            // 0 is only the post-error recovery value.
            let v = chosen_val.unwrap_or_else(|| {
                self.error(
                    MsgCode::ElabUnsupported,
                    &format!(
                        "parameter `{}` value is not a foldable constant expression",
                        p.name.name
                    ),
                );
                0
            });
            let key = self.fq(&p.name.name);
            saved.push((key.clone(), self.params.insert(key, v)));
        }
        saved
    }

    /// Restore the param map to the snapshot taken before this instance bound its
    /// params (so sibling instances of the same module re-bind cleanly).
    fn restore_params(&mut self, saved: Vec<(String, Option<i64>)>) {
        for (k, prev) in saved.into_iter().rev() {
            match prev {
                Some(v) => {
                    self.params.insert(k, v);
                }
                None => {
                    self.params.remove(&k);
                }
            }
        }
    }

    /// Resolve a bare param/genvar `name` to its value, searching the current
    /// scope then each enclosing GENERATE-block scope (strip one trailing
    /// `.segment` at a time). A genvar bound at the generate-for's scope (`top.i`)
    /// is visible inside the loop body's nested prefix (`top.g[0]`, `top.g[0].h`,
    /// …) — exactly Verilog's generate-scope visibility. The walk STOPS at an
    /// INSTANCE boundary (a plain-identifier segment) so a child instance never
    /// sees a parent module's param by bare name. Innermost binding wins.
    fn lookup_scoped(&self, name: &str) -> Option<i64> {
        self.walk_scopes(name, &self.params)
    }

    /// True iff `seg` is a GENERATE-block scope segment (`label[idx]`), as opposed
    /// to an instance-boundary segment (a plain identifier). Generate prefixes
    /// always carry the `[idx]` suffix, so a `[` unambiguously marks them.
    fn is_gen_scope_segment(seg: &str) -> bool {
        seg.contains('[')
    }

    /// Shared outward scope walk over a FQ-keyed `BTreeMap`. Looks up `name` in
    /// the current scope, then each enclosing generate-block scope, stopping at
    /// the first instance boundary. Used for both params/genvars and the symbol
    /// (net) table so the visibility rule is identical for each.
    fn walk_scopes<T: Copy>(&self, name: &str, table: &BTreeMap<String, T>) -> Option<T> {
        self.walk_scopes_key(name, |k| table.contains_key(k))
            .and_then(|k| table.get(&k).copied())
    }

    /// The key-returning core of [`Self::walk_scopes`] — ONE source of truth
    /// for the visibility rule, so key-level consumers (the modport
    /// read-only check, the iface-instance lookup) can never drift from the
    /// value-level lookups.
    fn walk_scopes_key(&self, name: &str, hit: impl Fn(&str) -> bool) -> Option<String> {
        let mut prefix = self.cur_prefix.as_str();
        loop {
            let key = if prefix.is_empty() {
                name.to_string()
            } else {
                format!("{prefix}.{name}")
            };
            if hit(&key) {
                return Some(key);
            }
            if prefix.is_empty() {
                return None;
            }
            // The innermost segment about to be stripped: only continue walking
            // outward if it is a generate-block scope (`label[idx]`). Stopping at
            // an instance-boundary segment preserves per-instance name isolation.
            let last_seg = match prefix.rfind('.') {
                Some(i) => &prefix[i + 1..],
                None => prefix,
            };
            if !Self::is_gen_scope_segment(last_seg) {
                return None;
            }
            prefix = match prefix.rfind('.') {
                Some(i) => &prefix[..i],
                None => "",
            };
        }
    }

    /// Param-aware const-eval in a SIGNED 64-bit domain (P0-6, 2026-06-10).
    /// Folds: literals (sign-aware), params/genvars in scope, unary `+ - ~ !`,
    /// the binary operator set with i64 semantics (so a descending genvar
    /// condition `i >= 0` actually terminates), ternary `?:` and `$clog2`
    /// (P0-5 — the `localparam AW = $clog2(DEPTH)` / `W = M ? a : b` idioms).
    /// Overflow and ill-defined folds return None — param-binding callers
    /// escalate None to an ERROR (never a silent 0), width callers clamp
    /// loudly. NOTE: this is a width-less mathematical-integer model; a
    /// logical `>>` of a NEGATIVE value is width-dependent and folds None.
    fn const_eval_in_scope(&self, e: &ast::Expr) -> Option<i64> {
        match &e.kind {
            ast::ExprKind::IntLit { .. } => const_eval_i64_lit(e),
            ast::ExprKind::Paren { inner } => self.const_eval_in_scope(inner),
            ast::ExprKind::Unary { op, operand } => {
                let v = self.const_eval_in_scope(operand)?;
                match op {
                    ast::UnOp::Plus => Some(v),
                    ast::UnOp::Minus => v.checked_neg(),
                    ast::UnOp::BitNot => Some(!v),
                    ast::UnOp::LogNot => Some((v == 0) as i64),
                    _ => None,
                }
            }
            // param/genvar reference: single-segment name bound in this scope OR
            // an ENCLOSING one. Walking outward lets a genvar bound at the
            // generate-for's scope (`top.i`) resolve inside the loop body's
            // nested prefix (`top.g[0]`), matching Verilog generate scoping.
            ast::ExprKind::Ident(path) if path.segments.len() == 1 => {
                self.lookup_scoped(&path.segments[0].name)
            }
            ast::ExprKind::Ternary {
                cond,
                then_e,
                else_e,
            } => {
                let c = self.const_eval_in_scope(cond)?;
                if c != 0 {
                    self.const_eval_in_scope(then_e)
                } else {
                    self.const_eval_in_scope(else_e)
                }
            }
            ast::ExprKind::SysCall { name, args } if name.name == "$clog2" && args.len() == 1 => {
                let n = self.const_eval_in_scope(&args[0])?;
                if n < 0 {
                    return None; // width-dependent in IEEE; loud in this domain
                }
                if n <= 1 {
                    Some(0)
                } else {
                    Some((64 - ((n - 1) as u64).leading_zeros()) as i64)
                }
            }
            // v7 P2-D: `pkg::sym` in const contexts.
            ast::ExprKind::PkgScoped { pkg, name } => self
                .pkg_consts
                .get(&pkg.name)
                .and_then(|c| c.get(&name.name))
                .copied(),
            // v7 `$bits` in const contexts (localparam init, range specs): the
            // view subset only — no lowering happens in this domain. A shape
            // it can't see folds None → LOUD at the binding site.
            ast::ExprKind::SysCall { name, args } if name.name == "$bits" && args.len() == 1 => {
                self.bits_of_view(&args[0], true).map(|n| n as i64)
            }
            ast::ExprKind::Binary { op, lhs, rhs } => {
                let a = self.const_eval_in_scope(lhs)?;
                let b = self.const_eval_in_scope(rhs)?;
                match op {
                    // checked_*: i64 overflow → None → LOUD at the call sites.
                    ast::BinOp::Add => a.checked_add(b),
                    ast::BinOp::Sub => a.checked_sub(b),
                    ast::BinOp::Mul => a.checked_mul(b),
                    ast::BinOp::Div if b != 0 => a.checked_div(b),
                    ast::BinOp::Mod if b != 0 => a.checked_rem(b),

                    // Comparison / equality / logical / bitwise folding — required
                    // so a generate-for CONDITION (`i < N`, `i >= 0`, …) const-folds
                    // to 1/0 during unroll. SIGNED i64 semantics; `===`/`!==`
                    // collapse to `==`/`!=` since a folded const has no x/z.
                    ast::BinOp::Lt => Some((a < b) as i64),
                    ast::BinOp::Le => Some((a <= b) as i64),
                    ast::BinOp::Gt => Some((a > b) as i64),
                    ast::BinOp::Ge => Some((a >= b) as i64),
                    ast::BinOp::Eq | ast::BinOp::CaseEq => Some((a == b) as i64),
                    ast::BinOp::Ne | ast::BinOp::CaseNe => Some((a != b) as i64),
                    ast::BinOp::BitAnd => Some(a & b),
                    ast::BinOp::BitOr => Some(a | b),
                    ast::BinOp::BitXor => Some(a ^ b),
                    ast::BinOp::BitXnor => Some(!(a ^ b)),
                    ast::BinOp::LogAnd => Some(((a != 0) && (b != 0)) as i64),
                    ast::BinOp::LogOr => Some(((a != 0) || (b != 0)) as i64),
                    ast::BinOp::Pow => const_pow_i64(a, b),
                    // `<<`/`<<<`: value-preserving or None (a shifted-out/sign-
                    // overflowing param value would be silently wrong). `1<<32`
                    // folds to 4294967296 (iverilog folds unsized consts wide).
                    ast::BinOp::Shl | ast::BinOp::AShl => const_shl_i64(a, b),
                    // `>>` (logical): well-defined here only for a ≥ 0 (the
                    // result of a logical shift of a negative value depends on
                    // the operand WIDTH, which this domain doesn't model).
                    ast::BinOp::Shr if a >= 0 => {
                        if !(0..64).contains(&b) {
                            Some(0)
                        } else {
                            Some(((a as u64) >> b) as i64)
                        }
                    }
                    // `>>>` (arithmetic): sign-extending shift; an over-width or
                    // negative amount saturates to all-sign.
                    ast::BinOp::AShr => {
                        if !(0..64).contains(&b) {
                            Some(if a < 0 { -1 } else { 0 })
                        } else {
                            Some(a >> b)
                        }
                    }
                    // Div/Mod by zero, negative-operand `>>` → non-constant.
                    _ => None,
                }
            }
            _ => None,
        }
    }

    /// P1-9 (E3018): assignment-kind legality. `is_proc=true` (a procedural `=`/
    /// `<=`) may not target a NET (`wire`); `is_proc=false` (a user `assign`) may
    /// not drive a VARIABLE (`reg`/`integer`/`real`). SV `logic` passes both ways
    /// (IEEE 1800 admits either one continuous driver or procedural writes).
    /// Called ONLY for user-written assignments — port-binding/decl-init synthetic
    /// cont-assigns are exempt (IEEE 1800 §23.3.3 var ports are legal).
    fn check_lvalue_kind(&mut self, lhs: &ir::Lvalue, is_proc: bool) {
        for c in &lhs.chunks {
            let Some(nv) = self.nets.get(c.net as usize) else {
                continue; // POISON_NET / post-error recovery chunk
            };
            let bad = if is_proc {
                matches!(nv.kind, ir::NetKind::Wire)
            } else {
                matches!(
                    nv.kind,
                    ir::NetKind::Reg
                        | ir::NetKind::Integer
                        | ir::NetKind::Real
                        | ir::NetKind::String
                )
            };
            if bad {
                let name = self
                    .symbols
                    .iter()
                    .find(|(_, &id)| id == c.net)
                    .map(|(n, _)| n.clone())
                    .unwrap_or_else(|| format!("#{}", c.net));
                let msg = if is_proc {
                    format!("procedural assignment to net `{name}` (declare it reg/logic)")
                } else {
                    format!("continuous assign drives variable `{name}` (declare it wire/logic)")
                };
                self.error(MsgCode::ElabLvalueKind, &msg);
            }
        }
    }

    /// `Expr::Const` → its u64 value (None for non-const / X-bearing) — used to
    /// turn a static part-select's `(offset, width)` ExprId edges into a bit
    /// interval for the multi-driver scan.
    fn const_expr_u64(&self, eid: u32) -> Option<u64> {
        match self.exprs.get(eid as usize)? {
            ir::Expr::Const { val } => {
                let c = self.consts.get(*val as usize)?;
                if c.bits.unk.iter().any(|&u| u != 0) {
                    return None;
                }
                Some(c.bits.val.first().copied().unwrap_or(0))
            }
            // A static part-select's width edge is the unfolded `(msb - lsb) + 1`
            // tree (`width_from_msb_lsb_checked`); fold the two arithmetic ops.
            ir::Expr::Binary {
                op: ir::BinOp::Add,
                lhs,
                rhs,
            } => Some(
                self.const_expr_u64(*lhs)?
                    .wrapping_add(self.const_expr_u64(*rhs)?),
            ),
            ir::Expr::Binary {
                op: ir::BinOp::Sub,
                lhs,
                rhs,
            } => Some(
                self.const_expr_u64(*lhs)?
                    .wrapping_sub(self.const_expr_u64(*rhs)?),
            ),
            _ => None,
        }
    }

    /// P1-8: emit `ElabMultidriver` for any net whose continuous-assign drivers
    /// OVERLAP at the bit level. Whole-net targets count as `[0, width)`; a
    /// static part/bit-select as `[off, off+w)`. DYNAMIC (non-const offset)
    /// selects and array-element writes are not counted (the conservative cut —
    /// a false positive on a disjoint dynamic split would reject legal code).
    /// Deterministic: nets in ascending id, intervals sorted, one report per net.
    fn check_whole_net_multidriver(&mut self) {
        let mut per_net: BTreeMap<u32, Vec<(u64, u64)>> = BTreeMap::new();
        for ca in &self.cont_assigns {
            for c in &ca.lhs.chunks {
                if c.word.is_some() {
                    continue; // array-element write: not counted (v1)
                }
                let Some(nv) = self.nets.get(c.net as usize) else {
                    continue;
                };
                let iv = match (c.offset, c.width) {
                    (None, None) => Some((0u64, nv.width.max(1) as u64)),
                    (Some(off_e), w_e) => {
                        let off = self.const_expr_u64(off_e);
                        let w = match w_e {
                            Some(we) => self.const_expr_u64(we),
                            None => Some(1), // bit-select
                        };
                        match (off, w) {
                            (Some(o), Some(w)) => Some((o, o.saturating_add(w.max(1)))),
                            _ => None, // dynamic select: skip
                        }
                    }
                    (None, Some(_)) => None, // not produced by collect_lval_chunks
                };
                if let Some(iv) = iv {
                    per_net.entry(c.net).or_default().push(iv);
                }
            }
        }
        for (net, mut ivs) in per_net {
            if ivs.len() < 2 {
                continue;
            }
            ivs.sort_unstable();
            let overlap = ivs.windows(2).any(|p| p[1].0 < p[0].1);
            if overlap {
                let name = self
                    .symbols
                    .iter()
                    .find(|(_, &id)| id == net)
                    .map(|(n, _)| n.clone())
                    .unwrap_or_else(|| format!("#{net}"));
                self.error(
                    MsgCode::ElabMultidriver,
                    &format!(
                        "net `{name}` driven by multiple overlapping continuous \
                         assignments"
                    ),
                );
            }
        }
    }

    // ── PASS 1a: ANSI ports → nets ─────────────────────────────────
    fn elaborate_ports(&mut self, ports: &ast::PortList) {
        if let ast::PortList::Ansi(list) = ports {
            for p in list {
                if p.iface.is_some() {
                    // v5 ⑥ (D): an interface-typed port creates NO net — its
                    // members alias the connected instance's nets at binding.
                    continue;
                }
                let kind = p.net_or_var.unwrap_or(ast::NetVarKind::Wire); // default net type
                let (mut width, mut msb, lsb, signed) =
                    self.range_to_dims(kind, p.range.as_ref(), p.signed);
                // A packed multi-dim port (`input [1:0][7:0] m`) is a flat vector.
                let packed_ext = self.packed_extents(p.range.as_ref(), &p.packed);
                if !p.packed.is_empty() {
                    width = packed_ext
                        .iter()
                        .fold(1u32, |a, &(_, w)| a.saturating_mul(w.max(1)));
                    msb = width.saturating_sub(1);
                }
                let dir = map_port_dir(p.dir);
                let init = default_init(kind, width);
                self.add_net(
                    &p.name.name,
                    ir::NetVar {
                        kind: map_net_kind_or_wire(kind),
                        width,
                        msb,
                        lsb,
                        signed,
                        array_len: 1,
                        dir,
                        init,
                    },
                );
                if !p.packed.is_empty() {
                    if let Some(&id) = self.symbols.get(&self.fq(&p.name.name)) {
                        self.packed_dims.insert(id, packed_ext);
                    }
                }
                if !net_kind_supported(kind) {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "unsupported net/var kind on port (v1)",
                    );
                }
            }
        }
        // NonAnsi/None: dir comes from body PortDecls; v1 leaves ports Internal
        // unless ANSI. (Body PortDecl dir-merge is a small follow-up.)
    }

    /// Recursively create nets for every `begin…end`/`fork…join` block-local
    /// declaration reachable from a procedural-block body. v1 flattens these to
    /// module-scope nets (no per-process frame). Called in the Nets phase.
    fn hoist_block_local_nets(
        &mut self,
        s: &ast::Stmt,
        ports: &ast::PortList,
        body: &[ast::ModuleItem],
    ) {
        match s {
            ast::Stmt::Block { decls, stmts, .. } | ast::Stmt::Fork { decls, stmts, .. } => {
                for d in decls {
                    // v1 flattens block-locals into the module namespace (no
                    // per-block scope). If a local name was already created by an
                    // EARLIER block, skip re-creating it rather than erroring
                    // "redeclared" — two SEQUENTIAL named blocks reusing the same
                    // temp name (`integer local_v;`) then share one net, which is
                    // correct since they never overlap in time.
                    let exists = d
                        .names
                        .first()
                        .is_some_and(|n| self.symbols.contains_key(&self.fq(&n.name.name)));
                    if exists {
                        continue;
                    }
                    self.elaborate_netvar_decl(d, ports, body);
                }
                for st in stmts {
                    self.hoist_block_local_nets(st, ports, body);
                }
            }
            ast::Stmt::If { then_s, else_s, .. } => {
                self.hoist_block_local_nets(then_s, ports, body);
                if let Some(e) = else_s {
                    self.hoist_block_local_nets(e, ports, body);
                }
            }
            ast::Stmt::Case { items, .. } => {
                for it in items {
                    let inner = match it {
                        ast::CaseItem::Match { body: b, .. } => b,
                        ast::CaseItem::Default { body: b, .. } => b,
                    };
                    self.hoist_block_local_nets(inner, ports, body);
                }
            }
            ast::Stmt::For { body: b, .. }
            | ast::Stmt::While { body: b, .. }
            | ast::Stmt::Repeat { body: b, .. }
            | ast::Stmt::Forever { body: b, .. } => {
                self.hoist_block_local_nets(b, ports, body);
            }
            _ => {}
        }
    }

    // ── PASS 1b: body NetVarDecl → nets ────────────────────────────
    fn elaborate_netvar_decl(
        &mut self,
        d: &ast::NetVarDecl,
        ports: &ast::PortList,
        body: &[ast::ModuleItem],
    ) {
        if !net_kind_supported(d.kind) {
            self.error(MsgCode::ElabUnsupported, "unsupported net/var kind (v1)");
            // still emit a Wire-shaped net per name so references resolve.
        }
        // Multi-dim PACKED array (`logic [3:0][7:0]`): the net is a flat vector of
        // `product(packed widths)` bits; a select `m[i]` is a bit-slice. Computed once
        // per decl (shared by all names; unpacked dims are per-name).
        let packed_ext = self.packed_extents(d.range.as_ref(), &d.packed);
        // a named event carries NO range/init/array surface (IEEE §6.17) —
        // loud, then the bare counter net is still created so refs resolve.
        if matches!(d.kind, ast::NetVarKind::Event)
            && (d.range.is_some()
                || !d.packed.is_empty()
                || d.names
                    .iter()
                    .any(|n| n.init.is_some() || !n.unpacked.is_empty()))
        {
            self.error(
                MsgCode::ElabUnsupported,
                "a named event takes no range, initializer or array dimensions",
            );
        }
        for decl in &d.names {
            let (mut width, mut msb, lsb, signed) =
                self.range_to_dims(d.kind, d.range.as_ref(), d.signed);
            if !d.packed.is_empty() {
                width = packed_ext
                    .iter()
                    .fold(1u32, |a, &(_, w)| a.saturating_mul(w.max(1)));
                msb = width.saturating_sub(1);
            }
            // ── v7 P2-C: `string s` — heap-handle declaration ──
            // width 0 / array_len 0; the engine heap holds the bytes (dyn
            // precedent). Reads materialize is_str packed values; writes
            // strip leading NULs through the funnel.
            if matches!(d.kind, ast::NetVarKind::String) {
                if d.range.is_some() || !d.packed.is_empty() || !decl.unpacked.is_empty() {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "a string variable takes no packed/unpacked dimensions (v7)",
                    );
                    continue;
                }
                if decl.init.is_some() {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "a string declaration initializer is outside the v7 \
                         scope (assign in an initial block)",
                    );
                    continue;
                }
                let dir = self.dir_for_name(&decl.name.name, ports, body);
                if dir != ir::PortDir::Internal {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "a string variable cannot be a port (outside the v7 scope)",
                    );
                    continue;
                }
                self.add_net(
                    &decl.name.name,
                    ir::NetVar {
                        kind: ir::NetKind::String,
                        width: 0,
                        msb: 0,
                        lsb: 0,
                        signed: false,
                        array_len: 0,
                        dir: ir::PortDir::Internal,
                        init: default_init(ast::NetVarKind::Reg, 1),
                    },
                );
                continue;
            }
            // ── v5 ⑥: dynamic-storage HANDLE declaration ──
            // `integer d[]` / `logic [7:0] q[$]` / `integer a[integer]`:
            // one dyn dim → a handle net (element width/signedness,
            // `array_len 0`, heap-backed). Engine slices ③④⑤ are the
            // storage; this is the front door.
            if let Some(handle_kind) = self.dyn_dim_kind(&decl.unpacked) {
                if decl.unpacked.len() != 1 {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "a dynamic dimension cannot be mixed with other unpacked dimensions (nested dynamic storage is outside the MVP)",
                    );
                    continue;
                }
                // v6 ③: bounded queue `[$:N]` — fold N (a non-negative
                // const) into the sidecar; the engine truncates the TAIL of
                // any op that exceeds size N+1 (iverilog live).
                let queue_bound: Option<u32> = match &decl.unpacked[0] {
                    ast::Dim::Queue(Some(be)) => {
                        let n = self.const_eval_in_scope(be);
                        match n {
                            Some(v) if (0..=i64::from(u32::MAX)).contains(&v) => Some(v as u32),
                            _ => {
                                self.error(
                                    MsgCode::ElabUnsupported,
                                    "a queue bound must be a non-negative constant expression",
                                );
                                continue;
                            }
                        }
                    }
                    _ => None,
                };
                if decl.init.is_some() {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "a dynamic-storage handle takes no initializer (use `new[]`/methods at runtime)",
                    );
                    continue;
                }
                if matches!(
                    d.kind,
                    ast::NetVarKind::Real | ast::NetVarKind::Realtime | ast::NetVarKind::Event
                ) {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "real/event elements in dynamic storage are outside the MVP",
                    );
                    continue;
                }
                if !net_is_variable(d.kind) {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "dynamic storage must be a VARIABLE kind (reg/logic/integer/time), not a net",
                    );
                    continue;
                }
                let dir = self.dir_for_name(&decl.name.name, ports, body);
                if dir != ir::PortDir::Internal {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "a dynamic-storage handle cannot be a port (outside the MVP)",
                    );
                    continue;
                }
                let next_id = self.nets.len() as u32;
                self.add_net(
                    &decl.name.name,
                    ir::NetVar {
                        kind: handle_kind,
                        width,
                        msb,
                        lsb,
                        signed,
                        array_len: 0, // the handle marker — elements live in the engine heap
                        dir,
                        init: default_init(d.kind, width),
                    },
                );
                if let Some(b) = queue_bound {
                    if self.nets.len() as u32 > next_id {
                        self.queue_bounds.insert(next_id, b);
                    }
                }
                continue;
            }
            let dim_extents = self.array_dim_extents(&decl.unpacked);
            let array_len = dim_extents
                .iter()
                .fold(1u32, |acc, &(_, n)| acc.saturating_mul(n.max(1)));
            // P2-6: cap the unpacked element count like MAX_NET_WIDTH caps the
            // vector width — `reg [7:0] m [0:2147483647]` would otherwise try a
            // multi-GB allocation at t0 (OS OOM kill, no diagnostic).
            if (array_len as u64) > MAX_ARRAY_LEN {
                self.error(
                    MsgCode::ElabUnsupported,
                    &format!(
                        "unpacked array `{}` has {} elements (cap {MAX_ARRAY_LEN})",
                        decl.name.name, array_len
                    ),
                );
                continue;
            }
            let dir = self.dir_for_name(&decl.name.name, ports, body);
            // init: const-fold a literal initializer; otherwise time-0 default.
            let init = match &decl.init {
                Some(e) => fold_init(e, width).unwrap_or_else(|| default_init(d.kind, width)),
                None => default_init(d.kind, width),
            };
            self.add_net(
                &decl.name.name,
                ir::NetVar {
                    kind: map_net_kind_or_wire(d.kind),
                    width,
                    msb,
                    lsb,
                    signed,
                    array_len,
                    dir,
                    init,
                },
            );
            if matches!(d.kind, ast::NetVarKind::Event) {
                let key = self.fq(&decl.name.name);
                if let Some(&id) = self.symbols.get(&key) {
                    self.event_nets.insert(id);
                }
            }
            // Record per-dim extents when addressing is NOT plain 0-based: any
            // MULTI-dim array, OR a 1-D array with a non-zero lower bound (`mem[4:7]`).
            // A plain 0-based 1-D array stays ABSENT so its lowering falls back to
            // `[(0, array_len)]` — byte-identical to the long-standing golden IR.
            // Keyed by the just-assigned NetId (looked up post-add so a duplicate-skip
            // does not mis-key). (a)-flattening: no frozen-IR field added.
            if dim_extents.len() >= 2 || dim_extents.iter().any(|&(lo, _)| lo != 0) {
                let key = self.fq(&decl.name.name);
                if let Some(&id) = self.symbols.get(&key) {
                    self.array_dims.insert(id, dim_extents);
                }
            }
            // Declared per-dim DIRECTION for array-assignment correspondence
            // (sparse: only when some dim is descending, e.g. `mem[3:0]`).
            let desc: Vec<bool> = decl
                .unpacked
                .iter()
                .map(|d| match d {
                    ast::Dim::Range(r) => {
                        let msb = self.const_eval_in_scope(&r.msb);
                        let lsb = self.const_eval_in_scope(&r.lsb);
                        matches!((msb, lsb), (Some(m), Some(l)) if m > l)
                    }
                    _ => false,
                })
                .collect();
            if desc.iter().any(|&d| d) {
                let key = self.fq(&decl.name.name);
                if let Some(&id) = self.symbols.get(&key) {
                    self.array_dim_desc.insert(id, desc);
                }
            }
            // Declared array-ness — covers `[0:0]` (1-element) arrays that
            // `array_len > 1` cannot distinguish from scalars.
            if !decl.unpacked.is_empty() {
                let key = self.fq(&decl.name.name);
                if let Some(&id) = self.symbols.get(&key) {
                    self.unpacked_array_nets.insert(id);
                }
            }
            // Record packed-dim extents for a multi-dim packed net so a select can be
            // lowered to the right bit-slice.
            if !d.packed.is_empty() {
                let key = self.fq(&decl.name.name);
                if let Some(&id) = self.symbols.get(&key) {
                    self.packed_dims.insert(id, packed_ext.clone());
                }
            }
        }
    }

    /// Per-PACKED-dim `(lo, width)` extents of `[range][packed…]` (outer→inner). The
    /// product of the widths is the flat vector width; `lo` is the dim's lower bound
    /// (subtracted to 0-base a source index). Empty for a scalar/plain vector.
    fn packed_extents(
        &mut self,
        range: Option<&ast::Range>,
        packed: &[ast::Range],
    ) -> Vec<(u32, u32)> {
        let mut out = Vec::new();
        for r in range.into_iter().chain(packed.iter()) {
            // Negative folded bounds (underflow artifact) clamp to 0 — width math
            // stays small instead of the old u32-wrap explosion.
            let msb = clamp_bound_u32(self.const_eval_in_scope(&r.msb));
            let lsb = clamp_bound_u32(self.const_eval_in_scope(&r.lsb));
            let w = (((msb.abs_diff(lsb) as u64) + 1).min(u32::MAX as u64)) as u32;
            out.push((msb.min(lsb), w.max(1)));
        }
        out
    }

    /// Per-dimension `(lo, size)` extents of an unpacked-array declaration (source
    /// order). `lo` is the lower (minimum) range endpoint — the value subtracted
    /// from a source index to get a 0-based word slot (`mem[4:7]` → lo 4). `size`
    /// is the param/genvar-aware folded length (`abs_diff+1`, widened to `u64` then
    /// clamped to `u32` to avoid the [`Self::range_to_dims`] panic), floored at 1 so
    /// a degenerate `[0:0]` dim contributes one word. The product of the sizes is
    /// the flat `array_len`.
    fn array_dim_extents(&mut self, dims: &[ast::Dim]) -> Vec<(u32, u32)> {
        dims.iter()
            .map(|d| match d {
                ast::Dim::Range(r) => {
                    let msb = clamp_bound_u32(self.const_eval_in_scope(&r.msb));
                    let lsb = clamp_bound_u32(self.const_eval_in_scope(&r.lsb));
                    let size = (((msb.abs_diff(lsb) as u64) + 1).min(u32::MAX as u64)) as u32;
                    (msb.min(lsb), size.max(1))
                }
                ast::Dim::Size(e) => (
                    0,
                    self.const_eval_in_scope(e)
                        .map_or(1, |v| {
                            u32::try_from(v).unwrap_or(if v < 0 { 1 } else { u32::MAX })
                        })
                        .max(1),
                ),
                // v5 ⑥: dyn dims never reach the static-extent path
                // (`elaborate_netvar_decl` routes them to handle nets first) —
                // neutral extent, defensive only.
                ast::Dim::Dyn | ast::Dim::Queue(_) | ast::Dim::Assoc(_) => (0, 1),
            })
            .collect()
    }

    /// Total bit width of a LOWERED lvalue (mirrors the engine's
    /// `lvalue_width`/backend `lvalue_width_of`): whole-net chunks read the net
    /// (element) width, bit selects are 1, part selects read their const width
    /// edge. Used to size intra-assignment capture temps EXACTLY.
    fn ir_lvalue_width(&self, lv: &ir::Lvalue) -> u32 {
        lv.chunks
            .iter()
            .map(|c| match c.kind {
                ir::SelKind::Bit => {
                    if c.offset.is_none() && c.width.is_none() {
                        self.nets[c.net as usize].width
                    } else {
                        1
                    }
                }
                _ => c
                    .width
                    .and_then(|eid| self.const_of_expr_u32(eid))
                    .unwrap_or(1),
            })
            .sum::<u32>()
            .max(1)
    }

    /// Read back a const width edge this elaboration pushed (`Expr::Const`).
    fn const_of_expr_u32(&self, eid: u32) -> Option<u32> {
        if let ir::Expr::Const { val } = self.exprs.get(eid as usize)? {
            let c = self.consts.get(*val as usize)?;
            if c.bits.unk.iter().any(|&u| u != 0) {
                return None;
            }
            return u32::try_from(c.bits.val.first().copied().unwrap_or(0)).ok();
        }
        None
    }

    /// Lower a blocking intra-assignment EVENT control `lhs = [repeat(n)] @(ev) rhs`
    /// (IEEE 1800 §9.4.5) as capture-now / wait / write:
    ///   `tmp = rhs;  @(ev) × n;  lhs = tmp;`
    /// The RHS is captured NOW into a temp sized EXACTLY to the lvalue (so the rhs
    /// eval context is unchanged), the process waits for the event `n` times, then
    /// the captured value is written. The repeat count is folded scope-aware (so a
    /// `parameter`/`localparam` count works), and the wait is emitted `n` times via
    /// the validated EventCtrl lowering — NOT through `Stmt::Repeat`, whose
    /// scope-blind count fold would silently elide the wait for a non-literal count.
    /// A non-constant or oversized count is LOUD (never a silent 0-event write).
    /// `repeat(0)`/`repeat(<0)` ⇒ zero waits = an immediate write (IEEE). The lvalue
    /// is resolved up front but its index evaluates at the final write — identical to
    /// the `#d` intra-delay path.
    fn lower_intra_event_assign(
        &mut self,
        b: &mut ProcessBuilder,
        lhs: &ast::Lvalue,
        ie: &ast::IntraEvent,
        rhs: &ast::Expr,
        span: ast::Span,
    ) {
        // Fold the repeat count FIRST (loud-and-return before emitting any IR).
        let waits: u32 = match &ie.repeat {
            None => 1,
            Some(n) => match self.const_eval_in_scope(n) {
                Some(c) => {
                    let c = c.max(0); // repeat(0)/repeat(<0) ⇒ zero iterations (IEEE)
                    if c > REPEAT_UNROLL_CAP as i64 {
                        self.error(
                            MsgCode::ElabUnsupported,
                            &format!(
                                "an intra-assignment `repeat(n)` count exceeds the unroll cap ({REPEAT_UNROLL_CAP})"
                            ),
                        );
                        return;
                    }
                    c as u32
                }
                None => {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "a runtime (non-constant) `repeat(n)` count in an intra-assignment \
                         event control is unsupported (n must fold to a constant)",
                    );
                    return;
                }
            },
        };
        let rhs_id = self.lower_expr(rhs);
        let lv = self.lower_lvalue(lhs);
        self.check_lvalue_kind(&lv, true); // P1-9 (E3018): no proc write to a net
        let w = self.ir_lvalue_width(&lv);
        let tmp = self.fresh_ia_tmp(w);
        let cap = self.push_stmt(ir::Stmt::BlockingAssign {
            lhs: whole_net_lvalue(tmp),
            rhs: rhs_id,
        });
        b.push_stmt_id(cap);
        // Wait for the event `waits` times (zero ⇒ immediate write). Emitting the
        // EventCtrl `waits` times produces `waits` sequential Wait terminators.
        let evt = ast::Stmt::EventCtrl {
            ctrl: ie.ctrl.clone(),
            body: None,
            span,
        };
        for _ in 0..waits {
            self.lower_stmt(b, &evt);
        }
        // Write the captured value (lvalue index evaluated here, at write time).
        let tmp_read = self.push_expr(ir::Expr::Signal {
            net: tmp,
            word: None,
        });
        let wr = self.push_stmt(ir::Stmt::BlockingAssign {
            lhs: lv,
            rhs: tmp_read,
        });
        b.push_stmt_id(wr);
    }

    /// Synthesize a private capture temp for an intra-assignment delay site
    /// (`$ia_tmp$<n>` — `$` keeps it collision-proof against user identifiers).
    fn fresh_ia_tmp(&mut self, width: u32) -> u32 {
        let name = format!("$ia_tmp${}", self.nets.len());
        let nv = ir::NetVar {
            kind: ir::NetKind::Reg,
            width,
            msb: width.saturating_sub(1),
            lsb: 0,
            signed: false,
            array_len: 1,
            dir: ir::PortDir::Internal,
            init: default_init(ast::NetVarKind::Reg, width),
        };
        self.add_net(&name, nv);
        (self.nets.len() - 1) as u32
    }

    /// Register a net by name → NetId (declaration-order append). A duplicate
    /// name is a hard error: we keep the FIRST binding, emit `ElabUnsupported`
    /// (closest v1 code; doc-15 reserves `E-ELAB-DUP-DECL` for the eventual
    /// dedicated slot), and do NOT push the orphan net — so `net_count` and the
    /// golden hash are not perturbed by an unreferenceable duplicate.
    /// (LOWERING + COVERAGE verdicts: duplicate-net silent acceptance.)
    fn add_net(&mut self, name: &str, net: ir::NetVar) {
        let key = self.fq(name);
        if self.symbols.contains_key(&key) {
            self.error(
                MsgCode::ElabUnsupported,
                &format!("net/variable `{key}` redeclared (duplicate declaration)"),
            );
            return;
        }
        let id = self.nets.len() as u32;
        self.nets.push(net);
        self.symbols.insert(key, id);
    }

    /// Resolve declared range → (width, msb, lsb, signed). `Integer` is a fixed
    /// 32-bit signed type regardless of any range.
    ///
    /// Width arithmetic is overflow-guarded: `abs_diff(..) + 1` is computed in
    /// `u64` and rejected above [`MAX_NET_WIDTH`] with `ElabUnsupported` (the net
    /// is then clamped to width 1 so the arena stays valid). A `[N:0]` with
    /// `N = u32::MAX` no longer panics. (COVERAGE verdict HIGH.)
    fn range_to_dims(
        &mut self,
        kind: ast::NetVarKind,
        range: Option<&ast::Range>,
        signed: bool,
    ) -> (u32, u32, u32, bool) {
        if matches!(kind, ast::NetVarKind::Integer) {
            return (32, 31, 0, true);
        }
        // `real`/`realtime` are dimensionless 64-bit signed (no [msb:lsb] range).
        if matches!(kind, ast::NetVarKind::Real | ast::NetVarKind::Realtime) {
            return (64, 63, 0, true);
        }
        // `time` is a dimensionless 64-bit UNSIGNED 4-state variable (IEEE §6.11).
        if matches!(kind, ast::NetVarKind::Time) {
            return (64, 63, 0, false);
        }
        // a named event is dimensionless; its counter desugar is 64-bit unsigned.
        if matches!(kind, ast::NetVarKind::Event) {
            return (64, 63, 0, false);
        }
        match range {
            None => (1, 0, 0, signed),
            Some(r) => {
                // v3: fold through the param-aware evaluator so `[W-1:0]` resolves
                // `W` to the bound parameter value in the current instance scope.
                let msb_v = self.const_eval_in_scope(&r.msb);
                let lsb_v = self.const_eval_in_scope(&r.lsb);
                // A bound that folds NEGATIVE is the degenerate `[W-1:0]`-with-W==0
                // underflow artifact (the signed i64 domain shows it directly; the
                // old u32 wrap needed Sub-shape detection): clamp to width 1 + warn,
                // NOT a fatal MAX_NET_WIDTH explosion. A *literal* huge bound
                // (`[4294967295:0]`) folds positive and still hits the over-cap
                // error below.
                if msb_v.is_some_and(|v| v < 0) || lsb_v.is_some_and(|v| v < 0) {
                    self.warn(
                        "parameterized range underflowed (param value 0?); net clamped to width 1",
                    );
                    return (1, 0, 0, signed);
                }
                let clamp =
                    |v: Option<i64>| v.map_or(0u32, |v| u32::try_from(v).unwrap_or(u32::MAX));
                let msb = clamp(msb_v);
                let lsb = clamp(lsb_v);
                let width64 = (msb.abs_diff(lsb) as u64) + 1;
                if width64 > MAX_NET_WIDTH {
                    self.error(
                        MsgCode::ElabUnsupported,
                        &format!(
                            "declared net width {width64} exceeds the v1 cap ({MAX_NET_WIDTH})"
                        ),
                    );
                    return (1, 0, 0, signed);
                }
                (width64 as u32, msb, lsb, signed)
            }
        }
    }

    /// Direction of a body-declared net: Input/Output/Inout if it appears in the
    /// port list, else Internal.
    fn dir_for_name(
        &mut self,
        name: &str,
        ports: &ast::PortList,
        body: &[ast::ModuleItem],
    ) -> ir::PortDir {
        match ports {
            ast::PortList::Ansi(list) => list
                .iter()
                .find(|p| p.name.name == name)
                .map(|p| map_port_dir(p.dir))
                .unwrap_or(ir::PortDir::Internal),
            ast::PortList::NonAnsi(names) => {
                if names.iter().any(|i| i.name == name) {
                    // Fix 4: merge the body PortDecl direction (`output reg y;`)
                    // just like `port_list_dirs` does — no more silent Input
                    // default for a non-ANSI `output`/`inout` port.
                    body.iter()
                        .find_map(|it| match it {
                            ast::ModuleItem::PortDecl(pd)
                                if pd.names.iter().any(|x| x.name == name) =>
                            {
                                Some(map_port_dir(pd.dir))
                            }
                            _ => None,
                        })
                        .unwrap_or(ir::PortDir::Input)
                } else {
                    ir::PortDir::Internal
                }
            }
            ast::PortList::None => ir::PortDir::Internal,
        }
    }

    // ── PASS 2: continuous assigns ─────────────────────────────────
    /// A NET-type declaration initializer (`wire [3:0] x = a & b;`) is an IMPLICIT
    /// continuous assign — a driver, equivalent to a separate `assign x = a & b;`.
    /// A variable (reg/logic/integer/real/…) initializer is instead a one-time
    /// value applied at net creation, so it is skipped here.
    fn elaborate_net_init_drivers(&mut self, d: &ast::NetVarDecl) {
        let is_var = matches!(
            d.kind,
            ast::NetVarKind::Reg
                | ast::NetVarKind::Logic
                | ast::NetVarKind::Integer
                | ast::NetVarKind::Real
                | ast::NetVarKind::Realtime
                | ast::NetVarKind::Time
                | ast::NetVarKind::Event
        );
        if is_var {
            return;
        }
        for name in &d.names {
            let Some(init) = &name.init else {
                continue;
            };
            let path = ast::HierPath {
                segments: vec![name.name.clone()],
                span: name.name.span,
            };
            let lhs = self.lower_lvalue(&ast::Lvalue::Ident(path));
            let rhs_id = self.lower_expr(init);
            self.cont_assigns.push(ir::ContAssign {
                lhs,
                rhs: rhs_id,
                delay: None,
            });
        }
    }

    fn elaborate_cont_assign(&mut self, ca: &ast::ContinuousAssign) {
        // Delay: hdl-ast Delay values are exprs; sim-ir delay is Option<u32>.
        // v1 const-folds a literal rise delay; non-const → None (note slot).
        let mult = self.cur_time_mult;
        let delay = ca
            .delay
            .as_ref()
            .and_then(|d| d.values.first().and_then(|e| const_delay_ticks(e, mult)));
        for (lv, rhs) in &ca.assigns {
            let lhs = self.lower_lvalue(lv);
            // P1-9 (E3018): a user `assign` may not drive a Reg/Integer/Real
            // variable (SV `logic` admits one continuous driver — passes). Port
            // bindings / decl-inits are NOT routed here (IEEE 1800 var-port and
            // legacy `reg r = init` forms stay accepted).
            self.check_lvalue_kind(&lhs, false);
            let rhs_id = self.lower_expr(rhs);
            self.cont_assigns.push(ir::ContAssign {
                lhs,
                rhs: rhs_id,
                delay,
            });
        }
    }

    // ── expression lowering: post-order arena append, returns ExprId ──
    fn lower_expr(&mut self, e: &ast::Expr) -> u32 {
        match &e.kind {
            // ── leaves ──────────────────────────────────────────────
            ast::ExprKind::IntLit { kind, raw } => {
                let cid = self.lower_int_literal(*kind, raw);
                self.push_expr(ir::Expr::Const { val: cid })
            }
            // v7 P2-D: explicit `pkg::name` — folds through the package
            // const map (sees the PACKAGE value even when a local declaration
            // shadows an import, iverilog-pinned). Function references need
            // call syntax, which is outside the v7 scope — loud.
            ast::ExprKind::PkgScoped { pkg, name } => {
                match self
                    .pkg_consts
                    .get(&pkg.name)
                    .and_then(|c| c.get(&name.name))
                {
                    Some(&v) => self.const_param_expr(v),
                    None => {
                        self.error(
                            MsgCode::ElabUnsupported,
                            &format!(
                                "`{}::{}` does not name a package constant (v7 \
                                 supports param/enum-label references)",
                                pkg.name, name.name
                            ),
                        );
                        self.placeholder_expr()
                    }
                }
            }
            ast::ExprKind::Ident(path) => {
                // INLINE substitution (function/task formals). A single-segment name
                // bound to an actual-arg ExprId lowers to that ExprId directly — no
                // new IR node, exactly like `Paren` unwrapping. Innermost wins.
                if path.segments.len() == 1 {
                    let seg = &path.segments[0].name;
                    if let Some(eid) = self.subst_lookup(seg) {
                        return eid;
                    }
                    // output/inout task formal: resolves to the caller's net.
                    if let Some(net) = self.out_subst_lookup(seg) {
                        if self.net_is_static_array(net) {
                            // Phase-1.x ②: an out-actual bound to a whole
                            // array would otherwise read word 0 SILENTLY
                            // through the formal (adversarial find #2).
                            self.error(
                                MsgCode::ElabUnsupported,
                                "a task output formal bound to a whole unpacked \
                                 array has no value (v1: arrays cannot pass \
                                 through task ports)",
                            );
                        }
                        return self.push_expr(ir::Expr::Signal { net, word: None });
                    }
                    // parameter / localparam / genvar: a constant in THIS scope (or
                    // an enclosing generate scope) folds to a Const, NOT a net read.
                    // Resolved before `resolve_net` so a param never errors as an
                    // undeclared net (mirrors `const_eval_in_scope`'s lookup_scoped).
                    if let Some(v) = self.lookup_scoped(seg) {
                        return self.const_param_expr(v);
                    }
                }
                let net = self.resolve_net(path);
                if self.event_nets.contains(&net) {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "a named event has no value: it cannot be read in an \
                         expression (only `->e` and `@(e)` touch it)",
                    );
                }
                if self.is_dyn_handle_net(net) {
                    // v5 ⑥: whole-handle reads (incl. handle copy `d2 = d`)
                    // are outside the MVP — elements/methods only.
                    self.error(
                        MsgCode::ElabUnsupported,
                        "a dynamic-storage handle has no whole-value surface (read elements or call methods)",
                    );
                }
                if self.net_is_static_array(net) {
                    // Phase-1.x ②: a whole unpacked array is only a value in
                    // ARRAY ASSIGNMENT (intercepted before lowering reaches
                    // here). Anywhere else it used to read word 0 SILENTLY.
                    self.error(
                        MsgCode::ElabUnsupported,
                        "a whole unpacked array has no value in this context \
                         (v1: arrays are copied by array assignment; index an \
                         element elsewhere)",
                    );
                }
                self.push_expr(ir::Expr::Signal { net, word: None })
            }

            // ── operators (1:1 name-map; children lowered first) ────
            ast::ExprKind::Unary { op, operand } => {
                let operand = self.lower_expr(operand);
                let irop = map_unop(*op);
                // §6.2: bitwise `~` / reductions on a real are illegal (`+`/`-`/`!`
                // are legal: unary +/- are real-preserving, `!` is logical).
                if self.expr_is_real(operand)
                    && matches!(
                        irop,
                        ir::UnOp::BitNot
                            | ir::UnOp::RedAnd
                            | ir::UnOp::RedNand
                            | ir::UnOp::RedOr
                            | ir::UnOp::RedNor
                            | ir::UnOp::RedXor
                            | ir::UnOp::RedXnor
                    )
                {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "bitwise/shift/reduction not defined on real operand",
                    );
                }
                self.push_expr(ir::Expr::Unary { op: irop, operand })
            }
            ast::ExprKind::Binary { op, lhs, rhs } => {
                // v7 P2-C: a comparison with a STRING-domain operand routes
                // through StrCmp (packed compare zero-extends MSB-side, which
                // is NOT lexicographic for unequal lengths; sizing the
                // dynamic widths statically would truncate). `cmp <op> 0`
                // with a SIGNED zero keeps the relational signed.
                if matches!(
                    op,
                    ast::BinOp::Eq
                        | ast::BinOp::Ne
                        | ast::BinOp::Lt
                        | ast::BinOp::Le
                        | ast::BinOp::Gt
                        | ast::BinOp::Ge
                ) && (self.expr_is_string_ast(lhs) || self.expr_is_string_ast(rhs))
                {
                    let l = self.lower_expr(lhs);
                    let r = self.lower_expr(rhs);
                    let cmp = self.push_expr(ir::Expr::SysFunc {
                        which: ir::SysFuncId::StrCmp,
                        args: vec![l, r],
                    });
                    let zero = {
                        let cid = self.intern_const(make_const_i64(0, 32, true));
                        self.push_expr(ir::Expr::Const { val: cid })
                    };
                    return self.push_expr(ir::Expr::Binary {
                        op: map_binop(*op),
                        lhs: cmp,
                        rhs: zero,
                    });
                }
                let lhs = self.lower_expr(lhs); // POST-ORDER: lhs, then rhs, then self
                let rhs = self.lower_expr(rhs);
                let irop = map_binop(*op);
                // §6.2 permanent illegalities on a real operand.
                if self.expr_is_real(lhs) || self.expr_is_real(rhs) {
                    match irop {
                        ir::BinOp::Mod => self.error(
                            MsgCode::ElabUnsupported,
                            "modulo (%) not defined on real operand",
                        ),
                        ir::BinOp::Pow => self.error(
                            MsgCode::ElabUnsupported,
                            "power (**) not defined on real operand in MVP",
                        ),
                        ir::BinOp::BitAnd
                        | ir::BinOp::BitOr
                        | ir::BinOp::BitXor
                        | ir::BinOp::BitXnor
                        | ir::BinOp::Shl
                        | ir::BinOp::Shr
                        | ir::BinOp::AShl
                        | ir::BinOp::AShr => self.error(
                            MsgCode::ElabUnsupported,
                            "bitwise/shift/reduction not defined on real operand",
                        ),
                        _ => {}
                    }
                }
                self.push_expr(ir::Expr::Binary { op: irop, lhs, rhs })
            }
            ast::ExprKind::Ternary {
                cond,
                then_e,
                else_e,
            } => {
                let cond = self.lower_expr(cond);
                let then_e = self.lower_expr(then_e);
                let else_e = self.lower_expr(else_e);
                self.push_expr(ir::Expr::Ternary {
                    cond,
                    then_e,
                    else_e,
                })
            }

            // ── selects → Select{base,offset,width,kind} (all ExprIds) ──
            ast::ExprKind::BitSelect { base, index } => {
                // v5 ⑥: dyn-handle element read (`d[i]`, `q[$]`, `a[k]`) —
                // BEFORE the static array/packed chains (handles have
                // `array_len 0`, so those would mis-route to bit-select).
                if let Some(eid) = self.dyn_select_read(base, index) {
                    return eid;
                }
                // SYMMETRY with the LHS (`collect_lval_chunks`): a `base[i]…[k]`
                // chain rooted at an ARRAY net is a WORD select (the first D indices
                // flatten row-major to the element word `i0*s0+…+iD`), with any
                // trailing indices becoming bit-selects INTO that word. The single-
                // dim `mem[i]` and `mem[i][j]` cases are the D==1 specialisation —
                // lowered byte-identically to the old path. A scalar base falls
                // through to the plain bit-select below.
                if let Some((net, idxs)) = self.expr_array_chain(base, index) {
                    return self.lower_array_read(net, &idxs);
                }
                if let Some((net, idxs)) = self.expr_packed_chain(base, index) {
                    return self.lower_packed_read(net, &idxs);
                }
                let base_id = self.lower_expr(base);
                if self.expr_is_real(base_id) {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "bit/part-select not defined on real operand",
                    );
                }
                let raw_off = self.lower_expr(index);
                let offset = self.norm_offset_if_net(base, raw_off);
                let width = self.const_u32_expr(1, 32);
                self.push_expr(ir::Expr::Select {
                    base: base_id,
                    offset,
                    width,
                    kind: ir::SelKind::Bit,
                })
            }
            ast::ExprKind::PartSelect { base, msb, lsb } => {
                let base_id = self.lower_expr(base);
                if self.expr_is_real(base_id) {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "bit/part-select not defined on real operand",
                    );
                }
                let lsb_id = self.lower_expr(lsb);
                let msb_id = self.lower_expr(msb);
                let width = self.width_from_msb_lsb_checked(msb, lsb, msb_id, lsb_id);
                let offset = self.norm_offset_if_net(base, lsb_id);
                self.push_expr(ir::Expr::Select {
                    base: base_id,
                    offset,
                    width,
                    kind: ir::SelKind::PartConst,
                })
            }
            ast::ExprKind::IndexedPart {
                base,
                offset,
                width,
                dir,
            } => {
                let base_id = self.lower_expr(base);
                if self.expr_is_real(base_id) {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "bit/part-select not defined on real operand",
                    );
                }
                let raw_off = self.lower_expr(offset);
                let off = self.norm_offset_if_net(base, raw_off);
                let width = self.lower_expr(width);
                let kind = match dir {
                    ast::PartDir::PlusColon => ir::SelKind::PartIdxUp,
                    ast::PartDir::MinusColon => ir::SelKind::PartIdxDown,
                };
                self.push_expr(ir::Expr::Select {
                    base: base_id,
                    offset: off,
                    width,
                    kind,
                })
            }

            // ── structural ─────────────────────────────────────────
            ast::ExprKind::Concat { parts } => {
                // v7 P2-C: string concatenation needs dynamic-width results
                // the static Concat node cannot carry — loud, $sformatf works.
                if parts.iter().any(|p| self.expr_is_string_ast(p)) {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "string concatenation is outside the v7 scope (use $sformatf(\"%s%s\", a, b))",
                    );
                    return self.placeholder_expr();
                }
                let part_ids: Vec<u32> = parts.iter().map(|p| self.lower_expr(p)).collect();
                if part_ids.iter().any(|&p| self.expr_is_real(p)) {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "real may not appear in concatenation (use $realtobits)",
                    );
                }
                self.push_expr(ir::Expr::Concat { parts: part_ids })
            }
            ast::ExprKind::Replicate { count, value } => {
                // hdl-ast `value: Vec<Expr>` is the element LIST (no wrapper
                // Concat); sim-ir Replicate wants ONE `value: u32` → wrap in a
                // Concat node. (For a single element this is a 1-part Concat,
                // kept for shape-uniformity / determinism.)
                let count = self.lower_expr(count);
                let part_ids: Vec<u32> = value.iter().map(|p| self.lower_expr(p)).collect();
                if part_ids.iter().any(|&p| self.expr_is_real(p)) {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "real may not appear in concatenation (use $realtobits)",
                    );
                }
                let value = self.push_expr(ir::Expr::Concat { parts: part_ids });
                self.push_expr(ir::Expr::Replicate { count, value })
            }

            // ── calls ──────────────────────────────────────────────
            ast::ExprKind::SysCall { name, args } => {
                // v7: `$bits` is a TYPE function — its argument is NOT
                // evaluated (IEEE §20.6.2) — and folds to a const at
                // elaborate (IR-0). Array views bypass lowering entirely
                // (whole-array reads are loud by design).
                if name.name == "$bits" && args.len() == 1 {
                    return self.lower_bits_fold(&args[0]);
                }
                // v7: a SEEDED $random updates its ref argument — legal ONLY
                // as the direct rhs of a blocking assign (the special form
                // bypasses this arm). Any other placement is loud, never a
                // silent unseeded draw.
                if name.name == "$random" && !args.is_empty() {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "seeded $random is supported only as the direct rhs of \
                         a blocking assignment (v7)",
                    );
                    return self.placeholder_expr();
                }
                // v7: $fopen mutates the file table — direct-rhs only.
                if name.name == "$fopen" {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "$fopen is supported only as the direct rhs of a \
                         blocking assignment (v7)",
                    );
                    return self.placeholder_expr();
                }
                // v7 P2-C: $sformatf renders through the kernel-side format
                // engine — direct-rhs only (the dominant TB pattern is
                // `msg = $sformatf(...); $display("%s", msg);`).
                if name.name == "$sformatf" {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "$sformatf is supported only as the direct rhs of a \
                         blocking assignment (v7)",
                    );
                    return self.placeholder_expr();
                }
                // v7: $value$plusargs writes its ref var — direct-rhs only.
                if name.name == "$value$plusargs" {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "$value$plusargs is supported only as the direct rhs \
                         of a blocking assignment (v7)",
                    );
                    return self.placeholder_expr();
                }
                // v7: the $test$plusargs query must be a string literal (the
                // full string type lands with P2-C).
                if name.name == "$test$plusargs"
                    && !matches!(
                        args.first().map(|a| &a.kind),
                        Some(ast::ExprKind::StrLit { .. })
                    )
                {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "$test$plusargs needs a string-literal query (v7)",
                    );
                    return self.placeholder_expr();
                }
                let arg_ids: Vec<u32> = args.iter().map(|a| self.lower_expr(a)).collect();
                match map_sysfunc(&name.name) {
                    Some(which) => {
                        // v7 bit-vector predicates are integral-only; a real
                        // argument would silently count IEEE-754 mantissa
                        // bits — loud instead (IEEE: illegal operand type).
                        if matches!(
                            which,
                            ir::SysFuncId::CountOnes
                                | ir::SysFuncId::OneHot
                                | ir::SysFuncId::OneHot0
                                | ir::SysFuncId::IsUnknown
                        ) && arg_ids.iter().any(|&a| self.expr_is_real(a))
                        {
                            self.error(
                                MsgCode::ElabUnsupported,
                                "real operand is not legal for a bit-vector system function",
                            );
                            return self.placeholder_expr();
                        }
                        self.push_expr(ir::Expr::SysFunc {
                            which,
                            args: arg_ids,
                        })
                    }
                    None => {
                        self.error(
                            MsgCode::ElabUnsupported,
                            "unsupported system function in expression",
                        );
                        self.placeholder_expr()
                    }
                }
            }
            ast::ExprKind::Call { name, args } => self.inline_function(name, args),

            // ── transparent / placeholder ──────────────────────────
            ast::ExprKind::Paren { inner } => self.lower_expr(inner), // unwrap, no IR node
            ast::ExprKind::MinTypMax { typ, .. } => self.lower_expr(typ), // pick typ branch
            // v2: a string literal interns as a `StrUtf8` const. Used by $systask
            // format/args ($display("...", x), $dumpfile("dump.vcd")). Escapes are
            // processed by `parse_str_literal`; the const pool dedups StrUtf8 vs
            // Numeric via the repr tag (intern_const ConstKey).
            ast::ExprKind::StrLit { raw } => {
                let cid = self.intern_const(parse_str_literal(raw));
                self.push_expr(ir::Expr::Const { val: cid })
            }
            ast::ExprKind::RealLit { raw, .. } => {
                let cid = self.intern_const(parse_real_literal(raw));
                self.push_expr(ir::Expr::Const { val: cid })
            }
            // v5 ⑥: `new[n]` reached OUTSIDE `d = new[n]` (its only legal
            // placement, intercepted in `dyn_blocking_special`).
            ast::ExprKind::New { size, src } => {
                // V2005 compat: a net actually named `new` — re-lower as the
                // indexed read the source meant (`new[i]`).
                if src.is_none() && self.lookup_net_scoped("new").is_some() {
                    let span = e.span;
                    let fake = ast::Expr {
                        kind: ast::ExprKind::BitSelect {
                            base: Box::new(ast::Expr {
                                kind: ast::ExprKind::Ident(ast::HierPath {
                                    segments: vec![ast::Ident {
                                        name: "new".to_string(),
                                        span,
                                    }],
                                    span,
                                }),
                                span,
                            }),
                            index: size.clone(),
                        },
                        span,
                    };
                    return self.lower_expr(&fake);
                }
                self.error(
                    MsgCode::ElabUnsupported,
                    "`new[n]` is only valid as the rhs of a blocking assignment to a dynamic-array handle",
                );
                self.placeholder_expr()
            }
            // v5 ⑥: bare `$` — meaningful only inside a queue element select
            // (`lower_dyn_index` pins the substitution).
            ast::ExprKind::Dollar => match self.dollar_subst {
                Some(eid) => eid,
                None => {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "`$` is only valid inside a queue element select (`q[$]`)",
                    );
                    self.placeholder_expr()
                }
            },
            ast::ExprKind::Error => {
                self.error(
                    MsgCode::ElabUnsupported,
                    "cannot lower parse-error expression",
                );
                self.placeholder_expr()
            }
        }
    }

    // ── lvalue lowering ────────────────────────────────────────────
    fn lower_lvalue(&mut self, lv: &ast::Lvalue) -> ir::Lvalue {
        let mut chunks = Vec::new();
        self.collect_lval_chunks(lv, &mut chunks);
        // review F3: a string chunk inside a CONCAT lvalue has chunk width 0
        // — the runtime slice loop wrote an EMPTY piece (silently clearing
        // the string). Whole-string single-chunk stays the supported shape.
        if chunks.len() > 1 && chunks.iter().any(|c| self.is_string_net(c.net)) {
            self.error(
                MsgCode::ElabUnsupported,
                "a string inside a concatenation lvalue is outside the v7 scope",
            );
        }
        ir::Lvalue { chunks }
    }

    fn collect_lval_chunks(&mut self, lv: &ast::Lvalue, out: &mut Vec<ir::LvalChunk>) {
        // v6 ②: every lvalue shape roots at one Ident — check the modport
        // write rule once per root (concat parts re-enter here per part).
        if let Some(path) = lval_root_path(lv) {
            let path = path.clone();
            self.check_modport_write(&path);
        }
        match lv {
            ast::Lvalue::Ident(path) => {
                // An output/inout task formal written by an inlined body targets the
                // caller's net directly (symmetric with the read side in lower_expr).
                let net = if path.segments.len() == 1 {
                    self.out_subst_lookup(&path.segments[0].name)
                        .unwrap_or_else(|| self.resolve_net(path))
                } else {
                    self.resolve_net(path)
                };
                if self.event_nets.contains(&net) {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "a named event cannot be assigned (only `->e` triggers it)",
                    );
                }
                if self.is_dyn_handle_net(net) {
                    // v5 ⑥: whole-handle assignment (`d2 = d`, `assign q = …`)
                    // is outside the MVP (`d = new[n]` is intercepted earlier
                    // and never reaches the lvalue path).
                    self.error(
                        MsgCode::ElabUnsupported,
                        "a dynamic-storage handle cannot be assigned as a whole (use `new[]`, methods or element writes)",
                    );
                }
                if self.net_is_static_array(net) {
                    // Phase-1.x ②: a whole unpacked array is only a write
                    // target in procedural ARRAY ASSIGNMENT (intercepted
                    // before lowering reaches here). Anywhere else — force,
                    // continuous assign, … — it used to write word 0 SILENTLY.
                    self.error(
                        MsgCode::ElabUnsupported,
                        "a whole unpacked array cannot be the write target in \
                         this context (v1: procedural array assignment only)",
                    );
                }
                out.push(ir::LvalChunk {
                    net,
                    word: None,
                    offset: None,
                    width: None,
                    kind: ir::SelKind::Bit, // neutral tag; offset/width None ⇒ whole net
                });
            }
            ast::Lvalue::BitSelect { base, index, .. } => {
                // v5 ⑥: dyn-handle element write (`d[i] = v`, `q[$] = v`,
                // `a[k] = v`) — handles never take the static chunk paths.
                if let ast::Lvalue::Ident(p) = &**base {
                    if p.segments.len() == 1 {
                        if let Some((net, kind)) = self.dyn_handle(&p.segments[0].name) {
                            let word = self.lower_dyn_index(net, kind, index);
                            out.push(ir::LvalChunk {
                                net,
                                word: Some(word),
                                offset: None,
                                width: None,
                                kind: ir::SelKind::Bit,
                            });
                            return;
                        }
                    }
                }
                // SYMMETRY with the RHS read: a `base[i]…[k]` chain rooted at an
                // ARRAY net writes the flat element word (first D indices, row-major)
                // with an optional trailing single bit-select. `LvalChunk.word` is an
                // ExprId, evaluated at write time, so `mem[k] = …` (runtime k) and
                // `g[i][j] = …` (2-D element) both work; `mem[k]`/`g[i][j]` are the
                // D==1/D==2 ends of one path. A scalar base falls through to plain
                // bit-select.
                if let Some((net, idxs)) = self.lval_array_chain(base, index) {
                    self.collect_array_write(net, &idxs, out);
                } else if let Some((net, idxs)) = self.lval_packed_chain(base, index) {
                    self.collect_packed_write(net, &idxs, out);
                } else {
                    let net = self.lval_base_net(base);
                    let raw_off = self.lower_expr(index);
                    let offset = self.norm_offset_for_net(net, raw_off);
                    let width = self.const_u32_expr(1, 32);
                    out.push(ir::LvalChunk {
                        net,
                        word: None,
                        offset: Some(offset),
                        width: Some(width),
                        kind: ir::SelKind::Bit,
                    });
                }
            }
            ast::Lvalue::PartSelect { base, msb, lsb, .. } => {
                // `g[i][j][msb:lsb] = …` — part-select WITHIN an array element word.
                // `lval_part_base` resolves the element (net + flat word); a scalar
                // base gives `(net, None)` ⇒ the classic `r[msb:lsb]` chunk.
                let (net, word) = self.lval_part_base(base);
                let lsb_id = self.lower_expr(lsb);
                let msb_id = self.lower_expr(msb);
                let width = self.width_from_msb_lsb_checked(msb, lsb, msb_id, lsb_id);
                let offset = self.norm_offset_for_net(net, lsb_id);
                out.push(ir::LvalChunk {
                    net,
                    word,
                    offset: Some(offset),
                    width: Some(width),
                    kind: ir::SelKind::PartConst,
                });
            }
            ast::Lvalue::IndexedPart {
                base,
                offset,
                width,
                dir,
                ..
            } => {
                let (net, word) = self.lval_part_base(base);
                let raw_off = self.lower_expr(offset);
                let off = self.norm_offset_for_net(net, raw_off);
                let w = self.lower_expr(width);
                let kind = match dir {
                    ast::PartDir::PlusColon => ir::SelKind::PartIdxUp,
                    ast::PartDir::MinusColon => ir::SelKind::PartIdxDown,
                };
                out.push(ir::LvalChunk {
                    net,
                    word,
                    offset: Some(off),
                    width: Some(w),
                    kind,
                });
            }
            ast::Lvalue::Concat { parts, .. } => {
                // Flatten left→right (MSB-first source order) into the chunk list.
                for p in parts {
                    self.collect_lval_chunks(p, out);
                }
            }
            ast::Lvalue::Error(_) => {
                self.error(MsgCode::ElabUnsupported, "cannot lower parse-error lvalue");
                out.push(ir::LvalChunk {
                    net: POISON_NET,
                    word: None,
                    offset: None,
                    width: None,
                    kind: ir::SelKind::Bit,
                });
            }
        }
    }

    /// An lvalue select's base must reduce to a net Ident in v1 (no nested
    /// selects). Returns NetId; emits + returns [`POISON_NET`] otherwise.
    fn lval_base_net(&mut self, base: &ast::Lvalue) -> u32 {
        match base {
            ast::Lvalue::Ident(p) => self.resolve_net(p),
            _ => {
                self.error(
                    MsgCode::ElabUnsupported,
                    "nested lvalue select (v1: single-level)",
                );
                POISON_NET
            }
        }
    }

    /// Resolve the base of a part-select LHS to `(net, word)`. A bare `Ident` is a
    /// scalar (or 1-D word-0) base ⇒ `word = None`. A `g[i]…[k]` chain rooted at an
    /// array net is an ELEMENT part-select (`g[i][j][msb:lsb] = …`): all D indices
    /// flatten to the element word, and the part-select applies within it. Indexing
    /// fewer than D dims (partial slice) or more than D (bit-then-part) is loud.
    fn lval_part_base(&mut self, base: &ast::Lvalue) -> (u32, Option<u32>) {
        if let ast::Lvalue::BitSelect {
            base: b, index: i, ..
        } = base
        {
            if let Some((net, idxs)) = self.lval_array_chain(b, i) {
                let dims = self.net_dim_extents(net);
                let d = dims.len();
                if idxs.len() == d {
                    let word = self.flatten_word(&dims, &idxs);
                    return (net, Some(word));
                }
                self.error(
                    MsgCode::ElabUnsupported,
                    if idxs.len() < d {
                        "partial unpacked-array slice (v1: index every dimension)"
                    } else {
                        "bit-select then part-select on a multi-dim array lvalue (v1 unsupported)"
                    },
                );
                return (POISON_NET, None);
            }
        }
        (self.lval_base_net(base), None)
    }

    // ── name resolution ────────────────────────────────────────────
    /// Resolve a HierPath → NetId. v1: single-segment (flat) names only. Unknown
    /// → emit + return [`POISON_NET`] (u32::MAX, NOT 0 — so a surviving poison
    /// edge is detectable, never a silent alias of net 0). The IR is discarded on
    /// `had_error` regardless. (COVERAGE verdict MEDIUM.)
    fn resolve_net(&mut self, path: &ast::HierPath) -> u32 {
        if path.segments.len() != 1 {
            // v5 ⑥ (D): interface member access (`bus.sig`, `i.sig`) — the
            // dotted name IS the symbol key (aliases inserted by interface
            // port binding; direct `i.sig` hits the instance's own nets).
            let joined = path
                .segments
                .iter()
                .map(|s| s.name.as_str())
                .collect::<Vec<_>>()
                .join(".");
            if let Some(id) = self.lookup_net_scoped(&joined) {
                return id;
            }
            // hierarchical cross-ref (tb.dut.x in an expression) still DEFERRED.
            self.error(
                MsgCode::ElabUnsupported,
                "hierarchical name reference in expression (deferred)",
            );
            return POISON_NET;
        }
        // Resolve in the current scope, then each ENCLOSING scope. A net declared
        // in the module body (`top.d`) is visible from inside a generate block
        // (`top.g[0]`); a net declared inside the block (`top.g[0].t`) shadows it.
        let name = &path.segments[0].name;
        match self.lookup_net_scoped(name) {
            Some(id) => id,
            None => {
                self.error(
                    MsgCode::ElabUnresolvedName,
                    &format!("undeclared net/variable `{}`", self.fq(name)),
                );
                POISON_NET
            }
        }
    }

    /// Resolve a bare net `name` to its NetId, searching the current scope then
    /// each enclosing GENERATE-block scope. Symmetric with [`Self::lookup_scoped`]
    /// for params/genvars; STOPS at an instance boundary (per-instance net
    /// isolation). Returns the innermost (most specific) binding.
    fn lookup_net_scoped(&self, name: &str) -> Option<u32> {
        self.walk_scopes(name, &self.symbols)
    }

    // ── user function/task inlining (SD2 inline path) ──────────────
    /// Innermost-wins lookup in the input-formal substitution stack. Empty in
    /// steady state.
    fn subst_lookup(&self, name: &str) -> Option<u32> {
        self.subst
            .iter()
            .rev()
            .find(|(n, _)| n == name)
            .map(|(_, e)| *e)
    }
    /// Innermost-wins lookup in the output/inout-formal → caller-net stack.
    fn out_subst_lookup(&self, name: &str) -> Option<u32> {
        self.out_subst
            .iter()
            .rev()
            .find(|(n, _)| n == name)
            .map(|(_, e)| *e)
    }

    /// Inline a user-function call at an expression site → the ExprId of its return
    /// value (SD2 inline path; a 0-time function = zero schema cost). The common
    /// case is a combinational function whose body reduces to the return expression
    /// once the formals are substituted by the actual-arg ExprIds. Returns a
    /// placeholder ExprId on any unsupported shape (after emitting the diagnostic)
    /// so arena edges stay valid.
    fn inline_function(&mut self, name: &ast::HierPath, args: &[ast::Expr]) -> u32 {
        // v5 ⑥: `handle.method(args)` — a 2-segment call whose head is a dyn
        // handle is a METHOD, not a hierarchical call.
        if name.segments.len() == 2 {
            if let Some((net, kind)) = self.dyn_handle(&name.segments[0].name) {
                return self.lower_dyn_method_expr(net, kind, &name.segments[1].name, args);
            }
            // v7 P2-C: string methods.
            if let Some(net) = self.string_handle(&name.segments[0].name) {
                return self.lower_string_method_expr(net, &name.segments[1].name, args);
            }
        }
        if name.segments.len() != 1 {
            self.error(
                MsgCode::ElabUnsupported,
                "hierarchical function call (deferred)",
            );
            return self.placeholder_expr();
        }
        let fname = name.segments[0].name.clone();

        // Clone the def out of the table so we can mutate `self` while lowering.
        let func = match self.func_table.get(fname.as_str()) {
            Some(f) => f.clone(),
            None => {
                self.error(
                    MsgCode::ElabUnresolvedName,
                    &format!("call to undeclared function `{fname}`"),
                );
                return self.placeholder_expr();
            }
        };

        // B1 frame-call: a function in the frame set (automatic OR on a recursion
        // cycle) is LOWERED to the func arena (reserved in step 6.5), not inlined.
        // Emit an `Expr::Call` to its FuncId — the args are lowered in the CALLER
        // scope (they read caller nets / outer subst, never the callee formals).
        if let Some(&fid) = self.frame_idx.get(fname.as_str()) {
            return self.emit_frame_call(fid, &func, args);
        }
        // A non-framed recursive function reaching here means the recursion cycle
        // was missed by `build_frame_set` (it should have been framed) — the inline
        // path's `inline_stack` guard still catches it loud below.
        if self.inline_stack.iter().any(|n| n == &fname) {
            self.error(
                MsgCode::ElabUnsupported,
                &format!(
                    "recursive function `{fname}` (frame-call deferred; cycle: {} -> {fname})",
                    self.inline_stack.join(" -> ")
                ),
            );
            return self.placeholder_expr();
        }

        // Functions take INPUT formals only; an output/inout formal is illegal.
        if func
            .ports
            .iter()
            .any(|p| !matches!(p.dir, ast::PortDir::Input))
        {
            self.error(
                MsgCode::ElabUnsupported,
                &format!("function `{fname}` has output/inout formal (illegal)"),
            );
            return self.placeholder_expr();
        }
        let inputs: Vec<ast::TfPort> = func.ports.clone();
        if args.len() != inputs.len() {
            self.error(
                MsgCode::ElabUnsupported,
                &format!(
                    "function `{fname}`: {} args for {} formals",
                    args.len(),
                    inputs.len()
                ),
            );
            return self.placeholder_expr();
        }

        // (1) Lower each ACTUAL arg in the CALLER scope FIRST (before pushing the
        //     substitution frame) so args see the caller's nets and any OUTER
        //     substitution (nested inlining), never the function's own formals.
        let actual_ids: Vec<u32> = args.iter().map(|a| self.lower_expr(a)).collect();

        // (2) Reduce the straight-line body → an ExprId, formals bound to actuals.
        self.inline_stack.push(fname.clone());
        let result = self.reduce_function_body(&func, &inputs, &actual_ids);
        self.inline_stack.pop();
        result
    }

    // ── B1 frame-call: automatic/recursive function lowering ────────────────

    /// Emit an `Expr::Call` to a reserved frame `FuncId` (the call-site divert).
    /// Args are lowered in the CALLER scope (caller nets / outer subst). Returns a
    /// placeholder on an arity / out-formal violation (after the diagnostic).
    fn emit_frame_call(&mut self, fid: u32, func: &ast::FunctionDef, args: &[ast::Expr]) -> u32 {
        let fname = &func.name.name;
        if func
            .ports
            .iter()
            .any(|p| !matches!(p.dir, ast::PortDir::Input))
        {
            self.error(
                MsgCode::ElabUnsupported,
                &format!("function `{fname}` has an output/inout formal (illegal)"),
            );
            return self.placeholder_expr();
        }
        if args.len() != func.ports.len() {
            self.error(
                MsgCode::ElabUnsupported,
                &format!(
                    "function `{fname}`: {} args for {} formals",
                    args.len(),
                    func.ports.len()
                ),
            );
            return self.placeholder_expr();
        }
        let actual_ids: Vec<u32> = args.iter().map(|a| self.lower_expr(a)).collect();
        self.push_expr(ir::Expr::Call {
            func: fid,
            args: actual_ids,
        })
    }

    /// Reserve + lower every frame function of the CURRENT module instance. Runs
    /// at step 6.5: RESERVE all (sorted) so a call to a not-yet-lowered frame func
    /// resolves (breaks self + mutual recursion), then lower each body. No-op when
    /// the module declares no automatic/recursive functions.
    fn lower_frame_funcs(&mut self) {
        let frame_set = self.build_frame_set();
        if frame_set.is_empty() {
            return;
        }
        // RESERVE (sorted name order = deterministic net/FuncId allocation).
        for name in &frame_set {
            let func = self
                .func_table
                .get(name)
                .expect("frame func in table")
                .clone();
            self.reserve_frame_func(name, &func);
        }
        // LOWER each body (sorted) — every frame_idx is now reserved.
        for name in &frame_set {
            let func = self
                .func_table
                .get(name)
                .expect("frame func in table")
                .clone();
            let fid = self.frame_idx[name];
            self.lower_frame_func_body(name, &func, fid);
        }
    }

    /// The set of THIS module's functions needing a frame: every `automatic`
    /// function, plus every function on a recursion cycle (direct or mutual). A
    /// missed call edge is loud-safe (the function stays inline → `inline_stack`
    /// rejects), but the walk covers the common AST shapes.
    fn build_frame_set(&self) -> std::collections::BTreeSet<String> {
        let mut set: std::collections::BTreeSet<String> = std::collections::BTreeSet::new();
        for (name, f) in &self.func_table {
            // A function is framed when it is `automatic`, recursive (below), or its
            // body is NOT straight-line foldable (has control flow / a construct the
            // inline path rejects) — framing handles all three with one machine.
            if f.automatic || body_needs_frame(&f.body) {
                set.insert(name.clone());
            }
        }
        // call-graph edges restricted to known function names.
        let mut edges: BTreeMap<String, std::collections::BTreeSet<String>> = BTreeMap::new();
        for (name, f) in &self.func_table {
            let mut callees = std::collections::BTreeSet::new();
            collect_callee_stmt(&f.body, &mut callees);
            callees.retain(|c| self.func_table.contains_key(c));
            edges.insert(name.clone(), callees);
        }
        // f needs a frame iff f can reach f (direct or mutual recursion).
        for name in self.func_table.keys() {
            if reaches(name, name, &edges) {
                set.insert(name.clone());
            }
        }
        set
    }

    /// Allocate this frame function's nets (formals, return-var, body_decls — in
    /// that slot order) under a synthetic `$func$<name>` scope, push a placeholder
    /// `FuncDef` + the complete `FuncMeta`, and record the name→FuncId divert.
    fn reserve_frame_func(&mut self, name: &str, func: &ast::FunctionDef) {
        let fid = self.funcs.len() as u32;
        let base_net = self.nets.len() as u32;
        let n_params = func.ports.len() as u32;
        let (ret_width, ret_signed) = self.func_return_dims(func);
        let scope_seg = format!("$func${name}");
        let ret_name = name.to_string();
        self.with_scope(&scope_seg, |s| {
            // [0..n_params): input formals, port order.
            for p in &func.ports {
                let kind = p.net_or_var.unwrap_or(ast::NetVarKind::Reg);
                let (w, msb, lsb, signed) = s.range_to_dims(kind, p.range.as_ref(), p.signed);
                s.add_net(
                    &p.name.name,
                    ir::NetVar {
                        kind: map_net_kind_or_wire(kind),
                        width: w,
                        msb,
                        lsb,
                        signed,
                        array_len: 1,
                        dir: ir::PortDir::Internal,
                        init: default_init(kind, w),
                    },
                );
            }
            // [n_params]: the function-named RETURN var (declared range/sign).
            s.add_net(
                &ret_name,
                ir::NetVar {
                    kind: if ret_width == 32 && ret_signed {
                        ir::NetKind::Integer
                    } else {
                        ir::NetKind::Reg
                    },
                    width: ret_width,
                    msb: ret_width.saturating_sub(1),
                    lsb: 0,
                    signed: ret_signed,
                    array_len: 1,
                    dir: ir::PortDir::Internal,
                    init: default_init(ast::NetVarKind::Reg, ret_width),
                },
            );
            // [n_params+1..]: body_decls, source order (scalars only — a frame-
            // local array/dyn/string is outside the B1 cut and lowers as a 1-elem
            // net here; the body validator rejects any select/array lvalue use).
            for d in &func.body_decls {
                for decl in &d.names {
                    let (w, msb, lsb, signed) = s.range_to_dims(d.kind, d.range.as_ref(), d.signed);
                    s.add_net(
                        &decl.name.name,
                        ir::NetVar {
                            kind: map_net_kind_or_wire(d.kind),
                            width: w,
                            msb,
                            lsb,
                            signed,
                            array_len: 1,
                            dir: ir::PortDir::Internal,
                            init: default_init(d.kind, w),
                        },
                    );
                }
            }
        });
        let locals_len = self.nets.len() as u32 - base_net;
        self.frame_idx.insert(name.to_string(), fid);
        self.funcs.push(ir::FuncDef {
            entry: 0, // filled by lower_frame_func_body
            n_params,
            locals_len,
            is_task: false,
        });
        self.func_metas.push(FuncMeta {
            base_net,
            n_params,
            return_slot: n_params, // convention: return var right after the formals
            locals_len,
            is_automatic: func.automatic,
            ret_width,
            ret_signed,
        });
    }

    /// Lower a frame function's body into the GLOBAL `func_blocks` arena: build a
    /// process-local CFG (reusing `lower_stmt`), append it with every `Goto`/
    /// `Branch` target rebased by `+base`, set `FuncDef.entry`, then validate.
    fn lower_frame_func_body(&mut self, name: &str, func: &ast::FunctionDef, fid: u32) {
        let scope_seg = format!("$func${name}");
        let base = self.func_blocks.len() as u32;
        let (body, entry) = self.with_scope(&scope_seg, |s| {
            let mut b = ProcessBuilder::new();
            s.lower_stmt(&mut b, &func.body);
            b.finish()
        });
        for mut blk in body {
            rebase_terminator(&mut blk.term, base);
            self.func_blocks.push(blk);
        }
        self.funcs[fid as usize].entry = base + entry;
        let m = self.func_metas[fid as usize];
        self.validate_frame_body(name, base, m.base_net, m.locals_len);
    }

    /// Loud-reject any construct unsupported in a B1 frame function body: a non-
    /// `Goto`/`Branch`/`Return` terminator (timing/suspend/fork), a non-blocking-
    /// assign statement (`$display`/NBA/force/release), or a blocking-assign lvalue
    /// that is not a WHOLE frame-local net (a module-net write or a part/array
    /// select). One diagnostic per offending function (it fails elaboration).
    fn validate_frame_body(&mut self, name: &str, block_base: u32, net_base: u32, locals_len: u32) {
        let (lo, hi) = (net_base, net_base + locals_len);
        let mut why: Option<&'static str> = None;
        for bi in block_base as usize..self.func_blocks.len() {
            let blk = &self.func_blocks[bi];
            if !matches!(
                blk.term,
                ir::Terminator::Goto { .. }
                    | ir::Terminator::Branch { .. }
                    | ir::Terminator::Return
            ) {
                why = Some("a timing/suspend/fork control (#delay, @, wait, fork)");
            }
            for &sid in &blk.stmts {
                match &self.stmts[sid as usize] {
                    ir::Stmt::BlockingAssign { lhs, .. } => {
                        for c in &lhs.chunks {
                            let whole = c.offset.is_none() && c.word.is_none() && c.width.is_none();
                            let in_frame = c.net >= lo && c.net < hi;
                            if !whole {
                                why = Some("a part-select / array-element assignment");
                            } else if !in_frame {
                                why = Some("an assignment to a net outside the function");
                            }
                        }
                    }
                    _ => why = Some("a $systask / nonblocking / force / release statement"),
                }
            }
        }
        if let Some(w) = why {
            self.error(
                MsgCode::ElabUnsupported,
                &format!(
                    "frame function `{name}` body uses {w}, which is outside the B1 \
                     frame-call subset (only blocking assigns to its own locals, \
                     plus if/else/case/loops, are supported)"
                ),
            );
        }
    }

    /// Declared return self-width + signedness of a function (`function [15:0]`,
    /// `function integer`, `function signed [7:0]`, bare `function`).
    fn func_return_dims(&mut self, func: &ast::FunctionDef) -> (u32, bool) {
        let kind = match func.ret_type {
            ast::ParamType::Integer => ast::NetVarKind::Integer,
            ast::ParamType::Real => ast::NetVarKind::Real,
            ast::ParamType::Realtime => ast::NetVarKind::Realtime,
            ast::ParamType::Time => ast::NetVarKind::Time,
            ast::ParamType::Implicit => ast::NetVarKind::Reg,
        };
        let (w, _msb, _lsb, signed) = self.range_to_dims(kind, func.range.as_ref(), func.signed);
        (w, signed)
    }

    /// Fold a straight-line combinational function body to one return ExprId.
    /// Supported shapes: a single `f = <expr>;`, or a `begin … end` of blocking
    /// assigns to locals (SSA-by-substitution) ending in the return-var assign.
    /// Anything with control flow / nonblocking / task call ⇒ E-ELAB-UNSUPPORTED.
    fn reduce_function_body(
        &mut self,
        func: &ast::FunctionDef,
        inputs: &[ast::TfPort],
        actual_ids: &[u32],
    ) -> u32 {
        let frame_base = self.subst.len();
        // (a) bind each input formal NAME → actual ExprId.
        for (p, &eid) in inputs.iter().zip(actual_ids) {
            self.subst.push((p.name.name.clone(), eid));
        }
        // (b) walk the straight-line body, recording the return-var assignment.
        let fname = func.name.name.clone();
        let mut ret: Option<u32> = None;
        let ok = self.fold_straight_line(&func.body, &fname, &mut ret);
        // restore the substitution stack to its pre-call depth.
        self.subst.truncate(frame_base);

        if !ok {
            self.error(
                MsgCode::ElabUnsupported,
                &format!(
                    "function `{fname}` body is not reducible to an expression (control flow)"
                ),
            );
            return self.placeholder_expr();
        }
        match ret {
            Some(eid) => eid,
            None => {
                // body never assigned the return var → X (the function's default).
                self.warn(&format!(
                    "function `{fname}` never assigns its return value; X approximated"
                ));
                self.placeholder_expr()
            }
        }
    }

    /// Fold a straight-line function body. Returns false (caller emits the error)
    /// on the first non-foldable construct. Each `local = expr;` pushes a
    /// substitution binding (SSA-by-substitution); `fname = expr;` records the
    /// return ExprId. Lowering happens with the CURRENT substitution scope active.
    fn fold_straight_line(&mut self, s: &ast::Stmt, fname: &str, ret: &mut Option<u32>) -> bool {
        match s {
            ast::Stmt::Null(_) => true,
            ast::Stmt::Block { stmts, .. } => {
                // begin-end local decls need NO nets: each local lives only as a
                // substitution binding (combinational). Fold each stmt in order.
                stmts
                    .iter()
                    .all(|st| self.fold_straight_line(st, fname, ret))
            }
            ast::Stmt::Blocking {
                lhs, delay, rhs, ..
            } => {
                if delay.is_some() {
                    self.warn("intra-assignment delay in inlined function dropped");
                }
                // LHS must be a bare single-segment Ident (a local var or func name).
                let ast::Lvalue::Ident(p) = lhs else {
                    return false;
                };
                if p.segments.len() != 1 {
                    return false;
                }
                let target = p.segments[0].name.clone();
                // lower the RHS with the CURRENT substitution scope in effect.
                let rhs_id = self.lower_expr(rhs);
                if target == fname {
                    *ret = Some(rhs_id); // return assignment
                } else {
                    self.subst.push((target, rhs_id)); // local: innermost-wins binding
                }
                true
            }
            // if/case/loop/nonblocking/task-call/etc. ⇒ not reducible to one expr.
            _ => false,
        }
    }

    /// Inline a user-task call into the current process: the body statements join
    /// the caller's CFG via the normal `lower_stmt` machinery (so a task with
    /// if/case/delay just works). INPUT formals substitute a read ExprId; OUTPUT/
    /// INOUT formals bind to the caller's net (reads + writes hit it directly).
    fn inline_task(&mut self, b: &mut ProcessBuilder, name: &ast::HierPath, args: &[ast::Expr]) {
        // v5 ⑥: `handle.method(args);` — a 2-segment task enable whose head is
        // a dyn handle is a METHOD statement, not a hierarchical call.
        if name.segments.len() == 2 {
            if let Some((net, kind)) = self.dyn_handle(&name.segments[0].name) {
                self.lower_dyn_method_stmt(b, net, kind, &name.segments[1].name, args);
                return;
            }
            // v7 P2-C: `s.putc(i, c);`.
            if let Some(net) = self.string_handle(&name.segments[0].name) {
                self.lower_string_method_stmt(b, net, &name.segments[1].name, args);
                return;
            }
        }
        if name.segments.len() != 1 {
            self.error(
                MsgCode::ElabUnsupported,
                "hierarchical task call (deferred)",
            );
            return;
        }
        let tname = name.segments[0].name.clone();
        let task = match self.task_table.get(tname.as_str()) {
            Some(t) => t.clone(),
            None => {
                self.error(
                    MsgCode::ElabUnresolvedName,
                    &format!("call to undeclared task `{tname}`"),
                );
                return;
            }
        };
        if task.automatic {
            self.error(
                MsgCode::ElabUnsupported,
                &format!("automatic task `{tname}` (frame-call deferred)"),
            );
            return;
        }
        if self.inline_stack.iter().any(|n| n == &tname) {
            self.error(
                MsgCode::ElabUnsupported,
                &format!("recursive task `{tname}` (frame-call deferred)"),
            );
            return;
        }
        if args.len() != task.ports.len() {
            self.error(
                MsgCode::ElabUnsupported,
                &format!(
                    "task `{tname}`: {} args for {} formals",
                    args.len(),
                    task.ports.len()
                ),
            );
            return;
        }

        // Bind formals, lowering actuals in the CALLER scope, BEFORE inlining.
        let subst_base = self.subst.len();
        let out_base = self.out_subst.len();
        for (p, a) in task.ports.iter().zip(args) {
            match p.dir {
                ast::PortDir::Input => {
                    let eid = self.lower_expr(a); // caller-scope read
                    self.subst.push((p.name.name.clone(), eid));
                }
                ast::PortDir::Output | ast::PortDir::Inout => {
                    // v1: actual must be a bare net Ident → bind formal name → its
                    // NetId so body reads/writes of the formal hit the caller net.
                    match &a.kind {
                        ast::ExprKind::Ident(path) if path.segments.len() == 1 => {
                            let net = self.resolve_net(path);
                            self.out_subst.push((p.name.name.clone(), net));
                        }
                        _ => {
                            self.error(
                                MsgCode::ElabUnsupported,
                                &format!(
                                    "task `{tname}` output/inout arg must be a simple net (v1)"
                                ),
                            );
                        }
                    }
                }
            }
        }

        // INLINE the body into the current process via normal stmt lowering.
        self.inline_stack.push(tname.clone());
        self.lower_stmt(b, &task.body);
        self.inline_stack.pop();

        // pop our frames so sibling/outer code is unaffected.
        self.subst.truncate(subst_base);
        self.out_subst.truncate(out_base);
    }

    // ── const + expr helpers (single arena append points) ──────────
    /// THE deterministic expr append point.
    #[inline]
    fn push_expr(&mut self, e: ir::Expr) -> u32 {
        let id = self.exprs.len() as u32;
        self.exprs.push(e);
        id
    }

    /// Dedup-or-append a const; returns its ConstId. The dedup map is lookup-only
    /// and never reorders the arena (first-seen wins, driven by traversal order).
    fn intern_const(&mut self, cv: ir::ConstVal) -> u32 {
        let key: ConstKey = (
            cv.width,
            cv.signed,
            match cv.repr {
                ir::ConstRepr::Numeric => 0,
                ir::ConstRepr::StrUtf8 => 1,
                ir::ConstRepr::Real => 2,
            },
            cv.bits.val.clone(),
            cv.bits.unk.clone(),
        );
        if let Some(&id) = self.const_dedup.get(&key) {
            return id;
        }
        let id = self.consts.len() as u32;
        self.consts.push(cv);
        self.const_dedup.insert(key, id);
        id
    }

    /// Static real-ness of an already-lowered ExprId (for §6.2 illegality gates
    /// and the §4.1a format-string check). Real-typed iff it is a real const, a
    /// real net read, a `+`/`-` of a real, a `+ - * /` with a real operand, a
    /// ternary with a real branch, or a real-producing system function.
    fn expr_is_real(&self, eid: u32) -> bool {
        match self.exprs.get(eid as usize) {
            Some(ir::Expr::Const { val }) => self
                .consts
                .get(*val as usize)
                .is_some_and(|c| matches!(c.repr, ir::ConstRepr::Real)),
            Some(ir::Expr::Signal { net, .. }) => self
                .nets
                .get(*net as usize)
                .is_some_and(|n| matches!(n.kind, ir::NetKind::Real)),
            Some(ir::Expr::Unary { op, operand }) => {
                matches!(op, ir::UnOp::Plus | ir::UnOp::Minus) && self.expr_is_real(*operand)
            }
            Some(ir::Expr::Binary { op, lhs, rhs }) => {
                matches!(
                    op,
                    ir::BinOp::Add | ir::BinOp::Sub | ir::BinOp::Mul | ir::BinOp::Div
                ) && (self.expr_is_real(*lhs) || self.expr_is_real(*rhs))
            }
            Some(ir::Expr::Ternary { then_e, else_e, .. }) => {
                self.expr_is_real(*then_e) || self.expr_is_real(*else_e)
            }
            Some(ir::Expr::SysFunc { which, .. }) => matches!(
                which,
                ir::SysFuncId::Realtime | ir::SysFuncId::Itor | ir::SysFuncId::BitsToReal
            ),
            _ => false,
        }
    }

    /// §4.1a STATIC gate: walk the literal format string, pair each conversion
    /// specifier with its positional value-arg, and reject a `%b/%h/%o/%x` (radix)
    /// specifier on a real-typed argument. `%f/%g/%e/%d` on a real are legal.
    fn check_format_real_radix(&mut self, fmt: &str, arg_ids: &[u32]) {
        let mut chars = fmt.chars().peekable();
        let mut argi = 0usize;
        while let Some(c) = chars.next() {
            if c != '%' {
                continue;
            }
            // skip width/precision modifiers (digits and a single '.').
            while let Some(&d) = chars.peek() {
                if d.is_ascii_digit() || d == '.' {
                    chars.next();
                } else {
                    break;
                }
            }
            let spec = match chars.next() {
                Some(s) => s,
                None => break,
            };
            match spec {
                '%' | 'm' => {} // literal '%' / scope name — consume no arg
                'b' | 'B' | 'h' | 'H' | 'x' | 'X' | 'o' | 'O' => {
                    if arg_ids
                        .get(argi)
                        .copied()
                        .is_some_and(|e| self.expr_is_real(e))
                    {
                        self.error(
                            MsgCode::ElabUnsupported,
                            "binary/hex/octal format not defined on a real argument",
                        );
                    }
                    argi += 1;
                }
                // every other conversion consumes one positional argument.
                _ => {
                    argi += 1;
                }
            }
        }
    }

    fn lower_int_literal(&mut self, kind: ast::IntLitKind, raw: &str) -> u32 {
        let cv = match parse_int_literal(raw, kind) {
            Some(cv) => cv,
            None => {
                // Truncate the echoed lexeme: a digit-cap-rejected decimal can be
                // hundreds of thousands of chars, and echoing it verbatim would be
                // unbounded stderr (a DoS in its own right).
                let shown: String = if raw.chars().count() > 64 {
                    format!(
                        "{}…({} chars)",
                        raw.chars().take(64).collect::<String>(),
                        raw.len()
                    )
                } else {
                    raw.to_string()
                };
                self.error(
                    MsgCode::ElabUnsupported,
                    &format!("malformed integer literal `{shown}`"),
                );
                make_const_u32(0, 32)
            }
        };
        // P0-10: an unsized literal grows to hold its value (IEEE §3.5.1); cap the
        // result at MAX_NET_WIDTH like a declared net so a pathological wide
        // literal is rejected loud instead of interning a giant const (this also
        // makes the `bits.len() as u32` width casts in literal.rs unreachable past
        // u32). A sized over-cap literal is rejected for the same reason a
        // same-width net is.
        if cv.width as u64 > MAX_NET_WIDTH {
            self.error(
                MsgCode::ElabUnsupported,
                &format!(
                    "integer literal width {} exceeds the v1 cap ({MAX_NET_WIDTH})",
                    cv.width
                ),
            );
            return self.intern_const(make_const_u32(0, 32));
        }
        self.intern_const(cv)
    }

    /// Append a `Const` expr of literal `n` (width `w`); returns its ExprId.
    fn const_u32_expr(&mut self, n: u32, w: u32) -> u32 {
        let cid = self.intern_const(make_const_u32(n, w));
        self.push_expr(ir::Expr::Const { val: cid })
    }

    /// Lower an i64-domain param/genvar VALUE to a Const expr (P0-6). The
    /// legacy `0..=u32::MAX` range keeps the exact old shape (unsigned 32-bit,
    /// byte-identical golden bytes for every pre-existing design); a negative
    /// value in i32 range becomes a 32-bit SIGNED const (so `%0d` prints `-4`,
    /// iverilog parity); anything wider binds as a 64-bit const.
    fn const_param_expr(&mut self, v: i64) -> u32 {
        if let Ok(u) = u32::try_from(v) {
            return self.const_u32_expr(u, 32);
        }
        let cv = if i32::try_from(v).is_ok() {
            make_const_i64(v, 32, true)
        } else {
            make_const_i64(v, 64, v < 0)
        };
        let cid = self.intern_const(cv);
        self.push_expr(ir::Expr::Const { val: cid })
    }

    /// Normalize a select offset (a SOURCE bit index) into an internal-bit position
    /// for a net declared `[msb:lsb]`: descending (`msb≥lsb`) → `idx − lsb`; ascending
    /// (`msb<lsb`) → `lsb − idx`. A plain `[N:0]` net (lsb 0, descending) returns the
    /// raw offset unchanged so the long-standing golden IR is byte-for-byte preserved.
    /// A POISON/out-of-range net id (error recovery) is a no-op.
    fn norm_offset_for_net(&mut self, net: u32, raw_off: u32) -> u32 {
        let Some((msb, lsb)) = self.nets.get(net as usize).map(|nv| (nv.msb, nv.lsb)) else {
            return raw_off;
        };
        if msb >= lsb {
            if lsb == 0 {
                return raw_off; // `[N:0]` — raw index is already internal
            }
            let lsb_c = self.const_u32_expr(lsb, 32);
            self.push_expr(ir::Expr::Binary {
                op: ir::BinOp::Sub,
                lhs: raw_off,
                rhs: lsb_c,
            })
        } else {
            // ascending `[lo:hi]`: the largest source index (`lsb`) is internal bit 0.
            let lsb_c = self.const_u32_expr(lsb, 32);
            self.push_expr(ir::Expr::Binary {
                op: ir::BinOp::Sub,
                lhs: lsb_c,
                rhs: raw_off,
            })
        }
    }

    /// If `base` is a direct single-segment net `Ident`, normalize the offset by its
    /// declared range; otherwise (a computed/concat base, range `[?:0]`) leave it raw.
    fn norm_offset_if_net(&mut self, base: &ast::Expr, raw_off: u32) -> u32 {
        if let ast::ExprKind::Ident(path) = &base.kind {
            if path.segments.len() == 1 {
                if let Some(net) = self.lookup_net_scoped(&path.segments[0].name) {
                    return self.norm_offset_for_net(net, raw_off);
                }
            }
        }
        raw_off
    }

    /// Placeholder used after an error so downstream edges stay valid.
    fn placeholder_expr(&mut self) -> u32 {
        let cid = self.intern_const(make_const_u32(0, 1));
        self.push_expr(ir::Expr::Const { val: cid })
    }

    /// width = (msb - lsb) + 1 as an arena expr tree (no const-fold in v1).
    /// `msb`/`lsb` are the already-lowered ExprIds of the select bounds.
    ///
    /// GUARD (LOWERING verdict MINOR): if both bounds const-fold and
    /// `msb_const < lsb_const` — i.e. a part-select on a little-endian/ascending
    /// `[0:N]` net — the `Sub` would underflow as an unsigned arena op. v1 only
    /// supports descending `[N:0]` part-selects, so we emit `ElabUnsupported` and
    /// still synthesize the (well-formed but inert) width tree to keep the arena
    /// valid. The original-AST bounds are passed in only for the const check.
    fn width_from_msb_lsb_checked(
        &mut self,
        msb_ast: &ast::Expr,
        lsb_ast: &ast::Expr,
        msb_id: u32,
        lsb_id: u32,
    ) -> u32 {
        if let (Some(m), Some(l)) = (const_eval_u32(msb_ast), const_eval_u32(lsb_ast)) {
            if m < l {
                self.error(
                    MsgCode::ElabUnsupported,
                    "ascending/little-endian part-select [lsb:msb] not supported (v1: [msb:lsb])",
                );
            }
        }
        let diff = self.push_expr(ir::Expr::Binary {
            op: ir::BinOp::Sub,
            lhs: msb_id,
            rhs: lsb_id,
        });
        let one = self.const_u32_expr(1, 32);
        self.push_expr(ir::Expr::Binary {
            op: ir::BinOp::Add,
            lhs: diff,
            rhs: one,
        })
    }

    // ── v5 ⑥: dynamic-storage front-end (decl/index/method lowering) ─────────

    /// The handle NetKind when `dims` declares dynamic storage.
    fn dyn_dim_kind(&self, dims: &[ast::Dim]) -> Option<ir::NetKind> {
        dims.iter().find_map(|d| match d {
            ast::Dim::Dyn => Some(ir::NetKind::DynArray),
            ast::Dim::Queue(_) => Some(ir::NetKind::Queue),
            ast::Dim::Assoc(ast::AssocKey::Str) => Some(ir::NetKind::AssocStr),
            ast::Dim::Assoc(_) => Some(ir::NetKind::Assoc),
            _ => None,
        })
    }

    /// `name` (single segment, current scope) as a dyn HANDLE net + its kind.
    fn dyn_handle(&self, name: &str) -> Option<(u32, ir::NetKind)> {
        let n = self.lookup_net_scoped(name)?;
        let k = self.nets.get(n as usize)?.kind;
        matches!(
            k,
            ir::NetKind::DynArray | ir::NetKind::Queue | ir::NetKind::Assoc | ir::NetKind::AssocStr
        )
        .then_some((n, k))
    }

    /// v7 P2-C: `name` (single segment, current scope) as a STRING net.
    fn string_handle(&self, name: &str) -> Option<u32> {
        let n = self.lookup_net_scoped(name)?;
        (self.nets.get(n as usize)?.kind == ir::NetKind::String).then_some(n)
    }

    /// v7 P2-C: does this AST expression denote a STRING-domain value?
    /// (a string variable read, or a string-producing method call). Literals
    /// stay packed — a string-vs-literal comparison routes via the string
    /// side. Conservative: anything else is not string-domain.
    fn expr_is_string_ast(&self, e: &ast::Expr) -> bool {
        match &e.kind {
            ast::ExprKind::Paren { inner } => self.expr_is_string_ast(inner),
            ast::ExprKind::Ident(p) => match p.segments.as_slice() {
                [seg] => {
                    // review F2: an inlined FORMAL bound to a string actual
                    // must keep its string-domain-ness — resolve through the
                    // subst (the bypass lowered `a < b` as a packed compare,
                    // non-lexicographic for unequal lengths).
                    if let Some(eid) = self.subst_lookup(&seg.name) {
                        return self.ir_expr_is_string(eid);
                    }
                    if let Some(net) = self.out_subst_lookup(&seg.name) {
                        return self.is_string_net(net);
                    }
                    self.lookup_scoped(&seg.name).is_none()
                        && self.string_handle(&seg.name).is_some()
                }
                _ => false,
            },
            ast::ExprKind::Call { name, .. } => {
                name.segments.len() == 2
                    && self.string_handle(&name.segments[0].name).is_some()
                    && matches!(
                        name.segments[1].name.as_str(),
                        "substr" | "toupper" | "tolower"
                    )
            }
            _ => false,
        }
    }

    /// v7 P2-C: is `net` a string variable?
    fn is_string_net(&self, net: u32) -> bool {
        self.nets.get(net as usize).map(|n| n.kind) == Some(ir::NetKind::String)
    }

    /// v7 P2-C: does an already-LOWERED expr denote a string-domain value?
    /// (subst-bound formals resolve here — review F2.)
    fn ir_expr_is_string(&self, eid: u32) -> bool {
        match self.exprs.get(eid as usize) {
            Some(ir::Expr::Signal { net, word: None }) => self.is_string_net(*net),
            Some(ir::Expr::SysFunc { which, .. }) => matches!(
                which,
                ir::SysFuncId::StrSubstr
                    | ir::SysFuncId::StrToUpper
                    | ir::SysFuncId::StrToLower
                    | ir::SysFuncId::Sformatf
            ),
            _ => false,
        }
    }

    /// v7 P2-C: method-call EXPRESSION on a string (`s.len()`, `s.substr(i,j)`,
    /// `s.toupper()`, `s.getc(i)`, `s.compare(t)`). `putc` is the statement
    /// mutator (`lower_string_method_stmt`); unknown methods are loud.
    fn lower_string_method_expr(&mut self, net: u32, method: &str, args: &[ast::Expr]) -> u32 {
        let handle = self.push_expr(ir::Expr::Signal { net, word: None });
        let arity_ok = |n: usize| args.len() == n;
        let which = match method {
            "len" if arity_ok(0) => ir::SysFuncId::StrLen,
            "getc" if arity_ok(1) => ir::SysFuncId::StrGetC,
            "substr" if arity_ok(2) => ir::SysFuncId::StrSubstr,
            "toupper" if arity_ok(0) => ir::SysFuncId::StrToUpper,
            "tolower" if arity_ok(0) => ir::SysFuncId::StrToLower,
            "compare" if arity_ok(1) => ir::SysFuncId::StrCmp,
            _ => {
                self.error(
                    MsgCode::ElabUnsupported,
                    &format!(
                        "string method `{method}` (with this arity) is outside \
                         the v7 scope (len/getc/substr/toupper/tolower/compare/putc)"
                    ),
                );
                return self.placeholder_expr();
            }
        };
        let mut ids = vec![handle];
        ids.extend(args.iter().map(|a| self.lower_expr(a)));
        self.push_expr(ir::Expr::SysFunc { which, args: ids })
    }

    /// v7 P2-C: method-call STATEMENT on a string — `s.putc(i, c);`.
    fn lower_string_method_stmt(
        &mut self,
        b: &mut ProcessBuilder,
        net: u32,
        method: &str,
        args: &[ast::Expr],
    ) {
        if method != "putc" || args.len() != 2 {
            self.error(
                MsgCode::ElabUnsupported,
                &format!("string method statement `{method}` is outside the v7 scope (putc)"),
            );
            return;
        }
        let handle = self.push_expr(ir::Expr::Signal { net, word: None });
        let mut ids = vec![handle];
        ids.extend(args.iter().map(|a| self.lower_expr(a)));
        let sid = self.push_stmt(ir::Stmt::SysTask {
            which: ir::SysTaskId::StrPutC,
            fmt: None,
            args: ids,
        });
        b.push_stmt_id(sid);
    }

    /// Is `net` (already resolved) a dyn handle? Whole-handle value surfaces
    /// (reads, whole assigns, event controls) are loud-rejected on these.
    fn is_dyn_handle_net(&self, net: u32) -> bool {
        matches!(
            self.nets.get(net as usize).map(|n| n.kind),
            Some(
                ir::NetKind::DynArray
                    | ir::NetKind::Queue
                    | ir::NetKind::Assoc
                    | ir::NetKind::AssocStr
            )
        )
    }

    /// Lower a dyn ELEMENT index. For a QUEUE the bare `$` substitutes
    /// `size(handle)-1` (IEEE §7.10.1: `q[$]` = the last element), scoped to
    /// THIS index by save/restore so nested selects bind `$` to their own
    /// queue. Assoc keys lower plain — the engine's signed-i64 key domain
    /// takes the expression's own width/signedness.
    fn lower_dyn_index(&mut self, net: u32, kind: ir::NetKind, index: &ast::Expr) -> u32 {
        if kind != ir::NetKind::Queue {
            return self.lower_expr(index);
        }
        let handle = self.push_expr(ir::Expr::Signal { net, word: None });
        let size = self.push_expr(ir::Expr::SysFunc {
            which: ir::SysFuncId::DynSize,
            args: vec![handle],
        });
        let one = self.const_u32_expr(1, 32);
        let last = self.push_expr(ir::Expr::Binary {
            op: ir::BinOp::Sub,
            lhs: size,
            rhs: one,
        });
        let saved = self.dollar_subst.replace(last);
        let idx = self.lower_expr(index);
        self.dollar_subst = saved;
        idx
    }

    /// Read-side `handle[idx]` interception — `None` for non-handles so the
    /// caller's array/packed/scalar logic runs unchanged.
    fn dyn_select_read(&mut self, base: &ast::Expr, index: &ast::Expr) -> Option<u32> {
        let ast::ExprKind::Ident(p) = &base.kind else {
            return None;
        };
        if p.segments.len() != 1 {
            return None;
        }
        let (net, kind) = self.dyn_handle(&p.segments[0].name)?;
        let word = self.lower_dyn_index(net, kind, index);
        Some(self.push_expr(ir::Expr::Signal {
            net,
            word: Some(word),
        }))
    }

    /// Method-call EXPRESSION on a dyn handle (`d.size()`, `a.exists(k)`…).
    /// Pops reaching HERE are NOT the direct rhs of a blocking assign (that
    /// shape is intercepted in `dyn_blocking_special`) — loud, per the engine
    /// contract (`StmtEffect::QPop` is statement-level).
    fn lower_dyn_method_expr(
        &mut self,
        net: u32,
        kind: ir::NetKind,
        method: &str,
        args: &[ast::Expr],
    ) -> u32 {
        use ir::NetKind as K;
        let handle = self.push_expr(ir::Expr::Signal { net, word: None });
        match (method, kind) {
            ("size", _) | ("num", K::Assoc | K::AssocStr) => {
                if !args.is_empty() {
                    self.error(MsgCode::ElabUnsupported, "size()/num() take no arguments");
                }
                let which = if method == "num" {
                    ir::SysFuncId::AssocNum
                } else {
                    ir::SysFuncId::DynSize
                };
                self.push_expr(ir::Expr::SysFunc {
                    which,
                    args: vec![handle],
                })
            }
            ("exists", K::Assoc | K::AssocStr) => {
                let Some(k) = args.first() else {
                    self.error(MsgCode::ElabUnsupported, "exists() takes the key argument");
                    return self.placeholder_expr();
                };
                let key = self.lower_expr(k);
                self.push_expr(ir::Expr::SysFunc {
                    which: ir::SysFuncId::AssocExists,
                    args: vec![handle, key],
                })
            }
            ("pop_back" | "pop_front", K::Queue) => {
                self.error(
                    MsgCode::ElabUnsupported,
                    "a queue pop is only supported as the DIRECT rhs of a blocking assignment (`x = q.pop_back();`)",
                );
                self.placeholder_expr()
            }
            // v6: the iteration methods WRITE their ref key argument — same
            // direct-rhs-only contract as the pops.
            ("first" | "next" | "last" | "prev", _) => {
                self.error(
                    MsgCode::ElabUnsupported,
                    "first/next/last/prev are only supported as the DIRECT rhs of a blocking assignment (`st = a.first(k);`)",
                );
                self.placeholder_expr()
            }
            ("push_back" | "push_front" | "delete" | "insert", _) => {
                self.error(
                    MsgCode::ElabUnsupported,
                    "statement method used in expression position",
                );
                self.placeholder_expr()
            }
            _ => {
                self.error(
                    MsgCode::ElabUnsupported,
                    &format!("unknown or kind-mismatched dynamic-storage method `.{method}()`"),
                );
                self.placeholder_expr()
            }
        }
    }

    /// Method-call STATEMENT on a dyn handle (`q.push_back(v);`, `a.delete(k);`).
    fn lower_dyn_method_stmt(
        &mut self,
        b: &mut ProcessBuilder,
        net: u32,
        kind: ir::NetKind,
        method: &str,
        args: &[ast::Expr],
    ) {
        use ir::NetKind as K;
        let handle = self.push_expr(ir::Expr::Signal { net, word: None });
        let task = match (method, kind, args.len()) {
            ("push_back", K::Queue, 1) | ("push_front", K::Queue, 1) => {
                let v = self.lower_expr(&args[0]);
                let which = if method == "push_back" {
                    ir::SysTaskId::QPushBack
                } else {
                    ir::SysTaskId::QPushFront
                };
                ir::Stmt::SysTask {
                    which,
                    fmt: None,
                    args: vec![handle, v],
                }
            }
            ("delete", _, 0) => ir::Stmt::SysTask {
                which: ir::SysTaskId::DynDelete,
                fmt: None,
                args: vec![handle],
            },
            ("delete", K::Assoc | K::AssocStr, 1) => {
                let k = self.lower_expr(&args[0]);
                ir::Stmt::SysTask {
                    which: ir::SysTaskId::AssocDeleteKey,
                    fmt: None,
                    args: vec![handle, k],
                }
            }
            // v6: queue positional delete(i) — IEEE §7.10.2.3 (OOB/X index =
            // engine warn + skip).
            ("delete", K::Queue, 1) => {
                let i = self.lower_expr(&args[0]);
                ir::Stmt::SysTask {
                    which: ir::SysTaskId::QDeleteIdx,
                    fmt: None,
                    args: vec![handle, i],
                }
            }
            ("delete", _, 1) => {
                self.error(
                    MsgCode::ElabUnsupported,
                    "indexed delete(i) is a queue/assoc method (a dyn array only supports delete())",
                );
                return;
            }
            // v6: queue positional insert(i, v) — IEEE §7.10.2.2 (i == size
            // appends; OOB/X index = engine warn + no-op).
            ("insert", K::Queue, 2) => {
                let i = self.lower_expr(&args[0]);
                let v = self.lower_expr(&args[1]);
                ir::Stmt::SysTask {
                    which: ir::SysTaskId::QInsert,
                    fmt: None,
                    args: vec![handle, i, v],
                }
            }
            ("insert", K::Queue, _) => {
                self.error(
                    MsgCode::ElabUnsupported,
                    "insert() takes exactly (index, value)",
                );
                return;
            }
            ("pop_back" | "pop_front", K::Queue, _) => {
                self.error(
                    MsgCode::ElabUnsupported,
                    "a queue pop result must be assigned (`x = q.pop_back();`)",
                );
                return;
            }
            ("size" | "num" | "exists", _, _) => {
                self.error(
                    MsgCode::ElabUnsupported,
                    "value-returning method used as a statement",
                );
                return;
            }
            // v6: an iteration call whose status is discarded — loud (the
            // result drives the walk; dropping it is almost surely a bug).
            ("first" | "next" | "last" | "prev", _, _) => {
                self.error(
                    MsgCode::ElabUnsupported,
                    "first/next/last/prev results must be assigned (`st = a.first(k);`)",
                );
                return;
            }
            _ => {
                self.error(
                    MsgCode::ElabUnsupported,
                    &format!("unknown or kind-mismatched dynamic-storage method `.{method}()`"),
                );
                return;
            }
        };
        let sid = self.push_stmt(task);
        b.push_stmt_id(sid);
    }

    /// `d = new[n] [(src)]` and `x = q.pop_*()` — the two BLOCKING-assign
    /// special forms (v5 ⑥). True ⇒ fully lowered here.
    fn dyn_blocking_special(
        &mut self,
        b: &mut ProcessBuilder,
        lhs: &ast::Lvalue,
        delay: Option<&ast::Delay>,
        rhs: &ast::Expr,
    ) -> bool {
        match &rhs.kind {
            ast::ExprKind::New { size, src } => {
                // V2005 compat: a net actually named `new` → not the
                // allocation form; the plain path re-lowers it as a read.
                if self.lookup_net_scoped("new").is_some() {
                    return false;
                }
                let handle = match lhs {
                    ast::Lvalue::Ident(p) if p.segments.len() == 1 => {
                        self.dyn_handle(&p.segments[0].name)
                    }
                    _ => None,
                };
                let Some((net, ir::NetKind::DynArray)) = handle else {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "`new[n]` assigns only to a dynamic-ARRAY handle (`integer d[]; d = new[n];`)",
                    );
                    return true;
                };
                if delay.is_some() {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "a delayed `new[]` assignment is outside the MVP",
                    );
                    return true;
                }
                let h = self.push_expr(ir::Expr::Signal { net, word: None });
                let n_eid = self.lower_expr(size);
                let mut args = vec![h, n_eid];
                if let Some(s) = src {
                    let src_handle = match &s.kind {
                        ast::ExprKind::Ident(p) if p.segments.len() == 1 => {
                            self.dyn_handle(&p.segments[0].name)
                        }
                        _ => None,
                    };
                    let Some((src_net, ir::NetKind::DynArray)) = src_handle else {
                        self.error(
                            MsgCode::ElabUnsupported,
                            "`new[n](src)` copy source must be a dynamic-array handle",
                        );
                        return true;
                    };
                    args.push(self.push_expr(ir::Expr::Signal {
                        net: src_net,
                        word: None,
                    }));
                }
                let sid = self.push_stmt(ir::Stmt::SysTask {
                    which: ir::SysTaskId::DynNew,
                    fmt: None,
                    args,
                });
                b.push_stmt_id(sid);
                true
            }
            ast::ExprKind::Call { name, args } if name.segments.len() == 2 => {
                let Some((net, kind)) = self.dyn_handle(&name.segments[0].name) else {
                    return false;
                };
                let m = name.segments[1].name.as_str();
                // v6: iteration methods — `st = h.first(k);` (ref key arg).
                if matches!(m, "first" | "next" | "last" | "prev") {
                    return self.lower_iter_special(b, lhs, delay, net, kind, m, args);
                }
                if m != "pop_back" && m != "pop_front" {
                    return false; // size()/exists() etc. ride the normal expr path
                }
                if kind != ir::NetKind::Queue {
                    return false; // normal expr path louds the kind mismatch
                }
                if delay.is_some() {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "a delayed queue-pop assignment is outside the MVP",
                    );
                    return true;
                }
                if !args.is_empty() {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "pop_back()/pop_front() take no arguments",
                    );
                    return true;
                }
                let handle = self.push_expr(ir::Expr::Signal { net, word: None });
                let pop = self.push_expr(ir::Expr::SysFunc {
                    which: if m == "pop_front" {
                        ir::SysFuncId::QPopFront
                    } else {
                        ir::SysFuncId::QPopBack
                    },
                    args: vec![handle],
                });
                let lv = self.lower_lvalue(lhs);
                self.check_lvalue_kind(&lv, true);
                let sid = self.push_stmt(ir::Stmt::BlockingAssign { lhs: lv, rhs: pop });
                b.push_stmt_id(sid);
                true
            }
            _ => false,
        }
    }

    /// v6: `st = h.first(k);` / next/last/prev — the iteration special form
    /// (the third BLOCKING-assign special). The key is a REF argument: it must
    /// be a plain whole VARIABLE; the engine writes it on a hit. On dyn/queue
    /// handles the dense walk is an INTERNAL desugar target only — gated to
    /// the synthetic `__foreach_*` index so the user surface stays assoc-only
    /// (IEEE defines first/next on associative arrays alone).
    #[allow(clippy::too_many_arguments)]
    fn lower_iter_special(
        &mut self,
        b: &mut ProcessBuilder,
        lhs: &ast::Lvalue,
        delay: Option<&ast::Delay>,
        net: u32,
        kind: ir::NetKind,
        method: &str,
        args: &[ast::Expr],
    ) -> bool {
        if delay.is_some() {
            self.error(
                MsgCode::ElabUnsupported,
                "a delayed iteration assignment is outside the MVP",
            );
            return true;
        }
        if args.len() != 1 {
            self.error(
                MsgCode::ElabUnsupported,
                "first/next/last/prev take exactly the key variable",
            );
            return true;
        }
        let key_net = match &args[0].kind {
            ast::ExprKind::Ident(p) if p.segments.len() == 1 => {
                self.lookup_net_scoped(&p.segments[0].name)
            }
            _ => None,
        };
        let Some(knet) = key_net else {
            self.error(
                MsgCode::ElabUnsupported,
                "the iteration key must be a plain variable (`st = a.first(k);`)",
            );
            return true;
        };
        let kkind = self.nets.get(knet as usize).map(|n| n.kind);
        if !matches!(
            kkind,
            Some(ir::NetKind::Reg | ir::NetKind::Logic | ir::NetKind::Integer)
        ) {
            self.error(
                MsgCode::ElabUnsupported,
                "the iteration key must be an integral VARIABLE (reg/logic/integer family)",
            );
            return true;
        }
        if !matches!(kind, ir::NetKind::Assoc | ir::NetKind::AssocStr) {
            // The dense dyn/queue walk exists only for the foreach desugar.
            let synthetic = matches!(
                &args[0].kind,
                ast::ExprKind::Ident(p) if p.segments[0].name.starts_with("__foreach_")
            );
            if !synthetic {
                self.error(
                    MsgCode::ElabUnsupported,
                    "first/next/last/prev are associative-array methods (use `foreach` to walk a dyn array/queue)",
                );
                return true;
            }
        }
        let which = match method {
            "first" => ir::SysFuncId::AssocFirst,
            "next" => ir::SysFuncId::AssocNext,
            "last" => ir::SysFuncId::AssocLast,
            _ => ir::SysFuncId::AssocPrev,
        };
        let handle = self.push_expr(ir::Expr::Signal { net, word: None });
        let key = self.push_expr(ir::Expr::Signal {
            net: knet,
            word: None,
        });
        let rhs = self.push_expr(ir::Expr::SysFunc {
            which,
            args: vec![handle, key],
        });
        let lv = self.lower_lvalue(lhs);
        self.check_lvalue_kind(&lv, true);
        let sid = self.push_stmt(ir::Stmt::BlockingAssign { lhs: lv, rhs });
        b.push_stmt_id(sid);
        true
    }

    // ── multi-dim unpacked-array access (read/write, (a)-flattening) ─────────
    //
    // A `base[i0][i1]…[ik]` selection parses as a left-nested BitSelect chain. If
    // the innermost base is a plain single-segment `Ident` resolving to an ARRAY
    // net (`array_len > 1`), the whole chain is an array access; otherwise it is an
    // ordinary bit/part-select on a scalar value and these helpers return `None` so
    // the caller's existing logic runs. The index `Vec` is returned in SOURCE order
    // (`[i0, i1, …, ik]`): the chain walk yields outer-first, so the base part is
    // reversed and the outermost index appended last.

    /// Collect a read-side `base[index]` chain rooted at an array `Ident`.
    fn expr_array_chain<'a>(
        &self,
        base: &'a ast::Expr,
        index: &'a ast::Expr,
    ) -> Option<(u32, Vec<&'a ast::Expr>)> {
        let mut outer_first: Vec<&ast::Expr> = Vec::new();
        let mut cur = base;
        let net = loop {
            match &cur.kind {
                ast::ExprKind::BitSelect { base: b, index: i } => {
                    outer_first.push(i);
                    cur = b;
                }
                ast::ExprKind::Ident(p) if p.segments.len() == 1 => {
                    match self.lookup_net_scoped(&p.segments[0].name) {
                        // Declared array-ness, NOT `array_len > 1`: a `[0:0]`
                        // array's element access is still an ELEMENT access
                        // (adversarial find #5 — it used to bit-select word 0).
                        Some(n) if self.net_is_static_array(n) => break n,
                        _ => return None,
                    }
                }
                _ => return None,
            }
        };
        outer_first.reverse(); // base-chain → source order
        outer_first.push(index); // outermost index is the last in source order
        Some((net, outer_first))
    }

    /// Like [`Self::expr_array_chain`] but for a multi-dim PACKED net (a flat vector
    /// recorded in `packed_dims`): `m[i]…[k]` selects a bit-SLICE, not a word.
    fn expr_packed_chain<'a>(
        &self,
        base: &'a ast::Expr,
        index: &'a ast::Expr,
    ) -> Option<(u32, Vec<&'a ast::Expr>)> {
        let mut outer_first: Vec<&ast::Expr> = Vec::new();
        let mut cur = base;
        let net = loop {
            match &cur.kind {
                ast::ExprKind::BitSelect { base: b, index: i } => {
                    outer_first.push(i);
                    cur = b;
                }
                ast::ExprKind::Ident(p) if p.segments.len() == 1 => {
                    match self.lookup_net_scoped(&p.segments[0].name) {
                        Some(n) if self.packed_dims.contains_key(&n) => break n,
                        _ => return None,
                    }
                }
                _ => return None,
            }
        };
        outer_first.reverse();
        outer_first.push(index);
        Some((net, outer_first))
    }

    /// Lower a read `m[i0]…[ik]` on a packed multi-dim net to a bit-slice. The first
    /// `k` indices give the bit OFFSET (`(i-lo)*stride`, stride = product of inner
    /// dim widths — reusing [`Self::flatten_word`]); the result WIDTH is the product
    /// of the un-indexed inner dims. Lowered to an indexed part-select.
    fn lower_packed_read(&mut self, net: u32, idxs: &[&ast::Expr]) -> u32 {
        let dims = self.packed_dims[&net].clone();
        if idxs.len() > dims.len() {
            self.error(
                MsgCode::ElabUnsupported,
                "too many indices for packed array (more than its dimensions)",
            );
            return self.placeholder_expr();
        }
        let offset = self.flatten_word(&dims, idxs);
        let elem_w: u64 = dims[idxs.len()..].iter().map(|&(_, w)| w as u64).product();
        let base = self.push_expr(ir::Expr::Signal { net, word: None });
        let width = self.const_u32_expr(elem_w.min(u32::MAX as u64) as u32, 32);
        self.push_expr(ir::Expr::Select {
            base,
            offset,
            width,
            kind: ir::SelKind::PartIdxUp,
        })
    }

    /// Write-side twin of [`Self::expr_array_chain`] over `Lvalue` nodes.
    fn lval_array_chain<'a>(
        &self,
        base: &'a ast::Lvalue,
        index: &'a ast::Expr,
    ) -> Option<(u32, Vec<&'a ast::Expr>)> {
        let mut outer_first: Vec<&ast::Expr> = Vec::new();
        let mut cur = base;
        let net = loop {
            match cur {
                ast::Lvalue::BitSelect {
                    base: b, index: i, ..
                } => {
                    outer_first.push(i);
                    cur = b;
                }
                ast::Lvalue::Ident(p) if p.segments.len() == 1 => {
                    match self.lookup_net_scoped(&p.segments[0].name) {
                        // Same declared-array-ness rule as expr_array_chain.
                        Some(n) if self.net_is_static_array(n) => break n,
                        _ => return None,
                    }
                }
                _ => return None,
            }
        };
        outer_first.reverse();
        outer_first.push(index);
        Some((net, outer_first))
    }

    /// Write-side twin of [`Self::expr_packed_chain`] (multi-dim PACKED net).
    fn lval_packed_chain<'a>(
        &self,
        base: &'a ast::Lvalue,
        index: &'a ast::Expr,
    ) -> Option<(u32, Vec<&'a ast::Expr>)> {
        let mut outer_first: Vec<&ast::Expr> = Vec::new();
        let mut cur = base;
        let net = loop {
            match cur {
                ast::Lvalue::BitSelect {
                    base: b, index: i, ..
                } => {
                    outer_first.push(i);
                    cur = b;
                }
                ast::Lvalue::Ident(p) if p.segments.len() == 1 => {
                    match self.lookup_net_scoped(&p.segments[0].name) {
                        Some(n) if self.packed_dims.contains_key(&n) => break n,
                        _ => return None,
                    }
                }
                _ => return None,
            }
        };
        outer_first.reverse();
        outer_first.push(index);
        Some((net, outer_first))
    }

    /// Write `m[i0]…[ik] = …` on a packed multi-dim net into one bit-slice LvalChunk
    /// (indexed part-select), mirroring [`Self::lower_packed_read`].
    fn collect_packed_write(
        &mut self,
        net: u32,
        idxs: &[&ast::Expr],
        out: &mut Vec<ir::LvalChunk>,
    ) {
        let dims = self.packed_dims[&net].clone();
        if idxs.len() > dims.len() {
            self.error(
                MsgCode::ElabUnsupported,
                "too many indices for packed array (more than its dimensions)",
            );
            out.push(ir::LvalChunk {
                net: POISON_NET,
                word: None,
                offset: None,
                width: None,
                kind: ir::SelKind::Bit,
            });
            return;
        }
        let offset = self.flatten_word(&dims, idxs);
        let elem_w: u64 = dims[idxs.len()..].iter().map(|&(_, w)| w as u64).product();
        let width = self.const_u32_expr(elem_w.min(u32::MAX as u64) as u32, 32);
        out.push(ir::LvalChunk {
            net,
            word: None,
            offset: Some(offset),
            width: Some(width),
            kind: ir::SelKind::PartIdxUp,
        });
    }

    /// Per-dim `(lo, size)` extents of array `net` (source order). Arrays with
    /// non-0-based or multi-dim addressing record their shape in `array_dims`; a
    /// plain 0-based 1-D array falls back to a single `(0, array_len)` extent.
    fn net_dim_extents(&self, net: u32) -> Vec<(u32, u32)> {
        self.array_dims
            .get(&net)
            .cloned()
            .unwrap_or_else(|| vec![(0, self.nets[net as usize].array_len.max(1))])
    }

    /// Row-major flat word ExprId for the first `extents.len()` indices. Each index
    /// is normalized to a 0-based slot by subtracting its dim's `lo` (`mem[4]` on a
    /// `[4:7]` dim → `i-4`); strides are the suffix products of the dim sizes. A
    /// `lo` of 0 emits NO `Sub` and a stride of 1 emits NO `Mul`, so a plain 0-based
    /// 1-D `mem[i]` still lowers to exactly `lower_expr(i)` — the golden IR for the
    /// common case is byte-for-byte preserved.
    fn flatten_word(&mut self, extents: &[(u32, u32)], word_idxs: &[&ast::Expr]) -> u32 {
        let d = extents.len();
        // strides[k] = product(size[k+1..]) as u64 (saturating into u32 at use).
        let mut strides = vec![1u64; d];
        for k in (0..d.saturating_sub(1)).rev() {
            strides[k] = strides[k + 1].saturating_mul(extents[k + 1].1 as u64);
        }
        // Phase-1.x ③: per-dim bounds guards, MULTI-dim only. A 1-D access is
        // already exact (lo-normalization wraps an under-index to a huge word
        // that the engine's flat check rejects) and stays byte-identically
        // guard-free; with d ≥ 2 an inner-dim violation lands INSIDE the flat
        // space — a silent alias into the neighbouring row (iverilog 13.0
        // shares that alias, so the X behavior is hand-pinned to IEEE §7.4.6).
        let guard_dims = d >= 2;
        let mut valid: Option<u32> = None;
        let mut acc: Option<u32> = None;
        for (k, idx) in word_idxs.iter().enumerate() {
            let (lo, size) = extents[k];
            let i_eid = self.lower_expr(idx);
            if guard_dims {
                // `idx >= lo && idx <= hi` on the RAW index. A negative or
                // wrapped index always fails one side in either signedness
                // reading (bounds < 2^24 « 2^31); an X index X-poisons the
                // conjunction and the final ternary merge below.
                let lo_c = self.const_u32_expr(lo, 32);
                let hi_c = self.const_u32_expr(lo.saturating_add(size - 1), 32);
                let ge = self.push_expr(ir::Expr::Binary {
                    op: ir::BinOp::Ge,
                    lhs: i_eid,
                    rhs: lo_c,
                });
                let le = self.push_expr(ir::Expr::Binary {
                    op: ir::BinOp::Le,
                    lhs: i_eid,
                    rhs: hi_c,
                });
                let both = self.push_expr(ir::Expr::Binary {
                    op: ir::BinOp::LogAnd,
                    lhs: ge,
                    rhs: le,
                });
                valid = Some(match valid {
                    None => both,
                    Some(v) => self.push_expr(ir::Expr::Binary {
                        op: ir::BinOp::LogAnd,
                        lhs: v,
                        rhs: both,
                    }),
                });
            }
            // normalized 0-based coordinate: `idx - lo` (lo==0 ⇒ raw index, no Sub).
            let coord = if lo == 0 {
                i_eid
            } else {
                let lo_c = self.const_u32_expr(lo, 32);
                self.push_expr(ir::Expr::Binary {
                    op: ir::BinOp::Sub,
                    lhs: i_eid,
                    rhs: lo_c,
                })
            };
            let term = if strides[k] == 1 {
                coord
            } else {
                let s = self.const_u32_expr(strides[k].min(u32::MAX as u64) as u32, 32);
                self.push_expr(ir::Expr::Binary {
                    op: ir::BinOp::Mul,
                    lhs: coord,
                    rhs: s,
                })
            };
            acc = Some(match acc {
                None => term,
                Some(a) => self.push_expr(ir::Expr::Binary {
                    op: ir::BinOp::Add,
                    lhs: a,
                    rhs: term,
                }),
            });
        }
        let flat = acc.unwrap_or_else(|| self.const_u32_expr(0, 32));
        match valid {
            None => flat,
            Some(cond) => {
                // OOB sentinel 0x8000_0000: far above MAX_ARRAY_LEN (2^24) and
                // ADDITION-STABLE — a downstream `base + residual` (the array-
                // assignment expansion) cannot wrap it back into range. An X
                // condition ternary-merges flat-vs-sentinel into an unknown-
                // contaminated word, which the engine already treats as
                // invalid (read X / write no-op).
                let oob = self.const_u32_expr(0x8000_0000, 32);
                self.push_expr(ir::Expr::Ternary {
                    cond,
                    then_e: flat,
                    else_e: oob,
                })
            }
        }
    }

    /// Lower a read `net[idxs…]`: first D indices → flat word; ONE optional trailing
    /// index → a bit-select into the element word (`g[i][j][k]`). Fewer than D
    /// indices is a partial unpacked slice; more than D+1 is a bit-of-bit select —
    /// both unsupported in v1 (loud, not silent). The trailing cap is SYMMETRIC with
    /// the write path (`collect_array_write`), so over-indexing is rejected the same
    /// way on read and write rather than silently yielding X on one side.
    fn lower_array_read(&mut self, net: u32, idxs: &[&ast::Expr]) -> u32 {
        let dims = self.net_dim_extents(net);
        let d = dims.len();
        if idxs.len() < d {
            self.error(
                MsgCode::ElabUnsupported,
                "partial unpacked-array slice (v1: index every dimension)",
            );
            return self.placeholder_expr();
        }
        if idxs.len() > d + 1 {
            self.error(
                MsgCode::ElabUnsupported,
                "bit-select then bit-select on a multi-dim array element (v1: single bit/part)",
            );
            return self.placeholder_expr();
        }
        let word = self.flatten_word(&dims, &idxs[..d]);
        let val = self.push_expr(ir::Expr::Signal {
            net,
            word: Some(word),
        });
        if let Some(bidx) = idxs.get(d) {
            let offset = self.lower_expr(bidx);
            let width = self.const_u32_expr(1, 32);
            return self.push_expr(ir::Expr::Select {
                base: val,
                offset,
                width,
                kind: ir::SelKind::Bit,
            });
        }
        val
    }

    /// Lower a write `net[idxs…] = …` into one `LvalChunk`: first D indices → flat
    /// word; one trailing index → a single bit-select on the element. `< D` indices
    /// (partial slice) and `> D+1` indices (bit-of-bit LHS) are unsupported (loud).
    fn collect_array_write(&mut self, net: u32, idxs: &[&ast::Expr], out: &mut Vec<ir::LvalChunk>) {
        let dims = self.net_dim_extents(net);
        let d = dims.len();
        if idxs.len() < d {
            self.error(
                MsgCode::ElabUnsupported,
                "partial unpacked-array slice (v1: index every dimension)",
            );
            out.push(ir::LvalChunk {
                net: POISON_NET,
                word: None,
                offset: None,
                width: None,
                kind: ir::SelKind::Bit,
            });
            return;
        }
        let word = self.flatten_word(&dims, &idxs[..d]);
        let trailing = &idxs[d..];
        let (offset, width) = match trailing.len() {
            0 => (None, None),
            1 => {
                let off = self.lower_expr(trailing[0]);
                let w = self.const_u32_expr(1, 32);
                (Some(off), Some(w))
            }
            _ => {
                self.error(
                    MsgCode::ElabUnsupported,
                    "nested bit-select on a multi-dim array lvalue (v1: single bit/part)",
                );
                (None, None)
            }
        };
        out.push(ir::LvalChunk {
            net,
            word: Some(word),
            offset,
            width,
            kind: ir::SelKind::Bit,
        });
    }

    // ── unpacked-array ASSIGNMENT (whole array / partial slice) ─────
    //
    // IEEE 1800 §7.6: source and target need the same number of unpacked
    // dims, the same SIZE per dim, and identical element types; elements
    // correspond POSITIONALLY in declared left-to-right index order (the
    // LRM example pairs `A[10:1] = B[0:9]` as A[10]=B[0] … A[1]=B[9]).
    //
    // ⚠️ iverilog 13.0 rejects fixed-size unpacked array assignment outright,
    // so this lane is hand-pinned to the LRM (same precedent as assoc /
    // interface ports). The expansion is element-wise: one assignment per
    // element, leading (user) indices lowered ONCE and shared as a base
    // word expression, each element adding its constant residual offset.
    // Element-wise order is observationally equivalent to the LRM's
    // evaluate-then-assign because the supported slice forms make source
    // and target rows either identical or disjoint, and slice indices are
    // REJECTED if they read the target array (the one case where a write
    // mid-copy could move the index).

    /// `Some((net, leading))` when `lv` is a static unpacked-array lvalue
    /// indexed by FEWER indices than its dimension count (whole = zero).
    fn lval_array_view<'a>(&self, lv: &'a ast::Lvalue) -> Option<(u32, Vec<&'a ast::Expr>)> {
        match lv {
            ast::Lvalue::Ident(p) => {
                let name = match p.segments.as_slice() {
                    [seg] => {
                        if self.out_subst_lookup(&seg.name).is_some() {
                            return None; // task out-formal: vector surface
                        }
                        seg.name.clone()
                    }
                    segs => segs
                        .iter()
                        .map(|s| s.name.as_str())
                        .collect::<Vec<_>>()
                        .join("."),
                };
                let net = self.lookup_net_scoped(&name)?;
                self.net_is_static_array(net).then(|| (net, Vec::new()))
            }
            ast::Lvalue::BitSelect { base, index, .. } => {
                let (net, idxs) = self.lval_array_chain(base, index)?;
                (idxs.len() < self.net_dim_extents(net).len()).then_some((net, idxs))
            }
            _ => None,
        }
    }

    /// Read-side twin of [`Self::lval_array_view`] over expressions.
    fn expr_array_view<'a>(&self, e: &'a ast::Expr) -> Option<(u32, Vec<&'a ast::Expr>)> {
        match &e.kind {
            ast::ExprKind::Ident(p) => {
                let name = match p.segments.as_slice() {
                    [seg] => {
                        // Inline-subst formals / params shadow nets (mirrors
                        // the lower_expr Ident arm's resolution priority).
                        if self.subst_lookup(&seg.name).is_some()
                            || self.out_subst_lookup(&seg.name).is_some()
                            || self.lookup_scoped(&seg.name).is_some()
                        {
                            return None;
                        }
                        seg.name.clone()
                    }
                    segs => segs
                        .iter()
                        .map(|s| s.name.as_str())
                        .collect::<Vec<_>>()
                        .join("."),
                };
                let net = self.lookup_net_scoped(&name)?;
                self.net_is_static_array(net).then(|| (net, Vec::new()))
            }
            ast::ExprKind::BitSelect { base, index } => {
                let (net, idxs) = self.expr_array_chain(base, index)?;
                (idxs.len() < self.net_dim_extents(net).len()).then_some((net, idxs))
            }
            ast::ExprKind::Paren { inner } => self.expr_array_view(inner),
            _ => None,
        }
    }

    /// Fixed-size unpacked array stored in the flat word store (dyn/queue/assoc
    /// handles have `array_len == 0`). `array_len > 1` alone would exempt
    /// 1-element arrays (`reg x [0:0]`, adversarial find #5), so declared
    /// array-ness is tracked explicitly in `unpacked_array_nets`.
    fn net_is_static_array(&self, net: u32) -> bool {
        self.unpacked_array_nets.contains(&net)
            || self
                .nets
                .get(net as usize)
                .is_some_and(|nv| nv.array_len > 1)
    }

    /// Conservative aliasing walk: does `e` read net `target` through any
    /// name it mentions? (Names resolve exactly like the lowering would —
    /// scoped lookup incl. dotted interface aliases — so an index variable
    /// `i` never false-positives.)
    fn expr_reads_net(&self, e: &ast::Expr, target: u32) -> bool {
        match &e.kind {
            ast::ExprKind::Ident(p) => {
                let name = p
                    .segments
                    .iter()
                    .map(|s| s.name.as_str())
                    .collect::<Vec<_>>()
                    .join(".");
                self.lookup_net_scoped(&name) == Some(target)
            }
            ast::ExprKind::BitSelect { base, index } => {
                self.expr_reads_net(base, target) || self.expr_reads_net(index, target)
            }
            ast::ExprKind::Paren { inner } => self.expr_reads_net(inner, target),
            ast::ExprKind::Unary { operand, .. } => self.expr_reads_net(operand, target),
            ast::ExprKind::Binary { lhs, rhs, .. } => {
                self.expr_reads_net(lhs, target) || self.expr_reads_net(rhs, target)
            }
            ast::ExprKind::Ternary {
                cond,
                then_e,
                else_e,
            } => {
                self.expr_reads_net(cond, target)
                    || self.expr_reads_net(then_e, target)
                    || self.expr_reads_net(else_e, target)
            }
            ast::ExprKind::PartSelect { base, msb, lsb } => {
                self.expr_reads_net(base, target)
                    || self.expr_reads_net(msb, target)
                    || self.expr_reads_net(lsb, target)
            }
            ast::ExprKind::IndexedPart {
                base,
                offset,
                width,
                ..
            } => {
                self.expr_reads_net(base, target)
                    || self.expr_reads_net(offset, target)
                    || self.expr_reads_net(width, target)
            }
            ast::ExprKind::Concat { parts } => parts.iter().any(|p| self.expr_reads_net(p, target)),
            ast::ExprKind::Replicate { count, value } => {
                self.expr_reads_net(count, target)
                    || value.iter().any(|p| self.expr_reads_net(p, target))
            }
            // A user function body could read anything — conservative TRUE
            // keeps the guard sound (loud beats a silently moved index).
            ast::ExprKind::Call { .. } => true,
            // V2005-compat: with a net literally named `new` in scope,
            // `new[i]` lowers as a READ of that net (adversarial find #3) —
            // check the fallback target and walk the children.
            ast::ExprKind::New { size, src } => {
                self.lookup_net_scoped("new") == Some(target)
                    || self.expr_reads_net(size, target)
                    || src.as_ref().is_some_and(|s| self.expr_reads_net(s, target))
            }
            ast::ExprKind::MinTypMax { min, typ, max } => {
                self.expr_reads_net(min, target)
                    || self.expr_reads_net(typ, target)
                    || self.expr_reads_net(max, target)
            }
            ast::ExprKind::SysCall { args, .. } => {
                args.iter().any(|a| self.expr_reads_net(a, target))
            }
            _ => false,
        }
    }

    /// Per-position word offsets of a residual sub-array in DECLARED
    /// left-to-right order: position 0 is the leftmost element of every dim.
    /// `dims` are the residual `(lo, size)` extents (trailing dims of the
    /// full array, so suffix-product strides within the residual equal the
    /// full array's strides); `desc[k]` flips dim `k`'s traversal.
    fn residual_word_offsets(dims: &[(u32, u32)], desc: &[bool]) -> Vec<u32> {
        let n: u64 = dims.iter().map(|&(_, s)| s as u64).product();
        let mut strides = vec![1u64; dims.len()];
        for k in (0..dims.len().saturating_sub(1)).rev() {
            strides[k] = strides[k + 1].saturating_mul(dims[k + 1].1 as u64);
        }
        (0..n)
            .map(|p| {
                let mut rem = p;
                let mut off = 0u64;
                for k in (0..dims.len()).rev() {
                    let size = dims[k].1 as u64;
                    let digit = rem % size;
                    rem /= size;
                    let slot = if desc.get(k).copied().unwrap_or(false) {
                        size - 1 - digit
                    } else {
                        digit
                    };
                    off += slot * strides[k];
                }
                off.min(u32::MAX as u64) as u32
            })
            .collect()
    }

    /// Word ExprId for `base + off` (no Add node when either side is trivial).
    fn word_expr_at(&mut self, base: Option<u32>, off: u32) -> u32 {
        match base {
            None => self.const_u32_expr(off, 32),
            Some(b) if off == 0 => b,
            Some(b) => {
                let c = self.const_u32_expr(off, 32);
                self.push_expr(ir::Expr::Binary {
                    op: ir::BinOp::Add,
                    lhs: b,
                    rhs: c,
                })
            }
        }
    }

    /// Intercept `lhs = rhs` / `lhs <= [#d] rhs` when the LHS is an unpacked
    /// array (whole or partial slice). Returns `true` when the statement was
    /// consumed (expanded element-wise, or rejected loudly).
    fn array_assign_special(
        &mut self,
        b: &mut ProcessBuilder,
        lhs: &ast::Lvalue,
        delay: Option<&ast::Delay>,
        rhs: &ast::Expr,
        nonblocking: bool,
    ) -> bool {
        const ARRAY_COPY_UNROLL_CAP: u64 = 4096;
        let Some((t_net, t_lead)) = self.lval_array_view(lhs) else {
            return false;
        };
        // The expansion builds chunks by hand, bypassing collect_lval_chunks
        // — re-run its modport write rule here (adversarial find #1: a
        // modport-`input` array was silently writable as `p.arr = l`).
        if let Some(path) = lval_root_path(lhs) {
            let path = path.clone();
            self.check_modport_write(&path);
        }
        let Some((s_net, s_lead)) = self.expr_array_view(rhs) else {
            self.error(
                MsgCode::ElabUnsupported,
                "assigning a non-array value to an unpacked array (copy from an \
                 identically-shaped array, or index an element)",
            );
            return true;
        };
        let t_dims = self.net_dim_extents(t_net);
        let s_dims = self.net_dim_extents(s_net);
        let t_res = &t_dims[t_lead.len()..];
        let s_res = &s_dims[s_lead.len()..];
        if t_res.len() != s_res.len()
            || t_res.iter().zip(s_res).any(|(&(_, ts), &(_, ss))| ts != ss)
        {
            self.error(
                MsgCode::ElabUnsupported,
                "unpacked-array assignment requires the same number of dimensions \
                 and the same size per dimension (IEEE 1800 §7.6)",
            );
            return true;
        }
        let (tw, tk, tsg) = {
            let nv = &self.nets[t_net as usize];
            (nv.width, nv.kind, nv.signed)
        };
        let (sw, sk, ssg) = {
            let nv = &self.nets[s_net as usize];
            (nv.width, nv.kind, nv.signed)
        };
        // §6.22.2 equivalent element types: width, realness AND signedness
        // (a raw word copy would be bit-correct either way, but accepting a
        // signed/unsigned mix would silently diverge from conformant tools).
        if tw != sw || (tk == ir::NetKind::Real) != (sk == ir::NetKind::Real) || tsg != ssg {
            self.error(
                MsgCode::ElabUnsupported,
                "unpacked-array assignment requires identical element types \
                 (IEEE 1800 §7.6)",
            );
            return true;
        }
        if !nonblocking && delay.is_some() {
            self.error(
                MsgCode::ElabUnsupported,
                "intra-assignment delay on an unpacked-array assignment \
                 (v1: plain `=`, `<=`, or `<= #d`)",
            );
            return true;
        }
        if t_lead
            .iter()
            .chain(s_lead.iter())
            .any(|i| self.expr_reads_net(i, t_net))
        {
            self.error(
                MsgCode::ElabUnsupported,
                "an array-slice index in an array assignment reads the assignment \
                 target itself (v1: the element-wise copy could move the index)",
            );
            return true;
        }
        let n: u64 = t_res.iter().map(|&(_, s)| s as u64).product();
        if n > ARRAY_COPY_UNROLL_CAP {
            self.error(
                MsgCode::ElabUnsupported,
                &format!(
                    "unpacked-array assignment copies {n} elements \
                     (v1 cap {ARRAY_COPY_UNROLL_CAP})"
                ),
            );
            return true;
        }
        let t_desc: Vec<bool> = self
            .array_dim_desc
            .get(&t_net)
            .map(|v| v[t_lead.len()..].to_vec())
            .unwrap_or_default();
        let s_desc: Vec<bool> = self
            .array_dim_desc
            .get(&s_net)
            .map(|v| v[s_lead.len()..].to_vec())
            .unwrap_or_default();
        let t_offs = Self::residual_word_offsets(t_res, &t_desc);
        let s_offs = Self::residual_word_offsets(s_res, &s_desc);
        // Leading (user) indices lower ONCE; every element shares the base
        // ExprId (pure reads — sharing is the function-inline precedent).
        let t_base = (!t_lead.is_empty()).then(|| self.flatten_word(&t_dims, &t_lead));
        let s_base = (!s_lead.is_empty()).then(|| self.flatten_word(&s_dims, &s_lead));
        let delay_id = if nonblocking {
            delay.map(|d| self.lower_delay(d).0)
        } else {
            None
        };
        let mut kind_checked = false;
        for (&t_off, &s_off) in t_offs.iter().zip(&s_offs) {
            let t_word = self.word_expr_at(t_base, t_off);
            let s_word = self.word_expr_at(s_base, s_off);
            let rhs_id = self.push_expr(ir::Expr::Signal {
                net: s_net,
                word: Some(s_word),
            });
            let lv = ir::Lvalue {
                chunks: vec![ir::LvalChunk {
                    net: t_net,
                    word: Some(t_word),
                    offset: None,
                    width: None,
                    kind: ir::SelKind::Bit,
                }],
            };
            if !kind_checked {
                self.check_lvalue_kind(&lv, true); // E3018 once (same net throughout)
                kind_checked = true;
            }
            let sid = if nonblocking {
                self.push_stmt(ir::Stmt::NonblockingAssign {
                    lhs: lv,
                    rhs: rhs_id,
                    delay: delay_id,
                })
            } else {
                self.push_stmt(ir::Stmt::BlockingAssign {
                    lhs: lv,
                    rhs: rhs_id,
                })
            };
            b.push_stmt_id(sid);
        }
        true
    }
}

// ════════════════════════════════════════════════════════════════════
//  v4 — GENERATE unrolling (GenerateConstruct → flat SimIr at elab time)
// ════════════════════════════════════════════════════════════════════
//
// A generate construct is expanded at ELABORATION time: a generate-for with N
// iterations becomes N copies of its body in the flat SimIr (genvar bound to
// each iteration value); a generate-if/case selects exactly one branch. Nothing
// generate-related survives into sim-ir — the genvar is an elaboration-only
// integer (it lives in `self.params`, never `self.nets`).
//
// PHASE SPLIT (the determinism contract): the existing flat-module lowering
// relies on net-decl order (pass 4) < cont-assign/proc order (pass 7) < child
// instance recursion (pass 8). A generate block mixes all three. So we re-walk
// the gen-item tree once per phase, doing only the matching kind of work. The
// unroll arithmetic (const-eval of init/cond/step) is pure and side-effect-free,
// so every phase reproduces the SAME genvar sequence and the SAME `label[idx]`
// prefixes — nets land entirely in the Nets walk (before any Logic), Logic
// before Instances, exactly mirroring the flat-module pass order.

/// Which slice of work a generate walk performs.
#[derive(Clone, Copy, PartialEq, Eq)]
enum GenPhase {
    /// Create NetVar nets only (so they sit in the parent's contiguous slice).
    Nets,
    /// Lower cont-assigns + processes only (nets already created in the Nets walk).
    Logic,
    /// Recurse into child module instances only (after the parent net slice is final).
    Instances,
}

impl<'s> Elaborator<'s> {
    /// Run `f` with `cur_prefix` temporarily extended by `seg` (a gen-block
    /// `label[idx]` segment). Restores the prefix on return. Genvar bindings in
    /// `self.params` are NOT touched here (the caller manages those).
    fn with_scope<R>(&mut self, seg: &str, f: impl FnOnce(&mut Self) -> R) -> R {
        let new_prefix = if self.cur_prefix.is_empty() {
            seg.to_string()
        } else {
            format!("{}.{}", self.cur_prefix, seg)
        };
        let saved = std::mem::replace(&mut self.cur_prefix, new_prefix);
        let r = f(self);
        self.cur_prefix = saved;
        r
    }

    /// Unroll/select a list of GenItems at elaboration time, in deterministic
    /// order. `phase` selects which lowering work to do (see [`GenPhase`]).
    /// `depth` is the nesting guard. Genvars bind into `self.params` (like a
    /// param) so `const_eval_in_scope` resolves them; `with_scope` gives each
    /// loop iteration its `label[idx].` namespace.
    fn elaborate_generate(
        &mut self,
        items: &[ast::GenItem],
        phase: GenPhase,
        depth: u32,
        map: &ModuleMap<'_>,
    ) {
        if depth > GENERATE_DEPTH_CAP {
            // depth guard reported ONCE (in the Nets phase) to avoid 3× dup.
            if phase == GenPhase::Nets {
                self.error(
                    MsgCode::ElabUnsupported,
                    "generate nesting too deep (deferred)",
                );
            }
            return;
        }
        for item in items {
            self.elaborate_gen_item(item, phase, depth, map);
        }
    }

    fn elaborate_gen_item(
        &mut self,
        item: &ast::GenItem,
        phase: GenPhase,
        depth: u32,
        map: &ModuleMap<'_>,
    ) {
        match item {
            // ── generate-for: bind genvar, unroll ascending ──────────
            ast::GenItem::For {
                init,
                cond,
                step,
                label,
                body,
                ..
            } => {
                let gv_key = self.fq(&init.lvalue.name);

                // INIT value, const-eval'd in the current scope.
                let Some(start) = self.const_eval_in_scope(&init.value) else {
                    if phase == GenPhase::Nets {
                        self.error(
                            MsgCode::ElabUnresolvedName,
                            "generate-for init is not a constant",
                        );
                    }
                    return;
                };

                // Save any prior binding of this name (an outer param/genvar of the
                // same identifier) and seed the genvar.
                let saved = self.params.insert(gv_key.clone(), start);

                let mut idx_count: u32 = 0;
                loop {
                    // cond folded WITH the genvar bound (so `i < N` resolves).
                    let keep = match self.const_eval_in_scope(cond) {
                        Some(c) => c != 0,
                        None => {
                            if phase == GenPhase::Nets {
                                self.error(
                                    MsgCode::ElabUnresolvedName,
                                    "generate-for condition is not a constant",
                                );
                            }
                            break;
                        }
                    };
                    if !keep {
                        break;
                    }
                    if idx_count >= GENERATE_UNROLL_CAP {
                        if phase == GenPhase::Nets {
                            self.error(
                                MsgCode::ElabUnsupported,
                                "generate-for exceeds the unroll cap (possible infinite loop)",
                            );
                        }
                        break;
                    }

                    // The genvar VALUE (not a 0-based counter) indexes the block
                    // name, so `for(i=2;i<5;…)` yields `[2],[3],[4]` per Verilog.
                    let iter_val = *self.params.get(&gv_key).unwrap_or(&0);
                    let lbl = label.as_ref().map(|l| l.name.as_str()).unwrap_or("genblk");
                    let block_prefix = format!("{lbl}[{iter_val}]");

                    self.with_scope(&block_prefix, |me| {
                        me.elaborate_generate(body, phase, depth + 1, map);
                    });

                    // step: fold (with genvar bound) → rebind the genvar.
                    let Some(next) = self.const_eval_in_scope(&step.value) else {
                        if phase == GenPhase::Nets {
                            self.error(
                                MsgCode::ElabUnresolvedName,
                                "generate-for step is not a constant",
                            );
                        }
                        break;
                    };
                    // STALL GUARD (verdict M1): the genvar VALUE namespaces each
                    // iteration's block (`label[iter_val]`). If the step does NOT
                    // advance it (`next == iter_val`, e.g. `i = i`), every iteration
                    // reuses the SAME prefix and collides at `add_net`, emitting one
                    // duplicate-decl error PER iteration up to the unroll cap (~4k
                    // spurious diagnostics). Detect the non-progressing step and stop
                    // with ONE diagnostic. (A value that merely repeats LATER — a
                    // non-monotonic cycle — is still bounded by the unroll cap;
                    // correctness intact, diagnostics less clean. Residual risk R3.)
                    if next == iter_val {
                        if phase == GenPhase::Nets {
                            self.error(
                                MsgCode::ElabUnsupported,
                                "generate-for genvar does not advance (step leaves it unchanged)",
                            );
                        }
                        break;
                    }
                    self.params.insert(gv_key.clone(), next);
                    idx_count += 1;
                }

                // restore the prior binding (siblings/ancestors unaffected).
                match saved {
                    Some(v) => {
                        self.params.insert(gv_key, v);
                    }
                    None => {
                        self.params.remove(&gv_key);
                    }
                }
            }

            // ── generate-if: const-eval cond, take ONE branch ────────
            ast::GenItem::If {
                cond,
                then_b,
                else_b,
                label,
                ..
            } => {
                let taken = match self.const_eval_in_scope(cond) {
                    Some(c) => c != 0,
                    None => {
                        if phase == GenPhase::Nets {
                            self.error(
                                MsgCode::ElabUnresolvedName,
                                "generate-if condition is not a constant",
                            );
                        }
                        return;
                    }
                };
                let body = if taken { then_b } else { else_b };
                self.elaborate_gen_scoped(label, body, phase, depth, map);
            }

            // ── generate-case: const-eval scrutinee, match ONE item ──
            ast::GenItem::Case {
                scrutinee, items, ..
            } => {
                let Some(scrut) = self.const_eval_in_scope(scrutinee) else {
                    if phase == GenPhase::Nets {
                        self.error(
                            MsgCode::ElabUnresolvedName,
                            "generate-case scrutinee is not a constant",
                        );
                    }
                    return;
                };
                // first Match whose label const-equals scrut wins; else Default.
                let mut chosen: Option<&[ast::GenItem]> = None;
                let mut default: Option<&[ast::GenItem]> = None;
                'scan: for ci in items {
                    match ci {
                        ast::GenCaseItem::Match { labels, body, .. } => {
                            for lab in labels {
                                if self.const_eval_in_scope(lab) == Some(scrut) {
                                    chosen = Some(body);
                                    break 'scan;
                                }
                            }
                        }
                        ast::GenCaseItem::Default { body, .. } => {
                            default = Some(body);
                        }
                    }
                }
                if let Some(body) = chosen.or(default) {
                    self.elaborate_generate(body, phase, depth + 1, map);
                }
            }

            // ── named/unnamed begin…end block inside generate ────────
            ast::GenItem::Block { label, items, .. } => {
                self.elaborate_gen_scoped(label, items, phase, depth, map);
            }

            // ── a plain module-item directly inside generate ─────────
            ast::GenItem::Item(mi) => self.lower_gen_module_item(mi, phase, depth, map),
        }
    }

    /// Elaborate a gen-block body under an OPTIONAL label scope. A `Some(label)`
    /// adds a `label.` prefix segment; an unlabeled body contributes directly to
    /// the current scope (the common LRM behavior when no `begin:label` is given).
    fn elaborate_gen_scoped(
        &mut self,
        label: &Option<ast::Ident>,
        items: &[ast::GenItem],
        phase: GenPhase,
        depth: u32,
        map: &ModuleMap<'_>,
    ) {
        match label {
            Some(l) => {
                // A generate-if/case/block is a SINGLETON scope — tag it `label[0]`
                // (mirroring generate-for's `label[idx]`) so `is_gen_scope_segment`
                // recognizes it as a GENERATE scope and `walk_scopes` resolves outer
                // nets THROUGH it (a plain `label` would be read as an instance
                // boundary, stopping the outward walk → `t.g.y` undeclared).
                let seg = format!("{}[0]", l.name);
                self.with_scope(&seg, |me| {
                    me.elaborate_generate(items, phase, depth + 1, map);
                });
            }
            None => self.elaborate_generate(items, phase, depth + 1, map),
        }
    }

    /// Lower ONE plain `ModuleItem` found inside a generate, honoring the current
    /// phase. MIRRORS the per-item dispatch in `elaborate_instance` steps
    /// (4)/(7)/(8) — the deliberate reuse the PR calls for.
    fn lower_gen_module_item(
        &mut self,
        mi: &ast::ModuleItem,
        phase: GenPhase,
        depth: u32,
        map: &ModuleMap<'_>,
    ) {
        match (phase, mi) {
            // NETS phase: only net declarations. No ports inside a generate
            // (LRM forbids port decls) → empty port list/body, dir = Internal.
            (GenPhase::Nets, ast::ModuleItem::NetVar(d)) => {
                self.elaborate_netvar_decl(d, &ast::PortList::None, &[]);
            }
            // LOGIC phase: cont-assigns + processes.
            (GenPhase::Logic, ast::ModuleItem::ContAssign(ca)) => {
                self.elaborate_cont_assign(ca);
            }
            (GenPhase::Logic, ast::ModuleItem::Proc(p)) => {
                let proc = self.lower_proc_block(p);
                debug_assert_eq!(
                    self.processes.len() as u32,
                    self.cur_proc,
                    "ProcId mismatch (generate): fork_modes keyed by cur_proc would miss"
                );
                self.push_process(proc);
            }
            // INSTANCES phase: recurse into child module instances. The parent
            // instance id is `self.cur_inst` (the instance whose body we are in).
            (GenPhase::Instances, ast::ModuleItem::Instance(inst)) => {
                self.elaborate_child_instances(inst, self.cur_inst, map);
            }
            // generate-inside-generate: recurse in the SAME phase, +1 depth.
            (_, ast::ModuleItem::Generate(g)) => {
                self.elaborate_generate(&g.items, phase, depth + 1, map);
            }
            // forbidden-in-generate (reported once, in the Nets phase).
            (GenPhase::Nets, ast::ModuleItem::Param(_) | ast::ModuleItem::PortDecl(_)) => {
                self.error(
                    MsgCode::ElabUnsupported,
                    "parameter/port declaration not allowed inside generate",
                );
            }
            (
                GenPhase::Nets,
                ast::ModuleItem::Func(_) | ast::ModuleItem::Task(_) | ast::ModuleItem::Defparam(_),
            ) => {
                self.error(
                    MsgCode::ElabUnsupported,
                    "construct deferred inside generate (func/task/defparam)",
                );
            }
            // Genvar decl inside generate: elaboration-only, no net → no-op.
            // Any item not matching the active phase: no-op (handled elsewhere).
            _ => {}
        }
    }
}

// ════════════════════════════════════════════════════════════════════
//  v2 — procedural-block lowering (ProceduralBlock → ir::Process)
// ════════════════════════════════════════════════════════════════════
//
// BLOCK-INDEX SPACE (the load-bearing decision):
//   `ir::Process.body: Vec<BasicBlock>` is INLINE per-process. Every Terminator
//   target (`Goto.target`, `Branch.then_bb`/`else_bb`, `Delay.resume`,
//   `Wait.resume`, …) and `Process.entry` is an index INTO THAT process's own
//   `body` Vec — process-LOCAL, 0-based, reset per process. `SimIr.blocks`
//   (the top-level arena) is NOT referenced by `Process`; v2 leaves it empty
//   (it is reserved for func/task bodies, deferred). `BlockId` below is a
//   newtype over that process-local index so it can never be confused with a
//   StmtId/ExprId/NetId (all bare u32 elsewhere).
//
//   `BasicBlock.stmts: Vec<u32>` hold indices into the GLOBAL `self.stmts`
//   arena (shared across processes), appended via `push_stmt`.

/// Index into a `ProcessBuilder::body` (the process-local CFG), NOT the global
/// `SimIr.blocks` arena.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
struct BlockId(u32);
impl BlockId {
    fn raw(self) -> u32 {
        self.0
    }
}

/// Builds the CFG (`Vec<BasicBlock>`) for ONE process. Owns the process-local
/// block list + the single "unsealed block" cursor.
///
/// INV-1 (sealing): exactly one block — the one `cur` points at — is unsealed
/// at any time. `end_block_with` is the only writer of a real terminator and it
/// CLOSES the cursor (`cur = None`); the caller must `start_block` before the
/// next emit. A freshly-allocated block is pre-filled with `Return`, so even a
/// builder bug degrades to a stray early return, NEVER a dangling index.
///
/// INV-2 (no dangling): a block is allocated (`new_block`) before its id is
/// named in any terminator; `finish` seals the trailing open block with
/// `Return`. Every control-flow form below ends by `start_block`-ing its single
/// "continue point", so on return from `lower_stmt` the cursor is always open
/// and is where control flows next — the caller is structurally unable to leave
/// an arm dangling.
struct ProcessBuilder {
    body: Vec<ir::BasicBlock>,
    cur: Option<BlockId>,
}

impl ProcessBuilder {
    /// Start with one empty block (the entry, id 0) as the open cursor.
    fn new() -> Self {
        let mut pb = ProcessBuilder {
            body: Vec::new(),
            cur: None,
        };
        let entry = pb.new_block();
        pb.cur = Some(entry);
        pb
    }

    /// Allocate a fresh block, provisionally terminated `Return` (overwritten by
    /// `end_block_with` when sealed). Returns its process-local id.
    fn new_block(&mut self) -> BlockId {
        let id = BlockId(self.body.len() as u32);
        self.body.push(ir::BasicBlock {
            stmts: Vec::new(),
            term: ir::Terminator::Return,
        });
        id
    }

    /// Make `b` the open cursor (the caller asserts no other block is open).
    fn start_block(&mut self, b: BlockId) {
        debug_assert!(self.cur.is_none(), "start_block over an open cursor");
        self.cur = Some(b);
    }

    /// Record an already-built `StmtId` (from the global arena) in the current
    /// block. Stays in the same block (no split).
    fn push_stmt_id(&mut self, sid: u32) {
        let b = self.cur.expect("push_stmt_id with no open block (INV-1)");
        self.body[b.0 as usize].stmts.push(sid);
    }

    /// Seal the current block with `term` and CLOSE the cursor.
    fn end_block_with(&mut self, term: ir::Terminator) {
        let b = self
            .cur
            .take()
            .expect("end_block_with with no open block (double seal?)");
        self.body[b.0 as usize].term = term;
    }

    /// Seal current with `Goto(target)`; cursor closed.
    fn goto(&mut self, target: BlockId) {
        self.end_block_with(ir::Terminator::Goto {
            target: target.raw(),
        });
    }

    /// Final hand-off: seal the trailing open block with `Return`. entry = 0.
    fn finish(mut self) -> (Vec<ir::BasicBlock>, u32) {
        if self.cur.is_some() {
            self.end_block_with(ir::Terminator::Return);
        }
        (self.body, 0)
    }
}

impl<'s> Elaborator<'s> {
    /// Register a named SVA sequence into the module-global table (first-wins, with a
    /// redeclaration warning). Shared by the top-level prescan and the generate-scope
    /// collector (slice A4) so both keep identical first-wins semantics.
    fn register_seq_decl(&mut self, s: &ast::SeqDecl) {
        if self.seq_table.contains_key(&s.name.name) {
            self.warn(&format!(
                "sequence `{}` redeclared; first declaration used",
                s.name.name
            ));
        } else {
            self.seq_table.insert(s.name.name.clone(), s.clone());
        }
    }

    /// Register a named SVA property (first-wins + redeclare warning). See
    /// [`Self::register_seq_decl`].
    fn register_prop_decl(&mut self, p: &ast::PropDecl) {
        if self.prop_table.contains_key(&p.name.name) {
            self.warn(&format!(
                "property `{}` redeclared; first declaration used",
                p.name.name
            ));
        } else {
            self.prop_table.insert(p.name.name.clone(), p.clone());
        }
    }

    /// Collect `sequence`/`property` declarations from a generate block into the
    /// module-global tables (slice A4). Walks the generate STRUCTURE — For/If/Case/
    /// Block bodies and nested generates — WITHOUT const-eval or genvar binding: a
    /// declaration is a definition (registered once), not per-instance logic.
    /// Limitations (loud, never silent-wrong): both branches of a generate-if are
    /// collected (a same-named decl in each yields a benign redeclare warning,
    /// first-wins); a genvar-parameterized decl body keeps its unbound genvar, which
    /// is a loud unresolved-name at the use site.
    fn collect_gen_sva_decls(&mut self, items: &[ast::GenItem]) {
        for gi in items {
            match gi {
                ast::GenItem::Item(boxed) => match &**boxed {
                    ast::ModuleItem::SequenceDecl(s) => self.register_seq_decl(s),
                    ast::ModuleItem::PropertyDecl(p) => self.register_prop_decl(p),
                    ast::ModuleItem::Generate(g) => self.collect_gen_sva_decls(&g.items),
                    _ => {}
                },
                ast::GenItem::For { body, .. } => self.collect_gen_sva_decls(body),
                ast::GenItem::Block { items, .. } => self.collect_gen_sva_decls(items),
                ast::GenItem::If { then_b, else_b, .. } => {
                    self.collect_gen_sva_decls(then_b);
                    self.collect_gen_sva_decls(else_b);
                }
                ast::GenItem::Case { items, .. } => {
                    for it in items {
                        match it {
                            ast::GenCaseItem::Match { body, .. }
                            | ast::GenCaseItem::Default { body, .. } => {
                                self.collect_gen_sva_decls(body)
                            }
                        }
                    }
                }
            }
        }
    }

    /// Property-references-property (slice A4): if the consequent is a bare named
    /// OVERLAP property `q`, replace it with the boolean `!q.ante || q.cons` (the
    /// single-tick meaning of `q`'s `b |-> c`). A no-op for any other consequent
    /// (literal / sequence / net / non-property name) — byte-identical. A guard
    /// violation leaves a benign `1'b1` consequent (the loud diagnostic already gates
    /// the run), so there is no spurious fire on top of the error.
    fn flatten_prop_consequent(&mut self, sva: &mut PendingSva) {
        let sp = sva.span;
        let name = match &sva.cons {
            ast::Sequence::Boolean(e) => match &e.kind {
                ast::ExprKind::Ident(p) if p.segments.len() == 1 => p.segments[0].name.clone(),
                _ => return,
            },
            _ => return,
        };
        // A real net of the same name wins the leaf path (preserves byte-identity for
        // a design with a net named like a property); a non-property name is left for
        // the ordinary lowering (a loud undeclared-net if neither).
        if self.lookup_net_scoped(&name).is_some() || !self.prop_table.contains_key(&name) {
            return;
        }
        // Inner NON-OVERLAP property reference (slice SVA-R2): `a |-> (b |=> c)`
        // ≡ `(a && b) |=> c` — the obligation spans a clock, so (unlike A4's
        // overlap `!b || c`) it cannot collapse to a single-tick boolean. Only the
        // canonical shape folds: an OVERLAP outer with a BOOLEAN outer antecedent
        // `a`. Rewriting the top-level `sva` to `(a && b) |=> c` (kind=NonOverlap)
        // hands the 1-cycle skew to the existing top-level `|=>` pend-reg machinery
        // below. Everything else (a 2-cycle skew from an outer `|=>`, a sequence
        // outer antecedent, an inner property whose own sides are property refs)
        // falls through to the overlap flattener's loud `|=>`-as-consequent reject.
        if matches!(sva.kind, ast::ImplicationKind::Overlap) {
            let outer_ante = match &sva.ante {
                ast::Sequence::Boolean(a) => Some(a.clone()),
                _ => None,
            };
            if let Some(a) = outer_ante {
                if let Some((b, c)) = self.peel_nonoverlap_property(&name, &sva.clock) {
                    sva.ante = ast::Sequence::Boolean(sva_binary(ast::BinOp::LogAnd, a, b, sp));
                    sva.cons = ast::Sequence::Boolean(c);
                    sva.kind = ast::ImplicationKind::NonOverlap;
                    return;
                }
            }
        }
        match self.flatten_overlap_property(&name, &sva.clock, sp) {
            Some(b) => sva.cons = ast::Sequence::Boolean(b),
            None => sva.cons = ast::Sequence::Boolean(sva_one(sp)),
        }
    }

    /// Non-emitting probe (slice SVA-R2): returns `(inner_ante, inner_cons)` iff
    /// `name` is a clean single-clock NON-OVERLAP property `b |=> c` whose
    /// antecedent and consequent are both plain booleans (NOT themselves property
    /// references), with no formals / `disable iff` / consequent clock and the SAME
    /// single bare-ident clock as the outer assertion. Returns `None` silently for
    /// any other shape, so the caller falls through to the loud overlap flattener.
    fn peel_nonoverlap_property(
        &self,
        name: &str,
        clock: &ast::Sensitivity,
    ) -> Option<(ast::Expr, ast::Expr)> {
        let pd = self.prop_table.get(name)?;
        if !matches!(pd.implication_kind, ast::ImplicationKind::NonOverlap)
            || !pd.formals.is_empty()
            || pd.disable_iff.is_some()
            || pd.consequent_clock.is_some()
        {
            return None;
        }
        let outer = sva_clock_signal(clock);
        if outer.is_none() || outer != sva_clock_signal(&pd.clock) {
            return None;
        }
        let (ast::Sequence::Boolean(b), ast::Sequence::Boolean(c)) =
            (&pd.antecedent, &pd.consequent)
        else {
            return None;
        };
        // A bare property-name on either side is a deeper (nested) skew beyond this
        // slice → `None` → loud fallthrough.
        if self.is_property_name(b) || self.is_property_name(c) {
            return None;
        }
        Some((b.clone(), c.clone()))
    }

    /// True iff `e` is a single-segment identifier that names a declared property
    /// and NOT a net of the same name (a real net wins the leaf path).
    fn is_property_name(&self, e: &ast::Expr) -> bool {
        if let ast::ExprKind::Ident(p) = &e.kind {
            if p.segments.len() == 1 {
                let n = &p.segments[0].name;
                return self.lookup_net_scoped(n).is_none() && self.prop_table.contains_key(n);
            }
        }
        false
    }

    /// Flatten a named OVERLAP property `name` to the boolean `!ante || cons` (slice
    /// A4) — the single-tick meaning of `b |-> c`. Recurses when `cons` is itself a
    /// bare overlap-property reference (cycle-guarded via `sva_inline_stack`).
    /// Returns `None` (after emitting a loud diagnostic) for any unsupported inner
    /// form: a different clock (multi-clock), `disable iff`, a consequent clock,
    /// formal arguments, a non-overlap `|=>`, a non-boolean antecedent/consequent, or
    /// recursion.
    fn flatten_overlap_property(
        &mut self,
        name: &str,
        clock: &ast::Sensitivity,
        sp: ast::Span,
    ) -> Option<ast::Expr> {
        if self.sva_inline_stack.iter().any(|n| n == name) {
            self.error(
                MsgCode::ElabUnsupported,
                &format!("recursive property `{name}` is illegal (IEEE 1800 §16.12)"),
            );
            return None;
        }
        let pd = self.prop_table.get(name).cloned()?;
        if !pd.formals.is_empty() {
            self.error(
                MsgCode::ElabUnsupported,
                "a parameterized property as a consequent is unsupported in this subset",
            );
            return None;
        }
        // Span-insensitive clock match: both must be the SAME single bare-ident edge.
        let outer = sva_clock_signal(clock);
        if pd.consequent_clock.is_some() || outer.is_none() || outer != sva_clock_signal(&pd.clock)
        {
            self.error(
                MsgCode::ElabUnsupported,
                "a named property consequent with a different / multi-clock clocking \
                 event is unsupported in this subset",
            );
            return None;
        }
        if pd.disable_iff.is_some() {
            self.error(
                MsgCode::ElabUnsupported,
                "a named property consequent with its own `disable iff` is unsupported \
                 in this subset",
            );
            return None;
        }
        if !matches!(pd.implication_kind, ast::ImplicationKind::Overlap) {
            self.error(
                MsgCode::ElabUnsupported,
                "a named `|=>` property used as a consequent is unsupported (overlap \
                 `|->` only in this subset)",
            );
            return None;
        }
        let ast::Sequence::Boolean(ante_e) = &pd.antecedent else {
            self.error(
                MsgCode::ElabUnsupported,
                "a named property consequent with a sequence antecedent is unsupported \
                 in this subset",
            );
            return None;
        };
        let ante_e = ante_e.clone();
        self.sva_inline_stack.push(name.to_string());
        // The inner consequent: a boolean leaf, or itself a bare overlap-property ref.
        let cons_b = match &pd.consequent {
            ast::Sequence::Boolean(e) => match &e.kind {
                ast::ExprKind::Ident(p)
                    if p.segments.len() == 1
                        && self.lookup_net_scoped(&p.segments[0].name).is_none()
                        && self.prop_table.contains_key(&p.segments[0].name) =>
                {
                    let inner = p.segments[0].name.clone();
                    self.flatten_overlap_property(&inner, clock, sp)
                }
                _ => Some(e.clone()),
            },
            _ => {
                self.error(
                    MsgCode::ElabUnsupported,
                    "a named property consequent with a sequence consequent is \
                     unsupported in this subset",
                );
                None
            }
        };
        self.sva_inline_stack.pop();
        let cons_b = cons_b?;
        // `b |-> c` at one tick ≡ `!b || c`.
        Some(sva_binary(
            ast::BinOp::LogOr,
            sva_unary(ast::UnOp::LogNot, ante_e, sp),
            cons_b,
            sp,
        ))
    }

    /// Synthesize a fresh `Reg` for an SVA helper (`|=>` pending bit / sampled-
    /// value prev register), returning its name so the synthesized checker AST
    /// can reference it by `Ident`. Mirrors `fresh_ia_tmp`. Init is the default
    /// `Reg` X — an X helper makes the first-clock `if (pend && …)` / `$rose`
    /// false, so there is no spurious violation before any value has been sampled.
    fn fresh_sva_reg(&mut self, width: u32, tag: &str) -> String {
        let w = width.max(1);
        let name = format!("__sva_{tag}_{}", self.nets.len());
        let nv = ir::NetVar {
            kind: ir::NetKind::Reg,
            width: w,
            msb: w.saturating_sub(1),
            lsb: 0,
            signed: false,
            array_len: 1,
            dir: ir::PortDir::Internal,
            init: default_init(ast::NetVarKind::Reg, w),
        };
        self.add_net(&name, nv);
        name
    }

    /// Multi-clock canonical pattern (slice A3): `@(c1) ante |=> @(c2) cons`. The
    /// (boolean) antecedent is sampled on c1 into a 1-bit handoff reg, and a SECOND
    /// synthesized process — clocked by c2 — consumes the handoff on its next c2 edge
    /// to check the (boolean) consequent:
    ///   always @(c1) handoff <= |ante;
    ///   always @(c2) if (handoff && !cons) $error(...);
    /// Pure IR-0 two-process synthesis (sim-ir untouched). The two sides use SEPARATE
    /// `SvaRegs`, so a `$past` in the antecedent samples on c1 and one in the
    /// consequent samples on c2 — each on its own clock, no cross-clock aliasing.
    ///
    /// TIE SEMANTICS (oracle-free, hand-IEEE pin): when c1 and c2 tick the same
    /// instant the c2 process reads the PRIOR-edge handoff (proc A's `handoff <= |ante`
    /// is an NBA that settles in the NBA region, after the c2 process's Active-region
    /// read). This is the conservative `|=>`-on-next-consume-edge reading; it is
    /// tool-divergent and unverifiable (iverilog rejects SVA), so it is pinned by a
    /// determinism test, not claimed IEEE-conformant.
    ///
    /// Everything outside the canonical shape is LOUD: `|->` with a consequent clock
    /// (parser), an OR-of-clocks / `@(*)` on either side, a multi-term sequence
    /// antecedent/consequent, and `disable iff` / a custom action block combined with
    /// a second clock (their sampling clock is ambiguous — deferred).
    fn synth_multiclock(&mut self, sva: PendingSva, sp: ast::Span) {
        let cons_clock = sva.cons_clock.clone().expect("cons_clock is Some");
        // `|=>` only (the parser only attaches a consequent clock to `|=>`).
        if !matches!(sva.kind, ast::ImplicationKind::NonOverlap) {
            self.error(
                MsgCode::ElabUnsupported,
                "a consequent clocking event requires `|=>` (non-overlapping implication)",
            );
            return;
        }
        // The consequent clock must be a single edge-event (no OR-of-clocks / `@(*)`).
        let c2_single = matches!(&cons_clock, ast::Sensitivity::List(evs) if evs.len() == 1);
        if !c2_single {
            self.error(
                MsgCode::ElabUnsupported,
                "the consequent clocking event must be a single edge (an OR-of-clocks / \
                 `@(*)` consequent clock is unsupported in this subset)",
            );
            return;
        }
        // v1 restricts both sides to a boolean (a multi-term sequence across two clocks
        // is deferred).
        let ast::Sequence::Boolean(ante_e) = &sva.ante else {
            self.error(
                MsgCode::ElabUnsupported,
                "a multi-clock property's antecedent must be a boolean in this subset \
                 (a sequence antecedent with a consequent clock is deferred)",
            );
            return;
        };
        let ast::Sequence::Boolean(cons_e) = &sva.cons else {
            self.error(
                MsgCode::ElabUnsupported,
                "a multi-clock property's consequent must be a boolean in this subset \
                 (a sequence consequent under a second clock is deferred)",
            );
            return;
        };
        // `disable iff` / a custom action block with a second clock is deferred: the
        // sampling/reset clock becomes ambiguous across the two processes.
        if sva.disable_iff.is_some() || sva.pass.is_some() || sva.fail.is_some() {
            self.error(
                MsgCode::ElabUnsupported,
                "`disable iff` / a custom action block combined with a consequent clock \
                 is unsupported in this subset",
            );
            return;
        }

        // 1-bit handoff reg (X-init like `pend`, so no spurious fire before c1 ticks).
        let handoff = self.fresh_sva_reg(1, "mc_pend");

        let handoff_path = ast::HierPath {
            segments: vec![ast::Ident {
                name: handoff.clone(),
                span: sp,
            }],
            span: sp,
        };

        // PROCESS A @ c1: SET-only `if (|ante) handoff <= 1'b1;` (the `|=>` obligation
        // persists until the CONSUMER discharges it — a later `ante`=0 c1 edge must
        // NOT clear a pending obligation), plus the antecedent's prev-reg NBAs (c1).
        // (review 2026-06-16: a level-held `handoff <= |ante` re-fired on every c2
        // edge in the window when c2 is faster than c1, and dropped an obligation on a
        // c1 edge with ante=0.)
        let mut regs_a = SvaRegs::default();
        let ante_b = self.rewrite_sampled(ante_e, &mut regs_a);
        let set_handoff = ast::Stmt::If {
            cond: sva_unary(ast::UnOp::RedOr, ante_b, sp),
            then_s: Box::new(ast::Stmt::NonBlocking {
                lhs: ast::Lvalue::Ident(handoff_path.clone()),
                delay: None,
                rhs: sva_one(sp),
                span: sp,
            }),
            else_s: None,
            span: sp,
        };
        let mut body_a = vec![set_handoff];
        body_a.extend(regs_a.nbas);
        let proc_a = self.lower_proc_block(&ast::ProceduralBlock {
            kind: ast::ProcKind::Always,
            sensitivity: Some(sva.clock.clone()),
            body: Box::new(sva_block_or_single(body_a, sp)),
            span: sp,
        });
        self.push_process(proc_a);

        // PROCESS B @ c2: CHECK + DISCHARGE — `if (handoff) begin if (!cons)
        // $error(...); handoff <= 1'b0; end` — so each match is consumed at EXACTLY
        // ONE c2 edge (single-shot obligation, not a level flag), plus the
        // consequent's prev-reg NBAs (sampled on c2). The X-init handoff keeps
        // `if (handoff)` from firing/discharging before the first c1 match.
        let mut regs_b = SvaRegs::default();
        let cons_b = self.rewrite_sampled(cons_e, &mut regs_b);
        let fire = ast::Stmt::If {
            cond: sva_unary(ast::UnOp::LogNot, cons_b, sp),
            then_s: Box::new(ast::Stmt::SysTaskCall {
                name: ast::Ident {
                    name: "$error".to_string(),
                    span: sp,
                },
                args: vec![ast::Expr {
                    kind: ast::ExprKind::StrLit {
                        raw: "\"Assertion property violation\"".to_string(),
                    },
                    span: sp,
                }],
                span: sp,
            }),
            else_s: None,
            span: sp,
        };
        let discharge = ast::Stmt::NonBlocking {
            lhs: ast::Lvalue::Ident(handoff_path),
            delay: None,
            rhs: sva_zero(sp),
            span: sp,
        };
        let consume = ast::Stmt::If {
            cond: sva_ident_expr(&handoff, sp),
            then_s: Box::new(ast::Stmt::Block {
                label: None,
                decls: Vec::new(),
                stmts: vec![fire, discharge],
                span: sp,
            }),
            else_s: None,
            span: sp,
        };
        let mut body_b = vec![consume];
        body_b.extend(regs_b.nbas);
        let proc_b = self.lower_proc_block(&ast::ProceduralBlock {
            kind: ast::ProcKind::Always,
            sensitivity: Some(cons_clock),
            body: Box::new(sva_block_or_single(body_b, sp)),
            span: sp,
        });
        self.push_process(proc_b);
    }

    /// v8 SVA: drain `pending_sva` into synthesized clocked checker processes.
    /// `assert property(@(clk) ante |-> cons)` ≡ `always @(clk) if (ante &&
    /// !cons) $error(...)`. For `|=>` (non-overlapping) the antecedent is delayed
    /// one clock through a pending reg: `always @(clk) begin if (pend && !cons)
    /// $error(...); pend <= ante; end` — the check reads the PRIOR clock's
    /// antecedent, then samples this clock's. The `$error` reuses the immediate-
    /// assert severity shape (routes to the diagnostic stream + exit class 1).
    fn materialize_sva_checkers(&mut self) {
        let pending = std::mem::take(&mut self.pending_sva);
        for mut sva in pending {
            let sp = sva.span;
            // A concurrent assertion must have a SINGLE clocking event (slice
            // S15). An OR-of-clocks event `@(posedge c1 or posedge c2)` (a
            // `Sensitivity::List` with >1 term) or `@(*)` is a multi-clock
            // property — the single-`always` checker model does not implement it.
            // Reject it loudly instead of building one (semantically wrong)
            // `always @(c1 or c2)` checker (this closes a silent-accept hole).
            // Mid-property second-`@` events are caught earlier by the parser.
            let single_clock = matches!(&sva.clock, ast::Sensitivity::List(evs) if evs.len() == 1);
            if !single_clock {
                self.error(
                    MsgCode::ElabUnsupported,
                    "a concurrent assertion must have a single clocking event \
                     (multi-clock / OR-of-clocks property clocks are unsupported \
                     in this subset)",
                );
                continue;
            }
            // Multi-clock canonical pattern (slice A3): `@(c1) ante |=> @(c2) cons`
            // synthesizes TWO processes (a c1-clocked sampler + a c2-clocked consumer)
            // joined by a 1-bit handoff reg, instead of the single-clock checker below.
            // Single-clock asserts (the common case) keep the byte-identical path.
            if sva.cons_clock.is_some() {
                self.synth_multiclock(sva, sp);
                continue;
            }
            // Property-references-property (slice A4): a bare named-PROPERTY consequent
            // `… |-> q` (q an OVERLAP property, same clock) flattens to the boolean
            // `!q.ante || q.cons`. A no-op for a literal / sequence / net consequent
            // (byte-identical), so it runs before the prev-reg allocation below to keep
            // the single-property path's numbering unchanged.
            self.flatten_prop_consequent(&mut sva);
            // Rewrite sampled-value functions ($past/$rose/$fell/$stable) into
            // reads of synthesized prev-registers, collecting the per-clock NBA
            // updates (`prev <= signal`) that maintain them.
            let mut regs = SvaRegs::default();
            // Expand the antecedent Sequence into a disjunction of (boolean-term,
            // hop-delay) alternatives, synthesize each one's match-this-clock
            // signal (a shift-register pipeline for ≥2 terms), and OR them. A
            // single 1-term alternative reproduces the flat-property path
            // byte-for-byte; bounded ranges produce >1 alternative.
            let mut pipeline_nbas: Vec<ast::Stmt> = Vec::new();
            // Peel a top-level NAMED-sequence reference to its declared body FIRST, so
            // a named sequence whose body is a top-level `within` reaches synth_within
            // exactly like the literal-antecedent path — otherwise the inlined `within`
            // body hit the unconditional reject in expand_sequence's Within arm (review
            // 2026-06-16: named ≠ inline for `within`). Cycle-guarded; byte-identical
            // for a literal antecedent (no top-level name to peel) and for a named
            // non-`within` antecedent (the body still flows through expand_sequence).
            let resolved_ante = self.resolve_named_top(&sva.ante);
            let ante = if let ast::Sequence::Within { seq1, seq2 } = &resolved_ante {
                // `seq1 within seq2` combines two sub-pipelines — synthesized
                // whole rather than as a (term, hop) alternative list.
                self.synth_within(seq1, seq2, &mut regs, &mut pipeline_nbas, sp)
            } else {
                let mut alternatives = self.expand_sequence(&resolved_ante, &mut regs);
                if alternatives.len() > SVA_SEQ_ALT_CAP {
                    self.error(
                        MsgCode::ElabUnsupported,
                        &format!(
                            "an SVA sequence expanded to {} alternatives (cap {}); narrow the bounded ranges",
                            alternatives.len(),
                            SVA_SEQ_ALT_CAP
                        ),
                    );
                    alternatives.truncate(SVA_SEQ_ALT_CAP);
                }
                let match_sigs: Vec<ast::Expr> = alternatives
                    .into_iter()
                    .map(|(terms, guard)| {
                        // Flat byte-identical path: a single PLAIN BOOLEAN term
                        // with no throughout guard reproduces the old `ante`
                        // exactly. A single goto/nonconsec term still needs the
                        // FSM (synth).
                        if terms.len() == 1 && guard.is_none() {
                            if let SeqTerm::Bool(_) = terms[0].0 {
                                let (SeqTerm::Bool(e), _) = terms.into_iter().next().unwrap()
                                else {
                                    unreachable!()
                                };
                                return e;
                            }
                        }
                        self.synth_seq_pipeline(terms, guard, &mut pipeline_nbas, sp)
                    })
                    .collect();
                // OR the alternatives' match signals. A single signal stays raw
                // (flat byte-identical); multiple are each reduced to a boolean
                // (reduction-OR) before the bitwise OR.
                if match_sigs.len() == 1 {
                    match_sigs.into_iter().next().unwrap()
                } else {
                    let mut it = match_sigs.into_iter();
                    let mut acc = sva_unary(ast::UnOp::RedOr, it.next().unwrap(), sp);
                    for m in it {
                        let mb = sva_unary(ast::UnOp::RedOr, m, sp);
                        acc = sva_binary(ast::BinOp::BitOr, acc, mb, sp);
                    }
                    acc
                }
            };
            // Consequent (slice S14). A boolean consequent is rewritten here (so
            // its prev-reg allocation order — and the byte-identical lowering —
            // is preserved); a sequence consequent is built as an obligation
            // chain AFTER `cond_lhs` is known (it seeds the chain).
            let cons_boolean = match &sva.cons {
                ast::Sequence::Boolean(e) => Some(self.rewrite_sampled(e, &mut regs)),
                _ => None,
            };

            // Action block (slice S11). The fail action — the `else` statement, or
            // the default `$error("Assertion property violation")` when absent —
            // runs on a violation; the optional pass action runs on a non-vacuous
            // success. When both are absent the body is byte-identical to the
            // pre-S11 checker (default $error, no pass branch).
            let fail_stmt_raw = match sva.fail {
                Some(s) => *s,
                None => ast::Stmt::SysTaskCall {
                    name: ast::Ident {
                        name: "$error".to_string(),
                        span: sp,
                    },
                    args: vec![ast::Expr {
                        kind: ast::ExprKind::StrLit {
                            raw: "\"Assertion property violation\"".to_string(),
                        },
                        span: sp,
                    }],
                    span: sp,
                },
            };
            let pass_action_raw = sva.pass;
            // `disable iff (expr)` reset (slice S12): a 1-bit reduction of the
            // (sampled) condition. When present, fire conditions are gated with
            // `!dis` and every obligation NBA is reset to 0 on the dis clock, so
            // in-flight attempts are aborted. Absent → the body is byte-identical
            // to the pre-S12 checker.
            let dis = sva
                .disable_iff
                .as_ref()
                .map(|e| sva_unary(ast::UnOp::RedOr, self.rewrite_sampled(e, &mut regs), sp));
            // Action-block sampled values (slice A2): rewrite $past/$rose/$fell/$stable
            // inside the fail/pass action statements to the SAME shared prev-regs the
            // property body uses. Done AFTER the antecedent/consequent/disable rewrites
            // so those keep the lower net IDs and an action `$past(sig)` of an
            // already-sampled signal dedups onto the existing prev-reg (regs.by_signal).
            // A no-sampled action allocates ZERO nets → byte-identical to pre-A2.
            let fail_stmt = self.rewrite_sampled_stmt(&fail_stmt_raw, &mut regs);
            let pass_action =
                pass_action_raw.map(|ps| Box::new(self.rewrite_sampled_stmt(&ps, &mut regs)));
            let (cond_lhs, pending_nba) = match sva.kind {
                ast::ImplicationKind::Overlap => (ante, None),
                ast::ImplicationKind::NonOverlap => {
                    // 1-bit pending reg: NBA-sampled with the antecedent's BOOLEAN
                    // truthiness each clock (reduction-OR, so a multi-bit antecedent
                    // is not truncated to its LSB), checked against the consequent
                    // on the FOLLOWING clock.
                    let pend = self.fresh_sva_reg(1, "pend");
                    let pend_path = ast::HierPath {
                        segments: vec![ast::Ident {
                            name: pend.clone(),
                            span: sp,
                        }],
                        span: sp,
                    };
                    let nba = ast::Stmt::NonBlocking {
                        lhs: ast::Lvalue::Ident(pend_path),
                        delay: None,
                        rhs: sva_unary(ast::UnOp::RedOr, ante, sp),
                        span: sp,
                    };
                    (sva_ident_expr(&pend, sp), Some(nba))
                }
            };
            // Consequent core (slice S14): the violation and (non-vacuous)
            // success signals. A boolean consequent is `cond_lhs && !cons` /
            // `cond_lhs && cons` (byte-identical to before S14); a sequence
            // consequent is an obligation chain whose due-delay regs are
            // obligation state (reset by `disable iff` like the antecedent).
            let mut cons_chain_nbas: Vec<ast::Stmt> = Vec::new();
            let (violation_core, success_core) = match cons_boolean {
                Some(cons) => (
                    sva_binary(
                        ast::BinOp::LogAnd,
                        cond_lhs.clone(),
                        sva_unary(ast::UnOp::LogNot, cons.clone(), sp),
                        sp,
                    ),
                    sva_binary(ast::BinOp::LogAnd, cond_lhs.clone(), cons, sp),
                ),
                None => self.build_seq_consequent(
                    &sva.cons,
                    &cond_lhs,
                    &mut regs,
                    &mut cons_chain_nbas,
                    sp,
                ),
            };
            // violation gated by `!dis`.
            let mut violation = violation_core;
            if let Some(d) = &dis {
                violation = sva_binary(
                    ast::BinOp::LogAnd,
                    sva_unary(ast::UnOp::LogNot, d.clone(), sp),
                    violation,
                    sp,
                );
            }
            let if_fail = ast::Stmt::If {
                cond: violation,
                then_s: Box::new(fail_stmt),
                else_s: None,
                span: sp,
            };
            // Clocked body: check FIRST (reads the prior clock's prev/pend), then
            // the NBA updates apply in the NBA region for the next clock.
            let mut stmts = vec![if_fail];
            // Pass action (if any) runs on a NON-VACUOUS success: antecedent
            // matched AND consequent held (vacuous success — antecedent false —
            // does not fire it; a hand-IEEE choice, documented). Also gated `!dis`.
            if let Some(ps) = pass_action {
                let mut success = success_core;
                if let Some(d) = &dis {
                    success = sva_binary(
                        ast::BinOp::LogAnd,
                        sva_unary(ast::UnOp::LogNot, d.clone(), sp),
                        success,
                        sp,
                    );
                }
                stmts.push(ast::Stmt::If {
                    cond: success,
                    then_s: ps,
                    else_s: None,
                    span: sp,
                });
            }
            // `disable iff` reset: clear in-flight obligation state (antecedent
            // pipeline + consequent chain + |=> pend NBAs) when dis is true. The
            // prev-sampling NBAs (regs.nbas) keep sampling — only the attempt
            // obligations are aborted.
            let (pipeline_nbas, cons_chain_nbas, pending_nba) = if let Some(d) = &dis {
                (
                    pipeline_nbas
                        .into_iter()
                        .map(|s| gate_nba_with_disable(s, d, sp))
                        .collect::<Vec<_>>(),
                    cons_chain_nbas
                        .into_iter()
                        .map(|s| gate_nba_with_disable(s, d, sp))
                        .collect::<Vec<_>>(),
                    pending_nba.map(|s| gate_nba_with_disable(s, d, sp)),
                )
            } else {
                (pipeline_nbas, cons_chain_nbas, pending_nba)
            };
            stmts.extend(regs.nbas);
            stmts.extend(pipeline_nbas);
            stmts.extend(cons_chain_nbas);
            if let Some(nba) = pending_nba {
                stmts.push(nba);
            }
            let body = if stmts.len() == 1 {
                stmts.pop().unwrap()
            } else {
                ast::Stmt::Block {
                    label: None,
                    decls: Vec::new(),
                    stmts,
                    span: sp,
                }
            };
            let pb = ast::ProceduralBlock {
                kind: ast::ProcKind::Always,
                sensitivity: Some(sva.clock),
                body: Box::new(body),
                span: sp,
            };
            let proc = self.lower_proc_block(&pb);
            self.push_process(proc);
        }
    }

    /// Reject an SVA repetition count that exceeds the synthesis cap
    /// (`SVA_SEQ_ALT_CAP`). Every repetition count synthesizes O(count) 1-bit
    /// helper regs (goto/nonconsec/unbounded-consec FSMs) or fans a bounded
    /// `[*n]` into an n-term shift pipeline, so an absurd literal would hang
    /// elaboration; this caps it loudly, mirroring the post-expansion alternative
    /// cap and the bounded-range / `within` guards. Returns `false` (with the
    /// error already emitted) when the count is over the cap.
    fn sva_count_within_cap(&mut self, count: u32, what: &str) -> bool {
        if count as usize > SVA_SEQ_ALT_CAP {
            self.error(
                MsgCode::ElabUnsupported,
                &format!(
                    "an SVA {what} count {count} exceeds the cap {SVA_SEQ_ALT_CAP}; narrow it"
                ),
            );
            false
        } else {
            true
        }
    }

    /// Expand a `Sequence` into a DISJUNCTION of conjunctive term-lists — each a
    /// `Vec<(boolean-term, hop-delay)>` where `hop-delay` is the `##d` cycle gap
    /// BEFORE that term (the first term's delay is unused — it is the seed). A
    /// bounded range `##[m:n]` / `[*m:n]` fans out into `n-m+1` (or a product of
    /// such) alternatives; the antecedent matches if ANY alternative completes.
    /// `[*k]` repetitions expand to `##1` chains. Each leaf term is passed
    /// through `rewrite_sampled` (deduped by signal), so a sampled-value fn
    /// inside a sequence term still works and is allocated once.
    /// Inline a named sequence INSTANCE: cycle-guard, then expand the declared
    /// body (which may itself reference other named sequences — handled by the
    /// recursion). A self/mutual-recursive sequence (IEEE 1800 §16.8: illegal) is
    /// rejected loud and yields a never-matching `1'b0` alternative so elaboration
    /// continues. Parameterized decls are rejected loud (reserved for a follow-on).
    fn inline_named_sequence(
        &mut self,
        decl: &ast::SeqDecl,
        args: &[ast::Expr],
        regs: &mut SvaRegs,
    ) -> Vec<SeqAlt> {
        // Positional formal-argument binding (slice A1). Arity mismatch (including a
        // non-parameterized sequence given args, or vice versa) is loud.
        if decl.formals.len() != args.len() {
            self.error(
                MsgCode::ElabUnsupported,
                &format!(
                    "named sequence `{}` expects {} formal argument(s), got {}",
                    decl.name.name,
                    decl.formals.len(),
                    args.len()
                ),
            );
            return sva_never_alt(&decl.body);
        }
        if self.sva_inline_stack.iter().any(|n| n == &decl.name.name) {
            self.error(
                MsgCode::ElabUnsupported,
                &format!(
                    "recursive sequence `{}` is illegal (IEEE 1800 §16.8)",
                    decl.name.name
                ),
            );
            return sva_never_alt(&decl.body);
        }
        // The no-formal path clones (then expands) the body, structurally identical
        // to expanding `&decl.body` directly → byte-identical to before slice A1.
        let body = if decl.formals.is_empty() {
            decl.body.clone()
        } else {
            subst_sequence(&decl.body, &sva_formal_map(&decl.formals, args))
        };
        self.sva_inline_stack.push(decl.name.name.clone());
        let out = self.expand_sequence(&body, regs);
        self.sva_inline_stack.pop();
        out
    }

    /// Peel a TOP-LEVEL named-sequence reference (a bare-ident `Boolean` or an
    /// `Instance`) to its declared body, recursing through a chain (`s1`→`s2`→body),
    /// so the materialize dispatch sees the real top-level shape (notably a top-level
    /// `within`). Returns an owned clone; non-name shapes (Delay/Repeat/literal
    /// Within/…) and unknown names are returned as-is (their nested named references
    /// are still resolved later by `expand_sequence`). Cycle-guarded: a recursive top
    /// sequence is loud and collapses to `1'b0`.
    fn resolve_named_top(&mut self, seq: &ast::Sequence) -> ast::Sequence {
        let name = match seq {
            ast::Sequence::Boolean(e) => match &e.kind {
                ast::ExprKind::Ident(p) if p.segments.len() == 1 => {
                    Some(p.segments[0].name.clone())
                }
                _ => None,
            },
            ast::Sequence::Instance { name, args, .. } if args.is_empty() => {
                Some(name.name.clone())
            }
            _ => None,
        };
        let Some(name) = name else {
            return seq.clone();
        };
        let Some(decl) = self.seq_table.get(&name).cloned() else {
            return seq.clone(); // a real net / unknown name — leave it for expand_sequence
        };
        // A bare top-level reference (`s |-> …`) passes ZERO actuals; a parameterized
        // sequence needs its formals bound. Mirror `inline_named_sequence`'s arity
        // error (review 2026-06-16: this path was peeling `decl.body` with the formals
        // left as net references — silent-wrong when a formal name shadowed a real
        // net). Every sibling path (expand_sequence Boolean/Call/Instance, property
        // collect) already arity-checks; close the hole here too.
        if !decl.formals.is_empty() {
            self.error(
                MsgCode::ElabUnsupported,
                &format!(
                    "named sequence `{}` expects {} formal argument(s), got 0",
                    name,
                    decl.formals.len()
                ),
            );
            return ast::Sequence::Boolean(sva_zero(decl.span));
        }
        if self.sva_inline_stack.iter().any(|n| n == &name) {
            self.error(
                MsgCode::ElabUnsupported,
                &format!("recursive sequence `{}` is illegal (IEEE 1800 §16.8)", name),
            );
            return ast::Sequence::Boolean(sva_zero(decl.span));
        }
        self.sva_inline_stack.push(name);
        let r = self.resolve_named_top(&decl.body);
        self.sva_inline_stack.pop();
        r
    }

    fn expand_sequence(&mut self, seq: &ast::Sequence, regs: &mut SvaRegs) -> Vec<SeqAlt> {
        match seq {
            ast::Sequence::Boolean(e) => {
                // A bare single-segment identifier that names a declared sequence is
                // a sequence INSTANCE — inline its body (cycle-guarded). Anything
                // else (a real net, an expression) is an ordinary boolean leaf, so a
                // net and a sequence of the same name coexist (lookup miss → leaf).
                if let ast::ExprKind::Ident(path) = &e.kind {
                    if path.segments.len() == 1 {
                        if let Some(decl) = self.seq_table.get(&path.segments[0].name).cloned() {
                            return self.inline_named_sequence(&decl, &[], regs);
                        }
                    }
                }
                // A `Call` whose callee names a declared sequence is a PARAMETERIZED
                // sequence instance `s(a,b)` (it parses as a boolean-leaf `Call` in a
                // sequence body / antecedent). Bind the actuals and inline. A callee
                // that is NOT a declared sequence falls through to the ordinary
                // boolean leaf (an actual user function call → the usual lowering).
                if let ast::ExprKind::Call { name, args } = &e.kind {
                    if name.segments.len() == 1 {
                        if let Some(decl) = self.seq_table.get(&name.segments[0].name).cloned() {
                            return self.inline_named_sequence(&decl, args, regs);
                        }
                    }
                }
                let term = self.rewrite_sampled(e, regs);
                vec![(vec![(SeqTerm::Bool(term), SeqHop::Fixed(0))], None)]
            }
            // An explicit named instance reaching a sequence position (a property
            // instance is spliced at collect time and never gets here; this arm
            // covers a named SEQUENCE instance / future forms): resolve it against
            // the sequence table and inline. Unknown name / non-empty args are loud.
            ast::Sequence::Instance { name, args, .. } => {
                match self.seq_table.get(&name.name).cloned() {
                    // Inline (binding `args` to the declared formals — slice A1).
                    Some(decl) => self.inline_named_sequence(&decl, args, regs),
                    None => {
                        self.error(
                            MsgCode::ElabUnsupported,
                            &format!("unknown sequence `{}`", name.name),
                        );
                        sva_never_alt(seq)
                    }
                }
            }
            ast::Sequence::Delay {
                min, max, lhs, rhs, ..
            } => {
                let ls = self.expand_sequence(lhs, regs);
                let rs = self.expand_sequence(rhs, regs);
                let mut out = Vec::new();
                // An unbounded `##[m:$]` cannot fan out — it becomes one
                // `AtLeast(m)` hop (synthesized as a latch). A bounded `##[m:n]`
                // fans into the n-m+1 `Fixed(d)` delay alternatives.
                let hops: Vec<SeqHop> = match max {
                    None => vec![SeqHop::AtLeast(*min)],
                    Some(n) => (*min..=*n).map(SeqHop::Fixed).collect(),
                };
                for hop in hops {
                    for (lt, lg) in &ls {
                        for (rt, rg) in &rs {
                            let mut combined = lt.clone();
                            let mut r2 = rt.clone();
                            // The first term of `rhs` is reached via `hop` after
                            // the last term of `lhs`.
                            if let Some(first) = r2.first_mut() {
                                first.1 = hop;
                            }
                            combined.extend(r2);
                            out.push((combined, and_opt(lg.clone(), rg.clone(), seq_span(lhs))));
                        }
                    }
                }
                out
            }
            ast::Sequence::Repeat {
                seq,
                min,
                kind: kind @ (ast::RepeatKind::Goto | ast::RepeatKind::Nonconsec),
                ..
            } => {
                // goto `[->n]` / nonconsec `[=n]` synthesize an existence-latch
                // FSM rather than a fixed shift, so they become a single FSM
                // term (boolean operand only; `min == max == n`).
                let n = (*min).max(1);
                if !self.sva_count_within_cap(n, "goto/nonconsec repetition") {
                    return sva_never_alt(seq);
                }
                let ast::Sequence::Boolean(b) = &**seq else {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "goto/nonconsec repetition requires a boolean operand in this subset",
                    );
                    return vec![(
                        vec![(SeqTerm::Bool(sva_one(seq_span(seq))), SeqHop::Fixed(0))],
                        None,
                    )];
                };
                let bt = self.rewrite_sampled(b, regs);
                let term = match kind {
                    ast::RepeatKind::Goto => SeqTerm::Goto(bt, n),
                    _ => SeqTerm::Nonconsec(bt, n),
                };
                vec![(vec![(term, SeqHop::Fixed(0))], None)]
            }
            ast::Sequence::Repeat {
                seq,
                min,
                max: None,
                kind: ast::RepeatKind::Consec,
            } => {
                // `b[*m:$]` — unbounded consecutive repeat (≥ m). Cannot fan out;
                // synthesize a gated run-latch (a single ConsecAtLeast term).
                // Boolean operand only (S8 goto/nonconsec precedent).
                let m = (*min).max(1);
                if !self.sva_count_within_cap(m, "unbounded consecutive repetition") {
                    return sva_never_alt(seq);
                }
                let ast::Sequence::Boolean(b) = &**seq else {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "unbounded consecutive repetition `[*m:$]` requires a boolean operand in this subset",
                    );
                    return vec![(
                        vec![(SeqTerm::Bool(sva_one(seq_span(seq))), SeqHop::Fixed(0))],
                        None,
                    )];
                };
                let bt = self.rewrite_sampled(b, regs);
                vec![(
                    vec![(SeqTerm::ConsecAtLeast(bt, m), SeqHop::Fixed(0))],
                    None,
                )]
            }
            ast::Sequence::Repeat {
                seq,
                min,
                max,
                kind: ast::RepeatKind::Consec,
            } => {
                let base = self.expand_sequence(seq, regs);
                let lo = (*min).max(1);
                let hi = max.unwrap_or(*min).max(lo);
                // Cap the upper count: each copy adds `base`'s terms to every
                // alternative (an `n`-term shift pipeline for the exact `[*n]`
                // case, which the post-expansion alternative-COUNT cap misses),
                // so an absurd literal would hang the fan-out below.
                if !self.sva_count_within_cap(hi, "consecutive repetition") {
                    return sva_never_alt(seq);
                }
                let mut out = Vec::new();
                'kloop: for k in lo..=hi {
                    // k copies of `base`, each copy after the first prefixed with
                    // `##1`. A multi-alternative base makes this a k-fold product.
                    let mut combos: Vec<SeqAlt> = vec![(Vec::new(), None)];
                    for i in 0..k {
                        let mut next = Vec::new();
                        for (pterms, pg) in &combos {
                            for (bterms, bg) in &base {
                                let mut copy = bterms.clone();
                                if i > 0 {
                                    if let Some(first) = copy.first_mut() {
                                        first.1 = SeqHop::Fixed(1);
                                    }
                                }
                                let mut merged = pterms.clone();
                                merged.extend(copy);
                                let sp = seq_span(seq);
                                next.push((merged, and_opt(pg.clone(), bg.clone(), sp)));
                            }
                        }
                        combos = next;
                        // Guard the k-fold PRODUCT of a multi-alternative base
                        // (e.g. `(a ##[1:2] b)[*1:20]` = 2^20) from exploding the
                        // build before the post-expansion cap can truncate it.
                        if out.len() + combos.len() > SVA_SEQ_ALT_CAP {
                            self.error(
                                MsgCode::ElabUnsupported,
                                &format!(
                                    "an SVA bounded repetition expanded past the cap {SVA_SEQ_ALT_CAP}; narrow the ranges"
                                ),
                            );
                            break 'kloop;
                        }
                    }
                    out.extend(combos);
                }
                out
            }
            ast::Sequence::Throughout { cond, seq } => {
                let inner = self.expand_sequence(seq, regs);
                let sp = cond.span;
                let g = sva_unary(ast::UnOp::RedOr, self.rewrite_sampled(cond, regs), sp);
                let mut out = Vec::new();
                for (terms, og) in inner {
                    // `throughout` over an unbounded inner hop (`##[m:$]`) or a
                    // goto/nonconsec FSM term would need the guard threaded
                    // through the latch/FSM — deferred.
                    if terms.iter().any(|(t, h)| {
                        matches!(h, SeqHop::AtLeast(_)) || !matches!(t, SeqTerm::Bool(_))
                    }) {
                        self.error(
                            MsgCode::ElabUnsupported,
                            "`throughout` over an unbounded or goto/nonconsec sequence is unsupported in this subset",
                        );
                    }
                    out.push((terms, and_opt(og, Some(g.clone()), sp)));
                }
                out
            }
            ast::Sequence::Within { seq1, .. } => {
                // `within` is synthesized as a whole (two sub-pipelines combined)
                // by `synth_within` at the top level — it cannot appear as a term
                // inside a larger `##` chain in this subset.
                self.error(
                    MsgCode::ElabUnsupported,
                    "`within` is only supported as a top-level concurrent-assertion antecedent",
                );
                vec![(
                    vec![(SeqTerm::Bool(sva_zero(seq_span(seq1))), SeqHop::Fixed(0))],
                    None,
                )]
            }
        }
    }

    /// Synthesize the top-level `seq1 within seq2` antecedent match signal
    /// (slice S9): `seq1` must match entirely inside a `seq2` match. For bounded
    /// boolean operands this is `match(seq2) & OR_{i=0}^{L-k1} reg^i(match(seq1))`
    /// — over a seq2 window of length `L`, seq1 (length `k1`) completed at some
    /// clock that both ends within the window and starts at/after its start. ORed
    /// over every (seq2-alt × seq1-alt) combination. Pure IR-0.
    fn synth_within(
        &mut self,
        seq1: &ast::Sequence,
        seq2: &ast::Sequence,
        regs: &mut SvaRegs,
        nbas: &mut Vec<ast::Stmt>,
        sp: ast::Span,
    ) -> ast::Expr {
        let s1 = self.expand_sequence(seq1, regs);
        let s2 = self.expand_sequence(seq2, regs);
        // Both operands must be bounded, boolean-only, guard-free (no `##[m:$]`,
        // goto/nonconsec, throughout, or nested within inside).
        let ok = |alts: &[SeqAlt]| {
            alts.iter().all(|(t, g)| {
                g.is_none()
                    && t.iter().all(|(tm, h)| {
                        matches!(tm, SeqTerm::Bool(_)) && matches!(h, SeqHop::Fixed(_))
                    })
            })
        };
        if !ok(&s1) || !ok(&s2) {
            self.error(
                MsgCode::ElabUnsupported,
                "`within` requires bounded boolean sequences in this subset",
            );
            return sva_zero(sp);
        }
        if s1.len() * s2.len() > SVA_SEQ_ALT_CAP {
            self.error(
                MsgCode::ElabUnsupported,
                "a `within` expanded past the sequence alternative cap; narrow the bounded ranges",
            );
            return sva_zero(sp);
        }
        let mut combos: Vec<ast::Expr> = Vec::new();
        for (s2t, _) in &s2 {
            let l = window_len(s2t);
            let match_2 = self.synth_seq_pipeline(s2t.clone(), None, nbas, sp);
            for (s1t, _) in &s1 {
                let k1 = window_len(s1t);
                if k1 > l {
                    continue; // seq1 cannot fit in this seq2 window
                }
                let match_1 = self.synth_seq_pipeline(s1t.clone(), None, nbas, sp);
                // OR match_1 over the last (L - k1 + 1) clocks (the positions
                // where seq1 fits inside the seq2 window ending now).
                let mut acc = match_1.clone();
                let mut cur = match_1;
                for _ in 0..(l - k1) {
                    cur = self.seq_delay_reg(cur, nbas, sp);
                    acc = sva_binary(ast::BinOp::BitOr, acc, cur.clone(), sp);
                }
                combos.push(sva_binary(ast::BinOp::BitAnd, match_2.clone(), acc, sp));
            }
        }
        if combos.is_empty() {
            return sva_zero(sp); // seq1 longer than every seq2 window
        }
        let mut it = combos.into_iter();
        let mut acc = it.next().unwrap();
        for c in it {
            acc = sva_binary(ast::BinOp::BitOr, acc, c, sp);
        }
        acc
    }

    /// Synthesize the "sequence matches and ends THIS clock" boolean from a
    /// flattened (≥2-term) term list as a shift-register pipeline of 1-bit
    /// pending regs. `cur` starts as term0's truthiness, re-seeded every clock
    /// (overlapping match threads are inherent to the NBA shift). For each later
    /// term with hop-delay `d`, delay `cur` by `d` registered clocks (`d == 0` is
    /// same-cycle `##0` fusion — no register), then AND with that term's
    /// truthiness. A stage-reg read yields the PRIOR clock's value (the checker's
    /// if-check runs before the NBAs), so the chain advances one term per clock.
    /// Every term is reduced with `|` so a multi-bit term is a boolean (the F1
    /// reduction-OR rule). Pure IR-0 — only pre-existing sim-ir nodes.
    fn synth_seq_pipeline(
        &mut self,
        terms: Vec<(SeqTerm, SeqHop)>,
        guard: Option<ast::Expr>,
        pipeline_nbas: &mut Vec<ast::Stmt>,
        sp: ast::Span,
    ) -> ast::Expr {
        // A `throughout` guard `g` (already 1-bit) must hold at EVERY clock the
        // thread is alive: AND it into the seed and after every shift stage.
        let guard_and = |cur: ast::Expr| match &guard {
            Some(g) => sva_binary(ast::BinOp::BitAnd, cur, g.clone(), sp),
            None => cur,
        };
        let mut it = terms.into_iter();
        let (t0, _) = it
            .next()
            .expect("synth_seq_pipeline requires at least one term");
        // Seed: a Bool term is just `|t0`; a leading goto/nonconsec activates a
        // counting thread every clock (act = 1'b1).
        let seed = match t0 {
            SeqTerm::Bool(e) => sva_unary(ast::UnOp::RedOr, e, sp),
            SeqTerm::Goto(b, n) => self.goto_fsm(sva_one(sp), b, n, pipeline_nbas, sp),
            SeqTerm::Nonconsec(b, n) => self.nonconsec_fsm(sva_one(sp), b, n, pipeline_nbas, sp),
            SeqTerm::ConsecAtLeast(b, m) => {
                self.consec_run_fsm(sva_one(sp), b, m, pipeline_nbas, sp)
            }
        };
        let mut cur = guard_and(seed);
        for (term, hop) in it {
            match hop {
                SeqHop::Fixed(d) => {
                    for _ in 0..d {
                        cur = guard_and(self.seq_delay_reg(cur, pipeline_nbas, sp));
                    }
                }
                SeqHop::AtLeast(m) => {
                    // `##[m:$]`: delay `m-1` fixed clocks, then a never-reset
                    // `armed` latch — `armed <= armed | cur`. Reads of `armed`
                    // give the PRIOR-clock value (= "the prefix matched at some
                    // clock ≥ m ago"), so the match stays alive and re-completes
                    // on every later term clock. X-init armed stays don't-know
                    // until the first prefix match (no spurious fire via if(X)).
                    for _ in 0..m.saturating_sub(1) {
                        cur = self.seq_delay_reg(cur, pipeline_nbas, sp);
                    }
                    let armed = self.fresh_sva_reg(1, "arm");
                    let armed_path = ast::HierPath {
                        segments: vec![ast::Ident {
                            name: armed.clone(),
                            span: sp,
                        }],
                        span: sp,
                    };
                    let latch_rhs =
                        sva_binary(ast::BinOp::BitOr, sva_ident_expr(&armed, sp), cur, sp);
                    pipeline_nbas.push(ast::Stmt::NonBlocking {
                        lhs: ast::Lvalue::Ident(armed_path),
                        delay: None,
                        rhs: latch_rhs,
                        span: sp,
                    });
                    cur = sva_ident_expr(&armed, sp);
                }
            }
            // Apply the term to the (post-hop) activation `cur`:
            cur = match term {
                SeqTerm::Bool(e) => sva_binary(
                    ast::BinOp::BitAnd,
                    cur,
                    sva_unary(ast::UnOp::RedOr, e, sp),
                    sp,
                ),
                SeqTerm::Goto(b, n) => self.goto_fsm(cur, b, n, pipeline_nbas, sp),
                SeqTerm::Nonconsec(b, n) => self.nonconsec_fsm(cur, b, n, pipeline_nbas, sp),
                SeqTerm::ConsecAtLeast(b, m) => self.consec_run_fsm(cur, b, m, pipeline_nbas, sp),
            };
        }
        cur
    }

    /// Goto repetition `b[->n]` (slice S8). `act` is the (this-clock) activation:
    /// a counting thread starts wherever `act` is true. Existence-latch FSM with
    /// `n` 1-bit regs `reg_0..reg_{n-1}` (`reg_s` = "∃ thread that has seen `s`
    /// b's, pending the next"); a `b` advances every stage. Returns the
    /// match-this-clock signal `b & avail_{n-1}` (the n-th b). Exact for the
    /// `|->` any-completion semantics. Pure IR-0.
    fn goto_fsm(
        &mut self,
        act: ast::Expr,
        b: ast::Expr,
        n: u32,
        nbas: &mut Vec<ast::Stmt>,
        sp: ast::Span,
    ) -> ast::Expr {
        let n = n.max(1) as usize;
        let regs: Vec<String> = (0..n).map(|_| self.fresh_sva_reg(1, "gto")).collect();
        let bb = || sva_unary(ast::UnOp::RedOr, b.clone(), sp); // |b
        let nbb = || sva_unary(ast::UnOp::BitNot, bb(), sp); // ~|b
                                                             // avail_s = reg_s, except avail_0 also admits a freshly-activated thread.
        let avail = |s: usize| -> ast::Expr {
            if s == 0 {
                sva_binary(
                    ast::BinOp::BitOr,
                    sva_ident_expr(&regs[0], sp),
                    act.clone(),
                    sp,
                )
            } else {
                sva_ident_expr(&regs[s], sp)
            }
        };
        // reg_0 <= avail_0 & ~b  (seen-0 threads persist while no b)
        nbas.push(sva_nb(
            &regs[0],
            sva_binary(ast::BinOp::BitAnd, avail(0), nbb(), sp),
            sp,
        ));
        // reg_s <= (b & avail_{s-1}) | (~b & reg_s)  for s = 1..n-1
        #[allow(clippy::needless_range_loop)] // s indexes regs AND feeds avail(s-1)
        for s in 1..n {
            let adv = sva_binary(ast::BinOp::BitAnd, bb(), avail(s - 1), sp);
            let stay = sva_binary(ast::BinOp::BitAnd, nbb(), sva_ident_expr(&regs[s], sp), sp);
            nbas.push(sva_nb(
                &regs[s],
                sva_binary(ast::BinOp::BitOr, adv, stay, sp),
                sp,
            ));
        }
        // match = b & avail_{n-1}
        sva_binary(ast::BinOp::BitAnd, bb(), avail(n - 1), sp)
    }

    /// Nonconsecutive repetition `b[=n]` (slice S8) = goto to the n-th b, then an
    /// `ext` latch that keeps the match alive on subsequent non-b clocks (a
    /// further b would be the (n+1)-th and breaks it). Output this clock =
    /// `match_g | (ext & ~b)`; the latch holds exactly that. Pure IR-0.
    fn nonconsec_fsm(
        &mut self,
        act: ast::Expr,
        b: ast::Expr,
        n: u32,
        nbas: &mut Vec<ast::Stmt>,
        sp: ast::Span,
    ) -> ast::Expr {
        let match_g = self.goto_fsm(act, b.clone(), n, nbas, sp);
        let ext = self.fresh_sva_reg(1, "ncx");
        let nbb = sva_unary(ast::UnOp::BitNot, sva_unary(ast::UnOp::RedOr, b, sp), sp);
        let ext_alive = sva_binary(ast::BinOp::BitAnd, sva_ident_expr(&ext, sp), nbb, sp);
        // cur = match_g | (ext & ~b); ext <= cur (the same expression).
        let cur = sva_binary(ast::BinOp::BitOr, match_g, ext_alive, sp);
        nbas.push(sva_nb(&ext, cur.clone(), sp));
        cur
    }

    /// Unbounded consecutive repetition `b[*m:$]` (slice S13). `act` is the
    /// (this-clock) activation: a run may START wherever `act` is true. A gated
    /// run-latch with `m` 1-bit regs `c_1..c_m`, where `c_k` = "an alive thread
    /// (started at a valid activation) has now seen `k` consecutive `b`'s":
    ///   c_1 = act & |b                                  (a run begins)
    ///   c_k = reg(c_{k-1}) & |b              for 1<k<m  (the run advances)
    ///   c_m = (reg(c_{m-1}) | reg(c_m)) & |b            (advance OR self-latch ≥m)
    /// (`m == 1` collapses to the single self-latch `c_1 = (act|reg(c_1)) & |b`).
    /// Returns the match-this-clock signal `c_m` ("run ≥ m ends now"), exact for
    /// the `|->` any-completion semantics. A reg read yields the PRIOR clock's
    /// value (the checker's if-check runs before the NBAs), so the chain advances
    /// one count per clock; a non-`b` clock zeroes `c_1` and (one clock later)
    /// collapses the chain. X-init regs stay don't-know until the first real run
    /// (lenient: `if(X)` never fires). Pure IR-0.
    fn consec_run_fsm(
        &mut self,
        act: ast::Expr,
        b: ast::Expr,
        m: u32,
        nbas: &mut Vec<ast::Stmt>,
        sp: ast::Span,
    ) -> ast::Expr {
        let m = m.max(1) as usize;
        let regs: Vec<String> = (0..m).map(|_| self.fresh_sva_reg(1, "crl")).collect();
        let bb = || sva_unary(ast::UnOp::RedOr, b.clone(), sp); // |b
                                                                // c_1 (also the self-latch when m == 1).
        let c1 = if m == 1 {
            let or = sva_binary(ast::BinOp::BitOr, act, sva_ident_expr(&regs[0], sp), sp);
            sva_binary(ast::BinOp::BitAnd, or, bb(), sp)
        } else {
            sva_binary(ast::BinOp::BitAnd, act, bb(), sp)
        };
        nbas.push(sva_nb(&regs[0], c1.clone(), sp));
        let mut last = c1;
        for k in 2..=m {
            // reg(c_{k-1}) — the prior-clock count-(k-1) state.
            let prior_prev = sva_ident_expr(&regs[k - 2], sp);
            let ck = if k < m {
                sva_binary(ast::BinOp::BitAnd, prior_prev, bb(), sp)
            } else {
                // top reg saturates at ≥ m: (reg(c_{m-1}) | reg(c_m)) & |b.
                let or = sva_binary(
                    ast::BinOp::BitOr,
                    prior_prev,
                    sva_ident_expr(&regs[k - 1], sp),
                    sp,
                );
                sva_binary(ast::BinOp::BitAnd, or, bb(), sp)
            };
            nbas.push(sva_nb(&regs[k - 1], ck.clone(), sp));
            last = ck;
        }
        last
    }

    /// Register `cur` into a fresh 1-bit `seq` stage (one clock of delay) and
    /// return a read of it (which yields the PRIOR clock's value). Shared by the
    /// fixed-delay shift and the `##[m:$]` latch's `m-1` pre-delay.
    fn seq_delay_reg(
        &mut self,
        cur: ast::Expr,
        pipeline_nbas: &mut Vec<ast::Stmt>,
        sp: ast::Span,
    ) -> ast::Expr {
        let r = self.fresh_sva_reg(1, "seq");
        let r_path = ast::HierPath {
            segments: vec![ast::Ident {
                name: r.clone(),
                span: sp,
            }],
            span: sp,
        };
        pipeline_nbas.push(ast::Stmt::NonBlocking {
            lhs: ast::Lvalue::Ident(r_path),
            delay: None,
            rhs: cur,
            span: sp,
        });
        sva_ident_expr(&r, sp)
    }

    /// Build the (violation, completion) signals for a SEQUENCE consequent
    /// (`ante |-> b ##1 c`, slice S14) as an obligation chain. `cond_lhs` is the
    /// antecedent match (already +1-clock-delayed for `|=>`), which SEEDS the
    /// obligation. For each flattened term `term_k` due `hop_k` clocks after the
    /// prior term held:
    ///   viol_k     = due_k && !|term_k          (the obligation breaks here)
    ///   due_{k+1}  = delay_{hop_{k+1}}(due_k && |term_k)
    /// violation = OR_k viol_k; completion = due_{last} && |term_last (a
    /// non-vacuous success for the pass action). A reg read yields the PRIOR
    /// clock's value (the if-check runs before the NBAs), so the chain advances
    /// one term per clock. Bounded, single-alternative, boolean-term consequents
    /// only (ranges / goto / nonconsec / unbounded / throughout / within → loud).
    /// Pure IR-0.
    fn build_seq_consequent(
        &mut self,
        cons: &ast::Sequence,
        cond_lhs: &ast::Expr,
        regs: &mut SvaRegs,
        chain_nbas: &mut Vec<ast::Stmt>,
        sp: ast::Span,
    ) -> (ast::Expr, ast::Expr) {
        let mut alts = self.expand_sequence(cons, regs);
        let ok = alts.len() == 1
            && alts[0].1.is_none()
            && alts[0]
                .0
                .iter()
                .all(|(t, h)| matches!(t, SeqTerm::Bool(_)) && matches!(h, SeqHop::Fixed(_)));
        if !ok {
            self.error(
                MsgCode::ElabUnsupported,
                "a sequence consequent must be a single bounded boolean sequence \
                 (ranges / goto / nonconsec / unbounded / throughout / within / \
                 multi-clock consequents are unsupported in this subset)",
            );
            // Recovery: never-violate / never-complete (the run aborts on error).
            return (sva_zero(sp), sva_zero(sp));
        }
        let (terms, _) = alts.pop().unwrap();
        // Seed the obligation with the BOOLEAN truthiness of the antecedent match.
        // `due` is advanced each term with a width-preserving `BitAnd(due, |term)`,
        // so a multi-bit `cond_lhs` (e.g. `valid_vec |-> …`, where the |-> match
        // expr is the raw, un-reduced antecedent) MUST be reduced first — else a
        // truthy value with bit0=0 (2'b10 & 2'b01 = 0) would silently drop the
        // obligation (S14 review HIGH). `|=>` already reduces cond_lhs to the
        // 1-bit pend reg, and RedOr of a 1-bit value is idempotent, so this is
        // uniformly correct.
        let mut due = sva_unary(ast::UnOp::RedOr, cond_lhs.clone(), sp);
        let mut viols: Vec<ast::Expr> = Vec::new();
        for (k, (term, hop)) in terms.into_iter().enumerate() {
            let SeqTerm::Bool(e) = term else {
                unreachable!("ok-check guarantees Bool terms")
            };
            let tb = sva_unary(ast::UnOp::RedOr, e, sp); // |term_k
                                                         // Delay the obligation by the hop BEFORE this term (hop_0 unused: the
                                                         // first term is due the seed clock).
            if k > 0 {
                if let SeqHop::Fixed(d) = hop {
                    for _ in 0..d {
                        due = self.seq_delay_reg(due, chain_nbas, sp);
                    }
                }
            }
            // viol_k = due && !|term_k.
            viols.push(sva_binary(
                ast::BinOp::LogAnd,
                due.clone(),
                sva_unary(ast::UnOp::LogNot, tb.clone(), sp),
                sp,
            ));
            // Advance: due_next (combinational) = due && |term_k. The next
            // iteration's hop registers it.
            due = sva_binary(ast::BinOp::BitAnd, due, tb, sp);
        }
        // After the last term, `due` = due_last && |term_last = "consequent
        // completed this clock" (the pass-action success signal).
        let completed = due;
        let mut it = viols.into_iter();
        let mut violation = it
            .next()
            .expect("a sequence consequent has at least one term");
        for v in it {
            violation = sva_binary(ast::BinOp::BitOr, violation, v, sp);
        }
        (violation, completed)
    }

    /// Recursively rewrite SVA sampled-value functions in `e` into reads of
    /// synthesized prev-registers, registering each prev-reg + its `prev <=
    /// signal` NBA in `regs` (one prev-reg per distinct signal, shared). The
    /// argument must be a simple signal; anything else is a loud E3009.
    ///   $past(x)   → prev_x                (value one clock ago)
    ///   $stable(x) → (prev_x === x)        (no change, full 4-state)
    ///   $rose(x)   → (~prev_x[0] & x[0])   (LSB 0→1)
    ///   $fell(x)   → ( prev_x[0] & ~x[0])  (LSB 1→0)
    fn rewrite_sampled(&mut self, e: &ast::Expr, regs: &mut SvaRegs) -> ast::Expr {
        let sp = e.span;
        match &e.kind {
            ast::ExprKind::SysCall { name, args } if is_sva_sampled_fn(&name.name) => {
                if args.len() != 1 {
                    self.error(
                        MsgCode::ElabUnsupported,
                        &format!("`{}` takes one signal argument in v1", name.name),
                    );
                    return e.clone();
                }
                let ast::ExprKind::Ident(path) = &args[0].kind else {
                    self.error(
                        MsgCode::ElabUnsupported,
                        &format!("`{}` argument must be a simple signal in v1", name.name),
                    );
                    return e.clone();
                };
                // A hierarchical (multi-segment) reference would be keyed only by
                // its last segment below — two distinct signals (`top.x`/`u.x`)
                // would silently ALIAS onto one prev-register. Reject it loudly,
                // matching the existing hierarchical-reference policy (E3009).
                if path.segments.len() != 1 {
                    self.error(
                        MsgCode::ElabUnsupported,
                        &format!(
                            "`{}` of a hierarchical signal is unsupported in v1",
                            name.name
                        ),
                    );
                    return e.clone();
                }
                let sig = path
                    .segments
                    .last()
                    .map(|s| s.name.clone())
                    .unwrap_or_default();
                let prev = self.sva_prev_for(&sig, &args[0], regs);
                let prev_ref = sva_ident_expr(&prev, sp);
                match name.name.as_str() {
                    "$past" => prev_ref,
                    "$stable" => sva_binary(ast::BinOp::CaseEq, prev_ref, args[0].clone(), sp),
                    "$rose" => sva_binary(
                        ast::BinOp::BitAnd,
                        sva_unary(ast::UnOp::BitNot, sva_bit0(prev_ref, sp), sp),
                        sva_bit0(args[0].clone(), sp),
                        sp,
                    ),
                    "$fell" => sva_binary(
                        ast::BinOp::BitAnd,
                        sva_bit0(prev_ref, sp),
                        sva_unary(ast::UnOp::BitNot, sva_bit0(args[0].clone(), sp), sp),
                        sp,
                    ),
                    _ => unreachable!("guarded by is_sva_sampled_fn"),
                }
            }
            ast::ExprKind::Unary { op, operand } => {
                sva_unary(*op, self.rewrite_sampled(operand, regs), sp)
            }
            ast::ExprKind::Binary { op, lhs, rhs } => sva_binary(
                *op,
                self.rewrite_sampled(lhs, regs),
                self.rewrite_sampled(rhs, regs),
                sp,
            ),
            ast::ExprKind::Ternary {
                cond,
                then_e,
                else_e,
            } => ast::Expr {
                kind: ast::ExprKind::Ternary {
                    cond: Box::new(self.rewrite_sampled(cond, regs)),
                    then_e: Box::new(self.rewrite_sampled(then_e, regs)),
                    else_e: Box::new(self.rewrite_sampled(else_e, regs)),
                },
                span: sp,
            },
            ast::ExprKind::Paren { inner } => ast::Expr {
                kind: ast::ExprKind::Paren {
                    inner: Box::new(self.rewrite_sampled(inner, regs)),
                },
                span: sp,
            },
            // Leaf or a form that cannot host a sampled-value call in the subset:
            // clone verbatim (a sampled call nested in e.g. a concat is left as a
            // plain SysCall → the usual "unsupported system function" E3009).
            _ => e.clone(),
        }
    }

    /// Walk an SVA action-block statement (slice A2), rewriting every contained
    /// expression through `rewrite_sampled` so `$past`/`$rose`/`$fell`/`$stable`
    /// inside `$error`/`$display`/condition/assignment leaves resolve to the SAME
    /// shared prev-registers as the property body. Structural clone otherwise, so an
    /// action with NO sampled-value fn allocates no nets (byte-identical to pre-A2).
    /// rewrite_sampled keeps its own guards (hierarchical / multi-arg / non-signal
    /// sampled args → E3009; sampled fn nested in a concat/select stays unsupported),
    /// because every Expr is routed through it rather than cloned blind.
    fn rewrite_sampled_stmt(&mut self, s: &ast::Stmt, regs: &mut SvaRegs) -> ast::Stmt {
        use ast::Stmt as S;
        match s {
            S::SysTaskCall { name, args, span } => S::SysTaskCall {
                name: name.clone(),
                args: args.iter().map(|e| self.rewrite_sampled(e, regs)).collect(),
                span: *span,
            },
            S::UserTaskCall { name, args, span } => S::UserTaskCall {
                name: name.clone(),
                args: args.iter().map(|e| self.rewrite_sampled(e, regs)).collect(),
                span: *span,
            },
            S::If {
                cond,
                then_s,
                else_s,
                span,
            } => S::If {
                cond: self.rewrite_sampled(cond, regs),
                then_s: Box::new(self.rewrite_sampled_stmt(then_s, regs)),
                else_s: else_s
                    .as_ref()
                    .map(|e| Box::new(self.rewrite_sampled_stmt(e, regs))),
                span: *span,
            },
            S::Block {
                label,
                decls,
                stmts,
                span,
            } => S::Block {
                label: label.clone(),
                decls: decls.clone(),
                stmts: stmts
                    .iter()
                    .map(|st| self.rewrite_sampled_stmt(st, regs))
                    .collect(),
                span: *span,
            },
            S::Blocking {
                lhs,
                delay,
                event,
                rhs,
                span,
            } => S::Blocking {
                lhs: lhs.clone(),
                delay: delay.clone(),
                event: event.clone(),
                rhs: self.rewrite_sampled(rhs, regs),
                span: *span,
            },
            S::NonBlocking {
                lhs,
                delay,
                rhs,
                span,
            } => S::NonBlocking {
                lhs: lhs.clone(),
                delay: delay.clone(),
                rhs: self.rewrite_sampled(rhs, regs),
                span: *span,
            },
            S::Case {
                kind,
                scrutinee,
                items,
                span,
            } => S::Case {
                kind: *kind,
                scrutinee: self.rewrite_sampled(scrutinee, regs),
                items: items
                    .iter()
                    .map(|it| match it {
                        ast::CaseItem::Match { labels, body, span } => ast::CaseItem::Match {
                            labels: labels
                                .iter()
                                .map(|e| self.rewrite_sampled(e, regs))
                                .collect(),
                            body: Box::new(self.rewrite_sampled_stmt(body, regs)),
                            span: *span,
                        },
                        ast::CaseItem::Default { body, span } => ast::CaseItem::Default {
                            body: Box::new(self.rewrite_sampled_stmt(body, regs)),
                            span: *span,
                        },
                    })
                    .collect(),
                span: *span,
            },
            // Action statements with no sampled-value-hosting expressions (or forms
            // out of the action-block subset — timing controls, fork, …) clone
            // verbatim: no net allocation, so byte-identical to pre-A2.
            other => other.clone(),
        }
    }

    /// Get-or-create the shared prev-register for `sig` (matching its declared
    /// width), registering the `prev <= signal` NBA on first creation.
    fn sva_prev_for(&mut self, sig: &str, sig_expr: &ast::Expr, regs: &mut SvaRegs) -> String {
        if let Some((_, prev)) = regs.by_signal.iter().find(|(s, _)| s == sig) {
            return prev.clone();
        }
        let width = self
            .lookup_net_scoped(sig)
            .map(|id| self.nets[id as usize].width)
            .unwrap_or(1);
        let prev = self.fresh_sva_reg(width, "prev");
        let sp = sig_expr.span;
        let prev_path = ast::HierPath {
            segments: vec![ast::Ident {
                name: prev.clone(),
                span: sp,
            }],
            span: sp,
        };
        regs.nbas.push(ast::Stmt::NonBlocking {
            lhs: ast::Lvalue::Ident(prev_path),
            delay: None,
            rhs: sig_expr.clone(),
            span: sp,
        });
        regs.by_signal.push((sig.to_string(), prev.clone()));
        prev
    }

    // ── one ProceduralBlock → one Process ──────────────────────────
    fn lower_proc_block(&mut self, p: &ast::ProceduralBlock) -> ir::Process {
        // The ProcId this process WILL occupy when the caller pushes it. Stable for
        // the whole body lowering (lower_proc_block is non-reentrant: it fully
        // builds one Process and returns BEFORE processes.push). Any fork mode
        // recorded below is keyed by this id; the caller debug_asserts the match.
        self.cur_proc = self.processes.len() as u32;
        // Reset the nesting guard at every top-level body entry (a process body is
        // never lowered while already inside a fork child of another process).
        self.in_fork = false;

        // P2-E `final`: zero-time one-shot — ANY timing control in the body
        // (#/@/wait, anywhere, fork branches included) is illegal (§9.2.3).
        if matches!(p.kind, ast::ProcKind::Final) {
            if stmt_has_timing(&p.body) {
                self.error(
                    MsgCode::ElabUnsupported,
                    "a final block executes in zero time — timing controls \
                     (#/@/wait) are illegal inside it (IEEE §9.2.3)",
                );
            }
            self.final_procs.insert(self.cur_proc);
        }

        // M-C: a bare `always` with NO header @(...) re-arms via its own in-body
        // timing (`always #5 clk=~clk;`). Detect that and wrap the body in an
        // implicit forever so control loops back to the in-body delay/event.
        let bare_always_self_timed =
            matches!(p.kind, ast::ProcKind::Always) && p.sensitivity.is_none();

        let sensitivity = self.lower_sensitivity(p.kind, p.sensitivity.as_ref(), &p.body);
        let mut b = ProcessBuilder::new(); // entry block #0 open
        if bare_always_self_timed && stmt_has_timing(&p.body) {
            // Implicit `forever { body }` so the process re-arms on its own #/@.
            self.lower_forever(&mut b, &p.body);
        } else {
            self.lower_stmt(&mut b, &p.body); // recursive body lowering
        }
        let (body, entry) = b.finish(); // seals trailing block with Return

        // Implicit-sensitivity inference for `@*` / `always_comb` / `always_latch`:
        // lower_sensitivity leaves these `Comb`/`Latch` with EMPTY edges. Infer the
        // read-set (every net read on a RHS / branch condition in the lowered body)
        // and record it as level-sensitive edges so the engine re-fires the block
        // when any input changes. EXCLUDES a bare self-timed `always` (re-arms via
        // its own in-body #/@, no data read-set).
        let is_comb_inferred = matches!(
            p.kind,
            ast::ProcKind::AlwaysComb | ast::ProcKind::AlwaysLatch
        ) || matches!(
            (p.kind, p.sensitivity.as_ref()),
            (ast::ProcKind::Always, Some(ast::Sensitivity::Star))
        );
        let sensitivity = if is_comb_inferred && sensitivity.edges.is_empty() {
            let nets = self.comb_read_set(&body);
            ir::Sensitivity {
                kind: sensitivity.kind,
                edges: nets
                    .into_iter()
                    .map(|net| ir::EdgeTerm {
                        net,
                        kind: ir::EdgeKind::AnyEdge,
                    })
                    .collect(),
            }
        } else {
            sensitivity
        };

        ir::Process {
            sensitivity,
            body,
            entry,
            suspend: fresh_suspend(entry),
        }
    }

    /// Read-set of a lowered process body: every net referenced on a RHS or a
    /// branch condition (LHS write targets are NOT reads). Drives implicit
    /// `@*`/`always_comb` sensitivity. Deterministic ascending net order.
    fn comb_read_set(&self, body: &[ir::BasicBlock]) -> Vec<u32> {
        let mut reads = std::collections::BTreeSet::new();
        for bb in body {
            for &sid in &bb.stmts {
                match &self.stmts[sid as usize] {
                    ir::Stmt::BlockingAssign { rhs, .. }
                    | ir::Stmt::NonblockingAssign { rhs, .. } => {
                        self.collect_expr_reads(*rhs, &mut reads);
                    }
                    ir::Stmt::SysTask { fmt, args, .. } => {
                        if let Some(f) = fmt {
                            self.collect_expr_reads(*f, &mut reads);
                        }
                        for &a in args {
                            self.collect_expr_reads(a, &mut reads);
                        }
                    }
                    ir::Stmt::Disable { .. } => {}
                    // shape-reserved at format_version 4 (never lowered yet);
                    // a force RHS would be a read when the increment lands.
                    ir::Stmt::Force { rhs, .. } => {
                        self.collect_expr_reads(*rhs, &mut reads);
                    }
                    ir::Stmt::Release { .. } => {}
                }
            }
            if let ir::Terminator::Branch { cond, .. } = &bb.term {
                self.collect_expr_reads(*cond, &mut reads);
            }
        }
        reads.into_iter().collect()
    }

    /// Recursively collect every `Signal` net read by expression `eid`.
    fn collect_expr_reads(&self, eid: u32, reads: &mut std::collections::BTreeSet<u32>) {
        match &self.exprs[eid as usize] {
            ir::Expr::Const { .. } => {}
            ir::Expr::Signal { net, word } => {
                reads.insert(*net);
                // The array WORD index is itself a read: `always_comb y = mem[sel]`
                // must re-fire when `sel` (or any signal in a multi-dim flat index
                // `i*ncols+j`) changes, not only when the memory changes. Symmetric
                // with the `Select` arm recursing into its offset.
                if let Some(weid) = word {
                    self.collect_expr_reads(*weid, reads);
                }
            }
            ir::Expr::Select {
                base,
                offset,
                width,
                ..
            } => {
                self.collect_expr_reads(*base, reads);
                self.collect_expr_reads(*offset, reads);
                self.collect_expr_reads(*width, reads);
            }
            ir::Expr::Concat { parts } => {
                for &p in parts {
                    self.collect_expr_reads(p, reads);
                }
            }
            ir::Expr::Replicate { count, value } => {
                self.collect_expr_reads(*count, reads);
                self.collect_expr_reads(*value, reads);
            }
            ir::Expr::Unary { operand, .. } => self.collect_expr_reads(*operand, reads),
            ir::Expr::Binary { lhs, rhs, .. } => {
                self.collect_expr_reads(*lhs, reads);
                self.collect_expr_reads(*rhs, reads);
            }
            ir::Expr::Ternary {
                cond,
                then_e,
                else_e,
            } => {
                self.collect_expr_reads(*cond, reads);
                self.collect_expr_reads(*then_e, reads);
                self.collect_expr_reads(*else_e, reads);
            }
            ir::Expr::SysFunc { args, .. } => {
                for &a in args {
                    self.collect_expr_reads(a, reads);
                }
            }
            ir::Expr::Call { .. } => {}
        }
    }

    // ── sensitivity mapping ────────────────────────────────────────
    /// `ProcKind` + AST `Sensitivity` → `ir::Sensitivity`. Classification:
    /// any explicit edge ⇒ `Edge`; all bare ⇒ `Level`; `always_ff` forces
    /// `Edge`; `@(*)`/`always_comb` ⇒ `Comb` (read-set inference deferred —
    /// empty edges, no error); `always_latch` ⇒ `Latch`; `initial` ⇒ `Initial`.
    fn lower_sensitivity(
        &mut self,
        kind: ast::ProcKind,
        sens: Option<&ast::Sensitivity>,
        body: &ast::Stmt, // M-C: inspect body for in-body timing on bare `always`
    ) -> ir::Sensitivity {
        use ast::ProcKind::*;
        match kind {
            // P2-E `final`: Initial-shaped in the frozen IR (no sensitivity
            // variant exists and none is needed) — the engine SKIPS arming it
            // via the final_procs side table and runs it at end of simulation.
            Initial | Final => ir::Sensitivity {
                kind: ir::SensKind::Initial,
                edges: Vec::new(),
            },
            AlwaysComb => ir::Sensitivity {
                kind: ir::SensKind::Comb,
                edges: Vec::new(),
            },
            AlwaysLatch => ir::Sensitivity {
                kind: ir::SensKind::Latch,
                edges: Vec::new(),
            },
            AlwaysFf => self.classify_event_list(sens, /* force_edge = */ true),
            Always => match sens {
                None => {
                    if stmt_has_timing(body) {
                        // Legal self-timed `always` (clock generator). The body's
                        // own #/@ drives time; the process re-runs (forever-wrapped
                        // in lower_proc_block). No header edges → Comb-shaped arm.
                        ir::Sensitivity {
                            kind: ir::SensKind::Comb,
                            edges: Vec::new(),
                        }
                    } else {
                        // Truly unschedulable: warn (non-fatal) but still emit a
                        // valid (inert) process rather than killing the whole IR.
                        self.warn(
                            "always with neither @(...) nor in-body timing is \
                             unschedulable; lowered as an inert process",
                        );
                        ir::Sensitivity {
                            kind: ir::SensKind::Comb,
                            edges: Vec::new(),
                        }
                    }
                }
                Some(ast::Sensitivity::Star) => ir::Sensitivity {
                    kind: ir::SensKind::Comb,
                    edges: Vec::new(),
                },
                Some(s @ ast::Sensitivity::List(_)) => {
                    self.classify_event_list(Some(s), /* force_edge = */ false)
                }
            },
        }
    }

    /// Map a `Sensitivity::List` to Edge-or-Level. `force_edge` (always_ff) pins
    /// the kind to Edge. Determinism: edges appended in source order.
    fn classify_event_list(
        &mut self,
        sens: Option<&ast::Sensitivity>,
        force_edge: bool,
    ) -> ir::Sensitivity {
        let list = match sens {
            Some(ast::Sensitivity::List(l)) => l.as_slice(),
            Some(ast::Sensitivity::Star) | None => {
                if force_edge {
                    self.warn("always_ff requires an explicit @(edge ...) list");
                }
                return ir::Sensitivity {
                    kind: if force_edge {
                        ir::SensKind::Edge
                    } else {
                        ir::SensKind::Comb
                    },
                    edges: Vec::new(),
                };
            }
        };
        let any_edge = force_edge || list.iter().any(|ev| !matches!(ev.edge, ast::Edge::NoEdge));
        let edges = list
            .iter()
            .map(|ev| ir::EdgeTerm {
                net: self.sens_event_net(&ev.expr, any_edge),
                kind: map_edge(ev.edge),
            })
            .collect();
        ir::Sensitivity {
            kind: if any_edge {
                ir::SensKind::Edge
            } else {
                ir::SensKind::Level
            },
            edges,
        }
    }

    /// Resolve an event-control expr to the net it senses. Supported: a bare
    /// signal name (or parenthesized one), and — only in an EDGE-sensitive list
    /// (`edge_ctx`) — a CONSTANT bit-select whose selected bit IS the net's LSB
    /// (packed bit 0). The engine's EDGE model checks bit 0 only, so
    /// `@(posedge clk[lsb])` arms identically to `@(posedge clk)` (IEEE: vector
    /// posedge tracks the LSB). LEVEL sensitivity, by contrast, fires on a
    /// WHOLE-NET change, so a level bit-select (`@(clk[0])`) is NOT representable
    /// (mapping it to the net over-triggers on sibling-bit changes) → rejected.
    /// Everything else (non-LSB bit, part-select, variable/non-const index, array
    /// element, multi-dim packed select, computed base) needs per-bit tracking we
    /// lack → LOUD reject (E3009), NOT a silent POISON_NET that would index
    /// `net_to_edge[u32::MAX]` and panic the scheduler (`error` sets `had_error`,
    /// so the IR is discarded and sim-engine is never reached).
    fn sens_event_net(&mut self, e: &ast::Expr, edge_ctx: bool) -> u32 {
        match &e.kind {
            ast::ExprKind::Ident(path) => {
                let n = self.resolve_net(path);
                if self.is_dyn_handle_net(n) || self.is_string_net(n) {
                    // v5 ⑥/v7: handles carry no dirty channel — they can
                    // never wake a process (design §4).
                    self.error(
                        MsgCode::ElabUnsupported,
                        "a dynamic-storage handle cannot appear in an event control",
                    );
                }
                n
            }
            ast::ExprKind::Paren { inner } => self.sens_event_net(inner, edge_ctx),
            ast::ExprKind::BitSelect { base, index } => {
                if edge_ctx {
                    if let Some(net) = self.lsb_bitselect_net(base, index) {
                        return net; // == the bare-ident net id: bit0 edge is exact
                    }
                    self.error(
                        MsgCode::ElabUnsupported,
                        "edge event-control bit-select must select the net's LSB with a constant \
                         index (non-LSB / part-select / variable index / array / packed need \
                         per-bit edge tracking)",
                    );
                } else {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "single-bit level (non-edge) event control is not supported; use \
                         posedge/negedge or the whole signal (level fires on any whole-net change)",
                    );
                }
                POISON_NET
            }
            _ => {
                self.error(
                    MsgCode::ElabUnsupported,
                    "event control must be a bare signal name or a constant LSB bit-select",
                );
                POISON_NET
            }
        }
    }

    /// `clk[k]` maps EXACTLY to arming on the underlying net (bit-0 edge) iff `k`
    /// is a compile-time constant equal to the net's LSB endpoint. `nv.lsb` is the
    /// source index that lands on packed bit 0 in BOTH range directions (descending
    /// `[hi:lo]` → `lo`; ascending `[lo:hi]` stored as `msb<lsb` → the larger bound
    /// `lsb`). Returns the net id when supported, else `None` (→ caller rejects loud).
    fn lsb_bitselect_net(&self, base: &ast::Expr, index: &ast::Expr) -> Option<u32> {
        let ast::ExprKind::Ident(path) = &base.kind else {
            return None; // computed / hierarchical / concat base
        };
        if path.segments.len() != 1 {
            return None;
        }
        let net = self.lookup_net_scoped(&path.segments[0].name)?;
        // Reject array elements (multi-bit words), multi-dim packed selects, and
        // dyn-storage/string handles — none is a scalar net whose bit 0 we can arm.
        if self.net_is_static_array(net)
            || self.packed_dims.contains_key(&net)
            || self.is_dyn_handle_net(net)
            || self.is_string_net(net)
        {
            return None;
        }
        let k = self.const_eval_in_scope(index)?;
        let lsb = self.nets.get(net as usize)?.lsb as i64;
        (k == lsb).then_some(net)
    }

    // ── the recursive statement-lowering heart ─────────────────────
    /// CONTRACT: on entry `b.cur` is open; on exit `b.cur` is open and is the
    /// "continue point" (where control flows next). Every form upholds this.
    fn lower_stmt(&mut self, b: &mut ProcessBuilder, s: &ast::Stmt) {
        match s {
            // ── STRAIGHT-LINE (stay in the same block) ──────────────
            ast::Stmt::Blocking {
                lhs,
                delay,
                event,
                rhs,
                span,
            } => {
                // Intra-assignment EVENT control `= [repeat(n)] @(ev) rhs` (IEEE
                // §9.4.5): capture-now / wait / write. Handled FIRST — the rhs is a
                // plain captured value (a special form like `new`/`pop` combined with
                // event control falls through lower_expr to its own loud diagnostic).
                if let Some(ie) = event {
                    self.lower_intra_event_assign(b, lhs, ie, rhs, *span);
                    return;
                }
                // v5 ⑥: `d = new[n]` / `x = q.pop_*()` special forms.
                if self.dyn_blocking_special(b, lhs, delay.as_ref(), rhs) {
                    return;
                }
                // Phase-1.x ②: unpacked-array assignment (whole / slice).
                if self.array_assign_special(b, lhs, delay.as_ref(), rhs, false) {
                    return;
                }
                // v7: `x = $random(seed)` — the seeded draw writes the seed
                // back, statement-level intercept (the only legal placement).
                if self.random_seeded_special(b, lhs, delay.as_ref(), rhs) {
                    return;
                }
                // v7: `ok = $value$plusargs(fmt, var)` — same family.
                if self.value_plusargs_special(b, lhs, delay.as_ref(), rhs) {
                    return;
                }
                // v7: `fd = $fopen(name[, mode])` — same family.
                if self.fopen_special(b, lhs, delay.as_ref(), rhs) {
                    return;
                }
                // v7 P2-C: `s = $sformatf(fmt, args…)` — same family.
                if self.sformatf_special(b, lhs, delay.as_ref(), rhs) {
                    return;
                }
                let rhs_id = self.lower_expr(rhs);
                let lv = self.lower_lvalue(lhs);
                self.check_lvalue_kind(&lv, true); // P1-9 (E3018): no proc write to a net
                if let Some(d) = delay {
                    // IEEE §9.2.2 intra-assignment delay: the RHS evaluates NOW,
                    // the process suspends `d`, THEN the write happens. Lower as
                    //   tmp = rhs;  #d;  lhs = tmp;
                    // with a synthetic tmp sized EXACTLY to the lvalue width so
                    // the rhs eval context (max(lhs_w, self_w)) is unchanged —
                    // a wider tmp would alter div/shift operand truncation.
                    let w = self.ir_lvalue_width(&lv);
                    let tmp = self.fresh_ia_tmp(w);
                    let cap = self.push_stmt(ir::Stmt::BlockingAssign {
                        lhs: whole_net_lvalue(tmp),
                        rhs: rhs_id,
                    });
                    b.push_stmt_id(cap);
                    let (amount, region) = self.lower_delay(d);
                    let resume = b.new_block();
                    b.end_block_with(ir::Terminator::Delay {
                        amount,
                        region,
                        resume: resume.raw(),
                    });
                    b.start_block(resume);
                    let tmp_read = self.push_expr(ir::Expr::Signal {
                        net: tmp,
                        word: None,
                    });
                    let wr = self.push_stmt(ir::Stmt::BlockingAssign {
                        lhs: lv,
                        rhs: tmp_read,
                    });
                    b.push_stmt_id(wr);
                } else {
                    let sid = self.push_stmt(ir::Stmt::BlockingAssign {
                        lhs: lv,
                        rhs: rhs_id,
                    });
                    b.push_stmt_id(sid);
                }
            }
            ast::Stmt::NonBlocking {
                lhs, delay, rhs, ..
            } => {
                // `a <= #d rhs` (v5 increment A): a VALUE-CARRYING transport
                // delay — RHS and any LHS index are sampled at execution time,
                // the update joins the NBA region of t+d, and overlapping
                // activations each deliver their own capture. `d` is an ExprId
                // evaluated at execution (v4 runtime-delay model, scaled by
                // the process's timescale multiplier); d == 0 degenerates to
                // the plain same-tick NBA path (statement order preserved).
                // Phase-1.x ②: unpacked-array assignment (whole / slice).
                if self.array_assign_special(b, lhs, delay.as_ref(), rhs, true) {
                    return;
                }
                let rhs_id = self.lower_expr(rhs);
                let lv = self.lower_lvalue(lhs);
                self.check_lvalue_kind(&lv, true); // P1-9 (E3018)
                let delay_id = delay.as_ref().map(|d| self.lower_delay(d).0);
                let sid = self.push_stmt(ir::Stmt::NonblockingAssign {
                    lhs: lv,
                    rhs: rhs_id,
                    delay: delay_id,
                });
                b.push_stmt_id(sid);
            }
            ast::Stmt::SysTaskCall { name, args, .. } => {
                if let Some(sid) = self.lower_systask(name, args) {
                    b.push_stmt_id(sid);
                }
            }
            ast::Stmt::Null(_) => { /* no-op, same block */ }

            // ── SEQUENCING: begin … end ─────────────────────────────
            // begin..end: block-local decls were already hoisted to module nets in
            // the Nets phase (hoist_block_local_nets), so just lower the stmts here.
            ast::Stmt::Block { label, stmts, .. } => {
                // Named block targeted by some `disable` in its own body:
                // allocate an exit BB so the disable lowers as a Goto (doc-17
                // lowering row). Allocation is LAZY (pre-scan) so unlabeled /
                // never-disabled blocks lower byte-identically to the old CFG.
                let exit = label.as_ref().and_then(|lab| {
                    stmts
                        .iter()
                        .any(|st| stmt_disables_label(st, &lab.name))
                        .then(|| {
                            let exit = b.new_block();
                            self.disable_stack.push((lab.name.clone(), exit));
                            exit
                        })
                });
                for st in stmts {
                    self.lower_stmt(b, st);
                }
                if let Some(exit) = exit {
                    self.disable_stack.pop();
                    b.goto(exit);
                    b.start_block(exit);
                }
            }

            // ── IF / ELSE — the canonical merge pattern ─────────────
            ast::Stmt::If {
                cond,
                then_s,
                else_s,
                ..
            } => {
                let cond_id = self.lower_expr(cond);
                let then_bb = b.new_block();
                let else_bb = b.new_block();
                let merge = b.new_block();
                b.end_block_with(ir::Terminator::Branch {
                    cond: cond_id,
                    then_bb: then_bb.raw(),
                    else_bb: else_bb.raw(),
                });
                b.start_block(then_bb);
                self.lower_stmt(b, then_s);
                b.goto(merge);
                b.start_block(else_bb);
                if let Some(e) = else_s {
                    self.lower_stmt(b, e);
                }
                b.goto(merge);
                b.start_block(merge); // continue in merge (post-condition)
            }

            // ── DEFERRED IMMEDIATE ASSERT (§16.4) — If + flush marker ─
            // `assert #0` (Observed) / `assert final` (Reactive): lowered like an
            // immediate assert (Branch over pass/fail BBs) PLUS a per-assertion
            // flush marker emitted before the Branch. The action SysTask(s) are
            // recorded out-of-band so the engine enqueues them for region
            // maturation with flush-on-re-reach instead of firing inline.
            ast::Stmt::DeferredAssert {
                region,
                cond,
                then_s,
                else_s,
                ..
            } => {
                let dr = match region {
                    ast::AssertDefer::Observed => DeferRegion::Observed,
                    ast::AssertDefer::Reactive => DeferRegion::Reactive,
                };
                // Clear any enclosing deferred context so the marker itself is not
                // recorded as an outer assert's action (nested deferreds are
                // pathological but kept correct).
                let outer = self.cur_defer.take();
                // (1) FLUSH MARKER: a suppressed no-op `$display`. Reaching it (in
                //     the Active region) cancels any prior pending report for this
                //     assertion instance + activity — flush-on-re-reach (§16.4).
                let marker = self.push_stmt(ir::Stmt::SysTask {
                    which: ir::SysTaskId::Display,
                    fmt: None,
                    args: Vec::new(),
                });
                self.defer_marks.insert(marker, dr);
                b.push_stmt_id(marker);
                // (2) Lower like an `If`; the `push_stmt` hook (keyed on
                //     `cur_defer`) records each arm's action SysTasks into
                //     `defer_acts` under this marker.
                let cond_id = self.lower_expr(cond);
                let then_bb = b.new_block();
                let else_bb = b.new_block();
                let merge = b.new_block();
                b.end_block_with(ir::Terminator::Branch {
                    cond: cond_id,
                    then_bb: then_bb.raw(),
                    else_bb: else_bb.raw(),
                });
                let n_before = self.defer_acts.len();
                self.cur_defer = Some((marker, dr));
                b.start_block(then_bb);
                self.lower_stmt(b, then_s);
                b.goto(merge);
                b.start_block(else_bb);
                self.lower_stmt(b, else_s);
                b.goto(merge);
                self.cur_defer = outer;
                b.start_block(merge);
                // (3) Neither arm produced a deferrable action ⇒ it ran inline
                //     (evaluate-when-reached): a documented hand-IEEE corner.
                if self.defer_acts.len() == n_before && !self.defer_inline_warned {
                    self.defer_inline_warned = true;
                    self.warn(
                        "a deferred assertion's action contains no $display/$error-class \
                         statement; it executes inline (evaluate-when-reached), not deferred",
                    );
                }
            }

            // ── CASE / CASEZ / CASEX — Branch chain ─────────────────
            ast::Stmt::Case {
                kind,
                scrutinee,
                items,
                ..
            } => self.lower_case(b, *kind, scrutinee, items),

            // ── #delay ──────────────────────────────────────────────
            ast::Stmt::DelayCtrl { delay, body, .. } => {
                let (amount, region) = self.lower_delay(delay);
                let resume = b.new_block();
                b.end_block_with(ir::Terminator::Delay {
                    amount,
                    region,
                    resume: resume.raw(),
                });
                b.start_block(resume);
                if let Some(body) = body {
                    self.lower_stmt(b, body);
                }
            }

            // ── @(event) ────────────────────────────────────────────
            ast::Stmt::EventCtrl { ctrl, body, .. } => {
                // P1-4: in-body `@(*)` infers the read-set of the statement it
                // CONTROLS (IEEE 1800 §9.4.2.2) — the cause is patched after the
                // body lowers (blocks ≥ `resume` are exactly the controlled
                // statement at snapshot time; later siblings append afterwards).
                let star = matches!(ctrl, ast::Sensitivity::Star);
                let cause = if star {
                    ir::WaitCause::Level { nets: Vec::new() } // patched below
                } else {
                    self.lower_event_wait_cause(ctrl)
                };
                let wait_bb = b.cur.expect("EventCtrl with no open block");
                let resume = b.new_block();
                b.end_block_with(ir::Terminator::Wait {
                    cond: cause,
                    resume: resume.raw(),
                });
                b.start_block(resume);
                if let Some(body) = body {
                    self.lower_stmt(b, body);
                }
                if star {
                    let nets = self.comb_read_set(&b.body[resume.raw() as usize..]);
                    if nets.is_empty() {
                        self.warn("in-body @(*) reads no nets; it can never wake");
                    }
                    b.body[wait_bb.raw() as usize].term = ir::Terminator::Wait {
                        cond: ir::WaitCause::Level { nets },
                        resume: resume.raw(),
                    };
                }
            }

            // ── wait(expr) — level wait via WaitCause::Expr ─────────
            ast::Stmt::Wait { cond, body, .. } => {
                let e = self.lower_expr(cond);
                let resume = b.new_block();
                b.end_block_with(ir::Terminator::Wait {
                    cond: ir::WaitCause::Expr { expr: e },
                    resume: resume.raw(),
                });
                b.start_block(resume);
                if let Some(body) = body {
                    self.lower_stmt(b, body);
                }
            }

            // ── LOOPS (SECONDARY) ───────────────────────────────────
            ast::Stmt::Forever { body, .. } => self.lower_forever(b, body),
            ast::Stmt::While { cond, body, .. } => self.lower_while(b, cond, body),
            ast::Stmt::Repeat { count, body, .. } => self.lower_repeat(b, count, body),
            ast::Stmt::For {
                init,
                cond,
                step,
                body,
                ..
            } => self.lower_for(b, init, cond, step, body),

            // disable: REAL for a lexically-enclosing named begin-block (the
            // break/continue idiom) — doc-17's lowering row "Stmt::Disable then
            // Goto": the Disable stmt keeps the diagnostic shape (engine no-op,
            // target = the exit BB it jumps to), the Goto does the work. The
            // fork floor keeps a child from jumping across its join barrier.
            // Anything else (cross-process block, task body, hierarchical path,
            // unknown label) is a LOUD error — the old warn+no-op silently kept
            // executing the "disabled" block.
            ast::Stmt::Disable { target, .. } => {
                let hit = if target.segments.len() == 1 {
                    self.disable_stack[self.disable_fork_floor..]
                        .iter()
                        .rev()
                        .find(|(n, _)| n == &target.segments[0].name)
                        .map(|(_, exit)| *exit)
                } else {
                    None
                };
                // P2-E: `disable fork` — kill the caller's descendants
                // (IEEE §9.6.3). Straight-line statement, no control flow.
                if target.segments.len() == 1 && target.segments[0].name == "fork" {
                    let sid = self.push_stmt(ir::Stmt::Disable {
                        scope_kind: ir::DisableKind::Fork,
                        target: 0,
                    });
                    b.push_stmt_id(sid);
                    return;
                }
                match hit {
                    Some(exit) => {
                        let sid = self.push_stmt(ir::Stmt::Disable {
                            scope_kind: ir::DisableKind::Scope,
                            target: exit.raw(),
                        });
                        b.push_stmt_id(sid);
                        b.goto(exit);
                        // unreachable continuation keeps the one-open-cursor
                        // contract (INV-1) for the rest of the block.
                        let dead = b.new_block();
                        b.start_block(dead);
                    }
                    None => {
                        let path = target
                            .segments
                            .iter()
                            .map(|s| s.name.as_str())
                            .collect::<Vec<_>>()
                            .join(".");
                        self.error(
                            MsgCode::ElabUnsupported,
                            &format!(
                                "disable target `{path}` is not a lexically-enclosing \
                                 named block of this statement; v1 supports only the \
                                 break/continue idiom (cross-process, task, fork-crossing \
                                 and hierarchical disable are unsupported)"
                            ),
                        );
                    }
                }
            }
            ast::Stmt::Fork {
                stmts,
                join,
                decls,
                span,
                label: _,
            } => {
                // ── HARD MVP BOUNDARY: no nested fork (§6.2). A fork inside a fork
                //    child is a fatal elaborate error — NOT "warn and proceed". This
                //    keeps child identity flat (a single, non-chained tie shift) and
                //    forbids tie aliasing/overflow.
                if self.in_fork {
                    self.error_unsupported(
                        *span,
                        "nested fork is unsupported in v1 \
                         (a fork child may not itself contain a fork)",
                    );
                    // Emit a well-formed but inert block so INV-1/INV-2 still hold:
                    // seal the cursor straight to the continuation. No children, no
                    // barrier, no mode entry.
                    let cont = b.new_block();
                    b.goto(cont);
                    b.start_block(cont);
                    return;
                }

                // fork-local decls share the enclosing scope in v1 (like begin-block
                // decls); WARN-ignore them, matching Stmt::Block decl handling.
                if !decls.is_empty() {
                    self.warn(
                        "fork-local decls ignored (v1 shared-scope); \
                         declared in enclosing scope",
                    );
                }

                // INV-2: allocate EVERY named block BEFORE building the Fork
                // terminator. Allocation order is deterministic (3-OS golden
                // stability): join, resume, then each child entry in source order.
                let join_bb = b.new_block();
                let resume_bb = b.new_block();
                let child_entries: Vec<BlockId> = (0..stmts.len()).map(|_| b.new_block()).collect();

                // Record the join MODE into the side table (NOT IR), keyed by
                // (cur_proc, join_bb). The engine's lookup is total-or-fatal.
                self.record_fork_mode(*join, join_bb.raw());

                // INV-1: seal the parent block with Fork — this CLOSES the cursor.
                b.end_block_with(ir::Terminator::Fork {
                    children: child_entries.iter().map(|e| e.raw()).collect(),
                    join: join_bb.raw(),
                    resume_bb: resume_bb.raw(),
                });

                // Lower each child chain. `lower_stmt` returns with the cursor open
                // at the child's single continuation; `goto(join_bb)` seals that tail
                // so the child's LAST block hands control to the join. Empty `stmts`
                // ⇒ this loop is skipped (valid: Fork{children:[]}). `in_fork` is set
                // so any Fork lowered INSIDE a child hits the hard error above.
                let prev_in_fork = self.in_fork;
                self.in_fork = true;
                // A fork child is its own process: it may disable only blocks
                // inside its OWN body (floor), never across the join barrier.
                let prev_floor = self.disable_fork_floor;
                self.disable_fork_floor = self.disable_stack.len();
                for (child_entry, st) in child_entries.iter().zip(stmts.iter()) {
                    b.start_block(*child_entry);
                    self.lower_stmt(b, st);
                    b.goto(join_bb);
                }
                self.disable_fork_floor = prev_floor;
                self.in_fork = prev_in_fork;

                // Seal the join block: join_bb → resume_bb. IMPORTANT: this Goto is a
                // NEVER-EXECUTED sentinel. The engine intercepts a child the instant
                // its next bb equals join_bb (centralized loop-top check) and routes
                // it to on_child_complete + Step::Done BEFORE this block is fetched.
                // The parent is resumed DIRECTLY at resume_bb by the barrier. The
                // block exists only to keep the CFG well-formed (INV-2) and to give
                // join_bb a concrete, unique BlockId used as the completion sentinel.
                b.start_block(join_bb);
                b.goto(resume_bb);

                // Open resume_bb as the single continuation. Post-condition for the
                // caller: exactly one open block, at the parent's continuation point.
                b.start_block(resume_bb);
            }
            ast::Stmt::UserTaskCall { name, args, .. } => self.inline_task(b, name, args),
            // P1-2: these were warn+no-op — values never changed and an `@(ev)`
            // waited forever. A hard error beats silent misbehavior (defparam
            // precedent); real semantics are a Phase-2 item.
            // `->e` (v5 batch B): the named event is a 64-bit counter reg, so
            // the trigger is `e = e + 1` — every waiter (`@(e)`, mixed lists)
            // sees a guaranteed value change. A same-slot DOUBLE trigger still
            // changes the counter (0→2) where a 1-bit toggle would be lost
            // (0→1→0). The frozen WaitCause::Named / WakeCond::NamedEvent stay
            // reserved-unused; sim-ir is untouched by this lane.
            ast::Stmt::EventTrigger { name, .. } => {
                let net = self.resolve_net(name);
                if net == POISON_NET {
                    return; // resolve_net already errored
                }
                if !self.event_nets.contains(&net) {
                    self.error(
                        MsgCode::ElabUnsupported,
                        &format!(
                            "`->` target `{}` is not a named event",
                            name.segments
                                .iter()
                                .map(|s| s.name.as_str())
                                .collect::<Vec<_>>()
                                .join(".")
                        ),
                    );
                    return;
                }
                let sig = self.push_expr(ir::Expr::Signal { net, word: None });
                let one = self.const_u32_expr(1, 64);
                let add = self.push_expr(ir::Expr::Binary {
                    op: ir::BinOp::Add,
                    lhs: sig,
                    rhs: one,
                });
                let sid = self.push_stmt(ir::Stmt::BlockingAssign {
                    lhs: whole_net_lvalue(net),
                    rhs: add,
                });
                b.push_stmt_id(sid);
            }
            // Procedural continuous assignment (IEEE 1364 §9.3.1): reuses the
            // force machinery at a WEAKER rank — lowered as Stmt::Force /
            // Stmt::Release with the StmtId marked in the assign-rank sidecar
            // (the frozen Stmt has no Assign/Deassign variants; designs without
            // proc-assign lower byte-identically). Targets must be a WHOLE
            // VARIABLE: a net is E3018 (same check as procedural writes), a
            // bit/part-select is loud-unsupported (the force restriction).
            ast::Stmt::Assign { lhs, rhs, .. } => {
                let rhs_id = self.lower_expr(rhs);
                let lv = self.lower_lvalue(lhs);
                self.check_lvalue_kind(&lv, true);
                if !is_whole_single_net(&lv) {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "procedural assign target must be a whole variable (a bit/part-select is not a legal target)",
                    );
                    return;
                }
                let sid = self.push_stmt(ir::Stmt::Force {
                    lhs: lv,
                    rhs: rhs_id,
                });
                self.assign_ranks.insert(sid);
                b.push_stmt_id(sid);
            }
            ast::Stmt::Deassign { lhs, .. } => {
                let lv = self.lower_lvalue(lhs);
                self.check_lvalue_kind(&lv, true);
                if !is_whole_single_net(&lv) {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "deassign target must be a whole variable",
                    );
                    return;
                }
                let sid = self.push_stmt(ir::Stmt::Release { lhs: lv });
                self.assign_ranks.insert(sid);
                b.push_stmt_id(sid);
            }
            // force/release (IEEE 1364 §9.3.2) — WHOLE net/variable targets
            // only (bit/part-selects are illegal force targets per the LRM and
            // rejected loudly). v1 model = sample-once: the RHS is evaluated
            // at execution time (matching the iverilog oracle, which warns
            // "RHS will only be evaluated once"); full procedural-continuous
            // re-evaluation is a documented refinement.
            ast::Stmt::Force { lhs, rhs, .. } => {
                let rhs_id = self.lower_expr(rhs);
                let lv = self.lower_lvalue(lhs);
                if !is_whole_single_net(&lv) {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "force target must be a whole net/variable (a bit/part-select is not a legal force target)",
                    );
                    return;
                }
                let sid = self.push_stmt(ir::Stmt::Force {
                    lhs: lv,
                    rhs: rhs_id,
                });
                b.push_stmt_id(sid);
            }
            ast::Stmt::Release { lhs, .. } => {
                let lv = self.lower_lvalue(lhs);
                if !is_whole_single_net(&lv) {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "release target must be a whole net/variable",
                    );
                    return;
                }
                let sid = self.push_stmt(ir::Stmt::Release { lhs: lv });
                b.push_stmt_id(sid);
            }
            // ── wait fork — block on the implicit child barrier (v8) ────
            // No condition expr and no body: the scheduler resolves it against
            // this process's outstanding forked children (IEEE §9.6.1). Final
            // blocks already reject it via `stmt_has_timing` above.
            ast::Stmt::WaitFork { .. } => {
                let resume = b.new_block();
                b.end_block_with(ir::Terminator::Wait {
                    cond: ir::WaitCause::Fork,
                    resume: resume.raw(),
                });
                b.start_block(resume);
            }
            // v8 SVA subset: a concurrent assertion is a CONTINUOUSLY-checking
            // background process clocked by `@(clk)`, not a one-shot procedural
            // statement — collect it and emit nothing into the enclosing block.
            // It is materialized as a synthesized clocked checker after the
            // module's process loop (`materialize_sva_checkers`).
            ast::Stmt::ConcurrentAssert {
                clock,
                disable_iff,
                antecedent,
                implication_kind,
                consequent,
                consequent_clock,
                pass,
                fail,
                span,
            } => {
                // Named-property INSTANCE: `assert property(NAME)` parses to an empty
                // clock + a `Sequence::Instance` antecedent. Splice the declared
                // property's REAL spec (clock/disable_iff/ante/kind/cons) here, at
                // collect time, so the single-clock gate in `materialize_sva_checkers`
                // sees the named property's clock (never the empty sentinel). The
                // call-site action block (pass/fail) is carried through.
                if let ast::Sequence::Instance { name, args, .. } = antecedent {
                    match self.prop_table.get(&name.name).cloned() {
                        Some(pd) if pd.formals.len() != args.len() => {
                            // Arity mismatch (slice A1) — includes a bare `p` instance
                            // of a parameterized property (0 args vs N formals).
                            self.error(
                                MsgCode::ElabUnsupported,
                                &format!(
                                    "named property `{}` expects {} formal argument(s), got {}",
                                    name.name,
                                    pd.formals.len(),
                                    args.len()
                                ),
                            );
                        }
                        Some(pd) if pd.formals.is_empty() => {
                            // Byte-identical to before slice A1 (no substitution).
                            self.pending_sva.push(PendingSva {
                                clock: pd.clock,
                                disable_iff: pd.disable_iff,
                                ante: pd.antecedent,
                                kind: pd.implication_kind,
                                cons: pd.consequent,
                                pass: pass.clone(),
                                fail: fail.clone(),
                                cons_clock: pd.consequent_clock,
                                span: *span,
                            });
                        }
                        Some(pd) => {
                            // Parameterized property: bind actuals → formals and
                            // substitute through the whole spliced spec (clock,
                            // disable, antecedent, consequent) before scheduling.
                            let map = sva_formal_map(&pd.formals, args);
                            self.pending_sva.push(PendingSva {
                                clock: subst_sensitivity(&pd.clock, &map),
                                disable_iff: pd.disable_iff.as_ref().map(|e| subst_expr(e, &map)),
                                ante: subst_sequence(&pd.antecedent, &map),
                                kind: pd.implication_kind,
                                cons: subst_sequence(&pd.consequent, &map),
                                pass: pass.clone(),
                                fail: fail.clone(),
                                cons_clock: pd
                                    .consequent_clock
                                    .as_ref()
                                    .map(|s| subst_sensitivity(s, &map)),
                                span: *span,
                            });
                        }
                        None => {
                            // Distinguish a declared-but-wrong-kind name from a
                            // genuinely unknown one (review 2026-06-16: a net or a
                            // sequence name reported a misleading "unknown property").
                            let msg = if self.seq_table.contains_key(&name.name) {
                                format!(
                                    "`{}` is a named SEQUENCE, not a property; a bare \
                                     sequence used as a property (without `|->`/`|=>`) \
                                     is unsupported in this subset",
                                    name.name
                                )
                            } else {
                                format!(
                                    "unknown property `{}` in `assert property(...)` \
                                     (declare a `property {} ; … endproperty`, or use a \
                                     clocked boolean property `@(...) {}`)",
                                    name.name, name.name, name.name
                                )
                            };
                            self.error(MsgCode::ElabUnsupported, &msg);
                        }
                    }
                } else {
                    self.pending_sva.push(PendingSva {
                        clock: clock.clone(),
                        disable_iff: disable_iff.clone(),
                        ante: antecedent.clone(),
                        kind: *implication_kind,
                        cons: consequent.clone(),
                        pass: pass.clone(),
                        fail: fail.clone(),
                        cons_clock: consequent_clock.clone(),
                        span: *span,
                    });
                }
            }
            // Parse error is the ONE genuinely-fatal stmt: keep self.error.
            ast::Stmt::Error(_) => {
                self.error(
                    MsgCode::ElabUnsupported,
                    "cannot lower parse-error statement",
                );
            }
        }
    }

    // ── case → Branch chain ────────────────────────────────────────
    fn lower_case(
        &mut self,
        b: &mut ProcessBuilder,
        kind: ast::CaseKind,
        scrutinee: &ast::Expr,
        items: &[ast::CaseItem],
    ) {
        // casez/casex wildcard semantics are realized per-label by masking the
        // label's unknown (`?`/`z`/`x`) bits out of the compare (see
        // `case_label_eq`). Plain `case` is an exact 4-state `===`.
        let scrut_id = self.lower_expr(scrutinee);
        let merge = b.new_block();

        // Pre-allocate each Match arm's entry block; pin the default body.
        // Allocation order (deterministic): merge, then each Match arm block in
        // source order, then per-label miss-blocks during the cascade.
        let mut arm_bodies: Vec<(BlockId, &ast::Stmt)> = Vec::new();
        let mut default_body: Option<&ast::Stmt> = None;
        let mut tests: Vec<(&[ast::Expr], BlockId)> = Vec::new();
        for it in items {
            match it {
                ast::CaseItem::Match { labels, body, .. } => {
                    let arm = b.new_block();
                    tests.push((labels.as_slice(), arm));
                    arm_bodies.push((arm, body));
                }
                ast::CaseItem::Default { body, .. } => default_body = Some(body),
            }
        }

        // Test cascade: for each label, a wildcard-aware match → arm else next.
        for (labels, arm) in &tests {
            for label in *labels {
                let eq = self.case_label_eq(scrut_id, label, kind);
                let next = b.new_block();
                b.end_block_with(ir::Terminator::Branch {
                    cond: eq,
                    then_bb: arm.raw(),
                    else_bb: next.raw(),
                });
                b.start_block(next);
            }
        }
        // All tests missed → the default (or empty) → merge.
        if let Some(body) = default_body {
            self.lower_stmt(b, body);
        }
        b.goto(merge);

        // Lower each arm body, each ending Goto(merge).
        for (arm, body) in arm_bodies {
            b.start_block(arm);
            self.lower_stmt(b, body);
            b.goto(merge);
        }
        b.start_block(merge);
    }

    /// v7: `x = $random(seed)` special form. The seed must lower to a plain
    /// whole-net Signal (an integral VARIABLE — IEEE 1364 §17.9.1); the rhs
    /// becomes `SysFunc{Random,[seed]}` which the engine intercepts
    /// statement-level (`StmtEffect::SeededRandom` — seed written back in the
    /// WRITE phase). Returns false when the rhs is not a seeded $random.
    /// An intra-assignment delay keeps draw-now/write-later semantics by
    /// riding the SAME desugar as a plain blocking (`tmp = draw; #d; lhs=tmp`)
    /// — the seed updates at the DRAW, like iverilog.
    fn random_seeded_special(
        &mut self,
        b: &mut ProcessBuilder,
        lhs: &ast::Lvalue,
        delay: Option<&ast::Delay>,
        rhs: &ast::Expr,
    ) -> bool {
        let ast::ExprKind::SysCall { name, args } = &rhs.kind else {
            return false;
        };
        if name.name != "$random" || args.is_empty() {
            return false;
        }
        if args.len() > 1 {
            self.error(MsgCode::ElabUnsupported, "$random takes at most one seed");
            return true;
        }
        let seed_id = self.lower_expr(&args[0]);
        if !matches!(
            self.exprs.get(seed_id as usize),
            Some(ir::Expr::Signal { word: None, .. })
        ) {
            self.error(
                MsgCode::ElabUnsupported,
                "$random seed must be a plain integral variable (v7)",
            );
            return true;
        }
        let rhs_id = self.push_expr(ir::Expr::SysFunc {
            which: ir::SysFuncId::Random,
            args: vec![seed_id],
        });
        let lv = self.lower_lvalue(lhs);
        self.check_lvalue_kind(&lv, true);
        if let Some(d) = delay {
            // capture-now/write-later: the DRAW (and seed update) happens at
            // the capture statement; only the lhs write is delayed.
            let w = self.ir_lvalue_width(&lv);
            let tmp = self.fresh_ia_tmp(w);
            let cap = self.push_stmt(ir::Stmt::BlockingAssign {
                lhs: whole_net_lvalue(tmp),
                rhs: rhs_id,
            });
            b.push_stmt_id(cap);
            let (amount, region) = self.lower_delay(d);
            let resume = b.new_block();
            b.end_block_with(ir::Terminator::Delay {
                amount,
                region,
                resume: resume.raw(),
            });
            b.start_block(resume);
            let tmp_read = self.push_expr(ir::Expr::Signal {
                net: tmp,
                word: None,
            });
            let wr = self.push_stmt(ir::Stmt::BlockingAssign {
                lhs: lv,
                rhs: tmp_read,
            });
            b.push_stmt_id(wr);
        } else {
            let sid = self.push_stmt(ir::Stmt::BlockingAssign {
                lhs: lv,
                rhs: rhs_id,
            });
            b.push_stmt_id(sid);
        }
        true
    }

    /// v7: `ok = $value$plusargs(fmt, var)` special form (the seeded-$random
    /// family — the engine writes `var` in the WRITE phase). The fmt must be
    /// a string LITERAL with at most one conversion spec from the supported
    /// set (%d/%h/%x/%o/%b/%s — %e/%f/%g real conversions are loud-deferred);
    /// `var` must lower to a plain whole-net Signal.
    fn value_plusargs_special(
        &mut self,
        b: &mut ProcessBuilder,
        lhs: &ast::Lvalue,
        delay: Option<&ast::Delay>,
        rhs: &ast::Expr,
    ) -> bool {
        let ast::ExprKind::SysCall { name, args } = &rhs.kind else {
            return false;
        };
        if name.name != "$value$plusargs" {
            return false;
        }
        if args.len() != 2 {
            self.error(
                MsgCode::ElabUnsupported,
                "$value$plusargs takes (format, variable)",
            );
            return true;
        }
        let ast::ExprKind::StrLit { .. } = &args[0].kind else {
            self.error(
                MsgCode::ElabUnsupported,
                "$value$plusargs needs a string-literal format (v7)",
            );
            return true;
        };
        let fmt_id = self.lower_expr(&args[0]);
        // validate the conversion set on the DECODED text (the const pool
        // holds the unescaped bytes the engine will see).
        if let Some(ir::Expr::Const { val }) = self.exprs.get(fmt_id as usize) {
            let c = &self.consts[*val as usize];
            let mut bytes = Vec::new();
            let nbytes = (c.width as usize).div_ceil(8);
            for bi in (0..nbytes).rev() {
                let bit = bi * 8;
                let w = bit / 64;
                let sh = bit % 64;
                bytes.push((c.bits.val.get(w).copied().unwrap_or(0) >> sh) as u8);
            }
            let text: String = String::from_utf8_lossy(&bytes).into_owned();
            let specs: Vec<char> = text
                .match_indices('%')
                .filter_map(|(i, _)| text[i + 1..].chars().next())
                .collect();
            if specs.len() > 1
                || specs.first().is_some_and(|c| {
                    !matches!(
                        c,
                        'd' | 'D' | 'h' | 'H' | 'x' | 'X' | 'o' | 'O' | 'b' | 'B' | 's' | 'S'
                    )
                })
            {
                self.error(
                    MsgCode::ElabUnsupported,
                    "$value$plusargs format supports one %d/%h/%x/%o/%b/%s spec (v7)",
                );
                return true;
            }
        }
        let var_id = self.lower_expr(&args[1]);
        if !matches!(
            self.exprs.get(var_id as usize),
            Some(ir::Expr::Signal { word: None, .. })
        ) {
            self.error(
                MsgCode::ElabUnsupported,
                "$value$plusargs target must be a plain variable (v7)",
            );
            return true;
        }
        let rhs_id = self.push_expr(ir::Expr::SysFunc {
            which: ir::SysFuncId::ValuePlusargs,
            args: vec![fmt_id, var_id],
        });
        let lv = self.lower_lvalue(lhs);
        self.check_lvalue_kind(&lv, true);
        if let Some(d) = delay {
            // capture-now/write-later (the shared intra-assignment desugar) —
            // the plusarg search and var write happen at the CAPTURE.
            let w = self.ir_lvalue_width(&lv);
            let tmp = self.fresh_ia_tmp(w);
            let cap = self.push_stmt(ir::Stmt::BlockingAssign {
                lhs: whole_net_lvalue(tmp),
                rhs: rhs_id,
            });
            b.push_stmt_id(cap);
            let (amount, region) = self.lower_delay(d);
            let resume = b.new_block();
            b.end_block_with(ir::Terminator::Delay {
                amount,
                region,
                resume: resume.raw(),
            });
            b.start_block(resume);
            let tmp_read = self.push_expr(ir::Expr::Signal {
                net: tmp,
                word: None,
            });
            let wr = self.push_stmt(ir::Stmt::BlockingAssign {
                lhs: lv,
                rhs: tmp_read,
            });
            b.push_stmt_id(wr);
        } else {
            let sid = self.push_stmt(ir::Stmt::BlockingAssign {
                lhs: lv,
                rhs: rhs_id,
            });
            b.push_stmt_id(sid);
        }
        true
    }

    /// v7: `fd = $fopen(name[, mode])` special form — the open mutates the
    /// engine file table (WRITE phase). Both arguments must be string
    /// LITERALS (a runtime filename needs the P2-C string type).
    fn fopen_special(
        &mut self,
        b: &mut ProcessBuilder,
        lhs: &ast::Lvalue,
        delay: Option<&ast::Delay>,
        rhs: &ast::Expr,
    ) -> bool {
        let ast::ExprKind::SysCall { name, args } = &rhs.kind else {
            return false;
        };
        if name.name != "$fopen" {
            return false;
        }
        if args.is_empty() || args.len() > 2 {
            self.error(MsgCode::ElabUnsupported, "$fopen takes (name[, mode])");
            return true;
        }
        if !args
            .iter()
            .all(|a| matches!(a.kind, ast::ExprKind::StrLit { .. }))
        {
            self.error(
                MsgCode::ElabUnsupported,
                "$fopen arguments must be string literals (v7)",
            );
            return true;
        }
        let arg_ids: Vec<u32> = args.iter().map(|a| self.lower_expr(a)).collect();
        let rhs_id = self.push_expr(ir::Expr::SysFunc {
            which: ir::SysFuncId::Fopen,
            args: arg_ids,
        });
        let lv = self.lower_lvalue(lhs);
        self.check_lvalue_kind(&lv, true);
        if delay.is_some() {
            // exotic; keep the contract narrow + loud rather than guessing
            // open-now/assign-later semantics nobody writes.
            self.error(
                MsgCode::ElabUnsupported,
                "intra-assignment delay on $fopen is unsupported (v7)",
            );
            return true;
        }
        let sid = self.push_stmt(ir::Stmt::BlockingAssign {
            lhs: lv,
            rhs: rhs_id,
        });
        b.push_stmt_id(sid);
        true
    }

    // ── v7 P2-D packages (IR-0 — elaborate-side symbol flattening) ──
    /// Fold one package body: params/localparams + enum labels (decl order,
    /// package-local visibility) into `pkg_consts`; clone funcs/tasks into
    /// `pkg_funcs`/`pkg_tasks`. Anything else in a package body is loud
    /// (variables / cont-assigns / procs are outside the v7 scope).
    fn elaborate_package(&mut self, pm: &ast::ModuleDecl) {
        let pkg = pm.name.name.clone();
        // fold under a synthetic scope so the package's own params resolve
        // while folding later ones (`localparam L2 = W * 2`).
        let saved_prefix = std::mem::replace(&mut self.cur_prefix, format!("$pkg${pkg}"));
        let mut saved: Vec<(String, Option<i64>)> = Vec::new();
        let mut consts: BTreeMap<String, i64> = BTreeMap::new();
        let mut funcs: BTreeMap<String, ast::FunctionDef> = BTreeMap::new();
        let mut tasks: BTreeMap<String, ast::TaskDef> = BTreeMap::new();
        for item in &pm.body {
            match item {
                ast::ModuleItem::Param(p) => {
                    let v = self.const_eval_in_scope(&p.value).unwrap_or_else(|| {
                        self.error(
                            MsgCode::ElabUnsupported,
                            &format!(
                                "package parameter `{}` value is not a foldable constant",
                                p.name.name
                            ),
                        );
                        0
                    });
                    let key = self.fq(&p.name.name);
                    saved.push((key.clone(), self.params.insert(key, v)));
                    consts.insert(p.name.name.clone(), v);
                }
                ast::ModuleItem::Typedef(td) => {
                    #[allow(irrefutable_let_patterns)]
                    if let ast::TypedefKind::Enum { labels, .. } = &td.kind {
                        let mut next: i64 = 0;
                        for l in labels {
                            let v = match &l.value {
                                Some(e) => self.const_eval_in_scope(e).unwrap_or_else(|| {
                                    self.error(
                                        MsgCode::ElabUnsupported,
                                        &format!(
                                            "enum label `{}` value is not a foldable constant",
                                            l.name.name
                                        ),
                                    );
                                    0
                                }),
                                None => next,
                            };
                            next = v + 1;
                            let key = self.fq(&l.name.name);
                            saved.push((key.clone(), self.params.insert(key, v)));
                            consts.insert(l.name.name.clone(), v);
                        }
                    }
                    // Alias/Struct typedefs ride the parser's unit-global
                    // typedef map (type NAMES are parse-resolved) — no
                    // elaborate-side symbol needed.
                }
                ast::ModuleItem::Func(f) => {
                    funcs.insert(f.name.name.clone(), f.clone());
                }
                ast::ModuleItem::Task(t) => {
                    tasks.insert(t.name.name.clone(), t.clone());
                }
                ast::ModuleItem::Import(_) => {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "imports inside a package are outside the v7 scope",
                    );
                }
                _ => {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "only parameters/typedefs/functions/tasks are supported \
                         in a package body (v7)",
                    );
                }
            }
        }
        for (k, prev) in saved.into_iter().rev() {
            match prev {
                Some(v) => {
                    self.params.insert(k, v);
                }
                None => {
                    self.params.remove(&k);
                }
            }
        }
        self.cur_prefix = saved_prefix;
        self.pkg_consts.insert(pkg.clone(), consts);
        self.pkg_funcs.insert(pkg.clone(), funcs);
        self.pkg_tasks.insert(pkg, tasks);
    }

    /// Bind one import's CONST symbols into the current module scope.
    fn apply_import_consts(
        &mut self,
        imp: &ast::ImportDecl,
        saved_params: &mut Vec<(String, Option<i64>)>,
    ) {
        let pkg = imp.pkg.name.as_str();
        let Some(consts) = self.pkg_consts.get(pkg) else {
            self.error(
                MsgCode::ElabUnsupported,
                &format!("import from unknown package `{pkg}`"),
            );
            return;
        };
        match &imp.item {
            None => {
                let all: Vec<(String, i64)> = consts.iter().map(|(k, &v)| (k.clone(), v)).collect();
                for (name, v) in all {
                    let key = self.fq(&name);
                    saved_params.push((key.clone(), self.params.insert(key, v)));
                }
            }
            Some(sym) => {
                if let Some(&v) = consts.get(&sym.name) {
                    let key = self.fq(&sym.name);
                    saved_params.push((key.clone(), self.params.insert(key, v)));
                } else if !self
                    .pkg_funcs
                    .get(pkg)
                    .is_some_and(|f| f.contains_key(&sym.name))
                    && !self
                        .pkg_tasks
                        .get(pkg)
                        .is_some_and(|t| t.contains_key(&sym.name))
                {
                    self.error(
                        MsgCode::ElabUnsupported,
                        &format!("package `{pkg}` has no symbol `{}`", sym.name),
                    );
                }
            }
        }
    }

    /// Bind one import's FUNCTION/TASK symbols (local definitions win —
    /// skip-if-present, called after the module's own (3.5) collection).
    fn apply_import_routines(&mut self, imp: &ast::ImportDecl) {
        let pkg = imp.pkg.name.as_str();
        let (funcs, tasks) = match (self.pkg_funcs.get(pkg), self.pkg_tasks.get(pkg)) {
            (Some(f), Some(t)) => (f.clone(), t.clone()),
            _ => return, // unknown package already diagnosed in the const pass
        };
        match &imp.item {
            None => {
                for (n, f) in funcs {
                    self.func_table.entry(n).or_insert(f);
                }
                for (n, t) in tasks {
                    self.task_table.entry(n).or_insert(t);
                }
            }
            Some(sym) => {
                if let Some(f) = funcs.get(&sym.name) {
                    self.func_table
                        .entry(sym.name.clone())
                        .or_insert_with(|| f.clone());
                }
                if let Some(t) = tasks.get(&sym.name) {
                    self.task_table
                        .entry(sym.name.clone())
                        .or_insert_with(|| t.clone());
                }
            }
        }
    }

    /// v7 P2-C: `dest = $sformatf(fmt, args…)` special form. The format
    /// must be a string LITERAL; rendering runs kernel-side (WRITE phase,
    /// `StmtEffect::Sformatf`) and the result is a string-domain value the
    /// funnel converts per the destination (§6.16).
    fn sformatf_special(
        &mut self,
        b: &mut ProcessBuilder,
        lhs: &ast::Lvalue,
        delay: Option<&ast::Delay>,
        rhs: &ast::Expr,
    ) -> bool {
        let ast::ExprKind::SysCall { name, args } = &rhs.kind else {
            return false;
        };
        if name.name != "$sformatf" {
            return false;
        }
        let Some(ast::ExprKind::StrLit { .. }) = args.first().map(|a| &a.kind) else {
            self.error(
                MsgCode::ElabUnsupported,
                "$sformatf needs a string-literal format (v7)",
            );
            return true;
        };
        if delay.is_some() {
            self.error(
                MsgCode::ElabUnsupported,
                "intra-assignment delay on $sformatf is unsupported (v7)",
            );
            return true;
        }
        let arg_ids: Vec<u32> = args.iter().map(|a| self.lower_expr(a)).collect();
        let rhs_id = self.push_expr(ir::Expr::SysFunc {
            which: ir::SysFuncId::Sformatf,
            args: arg_ids,
        });
        let lv = self.lower_lvalue(lhs);
        self.check_lvalue_kind(&lv, true);
        let sid = self.push_stmt(ir::Stmt::BlockingAssign {
            lhs: lv,
            rhs: rhs_id,
        });
        b.push_stmt_id(sid);
        true
    }

    // ── $bits const-fold (v7, IR-0) ────────────────────────────────
    /// `$bits(arg)` → 32-bit Const. The argument is a TYPE reference, never
    /// evaluated; unsupported shapes are LOUD (E3009), never a silent 0.
    fn lower_bits_fold(&mut self, arg: &ast::Expr) -> u32 {
        let n = self
            .bits_of_view(arg, false)
            .or_else(|| {
                // General expression: lower it (dead arena nodes — the arg is
                // not evaluated at runtime) and fold its self-determined width.
                let eid = self.lower_expr(arg);
                self.ir_bits_of(eid)
            })
            .filter(|&n| n > 0);
        match n {
            Some(n) => self.const_u32_expr(n, 32),
            None => {
                self.error(
                    MsgCode::ElabUnsupported,
                    "$bits argument shape unsupported (nets, array views, and \
                     self-determined expressions fold; v7)",
                );
                self.placeholder_expr()
            }
        }
    }

    /// Width of the shapes `$bits` can take WITHOUT lowering: a static-array
    /// view (whole array = total bits, partial chain = remaining slice), a
    /// plain net ident, or a bound param (unsized i64 domain → 32,
    /// iverilog-pinned). Inline-subst formals fall through to the lowering
    /// path (the subst maps them to the actual's expr).
    ///
    /// `prescan_first`: in CONST contexts (param binding (3b), range specs)
    /// the current module's nets are not in the real table yet — the
    /// decl-order prescan is the authority there. At runtime the real table
    /// resolves first (it sees generate-scoped shadows the prescan doesn't).
    fn bits_of_view(&self, e: &ast::Expr, prescan_first: bool) -> Option<u32> {
        if let ast::ExprKind::Paren { inner } = &e.kind {
            return self.bits_of_view(inner, prescan_first);
        }
        let from_prescan = |me: &Self| -> Option<u32> {
            let (root, depth) = ident_index_chain(e)?;
            // mirror the lower_expr Ident resolution priority: a bound
            // formal/param shadows a same-named decl.
            if me.subst_lookup(root).is_some()
                || me.out_subst_lookup(root).is_some()
                || me.lookup_scoped(root).is_some()
            {
                return None;
            }
            let (elem, dims) = me.bits_prescan.get(root)?;
            if depth > dims.len() {
                return None; // indexing into packed space → lowering path
            }
            let rem: u64 = dims[depth..].iter().product();
            u32::try_from(elem.saturating_mul(rem)).ok()
        };
        let from_table = |me: &Self| -> Option<u32> {
            if let Some((net, idxs)) = me.expr_array_view(e) {
                let nv = me.nets.get(net as usize)?;
                let w = nv.width.max(1) as u64;
                if idxs.is_empty() {
                    return u32::try_from(w * nv.array_len.max(1) as u64).ok();
                }
                let dims = me.array_dims.get(&net)?;
                if idxs.len() > dims.len() {
                    return None; // trailing packed selects → lowering path
                }
                let rem: u64 = dims[idxs.len()..]
                    .iter()
                    .map(|&(lo, hi)| hi.abs_diff(lo) as u64 + 1)
                    .product();
                return u32::try_from(rem * w).ok();
            }
            if let ast::ExprKind::Ident(p) = &e.kind {
                if let [seg] = p.segments.as_slice() {
                    let name = seg.name.as_str();
                    if me.subst_lookup(name).is_some() || me.out_subst_lookup(name).is_some() {
                        return None; // formal — resolve via the lowering path
                    }
                    if me.lookup_scoped(name).is_some() {
                        return Some(32); // param/genvar (width-less i64 domain)
                    }
                    if let Some(net) = me.lookup_net_scoped(name) {
                        let nv = me.nets.get(net as usize)?;
                        if nv.kind == ir::NetKind::String {
                            return None; // dynamic length — loud at the site
                        }
                        return Some(nv.width.max(1));
                    }
                }
            }
            None
        };
        if prescan_first {
            from_prescan(self).or_else(|| from_table(self))
        } else {
            from_table(self).or_else(|| from_prescan(self))
        }
    }

    /// v7 `$bits` prescan (see `bits_prescan`): record one body decl's widths.
    /// Every fold failure is a SILENT skip — the `$bits` call site is the loud
    /// one; the real net lowering later re-folds with full diagnostics.
    fn prescan_net_bits(&mut self, d: &ast::NetVarDecl) {
        let fold_range = |me: &Self, r: &ast::Range| -> Option<u64> {
            match (
                me.const_eval_in_scope(&r.msb),
                me.const_eval_in_scope(&r.lsb),
            ) {
                (Some(m), Some(l)) if m >= 0 && l >= 0 => Some(m.abs_diff(l) + 1),
                _ => None,
            }
        };
        if matches!(d.kind, ast::NetVarKind::String) {
            return; // dynamic length — $bits on a string stays loud
        }
        let elem: u64 = match d.kind {
            ast::NetVarKind::Integer => 32,
            ast::NetVarKind::Real
            | ast::NetVarKind::Realtime
            | ast::NetVarKind::Time
            | ast::NetVarKind::Event => 64,
            _ => {
                let mut w = match &d.range {
                    None => 1u64,
                    Some(r) => match fold_range(self, r) {
                        Some(w) => w,
                        None => return,
                    },
                };
                for r in &d.packed {
                    match fold_range(self, r) {
                        Some(pw) => w = w.saturating_mul(pw),
                        None => return,
                    }
                }
                w
            }
        };
        'names: for n in &d.names {
            let mut dims: Vec<u64> = Vec::new();
            for dim in &n.unpacked {
                match dim {
                    ast::Dim::Range(r) => match fold_range(self, r) {
                        Some(len) => dims.push(len),
                        None => continue 'names,
                    },
                    ast::Dim::Size(e) => match self.const_eval_in_scope(e) {
                        Some(s) if s > 0 => dims.push(s as u64),
                        _ => continue 'names,
                    },
                    // dyn/queue/assoc — no static bit size
                    _ => continue 'names,
                }
            }
            self.bits_prescan.insert(n.name.name.clone(), (elem, dims));
        }
    }

    /// Self-determined width of an already-lowered expr (mirrors the engine's
    /// width table rules over the partial arena). `None` ⇒ loud at the caller.
    fn ir_bits_of(&self, eid: u32) -> Option<u32> {
        let e = self.exprs.get(eid as usize)?;
        Some(match e {
            ir::Expr::Const { val } => self.consts.get(*val as usize)?.width.max(1),
            ir::Expr::Signal { net, .. } => {
                let nv = self.nets.get(*net as usize)?;
                // review F1: a String handle's table width is 0 — `.max(1)`
                // made `$bits(s)` a silent 1. Dynamic length ⇒ loud at site.
                if nv.kind == ir::NetKind::String {
                    return None;
                }
                nv.width.max(1)
            }
            ir::Expr::Select { width, kind, .. } => match kind {
                ir::SelKind::Bit => 1,
                // direct Const OR the synthesized `Add(Sub(msb,lsb),1)` width
                // tree (mirrors the engine's shallow width-edge fold).
                _ => self.width_edge_u32(*width)?,
            },
            ir::Expr::Concat { parts } => {
                let mut s: u64 = 0;
                for &p in parts {
                    s += self.ir_bits_of(p)? as u64;
                }
                u32::try_from(s).ok()?
            }
            ir::Expr::Replicate { count, value } => {
                let c = self.width_edge_u32(*count)? as u64;
                let vw = self.ir_bits_of(*value)? as u64;
                u32::try_from(c * vw).ok()?
            }
            ir::Expr::Unary { op, operand } => match op {
                ir::UnOp::Plus | ir::UnOp::Minus | ir::UnOp::BitNot => self.ir_bits_of(*operand)?,
                _ => 1, // reductions / LogNot
            },
            ir::Expr::Binary { op, lhs, rhs } => {
                use ir::BinOp::*;
                match op {
                    Add | Sub | Mul | Div | Mod | Pow | BitAnd | BitOr | BitXor | BitXnor => {
                        self.ir_bits_of(*lhs)?.max(self.ir_bits_of(*rhs)?)
                    }
                    Shl | Shr | AShl | AShr => self.ir_bits_of(*lhs)?,
                    _ => 1, // comparisons / case(z/x) / logical
                }
            }
            ir::Expr::Ternary { then_e, else_e, .. } => {
                self.ir_bits_of(*then_e)?.max(self.ir_bits_of(*else_e)?)
            }
            ir::Expr::SysFunc { which, args } => {
                use ir::SysFuncId as F;
                match which {
                    F::Time | F::Realtime | F::Itor | F::BitsToReal | F::RealToBits => 64,
                    F::Signed | F::Unsigned => {
                        let a = *args.first()?;
                        self.ir_bits_of(a)?
                    }
                    F::Clog2
                    | F::Rtoi
                    | F::DynSize
                    | F::AssocNum
                    | F::AssocFirst
                    | F::AssocNext
                    | F::AssocLast
                    | F::AssocPrev
                    | F::Random
                    | F::Urandom
                    | F::UrandomRange
                    | F::CountOnes
                    | F::Stime
                    | F::Fopen
                    | F::TestPlusargs
                    | F::ValuePlusargs
                    | F::StrLen
                    | F::StrCmp => 32,
                    F::AssocExists | F::OneHot | F::OneHot0 | F::IsUnknown => 1,
                    F::StrGetC => 8,
                    // element-typed pops / dynamic-length string producers
                    F::QPopBack
                    | F::QPopFront
                    | F::Sformatf
                    | F::StrSubstr
                    | F::StrToUpper
                    | F::StrToLower => return None,
                }
            }
            ir::Expr::Call { .. } => return None,
        })
    }

    /// Width-edge fold for `ir_bits_of`: a direct `Const`, or the shallow
    /// `Add(Sub(msb,lsb),1)` tree elaborate synthesizes for `[msb:lsb]` —
    /// the same two shapes the engine's width-table fold accepts.
    fn width_edge_u32(&self, eid: u32) -> Option<u32> {
        if let Some(c) = self.const_of_expr_u32(eid) {
            return Some(c);
        }
        match self.exprs.get(eid as usize)? {
            ir::Expr::Binary {
                op: ir::BinOp::Add,
                lhs,
                rhs,
            } => {
                let a = self.width_edge_u32(*lhs)?;
                let b = self.width_edge_u32(*rhs)?;
                Some(a.saturating_add(b))
            }
            ir::Expr::Binary {
                op: ir::BinOp::Sub,
                lhs,
                rhs,
            } => {
                let a = self.width_edge_u32(*lhs)?;
                let b = self.width_edge_u32(*rhs)?;
                Some(a.saturating_sub(b))
            }
            _ => None,
        }
    }

    /// Per-label equality test for a case arm. Plain `case` is the exact 4-state
    /// `scrut === label`.
    ///
    /// `casez`/`casex` lower to the dedicated v7 match ops: a bit position is
    /// don't-care iff EITHER side (label or RUNTIME scrutinee) has z there
    /// (`CasezEq`) or x-or-z (`CasexEq`); every remaining position compares
    /// 4-state exact. This replaces the v1 `redor(scrut^label) !== 1` formula,
    /// which was exact for casex but over-lenient for casez (it wildcarded x
    /// too — `casez(1x10)` falsely matched `1010`; iverilog-pinned strict).
    fn case_label_eq(&mut self, scrut_id: u32, label: &ast::Expr, kind: ast::CaseKind) -> u32 {
        let lbl_id = self.lower_expr(label);
        let op = match kind {
            ast::CaseKind::Case => ir::BinOp::CaseEq,
            ast::CaseKind::Casez => ir::BinOp::CasezEq,
            ast::CaseKind::Casex => ir::BinOp::CasexEq,
        };
        self.push_expr(ir::Expr::Binary {
            op,
            lhs: scrut_id,
            rhs: lbl_id,
        })
    }

    // ── loops (SECONDARY) ──────────────────────────────────────────
    fn lower_while(&mut self, b: &mut ProcessBuilder, cond: &ast::Expr, body: &ast::Stmt) {
        let head = b.new_block();
        let body_bb = b.new_block();
        let exit = b.new_block();
        b.goto(head);
        b.start_block(head);
        let c = self.lower_expr(cond);
        b.end_block_with(ir::Terminator::Branch {
            cond: c,
            then_bb: body_bb.raw(),
            else_bb: exit.raw(),
        });
        b.start_block(body_bb);
        self.lower_stmt(b, body);
        b.goto(head); // back-edge
        b.start_block(exit);
    }

    fn lower_forever(&mut self, b: &mut ProcessBuilder, body: &ast::Stmt) {
        let head = b.new_block();
        b.goto(head);
        b.start_block(head);
        self.lower_stmt(b, body);
        b.goto(head); // unconditional back-edge
                      // No natural continue point; open a fresh (unreachable) block so the
                      // post-condition (cursor open) holds. It gets Return at finish.
        let dead = b.new_block();
        b.start_block(dead);
    }

    /// `repeat(N)` with a const, small `N` → straight unroll (no runtime counter,
    /// which `Stmt`'s net-only Lvalue cannot express). Non-const/large → reject.
    fn lower_repeat(&mut self, b: &mut ProcessBuilder, count: &ast::Expr, body: &ast::Stmt) {
        match const_eval_u32(count) {
            Some(n) if n <= REPEAT_UNROLL_CAP => {
                for _ in 0..n {
                    self.lower_stmt(b, body);
                }
            }
            _ => self.warn("repeat with non-constant or large count skipped (v2); body omitted"),
        }
    }

    /// `for (init; cond; step) body` desugars to `init; while (cond) { body; step }`.
    /// The counter is an ordinary declared net (classic Verilog `integer i`), the
    /// same runtime-counter shape `lower_while` already handles — there is no
    /// special suspend-surviving state, so the net-only `Stmt` Lvalue suffices.
    /// (A C99-style `for (int i = 0; …)` block-local counter would need an
    /// automatic per-process frame, which v1 lacks; the parser produces an
    /// assignment `init`, not a declaration, so that case does not arise here.)
    fn lower_for(
        &mut self,
        b: &mut ProcessBuilder,
        init: &ast::Stmt,
        cond: &ast::Expr,
        step: &ast::Stmt,
        body: &ast::Stmt,
    ) {
        self.lower_stmt(b, init); // run the initializer once, before the loop head
        let head = b.new_block();
        let body_bb = b.new_block();
        let exit = b.new_block();
        b.goto(head);
        b.start_block(head);
        let c = self.lower_expr(cond);
        b.end_block_with(ir::Terminator::Branch {
            cond: c,
            then_bb: body_bb.raw(),
            else_bb: exit.raw(),
        });
        b.start_block(body_bb);
        self.lower_stmt(b, body);
        self.lower_stmt(b, step); // step runs at the END of each iteration
        b.goto(head); // back-edge to re-test the condition
        b.start_block(exit);
    }

    // ── in-body @(...) / wait → WaitCause; #delay → (amount, region) ─
    /// In-body `@(...)` → ONE `WaitCause`. Single edge term → `Edge`; all bare →
    /// `Level`; multi-edge → ERROR (the frozen `WaitCause::Edge` carries one term;
    /// silently waiting on the FIRST term only changed wake semantics — P1-4).
    /// `@(*)` is handled by the `EventCtrl` arm (read-set patch), not here.
    fn lower_event_wait_cause(&mut self, ctrl: &ast::Sensitivity) -> ir::WaitCause {
        match ctrl {
            ast::Sensitivity::Star => {
                unreachable!("in-body @(*) is lowered by the EventCtrl arm")
            }
            ast::Sensitivity::List(list) => {
                let n_edges = list
                    .iter()
                    .filter(|ev| !matches!(ev.edge, ast::Edge::NoEdge))
                    .count();
                if n_edges > 0 {
                    if list.len() > 1 {
                        self.error(
                            MsgCode::ElabUnsupported,
                            "multi-term in-body edge wait is unsupported in v1 \
                             (the IR carries a single edge term; move it to a \
                             block-header sensitivity or split the wait)",
                        );
                    }
                    let ev = list
                        .iter()
                        .find(|ev| !matches!(ev.edge, ast::Edge::NoEdge))
                        .expect("n_edges>0 ⇒ at least one edge term");
                    ir::WaitCause::Edge {
                        net: self.sens_event_net(&ev.expr, true),
                        kind: map_edge(ev.edge),
                    }
                } else {
                    let nets = list
                        .iter()
                        .map(|ev| self.sens_event_net(&ev.expr, false))
                        .collect();
                    ir::WaitCause::Level { nets }
                }
            }
        }
    }

    /// `#delay` → `(amount, region)`. Since format_version 4 `amount` is the
    /// **ExprId of the raw delay value in module time units** — the engine
    /// evaluates it at suspension time and scales by the per-process
    /// multiplier (round(v × M); X/Z → 0, iverilog parity). A const `#5`
    /// simply folds to a Const expr, so const and runtime delays share one
    /// path. SD3: a delay that PROVABLY rounds to 0 ticks (`#0`, or a real
    /// under half a precision tick) marks `Inactive`; everything else —
    /// including runtime values that happen to be 0 — is `Active` and the
    /// engine's `ticks == 0` check supplies the inactive nudge at runtime.
    fn lower_delay(&mut self, d: &ast::Delay) -> (u32, ir::DelayRegion) {
        let mult = self.cur_time_mult;
        let Some(e) = d.values.first() else {
            // defensive: parser always supplies a value; treat as `#0`.
            let zero = self.lower_expr(&ast::Expr {
                kind: ast::ExprKind::IntLit {
                    kind: ast::IntLitKind::Decimal,
                    raw: "0".to_string(),
                },
                span: ast::Span { lo: 0, hi: 0 },
            });
            return (zero, ir::DelayRegion::Inactive);
        };
        // min:typ:max picks typ — same branch const_delay_ticks used.
        let pick = match &e.kind {
            ast::ExprKind::MinTypMax { typ, .. } => typ.as_ref(),
            _ => e,
        };
        let amount = self.lower_expr(pick);
        let region = if const_delay_ticks(pick, mult) == Some(0) {
            ir::DelayRegion::Inactive
        } else {
            ir::DelayRegion::Active
        };
        (amount, region)
    }

    // ── $systask lowering (SysTaskId map + fmt/args split) ─────────
    /// `$display(...)` etc. → `ir::Stmt::SysTask` appended to `self.stmts`;
    /// returns its StmtId. Unknown `$task` → `ElabUnsupported`, `None` (skip).
    /// fmt/args split: for the print family the FIRST arg, IF it is a string
    /// literal, becomes `fmt`; the rest are value args. Non-print tasks
    /// ($finish/$dumpfile/...) carry `fmt: None`, every arg in `args`.
    fn lower_systask(&mut self, name: &ast::Ident, args: &[ast::Expr]) -> Option<u32> {
        // P1-1: `$fatal`/`$error`/`$warning`/`$info` lower as `Display` stmts plus
        // an out-of-band SeverityTable entry (the frozen SysTaskId has no severity
        // variants; the engine intercepts by StmtId and routes to the diag stream).
        if let Some(sev) = map_severity(&name.name) {
            return Some(self.lower_severity_task(sev, args));
        }
        let which = match map_systask(&name.name) {
            Some(w) => w,
            None => {
                // M-D: unknown $task ($timeformat/$monitoron/$readmemh/...) is a
                // WARN + skip (no Stmt emitted), NOT an IR-killing error. The
                // testbench survives.
                self.warn(&format!(
                    "unsupported system task `{}` skipped (v2)",
                    name.name
                ));
                return None;
            }
        };
        let takes_fmt = matches!(
            which,
            ir::SysTaskId::Display
                | ir::SysTaskId::Write
                | ir::SysTaskId::Monitor
                | ir::SysTaskId::Strobe
        );
        // M-D: $dumpvars(level, scope...) passes a scope/module name, not a net.
        // Lowering a scope ident through lower_expr would resolve_net → fatal
        // unresolved-name. For the dump family, drop any non-net/non-const arg
        // with a warning instead of resolving it.
        let dump_family = matches!(
            which,
            ir::SysTaskId::DumpVars
                | ir::SysTaskId::DumpFile
                | ir::SysTaskId::DumpOn
                | ir::SysTaskId::DumpOff
                | ir::SysTaskId::DumpAll
        );
        let mut fmt_raw: Option<String> = None;
        // v7 file print family: args[0] is the DESCRIPTOR; the format (when a
        // string literal) is args[1]. Stmt args stay [fd, value-args…].
        let file_fmt = matches!(
            which,
            ir::SysTaskId::Fdisplay | ir::SysTaskId::Fwrite | ir::SysTaskId::Sformat
        );
        let mut file_args_buf: Vec<ast::Expr> = Vec::new();
        let (fmt, value_args): (Option<u32>, &[ast::Expr]) = if file_fmt {
            match args.get(1).map(|e| &e.kind) {
                Some(ast::ExprKind::StrLit { raw }) => {
                    fmt_raw = Some(parse_str_literal_text(raw));
                    let cid = self.intern_const(parse_str_literal(raw));
                    let fmt_expr = self.push_expr(ir::Expr::Const { val: cid });
                    file_args_buf.push(args[0].clone());
                    file_args_buf.extend(args.iter().skip(2).cloned());
                    (Some(fmt_expr), file_args_buf.as_slice())
                }
                _ => (None, args),
            }
        } else if takes_fmt {
            match args.first().map(|e| &e.kind) {
                Some(ast::ExprKind::StrLit { raw }) => {
                    fmt_raw = Some(parse_str_literal_text(raw));
                    let cid = self.intern_const(parse_str_literal(raw));
                    let fmt_expr = self.push_expr(ir::Expr::Const { val: cid });
                    (Some(fmt_expr), &args[1..])
                }
                _ => (None, args),
            }
        } else {
            (None, args)
        };
        let arg_ids: Vec<u32> = value_args
            .iter()
            .filter_map(|a| {
                // `$dumpvars(level, scope)` — the level const and a scope/module
                // ident. v1 dumps ALL signals (a valid superset of any requested
                // depth/scope), so a scope ident is silently dropped here rather
                // than warned: scope/depth-SELECTIVE dumping is a refinement, but
                // the common `$dumpvars(0, top)` idiom must not spew a warning.
                if dump_family && !self.is_net_or_const_arg(a) {
                    // ⑤b: a scope/module arg encodes as a SYNTHETIC string
                    // const carrying two candidates `fq\x01raw` — the runtime
                    // filter tries the elaborate-scope-resolved FQ first, then
                    // the raw text as a root-absolute path. Non-ident args
                    // keep the historical silent drop.
                    if let ast::ExprKind::Ident(p) = &a.kind {
                        let joined = p
                            .segments
                            .iter()
                            .map(|s| s.name.as_str())
                            .collect::<Vec<_>>()
                            .join(".");
                        let fq = self.fq(&joined);
                        let enc = format!("{fq}\u{0001}{joined}");
                        let cid =
                            self.intern_const(crate::literal::str_const_from_bytes(enc.as_bytes()));
                        Some(self.push_expr(ir::Expr::Const { val: cid }))
                    } else {
                        None
                    }
                } else {
                    // Item-⑤ status quo: a whole-array `$dumpvars(1, mem)` arg
                    // keeps its historical word-0 surface (doc-01 known v1
                    // simplification: v1 dumps ALL signals anyway) — the
                    // Phase-1.x ② whole-array loud check must not fire here.
                    // v7: $readmem's MEMORY argument is the same whole-array
                    // Signal shape (the engine writes elements via the funnel).
                    let readmem_family =
                        matches!(which, ir::SysTaskId::ReadmemB | ir::SysTaskId::ReadmemH);
                    if dump_family || readmem_family {
                        if let Some((net, lead)) = self.expr_array_view(a) {
                            if lead.is_empty() {
                                return Some(self.push_expr(ir::Expr::Signal { net, word: None }));
                            }
                        }
                    }
                    Some(self.lower_expr(a))
                }
            })
            .collect();
        // §4.1a STATIC gate: a `%b/%h/%o/%x` conversion specifier paired with a
        // real-typed argument is illegal (real has no radix form; use $realtobits).
        if let Some(fmt_str) = &fmt_raw {
            self.check_format_real_radix(fmt_str, &arg_ids);
        }
        let sid = self.push_stmt(ir::Stmt::SysTask {
            which,
            fmt,
            args: arg_ids,
        });
        // P1-5: the b/o/h print variants change the DEFAULT radix of unformatted
        // args — record it out-of-band (frozen SysTaskId has no radix variants).
        if let Some(r) = radix_of_systask(&name.name) {
            self.radixes.insert(sid, r);
        }
        Some(sid)
    }

    /// P1-1: lower `$fatal([finish_number][, fmt, args…])` / `$error`/`$warning`/
    /// `$info([fmt, args…])` to a `SysTaskId::Display` stmt + a [`SeverityTable`]
    /// entry keyed by its StmtId. `$fatal`'s leading INTEGER LITERAL is the IEEE
    /// finish_number — consumed and ignored (like `$finish(n)`), never printed.
    /// The fmt/args split mirrors the print family (first string literal = fmt).
    fn lower_severity_task(&mut self, sev: SeverityKind, args: &[ast::Expr]) -> u32 {
        let args: &[ast::Expr] = if sev == SeverityKind::Fatal
            && matches!(
                args.first().map(|e| &e.kind),
                Some(ast::ExprKind::IntLit { .. })
            ) {
            &args[1..]
        } else {
            args
        };
        let mut fmt_raw: Option<String> = None;
        let (fmt, value_args): (Option<u32>, &[ast::Expr]) = match args.first().map(|e| &e.kind) {
            Some(ast::ExprKind::StrLit { raw }) => {
                fmt_raw = Some(parse_str_literal_text(raw));
                let cid = self.intern_const(parse_str_literal(raw));
                let fmt_expr = self.push_expr(ir::Expr::Const { val: cid });
                (Some(fmt_expr), &args[1..])
            }
            _ => (None, args),
        };
        let arg_ids: Vec<u32> = value_args.iter().map(|a| self.lower_expr(a)).collect();
        if let Some(fmt_str) = &fmt_raw {
            self.check_format_real_radix(fmt_str, &arg_ids);
        }
        let sid = self.push_stmt(ir::Stmt::SysTask {
            which: ir::SysTaskId::Display,
            fmt,
            args: arg_ids,
        });
        self.severities.insert(sid, sev);
        sid
    }

    /// True if `a` is a bare net Ident or an integer/string literal — i.e. a thing
    /// `lower_expr` can lower without a fatal unresolved-name. A hierarchical /
    /// scope name (`top.dut`) or anything else returns false (dump-family skips it).
    fn is_net_or_const_arg(&self, a: &ast::Expr) -> bool {
        match &a.kind {
            ast::ExprKind::Ident(path) => {
                path.segments.len() == 1
                    && self.symbols.contains_key(&self.fq(&path.segments[0].name))
            }
            ast::ExprKind::IntLit { .. } | ast::ExprKind::StrLit { .. } => true,
            _ => false,
        }
    }
}

/// Does any `disable <label>` (single-segment) appear in this statement tree?
/// Drives LAZY exit-BB allocation for named blocks: a label nobody disables
/// lowers exactly like an unlabeled block (byte-identical CFG to the
/// pre-disable lowering — golden corpus unaffected). Fork children are
/// included (a child's cross-boundary disable is rejected loudly later;
/// scanning them keeps this a pure syntactic property). Task bodies are NOT
/// resolved here — `disable` of a caller's label from inside a task stays a
/// loud unsupported error (the label is then absent from the disable stack).
fn stmt_disables_label(s: &ast::Stmt, label: &str) -> bool {
    use ast::Stmt as S;
    match s {
        S::Disable { target, .. } => target.segments.len() == 1 && target.segments[0].name == label,
        S::Block { stmts, .. } | S::Fork { stmts, .. } => {
            stmts.iter().any(|st| stmt_disables_label(st, label))
        }
        S::If { then_s, else_s, .. } => {
            stmt_disables_label(then_s, label)
                || else_s
                    .as_deref()
                    .is_some_and(|e| stmt_disables_label(e, label))
        }
        S::Case { items, .. } => items.iter().any(|it| match it {
            ast::CaseItem::Match { body, .. } | ast::CaseItem::Default { body, .. } => {
                stmt_disables_label(body, label)
            }
        }),
        S::For {
            init, step, body, ..
        } => {
            stmt_disables_label(init, label)
                || stmt_disables_label(step, label)
                || stmt_disables_label(body, label)
        }
        S::While { body, .. } | S::Repeat { body, .. } | S::Forever { body, .. } => {
            stmt_disables_label(body, label)
        }
        S::DelayCtrl { body, .. } | S::EventCtrl { body, .. } | S::Wait { body, .. } => body
            .as_deref()
            .is_some_and(|b| stmt_disables_label(b, label)),
        _ => false,
    }
}

/// A fresh time-0 `SuspendState`. `resume_pc = entry`; everything else default.
/// `wake_key` is a never-armed placeholder the engine overwrites on first
/// suspend — `WakeCond` (the suspend-state type) is DISTINCT from `WaitCause`
/// (the terminator type); a `Level{nets:[]}` (vacuously false) is the minimal
/// valid seed since `WakeCond` has no none-variant.
fn fresh_suspend(entry: u32) -> ir::SuspendState {
    ir::SuspendState {
        resume_pc: entry,
        locals: Vec::new(),
        join_state: ir::JoinState {
            parent: None,
            children: Vec::new(),
            detached: Vec::new(),
            flags: ir::ProcFlags(0),
        },
        wake_key: ir::WakeKey {
            cond: ir::WakeCond::Level { nets: Vec::new() },
            region: ir::RegionTag::Active,
            tie_break: 0,
        },
        call_stack: Vec::new(),
        frame_arena: Vec::new(),
    }
}

/// hdl-ast `Edge` → sim-ir `EdgeKind`. A bare signal (`NoEdge`) in an
/// edge-classified or level list arms on `AnyEdge`.
fn map_edge(e: ast::Edge) -> ir::EdgeKind {
    match e {
        ast::Edge::Posedge => ir::EdgeKind::Posedge,
        ast::Edge::Negedge => ir::EdgeKind::Negedge,
        ast::Edge::NoEdge => ir::EdgeKind::AnyEdge,
    }
}

/// `$display`→Display … `$dumpall`→DumpAll. `name` retains the leading `$`
/// (parser keeps it, parallel to `map_sysfunc`). Unknown → None.
/// `$monitoron`/`$monitoroff`/`$timeformat` etc. are DEFERRED.
/// Severity-task name → [`SeverityKind`] (P1-1). These do NOT map to a frozen
/// `SysTaskId`; they lower as `Display` + an out-of-band severity entry.
fn map_severity(dollar_name: &str) -> Option<SeverityKind> {
    match dollar_name {
        "$fatal" => Some(SeverityKind::Fatal),
        "$error" => Some(SeverityKind::Error),
        "$warning" => Some(SeverityKind::Warning),
        "$info" => Some(SeverityKind::Info),
        _ => None,
    }
}

/// b/o/h print-task variant → its default radix (P1-5). Exact-match (so
/// `$monitoron`/`$monitoroff` never alias `$monitoro` + a stray suffix).
fn radix_of_systask(dollar_name: &str) -> Option<u8> {
    match dollar_name {
        "$displayb" | "$writeb" | "$strobeb" | "$monitorb" | "$fdisplayb" | "$fwriteb" => Some(2),
        "$displayo" | "$writeo" | "$strobeo" | "$monitoro" | "$fdisplayo" | "$fwriteo" => Some(8),
        "$displayh" | "$writeh" | "$strobeh" | "$monitorh" | "$fdisplayh" | "$fwriteh" => Some(16),
        _ => None,
    }
}

fn map_systask(dollar_name: &str) -> Option<ir::SysTaskId> {
    match dollar_name {
        "$display" | "$displayb" | "$displayo" | "$displayh" => Some(ir::SysTaskId::Display),
        "$write" | "$writeb" | "$writeo" | "$writeh" => Some(ir::SysTaskId::Write),
        "$monitor" | "$monitorb" | "$monitoro" | "$monitorh" => Some(ir::SysTaskId::Monitor),
        "$strobe" | "$strobeb" | "$strobeo" | "$strobeh" => Some(ir::SysTaskId::Strobe),
        "$finish" => Some(ir::SysTaskId::Finish),
        "$stop" => Some(ir::SysTaskId::Stop),
        "$dumpfile" => Some(ir::SysTaskId::DumpFile),
        "$dumpvars" => Some(ir::SysTaskId::DumpVars),
        "$dumpon" => Some(ir::SysTaskId::DumpOn),
        "$dumpoff" => Some(ir::SysTaskId::DumpOff),
        "$dumpall" => Some(ir::SysTaskId::DumpAll),
        "$dumpflush" => Some(ir::SysTaskId::DumpFlush),
        "$dumplimit" => Some(ir::SysTaskId::DumpLimit),
        // v7 file I/O ($fopen is a special form — it returns the fd).
        "$readmemb" => Some(ir::SysTaskId::ReadmemB),
        "$readmemh" => Some(ir::SysTaskId::ReadmemH),
        "$fclose" => Some(ir::SysTaskId::Fclose),
        "$sformat" => Some(ir::SysTaskId::Sformat),
        "$fdisplay" | "$fdisplayb" | "$fdisplayo" | "$fdisplayh" => Some(ir::SysTaskId::Fdisplay),
        "$fwrite" | "$fwriteb" | "$fwriteo" | "$fwriteh" => Some(ir::SysTaskId::Fwrite),
        _ => None,
    }
}

// ── free helpers (pure, no &self) ──────────────────────────────────

/// Does this statement (recursively) contain its own timing control — `#delay`,
/// `@(event)`, or `wait` — anywhere on a path? Used to decide whether a bare
/// `always` (no header @) is a legal self-timed process (clock generator) vs an
/// unschedulable one. Conservative: any nested timing anywhere counts. (M-C)
fn stmt_has_timing(s: &ast::Stmt) -> bool {
    match s {
        ast::Stmt::DelayCtrl { .. }
        | ast::Stmt::EventCtrl { .. }
        | ast::Stmt::Wait { .. }
        | ast::Stmt::WaitFork { .. } => true,
        ast::Stmt::Block { stmts, .. } => stmts.iter().any(stmt_has_timing),
        ast::Stmt::If { then_s, else_s, .. } => {
            stmt_has_timing(then_s) || else_s.as_deref().is_some_and(stmt_has_timing)
        }
        ast::Stmt::Case { items, .. } => items.iter().any(|it| match it {
            ast::CaseItem::Match { body, .. } | ast::CaseItem::Default { body, .. } => {
                stmt_has_timing(body)
            }
        }),
        ast::Stmt::For { body, .. }
        | ast::Stmt::While { body, .. }
        | ast::Stmt::Repeat { body, .. }
        | ast::Stmt::Forever { body, .. } => stmt_has_timing(body),
        ast::Stmt::Fork { stmts, .. } => stmts.iter().any(stmt_has_timing),
        _ => false,
    }
}

/// Clamp a folded i64 range bound to the u32 width math: negative (underflow
/// artifact) → 0, beyond u32 → u32::MAX (the over-cap width check then fires
/// loudly). None (non-constant) → 0 (caller's legacy default).
fn clamp_bound_u32(v: Option<i64>) -> u32 {
    v.map_or(0, |v| {
        u32::try_from(v).unwrap_or(if v < 0 { 0 } else { u32::MAX })
    })
}

/// Sign-aware i64 fold of an integer literal: an EXPLICITLY signed based
/// literal with its sign bit set (`8'shFF`) folds negative. A plain decimal
/// (`4294967295`) is the positive value as written — IEEE marks unsized
/// decimals signed, but the written magnitude is the value (iverilog folds it
/// positive), so sign-extending on the bit image would turn it into -1. The
/// image must fit i64 (else None → loud at the param sites). X/Z bits → None.
fn const_eval_i64_lit(e: &ast::Expr) -> Option<i64> {
    let ast::ExprKind::IntLit { kind, raw } = &e.kind else {
        return None;
    };
    let cv = parse_int_literal(raw, *kind)?;
    if cv.bits.unk.iter().any(|&w| w != 0) {
        return None;
    }
    if cv.bits.val.iter().skip(1).any(|&w| w != 0) {
        return None; // >64-bit literal value — outside the i64 const domain
    }
    let v = cv.bits.val.first().copied().unwrap_or(0);
    let explicit_signed = cv.signed && !matches!(kind, ast::IntLitKind::Decimal);
    if explicit_signed && cv.width >= 1 && cv.width < 64 && (v >> (cv.width - 1)) & 1 == 1 {
        return Some((v | (!0u64 << cv.width)) as i64);
    }
    if explicit_signed && cv.width == 64 {
        return Some(v as i64);
    }
    i64::try_from(v).ok()
}

/// `**` in the i64 const domain. Negative exponents follow the IEEE integer
/// table (1**n=1, (-1)**n=±1, 0**neg undefined → None, else 0); overflow → None.
fn const_pow_i64(a: i64, b: i64) -> Option<i64> {
    if b < 0 {
        return match a {
            1 => Some(1),
            -1 => Some(if b % 2 == 0 { 1 } else { -1 }),
            0 => None,
            _ => Some(0),
        };
    }
    a.checked_pow(u32::try_from(b).ok()?)
}

/// `<<`/`<<<` in the i64 const domain: value-preserving or None. A shift that
/// loses bits (or lands in the sign bit) would be a silently wrong param value
/// — the round-trip check rejects it loudly. `0 << anything` stays 0.
fn const_shl_i64(a: i64, b: i64) -> Option<i64> {
    if a == 0 {
        return Some(0);
    }
    if !(0..64).contains(&b) {
        return None; // every bit of a non-zero value shifted out / negative amount
    }
    let r = a.checked_shl(b as u32)?;
    if (r >> b) == a {
        Some(r)
    } else {
        None
    }
}

/// Tiny const-evaluator (v1: literals + paren + unary +/-). Evaluate a constant
/// integer expression to `u32`. Anything else (Ident/param, arithmetic) → None
/// (caller substitutes a default + may diagnose). SLOT: param-dependent ranges
/// get a `&params` table here when parameter elaboration lands.
fn const_eval_u32(e: &ast::Expr) -> Option<u32> {
    match &e.kind {
        ast::ExprKind::IntLit { kind, raw } => {
            let cv = parse_int_literal(raw, *kind)?;
            // Reject x/z: a literal with any unknown bit (e.g. `4'dx`) is not a
            // valid constant index/bound/delay — return None so the caller
            // applies its default rather than silently treating x/z as 0.
            // (LOWERING verdict NIT.)
            if cv.bits.unk.iter().any(|&w| w != 0) {
                return None;
            }
            // take the low 32 bits of the value plane (2-state by the check above).
            Some(cv.bits.val.first().copied().unwrap_or(0) as u32)
        }
        ast::ExprKind::Paren { inner } => const_eval_u32(inner),
        ast::ExprKind::Unary { op, operand } => {
            let v = const_eval_u32(operand)?;
            match op {
                ast::UnOp::Plus => Some(v),
                ast::UnOp::Minus => Some(v.wrapping_neg()),
                _ => None,
            }
        }
        _ => None,
    }
}

/// Const-fold a `#delay` value to integer ticks on the GLOBAL precision timeline.
/// `mult` is the module's delay multiplier `M = 10^(unit_exp − global_prec_exp)`:
/// a delay of `d` module-units becomes `round(d × M)` precision ticks (IEEE 1364 §9
/// round-half-away). The multiply happens INSIDE the rounding so a fractional
/// `#2.5` with `M=1000` is the exact `2500`, not `round(2.5)×1000`. With `M=1` (the
/// 1ns/1ns base) this is byte-identical to the prior `round(d)` behavior.
fn const_delay_ticks(e: &ast::Expr, mult: u64) -> Option<u32> {
    let pick = match &e.kind {
        ast::ExprKind::MinTypMax { typ, .. } => typ.as_ref(),
        _ => e,
    };
    let real = match &pick.kind {
        ast::ExprKind::RealLit { raw, .. } => Some(raw),
        ast::ExprKind::Paren { inner } => match &inner.kind {
            ast::ExprKind::RealLit { raw, .. } => Some(raw),
            _ => None,
        },
        _ => None,
    };
    if let Some(raw) = real {
        let x = parse_real_f64(raw) * mult as f64;
        return Some((x.round() as i64).clamp(0, u32::MAX as i64) as u32);
    }
    // integer delay: exact `d × M` (saturating into u32).
    const_eval_u32(pick).map(|d| (d as u64).saturating_mul(mult).min(u32::MAX as u64) as u32)
}

/// Const-fold a net/var initializer literal into a `BitPacked` of `width`.
/// Non-literal initializers → None (procedural; deferred), caller defaults.
fn fold_init(e: &ast::Expr, width: u32) -> Option<ir::BitPacked> {
    match &e.kind {
        ast::ExprKind::IntLit { kind, raw } => {
            let cv = parse_int_literal(raw, *kind)?;
            Some(resize_bits(&cv.bits, cv.width, width, cv.signed))
        }
        ast::ExprKind::Paren { inner } => fold_init(inner, width),
        _ => None,
    }
}

fn map_unop(op: ast::UnOp) -> ir::UnOp {
    use ast::UnOp::*;
    match op {
        Plus => ir::UnOp::Plus,
        Minus => ir::UnOp::Minus,
        LogNot => ir::UnOp::LogNot,
        BitNot => ir::UnOp::BitNot,
        RedAnd => ir::UnOp::RedAnd,
        RedNand => ir::UnOp::RedNand,
        RedOr => ir::UnOp::RedOr,
        RedNor => ir::UnOp::RedNor,
        RedXor => ir::UnOp::RedXor,
        RedXnor => ir::UnOp::RedXnor,
    }
}

fn map_binop(op: ast::BinOp) -> ir::BinOp {
    use ast::BinOp::*;
    match op {
        Add => ir::BinOp::Add,
        Sub => ir::BinOp::Sub,
        Mul => ir::BinOp::Mul,
        Div => ir::BinOp::Div,
        Mod => ir::BinOp::Mod,
        Pow => ir::BinOp::Pow,
        Shl => ir::BinOp::Shl,
        Shr => ir::BinOp::Shr,
        AShl => ir::BinOp::AShl,
        AShr => ir::BinOp::AShr,
        Lt => ir::BinOp::Lt,
        Le => ir::BinOp::Le,
        Gt => ir::BinOp::Gt,
        Ge => ir::BinOp::Ge,
        Eq => ir::BinOp::Eq,
        Ne => ir::BinOp::Ne,
        CaseEq => ir::BinOp::CaseEq,
        CaseNe => ir::BinOp::CaseNe,
        BitAnd => ir::BinOp::BitAnd,
        BitXor => ir::BinOp::BitXor,
        BitXnor => ir::BinOp::BitXnor,
        BitOr => ir::BinOp::BitOr,
        LogAnd => ir::BinOp::LogAnd,
        LogOr => ir::BinOp::LogOr,
    }
}

/// `$time`→Time, `$realtime`→Realtime, `$signed`→Signed, `$unsigned`→Unsigned,
/// `$clog2`→Clog2. `name` retains the leading `$` (verdict M6).
fn map_sysfunc(dollar_name: &str) -> Option<ir::SysFuncId> {
    match dollar_name {
        "$time" => Some(ir::SysFuncId::Time),
        "$realtime" => Some(ir::SysFuncId::Realtime),
        "$signed" => Some(ir::SysFuncId::Signed),
        "$unsigned" => Some(ir::SysFuncId::Unsigned),
        "$clog2" => Some(ir::SysFuncId::Clog2),
        "$rtoi" => Some(ir::SysFuncId::Rtoi),
        "$itor" => Some(ir::SysFuncId::Itor),
        "$realtobits" => Some(ir::SysFuncId::RealToBits),
        "$bitstoreal" => Some(ir::SysFuncId::BitsToReal),
        // v7 bit-vector predicates ($bits never reaches here — const-folded).
        "$countones" => Some(ir::SysFuncId::CountOnes),
        "$onehot" => Some(ir::SysFuncId::OneHot),
        "$onehot0" => Some(ir::SysFuncId::OneHot0),
        "$isunknown" => Some(ir::SysFuncId::IsUnknown),
        // v7 random + time + plusarg probe ($value$plusargs is a special
        // form — it writes its ref var, never mapped here).
        "$test$plusargs" => Some(ir::SysFuncId::TestPlusargs),
        "$random" => Some(ir::SysFuncId::Random),
        "$urandom" => Some(ir::SysFuncId::Urandom),
        "$urandom_range" => Some(ir::SysFuncId::UrandomRange),
        "$stime" => Some(ir::SysFuncId::Stime),
        _ => None,
    }
}

/// Walk a `name[i][j]…` chain to its single-segment root ident, counting the
/// indices ($bits prescan key — the indices are NOT evaluated, IEEE §20.6.2).
fn ident_index_chain(e: &ast::Expr) -> Option<(&str, usize)> {
    let mut depth = 0usize;
    let mut cur = e;
    loop {
        match &cur.kind {
            ast::ExprKind::BitSelect { base, .. } => {
                depth += 1;
                cur = base;
            }
            ast::ExprKind::Paren { inner } => cur = inner,
            ast::ExprKind::Ident(p) => {
                return match p.segments.as_slice() {
                    [seg] => Some((seg.name.as_str(), depth)),
                    _ => None,
                };
            }
            _ => return None,
        }
    }
}

fn map_port_dir(d: ast::PortDir) -> ir::PortDir {
    match d {
        ast::PortDir::Input => ir::PortDir::Input,
        ast::PortDir::Output => ir::PortDir::Output,
        ast::PortDir::Inout => ir::PortDir::Inout,
    }
}

// ── v3 port-wiring helpers ─────────────────────────────────────────
/// A whole-net lvalue chunk (no word/offset/width → drives the entire net).
fn whole_net_chunk(net: u32) -> ir::LvalChunk {
    ir::LvalChunk {
        net,
        word: None,
        offset: None,
        width: None,
        kind: ir::SelKind::Bit,
    }
}
/// A single-chunk whole-net lvalue.
fn whole_net_lvalue(net: u32) -> ir::Lvalue {
    ir::Lvalue {
        chunks: vec![whole_net_chunk(net)],
    }
}

/// Reinterpret a parent connection `Expr` as an `ast::Lvalue` for an OUTPUT port
/// (the connection target must be a net / select / concat). Returns None for a
/// non-lvalue expression (a literal or an arithmetic result) — the caller emits
/// `ElabPortMismatch`. Mirrors the `Expr`/`Lvalue` variant shapes 1:1.
fn expr_to_lvalue(e: &ast::Expr) -> Option<ast::Lvalue> {
    match &e.kind {
        ast::ExprKind::Ident(path) => Some(ast::Lvalue::Ident(path.clone())),
        ast::ExprKind::Paren { inner } => expr_to_lvalue(inner),
        ast::ExprKind::BitSelect { base, index } => Some(ast::Lvalue::BitSelect {
            base: Box::new(expr_to_lvalue(base)?),
            index: index.clone(),
            span: e.span,
        }),
        ast::ExprKind::PartSelect { base, msb, lsb } => Some(ast::Lvalue::PartSelect {
            base: Box::new(expr_to_lvalue(base)?),
            msb: msb.clone(),
            lsb: lsb.clone(),
            span: e.span,
        }),
        ast::ExprKind::IndexedPart {
            base,
            offset,
            width,
            dir,
        } => Some(ast::Lvalue::IndexedPart {
            base: Box::new(expr_to_lvalue(base)?),
            offset: offset.clone(),
            width: width.clone(),
            dir: *dir,
            span: e.span,
        }),
        ast::ExprKind::Concat { parts } => {
            let lv_parts: Option<Vec<ast::Lvalue>> = parts.iter().map(expr_to_lvalue).collect();
            Some(ast::Lvalue::Concat {
                parts: lv_parts?,
                span: e.span,
            })
        }
        _ => None,
    }
}

/// B1 frame-call: does this function body need a frame (is it NOT straight-line
/// foldable by the inline path)? True for any control flow (if/case/loop/fork),
/// non-blocking assign, $systask, or timing — exactly the constructs
/// `fold_straight_line` rejects. A straight-line body (`Null`/`Block`/`Blocking`)
/// stays on the byte-identical inline path unless it is automatic/recursive.
fn body_needs_frame(s: &ast::Stmt) -> bool {
    use ast::Stmt::*;
    match s {
        Null(_) | Blocking { .. } => false,
        Block { stmts, .. } => stmts.iter().any(body_needs_frame),
        _ => true,
    }
}

/// B1 frame-call: collect single-segment user-function/task call names reachable
/// from a statement (for recursion detection). Incomplete coverage is loud-safe
/// (a missed edge leaves the function on the inline path → `inline_stack` rejects).
fn collect_callee_stmt(s: &ast::Stmt, out: &mut std::collections::BTreeSet<String>) {
    use ast::Stmt::*;
    match s {
        Blocking { rhs, .. } => collect_callee_expr(rhs, out),
        NonBlocking { rhs, .. } => collect_callee_expr(rhs, out),
        If {
            cond,
            then_s,
            else_s,
            ..
        } => {
            collect_callee_expr(cond, out);
            collect_callee_stmt(then_s, out);
            if let Some(e) = else_s {
                collect_callee_stmt(e, out);
            }
        }
        Case {
            scrutinee, items, ..
        } => {
            collect_callee_expr(scrutinee, out);
            for it in items {
                match it {
                    ast::CaseItem::Match { labels, body, .. } => {
                        for g in labels {
                            collect_callee_expr(g, out);
                        }
                        collect_callee_stmt(body, out);
                    }
                    ast::CaseItem::Default { body, .. } => collect_callee_stmt(body, out),
                }
            }
        }
        For {
            init,
            cond,
            step,
            body,
            ..
        } => {
            collect_callee_stmt(init, out);
            collect_callee_expr(cond, out);
            collect_callee_stmt(step, out);
            collect_callee_stmt(body, out);
        }
        While { cond, body, .. } => {
            collect_callee_expr(cond, out);
            collect_callee_stmt(body, out);
        }
        Repeat { count, body, .. } => {
            collect_callee_expr(count, out);
            collect_callee_stmt(body, out);
        }
        Forever { body, .. } => collect_callee_stmt(body, out),
        Block { stmts, .. } | Fork { stmts, .. } => {
            for st in stmts {
                collect_callee_stmt(st, out);
            }
        }
        SysTaskCall { args, .. } => {
            for a in args {
                collect_callee_expr(a, out);
            }
        }
        UserTaskCall { name, args, .. } => {
            if name.segments.len() == 1 {
                out.insert(name.segments[0].name.clone());
            }
            for a in args {
                collect_callee_expr(a, out);
            }
        }
        _ => {}
    }
}

/// B1 frame-call: collect call names reachable from an expression (companion to
/// [`collect_callee_stmt`]).
fn collect_callee_expr(e: &ast::Expr, out: &mut std::collections::BTreeSet<String>) {
    use ast::ExprKind::*;
    match &e.kind {
        Call { name, args } => {
            if name.segments.len() == 1 {
                out.insert(name.segments[0].name.clone());
            }
            for a in args {
                collect_callee_expr(a, out);
            }
        }
        Unary { operand, .. } => collect_callee_expr(operand, out),
        Binary { lhs, rhs, .. } => {
            collect_callee_expr(lhs, out);
            collect_callee_expr(rhs, out);
        }
        Ternary {
            cond,
            then_e,
            else_e,
        } => {
            collect_callee_expr(cond, out);
            collect_callee_expr(then_e, out);
            collect_callee_expr(else_e, out);
        }
        BitSelect { base, index } => {
            collect_callee_expr(base, out);
            collect_callee_expr(index, out);
        }
        PartSelect { base, msb, lsb } => {
            collect_callee_expr(base, out);
            collect_callee_expr(msb, out);
            collect_callee_expr(lsb, out);
        }
        IndexedPart {
            base,
            offset,
            width,
            ..
        } => {
            collect_callee_expr(base, out);
            collect_callee_expr(offset, out);
            collect_callee_expr(width, out);
        }
        Concat { parts } => {
            for p in parts {
                collect_callee_expr(p, out);
            }
        }
        Replicate { count, value } => {
            collect_callee_expr(count, out);
            for v in value {
                collect_callee_expr(v, out);
            }
        }
        SysCall { args, .. } => {
            for a in args {
                collect_callee_expr(a, out);
            }
        }
        Paren { inner } => collect_callee_expr(inner, out),
        MinTypMax { min, typ, max } => {
            collect_callee_expr(min, out);
            collect_callee_expr(typ, out);
            collect_callee_expr(max, out);
        }
        New { size, src } => {
            collect_callee_expr(size, out);
            if let Some(s) = src {
                collect_callee_expr(s, out);
            }
        }
        _ => {}
    }
}

/// B1 frame-call: can `start` reach `target` over the call-graph `edges`
/// (`start == target` ⇒ "is `start` recursive?", direct OR mutual)? Iterative
/// DFS from `start`'s callees.
fn reaches(
    start: &str,
    target: &str,
    edges: &BTreeMap<String, std::collections::BTreeSet<String>>,
) -> bool {
    let mut stack: Vec<&str> = edges
        .get(start)
        .into_iter()
        .flatten()
        .map(|s| s.as_str())
        .collect();
    let mut seen: std::collections::BTreeSet<&str> = std::collections::BTreeSet::new();
    while let Some(n) = stack.pop() {
        if n == target {
            return true;
        }
        if !seen.insert(n) {
            continue;
        }
        if let Some(cs) = edges.get(n) {
            stack.extend(cs.iter().map(|s| s.as_str()));
        }
    }
    false
}

/// B1 frame-call: rebase a process-local terminator's block target(s) by `+base`
/// when the lowered func CFG is appended to the GLOBAL `ir.blocks` arena. A valid
/// frame body only carries `Goto`/`Branch`/`Return`; the suspend/fork variants are
/// rebased defensively (the body validator rejects them) so no index dangles.
fn rebase_terminator(t: &mut ir::Terminator, base: u32) {
    match t {
        ir::Terminator::Goto { target } => *target += base,
        ir::Terminator::Branch {
            then_bb, else_bb, ..
        } => {
            *then_bb += base;
            *else_bb += base;
        }
        ir::Terminator::Delay { resume, .. } | ir::Terminator::Wait { resume, .. } => {
            *resume += base
        }
        ir::Terminator::Fork {
            join, resume_bb, ..
        } => {
            *join += base;
            *resume_bb += base;
        }
        ir::Terminator::Call { ret_bb, .. } => *ret_bb += base,
        ir::Terminator::Return => {}
    }
}

/// hdl-ast has 18 net/var kinds; sim-ir freezes only 4. Aliases collapse to the
/// closest 4-state kind; unsupported kinds still map to Wire so references
/// resolve (the call site emits `ElabUnsupported`).
fn map_net_kind_or_wire(k: ast::NetVarKind) -> ir::NetKind {
    use ast::NetVarKind::*;
    match k {
        Reg => ir::NetKind::Reg,
        Logic => ir::NetKind::Logic,
        Integer => ir::NetKind::Integer,
        // `real`/`realtime` → IEEE-754 f64 net (64-bit, signed, 2-state).
        Real | Realtime => ir::NetKind::Real,
        // `time` → 64-bit unsigned 4-state VARIABLE. The frozen NetKind has no
        // Time variant; Reg carries the same legality (procedural-assign ok,
        // user `assign` rejected) and 4-state all-X init. Width/signedness come
        // from range_to_dims (64, unsigned).
        Time => ir::NetKind::Reg,
        // named event → its 64-bit counter reg (v5 batch B desugar).
        Event => ir::NetKind::Reg,
        // Wire + all net aliases (Tri/Uwire/Wand/...) behave as Wire in v1.
        _ => ir::NetKind::Wire,
    }
}

/// v5 ⑥: VARIABLE kinds eligible as dynamic-storage ELEMENT types (the heap
/// stores 4-state `Value`s; real elements are deferred, nets are illegal).
/// The root `Ident` of an lvalue (through select bases). `None` for a concat
/// (its parts are checked individually) and parse-error recovery.
fn lval_root_path(lv: &ast::Lvalue) -> Option<&ast::HierPath> {
    match lv {
        ast::Lvalue::Ident(p) => Some(p),
        ast::Lvalue::BitSelect { base, .. }
        | ast::Lvalue::PartSelect { base, .. }
        | ast::Lvalue::IndexedPart { base, .. } => lval_root_path(base),
        _ => None,
    }
}

fn net_is_variable(k: ast::NetVarKind) -> bool {
    use ast::NetVarKind::*;
    matches!(k, Reg | Logic | Integer | Time)
}

/// True iff an lvalue is exactly ONE whole-net chunk (no bit/part-select, no
/// array word) — the only legal force/release target shape (IEEE §9.3.2).
fn is_whole_single_net(lv: &ir::Lvalue) -> bool {
    matches!(
        lv.chunks.as_slice(),
        [ir::LvalChunk {
            word: None,
            offset: None,
            ..
        }]
    )
}

/// Whether a kind is modeled in v1 without an `ElabUnsupported` note. Pure
/// aliases (Tri/Uwire) are accepted silently; resolution nets (wand/wor/...)
/// are flagged (still mapped to Wire so the arena stays valid).
fn net_kind_supported(k: ast::NetVarKind) -> bool {
    use ast::NetVarKind::*;
    matches!(
        k,
        Wire | Tri | Uwire | Reg | Logic | Integer | Real | Realtime | Time | Event | String
    )
}

/// Time-0 default `init`: variables (reg/logic/integer) start all-X; nets start
/// all-Z. `(v,u)`: X=`01`, Z=`11`.
fn default_init(kind: ast::NetVarKind, width: u32) -> ir::BitPacked {
    // A real default = +0.0 = all-zero bits, never X (it is always 2-state).
    if matches!(kind, ast::NetVarKind::Real | ast::NetVarKind::Realtime) {
        return ir::BitPacked {
            val: vec![0],
            unk: vec![0],
        };
    }
    // A named-event counter starts at ZERO, never X: `e = e + 1` on an all-X
    // start would stay X forever and no `@(e)` edge could ever fire.
    if matches!(kind, ast::NetVarKind::Event) {
        return ir::BitPacked {
            val: vec![0],
            unk: vec![0],
        };
    }
    let nwords = (((width as usize) + 63) / 64).max(1);
    let is_var = matches!(
        kind,
        ast::NetVarKind::Reg
            | ast::NetVarKind::Logic
            | ast::NetVarKind::Integer
            | ast::NetVarKind::Real
            | ast::NetVarKind::Realtime
            | ast::NetVarKind::Time
    );
    let mut val = vec![0u64; nwords];
    let mut unk = vec![0u64; nwords];
    for i in 0..(width as usize) {
        let w = i / 64;
        let off = i % 64;
        unk[w] |= 1u64 << off; // X and Z both have unk=1
        if !is_var {
            val[w] |= 1u64 << off; // Z has val=1; X has val=0
        }
    }
    ir::BitPacked { val, unk }
}

/// Resize a `BitPacked` from `from_w` to `to_w` bits. Truncates or zero-/sign-/
/// x-/z-extends per IEEE §3.5.1 (extend with the MSB *state*; sign-extend a `1`
/// only when `signed`). Used for net initializers.
fn resize_bits(src: &ir::BitPacked, from_w: u32, to_w: u32, signed: bool) -> ir::BitPacked {
    let nwords = (((to_w as usize) + 63) / 64).max(1);
    let mut val = vec![0u64; nwords];
    let mut unk = vec![0u64; nwords];
    let get = |plane: &[u64], i: usize| -> bool {
        plane
            .get(i / 64)
            .map(|w| (w >> (i % 64)) & 1 == 1)
            .unwrap_or(false)
    };
    // MSB state of the source (for extension).
    let msb_i = from_w.saturating_sub(1) as usize;
    let msb_v = get(&src.val, msb_i);
    let msb_u = get(&src.unk, msb_i);
    let (ext_v, ext_u) = match (msb_v, msb_u) {
        (false, true) => (false, true),   // X → x-extend
        (true, true) => (true, true),     // Z → z-extend
        (true, false) => (signed, false), // 1 → sign-extend only if signed
        _ => (false, false),              // 0 → zero-extend
    };
    for i in 0..(to_w as usize) {
        let (v, u) = if (i as u32) < from_w {
            (get(&src.val, i), get(&src.unk, i))
        } else {
            (ext_v, ext_u)
        };
        if v {
            val[i / 64] |= 1u64 << (i % 64);
        }
        if u {
            unk[i / 64] |= 1u64 << (i % 64);
        }
    }
    ir::BitPacked { val, unk }
}

// ────────────────────────────── Tests ──────────────────────────────
#[cfg(test)]
mod tests;
