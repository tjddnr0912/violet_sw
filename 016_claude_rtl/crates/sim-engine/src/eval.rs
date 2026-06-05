//! 4-state expression evaluator. Evaluates a `sim_ir::Expr` (by ExprId into
//! `SimIr.exprs`) to a [`Value`], reading nets via [`NetReader`] and consts from
//! `SimIr.consts`. IEEE-1364 4-state semantics; Z is normalized to X in every
//! operator except `===`/`!==`.
//!
//! v1 simplifications (documented, IEEE-permitted):
//! - any X/Z in an arithmetic operand poisons the whole result to X;
//! - the integer arithmetic lane is 64-bit (wider vectors truncate the numeric
//!   result — bitwise/concat/select/shift remain full-width).

use sim_ir::{BinOp, ConstRepr, Expr, SelKind, SimIr, SysFuncId, UnOp};

use crate::value::{and1, low_mask, not1, nwords, or1, xnor1, xor1, Value};

/// A per-bit 4-state primitive: `(v,u) op (v,u) -> (v,u)`.
type BitOp = fn((u64, u64), (u64, u64)) -> (u64, u64);

/// Read-only net access the evaluator needs. The engine state implements it.
pub trait NetReader {
    /// Current 4-state value of net `net`, optional array word index.
    fn read_net(&self, net: u32, word: Option<u32>) -> Value;
}

/// Evaluation context: the IR (consts/exprs), the net table, current time, and
/// the self-width side table that drives context-determined sizing.
pub struct EvalCtx<'a, N: NetReader> {
    pub ir: &'a SimIr,
    pub nets: &'a N,
    pub now: u64,
    pub wt: &'a crate::width::WidthTable,
    /// Time multiplier `M` of the process whose expression is being evaluated
    /// (`$time = now / M`, `$realtime = now / M` real). 1 ⇒ the 1ns/1ns base.
    pub time_mult: u64,
}

impl<'a, N: NetReader> EvalCtx<'a, N> {
    /// Self-determined eval: size the node to its own self-width. Unchanged
    /// public surface; used by control-flow truthiness and systask args.
    pub fn eval(&self, eid: u32) -> Value {
        let sw = self.wt.get(eid);
        self.eval_ctx(eid, sw.width, sw.signed)
    }

