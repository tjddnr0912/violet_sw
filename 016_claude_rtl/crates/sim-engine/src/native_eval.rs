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
//! `Add`/`Sub`/`Mul`/`Div`/`Mod`, the four bitwise ops, all eight comparisons
//! (`<`/`<=`/`>`/`>=`/`==`/`!=`/`===`/`!==`), shifts (`<<`/`>>`/`>>>`), logical
//! `&&`/`||`; unary `BitNot`/`Plus`/`Minus`, the six reductions, `!`; and the
//! ternary `?:` (X-cond branch merge included). Any other variant (`**`, concat,
//! replicate, select, sysfunc, call), a real const, an array-indexed signal, or a
//! node wider than 64 bits makes the whole expression return `None`, so the VM
//! delegates to the kernel's tree-walk `eval_ctx` (the differential ORACLE). The
//! over-64-bit lane and real stay deferred follow-ons.
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

#[derive(Clone, Copy, PartialEq)]
enum CmpKind {
    Lt,
    Le,
    Gt,
    Ge,
}

#[derive(Clone, Copy)]
enum DivKind {
    Div,
    Mod,
}

#[derive(Clone, Copy)]
enum RedK {
    And,
    Or,
    Xor,
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
    /// pop b, pop a → push the 1-bit relational result at pair width `w`
    /// (signed iff BOTH operands signed; any X/Z → 1-bit X). Mirrors oracle
    /// `relational` (single-word case).
    Cmp { kind: CmpKind, w: u32, signed: bool },
    /// pop b, pop a → push 1-bit `==`/`!=` (any X/Z in the compared bits → X).
    EqNe { ne: bool, w: u32 },
    /// pop b, pop a → push 1-bit `===`/`!==` (exact 4-state plane compare; never X).
    CaseEqNe { ne: bool, w: u32 },
    /// pop amount (self-determined), pop l (`w`-wide) → push `l << amt` at `w`
    /// (X/Z amount → all-X; amt ≥ w shifts everything out). Oracle `shift_left`
    /// grow-then-truncate ≡ direct masked shift for w ≤ 64.
    Shl { w: u32 },
    /// pop amount, pop l → push `l >> amt` at `w`. `arith` (the lhs OWN sign for
    /// `>>>`) fills vacated top bits with l's MSB pair (which may be X/Z).
    Shr { w: u32, arith: bool },
    /// pop b, pop a → push `w`-wide div/mod (X/Z or divide-by-zero → all-X;
    /// signed = truncating toward zero, exactly oracle `arith`'s i128 lane).
    DivMod { kind: DivKind, w: u32, signed: bool },
    /// pop else, pop then, pop cond → push the selected branch at `w`; an X/Z
    /// cond merges the branches bit-wise (agree → through, differ → X).
    Ternary { w: u32, cond_w: u32 },
    /// pop a (self-determined, `opw` wide) → push the 1-bit reduction
    /// (negated for the N-forms; X stays X under negation).
    Reduce { kind: RedK, neg: bool, opw: u32 },
    /// pop a → push 1-bit `!a` via tri-valued truthiness.
    LogNot { opw: u32 },
    /// pop r, pop l (each self-determined) → push 1-bit `&&`/`||` (tri-valued).
    LogBin { and: bool, lw: u32, rw: u32 },
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
            // reductions / lognot: 1-bit result over a SELF-DETERMINED operand
            // (lower with ctx_width 0 / ctx_signed true ⇒ (self_w, self_signed),
            // exactly the oracle's `self.eval(operand)`), then zero-extend (free:
            // the register's upper bits are already 0 and parents mask).
            UnOp::LogNot => {
                let opw = wt.get(*operand).width;
                lower(ir, wt, *operand, 0, true, ops)?;
                ops.push(NOp::LogNot { opw });
                Some(())
            }
            UnOp::RedAnd
            | UnOp::RedNand
            | UnOp::RedOr
            | UnOp::RedNor
            | UnOp::RedXor
            | UnOp::RedXnor => {
                let opw = wt.get(*operand).width;
                lower(ir, wt, *operand, 0, true, ops)?;
                let (kind, neg) = match op {
                    UnOp::RedAnd => (RedK::And, false),
                    UnOp::RedNand => (RedK::And, true),
                    UnOp::RedOr => (RedK::Or, false),
                    UnOp::RedNor => (RedK::Or, true),
                    UnOp::RedXor => (RedK::Xor, false),
                    _ => (RedK::Xor, true), // RedXnor
                };
                ops.push(NOp::Reduce { kind, neg, opw });
                Some(())
            }
        },
        Expr::Binary { op, lhs, rhs } => {
            use BinOp as B;
            match op {
                // COMPARISONS: operands mutually context-determined at
                // (max(self_w(L), self_w(R)), bothsigned); 1-bit result.
                B::Lt | B::Le | B::Gt | B::Ge | B::Eq | B::Ne | B::CaseEq | B::CaseNe => {
                    let cmp_w = wt.get(*lhs).width.max(wt.get(*rhs).width);
                    if cmp_w == 0 || cmp_w > 64 {
                        return None;
                    }
                    let pair_signed = wt.get(*lhs).signed && wt.get(*rhs).signed;
                    lower(ir, wt, *lhs, cmp_w, pair_signed, ops)?;
                    lower(ir, wt, *rhs, cmp_w, pair_signed, ops)?;
                    ops.push(match op {
                        B::Lt => NOp::Cmp {
                            kind: CmpKind::Lt,
                            w: cmp_w,
                            signed: pair_signed,
                        },
                        B::Le => NOp::Cmp {
                            kind: CmpKind::Le,
                            w: cmp_w,
                            signed: pair_signed,
                        },
                        B::Gt => NOp::Cmp {
                            kind: CmpKind::Gt,
                            w: cmp_w,
                            signed: pair_signed,
                        },
                        B::Ge => NOp::Cmp {
                            kind: CmpKind::Ge,
                            w: cmp_w,
                            signed: pair_signed,
                        },
                        B::Eq => NOp::EqNe {
                            ne: false,
                            w: cmp_w,
                        },
                        B::Ne => NOp::EqNe { ne: true, w: cmp_w },
                        B::CaseEq => NOp::CaseEqNe {
                            ne: false,
                            w: cmp_w,
                        },
                        _ => NOp::CaseEqNe { ne: true, w: cmp_w }, // CaseNe
                    });
                    Some(())
                }
                // LOGICAL: each operand self-determined, tri-valued combine.
                B::LogAnd | B::LogOr => {
                    let lw = wt.get(*lhs).width;
                    let rw = wt.get(*rhs).width;
                    lower(ir, wt, *lhs, 0, true, ops)?;
                    lower(ir, wt, *rhs, 0, true, ops)?;
                    ops.push(NOp::LogBin {
                        and: matches!(op, B::LogAnd),
                        lw,
                        rw,
                    });
                    Some(())
                }
                // SHIFTS: LEFT context-determined; amount SELF-determined.
                B::Shl | B::AShl => {
                    lower(ir, wt, *lhs, w, eff_signed, ops)?;
                    lower(ir, wt, *rhs, 0, true, ops)?;
                    ops.push(NOp::Shl { w });
                    Some(())
                }
                B::Shr => {
                    lower(ir, wt, *lhs, w, eff_signed, ops)?;
                    lower(ir, wt, *rhs, 0, true, ops)?;
                    ops.push(NOp::Shr { w, arith: false });
                    Some(())
                }
                // `>>>`: fill governed by the LEFT operand's OWN sign (oracle
                // evaluates lhs at (w, own-sign); the final ctx re-stamp only
                // changes the sign FLAG, never the bits — registers carry bits).
                B::AShr => {
                    let lhs_signed = wt.get(*lhs).signed;
                    lower(ir, wt, *lhs, w, lhs_signed, ops)?;
                    lower(ir, wt, *rhs, 0, true, ops)?;
                    ops.push(NOp::Shr {
                        w,
                        arith: lhs_signed,
                    });
                    Some(())
                }
                // DIV/MOD: context-determined like Add (X/Z or /0 → all-X).
                B::Div | B::Mod => {
                    lower(ir, wt, *lhs, w, eff_signed, ops)?;
                    lower(ir, wt, *rhs, w, eff_signed, ops)?;
                    ops.push(NOp::DivMod {
                        kind: if matches!(op, B::Div) {
                            DivKind::Div
                        } else {
                            DivKind::Mod
                        },
                        w,
                        signed: eff_signed,
                    });
                    Some(())
                }
                _ => {
                    let class = classify_binop(*op)?;
                    // ARITHMETIC + BITWISE: BOTH operands at (w, eff_signed).
                    lower(ir, wt, *lhs, w, eff_signed, ops)?;
                    lower(ir, wt, *rhs, w, eff_signed, ops)?;
                    ops.push(match class {
                        BinClass::Arith(kind) => NOp::Arith { kind, w },
                        BinClass::Bit(kind) => NOp::Bitwise { kind, w },
                    });
                    Some(())
                }
            }
        }
        // ternary: cond self-determined truthiness; branches context-determined.
        Expr::Ternary {
            cond,
            then_e,
            else_e,
        } => {
            let cond_w = wt.get(*cond).width;
            lower(ir, wt, *cond, 0, true, ops)?;
            lower(ir, wt, *then_e, w, eff_signed, ops)?;
            lower(ir, wt, *else_e, w, eff_signed, ops)?;
            ops.push(NOp::Ternary { w, cond_w });
            Some(())
        }
        // concat / replicate / select / sysfunc / call: deferred increment.
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
            NOp::Cmp { kind, w, signed } => {
                let (bv, bu) = stack.pop().expect("native cmp: missing rhs");
                let (av, au) = stack.pop().expect("native cmp: missing lhs");
                let m = low_mask(w);
                let res = if (au & m) != 0 || (bu & m) != 0 {
                    (0, 1) // oracle: any X/Z → 1-bit X
                } else {
                    use std::cmp::Ordering::*;
                    let ord = if signed {
                        let sx = |x: u64| ((x << (64 - w)) as i64) >> (64 - w);
                        sx(av & m).cmp(&sx(bv & m))
                    } else {
                        (av & m).cmp(&(bv & m))
                    };
                    let b = matches!(
                        (kind, ord),
                        (CmpKind::Lt, Less)
                            | (CmpKind::Le, Less)
                            | (CmpKind::Le, Equal)
                            | (CmpKind::Gt, Greater)
                            | (CmpKind::Ge, Greater)
                            | (CmpKind::Ge, Equal)
                    );
                    (b as u64, 0)
                };
                stack.push(res);
            }
            NOp::EqNe { ne, w } => {
                let (bv, bu) = stack.pop().expect("native eq: missing rhs");
                let (av, au) = stack.pop().expect("native eq: missing lhs");
                let m = low_mask(w);
                let res = if (au & m) != 0 || (bu & m) != 0 {
                    (0, 1) // any compared X/Z bit → X
                } else {
                    let eq = (av & m) == (bv & m);
                    ((eq ^ ne) as u64, 0)
                };
                stack.push(res);
            }
            NOp::CaseEqNe { ne, w } => {
                let (bv, bu) = stack.pop().expect("native caseeq: missing rhs");
                let (av, au) = stack.pop().expect("native caseeq: missing lhs");
                let m = low_mask(w);
                let eq = (av & m) == (bv & m) && (au & m) == (bu & m);
                stack.push(((eq ^ ne) as u64, 0));
            }
            NOp::Shl { w } => {
                let (rv, ru) = stack.pop().expect("native shl: missing amount");
                let (lv, lu) = stack.pop().expect("native shl: missing lhs");
                let m = low_mask(w);
                let res = if ru != 0 {
                    (0, m) // X/Z amount → all-X at w (oracle xs(l.width))
                } else if rv >= 64 {
                    (0, 0) // everything shifted out
                } else {
                    ((lv << rv) & m, (lu << rv) & m)
                };
                stack.push(res);
            }
            NOp::Shr { w, arith } => {
                let (rv, ru) = stack.pop().expect("native shr: missing amount");
                let (lv, lu) = stack.pop().expect("native shr: missing lhs");
                let m = low_mask(w);
                let res = if ru != 0 {
                    (0, m)
                } else if !arith {
                    if rv >= 64 {
                        (0, 0)
                    } else {
                        ((lv >> rv) & m, (lu >> rv) & m)
                    }
                } else {
                    // sign fill from l's MSB pair (which may itself be X/Z).
                    let fv = (lv >> (w - 1)) & 1;
                    let fu = (lu >> (w - 1)) & 1;
                    let body = if rv >= 64 {
                        (0, 0)
                    } else {
                        ((lv >> rv) & m, (lu >> rv) & m)
                    };
                    let fill_n = rv.min(w as u64) as u32; // top bits to fill
                    let fill_mask = if fill_n == 0 {
                        0
                    } else {
                        m & !low_mask(w - fill_n)
                    };
                    (
                        (body.0 & !fill_mask) | (if fv == 1 { fill_mask } else { 0 }),
                        (body.1 & !fill_mask) | (if fu == 1 { fill_mask } else { 0 }),
                    )
                };
                stack.push(res);
            }
            NOp::DivMod { kind, w, signed } => {
                let (bv, bu) = stack.pop().expect("native divmod: missing rhs");
                let (av, au) = stack.pop().expect("native divmod: missing lhs");
                let m = low_mask(w);
                let res = if (au & m) != 0 || (bu & m) != 0 {
                    (0, m)
                } else if signed {
                    let sx = |x: u64| ((x << (64 - w)) as i64) >> (64 - w);
                    let b = sx(bv & m);
                    if b == 0 {
                        (0, m) // divide by zero → all-X
                    } else {
                        let a = sx(av & m);
                        let r = match kind {
                            DivKind::Div => a.wrapping_div(b),
                            DivKind::Mod => a.wrapping_rem(b),
                        };
                        ((r as u64) & m, 0)
                    }
                } else {
                    let b = bv & m;
                    if b == 0 {
                        (0, m)
                    } else {
                        let a = av & m;
                        let r = match kind {
                            DivKind::Div => a / b,
                            DivKind::Mod => a % b,
                        };
                        (r & m, 0)
                    }
                };
                stack.push(res);
            }
            NOp::Ternary { w, cond_w } => {
                let (ev, eu) = stack.pop().expect("native ternary: missing else");
                let (tv, tu) = stack.pop().expect("native ternary: missing then");
                let (cv, cu) = stack.pop().expect("native ternary: missing cond");
                let mc = low_mask(cond_w);
                let m = low_mask(w);
                // truthiness: any definite-1 → True; else any unknown → Unknown;
                // else False (matches oracle `Tri`).
                let res = if (cv & !cu & mc) != 0 {
                    (tv & m, tu & m)
                } else if (cu & mc) != 0 {
                    // merge_x: identical (val,unk) pairs pass through, else X.
                    let ident = !((tv ^ ev) | (tu ^ eu)) & m;
                    ((tv & ident), (tu & ident) | (m & !ident))
                } else {
                    (ev & m, eu & m)
                };
                stack.push(res);
            }
            NOp::Reduce { kind, neg, opw } => {
                let (av, au) = stack.pop().expect("native reduce: missing operand");
                let m = low_mask(opw);
                let known1 = av & !au & m;
                let known0 = !au & !av & m;
                let unk = au & m;
                let (v, u): (u64, u64) = match kind {
                    RedK::And if known0 != 0 => (0, 0),
                    RedK::And if unk != 0 => (0, 1),
                    RedK::And => (1, 0),
                    RedK::Or if known1 != 0 => (1, 0),
                    RedK::Or if unk != 0 => (0, 1),
                    RedK::Or => (0, 0),
                    RedK::Xor if unk != 0 => (0, 1),
                    RedK::Xor => ((known1.count_ones() & 1) as u64, 0),
                };
                let out = if neg && u == 0 { (v ^ 1, 0) } else { (v, u) };
                stack.push(out);
            }
            NOp::LogNot { opw } => {
                let (av, au) = stack.pop().expect("native lognot: missing operand");
                let m = low_mask(opw);
                let res = if (av & !au & m) != 0 {
                    (0, 0) // truthy → !a = 0
                } else if (au & m) != 0 {
                    (0, 1) // unknown → X
                } else {
                    (1, 0) // falsy → 1
                };
                stack.push(res);
            }
            NOp::LogBin { and, lw, rw } => {
                let (bv, bu) = stack.pop().expect("native logbin: missing rhs");
                let (av, au) = stack.pop().expect("native logbin: missing lhs");
                let tri = |v: u64, u: u64, w: u32| {
                    let m = low_mask(w);
                    if (v & !u & m) != 0 {
                        Some(true)
                    } else if (u & m) != 0 {
                        None
                    } else {
                        Some(false)
                    }
                };
                let (l, r) = (tri(av, au, lw), tri(bv, bu, rw));
                let res = if and {
                    match (l, r) {
                        (Some(false), _) | (_, Some(false)) => (0, 0),
                        (Some(true), Some(true)) => (1, 0),
                        _ => (0, 1),
                    }
                } else {
                    match (l, r) {
                        (Some(true), _) | (_, Some(true)) => (1, 0),
                        (Some(false), Some(false)) => (0, 0),
                        _ => (0, 1),
                    }
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
        // Concat stays outside the subset → None (Div joined the subset in the
        // comparisons/shifts/div increment).
        let ir = ir_of(
            vec![sig(0), sig(1), Expr::Concat { parts: vec![0, 1] }],
            vec![],
            vec![nv(32, false), nv(32, false)],
        );
        let wt = WidthTable::build(&ir);
        assert!(try_compile(&ir, &wt, 2, 64, false).is_none());
    }

    // ── follow-on increment: comparisons / shifts / div-mod / ternary /
    //    reductions / logical (REMAINING_WORK "native-eval follow-on") ──

    fn un(op: UnOp, operand: u32) -> Expr {
        Expr::Unary { op, operand }
    }
    fn vw(w: u32, x: u64) -> Value {
        let mut v = Value::zeros(w, false);
        v.val[0] = x & low_mask(w);
        v
    }
    fn vws(w: u32, x: u64) -> Value {
        let mut v = Value::zeros(w, true);
        v.val[0] = x & low_mask(w);
        v
    }
    fn vw_xz(w: u32, x: u64, xm: u64) -> Value {
        let mut v = Value::zeros(w, false);
        let m = low_mask(w);
        v.val[0] = x & !xm & m;
        v.unk[0] = xm & m;
        v
    }

    #[test]
    fn relational_signed_pair_matches_oracle() {
        for op in [BinOp::Lt, BinOp::Le, BinOp::Gt, BinOp::Ge] {
            let ir = ir_of(
                vec![sig(0), sig(1), bin(op, 0, 1)],
                vec![],
                vec![nv(8, true), nv(8, true)],
            );
            // -8 vs 3, 3 vs -8, equal, MIN vs MAX — signed ordering.
            for (a, b) in [(0xF8u64, 3u64), (3, 0xF8), (5, 5), (0x80, 0x7F)] {
                assert_matches_oracle(&ir, 2, 32, false, &[vws(8, a), vws(8, b)]);
            }
            // any X/Z → 1-bit X (zero-extended into the context).
            assert_matches_oracle(&ir, 2, 32, false, &[vw_xz(8, 5, 0b100), vws(8, 9)]);
        }
    }

    #[test]
    fn relational_mixed_sign_is_unsigned_compare() {
        // one unsigned operand ⇒ pair compares UNSIGNED (0xF8 > 3, not -8 < 3).
        let ir = ir_of(
            vec![sig(0), sig(1), bin(BinOp::Lt, 0, 1)],
            vec![],
            vec![nv(8, true), nv(8, false)],
        );
        assert_matches_oracle(&ir, 2, 8, false, &[vws(8, 0xF8), vw(8, 3)]);
        assert_matches_oracle(&ir, 2, 8, false, &[vws(8, 3), vw(8, 0xF8)]);
    }

    #[test]
    fn equality_and_case_equality_match_oracle() {
        for op in [BinOp::Eq, BinOp::Ne] {
            let ir = ir_of(
                vec![sig(0), sig(1), bin(op, 0, 1)],
                vec![],
                vec![nv(8, false), nv(8, false)],
            );
            assert_matches_oracle(&ir, 2, 8, false, &[vw(8, 0xAB), vw(8, 0xAB)]);
            assert_matches_oracle(&ir, 2, 8, false, &[vw(8, 0xAB), vw(8, 0xAC)]);
            // any X in either ⇒ X result for ==/!=.
            assert_matches_oracle(&ir, 2, 8, false, &[vw_xz(8, 0xAB, 1), vw(8, 0xAB)]);
        }
        for op in [BinOp::CaseEq, BinOp::CaseNe] {
            let ir = ir_of(
                vec![sig(0), sig(1), bin(op, 0, 1)],
                vec![],
                vec![nv(8, false), nv(8, false)],
            );
            // === compares X positions literally: matching X ⇒ equal, never X.
            assert_matches_oracle(
                &ir,
                2,
                8,
                false,
                &[vw_xz(8, 0xA0, 0xF), vw_xz(8, 0xA0, 0xF)],
            );
            assert_matches_oracle(&ir, 2, 8, false, &[vw_xz(8, 0xA0, 0xF), vw(8, 0xA0)]);
        }
    }

    #[test]
    fn shifts_match_oracle() {
        for op in [BinOp::Shl, BinOp::Shr, BinOp::AShr] {
            let ir = ir_of(
                vec![sig(0), sig(1), bin(op, 0, 1)],
                vec![],
                vec![nv(16, true), nv(8, false)],
            );
            for (x, amt) in [
                (0x8001u64, 0u64),
                (0x8001, 3),
                (0x8001, 15),
                (0x8001, 16), // == width: everything out / full sign fill
                (0x8001, 200),
                (0x7001, 4),
            ] {
                assert_matches_oracle(&ir, 2, 16, false, &[vws(16, x), vw(8, amt)]);
                // signed enclosing context too (AShr fill follows lhs OWN sign).
                assert_matches_oracle(&ir, 2, 16, true, &[vws(16, x), vw(8, amt)]);
            }
            // X/Z amount poisons; X MSB on AShr fills X.
            assert_matches_oracle(&ir, 2, 16, false, &[vws(16, 0x8001), vw_xz(8, 2, 1)]);
            assert_matches_oracle(&ir, 2, 16, false, &[vw_xz(16, 1, 1 << 15), vw(8, 3)]);
        }
    }

    #[test]
    fn div_mod_match_oracle() {
        for op in [BinOp::Div, BinOp::Mod] {
            // UNSIGNED
            let ir = ir_of(
                vec![sig(0), sig(1), bin(op, 0, 1)],
                vec![],
                vec![nv(16, false), nv(16, false)],
            );
            for (a, b) in [(100u64, 7u64), (7, 100), (0xFFFF, 3), (5, 0)] {
                assert_matches_oracle(&ir, 2, 16, false, &[vw(16, a), vw(16, b)]);
            }
            assert_matches_oracle(&ir, 2, 16, false, &[vw_xz(16, 9, 1), vw(16, 3)]);
            // SIGNED: truncating toward zero (-7/2 = -3, -7%2 = -1).
            let irs = ir_of(
                vec![sig(0), sig(1), bin(op, 0, 1)],
                vec![],
                vec![nv(16, true), nv(16, true)],
            );
            for (a, b) in [(0xFFF9u64, 2u64), (7, 0xFFFE), (0xFFF9, 0xFFFE), (5, 0)] {
                assert_matches_oracle(&irs, 2, 16, true, &[vws(16, a), vws(16, b)]);
            }
        }
    }

    #[test]
    fn ternary_matches_oracle() {
        // exprs: 0=cond sig2, 1=sig0, 2=sig1, 3 = cond ? sig0 : sig1
        let ir = ir_of(
            vec![
                sig(2),
                sig(0),
                sig(1),
                Expr::Ternary {
                    cond: 0,
                    then_e: 1,
                    else_e: 2,
                },
            ],
            vec![],
            vec![nv(8, false), nv(8, false), nv(1, false)],
        );
        let (t, e) = (vw(8, 0xAA), vw(8, 0xAC));
        assert_matches_oracle(&ir, 3, 8, false, &[t.clone(), e.clone(), vw(1, 1)]);
        assert_matches_oracle(&ir, 3, 8, false, &[t.clone(), e.clone(), vw(1, 0)]);
        // X cond ⇒ bitwise merge: agreeing bits pass, differing become X.
        assert_matches_oracle(&ir, 3, 8, false, &[t.clone(), e.clone(), vw_xz(1, 0, 1)]);
        // merge where branches carry X themselves.
        assert_matches_oracle(
            &ir,
            3,
            8,
            false,
            &[vw_xz(8, 0xA0, 3), vw_xz(8, 0xA0, 3), vw_xz(1, 0, 1)],
        );
    }

    #[test]
    fn reductions_and_lognot_match_oracle() {
        for op in [
            UnOp::RedAnd,
            UnOp::RedNand,
            UnOp::RedOr,
            UnOp::RedNor,
            UnOp::RedXor,
            UnOp::RedXnor,
            UnOp::LogNot,
        ] {
            let ir = ir_of(vec![sig(0), un(op, 0)], vec![], vec![nv(8, false)]);
            for v in [
                vw(8, 0xFF),
                vw(8, 0x00),
                vw(8, 0b1010_0110),
                vw_xz(8, 0xFF, 0b1), // X with otherwise-all-1 (AND → X, OR → 1)
                vw_xz(8, 0x00, 0b1000), // X with otherwise-all-0 (OR → X, AND → 0)
            ] {
                assert_matches_oracle(&ir, 1, 8, false, &[v.clone()]);
            }
        }
    }

    #[test]
    fn logical_and_or_match_oracle() {
        for op in [BinOp::LogAnd, BinOp::LogOr] {
            let ir = ir_of(
                vec![sig(0), sig(1), bin(op, 0, 1)],
                vec![],
                vec![nv(8, false), nv(8, false)],
            );
            for (a, b) in [
                (vw(8, 5), vw(8, 9)),             // T,T
                (vw(8, 0), vw(8, 9)),             // F,T
                (vw(8, 5), vw(8, 0)),             // T,F
                (vw(8, 0), vw(8, 0)),             // F,F
                (vw_xz(8, 0, 1), vw(8, 9)),       // X,T
                (vw_xz(8, 0, 1), vw(8, 0)),       // X,F
                (vw_xz(8, 0, 1), vw_xz(8, 0, 2)), // X,X
                (vw_xz(8, 2, 1), vw(8, 0)),       // definite-1 + X bit = TRUE, F
            ] {
                assert_matches_oracle(&ir, 2, 8, false, &[a.clone(), b.clone()]);
            }
        }
    }

    #[test]
    fn comparison_of_arith_results_matches_oracle() {
        // (s0 + s1) < (s2 * s3) — comparison over native sub-trees.
        let ir = ir_of(
            vec![
                sig(0),
                sig(1),
                bin(BinOp::Add, 0, 1),
                sig(2),
                sig(3),
                bin(BinOp::Mul, 3, 4),
                bin(BinOp::Lt, 2, 5),
            ],
            vec![],
            vec![nv(16, false); 4],
        );
        assert_matches_oracle(
            &ir,
            6,
            8,
            false,
            &[vw(16, 100), vw(16, 200), vw(16, 20), vw(16, 14)],
        );
        assert_matches_oracle(
            &ir,
            6,
            8,
            false,
            &[vw(16, 1000), vw(16, 2000), vw(16, 2), vw(16, 3)],
        );
    }
}
