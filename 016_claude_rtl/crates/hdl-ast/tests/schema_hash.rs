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
/// Re-pinned 2026-06-16 multi-clock slice A3 (`ConcurrentAssert.consequent_clock:
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
    2, 220, 161, 237, 45, 66, 116, 112, 6, 123, 70, 194, 137, 95, 192, 236, 148, 153, 77, 154, 74,
    215, 238, 147, 90, 218, 235, 125, 225, 42, 135, 134,
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
