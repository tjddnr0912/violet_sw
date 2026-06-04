//! Engine-side IEEE 1364-2005 context-determined width inference.
//!
//! Builds a side table `Vec<SelfWidth>` indexed by ExprId, parallel to
//! `SimIr.exprs`, computed once at `SimState::new`. The frozen sim-ir is read
//! verbatim; this table lives ENTIRELY in engine state. It encodes each expr's
//! self-determined (bottom-up) width and signedness per §5.4.1 / §5.5.
//!
//! See `docs/superpowers/plans/2026-06-04-width-inference-spec.md`.

use sim_ir::{BinOp, ConstRepr, Expr, SelKind, SimIr, SysFuncId, UnOp};

/// Self-determined sizing of one expression node (IEEE §5.4.1 / §5.5).
/// `width` is the bottom-up self-width; `signed` is the self-signedness
/// (the both-signed rule already folded in for context-determined operators).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct SelfWidth {
    pub width: u32,
    pub signed: bool,
}

/// The whole side table, one entry per `SimIr.exprs[i]`.
pub(crate) struct WidthTable {
    sw: Vec<SelfWidth>,
}

impl WidthTable {
    #[inline]
    pub(crate) fn get(&self, eid: u32) -> SelfWidth {
        self.sw[eid as usize]
    }
    #[inline]
    pub(crate) fn width(&self, eid: u32) -> u32 {
        self.sw[eid as usize].width
    }
    #[inline]
    pub(crate) fn signed(&self, eid: u32) -> bool {
        self.sw[eid as usize].signed
    }
}

const WIDTH_MAX: u32 = 1 << 24;

#[inline]
// `w` is u32 so it is already >= 0; do NOT add `.max(0)` — that is a no-op that
// trips `clippy::unnecessary_min_or_max` under `-D warnings`. A floor of 1 is
// applied separately by callers that need it (`.max(1)`), not here.
fn clamp_w(w: u32) -> u32 {
    w.min(WIDTH_MAX)
}
#[inline]
fn add_w(a: u32, b: u32) -> u32 {
    clamp_w(a.saturating_add(b))
}
#[inline]
fn mul_w(a: u32, b: u32) -> u32 {
    clamp_w(a.saturating_mul(b))
}

impl WidthTable {
    /// Build the self-width table by a single forward pass over `ir.exprs`.
    /// PRECONDITION (verified §1): every child ExprId < its parent ExprId, so a
    /// forward scan reads only already-filled entries.
    pub(crate) fn build(ir: &SimIr) -> WidthTable {
        let n = ir.exprs.len();
        let mut sw: Vec<SelfWidth> = Vec::with_capacity(n);
        for i in 0..n {
            let s = Self::self_width_of(ir, &sw, i as u32);
            debug_assert_eq!(sw.len(), i, "forward pass invariant");
            sw.push(s);
        }
        WidthTable { sw }
    }
}

/// Read an already-computed child's self-width. `child` MUST be < `parent`
/// (post-order arena, §1). The guard converts any future ordering regression
/// into a deterministic panic instead of reading a default/garbage slot.
#[inline]
fn child(sw: &[SelfWidth], parent: u32, child: u32) -> SelfWidth {
    assert!(
        (child as usize) < sw.len() && child < parent,
        "width pass: child {child} not yet computed for parent {parent} \
         (arena not post-order — see width.rs §1)"
    );
    sw[child as usize]
}

