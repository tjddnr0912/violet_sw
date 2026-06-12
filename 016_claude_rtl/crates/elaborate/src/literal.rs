//! 4-state integer-literal parser (IEEE 1364-2005 §3.5 / §3.5.1).
//!
//! Lowers a verbatim IntLit lexeme (`raw`, including the apostrophe) into a
//! `sim_ir::ConstVal`. The two output planes follow the FROZEN encoding
//! `(v,u)`: `00→0`, `10→1`, `01→X`, `11→Z`; word0 bit0 = LSB.
//!
//! Forms handled (lexer-validated upstream — see hdl-lexer IntSized/
//! IntUnsizedBased/IntDecimal):
//!   `42`, `1_000`                         → Decimal, 32-bit signed
//!   `'b1101`, `'hFF`, `'sd9`              → UnsizedBased, 32-bit
//!   `8'hAB`, `4'b1010`, `4'sd5`           → Sized
//!   `8'b1010_xxxx`, `4'bx`, `8'hzz`       → x/z digits
//!   `'0 '1 'x 'z`                         → SV single-char fills (UnsizedBased)
//!   `?` is an alias for `z`.
//!
//! ## Sign/extension rule (§3.5.1 — decided and pinned here)
//! When the supplied digits yield fewer bits than `width`, the literal is
//! LEFT-extended to `width`. The extension bit is the *state* of the supplied
//! MSB: `x` → x-extend, `z` → z-extend, else (`0`/`1`) → **0**-extend. This is
//! NOT sign-extension — a `1` MSB never replicates. (Sign-extension into a wider
//! *expression context* is a separate concern handled at expr-context sizing,
//! deferred past v1.) Excess bits beyond `width` are truncated (MSBs dropped).

use hdl_ast::IntLitKind;
use sim_ir::{BitPacked, ConstRepr, ConstVal};

/// One parsed 4-state bit, in (val, unk) plane form.
#[derive(Clone, Copy)]
struct Bit {
    v: bool,
    u: bool,
}
const B0: Bit = Bit { v: false, u: false };
const B1: Bit = Bit { v: true, u: false };
const BX: Bit = Bit { v: false, u: true };
const BZ: Bit = Bit { v: true, u: true };

/// Pack an LSB-first `Bit` slice into `width` bits. Missing bits use `fill`;
/// bits beyond `width` are dropped. Result has `ceil(width/64)` words (≥1).
fn pack_bits(bits: &[Bit], width: u32, fill: Bit) -> BitPacked {
    let nwords = (((width as usize) + 63) / 64).max(1);
    let mut val = vec![0u64; nwords];
    let mut unk = vec![0u64; nwords];
    for i in 0..(width as usize) {
        let b = if i < bits.len() { bits[i] } else { fill };
        let w = i / 64;
        let off = i % 64;
        if b.v {
            val[w] |= 1u64 << off;
        }
        if b.u {
            unk[w] |= 1u64 << off;
        }
    }
    BitPacked { val, unk }
}

/// Map one based digit (`b`/`o`/`h`) to `k` LSB-first bits. `x`/`z`/`?` fill the
/// whole digit. Returns `None` for an out-of-radix digit.
fn digit_bits(c: char, base: u32) -> Option<Vec<Bit>> {
    let k = match base {
        2 => 1,
        8 => 3,
        16 => 4,
        _ => return None,
    };
    match c {
        'x' | 'X' => return Some(vec![BX; k]),
        'z' | 'Z' | '?' => return Some(vec![BZ; k]),
        _ => {}
    }
    let d = c.to_digit(base)?;
    let mut out = Vec::with_capacity(k);
    for i in 0..k {
        out.push(if (d >> i) & 1 == 1 { B1 } else { B0 });
    }
    Some(out)
}

