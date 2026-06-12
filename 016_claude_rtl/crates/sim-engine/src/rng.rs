//! v7 random-number kernels.
//!
//! `$random` = IEEE 1364-2005 Annex N (`uniform`/`rtl_dist_uniform`
//! specialized to the full-range draw): a 32-bit LCG (`s' = 69069·s + 1`,
//! zero seed substitutes 259341593 first) whose high 23 bits map through an
//! IEEE-754 float mantissa into [1,2), then affine-stretch over the full
//! signed 32-bit range with the Annex's exact floor-style negative cast.
//! Pure double mul/add — bit-exact on every IEEE-754 platform (the 3-OS
//! determinism contract; no libm). iverilog implements the same annex, so
//! the sequence is differential-pinned live.
//!
//! `$urandom`/`$urandom_range` are IMPLEMENTATION-DEFINED by IEEE 1800
//! §18.13 — vitamin pins splitmix64 (top 32 bits) from initial state 0,
//! global (the engine is single-threaded; thread-stability is N/A). The
//! sequence is part of vitamin's reproducibility contract: same design,
//! same seed → byte-identical on every OS.

/// One full-range `$random` draw (Annex N). Updates `seed` in place and
/// returns the signed 32-bit value.
pub(crate) fn annex_n_random(seed: &mut u32) -> i32 {
    if *seed == 0 {
        *seed = 259_341_593;
    }
    *seed = seed.wrapping_mul(69_069).wrapping_add(1);
    // High 23 seed bits → float mantissa with exponent 0 ⇒ c ∈ [1, 2).
    let c = f32::from_bits((*seed >> 9) | 0x3f80_0000) as f64;
    let d = 0.000_000_119_209_289_550_781_25_f64; // 2^-23, Annex constant
    let c = c + c * d;
    // Stretch over the dist_uniform range WITH the `end+1` step folded in
    // (scale = 2^32, exact in doubles), then the Annex floor-style cast:
    // `(long) r` for r ≥ 0, `(long)(r - 1)` otherwise. All four live-pinned
    // iverilog draws (two signs × two seeds) reproduce bit-exactly; the
    // plain (b-a)-scale + trunc reading of the annex text is off by one on
    // both (the t6 probe, 2026-06-12).
    let r = ((c - 1.0) * 4_294_967_296.0) - 2_147_483_648.0;
    if r >= 0.0 {
        r as i64 as i32
    } else {
        (r - 1.0) as i64 as i32
    }
}

/// One `$urandom` draw (vitamin-pinned splitmix64, top 32 bits).
pub(crate) fn splitmix_urandom(state: &mut u64) -> u32 {
    *state = state.wrapping_add(0x9E37_79B9_7F4A_7C15);
    let mut z = *state;
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^= z >> 31;
    (z >> 32) as u32
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn annex_n_matches_iverilog_seeded() {
        // iverilog 13.0 live (2026-06-12): s=5 → -2147138048 (seed 345346),
        // then 230383387 (seed -1917100901 as i32 = 2377866395 as u32).
        let mut s: u32 = 5;
        assert_eq!(annex_n_random(&mut s), -2147138048);
        assert_eq!(s, 345346);
        assert_eq!(annex_n_random(&mut s), 230383387);
        assert_eq!(s as i32, -1917100901);
    }

    #[test]
    fn annex_n_matches_iverilog_default_seed() {
        // iverilog live: first three no-arg draws from the zero seed.
        let mut s: u32 = 0;
        assert_eq!(annex_n_random(&mut s), 303379748);
        assert_eq!(annex_n_random(&mut s), -1064739199);
        assert_eq!(annex_n_random(&mut s), -2071669239);
    }

    #[test]
    fn splitmix_is_deterministic_from_zero() {
        // vitamin contract pin (NOT an oracle): the documented $urandom
        // sequence from the initial state. A change here is a contract break.
        let mut st: u64 = 0;
        let a = splitmix_urandom(&mut st);
        let b = splitmix_urandom(&mut st);
        let mut st2: u64 = 0;
        assert_eq!(a, splitmix_urandom(&mut st2));
        assert_eq!(b, splitmix_urandom(&mut st2));
        assert_ne!(a, b);
    }
}
