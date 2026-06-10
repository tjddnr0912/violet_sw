//! sim-ir — language-neutral simulation IR.
//!
//! PR1-B defines ONLY the frozen `SuspendState` runtime-state closure
//! (06 process model · shapes FROZEN 2026-06-02). The unspecified types
//! `Process`/`BasicBlock`/`Stmt`/`Expr`/`Sensitivity`/`Terminator` are deferred
//! to M3 — they require the net/expr arena freeze before the *root* hash can lock.
//! `FourState` and `EdgeKind` are scalar leaf enums newly frozen here (the only
//! members of the unspecified set the SuspendState closure transitively touches).
extern crate self as sim_ir;

use serde::{Deserialize, Serialize};
use vita_artifact_derive::SchemaHash;

/// Scalar 4-state logic value (IEEE 1364 §6). NEWLY FROZEN in PR1-B.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum FourState {
    Zero,
    One,
    X,
    Z,
}

/// Edge kind for an edge-sensitive wake condition. NEWLY FROZEN in PR1-B.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum EdgeKind {
    Posedge,
    Negedge,
    AnyEdge,
}

/// [SD1] vvp 1-bit flag bitset; newtype so the schema shape is distinct from a bare u8.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct ProcFlags(pub u8);

/// [SD4] IEEE 1364 4 regions; 17-region split is an intentional Phase-2 flip.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum RegionTag {
    Active,
    Inactive,
    Nba,
    Monitor,
}

/// [SD5] closed 6-variant set of process-suspend conditions.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum WakeCond {
    Edge { net: u32, kind: sim_ir::EdgeKind },
    Level { nets: Vec<u32> },
    WaitTrue { expr: u32 },
    TimeAbs { tick: u64 },
    NamedEvent { ev: u32 },
    Join { join_ref: u32 },
}

/// [SD4] region stored explicitly (never re-derived → keeps logic out of the hash).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct WakeKey {
    pub cond: sim_ir::WakeCond,
    pub region: sim_ir::RegionTag,
    pub tie_break: u32,
}

/// [SD2] integer-indexed call frame (not a native call stack).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct Frame {
    pub return_pc: u32,
    pub callee_entry: u32,
    pub locals_base: u32,
    pub locals_len: u32,
    pub is_automatic: bool,
}

/// [SD1] vvp two-set fork/join port.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct JoinState {
    pub parent: Option<u32>,
    pub children: Vec<u32>,
    pub detached: Vec<u32>,
    pub flags: sim_ir::ProcFlags,
}

/// [resume/reserved] RULE D2 atomic-freeze unit (16 §1) — PR1-B golden root.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct SuspendState {
    pub resume_pc: u32,
    pub locals: Vec<sim_ir::FourState>,
    pub join_state: sim_ir::JoinState,
    pub wake_key: sim_ir::WakeKey,
    pub call_stack: Vec<sim_ir::Frame>,
    pub frame_arena: Vec<sim_ir::FourState>,
}

// ── M3 backbone ──────────────────────────────────────────────────────────────

/// Unary operator (§1).
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

/// Binary operator (§1).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum BinOp {
    Add,
    Sub,
    Mul,
    Div,
    Mod,
    Pow,
    BitAnd,
    BitOr,
    BitXor,
    BitXnor,
    LogAnd,
    LogOr,
    Lt,
    Le,
    Gt,
    Ge,
    Eq,
    Ne,
    CaseEq,
    CaseNe,
    Shl,
    Shr,
    AShl,
    AShr,
}

/// Bit/part-select kind (§1).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum SelKind {
    Bit,
    PartConst,
    PartIdxUp,
    PartIdxDown,
}

/// System-function id (§1).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum SysFuncId {
    Time,
    Realtime,
    Signed,
    Unsigned,
    Clog2,
    Rtoi,       // $rtoi  — real → int, TRUNCATE toward zero
    Itor,       // $itor  — int  → real, exact convert
    RealToBits, // $realtobits — real → 64-bit vector (raw IEEE bits)
    BitsToReal, // $bitstoreal — 64-bit vector → real (raw IEEE bits)
}

