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
use literal::{make_const_u32, parse_int_literal};
use sim_ir as ir;

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
            symbols: BTreeMap::new(),
            const_dedup: BTreeMap::new(),
        }
    }

    fn finish(self) -> ir::SimIr {
        ir::SimIr {
            instances: self.instances,
            nets: self.nets,
            processes: Vec::new(), // ← NEXT SLICE (procedural lowering)
            cont_assigns: self.cont_assigns,
            funcs: Vec::new(), // ← NEXT SLICE (function/task)
            exprs: self.exprs,
            stmts: Vec::new(),  // ← NEXT SLICE
            blocks: Vec::new(), // ← NEXT SLICE
            consts: self.consts,
        }
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
                ast::ModuleItem::Proc(_) => {
                    // DEFERRED: procedural-block → Process/BB lowering (next slice).
                    self.error(
                        MsgCode::ElabUnsupported,
                        "procedural blocks are not yet supported (v1)",
                    );
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
            ast::ExprKind::RealLit { .. } | ast::ExprKind::StrLit { .. } => {
                self.error(
                    MsgCode::ElabUnsupported,
                    "real/string literal not supported (v1)",
                );
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

// ── free helpers (pure, no &self) ──────────────────────────────────

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
