//! [C4-lite] Native expression evaluator — a VM-only fast path that compiles a
//! `sim_ir::Expr` tree into a flat post-order register program and evaluates it
//! WITHOUT building a `Value` per node, removing the recursive `eval_ctx` dispatch
//! and per-operator `Value` construction that dominate expression-bound designs
//! (doc-18 §실측: eval is 55–82% of runtime once expressions are wide).
//!
//! ## Scope (intentionally bounded; everything else falls back to the kernel)
//! [`try_compile`] returns `Some` ONLY when the WHOLE tree is in this subset, and
//! EVERY node's context-determined eval width is at most 64 bits (one plane word):
//! leaves `Const` (non-real) and scalar `Signal` (`word == None`); binary
//! `Add`/`Sub`/`Mul` and `BitAnd`/`BitOr`/`BitXor`/`BitXnor`; unary `BitNot`,
//! `Plus`, `Minus`. Any other variant/operator, a real const, an array-indexed
//! signal, or a node wider than 64 bits makes the whole expression return `None`,
//! so the VM delegates to the kernel's tree-walk `eval_ctx` (the differential
//! ORACLE). Comparisons, shifts, Div/Mod, reductions, ternary, select/concat, the
//! over-64-bit lane, and real are deferred follow-ons.
//!
//! ## Why it is byte-identical (the P5 gate proves it end-to-end on top)
//! The interpreter's `eval_ctx` stays the oracle; native eval reproduces it EXACTLY
//! for the supported nodes (width at most 64). Width/sign context propagates DOWN
//! exactly as `eval_ctx` does (`w = self.max(ctx)`, `eff_signed = self_signed &&
//! ctx_signed`) — the SAME recursion, so per-node widths match. Leaves reuse the
//! EXACT oracle path: `read_net(net,None)` / `eval_const`-equiv, then
//! `resize_keep_sign(w, eff_signed)` — net read + context resize verbatim. Arith
//! (oracle `arith()`): if EITHER operand has any X/Z the whole result is X; else a
//! 128-bit lane masked to `w`, and for `w` at most 64 the low-`w` bits of a `u64`
//! wrapping op equal that lane (two's-complement, hence sign-independent), so
//! `(a OP b) & low_mask(w)` matches both signed and unsigned. Bitwise/not reuse the
//! SAME `value::{and_w,or_w,xor_w,xnor_w,not_w}` 4-state word primitives the oracle
//! calls, masked to `w`. A register is the single-word 4-state pair `(val, unk)`,
//! masked to its node width on production, so the program rebuilds exactly one
//! `Value` at the end.

use sim_ir::{BinOp, ConstRepr, Expr, SimIr, UnOp};

use crate::eval::NetReader;
use crate::value::{and_w, low_mask, not_w, or_w, xnor_w, xor_w, Value};
use crate::width::WidthTable;

#[derive(Clone, Copy)]
enum ArithKind {
    Add,
    Sub,
    Mul,
}

#[derive(Clone, Copy)]
enum BitKind {
    And,
    Or,
    Xor,
    Xnor,
}

/// One native eval instruction (post-order; operates on a value stack of single-word
/// 4-state pairs `(val, unk)`). `Plus` needs no opcode — its operand is simply
/// compiled at this node's `(w, eff_signed)` and left on the stack (passthrough).
#[derive(Clone, Copy)]
enum NOp {
    /// push a compile-time constant, already resized to its node width and masked.
    Const { val: u64, unk: u64 },
    /// push `read_net(net, None).resize_keep_sign(w, signed)`, masked to `w`.
    LoadScalar { net: u32, w: u32, signed: bool },
    /// pop b, pop a → push the `w`-wide arith result (all-X if either has any X/Z).
    Arith { kind: ArithKind, w: u32 },
    /// pop b, pop a → push the `w`-wide 4-state bitwise result.
    Bitwise { kind: BitKind, w: u32 },
    /// pop a → push the `w`-wide 4-state complement.
    Not { w: u32 },
    /// pop a → push the `w`-wide two's-complement negate (all-X if any X/Z).
    Neg { w: u32 },
}

