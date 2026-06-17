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
    /// `interface name; … endinterface` (v5 ⑥). The body SHAPE reuses
    /// `ModuleDecl` (params/signals/cont-assigns/procs come for free);
    /// elaborate keeps interfaces in their own map and flattens an instance
    /// into plain nets + symbol aliases (spike 2026-06-10: no new IR).
    Interface(ModuleDecl),
    /// `package name; … endpackage` (v7 P2-D). Body shape reuses
    /// `ModuleDecl` like interfaces (params/typedefs/funcs/tasks); elaborate
    /// flattens imported symbols by name — no IR.
    Package(ModuleDecl),
    /// Compilation-unit-scope `import pkg::*;` / `import pkg::sym;` (v7) —
    /// one item per comma-separated term.
    Import(ImportDecl),
    /// Recovery placeholder for an unparseable top-level construct.
    Error(Span),
}

/// One `import` term (v7 P2-D): `pkg::*` (`item: None`) or `pkg::sym`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct ImportDecl {
    pub pkg: Ident,
    pub item: Option<Ident>,
    pub span: Span,
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
    pub range: Option<Range>, // packed [msb:lsb] (the FIRST/outer packed dim)
    pub packed: Vec<Range>,   // ADDITIONAL packed dims: `[3:0][7:0]` ⇒ range=[3:0], packed=[[7:0]]
    pub name: Ident,
    pub default: Option<Expr>, // ANSI default value slot (rare)
    /// Interface-typed port `intf p` / `intf.mp p` (v5 ⑥). When set, `dir`
    /// is a placeholder (interface ports carry no direction) and elaborate
    /// binds the port by SYMBOL ALIASING instead of cont-assign wiring.
    pub iface: Option<IfaceRef>,
    pub span: Span,
}

/// The interface type of an ANSI port: `intf` or `intf.modport`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct IfaceRef {
    pub iface: Ident,
    pub modport: Option<Ident>,
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
    Typedef(TypedefDecl),        // SV `typedef enum/struct/<type> name;` (Phase-2)
    Import(ImportDecl),          // v7 P2-D module-scope `import pkg::…;`
    /// `modport mp (input a, output b);` (v5 ⑥ — parsed and ACCEPTED; the
    /// per-member direction checks are a follow-on increment).
    Modport(ModportDecl),
    /// Named SVA `sequence NAME; …; endsequence` (Phase-3 named-SVA slice). Inlined
    /// at use sites by elaborate; pure IR-0.
    SequenceDecl(SeqDecl),
    /// Named SVA `property NAME; …; endproperty` (Phase-3 named-SVA slice). Spliced
    /// at `assert property(NAME)` by elaborate; pure IR-0.
    PropertyDecl(PropDecl),
    /// Recovery placeholder for an unparseable item.
    Error(Span),
}

/// An interface modport: a named direction view over interface members.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct ModportDecl {
    pub name: Ident,
    /// `(dir, member)` pairs in source order; the direction is sticky across
    /// commas (`input a, b` ⇒ both inputs).
    pub ports: Vec<(PortDir, Ident)>,
    pub span: Span,
}

/// `typedef <kind> name;` (SV user-defined type, Phase-2).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct TypedefDecl {
    pub name: Ident,
    pub kind: TypedefKind,
    pub span: Span,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum TypedefKind {
    /// `typedef enum [base] { RED, GREEN=5, … } color_t;` — labels become module
    /// constants; the type is the (default int) base. `base` is the optional packed
    /// base range (`enum logic [1:0] {…}`).
    Enum {
        base: Option<Range>,
        labels: Vec<EnumLabel>,
    },
    /// `typedef logic [7:0] byte_t;` — a plain type alias. The parser resolves
    /// `byte_t x;` to this underlying net/var type directly; elaborate is a no-op.
    Alias {
        kind: NetVarKind,
        signed: bool,
        range: Option<Range>,
        packed: Vec<Range>,
    },
    /// `typedef struct packed { logic [7:0] a; logic [3:0] b; } pkt_t;` — a packed
    /// struct. The parser lays members MSB-first into one flat `logic` vector and
    /// desugars `s.a` to a constant part-select; elaborate is a no-op.
    Struct { members: Vec<StructMember> },
}

/// One enum label: `RED` or `GREEN = 5`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct EnumLabel {
    pub name: Ident,
    pub value: Option<Expr>,
}