    /// Evaluate `eid` in a context of at least `ctx_width` bits with context
    /// signedness `ctx_signed`. Returns a Value of width
    /// `max(self_width, ctx_width)`.
    ///
    /// CONTRACT:
    /// - context-determined nodes propagate `(max_width, AND-reduced signed)`
    ///   DOWN into their context-determined children (IEEE §5.4.1, §5.5.1);
    /// - self-determined nodes evaluate their children at the children's OWN
    ///   self-widths, produce the node's natural result, then resize the RESULT
    ///   to `ctx_width` using `ctx_signed` for the extension choice.
    pub fn eval_ctx(&self, eid: u32, ctx_width: u32, ctx_signed: bool) -> Value {
        let self_sw = self.wt.get(eid);
        // The evaluation width for THIS node and its context-determined children.
        let w = self_sw.width.max(ctx_width);
        // The global-unsigned rule (§5.5.1): once ANY operand in the
        // context-determined region is unsigned, the whole region is unsigned.
        // `eff_signed` = node self-signedness AND the context signedness.
        let eff_signed = self_sw.signed && ctx_signed;

        match &self.ir.exprs[eid as usize] {
            // ── leaves: read, then resize to `w` with eff_signed ───────────
            Expr::Const { val } => {
                let base = self.eval_const(*val);
                base.resize_keep_sign(w, eff_signed)
            }
            Expr::Signal { net, word } => {
                // `word` is an ExprId (the array index expr), evaluated NOW so a
                // runtime `mem[k]` selects the right element. None ⇒ scalar/whole.
                // An X/Z index (`to_u64` → None) maps to the `u32::MAX` out-of-range
                // sentinel → `net_word_packed` returns all-X — NOT a silent read of
                // word 0. Symmetric with the write side (`resolve_lvalue_offsets`).
                let widx = word.map(|weid| {
                    self.eval(weid)
                        .to_u64()
                        .map(|v| v as u32)
                        .unwrap_or(u32::MAX)
                });
                let base = self.nets.read_net(*net, widx);
                base.resize_keep_sign(w, eff_signed)
            }

            // ── unary ──────────────────────────────────────────────────────
            Expr::Unary { op, operand } => match op {
                // context-determined unary: propagate (w, eff_signed) into operand,
                // operate at w, result already w-wide.
                UnOp::Plus => self.eval_ctx(*operand, w, eff_signed),
                UnOp::Minus => {
                    let a = self.eval_ctx(*operand, w, eff_signed);
                    self.negate(&a) // width-preserving, stays `w`
                }
                UnOp::BitNot => {
                    let a = self.eval_ctx(*operand, w, eff_signed);
                    let mut r = Value::zeros(a.width, eff_signed);
                    for k in 0..a.width {
                        let (v, u) = not1(a.get_vu(k));
                        r.set_vu(k, v, u);
                    }
                    r
                }
                // reductions + lognot: SELF-DETERMINED operand, 1-bit result,
                // then zero-extend to `w` (= self_width(1).max(ctx_width), always
                // unsigned).
                UnOp::LogNot
                | UnOp::RedAnd
                | UnOp::RedNand
                | UnOp::RedOr
                | UnOp::RedNor
                | UnOp::RedXor
                | UnOp::RedXnor => {
                    let bit = self.eval_unary_self(*op, *operand); // 1-bit
                    bit.resize_keep_sign(w, false) // zero-extend
                }
            },

            // ── binary ─────────────────────────────────────────────────────
            Expr::Binary { op, lhs, rhs } => self.eval_binary_ctx(*op, *lhs, *rhs, w, eff_signed),

            // ── ternary: cond self-determined; branches context-determined ──
            Expr::Ternary {
                cond,
                then_e,
                else_e,
            } => match self.truthiness(&self.eval(*cond)) {
                Tri::True => self.eval_ctx(*then_e, w, eff_signed),
                Tri::False => self.eval_ctx(*else_e, w, eff_signed),
                Tri::Unknown => {
                    // both branches at (w, eff_signed); merge differing→X.
                    let t = self.eval_ctx(*then_e, w, eff_signed);
                    let e = self.eval_ctx(*else_e, w, eff_signed);
                    self.merge_x(&t, &e, w, eff_signed)
                }
            },

            // ── SELF-DETERMINED structural / select: eval natural, resize ──
            Expr::Concat { parts } => {
                let nat = self.eval_concat(parts); // sum of self-widths
                nat.resize_keep_sign(w, false) // concat unsigned
            }
            Expr::Replicate { count, value } => {
                let nat = self.eval_replicate(*count, *value);
                nat.resize_keep_sign(w, false) // replicate unsigned
            }
            Expr::Select {
                base,
                offset,
                width,
                kind,
            } => {
                let nat = self.eval_select(*base, *offset, *width, *kind); // unsigned
                nat.resize_keep_sign(w, false) // select unsigned
            }

            // ── system functions ───────────────────────────────────────────
            Expr::SysFunc { which, args } => self.eval_sysfunc_ctx(*which, args, w, eff_signed),

            // ── user call: 1-bit X (v1), extend to `w` (= 1.max(ctx_width)) ──
            // elaborate v1 NEVER emits `Expr::Call`; defensive/unreachable arm.
            Expr::Call { .. } => Value::x1().resize_keep_sign(w, false),
        }
    }

    /// Verilog truthiness of an expression: any definite-1 → true, all
    /// definite-0 → false, else (some x/z, no definite 1) → unknown.
    pub fn truthy(&self, eid: u32) -> bool {
        // X/Z is "false" for control flow (`if(x)` takes else). For logical
        // operators we use the tri-valued helper instead.
        matches!(self.truthiness(&self.eval(eid)), Tri::True)
    }

    fn eval_const(&self, cid: u32) -> Value {
        let c = &self.ir.consts[cid as usize];
        if matches!(c.repr, ConstRepr::Real) {
            // val[0] already holds f64::to_bits; reinterpret as real.
            return Value::from_f64(f64::from_bits(c.bits.val.first().copied().unwrap_or(0)));
        }
        let signed = matches!(c.repr, ConstRepr::Numeric) && c.signed;
        Value::from_packed(&c.bits, c.width, signed)
    }

    // ── Unary ──────────────────────────────────────────────────────────────

    /// 1-bit reduction/lognot result for a self-determined operand.
    fn eval_unary_self(&self, op: UnOp, operand: u32) -> Value {
        let a = self.eval(operand); // OWN self width
        match op {
            UnOp::LogNot => match self.truthiness(&a) {
                Tri::True => Value::zeros(1, false),
                Tri::False => Value::one1(),
                Tri::Unknown => Value::x1(),
            },
            UnOp::RedAnd => self.reduce(&a, and1),
            UnOp::RedNand => self.reduce_not(&a, and1),
            UnOp::RedOr => self.reduce(&a, or1),
            UnOp::RedNor => self.reduce_not(&a, or1),
            UnOp::RedXor => self.reduce(&a, xor1),
            UnOp::RedXnor => self.reduce_not(&a, xor1),
            _ => unreachable!("eval_unary_self only for reductions/lognot"),
        }
    }