/// A compiled expression. `root_w`/`root_signed` stamp the final `Value` so it is
/// byte-identical to `eval_ctx`'s return for this `(ExprId, ctx)`; the kernel hands
/// that `Value` straight to `k_write_lvalue`/`k_schedule_nba`.
pub(crate) struct NativeProg {
    ops: Vec<NOp>,
    root_w: u32,
    root_signed: bool,
}

/// `eval_const` minus the real lane (we bail on real). Returns the const's natural
/// `Value` (pre-resize); `None` for a real const.
fn const_value(ir: &SimIr, cid: u32) -> Option<Value> {
    let c = &ir.consts[cid as usize];
    if matches!(c.repr, ConstRepr::Real) {
        return None;
    }
    let signed = matches!(c.repr, ConstRepr::Numeric) && c.signed;
    Some(Value::from_packed(&c.bits, c.width, signed))
}

/// `BinOp` → its native class, or `None` if unsupported (Div/Mod/Pow/compare/shift/
/// logical — each has subtler semantics, deferred to a later increment).
enum BinClass {
    Arith(ArithKind),
    Bit(BitKind),
}
fn classify_binop(op: BinOp) -> Option<BinClass> {
    Some(match op {
        BinOp::Add => BinClass::Arith(ArithKind::Add),
        BinOp::Sub => BinClass::Arith(ArithKind::Sub),
        BinOp::Mul => BinClass::Arith(ArithKind::Mul),
        BinOp::BitAnd => BinClass::Bit(BitKind::And),
        BinOp::BitOr => BinClass::Bit(BitKind::Or),
        BinOp::BitXor => BinClass::Bit(BitKind::Xor),
        BinOp::BitXnor => BinClass::Bit(BitKind::Xnor),
        _ => return None,
    })
}

/// Try to compile `eid` evaluated in context `(ctx_width, ctx_signed)` — the SAME
/// context `eval_for_lvalue` passes (`ctx_width = max(lvalue_w, self_w(rhs))`,
/// `ctx_signed = rhs self-sign`). `None` ⇒ outside the supported subset ⇒ fall back.
pub(crate) fn try_compile(
    ir: &SimIr,
    wt: &WidthTable,
    eid: u32,
    ctx_width: u32,
    ctx_signed: bool,
) -> Option<NativeProg> {
    let self_sw = wt.get(eid);
    let root_w = self_sw.width.max(ctx_width);
    if root_w == 0 || root_w > 64 {
        return None;
    }
    let mut ops = Vec::new();
    lower(ir, wt, eid, ctx_width, ctx_signed, &mut ops)?;
    Some(NativeProg {
        ops,
        root_w,
        // At the root, `ctx_signed` IS `rhs` self-sign (eval_for_lvalue), so
        // `eff_signed = self_signed && ctx_signed == ctx_signed`, and every oracle
        // arm stamps the result `signed = eff_signed`. So the final Value's sign flag
        // is `ctx_signed` — matching `resize_keep_sign(w, ctx_signed)`.
        root_signed: ctx_signed,
    })
}