/// Build the LSB-first bit vector for a based digit string (`b`/`o`/`h`).
fn based_bits(digits: &str, base: u32) -> Option<Vec<Bit>> {
    // Accumulate MSB-first (source order), then reverse to LSB-first.
    let mut msb_first: Vec<Bit> = Vec::new();
    for c in digits.chars() {
        let db = digit_bits(c, base)?;
        for b in db.iter().rev() {
            msb_first.push(*b);
        }
    }
    if msb_first.is_empty() {
        return None; // a based literal with no digits is malformed
    }
    msb_first.reverse();
    Some(msb_first)
}

/// Decimal magnitude → LSB-first bit vector (schoolbook base-10→binary, so it is
/// overflow-proof and width-agnostic). Returns `None` on a non-digit char.
fn decimal_bits(digits: &str) -> Option<Vec<Bit>> {
    let mut dividend: Vec<u8> = Vec::with_capacity(digits.len());
    for b in digits.bytes() {
        if !b.is_ascii_digit() {
            return None;
        }
        dividend.push(b - b'0');
    }
    if dividend.is_empty() {
        return None;
    }
    let mut bits: Vec<Bit> = Vec::new();
    while dividend.iter().any(|&d| d != 0) {
        let mut rem = 0u32;
        let mut quot: Vec<u8> = Vec::with_capacity(dividend.len());
        for &d in &dividend {
            let cur = rem * 10 + d as u32;
            quot.push((cur / 2) as u8);
            rem = cur % 2;
        }
        let first_nz = quot.iter().position(|&d| d != 0).unwrap_or(quot.len());
        dividend = quot[first_nz..].to_vec();
        bits.push(if rem == 1 { B1 } else { B0 });
    }
    if bits.is_empty() {
        bits.push(B0); // the value 0
    }
    Some(bits)
}

/// The extension bit per §3.5.1: x/z-extend if the supplied MSB is x/z, else 0.
fn ext_fill(bits: &[Bit]) -> Bit {
    match bits.last().copied().unwrap_or(B0) {
        Bit { v: false, u: true } => BX, // X
        Bit { v: true, u: true } => BZ,  // Z
        _ => B0,                         // 0 or 1 → zero-extend
    }
}

/// Parse a raw IntLit lexeme into a `ConstVal`. `None` ⇒ malformed (caller emits
/// a diagnostic and substitutes a zero const).
pub fn parse_int_literal(raw: &str, kind: IntLitKind) -> Option<ConstVal> {
    match kind {
        // ── plain decimal: 42 → 32-bit signed ──────────────────────────
        IntLitKind::Decimal => {
            let digits: String = raw.chars().filter(|&c| c != '_').collect();
            let bits = decimal_bits(&digits)?;
            let bits_packed = pack_bits(&bits, 32, B0);
            Some(ConstVal {
                width: 32,
                signed: true,
                repr: ConstRepr::Numeric,
                bits: bits_packed,
            })
        }

        // ── sized / unsized based: [W]'[s]B digits ─────────────────────
        IntLitKind::Sized | IntLitKind::UnsizedBased => {
            let tick = raw.find('\'')?;
            let size_part = &raw[..tick];
            let mut rest = raw[tick + 1..].chars().peekable();

            // optional signed marker
            let mut signed = false;
            if matches!(rest.peek(), Some('s') | Some('S')) {
                signed = true;
                rest.next();
            }

            // width: explicit for Sized; 32 for unsized (context sizing deferred).
            let width: u32 = if size_part.is_empty() {
                32
            } else {
                let sd: String = size_part.chars().filter(|&c| c != '_').collect();
                sd.parse::<u32>().ok()?
            };
            if width == 0 {
                return None;
            }

            let base_char = rest.peek().copied().unwrap_or('\0');
            let is_base = matches!(base_char, 'd' | 'D' | 'b' | 'B' | 'o' | 'O' | 'h' | 'H');

            if !is_base {
                // SV single-char fill: '0 '1 'x 'z (no base letter, no digits).
                let fill = match base_char {
                    '0' => B0,
                    '1' => B1,
                    'x' | 'X' => BX,
                    'z' | 'Z' | '?' => BZ,
                    _ => return None,
                };
                rest.next();
                if rest.next().is_some() {
                    return None; // trailing junk after a single fill char
                }
                return Some(ConstVal {
                    width,
                    signed,
                    repr: ConstRepr::Numeric,
                    bits: pack_bits(&[], width, fill),
                });
            }

            rest.next(); // consume base letter
            let digits: String = rest.filter(|&c| c != '_').collect();
            let base: u32 = match base_char {
                'd' | 'D' => 10,
                'b' | 'B' => 2,
                'o' | 'O' => 8,
                'h' | 'H' => 16,
                _ => return None,
            };

            let bits: Vec<Bit> = if base == 10 {
                // decimal-based: x/z legal ONLY as the whole single-token value.
                let lc = digits.to_ascii_lowercase();
                if lc == "x" {
                    vec![BX]
                } else if lc == "z" || lc == "?" {
                    vec![BZ]
                } else {
                    decimal_bits(&digits)?
                }
            } else {
                based_bits(&digits, base)?
            };

            let fill = ext_fill(&bits);
            Some(ConstVal {
                width,
                signed,
                repr: ConstRepr::Numeric,
                bits: pack_bits(&bits, width, fill),
            })
        }
    }
}