    fn reduce(&self, a: &Value, f: BitOp) -> Value {
        if a.width == 0 {
            return Value::zeros(1, false);
        }
        let mut acc = a.get_vu(0);
        for i in 1..a.width {
            acc = f(acc, a.get_vu(i));
        }
        let mut r = Value::zeros(1, false);
        r.set_vu(0, acc.0, acc.1);
        r
    }

    fn reduce_not(&self, a: &Value, f: BitOp) -> Value {
        let red = self.reduce(a, f);
        let (v, u) = not1(red.get_vu(0));
        let mut r = Value::zeros(1, false);
        r.set_vu(0, v, u);
        r
    }

    fn negate(&self, a: &Value) -> Value {
        if a.is_real {
            // unwrap_or(0.0): on a real, to_f64 always returns Some, but we keep
            // the same unwrap policy everywhere to avoid a latent panic surface.
            return Value::from_f64(-a.to_f64().unwrap_or(0.0));
        }
        if a.has_xz() {
            return Value::xs(a.width, a.signed);
        }
        let m = low_mask(a.width);
        let r = (!a.val.first().copied().unwrap_or(0)).wrapping_add(1) & m;
        let mut out = Value::zeros(a.width, a.signed);
        out.val[0] = r;
        out.mask_top();
        out
    }

    // ── Binary ─────────────────────────────────────────────────────────────

    /// Context-routed binary dispatch. `w` is the already-resolved eval width
    /// (= self_width.max(ctx_width)); the comparison/logical arms zero-extend
    /// their 1-bit result to `w` (= 1.max(ctx_width)).
    fn eval_binary_ctx(&self, op: BinOp, lhs: u32, rhs: u32, w: u32, eff_signed: bool) -> Value {
        use BinOp::*;
        match op {
            // ARITHMETIC — context-determined: BOTH operands sized to
            // (w, eff_signed), op at width w.
            Add | Sub | Mul | Div | Mod => {
                let l = self.eval_ctx(lhs, w, eff_signed);
                let r = self.eval_ctx(rhs, w, eff_signed);
                self.arith(op, &l, &r) // operates at max(l.w,r.w)=w
            }

            // POWER — base is context-determined; EXPONENT is SELF-DETERMINED.
            // `**` is signed iff the BASE is signed. The incoming `eff_signed`
            // (= base.self_signed AND ctx_signed) is already the base's effective
            // sign — the exponent never entered it. Evaluate the base in context;
            // the exponent is self-determined and its sign is restamped to the
            // base's so `arith`'s both-signed reduction follows the base.
            Pow => {
                let base = self.eval_ctx(lhs, w, eff_signed);
                let mut exp = self.eval(rhs);
                exp.signed = base.signed;
                self.arith(op, &base, &exp) // result width = base width = w
            }

            // BITWISE — context-determined: BOTH operands sized to (w, eff_signed).
            BitAnd | BitOr | BitXor | BitXnor => {
                let l = self.eval_ctx(lhs, w, eff_signed);
                let r = self.eval_ctx(rhs, w, eff_signed);
                let f: BitOp = match op {
                    BitAnd => and1,
                    BitOr => or1,
                    BitXor => xor1,
                    BitXnor => xnor1,
                    _ => unreachable!("bitwise arm only handles BitAnd/Or/Xor/Xnor"),
                };
                self.bitwise(&l, &r, f)
            }

            // COMPARISONS / CASE-EQ — self-determined result (1-bit), but the two
            // operands are MUTUALLY context-determined: size each to
            // max(self_width(L), self_width(R)) with their pair-signedness. The
            // comparison does NOT inherit the enclosing ctx — this correctly stops
            // upward width/sign propagation.
            Lt | Le | Gt | Ge | Eq | Ne | CaseEq | CaseNe => {
                let cmp_w = self.wt.width(lhs).max(self.wt.width(rhs));
                let pair_signed = self.wt.signed(lhs) && self.wt.signed(rhs);
                let l = self.eval_ctx(lhs, cmp_w, pair_signed);
                let r = self.eval_ctx(rhs, cmp_w, pair_signed);
                let bit = match op {
                    CaseEq | CaseNe => self.case_eq(op, &l, &r),
                    Eq | Ne => self.log_eq(op, &l, &r),
                    _ => self.relational(op, &l, &r),
                };
                bit.resize_keep_sign(w, false) // zero-extend 1→w (= max(1,ctx))
            }

            // LOGICAL — self-determined operands, each reduced independently.
            LogAnd | LogOr => {
                let l = self.eval(lhs); // OWN self-width
                let r = self.eval(rhs);
                let bit = if matches!(op, LogAnd) {
                    self.log_and(&l, &r)
                } else {
                    self.log_or(&l, &r)
                };
                bit.resize_keep_sign(w, false) // = max(1, ctx)
            }

            // SHIFTS — LEFT operand is context-determined (result width = w);
            // RIGHT operand (amount) is SELF-DETERMINED (own width).
            Shl | AShl => {
                let l = self.eval_ctx(lhs, w, eff_signed); // widen LEFT FIRST
                let r = self.eval(rhs); // amount, own width
                let shifted = self.shift_left(&l, &r); // grows then we clamp
                shifted.resize_keep_sign(w, eff_signed) // back to ctx width
            }
            Shr => {
                let l = self.eval_ctx(lhs, w, eff_signed);
                let r = self.eval(rhs);
                self.shift_right(&l, &r, false) // logical, fill 0
            }
            // ARITHMETIC RIGHT SHIFT — the sign-fill is governed by the LEFT
            // operand's OWN self-signedness, NOT the enclosing context. An unsigned
            // enclosing context MUST NOT demote a genuinely-signed `s >>> n` to a
            // logical shift. Evaluate the LEFT operand with its OWN self-sign so its
            // MSB carries the true sign bit, and pass that same own-sign as the fill
            // flag; only AFTER shifting resize to the surrounding (w, eff_signed).
            AShr => {
                let lhs_signed = self.wt.signed(lhs); // OWN self-sign
                let l = self.eval_ctx(lhs, w, lhs_signed); // keep its OWN sign for fill MSB
                let r = self.eval(rhs);
                let shifted = self.shift_right(&l, &r, lhs_signed); // arith iff LEFT signed
                shifted.resize_keep_sign(w, eff_signed) // re-stamp to ctx sign
            }
        }
    }