/// Post-order lowering mirroring `eval_ctx`'s context propagation. Returns `None`
/// (bailing the WHOLE expression) on any unsupported node or any node width > 64.
fn lower(
    ir: &SimIr,
    wt: &WidthTable,
    eid: u32,
    ctx_width: u32,
    ctx_signed: bool,
    ops: &mut Vec<NOp>,
) -> Option<()> {
    let self_sw = wt.get(eid);
    let w = self_sw.width.max(ctx_width);
    let eff_signed = self_sw.signed && ctx_signed;
    if w == 0 || w > 64 {
        return None;
    }
    match &ir.exprs[eid as usize] {
        Expr::Const { val } => {
            let r = const_value(ir, *val)?.resize_keep_sign(w, eff_signed);
            let m = low_mask(w);
            ops.push(NOp::Const {
                val: r.val.first().copied().unwrap_or(0) & m,
                unk: r.unk.first().copied().unwrap_or(0) & m,
            });
            Some(())
        }
        Expr::Signal { net, word } => {
            if word.is_some() {
                return None; // array-indexed read: dynamic index, deferred
            }
            ops.push(NOp::LoadScalar {
                net: *net,
                w,
                signed: eff_signed,
            });
            Some(())
        }
        Expr::Unary { op, operand } => match op {
            // context-determined unary: propagate (w, eff_signed) into the operand.
            UnOp::Plus => lower(ir, wt, *operand, w, eff_signed, ops), // passthrough
            UnOp::Minus => {
                lower(ir, wt, *operand, w, eff_signed, ops)?;
                ops.push(NOp::Neg { w });
                Some(())
            }
            UnOp::BitNot => {
                lower(ir, wt, *operand, w, eff_signed, ops)?;
                ops.push(NOp::Not { w });
                Some(())
            }
            // reductions / lognot: 1-bit self-determined result, deferred increment.
            _ => None,
        },
        Expr::Binary { op, lhs, rhs } => {
            let class = classify_binop(*op)?;
            // ARITHMETIC + BITWISE are context-determined: BOTH operands at (w, eff_signed).
            lower(ir, wt, *lhs, w, eff_signed, ops)?;
            lower(ir, wt, *rhs, w, eff_signed, ops)?;
            ops.push(match class {
                BinClass::Arith(kind) => NOp::Arith { kind, w },
                BinClass::Bit(kind) => NOp::Bitwise { kind, w },
            });
            Some(())
        }
        // ternary / concat / replicate / select / sysfunc / call: deferred increment.
        _ => None,
    }
}

