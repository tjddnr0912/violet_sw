//! hdl-ast — the parsed AST for the vitamin front-end (preprocess → lex → PARSE → …).
//!
//! Produced by `hdl-parser`, consumed by `elaborate` (which lowers it to the
//! span-free `sim-ir`, dropping spans into a side-table). Unlike sim-ir, **every
//! node carries a source span** (doc-14 §1: the `.vu` body = "hdl-ast 단위 트리 …
//! + 소스 스팬"). Spans are `u32` byte offsets → deterministic, `.vu`-safe.
//!
//! ## Serialization decision (load-bearing — verified against the derive source)
//! These types derive `Serialize + Deserialize` so elaborate can write the `.vu`
//! body, AND `SchemaHash` so the `.vu` container can gate staleness against the
//! `SourceUnit` shape. The `Box`-recursive AST is hashable because the derive
//! carries a transparent `("Box", 1)` arm (`vita-artifact-derive`) that renders a
//! `Box<T>` as its inner `T` — alongside the `Option`/`Vec`/`BTreeSet` arms —
//! instead of emitting a bare `<Box as SchemaShape>::register`. The shapes obey
//! the determinism rules (no usize/HashMap/float; `Span` = two `u32`), so the
//! `schema_hash::<SourceUnit>()` root is pinned by the golden gate in
//! `tests/schema_hash.rs`. Field add/remove/reorder flips that root, which
//! invalidates every `.vu` on disk (intentional — a `format_version` bump and a
//! golden update must accompany any deliberate change).

use serde::{Deserialize, Serialize};
use vita_artifact_derive::SchemaHash;

// ───────────────────────────── Span ─────────────────────────────
/// Half-open byte range `[lo, hi)` into the preprocessed source. `u32` (not the
/// lexer's `Range<usize>`) so the serialized shape is deterministic across OSes.
/// The parser narrows each `Spanned.span: Range<usize>` at node construction.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct Span {
    pub lo: u32,
    pub hi: u32,
}
impl Span {
    #[inline]
    pub fn new(lo: u32, hi: u32) -> Self {
        Self { lo, hi }
    }
    /// Span union: `self.lo .. max(other.hi, self.lo)`. The normal case is a
    /// strictly-monotonic cursor (`start.to(prev_span())`), where `other.hi >=
    /// self.lo` already holds and the union is `self.lo .. other.hi` byte for byte.
    #[inline]
    pub fn to(self, other: Span) -> Span {
        // CLAMP (verdict M2): a recovery path that composes spans out of order —
        // a parser header whose tokens never advanced past `start` (e.g.
        // `generate for endgenerate`, or PR2's `initial for end`) — would otherwise
        // yield an inverted `[lo, hi)` with `hi < lo`. The old `debug_assert!`
        // PANICKED there (a debug/test-only DoS on truncated input); release
        // silently produced a wrong span. Flooring `hi` at `lo` makes the union
        // total and non-panicking on EVERY input while preserving the normal
        // monotonic-cursor case byte for byte (where `other.hi >= self.lo` already
        // holds), so the determinism / golden-hash contract is unchanged.
        Span {
            lo: self.lo,
            hi: other.hi.max(self.lo),
        }
    }
}

/// An identifier reference: raw lexeme (re-sliced from source by the parser) + span.
/// `EscapedIdent` keeps its raw `\…` form; stripping the leading `\` and the
/// trailing-whitespace rule is the consumer's job. Interning to a `u32 Symbol` is
/// a later optimization (Residual 9); `String` keeps PR1 simple, determinism-safe.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct Ident {
    pub name: String,
    pub span: Span,
}

/// Hierarchical name `a` | `a.b.c`. One-segment is the common case.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct HierPath {
    pub segments: Vec<Ident>,
    pub span: Span,
}

