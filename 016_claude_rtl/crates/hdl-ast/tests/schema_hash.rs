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
/// Re-pinned 2026-06-19 N7 `return` statement (`Stmt::Return{value: Option<Expr>}`
/// — SV `return [expr];`, used pervasively by class methods; all `.vu` artifacts
/// stale, no sim-ir/format_version change, pure IR-0: lowers to a return-var
/// assign + jump to the body exit block). (Previous re-pins:
/// 2026-06-19 N7 class/OOP skeleton (`TopItem::Class` +
/// `ModuleItem::Class` + `ClassDecl`/`ClassItem` + `NetVarKind::ClassHandle` +
/// `NetVarDecl.class_type: Option<Ident>` + `ExprKind::{ClassNew,Null}` —
/// `class`/`extends`/`virtual`/`new`/`null`; all `.vu` artifacts are stale, no
/// sim-ir/format_version change, pure IR-0: class objects live in the engine
/// `class_heap` with `NetKind::Integer` handle nets + layout/vtable sidecars).
/// (Previous re-pins:
/// 2026-06-19 SVPART 2-state integer types (`NetVarKind::{Bit,Byte,
/// Shortint,Int,Longint}` — `bit`/`byte`/`shortint`/`int`/`longint`; all `.vu`
/// artifacts are stale, no sim-ir/format_version change, pure IR-0: these map to
/// `NetKind::Reg` storage with fixed widths/sign and a 2-state 0-init). (Previous re-pins:
/// 2026-06-19 N5 slice D coverage options (`Coverpoint.at_least`/`weight:
/// Option<Expr>` + `CovergroupDecl.at_least: Option<Expr>` — `option.at_least`/
/// `option.weight`; all `.vu` artifacts are stale, no sim-ir/format_version change,
/// pure IR-0: at_least>1 uses per-bin saturating counters, weight enters the
/// get_coverage weighted average). (Previous re-pins:
/// 2026-06-19 N5 slice C cross coverage (`CovergroupDecl.crosses:
/// Vec<CrossSpec>` + the `CrossSpec` struct — `cross cp_a, cp_b;`; all `.vu`
/// artifacts are stale, no sim-ir/format_version change, pure IR-0: a product
/// hit-bitmap whose bit fires when every constituent coverpoint's bin matches the
/// same sample). (Previous re-pins:
/// 2026-06-19 N5 slice F covergroup sampling event (`CovergroupDecl.clock:
/// Option<Sensitivity>` — `covergroup cg @(posedge clk);` auto-samples each instance;
/// all `.vu` artifacts are stale, no sim-ir/format_version change, pure IR-0: a
/// synthesized `always @(clk) inst.sample();` per clocked instance). (Previous re-pins:
/// 2026-06-19 N5 slice A explicit coverage bins (`Coverpoint.iff:
/// Option<Expr>` + `Coverpoint.bins: Vec<BinSpec>` + the `BinSpec`/`BinKind`/
/// `BinArray`/`CoverRange`/`RangeEnd` types — `coverpoint x [iff(g)] { bins a =
/// {0,[2:4]}; ignore_bins/illegal_bins/default … }`; all `.vu` artifacts are stale,
/// no sim-ir/format_version change, pure IR-0: per-bin membership predicate →
/// counting-bin bits in the existing 64-bit hit-bitmap. `iff` is reserved here
/// (parsed, elaborate loud-rejects) for the guard slice. (Previous re-pins:
/// 2026-06-17 N2d recursive-property + property-level `and`/`or`
/// (`PropExpr` enum + `ConcurrentAssert.prop_expr` / `PropDecl.prop_expr:
/// Option<PropExpr>` — the `and`/`or`/recursion layer above a flat implication;
/// `None` = the byte-identical flat path; all `.vu` artifacts are stale, no
/// sim-ir/format_version change, pure IR-0: `synth_prop_expr` reduces the tree to
/// a per-clock boolean violation check). (Previous re-pins:
/// 2026-06-17 B4 frame-call variable-lifetime override
/// (`NetVarDecl.lifetime: Option<bool>` — `automatic int x;` in a frame
/// function/task body_decl gives that local fresh-per-call storage; all `.vu`
/// artifacts are stale, no sim-ir/format_version change, pure IR-0: the per-slot
/// lifetime rides the engine routing side table out-of-band).
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
/// 2026-06-19 N5 functional coverage (`ModuleItem::{Covergroup,CoverInstance}` plus
/// the `CovergroupDecl`/`Coverpoint`/`CoverInstance` structs — `covergroup … endgroup`
/// and `cg c = new;`; all `.vu` artifacts are stale, no sim-ir/format_version change,
/// pure IR-0 bitmap-synthesis). (Previous re-pins:
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
    202, 131, 177, 121, 231, 139, 246, 234, 184, 79, 144, 194, 109, 66, 141, 97, 98, 189, 56, 185,
    214, 80, 29, 47, 30, 111, 10, 220, 173, 244, 164, 18,
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
