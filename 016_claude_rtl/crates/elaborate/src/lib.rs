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
use literal::{make_const_u32, parse_int_literal, parse_str_literal};
use sim_ir as ir;

/// Const-bounded `repeat`/`for` are UNROLLED (the loop counter cannot live in a
/// `SuspendState.locals` slot — `Stmt`'s `Lvalue` only addresses nets, not
/// locals, and `Stmt` is frozen). This caps the unroll so a `repeat(1_000_000)`
/// in hostile input cannot explode the block arena. Above the cap → `ElabUnsupported`.
const REPEAT_UNROLL_CAP: u32 = 1024;

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
    let mut el = Elaborator::new(sink);
    el.run(unit);
    if el.had_error {
        None
    } else {
        Some(el.finish())
    }
}

/// Canonical dedup key for the const pool. Cloning the `Vec<u64>` planes keeps
/// the compare total and order-independent (used only for lookup, never to drive
/// arena order — see determinism note).
type ConstKey = (u32, bool, u8, Vec<u64>, Vec<u64>);

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
    symbols: BTreeMap<String, u32>, // net/var NAME → NetId
    const_dedup: BTreeMap<ConstKey, u32>,
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
        }
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

    // ── two-phase driver ───────────────────────────────────────────
    fn run(&mut self, unit: &ast::SourceUnit) {
        // v1: exactly one top module. Take the first; ignore the rest
        // (multi-module/hierarchy is DEFERRED).
        let module = match unit.items.iter().find_map(|it| match it {
            ast::TopItem::Module(m) => Some(m),
            ast::TopItem::Error(_) => None,
        }) {
            Some(m) => m,
            None => {
                // "no module at all" is a missing-construct condition, not a
                // failed *instance* resolution → ElabUnsupported reads truer than
                // ElabUnresolvedInstance. (COVERAGE verdict LOW.)
                self.error(MsgCode::ElabUnsupported, "no top module to elaborate");
                return;
            }
        };

        // PASS 1: declarations → nets + symbol table (DECLARATION ORDER).
        // ANSI ports first (they are nets too), then body NetVarDecls.
        self.elaborate_ports(&module.ports);
        for item in &module.body {
            if let ast::ModuleItem::NetVar(d) = item {
                self.elaborate_netvar_decl(d, &module.ports);
            }
        }

        // Self-instance for the top module: window = [0, nets.len()).
        self.instances.push(ir::Instance {
            parent: None,
            module: 0,
            first_net: 0,
            net_count: self.nets.len() as u32,
        });

        // PASS 2: continuous assigns → cont_assigns (+ exprs/consts arenas).
        for item in &module.body {
            match item {
                ast::ModuleItem::ContAssign(ca) => self.elaborate_cont_assign(ca),
                ast::ModuleItem::Proc(p) => {
                    // v2: procedural-block → Process (one per block, body order).
                    let proc = self.lower_proc_block(p);
                    self.processes.push(proc);
                }
                ast::ModuleItem::Instance(_)
                | ast::ModuleItem::Generate(_)
                | ast::ModuleItem::Func(_)
                | ast::ModuleItem::Task(_)
                | ast::ModuleItem::Defparam(_) => {
                    self.error(MsgCode::ElabUnsupported, "construct deferred past v1");
                }
                // NetVar already done; Param/PortDecl/Genvar/Error: no-op in v1.
                _ => {}
            }
        }

        // PASS 3: whole-net multidriver check. Bit-level driver resolution is
        // DEFERRED, but the trivial common case — the SAME net fully driven by
        // two continuous assigns — is caught here. A "full-net" lhs is a single
        // chunk with no word/offset/width. (COVERAGE verdict MEDIUM.)
        self.check_whole_net_multidriver();
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

    // ── PASS 1b: body NetVarDecl → nets ────────────────────────────
    fn elaborate_netvar_decl(&mut self, d: &ast::NetVarDecl, ports: &ast::PortList) {
        if !net_kind_supported(d.kind) {
            self.error(MsgCode::ElabUnsupported, "unsupported net/var kind (v1)");
            // still emit a Wire-shaped net per name so references resolve.
        }
        for decl in &d.names {
            let (width, msb, lsb, signed) = self.range_to_dims(d.kind, d.range.as_ref(), d.signed);
            let array_len = self.array_len_of(&decl.unpacked);
            let dir = self.dir_for_name(&decl.name.name, ports);
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
        }
    }

    /// Register a net by name → NetId (declaration-order append). A duplicate
    /// name is a hard error: we keep the FIRST binding, emit `ElabUnsupported`
    /// (closest v1 code; doc-15 reserves `E-ELAB-DUP-DECL` for the eventual
    /// dedicated slot), and do NOT push the orphan net — so `net_count` and the
    /// golden hash are not perturbed by an unreferenceable duplicate.
    /// (LOWERING + COVERAGE verdicts: duplicate-net silent acceptance.)
    fn add_net(&mut self, name: &str, net: ir::NetVar) {
        if self.symbols.contains_key(name) {
            self.error(
                MsgCode::ElabUnsupported,
                &format!("net/variable `{name}` redeclared (duplicate declaration)"),
            );
            return;
        }
        let id = self.nets.len() as u32;
        self.nets.push(net);
        self.symbols.insert(name.to_string(), id);
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
        match range {
            None => (1, 0, 0, signed),
            Some(r) => {
                let msb = const_eval_u32(&r.msb).unwrap_or(0);
                let lsb = const_eval_u32(&r.lsb).unwrap_or(0);
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

    /// Unpacked-array length = product of each dim's length. Empty → 1.
    /// Each dim length and the running product are overflow-saturated in `u32`
    /// (the `abs_diff + 1` is widened to `u64` first to avoid the same panic as
    /// [`Self::range_to_dims`]). (COVERAGE verdict HIGH — companion guard.)
    fn array_len_of(&mut self, dims: &[ast::Dim]) -> u32 {
        let mut len: u32 = 1;
        for d in dims {
            let n: u32 = match d {
                ast::Dim::Range(r) => {
                    let msb = const_eval_u32(&r.msb).unwrap_or(0);
                    let lsb = const_eval_u32(&r.lsb).unwrap_or(0);
                    (((msb.abs_diff(lsb) as u64) + 1).min(u32::MAX as u64)) as u32
                }
                ast::Dim::Size(e) => const_eval_u32(e).unwrap_or(1),
            };
            len = len.saturating_mul(n.max(1));
        }
        len
    }

    /// Direction of a body-declared net: Input/Output/Inout if it appears in the
    /// port list, else Internal.
    fn dir_for_name(&mut self, name: &str, ports: &ast::PortList) -> ir::PortDir {
        match ports {
            ast::PortList::Ansi(list) => list
                .iter()
                .find(|p| p.name.name == name)
                .map(|p| map_port_dir(p.dir))
                .unwrap_or(ir::PortDir::Internal),
            ast::PortList::NonAnsi(names) => {
                if names.iter().any(|i| i.name == name) {
                    // TODO(v2, COVERAGE verdict LOW): a non-ANSI body `PortDecl`
                    // carries the REAL direction (`output reg y;`). v1 defaults
                    // every non-ANSI port to Input — so an `output` port lowers to
                    // a WRONG-but-plausible Input dir. Merge body PortDecl dirs
                    // before trusting `dir` on a NonAnsi module.
                    ir::PortDir::Input
                } else {
                    ir::PortDir::Internal
                }
            }
            ast::PortList::None => ir::PortDir::Internal,
        }
    }

    // ── PASS 2: continuous assigns ─────────────────────────────────
    fn elaborate_cont_assign(&mut self, ca: &ast::ContinuousAssign) {
        // Delay: hdl-ast Delay values are exprs; sim-ir delay is Option<u32>.
        // v1 const-folds a literal rise delay; non-const → None (note slot).
        let delay = ca.delay.as_ref().and_then(|d| {
            d.values.first().and_then(|e| {
                // a #(min:typ:max) delay surfaces as MinTypMax → take typ branch.
                let pick = match &e.kind {
                    ast::ExprKind::MinTypMax { typ, .. } => typ.as_ref(),
                    _ => e,
                };
                const_eval_u32(pick)
            })
        });
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
                let net = self.resolve_net(path);
                self.push_expr(ir::Expr::Signal { net, word: None })
            }

            // ── operators (1:1 name-map; children lowered first) ────
            ast::ExprKind::Unary { op, operand } => {
                let operand = self.lower_expr(operand);
                self.push_expr(ir::Expr::Unary {
                    op: map_unop(*op),
                    operand,
                })
            }
            ast::ExprKind::Binary { op, lhs, rhs } => {
                let lhs = self.lower_expr(lhs); // POST-ORDER: lhs, then rhs, then self
                let rhs = self.lower_expr(rhs);
                self.push_expr(ir::Expr::Binary {
                    op: map_binop(*op),
                    lhs,
                    rhs,
                })
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
                // SYMMETRY with the LHS (`collect_lval_chunks`): `mem[i]` on an
                // ARRAY net is a WORD select, not a bit select. The LHS disambig
                // is `array_len > 1`; the RHS must match or a memory-element read
                // silently lowers to a bit read of the whole memory (LOWERING
                // verdict MAJOR). Only a direct `Ident` base can be a memory word
                // in v1; a select-of-a-select base falls through to bit-select.
                if let Some(net) = self.array_word_base(base) {
                    let word = self.const_word_index(index);
                    return self.push_expr(ir::Expr::Signal {
                        net,
                        word: Some(word),
                    });
                }
                let base = self.lower_expr(base);
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
                self.push_expr(ir::Expr::Concat { parts: part_ids })
            }
            ast::ExprKind::Replicate { count, value } => {
                // hdl-ast `value: Vec<Expr>` is the element LIST (no wrapper
                // Concat); sim-ir Replicate wants ONE `value: u32` → wrap in a
                // Concat node. (For a single element this is a 1-part Concat,
                // kept for shape-uniformity / determinism.)
                let count = self.lower_expr(count);
                let part_ids: Vec<u32> = value.iter().map(|p| self.lower_expr(p)).collect();
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
            ast::ExprKind::Call { .. } => {
                // User-function calls need `funcs` lowering → DEFERRED past v1.
                self.error(
                    MsgCode::ElabUnsupported,
                    "user function calls not supported (v1)",
                );
                self.placeholder_expr()
            }

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
            ast::ExprKind::RealLit { .. } => {
                self.error(MsgCode::ElabUnsupported, "real literal not supported (v2)");
                self.placeholder_expr()
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
                let net = self.resolve_net(path);
                out.push(ir::LvalChunk {
                    net,
                    word: None,
                    offset: None,
                    width: None,
                    kind: ir::SelKind::Bit, // neutral tag; offset/width None ⇒ whole net
                });
            }
            ast::Lvalue::BitSelect { base, index, .. } => {
                let net = self.lval_base_net(base);
                // Array word-select vs bit-select disambiguated by array_len.
                // `LvalChunk.word` is a CONST word INDEX immediate (not an
                // ExprId), symmetric with the RHS `Signal.word`; `offset`/`width`
                // remain ExprId edges into the arena. (LOWERING verdict MAJOR.)
                let is_word = self
                    .nets
                    .get(net as usize)
                    .map(|n| n.array_len > 1)
                    .unwrap_or(false);
                if is_word {
                    let word = self.const_word_index(index);
                    out.push(ir::LvalChunk {
                        net,
                        word: Some(word),
                        offset: None,
                        width: None,
                        kind: ir::SelKind::Bit,
                    });
                } else {
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
                let net = self.lval_base_net(base);
                let lsb_id = self.lower_expr(lsb);
                let msb_id = self.lower_expr(msb);
                let width = self.width_from_msb_lsb_checked(msb, lsb, msb_id, lsb_id);
                out.push(ir::LvalChunk {
                    net,
                    word: None,
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
                let net = self.lval_base_net(base);
                let off = self.lower_expr(offset);
                let w = self.lower_expr(width);
                let kind = match dir {
                    ast::PartDir::PlusColon => ir::SelKind::PartIdxUp,
                    ast::PartDir::MinusColon => ir::SelKind::PartIdxDown,
                };
                out.push(ir::LvalChunk {
                    net,
                    word: None,
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

    // ── name resolution ────────────────────────────────────────────
    /// Resolve a HierPath → NetId. v1: single-segment (flat) names only. Unknown
    /// → emit + return [`POISON_NET`] (u32::MAX, NOT 0 — so a surviving poison
    /// edge is detectable, never a silent alias of net 0). The IR is discarded on
    /// `had_error` regardless. (COVERAGE verdict MEDIUM.)
    fn resolve_net(&mut self, path: &ast::HierPath) -> u32 {
        if path.segments.len() != 1 {
            self.error(
                MsgCode::ElabUnsupported,
                "hierarchical name reference (v1: flat only)",
            );
            return POISON_NET;
        }
        let name = &path.segments[0].name;
        match self.symbols.get(name) {
            Some(&id) => id,
            None => {
                self.error(
                    MsgCode::ElabUnresolvedName,
                    &format!("undeclared net/variable `{name}`"),
                );
                POISON_NET
            }
        }
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

    /// If `base` is a plain `Ident` resolving to an ARRAY net (`array_len > 1`),
    /// return its NetId — meaning `base[index]` is a memory WORD select, not a
    /// bit select. Otherwise `None`. Used by the RHS BitSelect arm to mirror the
    /// LHS word/bit disambiguation. (LOWERING verdict MAJOR.)
    fn array_word_base(&mut self, base: &ast::Expr) -> Option<u32> {
        if let ast::ExprKind::Ident(path) = &base.kind {
            if path.segments.len() == 1 {
                if let Some(&net) = self.symbols.get(&path.segments[0].name) {
                    if self.nets.get(net as usize).is_some_and(|n| n.array_len > 1) {
                        return Some(net);
                    }
                }
            }
        }
        None
    }

    /// Const-evaluate an array word index to a `u32` immediate (for
    /// `Signal.word` / `LvalChunk.word`). A non-const index is not representable
    /// as a static word in v1 → emit `ElabUnsupported` and fall back to word 0.
    fn const_word_index(&mut self, index: &ast::Expr) -> u32 {
        match const_eval_u32(index) {
            Some(w) => w,
            None => {
                self.error(
                    MsgCode::ElabUnsupported,
                    "non-constant memory word index (v1: constant index only)",
                );
                0
            }
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
        ir::Process {
            sensitivity,
            body,
            entry,
            suspend: fresh_suspend(entry),
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
            // begin..end: block-local decls WARN (ignored) instead of killing IR.
            ast::Stmt::Block { decls, stmts, .. } => {
                if !decls.is_empty() {
                    self.warn("block-local declarations ignored (v2); body lowered");
                }
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
            ast::Stmt::Fork { stmts, .. } => {
                // No Fork terminator lowering yet (join-state deferred). Degrade to
                // SEQUENTIAL execution of the children + warn — sound CFG, wrong
                // concurrency, but the IR survives the demo. (Was IR-killing.)
                self.warn("fork/join lowered as sequential (v2); concurrency not modeled");
                for st in stmts {
                    self.lower_stmt(b, st);
                }
            }
            ast::Stmt::UserTaskCall { .. } => {
                self.warn("user task call skipped (v2); no-op");
            }
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
        // PRIORITY (COVERAGE M-B): casez/casex MUST lower. Wildcard ?/x/z bit
        // semantics are approximated by `===` (CaseEq). This is exact for label
        // sets with no ?/x/z bits (the common FSM/testbench case) and a documented
        // over-strict match otherwise. WARN (non-fatal) — the IR survives.
        if !matches!(kind, ast::CaseKind::Case) {
            self.warn(
                "casez/casex wildcard bits approximated by === (exact when labels \
                 have no ?/x/z); IR lowered",
            );
        }
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

        // Test cascade: for each label, `scrut === label` → arm else next test.
        for (labels, arm) in &tests {
            for label in *labels {
                let lbl_id = self.lower_expr(label);
                let eq = self.push_expr(ir::Expr::Binary {
                    op: ir::BinOp::CaseEq,
                    lhs: scrut_id,
                    rhs: lbl_id,
                });
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

    /// `for` is SECONDARY and needs a runtime counter that survives a suspend —
    /// not representable in the frozen net-only `Stmt::*Assign` Lvalue. v2 rejects
    /// it with a recovering stub (the cursor stays open, an empty Return-block).
    fn lower_for(
        &mut self,
        _b: &mut ProcessBuilder,
        _init: &ast::Stmt,
        _cond: &ast::Expr,
        _step: &ast::Stmt,
        _body: &ast::Stmt,
    ) {
        self.warn("for loop skipped (v2); counter not expressible in frozen net-only Stmt");
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
        let amount = d
            .values
            .first()
            .and_then(|e| {
                let pick = match &e.kind {
                    ast::ExprKind::MinTypMax { typ, .. } => typ.as_ref(),
                    _ => e,
                };
                const_eval_u32(pick)
            })
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
        let (fmt, value_args): (Option<u32>, &[ast::Expr]) = if takes_fmt {
            match args.first().map(|e| &e.kind) {
                Some(ast::ExprKind::StrLit { raw }) => {
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
                if dump_family && !self.is_net_or_const_arg(a) {
                    self.warn("$dump* scope/non-signal argument skipped (v2)");
                    None
                } else {
                    Some(self.lower_expr(a))
                }
            })
            .collect();
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
                path.segments.len() == 1 && self.symbols.contains_key(&path.segments[0].name)
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

/// hdl-ast has 18 net/var kinds; sim-ir freezes only 4. Aliases collapse to the
/// closest 4-state kind; unsupported kinds still map to Wire so references
/// resolve (the call site emits `ElabUnsupported`).
fn map_net_kind_or_wire(k: ast::NetVarKind) -> ir::NetKind {
    use ast::NetVarKind::*;
    match k {
        Reg => ir::NetKind::Reg,
        Logic => ir::NetKind::Logic,
        Integer => ir::NetKind::Integer,
        // Wire + all net aliases (Tri/Uwire/Wand/...) behave as Wire in v1.
        _ => ir::NetKind::Wire,
    }
}

/// Whether a kind is modeled in v1 without an `ElabUnsupported` note. Pure
/// aliases (Tri/Uwire) are accepted silently; resolution nets and real/time are
/// flagged (still mapped to Wire so the arena stays valid).
fn net_kind_supported(k: ast::NetVarKind) -> bool {
    use ast::NetVarKind::*;
    matches!(k, Wire | Tri | Uwire | Reg | Logic | Integer)
}

/// Time-0 default `init`: variables (reg/logic/integer) start all-X; nets start
/// all-Z. `(v,u)`: X=`01`, Z=`11`.
fn default_init(kind: ast::NetVarKind, width: u32) -> ir::BitPacked {
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