/// One packed-struct member: `logic [7:0] a;`. v1 members are scalar/vector
/// net/var types with a constant-literal range (no nested struct / param width).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct StructMember {
    pub name: Ident,
    pub kind: NetVarKind,
    pub signed: bool,
    pub range: Option<Range>,
    pub span: Span,
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
    pub range: Option<Range>, // packed/vector [msb:lsb] (the FIRST/outer packed dim)
    pub packed: Vec<Range>,   // ADDITIONAL packed dims: `logic [3:0][7:0]` ⇒ packed=[[7:0]]
    pub names: Vec<DeclName>, // one decl, possibly many names
    /// B4: per-declaration lifetime OVERRIDE (`automatic int x;` / `static int y;`).
    /// `Some(true)` = automatic, `Some(false)` = static, `None` = follow the
    /// enclosing function/task default. Honored only on a frame function/task
    /// body_decl (IEEE §6.21; iverilog rejects the override outright).
    pub lifetime: Option<bool>,
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
    /// `[]` — dynamic array (v5 ⑥).
    Dyn,
    /// `[$]` queue; `[$:N]` bounded queue (bound PARSED, elaborate loud-rejects
    /// it — bounded queues are outside the MVP).
    Queue(Option<Expr>),
    /// `[integer]` / `[time]` / `[string]` — associative array key type
    /// (integral keys live in the engine's signed-i64 domain; string keys in
    /// the byte-string domain, v6).
    Assoc(AssocKey),
}

