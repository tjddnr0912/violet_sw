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
/// Re-pinned 2026-06-11 (v5 ⑥ front-end batch — ONE flip for the whole
/// increment): `Dim::{Dyn, Queue, Assoc}` + `AssocKey` + `ExprKind::{New,
/// Dollar}` (dyn storage) and `TopItem::Interface` + `ModuleItem::Modport` +
/// `ModportDecl` + `AnsiPort.iface`/`IfaceRef` (interfaces) — all `.vu`
/// artifacts are stale. (Previous re-pins: 2026-06-11 `NetVarKind::Event`;
/// 2026-06-05 `TypedefKind::Struct` + `StructMember`.)
const EXPECTED: [u8; 32] = [
    153, 57, 249, 68, 49, 29, 28, 187, 152, 123, 186, 88, 206, 159, 218, 211, 248, 148, 0, 24, 44,
    177, 75, 109, 164, 8, 240, 215, 124, 199, 77, 26,
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