/// Parse a raw `StrLit` lexeme (e.g. `"hello\n"`, WITH the surrounding quotes,
/// escapes unprocessed by the parser) into a `StrUtf8` `ConstVal`.
///
/// The surrounding double-quotes are stripped (recovery-safe if one is missing),
/// C-style escapes (`\n \t \r \\ \" \0`) are processed, and the resulting UTF-8
/// bytes are packed in IEEE §5.9 order: the FIRST character is the MOST
/// significant byte (byte `k` of `n` occupies bits `[(n-1-k)*8 .. (n-k)*8)`),
/// so `"ab"` evaluates numerically to 16'h6162 (iverilog live: 24930).
/// `width = nbytes*8`. Strings are 2-state, so the `unk` plane is all zero.
/// (`\ddd` octal / `\xhh` hex are deferred — recovered by literal copy.)
/// (v6 fix: the pre-v6 packing was LSB-first — a latent numeric-surface
/// divergence that string-keyed assoc arrays were the first to expose.)
/// Unescape a raw string-literal lexeme (quotes stripped, C escapes processed)
/// into its byte vector. Shared by `parse_str_literal` and the elaborate-time
/// format-specifier scan (§4.1a).
pub fn unescape_str_literal_bytes(raw: &str) -> Vec<u8> {
    let inner = raw.strip_prefix('"').unwrap_or(raw);
    let inner = inner.strip_suffix('"').unwrap_or(inner);

    let mut bytes: Vec<u8> = Vec::with_capacity(inner.len());
    let mut cs = inner.chars();
    while let Some(c) = cs.next() {
        if c != '\\' {
            let mut buf = [0u8; 4];
            bytes.extend_from_slice(c.encode_utf8(&mut buf).as_bytes());
            continue;
        }
        match cs.next() {
            Some('n') => bytes.push(b'\n'),
            Some('t') => bytes.push(b'\t'),
            Some('r') => bytes.push(b'\r'),
            Some('\\') => bytes.push(b'\\'),
            Some('"') => bytes.push(b'"'),
            Some('0') => bytes.push(0),
            Some(other) => {
                bytes.push(b'\\');
                let mut buf = [0u8; 4];
                bytes.extend_from_slice(other.encode_utf8(&mut buf).as_bytes());
            }
            None => bytes.push(b'\\'),
        }
    }
    bytes
}

/// The unescaped UTF-8 text of a string literal (lossy for any non-UTF-8 bytes,
/// which never occur in a Verilog format string). Used by the §4.1a static gate.
pub fn parse_str_literal_text(raw: &str) -> String {
    String::from_utf8_lossy(&unescape_str_literal_bytes(raw)).into_owned()
}