/// Expression arena node (§1).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum Expr {
    Const {
        val: u32,
    },
    Signal {
        net: u32,
        word: Option<u32>,
    },
    Select {
        base: u32,
        offset: u32,
        width: u32,
        kind: sim_ir::SelKind,
    },
    Concat {
        parts: Vec<u32>,
    },
    Replicate {
        count: u32,
        value: u32,
    },
    Unary {
        op: sim_ir::UnOp,
        operand: u32,
    },
    Binary {
        op: sim_ir::BinOp,
        lhs: u32,
        rhs: u32,
    },
    Ternary {
        cond: u32,
        then_e: u32,
        else_e: u32,
    },
    SysFunc {
        which: sim_ir::SysFuncId,
        args: Vec<u32>,
    },
    Call {
        func: u32,
        args: Vec<u32>,
    },
}

/// System-task id (§2).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum SysTaskId {
    Display,
    Write,
    Monitor,
    Strobe,
    Finish,
    Stop,
    DumpFile,
    DumpVars,
    DumpOn,
    DumpOff,
    DumpAll,
    /// `$dumpflush` — flush the VCD sink now (format_version 4).
    DumpFlush,
    /// `$dumplimit(bytes)` — byte budget; on exceeding it the writer emits a
    /// one-time `$comment Dump limit reached $end` and drops further records
    /// (format_version 4).
    DumpLimit,
}

/// Disable kind (§2).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum DisableKind {
    Fork,
    Scope,
}

/// Statement arena node (§2).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum Stmt {
    BlockingAssign {
        lhs: sim_ir::Lvalue,
        rhs: u32,
    },
    NonblockingAssign {
        lhs: sim_ir::Lvalue,
        rhs: u32,
    },
    SysTask {
        which: sim_ir::SysTaskId,
        fmt: Option<u32>,
        args: Vec<u32>,
    },
    Disable {
        scope_kind: sim_ir::DisableKind,
        target: u32,
    },
    /// `force lhs = rhs` (shape reserved at format_version 4; elaborate still
    /// loud-rejects until the force/release semantics increment lands — the
    /// engine treats it as a defensive no-op meanwhile).
    Force {
        lhs: sim_ir::Lvalue,
        rhs: u32,
    },
    /// `release lhs` (shape reserved at format_version 4 — see `Force`).
    Release {
        lhs: sim_ir::Lvalue,
    },
}

/// Assignment target (§3).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct Lvalue {
    pub chunks: Vec<sim_ir::LvalChunk>,
}

/// One chunk of an lvalue (§3).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct LvalChunk {
    pub net: u32,
    pub word: Option<u32>,
    pub offset: Option<u32>,
    pub width: Option<u32>,
    pub kind: sim_ir::SelKind,
}

/// Delay scheduling region (§4).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum DelayRegion {
    Active,
    Inactive,
}

/// In-body wait cause (§4).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum WaitCause {
    Edge { net: u32, kind: sim_ir::EdgeKind },
    Level { nets: Vec<u32> },
    Expr { expr: u32 },
    Named { ev: u32 },
}

/// Basic-block terminator (§4, RULE-D2 Fork/Call verbatim).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum Terminator {
    Goto {
        target: u32,
    },
    Branch {
        cond: u32,
        then_bb: u32,
        else_bb: u32,
    },
    Delay {
        /// ExprId of the delay VALUE in the process's module TIME UNITS — raw
        /// and unscaled (format_version 4; was a pre-scaled literal tick count
        /// in v3). The engine evaluates it AT SUSPENSION TIME and converts:
        /// real → round(v × M), integral → v × M (u64-saturating), any X/Z
        /// → 0 ticks (iverilog parity), where M is the per-process timescale
        /// multiplier. A const `#5`/`#2.5` simply folds to a Const expr.
        amount: u32,
        region: sim_ir::DelayRegion,
        resume: u32,
    },
    Wait {
        cond: sim_ir::WaitCause,
        resume: u32,
    },
    Fork {
        children: Vec<u32>,
        join: u32,
        resume_bb: u32,
    },
    Call {
        target: u32,
        ret_bb: u32,
    },
    Return,
}