    fn bitwise(&self, l: &Value, r: &Value, f: BitOp) -> Value {
        let w = l.width.max(r.width);
        let both_signed = l.signed && r.signed;
        let le = l.clone().resize_keep_sign(w, both_signed);
        let re = r.clone().resize_keep_sign(w, both_signed);
        let mut out = Value::zeros(w, both_signed);
        for i in 0..w {
            let (v, u) = f(le.get_vu(i), re.get_vu(i));
            out.set_vu(i, v, u);
        }
        out
    }

    fn arith(&self, op: BinOp, l: &Value, r: &Value) -> Value {
        if l.is_real || r.is_real {
            // IEEE 1364 §4.3: if either operand is real, the other promotes to real.
            // An X/Z integer entering a mixed real op decays to 0.0 (documented MVP
            // policy), never panics, never X-propagates.
            let a = l.to_f64().unwrap_or(0.0);
            let b = r.to_f64().unwrap_or(0.0);
            let res = match op {
                BinOp::Add => a + b,
                BinOp::Sub => a - b,
                BinOp::Mul => a * b,
                BinOp::Div => a / b, // f64: x/0 → ±inf, 0/0 → NaN; NOT X
                // `%` and `**` on a real are permanent illegalities gated at
                // elaborate (§6.2). Defensive NaN poison instead of unreachable!()
                // so a gate regression can never crash the simulator.
                BinOp::Mod => f64::NAN,
                BinOp::Pow => f64::NAN,
                _ => f64::NAN,
            };
            return Value::from_f64(res);
        }
        let w = l.width.max(r.width).max(1);
        let both_signed = l.signed && r.signed;
        if l.has_xz() || r.has_xz() {
            return Value::xs(w, both_signed);
        }
        // Arithmetic lane: 128 bits. SIGNED stays a 64-bit lane — sign
        // reconstruction (`to_i128_signed`) gates on width≤64, and a >64-bit signed
        // value would read mis-signed; poison to X (an honest "unsupported" beats a
        // silently wrong number). UNSIGNED now spans the full 128-bit u128 lane (so
        // a `[127:0]` add/mul carries past bit 63 correctly); only width>128 — beyond
        // the lane — poisons, mirroring the signed guard rather than truncating.
        if both_signed && w > 64 {
            return Value::xs(w, true);
        }
        if !both_signed && w > 128 {
            return Value::xs(w, false);
        }
        let res: u128 = if both_signed {
            let a = l
                .clone()
                .resize_keep_sign(w, true)
                .to_i128_signed()
                .unwrap();
            let b = r
                .clone()
                .resize_keep_sign(w, true)
                .to_i128_signed()
                .unwrap();
            match op {
                BinOp::Add => a.wrapping_add(b) as u128,
                BinOp::Sub => a.wrapping_sub(b) as u128,
                BinOp::Mul => a.wrapping_mul(b) as u128,
                BinOp::Div => {
                    if b == 0 {
                        return Value::xs(w, true);
                    }
                    a.wrapping_div(b) as u128
                }
                BinOp::Mod => {
                    if b == 0 {
                        return Value::xs(w, true);
                    }
                    a.wrapping_rem(b) as u128
                }
                BinOp::Pow => ipow_signed(a, b),
                _ => unreachable!(),
            }
        } else {
            let a = l.to_u128().unwrap();
            let b = r.to_u128().unwrap();
            match op {
                BinOp::Add => a.wrapping_add(b),
                BinOp::Sub => a.wrapping_sub(b),
                BinOp::Mul => a.wrapping_mul(b),
                BinOp::Div => {
                    if b == 0 {
                        return Value::xs(w, false);
                    }
                    a / b
                }
                BinOp::Mod => {
                    if b == 0 {
                        return Value::xs(w, false);
                    }
                    a % b
                }
                BinOp::Pow => a.checked_pow(b as u32).unwrap_or(0),
                _ => unreachable!(),
            }
        };
        // Store the low 128 bits across word 0 (and word 1 for w>64); `mask_top`
        // clears bits above `w`.
        let mut out = Value::zeros(w, both_signed);
        out.val[0] = res as u64;
        if nwords(w) > 1 {
            if out.val.len() < 2 {
                out.val.resize(2, 0);
            }
            out.val[1] = (res >> 64) as u64;
        }
        out.mask_top();
        out
    }