pub fn parse_str_literal(raw: &str) -> ConstVal {
    str_const_from_bytes(&unescape_str_literal_bytes(raw))
}

/// Build a `StrUtf8` ConstVal from plain bytes (no quotes/escapes). Used for
/// SYNTHETIC strings too (e.g. the $dumpvars scope-path encoding, ⑤b).
pub fn str_const_from_bytes(bytes: &[u8]) -> ConstVal {
    let width = (bytes.len() as u32).saturating_mul(8);
    let nwords = (((width as usize) + 63) / 64).max(1);
    let mut val = vec![0u64; nwords];
    let unk = vec![0u64; nwords]; // strings are 2-state
    for (k, &b) in bytes.iter().enumerate() {
        // IEEE §5.9: first character = MOST significant byte.
        let bit = (bytes.len() - 1 - k) * 8;
        // bit % 64 ∈ {0,8,..,56} (8 | 64) → a byte never straddles a word.
        val[bit / 64] |= (b as u64) << (bit % 64);
    }
    ConstVal {
        width,
        signed: false,
        repr: ConstRepr::StrUtf8,
        bits: BitPacked { val, unk },
    }
}

/// IEEE 1364 real literal → `ConstVal { repr: Real }`. Underscores are stripped;
/// round-to-nearest-even is Rust's f64 parse default. The f64 is stored as
/// `to_bits()` in `bits.val[0]`, `unk = [0]`, `width = 64`, `signed = true`.
///
/// OVERFLOW: an out-of-range literal (e.g. `1e400`) parses to `Ok(±inf)`, NOT
/// `Err`, so it interns as `±inf` with the canonical IEEE bit pattern
/// (deterministic, §0). `unwrap_or(0.0)` only covers a truly unparseable string,
/// which the validated grammar should never deliver.
pub fn parse_real_literal(raw: &str) -> ConstVal {
    let cleaned: String = raw.chars().filter(|&c| c != '_').collect();
    let x = cleaned.parse::<f64>().unwrap_or(0.0);
    ConstVal {
        width: 64,
        signed: true,
        repr: ConstRepr::Real,
        bits: BitPacked {
            val: vec![x.to_bits()],
            unk: vec![0],
        },
    }
}

/// Parse a raw real literal lexeme to its f64 value (for real delays `#1.5`).
pub fn parse_real_f64(raw: &str) -> f64 {
    let cleaned: String = raw.chars().filter(|&c| c != '_').collect();
    cleaned.parse::<f64>().unwrap_or(0.0)
}

/// Synthesize a 2-state `ConstVal` from an i64 (two's-complement image masked
/// to `width`). Param values outside the legacy u32 range bind through this
/// (negative → 32-bit signed; beyond 32 bits → 64-bit), P0-6.
pub fn make_const_i64(v: i64, width: u32, signed: bool) -> ConstVal {
    let nwords = ((width as usize).div_ceil(64)).max(1);
    let mut val = vec![0u64; nwords];
    let unk = vec![0u64; nwords];
    val[0] = v as u64;
    if width < 64 {
        val[0] &= (1u64 << width) - 1;
    }
    ConstVal {
        width,
        signed,
        repr: ConstRepr::Numeric,
        bits: BitPacked { val, unk },
    }
}

/// Synthesize a small unsigned `ConstVal` of `n` in `width` bits (used for
/// select widths / single-bit selects). Always 2-state (`unk` all zero).
pub fn make_const_u32(n: u32, width: u32) -> ConstVal {
    let nwords = (((width as usize) + 63) / 64).max(1);
    let mut val = vec![0u64; nwords];
    let unk = vec![0u64; nwords];
    for i in 0..(width.min(32) as usize) {
        if (n >> i) & 1 == 1 {
            val[i / 64] |= 1u64 << (i % 64);
        }
    }
    ConstVal {
        width,
        signed: false,
        repr: ConstRepr::Numeric,
        bits: BitPacked { val, unk },
    }
}
