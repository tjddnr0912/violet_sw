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
/// Re-pinned 2026-06-12 v7 (the P2-C/P2-D AST flip: `TopItem::{Package,
/// Import}` + `ImportDecl` + `ModuleItem::Import` + `ExprKind::PkgScoped` +
/// `NetVarKind::String`; all `.vu` artifacts are stale). (Previous re-pins:
/// 2026-06-11 v6 `AssocKey::Str`; 2026-06-11 v5 ⑥ front-end batch
/// `Dim::{Dyn,Queue,Assoc}`+`ExprKind::{New,Dollar}`+interfaces;
/// 2026-06-11 `NetVarKind::Event`; 2026-06-05 `TypedefKind::Struct`.)
const EXPECTED: [u8; 32] = [
    199, 112, 99, 183, 63, 36, 179, 47, 138, 44, 202, 165, 236, 51, 115, 161, 40, 80, 109, 114,
    217, 41, 65, 145, 143, 212, 97, 214, 137, 123, 35, 62,
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