/// Assoc-array key type.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum AssocKey {
    Integer, // 32-bit signed
    Time,    // 64-bit unsigned
    /// `[string]` (v6) — byte-string keys (contextual keyword: `string` stays
    /// a plain identifier everywhere else).
    Str,
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
    /// `event e;` (v5 batch B — elaborate desugars it to a 64-bit counter reg).
    Event,
    /// SV `string` variable (v7 P2-C — heap-handle storage, dyn precedent).
    String,
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
    /// `final` (P2-E): a zero-time one-shot at end of simulation (IEEE
    /// §9.2.3 — timing controls inside are illegal, loud at elaborate).
    Final,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum Sensitivity {
    Star,                 // @(*) / @* (both map here; M5 note)
    List(Vec<EventExpr>), // @(posedge clk or negedge rst or a)
}
/// Intra-assignment EVENT control after `=`/`<=` (IEEE 1800 §9.4.5): `@(event)` or
/// `repeat(n) @(event)`. The RHS (and any LHS index) is captured at the statement,
/// then the value is written after the event occurs (`repeat` times when present).
/// On `Stmt::Blocking` the process BLOCKS until the write; on `Stmt::NonBlocking`
/// (slice N1) it does NOT block — a detached helper performs the NBA write later.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct IntraEvent {
    /// `repeat(n)` count; `None` is a plain `@(event)` (one occurrence).
    pub repeat: Option<Expr>,
    pub ctrl: Sensitivity,
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
        /// Intra-assignment event control `= @(ev) rhs` / `= repeat(n) @(ev) rhs`
        /// (mutually exclusive with `delay`). `None` for a plain `=`.
        event: Option<IntraEvent>,
        rhs: Expr,
        span: Span,
    }, // =
    NonBlocking {
        lhs: Lvalue,
        delay: Option<Delay>,
        /// Intra-assignment event control `<= @(ev) rhs` / `<= repeat(n) @(ev) rhs`
        /// (mutually exclusive with `delay`). `None` for a plain `<=`. (Slice N1.)
        event: Option<IntraEvent>,
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
    /// `wait fork;` (IEEE §9.6.1) — block until all child processes forked by
    /// the current process complete. v8 AST flip; parser/elaborate wired in the
    /// wait-fork feature slice (the bump leaves it shape-only).
    WaitFork {
        span: Span,
    },
    /// Concurrent assertion subset (SVA, Phase-3): `assert property(@(clk) a
    /// |-> b)` / `|=>`. The antecedent is a `Sequence` (slice S4 added bounded
    /// `##n` cycle-delay + `[*n]` consecutive repetition; a flat boolean is
    /// `Sequence::Boolean`); the consequent stays a flat boolean `Expr`. The
    /// parser/elaborate desugar (shift-register pipeline + clocked `$error`)
    /// lands in the SVA feature slices.
    ConcurrentAssert {
        clock: Sensitivity,
        /// Optional `disable iff (expr)` reset (slice S12, IEEE 1800 §16.12.7):
        /// when the (clock-sampled) condition is true the attempt is aborted (no
        /// pass/fail) and in-flight pipeline/pending state is cleared.
        disable_iff: Option<Expr>,
        antecedent: Sequence,
        implication_kind: ImplicationKind,
        /// The consequent. Slice S14 generalized this from a flat boolean `Expr`
        /// to a `Sequence` (`a |-> b ##1 c`); a plain boolean consequent is
        /// `Sequence::Boolean(_)` and keeps the byte-identical lowering.
        consequent: Sequence,
        /// Optional CONSEQUENT clocking event (slice A3, multi-clock): the leading
        /// `@(c2)` of `@(c1) ante |=> @(c2) cons`. `None` = single-clock (the byte-
        /// identical lowering). `Some(c2)` selects the two-process handoff synthesis
        /// (a c1-clocked sampler + a c2-clocked consumer); only valid with `|=>`.
        consequent_clock: Option<Sensitivity>,
        /// Optional action block (slice S11, IEEE 1800 §16.14.1):
        /// `assert property(...) [pass] [else fail]`. `pass` runs on a
        /// non-vacuous success, `fail` (the `else` statement) replaces the
        /// default `$error` on a violation. A bare `assert property(...);` leaves
        /// both `None` (default $error, no pass action).
        pass: Option<Box<Stmt>>,
        fail: Option<Box<Stmt>>,
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
    /// Deferred immediate assertion (IEEE 1800-2017 §16.4): `assert #0 (c)` is
    /// the Observed-deferred form, `assert final (c)` the Reactive-deferred form.
    /// Unlike a plain immediate `assert` (which stays `Stmt::If`), the condition
    /// is sampled WHEN REACHED but the pass/fail action MATURES in a later
    /// scheduling region with flush-on-re-reach (§4.4). The desugar mirrors `If`:
    /// `then_s` is the pass action (`Null` when none), `else_s` the fail action
    /// (the synthesized `$error("Assertion failed")` when there is no `else`).
    DeferredAssert {
        region: AssertDefer,
        cond: Expr,
        then_s: Box<Stmt>,
        else_s: Box<Stmt>,
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
/// Maturation region of a deferred immediate assertion (IEEE 1800 §16.4 / §4.4).
/// `assert #0` → Observed, `assert final` → Reactive. The plain immediate
/// `assert` carries no `AssertDefer` (it stays `Stmt::If`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum AssertDefer {
    /// `assert #0` — matures in the Observed region.
    Observed,
    /// `assert final` — matures in the Reactive region.
    Reactive,
}
/// SVA implication operator (Phase-3 subset). `|->` checks the consequent in the
/// SAME clock tick as the antecedent match (overlapping); `|=>` checks it on the
/// NEXT tick (non-overlapping).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum ImplicationKind {
    /// `|->` overlapping — consequent evaluated in the same tick.
    Overlap,
    /// `|=>` non-overlapping — consequent evaluated on the next clock tick.
    NonOverlap,
}
/// SVA sequence (Phase-3 subset, slice S4). A sequence describes a multi-clock
/// match pattern in a concurrent assertion's antecedent. Slice S4 supports only
/// bounded compile-time-constant forms (`min == max`); ranges (`##[m:n]`,
/// `[*m:n]`), unbounded (`[*0:$]`), goto/nonconsecutive (`[->n]`/`[=n]`),
/// `throughout`/`within` and multi-clock are deferred (loud parse errors). The
/// elaborate desugar lowers a `Sequence` to a synthesized shift-register pipeline
/// of 1-bit pending registers inside the clocked checker — pure IR-0, no sim-ir
/// change.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum Sequence {
    /// A boolean leaf term. A flat property antecedent (`a |-> b`) is
    /// `Boolean(a)`.
    Boolean(Expr),
    /// `lhs ##min rhs` cycle-delay concatenation. Slice S4 emits only
    /// `min == max` (a constant delay; `max` is `Some(min)`); `##0` is
    /// same-cycle fusion, `##1` next cycle. The range form keeps `max` for
    /// forward compatibility but the parser rejects `min != max` (deferred).
    Delay {
        min: u32,
        max: Option<u32>,
        lhs: Box<Sequence>,
        rhs: Box<Sequence>,
    },
    /// Repetition. `Consec` (`[*n]`/`[*m:n]`, slices S4/S5) is consecutive;
    /// `Goto` (`[->n]`, slice S8) ends ON the n-th (gap-allowed) occurrence;
    /// `Nonconsec` (`[=n]`, slice S8) allows the match to extend past the n-th.
    /// Goto/Nonconsec require a boolean `seq` operand and a single count
    /// (`min == max`); their ranges are deferred (loud).
    Repeat {
        seq: Box<Sequence>,
        min: u32,
        max: Option<u32>,
        kind: RepeatKind,
    },
    /// `cond throughout seq` (slice S7) — the boolean `cond` must hold at every
    /// clock of `seq`'s match window. Lowered by ANDing `cond` into the seed and
    /// every shift stage of the synthesized pipeline (bounded inner only).
    Throughout { cond: Box<Expr>, seq: Box<Sequence> },
    /// `seq1 within seq2` (slice S9) — `seq1` must match entirely inside a match
    /// of `seq2`. Lowered (bounded both) to `match(seq2) & OR over the seq2
    /// window of registered `match(seq1)`. Top-level antecedent only.
    Within {
        seq1: Box<Sequence>,
        seq2: Box<Sequence>,
    },
    /// A NAMED property/sequence instance: `assert property(NAME)` (a property
    /// instance) or a future parameterized reference. The parser emits this ONLY
    /// at the property-instance position (a bare `NAME` inside a sequence body
    /// still parses as `Boolean(Ident)` and is resolved against the sequence
    /// table at elaborate). `args` is reserved for the formal-arguments follow-on
    /// (the current subset rejects a non-empty list loud); carrying the field now
    /// means that slice adds NO further `.vu` AST-hash re-pin. Elaborate inlines
    /// the named declaration's body, so this is pure IR-0 (no sim-ir change).
    Instance {
        name: Ident,
        args: Vec<Expr>,
        span: Span,
    },
}