/// Sensitivity kind (§6).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum SensKind {
    Initial,
    Comb,
    Latch,
    Edge,
    Level,
}

/// One edge entry in a sensitivity list (§6).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct EdgeTerm {
    pub net: u32,
    pub kind: sim_ir::EdgeKind,
}

/// Process sensitivity (§6).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct Sensitivity {
    pub kind: sim_ir::SensKind,
    pub edges: Vec<sim_ir::EdgeTerm>,
}

/// Net/variable kind (§6).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum NetKind {
    Wire,
    Reg,
    Logic,
    Integer,
    /// IEEE-754 f64 net (`real`/`realtime`). 64-bit, signed, 2-state. The f64 is
    /// stored as `f64::to_bits()` in `init.val[0]`, `init.unk` all-zero. No f64
    /// field is introduced — the V-PRIM derive guard sees only `u64` inside
    /// `BitPacked`. `realtime` is a synonym and ALSO maps here (no 6th variant).
    Real,
}

/// Port direction (§6).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum PortDir {
    Input,
    Output,
    Inout,
    Internal,
}

/// 2-plane 4-state bit vector (§6).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct BitPacked {
    pub val: Vec<u64>,
    pub unk: Vec<u64>,
}

/// Net/variable arena entry (§6).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct NetVar {
    pub kind: sim_ir::NetKind,
    pub width: u32,
    pub msb: u32,
    pub lsb: u32,
    pub signed: bool,
    pub array_len: u32,
    pub dir: sim_ir::PortDir,
    pub init: sim_ir::BitPacked,
}

/// Constant representation tag (§6).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub enum ConstRepr {
    Numeric,
    StrUtf8,
    /// IEEE-754 f64 literal. `ConstVal.width = 64`, `signed = true`,
    /// `bits.val[0] = literal.to_bits()`, `bits.unk = [0]`. No f64 field.
    Real,
}

/// Constant pool entry (§6).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct ConstVal {
    pub width: u32,
    pub signed: bool,
    pub repr: sim_ir::ConstRepr,
    pub bits: sim_ir::BitPacked,
}

/// Control-flow basic block (§7).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct BasicBlock {
    pub stmts: Vec<u32>,
    pub term: sim_ir::Terminator,
}

/// Process (§7).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct Process {
    pub sensitivity: sim_ir::Sensitivity,
    pub body: Vec<sim_ir::BasicBlock>,
    pub entry: u32,
    pub suspend: sim_ir::SuspendState,
}

/// Continuous assignment (§7).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct ContAssign {
    pub lhs: sim_ir::Lvalue,
    pub rhs: u32,
    pub delay: Option<u32>,
}

/// Module instance (§7).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct Instance {
    pub parent: Option<u32>,
    pub module: u32,
    pub first_net: u32,
    pub net_count: u32,
}

/// Function/task definition (§7).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct FuncDef {
    pub entry: u32,
    pub n_params: u32,
    pub locals_len: u32,
    pub is_task: bool,
}

/// Golden root — `schema_hash::<sim_ir::SimIr>()` is the pinned gate (§7).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, SchemaHash)]
pub struct SimIr {
    pub instances: Vec<sim_ir::Instance>,
    pub nets: Vec<sim_ir::NetVar>,
    pub processes: Vec<sim_ir::Process>,
    pub cont_assigns: Vec<sim_ir::ContAssign>,
    pub funcs: Vec<sim_ir::FuncDef>,
    pub exprs: Vec<sim_ir::Expr>,
    pub stmts: Vec<sim_ir::Stmt>,
    pub blocks: Vec<sim_ir::BasicBlock>,
    pub consts: Vec<sim_ir::ConstVal>,
}