    fn relational(&self, op: BinOp, l: &Value, r: &Value) -> Value {
        if l.is_real || r.is_real {
            let a = l.to_f64().unwrap_or(0.0);
            let b = r.to_f64().unwrap_or(0.0);
            let bit = match (op, a.partial_cmp(&b)) {
                // partial_cmp is None on NaN → all ordered comparisons false (IEEE).
                (_, None) => false,
                (BinOp::Lt, Some(o)) => o == std::cmp::Ordering::Less,
                (BinOp::Le, Some(o)) => o != std::cmp::Ordering::Greater,
                (BinOp::Gt, Some(o)) => o == std::cmp::Ordering::Greater,
                (BinOp::Ge, Some(o)) => o != std::cmp::Ordering::Less,
                _ => unreachable!("relational only handles Lt/Le/Gt/Ge"),
            };
            return Value::logic(bit);
        }
        if l.has_xz() || r.has_xz() {
            return Value::x1();
        }
        let both_signed = l.signed && r.signed;
        let ord = if both_signed {
            l.clone()
                .to_i128_signed()
                .unwrap()
                .cmp(&r.clone().to_i128_signed().unwrap())
        } else {
            l.to_u64().unwrap().cmp(&r.to_u64().unwrap())
        };
        use std::cmp::Ordering::*;
        let b = matches!(
            (op, ord),
            (BinOp::Lt, Less)
                | (BinOp::Le, Less)
                | (BinOp::Le, Equal)
                | (BinOp::Gt, Greater)
                | (BinOp::Ge, Greater)
                | (BinOp::Ge, Equal)
        );
        Value::logic(b)
    }

    /// `==` / `!=`: any compared bit x/z → X; else bit-equality.
    ///
    /// Width unification follows IEEE 1364-2001 §4.5: the comparison is signed
    /// ONLY when BOTH operands are signed; if either is unsigned both operands
    /// zero-extend. Using `resize` (which honors each operand's *own* sign) would
    /// sign-extend a lone signed operand in an unsigned context and report a false
    /// match (e.g. `4'sb1111 == 8'hFF` → wrong `1`). `resize_keep_sign` clears the
    /// sign when the context is unsigned, so we zero-extend correctly.
    fn log_eq(&self, op: BinOp, l: &Value, r: &Value) -> Value {
        if l.is_real || r.is_real {
            let a = l.to_f64().unwrap_or(0.0);
            let b = r.to_f64().unwrap_or(0.0);
            // VALUE comparison: +0.0 == -0.0 is true; NaN != NaN.
            let eq = a == b;
            return Value::logic(if op == BinOp::Eq { eq } else { !eq });
        }
        let w = l.width.max(r.width);
        let ctx_signed = l.signed && r.signed;
        let le = l.clone().resize_keep_sign(w, ctx_signed);
        let re = r.clone().resize_keep_sign(w, ctx_signed);
        let mut diff = false;
        for i in 0..w {
            let (lv, lu) = le.get_vu(i);
            let (rv, ru) = re.get_vu(i);
            if lu != 0 || ru != 0 {
                return Value::x1();
            }
            if lv != rv {
                diff = true;
            }
        }
        let eq = !diff;
        Value::logic(if op == BinOp::Eq { eq } else { !eq })
    }