/// A named SVA sequence declaration: `sequence NAME [(formals)]; <seq>; endsequence`
/// (IEEE 1800 §16.8). Stored at elaborate and INLINED at each use site (reusing the
/// existing sequence desugar). `formals` is reserved for the parameterized follow-on
/// (the current subset rejects a non-empty list loud).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct SeqDecl {
    pub name: Ident,
    pub formals: Vec<Ident>,
    pub body: Sequence,
    pub span: Span,
}

/// A named SVA property declaration: `property NAME [(formals)]; <property_spec>;
/// endproperty` (IEEE 1800 §16.12). The body mirrors a `Stmt::ConcurrentAssert`'s
/// property spec (clock + optional `disable iff` + `antecedent impl consequent`); a
/// `assert property(NAME)` instance splices these fields at elaborate. `formals`
/// reserved (see [`SeqDecl`]).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct PropDecl {
    pub name: Ident,
    pub formals: Vec<Ident>,
    pub clock: Sensitivity,
    pub disable_iff: Option<Expr>,
    pub antecedent: Sequence,
    pub implication_kind: ImplicationKind,
    pub consequent: Sequence,
    /// Optional consequent clocking event (slice A3, multi-clock) — see
    /// [`Stmt::ConcurrentAssert`]'s `consequent_clock`. `None` = single-clock.
    pub consequent_clock: Option<Sensitivity>,
    pub span: Span,
}
/// SVA repetition operator (slices S4/S5/S8).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum RepeatKind {
    /// `[*n]` / `[*m:n]` — consecutive.
    Consec,
    /// `[->n]` — goto: the n-th (gap-allowed) occurrence, ending on it.
    Goto,
    /// `[=n]` — nonconsecutive: n occurrences, match may extend past the n-th.
    Nonconsec,
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
    /// `pkg::name` package-scoped value reference (v7 P2-D).
    PkgScoped {
        pkg: Ident,
        name: Ident,
    },
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
    /// `new[n]` / `new[n](src)` — dynamic-array allocation (v5 ⑥). Parsed
    /// CONTEXTUALLY (the ident `new` immediately followed by `[`); elaborate
    /// falls back to an ordinary array read when a net named `new` is in
    /// scope, preserving V2005 programs that use `new` as an identifier.
    New {
        size: Box<Expr>,
        src: Option<Box<Expr>>,
    },
    /// Bare `$` — the queue last-index (`q[$]`, `q[$-1]`). Only meaningful
    /// inside a queue element select; elaborate substitutes `size()-1` there
    /// and loud-rejects it anywhere else.
    Dollar,
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
