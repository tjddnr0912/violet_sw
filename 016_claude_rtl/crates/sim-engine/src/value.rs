//! Runtime 4-state value + the per-bit IEEE-1364 truth-table primitives.
//!
//! Encoding (canonical, identical to `sim_ir::BitPacked` and `vcd-writer`):
//! per-bit two planes `(v,u)`: `(0,0)=0`, `(1,0)=1`, `(0,1)=X`, `(1,1)=Z`.
//! word0 bit0 = LSB. This is load-bearing — a `Value` round-trips to the VCD
//! writer for free via [`Value::into_bitpacked`].
//!
//! Z is treated as X in every operator except `===`/`!==` (and net storage);
//! the per-bit primitives below state their tables over `{0,1,X}` and a Z input
//! (`(1,1)`) folds to X because it has `u=1`.

use sim_ir::BitPacked;

#[inline]
pub(crate) fn nwords(width: u32) -> usize {
    ((width as usize) + 63) / 64
}

/// Mask of valid bits in the most-significant word (handles `width % 64 == 0`).
#[inline]
pub(crate) fn top_mask(width: u32) -> u64 {
    let r = width % 64;
    if width == 0 {
        0
    } else if r == 0 {
        u64::MAX
    } else {
        (1u64 << r) - 1
    }
}

/// A runtime 4-state vector. `val`/`unk` are bit-parallel planes, word0 bit0 =
/// LSB, identical encoding to `sim_ir::BitPacked`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Value {
    pub val: Vec<u64>,
    pub unk: Vec<u64>,
    pub width: u32,
    /// Result signedness (drives sign-extension, `>>>`, relational, `$signed`).
    pub signed: bool,
    /// When true, `val[0]` is `f64::to_bits(x)` and this Value is an IEEE-754
    /// real (64-bit, 2-state, `unk == [0]`). All 4-state paths keep this false.
    pub is_real: bool,
}

impl Value {
    pub fn zeros(width: u32, signed: bool) -> Self {
        let n = nwords(width).max(1);
        Value {
            val: vec![0; n],
            unk: vec![0; n],
            width,
            signed,
            is_real: false,
        }
    }

    /// All-X of a given width (the canonical "poison" for arith/relational when
    /// an operand has any X/Z).
    pub fn xs(width: u32, signed: bool) -> Self {
        let n = nwords(width).max(1);
        let mut v = Value {
            val: vec![0; n],
            unk: vec![u64::MAX; n],
            width,
            signed,
            is_real: false,
        };
        v.mask_top();
        v
    }

    pub fn one1() -> Self {
        let mut v = Value::zeros(1, false);
        v.val[0] = 1;
        v
    }

    pub fn x1() -> Self {
        let mut v = Value::zeros(1, false);
        v.unk[0] = 1; // (v=0,u=1) = X
        v
    }

    pub fn logic(b: bool) -> Self {
        if b {
            Value::one1()
        } else {
            Value::zeros(1, false)
        }
    }

    /// Build a `Value` from a `BitPacked` of the given width (net/const read).
    pub fn from_packed(b: &BitPacked, width: u32, signed: bool) -> Self {
        let n = nwords(width).max(1);
        let mut val = b.val.clone();
        let mut unk = b.unk.clone();
        val.resize(n, 0);
        unk.resize(n, 0);
        let mut v = Value {
            val,
            unk,
            width,
            signed,
            is_real: false,
        };
        v.mask_top();
        v
    }

    /// Clear bits above `width` in the top word (keep planes canonical).
    pub(crate) fn mask_top(&mut self) {
        if self.is_real {
            return; // a real is 64 IEEE bits; never bit-mask (would corrupt it).
        }
        let n = nwords(self.width).max(1);
        self.val.resize(n, 0);
        self.unk.resize(n, 0);
        let m = top_mask(self.width);
        if let Some(last) = self.val.get_mut(n - 1) {
            *last &= m;
        }
        if let Some(last) = self.unk.get_mut(n - 1) {
            *last &= m;
        }
    }

    #[inline]
    pub fn get_vu(&self, i: u32) -> (u64, u64) {
        let w = (i / 64) as usize;
        let s = i % 64;
        let v = self.val.get(w).map_or(0, |x| (x >> s) & 1);
        let u = self.unk.get(w).map_or(0, |x| (x >> s) & 1);
        (v, u)
    }

    #[inline]
    pub fn set_vu(&mut self, i: u32, v: u64, u: u64) {
        let w = (i / 64) as usize;
        let s = i % 64;
        if w >= self.val.len() {
            self.val.resize(w + 1, 0);
            self.unk.resize(w + 1, 0);
        }
        self.val[w] = (self.val[w] & !(1 << s)) | ((v & 1) << s);
        self.unk[w] = (self.unk[w] & !(1 << s)) | ((u & 1) << s);
    }