    /// `===` / `!==`: exact 4-state per-bit compare, never X. Width unification
    /// uses the same context-signedness rule as `==` (zero-extend unless BOTH
    /// signed) so a mixed-sign `===` matches IEEE numeric extension.
    fn case_eq(&self, op: BinOp, l: &Value, r: &Value) -> Value {
        if l.is_real || r.is_real {
            // MVP: === on real == VALUE equality. A real is 2-state, so === and ==
            // coincide; +0.0 === -0.0 is TRUE (value equal), NaN !== NaN.
            let a = l.to_f64().unwrap_or(0.0);
            let b = r.to_f64().unwrap_or(0.0);
            let eq = a == b;
            return Value::logic(if op == BinOp::CaseEq { eq } else { !eq });
        }
        let w = l.width.max(r.width);
        let ctx_signed = l.signed && r.signed;
        let le = l.clone().resize_keep_sign(w, ctx_signed);
        let re = r.clone().resize_keep_sign(w, ctx_signed);
        let mut eq = true;
        for i in 0..w {
            if le.get_vu(i) != re.get_vu(i) {
                eq = false;
                break;
            }
        }
        Value::logic(if op == BinOp::CaseEq { eq } else { !eq })
    }

    fn log_and(&self, l: &Value, r: &Value) -> Value {
        match (self.truthiness(l), self.truthiness(r)) {
            (Tri::False, _) | (_, Tri::False) => Value::zeros(1, false),
            (Tri::True, Tri::True) => Value::one1(),
            _ => Value::x1(),
        }
    }

    fn log_or(&self, l: &Value, r: &Value) -> Value {
        match (self.truthiness(l), self.truthiness(r)) {
            (Tri::True, _) | (_, Tri::True) => Value::one1(),
            (Tri::False, Tri::False) => Value::zeros(1, false),
            _ => Value::x1(),
        }
    }

    fn shift_left(&self, l: &Value, r: &Value) -> Value {
        let amt = match r.to_u64() {
            Some(a) => a,
            None => return Value::xs(l.width, l.signed),
        };
        // v1 has no context-determined width (elaborate defers expr sizing), so a
        // self-determined `<<` would truncate to `l.width` and drop bits that a
        // wider assignment context would keep (`4'b0001 << 5` → 0 instead of
        // `8'h20`). We GROW the result to `l.width + amt` so no bit is ever lost;
        // the enclosing `write_lvalue`/operator then truncates to the real LHS
        // width. This is lossless and matches any context at least that wide;
        // narrower contexts truncate identically either way. Cap the growth so a
        // pathological shift amount can't allocate unboundedly.
        let grow = (l.width as u64).saturating_add(amt).min(4096) as u32;
        let w = grow.max(l.width).max(1);
        let mut out = Value::zeros(w, l.signed);
        for i in 0..w {
            if (i as u64) >= amt {
                let src = i as u64 - amt;
                if src < l.width as u64 {
                    let (v, u) = l.get_vu(src as u32);
                    out.set_vu(i, v, u);
                }
            }
        }
        out
    }

    fn shift_right(&self, l: &Value, r: &Value, arith: bool) -> Value {
        let amt = match r.to_u64() {
            Some(a) => a,
            None => return Value::xs(l.width, l.signed),
        };
        let w = l.width;
        let (fv, fu) = if arith && w > 0 {
            l.get_vu(w - 1)
        } else {
            (0, 0)
        };
        let mut out = Value::zeros(w, l.signed);
        for i in 0..w {
            let src = i as u64 + amt;
            if src < w as u64 {
                let (v, u) = l.get_vu(src as u32);
                out.set_vu(i, v, u);
            } else {
                out.set_vu(i, fv, fu);
            }
        }
        out
    }

    // ── Ternary ────────────────────────────────────────────────────────────