impl WidthTable {
    fn self_width_of(ir: &SimIr, sw: &[SelfWidth], i: u32) -> SelfWidth {
        match &ir.exprs[i as usize] {
            // ── leaves ──────────────────────────────────────────────────────
            Expr::Const { val } => {
                let c = &ir.consts[*val as usize];
                // A real const is {width:64, signed:true} (its real-ness is
                // established at eval time via ConstRepr::Real).
                if matches!(c.repr, ConstRepr::Real) {
                    return SelfWidth {
                        width: 64,
                        signed: true,
                    };
                }
                // A const is signed ONLY when repr==Numeric AND its signed flag set
                // (string consts never signed) — mirrors eval_const (eval.rs:67).
                let signed = matches!(c.repr, ConstRepr::Numeric) && c.signed;
                SelfWidth {
                    width: clamp_w(c.width.max(1)),
                    signed,
                }
            }
            Expr::Signal { net, .. } => {
                let nv = &ir.nets[*net as usize];
                // `word` selects an ARRAY element; element width == NetVar.width.
                SelfWidth {
                    width: clamp_w(nv.width.max(1)),
                    signed: nv.signed,
                }
            }

            // ── select: bit=1 (UNSIGNED), part=`width` operand (UNSIGNED) ─────
            // IEEE §5.4.1: bit-select and part-select results are ALWAYS unsigned.
            Expr::Select { width, kind, .. } => {
                let w = match kind {
                    SelKind::Bit => 1,
                    // `width` is an EXPR INDEX (frozen IR). v1 elaborate emits a
                    // constant width tree for PartConst/PartIdxUp/PartIdxDown; we
                    // resolve it via the const-fold helper (§3.4). If it does not
                    // const-fold, fall back to width 1 (defensive); eval_select
                    // still clamps at runtime.
                    _ => const_u32_of_expr(ir, *width).unwrap_or(1),
                };
                SelfWidth {
                    width: clamp_w(w.max(1)),
                    signed: false,
                }
            }

            // ── concat: SUM of part self-widths, ALWAYS UNSIGNED, self-determined ─
            Expr::Concat { parts } => {
                let mut total = 0u32;
                for &p in parts {
                    total = add_w(total, child(sw, i, p).width);
                }
                SelfWidth {
                    width: clamp_w(total.max(1)),
                    signed: false,
                }
            }

            // ── replicate: count * width(value), ALWAYS UNSIGNED, self-determined ─
            Expr::Replicate { count, value } => {
                let n = const_u32_of_expr(ir, *count).unwrap_or(0);
                let vw = child(sw, i, *value).width;
                SelfWidth {
                    width: clamp_w(mul_w(n, vw).max(1)),
                    signed: false,
                }
            }

            // ── unary ─────────────────────────────────────────────────────────
            Expr::Unary { op, operand } => {
                let o = child(sw, i, *operand);
                match op {
                    // context-determined unary: width = operand width, sign = operand
                    UnOp::Plus | UnOp::Minus | UnOp::BitNot => SelfWidth {
                        width: o.width.max(1),
                        signed: o.signed,
                    },
                    // reductions + logical-not: 1-bit, UNSIGNED, operand self-det
                    UnOp::LogNot
                    | UnOp::RedAnd
                    | UnOp::RedNand
                    | UnOp::RedOr
                    | UnOp::RedNor
                    | UnOp::RedXor
                    | UnOp::RedXnor => SelfWidth {
                        width: 1,
                        signed: false,
                    },
                }
            }

            // ── binary ────────────────────────────────────────────────────────
            Expr::Binary { op, lhs, rhs } => {
                let l = child(sw, i, *lhs);
                let r = child(sw, i, *rhs);
                match op {
                    // arithmetic + bitwise: max(L,R), signed iff BOTH signed
                    BinOp::Add
                    | BinOp::Sub
                    | BinOp::Mul
                    | BinOp::Div
                    | BinOp::Mod
                    | BinOp::BitAnd
                    | BinOp::BitOr
                    | BinOp::BitXor
                    | BinOp::BitXnor => SelfWidth {
                        width: clamp_w(l.width.max(r.width).max(1)),
                        signed: l.signed && r.signed,
                    },
                    // power: width = max(L,R) (IEEE Table 5-22), but the EXPONENT is
                    // SELF-DETERMINED, so it does NOT participate in the both-signed
                    // fold. `**` is signed iff the BASE is signed — an unsigned
                    // exponent must NOT demote a signed base to unsigned.
                    BinOp::Pow => SelfWidth {
                        width: clamp_w(l.width.max(r.width).max(1)),
                        signed: l.signed, // BASE sign only
                    },
                    // comparisons / case-eq / logical: 1-bit, UNSIGNED
                    BinOp::Lt
                    | BinOp::Le
                    | BinOp::Gt
                    | BinOp::Ge
                    | BinOp::Eq
                    | BinOp::Ne
                    | BinOp::CaseEq
                    | BinOp::CaseNe
                    | BinOp::LogAnd
                    | BinOp::LogOr => SelfWidth {
                        width: 1,
                        signed: false,
                    },
                    // shifts: width = LEFT operand width, sign follows LEFT.
                    // RHS (amount) is SELF-DETERMINED — does not affect this width.
                    BinOp::Shl | BinOp::Shr | BinOp::AShl | BinOp::AShr => SelfWidth {
                        width: l.width.max(1),
                        signed: l.signed,
                    },
                }
            }

            // ── ternary: max(then,else), signed iff BOTH branches signed ───────
            Expr::Ternary { then_e, else_e, .. } => {
                let t = child(sw, i, *then_e);
                let e = child(sw, i, *else_e);
                SelfWidth {
                    width: clamp_w(t.width.max(e.width).max(1)),
                    signed: t.signed && e.signed,
                }
            }

            // ── system functions (§6) ──────────────────────────────────────────
            Expr::SysFunc { which, args } => match which {
                // $time / $realtime: 64-bit unsigned (realtime modeled as 64-bit).
                SysFuncId::Time | SysFuncId::Realtime => SelfWidth {
                    width: 64,
                    signed: false,
                },
                // $signed / $unsigned: PRESERVE operand width, flip sign attribute.
                SysFuncId::Signed => {
                    let w = args.first().map(|&a| child(sw, i, a).width).unwrap_or(1);
                    SelfWidth {
                        width: w.max(1),
                        signed: true,
                    }
                }
                SysFuncId::Unsigned => {
                    let w = args.first().map(|&a| child(sw, i, a).width).unwrap_or(1);
                    SelfWidth {
                        width: w.max(1),
                        signed: false,
                    }
                }
                // $clog2: integer return → 32-bit signed `integer` convention.
                SysFuncId::Clog2 => SelfWidth {
                    width: 32,
                    signed: true,
                },
                // $rtoi: integer return → 32-bit signed.
                SysFuncId::Rtoi => SelfWidth {
                    width: 32,
                    signed: true,
                },
                // $itor / $bitstoreal: real return → 64-bit signed (real-domain;
                // the is_real flag is established at eval time).
                SysFuncId::Itor | SysFuncId::BitsToReal => SelfWidth {
                    width: 64,
                    signed: true,
                },
                // $realtobits: raw 64-bit vector → 64-bit unsigned.
                SysFuncId::RealToBits => SelfWidth {
                    width: 64,
                    signed: false,
                },
            },

            // ── user function call: 1-bit X (v1) — mirrors eval.rs:53. ─────────
            // NOTE: elaborate v1 NEVER actually emits `ir::Expr::Call`; this arm is
            // defensive/unreachable in practice, kept for exhaustive-match safety.
            Expr::Call { .. } => SelfWidth {
                width: 1,
                signed: false,
            },
        }
    }
}