    /// Any X/Z anywhere within width? Drives arith/relational/`==` poisoning.
    pub fn has_xz(&self) -> bool {
        let n = nwords(self.width);
        for w in 0..n {
            let mask = if w == n - 1 {
                top_mask(self.width)
            } else {
                u64::MAX
            };
            if self.unk.get(w).copied().unwrap_or(0) & mask != 0 {
                return true;
            }
        }
        false
    }

    /// Clean integer of the low 64 bits; `None` if any X/Z (caller poisons).
    /// v1: arithmetic is a 64-bit lane (documented limitation).
    pub fn to_u64(&self) -> Option<u64> {
        if self.has_xz() {
            return None;
        }
        Some(self.val.first().copied().unwrap_or(0) & low_mask(self.width))
    }

    /// Clean integer of the low 128 bits; `None` if any X/Z. Widens the unsigned
    /// arithmetic lane from 64 to 128 bits (so a `[127:0]` add carries correctly).
    pub fn to_u128(&self) -> Option<u128> {
        if self.has_xz() {
            return None;
        }
        let lo = self.val.first().copied().unwrap_or(0) as u128;
        let hi = self.val.get(1).copied().unwrap_or(0) as u128;
        let raw = lo | (hi << 64);
        if self.width >= 128 {
            Some(raw)
        } else {
            Some(raw & ((1u128 << self.width) - 1))
        }
    }

    /// Sign-aware i128 view of the low bits (for signed arith/relational).
    pub fn to_i128_signed(&self) -> Option<i128> {
        let u = self.to_u64()? as i128;
        if self.signed && self.width >= 1 && self.width <= 64 {
            let sign = (self.val.first().copied().unwrap_or(0) >> (self.width - 1)) & 1;
            if sign == 1 {
                return Some(u - (1i128 << self.width));
            }
        }
        Some(u)
    }

    /// Pack into a `BitPacked` of `out_width`, zero/sign-/X-extending or
    /// truncating. Bridge to net writes and the VCD writer.
    pub fn into_bitpacked(self, out_width: u32) -> BitPacked {
        let r = self.resize(out_width);
        BitPacked {
            val: r.val,
            unk: r.unk,
        }
    }

    /// Resize to `new_width`: signed → sign-extend the MSB *bit value* (X MSB →
    /// X fill); unsigned → zero-extend; shrink → truncate.
    pub fn resize(mut self, new_width: u32) -> Value {
        if self.is_real {
            return self; // a real is dimensionless 64-bit; width context is a no-op.
        }
        if new_width == self.width {
            self.mask_top();
            return self;
        }
        let mut out = Value::zeros(new_width, self.signed);
        let copy = self.width.min(new_width);
        for i in 0..copy {
            let (v, u) = self.get_vu(i);
            out.set_vu(i, v, u);
        }
        if new_width > self.width {
            let (fv, fu) = if self.signed && self.width > 0 {
                self.get_vu(self.width - 1)
            } else {
                (0, 0)
            };
            for i in self.width..new_width {
                out.set_vu(i, fv, fu);
            }
        }
        out.mask_top();
        out
    }

    /// `resize` but extension policy follows the *combined* signedness (only
    /// sign-extend when context-signed, per IEEE 1364-2001 §4.5).
    pub fn resize_keep_sign(mut self, w: u32, ctx_signed: bool) -> Value {
        if self.is_real {
            return self; // FIRST: before any `.signed` mutation — a real is width/sign-free.
        }
        self.signed = self.signed && ctx_signed;
        let mut out = self.resize(w);
        out.signed = ctx_signed;
        out
    }

    /// Build a real Value from an f64. width=64, signed=true, unk=0, is_real.
    pub fn from_f64(x: f64) -> Value {
        Value {
            val: vec![x.to_bits()],
            unk: vec![0],
            width: 64,
            signed: true,
            is_real: true,
        }
    }

    /// Decode to f64. If already real, reinterpret val[0]. Otherwise coerce the
    /// 4-state integer value to f64 (IEEE 1364 §4.3 int→real promotion), honoring
    /// signedness. Returns None only if an integer operand is X/Z (caller decides
    /// poison vs 0.0).
    pub fn to_f64(&self) -> Option<f64> {
        if self.is_real {
            return Some(f64::from_bits(self.val[0]));
        }
        if self.has_xz() {
            return None;
        }
        if self.signed {
            self.to_i128_signed().map(|i| i as f64)
        } else {
            self.to_u64().map(|u| u as f64)
        }
    }

    /// Build an INTEGER (is_real=false) Value of `width` bits from an i128,
    /// masked to width with two's-complement wrap. Constructor the real→int
    /// coercion and `$rtoi` need. Keeps the low `width` bits of `i`'s two's-
    /// complement image; `signed` only stamps the result's sign flag.
    pub fn from_i128(i: i128, width: u32, signed: bool) -> Value {
        let mut v = Value::zeros(width.max(1), signed);
        let bits = i as u128; // reinterpret two's-complement bit image
        let words = (width as usize).div_ceil(64);
        for w in 0..words.min(v.val.len()) {
            v.val[w] = (bits >> (w * 64)) as u64;
        }
        v.width = width;
        v.mask_top(); // is_real=false so mask_top applies (clears bits above width)
        v
    }
}

