//! Golden SchemaHash gate for the hdl-ast `.vu` root (`SourceUnit`).
//!
//! The hash collapses the whole AST type-reachability closure into one blake3
//! value. Box-recursive `Expr` is handled by the derive's transparent `Box<T>`
//! arm + the registry's `insert_once` cycle guard, so the recursive AST hashes
//! without infinite recursion. Any field add/remove/reorder anywhere in the
//! reachable AST flips this hash, signalling that every `.vu` artifact is stale.
//!
//! When this fails after a DELIBERATE AST shape change, re-pin `EXPECTED` to the
//! new value (and bump the `.vu` format_version when the staged flow lands).

use vita_schema::schema_hash;

/// Pinned root hash of `hdl_ast::SourceUnit`'s full type closure.
/// Re-pinned 2026-06-17 B4 frame-call variable-lifetime override
/// (`NetVarDecl.lifetime: Option<bool>` — `automatic int x;` in a frame
/// function/task body_decl gives that local fresh-per-call storage; all `.vu`
/// artifacts are stale, no sim-ir/format_version change, pure IR-0: the per-slot
/// lifetime rides the engine routing side table out-of-band). (Previous re-pins:
/// 2026-06-17 N2a-1 multi-clock SVA sequence boundary
/// (`Sequence::Clocked { clock, seq }` — a `##`-boundary re-clocking event
/// `a ##1 @(c2) b`; all `.vu` artifacts are stale, no sim-ir/format_version change,
/// pure IR-0: a dedicated cross-clock two-process handoff synthesis). (Previous re-pins:
/// 2026-06-17 N1 non-blocking intra-assignment event control
/// (`Stmt::NonBlocking.event: Option<IntraEvent>` — `lhs <= [repeat(n)] @(ev) rhs`;
/// all `.vu` artifacts are stale, no sim-ir/format_version change, pure IR-0:
/// capture-now / `fork … join_none` / NBA-write desugar).
/// 2026-06-17 B4 per-variable lifetime override (`NetVarDecl.lifetime:
/// Option<bool>` — block-/variable-level `automatic` for frame functions/tasks);
/// 2026-06-16 deferred immediate assertions (`Stmt::DeferredAssert` +
/// `AssertDefer` enum — `assert #0` (Observed) / `assert final` (Reactive); all
/// `.vu` artifacts are stale, no sim-ir/format_version change, pure IR-0: a
/// flush-marker + region maturation queues carried out-of-band).
/// 2026-06-16 intra-assignment event control (`Stmt::Blocking.event:
/// Option<IntraEvent>` + new `IntraEvent` struct — `lhs = [repeat(n)] @(ev) rhs`;
/// all `.vu` artifacts are stale, no sim-ir/format_version change, pure IR-0
/// capture/wait/write desugar). (Previous re-pins:
/// 2026-06-16 multi-clock slice A3 (`ConcurrentAssert.consequent_clock:
/// Option<Sensitivity>` + `PropDecl.consequent_clock` — the `@(c2)` consequent clock
/// of `@(c1) ante |=> @(c2) cons`; all `.vu` artifacts are stale, no
/// sim-ir/format_version change, pure IR-0). (Previous re-pins:
/// 2026-06-16 named-SVA slice (`Sequence::Instance` +
/// `ModuleItem::{SequenceDecl,PropertyDecl}` + `SeqDecl`/`PropDecl` — named
/// `sequence`/`property` declarations & instantiation);
/// 2026-06-15 SVA slice S14 (`ConcurrentAssert.consequent: Expr →
/// Sequence` — sequence consequent AST flip; all `.vu` artifacts are stale, no
/// sim-ir/format_version change); 2026-06-15 S12
/// `ConcurrentAssert.disable_iff: Option<Expr>`; 2026-06-15 S11
/// `ConcurrentAssert.{pass,fail}: Option<Box<Stmt>>`; 2026-06-15 S9
/// `Sequence::Within`; 2026-06-15 S8 `Sequence::Repeat.kind: RepeatKind`;
/// 2026-06-15 S7 `Sequence::Throughout`; 2026-06-15 S4 `Sequence` enum +
/// `ConcurrentAssert.antecedent: Expr → Sequence`;
/// 2026-06-14 v8 `Stmt::WaitFork`+`ConcurrentAssert`+`ImplicationKind`;
/// 2026-06-12 P2-E `ProcKind::Final`; 2026-06-12 v7 P2-C/P2-D flip
/// `TopItem::{Package,Import}`+`ImportDecl`+`ModuleItem::Import`+
/// `ExprKind::PkgScoped`+`NetVarKind::String`; 2026-06-11 v6 `AssocKey::Str`;
/// 2026-06-11 v5 ⑥ front-end batch; 2026-06-11 `NetVarKind::Event`;
/// 2026-06-05 `TypedefKind::Struct`.)
const EXPECTED: [u8; 32] = [
    203, 117, 139, 101, 210, 67, 173, 11, 15, 140, 77, 26, 120, 248, 19, 165, 55, 38, 41, 154, 133,
    29, 60, 180, 125, 87, 14, 27, 0, 124, 197, 137,
];

#[test]
fn schema_hash_is_pinned() {
    assert_eq!(
        schema_hash::<hdl_ast::SourceUnit>(),
        EXPECTED,
        "hdl-ast SourceUnit schema shape changed — re-pin EXPECTED and treat all \
         existing .vu artifacts as stale"
    );
}

#[test]
fn schema_hash_is_deterministic() {
    // Same input → identical hash within a process (the registry DFS is
    // order-stable; the recursive Box<Expr> closure terminates via insert_once).
    assert_eq!(
        schema_hash::<hdl_ast::SourceUnit>(),
        schema_hash::<hdl_ast::SourceUnit>()
    );
}