/// Resolve an expr to a compile-time u32 if it is a literal const (the v1
/// elaborate guarantee for part-select width and replicate count). Returns
/// None for non-const trees (e.g. a runtime offset, which never feeds width).
/// NOTE: this is a SHALLOW fold over exactly the trees elaborate synthesizes:
///   - direct `Const` (replicate count, PartIdxUp/Down width);
///   - `Add(lhs, rhs)` — the OUTER node of `[msb:lsb]` width `Add(Sub(msb,lsb),1)`;
///   - `Sub(lhs, rhs)` — the INNER `msb - lsb` node.
///
/// `Mul`/other shapes → None (caller falls back to width 1; eval clamps at run).
pub(crate) fn const_u32_of_expr(ir: &SimIr, eid: u32) -> Option<u32> {
    match &ir.exprs[eid as usize] {
        Expr::Const { val } => {
            let c = &ir.consts[*val as usize];
            // value-plane (`bits.val: Vec<u64>`) word0, no X/Z. Reject if any
            // unknown bit set. Anti-wrap (§10): a count/width above u32::MAX would
            // be silently truncated by `as u32`, so CLAMP to WIDTH_MAX whenever any
            // word >= 1 is nonzero OR word0 > u32::MAX, rather than wrap.
            if c.bits.unk.iter().any(|&u| u != 0) {
                return None;
            }
            let word0 = c.bits.val.first().copied().unwrap_or(0);
            let high_words_set = c.bits.val.iter().skip(1).any(|&v| v != 0);
            if high_words_set || word0 > u32::MAX as u64 {
                return Some(WIDTH_MAX);
            }
            Some((word0 as u32).min(WIDTH_MAX))
        }
        // OUTER node of the `[msb:lsb]` width tree: `(msb - lsb) + 1`.
        Expr::Binary {
            op: BinOp::Add,
            lhs,
            rhs,
        } => {
            let a = const_u32_of_expr(ir, *lhs)?;
            let b = const_u32_of_expr(ir, *rhs)?;
            Some(clamp_w(a.saturating_add(b)))
        }
        // INNER node of the `[msb:lsb]` width tree: `msb - lsb`.
        Expr::Binary {
            op: BinOp::Sub,
            lhs,
            rhs,
        } => {
            let a = const_u32_of_expr(ir, *lhs)?;
            let b = const_u32_of_expr(ir, *rhs)?;
            Some(a.saturating_sub(b))
        }
        _ => None,
    }
}
