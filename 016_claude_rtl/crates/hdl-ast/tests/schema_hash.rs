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
const EXPECTED: [u8; 32] = [
    9, 20, 170, 115, 160, 193, 247, 140, 163, 198, 231, 190, 198, 203, 201, 4, 86, 55, 169, 79, 31,
    209, 46, 7, 175, 54, 220, 15, 3, 35, 19, 90,
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
