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
/// Re-pinned 2026-06-15 SVA slice S7 (`Sequence::Throughout` variant —
/// `cond throughout seq` AST flip; all `.vu` artifacts are stale, no
/// sim-ir/format_version change). (Previous re-pins: 2026-06-15 S4 `Sequence`
/// enum + `ConcurrentAssert.antecedent: Expr → Sequence`;
/// 2026-06-14 v8 `Stmt::WaitFork`+`ConcurrentAssert`+`ImplicationKind`;
/// 2026-06-12 P2-E `ProcKind::Final`; 2026-06-12 v7 P2-C/P2-D flip
/// `TopItem::{Package,Import}`+`ImportDecl`+`ModuleItem::Import`+
/// `ExprKind::PkgScoped`+`NetVarKind::String`; 2026-06-11 v6 `AssocKey::Str`;
/// 2026-06-11 v5 ⑥ front-end batch; 2026-06-11 `NetVarKind::Event`;
/// 2026-06-05 `TypedefKind::Struct`.)
const EXPECTED: [u8; 32] = [
    194, 125, 167, 97, 124, 98, 235, 194, 179, 254, 100, 110, 26, 122, 71, 237, 93, 119, 223, 155,
    23, 162, 20, 223, 105, 178, 165, 94, 22, 209, 8, 158,
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
