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

use crate::value::{and1, low_mask, not1, or1, xnor1, xor1, Value};

/// A per-bit 4-state primitive: `(v,u) op (v,u) -> (v,u)`.
type BitOp = fn((u64, u64), (u64, u64)) -> (u64, u64);

/// Read-only net access the evaluator needs. The engine state implements it.
pub trait NetReader {
    /// Current 4-state value of net `net`, optional array word index.
    fn read_net(&self, net: u32, word: Option<u32>) -> Value;
}

/// Evaluation context: the IR (consts/exprs), the net table, and current time.
pub struct EvalCtx<'a, N: NetReader> {
    pub ir: &'a SimIr,
    pub nets: &'a N,
    pub now: u64,
}

impl<'a, N: NetReader> EvalCtx<'a, N> {
    pub fn eval(&self, eid: u32) -> Value {
        match &self.ir.exprs[eid as usize] {
            Expr::Const { val } => self.eval_const(*val),
            Expr::Signal { net, word } => self.nets.read_net(*net, *word),
            Expr::Select {
                base,
                offset,
                width,
                kind,
            } => self.eval_select(*base, *offset, *width, *kind),
            Expr::Concat { parts } => self.eval_concat(parts),
            Expr::Replicate { count, value } => self.eval_replicate(*count, *value),
            Expr::Unary { op, operand } => self.eval_unary(*op, *operand),
            Expr::Binary { op, lhs, rhs } => self.eval_binary(*op, *lhs, *rhs),
            Expr::Ternary {
                cond,
                then_e,
                else_e,
            } => self.eval_ternary(*cond, *then_e, *else_e),
            Expr::SysFunc { which, args } => self.eval_sysfunc(*which, args),
            // User functions deferred to v2; v1 returns 1-bit X.
            Expr::Call { .. } => Value::x1(),
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
        let signed = matches!(c.repr, ConstRepr::Numeric) && c.signed;
        Value::from_packed(&c.bits, c.width, signed)
    }

    // ── Unary ──────────────────────────────────────────────────────────────

    fn eval_unary(&self, op: UnOp, operand: u32) -> Value {
        let a = self.eval(operand);
        match op {
            UnOp::Plus => a,
            UnOp::Minus => self.negate(&a),
            UnOp::BitNot => {
                let mut r = Value::zeros(a.width, a.signed);
                for i in 0..a.width {
                    let (v, u) = not1(a.get_vu(i));
                    r.set_vu(i, v, u);
                }
                r
            }
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

    fn eval_binary(&self, op: BinOp, lhs: u32, rhs: u32) -> Value {
        use BinOp::*;
        let l = self.eval(lhs);
        let r = self.eval(rhs);
        match op {
            BitAnd => self.bitwise(&l, &r, and1),
            BitOr => self.bitwise(&l, &r, or1),
            BitXor => self.bitwise(&l, &r, xor1),
            BitXnor => self.bitwise(&l, &r, xnor1),
            LogAnd => self.log_and(&l, &r),
            LogOr => self.log_or(&l, &r),
            Add | Sub | Mul | Div | Mod | Pow => self.arith(op, &l, &r),
            Lt | Le | Gt | Ge => self.relational(op, &l, &r),
            Eq | Ne => self.log_eq(op, &l, &r),
            CaseEq | CaseNe => self.case_eq(op, &l, &r),
            Shl | AShl => self.shift_left(&l, &r),
            Shr => self.shift_right(&l, &r, false),
            AShr => self.shift_right(&l, &r, l.signed),
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
        let w = l.width.max(r.width).max(1);
        let both_signed = l.signed && r.signed;
        if l.has_xz() || r.has_xz() {
            return Value::xs(w, both_signed);
        }
        // v1 arithmetic is a 64-bit lane. For a SIGNED result wider than 64 bits
        // the sign reconstruction (`to_i128_signed` gates on width≤64) is unsafe —
        // `to_u64` would drop bits ≥64 and a negative would read as a large
        // positive, yielding a DEFINITE wrong number. Poison to X instead: an X is
        // an honest "unsupported", a silently mis-signed value is not. (Unsigned
        // width>64 also truncates to 64 bits — a documented lane limitation — but
        // it does not flip sign, so it is left as-is.)
        if both_signed && w > 64 {
            return Value::xs(w, true);
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
            let a = l.to_u64().unwrap() as u128;
            let b = r.to_u64().unwrap() as u128;
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
                BinOp::Pow => (a as u64).checked_pow(b as u32).unwrap_or(0) as u128,
                _ => unreachable!(),
            }
        };
        let mut out = Value::zeros(w, both_signed);
        out.val[0] = (res as u64) & low_mask(w);
        out.mask_top();
        out
    }

    fn relational(&self, op: BinOp, l: &Value, r: &Value) -> Value {
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

    fn eval_ternary(&self, cond: u32, then_e: u32, else_e: u32) -> Value {
        let c = self.eval(cond);
        match self.truthiness(&c) {
            Tri::True => self.eval(then_e),
            Tri::False => self.eval(else_e),
            Tri::Unknown => {
                let t = self.eval(then_e);
                let e = self.eval(else_e);
                let w = t.width.max(e.width);
                let te = t.resize(w);
                let ee = e.resize(w);
                let mut out = Value::zeros(w, te.signed && ee.signed);
                for i in 0..w {
                    let a = te.get_vu(i);
                    let b = ee.get_vu(i);
                    if a == b {
                        out.set_vu(i, a.0, a.1);
                    } else {
                        out.set_vu(i, 0, 1); // differ → X
                    }
                }
                out
            }
        }
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
            SysFuncId::Time | SysFuncId::Realtime => {
                let mut v = Value::zeros(64, false);
                v.val[0] = self.now;
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

    // ── helpers ────────────────────────────────────────────────────────────

    fn truthiness(&self, a: &Value) -> Tri {
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
