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

use std::collections::BTreeMap;

use diag::{Diagnostic, LogEvent, LogSink, MsgCode, Severity};
use hdl_ast as ast;
use literal::{
    make_const_u32, parse_int_literal, parse_real_f64, parse_real_literal, parse_str_literal,
    parse_str_literal_text,
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
    let (ir, modes, names, _mult) =
        elaborate_with_timescale(unit, sink, &std::collections::BTreeMap::new(), -9);
    (ir, modes, names)
}

/// Full elaborate entry with the resolved timescale env from
/// `hdl_preprocess::resolve_module_timescales`. `mod_unit_exp` maps each module name
/// to its delay-unit exponent and `global_prec_exp` is the design-wide tick base;
/// `#delay` literals scale to `round(d × 10^(unit−prec))` ticks. Also returns the
/// per-process multiplier table for `SimOpts.proc_multipliers` (`$time`/`$realtime`
/// scaling). All three side tables ride out-of-band; the golden `SimIr` is unchanged.
pub fn elaborate_with_timescale(
    unit: &ast::SourceUnit,
    sink: &dyn LogSink,
    mod_unit_exp: &std::collections::BTreeMap<String, i8>,
    global_prec_exp: i8,
) -> (Option<ir::SimIr>, ForkModeTable, NetNameTable, Vec<u32>) {
    let mut el = Elaborator::new(sink);
    el.mod_unit_exp = mod_unit_exp.clone();
    el.global_prec_exp = global_prec_exp;
    el.run(unit);
    let modes = std::mem::take(&mut el.fork_modes);
    let mult = std::mem::take(&mut el.proc_multipliers);
    let names = el.net_name_table(); // BEFORE finish() consumes `el`
    if el.had_error {
        (None, modes, names, mult)
    } else {
        (Some(el.finish()), modes, names, mult)
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
    value: Option<u32>,
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

/// Pick the TOP module: one never instantiated by any other. Tie-break (≥2
/// candidates, e.g. two independent testbenches): the LAST-declared, matching the
/// common DUT-then-testbench file order. Degenerate (every module instantiated —
/// a cycle, or a pure library): fall back to the last-declared so `run` still
/// produces IR. Deterministic (declaration-order scan; `BTreeSet`).
fn pick_top<'a>(map: &ModuleMap<'a>, order: &[&'a ast::ModuleDecl]) -> Option<&'a ast::ModuleDecl> {
    let mut instantiated: std::collections::BTreeSet<&str> = std::collections::BTreeSet::new();
    for m in order {
        for item in &m.body {
            if let ast::ModuleItem::Instance(inst) = item {
                // count only names that resolve to a known module (an unknown name
                // is an instantiation error, surfaced later in the recursion).
                if map.contains_key(inst.module_name.name.as_str()) {
                    instantiated.insert(inst.module_name.name.as_str());
                }
            }
        }
    }
    order
        .iter()
        .copied()
        .filter(|m| !instantiated.contains(m.name.name.as_str()))
        .last()
        .or_else(|| order.last().copied())
}

/// A module's ports as `(local_name, dir)` in HEADER declaration order. ANSI
/// ports read dir inline; non-ANSI merges the body `PortDecl` directions over the
/// header name list (an undeclared header name defaults to Input + is rare).
/// Port wiring walks this in order, so a named connection list in any source
/// order produces a deterministic cont-assign sequence.
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

    // ── v3 hierarchy state ──
    // `cur_prefix` is the dotted instance path of the instance currently being
    // lowered ("tb", then "tb.dut", …). The symbol table is keyed by the FQ name
    // `cur_prefix + "." + local`, so `tb.q` and `tb.dut.q` never collide. Empty
    // only transiently (the top is always given its module name as the root path).
    cur_prefix: String,
    // FQ param-name → const value, visible while lowering an instance scope.
    // Re-points the v1 free `const_eval_u32` SLOT so `[W-1:0]` folds to a width.
    params: BTreeMap<String, u32>,
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

    // ── timescale state (engine-facing side channel, NOT in SimIr) ──
    // module NAME → its delay-unit exponent (base-10 of seconds), and the design-wide
    // finest precision exponent (the global tick base). Both supplied by the glue from
    // `hdl_preprocess::resolve_module_timescales`. Empty/`-9` ⇒ the `1ns/1ns` base
    // (multiplier 1 everywhere → byte-identical to the pre-timescale lowering).
    mod_unit_exp: std::collections::BTreeMap<String, i8>,
    global_prec_exp: i8,
    // Delay multiplier `M = 10^(unit_exp − global_prec_exp)` of the module CURRENTLY
    // being lowered (saved/restored around each `elaborate_instance`, like cur_prefix).
    // `#delay` literals scale by this; `$time`/`$realtime` divide by it (per process).
    cur_time_mult: u64,
    // Per-ProcId multiplier table (parallel to `processes`), threaded to the engine via
    // `SimOpts.proc_multipliers` for `$time`/`$realtime` scaling. NEVER in the golden root.
    proc_multipliers: Vec<u32>,
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
            cur_prefix: String::new(),
            params: BTreeMap::new(),
            inst_stack: Vec::new(),
            cur_inst: 0,
            func_table: BTreeMap::new(),
            task_table: BTreeMap::new(),
            subst: Vec::new(),
            out_subst: Vec::new(),
            inline_stack: Vec::new(),
            fork_modes: ForkModeTable::new(),
            cur_proc: 0,
            in_fork: false,
            mod_unit_exp: BTreeMap::new(),
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
        self.processes.push(p);
    }

    fn finish(self) -> ir::SimIr {
        ir::SimIr {
            instances: self.instances,
            nets: self.nets,
            processes: self.processes, // ← v2: procedural lowering
            cont_assigns: self.cont_assigns,
            funcs: Vec::new(), // ← NEXT SLICE (function/task)
            exprs: self.exprs,
            stmts: self.stmts,  // ← v2: per-BB straight-line stmt arena
            blocks: Vec::new(), // funcs body arena — reserved (deferred past v2)
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
        self.sink.emit(LogEvent::Diagnostic(Diagnostic {
            severity: Severity::Warning,
            code: MsgCode::ElabWidthTrunc,
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
                self.warn(&format!(
                    "module `{name}` declared {n} times; first declaration used"
                ));
            }
        }

        let top = match pick_top(&map, &order) {
            Some(t) => t,
            None => {
                self.error(MsgCode::ElabUnsupported, "no top module to elaborate");
                return;
            }
        };

        // Top instance: parent None, path = its own module name (root VCD scope),
        // no incoming port/param bindings.
        let top_path = top.name.name.clone();
        self.elaborate_instance(top, &top_path, None, &[], PortBinding::None, &map);

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

        // (3b) BODY-level `parameter`/`localparam` (a `ModuleItem::Param`, NOT in
        //      the ANSI `#(...)` header that `bind_params` handles). Bind in decl
        //      order — a `localparam C = A*B+1` may reference an earlier param —
        //      BEFORE nets so `[W-1:0]` folds and runtime refs (`x = P`) resolve.
        for item in &module.body {
            if let ast::ModuleItem::Param(p) = item {
                let v = self.const_eval_in_scope(&p.value).unwrap_or(0);
                let key = self.fq(&p.name.name);
                saved_params.push((key.clone(), self.params.insert(key, v)));
            }
        }

        // (3.5) collect THIS module's functions/tasks (bare name → def) for inline
        //       expansion at call sites (pass 7). Saved/restored so a sibling/parent
        //       instance of another module does not inherit them. Functions are not
        //       hierarchical in v1, so the bare name is the key.
        let saved_funcs = std::mem::take(&mut self.func_table);
        let saved_tasks = std::mem::take(&mut self.task_table);
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
                _ => {}
            }
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

        // (6) port-connection cont-assigns (parent expr ↔ child port net).
        self.wire_ports(module, binding, &saved_prefix);

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
        self.func_table = saved_funcs;
        self.task_table = saved_tasks;
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
                // DEFERRED: instance arrays. Lower a single instance + note.
                self.warn("instance-array range ignored (v3: single instance)");
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
    ) -> Vec<(String, Option<u32>)> {
        // Build name→value from the resolved overrides. Positional binds to the
        // i-th declaration index (matches module.params order).
        let mut ovr_by_name: BTreeMap<&str, Option<u32>> = BTreeMap::new();
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
            let chosen_val: Option<u32> = match ovr_by_name.get(p.name.name.as_str()) {
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
            let v = chosen_val.unwrap_or(0);
            let key = self.fq(&p.name.name);
            saved.push((key.clone(), self.params.insert(key, v)));
        }
        saved
    }

    /// Restore the param map to the snapshot taken before this instance bound its
    /// params (so sibling instances of the same module re-bind cleanly).
    fn restore_params(&mut self, saved: Vec<(String, Option<u32>)>) {
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
    fn lookup_scoped(&self, name: &str) -> Option<u32> {
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
    fn walk_scopes(&self, name: &str, table: &BTreeMap<String, u32>) -> Option<u32> {
        let mut prefix = self.cur_prefix.as_str();
        loop {
            let key = if prefix.is_empty() {
                name.to_string()
            } else {
                format!("{prefix}.{name}")
            };
            if let Some(&v) = table.get(&key) {
                return Some(v);
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

    /// Param-aware const-eval (the v1 free `const_eval_u32` SLOT). Extends the
    /// literal evaluator with: an `Ident` naming a param bound in the current
    /// scope, and Add/Sub/Mul/Div/Mod/Shl/Shr binary folding (so `WIDTH-1` /
    /// `WIDTH*2` resolve). Returns None for anything still non-constant (signal
    /// ref, unbound name, unsupported op) — caller defaults + may diagnose.
    fn const_eval_in_scope(&self, e: &ast::Expr) -> Option<u32> {
        match &e.kind {
            // literal / paren / unary +,-  → reuse the v1 free evaluator.
            ast::ExprKind::IntLit { .. } => const_eval_u32(e),
            ast::ExprKind::Paren { inner } => self.const_eval_in_scope(inner),
            ast::ExprKind::Unary { op, operand } => {
                let v = self.const_eval_in_scope(operand)?;
                match op {
                    ast::UnOp::Plus => Some(v),
                    ast::UnOp::Minus => Some(v.wrapping_neg()),
                    ast::UnOp::BitNot => Some(!v),
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
            ast::ExprKind::Binary { op, lhs, rhs } => {
                let a = self.const_eval_in_scope(lhs)?;
                let b = self.const_eval_in_scope(rhs)?;
                match op {
                    ast::BinOp::Add => Some(a.wrapping_add(b)),
                    ast::BinOp::Sub => Some(a.wrapping_sub(b)),
                    ast::BinOp::Mul => Some(a.wrapping_mul(b)),
                    ast::BinOp::Div if b != 0 => Some(a / b),
                    ast::BinOp::Mod if b != 0 => Some(a % b),
                    ast::BinOp::Shl => Some(a.wrapping_shl(b)),
                    ast::BinOp::Shr => Some(a.wrapping_shr(b)),
                    // Comparison / equality / logical / bitwise folding — required
                    // so a generate-for CONDITION (`i < N`, `i != 0`, …) const-folds
                    // to 1/0 during unroll. Unsigned u32 semantics (genvars are
                    // elaboration integers); `===`/`!==` collapse to `==`/`!=` since
                    // a folded const has no x/z. (Width/sign-correct evaluation is a
                    // later refinement; this is exact for the genvar-loop domain.)
                    ast::BinOp::Lt => Some((a < b) as u32),
                    ast::BinOp::Le => Some((a <= b) as u32),
                    ast::BinOp::Gt => Some((a > b) as u32),
                    ast::BinOp::Ge => Some((a >= b) as u32),
                    ast::BinOp::Eq | ast::BinOp::CaseEq => Some((a == b) as u32),
                    ast::BinOp::Ne | ast::BinOp::CaseNe => Some((a != b) as u32),
                    ast::BinOp::BitAnd => Some(a & b),
                    ast::BinOp::BitOr => Some(a | b),
                    ast::BinOp::BitXor => Some(a ^ b),
                    ast::BinOp::BitXnor => Some(!(a ^ b)),
                    ast::BinOp::LogAnd => Some(((a != 0) && (b != 0)) as u32),
                    ast::BinOp::LogOr => Some(((a != 0) || (b != 0)) as u32),
                    // `**` is IN-MVP and `parameter W = 2**N` is ubiquitous; folding
                    // it (was the `_ => None` silent-0 trap) keeps width/param exprs
                    // correct. Overflow saturates to u32::MAX so an absurd width still
                    // trips the downstream MAX_NET_WIDTH cap LOUDLY rather than wrap.
                    ast::BinOp::Pow => Some(a.checked_pow(b).unwrap_or(u32::MAX)),
                    // Arithmetic shifts: in the unsigned u32 elaboration domain
                    // (genvars/params are non-negative integers) they coincide with
                    // the logical shifts already handled above.
                    ast::BinOp::AShl => Some(a.wrapping_shl(b)),
                    ast::BinOp::AShr => Some(a.wrapping_shr(b)),
                    // Div/Mod by zero (the guards above fail) → non-constant.
                    _ => None,
                }
            }
            _ => None,
        }
    }

    /// True iff this range bound is a SUBTRACTION whose const-folded operands
    /// underflow (`lhs < rhs`) — i.e. a `[W-1:0]` with `W==0` that wraps to
    /// `u32::MAX`. Distinguishes a param-driven underflow artifact (clamp+warn)
    /// from a *literal* huge bound like `[4294967295:0]` (still a fatal over-cap
    /// width). Only the direct `a - b` shape is treated as an artifact; an `Paren`
    /// wrapper is unwrapped (Fix 1 defensive).
    fn bound_underflowed(&self, e: &ast::Expr) -> bool {
        match &e.kind {
            ast::ExprKind::Paren { inner } => self.bound_underflowed(inner),
            ast::ExprKind::Binary {
                op: ast::BinOp::Sub,
                lhs,
                rhs,
            } => match (self.const_eval_in_scope(lhs), self.const_eval_in_scope(rhs)) {
                (Some(a), Some(b)) => a < b,
                _ => false,
            },
            _ => false,
        }
    }

    /// Emit `ElabMultidriver` for any net targeted by ≥2 whole-net continuous
    /// assigns. Deterministic: nets scanned in ascending NetId (BTreeMap), each
    /// reported once. Partial-select / bit-select drivers are NOT counted (that
    /// needs the deferred bit-level resolver).
    fn check_whole_net_multidriver(&mut self) {
        let mut full_drives: BTreeMap<u32, u32> = BTreeMap::new();
        for ca in &self.cont_assigns {
            if ca.lhs.chunks.len() == 1 {
                let c = &ca.lhs.chunks[0];
                if c.word.is_none() && c.offset.is_none() && c.width.is_none() {
                    *full_drives.entry(c.net).or_insert(0) += 1;
                }
            }
        }
        let dups: Vec<u32> = full_drives
            .into_iter()
            .filter(|&(_, n)| n > 1)
            .map(|(net, _)| net)
            .collect();
        for net in dups {
            self.error(
                MsgCode::ElabMultidriver,
                &format!("net #{net} driven by multiple continuous assignments"),
            );
        }
    }

    // ── PASS 1a: ANSI ports → nets ─────────────────────────────────
    fn elaborate_ports(&mut self, ports: &ast::PortList) {
        if let ast::PortList::Ansi(list) = ports {
            for p in list {
                let kind = p.net_or_var.unwrap_or(ast::NetVarKind::Wire); // default net type
                let (width, msb, lsb, signed) =
                    self.range_to_dims(kind, p.range.as_ref(), p.signed);
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
        for decl in &d.names {
            let (width, msb, lsb, signed) = self.range_to_dims(d.kind, d.range.as_ref(), d.signed);
            let dim_extents = self.array_dim_extents(&decl.unpacked);
            let array_len = dim_extents
                .iter()
                .fold(1u32, |acc, &(_, n)| acc.saturating_mul(n.max(1)));
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
        }
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
                    let msb = self.const_eval_in_scope(&r.msb).unwrap_or(0);
                    let lsb = self.const_eval_in_scope(&r.lsb).unwrap_or(0);
                    let size = (((msb.abs_diff(lsb) as u64) + 1).min(u32::MAX as u64)) as u32;
                    (msb.min(lsb), size.max(1))
                }
                ast::Dim::Size(e) => (0, self.const_eval_in_scope(e).unwrap_or(1).max(1)),
            })
            .collect()
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
        match range {
            None => (1, 0, 0, signed),
            Some(r) => {
                // v3: fold through the param-aware evaluator so `[W-1:0]` resolves
                // `W` to the bound parameter value in the current instance scope.
                let msb = self.const_eval_in_scope(&r.msb).unwrap_or(0);
                let lsb = self.const_eval_in_scope(&r.lsb).unwrap_or(0);
                // Guard a degenerate `[W-1:0]` with W==0 → `[0u32.wrapping_sub(1):0]`
                // = `[0xFFFF_FFFF:0]` (Fix 1 defensive): a bound EXPRESSION whose
                // subtraction wrapped (a param-dependent underflow) is clamped to
                // width 1 + warn, NOT a fatal MAX_NET_WIDTH explosion. A *literal*
                // huge bound (`[4294967295:0]`) is NOT an underflow artifact and
                // still hits the over-cap error below.
                if self.bound_underflowed(&r.msb) || self.bound_underflowed(&r.lsb) {
                    self.warn(
                        "parameterized range underflowed (param value 0?); net clamped to width 1",
                    );
                    return (1, 0, 0, signed);
                }
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
                        return self.push_expr(ir::Expr::Signal { net, word: None });
                    }
                    // parameter / localparam / genvar: a constant in THIS scope (or
                    // an enclosing generate scope) folds to a Const, NOT a net read.
                    // Resolved before `resolve_net` so a param never errors as an
                    // undeclared net (mirrors `const_eval_in_scope`'s lookup_scoped).
                    if let Some(v) = self.lookup_scoped(seg) {
                        return self.const_u32_expr(v, 32);
                    }
                }
                let net = self.resolve_net(path);
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
                let base = self.lower_expr(base);
                if self.expr_is_real(base) {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "bit/part-select not defined on real operand",
                    );
                }
                let offset = self.lower_expr(index);
                let width = self.const_u32_expr(1, 32);
                self.push_expr(ir::Expr::Select {
                    base,
                    offset,
                    width,
                    kind: ir::SelKind::Bit,
                })
            }
            ast::ExprKind::PartSelect { base, msb, lsb } => {
                let base = self.lower_expr(base);
                if self.expr_is_real(base) {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "bit/part-select not defined on real operand",
                    );
                }
                let lsb_id = self.lower_expr(lsb);
                let msb_id = self.lower_expr(msb);
                let width = self.width_from_msb_lsb_checked(msb, lsb, msb_id, lsb_id);
                self.push_expr(ir::Expr::Select {
                    base,
                    offset: lsb_id,
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
                let base = self.lower_expr(base);
                if self.expr_is_real(base) {
                    self.error(
                        MsgCode::ElabUnsupported,
                        "bit/part-select not defined on real operand",
                    );
                }
                let offset = self.lower_expr(offset);
                let width = self.lower_expr(width);
                let kind = match dir {
                    ast::PartDir::PlusColon => ir::SelKind::PartIdxUp,
                    ast::PartDir::MinusColon => ir::SelKind::PartIdxDown,
                };
                self.push_expr(ir::Expr::Select {
                    base,
                    offset,
                    width,
                    kind,
                })
            }

            // ── structural ─────────────────────────────────────────
            ast::ExprKind::Concat { parts } => {
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
                let arg_ids: Vec<u32> = args.iter().map(|a| self.lower_expr(a)).collect();
                match map_sysfunc(&name.name) {
                    Some(which) => self.push_expr(ir::Expr::SysFunc {
                        which,
                        args: arg_ids,
                    }),
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
        ir::Lvalue { chunks }
    }

    fn collect_lval_chunks(&mut self, lv: &ast::Lvalue, out: &mut Vec<ir::LvalChunk>) {
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
                out.push(ir::LvalChunk {
                    net,
                    word: None,
                    offset: None,
                    width: None,
                    kind: ir::SelKind::Bit, // neutral tag; offset/width None ⇒ whole net
                });
            }
            ast::Lvalue::BitSelect { base, index, .. } => {
                // SYMMETRY with the RHS read: a `base[i]…[k]` chain rooted at an
                // ARRAY net writes the flat element word (first D indices, row-major)
                // with an optional trailing single bit-select. `LvalChunk.word` is an
                // ExprId, evaluated at write time, so `mem[k] = …` (runtime k) and
                // `g[i][j] = …` (2-D element) both work; `mem[k]`/`g[i][j]` are the
                // D==1/D==2 ends of one path. A scalar base falls through to plain
                // bit-select.
                if let Some((net, idxs)) = self.lval_array_chain(base, index) {
                    self.collect_array_write(net, &idxs, out);
                } else {
                    let net = self.lval_base_net(base);
                    let offset = self.lower_expr(index);
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
                out.push(ir::LvalChunk {
                    net,
                    word,
                    offset: Some(lsb_id),
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
                let off = self.lower_expr(offset);
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

        // SD2: automatic ⇒ frame-call, deferred. Direct/mutual recursion is caught
        // by the inline_stack guard.
        if func.automatic {
            self.error(
                MsgCode::ElabUnsupported,
                &format!("automatic function `{fname}` (frame-call deferred)"),
            );
            return self.placeholder_expr();
        }
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
                self.error(
                    MsgCode::ElabUnsupported,
                    &format!("malformed integer literal `{raw}`"),
                );
                make_const_u32(0, 32)
            }
        };
        self.intern_const(cv)
    }

    /// Append a `Const` expr of literal `n` (width `w`); returns its ExprId.
    fn const_u32_expr(&mut self, n: u32, w: u32) -> u32 {
        let cid = self.intern_const(make_const_u32(n, w));
        self.push_expr(ir::Expr::Const { val: cid })
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
                        Some(n) if self.nets.get(n as usize).is_some_and(|nv| nv.array_len > 1) => {
                            break n
                        }
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
                        Some(n) if self.nets.get(n as usize).is_some_and(|nv| nv.array_len > 1) => {
                            break n
                        }
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
        let mut acc: Option<u32> = None;
        for (k, idx) in word_idxs.iter().enumerate() {
            let lo = extents[k].0;
            // normalized 0-based coordinate: `idx - lo` (lo==0 ⇒ raw index, no Sub).
            let coord = if lo == 0 {
                self.lower_expr(idx)
            } else {
                let i = self.lower_expr(idx);
                let lo_c = self.const_u32_expr(lo, 32);
                self.push_expr(ir::Expr::Binary {
                    op: ir::BinOp::Sub,
                    lhs: i,
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
        acc.unwrap_or_else(|| self.const_u32_expr(0, 32))
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
            Initial => ir::Sensitivity {
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
                net: self.sens_event_net(&ev.expr),
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

    /// Resolve an event-control expr to the net it senses. v2: bare signal name
    /// (or parenthesized one); anything else → POISON_NET + note.
    fn sens_event_net(&mut self, e: &ast::Expr) -> u32 {
        match &e.kind {
            ast::ExprKind::Ident(path) => self.resolve_net(path),
            ast::ExprKind::Paren { inner } => self.sens_event_net(inner),
            _ => {
                self.warn("event control on a non-signal expression (v2: bare signal names)");
                POISON_NET
            }
        }
    }

    // ── the recursive statement-lowering heart ─────────────────────
    /// CONTRACT: on entry `b.cur` is open; on exit `b.cur` is open and is the
    /// "continue point" (where control flows next). Every form upholds this.
    fn lower_stmt(&mut self, b: &mut ProcessBuilder, s: &ast::Stmt) {
        match s {
            // ── STRAIGHT-LINE (stay in the same block) ──────────────
            ast::Stmt::Blocking {
                lhs, delay, rhs, ..
            } => {
                // intra-assignment delay: WARN + drop the delay, keep the assign (M-D).
                if delay.is_some() {
                    self.warn("intra-assignment delay (= #d) dropped (v2); assign kept");
                }
                let rhs_id = self.lower_expr(rhs);
                let lv = self.lower_lvalue(lhs);
                let sid = self.push_stmt(ir::Stmt::BlockingAssign {
                    lhs: lv,
                    rhs: rhs_id,
                });
                b.push_stmt_id(sid);
            }
            ast::Stmt::NonBlocking {
                lhs, delay, rhs, ..
            } => {
                if delay.is_some() {
                    self.warn("intra-assignment delay (<= #d) dropped (v2); assign kept");
                }
                let rhs_id = self.lower_expr(rhs);
                let lv = self.lower_lvalue(lhs);
                let sid = self.push_stmt(ir::Stmt::NonblockingAssign {
                    lhs: lv,
                    rhs: rhs_id,
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
            ast::Stmt::Block { stmts, .. } => {
                for st in stmts {
                    self.lower_stmt(b, st);
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
                let cause = self.lower_event_wait_cause(ctrl);
                let resume = b.new_block();
                b.end_block_with(ir::Terminator::Wait {
                    cond: cause,
                    resume: resume.raw(),
                });
                b.start_block(resume);
                if let Some(body) = body {
                    self.lower_stmt(b, body);
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

            // ── SECONDARY / DEFERRED → WARN + recover (stay in block) ──
            // disable: doc-17 lowering table says "Stmt::Disable then Goto", but
            // scope-id resolution (DisableKind/target) is deferred. Emit the
            // Stmt::Disable with a Scope/0 placeholder so the *shape* is present,
            // then continue straight-line. Non-fatal. (CFG MINOR-1 reconciled.)
            ast::Stmt::Disable { .. } => {
                self.warn("disable target scope-id unresolved (v2); emitted as Scope/0 no-op");
                let sid = self.push_stmt(ir::Stmt::Disable {
                    scope_kind: ir::DisableKind::Scope,
                    target: 0,
                });
                b.push_stmt_id(sid);
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
                for (child_entry, st) in child_entries.iter().zip(stmts.iter()) {
                    b.start_block(*child_entry);
                    self.lower_stmt(b, st);
                    b.goto(join_bb);
                }
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
            ast::Stmt::EventTrigger { .. }
            | ast::Stmt::Assign { .. }
            | ast::Stmt::Deassign { .. }
            | ast::Stmt::Force { .. }
            | ast::Stmt::Release { .. } => {
                self.warn("procedural-continuous / event-trigger construct skipped (v2); no-op");
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

    /// Per-label equality test for a case arm. Plain `case` is the exact 4-state
    /// `scrut === label`.
    ///
    /// For `casez`/`casex`, a bit position is don't-care if EITHER the label OR the
    /// SCRUTINEE has a wildcard there — and the scrutinee's wildcards are RUNTIME
    /// values, so a static label-only mask is insufficient (it left `casex(1x10)`
    /// vs `1010` falsely missing). We instead exploit the 4-state algebra:
    ///   match  ⇔  reduction_or(scrut ^ label) !== 1'b1
    /// `^` yields `1` only where both sides are KNOWN and DIFFER, and `x` wherever
    /// either side is x/z; reduction-or is `1` iff some position definitely differs
    /// (the `x`/`z` positions wash to `x`, which is `!== 1`). This covers label AND
    /// scrutinee wildcards at runtime using only existing ops — NO frozen-IR change.
    ///
    /// (casez nominally wildcards only `z`/`?`, not `x`; this treats every unknown —
    /// on either side — as a wildcard, which is exact for the ubiquitous `z`/`?`
    /// form and only over-lenient on a rare explicit-`x`-in-casez, the same v1
    /// simplification the prior label-mask already made, now symmetric on both sides.)
    fn case_label_eq(&mut self, scrut_id: u32, label: &ast::Expr, kind: ast::CaseKind) -> u32 {
        let lbl_id = self.lower_expr(label);
        if matches!(kind, ast::CaseKind::Case) {
            return self.push_expr(ir::Expr::Binary {
                op: ir::BinOp::CaseEq,
                lhs: scrut_id,
                rhs: lbl_id,
            });
        }
        let xor = self.push_expr(ir::Expr::Binary {
            op: ir::BinOp::BitXor,
            lhs: scrut_id,
            rhs: lbl_id,
        });
        let red = self.push_expr(ir::Expr::Unary {
            op: ir::UnOp::RedOr,
            operand: xor,
        });
        let one = self.const_u32_expr(1, 1);
        self.push_expr(ir::Expr::Binary {
            op: ir::BinOp::CaseNe,
            lhs: red,
            rhs: one,
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
    /// `Level`; multi-edge → first edge term + note (no multi-edge variant).
    fn lower_event_wait_cause(&mut self, ctrl: &ast::Sensitivity) -> ir::WaitCause {
        match ctrl {
            ast::Sensitivity::Star => {
                self.warn("in-body @(*) wait (v2: explicit signal list)");
                ir::WaitCause::Level { nets: Vec::new() }
            }
            ast::Sensitivity::List(list) => {
                let has_edge = list.iter().any(|ev| !matches!(ev.edge, ast::Edge::NoEdge));
                if has_edge {
                    if list.len() > 1 {
                        self.warn("multi-term in-body edge wait (v2: single edge term)");
                    }
                    let ev = list
                        .iter()
                        .find(|ev| !matches!(ev.edge, ast::Edge::NoEdge))
                        .expect("has_edge ⇒ at least one edge term");
                    ir::WaitCause::Edge {
                        net: self.sens_event_net(&ev.expr),
                        kind: map_edge(ev.edge),
                    }
                } else {
                    let nets = list
                        .iter()
                        .map(|ev| self.sens_event_net(&ev.expr))
                        .collect();
                    ir::WaitCause::Level { nets }
                }
            }
        }
    }

    /// `#delay` → `(amount, region)`. `amount` is the const-folded tick count
    /// (matches the frozen `Terminator::Delay.amount: u32`). SD3: `#0` →
    /// `Inactive`, `#d>0` → `Active`. Non-const → note + degrade to `#0`.
    fn lower_delay(&mut self, d: &ast::Delay) -> (u32, ir::DelayRegion) {
        let mult = self.cur_time_mult;
        let amount = d
            .values
            .first()
            .and_then(|e| const_delay_ticks(e, mult))
            .unwrap_or_else(|| {
                self.warn("non-constant #delay not supported (v2); degraded to #0");
                0
            });
        let region = if amount == 0 {
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
        let (fmt, value_args): (Option<u32>, &[ast::Expr]) = if takes_fmt {
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
                    None
                } else {
                    Some(self.lower_expr(a))
                }
            })
            .collect();
        // §4.1a STATIC gate: a `%b/%h/%o/%x` conversion specifier paired with a
        // real-typed argument is illegal (real has no radix form; use $realtobits).
        if let Some(fmt_str) = &fmt_raw {
            self.check_format_real_radix(fmt_str, &arg_ids);
        }
        Some(self.push_stmt(ir::Stmt::SysTask {
            which,
            fmt,
            args: arg_ids,
        }))
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
fn map_systask(dollar_name: &str) -> Option<ir::SysTaskId> {
    match dollar_name {
        "$display" | "$displayb" | "$displayo" | "$displayh" => Some(ir::SysTaskId::Display),
        "$write" | "$writeb" | "$writeo" | "$writeh" => Some(ir::SysTaskId::Write),
        "$monitor" => Some(ir::SysTaskId::Monitor),
        "$strobe" => Some(ir::SysTaskId::Strobe),
        "$finish" => Some(ir::SysTaskId::Finish),
        "$stop" => Some(ir::SysTaskId::Stop),
        "$dumpfile" => Some(ir::SysTaskId::DumpFile),
        "$dumpvars" => Some(ir::SysTaskId::DumpVars),
        "$dumpon" => Some(ir::SysTaskId::DumpOn),
        "$dumpoff" => Some(ir::SysTaskId::DumpOff),
        "$dumpall" => Some(ir::SysTaskId::DumpAll),
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
        ast::Stmt::DelayCtrl { .. } | ast::Stmt::EventCtrl { .. } | ast::Stmt::Wait { .. } => true,
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
        _ => None,
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
        // Wire + all net aliases (Tri/Uwire/Wand/...) behave as Wire in v1.
        _ => ir::NetKind::Wire,
    }
}

/// Whether a kind is modeled in v1 without an `ElabUnsupported` note. Pure
/// aliases (Tri/Uwire) are accepted silently; resolution nets and real/time are
/// flagged (still mapped to Wire so the arena stays valid).
fn net_kind_supported(k: ast::NetVarKind) -> bool {
    use ast::NetVarKind::*;
    matches!(
        k,
        Wire | Tri | Uwire | Reg | Logic | Integer | Real | Realtime
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