/// Run a compiled program against `nets`, producing the single `Value` the oracle's
/// `eval_ctx` would return for the same `(ExprId, ctx)`.
pub(crate) fn run(prog: &NativeProg, nets: &dyn NetReader) -> Value {
    let mut stack: Vec<(u64, u64)> = Vec::with_capacity(prog.ops.len());
    for op in &prog.ops {
        match *op {
            NOp::Const { val, unk } => stack.push((val, unk)),
            NOp::LoadScalar { net, w, signed } => {
                let v = nets.read_net(net, None).resize_keep_sign(w, signed);
                let m = low_mask(w);
                stack.push((
                    v.val.first().copied().unwrap_or(0) & m,
                    v.unk.first().copied().unwrap_or(0) & m,
                ));
            }
            NOp::Arith { kind, w } => {
                let (bv, bu) = stack.pop().expect("native arith: missing rhs");
                let (av, au) = stack.pop().expect("native arith: missing lhs");
                let m = low_mask(w);
                // Oracle `arith`: ANY X/Z in EITHER operand poisons the whole result to
                // X. An X bit is `(val=0, unk=1)` (matching `Value::xs`), so all-X is
                // `(0, m)` — NOT `(m, m)`.
                let res = if (au & m) != 0 || (bu & m) != 0 {
                    (0, m)
                } else {
                    let rv = match kind {
                        ArithKind::Add => av.wrapping_add(bv),
                        ArithKind::Sub => av.wrapping_sub(bv),
                        ArithKind::Mul => av.wrapping_mul(bv),
                    };
                    (rv & m, 0)
                };
                stack.push(res);
            }
            NOp::Bitwise { kind, w } => {
                let (bv, bu) = stack.pop().expect("native bitwise: missing rhs");
                let (av, au) = stack.pop().expect("native bitwise: missing lhs");
                let m = low_mask(w);
                let (rv, ru) = match kind {
                    BitKind::And => and_w(av, au, bv, bu),
                    BitKind::Or => or_w(av, au, bv, bu),
                    BitKind::Xor => xor_w(av, au, bv, bu),
                    BitKind::Xnor => xnor_w(av, au, bv, bu),
                };
                stack.push((rv & m, ru & m));
            }
            NOp::Not { w } => {
                let (av, au) = stack.pop().expect("native not: missing operand");
                let m = low_mask(w);
                let (rv, ru) = not_w(av, au);
                stack.push((rv & m, ru & m));
            }
            NOp::Neg { w } => {
                let (av, au) = stack.pop().expect("native neg: missing operand");
                let m = low_mask(w);
                let res = if (au & m) != 0 {
                    (0, m) // oracle `negate`: any X/Z poisons to X (val=0, unk=1)
                } else {
                    ((!av).wrapping_add(1) & m, 0)
                };
                stack.push(res);
            }
        }
    }
    let (fv, fu) = stack.pop().expect("native eval produced no result");
    let mut out = Value::zeros(prog.root_w, prog.root_signed);
    out.val[0] = fv;
    out.unk[0] = fu;
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use sim_ir::SimIr;

    /// A `NetReader` returning a fixed `Value` per NetId (and all-X for any other).
    struct FakeNets(Vec<Value>);
    impl NetReader for FakeNets {
        fn read_net(&self, net: u32, _word: Option<u32>) -> Value {
            self.0
                .get(net as usize)
                .cloned()
                .unwrap_or_else(|| Value::xs(1, false))
        }
    }

    fn nv(width: u32, signed: bool) -> sim_ir::NetVar {
        sim_ir::NetVar {
            kind: sim_ir::NetKind::Reg,
            width,
            msb: width.saturating_sub(1),
            lsb: 0,
            signed,
            array_len: 1,
            dir: sim_ir::PortDir::Internal,
            init: sim_ir::BitPacked {
                val: vec![0],
                unk: vec![0],
            },
        }
    }

    /// Minimal `SimIr` carrying only the arenas width inference + native eval read:
    /// `exprs`, `consts`, `nets`. Everything else is empty.
    fn ir_of(exprs: Vec<Expr>, consts: Vec<sim_ir::ConstVal>, nets: Vec<sim_ir::NetVar>) -> SimIr {
        SimIr {
            instances: vec![],
            nets,
            processes: vec![],
            cont_assigns: vec![],
            funcs: vec![],
            exprs,
            stmts: vec![],
            blocks: vec![],
            consts,
        }
    }

    /// Cross-check native `try_compile + run` against the interpreter oracle
    /// `EvalCtx::eval_ctx` for `eid` in context `(ctx_w, ctx_signed)` over a set of
    /// net `Value`s. Asserts the produced `Value`s are byte-identical (val, unk,
    /// width, signed) — the same equality the P5 gate enforces end-to-end.
    fn assert_matches_oracle(ir: &SimIr, eid: u32, ctx_w: u32, ctx_signed: bool, nets: &[Value]) {
        let wt = WidthTable::build(ir);
        let fake = FakeNets(nets.to_vec());
        let oracle = {
            let ctx = crate::eval::EvalCtx {
                ir,
                nets: &fake,
                now: 0,
                wt: &wt,
                time_mult: 1,
            };
            ctx.eval_ctx(eid, ctx_w, ctx_signed)
        };
        let prog = try_compile(ir, &wt, eid, ctx_w, ctx_signed)
            .expect("expression must be native-compilable in this test");
        let native = run(&prog, &fake);
        assert_eq!(
            native, oracle,
            "native eval diverged from oracle for eid {eid} ctx ({ctx_w},{ctx_signed})"
        );
    }

    fn sig(net: u32) -> Expr {
        Expr::Signal { net, word: None }
    }
    fn bin(op: BinOp, lhs: u32, rhs: u32) -> Expr {
        Expr::Binary { op, lhs, rhs }
    }

    // ── a 64-bit clean Value with given low word ──
    fn v64(x: u64) -> Value {
        let mut v = Value::zeros(64, false);
        v.val[0] = x;
        v
    }
    // ── an X/Z-bearing Value: `xmask` marks unknown bits ──
    fn v64_xz(val: u64, xmask: u64) -> Value {
        let mut v = Value::zeros(64, false);
        v.val[0] = val & !xmask;
        v.unk[0] = xmask;
        v
    }

    #[test]
    fn add_two_signals_matches_oracle_incl_wrap() {
        // exprs: 0=sig(0), 1=sig(1), 2 = 0 + 1
        let ir = ir_of(
            vec![sig(0), sig(1), bin(BinOp::Add, 0, 1)],
            vec![],
            vec![nv(64, false), nv(64, false)],
        );
        for (a, b) in [(7u64, 35u64), (u64::MAX, 1), (0, 0), (1 << 63, 1 << 63)] {
            assert_matches_oracle(&ir, 2, 64, false, &[v64(a), v64(b)]);
        }
    }

    #[test]
    fn arith_xz_operand_poisons_whole_result() {
        let ir = ir_of(
            vec![sig(0), sig(1), bin(BinOp::Add, 0, 1)],
            vec![],
            vec![nv(64, false), nv(64, false)],
        );
        // one X bit anywhere in an operand ⇒ the oracle poisons the whole add to X.
        assert_matches_oracle(&ir, 2, 64, false, &[v64_xz(5, 0b10), v64(9)]);
        assert_matches_oracle(&ir, 2, 64, false, &[v64(9), v64_xz(0, 1 << 40)]);
    }

    #[test]
    fn sub_and_mul_match_oracle() {
        for op in [BinOp::Sub, BinOp::Mul] {
            let ir = ir_of(
                vec![sig(0), sig(1), bin(op, 0, 1)],
                vec![],
                vec![nv(32, false), nv(32, false)],
            );
            for (a, b) in [(3u64, 9u64), (0xFFFF_FFFF, 2), (123456, 654321)] {
                assert_matches_oracle(&ir, 2, 32, false, &[v64(a), v64(b)]);
            }
        }
    }

    #[test]
    fn bitwise_4state_matches_oracle() {
        for op in [BinOp::BitAnd, BinOp::BitOr, BinOp::BitXor, BinOp::BitXnor] {
            let ir = ir_of(
                vec![sig(0), sig(1), bin(op, 0, 1)],
                vec![],
                vec![nv(16, false), nv(16, false)],
            );
            // include X/Z so the 4-state truth tables (not just 2-state) are exercised.
            let a = v64_xz(0b1010_0101, 0b0000_1100);
            let b = v64_xz(0b1100_0011, 0b0011_0000);
            assert_matches_oracle(&ir, 2, 16, false, &[a, b]);
        }
    }

    #[test]
    fn bitnot_and_negate_match_oracle() {
        // ~sig0
        let ir_not = ir_of(
            vec![
                sig(0),
                Expr::Unary {
                    op: UnOp::BitNot,
                    operand: 0,
                },
            ],
            vec![],
            vec![nv(8, false)],
        );
        assert_matches_oracle(&ir_not, 1, 8, false, &[v64(0b1011_0010)]);
        assert_matches_oracle(&ir_not, 1, 8, false, &[v64_xz(0b1011_0010, 0b0000_1111)]);

        // -sig0 (two's complement); X/Z poisons.
        let ir_neg = ir_of(
            vec![
                sig(0),
                Expr::Unary {
                    op: UnOp::Minus,
                    operand: 0,
                },
            ],
            vec![],
            vec![nv(8, true)],
        );
        assert_matches_oracle(&ir_neg, 1, 8, true, &[v64(5)]);
        assert_matches_oracle(&ir_neg, 1, 8, true, &[v64_xz(5, 0b10)]);
    }

    #[test]
    fn chained_adds_match_oracle() {
        // (((s0 + s1) + s2) + s3) — the EXPR_HEAVY shape, all 64-bit.
        let ir = ir_of(
            vec![
                sig(0),
                sig(1),
                bin(BinOp::Add, 0, 1),
                sig(2),
                bin(BinOp::Add, 2, 3),
                sig(3),
                bin(BinOp::Add, 4, 5),
            ],
            vec![],
            vec![nv(64, false), nv(64, false), nv(64, false), nv(64, false)],
        );
        assert_matches_oracle(&ir, 6, 64, false, &[v64(11), v64(22), v64(33), v64(44)]);
    }

    #[test]
    fn over_64_bits_is_not_native_compilable() {
        // a 100-bit add must bail (None) → the VM keeps interpreting it.
        let ir = ir_of(
            vec![sig(0), sig(1), bin(BinOp::Add, 0, 1)],
            vec![],
            vec![nv(100, false), nv(100, false)],
        );
        let wt = WidthTable::build(&ir);
        assert!(try_compile(&ir, &wt, 2, 100, false).is_none());
    }

    #[test]
    fn unsupported_operator_bails() {
        // Div is not in the subset → None.
        let ir = ir_of(
            vec![sig(0), sig(1), bin(BinOp::Div, 0, 1)],
            vec![],
            vec![nv(32, false), nv(32, false)],
        );
        let wt = WidthTable::build(&ir);
        assert!(try_compile(&ir, &wt, 2, 32, false).is_none());
    }
}