/// real → int assignment coercion: ROUND half-away-from-zero, then build an
/// integer Value masked to the target width. Saturation/NaN handling: large |x|
/// saturates to i128 extremes; NaN.round() as i128 == 0.
pub(crate) fn real_to_int_round(x: f64, width: u32, signed: bool) -> Value {
    let r = x.round(); // Rust f64::round = round-half-away-from-zero
    let i = r as i128; // large |x| SATURATES to i128 extremes; NaN → 0
    Value::from_i128(i, width, signed)
}

/// Low mask over `width` bits in a single u64 (width ≤ 64 usage).
#[inline]
pub(crate) fn low_mask(width: u32) -> u64 {
    if width >= 64 {
        u64::MAX
    } else if width == 0 {
        0
    } else {
        (1u64 << width) - 1
    }
}

// ── per-bit 4-state primitives (the truth tables, explicit) ────────────────

/// One-bit AND: any definite 0 → 0; both definite 1 → 1; else (x/z, no 0) → X.
#[inline]
pub(crate) fn and1(a: (u64, u64), b: (u64, u64)) -> (u64, u64) {
    let a0 = a.1 == 0 && a.0 == 0;
    let b0 = b.1 == 0 && b.0 == 0;
    if a0 || b0 {
        return (0, 0);
    }
    if a.1 != 0 || b.1 != 0 {
        return (0, 1);
    }
    (1, 0)
}

/// One-bit OR: any definite 1 → 1; both definite 0 → 0; else (x/z, no 1) → X.
#[inline]
pub(crate) fn or1(a: (u64, u64), b: (u64, u64)) -> (u64, u64) {
    let a1 = a.1 == 0 && a.0 == 1;
    let b1 = b.1 == 0 && b.0 == 1;
    if a1 || b1 {
        return (1, 0);
    }
    if a.1 != 0 || b.1 != 0 {
        return (0, 1);
    }
    (0, 0)
}

/// One-bit XOR: any x/z operand → X; else val xor.
#[inline]
pub(crate) fn xor1(a: (u64, u64), b: (u64, u64)) -> (u64, u64) {
    if a.1 != 0 || b.1 != 0 {
        return (0, 1);
    }
    ((a.0 ^ b.0) & 1, 0)
}

/// One-bit NOT: ~x = x; ~0 = 1; ~1 = 0.
#[inline]
pub(crate) fn not1(a: (u64, u64)) -> (u64, u64) {
    if a.1 != 0 {
        return (0, 1);
    }
    ((!a.0) & 1, 0)
}

/// One-bit XNOR.
#[inline]
pub(crate) fn xnor1(a: (u64, u64), b: (u64, u64)) -> (u64, u64) {
    not1(xor1(a, b))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn and_or_xz_tables() {
        let zero = (0, 0);
        let one = (1, 0);
        let x = (0, 1);
        let z = (1, 1);
        // AND: 0&x=0, 1&x=x, x&x=x, 0&z=0
        assert_eq!(and1(zero, x), (0, 0));
        assert_eq!(and1(one, x), (0, 1));
        assert_eq!(and1(x, x), (0, 1));
        assert_eq!(and1(zero, z), (0, 0));
        assert_eq!(and1(one, one), (1, 0));
        // OR: 1|x=1, 0|x=x, x|x=x
        assert_eq!(or1(one, x), (1, 0));
        assert_eq!(or1(zero, x), (0, 1));
        assert_eq!(or1(x, x), (0, 1));
        assert_eq!(or1(zero, zero), (0, 0));
        // NOT
        assert_eq!(not1(x), (0, 1));
        assert_eq!(not1(zero), (1, 0));
        assert_eq!(not1(one), (0, 0));
    }

    #[test]
    fn resize_signext() {
        let mut v = Value::zeros(4, true);
        // 0b1000 = -8 as signed 4-bit
        v.set_vu(3, 1, 0);
        let w = v.resize(8);
        // sign-extend: bits 4..8 should be 1
        for i in 4..8 {
            assert_eq!(w.get_vu(i), (1, 0));
        }
    }

    #[test]
    fn packed_roundtrip() {
        let b = BitPacked {
            val: vec![0b1010],
            unk: vec![0b0100],
        };
        let v = Value::from_packed(&b, 4, false);
        assert_eq!(v.get_vu(1), (1, 0));
        assert_eq!(v.get_vu(2), (0, 1)); // X
        let back = v.into_bitpacked(4);
        assert_eq!(back.val[0] & 0xF, 0b1010);
        assert_eq!(back.unk[0] & 0xF, 0b0100);
    }
}
