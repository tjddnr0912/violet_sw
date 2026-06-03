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