// ──────────────────────────── SourceUnit ────────────────────────────
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct SourceUnit {
    pub items: Vec<TopItem>,
    pub span: Span,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum TopItem {
    Module(ModuleDecl),
    /// Recovery placeholder for an unparseable top-level construct.
    Error(Span),
}

// ──────────────────────────── Module ────────────────────────────
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct ModuleDecl {
    pub is_macromodule: bool, // `module` vs `macromodule`
    pub name: Ident,
    pub params: Vec<ParamDecl>, // ANSI `#( … )` param port list (empty if none)
    pub ports: PortList,
    pub body: Vec<ModuleItem>,
    pub span: Span,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum PortList {
    /// ANSI: header carries dir + type + range inline.
    Ansi(Vec<AnsiPort>),
    /// non-ANSI: header = bare names; dir/type come from body `PortDecl`s.
    NonAnsi(Vec<Ident>),
    /// `module m;` — no port parenthesis at all.
    None,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct AnsiPort {
    pub dir: PortDir,
    pub net_or_var: Option<NetVarKind>, // None ⇒ default wire
    pub signed: bool,
    pub range: Option<Range>, // packed [msb:lsb]
    pub name: Ident,
    pub default: Option<Expr>, // ANSI default value slot (rare)
    pub span: Span,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum PortDir {
    Input,
    Output,
    Inout,
}

// ──────────────────────────── ModuleItem ────────────────────────────
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum ModuleItem {
    NetVar(NetVarDecl),
    Param(ParamDecl),   // body-level parameter/localparam
    PortDecl(PortDecl), // non-ANSI body port-direction decl
    ContAssign(ContinuousAssign),
    Proc(ProceduralBlock),       // [A] type defined; body stub-parsed in PR1
    Instance(ModuleInstance),    // [A]
    Generate(GenerateConstruct), // [A]
    Genvar {
        names: Vec<Ident>,
        span: Span,
    }, // [A]
    Func(FunctionDef),           // [A]
    Task(TaskDef),               // [A]
    Defparam(DefparamItem),      // [A] defparam path = expr;
    /// Recovery placeholder for an unparseable item.
    Error(Span),
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct DefparamItem {
    pub assigns: Vec<(HierPath, Expr)>,
    pub span: Span,
}

// ──────────────────── PortDecl (non-ANSI body dir) ────────────────────
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct PortDecl {
    pub dir: PortDir,
    pub net_or_var: Option<NetVarKind>, // e.g. `output reg`
    pub signed: bool,
    pub range: Option<Range>,
    pub names: Vec<Ident>, // `input [3:0] a, b;`
    pub span: Span,
}

// ──────────────────────────── ParamDecl ────────────────────────────
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct ParamDecl {
    pub kind: ParamKind,
    pub signed: bool,
    pub ty: ParamType,
    pub range: Option<Range>,
    pub name: Ident,
    pub value: Expr, // RHS const-expr (required)
    pub span: Span,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum ParamKind {
    Parameter,
    Localparam,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum ParamType {
    Implicit,
    Integer,
    Real,
    Realtime,
    Time,
}

// ──────────────────────────── NetVarDecl ────────────────────────────
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct NetVarDecl {
    pub kind: NetVarKind,
    pub signed: bool,
    pub range: Option<Range>, // packed/vector [msb:lsb]
    pub names: Vec<DeclName>, // one decl, possibly many names
    pub span: Span,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct DeclName {
    pub name: Ident,
    pub unpacked: Vec<Dim>, // memory dims: reg [7:0] mem [0:255] / mem [256]
    pub init: Option<Expr>, // net/var initializer `= expr`
    pub span: Span,
}
/// An unpacked array dimension. `[msb:lsb]` (V2005) OR `[size]` (SV size-form).
/// (verdict M3: the AST must represent both; the parser accepts `[size]` too.)
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum Dim {
    Range(Range), // [hi:lo]
    Size(Expr),   // [N]
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum NetVarKind {
    // nets
    Wire,
    Tri,
    Wand,
    Triand,
    Wor,
    Trior,
    Tri0,
    Tri1,
    Supply0,
    Supply1,
    Trireg,
    Uwire,
    // variables
    Reg,
    Logic,
    Integer,
    Real,
    Realtime,
    Time,
}

/// `[msb:lsb]`. Bounds are exprs (usually const), NOT pre-evaluated.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct Range {
    pub msb: Expr,
    pub lsb: Expr,
    pub span: Span,
}

// ─────────────────────── ContinuousAssign ───────────────────────
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct ContinuousAssign {
    pub delay: Option<Delay>,
    pub assigns: Vec<(Lvalue, Expr)>, // assign a=b, c=d;
    pub span: Span,
}
/// `#d` | `#(d)` | `#(rise,fall)` | `#(rise,fall,turnoff)`. Each value is a
/// `MinTypMax`-or-plain expr (verdict M2 — `#(1:2:3)` is legal). The parser stores
/// each delay value via `Expr` (mintypmax surfaces as `ExprKind::MinTypMax`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct Delay {
    pub values: Vec<Expr>,
    pub span: Span,
}

// ───────────────── ProceduralBlock + Sensitivity [A] ─────────────────
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct ProceduralBlock {
    pub kind: ProcKind,
    pub sensitivity: Option<Sensitivity>, // only general `always @(…)`
    pub body: Box<Stmt>,                  // usually Block; stub-parsed in PR1
    pub span: Span,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum ProcKind {
    Initial,
    Always,
    AlwaysFf,
    AlwaysComb,
    AlwaysLatch,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum Sensitivity {
    Star,                 // @(*) / @* (both map here; M5 note)
    List(Vec<EventExpr>), // @(posedge clk or negedge rst or a)
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct EventExpr {
    pub edge: Edge,
    pub expr: Expr,
    pub span: Span,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum Edge {
    Posedge,
    Negedge,
    NoEdge,
}

// ──────────────────────────── Statement [A] ────────────────────────────
// FULL variant set frozen NOW (verdict M7): SchemaHash will eventually hash this
// enum, so adding `Fork`/`Assign`/`Deassign`/`Force`/`Release` later would flip the
// schema. The grammar §2.7 superset is adopted; parsing of all of these is deferred
// to PR2 (PR1 only constructs `Block`/`Error`/`Null` via the recovering stub).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum Stmt {
    Blocking {
        lhs: Lvalue,
        delay: Option<Delay>,
        rhs: Expr,
        span: Span,
    }, // =
    NonBlocking {
        lhs: Lvalue,
        delay: Option<Delay>,
        rhs: Expr,
        span: Span,
    }, // <=
    If {
        cond: Expr,
        then_s: Box<Stmt>,
        else_s: Option<Box<Stmt>>,
        span: Span,
    },
    Case {
        kind: CaseKind,
        scrutinee: Expr,
        items: Vec<CaseItem>,
        span: Span,
    },
    For {
        init: Box<Stmt>,
        cond: Expr,
        step: Box<Stmt>,
        body: Box<Stmt>,
        span: Span,
    },
    While {
        cond: Expr,
        body: Box<Stmt>,
        span: Span,
    },
    Repeat {
        count: Expr,
        body: Box<Stmt>,
        span: Span,
    },
    Forever {
        body: Box<Stmt>,
        span: Span,
    },
    Block {
        label: Option<Ident>,
        decls: Vec<NetVarDecl>,
        stmts: Vec<Stmt>,
        span: Span,
    },
    Fork {
        label: Option<Ident>,
        decls: Vec<NetVarDecl>,
        stmts: Vec<Stmt>,
        join: JoinKind,
        span: Span,
    },
    SysTaskCall {
        name: Ident,
        args: Vec<Expr>,
        span: Span,
    }, // $display(...); name retains `$`
    UserTaskCall {
        name: HierPath,
        args: Vec<Expr>,
        span: Span,
    },
    DelayCtrl {
        delay: Delay,
        body: Option<Box<Stmt>>,
        span: Span,
    }, // #d stmt
    EventCtrl {
        ctrl: Sensitivity,
        body: Option<Box<Stmt>>,
        span: Span,
    }, // @(…) stmt
    EventTrigger {
        name: HierPath,
        span: Span,
    }, // -> ev ;
    Wait {
        cond: Expr,
        body: Option<Box<Stmt>>,
        span: Span,
    },
    Disable {
        target: HierPath,
        span: Span,
    },
    // procedural-continuous family (§2.7):
    Assign {
        lhs: Lvalue,
        rhs: Expr,
        span: Span,
    }, // procedural `assign lv = e;`
    Deassign {
        lhs: Lvalue,
        span: Span,
    },
    Force {
        lhs: Lvalue,
        rhs: Expr,
        span: Span,
    },
    Release {
        lhs: Lvalue,
        span: Span,
    },
    Null(Span), // bare ;
    /// Recovery placeholder for an unparseable / not-yet-implemented statement.
    Error(Span),
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum JoinKind {
    Join,
    JoinAny,
    JoinNone,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum CaseKind {
    Case,
    Casez,
    Casex,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum CaseItem {
    Match {
        labels: Vec<Expr>,
        body: Box<Stmt>,
        span: Span,
    },
    Default {
        body: Box<Stmt>,
        span: Span,
    },
}

// ──────────────────────────── Expr [P] ────────────────────────────
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct Expr {
    pub kind: ExprKind,
    pub span: Span,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum ExprKind {
    // literals: raw lexeme + kind; value parse deferred to elaborate.
    IntLit {
        kind: IntLitKind,
        raw: String,
    },
    RealLit {
        kind: RealLitKind,
        raw: String,
    },
    StrLit {
        raw: String,
    }, // includes quotes; unescape deferred
    // names
    Ident(HierPath), // a, a.b.c
    // operators (precedence table §4 → Pratt binding powers)
    Unary {
        op: UnOp,
        operand: Box<Expr>,
    },
    Binary {
        op: BinOp,
        lhs: Box<Expr>,
        rhs: Box<Expr>,
    },
    Ternary {
        cond: Box<Expr>,
        then_e: Box<Expr>,
        else_e: Box<Expr>,
    },
    // postfix / structural
    BitSelect {
        base: Box<Expr>,
        index: Box<Expr>,
    }, // a[i]
    PartSelect {
        base: Box<Expr>,
        msb: Box<Expr>,
        lsb: Box<Expr>,
    }, // a[m:l]
    IndexedPart {
        base: Box<Expr>,
        offset: Box<Expr>,
        width: Box<Expr>,
        dir: PartDir,
    }, // a[b+:w] (M6: `offset`)
    /// `{a,b,c}` concatenation.
    Concat {
        parts: Vec<Expr>,
    },
    /// `{n{x,y}}` replication. NOTE (verdict M5): `value` holds the repeated
    /// element list DIRECTLY (the concat parts), NOT a wrapper `Concat` node, so
    /// `{n{x}}` ⇒ `Replicate{count:n, value:[x]}`. No `ExprKind::Concat` wrapper.
    Replicate {
        count: Box<Expr>,
        value: Vec<Expr>,
    },
    Call {
        name: HierPath,
        args: Vec<Expr>,
    }, // func(args)
    /// `$time`, `$signed(x)`. NOTE (verdict M6): `name.name` retains the leading
    /// `$` (the lexer's `SystemTask` lexeme includes it), parallel to EscapedIdent.
    SysCall {
        name: Ident,
        args: Vec<Expr>,
    },
    Paren {
        inner: Box<Expr>,
    }, // (e) — span fidelity
    MinTypMax {
        min: Box<Expr>,
        typ: Box<Expr>,
        max: Box<Expr>,
    }, // a:b:c
    /// Recovery placeholder so the Pratt loop can keep folding past an error.
    Error,
}

/// Unary / reduction operators — names mirror sim-ir `UnOp` 1:1 (verified
/// sim-ir/src/lib.rs:97) for a clean lowering name-map.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum UnOp {
    Plus,
    Minus,
    LogNot,
    BitNot,
    RedAnd,
    RedNand,
    RedOr,
    RedNor,
    RedXor,
    RedXnor,
}
/// Binary operators — names mirror sim-ir `BinOp` 1:1 (verified sim-ir/src/lib.rs:112):
/// `AShl`/`AShr` = `<<<`/`>>>`;  `Le`/`Ge`/`Ne`; `CaseEq`/`CaseNe` = `===`/`!==`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum BinOp {
    Add,
    Sub,
    Mul,
    Div,
    Mod,
    Pow,
    Shl,
    Shr,
    AShl,
    AShr,
    Lt,
    Le,
    Gt,
    Ge,
    Eq,
    Ne,
    CaseEq,
    CaseNe,
    BitAnd,
    BitXor,
    BitXnor,
    BitOr,
    LogAnd,
    LogOr,
}
/// Indexed part-select direction. Lowers to sim-ir `SelKind::PartIdxUp/Down`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum PartDir {
    PlusColon,
    MinusColon,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum IntLitKind {
    Decimal,
    Sized,
    UnsizedBased,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum RealLitKind {
    Fixed,
    Exp,
}

// ──────────────────────────── Lvalue [P] ────────────────────────────
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum Lvalue {
    Ident(HierPath),
    BitSelect {
        base: Box<Lvalue>,
        index: Box<Expr>,
        span: Span,
    },
    PartSelect {
        base: Box<Lvalue>,
        msb: Box<Expr>,
        lsb: Box<Expr>,
        span: Span,
    },
    IndexedPart {
        base: Box<Lvalue>,
        offset: Box<Expr>,
        width: Box<Expr>,
        dir: PartDir,
        span: Span,
    },
    Concat {
        parts: Vec<Lvalue>,
        span: Span,
    }, // {cout, sum} = …
    Error(Span),
}
impl Lvalue {
    pub fn span(&self) -> Span {
        match self {
            Lvalue::Ident(h) => h.span,
            Lvalue::BitSelect { span, .. }
            | Lvalue::PartSelect { span, .. }
            | Lvalue::IndexedPart { span, .. }
            | Lvalue::Concat { span, .. }
            | Lvalue::Error(span) => *span,
        }
    }
}

// ──────────────────── ModuleInstance / Generate / TF [A] ────────────────────
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct ModuleInstance {
    pub module_name: Ident,
    pub param_overrides: Vec<ParamConn>, // #(.W(8)) | #(8)
    pub instances: Vec<InstanceItem>,
    pub span: Span,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct InstanceItem {
    pub name: Ident,
    pub unpacked: Vec<Dim>,
    pub conns: PortConnList,
    pub span: Span,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum ParamConn {
    Named {
        name: Ident,
        value: Option<Expr>,
        span: Span,
    },
    Positional(Expr),
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum PortConnList {
    Named(Vec<PortConn>),
    Positional(Vec<Option<Expr>>),
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct PortConn {
    pub name: Ident,
    pub value: Option<Expr>,
    pub span: Span,
} // .a(x) / .a()

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct GenerateConstruct {
    pub items: Vec<GenItem>,
    pub span: Span,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum GenItem {
    For {
        init: GenAssign,
        cond: Expr,
        step: GenAssign,
        label: Option<Ident>,
        body: Vec<GenItem>,
        span: Span,
    },
    If {
        cond: Expr,
        then_b: Vec<GenItem>,
        else_b: Vec<GenItem>,
        label: Option<Ident>,
        span: Span,
    },
    Case {
        scrutinee: Expr,
        items: Vec<GenCaseItem>,
        span: Span,
    },
    Block {
        label: Option<Ident>,
        items: Vec<GenItem>,
        span: Span,
    },
    Item(Box<ModuleItem>),
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct GenAssign {
    pub lvalue: Ident,
    pub value: Expr,
    pub span: Span,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum GenCaseItem {
    Match {
        labels: Vec<Expr>,
        body: Vec<GenItem>,
        span: Span,
    },
    Default {
        body: Vec<GenItem>,
        span: Span,
    },
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct FunctionDef {
    pub automatic: bool,
    pub signed: bool,
    pub range: Option<Range>,
    pub ret_type: ParamType,
    pub name: Ident,
    pub ports: Vec<TfPort>,
    pub body_decls: Vec<NetVarDecl>,
    pub body: Box<Stmt>,
    pub span: Span,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct TaskDef {
    pub automatic: bool,
    pub name: Ident,
    pub ports: Vec<TfPort>,
    pub body_decls: Vec<NetVarDecl>,
    pub body: Box<Stmt>,
    pub span: Span,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct TfPort {
    pub dir: PortDir,
    pub net_or_var: Option<NetVarKind>,
    pub signed: bool,
    pub range: Option<Range>,
    pub name: Ident,
    pub span: Span,
}

// ──────────────────────────── Tests ────────────────────────────
#[cfg(test)]
mod tests {
    use super::*;

    /// Round-trip a Box-recursive `Expr` tree through postcard (proves serde works
    /// on the Box-recursive AST — the primary goal of the dev-dep).
    #[test]
    fn postcard_roundtrip_expr() {
        let span = Span::new(0, 4);
        // Build:  -(a + b)
        let a = Expr {
            kind: ExprKind::Ident(HierPath {
                segments: vec![Ident {
                    name: "a".to_string(),
                    span,
                }],
                span,
            }),
            span,
        };
        let b = Expr {
            kind: ExprKind::Ident(HierPath {
                segments: vec![Ident {
                    name: "b".to_string(),
                    span,
                }],
                span,
            }),
            span,
        };
        let add = Expr {
            kind: ExprKind::Binary {
                op: BinOp::Add,
                lhs: Box::new(a),
                rhs: Box::new(b),
            },
            span,
        };
        let neg = Expr {
            kind: ExprKind::Unary {
                op: UnOp::Minus,
                operand: Box::new(add),
            },
            span,
        };

        let bytes = postcard::to_stdvec(&neg).expect("serialize");
        let decoded: Expr = postcard::from_bytes(&bytes).expect("deserialize");
        assert_eq!(neg, decoded);
    }
}