    /// Merge two equal-width branches bit-by-bit: agreeing bits pass through,
    /// differing bits become X. Both `t`/`e` are already `w`-wide from
    /// `eval_ctx`, so no inner resize is needed (verbatim former eval_ternary
    /// unknown-branch body).
    fn merge_x(&self, t: &Value, e: &Value, w: u32, signed: bool) -> Value {
        let mut out = Value::zeros(w, signed);
        for k in 0..w {
            let a = t.get_vu(k);
            let b = e.get_vu(k);
            if a == b {
                out.set_vu(k, a.0, a.1);
            } else {
                out.set_vu(k, 0, 1); // differ → X
            }
        }
        out
    }

    // ── Concat / Replicate ─────────────────────────────────────────────────

    fn eval_concat(&self, parts: &[u32]) -> Value {
        let vals: Vec<Value> = parts.iter().map(|&p| self.eval(p)).collect();
        let total: u32 = vals.iter().map(|v| v.width).sum();
        let mut out = Value::zeros(total.max(1), false);
        out.width = total;
        // parts[0] is MSB-most; fill from the top down.
        let mut pos = total;
        for v in &vals {
            pos -= v.width;
            for i in 0..v.width {
                let (vv, uu) = v.get_vu(i);
                out.set_vu(pos + i, vv, uu);
            }
        }
        out.mask_top();
        out
    }

    fn eval_replicate(&self, count: u32, value: u32) -> Value {
        // `count` is an ExprId (frozen IR: Replicate.count is a const-expr edge),
        // NOT a literal — fold it to the repeat count, symmetric with the
        // self-width table (width.rs) and eval_select's width fold.
        let count = crate::width::const_u32_of_expr(self.ir, count).unwrap_or(0);
        let v = self.eval(value);
        let total = v.width.saturating_mul(count);
        let mut out = Value::zeros(total.max(1), false);
        out.width = total;
        for c in 0..count {
            let base = c * v.width;
            for i in 0..v.width {
                let (vv, uu) = v.get_vu(i);
                out.set_vu(base + i, vv, uu);
            }
        }
        out.mask_top();
        out
    }

    // ── Select ─────────────────────────────────────────────────────────────

    fn eval_select(&self, base: u32, offset: u32, width: u32, kind: SelKind) -> Value {
        // `width` is an ExprId (frozen IR: `Select.width` is a const-expr edge,
        // e.g. `Add(Sub(msb,lsb),1)`), NOT a literal bit count — fold it to its
        // value. `offset` stays an evaluated expr (it is the runtime index for
        // indexed `[base +: w]`/`[base -: w]` selects).
        let width = crate::width::const_u32_of_expr(self.ir, width).unwrap_or(1);
        let src = self.eval(base);
        let off_val = self.eval(offset);
        let off = match off_val.to_u64() {
            Some(o) => o as i64,
            None => return Value::xs(width.max(1), false),
        };
        let (lsb, w) = match kind {
            SelKind::Bit => (off, 1u32),
            SelKind::PartConst | SelKind::PartIdxUp => (off, width),
            SelKind::PartIdxDown => (off - (width as i64) + 1, width),
        };
        let mut out = Value::zeros(w.max(1), false);
        out.width = w;
        for i in 0..w as i64 {
            let src_idx = lsb + i;
            if src_idx >= 0 && (src_idx as u32) < src.width {
                let (v, u) = src.get_vu(src_idx as u32);
                out.set_vu(i as u32, v, u);
            } else {
                out.set_vu(i as u32, 0, 1); // out-of-range read → X
            }
        }
        out.mask_top();
        out
    }

    // ── SysFunc ────────────────────────────────────────────────────────────

    fn eval_sysfunc(&self, which: SysFuncId, args: &[u32]) -> Value {
        match which {
            SysFuncId::Time => {
                // $time: current time in the CALLING module's units, truncated to int
                // (now is global-precision ticks; divide by the module multiplier M).
                let m = self.time_mult.max(1);
                let mut v = Value::zeros(64, false);
                v.val[0] = self.now / m;
                v
            }
            SysFuncId::Realtime => {
                // $realtime: same as $time but keeping the sub-unit fraction.
                let m = self.time_mult.max(1) as f64;
                Value::from_f64(self.now as f64 / m)
            }
            SysFuncId::Rtoi => {
                // real → int, TRUNCATE toward zero. Result is a plain integer Value.
                let x = self.eval(args[0]).to_f64().unwrap_or(0.0);
                Value::from_i128(x.trunc() as i128, 32, true)
            }
            SysFuncId::Itor => {
                // int → real, exact convert.
                let i = self.eval(args[0]).to_i128_signed().unwrap_or(0);
                Value::from_f64(i as f64)
            }
            SysFuncId::RealToBits => {
                // real → 64-bit vector (raw IEEE bits). val[0] already holds
                // to_bits(); clear is_real so it reads as a plain 64-bit vector.
                let mut v = self.eval(args[0]);
                v.is_real = false;
                v.signed = false;
                v.width = 64;
                v
            }
            SysFuncId::BitsToReal => {
                // 64-bit vector → real. Same bits, set is_real. X/Z → NaN poison
                // (§6.2 "cannot convert X/Z to real") rather than a fabricated real.
                let src = self.eval(args[0]);
                if src.has_xz() {
                    return Value::from_f64(f64::NAN);
                }
                let mut v = src;
                v.is_real = true;
                v.signed = true;
                v.width = 64;
                v
            }
            SysFuncId::Signed => {
                let mut a = self.eval(args[0]);
                a.signed = true;
                a
            }
            SysFuncId::Unsigned => {
                let mut a = self.eval(args[0]);
                a.signed = false;
                a
            }
            SysFuncId::Clog2 => {
                let a = self.eval(args[0]);
                match a.to_u64() {
                    None => Value::xs(32, false),
                    Some(0) | Some(1) => Value::zeros(32, false),
                    Some(n) => {
                        let bits = 64 - (n - 1).leading_zeros();
                        let mut v = Value::zeros(32, false);
                        v.val[0] = bits as u64;
                        v
                    }
                }
            }
        }
    }

    /// `$signed`/`$unsigned`/`$time`/`$clog2` in context: cast preserves width
    /// but flips sign; $time/$clog2 produce a fixed-width value then extend.
    fn eval_sysfunc_ctx(&self, which: SysFuncId, args: &[u32], w: u32, eff_signed: bool) -> Value {
        match which {
            SysFuncId::Signed => {
                // operand at its OWN self width. `$signed` re-stamps it signed, but
                // the EXTENSION FILL is governed by `eff_signed` (= self-signed AND
                // ctx_signed), NOT the unconditional cast: under the global-unsigned
                // rule (§5.5.1) an unsigned sibling makes the whole region unsigned,
                // so `$signed(x)` must ZERO-extend there, not sign-extend. Setting
                // `.signed = eff_signed` BEFORE the resize makes the fill policy
                // unambiguously flag-driven.
                let mut a = self.eval(args[0]);
                a.signed = eff_signed;
                a.resize_keep_sign(w, eff_signed)
            }
            SysFuncId::Unsigned => {
                let mut a = self.eval(args[0]);
                a.signed = false;
                a.resize_keep_sign(w, false) // unsigned cast → zero-extend
            }
            // $time/$realtime (64-bit) and $clog2 (32-bit): natural value, then
            // resize to context (zero/sign per eff_signed).
            _ => self
                .eval_sysfunc(which, args)
                .resize_keep_sign(w, eff_signed),
        }
    }

    // ── helpers ────────────────────────────────────────────────────────────

    fn truthiness(&self, a: &Value) -> Tri {
        // A real is logically true iff it is != 0.0 (IEEE 1364: `-0.0 == 0.0`,
        // so both signed zeros are FALSE; NaN != 0.0 → truthy). Reinterpreting a
        // real's f64 bits as a 4-state vector would wrongly read `-0.0`
        // (sign bit set, value zero) as true in `if`/`!`/ternary/`&&`/`||`.
        if a.is_real {
            return if a.to_f64().unwrap_or(0.0) != 0.0 {
                Tri::True
            } else {
                Tri::False
            };
        }
        let mut any_unknown = false;
        for i in 0..a.width {
            let (v, u) = a.get_vu(i);
            if u == 0 && v == 1 {
                return Tri::True;
            }
            if u != 0 {
                any_unknown = true;
            }
        }
        if any_unknown {
            Tri::Unknown
        } else {
            Tri::False
        }
    }
}

enum Tri {
    True,
    False,
    Unknown,
}

fn ipow_signed(base: i128, exp: i128) -> u128 {
    if exp < 0 {
        // negative exponent on integers → 0 (except base==1 → 1, base==-1 → ±1)
        return match base {
            1 => 1,
            -1 => {
                if exp % 2 == 0 {
                    1
                } else {
                    (-1i128) as u128
                }
            }
            _ => 0,
        };
    }
    let mut acc: i128 = 1;
    let mut e = exp;
    let mut b = base;
    while e > 0 {
        if e & 1 == 1 {
            acc = acc.wrapping_mul(b);
        }
        b = b.wrapping_mul(b);
        e >>= 1;
    }
    acc as u128
}
