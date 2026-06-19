//! hdl-parser — token-stream → hdl-ast (PARSE stage).
//!
//! Hand-written recursive descent + Pratt expression parser over `&[Spanned]`.
//! Never panics: errors are recorded in `Vec<ParseError>` and recovered via
//! panic-mode sync (to `;` / `end` / `endmodule` / top-level keywords). The driver
//! maps each `ParseError` → `diag::Diagnostic` (E-PARSE-UNEXPECTED-TOKEN/VITA-E2002)
//! and owns the `--error-limit` hard stop (doc-13). PR1 fully parses: module header
//! (ANSI + non-ANSI), parameter/localparam, net/var decls, continuous `assign` —
//! each with the full precedence-correct expression grammar. Procedural blocks /
//! instances / generate recover to a stub `Error` item (their hdl-ast types exist).
//!
//! Technique (decisive): pure hand-RD + Pratt, NO winnow dep — verified absent from
//! `[workspace.dependencies]`. Per doc-02 this slice IS the hand-RD target set
//! (hot + recovery-critical + precedence-heavy); winnow's `TokenSlice` needs a
//! `Location` newtype to surface spans and its recovery is `unstable-recover`-gated.

use hdl_ast::*;
use hdl_lexer::{Kw, Spanned, TokenKind, WordKind};

// ───────────────────────────── errors ─────────────────────────────
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParseError {
    pub span: Span,               // offending token's span (u32)
    pub expected: &'static str,   // "expression", "';'", "identifier", …
    pub found: Option<TokenKind>, // None ⇒ EOF
}

// ───────────────────────────── cursor ─────────────────────────────
/// Resolved underlying type of a `typedef` name, used to lower `T x;` declarations
/// (Phase-2). For `typedef enum {…} color_t;` the underlying storage is `int`
/// (32-bit signed); a future `typedef logic [7:0] byte_t;` would carry its range.
#[derive(Clone)]
struct TypeInfo {
    kind: NetVarKind,
    signed: bool,
    range: Option<Range>,
    packed: Vec<Range>,
}

/// Flat bit layout of a packed struct: members are placed MSB-first into one
/// `logic [total-1:0]` vector. `fields` carries `(name, lsb_offset, width)` so a
/// `s.field` access desugars to the constant part-select `s[off+w-1 : off]`.
#[derive(Clone)]
struct StructLayout {
    fields: Vec<(String, u32, u32)>,
}
impl StructLayout {
    fn field(&self, name: &str) -> Option<(u32, u32)> {
        self.fields
            .iter()
            .find(|(n, _, _)| n == name)
            .map(|(_, o, w)| (*o, *w))
    }
}

pub struct Parser<'t, 's> {
    toks: &'t [Spanned],
    src: &'s str,
    pos: usize,
    src_end: u32,
    pub errors: Vec<ParseError>,
    error_limit: usize,
    /// P2-5: live expression-recursion depth; capped so a pathological
    /// `((((…))))` yields a parse error instead of a stack overflow.
    expr_depth: u32,
    /// SV user-defined type names (`typedef … name;`) → resolved underlying type.
    /// Accumulates across the source unit; lets `name var;` parse as a typed decl.
    typedefs: std::collections::HashMap<String, TypeInfo>,
    /// Packed-struct type name → flat bit layout (for `s.field` desugaring).
    struct_layouts: std::collections::HashMap<String, StructLayout>,
    /// Variable name → its struct type name (module-scoped; cleared per module).
    var_struct: std::collections::HashMap<String, String>,
}

impl<'t, 's> Parser<'t, 's> {
    pub fn new(toks: &'t [Spanned], src: &'s str) -> Self {
        Self {
            toks,
            src,
            pos: 0,
            src_end: src.len() as u32,
            errors: Vec::new(),
            error_limit: 50,
            expr_depth: 0,
            typedefs: std::collections::HashMap::new(),
            struct_layouts: std::collections::HashMap::new(),
            var_struct: std::collections::HashMap::new(),
        }
    }

    // -- span helpers --
    #[inline]
    fn sp(r: &std::ops::Range<usize>) -> Span {
        Span::new(r.start as u32, r.end as u32)
    }
    #[inline]
    fn cur_span(&self) -> Span {
        self.toks
            .get(self.pos)
            .map(|t| Self::sp(&t.span))
            .unwrap_or(Span::new(self.src_end, self.src_end))
    }
    /// Span of the just-consumed token. VALID ONLY after ≥1 bump (verdict M3-soundness):
    /// at `pos==0` it falls back to `cur_span()` (a safe degenerate), never an
    /// inverted span. Every call site (`start.to(prev_span())`) has bumped first.
    #[inline]
    fn prev_span(&self) -> Span {
        if self.pos == 0 {
            return self.cur_span();
        }
        self.toks
            .get(self.pos - 1)
            .map(|t| Self::sp(&t.span))
            .unwrap_or(Span::new(self.src_end, self.src_end))
    }
    /// Raw lexeme of the token at `pos` (re-slice — tokens carry no value).
    fn cur_text(&self) -> &'s str {
        self.toks
            .get(self.pos)
            .map(|t| &self.src[t.span.clone()])
            .unwrap_or("")
    }
    /// Source text of the token `n` past the cursor (0 = current). Empty past EOF.
    fn text_at(&self, n: usize) -> &'s str {
        self.toks
            .get(self.pos + n)
            .map(|t| &self.src[t.span.clone()])
            .unwrap_or("")
    }

    // -- cursor primitives --
    #[inline]
    fn peek(&self) -> Option<TokenKind> {
        self.toks.get(self.pos).map(|t| t.kind)
    }
    /// Lookahead `n` tokens past the cursor (0 = `peek`).
    #[inline]
    fn peek_at(&self, n: usize) -> Option<TokenKind> {
        self.toks.get(self.pos + n).map(|t| t.kind)
    }
    #[inline]
    fn at_eof(&self) -> bool {
        self.pos >= self.toks.len()
    }
    fn bump(&mut self) -> Option<&'t Spanned> {
        let t = self.toks.get(self.pos);
        if t.is_some() {
            self.pos += 1;
        }
        t
    }
    fn at_kw(&self, kw: Kw) -> bool {
        matches!(self.peek(), Some(TokenKind::Word(WordKind::Keyword(k))) if k == kw)
    }
    fn is_ident(&self) -> bool {
        matches!(
            self.peek(),
            Some(TokenKind::Word(WordKind::Ident)) | Some(TokenKind::EscapedIdent)
        )
    }
    /// True if the next token is a plain identifier spelled exactly `name` — used
    /// for SVA contextual keywords (`throughout`) that are not reserved globally.
    fn at_ident_kw(&self, name: &str) -> bool {
        matches!(self.peek(), Some(TokenKind::Word(WordKind::Ident))) && self.cur_text() == name
    }
    /// True if the next token is a lexer error sentinel (verdict: dedicated handling —
    /// the lexer already emitted the LexError, so we recover WITHOUT re-reporting).
    fn at_lex_error(&self) -> bool {
        matches!(self.peek(), Some(TokenKind::Error(_)))
    }
    fn eat(&mut self, k: TokenKind) -> bool {
        if self.peek() == Some(k) {
            self.pos += 1;
            true
        } else {
            false
        }
    }
    fn eat_kw(&mut self, kw: Kw) -> bool {
        if self.at_kw(kw) {
            self.pos += 1;
            true
        } else {
            false
        }
    }
    /// Consume `k` or record an error (does NOT advance — caller decides to sync).
    fn expect(&mut self, k: TokenKind, what: &'static str) -> bool {
        if self.peek() == Some(k) {
            self.pos += 1;
            true
        } else {
            self.error(what);
            false
        }
    }
    /// Record an error. Suppresses re-reporting on a lexer `Error` token (already
    /// diagnosed by the lexer) — we still record nothing for it, just let the caller
    /// recover. Capped at `error_limit`.
    fn error(&mut self, expected: &'static str) {
        if self.at_lex_error() {
            return;
        } // lexer already emitted a LexError here
        if self.errors.len() < self.error_limit {
            self.errors.push(ParseError {
                span: self.cur_span(),
                expected,
                found: self.peek(),
            });
        }
    }

    /// Like [`error`] but reports at an explicit `span` (e.g. a node parsed earlier).
    fn error_at(&mut self, span: Span, expected: &'static str) {
        if self.errors.len() < self.error_limit {
            self.errors.push(ParseError {
                span,
                expected,
                found: self.peek(),
            });
        }
    }

    // -- ident extraction --
    fn ident(&mut self) -> Option<Ident> {
        if self.is_ident() {
            let t = self.bump().unwrap();
            Some(Ident {
                name: self.src[t.span.clone()].to_string(),
                span: Self::sp(&t.span),
            })
        } else {
            self.error("identifier");
            None
        }
    }
    fn hier_path(&mut self) -> Option<HierPath> {
        let first = self.ident()?;
        let lo = first.span;
        let mut segs = vec![first];
        while self.peek() == Some(TokenKind::Dot) {
            self.bump();
            match self.ident() {
                Some(id) => segs.push(id),
                None => break,
            }
        }
        let hi = segs.last().unwrap().span;
        Some(HierPath {
            segments: segs,
            span: lo.to(hi),
        })
    }

    // ───────────────────────── recovery ─────────────────────────
    /// Panic-mode: skip to a sync anchor. Consumes a `;`; stops AT a top-level
    /// keyword. Note: block-terminator keywords (`end`/`endcase`/`endfunction`/…)
    /// are stop-anchors so PR2 statement recovery lands on the right boundary
    /// (verdict m4 pre-emptive). Always makes ≥0 progress; the body loop's
    /// forward-progress guard (parse_module) handles the no-progress case.
    fn synchronize(&mut self) {
        while let Some(k) = self.peek() {
            match k {
                TokenKind::Semi => {
                    self.bump();
                    return;
                }
                TokenKind::Word(WordKind::Keyword(
                    Kw::End
                    | Kw::Endmodule
                    | Kw::Endcase
                    | Kw::Endfunction
                    | Kw::Endtask
                    | Kw::Endgenerate
                    | Kw::Join
                    | Kw::Module
                    | Kw::Macromodule
                    | Kw::Assign
                    | Kw::Input
                    | Kw::Output
                    | Kw::Inout
                    | Kw::Wire
                    | Kw::Tri
                    | Kw::Wand
                    | Kw::Triand
                    | Kw::Wor
                    | Kw::Trior
                    | Kw::Tri0
                    | Kw::Tri1
                    | Kw::Supply0
                    | Kw::Supply1
                    | Kw::Trireg
                    | Kw::Uwire
                    | Kw::Reg
                    | Kw::Logic
                    | Kw::Integer
                    | Kw::Real
                    | Kw::Realtime
                    | Kw::Time
                    | Kw::Parameter
                    | Kw::Localparam
                    | Kw::Initial
                    | Kw::Always
                    | Kw::AlwaysFf
                    | Kw::AlwaysComb
                    | Kw::AlwaysLatch
                    | Kw::Generate
                    | Kw::Genvar
                    | Kw::Defparam,
                )) => return,
                _ => {
                    self.bump();
                }
            }
        }
    }
}

// ─────────────────────── Pratt binding powers ───────────────────────
// Verified against hdl-reference/verilog/03-expressions-operators.md (14-level
// table, 1=highest). Higher bp = binds tighter. Left-assoc ⇒ rbp=lbp+1;
// right-assoc ⇒ rbp=lbp-1. Ternary handled specially in `expr` (NOT in infix_bp).
fn infix_bp(k: TokenKind) -> Option<(u8, u8)> {
    use TokenKind as T;
    Some(match k {
        T::PipePipe => (5, 6),                                     // ||   lvl13
        T::AmpAmp => (7, 8),                                       // &&   lvl12
        T::Pipe => (9, 10),                                        // |    lvl11
        T::Caret | T::TildeCaret | T::CaretTilde => (11, 12),      // ^ ~^ ^~ lvl10
        T::Amp => (13, 14),                                        // &    lvl9
        T::EqEq | T::BangEq | T::EqEqEq | T::BangEqEq => (15, 16), // == != === !== lvl8
        T::Lt | T::LtEq | T::Gt | T::GtEq => (17, 18),             // < <= > >= lvl7
        T::Shl | T::Shr | T::ShlA | T::ShrA => (19, 20),           // << >> <<< >>> lvl6
        T::Plus | T::Minus => (21, 22),                            // + -  lvl5
        T::Star | T::Slash | T::Percent => (23, 24),               // * / % lvl4
        T::StarStar => (26, 25),                                   // **   lvl3 right-assoc
        _ => return None,
    })
}
const TERNARY_LBP: u8 = 4; // lvl14, right-assoc; rbp = 3
const TERNARY_RBP: u8 = 3;
const UNARY_BP: u8 = 27; // lvl2, prefix right-assoc — binds tighter than **

fn bin_op(k: TokenKind) -> BinOp {
    use TokenKind as T;
    match k {
        T::StarStar => BinOp::Pow,
        T::Star => BinOp::Mul,
        T::Slash => BinOp::Div,
        T::Percent => BinOp::Mod,
        T::Plus => BinOp::Add,
        T::Minus => BinOp::Sub,
        T::Shl => BinOp::Shl,
        T::Shr => BinOp::Shr,
        T::ShlA => BinOp::AShl,
        T::ShrA => BinOp::AShr,
        T::Lt => BinOp::Lt,
        T::LtEq => BinOp::Le,
        T::Gt => BinOp::Gt,
        T::GtEq => BinOp::Ge,
        T::EqEq => BinOp::Eq,
        T::BangEq => BinOp::Ne,
        T::EqEqEq => BinOp::CaseEq,
        T::BangEqEq => BinOp::CaseNe,
        T::Amp => BinOp::BitAnd,
        T::Caret => BinOp::BitXor,
        T::TildeCaret | T::CaretTilde => BinOp::BitXnor,
        T::Pipe => BinOp::BitOr,
        T::AmpAmp => BinOp::LogAnd,
        T::PipePipe => BinOp::LogOr,
        _ => unreachable!("bin_op called on non-binary token"),
    }
}
fn prefix_op(k: TokenKind) -> Option<UnOp> {
    use TokenKind as T;
    Some(match k {
        T::Plus => UnOp::Plus,
        T::Minus => UnOp::Minus,
        T::Bang => UnOp::LogNot,
        T::Tilde => UnOp::BitNot,
        T::Amp => UnOp::RedAnd,
        T::TildeAmp => UnOp::RedNand,
        T::Pipe => UnOp::RedOr,
        T::TildePipe => UnOp::RedNor,
        T::Caret => UnOp::RedXor,
        T::TildeCaret | T::CaretTilde => UnOp::RedXnor,
        _ => return None,
    })
}
/// True for any operator-class token that can legally appear in INFIX position.
/// Used after the Pratt loop to detect a leftover operator (verdict B1): e.g.
/// `~&`/`~|`/`~` are pure-unary, so `a ~& b` would otherwise silently truncate.
fn is_operatorish(k: TokenKind) -> bool {
    use TokenKind as T;
    infix_bp(k).is_some()
        || matches!(
            k,
            T::Question | T::TildeAmp | T::TildePipe | T::Tilde | T::Bang | T::StarStar
        )
}

impl<'t, 's> Parser<'t, 's> {
    /// Pratt entry. `min_bp` = caller's right binding power. After the fold loop,
    /// if the next token is operator-class but matched no infix slot, emit one
    /// error (verdict B1: do not silently leave `~& b` unconsumed).
    /// P2-5 guard: cap the expression recursion so deep nesting is a clean
    /// parse error, never a SIGSEGV. 256 is ≫ any real RTL expression (deepest
    /// practical cones are <50) and fits a default 2 MiB test-thread stack
    /// even in debug builds (~5 fat frames per paren level).
    const MAX_EXPR_DEPTH: u32 = 256;

    pub fn expr(&mut self, min_bp: u8) -> Expr {
        self.expr_depth += 1;
        if self.expr_depth > Self::MAX_EXPR_DEPTH {
            self.expr_depth -= 1;
            self.error("expression nesting too deep (cap 256)");
            return Expr {
                kind: ExprKind::Error,
                span: self.cur_span(),
            };
        }
        let r = self.expr_capped(min_bp);
        self.expr_depth -= 1;
        r
    }

    fn expr_capped(&mut self, min_bp: u8) -> Expr {
        let mut lhs = self.expr_prefix();
        loop {
            let Some(op) = self.peek() else { break };
            if op == TokenKind::Question {
                // ternary, right-assoc
                if TERNARY_LBP < min_bp {
                    break;
                }
                self.bump();
                let then_e = self.expr(0); // reset inside branch
                self.expect(TokenKind::Colon, "':' in conditional");
                let else_e = self.expr(TERNARY_RBP); // right-assoc
                let span = lhs.span.to(else_e.span);
                lhs = Expr {
                    kind: ExprKind::Ternary {
                        cond: Box::new(lhs),
                        then_e: Box::new(then_e),
                        else_e: Box::new(else_e),
                    },
                    span,
                };
                continue;
            }
            let Some((l_bp, r_bp)) = infix_bp(op) else {
                break;
            };
            if l_bp < min_bp {
                break;
            }
            self.bump();
            let rhs = self.expr(r_bp);
            let span = lhs.span.to(rhs.span);
            lhs = Expr {
                kind: ExprKind::Binary {
                    op: bin_op(op),
                    lhs: Box::new(lhs),
                    rhs: Box::new(rhs),
                },
                span,
            };
        }
        // B1: leftover operator that is not a valid infix continuation
        if min_bp == 0 {
            if let Some(op) = self.peek() {
                if is_operatorish(op) && infix_bp(op).is_none() && op != TokenKind::Question {
                    self.error("operator (got a unary-only operator in infix position)");
                }
            }
        }
        lhs
    }

    fn expr_prefix(&mut self) -> Expr {
        if let Some(op) = self.peek().and_then(prefix_op) {
            let start = self.cur_span();
            self.bump();
            let operand = self.expr(UNARY_BP); // lvl2 right-assoc, tighter than **
            let span = start.to(operand.span);
            return Expr {
                kind: ExprKind::Unary {
                    op,
                    operand: Box::new(operand),
                },
                span,
            };
        }
        self.expr_postfix()
    }

    /// primary, then postfix loop: [idx]/[m:l]/[b+:w]; call(args) handled in primary.
    fn expr_postfix(&mut self) -> Expr {
        let mut e = self.expr_primary();
        loop {
            match self.peek() {
                Some(TokenKind::LBracket) => e = self.parse_select(e),
                // HIER-REST②: a `.` after a `name[idx]` select is a hierarchical
                // reference into a generate / instance-array element (`g[0].x`,
                // `bank[3].c.r`). Fold the CONSTANT index into the scope-segment name
                // (`g`+`[0]` ⇒ `g[0]`) so the normal hierarchical resolver handles it
                // — no new IR. (A deeper `g[0].sub[2].y` re-enters via this loop.)
                Some(TokenKind::Dot) if Self::is_indexed_hier_base(&e) => {
                    e = self.parse_indexed_hier(e);
                }
                _ => break,
            }
        }
        e
    }

    /// True when `e` is `name[idx]` / `path[idx]` — a bit-select rooted at a plain
    /// Ident, the shape a following `.` turns into a generate/instance-array
    /// hierarchical reference. (HIER-REST②.)
    fn is_indexed_hier_base(e: &Expr) -> bool {
        matches!(&e.kind, ExprKind::BitSelect { base, .. }
            if matches!(base.kind, ExprKind::Ident(_)))
    }

    /// Parse `path[idx].member(.member)*` into a hierarchical `Ident` whose indexed
    /// segment folds the CONSTANT index into the scope-segment name. Reuses the normal
    /// hierarchical resolver (no new AST/IR). A non-plain-decimal index is a loud parse
    /// error (documented sub-limitation). (HIER-REST②.)
    fn parse_indexed_hier(&mut self, base: Expr) -> Expr {
        let start = base.span;
        let mut segs: Vec<Ident> = Vec::new();
        if let ExprKind::BitSelect { base: b, index } = base.kind {
            if let ExprKind::Ident(p) = b.kind {
                let n = p.segments.len();
                for (i, seg) in p.segments.into_iter().enumerate() {
                    if i + 1 == n {
                        let idx_str = self.const_index_string(&index);
                        segs.push(Ident {
                            name: format!("{}[{idx_str}]", seg.name),
                            span: seg.span,
                        });
                    } else {
                        segs.push(seg);
                    }
                }
            }
        }
        // Consume `.member` segments (plain names; a following `[k].` re-enters the
        // outer postfix loop, a leaf `[k]` is a normal bit-select on the whole path).
        while self.eat(TokenKind::Dot) {
            match self.ident() {
                Some(id) => segs.push(id),
                None => break,
            }
        }
        let hi = segs.last().map(|s| s.span).unwrap_or(start);
        Expr {
            kind: ExprKind::Ident(HierPath {
                segments: segs,
                span: start.to(hi),
            }),
            span: start.to(hi),
        }
    }

    /// Format a CONSTANT generate-array index as a decimal scope-segment string.
    /// Supports a plain (unsized, base-less) decimal literal — the common `g[0]` form,
    /// whose value equals the generate iteration's scope index. Anything else is loud.
    fn const_index_string(&mut self, idx: &Expr) -> String {
        if let ExprKind::IntLit { raw, .. } = &idx.kind {
            let digits: String = raw.chars().filter(|c| *c != '_').collect();
            if !digits.is_empty() && digits.bytes().all(|c| c.is_ascii_digit()) {
                // Normalize the value (strip leading zeros: `g[00]` ⇒ scope `g[0]`).
                if let Ok(v) = digits.parse::<u64>() {
                    return v.to_string();
                }
            }
        }
        self.error_at(
            idx.span,
            "a plain decimal generate-array index in a hierarchical reference",
        );
        "0".to_string()
    }

    fn parse_select(&mut self, base: Expr) -> Expr {
        let start = base.span;
        self.bump(); // '['
        let first = self.expr(0);
        let kind = match self.peek() {
            Some(TokenKind::Colon) => {
                self.bump();
                let lsb = self.expr(0);
                ExprKind::PartSelect {
                    base: Box::new(base),
                    msb: Box::new(first),
                    lsb: Box::new(lsb),
                }
            }
            Some(TokenKind::PlusColon) => {
                self.bump();
                let w = self.expr(0);
                ExprKind::IndexedPart {
                    base: Box::new(base),
                    offset: Box::new(first),
                    width: Box::new(w),
                    dir: PartDir::PlusColon,
                }
            }
            Some(TokenKind::MinusColon) => {
                self.bump();
                let w = self.expr(0);
                ExprKind::IndexedPart {
                    base: Box::new(base),
                    offset: Box::new(first),
                    width: Box::new(w),
                    dir: PartDir::MinusColon,
                }
            }
            _ => ExprKind::BitSelect {
                base: Box::new(base),
                index: Box::new(first),
            },
        };
        self.expect(TokenKind::RBracket, "']'");
        Expr {
            kind,
            span: start.to(self.prev_span()),
        }
    }

    fn expr_primary(&mut self) -> Expr {
        use TokenKind as T;
        let start = self.cur_span();
        match self.peek() {
            // lexer error sentinel: skip it (already diagnosed), yield Error node
            Some(T::Error(_)) => {
                self.bump();
                Expr {
                    kind: ExprKind::Error,
                    span: start,
                }
            }
            // numeric / string literals
            Some(T::IntDecimal) => self.lit_int(IntLitKind::Decimal),
            Some(T::IntSized) => self.lit_int(IntLitKind::Sized),
            Some(T::IntUnsizedBased) => self.lit_int(IntLitKind::UnsizedBased),
            Some(T::RealFixed) => self.lit_real(RealLitKind::Fixed),
            Some(T::RealExp) => self.lit_real(RealLitKind::Exp),
            Some(T::Str) => {
                let raw = self.cur_text().to_string();
                self.bump();
                Expr {
                    kind: ExprKind::StrLit { raw },
                    span: start,
                }
            }
            // system function call: $time, $signed(x). name retains the `$`.
            Some(T::SystemTask) => {
                let t = self.bump().unwrap();
                let name = Ident {
                    name: self.src[t.span.clone()].to_string(),
                    span: Self::sp(&t.span),
                };
                let args = if self.peek() == Some(T::LParen) {
                    self.call_args()
                } else {
                    Vec::new()
                };
                Expr {
                    kind: ExprKind::SysCall { name, args },
                    span: start.to(self.prev_span()),
                }
            }
            // v5 ⑥: bare `$` — queue last-index (`q[$]`, `q[$-1]`). A primary
            // so Pratt arithmetic folds over it; elaborate substitutes
            // `size()-1` inside a queue select and loud-rejects it elsewhere.
            Some(T::Dollar) => {
                self.bump();
                Expr {
                    kind: ExprKind::Dollar,
                    span: start,
                }
            }
            // identifier / hierarchical name / function call
            _ if self.is_ident() => {
                let path = self.hier_path().unwrap();
                // v7 P2-D: `pkg::name` package-scoped value reference.
                if path.segments.len() == 1 && self.peek() == Some(T::ColonColon) {
                    self.bump(); // '::'
                    if let Some(name) = self.ident() {
                        return Expr {
                            kind: ExprKind::PkgScoped {
                                pkg: path.segments.into_iter().next().unwrap(),
                                name,
                            },
                            span: start.to(self.prev_span()),
                        };
                    }
                    return Expr {
                        kind: ExprKind::Error,
                        span: start.to(self.prev_span()),
                    };
                }
                // v5 ⑥: contextual `new[n]` / `new[n](src)` — the ident `new`
                // immediately followed by `[`. Elaborate falls back to an
                // array read when a net named `new` is actually in scope
                // (V2005 keeps `new` as an ordinary identifier).
                if path.segments.len() == 1
                    && path.segments[0].name == "new"
                    && self.peek() == Some(T::LBracket)
                {
                    self.bump(); // '['
                    let size = self.expr(0);
                    self.expect(T::RBracket, "']'");
                    let src = if self.peek() == Some(T::LParen) {
                        self.bump();
                        let s = self.expr(0);
                        self.expect(T::RParen, "')'");
                        Some(Box::new(s))
                    } else {
                        None
                    };
                    return Expr {
                        kind: ExprKind::New {
                            size: Box::new(size),
                            src,
                        },
                        span: start.to(self.prev_span()),
                    };
                }
                // packed-struct member access `s.field` → constant part-select.
                if let Some((base, off, w)) = self.struct_field_select(&path) {
                    let span = path.span;
                    return Expr {
                        kind: ExprKind::PartSelect {
                            base: Box::new(Expr {
                                kind: ExprKind::Ident(base),
                                span,
                            }),
                            msb: Box::new(Self::dec_lit(off + w - 1, span)),
                            lsb: Box::new(Self::dec_lit(off, span)),
                        },
                        span,
                    };
                }
                if self.peek() == Some(T::LParen) {
                    let args = self.call_args();
                    Expr {
                        kind: ExprKind::Call { name: path, args },
                        span: start.to(self.prev_span()),
                    }
                } else {
                    let sp = path.span;
                    Expr {
                        kind: ExprKind::Ident(path),
                        span: sp,
                    }
                }
            }
            // parenthesized / min:typ:max
            Some(T::LParen) => {
                self.bump();
                let inner = self.expr(0);
                if self.peek() == Some(T::Colon) {
                    self.bump();
                    let typ = self.expr(0);
                    self.expect(T::Colon, "':' in min:typ:max");
                    let max = self.expr(0);
                    self.expect(T::RParen, "')'");
                    Expr {
                        kind: ExprKind::MinTypMax {
                            min: Box::new(inner),
                            typ: Box::new(typ),
                            max: Box::new(max),
                        },
                        span: start.to(self.prev_span()),
                    }
                } else {
                    self.expect(T::RParen, "')'");
                    Expr {
                        kind: ExprKind::Paren {
                            inner: Box::new(inner),
                        },
                        span: start.to(self.prev_span()),
                    }
                }
            }
            // concat / replication
            Some(T::LBrace) => self.brace_expr(start),
            _ => {
                self.error("expression");
                Expr {
                    kind: ExprKind::Error,
                    span: start,
                }
            }
        }
    }

    fn lit_int(&mut self, kind: IntLitKind) -> Expr {
        let start = self.cur_span();
        let raw = self.cur_text().to_string();
        self.bump();
        Expr {
            kind: ExprKind::IntLit { kind, raw },
            span: start,
        }
    }
    fn lit_real(&mut self, kind: RealLitKind) -> Expr {
        let start = self.cur_span();
        let raw = self.cur_text().to_string();
        self.bump();
        Expr {
            kind: ExprKind::RealLit { kind, raw },
            span: start,
        }
    }
    fn call_args(&mut self) -> Vec<Expr> {
        self.bump(); // '('
        let mut args = Vec::new();
        if self.peek() != Some(TokenKind::RParen) {
            loop {
                args.push(self.expr(0));
                if !self.eat(TokenKind::Comma) {
                    break;
                }
            }
        }
        self.expect(TokenKind::RParen, "')'");
        args
    }
    /// `{a,b}` concat OR `{n{a,b}}` replication. After parsing `first`, a following
    /// `{` ⇒ replication (first=count); the inner braced list becomes `value:
    /// Vec<Expr>` DIRECTLY (verdict M5 — no Concat wrapper). `{ {a},{b} }` is a
    /// concat-of-concats: `first={a}` then next is `,`, so concat path is taken.
    fn brace_expr(&mut self, start: Span) -> Expr {
        self.bump(); // outer '{'
        let first = self.expr(0);
        if self.peek() == Some(TokenKind::LBrace) {
            // replication: first = count, inner {…} = the repeated element list.
            self.bump(); // inner '{'
            let mut value = vec![self.expr(0)];
            while self.eat(TokenKind::Comma) {
                value.push(self.expr(0));
            }
            self.expect(TokenKind::RBrace, "'}' closing replication value");
            self.expect(TokenKind::RBrace, "'}' closing replication");
            return Expr {
                kind: ExprKind::Replicate {
                    count: Box::new(first),
                    value,
                },
                span: start.to(self.prev_span()),
            };
        }
        let mut parts = vec![first];
        while self.eat(TokenKind::Comma) {
            parts.push(self.expr(0));
        }
        self.expect(TokenKind::RBrace, "'}'");
        Expr {
            kind: ExprKind::Concat { parts },
            span: start.to(self.prev_span()),
        }
    }
}

// ───────────── module / port / param / decl / contassign ─────────────
impl<'t, 's> Parser<'t, 's> {
    fn opt_signed(&mut self) -> bool {
        // `unsigned` is the redundant explicit form of the default (reg/wire are
        // unsigned) — consume it and report signed=false, so `reg unsigned [7:0]`
        // parses like `reg [7:0]`. `signed` reports true.
        if self.eat_kw(Kw::Unsigned) {
            return false;
        }
        self.eat_kw(Kw::Signed)
    }
    /// `[msb:lsb]` packed range (requires `:`).
    fn opt_range(&mut self) -> Option<Range> {
        if self.peek() != Some(TokenKind::LBracket) {
            return None;
        }
        let start = self.cur_span();
        self.bump();
        let msb = self.expr(0);
        self.expect(TokenKind::Colon, "':' in range");
        let lsb = self.expr(0);
        self.expect(TokenKind::RBracket, "']'");
        Some(Range {
            msb,
            lsb,
            span: start.to(self.prev_span()),
        })
    }

    /// Additional packed dims after the first `[msb:lsb]` — `logic [3:0][7:0]` ⇒
    /// `[[7:0]]`. Each is a `[msb:lsb]` range; collected greedily before the name.
    fn opt_packed_dims(&mut self) -> Vec<Range> {
        let mut dims = Vec::new();
        while let Some(r) = self.opt_range() {
            dims.push(r);
        }
        dims
    }

    /// Unpacked dimension `[hi:lo]` (Range) or `[N]` (Size) — verdict M3.
    /// v5 ⑥ adds the dynamic-storage forms: `[]` (dyn array), `[$]`/`[$:N]`
    /// (queue / bounded queue — the bound parses, elaborate loud-rejects it),
    /// `[integer]`/`[time]` (assoc, integer key types only). `[*]` (wildcard
    /// assoc) is a parse error — outside the MVP.
    /// A dimension can start with `[` or — since slice S4 fused `[*` into one
    /// token — `[*` (the wildcard assoc `[*]` spelling). `parse_dim` handles
    /// both; the array-dim loops gate on this so the no-space `[*]` still reaches
    /// the precise wildcard diagnostic instead of a generic token cascade.
    fn at_dim_start(&self) -> bool {
        matches!(
            self.peek(),
            Some(TokenKind::LBracket | TokenKind::LBracketStar)
        )
    }
    fn parse_dim(&mut self) -> Option<Dim> {
        // `[*]` wildcard assoc index. Since slice S4 the lexer fuses `[*` into a
        // single `LBracketStar` token (for SVA `[*n]`), so the canonical no-space
        // spelling never reaches the `Star` arm below — handle it here. Outside
        // the MVP: reject loudly with the precise message, recover as a dyn dim.
        // (The spaced `[ *]` spelling still lexes as `[`+`*` and hits the `Star`
        // arm.)
        if self.peek() == Some(TokenKind::LBracketStar) {
            self.bump(); // `[*`
            self.error(
                "a concrete assoc key type (`[integer]`/`[time]`) — wildcard `[*]` is unsupported",
            );
            self.expect(TokenKind::RBracket, "']'");
            return Some(Dim::Dyn);
        }
        if self.peek() != Some(TokenKind::LBracket) {
            return None;
        }
        self.bump(); // '['
        match self.peek() {
            // `[]` — dynamic array.
            Some(TokenKind::RBracket) => {
                self.bump();
                return Some(Dim::Dyn);
            }
            // `[$]` / `[$:N]` — queue.
            Some(TokenKind::Dollar) => {
                self.bump();
                let bound = if self.peek() == Some(TokenKind::Colon) {
                    self.bump();
                    Some(self.expr(0))
                } else {
                    None
                };
                self.expect(TokenKind::RBracket, "']'");
                return Some(Dim::Queue(bound));
            }
            // `[integer]` / `[time]` — assoc key type (keyword-led, so it can
            // never shadow a same-named size parameter).
            Some(TokenKind::Word(WordKind::Keyword(k @ (Kw::Integer | Kw::Time)))) => {
                self.bump();
                self.expect(TokenKind::RBracket, "']'");
                return Some(Dim::Assoc(if k == Kw::Integer {
                    AssocKey::Integer
                } else {
                    AssocKey::Time
                }));
            }
            // `[string]` (v6) — since the v7 AST flip `string` is a real
            // KEYWORD (the P2-C type), so the assoc key form is keyword-led
            // like `[integer]`/`[time]`.
            Some(TokenKind::Word(WordKind::Keyword(Kw::String))) => {
                self.bump();
                self.expect(TokenKind::RBracket, "']'");
                return Some(Dim::Assoc(AssocKey::Str));
            }
            // `[*]` — wildcard assoc index: outside the MVP, reject loudly at
            // parse (recover as a plain dyn dim so the decl still resolves).
            Some(TokenKind::Star) => {
                self.bump();
                self.error("a concrete assoc key type (`[integer]`/`[time]`) — wildcard `[*]` is unsupported");
                self.expect(TokenKind::RBracket, "']'");
                return Some(Dim::Dyn);
            }
            _ => {}
        }
        let first = self.expr(0);
        let dim = if self.peek() == Some(TokenKind::Colon) {
            let r_start = first.span;
            self.bump();
            let lsb = self.expr(0);
            Dim::Range(Range {
                msb: first,
                lsb,
                span: r_start.to(self.prev_span()),
            })
        } else {
            Dim::Size(first)
        };
        self.expect(TokenKind::RBracket, "']'");
        Some(dim)
    }
    /// v7 P2-D: `import pkg::*;` / `import pkg::sym;` — ONE term per
    /// statement (a comma list is a loud parse error; rare in practice).
    fn parse_import_decl(&mut self) -> Option<ImportDecl> {
        let start = self.cur_span();
        self.bump(); // import
        let pkg = self.ident()?;
        if !self.expect(TokenKind::ColonColon, "'::'") {
            return None;
        }
        let item = if self.peek() == Some(TokenKind::Star) {
            self.bump();
            None
        } else {
            Some(self.ident()?)
        };
        if self.peek() == Some(TokenKind::Comma) {
            self.error("';' (one import term per statement in v7)");
            return None;
        }
        if !self.expect(TokenKind::Semi, "';'") {
            return None;
        }
        Some(ImportDecl {
            pkg,
            item,
            span: start.to(self.prev_span()),
        })
    }

    fn net_var_kind(&self) -> Option<NetVarKind> {
        use Kw::*;
        match self.peek() {
            Some(TokenKind::Word(WordKind::Keyword(k))) => Some(match k {
                Wire => NetVarKind::Wire,
                Tri => NetVarKind::Tri,
                Wand => NetVarKind::Wand,
                Triand => NetVarKind::Triand,
                Wor => NetVarKind::Wor,
                Trior => NetVarKind::Trior,
                Tri0 => NetVarKind::Tri0,
                Tri1 => NetVarKind::Tri1,
                Supply0 => NetVarKind::Supply0,
                Supply1 => NetVarKind::Supply1,
                Trireg => NetVarKind::Trireg,
                Uwire => NetVarKind::Uwire,
                Reg => NetVarKind::Reg,
                Logic => NetVarKind::Logic,
                Integer => NetVarKind::Integer,
                Real => NetVarKind::Real,
                Realtime => NetVarKind::Realtime,
                Time => NetVarKind::Time,
                Event => NetVarKind::Event,
                String => NetVarKind::String,
                _ => return None,
            }),
            _ => None,
        }
    }

    pub fn parse_source_unit(&mut self) -> SourceUnit {
        let start = self.cur_span();
        let mut items = Vec::new();
        while !self.at_eof() {
            let before = self.pos;
            if self.at_kw(Kw::Module) || self.at_kw(Kw::Macromodule) {
                match self.parse_module() {
                    Some(m) => items.push(TopItem::Module(m)),
                    None => {
                        items.push(TopItem::Error(self.prev_span()));
                        self.synchronize();
                    }
                }
            } else if self.at_kw(Kw::Interface) {
                // v5 ⑥: `interface … endinterface` — same shape as a module.
                match self.parse_module_like(Kw::Interface, Kw::Endinterface) {
                    Some(m) => items.push(TopItem::Interface(m)),
                    None => {
                        items.push(TopItem::Error(self.prev_span()));
                        self.synchronize();
                    }
                }
            } else if self.at_kw(Kw::Package) {
                // v7 P2-D: `package … endpackage` — body shape reuses modules.
                match self.parse_module_like(Kw::Package, Kw::Endpackage) {
                    Some(m) => items.push(TopItem::Package(m)),
                    None => {
                        items.push(TopItem::Error(self.prev_span()));
                        self.synchronize();
                    }
                }
            } else if self.at_kw(Kw::Import) {
                // v7 P2-D: compilation-unit-scope import.
                match self.parse_import_decl() {
                    Some(i) => items.push(TopItem::Import(i)),
                    None => {
                        items.push(TopItem::Error(self.prev_span()));
                        self.synchronize();
                    }
                }
            } else {
                self.error("'module'");
                let s = self.cur_span();
                items.push(TopItem::Error(s));
                self.synchronize();
            }
            // BLOCKER B3 (top level): guarantee forward progress.
            if self.pos == before {
                self.bump();
            }
        }
        SourceUnit {
            items,
            span: start.to(self.prev_span()),
        }
    }

    fn parse_module(&mut self) -> Option<ModuleDecl> {
        self.parse_module_like(Kw::Module, Kw::Endmodule)
    }

    /// One body shared by `module…endmodule` and `interface…endinterface`
    /// (v5 ⑥): the header/body grammar is identical for the MVP subset.
    fn parse_module_like(&mut self, _start_kw: Kw, end_kw: Kw) -> Option<ModuleDecl> {
        let start = self.cur_span();
        // Variable→struct bindings are module-scoped (type *names* are not).
        self.var_struct.clear();
        let is_macromodule = self.at_kw(Kw::Macromodule);
        self.bump(); // module / macromodule / interface
        let name = self.ident()?;

        // ANSI param port list: #( parameter … )
        let mut params = Vec::new();
        if self.peek() == Some(TokenKind::Hash) {
            self.bump();
            self.expect(TokenKind::LParen, "'(' after '#'");
            loop {
                if let Some(p) = self.parse_param_decl() {
                    params.push(p);
                }
                if !self.eat(TokenKind::Comma) {
                    break;
                }
            }
            self.expect(TokenKind::RParen, "')'");
        }

        // port list: ANSI ( dir type name, … ) | non-ANSI ( name, … ) | none
        let ports = self.parse_port_list();
        self.expect(TokenKind::Semi, "';' after module header");

        // body until the end keyword — with forward-progress guard (BLOCKER B3)
        let mut body = Vec::new();
        while !self.at_eof() && !self.at_kw(end_kw) {
            let before = self.pos;
            match self.parse_module_item() {
                Some(it) => body.push(it),
                None => {
                    body.push(ModuleItem::Error(self.cur_span()));
                    self.synchronize();
                }
            }
            if self.pos == before {
                self.bump();
            } // B3: never spin on a stuck token
        }
        self.expect(
            TokenKind::Word(WordKind::Keyword(end_kw)),
            if end_kw == Kw::Endinterface {
                "'endinterface'"
            } else {
                "'endmodule'"
            },
        );
        Some(ModuleDecl {
            is_macromodule,
            name,
            params,
            ports,
            body,
            span: start.to(self.prev_span()),
        })
    }

    /// Decide ANSI vs non-ANSI by the FIRST token inside `(`: a direction keyword
    /// ⇒ ANSI. A bare identifier ⇒ non-ANSI name list. (Documented PR1 limitation,
    /// verdict H2/M1: a malformed ANSI header beginning with a bare net/var kind —
    /// e.g. illegal `module m(reg x)` — is routed to non-ANSI and errors in the body.
    /// Strict V2005 non-ANSI headers are bare-name-only, so this is correct for scope.)
    fn parse_port_list(&mut self) -> PortList {
        if self.peek() != Some(TokenKind::LParen) {
            return PortList::None;
        }
        self.bump(); // '('
        if self.peek() == Some(TokenKind::RParen) {
            self.bump();
            return PortList::Ansi(Vec::new());
        }
        let ansi = matches!(
            self.peek(),
            Some(TokenKind::Word(WordKind::Keyword(
                Kw::Input | Kw::Output | Kw::Inout
            )))
        ) ||
            // v5 ⑥: `module m(intf bus, …)` — an interface-typed first port:
            // Ident followed by Ident (`intf bus`) or Dot (`intf.mp bus`).
            (matches!(self.peek(), Some(TokenKind::Word(WordKind::Ident)))
                && matches!(
                    self.peek_at(1),
                    Some(TokenKind::Word(WordKind::Ident) | TokenKind::Dot)
                ));
        if ansi {
            let mut ports: Vec<AnsiPort> = Vec::new();
            loop {
                let prev = ports.last().cloned(); // for dir + type/range inheritance
                let port = self.parse_ansi_port(prev.as_ref());
                ports.push(port);
                if !self.eat(TokenKind::Comma) {
                    break;
                }
            }
            self.expect(TokenKind::RParen, "')'");
            PortList::Ansi(ports)
        } else {
            let mut names = Vec::new();
            loop {
                if let Some(id) = self.ident() {
                    names.push(id);
                }
                if !self.eat(TokenKind::Comma) {
                    break;
                }
            }
            self.expect(TokenKind::RParen, "')'");
            PortList::NonAnsi(names)
        }
    }

    /// v5 ⑥: `modport name (input a, b, output c);` — the direction is sticky
    /// across commas. Parsed + ACCEPTED (per-member direction checks are a
    /// follow-on); task/function modport members are outside the MVP.
    fn parse_modport(&mut self) -> Option<ModportDecl> {
        let start = self.cur_span();
        self.bump(); // modport
        let name = self.ident()?;
        self.expect(TokenKind::LParen, "'('");
        let mut ports = Vec::new();
        let mut dir: Option<PortDir> = None;
        loop {
            match self.peek() {
                Some(TokenKind::Word(WordKind::Keyword(Kw::Input))) => {
                    self.bump();
                    dir = Some(PortDir::Input);
                }
                Some(TokenKind::Word(WordKind::Keyword(Kw::Output))) => {
                    self.bump();
                    dir = Some(PortDir::Output);
                }
                Some(TokenKind::Word(WordKind::Keyword(Kw::Inout))) => {
                    self.bump();
                    dir = Some(PortDir::Inout);
                }
                _ => {}
            }
            let Some(d) = dir else {
                self.error("a direction (input/output/inout) before the first modport member");
                break;
            };
            let Some(member) = self.ident() else {
                self.error("modport member name");
                break;
            };
            ports.push((d, member));
            if !self.eat(TokenKind::Comma) {
                break;
            }
        }
        self.expect(TokenKind::RParen, "')'");
        self.expect(TokenKind::Semi, "';'");
        Some(ModportDecl {
            name,
            ports,
            span: start.to(self.prev_span()),
        })
    }

    /// `prev = None` ⇒ first ANSI port; a missing direction is then an ERROR
    /// (verdict M4: don't silently default the first port to Input). A comma-continued
    /// port with no direction inherits the previous port's direction; a PURE
    /// continuation (`input [7:0] a, b`) that also omits its own type/range/signed
    /// inherits those too, so both `a` and `b` are `[7:0]` (IEEE 1800 §23.2.2.1).
    fn parse_ansi_port(&mut self, prev: Option<&AnsiPort>) -> AnsiPort {
        let start = self.cur_span();
        // v5 ⑥: interface-typed port `intf p` / `intf.mp p` — an Ident in the
        // type position followed by Ident/Dot. No direction, no range.
        if matches!(self.peek(), Some(TokenKind::Word(WordKind::Ident)))
            && matches!(
                self.peek_at(1),
                Some(TokenKind::Word(WordKind::Ident) | TokenKind::Dot)
            )
        {
            let iface = self.ident().unwrap();
            let modport = if self.eat(TokenKind::Dot) {
                self.ident()
            } else {
                None
            };
            let name = self.ident().unwrap_or(Ident {
                name: String::new(),
                span: self.cur_span(),
            });
            let ispan = iface.span;
            return AnsiPort {
                dir: PortDir::Input, // placeholder — iface ports carry no dir
                net_or_var: None,
                signed: false,
                range: None,
                packed: Vec::new(),
                name,
                default: None,
                iface: Some(IfaceRef {
                    iface,
                    modport,
                    span: ispan,
                }),
                span: start.to(self.prev_span()),
            };
        }
        let explicit_dir = match self.peek() {
            Some(TokenKind::Word(WordKind::Keyword(Kw::Input))) => {
                self.bump();
                Some(PortDir::Input)
            }
            Some(TokenKind::Word(WordKind::Keyword(Kw::Output))) => {
                self.bump();
                Some(PortDir::Output)
            }
            Some(TokenKind::Word(WordKind::Keyword(Kw::Inout))) => {
                self.bump();
                Some(PortDir::Inout)
            }
            _ => None,
        };
        let dir = match (explicit_dir, prev.map(|p| p.dir)) {
            (Some(d), _) => d,
            (None, Some(prev_dir)) => prev_dir, // inherit
            (None, None) => {
                self.error("port direction (first ANSI port must specify one)");
                PortDir::Input
            } // recover as Input
        };
        let mut net_or_var = self.net_var_kind();
        if net_or_var.is_some() {
            self.bump();
        }
        let mut signed = self.opt_signed();
        let mut range = self.opt_range();
        let mut packed = self.opt_packed_dims(); // additional packed dims `[3:0][7:0]`
                                                 // A pure continuation (no own direction/type/range/signed) inherits the
                                                 // previous port's type — `input [7:0] a, b` ⇒ b is also `[7:0]`.
        if explicit_dir.is_none()
            && net_or_var.is_none()
            && range.is_none()
            && packed.is_empty()
            && !signed
        {
            if let Some(p) = prev {
                net_or_var = p.net_or_var;
                signed = p.signed;
                range = p.range.clone();
                packed = p.packed.clone();
            }
        }
        let name = self.ident().unwrap_or(Ident {
            name: String::new(),
            span: self.cur_span(),
        });
        let default = if self.eat(TokenKind::Eq) {
            Some(self.expr(0))
        } else {
            None
        };
        AnsiPort {
            dir,
            net_or_var,
            signed,
            range,
            packed,
            name,
            default,
            iface: None,
            span: start.to(self.prev_span()),
        }
    }

    /// Parse one parameter/localparam decl (the keyword is optional on `#(…)`
    /// continuations, defaulting to `Parameter`, which matches IEEE-1364 §12.2).
    fn parse_param_decl(&mut self) -> Option<ParamDecl> {
        let start = self.cur_span();
        let kind = if self.eat_kw(Kw::Localparam) {
            ParamKind::Localparam
        } else {
            self.eat_kw(Kw::Parameter);
            ParamKind::Parameter
        };
        let signed = self.opt_signed();
        let ty = match self.peek() {
            Some(TokenKind::Word(WordKind::Keyword(Kw::Integer))) => {
                self.bump();
                ParamType::Integer
            }
            Some(TokenKind::Word(WordKind::Keyword(Kw::Real))) => {
                self.bump();
                ParamType::Real
            }
            Some(TokenKind::Word(WordKind::Keyword(Kw::Realtime))) => {
                self.bump();
                ParamType::Realtime
            }
            Some(TokenKind::Word(WordKind::Keyword(Kw::Time))) => {
                self.bump();
                ParamType::Time
            }
            _ => ParamType::Implicit,
        };
        let range = self.opt_range();
        let name = self.ident()?;
        self.expect(TokenKind::Eq, "'=' in parameter");
        let value = self.expr(0);
        Some(ParamDecl {
            kind,
            signed,
            ty,
            range,
            name,
            value,
            span: start.to(self.prev_span()),
        })
    }

    fn parse_module_item(&mut self) -> Option<ModuleItem> {
        // skip a stray lexer error token without re-reporting (already diagnosed)
        if self.at_lex_error() {
            let s = self.cur_span();
            self.bump();
            return Some(ModuleItem::Error(s));
        }
        // parameter / localparam
        if self.at_kw(Kw::Parameter) || self.at_kw(Kw::Localparam) {
            let p = self.parse_param_decl()?;
            self.expect(TokenKind::Semi, "';'");
            return Some(ModuleItem::Param(p));
        }
        // continuous assign
        if self.at_kw(Kw::Assign) {
            return self.parse_cont_assign().map(ModuleItem::ContAssign);
        }
        // non-ANSI body port direction decl
        if matches!(
            self.peek(),
            Some(TokenKind::Word(WordKind::Keyword(
                Kw::Input | Kw::Output | Kw::Inout
            )))
        ) {
            return self.parse_port_decl().map(ModuleItem::PortDecl);
        }
        // SV `typedef enum/…/<type> name;` (Phase-2 user-defined types).
        if self.at_kw(Kw::Typedef) {
            return self.parse_typedef();
        }
        // v5 ⑥: `modport mp (input a, output b);` — interface body item.
        if self.at_kw(Kw::Modport) {
            return self.parse_modport().map(ModuleItem::Modport);
        }
        // v7 P2-D: module/package-scope `import pkg::…;`.
        if self.at_kw(Kw::Import) {
            return self.parse_import_decl().map(ModuleItem::Import);
        }
        // net/var declaration
        if self.net_var_kind().is_some() {
            return self.parse_net_var().map(ModuleItem::NetVar);
        }
        // typedef-name declaration: `color_t c, d;` where `color_t` was typedef'd.
        if let Some(info) = self.peek_typedef_name() {
            return self.parse_typed_decl(info).map(ModuleItem::NetVar);
        }
        // procedural blocks → REAL parsing (PR2).
        if matches!(
            self.peek(),
            Some(TokenKind::Word(WordKind::Keyword(
                Kw::Initial
                    | Kw::Always
                    | Kw::AlwaysFf
                    | Kw::AlwaysComb
                    | Kw::AlwaysLatch
                    | Kw::Final
            )))
        ) {
            return Some(ModuleItem::Proc(self.parse_procedural_block()));
        }
        // function/endfunction and task/endtask definitions.
        if self.at_kw(Kw::Function) {
            return Some(ModuleItem::Func(self.parse_function_def()));
        }
        if self.at_kw(Kw::Task) {
            return Some(ModuleItem::Task(self.parse_task_def()));
        }
        // genvar declaration:  genvar i, j;
        if self.at_kw(Kw::Genvar) {
            return Some(self.parse_genvar_decl());
        }
        // generate construct:  generate … endgenerate  (PR3 — real parsing).
        if self.at_kw(Kw::Generate) {
            return Some(ModuleItem::Generate(self.parse_generate_construct()));
        }
        // module-level concurrent assertion: `assert property(@(clk) …);`
        // (slice S10). Only `assert property` is a module item — an immediate
        // `assert (expr)` is procedural-only and is a loud error here. The
        // concurrent form is wrapped in a synthetic `initial` so it flows
        // through the same procedural ConcurrentAssert collection
        // (`pending_sva`); the checker is materialized at module level
        // regardless, so this is a pure parser-placement change (no AST shape
        // change, no sim-ir change).
        if self.at_kw(Kw::Assert) {
            let start = self.cur_span();
            self.bump(); // `assert`
            if !self.at_kw(Kw::Property) {
                self.error(
                    "`property` after `assert` at module level (immediate \
                     assertions are procedural-only)",
                );
                return Some(ModuleItem::Error(start.to(self.prev_span())));
            }
            let stmt = self.parse_concurrent_assert(start);
            let span = start.to(self.prev_span());
            return Some(ModuleItem::Proc(ProceduralBlock {
                kind: ProcKind::Initial,
                sensitivity: None,
                body: Box::new(stmt),
                span,
            }));
        }
        // Named SVA declarations (Phase-3 named-SVA slice). `sequence` /
        // `endsequence` / `endproperty` are CONTEXTUAL keywords (`at_ident_kw`,
        // like `throughout`/`within`/`iff`); `property` is `Kw::Property`. Placed
        // before the bare-ident instantiation arm so `sequence s; …` is not
        // mis-parsed as a module instantiation. A net named `sequence`
        // (`wire sequence;`) is unaffected — `net_var_kind` matches first.
        //
        // `sequence` is NOT a Verilog-2005 reserved word, so a V2005 module TYPE
        // literally named `sequence` and its instantiation (`sequence u(.o(o))`) must
        // STILL parse. A no-formals decl `sequence NAME ;` routes here on the cheap
        // 2-token guard. A PARAMETERIZED decl `sequence NAME ( … ) ;` (slice A1)
        // collides with a positional/named module instantiation of the same shape;
        // disambiguate by a content-independent forward scan for the terminating
        // `endsequence` (a decl always has one; an instantiation never does). The
        // scan is what lets `sequence u(.o(o));` (no `endsequence`) stay an
        // instantiation while `sequence s(x,y); … endsequence` is a decl.
        // `property` IS a hard keyword (`Kw::Property`) — it cannot name a module, so
        // there is no masking there.
        if self.at_ident_kw("sequence")
            && matches!(
                self.peek_at(1),
                Some(TokenKind::Word(WordKind::Ident)) | Some(TokenKind::EscapedIdent)
            )
            && (self.peek_at(2) == Some(TokenKind::Semi)
                || (self.peek_at(2) == Some(TokenKind::LParen) && self.is_sequence_decl_ahead()))
        {
            return self.parse_sequence_decl();
        }
        if self.at_kw(Kw::Property) {
            return self.parse_property_decl();
        }
        // N5: functional-coverage model `covergroup NAME; … endgroup`.
        if self.at_kw(Kw::Covergroup) {
            return self.parse_covergroup();
        }
        // N5: a covergroup INSTANCE `CG_TYPE NAME = new;` — distinguished from a module
        // instantiation (`CG_TYPE NAME ( … )`) by the `=` at lookahead 2. Placed before
        // the bare-ident instantiation arm.
        if self.is_ident()
            && matches!(
                self.peek_at(1),
                Some(TokenKind::Word(WordKind::Ident)) | Some(TokenKind::EscapedIdent)
            )
            && self.peek_at(2) == Some(TokenKind::Eq)
        {
            return self.parse_cover_instance();
        }
        // bare ident at module-item position ⇒ module instantiation.
        // (No keyword-led item matched above; in V2005 module scope a leading
        //  bare identifier can ONLY begin an instantiation — there is no
        //  bare-ident contassign/decl. The dispatch position itself is the
        //  disambiguation, so no multi-token lookahead is needed to decide.
        //  Gate PRIMITIVES (`and`/`or`/`buf`/…) are keyword-led, never reach
        //  this arm, and are not parsed in v1 — they fall through to the loud
        //  "expected module item" E2002 below.)
        if self.is_ident() {
            let module_name = self.ident().unwrap();
            return Some(ModuleItem::Instance(
                self.parse_module_instance(module_name),
            ));
        }
        self.error("module item");
        None
    }

    // ─────────────────────── module instantiation ───────────────────────
    /// Parse a module instantiation, given the already-consumed `module_name`.
    /// Grammar:  module_name [ #(param_overrides) ] inst_body {, inst_body} ;
    /// where     inst_body = inst_name [unpacked_dims] ( port_connections )
    ///
    /// Disambiguation: the caller reaches a bare ident at module-item position
    /// only after every keyword-led item is ruled out; in V2005 module scope a
    /// leading bare identifier can ONLY start an instantiation, so no lookahead
    /// is needed to decide. Gate primitives (and/or/not …) are NOT special-cased
    /// here — they lex as plain idents and so flow through this path; a true
    /// gate-primitive instance has no module body for elaborate to find and is a
    /// DEFERRED limitation (it still recovers as an ordinary instance shape).
    /// Always returns a `ModuleInstance` (recovery is internal: sync via the
    /// terminal `expect(Semi)` + per-list forward-progress guards).
    fn parse_module_instance(&mut self, module_name: Ident) -> ModuleInstance {
        let start = module_name.span;

        // optional parameter override list  #( … )
        let param_overrides = if self.peek() == Some(TokenKind::Hash) {
            self.bump(); // '#'
            self.parse_param_overrides()
        } else {
            Vec::new()
        };

        // one-or-more instance bodies, comma-separated
        let mut instances = Vec::new();
        loop {
            let before = self.pos;
            instances.push(self.parse_instance_item());
            if self.pos == before {
                self.bump(); // forward-progress guard
            }
            if !self.eat(TokenKind::Comma) {
                break;
            }
        }

        self.expect(TokenKind::Semi, "';' after instantiation");
        ModuleInstance {
            module_name,
            param_overrides,
            instances,
            span: start.to(self.prev_span()),
        }
    }

    // ───────────────────────── N5: functional coverage ─────────────────────
    /// `covergroup NAME [(args)] [@(event)]; ([LABEL:] coverpoint EXPR [{..}|iff..];)*
    /// endgroup` — a functional-coverage model. The header tail (args / sampling event)
    /// and any per-coverpoint bins/iff are SKIPPED to `;` in this slice (auto-bins,
    /// explicit `sample()`); only the coverpoint EXPR is captured.
    fn parse_covergroup(&mut self) -> Option<ModuleItem> {
        let start = self.cur_span();
        self.bump(); // `covergroup`
        let name = self.ident()?;
        // optional `( ports )` — skip balanced (covergroup args, slice-future).
        if self.peek() == Some(TokenKind::LParen) {
            let mut depth = 0i32;
            loop {
                match self.peek() {
                    Some(TokenKind::LParen) => depth += 1,
                    Some(TokenKind::RParen) => {
                        depth -= 1;
                        if depth == 0 {
                            self.bump();
                            break;
                        }
                    }
                    None => break,
                    _ => {}
                }
                self.bump();
            }
        }
        // optional `@(event)` sampling clock (slice F): auto-sample on this event.
        let clock = if self.peek() == Some(TokenKind::At) {
            Some(self.parse_sensitivity())
        } else {
            None
        };
        // skip any remaining header tail (`with function sample(...)`, etc.) to `;`.
        while !matches!(self.peek(), Some(TokenKind::Semi) | None) {
            self.bump();
        }
        self.expect(TokenKind::Semi, "';' after covergroup header");
        let mut points = Vec::new();
        let mut crosses = Vec::new();
        let mut cg_at_least: Option<Expr> = None;
        loop {
            if self.at_kw(Kw::Endgroup) || self.peek().is_none() {
                break;
            }
            // optional `LABEL :`
            let label = if self.is_ident() && self.peek_at(1) == Some(TokenKind::Colon) {
                let l = self.ident().unwrap();
                self.bump(); // ':'
                Some(l)
            } else {
                None
            };
            if self.at_ident_kw("cross") {
                if let Some(cr) = self.parse_cross(label) {
                    crosses.push(cr);
                }
                continue;
            }
            // covergroup-level `option.NAME = expr;` (slice D): only `at_least` affects
            // the measured %; other options (goal/comment/per_instance/…) are accepted
            // and ignored (they do not change the coverage value in this model).
            if self.at_ident_kw("option") || self.at_ident_kw("type_option") {
                if let Some((name, val)) = self.parse_cover_option() {
                    if name == "at_least" {
                        cg_at_least = Some(val);
                    }
                }
                continue;
            }
            if self.at_kw(Kw::Coverpoint) {
                let cp_start = self.cur_span();
                self.bump(); // `coverpoint`
                let expr = self.expr(0);
                // optional coverpoint-level `iff (G)` guard (slice B).
                let iff = self.parse_cover_iff();
                // optional `{ bin* | option* }` body (else a bare `;`).
                let (bins, at_least, weight) = if self.peek() == Some(TokenKind::LBrace) {
                    let b = self.parse_coverpoint_body();
                    self.eat(TokenKind::Semi); // `;` after `}` is optional
                    b
                } else {
                    self.expect(TokenKind::Semi, "';' after coverpoint");
                    (Vec::new(), None, None)
                };
                points.push(Coverpoint {
                    label,
                    expr,
                    iff,
                    bins,
                    at_least,
                    weight,
                    span: cp_start.to(self.prev_span()),
                });
            } else {
                // an unsupported covergroup item (cross / option / …) — loud, skip to `;`.
                self.error("`coverpoint` in covergroup (cross/option are a follow-on)");
                while !matches!(self.peek(), Some(TokenKind::Semi) | None) {
                    self.bump();
                }
                self.eat(TokenKind::Semi);
            }
        }
        if self.at_kw(Kw::Endgroup) {
            self.bump();
        } else {
            self.error("`endgroup`");
        }
        // optional `: NAME` after endgroup
        if self.peek() == Some(TokenKind::Colon) {
            self.bump();
            let _ = self.ident();
        }
        Some(ModuleItem::Covergroup(CovergroupDecl {
            name,
            points,
            crosses,
            clock,
            at_least: cg_at_least,
            span: start.to(self.prev_span()),
        }))
    }

    /// `CG_TYPE NAME = new [(args)] ;` — a covergroup instance.
    fn parse_cover_instance(&mut self) -> Option<ModuleItem> {
        let start = self.cur_span();
        let cg_type = self.ident()?;
        let name = self.ident()?;
        self.expect(TokenKind::Eq, "'=' in covergroup instance");
        if self.at_ident_kw("new") {
            self.bump();
        } else {
            self.error("`new` in covergroup instance");
        }
        // optional `( args )` — skip balanced.
        if self.peek() == Some(TokenKind::LParen) {
            let mut depth = 0i32;
            loop {
                match self.peek() {
                    Some(TokenKind::LParen) => depth += 1,
                    Some(TokenKind::RParen) => {
                        depth -= 1;
                        if depth == 0 {
                            self.bump();
                            break;
                        }
                    }
                    None => break,
                    _ => {}
                }
                self.bump();
            }
        }
        self.expect(TokenKind::Semi, "';' after covergroup instance");
        Some(ModuleItem::CoverInstance(CoverInstance {
            cg_type,
            name,
            span: start.to(self.prev_span()),
        }))
    }

    /// `[LABEL:] cross cp_a, cp_b [, …] [{ … }] ;` — a cross of named coverpoints
    /// (slice C; the `cross` ident is at the cursor, LABEL already consumed). A cross
    /// SELECT body `{ binsof/intersect }` is loud-rejected and balanced-skipped.
    fn parse_cross(&mut self, label: Option<Ident>) -> Option<CrossSpec> {
        let start = self.cur_span();
        self.bump(); // `cross`
        let mut points = Vec::new();
        loop {
            let before = self.pos;
            if let Some(id) = self.ident() {
                points.push(id);
            }
            if self.pos == before {
                self.bump(); // forward-progress guard
            }
            if !self.eat(TokenKind::Comma) {
                break;
            }
        }
        // optional cross SELECT body `{ binsof … }` — follow-on; loud + balanced skip.
        if self.peek() == Some(TokenKind::LBrace) {
            self.error("cross select body (binsof/intersect) (follow-on)");
            let mut depth = 0i32;
            loop {
                match self.peek() {
                    Some(TokenKind::LBrace) => {
                        depth += 1;
                        self.bump();
                    }
                    Some(TokenKind::RBrace) => {
                        depth -= 1;
                        self.bump();
                        if depth == 0 {
                            break;
                        }
                    }
                    None => break,
                    _ => {
                        self.bump();
                    }
                }
            }
        }
        self.expect(TokenKind::Semi, "';' after cross");
        Some(CrossSpec {
            name: label,
            points,
            span: start.to(self.prev_span()),
        })
    }

    /// Optional `iff ( expr )` guard after a coverpoint expr or a bin RHS (slice B).
    /// `iff` is a contextual ident here (not a reserved keyword globally).
    fn parse_cover_iff(&mut self) -> Option<Expr> {
        if !self.at_ident_kw("iff") {
            return None;
        }
        self.bump(); // `iff`
        self.expect(TokenKind::LParen, "'(' after iff");
        let g = self.expr(0);
        self.expect(TokenKind::RParen, "')' after iff guard");
        Some(g)
    }

    /// Parse a coverpoint body `{ (bin | option)* }` (the opening `{` is at the
    /// cursor). Returns `(bins, at_least, weight)`. Each bin is `KIND NAME[array] =
    /// ( {range_list} | default ) [iff(G)] ;`. Unsupported bin forms
    /// (wildcard/transition/`binsof`/`intersect`/junk) are LOUD-rejected and
    /// balanced-skipped — never silently dropped. `option.at_least`/`option.weight`
    /// are captured; other `option.*` are accepted and ignored.
    #[allow(clippy::type_complexity)]
    fn parse_coverpoint_body(&mut self) -> (Vec<BinSpec>, Option<Expr>, Option<Expr>) {
        self.bump(); // `{`
        let mut bins = Vec::new();
        let mut at_least = None;
        let mut weight = None;
        loop {
            if matches!(self.peek(), Some(TokenKind::RBrace) | None) {
                break;
            }
            let before = self.pos;
            if self.at_ident_kw("option") || self.at_ident_kw("type_option") {
                if let Some((name, val)) = self.parse_cover_option() {
                    match name.as_str() {
                        "at_least" => at_least = Some(val),
                        "weight" => weight = Some(val),
                        _ => {} // accepted-ignored (does not change the measured %)
                    }
                }
            } else if let Some(b) = self.parse_bin_spec() {
                bins.push(b);
            }
            if self.pos == before {
                self.bump(); // forward-progress guard
            }
        }
        self.eat(TokenKind::RBrace);
        (bins, at_least, weight)
    }

    /// `option.NAME = expr ;` / `type_option.NAME = expr ;` (the `option` ident is at
    /// the cursor). Returns `(NAME, value-expr)`. Slice D.
    fn parse_cover_option(&mut self) -> Option<(String, Expr)> {
        self.bump(); // `option` / `type_option`
        self.expect(TokenKind::Dot, "'.' after option");
        let name = self.ident()?;
        self.expect(TokenKind::Eq, "'=' in option");
        let val = self.expr(0);
        self.expect(TokenKind::Semi, "';' after option");
        Some((name.name, val))
    }

    /// One `KIND NAME[array] = RHS [iff(G)] ;` bin. Returns `None` (after a loud
    /// diagnostic + balanced skip to the bin's `;`) for unsupported forms.
    fn parse_bin_spec(&mut self) -> Option<BinSpec> {
        let start = self.cur_span();
        // `wildcard bins …` — follow-on; loud-reject.
        if self.at_ident_kw("wildcard") {
            self.error("wildcard coverage bins (follow-on)");
            self.skip_bin_to_semi();
            return None;
        }
        let kind = if self.at_ident_kw("bins") {
            BinKind::Regular
        } else if self.at_ident_kw("ignore_bins") {
            BinKind::Ignore
        } else if self.at_ident_kw("illegal_bins") {
            BinKind::Illegal
        } else {
            // `cross`/`option`/junk inside a coverpoint body — loud-reject.
            self.error("`bins`/`ignore_bins`/`illegal_bins` in coverpoint body");
            self.skip_bin_to_semi();
            return None;
        };
        self.bump(); // the bins-kind ident
        let name = self.ident()?;
        // optional array suffix: `[]` (unsized) or `[N]` (fixed).
        let array = if self.peek() == Some(TokenKind::LBracket) {
            self.bump(); // `[`
            if self.eat(TokenKind::RBracket) {
                BinArray::Unsized
            } else {
                let n = self.expr(0);
                self.expect(TokenKind::RBracket, "']' in bin array size");
                BinArray::Fixed(n)
            }
        } else {
            BinArray::Scalar
        };
        self.expect(TokenKind::Eq, "'=' in bin definition");
        // RHS: `default` | `{ open_range_list }` | `( trans_list )`(loud).
        let (values, is_default) = if self.at_kw(Kw::Default) {
            self.bump(); // `default`
            if self.at_ident_kw("sequence") {
                self.error("default sequence (transition) bins (follow-on)");
                self.skip_bin_to_semi();
                return None;
            }
            (Vec::new(), true)
        } else if self.peek() == Some(TokenKind::LParen) {
            self.error("transition coverage bins (follow-on)");
            self.skip_bin_to_semi();
            return None;
        } else if self.peek() == Some(TokenKind::LBrace) {
            (self.parse_open_range_list(), false)
        } else {
            self.error("bin value set `{...}` or `default`");
            self.skip_bin_to_semi();
            return None;
        };
        let iff = self.parse_cover_iff();
        self.expect(TokenKind::Semi, "';' after bin");
        Some(BinSpec {
            name,
            kind,
            array,
            values,
            is_default,
            iff,
            span: start.to(self.prev_span()),
        })
    }

    /// Parse `{ range (, range)* }` (the opening `{` is at the cursor).
    fn parse_open_range_list(&mut self) -> Vec<CoverRange> {
        self.bump(); // `{`
        let mut out = Vec::new();
        loop {
            if matches!(self.peek(), Some(TokenKind::RBrace) | None) {
                break;
            }
            let before = self.pos;
            if let Some(r) = self.parse_cover_range() {
                out.push(r);
            }
            if self.pos == before {
                self.bump(); // forward-progress guard
            }
            if !self.eat(TokenKind::Comma) {
                break;
            }
        }
        self.eat(TokenKind::RBrace);
        out
    }

    /// One open_range_list element: `[ end : end ]` (inclusive range) or a single
    /// value `expr` (`lo==hi`). A transition arrow `=>` after a value is loud-rejected.
    fn parse_cover_range(&mut self) -> Option<CoverRange> {
        if self.peek() == Some(TokenKind::LBracket) {
            self.bump(); // `[`
            let lo = self.parse_range_end();
            self.expect(TokenKind::Colon, "':' in range");
            let hi = self.parse_range_end();
            self.expect(TokenKind::RBracket, "']' in range");
            Some(CoverRange { lo, hi })
        } else {
            let v = self.expr(0);
            // transition `=>` (lexes as `=` then `>`) — follow-on.
            if self.peek() == Some(TokenKind::Eq) && self.peek_at(1) == Some(TokenKind::Gt) {
                self.error("transition coverage bins (follow-on)");
                return None;
            }
            let end = RangeEnd::Val(v);
            Some(CoverRange {
                lo: end.clone(),
                hi: end,
            })
        }
    }

    /// A range endpoint: `$` (type extreme) or a constant expression.
    fn parse_range_end(&mut self) -> RangeEnd {
        if self.peek() == Some(TokenKind::Dollar) {
            self.bump();
            RangeEnd::TypeExtreme
        } else {
            RangeEnd::Val(self.expr(0))
        }
    }

    /// Balanced skip to the terminating `;` of a malformed bin (recovery). Stops at
    /// a depth-0 `}` (the body terminator) without consuming it.
    fn skip_bin_to_semi(&mut self) {
        let mut depth = 0i32;
        loop {
            match self.peek() {
                None => break,
                Some(TokenKind::RBrace) if depth == 0 => break,
                Some(TokenKind::Semi) if depth == 0 => {
                    self.bump();
                    break;
                }
                Some(TokenKind::LParen | TokenKind::LBracket | TokenKind::LBrace) => {
                    depth += 1;
                    self.bump();
                }
                Some(TokenKind::RParen | TokenKind::RBracket | TokenKind::RBrace) => {
                    depth -= 1;
                    self.bump();
                }
                _ => {
                    self.bump();
                }
            }
        }
    }

    /// Parse `( param_overrides )` after a consumed `#`.
    /// `.NAME(expr)` ⇒ ParamConn::Named ; bare `expr` ⇒ ParamConn::Positional.
    /// The first token being `Dot` selects the named form for the whole list.
    /// An empty `#()` is legal (yields an empty Vec).
    fn parse_param_overrides(&mut self) -> Vec<ParamConn> {
        let mut out = Vec::new();
        if !self.expect(TokenKind::LParen, "'(' after '#'") {
            return out;
        }
        if self.peek() == Some(TokenKind::RParen) {
            self.bump(); // empty `#()`
            return out;
        }
        let named = self.peek() == Some(TokenKind::Dot);
        loop {
            let before = self.pos;
            if named {
                out.push(self.parse_named_param_conn());
            } else {
                // positional override: a single const-expr (never empty)
                out.push(ParamConn::Positional(self.expr(0)));
            }
            if self.pos == before {
                self.bump(); // progress guard
            }
            if !self.eat(TokenKind::Comma) {
                break;
            }
        }
        self.expect(TokenKind::RParen, "')' closing parameter overrides");
        out
    }

    /// `.NAME(expr)` | `.NAME()`  → ParamConn::Named { name, value, span }.
    fn parse_named_param_conn(&mut self) -> ParamConn {
        let start = self.cur_span();
        self.expect(TokenKind::Dot, "'.' in named parameter override");
        let name = self.ident().unwrap_or(Ident {
            name: String::new(),
            span: self.cur_span(),
        });
        self.expect(TokenKind::LParen, "'(' after parameter name");
        let value = if self.peek() == Some(TokenKind::RParen) {
            None // `.W()` — explicitly-empty override
        } else {
            Some(self.expr(0))
        };
        self.expect(TokenKind::RParen, "')' after parameter value");
        ParamConn::Named {
            name,
            value,
            span: start.to(self.prev_span()),
        }
    }

    /// One instance: inst_name [unpacked_dims] ( port_connections )
    fn parse_instance_item(&mut self) -> InstanceItem {
        let start = self.cur_span();
        let name = self.ident().unwrap_or(Ident {
            name: String::new(),
            span: self.cur_span(),
        });

        // optional instance-array dims: `u_x [3:0] (...)` / `u_x [4] (...)`
        let mut unpacked = Vec::new();
        while self.at_dim_start() {
            match self.parse_dim() {
                Some(d) => unpacked.push(d),
                None => break,
            }
        }

        let conns = self.parse_port_conns();
        InstanceItem {
            name,
            unpacked,
            conns,
            span: start.to(self.prev_span()),
        }
    }

    /// `( … )` port-connection list.
    ///   first element `.NAME(...)`      ⇒ Named
    ///   first element `.*`               ⇒ implicit (DEFERRED: stub → empty Named)
    ///   first element bare expr / empty  ⇒ Positional (empty `()` ⇒ Positional([]))
    fn parse_port_conns(&mut self) -> PortConnList {
        if !self.expect(TokenKind::LParen, "'(' before port connections") {
            // recovered with no '(' — synthesize an empty positional list
            return PortConnList::Positional(Vec::new());
        }
        // empty `()` ⇒ zero-arity positional
        if self.peek() == Some(TokenKind::RParen) {
            self.bump();
            return PortConnList::Positional(Vec::new());
        }
        // `.*` implicit connection (DEFERRED). `.*` = Dot then Star (no DotStar token).
        if self.peek() == Some(TokenKind::Dot)
            && self.toks.get(self.pos + 1).map(|t| t.kind) == Some(TokenKind::Star)
        {
            self.error("(.* implicit port connection not yet supported; ignored)");
            self.bump(); // '.'
            self.bump(); // '*'
                         // tolerate any trailing explicit conns after `.*` by skipping to ')'
            while !self.at_eof() && self.peek() != Some(TokenKind::RParen) {
                self.bump();
            }
            self.expect(TokenKind::RParen, "')' after '.*'");
            return PortConnList::Named(Vec::new());
        }

        // named iff the first connection starts with a dot
        let named = self.peek() == Some(TokenKind::Dot);
        if named {
            let mut conns = Vec::new();
            loop {
                let before = self.pos;
                conns.push(self.parse_named_port_conn());
                if self.pos == before {
                    self.bump();
                }
                if !self.eat(TokenKind::Comma) {
                    break;
                }
            }
            self.expect(TokenKind::RParen, "')' closing port connections");
            PortConnList::Named(conns)
        } else {
            // positional: each element is `expr` OR empty (a skipped port → None).
            let mut conns: Vec<Option<Expr>> = Vec::new();
            loop {
                match self.peek() {
                    // an empty slot: `,` or `)` where an expr would start
                    Some(TokenKind::Comma) | Some(TokenKind::RParen) => conns.push(None),
                    _ => conns.push(Some(self.expr(0))),
                }
                if !self.eat(TokenKind::Comma) {
                    break;
                }
            }
            self.expect(TokenKind::RParen, "')' closing port connections");
            PortConnList::Positional(conns)
        }
    }

    /// `.PORT(expr)` | `.PORT()`  → PortConn { name, value, span }.
    /// `.PORT()` (explicitly-unconnected) ⇒ value = None.
    fn parse_named_port_conn(&mut self) -> PortConn {
        let start = self.cur_span();
        self.expect(TokenKind::Dot, "'.' in named port connection");
        let name = self.ident().unwrap_or(Ident {
            name: String::new(),
            span: self.cur_span(),
        });
        self.expect(TokenKind::LParen, "'(' after port name");
        let value = if self.peek() == Some(TokenKind::RParen) {
            None // `.clk()` — explicitly unconnected
        } else {
            Some(self.expr(0))
        };
        self.expect(TokenKind::RParen, "')' after port expression");
        PortConn {
            name,
            value,
            span: start.to(self.prev_span()),
        }
    }

    fn parse_port_decl(&mut self) -> Option<PortDecl> {
        let start = self.cur_span();
        let dir = match self.peek() {
            Some(TokenKind::Word(WordKind::Keyword(Kw::Input))) => {
                self.bump();
                PortDir::Input
            }
            Some(TokenKind::Word(WordKind::Keyword(Kw::Output))) => {
                self.bump();
                PortDir::Output
            }
            _ => {
                self.bump();
                PortDir::Inout
            }
        };
        let net_or_var = self.net_var_kind();
        if net_or_var.is_some() {
            self.bump();
        }
        let signed = self.opt_signed();
        let range = self.opt_range();
        let mut names = Vec::new();
        loop {
            if let Some(id) = self.ident() {
                names.push(id);
            }
            if !self.eat(TokenKind::Comma) {
                break;
            }
        }
        self.expect(TokenKind::Semi, "';'");
        Some(PortDecl {
            dir,
            net_or_var,
            signed,
            range,
            names,
            span: start.to(self.prev_span()),
        })
    }

    fn parse_net_var(&mut self) -> Option<NetVarDecl> {
        let start = self.cur_span();
        let kind = self.net_var_kind().unwrap();
        self.bump();
        let signed = self.opt_signed();
        let range = self.opt_range();
        let packed = self.opt_packed_dims(); // additional packed dims `logic [3:0][7:0]`
        let names = self.parse_decl_name_list()?;
        self.expect(TokenKind::Semi, "';'");
        Some(NetVarDecl {
            kind,
            signed,
            range,
            packed,
            names,
            lifetime: None,
            span: start.to(self.prev_span()),
        })
    }

    /// Comma-separated declarator list: `a, b[3:0], c = init`. Shared by
    /// `parse_net_var` and the typedef-name decl path. Does NOT consume the `;`.
    fn parse_decl_name_list(&mut self) -> Option<Vec<DeclName>> {
        let mut names = Vec::new();
        loop {
            let n_start = self.cur_span();
            let name = self.ident()?;
            let mut unpacked = Vec::new();
            while self.at_dim_start() {
                match self.parse_dim() {
                    Some(d) => unpacked.push(d),
                    None => break,
                }
            }
            let init = if self.eat(TokenKind::Eq) {
                Some(self.expr(0))
            } else {
                None
            };
            names.push(DeclName {
                name,
                unpacked,
                init,
                span: n_start.to(self.prev_span()),
            });
            if !self.eat(TokenKind::Comma) {
                break;
            }
        }
        Some(names)
    }

    /// If the current token names a known typedef, return its resolved underlying
    /// type (peek only — the caller commits the decl). `None` ⇒ not a type name.
    fn peek_typedef_name(&self) -> Option<TypeInfo> {
        if self.is_ident() {
            return self.typedefs.get(self.cur_text()).cloned();
        }
        None
    }

    /// `T name1, name2 = init, …;` where the leading type-name resolved to `info`.
    fn parse_typed_decl(&mut self, info: TypeInfo) -> Option<NetVarDecl> {
        let start = self.cur_span();
        let tyname = self.cur_text().to_string();
        self.bump(); // the type-name identifier
        let names = self.parse_decl_name_list()?;
        self.expect(TokenKind::Semi, "';'");
        // If this is a struct type, bind each declared name → type so `var.field`
        // member accesses can be desugared to part-selects.
        if self.struct_layouts.contains_key(&tyname) {
            for n in &names {
                self.var_struct.insert(n.name.name.clone(), tyname.clone());
            }
        }
        Some(NetVarDecl {
            kind: info.kind,
            signed: info.signed,
            range: info.range,
            packed: info.packed,
            names,
            lifetime: None,
            span: start.to(self.prev_span()),
        })
    }

    /// `typedef enum [base] { L0, L1 = expr, … } name;` (Phase-2). Registers
    /// `name` in `self.typedefs` (so a later `name var;` parses) and returns the
    /// AST node so elaborate can register the labels as integer constants.
    fn parse_typedef(&mut self) -> Option<ModuleItem> {
        let start = self.cur_span();
        self.bump(); // `typedef`
        if self.at_kw(Kw::Struct) {
            return self.parse_typedef_struct(start);
        }
        if !self.at_kw(Kw::Enum) {
            // `typedef logic [7:0] byte_t;` — plain alias to a net/var type.
            if self.net_var_kind().is_some() {
                return self.parse_typedef_alias(start);
            }
            // unpacked struct / union forms are out of v1 scope.
            self.error("`enum`, `struct packed`, or a type after `typedef`");
            self.synchronize();
            return Some(ModuleItem::Error(start.to(self.prev_span())));
        }
        self.bump(); // `enum`
                     // Optional packed base: `enum logic [1:0] {…}` or `enum [1:0] {…}`.
        let base = if self.net_var_kind().is_some() {
            self.bump(); // base kind keyword (logic/reg/integer/…)
            let _ = self.opt_signed();
            self.opt_range()
        } else {
            self.opt_range()
        };
        self.expect(TokenKind::LBrace, "'{' for enum body");
        let mut labels = Vec::new();
        if self.peek() != Some(TokenKind::RBrace) {
            loop {
                let name = self.ident()?;
                let value = if self.eat(TokenKind::Eq) {
                    Some(self.expr(0))
                } else {
                    None
                };
                labels.push(EnumLabel { name, value });
                if !self.eat(TokenKind::Comma) {
                    break;
                }
            }
        }
        self.expect(TokenKind::RBrace, "'}' to close enum body");
        let tname = self.ident()?;
        self.expect(TokenKind::Semi, "';'");
        // Enum storage is `int` (32-bit signed) unless a packed base range was
        // given, in which case a `logic` vector of that range.
        let info = match &base {
            Some(r) => TypeInfo {
                kind: NetVarKind::Logic,
                signed: false,
                range: Some(r.clone()),
                packed: Vec::new(),
            },
            None => TypeInfo {
                kind: NetVarKind::Integer,
                signed: true,
                range: None,
                packed: Vec::new(),
            },
        };
        self.typedefs.insert(tname.name.clone(), info);
        Some(ModuleItem::Typedef(TypedefDecl {
            name: tname,
            kind: TypedefKind::Enum { base, labels },
            span: start.to(self.prev_span()),
        }))
    }

    /// `typedef <kind> [signed] [range] [packed] name;` — a plain type alias.
    /// `start` is the span of the leading `typedef` keyword (already consumed).
    fn parse_typedef_alias(&mut self, start: Span) -> Option<ModuleItem> {
        let kind = self.net_var_kind().unwrap();
        self.bump(); // kind keyword
        let signed = self.opt_signed();
        let range = self.opt_range();
        let packed = self.opt_packed_dims();
        let tname = self.ident()?;
        self.expect(TokenKind::Semi, "';'");
        self.typedefs.insert(
            tname.name.clone(),
            TypeInfo {
                kind,
                signed,
                range: range.clone(),
                packed: packed.clone(),
            },
        );
        Some(ModuleItem::Typedef(TypedefDecl {
            name: tname,
            kind: TypedefKind::Alias {
                kind,
                signed,
                range,
                packed,
            },
            span: start.to(self.prev_span()),
        }))
    }

    /// `typedef struct packed { <type> f1, f2; … } name;` (Phase-2). Members are
    /// laid out MSB-first into one flat `logic [W-1:0]` vector; the layout is
    /// recorded so `name var;` resolves and `var.field` desugars to a part-select.
    /// `start` is the span of the leading `typedef` keyword (already consumed).
    fn parse_typedef_struct(&mut self, start: Span) -> Option<ModuleItem> {
        self.bump(); // `struct`
        if !self.eat_kw(Kw::Packed) {
            // unpacked struct has no flat layout in v1 — reject loudly.
            self.error("`packed` after `struct` (unpacked struct unsupported in v1)");
            self.synchronize();
            return Some(ModuleItem::Error(start.to(self.prev_span())));
        }
        let _ = self.opt_signed(); // `struct packed signed` — sign ignored for layout
        self.expect(TokenKind::LBrace, "'{' for struct body");
        let mut members = Vec::new();
        while self.peek() != Some(TokenKind::RBrace) && !self.at_eof() {
            let before = self.pos;
            let m_start = self.cur_span();
            let Some(kind) = self.net_var_kind() else {
                self.error("a net/var type in struct member");
                break;
            };
            self.bump(); // kind keyword
            let signed = self.opt_signed();
            let range = self.opt_range();
            loop {
                let Some(name) = self.ident() else { break };
                members.push(StructMember {
                    name,
                    kind,
                    signed,
                    range: range.clone(),
                    span: m_start.to(self.prev_span()),
                });
                if !self.eat(TokenKind::Comma) {
                    break;
                }
            }
            self.expect(TokenKind::Semi, "';'");
            if self.pos == before {
                self.bump(); // forward-progress guard
            }
        }
        self.expect(TokenKind::RBrace, "'}' to close struct body");
        let tname = self.ident()?;
        self.expect(TokenKind::Semi, "';'");
        // Compute each member width (constant-literal ranges only in v1).
        let mut widths = Vec::with_capacity(members.len());
        for m in &members {
            match self.member_width(&m.range) {
                Some(w) if w > 0 => widths.push(w),
                _ => {
                    self.error_at(
                        m.span,
                        "struct member width must be a constant-literal range in v1",
                    );
                    widths.push(1);
                }
            }
        }
        let total: u32 = widths.iter().sum();
        // Lay out MSB-first: first member occupies the high bits.
        let mut off = total;
        let mut fields = Vec::with_capacity(members.len());
        for (m, w) in members.iter().zip(&widths) {
            off -= w;
            fields.push((m.name.name.clone(), off, *w));
        }
        self.struct_layouts
            .insert(tname.name.clone(), StructLayout { fields });
        self.typedefs.insert(
            tname.name.clone(),
            TypeInfo {
                kind: NetVarKind::Logic,
                signed: false,
                range: Some(Self::dec_range(total.saturating_sub(1))),
                packed: Vec::new(),
            },
        );
        Some(ModuleItem::Typedef(TypedefDecl {
            name: tname,
            kind: TypedefKind::Struct { members },
            span: start.to(self.prev_span()),
        }))
    }

    /// Width of a struct member from its range. `None` ⇒ scalar (1). Only
    /// constant-literal bounds fold (`[7:0]`, `[8-1:0]`); param widths return `None`.
    fn member_width(&self, range: &Option<Range>) -> Option<u32> {
        match range {
            None => Some(1),
            Some(r) => {
                let msb = Self::const_lit(&r.msb)?;
                let lsb = Self::const_lit(&r.lsb)?;
                Some(msb.abs_diff(lsb) as u32 + 1)
            }
        }
    }

    /// Fold a constant-literal expression to `i64` at parse time (decimal literals
    /// and +/-/* of them). Returns `None` for anything non-constant.
    fn const_lit(e: &Expr) -> Option<i64> {
        match &e.kind {
            ExprKind::IntLit {
                kind: IntLitKind::Decimal,
                raw,
            } => raw
                .chars()
                .filter(|c| *c != '_')
                .collect::<String>()
                .parse::<i64>()
                .ok(),
            ExprKind::Unary {
                op: UnOp::Minus,
                operand,
            } => Some(-Self::const_lit(operand)?),
            ExprKind::Binary { op, lhs, rhs } => {
                let a = Self::const_lit(lhs)?;
                let b = Self::const_lit(rhs)?;
                match op {
                    BinOp::Add => Some(a + b),
                    BinOp::Sub => Some(a - b),
                    BinOp::Mul => Some(a * b),
                    _ => None,
                }
            }
            _ => None,
        }
    }

    /// A `[hi:0]` range made of decimal literals, for the synthesized struct vector.
    fn dec_range(hi: u32) -> Range {
        Range {
            msb: Self::dec_lit(hi, Span::new(0, 0)),
            lsb: Self::dec_lit(0, Span::new(0, 0)),
            span: Span::new(0, 0),
        }
    }

    /// A decimal integer-literal expression with the given value.
    fn dec_lit(v: u32, span: Span) -> Expr {
        Expr {
            kind: ExprKind::IntLit {
                kind: IntLitKind::Decimal,
                raw: v.to_string(),
            },
            span,
        }
    }

    /// If `path` is `var.field` where `var` is a packed-struct variable and `field`
    /// is one of its members, return `(base_path_to_var, lsb_offset, width)`.
    fn struct_field_select(&self, path: &HierPath) -> Option<(HierPath, u32, u32)> {
        if path.segments.len() != 2 {
            return None;
        }
        let tyname = self.var_struct.get(&path.segments[0].name)?;
        let (off, w) = self
            .struct_layouts
            .get(tyname)?
            .field(&path.segments[1].name)?;
        let base = HierPath {
            segments: vec![path.segments[0].clone()],
            span: path.segments[0].span,
        };
        Some((base, off, w))
    }

    fn parse_cont_assign(&mut self) -> Option<ContinuousAssign> {
        let start = self.cur_span();
        self.bump(); // assign
        let delay = if self.peek() == Some(TokenKind::Hash) {
            self.parse_delay()
        } else {
            None
        };
        let mut assigns = Vec::new();
        loop {
            let lv = self.parse_lvalue();
            self.expect(TokenKind::Eq, "'=' in assign");
            let rhs = self.expr(0);
            assigns.push((lv, rhs));
            if !self.eat(TokenKind::Comma) {
                break;
            }
        }
        self.expect(TokenKind::Semi, "';'");
        Some(ContinuousAssign {
            delay,
            assigns,
            span: start.to(self.prev_span()),
        })
    }
    /// `#5` | `#(d)` | `#(r,f)` | `#(r,f,t)`. Each paren'd value may be mintypmax
    /// `1:2:3` (verdict M2). Uses `parse_delay_value` which accepts `a:b:c`.
    fn parse_delay(&mut self) -> Option<Delay> {
        let start = self.cur_span();
        self.bump(); // '#'
        let mut values = Vec::new();
        if self.eat(TokenKind::LParen) {
            loop {
                values.push(self.parse_delay_value());
                if !self.eat(TokenKind::Comma) {
                    break;
                }
            }
            self.expect(TokenKind::RParen, "')'");
        } else {
            // bare `#delay_value`: a single number/ident (no parens) — high bp,
            // no mintypmax (a bare `#1:2:3` is not legal V2005 delay).
            values.push(self.expr(UNARY_BP));
        }
        Some(Delay {
            values,
            span: start.to(self.prev_span()),
        })
    }
    /// A delay value inside `#(…)`: `expr` or `min:typ:max` (verdict M2).
    fn parse_delay_value(&mut self) -> Expr {
        let start = self.cur_span();
        let first = self.expr(0);
        if self.peek() == Some(TokenKind::Colon) {
            self.bump();
            let typ = self.expr(0);
            self.expect(TokenKind::Colon, "':' in min:typ:max delay");
            let max = self.expr(0);
            Expr {
                kind: ExprKind::MinTypMax {
                    min: Box::new(first),
                    typ: Box::new(typ),
                    max: Box::new(max),
                },
                span: start.to(self.prev_span()),
            }
        } else {
            first
        }
    }

    /// LHS = concat of selects/idents only. Parse directly to `Lvalue`.
    fn parse_lvalue(&mut self) -> Lvalue {
        if self.peek() == Some(TokenKind::LBrace) {
            let start = self.cur_span();
            self.bump();
            let mut parts = Vec::new();
            loop {
                parts.push(self.parse_lvalue());
                if !self.eat(TokenKind::Comma) {
                    break;
                }
            }
            self.expect(TokenKind::RBrace, "'}'");
            return Lvalue::Concat {
                parts,
                span: start.to(self.prev_span()),
            };
        }
        let Some(path) = self.hier_path() else {
            let s = self.cur_span();
            return Lvalue::Error(s);
        };
        // packed-struct member target `s.field = …` → constant part-select lvalue.
        let mut lv = if let Some((base, off, w)) = self.struct_field_select(&path) {
            let span = path.span;
            Lvalue::PartSelect {
                base: Box::new(Lvalue::Ident(base)),
                msb: Box::new(Self::dec_lit(off + w - 1, span)),
                lsb: Box::new(Self::dec_lit(off, span)),
                span,
            }
        } else {
            Lvalue::Ident(path)
        };
        loop {
            if self.peek() == Some(TokenKind::LBracket) {
                let start = lv.span();
                self.bump();
                let first = self.expr(0);
                lv = match self.peek() {
                    Some(TokenKind::Colon) => {
                        self.bump();
                        let lsb = self.expr(0);
                        self.expect(TokenKind::RBracket, "']'");
                        Lvalue::PartSelect {
                            base: Box::new(lv),
                            msb: Box::new(first),
                            lsb: Box::new(lsb),
                            span: start.to(self.prev_span()),
                        }
                    }
                    Some(TokenKind::PlusColon) => {
                        self.bump();
                        let w = self.expr(0);
                        self.expect(TokenKind::RBracket, "']'");
                        Lvalue::IndexedPart {
                            base: Box::new(lv),
                            offset: Box::new(first),
                            width: Box::new(w),
                            dir: PartDir::PlusColon,
                            span: start.to(self.prev_span()),
                        }
                    }
                    Some(TokenKind::MinusColon) => {
                        self.bump();
                        let w = self.expr(0);
                        self.expect(TokenKind::RBracket, "']'");
                        Lvalue::IndexedPart {
                            base: Box::new(lv),
                            offset: Box::new(first),
                            width: Box::new(w),
                            dir: PartDir::MinusColon,
                            span: start.to(self.prev_span()),
                        }
                    }
                    _ => {
                        self.expect(TokenKind::RBracket, "']'");
                        Lvalue::BitSelect {
                            base: Box::new(lv),
                            index: Box::new(first),
                            span: start.to(self.prev_span()),
                        }
                    }
                };
            } else if self.peek() == Some(TokenKind::Dot) && Self::is_indexed_hier_lval(&lv) {
                // HIER-REST②: `g[0].x = …` — fold the constant index into the
                // scope-segment name, mirroring the expression side.
                lv = self.parse_indexed_hier_lval(lv);
            } else {
                break;
            }
        }
        lv
    }

    /// True when `lv` is `name[idx]` — a bit-select lvalue rooted at a plain Ident.
    fn is_indexed_hier_lval(lv: &Lvalue) -> bool {
        matches!(lv, Lvalue::BitSelect { base, .. } if matches!(**base, Lvalue::Ident(_)))
    }

    /// LVALUE twin of [`Self::parse_indexed_hier`]: `g[0].x = …`.
    fn parse_indexed_hier_lval(&mut self, base: Lvalue) -> Lvalue {
        let start = base.span();
        let mut segs: Vec<Ident> = Vec::new();
        if let Lvalue::BitSelect { base: b, index, .. } = base {
            if let Lvalue::Ident(p) = *b {
                let n = p.segments.len();
                for (i, seg) in p.segments.into_iter().enumerate() {
                    if i + 1 == n {
                        let idx_str = self.const_index_string(&index);
                        segs.push(Ident {
                            name: format!("{}[{idx_str}]", seg.name),
                            span: seg.span,
                        });
                    } else {
                        segs.push(seg);
                    }
                }
            }
        }
        while self.eat(TokenKind::Dot) {
            match self.ident() {
                Some(id) => segs.push(id),
                None => break,
            }
        }
        let hi = segs.last().map(|s| s.span).unwrap_or(start);
        Lvalue::Ident(HierPath {
            segments: segs,
            span: start.to(hi),
        })
    }
}

// ════════════════════════ PR3: generate / genvar ════════════════════════
//
// Parse-only: build the hdl-ast `GenerateConstruct`/`GenItem` tree; elaborate
// unrolls it. Mirrors the procedural for/if/case shapes (PR2) but produces
// `GenItem`s, not `Stmt`s. Every loop over a sub-item list carries a
// forward-progress guard (`pos == before → bump`) so malformed input can never
// spin, matching the rest of the parser's recovery discipline.
impl<'t, 's> Parser<'t, 's> {
    /// `genvar i, j;` → `ModuleItem::Genvar{names, span}`. The `genvar` keyword is
    /// already at `peek()`. An empty/garbled name list still terminates at `;`.
    fn parse_genvar_decl(&mut self) -> ModuleItem {
        let start = self.cur_span();
        self.bump(); // `genvar`
        let mut names = Vec::new();
        if let Some(id) = self.ident() {
            names.push(id);
            while self.eat(TokenKind::Comma) {
                match self.ident() {
                    Some(id) => names.push(id),
                    None => break, // diagnosed by ident(); stop the list
                }
            }
        }
        self.expect(TokenKind::Semi, "';' after genvar declaration");
        ModuleItem::Genvar {
            names,
            span: start.to(self.prev_span()),
        }
    }

    /// `generate <gen_items> endgenerate`. Dispatch only calls this on the
    /// `generate` keyword; the SV bare-`if`/`for`/`case`-at-module-scope form is a
    /// DEFERRED variant.
    fn parse_generate_construct(&mut self) -> GenerateConstruct {
        let start = self.cur_span();
        self.bump(); // `generate`
        let items = self.parse_gen_items_until(&|p| p.at_kw(Kw::Endgenerate) || p.at_eof());
        self.expect(
            TokenKind::Word(WordKind::Keyword(Kw::Endgenerate)),
            "'endgenerate'",
        );
        GenerateConstruct {
            items,
            span: start.to(self.prev_span()),
        }
    }

    /// Parse `GenItem`s until `stop` is true (or EOF). Shared by the construct
    /// body, gen-blocks (`begin … end`), and case-item bodies. Forward-progress
    /// guarded.
    fn parse_gen_items_until(&mut self, stop: &dyn Fn(&Self) -> bool) -> Vec<GenItem> {
        let mut items = Vec::new();
        while !self.at_eof() && !stop(self) {
            let before = self.pos;
            if let Some(it) = self.parse_gen_item() {
                items.push(it);
            }
            if self.pos == before {
                self.bump(); // never spin on a stuck gen-item
            }
        }
        items
    }

    /// One generate item: `for` / `if` / `case` / `begin…end` block / genvar decl
    /// / a plain module-item (instance, cont-assign, net, procedural block). A
    /// stray `;` (empty item) is consumed and yields nothing.
    fn parse_gen_item(&mut self) -> Option<GenItem> {
        if self.eat(TokenKind::Semi) {
            return None; // empty generate item
        }
        if self.at_kw(Kw::For) {
            return Some(self.parse_gen_for());
        }
        if self.at_kw(Kw::If) {
            return Some(self.parse_gen_if());
        }
        if self.at_kw(Kw::Case) {
            return Some(self.parse_gen_case());
        }
        if self.at_kw(Kw::Begin) {
            return Some(self.parse_gen_block());
        }
        // genvar decls inside generate are legal — keep them wrapped so elaborate's
        // no-op handler ignores them (they never become nets).
        if self.at_kw(Kw::Genvar) {
            return Some(GenItem::Item(Box::new(self.parse_genvar_decl())));
        }
        // anything else → a plain module-item (instance / assign / net / proc / …).
        // `parse_module_item` returns None only after recording an error; wrap a
        // real item, else propagate None (the caller's progress guard syncs).
        self.parse_module_item()
            .map(|mi| GenItem::Item(Box::new(mi)))
    }

    /// `for ( genvar_id = e ; cond ; genvar_id = e ) gen_block`. A `begin : label`
    /// hoists its label onto the For node (see `parse_gen_branch`).
    fn parse_gen_for(&mut self) -> GenItem {
        let start = self.cur_span();
        self.bump(); // `for`
        self.expect(TokenKind::LParen, "'(' after generate 'for'");
        let init = self.parse_gen_assign();
        self.expect(TokenKind::Semi, "';' after generate-for init");
        let cond = self.expr(0);
        self.expect(TokenKind::Semi, "';' after generate-for cond");
        let step = self.parse_gen_assign();
        self.expect(TokenKind::RParen, "')' after generate-for header");
        let (label, body) = self.parse_gen_branch();
        GenItem::For {
            init,
            cond,
            step,
            label,
            body,
            span: start.to(self.prev_span()),
        }
    }

    /// `genvar_id = expr` (no trailing `;`) for a generate-for init/step. LHS is a
    /// single genvar identifier (the LRM restricts it — not a general lvalue).
    fn parse_gen_assign(&mut self) -> GenAssign {
        let start = self.cur_span();
        let lvalue = self.ident().unwrap_or(Ident {
            name: String::new(),
            span: start,
        });
        self.expect(TokenKind::Eq, "'=' in generate-for assignment");
        let value = self.expr(0);
        GenAssign {
            lvalue,
            value,
            span: start.to(self.prev_span()),
        }
    }

    /// `if ( cond ) gen_item [ else gen_item ]`. Dangling-else binds EAGERLY to the
    /// nearest `if` (same rule as the procedural parser).
    fn parse_gen_if(&mut self) -> GenItem {
        let start = self.cur_span();
        self.bump(); // `if`
        self.expect(TokenKind::LParen, "'(' after generate 'if'");
        let cond = self.expr(0);
        self.expect(TokenKind::RParen, "')' after generate-if condition");
        let (label, then_b) = self.parse_gen_branch();
        let else_b = if self.eat_kw(Kw::Else) {
            self.parse_gen_branch().1
        } else {
            Vec::new()
        };
        GenItem::If {
            cond,
            then_b,
            else_b,
            label,
            span: start.to(self.prev_span()),
        }
    }

    /// `case ( e ) { label{,label}: gen_item | default[:] gen_item } endcase`.
    fn parse_gen_case(&mut self) -> GenItem {
        let start = self.cur_span();
        self.bump(); // `case`
        self.expect(TokenKind::LParen, "'(' after generate 'case'");
        let scrutinee = self.expr(0);
        self.expect(TokenKind::RParen, "')' after generate-case scrutinee");
        let mut items = Vec::new();
        while !self.at_eof() && !self.at_kw(Kw::Endcase) {
            let before = self.pos;
            items.push(self.parse_gen_case_item());
            if self.pos == before {
                self.bump(); // never spin on a stuck case item
            }
        }
        self.expect(
            TokenKind::Word(WordKind::Keyword(Kw::Endcase)),
            "'endcase' for generate-case",
        );
        GenItem::Case {
            scrutinee,
            items,
            span: start.to(self.prev_span()),
        }
    }

    /// One generate-case item: `default [:] gen_item` | `label {, label} : gen_item`.
    fn parse_gen_case_item(&mut self) -> GenCaseItem {
        let start = self.cur_span();
        if self.eat_kw(Kw::Default) {
            self.eat(TokenKind::Colon); // ':' OPTIONAL after default
            let body = self.parse_gen_branch().1;
            return GenCaseItem::Default {
                body,
                span: start.to(self.prev_span()),
            };
        }
        let mut labels = vec![self.expr(0)];
        while self.eat(TokenKind::Comma) {
            labels.push(self.expr(0));
        }
        self.expect(TokenKind::Colon, "':' in generate-case item");
        let body = self.parse_gen_branch().1;
        GenCaseItem::Match {
            labels,
            body,
            span: start.to(self.prev_span()),
        }
    }

    /// `begin [: label] gen_items end [: label]` → a `GenItem::Block`.
    fn parse_gen_block(&mut self) -> GenItem {
        let start = self.cur_span();
        self.bump(); // `begin`
        let label = self.opt_block_label(); // reuse PR2 helper (`: name` or None)
        let items = self.parse_gen_items_until(&|p| p.at_kw(Kw::End) || p.at_eof());
        self.expect(TokenKind::Word(WordKind::Keyword(Kw::End)), "'end'");
        self.opt_block_label(); // optional `: end_label` (no AST slot → discard)
        GenItem::Block {
            label,
            items,
            span: start.to(self.prev_span()),
        }
    }

    /// Parse a control-structure BRANCH body and HOIST a `begin:label` label out of
    /// it. Returns `(label, items)`:
    /// - `begin [: lbl] … end` → `(lbl, inner_items)` (the begin/end is unwrapped so
    ///   the For/If node carries the label directly — elaborate's `label[idx]`
    ///   prefixing expects the loop/if to OWN the label).
    /// - any other single gen-item → `(None, vec![item])`.
    fn parse_gen_branch(&mut self) -> (Option<Ident>, Vec<GenItem>) {
        if self.at_kw(Kw::Begin) {
            match self.parse_gen_block() {
                GenItem::Block { label, items, .. } => (label, items),
                other => (None, vec![other]), // unreachable; defensive
            }
        } else {
            match self.parse_gen_item() {
                Some(it) => (None, vec![it]),
                None => (None, Vec::new()),
            }
        }
    }
}

// ════════════════════════ PR2: statements + procedural blocks ════════════════════════
impl<'t, 's> Parser<'t, 's> {
    // ─────────────────────── 1. procedural blocks ───────────────────────
    /// `initial S` | `always [@(…)] S` | `always_ff @(…) S` | `always_comb S`
    /// | `always_latch S`. For `always`/`always_ff` a leading `@(…)` folds onto
    /// `ProceduralBlock.sensitivity`.
    fn parse_procedural_block(&mut self) -> ProceduralBlock {
        let start = self.cur_span();
        let kind = match self.peek() {
            Some(TokenKind::Word(WordKind::Keyword(k))) => match k {
                Kw::Initial => ProcKind::Initial,
                Kw::Always => ProcKind::Always,
                Kw::AlwaysFf => ProcKind::AlwaysFf,
                Kw::AlwaysComb => ProcKind::AlwaysComb,
                Kw::AlwaysLatch => ProcKind::AlwaysLatch,
                Kw::Final => ProcKind::Final,
                _ => unreachable!("parse_procedural_block: caller pre-screens proc kw"),
            },
            _ => unreachable!("parse_procedural_block: caller pre-screens proc kw"),
        };
        self.bump(); // initial / always*

        let sensitivity = match kind {
            ProcKind::Always | ProcKind::AlwaysFf if self.peek() == Some(TokenKind::At) => {
                Some(self.parse_sensitivity())
            }
            _ => None,
        };

        let body = Box::new(self.parse_statement());
        ProceduralBlock {
            kind,
            sensitivity,
            body,
            span: start.to(self.prev_span()),
        }
    }

    // ─────────────────────── 1b. function / task definitions ───────────────────────
    /// `function [automatic] [signed] [range] [ret_type] name [(tf_ports)] ;
    ///    {body_decl} body_stmt endfunction`
    /// V2005: return width = `signed` + `range`; `ret_type` is one of
    /// ParamType::{Implicit,Integer,Real,Realtime,Time} (a `reg [N]` return maps to
    /// Implicit + range — ParamType has no Reg/Logic). Ports may be ANSI (in the
    /// paren list) or non-ANSI (input/output decls in the body prefix, hoisted).
    fn parse_function_def(&mut self) -> FunctionDef {
        let start = self.cur_span();
        self.bump(); // 'function'
        let automatic = self.eat_kw(Kw::Automatic);
        // return-type signedness/range/type, in V2005 order: [signed] [range] [type]
        let mut signed = self.opt_signed();
        let range = self.opt_range();
        let ret_type = self.opt_param_type();
        // a second `signed` after an integer-ish return is tolerated.
        signed = signed || self.opt_signed();
        let name = self.ident().unwrap_or_else(|| Ident {
            name: String::new(),
            span: self.cur_span(),
        });
        let mut ports = self.opt_tf_port_paren_list();
        self.expect(TokenKind::Semi, "';' after function header");
        let (body_decls, body) = self.tf_body(BlockEnd2::Endfunction, &mut ports);
        self.expect(
            TokenKind::Word(WordKind::Keyword(Kw::Endfunction)),
            "'endfunction'",
        );
        self.opt_block_label(); // optional `: name` after endfunction → discard
        FunctionDef {
            automatic,
            signed,
            range,
            ret_type,
            name,
            ports,
            body_decls,
            body: Box::new(body),
            span: start.to(self.prev_span()),
        }
    }

    /// `task [automatic] name [(tf_ports)] ; {body_decl} body_stmt endtask`
    fn parse_task_def(&mut self) -> TaskDef {
        let start = self.cur_span();
        self.bump(); // 'task'
        let automatic = self.eat_kw(Kw::Automatic);
        let name = self.ident().unwrap_or_else(|| Ident {
            name: String::new(),
            span: self.cur_span(),
        });
        let mut ports = self.opt_tf_port_paren_list();
        self.expect(TokenKind::Semi, "';' after task header");
        let (body_decls, body) = self.tf_body(BlockEnd2::Endtask, &mut ports);
        self.expect(TokenKind::Word(WordKind::Keyword(Kw::Endtask)), "'endtask'");
        self.opt_block_label();
        TaskDef {
            automatic,
            name,
            ports,
            body_decls,
            body: Box::new(body),
            span: start.to(self.prev_span()),
        }
    }

    /// Map an optional return/var type keyword to ParamType (V2005 set only).
    /// `reg`/`logic`/bit-vector returns are NOT a ParamType — they surface via
    /// signed+range with ret_type = Implicit, so those keywords are NOT consumed.
    fn opt_param_type(&mut self) -> ParamType {
        match self.peek() {
            Some(TokenKind::Word(WordKind::Keyword(Kw::Integer))) => {
                self.bump();
                ParamType::Integer
            }
            Some(TokenKind::Word(WordKind::Keyword(Kw::Real))) => {
                self.bump();
                ParamType::Real
            }
            Some(TokenKind::Word(WordKind::Keyword(Kw::Realtime))) => {
                self.bump();
                ParamType::Realtime
            }
            Some(TokenKind::Word(WordKind::Keyword(Kw::Time))) => {
                self.bump();
                ParamType::Time
            }
            _ => ParamType::Implicit,
        }
    }

    /// Optional ANSI tf-port list `( tf_port {, tf_port} )`. Returns `[]` if there
    /// is no `(` (non-ANSI form — ports come from body input/output decls instead).
    /// Empty `()` ⇒ `[]`. Direction is sticky across comma-grouped names.
    fn opt_tf_port_paren_list(&mut self) -> Vec<TfPort> {
        let mut ports = Vec::new();
        if self.peek() != Some(TokenKind::LParen) {
            return ports;
        }
        self.bump(); // '('
        if self.peek() == Some(TokenKind::RParen) {
            self.bump();
            return ports;
        }
        let mut inherited = PortDir::Input;
        loop {
            let before = self.pos;
            let (port, dir) = self.parse_tf_port(inherited);
            inherited = dir;
            ports.push(port);
            if self.pos == before {
                self.bump(); // forward-progress guard
            }
            if !self.eat(TokenKind::Comma) {
                break;
            }
        }
        self.expect(TokenKind::RParen, "')' closing tf-port list");
        ports
    }

    /// One ANSI tf-port: `[input|output|inout] [net_or_var] [signed] [range] name`.
    /// Returns the port plus the (possibly-inherited) direction so a following
    /// bare `, name` keeps the same dir.
    fn parse_tf_port(&mut self, inherited: PortDir) -> (TfPort, PortDir) {
        let start = self.cur_span();
        let dir = match self.peek() {
            Some(TokenKind::Word(WordKind::Keyword(Kw::Input))) => {
                self.bump();
                PortDir::Input
            }
            Some(TokenKind::Word(WordKind::Keyword(Kw::Output))) => {
                self.bump();
                PortDir::Output
            }
            Some(TokenKind::Word(WordKind::Keyword(Kw::Inout))) => {
                self.bump();
                PortDir::Inout
            }
            _ => inherited, // bare `, b` continues the previous direction
        };
        let net_or_var = self.net_var_kind();
        if net_or_var.is_some() {
            self.bump();
        }
        let signed = self.opt_signed();
        let range = self.opt_range();
        let name = self.ident().unwrap_or_else(|| Ident {
            name: String::new(),
            span: self.cur_span(),
        });
        (
            TfPort {
                dir,
                net_or_var,
                signed,
                range,
                name,
                span: start.to(self.prev_span()),
            },
            dir,
        )
    }

    /// Body of a function/task: a decl prefix (net/var decls AND — for the non-ANSI
    /// form — input/output/inout formal decls, hoisted into `ports`), then exactly
    /// ONE body statement (usually a `begin … end`), up to the endfunction/endtask
    /// closer. `ports` is appended to for non-ANSI formals.
    fn tf_body(&mut self, end: BlockEnd2, ports: &mut Vec<TfPort>) -> (Vec<NetVarDecl>, Stmt) {
        let mut body_decls = Vec::new();
        while !self.at_eof() && !self.at_tf_end(end) {
            if matches!(
                self.peek(),
                Some(TokenKind::Word(WordKind::Keyword(
                    Kw::Input | Kw::Output | Kw::Inout
                )))
            ) {
                // non-ANSI formal: `input [7:0] a, b;` → one TfPort per name.
                let before = self.pos;
                self.parse_tf_port_decl_into(ports);
                if self.pos == before {
                    self.bump();
                }
                continue;
            }
            // B4: a per-decl lifetime override `automatic <kind> <name>;` (only
            // `automatic` — `static` is not a reserved word). The keyword precedes
            // a normal var decl; consume it and stamp the lifetime on the decl.
            if self.at_kw(Kw::Automatic)
                && matches!(
                    self.peek_at(1),
                    Some(TokenKind::Word(WordKind::Keyword(
                        Kw::Reg | Kw::Logic | Kw::Integer | Kw::Real | Kw::Realtime | Kw::Time
                    )))
                )
            {
                self.bump(); // 'automatic'
                let before = self.pos;
                if let Some(mut d) = self.parse_net_var() {
                    d.lifetime = Some(true);
                    body_decls.push(d);
                }
                if self.pos == before {
                    self.bump();
                }
                continue;
            }
            if self.net_var_kind().is_some() {
                let before = self.pos;
                if let Some(d) = self.parse_net_var() {
                    body_decls.push(d);
                }
                if self.pos == before {
                    self.bump();
                }
                continue;
            }
            break; // first non-decl token starts the body statement
        }
        let body = if self.at_tf_end(end) {
            Stmt::Null(self.cur_span()) // empty body: `function f; endfunction`
        } else {
            self.parse_statement()
        };
        (body_decls, body)
    }

    /// True at the `endfunction`/`endtask` closer.
    fn at_tf_end(&self, end: BlockEnd2) -> bool {
        match end {
            BlockEnd2::Endfunction => self.at_kw(Kw::Endfunction),
            BlockEnd2::Endtask => self.at_kw(Kw::Endtask),
        }
    }

    /// Non-ANSI formal decl `input [r] a, b;` → one TfPort per name, appended.
    fn parse_tf_port_decl_into(&mut self, ports: &mut Vec<TfPort>) {
        let dir = match self.peek() {
            Some(TokenKind::Word(WordKind::Keyword(Kw::Output))) => {
                self.bump();
                PortDir::Output
            }
            Some(TokenKind::Word(WordKind::Keyword(Kw::Inout))) => {
                self.bump();
                PortDir::Inout
            }
            _ => {
                self.bump();
                PortDir::Input
            }
        };
        let net_or_var = self.net_var_kind();
        if net_or_var.is_some() {
            self.bump();
        }
        let signed = self.opt_signed();
        let range = self.opt_range();
        loop {
            let n_start = self.cur_span();
            let Some(name) = self.ident() else { break };
            ports.push(TfPort {
                dir,
                net_or_var,
                signed,
                range: range.clone(),
                name,
                span: n_start.to(self.prev_span()),
            });
            if !self.eat(TokenKind::Comma) {
                break;
            }
        }
        self.expect(TokenKind::Semi, "';' after tf-port declaration");
    }

    /// `@*` | `@(*)` → Star ;  `@(ev or ev , …)` → List.  Consumes the leading `@`.
    fn parse_sensitivity(&mut self) -> Sensitivity {
        self.bump(); // '@'
        if self.eat(TokenKind::Star) {
            return Sensitivity::Star; // `@*`
        }
        if !self.expect(TokenKind::LParen, "'(' or '*' after '@'") {
            return Sensitivity::List(Vec::new()); // recover; only `@` consumed
        }
        if self.peek() == Some(TokenKind::Star) {
            self.bump(); // `@(*)`
            self.expect(TokenKind::RParen, "')'");
            return Sensitivity::Star;
        }
        let mut events = Vec::new();
        if self.peek() == Some(TokenKind::RParen) {
            self.error("event expression"); // m2: `@()` is illegal — diagnose
        } else {
            loop {
                let before = self.pos;
                events.push(self.parse_event_expr());
                let sep = self.eat_kw(Kw::Or) || self.eat(TokenKind::Comma);
                // forward-progress guard MUST stay AFTER the separator-eat
                if self.pos == before {
                    self.bump();
                }
                if !sep || self.peek() == Some(TokenKind::RParen) {
                    break;
                }
            }
        }
        self.expect(TokenKind::RParen, "')'");
        Sensitivity::List(events)
    }

    /// `[posedge|negedge] expr` → EventExpr.
    fn parse_event_expr(&mut self) -> EventExpr {
        let start = self.cur_span();
        let edge = if self.eat_kw(Kw::Posedge) {
            Edge::Posedge
        } else if self.eat_kw(Kw::Negedge) {
            Edge::Negedge
        } else {
            Edge::NoEdge
        };
        let expr = self.expr(0);
        let span = start.to(expr.span);
        EventExpr { edge, expr, span }
    }

    // ─────────────────────── 2. statement dispatcher ───────────────────────
    fn parse_statement(&mut self) -> Stmt {
        use TokenKind as T;
        if self.at_lex_error() {
            let s = self.cur_span();
            self.bump(); // skip the lexer-error sentinel without re-reporting
            return Stmt::Error(s);
        }
        match self.peek() {
            Some(T::Semi) => {
                let s = self.cur_span();
                self.bump();
                Stmt::Null(s)
            }
            Some(T::Hash) => self.parse_delay_stmt(),
            Some(T::At) => self.parse_event_stmt(),
            Some(T::Arrow) => self.parse_trigger_stmt(),
            Some(T::LBrace) => self.parse_assign_or_call(), // {a,b} = … concat lvalue
            Some(T::Word(WordKind::Keyword(kw))) => match kw {
                Kw::Begin => self.parse_seq_block(),
                Kw::Fork => self.parse_par_block(),
                Kw::If => self.parse_if(),
                Kw::Case => self.parse_case(CaseKind::Case),
                Kw::Casez => self.parse_case(CaseKind::Casez),
                Kw::Casex => self.parse_case(CaseKind::Casex),
                Kw::For => self.parse_for(),
                Kw::While => self.parse_while(),
                // P2-E: `do body while (cond);` — parse-time desugar (no new
                // AST node): { body; while (cond) body }.
                Kw::Do => self.parse_do_while(),
                // P2-E: unique/priority QUALIFIERS on if/case — the violation
                // check desugars to a synthesized `$warning` arm (IEEE
                // §12.4/12.5: a no-match is a runtime violation warning).
                Kw::Unique | Kw::Priority => self.parse_unique_priority(),
                Kw::Foreach => self.parse_foreach(),
                Kw::Repeat => self.parse_repeat(),
                Kw::Forever => self.parse_forever(),
                Kw::Wait => self.parse_wait(),
                Kw::Disable => self.parse_disable(),
                Kw::Assign => self.parse_proc_assign(),
                Kw::Deassign => self.parse_deassign(),
                Kw::Force => self.parse_force(),
                Kw::Release => self.parse_release(),
                Kw::Assert => self.parse_assert(),
                _ => self.stmt_error(),
            },
            Some(T::SystemTask) => self.parse_systask_call(),
            _ if self.is_ident() => self.parse_assign_or_call(),
            _ => self.stmt_error(),
        }
    }

    /// Unparseable statement: record one error, build Error, sync, GUARANTEE ≥1
    /// token consumed.
    fn stmt_error(&mut self) -> Stmt {
        let s = self.cur_span();
        let before = self.pos;
        self.error("statement");
        self.synchronize();
        if self.pos == before {
            self.bump(); // forced progress when sync stopped immediately
        }
        Stmt::Error(s)
    }

    /// On a recovery path where `synchronize` may stop immediately: sync then
    /// force ≥1 token. Returns an `Error` spanning from `start`.
    fn stmt_error_at(&mut self, start: Span) -> Stmt {
        let before = self.pos;
        self.synchronize();
        if self.pos == before {
            self.bump();
        }
        Stmt::Error(start.to(self.prev_span()))
    }

    // ─────────────────────── 3. assignments / task calls ───────────────────────
    /// Leading ident or `{`: blocking `=`, nonblocking `<=`, or a user-task call.
    fn parse_assign_or_call(&mut self) -> Stmt {
        let start = self.cur_span();
        let lhs = self.parse_lvalue();
        match self.peek() {
            Some(TokenKind::Eq) => {
                self.bump();
                let (delay, event) = self.parse_intra_assign_timing(true);
                let rhs = self.expr(0);
                self.expect(TokenKind::Semi, "';'");
                Stmt::Blocking {
                    lhs,
                    delay,
                    event,
                    rhs,
                    span: start.to(self.prev_span()),
                }
            }
            Some(TokenKind::LtEq) => {
                self.bump();
                let (delay, event) = self.parse_intra_assign_timing(false);
                let rhs = self.expr(0);
                self.expect(TokenKind::Semi, "';'");
                Stmt::NonBlocking {
                    lhs,
                    delay,
                    event,
                    rhs,
                    span: start.to(self.prev_span()),
                }
            }
            // user-task call: bare HierPath followed by `(` or `;`
            Some(TokenKind::LParen) | Some(TokenKind::Semi) => {
                if let Lvalue::Ident(path) = lhs {
                    let args = if self.peek() == Some(TokenKind::LParen) {
                        self.call_args()
                    } else {
                        Vec::new()
                    };
                    self.expect(TokenKind::Semi, "';'");
                    Stmt::UserTaskCall {
                        name: path,
                        args,
                        span: start.to(self.prev_span()),
                    }
                } else {
                    // e.g. `a[i](…)` — an indexed lvalue cannot be a call.
                    self.error("'=' or '<=' after lvalue");
                    self.stmt_error_at(start)
                }
            }
            _ => {
                self.error("'=' or '<=' after lvalue");
                self.stmt_error_at(start)
            }
        }
    }

    /// Intra-assignment timing control after `=`/`<=` (IEEE 1800 §9.4.5): a `#d`
    /// delay (CAPTURED into `delay`), an `@(ev)` event control, or `repeat(n) @(ev)`
    /// (both CAPTURED into `event`). The elaborator lowers the event form as
    /// capture-now/wait/write for a blocking `=` (process blocks), and as a
    /// capture-now/`fork … join_none` desugar for a non-blocking `<=` (slice N1 —
    /// the process does not block). The `blocking` flag is retained for symmetry and
    /// future per-form diagnostics; both forms capture identically here.
    fn parse_intra_assign_timing(
        &mut self,
        _blocking: bool,
    ) -> (Option<Delay>, Option<IntraEvent>) {
        match self.peek() {
            Some(TokenKind::Hash) => (self.parse_delay(), None),
            Some(TokenKind::At) => {
                let ctrl = self.parse_sensitivity(); // consumes `@(…)`
                (None, Some(IntraEvent { repeat: None, ctrl }))
            }
            _ if self.at_kw(Kw::Repeat) => {
                self.bump(); // repeat
                self.expect(TokenKind::LParen, "'(' after 'repeat'");
                let count = self.expr(0);
                self.expect(TokenKind::RParen, "')'");
                if self.peek() == Some(TokenKind::At) {
                    let ctrl = self.parse_sensitivity();
                    (
                        None,
                        Some(IntraEvent {
                            repeat: Some(count),
                            ctrl,
                        }),
                    )
                } else {
                    self.error("`@(event)` after `repeat(n)` in an intra-assignment control");
                    (None, None)
                }
            }
            _ => (None, None),
        }
    }

    fn parse_systask_call(&mut self) -> Stmt {
        let start = self.cur_span();
        let t = self.bump().unwrap(); // SystemTask; lexeme retains `$`
        let name = Ident {
            name: self.src[t.span.clone()].to_string(),
            span: Self::sp(&t.span),
        };
        let args = if self.peek() == Some(TokenKind::LParen) {
            self.call_args()
        } else {
            Vec::new()
        };
        self.expect(TokenKind::Semi, "';'");
        Stmt::SysTaskCall {
            name,
            args,
            span: start.to(self.prev_span()),
        }
    }

    // procedural-continuous family — all reuse parse_lvalue
    fn parse_proc_assign(&mut self) -> Stmt {
        let start = self.cur_span();
        self.bump(); // assign
        let lhs = self.parse_lvalue();
        self.expect(TokenKind::Eq, "'=' in procedural assign");
        let rhs = self.expr(0);
        self.expect(TokenKind::Semi, "';'");
        Stmt::Assign {
            lhs,
            rhs,
            span: start.to(self.prev_span()),
        }
    }
    fn parse_force(&mut self) -> Stmt {
        let start = self.cur_span();
        self.bump(); // force
        let lhs = self.parse_lvalue();
        self.expect(TokenKind::Eq, "'=' in force");
        let rhs = self.expr(0);
        self.expect(TokenKind::Semi, "';'");
        Stmt::Force {
            lhs,
            rhs,
            span: start.to(self.prev_span()),
        }
    }
    fn parse_deassign(&mut self) -> Stmt {
        let start = self.cur_span();
        self.bump(); // deassign
        let lhs = self.parse_lvalue();
        self.expect(TokenKind::Semi, "';'");
        Stmt::Deassign {
            lhs,
            span: start.to(self.prev_span()),
        }
    }
    fn parse_release(&mut self) -> Stmt {
        let start = self.cur_span();
        self.bump(); // release
        let lhs = self.parse_lvalue();
        self.expect(TokenKind::Semi, "';'");
        Stmt::Release {
            lhs,
            span: start.to(self.prev_span()),
        }
    }

    /// SV immediate assertion (IEEE 1800 §16.3):
    ///   `assert [final] (expr) [pass_stmt] [else fail_stmt]`
    /// Desugared AT PARSE TIME to `Stmt::If` — the AST `Stmt` variant set is
    /// frozen (verdict M7), and `if` already has the exact assert condition
    /// semantics (0/X/Z cond → else branch = assertion failure). A missing
    /// else clause synthesizes the IEEE default failure action
    /// `$error("Assertion failed")`, which lowers through the severity table
    /// (stderr diagnostic + nonzero exit; run continues).
    ///
    /// DEFERRED immediate assertions (§16.4): `assert #0 (expr)` (Observed
    /// deferred) and `assert final (expr)` (Reactive deferred) are evaluated WHEN
    /// REACHED but their action MATURES in a later scheduling region with
    /// flush-on-re-reach. These parse to `Stmt::DeferredAssert` (carrying the
    /// region); elaborate emits a per-assertion flush marker + records the action
    /// StmtIds in the deferred sidecars, and the engine adds genuine Observed/
    /// Reactive maturation queues. iverilog rejects deferred assertions, so there
    /// is no oracle (hand-IEEE). A non-zero `#<n>` delay on an assert is NOT a
    /// deferred assertion → loud. Concurrent (`assert property`) is handled
    /// separately. Dangling-else: in `assert (c) if (x) a; else b;` the else binds
    /// to the inner if and the assert gets the synthesized default.
    fn parse_assert(&mut self) -> Stmt {
        let start = self.cur_span();
        self.bump(); // `assert`
                     // v8 SVA subset: `assert property(@(clk) a |-> b);`
        if self.at_kw(Kw::Property) {
            return self.parse_concurrent_assert(start);
        }
        // Deferred immediate assertion (IEEE 1800-2017 §16.4): `assert #0` is the
        // Observed-deferred form, `assert final` the Reactive-deferred form. Both
        // sample the condition WHEN REACHED but MATURE the pass/fail action in a
        // later scheduling region with flush-on-re-reach (see Stmt::DeferredAssert
        // + the engine's Observed/Reactive maturation queues). A plain `assert`
        // (no `#0`/`final`) stays the immediate `Stmt::If` desugar below.
        let defer: Option<AssertDefer> = if self.peek() == Some(TokenKind::Hash) {
            self.bump(); // `#`
                         // Only `#0` is the Observed deferred form (§16.4). A non-zero delay on
                         // an assert is not a deferred assertion → loud.
            if matches!(self.peek(), Some(TokenKind::IntDecimal)) && self.cur_text() == "0" {
                self.bump(); // `0`
                Some(AssertDefer::Observed)
            } else {
                self.error(
                    "a deferred-assertion delay must be `#0` (the Observed deferred form); \
                     a non-zero `#` delay on an assertion is unsupported",
                );
                return self.stmt_error_at(start);
            }
        } else if self.eat_kw(Kw::Final) {
            Some(AssertDefer::Reactive)
        } else {
            None
        };
        if self.peek() != Some(TokenKind::LParen) {
            self.error("'(' after 'assert'");
            return self.stmt_error_at(start);
        }
        self.bump(); // `(`
        let cond = self.expr(0);
        self.expect(TokenKind::RParen, "')'");
        // action_block ::= statement_or_null | [statement] `else` statement
        let then_s = if self.at_kw(Kw::Else) {
            Box::new(Stmt::Null(start)) // else-only form: no pass action
        } else {
            Box::new(self.parse_statement())
        };
        let else_s = if self.eat_kw(Kw::Else) {
            Box::new(self.parse_statement())
        } else {
            let sp = start.to(self.prev_span());
            Box::new(Stmt::SysTaskCall {
                name: Ident {
                    name: "$error".to_string(),
                    span: sp,
                },
                args: vec![Expr {
                    kind: ExprKind::StrLit {
                        raw: "\"Assertion failed\"".to_string(),
                    },
                    span: sp,
                }],
                span: sp,
            })
        };
        let span = start.to(self.prev_span());
        match defer {
            // Deferred (#0 / final): preserve the region so elaborate emits the
            // flush marker + records the action StmtIds in the deferred sidecars.
            Some(region) => Stmt::DeferredAssert {
                region,
                cond,
                then_s,
                else_s,
                span,
            },
            // Plain immediate assert: the byte-identical `Stmt::If` desugar.
            None => Stmt::If {
                cond,
                then_s,
                else_s: Some(else_s),
                span,
            },
        }
    }

    /// SVA subset (Phase-3): `assert property(@(posedge clk) seq |-> consequent);`
    /// (overlapping `|->` / non-overlapping `|=>`). Single clock. The antecedent
    /// is a `Sequence` — slice S4 added bounded `##n` cycle-delay and `[*n]`
    /// consecutive repetition (ranges/unbounded/goto/throughout/within stay a
    /// loud parse error). The consequent stays a flat boolean. The failure
    /// action is the implicit `$error` synthesized at elaborate time.
    fn parse_concurrent_assert(&mut self, start: Span) -> Stmt {
        self.bump(); // `property`
        self.expect(TokenKind::LParen, "'(' after 'property'");
        // Named-property INSTANCE: `assert property(NAME);` — NAME is a property
        // declared elsewhere, resolved + inlined at elaborate. Detect by a single
        // identifier immediately followed by `)`. A `NAME(args)` form is the
        // parameterized instance, reserved + loud in this subset.
        if self.is_ident() && self.peek_at(1) == Some(TokenKind::RParen) {
            let name = self.ident().unwrap();
            self.expect(TokenKind::RParen, "')'");
            let (pass, fail) = self.parse_assert_action_block();
            return Stmt::ConcurrentAssert {
                // empty clock = "named-property reference"; elaborate splices the
                // declared property's real clock/spec in at collect time.
                clock: Sensitivity::List(Vec::new()),
                disable_iff: None,
                antecedent: Sequence::Instance {
                    name,
                    args: Vec::new(),
                    span: start,
                },
                implication_kind: ImplicationKind::Overlap,
                consequent: Sequence::Boolean(Self::sva_true_lit(start)),
                consequent_clock: None,
                pass,
                fail,
                prop_expr: None,
                span: start.to(self.prev_span()),
            };
        }
        if self.is_ident() && self.peek_at(1) == Some(TokenKind::LParen) {
            // `assert property(NAME(args))` — parameterized property instance
            // (slice A1). Parse the positional actual arguments; elaborate binds them
            // to the declared property's formals and substitutes before splicing.
            let name = self.ident().unwrap();
            self.expect(TokenKind::LParen, "'(' before property arguments");
            let mut args = Vec::new();
            if self.peek() != Some(TokenKind::RParen) {
                loop {
                    args.push(self.expr(0));
                    if self.eat(TokenKind::Comma) {
                        continue;
                    }
                    break;
                }
            }
            self.expect(TokenKind::RParen, "')' after property arguments");
            self.expect(TokenKind::RParen, "')'");
            let (pass, fail) = self.parse_assert_action_block();
            return Stmt::ConcurrentAssert {
                clock: Sensitivity::List(Vec::new()),
                disable_iff: None,
                antecedent: Sequence::Instance {
                    name,
                    args,
                    span: start,
                },
                implication_kind: ImplicationKind::Overlap,
                consequent: Sequence::Boolean(Self::sva_true_lit(start)),
                consequent_clock: None,
                pass,
                fail,
                prop_expr: None,
                span: start.to(self.prev_span()),
            };
        }
        let (
            clock,
            disable_iff,
            antecedent,
            implication_kind,
            consequent,
            consequent_clock,
            prop_expr,
        ) = self.parse_property_spec(start);
        self.expect(TokenKind::RParen, "')'");
        // action_block ::= statement_or_null | [statement] `else` statement_or_null
        // (slice S11). A bare `;` leaves both None (default $error, no pass).
        let (pass, fail) = self.parse_assert_action_block();
        Stmt::ConcurrentAssert {
            clock,
            disable_iff,
            antecedent,
            implication_kind,
            consequent,
            consequent_clock,
            pass,
            fail,
            prop_expr,
            span: start.to(self.prev_span()),
        }
    }

    /// A synthetic `1` literal expr (the bare-property `1'b1 |-> e` sentinel and
    /// the named-instance placeholder consequent).
    fn sva_true_lit(span: Span) -> Expr {
        Expr {
            kind: ExprKind::IntLit {
                kind: IntLitKind::Decimal,
                raw: "1".to_string(),
            },
            span,
        }
    }

    /// Parse a property spec `@(clk) [disable iff(e)] seq [ |-> | |=> ] seq` — the
    /// body shared by an inline `assert property( <spec> )` and a named
    /// `property NAME; <spec>; endproperty`. Does NOT consume the surrounding
    /// parens / terminators; the caller does.
    fn parse_property_spec(
        &mut self,
        start: Span,
    ) -> (
        Sensitivity,
        Option<Expr>,
        Sequence,
        ImplicationKind,
        Sequence,
        Option<Sensitivity>,
        Option<PropExpr>,
    ) {
        // Sequence/property LOCAL VARIABLES (slice A2): a typed declaration at the
        // body start (`property p; int x; @(clk) …`) needs per-attempt thread storage
        // that is not synthesizable to a single register — unsupported. Detect it here
        // for a TARGETED diagnostic (instead of the generic "'@(...)'" cascade) and
        // skip the declaration(s) up to the real clocking event so the rest recovers.
        if self.at_sva_local_var_decl() {
            self.error(
                "no sequence/property local variables (e.g. `int x; (a, x=d)`) — \
                 they need per-attempt thread storage, not synthesizable RTL",
            );
            // Skip the declaration(s) — each is `<type> <name> [= e] ;` — landing the
            // cursor on the real `@` clocking event. Each decl ends at its own `;`
            // (which precedes the clock), so we consume THROUGH that `;` and repeat
            // while another decl follows (review 2026-06-16: stopping ON the first
            // `;` left the cursor before `@` and never cleared a second decl).
            while self.at_sva_local_var_decl() {
                while !matches!(
                    self.peek(),
                    Some(TokenKind::Semi) | Some(TokenKind::At) | None
                ) {
                    self.bump();
                }
                if !self.eat(TokenKind::Semi) {
                    break; // hit `@` / EOF before a `;` — stop skipping
                }
            }
        }
        // Clocking event `@(...)`. `parse_sensitivity` consumes the leading `@`.
        let clock = if self.peek() == Some(TokenKind::At) {
            self.parse_sensitivity()
        } else {
            self.error("'@(...)' clocking event in concurrent assertion");
            Sensitivity::List(Vec::new())
        };
        // Optional `disable iff (expr)` reset (slice S12), between the clocking
        // event and the property expression. `disable` is a keyword; `iff` is a
        // contextual keyword (a plain identifier elsewhere).
        let disable_iff = if self.at_kw(Kw::Disable) {
            self.bump(); // `disable`
            if self.at_ident_kw("iff") {
                self.bump(); // `iff`
            } else {
                self.error("`iff` after `disable` in a concurrent assertion");
            }
            self.expect(TokenKind::LParen, "'(' after `disable iff`");
            let e = self.expr(0);
            self.expect(TokenKind::RParen, "')' after `disable iff` condition");
            Some(e)
        } else {
            None
        };
        // Property-level `and`/`or` (slice N2d): when the body uses a top-level
        // (paren-depth-0) `and`/`or` property operator, parse a `PropExpr` TREE
        // instead of the flat `seq impl seq`. The flat fields then hold inert
        // placeholders; elaborate dispatches on `Some(prop_expr)`. This detection
        // keeps every and/or-free property (the whole existing corpus) on the
        // byte-identical flat path below — including slice A3 multi-clock, whose
        // `@(c2)` consequent clock the tree grammar does NOT carry (combining
        // and/or with multi-clock is out of subset → loud at elaborate). `and`/`or`
        // inside the clocking event or a parenthesized sub-expr is at depth > 0 and
        // ignored.
        if self.prop_has_toplevel_andor() {
            let pe = self.parse_prop_expr();
            let true_lit = Self::sva_true_lit(start);
            return (
                clock,
                disable_iff,
                Sequence::Boolean(true_lit.clone()),
                ImplicationKind::Overlap,
                Sequence::Boolean(true_lit),
                None,
                Some(pe),
            );
        }
        // `seq [ |-> | |=> ] expr` — a bare `property(@(clk) expr)` (no
        // implication) desugars to `1'b1 |-> expr`; `seq [ |-> | |=> ] seq` — the
        // consequent is also a Sequence (slice S14). A leading `@(c2)` on the
        // consequent of a `|=>` is a multi-clock property (slice A3).
        let ante_seq = self.parse_sequence();
        if self.eat(TokenKind::PipeArrow) {
            let cons_clock = self.parse_optional_consequent_clock(true);
            (
                clock,
                disable_iff,
                ante_seq,
                ImplicationKind::Overlap,
                self.parse_sequence(),
                cons_clock,
                None,
            )
        } else if self.eat(TokenKind::PipeEqArrow) {
            let cons_clock = self.parse_optional_consequent_clock(false);
            (
                clock,
                disable_iff,
                ante_seq,
                ImplicationKind::NonOverlap,
                self.parse_sequence(),
                cons_clock,
                None,
            )
        } else {
            let true_lit = Self::sva_true_lit(start);
            match ante_seq {
                // bare `property(@(clk) expr)` desugars to `1'b1 |-> expr`.
                Sequence::Boolean(e) => (
                    clock,
                    disable_iff,
                    Sequence::Boolean(true_lit),
                    ImplicationKind::Overlap,
                    Sequence::Boolean(e),
                    None,
                    None,
                ),
                other => {
                    self.error("an implication `|->`/`|=>` (a bare sequence property is unsupported in this subset)");
                    (
                        clock,
                        disable_iff,
                        other,
                        ImplicationKind::Overlap,
                        Sequence::Boolean(true_lit),
                        None,
                        None,
                    )
                }
            }
        }
    }

    /// Bounded paren/bracket-balanced lookahead from the cursor (which sits at the
    /// start of a property expression, after the clock + `disable iff`): true iff a
    /// property-level `and`/`or` keyword appears at depth 0 before the property's
    /// closing `)` (inline `assert property( … )`) or its `;` (a `property NAME; …;
    /// endproperty` declaration). Decisive and cannot be poisoned by a later
    /// construct — it stops at the first depth-underflow `)` / depth-0 `;` /
    /// `endproperty` / module boundary / EOF. `and`/`or` nested in the clocking
    /// event or a parenthesized sub-expression is at depth > 0 and ignored.
    fn prop_has_toplevel_andor(&self) -> bool {
        const BUDGET: usize = 65536;
        let mut i = 0usize;
        let mut depth: i32 = 0;
        loop {
            match self.peek_at(i) {
                None => return false,
                // SVA repeat-open tokens (`[*` / `[->` / `[=`) open a bracket that
                // closes with a plain `]` (RBracket), so they must count for depth
                // or the `]` underflows and a trailing top-level `and`/`or` is missed
                // (review N2d — the same new-token-vs-bracket-scan hazard as N2a-1).
                Some(
                    TokenKind::LParen
                    | TokenKind::LBracket
                    | TokenKind::LBracketStar
                    | TokenKind::LBracketArrow
                    | TokenKind::LBracketEq,
                ) => depth += 1,
                Some(TokenKind::RParen | TokenKind::RBracket) => {
                    if depth == 0 {
                        return false; // the property's closing `)` (inline form)
                    }
                    depth -= 1;
                }
                Some(TokenKind::Semi) if depth == 0 => return false, // decl body terminator
                Some(TokenKind::Word(WordKind::Keyword(Kw::And | Kw::Or))) if depth == 0 => {
                    return true
                }
                Some(TokenKind::Word(WordKind::Keyword(Kw::Module | Kw::Endmodule)))
                    if depth == 0 =>
                {
                    return false
                }
                _ => {}
            }
            if self.peek_at(i).is_some() && self.text_at(i) == "endproperty" {
                return false;
            }
            i += 1;
            if i > BUDGET {
                return false;
            }
        }
    }

    /// Parse a property expression (slice N2d). Precedence loosest→tightest:
    /// `or` < `and` < implication < primary. Reached only when
    /// `prop_has_toplevel_andor` detected a property-level `and`/`or`.
    fn parse_prop_expr(&mut self) -> PropExpr {
        self.parse_prop_or()
    }

    fn parse_prop_or(&mut self) -> PropExpr {
        let mut lhs = self.parse_prop_and();
        while self.at_kw(Kw::Or) {
            self.bump(); // `or`
            let rhs = self.parse_prop_and();
            lhs = PropExpr::Or(Box::new(lhs), Box::new(rhs));
        }
        lhs
    }

    fn parse_prop_and(&mut self) -> PropExpr {
        let mut lhs = self.parse_prop_impl();
        while self.at_kw(Kw::And) {
            self.bump(); // `and`
            let rhs = self.parse_prop_impl();
            lhs = PropExpr::And(Box::new(lhs), Box::new(rhs));
        }
        lhs
    }

    /// A property primary, optionally the antecedent of a single implication. A
    /// parenthesized PROPERTY `( … |-> … )` / `( … and … )` recurses; a
    /// parenthesized boolean expression `(a && b)` is left to `parse_sequence`
    /// (the implication antecedent). The consequent of `|->`/`|=>` is a full
    /// property expression, so `1'b1 |=> p` (the recursion site) parses with `p`
    /// as a bare `Seq(Boolean(Ident))` leaf resolved at elaborate.
    fn parse_prop_impl(&mut self) -> PropExpr {
        if self.peek() == Some(TokenKind::LParen) && self.paren_group_is_property() {
            self.bump(); // `(`
            let inner = self.parse_prop_expr();
            self.expect(TokenKind::RParen, "')' to close a parenthesized property");
            return inner;
        }
        let ante = self.parse_sequence();
        if self.eat(TokenKind::PipeArrow) {
            PropExpr::Impl {
                ante,
                kind: ImplicationKind::Overlap,
                cons: Box::new(self.parse_prop_expr()),
            }
        } else if self.eat(TokenKind::PipeEqArrow) {
            PropExpr::Impl {
                ante,
                kind: ImplicationKind::NonOverlap,
                cons: Box::new(self.parse_prop_expr()),
            }
        } else {
            PropExpr::Seq(ante)
        }
    }

    /// Cursor on `(`: true iff the balanced paren group contains, at the depth just
    /// inside this paren, a property operator (`|->`/`|=>`/`and`/`or`) — i.e. it is
    /// a parenthesized PROPERTY rather than a parenthesized boolean expression
    /// (which `parse_sequence` handles as an implication antecedent / leaf).
    fn paren_group_is_property(&self) -> bool {
        const BUDGET: usize = 65536;
        let mut i = 0usize;
        let mut depth: i32 = 0;
        loop {
            match self.peek_at(i) {
                None => return false,
                // SVA repeat-open tokens count for depth (see `prop_has_toplevel_andor`).
                Some(
                    TokenKind::LParen
                    | TokenKind::LBracket
                    | TokenKind::LBracketStar
                    | TokenKind::LBracketArrow
                    | TokenKind::LBracketEq,
                ) => depth += 1,
                Some(TokenKind::RParen | TokenKind::RBracket) => {
                    depth -= 1;
                    if depth == 0 {
                        return false; // closed without a property operator
                    }
                }
                Some(TokenKind::PipeArrow | TokenKind::PipeEqArrow) if depth == 1 => return true,
                Some(TokenKind::Word(WordKind::Keyword(Kw::And | Kw::Or))) if depth == 1 => {
                    return true
                }
                _ => {}
            }
            i += 1;
            if i > BUDGET {
                return false;
            }
        }
    }

    /// Parse an optional leading `@(c2)` consequent clocking event (slice A3, after
    /// the implication operator). `|=>` accepts it (multi-clock handoff); `|->` does
    /// NOT (no coherent same-tick cross-clock check) → loud, consume for recovery.
    fn parse_optional_consequent_clock(&mut self, is_overlap: bool) -> Option<Sensitivity> {
        if self.peek() != Some(TokenKind::At) {
            return None;
        }
        if is_overlap {
            // `self.error` frames its argument as "expected <X>, found <Y>", so the
            // message must be a noun phrase (review 2026-06-16).
            self.error(
                "a `|=>` for a multi-clock property (an overlapping `|->` cannot take \
                 a consequent clocking event)",
            );
            let _ = self.parse_sensitivity(); // consume `@(c2)` so the rest recovers
            return None;
        }
        Some(self.parse_sensitivity())
    }

    /// Disambiguate `sequence IDENT ( … )` (cursor on `sequence`) between an SVA
    /// sequence DECLARATION and a module instantiation of a V2005 module literally
    /// named `sequence`. The decl shape is exactly `sequence NAME ( formals ) ; BODY
    /// ; endsequence`, so AFTER the formals-terminator `;` the body is a single
    /// sequence expression with NO top-level `;`, and its terminating `;` is
    /// immediately followed by `endsequence`. An instantiation `sequence u(…) ;` has
    /// no such body+`endsequence`. We therefore (1) skip the balanced `( … )`, (2)
    /// require the formals `;`, then (3) scan the body to its next depth-0 `;` and
    /// accept ONLY if `endsequence` follows it. DECISIVE and bounded to the candidate
    /// construct — it cannot be poisoned by an unrelated later `sequence … endsequence`
    /// (review 2026-06-16: a content-independent scan-until-`endsequence` mis-routed a
    /// positional `sequence u(o);` merely followed by a real decl, and a fixed token
    /// budget flipped long decls). Lets `sequence u(.o(o));` stay an instantiation.
    fn is_sequence_decl_ahead(&self) -> bool {
        const BUDGET: usize = 65536;
        // (1) Skip the balanced `( … )` — peek_at(2) is the opening `(`.
        let mut i = 2usize;
        let mut depth = 0usize;
        loop {
            match self.peek_at(i) {
                None => return false,
                Some(TokenKind::LParen) => {
                    depth += 1;
                    i += 1;
                }
                Some(TokenKind::RParen) => {
                    i += 1;
                    depth -= 1;
                    if depth == 0 {
                        break;
                    }
                }
                _ => i += 1,
            }
            if i > BUDGET {
                return false;
            }
        }
        // (2) The formals list must be terminated by `;`.
        if self.peek_at(i) != Some(TokenKind::Semi) {
            return false;
        }
        i += 1;
        // (3) Scan the body to its next depth-0 `;`; a decl has `endsequence` after it.
        let mut bdepth = 0usize;
        loop {
            match self.peek_at(i) {
                None => return false,
                Some(TokenKind::LParen | TokenKind::LBracket) => {
                    bdepth += 1;
                    i += 1;
                }
                Some(TokenKind::RParen | TokenKind::RBracket) => {
                    bdepth = bdepth.saturating_sub(1);
                    i += 1;
                }
                Some(TokenKind::Semi) if bdepth == 0 => {
                    return self.text_at(i + 1) == "endsequence";
                }
                // A hard module boundary before the body terminator ⇒ not a decl.
                Some(TokenKind::Word(WordKind::Keyword(Kw::Module | Kw::Endmodule)))
                    if bdepth == 0 =>
                {
                    return false
                }
                _ => i += 1,
            }
            if i > BUDGET {
                return false;
            }
        }
    }

    /// Named SVA `sequence NAME [(formals)]; <seq>; endsequence` (IEEE §16.8).
    /// Formal arguments (slice A1) bind by position at the use site; the body reuses
    /// the existing `parse_sequence`, so every sequence operator is available by name.
    fn parse_sequence_decl(&mut self) -> Option<ModuleItem> {
        let start = self.cur_span();
        self.bump(); // `sequence` (contextual keyword)
        let name = self.ident()?;
        let formals = self.parse_sva_formals();
        self.expect(TokenKind::Semi, "';' after sequence name");
        let body = self.parse_sequence();
        self.expect(TokenKind::Semi, "';' after sequence body");
        if self.at_ident_kw("endsequence") {
            self.bump();
        } else {
            self.error("`endsequence`");
        }
        self.eat_end_label();
        Some(ModuleItem::SequenceDecl(SeqDecl {
            name,
            formals,
            body,
            span: start.to(self.prev_span()),
        }))
    }

    /// Named SVA `property NAME [(formals)]; <property_spec>; endproperty`
    /// (IEEE §16.12). Reuses `parse_property_spec` for the body; spliced at an
    /// `assert property(NAME)` instance by elaborate.
    fn parse_property_decl(&mut self) -> Option<ModuleItem> {
        let start = self.cur_span();
        self.bump(); // `property` (Kw::Property)
        let name = self.ident()?;
        let formals = self.parse_sva_formals();
        self.expect(TokenKind::Semi, "';' after property name");
        let (
            clock,
            disable_iff,
            antecedent,
            implication_kind,
            consequent,
            consequent_clock,
            prop_expr,
        ) = self.parse_property_spec(start);
        self.expect(TokenKind::Semi, "';' after property body");
        if self.at_ident_kw("endproperty") {
            self.bump();
        } else {
            self.error("`endproperty`");
        }
        self.eat_end_label();
        Some(ModuleItem::PropertyDecl(PropDecl {
            name,
            formals,
            clock,
            disable_iff,
            antecedent,
            implication_kind,
            consequent,
            consequent_clock,
            prop_expr,
            span: start.to(self.prev_span()),
        }))
    }

    /// Parse an SVA formal-argument list `( formal {, formal} )` after a named
    /// sequence/property name (slice A1, IEEE 1800 §16.8/§16.12). A formal is
    /// `[data_type] name [= default]`; the formal NAME is what elaborate substitutes,
    /// so we capture the LAST identifier before a top-level `,` / `)` / `=` and skip
    /// the optional type prefix and any default value (defaults are unsupported — all
    /// actuals must be passed; an arity mismatch is loud at the use site). No `(` →
    /// an empty list (a non-parameterized decl, byte-identical to before this slice).
    fn parse_sva_formals(&mut self) -> Vec<Ident> {
        let mut out = Vec::new();
        if self.peek() != Some(TokenKind::LParen) {
            return out;
        }
        self.bump(); // `(`
        if self.eat(TokenKind::RParen) {
            return out; // empty `()`
        }
        loop {
            match self.parse_one_sva_formal() {
                Some(id) => out.push(id),
                // An empty entry (`(,)`, `(,x)`, `(x,)`) is malformed — loud rather
                // than silently normalized (review 2026-06-16). Arity is still
                // enforced at the use site; this is recovery, not fatal.
                None => self.error("a formal name in the sequence/property formal list"),
            }
            if self.eat(TokenKind::Comma) {
                continue;
            }
            if !self.eat(TokenKind::RParen) {
                self.error("',' or ')' in a sequence/property formal list");
            }
            break;
        }
        out
    }

    /// One SVA formal: scan to the next top-level `,` / `)` / `=`, returning the last
    /// identifier seen (the formal name), regardless of any leading type / range
    /// tokens. A `= default` value is parse-and-dropped (unsupported).
    fn parse_one_sva_formal(&mut self) -> Option<Ident> {
        let mut last: Option<Ident> = None;
        loop {
            match self.peek() {
                Some(TokenKind::Comma) | Some(TokenKind::RParen) | None => break,
                Some(TokenKind::Eq) => {
                    self.bump(); // `=`
                    let _ = self.expr(0); // default value — consumed and ignored
                    break;
                }
                _ if self.is_ident() => {
                    last = self.ident();
                }
                _ => {
                    self.bump(); // a type keyword / `[m:l]` range / etc.
                }
            }
        }
        last
    }

    /// True at a sequence/property body LOCAL-VARIABLE declaration (slice A2): a
    /// data-type keyword (`logic`/`reg`/`integer`/`bit`-via-`logic`/…) or an SV
    /// integral type name lexed as an identifier (`int`/`bit`/`byte`/`shortint`/
    /// `longint`). A property/sequence body must otherwise begin with `@(clk)` (a
    /// property) or a sequence expression, so a type at the body start is a local var.
    fn at_sva_local_var_decl(&self) -> bool {
        if self.net_var_kind().is_some() {
            return true;
        }
        self.is_ident()
            && matches!(
                self.cur_text(),
                "int" | "bit" | "byte" | "shortint" | "longint"
            )
    }

    /// True if the upcoming `( … )` (cursor on `(`) contains a comma at paren-depth
    /// one — a sequence MATCH-ITEM local-variable list `(bool, x = e, …)` (slice A2).
    /// A parenthesized sequence has no top-level comma; concat/select commas nest
    /// deeper (counted via all bracket kinds), so they are not mistaken for one.
    fn at_sva_match_item_paren(&self) -> bool {
        if self.peek() != Some(TokenKind::LParen) {
            return false;
        }
        const BUDGET: usize = 8192;
        let mut depth = 0usize;
        let mut i = 0usize;
        while i < BUDGET {
            match self.peek_at(i) {
                None => return false,
                Some(
                    TokenKind::LParen
                    | TokenKind::LBracket
                    | TokenKind::LBrace
                    | TokenKind::LBracketStar
                    | TokenKind::LBracketArrow
                    | TokenKind::LBracketEq,
                ) => {
                    depth += 1;
                    i += 1;
                }
                Some(TokenKind::RParen | TokenKind::RBracket | TokenKind::RBrace) => {
                    depth = depth.saturating_sub(1);
                    i += 1;
                    if depth == 0 {
                        return false; // outer paren closed with no top-level comma
                    }
                }
                Some(TokenKind::Comma) if depth == 1 => return true,
                _ => i += 1,
            }
        }
        false
    }

    /// Consume a balanced `( … )` group starting at the current `(` (recovery). Tracks
    /// only paren depth (a nested `[ ]`/`{ }` contains no stray `)`). No-op if not at `(`.
    fn skip_balanced_paren_group(&mut self) {
        if self.peek() != Some(TokenKind::LParen) {
            return;
        }
        let mut depth = 0usize;
        while let Some(k) = self.peek() {
            match k {
                TokenKind::LParen => {
                    depth += 1;
                    self.bump();
                }
                TokenKind::RParen => {
                    self.bump();
                    depth -= 1;
                    if depth == 0 {
                        break;
                    }
                }
                _ => {
                    self.bump();
                }
            }
        }
    }

    /// Consume an optional `: label` after `endsequence`/`endproperty`
    /// (accept-and-ignore — the minimal-surface choice).
    fn eat_end_label(&mut self) {
        if self.peek() == Some(TokenKind::Colon) {
            self.bump();
            let _ = self.ident();
        }
    }

    /// Parse an assertion action block after the `property(...)` close paren
    /// (slice S11): `[pass_stmt] [else fail_stmt]`. A bare `;` yields
    /// `(None, None)` — the default $error fail and no pass action, kept distinct
    /// from `(Some(Null), None)` so the no-action checker is byte-identical to
    /// before this slice. Each statement consumes its own terminating `;`.
    fn parse_assert_action_block(&mut self) -> (Option<Box<Stmt>>, Option<Box<Stmt>>) {
        // `eat(Semi)` consumes a bare `;` (empty action block); `at_kw(Else)`
        // (else-only form) leaves the `else` for the `fail` arm below — both yield
        // no pass action. Short-circuit `||` keeps the `;`-consuming side effect.
        let pass = if self.eat(TokenKind::Semi) || self.at_kw(Kw::Else) {
            None
        } else {
            Some(Box::new(self.parse_statement()))
        };
        let fail = if self.eat_kw(Kw::Else) {
            Some(Box::new(self.parse_statement()))
        } else {
            None
        };
        (pass, fail)
    }

    /// Parse an SVA sequence (Phase-3 slices S4/S5): `##n` / bounded-range
    /// `##[m:n]` cycle-delay concatenation (left-associative, looser) over
    /// primaries that may carry a `[*n]` / `[*m:n]` consecutive-repetition
    /// postfix (tighter). Unbounded (`[*m:$]`/`##[m:$]`) / goto / nonconsecutive
    /// / `throughout` / `within` forms are deferred — loud at the enclosing
    /// `expect`. (min,max) carry the bound; max==Some(min) is the single-count
    /// form.
    fn parse_sequence(&mut self) -> Sequence {
        // `##` concatenation (tightest of the binary sequence ops).
        let lhs = self.parse_seq_concat();
        // `seq1 within seq2` (slice S9) — contextual keyword, binary over `##`
        // chains, RHS a full sequence.
        if self.at_ident_kw("within") {
            self.bump(); // `within`
            let rhs = self.parse_sequence();
            return Sequence::Within {
                seq1: Box::new(lhs),
                seq2: Box::new(rhs),
            };
        }
        // `cond throughout seq` (slice S7) — `throughout` is a contextual keyword;
        // its left operand must be a boolean leaf, its right operand a full
        // sequence (looser than `##`, so `g throughout a ##2 c` is
        // `g throughout (a ##2 c)`).
        if self.at_ident_kw("throughout") {
            self.bump(); // `throughout`
            let seq = self.parse_sequence();
            return match lhs {
                Sequence::Boolean(cond) => Sequence::Throughout {
                    cond: Box::new(cond),
                    seq: Box::new(seq),
                },
                _ => {
                    self.error("`throughout` requires a boolean left operand");
                    seq
                }
            };
        }
        lhs
    }

    /// `##`-concatenation chain over sequence primaries (left-associative).
    fn parse_seq_concat(&mut self) -> Sequence {
        let mut lhs = self.parse_seq_primary();
        while self.peek() == Some(TokenKind::HashHash) {
            self.bump(); // `##`
            let (min, max) = self.parse_seq_delay();
            let rhs = self.parse_seq_primary();
            lhs = Sequence::Delay {
                min,
                max,
                lhs: Box::new(lhs),
                rhs: Box::new(rhs),
            };
        }
        lhs
    }

    /// A sequence primary: a boolean leaf expression, optionally followed by one
    /// or more repetition postfixes — `[*n]`/`[*m:n]` consecutive, `[->n]` goto,
    /// or `[=n]` nonconsecutive.
    fn parse_seq_primary(&mut self) -> Sequence {
        // A `@(...)` clocking event at a sequence primary is a multi-clock RE-CLOCKING
        // boundary (slice N2a): `a ##1 @(c2) b`. The leading property clock was already
        // consumed by `parse_concurrent_assert`, so a `@` here re-establishes the
        // sampling clock for the following primary from this `##`-boundary onward
        // (IEEE 1800 §16.13/§16.16 clock flow). Wrap the following primary in
        // `Sequence::Clocked`; elaborate's `synth_crossclock` handles the supported
        // `a ##1 @(c2) b` shape and loud-rejects the rest.
        if self.peek() == Some(TokenKind::At) {
            let clock = self.parse_sensitivity();
            let seq = self.parse_seq_primary();
            return Sequence::Clocked {
                clock,
                seq: Box::new(seq),
            };
        }
        // A `( boolean , local_var = expr {, …} )` match-item paren (slice A2) is a
        // sequence LOCAL-VARIABLE assignment — a top-level comma just inside the paren
        // distinguishes it from a parenthesized sequence (which has none). Per-attempt
        // capture storage is not synthesizable to a single register → loud + skip,
        // instead of the generic `expected ')'` cascade.
        if self.at_sva_match_item_paren() {
            self.error(
                "no sequence/property local variables (e.g. `(a, x=d)` match-item \
                 capture) — they need per-attempt thread storage, not synthesizable RTL",
            );
            self.skip_balanced_paren_group();
            return Sequence::Boolean(Self::sva_true_lit(self.prev_span()));
        }
        let e = self.expr(0);
        let mut seq = Sequence::Boolean(e);
        loop {
            match self.peek() {
                Some(TokenKind::LBracketStar) => {
                    self.bump(); // `[*`
                    let (min, max) = self.parse_seq_repeat_bounds();
                    self.expect(TokenKind::RBracket, "']' to close `[*n]`");
                    seq = Sequence::Repeat {
                        seq: Box::new(seq),
                        min,
                        max,
                        kind: RepeatKind::Consec,
                    };
                }
                Some(tok @ (TokenKind::LBracketArrow | TokenKind::LBracketEq)) => {
                    self.bump(); // `[->` / `[=`
                    let (which, kind) = if tok == TokenKind::LBracketArrow {
                        ("[->n]", RepeatKind::Goto)
                    } else {
                        ("[=n]", RepeatKind::Nonconsec)
                    };
                    let n = self.parse_seq_count_single(which);
                    self.expect(TokenKind::RBracket, "']' to close goto/nonconsec count");
                    seq = Sequence::Repeat {
                        seq: Box::new(seq),
                        min: n,
                        max: Some(n),
                        kind,
                    };
                }
                _ => break,
            }
        }
        seq
    }

    /// Single positive count for `[->n]` / `[=n]`. Ranges (`[->m:n]`) and `0`
    /// are deferred (loud, recovered to 1).
    fn parse_seq_count_single(&mut self, which: &'static str) -> u32 {
        let n = self.parse_small_const(which);
        if self.peek() == Some(TokenKind::Colon) {
            self.error("a single goto/nonconsec count (ranges are unsupported in this subset)");
        }
        if n == 0 {
            self.error("a positive goto/nonconsec count");
            return 1;
        }
        n
    }

    /// Cycle delay after `##`: `##n` → (n, Some(n)), bounded range `##[m:n]`
    /// → (m, Some(n)), or unbounded `##[m:$]` → (m, None) (slice S6).
    fn parse_seq_delay(&mut self) -> (u32, Option<u32>) {
        if self.peek() == Some(TokenKind::LBracket) {
            self.bump(); // `[`
            let lo = self.parse_small_const("a lower bound in `##[m:n]`");
            self.expect(TokenKind::Colon, "':' in `##[m:n]`");
            if self.peek() == Some(TokenKind::Dollar) {
                self.bump(); // `$` — unbounded upper bound
                self.expect(TokenKind::RBracket, "']'");
                return (lo, None);
            }
            let hi = self.parse_small_const("an upper bound in `##[m:n]`");
            self.expect(TokenKind::RBracket, "']'");
            let (lo, hi) = (lo.min(hi), lo.max(hi));
            return (lo, Some(hi));
        }
        let n = self.parse_small_const("a constant cycle delay after `##`");
        (n, Some(n))
    }

    /// `[*n]` repetition bounds: `[*n]` → (n, Some(n)), bounded range `[*m:n]`
    /// → (m, Some(n)), or unbounded `[*m:$]` → (m, None) (slice S13). `[*0]` /
    /// `[*0:n]` (empty) and `[*0:$]` (zero-or-more / empty match) are deferred
    /// (loud, recovered positive). Caller consumed `[*`; this stops before `]`.
    fn parse_seq_repeat_bounds(&mut self) -> (u32, Option<u32>) {
        let lo = self.parse_small_const("a repetition count in `[*n]`");
        if self.peek() == Some(TokenKind::Colon) {
            self.bump(); // ':'
            if self.peek() == Some(TokenKind::Dollar) {
                self.bump(); // `$` — unbounded upper bound: `[*m:$]` (>= m)
                if lo == 0 {
                    self.error("a positive lower bound in `[*m:$]` (`[*0:$]` empty match is unsupported in this subset)");
                    return (1, None);
                }
                return (lo, None);
            }
            let hi = self.parse_small_const("an upper bound in `[*m:n]`");
            let (lo, hi) = (lo.min(hi), lo.max(hi));
            if lo == 0 {
                self.error("a positive repetition lower bound (`[*0:n]` empty match is unsupported in this subset)");
                return (1, Some(hi.max(1)));
            }
            return (lo, Some(hi));
        }
        if lo == 0 {
            self.error(
                "a positive repetition count (`[*0]` empty match is unsupported in this subset)",
            );
            return (1, Some(1));
        }
        (lo, Some(lo))
    }

    /// Read a small unsigned decimal constant from the current `IntDecimal`
    /// token (digit separators stripped). Non-literal / oversized → loud, 1.
    fn parse_small_const(&mut self, what: &'static str) -> u32 {
        if self.peek() == Some(TokenKind::IntDecimal) {
            let v = self.cur_text().replace('_', "").parse::<u32>().ok();
            self.bump();
            if let Some(v) = v {
                return v;
            }
        }
        self.error(what);
        1
    }

    // ─────────────────────── 4. control flow ───────────────────────
    fn parse_if(&mut self) -> Stmt {
        let start = self.cur_span();
        self.bump(); // if
        self.expect(TokenKind::LParen, "'(' after 'if'");
        let cond = self.expr(0);
        self.expect(TokenKind::RParen, "')'");
        let then_s = Box::new(self.parse_statement());
        // dangling-else binds EAGERLY to this (nearest) if
        let else_s = if self.eat_kw(Kw::Else) {
            Some(Box::new(self.parse_statement()))
        } else {
            None
        };
        Stmt::If {
            cond,
            then_s,
            else_s,
            span: start.to(self.prev_span()),
        }
    }

    fn parse_case(&mut self, kind: CaseKind) -> Stmt {
        let start = self.cur_span();
        self.bump(); // case/casez/casex
        self.expect(TokenKind::LParen, "'(' after case");
        let scrutinee = self.expr(0);
        self.expect(TokenKind::RParen, "')'");
        let mut items = Vec::new();
        while !self.at_eof() && !self.at_kw(Kw::Endcase) {
            let before = self.pos;
            items.push(self.parse_case_item());
            if self.pos == before {
                self.bump(); // never spin on a stuck case item
            }
        }
        self.expect(TokenKind::Word(WordKind::Keyword(Kw::Endcase)), "'endcase'");
        Stmt::Case {
            kind,
            scrutinee,
            items,
            span: start.to(self.prev_span()),
        }
    }

    /// `default [:] stmt` | `label {, label} : stmt`.
    fn parse_case_item(&mut self) -> CaseItem {
        let start = self.cur_span();
        if self.eat_kw(Kw::Default) {
            self.eat(TokenKind::Colon); // ':' OPTIONAL after default
            let body = Box::new(self.parse_statement());
            return CaseItem::Default {
                body,
                span: start.to(self.prev_span()),
            };
        }
        let mut labels = vec![self.expr(0)];
        while self.eat(TokenKind::Comma) {
            labels.push(self.expr(0));
        }
        self.expect(TokenKind::Colon, "':' in case item");
        let body = Box::new(self.parse_statement());
        CaseItem::Match {
            labels,
            body,
            span: start.to(self.prev_span()),
        }
    }

    fn parse_for(&mut self) -> Stmt {
        let start = self.cur_span();
        self.bump(); // for
        self.expect(TokenKind::LParen, "'(' after 'for'");
        let init = Box::new(self.parse_for_assign()); // `i = 0`, no trailing ';'
        self.expect(TokenKind::Semi, "';' after for-init");
        let cond = self.expr(0);
        self.expect(TokenKind::Semi, "';' after for-cond");
        let step = Box::new(self.parse_for_assign()); // `i = i+1`, no trailing ';'
        self.expect(TokenKind::RParen, "')'");
        let body = Box::new(self.parse_statement());
        Stmt::For {
            init,
            cond,
            step,
            body,
            span: start.to(self.prev_span()),
        }
    }

    /// A single blocking assignment WITHOUT a trailing `;` (for-init / for-step).
    fn parse_for_assign(&mut self) -> Stmt {
        let start = self.cur_span();
        let lhs = self.parse_lvalue();
        self.expect(TokenKind::Eq, "'=' in for-clause assignment");
        let rhs = self.expr(0);
        Stmt::Blocking {
            lhs,
            delay: None,
            event: None,
            rhs,
            span: start.to(self.prev_span()),
        }
    }

    fn parse_while(&mut self) -> Stmt {
        let start = self.cur_span();
        self.bump(); // while
        self.expect(TokenKind::LParen, "'(' after 'while'");
        let cond = self.expr(0);
        self.expect(TokenKind::RParen, "')'");
        let body = Box::new(self.parse_statement());
        Stmt::While {
            cond,
            body,
            span: start.to(self.prev_span()),
        }
    }

    /// P2-E: `do body while (cond);` desugars at parse to
    /// `begin body; while (cond) body end` — the body runs once before the
    /// first test (body CLONE; loops with side-effecting macro-expanded
    /// bodies are identical either way since both copies are the same AST).
    fn parse_do_while(&mut self) -> Stmt {
        let start = self.cur_span();
        self.bump(); // do
        let body = self.parse_statement();
        if !self.at_kw(Kw::While) {
            self.error("'while' after a do-body");
            return Stmt::Error(start.to(self.prev_span()));
        }
        self.bump(); // while
        self.expect(TokenKind::LParen, "'(' after 'while'");
        let cond = self.expr(0);
        self.expect(TokenKind::RParen, "')'");
        self.expect(TokenKind::Semi, "';' after do-while");
        let span = start.to(self.prev_span());
        let again = Stmt::While {
            cond,
            body: Box::new(body.clone()),
            span,
        };
        Stmt::Block {
            label: None,
            decls: Vec::new(),
            stmts: vec![body, again],
            span,
        }
    }

    /// P2-E: `unique`/`priority` qualified if/case. The qualified statement
    /// parses normally; the VIOLATION surface (IEEE §12.4.2/§12.5.3 — no
    /// branch/arm taken) desugars to a synthesized `$warning` else/default
    /// arm (iverilog-pinned text class: "value is unhandled..."). A statement
    /// that already HAS an else/default cannot miss — left untouched. The
    /// multi-match uniqueness check is a documented cut (the lowered cascade
    /// is first-match-wins, so overlap is unobservable).
    fn parse_unique_priority(&mut self) -> Stmt {
        let qspan = self.cur_span();
        self.bump(); // unique / priority
        let warn_stmt = |span: Span| Stmt::SysTaskCall {
            name: Ident {
                name: "$warning".to_string(),
                span,
            },
            args: vec![Expr {
                kind: ExprKind::StrLit {
                    raw: "\"value is unhandled for priority or unique case statement\"".to_string(),
                },
                span,
            }],
            span,
        };
        match self.peek() {
            Some(TokenKind::Word(WordKind::Keyword(Kw::If))) => {
                let mut s = self.parse_if();
                if let Stmt::If { else_s, span, .. } = &mut s {
                    if else_s.is_none() {
                        *else_s = Some(Box::new(warn_stmt(*span)));
                    }
                }
                s
            }
            Some(TokenKind::Word(WordKind::Keyword(k @ (Kw::Case | Kw::Casez | Kw::Casex)))) => {
                let kind = match k {
                    Kw::Casez => CaseKind::Casez,
                    Kw::Casex => CaseKind::Casex,
                    _ => CaseKind::Case,
                };
                let mut s = self.parse_case(kind);
                if let Stmt::Case { items, span, .. } = &mut s {
                    let has_default = items.iter().any(|i| matches!(i, CaseItem::Default { .. }));
                    if !has_default {
                        items.push(CaseItem::Default {
                            body: Box::new(warn_stmt(*span)),
                            span: *span,
                        });
                    }
                }
                s
            }
            _ => {
                self.error("'if' or 'case' after a unique/priority qualifier");
                Stmt::Error(qspan.to(self.prev_span()))
            }
        }
    }

    /// v5 ⑥ follow-on, reworked at v6: `foreach (arr[i]) stmt` — PARSE-TIME
    /// desugar to the uniform first/next walk (no new AST/IR node):
    ///   begin : (anon)  integer i; integer __st;
    ///     __st = arr.first(i);
    ///     while (__st == 1) begin stmt  __st = arr.next(i); end
    ///   end
    /// ONE shape serves every dyn kind: elaborate lowers first/next on
    /// dyn/queue handles to the DENSE 0..size-1 walk (synthetic-index gated —
    /// the user surface keeps them assoc-only) and on assoc handles to the
    /// key-order walk (§7.9.4). A status of −1 (key wider than the integer
    /// index — possible on i64/string-keyed assoc) stops the loop with the
    /// engine's W4020 truncation warn. Anything that is not a dyn handle gets
    /// the method-call loud error at elaborate.
    /// Multi-index foreach (`a[i,j]`) is outside the MVP — loud at parse.
    fn parse_foreach(&mut self) -> Stmt {
        let start = self.cur_span();
        self.bump(); // foreach
        self.expect(TokenKind::LParen, "'(' after 'foreach'");
        let Some(arr) = self.ident() else {
            self.error("an array name in 'foreach (name[index])'");
            return Stmt::Error(start);
        };
        self.expect(TokenKind::LBracket, "'['");
        let Some(ivar) = self.ident() else {
            self.error("a loop-index name in 'foreach (name[index])'");
            return Stmt::Error(start);
        };
        if self.peek() == Some(TokenKind::Comma) {
            self.error("a single foreach index (multi-dimension foreach is unsupported)");
        }
        self.expect(TokenKind::RBracket, "']'");
        self.expect(TokenKind::RParen, "')'");
        let mut body = self.parse_statement();
        let span = start.to(self.prev_span());
        // v1 elaborate FLATTENS block-locals into the module namespace (no
        // per-block scoping), so a decl named like an outer variable would be
        // skipped and the loop would CLOBBER the outer one (silent-wrong vs
        // IEEE/iverilog, where the foreach index is implicitly local). Make
        // the index a synthetic unique name and rename its references inside
        // the body instead — correct shadowing with zero scoping support.
        // (A nested foreach reusing the same index name renames ITS body
        // first, so the outer pass only sees its own occurrences.)
        let synth = Ident {
            name: format!("__foreach_{}_{}", ivar.name, start.lo),
            span: ivar.span,
        };
        rename_ident_in_stmt(&mut body, &ivar.name, &synth.name);
        let ivar = synth;
        let one_seg = |id: &Ident| HierPath {
            segments: vec![id.clone()],
            span: id.span,
        };
        let ivar_expr = |id: &Ident| Expr {
            kind: ExprKind::Ident(one_seg(id)),
            span: id.span,
        };
        // synthetic status var (unique like the index — same collision rules).
        let stvar = Ident {
            name: format!("__foreach_st_{}", start.lo),
            span: ivar.span,
        };
        // __st = arr.first(i) / arr.next(i)
        let iter_call = |method: &str| Expr {
            kind: ExprKind::Call {
                name: HierPath {
                    segments: vec![
                        arr.clone(),
                        Ident {
                            name: method.to_string(),
                            span: arr.span,
                        },
                    ],
                    span: arr.span,
                },
                args: vec![ivar_expr(&ivar)],
            },
            span: arr.span,
        };
        let st_assign = |method: &str| Stmt::Blocking {
            lhs: Lvalue::Ident(one_seg(&stvar)),
            delay: None,
            event: None,
            rhs: iter_call(method),
            span,
        };
        // while (__st == 1) — a −1 truncation status stops the walk (W4020
        // already warned at the engine seam).
        let cond = Expr {
            kind: ExprKind::Binary {
                op: BinOp::Eq,
                lhs: Box::new(ivar_expr(&stvar)),
                rhs: Box::new(Self::dec_lit(1, span)),
            },
            span,
        };
        let loop_body = Stmt::Block {
            label: None,
            decls: Vec::new(),
            stmts: vec![body, st_assign("next")],
            span,
        };
        // block-local `integer i; integer __st;` so neither leaks/collides.
        let decl_of = |id: &Ident| NetVarDecl {
            kind: NetVarKind::Integer,
            signed: true,
            range: None,
            packed: Vec::new(),
            names: vec![DeclName {
                name: id.clone(),
                unpacked: Vec::new(),
                init: None,
                span: id.span,
            }],
            lifetime: None,
            span: id.span,
        };
        Stmt::Block {
            label: None, // the synthetic names need no block scope
            decls: vec![decl_of(&ivar), decl_of(&stvar)],
            stmts: vec![
                st_assign("first"),
                Stmt::While {
                    cond,
                    body: Box::new(loop_body),
                    span,
                },
            ],
            span,
        }
    }

    fn parse_repeat(&mut self) -> Stmt {
        let start = self.cur_span();
        self.bump(); // repeat
        self.expect(TokenKind::LParen, "'(' after 'repeat'");
        let count = self.expr(0);
        self.expect(TokenKind::RParen, "')'");
        let body = Box::new(self.parse_statement());
        Stmt::Repeat {
            count,
            body,
            span: start.to(self.prev_span()),
        }
    }

    fn parse_forever(&mut self) -> Stmt {
        let start = self.cur_span();
        self.bump(); // forever — NO parens, NO count
        let body = Box::new(self.parse_statement());
        Stmt::Forever {
            body,
            span: start.to(self.prev_span()),
        }
    }

    // ─────────────────────── 5. blocks ───────────────────────
    fn parse_seq_block(&mut self) -> Stmt {
        let start = self.cur_span();
        self.bump(); // begin
        let label = self.opt_block_label();
        let (decls, stmts) = self.block_body(BlockEnd::End);
        self.expect(TokenKind::Word(WordKind::Keyword(Kw::End)), "'end'");
        self.opt_block_label(); // optional `: end_label` (no AST slot → discard)
        Stmt::Block {
            label,
            decls,
            stmts,
            span: start.to(self.prev_span()),
        }
    }

    fn parse_par_block(&mut self) -> Stmt {
        let start = self.cur_span();
        self.bump(); // fork
        let label = self.opt_block_label();
        let (decls, stmts) = self.block_body(BlockEnd::Join);
        let join = self.eat_join(); // Join | JoinAny | JoinNone (latter two are Idents)
        self.opt_block_label(); // optional `: join_label`
        Stmt::Fork {
            label,
            decls,
            stmts,
            join,
            span: start.to(self.prev_span()),
        }
    }

    /// `: name` after begin/fork (or end/join) → Some(ident), else None.
    fn opt_block_label(&mut self) -> Option<Ident> {
        if self.eat(TokenKind::Colon) {
            self.ident()
        } else {
            None
        }
    }

    /// Shared block body: decls-prefix THEN statements, until the closer.
    fn block_body(&mut self, end: BlockEnd) -> (Vec<NetVarDecl>, Vec<Stmt>) {
        let mut decls = Vec::new();
        while !self.at_eof() && !self.at_block_end(end) && self.net_var_kind().is_some() {
            let before = self.pos;
            if let Some(d) = self.parse_net_var() {
                decls.push(d);
            }
            if self.pos == before {
                self.bump(); // guard: malformed decl that consumed nothing
            }
        }
        let mut stmts = Vec::new();
        while !self.at_eof() && !self.at_block_end(end) {
            let before = self.pos;
            stmts.push(self.parse_statement());
            if self.pos == before {
                self.bump(); // guard: never spin on a stuck statement
            }
        }
        (decls, stmts)
    }

    /// True at this block's closer. `End` for begin; any join form for fork.
    fn at_block_end(&self, end: BlockEnd) -> bool {
        match end {
            BlockEnd::End => self.at_kw(Kw::End),
            BlockEnd::Join => {
                self.at_kw(Kw::Join)
                    || (self.is_ident() && matches!(self.cur_text(), "join_any" | "join_none"))
            }
        }
    }

    /// Consume the fork terminator → JoinKind.
    fn eat_join(&mut self) -> JoinKind {
        if self.eat_kw(Kw::Join) {
            JoinKind::Join
        } else if self.is_ident() && self.cur_text() == "join_any" {
            self.bump();
            JoinKind::JoinAny
        } else if self.is_ident() && self.cur_text() == "join_none" {
            self.bump();
            JoinKind::JoinNone
        } else {
            self.error("'join' / 'join_any' / 'join_none'");
            JoinKind::Join
        }
    }

    // ─────────────────────── 6. timing / event / misc ───────────────────────
    fn parse_delay_stmt(&mut self) -> Stmt {
        let start = self.cur_span();
        let delay = self.parse_delay().unwrap_or(Delay {
            values: Vec::new(),
            span: start,
        });
        let body = if self.eat(TokenKind::Semi) {
            None
        } else {
            Some(Box::new(self.parse_statement()))
        };
        Stmt::DelayCtrl {
            delay,
            body,
            span: start.to(self.prev_span()),
        }
    }

    fn parse_event_stmt(&mut self) -> Stmt {
        let start = self.cur_span();
        let ctrl = self.parse_sensitivity(); // consumes the `@`
        let body = if self.eat(TokenKind::Semi) {
            None
        } else {
            Some(Box::new(self.parse_statement()))
        };
        Stmt::EventCtrl {
            ctrl,
            body,
            span: start.to(self.prev_span()),
        }
    }

    fn parse_trigger_stmt(&mut self) -> Stmt {
        let start = self.cur_span();
        self.bump(); // '->'
                     // H1: on a missing name, emit Stmt::Error rather than an empty path.
        let Some(name) = self.hier_path() else {
            return self.stmt_error_at(start);
        };
        self.expect(TokenKind::Semi, "';'");
        Stmt::EventTrigger {
            name,
            span: start.to(self.prev_span()),
        }
    }

    fn parse_wait(&mut self) -> Stmt {
        let start = self.cur_span();
        self.bump(); // wait
                     // `wait fork;` — `fork` is `Kw::Fork`, not an ident, so special-case it
                     // before the `wait(expr)` path (mirrors `parse_disable`).
        if self.at_kw(Kw::Fork) {
            self.bump(); // fork
            self.expect(TokenKind::Semi, "';'");
            return Stmt::WaitFork {
                span: start.to(self.prev_span()),
            };
        }
        self.expect(TokenKind::LParen, "'(' after 'wait'");
        let cond = self.expr(0);
        self.expect(TokenKind::RParen, "')'");
        let body = if self.eat(TokenKind::Semi) {
            None
        } else {
            Some(Box::new(self.parse_statement()))
        };
        Stmt::Wait {
            cond,
            body,
            span: start.to(self.prev_span()),
        }
    }

    fn parse_disable(&mut self) -> Stmt {
        let start = self.cur_span();
        self.bump(); // disable
                     // M3: `disable fork;` — `fork` is `Kw::Fork`, not an ident, so special-case it.
        if self.at_kw(Kw::Fork) {
            let fspan = self.cur_span();
            self.bump(); // fork
            let seg = Ident {
                name: "fork".to_string(),
                span: fspan,
            };
            let target = HierPath {
                segments: vec![seg],
                span: fspan,
            };
            self.expect(TokenKind::Semi, "';'");
            return Stmt::Disable {
                target,
                span: start.to(self.prev_span()),
            };
        }
        // H1: on a missing/illegal name, emit Stmt::Error rather than an empty path.
        let Some(target) = self.hier_path() else {
            return self.stmt_error_at(start);
        };
        self.expect(TokenKind::Semi, "';'");
        Stmt::Disable {
            target,
            span: start.to(self.prev_span()),
        }
    }
}

/// Which keyword terminates a block body (begin→end, fork→join family).
#[derive(Clone, Copy)]
enum BlockEnd {
    End,
    Join,
}

/// Closer selector for function/task bodies (mirrors `BlockEnd` for begin/fork).
#[derive(Clone, Copy)]
enum BlockEnd2 {
    Endfunction,
    Endtask,
}

/// Public API — mirrors `hdl_lexer::lex`'s two-channel shape. Never panics; returns
/// a (partial) AST plus all recovered errors. The driver maps errors → diagnostics
/// (E-PARSE-UNEXPECTED-TOKEN / VITA-E2002) and enforces `--error-limit`.
/// Empty input ⇒ `(None, [])`.
pub fn parse(tokens: &[Spanned], src: &str) -> (Option<SourceUnit>, Vec<ParseError>) {
    let mut p = Parser::new(tokens, src);
    let unit = p.parse_source_unit();
    let su = if unit.items.is_empty() && p.errors.is_empty() {
        None
    } else {
        Some(unit)
    };
    (su, p.errors)
}

/// v5 ⑥ foreach desugar: rename every SINGLE-SEGMENT `Ident` reference to
/// `from` into `to`, across a statement tree — exprs, lvalues, nested stmts,
/// block-local decl initializers/dims AND event-control sensitivity exprs
/// (the last two were review finding 2026-06-11: a missed arm silently binds
/// the reference to the OUTER variable). Multi-segment paths are left alone
/// (`x.y` never names the loop index).
fn rename_ident_in_stmt(s: &mut Stmt, from: &str, to: &str) {
    let fix_path = |p: &mut HierPath| {
        if p.segments.len() == 1 && p.segments[0].name == from {
            p.segments[0].name = to.to_string();
        }
    };
    // SVA sequence antecedent: recurse into every boolean leaf so a loop-index
    // rename reaches sequence terms too (same outer-capture lesson as the
    // EventCtrl/foreach rename arms).
    fn fix_sequence(seq: &mut Sequence, from: &str, to: &str) {
        match seq {
            Sequence::Boolean(e) => fix_expr(e, from, to),
            Sequence::Delay { lhs, rhs, .. } => {
                fix_sequence(lhs, from, to);
                fix_sequence(rhs, from, to);
            }
            Sequence::Repeat { seq, .. } => fix_sequence(seq, from, to),
            Sequence::Throughout { cond, seq } => {
                fix_expr(cond, from, to);
                fix_sequence(seq, from, to);
            }
            Sequence::Within { seq1, seq2 } => {
                fix_sequence(seq1, from, to);
                fix_sequence(seq2, from, to);
            }
            // A re-clocking boundary: recurse into the inner sequence. The clock is a
            // module-level signal (never a loop index — you cannot clock on a genvar),
            // so its sensitivity is not renamed.
            Sequence::Clocked { seq, .. } => fix_sequence(seq, from, to),
            // A named instance: the `name` is a sequence/property identifier (not a
            // loop index), so it is never renamed; only the (reserved) actual-arg
            // expressions are.
            Sequence::Instance { args, .. } => {
                for a in args.iter_mut() {
                    fix_expr(a, from, to);
                }
            }
        }
    }
    /// Rename a loop index inside an N2d property-expression tree (foreach desugar
    /// completeness — the antecedent sequences and nested consequents must all be
    /// renamed, mirroring `fix_sequence`). Property/recursion names are
    /// identifiers, not loop indices, so they are not renamed (they parse as bare
    /// `Seq(Boolean(Ident))` leaves and resolve at elaborate).
    fn fix_prop_expr(pe: &mut PropExpr, from: &str, to: &str) {
        match pe {
            PropExpr::Seq(s) => fix_sequence(s, from, to),
            PropExpr::Impl { ante, cons, .. } => {
                fix_sequence(ante, from, to);
                fix_prop_expr(cons, from, to);
            }
            PropExpr::And(l, r) | PropExpr::Or(l, r) => {
                fix_prop_expr(l, from, to);
                fix_prop_expr(r, from, to);
            }
        }
    }
    fn fix_expr(e: &mut Expr, from: &str, to: &str) {
        match &mut e.kind {
            ExprKind::Ident(p) => {
                if p.segments.len() == 1 && p.segments[0].name == from {
                    p.segments[0].name = to.to_string();
                }
            }
            // v7: a package-scoped name can never be the loop index.
            ExprKind::PkgScoped { .. } => {}
            ExprKind::Unary { operand, .. } => fix_expr(operand, from, to),
            ExprKind::Binary { lhs, rhs, .. } => {
                fix_expr(lhs, from, to);
                fix_expr(rhs, from, to);
            }
            ExprKind::Ternary {
                cond,
                then_e,
                else_e,
            } => {
                fix_expr(cond, from, to);
                fix_expr(then_e, from, to);
                fix_expr(else_e, from, to);
            }
            ExprKind::BitSelect { base, index } => {
                fix_expr(base, from, to);
                fix_expr(index, from, to);
            }
            ExprKind::PartSelect { base, msb, lsb } => {
                fix_expr(base, from, to);
                fix_expr(msb, from, to);
                fix_expr(lsb, from, to);
            }
            ExprKind::IndexedPart {
                base,
                offset,
                width,
                ..
            } => {
                fix_expr(base, from, to);
                fix_expr(offset, from, to);
                fix_expr(width, from, to);
            }
            ExprKind::Concat { parts } | ExprKind::Replicate { value: parts, .. } => {
                for p in parts {
                    fix_expr(p, from, to);
                }
            }
            ExprKind::Call { args, .. } | ExprKind::SysCall { args, .. } => {
                for a in args {
                    fix_expr(a, from, to);
                }
            }
            ExprKind::Paren { inner } => fix_expr(inner, from, to),
            ExprKind::MinTypMax { min, typ, max } => {
                fix_expr(min, from, to);
                fix_expr(typ, from, to);
                fix_expr(max, from, to);
            }
            ExprKind::New { size, src } => {
                fix_expr(size, from, to);
                if let Some(s) = src {
                    fix_expr(s, from, to);
                }
            }
            ExprKind::IntLit { .. }
            | ExprKind::RealLit { .. }
            | ExprKind::StrLit { .. }
            | ExprKind::Dollar
            | ExprKind::Error => {}
        }
        // Replicate.count rides outside the parts vec.
        if let ExprKind::Replicate { count, .. } = &mut e.kind {
            fix_expr(count, from, to);
        }
    }
    fn fix_lv(lv: &mut Lvalue, from: &str, to: &str) {
        match lv {
            Lvalue::Ident(p) => {
                if p.segments.len() == 1 && p.segments[0].name == from {
                    p.segments[0].name = to.to_string();
                }
            }
            Lvalue::BitSelect { base, index, .. } => {
                fix_lv(base, from, to);
                fix_expr(index, from, to);
            }
            Lvalue::PartSelect { base, msb, lsb, .. } => {
                fix_lv(base, from, to);
                fix_expr(msb, from, to);
                fix_expr(lsb, from, to);
            }
            Lvalue::IndexedPart {
                base,
                offset,
                width,
                ..
            } => {
                fix_lv(base, from, to);
                fix_expr(offset, from, to);
                fix_expr(width, from, to);
            }
            Lvalue::Concat { parts, .. } => {
                for p in parts {
                    fix_lv(p, from, to);
                }
            }
            Lvalue::Error(_) => {}
        }
    }
    let fix_delay = |d: &mut Delay, from: &str, to: &str| {
        for e in &mut d.values {
            fix_expr(e, from, to);
        }
    };
    match s {
        Stmt::Blocking {
            lhs, delay, rhs, ..
        }
        | Stmt::NonBlocking {
            lhs, delay, rhs, ..
        } => {
            fix_lv(lhs, from, to);
            if let Some(d) = delay {
                fix_delay(d, from, to);
            }
            fix_expr(rhs, from, to);
        }
        Stmt::If {
            cond,
            then_s,
            else_s,
            ..
        } => {
            fix_expr(cond, from, to);
            rename_ident_in_stmt(then_s, from, to);
            if let Some(e) = else_s {
                rename_ident_in_stmt(e, from, to);
            }
        }
        Stmt::Case {
            scrutinee, items, ..
        } => {
            fix_expr(scrutinee, from, to);
            for it in items {
                match it {
                    CaseItem::Match { labels, body, .. } => {
                        for l in labels {
                            fix_expr(l, from, to);
                        }
                        rename_ident_in_stmt(body, from, to);
                    }
                    CaseItem::Default { body, .. } => rename_ident_in_stmt(body, from, to),
                }
            }
        }
        Stmt::For {
            init,
            cond,
            step,
            body,
            ..
        } => {
            rename_ident_in_stmt(init, from, to);
            fix_expr(cond, from, to);
            rename_ident_in_stmt(step, from, to);
            rename_ident_in_stmt(body, from, to);
        }
        Stmt::While { cond, body, .. } => {
            fix_expr(cond, from, to);
            rename_ident_in_stmt(body, from, to);
        }
        Stmt::Repeat { count, body, .. } => {
            fix_expr(count, from, to);
            rename_ident_in_stmt(body, from, to);
        }
        Stmt::Forever { body, .. } => rename_ident_in_stmt(body, from, to),
        Stmt::Block { decls, stmts, .. } | Stmt::Fork { decls, stmts, .. } => {
            // a nested redeclaration of the SAME name shadows — stop renaming
            // inside (its own occurrences already bind to the inner decl).
            if decls
                .iter()
                .any(|d| d.names.iter().any(|n| n.name.name == from))
            {
                return;
            }
            // decl INITIALIZERS and dimension exprs reference outer names too
            // (review finding 2026-06-11 — they live outside `stmts`).
            for d in decls.iter_mut() {
                if let Some(r) = &mut d.range {
                    fix_expr(&mut r.msb, from, to);
                    fix_expr(&mut r.lsb, from, to);
                }
                for r in &mut d.packed {
                    fix_expr(&mut r.msb, from, to);
                    fix_expr(&mut r.lsb, from, to);
                }
                for n in d.names.iter_mut() {
                    if let Some(e) = &mut n.init {
                        fix_expr(e, from, to);
                    }
                    for dim in &mut n.unpacked {
                        match dim {
                            Dim::Size(e) => fix_expr(e, from, to),
                            Dim::Range(r) => {
                                fix_expr(&mut r.msb, from, to);
                                fix_expr(&mut r.lsb, from, to);
                            }
                            Dim::Queue(Some(b)) => fix_expr(b, from, to),
                            Dim::Queue(None) | Dim::Dyn | Dim::Assoc(_) => {}
                        }
                    }
                }
            }
            for st in stmts {
                rename_ident_in_stmt(st, from, to);
            }
        }
        Stmt::SysTaskCall { args, .. } | Stmt::UserTaskCall { args, .. } => {
            for a in args {
                fix_expr(a, from, to);
            }
        }
        Stmt::DelayCtrl { delay, body, .. } => {
            fix_delay(delay, from, to);
            if let Some(b) = body {
                rename_ident_in_stmt(b, from, to);
            }
        }
        Stmt::EventCtrl { ctrl, body, .. } => {
            // the sensitivity exprs reference names too (review finding
            // 2026-06-11 — `@(arr[i])` inside a foreach body).
            if let Sensitivity::List(evs) = ctrl {
                for ev in evs {
                    fix_expr(&mut ev.expr, from, to);
                }
            }
            if let Some(b) = body {
                rename_ident_in_stmt(b, from, to);
            }
        }
        Stmt::Wait { cond, body, .. } => {
            fix_expr(cond, from, to);
            if let Some(b) = body {
                rename_ident_in_stmt(b, from, to);
            }
        }
        Stmt::Assign { lhs, rhs, .. } | Stmt::Force { lhs, rhs, .. } => {
            fix_lv(lhs, from, to);
            fix_expr(rhs, from, to);
        }
        Stmt::Deassign { lhs, .. } | Stmt::Release { lhs, .. } => fix_lv(lhs, from, to),
        Stmt::EventTrigger { name, .. } => fix_path(name),
        Stmt::ConcurrentAssert {
            clock,
            disable_iff,
            antecedent,
            consequent,
            pass,
            fail,
            prop_expr,
            ..
        } => {
            // Rename every operand (clock sensitivity exprs + disable iff +
            // antecedent + consequent + action-block statements + the N2d
            // property-expression tree) — same completeness lesson as EventCtrl
            // above (an unrenamed operand would silently capture the outer signal).
            if let Sensitivity::List(evs) = clock {
                for ev in evs {
                    fix_expr(&mut ev.expr, from, to);
                }
            }
            if let Some(e) = disable_iff {
                fix_expr(e, from, to);
            }
            fix_sequence(antecedent, from, to);
            fix_sequence(consequent, from, to);
            if let Some(pe) = prop_expr {
                fix_prop_expr(pe, from, to);
            }
            if let Some(s) = pass {
                rename_ident_in_stmt(s, from, to);
            }
            if let Some(s) = fail {
                rename_ident_in_stmt(s, from, to);
            }
        }
        Stmt::DeferredAssert {
            cond,
            then_s,
            else_s,
            ..
        } => {
            fix_expr(cond, from, to);
            rename_ident_in_stmt(then_s, from, to);
            rename_ident_in_stmt(else_s, from, to);
        }
        Stmt::WaitFork { .. } | Stmt::Disable { .. } | Stmt::Null(_) | Stmt::Error(_) => {}
    }
}

#[cfg(test)]
mod tests {
    /// v7 AST flip: package/import/string/pkg:: parse to their dedicated
    /// shapes (semantics land in the follow-on slices — parse-only here).
    #[test]
    fn v7_package_import_string_pkgscoped_parse() {
        let src = r#"
package p;
  parameter W = 8;
endpackage
import p::*;
module t;
  import p::W;
  string s;
  integer x;
  initial x = p::W;
endmodule
"#;
        let (toks, lex_errs) = hdl_lexer::lex(src);
        assert!(lex_errs.is_empty());
        let (unit, errs) = parse(&toks, src);
        assert!(errs.is_empty(), "parse errors: {errs:?}");
        let unit = unit.unwrap();
        assert!(matches!(unit.items[0], TopItem::Package(ref m) if m.name.name == "p"));
        assert!(
            matches!(unit.items[1], TopItem::Import(ref i) if i.pkg.name == "p" && i.item.is_none())
        );
        let TopItem::Module(ref m) = unit.items[2] else {
            panic!("expected module, got {:?}", unit.items[2]);
        };
        assert!(matches!(
            m.body[0],
            ModuleItem::Import(ref i) if i.pkg.name == "p"
                && i.item.as_ref().map(|x| x.name.as_str()) == Some("W")
        ));
        assert!(matches!(
            m.body[1],
            ModuleItem::NetVar(ref d) if matches!(d.kind, NetVarKind::String)
        ));
        // the initial body holds `x = p::W` — walk to the PkgScoped expr.
        let ModuleItem::Proc(ref pb) = m.body[3] else {
            panic!("expected proc, got {:?}", m.body[3]);
        };
        let mut found = false;
        fn walk(s: &Stmt, found: &mut bool) {
            if let Stmt::Blocking { rhs, .. } = s {
                if matches!(
                    rhs.kind,
                    ExprKind::PkgScoped { ref pkg, ref name }
                        if pkg.name == "p" && name.name == "W"
                ) {
                    *found = true;
                }
            }
            if let Stmt::Block { stmts, .. } = s {
                for st in stmts {
                    walk(st, found);
                }
            }
        }
        walk(&pb.body, &mut found);
        assert!(found, "p::W must parse as PkgScoped");
    }

    /// Review-finding regressions (2026-06-11): the foreach rename walker
    /// must leave NO single-segment reference to the source-level index name
    /// anywhere in the desugared tree — including block-local decl
    /// initializers/dims and event-control sensitivity exprs (the two arms a
    /// review caught as missed → silent outer-variable capture).
    #[test]
    fn foreach_rename_covers_decl_inits_and_event_ctrl() {
        let src = r#"
module t;
  integer q [$];
  integer r;
  initial begin
    foreach (q[i]) begin
      integer k = q[i];
      @(q[i]) r = q[i];
    end
  end
endmodule
"#;
        let (toks, lex_errs) = hdl_lexer::lex(src);
        assert!(lex_errs.is_empty());
        let (unit, errs) = parse(&toks, src);
        assert!(errs.is_empty(), "parse errors: {errs:?}");
        let unit = unit.unwrap();
        // walk the whole AST; collect every single-segment ident name.
        fn idents_in_expr(e: &Expr, out: &mut Vec<String>) {
            match &e.kind {
                ExprKind::Ident(p) => {
                    if p.segments.len() == 1 {
                        out.push(p.segments[0].name.clone());
                    }
                }
                ExprKind::Unary { operand, .. } => idents_in_expr(operand, out),
                ExprKind::Binary { lhs, rhs, .. } => {
                    idents_in_expr(lhs, out);
                    idents_in_expr(rhs, out);
                }
                ExprKind::Ternary {
                    cond,
                    then_e,
                    else_e,
                } => {
                    idents_in_expr(cond, out);
                    idents_in_expr(then_e, out);
                    idents_in_expr(else_e, out);
                }
                ExprKind::BitSelect { base, index } => {
                    idents_in_expr(base, out);
                    idents_in_expr(index, out);
                }
                ExprKind::PartSelect { base, msb, lsb } => {
                    idents_in_expr(base, out);
                    idents_in_expr(msb, out);
                    idents_in_expr(lsb, out);
                }
                ExprKind::Call { args, .. } | ExprKind::SysCall { args, .. } => {
                    for a in args {
                        idents_in_expr(a, out);
                    }
                }
                ExprKind::Paren { inner } => idents_in_expr(inner, out),
                _ => {}
            }
        }
        fn idents_in_stmt(s: &Stmt, out: &mut Vec<String>) {
            match s {
                Stmt::Blocking { lhs, rhs, .. } | Stmt::NonBlocking { lhs, rhs, .. } => {
                    if let Lvalue::Ident(p) = lhs {
                        if p.segments.len() == 1 {
                            out.push(p.segments[0].name.clone());
                        }
                    }
                    if let Lvalue::BitSelect { index, .. } = lhs {
                        idents_in_expr(index, out);
                    }
                    idents_in_expr(rhs, out);
                }
                Stmt::For {
                    init,
                    cond,
                    step,
                    body,
                    ..
                } => {
                    idents_in_stmt(init, out);
                    idents_in_expr(cond, out);
                    idents_in_stmt(step, out);
                    idents_in_stmt(body, out);
                }
                Stmt::Block { decls, stmts, .. } => {
                    for d in decls {
                        for n in &d.names {
                            if let Some(e) = &n.init {
                                idents_in_expr(e, out);
                            }
                        }
                    }
                    for st in stmts {
                        idents_in_stmt(st, out);
                    }
                }
                Stmt::EventCtrl { ctrl, body, .. } => {
                    if let Sensitivity::List(evs) = ctrl {
                        for ev in evs {
                            idents_in_expr(&ev.expr, out);
                        }
                    }
                    if let Some(b) = body {
                        idents_in_stmt(b, out);
                    }
                }
                _ => {}
            }
        }
        let mut names = Vec::new();
        for it in &unit.items {
            if let TopItem::Module(m) = it {
                for item in &m.body {
                    if let ModuleItem::Proc(pb) = item {
                        idents_in_stmt(&pb.body, &mut names);
                    }
                }
            }
        }
        assert!(
            !names.iter().any(|n| n == "i"),
            "the source index name must be fully renamed; leftover refs: {names:?}"
        );
        assert!(
            names.iter().any(|n| n.starts_with("__foreach_i_")),
            "the synthetic index must appear: {names:?}"
        );
    }

    use super::*;

    fn p(src: &str) -> (Option<SourceUnit>, Vec<ParseError>) {
        let (toks, lex_errs) = hdl_lexer::lex(src);
        assert!(lex_errs.is_empty(), "lex errors: {lex_errs:?}");
        parse(&toks, src)
    }
    fn first_module(su: &SourceUnit) -> &ModuleDecl {
        match &su.items[0] {
            TopItem::Module(m) => m,
            _ => panic!("not a module"),
        }
    }
    /// Parse a bare expression via `assign x = <expr>;` and return the RHS.
    fn expr_of(src: &str) -> Expr {
        let wrapped = format!("module m; assign x = {src};\nendmodule");
        let (su, errs) = p(&wrapped);
        assert!(errs.is_empty(), "parse errors for `{src}`: {errs:?}");
        let su = su.unwrap();
        let m = first_module(&su);
        match &m.body[0] {
            ModuleItem::ContAssign(ca) => ca.assigns[0].1.clone(),
            _ => panic!(),
        }
    }
    fn bin(e: &Expr) -> (BinOp, &Expr, &Expr) {
        match &e.kind {
            ExprKind::Binary { op, lhs, rhs } => (*op, lhs, rhs),
            other => panic!("not binary: {other:?}"),
        }
    }
    /// Parse a module body; return the first ProceduralBlock.
    fn proc_of(body: &str) -> ProceduralBlock {
        let src = format!("module m;\n{body}\nendmodule");
        let (su, errs) = p(&src);
        assert!(errs.is_empty(), "parse errors: {errs:?}");
        let su = su.unwrap();
        let m = first_module(&su);
        match m.body.iter().find(|i| matches!(i, ModuleItem::Proc(_))) {
            Some(ModuleItem::Proc(pb)) => pb.clone(),
            _ => panic!("no procedural block in body"),
        }
    }
    fn as_block(s: &Stmt) -> (&Option<Ident>, &Vec<NetVarDecl>, &Vec<Stmt>) {
        match s {
            Stmt::Block {
                label,
                decls,
                stmts,
                ..
            } => (label, decls, stmts),
            other => panic!("not a Block: {other:?}"),
        }
    }

    // 1. mul binds tighter than add:  a + b * c  =>  +(a, *(b,c))
    #[test]
    fn t1_mul_tighter_than_add() {
        let (op, _l, r) = {
            let e = expr_of("a + b * c");
            let (o, l, r) = bin(&e);
            (o, l.clone(), r.clone())
        };
        assert_eq!(op, BinOp::Add);
        assert_eq!(bin(&r).0, BinOp::Mul);
    }

    // 2. ternary right-assoc:  a ? b : c ? d : e  =>  a ? b : (c ? d : e)
    #[test]
    fn t2_ternary_right_assoc() {
        let e = expr_of("a ? b : c ? d : e");
        let ExprKind::Ternary { else_e, .. } = &e.kind else {
            panic!()
        };
        assert!(matches!(else_e.kind, ExprKind::Ternary { .. }));
    }

    // 3. concat LHS + left-assoc add:  assign {cout,sum} = a + b + cin;
    #[test]
    fn t3_concat_lhs_left_assoc() {
        let (su, errs) = p("module m; assign {cout, sum} = a + b + cin;\nendmodule");
        assert!(errs.is_empty(), "{errs:?}");
        let su = su.unwrap();
        let m = first_module(&su);
        let ModuleItem::ContAssign(ca) = &m.body[0] else {
            panic!()
        };
        let Lvalue::Concat { parts, .. } = &ca.assigns[0].0 else {
            panic!("LHS not concat")
        };
        assert_eq!(parts.len(), 2);
        let (op, l, _r) = bin(&ca.assigns[0].1);
        assert_eq!(op, BinOp::Add);
        assert_eq!(bin(l).0, BinOp::Add); // left child is (a+b)  → left-assoc
    }

    // 4. ANSI #(param)(ports) + direction inheritance
    #[test]
    fn t4_ansi_header() {
        let (su, errs) = p("module adder #(parameter WIDTH = 8)\
            (input [WIDTH-1:0] a, b, output [WIDTH-1:0] sum);\nendmodule");
        assert!(errs.is_empty(), "{errs:?}");
        let su = su.unwrap();
        let m = first_module(&su);
        assert_eq!(m.name.name, "adder");
        assert_eq!(m.params.len(), 1);
        assert_eq!(m.params[0].kind, ParamKind::Parameter);
        let PortList::Ansi(ports) = &m.ports else {
            panic!("not ANSI")
        };
        assert_eq!(ports.len(), 3);
        assert_eq!(ports[0].dir, PortDir::Input);
        assert_eq!(ports[1].dir, PortDir::Input); // `b` inherits
        assert_eq!(ports[2].dir, PortDir::Output);
    }

    // 5. non-ANSI module: header names + body dir/type
    #[test]
    fn t5_non_ansi() {
        let (su, errs) = p(
            "module m(a, b, y);\n  input a, b;\n  output y;\n  wire [3:0] tmp;\n\
            assign y = a & b;\nendmodule",
        );
        assert!(errs.is_empty(), "{errs:?}");
        let su = su.unwrap();
        let m = first_module(&su);
        let PortList::NonAnsi(names) = &m.ports else {
            panic!("not non-ANSI")
        };
        assert_eq!(
            names.iter().map(|i| i.name.as_str()).collect::<Vec<_>>(),
            ["a", "b", "y"]
        );
        assert!(matches!(m.body[0], ModuleItem::PortDecl(_)));
        assert!(m.body.iter().any(|i| matches!(i, ModuleItem::NetVar(_))));
        assert!(m
            .body
            .iter()
            .any(|i| matches!(i, ModuleItem::ContAssign(_))));
    }

    // 6. vector range is an expr, not pre-evaluated:  wire [WIDTH-1:0] bus;
    #[test]
    fn t6_range_is_expr() {
        let (su, _e) = p("module m; wire [WIDTH-1:0] bus;\nendmodule");
        let su = su.unwrap();
        let m = first_module(&su);
        let ModuleItem::NetVar(nv) = &m.body[0] else {
            panic!()
        };
        let r = nv.range.as_ref().unwrap();
        assert_eq!(bin(&r.msb).0, BinOp::Sub);
        assert!(matches!(r.lsb.kind, ExprKind::IntLit { .. }));
    }

    // 7. indexed part-select [b+:w]
    #[test]
    fn t7_indexed_part_select() {
        let e = expr_of("data[base +: 8]");
        let ExprKind::IndexedPart { dir, .. } = &e.kind else {
            panic!("{:?}", e.kind)
        };
        assert_eq!(*dir, PartDir::PlusColon);
    }

    // 8. & tighter than | :  a & b | c  =>  |(&(a,b), c)
    #[test]
    fn t8_and_tighter_than_or() {
        let e = expr_of("a & b | c");
        let (op, l, _r) = bin(&e);
        assert_eq!(op, BinOp::BitOr);
        assert_eq!(bin(l).0, BinOp::BitAnd);
    }

    // 9. unary tighter than equality:  !a == b  =>  ==(!a, b)
    #[test]
    fn t9_unary_tighter_than_eq() {
        let e = expr_of("!a == b");
        let (op, l, _r) = bin(&e);
        assert_eq!(op, BinOp::Eq);
        assert!(matches!(
            l.kind,
            ExprKind::Unary {
                op: UnOp::LogNot,
                ..
            }
        ));
    }

    // 10. add tighter than shift (the doc's #1 gotcha):  a + b << 2  =>  (a+b) << 2
    #[test]
    fn t10_add_tighter_than_shift() {
        let e = expr_of("a + b << 2");
        let (op, l, _r) = bin(&e);
        assert_eq!(op, BinOp::Shl);
        assert_eq!(bin(l).0, BinOp::Add);
    }

    // 11. replication value is a Vec, NOT a Concat wrapper (verdict M5):  {3{a}}
    #[test]
    fn t11_replication_value_is_vec() {
        let e = expr_of("{3{a}}");
        let ExprKind::Replicate { count, value } = &e.kind else {
            panic!("{:?}", e.kind)
        };
        assert!(matches!(count.kind, ExprKind::IntLit { .. }));
        assert_eq!(value.len(), 1);
        assert!(matches!(value[0].kind, ExprKind::Ident(_))); // bare `a`, not Concat{[a]}
    }

    // 12. mintypmax delay (verdict M2):  assign #(1:2:3) y = a;
    #[test]
    fn t12_mintypmax_delay() {
        let (su, errs) = p("module m; assign #(1:2:3) y = a;\nendmodule");
        assert!(errs.is_empty(), "{errs:?}");
        let su = su.unwrap();
        let m = first_module(&su);
        let ModuleItem::ContAssign(ca) = &m.body[0] else {
            panic!()
        };
        let d = ca.delay.as_ref().unwrap();
        assert_eq!(d.values.len(), 1);
        assert!(matches!(d.values[0].kind, ExprKind::MinTypMax { .. }));
    }

    // 13. recovery continues after a bad item (uses a lexer-error token `@`-stray
    //     plus garbage); the trailing valid assign still parses (verdict B3).
    #[test]
    fn t13_recovery_continues() {
        let (su, errs) = p("module m; wire @ ; assign y = a;\nendmodule");
        assert!(!errs.is_empty(), "expected a recovered error");
        let su = su.unwrap();
        let m = first_module(&su);
        assert!(
            m.body
                .iter()
                .any(|i| matches!(i, ModuleItem::ContAssign(_))),
            "parser must recover and parse the trailing assign"
        );
    }

    // 14. termination edges (verdict H3-soundness): must not hang / must terminate.
    #[test]
    fn t14_termination_edges() {
        assert_eq!(p("").0, None); // empty input ⇒ (None, [])
        let _ = p("module"); // truncated header
        let _ = p("module module;"); // sync-anchor == entry-token trap
        let _ = p("module m; endmodule extra ;"); // trailing junk
                                                  // reaching here without hang is the assertion
    }

    // 15. ** right-assoc and unary precedence:  -a ** b  =>  (-a) ** b ; 2**3**4 right
    #[test]
    fn t15_pow_assoc_and_unary() {
        let e = expr_of("2 ** 3 ** 4");
        let (op, _l, r) = bin(&e);
        assert_eq!(op, BinOp::Pow);
        assert_eq!(bin(&r.clone()).0, BinOp::Pow); // right child is 3**4 (right-assoc)
        let e2 = expr_of("- a ** b");
        let (op2, l2, _r2) = bin(&e2);
        assert_eq!(op2, BinOp::Pow); // top is **
        assert!(matches!(
            l2.kind,
            ExprKind::Unary {
                op: UnOp::Minus,
                ..
            }
        )); // left is (-a)
    }

    // S1. initial begin: blocking + nonblocking mix
    #[test]
    fn s1_initial_blocking_nonblocking() {
        let pb = proc_of("initial begin a = 1; q <= d; end");
        assert_eq!(pb.kind, ProcKind::Initial);
        assert!(pb.sensitivity.is_none());
        let (_l, _d, stmts) = as_block(&pb.body);
        assert!(matches!(stmts[0], Stmt::Blocking { .. }));
        assert!(matches!(stmts[1], Stmt::NonBlocking { .. }));
    }

    // S2. always @(posedge clk) if/else (no begin) — sensitivity on the BLOCK
    #[test]
    fn s2_always_posedge_if_else() {
        let pb = proc_of("always @(posedge clk) if (rst) q <= 0; else q <= d;");
        assert_eq!(pb.kind, ProcKind::Always);
        let Some(Sensitivity::List(evs)) = &pb.sensitivity else {
            panic!()
        };
        assert_eq!(evs.len(), 1);
        assert_eq!(evs[0].edge, Edge::Posedge);
        let Stmt::If { else_s, .. } = &*pb.body else {
            panic!("body not If")
        };
        assert!(else_s.is_some());
    }

    // S3. posedge/negedge `or`-separated sensitivity list
    #[test]
    fn s3_sensitivity_or_list() {
        let pb = proc_of("always @(posedge clk or negedge rst_n) q <= d;");
        let Some(Sensitivity::List(evs)) = &pb.sensitivity else {
            panic!()
        };
        assert_eq!(evs.len(), 2);
        assert_eq!(evs[0].edge, Edge::Posedge);
        assert_eq!(evs[1].edge, Edge::Negedge);
    }

    // S4. always_comb + case: sensitivity MUST be None (@ never consumed); multi-label
    #[test]
    fn s4_always_comb_case() {
        let pb = proc_of("always_comb case (sel) 2'b00, 2'b01: y = a; default: y = b; endcase");
        assert_eq!(pb.kind, ProcKind::AlwaysComb);
        assert!(pb.sensitivity.is_none());
        let Stmt::Case { kind, items, .. } = &*pb.body else {
            panic!()
        };
        assert_eq!(*kind, CaseKind::Case);
        let CaseItem::Match { labels, .. } = &items[0] else {
            panic!()
        };
        assert_eq!(labels.len(), 2); // two labels share one body
        assert!(matches!(items[1], CaseItem::Default { .. }));
    }

    // S5. casez kind + `default` WITHOUT a colon
    #[test]
    fn s5_casez_default_no_colon() {
        let pb = proc_of("always_comb casez (req) 4'b1???: g = 1; default g = 0; endcase");
        let Stmt::Case { kind, items, .. } = &*pb.body else {
            panic!()
        };
        assert_eq!(*kind, CaseKind::Casez);
        assert!(matches!(items[1], CaseItem::Default { .. }));
    }

    // S6. for-loop — init/step are Blocking built WITHOUT consuming the ';'
    #[test]
    fn s6_for_loop() {
        let pb = proc_of("initial for (i = 0; i < 8; i = i + 1) sum = sum + i;");
        let Stmt::For {
            init, step, body, ..
        } = &*pb.body
        else {
            panic!()
        };
        assert!(matches!(**init, Stmt::Blocking { .. }));
        assert!(matches!(**step, Stmt::Blocking { .. }));
        assert!(matches!(**body, Stmt::Blocking { .. }));
    }

    // S7. while + $display systask call (name retains `$`, 2 args)
    #[test]
    fn s7_while_and_display() {
        let pb =
            proc_of("initial while (cnt < 8) begin $display(\"c=%d\", cnt); cnt = cnt + 1; end");
        let Stmt::While { body, .. } = &*pb.body else {
            panic!()
        };
        let (_l, _d, stmts) = as_block(body);
        let Stmt::SysTaskCall { name, args, .. } = &stmts[0] else {
            panic!()
        };
        assert_eq!(name.name, "$display");
        assert_eq!(args.len(), 2);
    }

    // S8. #delay statement with body, then $finish with NO parens (empty args)
    #[test]
    fn s8_delay_and_finish() {
        let pb = proc_of("initial begin #20 rst = 0; #200 $finish; end");
        let (_l, _d, stmts) = as_block(&pb.body);
        let Stmt::DelayCtrl { body: b0, .. } = &stmts[0] else {
            panic!()
        };
        assert!(matches!(b0.as_deref(), Some(Stmt::Blocking { .. })));
        let Stmt::DelayCtrl { body: b1, .. } = &stmts[1] else {
            panic!()
        };
        let Some(Stmt::SysTaskCall { name, args, .. }) = b1.as_deref() else {
            panic!()
        };
        assert_eq!(name.name, "$finish");
        assert!(args.is_empty());
    }

    // S9. dangling-else binds to the INNER if
    #[test]
    fn s9_dangling_else_inner() {
        let pb = proc_of("initial if (a) if (b) x = 1; else x = 2;");
        let Stmt::If { then_s, else_s, .. } = &*pb.body else {
            panic!()
        };
        assert!(else_s.is_none(), "outer if must NOT own the else");
        let Stmt::If {
            else_s: inner_else, ..
        } = &**then_s
        else {
            panic!("then not If")
        };
        assert!(inner_else.is_some(), "inner if owns the else");
    }

    // S10. named begin-end with a local decl + end-label (label consumed, no hang)
    #[test]
    fn s10_named_block_local_decl() {
        let pb = proc_of("initial begin : blk reg [7:0] tmp; tmp = a; end");
        let (label, decls, stmts) = as_block(&pb.body);
        assert_eq!(label.as_ref().unwrap().name, "blk");
        assert_eq!(decls.len(), 1);
        assert_eq!(stmts.len(), 1);
        assert!(matches!(stmts[0], Stmt::Blocking { .. }));
    }

    // S11. always @(*) Star + nested begin
    #[test]
    fn s11_nested_block_and_star() {
        let pb = proc_of("always @(*) begin a = b; begin c = d; end end");
        assert!(matches!(pb.sensitivity, Some(Sensitivity::Star)));
        let (_l, _d, stmts) = as_block(&pb.body);
        assert!(matches!(stmts[0], Stmt::Blocking { .. }));
        assert!(matches!(stmts[1], Stmt::Block { .. }));
    }

    // S12. recovery: garbage statement → Error, no infinite loop, following stmt parses
    #[test]
    fn s12_recovery_garbage_stmt() {
        let (su, errs) = p("module m;\ninitial begin & ; x = 1; end\nendmodule");
        assert!(!errs.is_empty(), "expected a recovered error");
        let su = su.unwrap();
        let m = first_module(&su);
        let Some(ModuleItem::Proc(pb)) = m.body.iter().find(|i| matches!(i, ModuleItem::Proc(_)))
        else {
            panic!("no proc block")
        };
        let (_l, _d, stmts) = as_block(&pb.body);
        assert!(
            stmts.iter().any(|s| matches!(s, Stmt::Error(_))),
            "garbage → Error"
        );
        assert!(
            stmts.iter().any(|s| matches!(s, Stmt::Blocking { .. })),
            "must recover and parse `x = 1;`"
        );
    }

    // S13. fork / join_none — JoinKind from an Ident token (not a keyword)
    #[test]
    fn s13_fork_join_none() {
        let pb = proc_of("initial fork #10 a = 1; #20 b = 1; join_none");
        let Stmt::Fork { stmts, join, .. } = &*pb.body else {
            panic!()
        };
        assert_eq!(*join, JoinKind::JoinNone);
        assert_eq!(stmts.len(), 2);
    }

    // S14. repeat body is a bare EventCtrl (body None); wait body None;
    //      and intra-assign delay `q <= #1 d;` parses CLEAN into the delay field.
    #[test]
    fn s14_event_body_none_and_intra_delay() {
        let src = "module m;\ninitial begin repeat (8) @(posedge clk); wait (ready); q <= #1 d; end\nendmodule";
        let (su, errs) = p(src);
        assert!(errs.is_empty(), "intra-assign delay parses clean: {errs:?}");
        let su = su.unwrap();
        let m = first_module(&su);
        let Some(ModuleItem::Proc(pb)) = m.body.iter().find(|i| matches!(i, ModuleItem::Proc(_)))
        else {
            panic!("no proc block")
        };
        let (_l, _d, stmts) = as_block(&pb.body);
        let Stmt::Repeat { body, .. } = &stmts[0] else {
            panic!()
        };
        let Stmt::EventCtrl { body: eb, .. } = &**body else {
            panic!("repeat body not EventCtrl")
        };
        assert!(eb.is_none()); // `@(posedge clk);` → body None
        let Stmt::Wait { body: wb, .. } = &stmts[1] else {
            panic!()
        };
        assert!(wb.is_none());
        // intra-assign delay is CAPTURED into the AST delay field (the
        // elaborator decides semantics: blocking = real, NBA = loud defer).
        let Stmt::NonBlocking { delay, .. } = &stmts[2] else {
            panic!("not NonBlocking")
        };
        assert!(delay.is_some(), "intra-assign delay must be captured");
    }

    // S14b. blocking intra-assign delay `a = #3 b;` captures into `delay`; blocking
    //       intra-assign EVENT control `a = @(ev) b` / `a = repeat(n) @(ev) b`
    //       captures into `event` (slice: repeat-event intra-assignment).
    #[test]
    fn s14b_blocking_intra_delay_and_event_control_captured() {
        let (su, errs) = p("module m;\ninitial a = #3 b;\nendmodule");
        assert!(
            errs.is_empty(),
            "blocking intra-delay parses clean: {errs:?}"
        );
        let su = su.unwrap();
        let m = first_module(&su);
        let Some(ModuleItem::Proc(pb)) = m.body.iter().find(|i| matches!(i, ModuleItem::Proc(_)))
        else {
            panic!("no proc block")
        };
        let Stmt::Blocking { delay, event, .. } = &*pb.body else {
            panic!("not Blocking: {:?}", pb.body)
        };
        assert!(
            delay.is_some() && event.is_none(),
            "blocking intra-assign delay must be captured (no event)"
        );

        // Plain `@(ev)` intra-assign now parses clean and captures `event` (repeat=None).
        let (su, errs) = p("module m;\ninitial a = @(posedge clk) b;\nendmodule");
        assert!(
            errs.is_empty(),
            "intra-assign event control parses clean: {errs:?}"
        );
        let su = su.unwrap();
        let m = first_module(&su);
        let ModuleItem::Proc(pb) = m
            .body
            .iter()
            .find(|i| matches!(i, ModuleItem::Proc(_)))
            .unwrap()
        else {
            unreachable!()
        };
        let Stmt::Blocking { event, delay, .. } = &*pb.body else {
            panic!("not Blocking")
        };
        let ev = event.as_ref().expect("event control must be captured");
        assert!(
            delay.is_none() && ev.repeat.is_none(),
            "plain @(ev): repeat None"
        );

        // `repeat(n) @(ev)` captures the count.
        let (su, errs) = p("module m;\ninitial a = repeat(3) @(posedge clk) b;\nendmodule");
        assert!(
            errs.is_empty(),
            "repeat-event intra-assign parses clean: {errs:?}"
        );
        let su = su.unwrap();
        let m = first_module(&su);
        let ModuleItem::Proc(pb) = m
            .body
            .iter()
            .find(|i| matches!(i, ModuleItem::Proc(_)))
            .unwrap()
        else {
            unreachable!()
        };
        let Stmt::Blocking { event, .. } = &*pb.body else {
            panic!("not Blocking")
        };
        assert!(
            event.as_ref().and_then(|e| e.repeat.as_ref()).is_some(),
            "repeat(n) @(ev): repeat count must be captured"
        );
    }

    // S15. SV immediate assert (IEEE 1800 §16.3) desugars AT PARSE TIME to
    //      `Stmt::If` — the frozen AST Stmt set (M7) gains no variant, and `if`
    //      already has the exact assert condition semantics (X/Z → else). No
    //      else clause ⇒ the IEEE default failure action is synthesized as
    //      `$error("Assertion failed")`.
    #[test]
    fn s15_assert_desugars_to_if_with_default_error() {
        let (su, errs) = p("module m;\ninitial assert (a == 1);\nendmodule");
        assert!(errs.is_empty(), "immediate assert parses clean: {errs:?}");
        let su = su.unwrap();
        let m = first_module(&su);
        let Some(ModuleItem::Proc(pb)) = m.body.iter().find(|i| matches!(i, ModuleItem::Proc(_)))
        else {
            panic!("no proc block")
        };
        let Stmt::If { then_s, else_s, .. } = &*pb.body else {
            panic!("assert must desugar to If: {:?}", pb.body)
        };
        assert!(
            matches!(**then_s, Stmt::Null(_)),
            "no pass action → Null then-branch"
        );
        let Some(e) = else_s else {
            panic!("missing else clause must synthesize the default action")
        };
        let Stmt::SysTaskCall { name, args, .. } = &**e else {
            panic!("default else must be a $error call: {e:?}")
        };
        assert_eq!(name.name, "$error");
        assert_eq!(args.len(), 1);
        assert!(
            matches!(&args[0].kind, ExprKind::StrLit { raw } if raw.contains("Assertion failed"))
        );
    }

    // S15b. explicit pass/else actions map onto the If branches verbatim; the
    //       else-only form gets a Null then-branch.
    #[test]
    fn s15b_assert_actions_map_to_if_branches() {
        let (su, errs) =
            p("module m;\ninitial assert (a) $display(\"ok\"); else $display(\"no\");\nendmodule");
        assert!(errs.is_empty(), "{errs:?}");
        let su = su.unwrap();
        let m = first_module(&su);
        let Some(ModuleItem::Proc(pb)) = m.body.iter().find(|i| matches!(i, ModuleItem::Proc(_)))
        else {
            panic!("no proc block")
        };
        let Stmt::If { then_s, else_s, .. } = &*pb.body else {
            panic!("not If: {:?}", pb.body)
        };
        let Stmt::SysTaskCall { name, .. } = &**then_s else {
            panic!("pass action must be the then-branch")
        };
        assert_eq!(name.name, "$display");
        let Some(e) = else_s else { panic!("no else") };
        let Stmt::SysTaskCall { name, .. } = &**e else {
            panic!("user else action must be kept verbatim")
        };
        assert_eq!(name.name, "$display");

        // else-only: `assert (a) else x = 1;`
        let (su2, errs2) = p("module m;\ninitial assert (a) else x = 1;\nendmodule");
        assert!(errs2.is_empty(), "{errs2:?}");
        let su2 = su2.unwrap();
        let m2 = first_module(&su2);
        let Some(ModuleItem::Proc(pb2)) = m2.body.iter().find(|i| matches!(i, ModuleItem::Proc(_)))
        else {
            panic!("no proc block")
        };
        let Stmt::If { then_s, else_s, .. } = &*pb2.body else {
            panic!("not If")
        };
        assert!(matches!(**then_s, Stmt::Null(_)));
        assert!(matches!(else_s.as_deref(), Some(Stmt::Blocking { .. })));
    }

    // S15c. the DEFERRED forms now PARSE to `Stmt::DeferredAssert` (faithful
    //       deferred-assert slice): `#0` = Observed, `final` = Reactive. A
    //       non-zero `#<n>` delay on an assert stays a LOUD parse error.
    #[test]
    fn s15c_deferred_assert_parses_observed_and_reactive() {
        for (src, want) in [
            (
                "module m;\ninitial assert #0 (a);\nendmodule",
                AssertDefer::Observed,
            ),
            (
                "module m;\ninitial assert final (a);\nendmodule",
                AssertDefer::Reactive,
            ),
        ] {
            let (su, errs) = p(src);
            assert!(errs.is_empty(), "{src}: {errs:?}");
            let su = su.unwrap();
            let m = first_module(&su);
            let Some(ModuleItem::Proc(pb)) =
                m.body.iter().find(|i| matches!(i, ModuleItem::Proc(_)))
            else {
                panic!("no proc block")
            };
            let Stmt::DeferredAssert { region, .. } = &*pb.body else {
                panic!("not DeferredAssert: {:?}", pb.body)
            };
            assert_eq!(*region, want, "{src}");
        }
        // a non-zero `#` delay on an assert is NOT a deferred assert → loud.
        let (_, errs) = p("module m;\ninitial assert #1 (a);\nendmodule");
        assert!(!errs.is_empty(), "`assert #1` must be a loud parse error");
    }

    // S15d (v8 SVA subset). `assert property(@(clk) a |-> b)` parses to a
    // `Stmt::ConcurrentAssert`; `|->` is Overlap, `|=>` is NonOverlap.
    #[test]
    fn concurrent_assert_property_parses_overlap_and_nonoverlap() {
        let (su, errs) =
            p("module m;\ninitial assert property (@(posedge clk) a |-> b);\nendmodule");
        assert!(errs.is_empty(), "concurrent assertion must parse: {errs:?}");
        let su = su.unwrap();
        let m = first_module(&su);
        let ModuleItem::Proc(pb) = m
            .body
            .iter()
            .find(|i| matches!(i, ModuleItem::Proc(_)))
            .unwrap()
        else {
            unreachable!()
        };
        assert!(
            matches!(
                &*pb.body,
                Stmt::ConcurrentAssert {
                    implication_kind: ImplicationKind::Overlap,
                    ..
                }
            ),
            "expected ConcurrentAssert{{Overlap}}, got {:?}",
            pb.body
        );

        let (su2, errs2) =
            p("module m;\ninitial assert property (@(posedge clk) a |=> b);\nendmodule");
        assert!(errs2.is_empty(), "non-overlap must parse: {errs2:?}");
        let su2 = su2.unwrap();
        let m2 = first_module(&su2);
        let ModuleItem::Proc(pb2) = m2
            .body
            .iter()
            .find(|i| matches!(i, ModuleItem::Proc(_)))
            .unwrap()
        else {
            unreachable!()
        };
        assert!(
            matches!(
                &*pb2.body,
                Stmt::ConcurrentAssert {
                    implication_kind: ImplicationKind::NonOverlap,
                    ..
                }
            ),
            "expected ConcurrentAssert{{NonOverlap}}, got {:?}",
            pb2.body
        );
    }

    // S15e (SVA slice S4). Sequence antecedents: `##n` cycle-delay parses to
    // `Sequence::Delay`, `[*n]` consecutive repetition to `Sequence::Repeat`.
    #[test]
    fn concurrent_assert_seq_delay_parses() {
        let (su, errs) =
            p("module m;\ninitial assert property (@(posedge clk) a ##1 b |-> c);\nendmodule");
        assert!(
            errs.is_empty(),
            "sequence-delay antecedent must parse: {errs:?}"
        );
        let su = su.unwrap();
        let m = first_module(&su);
        let ModuleItem::Proc(pb) = m
            .body
            .iter()
            .find(|i| matches!(i, ModuleItem::Proc(_)))
            .unwrap()
        else {
            unreachable!()
        };
        let Stmt::ConcurrentAssert {
            antecedent,
            implication_kind: ImplicationKind::Overlap,
            ..
        } = &*pb.body
        else {
            panic!("expected ConcurrentAssert(Overlap), got {:?}", pb.body)
        };
        assert!(
            matches!(
                antecedent,
                Sequence::Delay {
                    min: 1,
                    max: Some(1),
                    ..
                }
            ),
            "expected Sequence::Delay{{1}}, got {antecedent:?}"
        );
    }

    #[test]
    fn concurrent_assert_seq_repeat_parses() {
        let (su, errs) =
            p("module m;\ninitial assert property (@(posedge clk) a[*3] |-> b);\nendmodule");
        assert!(
            errs.is_empty(),
            "repetition antecedent must parse: {errs:?}"
        );
        let su = su.unwrap();
        let m = first_module(&su);
        let ModuleItem::Proc(pb) = m
            .body
            .iter()
            .find(|i| matches!(i, ModuleItem::Proc(_)))
            .unwrap()
        else {
            unreachable!()
        };
        let Stmt::ConcurrentAssert { antecedent, .. } = &*pb.body else {
            panic!("expected ConcurrentAssert, got {:?}", pb.body)
        };
        assert!(
            matches!(
                antecedent,
                Sequence::Repeat {
                    min: 3,
                    max: Some(3),
                    ..
                }
            ),
            "expected Sequence::Repeat{{3}}, got {antecedent:?}"
        );
    }

    // S15f (S5). Bounded ranges `##[m:n]` / `[*m:n]` now PARSE to Delay/Repeat
    // with min != max; unbounded (`$`), `throughout`, `within` stay LOUD.
    #[test]
    fn concurrent_assert_seq_ranges_parse() {
        let (su, errs) =
            p("module m;\ninitial assert property (@(posedge clk) a ##[1:2] b |-> c);\nendmodule");
        assert!(errs.is_empty(), "bounded delay range must parse: {errs:?}");
        let su = su.unwrap();
        let m = first_module(&su);
        let ModuleItem::Proc(pb) = m
            .body
            .iter()
            .find(|i| matches!(i, ModuleItem::Proc(_)))
            .unwrap()
        else {
            unreachable!()
        };
        let Stmt::ConcurrentAssert { antecedent, .. } = &*pb.body else {
            panic!("expected ConcurrentAssert, got {:?}", pb.body)
        };
        assert!(
            matches!(
                antecedent,
                Sequence::Delay {
                    min: 1,
                    max: Some(2),
                    ..
                }
            ),
            "expected Sequence::Delay{{1,2}}, got {antecedent:?}"
        );

        let (su2, errs2) =
            p("module m;\ninitial assert property (@(posedge clk) a[*2:3] |-> b);\nendmodule");
        assert!(
            errs2.is_empty(),
            "bounded repeat range must parse: {errs2:?}"
        );
        let m2 = first_module(su2.as_ref().unwrap());
        let ModuleItem::Proc(pb2) = m2
            .body
            .iter()
            .find(|i| matches!(i, ModuleItem::Proc(_)))
            .unwrap()
        else {
            unreachable!()
        };
        let Stmt::ConcurrentAssert { antecedent, .. } = &*pb2.body else {
            panic!("expected ConcurrentAssert, got {:?}", pb2.body)
        };
        assert!(
            matches!(
                antecedent,
                Sequence::Repeat {
                    min: 2,
                    max: Some(3),
                    ..
                }
            ),
            "expected Sequence::Repeat{{2,3}}, got {antecedent:?}"
        );
    }

    // S15g (S6). Unbounded cycle delay `##[m:$]` parses to Delay{min, max:None}.
    #[test]
    fn concurrent_assert_seq_unbounded_delay_parses() {
        let (su, errs) =
            p("module m;\ninitial assert property (@(posedge clk) a ##[1:$] b |-> c);\nendmodule");
        assert!(errs.is_empty(), "unbounded delay must parse: {errs:?}");
        let m = first_module(su.as_ref().unwrap());
        let ModuleItem::Proc(pb) = m
            .body
            .iter()
            .find(|i| matches!(i, ModuleItem::Proc(_)))
            .unwrap()
        else {
            unreachable!()
        };
        let Stmt::ConcurrentAssert { antecedent, .. } = &*pb.body else {
            panic!("expected ConcurrentAssert, got {:?}", pb.body)
        };
        assert!(
            matches!(
                antecedent,
                Sequence::Delay {
                    min: 1,
                    max: None,
                    ..
                }
            ),
            "expected Sequence::Delay{{1, $}}, got {antecedent:?}"
        );
    }

    // S15h (S7). `cond throughout seq` parses to Sequence::Throughout.
    #[test]
    fn concurrent_assert_throughout_parses() {
        let (su, errs) = p(
            "module m;\ninitial assert property (@(posedge clk) g throughout a ##2 c |-> d);\nendmodule",
        );
        assert!(errs.is_empty(), "throughout must parse: {errs:?}");
        let m = first_module(su.as_ref().unwrap());
        let ModuleItem::Proc(pb) = m
            .body
            .iter()
            .find(|i| matches!(i, ModuleItem::Proc(_)))
            .unwrap()
        else {
            unreachable!()
        };
        let Stmt::ConcurrentAssert { antecedent, .. } = &*pb.body else {
            panic!("expected ConcurrentAssert, got {:?}", pb.body)
        };
        // `g throughout (a ##2 c)` — throughout is looser than `##`.
        let Sequence::Throughout { seq, .. } = antecedent else {
            panic!("expected Sequence::Throughout, got {antecedent:?}")
        };
        assert!(
            matches!(&**seq, Sequence::Delay { min: 2, .. }),
            "throughout RHS must be the `a ##2 c` sequence, got {seq:?}"
        );
    }

    // S15i (S8). `b[->n]` goto / `b[=n]` nonconsec parse to Repeat with the right
    // RepeatKind.
    #[test]
    fn concurrent_assert_goto_nonconsec_parse() {
        for (src, want_goto) in [
            (
                "module m;\ninitial assert property (@(posedge clk) a ##1 b[->2] |-> c);\nendmodule",
                true,
            ),
            (
                "module m;\ninitial assert property (@(posedge clk) a ##1 b[=2] |-> c);\nendmodule",
                false,
            ),
        ] {
            let (su, errs) = p(src);
            assert!(errs.is_empty(), "goto/nonconsec must parse: {errs:?} ({src})");
            let m = first_module(su.as_ref().unwrap());
            let ModuleItem::Proc(pb) = m
                .body
                .iter()
                .find(|i| matches!(i, ModuleItem::Proc(_)))
                .unwrap()
            else {
                unreachable!()
            };
            let Stmt::ConcurrentAssert { antecedent, .. } = &*pb.body else {
                panic!("expected ConcurrentAssert")
            };
            // antecedent is `a ##1 b[->2]` = Delay{.., rhs: Repeat{kind}}.
            let Sequence::Delay { rhs, .. } = antecedent else {
                panic!("expected Delay, got {antecedent:?}")
            };
            let Sequence::Repeat { kind, min: 2, .. } = &**rhs else {
                panic!("expected Repeat with count 2, got {rhs:?}")
            };
            let is_goto = matches!(kind, RepeatKind::Goto);
            assert_eq!(is_goto, want_goto, "wrong repeat kind for {src}");
        }
    }

    // S15j (S9). `seq1 within seq2` parses to Sequence::Within (binary over `##`
    // chains: `a within b ##2 c` = `a within (b ##2 c)`).
    #[test]
    fn concurrent_assert_within_parses() {
        let (su, errs) = p(
            "module m;\ninitial assert property (@(posedge clk) a within b ##2 c |-> d);\nendmodule",
        );
        assert!(errs.is_empty(), "within must parse: {errs:?}");
        let m = first_module(su.as_ref().unwrap());
        let ModuleItem::Proc(pb) = m
            .body
            .iter()
            .find(|i| matches!(i, ModuleItem::Proc(_)))
            .unwrap()
        else {
            unreachable!()
        };
        let Stmt::ConcurrentAssert { antecedent, .. } = &*pb.body else {
            panic!("expected ConcurrentAssert")
        };
        let Sequence::Within { seq2, .. } = antecedent else {
            panic!("expected Sequence::Within, got {antecedent:?}")
        };
        assert!(
            matches!(&**seq2, Sequence::Delay { min: 2, .. }),
            "within RHS must be `b ##2 c`, got {seq2:?}"
        );
    }

    // S13. Unbounded consecutive repeat `a[*m:$]` (m>=1) parses to
    // `Sequence::Repeat { min: m, max: None, kind: Consec }`.
    #[test]
    fn concurrent_assert_consec_unbounded_parses() {
        let (su, errs) =
            p("module m;\ninitial assert property (@(posedge clk) a[*2:$] |-> b);\nendmodule");
        assert!(errs.is_empty(), "`a[*2:$]` must parse: {errs:?}");
        let m = first_module(su.as_ref().unwrap());
        let ModuleItem::Proc(pb) = m
            .body
            .iter()
            .find(|i| matches!(i, ModuleItem::Proc(_)))
            .unwrap()
        else {
            unreachable!()
        };
        let Stmt::ConcurrentAssert { antecedent, .. } = &*pb.body else {
            panic!("expected ConcurrentAssert")
        };
        assert!(
            matches!(
                antecedent,
                Sequence::Repeat {
                    min: 2,
                    max: None,
                    kind: RepeatKind::Consec,
                    ..
                }
            ),
            "expected Repeat{{2, None, Consec}}, got {antecedent:?}"
        );
    }

    // Still-deferred sequence forms (empty unbounded `[*0:$]`, empty `[*0]`,
    // goto/nonconsec RANGES) stay LOUD — they pin the slice boundary (bounded
    // `[*m:n]` / unbounded `[*m:$]` with m>=1 are now supported, above).
    #[test]
    fn concurrent_assert_deferred_seq_forms_are_loud() {
        for src in [
            "module m;\ninitial assert property (@(posedge clk) a[*0:$] |-> b);\nendmodule",
            "module m;\ninitial assert property (@(posedge clk) a[*0] |-> b);\nendmodule",
            "module m;\ninitial assert property (@(posedge clk) a ##1 b[->1:2] |-> c);\nendmodule",
        ] {
            let (_, errs) = p(src);
            assert!(
                !errs.is_empty(),
                "deferred sequence form must be loud: {src}"
            );
        }
    }

    // ════════════════════ module instantiation (PR3) ════════════════════
    /// Return the first ModuleInstance in a module body.
    fn inst_of(body: &str) -> ModuleInstance {
        let src = format!("module m;\n{body}\nendmodule");
        let (su, errs) = p(&src);
        assert!(errs.is_empty(), "parse errors: {errs:?}");
        let su = su.unwrap();
        let m = first_module(&su);
        match m.body.iter().find(|i| matches!(i, ModuleItem::Instance(_))) {
            Some(ModuleItem::Instance(mi)) => mi.clone(),
            _ => panic!("no module instance in body"),
        }
    }
    fn id_name(e: &Expr) -> &str {
        match &e.kind {
            ExprKind::Ident(p) => p.segments[0].name.as_str(),
            other => panic!("not a bare ident: {other:?}"),
        }
    }

    // I1. named connections: dff u1(.clk(clk), .d(d), .q(q));
    #[test]
    fn i1_named_connections() {
        let mi = inst_of("dff u1(.clk(clk), .d(d), .q(q));");
        assert_eq!(mi.module_name.name, "dff");
        assert!(mi.param_overrides.is_empty());
        assert_eq!(mi.instances.len(), 1);
        let it = &mi.instances[0];
        assert_eq!(it.name.name, "u1");
        let PortConnList::Named(conns) = &it.conns else {
            panic!("not named")
        };
        assert_eq!(conns.len(), 3);
        assert_eq!(conns[0].name.name, "clk");
        assert_eq!(id_name(conns[0].value.as_ref().unwrap()), "clk");
        assert_eq!(conns[2].name.name, "q");
        assert_eq!(id_name(conns[2].value.as_ref().unwrap()), "q");
    }

    // I2. positional connections: dff u1(clk, d, q);
    #[test]
    fn i2_positional_connections() {
        let mi = inst_of("dff u1(clk, d, q);");
        assert_eq!(mi.module_name.name, "dff");
        let PortConnList::Positional(conns) = &mi.instances[0].conns else {
            panic!("not positional")
        };
        assert_eq!(conns.len(), 3);
        assert_eq!(id_name(conns[0].as_ref().unwrap()), "clk");
        assert_eq!(id_name(conns[1].as_ref().unwrap()), "d");
        assert_eq!(id_name(conns[2].as_ref().unwrap()), "q");
    }

    // I3. named param override: reg8 #(.W(8)) r(.d(d), .q(q));
    #[test]
    fn i3_named_param_override() {
        let mi = inst_of("reg8 #(.W(8)) r(.d(d), .q(q));");
        assert_eq!(mi.module_name.name, "reg8");
        assert_eq!(mi.param_overrides.len(), 1);
        let ParamConn::Named { name, value, .. } = &mi.param_overrides[0] else {
            panic!("not a named override")
        };
        assert_eq!(name.name, "W");
        assert!(matches!(
            value.as_ref().unwrap().kind,
            ExprKind::IntLit { .. }
        ));
        assert_eq!(mi.instances[0].name.name, "r");
    }

    // I4. positional param override + multiple params: mem #(8, 256) u(.clk(clk));
    #[test]
    fn i4_positional_param_override() {
        let mi = inst_of("mem #(8, 256) u(.clk(clk));");
        assert_eq!(mi.param_overrides.len(), 2);
        assert!(matches!(mi.param_overrides[0], ParamConn::Positional(_)));
        assert!(matches!(mi.param_overrides[1], ParamConn::Positional(_)));
    }

    // I5. multiple instances per statement: dff u0(clk,q0), u1(q0,q1);
    #[test]
    fn i5_multiple_instances_per_statement() {
        let mi = inst_of("dff u0(clk, q0), u1(q0, q1);");
        assert_eq!(mi.module_name.name, "dff");
        assert_eq!(mi.instances.len(), 2);
        assert_eq!(mi.instances[0].name.name, "u0");
        assert_eq!(mi.instances[1].name.name, "u1");
    }

    // I6. unconnected positional slot: alu u(a, , c);  → None in the middle.
    #[test]
    fn i6_positional_unconnected_slot() {
        let mi = inst_of("alu u(a, , c);");
        let PortConnList::Positional(conns) = &mi.instances[0].conns else {
            panic!("not positional")
        };
        assert_eq!(conns.len(), 3);
        assert!(conns[0].is_some());
        assert!(conns[1].is_none()); // skipped port
        assert!(conns[2].is_some());
    }

    // I7. explicitly-unconnected named port `.q()` ⇒ value None; empty `()` list.
    #[test]
    fn i7_named_empty_and_empty_list() {
        let mi = inst_of("dff u1(.clk(clk), .q());");
        let PortConnList::Named(conns) = &mi.instances[0].conns else {
            panic!("not named")
        };
        assert_eq!(conns.len(), 2);
        assert!(conns[1].value.is_none(), "`.q()` ⇒ None");
        // empty `()` list ⇒ zero-arity Positional
        let mi2 = inst_of("noports u2();");
        let PortConnList::Positional(c2) = &mi2.instances[0].conns else {
            panic!("empty () should be Positional")
        };
        assert!(c2.is_empty());
    }

    // I8. instance-array dim + a connection expr: rep u_x [3:0] (.in(bus));
    #[test]
    fn i8_instance_array_dim() {
        let mi = inst_of("rep u_x [3:0] (.in(bus));");
        let it = &mi.instances[0];
        assert_eq!(it.name.name, "u_x");
        assert_eq!(it.unpacked.len(), 1);
        assert!(matches!(it.unpacked[0], Dim::Range(_)));
    }

    // I9. expression-valued named connection: dff u(.d(a & b), .q(q));
    #[test]
    fn i9_expression_connection() {
        let mi = inst_of("dff u(.d(a & b), .q(q));");
        let PortConnList::Named(conns) = &mi.instances[0].conns else {
            panic!("not named")
        };
        let (op, _l, _r) = bin(conns[0].value.as_ref().unwrap());
        assert_eq!(op, BinOp::BitAnd);
    }

    // I10. recovery: `.*` implicit connection is stubbed (one error), trailing
    //      good item still parses (verdict: deferred, recovering).
    #[test]
    fn i10_dotstar_stub_recovers() {
        let (su, errs) = p("module m; sub u1(.*); assign y = a;\nendmodule");
        assert!(!errs.is_empty(), "expected the .* advisory");
        let su = su.unwrap();
        let m = first_module(&su);
        // the instance is still present (as an empty Named list)…
        assert!(m.body.iter().any(|i| matches!(i, ModuleItem::Instance(_))));
        // …and the trailing assign still parses.
        assert!(m
            .body
            .iter()
            .any(|i| matches!(i, ModuleItem::ContAssign(_))));
    }

    // ───────────────────────── PR3: generate / genvar ─────────────────────────

    /// Parse a single generate construct wrapped in a module; return its items.
    fn gen_of(body: &str) -> Vec<GenItem> {
        let src = format!("module m;\n{body}\nendmodule");
        let (su, errs) = p(&src);
        assert!(errs.is_empty(), "parse errors: {errs:?}");
        let su = su.unwrap();
        let m = first_module(&su);
        match m.body.iter().find_map(|i| match i {
            ModuleItem::Generate(g) => Some(g),
            _ => None,
        }) {
            Some(g) => g.items.clone(),
            None => panic!("no generate construct in: {src}"),
        }
    }

    // g1. genvar multi-declaration → Genvar{names==["i","j"]}.
    #[test]
    fn g1_genvar_decl() {
        let (su, errs) = p("module m; genvar i, j;\nendmodule");
        assert!(errs.is_empty(), "{errs:?}");
        let su = su.unwrap();
        let m = first_module(&su);
        let ModuleItem::Genvar { names, .. } = &m.body[0] else {
            panic!("not a genvar decl: {:?}", m.body[0]);
        };
        assert_eq!(
            names.iter().map(|i| i.name.as_str()).collect::<Vec<_>>(),
            ["i", "j"]
        );
    }

    // g2. labeled generate-for with an instance body → For{label hoisted to "g"},
    //     init/step lvalue "i", body one Item(Instance).
    #[test]
    fn g2_gen_for_labeled_instance() {
        let items = gen_of(
            "generate for (i = 0; i < 3; i = i + 1) begin : g\n  leaf u (.a(x[i]));\nend\nendgenerate",
        );
        assert_eq!(items.len(), 1);
        let GenItem::For {
            init,
            step,
            label,
            body,
            ..
        } = &items[0]
        else {
            panic!("not a For: {:?}", items[0]);
        };
        assert_eq!(init.lvalue.name, "i");
        assert_eq!(step.lvalue.name, "i");
        assert_eq!(label.as_ref().map(|l| l.name.as_str()), Some("g"));
        assert_eq!(body.len(), 1);
        assert!(matches!(
            &body[0],
            GenItem::Item(mi) if matches!(**mi, ModuleItem::Instance(_))
        ));
    }

    // g3. bare-body generate-for (no begin/end) → For{label none}, body one
    //     Item(ContAssign).
    #[test]
    fn g3_gen_for_bare_body() {
        let items =
            gen_of("generate for (i = 0; i < 2; i = i + 1) assign y[i] = a[i];\nendgenerate");
        assert_eq!(items.len(), 1);
        let GenItem::For { label, body, .. } = &items[0] else {
            panic!("not a For: {:?}", items[0]);
        };
        assert!(label.is_none());
        assert_eq!(body.len(), 1);
        assert!(matches!(
            &body[0],
            GenItem::Item(mi) if matches!(**mi, ModuleItem::ContAssign(_))
        ));
    }

    // g4. generate-if with and without else.
    #[test]
    fn g4_gen_if_else() {
        let items = gen_of("generate if (W) assign y = a; else assign y = b;\nendgenerate");
        let GenItem::If { then_b, else_b, .. } = &items[0] else {
            panic!("not an If: {:?}", items[0]);
        };
        assert_eq!(then_b.len(), 1);
        assert_eq!(else_b.len(), 1);

        let items = gen_of("generate if (W) assign y = a;\nendgenerate");
        let GenItem::If { then_b, else_b, .. } = &items[0] else {
            panic!("not an If: {:?}", items[0]);
        };
        assert_eq!(then_b.len(), 1);
        assert!(else_b.is_empty());
    }

    // g5. generate-case: 0:…  1,2:…  default:… → Match{1}, Match{2}, Default.
    #[test]
    fn g5_gen_case() {
        let items = gen_of(
            "generate case (W)\n  0: assign y = a;\n  1, 2: assign y = b;\n  default: assign y = c;\nendcase\nendgenerate",
        );
        let GenItem::Case { items: cis, .. } = &items[0] else {
            panic!("not a Case: {:?}", items[0]);
        };
        assert_eq!(cis.len(), 3);
        assert!(matches!(&cis[0], GenCaseItem::Match { labels, .. } if labels.len() == 1));
        assert!(matches!(&cis[1], GenCaseItem::Match { labels, .. } if labels.len() == 2));
        assert!(matches!(&cis[2], GenCaseItem::Default { .. }));
    }

    // g6. (M2 clamp) truncated generate headers recover with errors and DO NOT
    //     panic on the inverted Span::to union.
    #[test]
    fn g6_truncated_headers_no_panic() {
        for src in [
            "module m; generate for endgenerate\nendmodule",
            "module m; generate if (\nendmodule",
            "module m; generate case (\nendmodule",
            "module m; generate for (\nendmodule",
        ] {
            let (toks, _lex) = hdl_lexer::lex(src);
            let (_su, errs) = parse(&toks, src);
            assert!(!errs.is_empty(), "expected parse errors for `{src}`");
        }
    }

    // ─────────────────────── function / task definitions ───────────────────────
    fn item_of(body: &str) -> ModuleItem {
        let src = format!("module m;\n{body}\nendmodule");
        let (su, errs) = p(&src);
        assert!(errs.is_empty(), "parse errors: {errs:?}");
        let su = su.unwrap();
        let m = first_module(&su);
        m.body[0].clone()
    }

    // ft1. ANSI combinational function: width range, one input formal, single
    //      `f = <expr>` body reachable as a Block with one Blocking to the func name.
    #[test]
    fn ft1_parse_ansi_function_def() {
        let it = item_of("function [7:0] add1(input [7:0] x); add1 = x + 1; endfunction");
        let ModuleItem::Func(f) = it else {
            panic!("not a function: {it:?}");
        };
        assert_eq!(f.name.name, "add1");
        assert!(!f.automatic);
        assert!(f.range.is_some(), "expected [7:0] return range");
        assert_eq!(f.ret_type, ParamType::Implicit);
        assert_eq!(f.ports.len(), 1);
        assert_eq!(f.ports[0].dir, PortDir::Input);
        assert_eq!(f.ports[0].name.name, "x");
        assert!(f.ports[0].range.is_some());
        // body: a single blocking assign `add1 = x + 1`
        let Stmt::Blocking { lhs, rhs, .. } = &*f.body else {
            panic!("expected single Blocking body, got {:?}", f.body);
        };
        assert!(matches!(lhs, Lvalue::Ident(p) if p.segments[0].name == "add1"));
        assert!(matches!(&rhs.kind, ExprKind::Binary { op: BinOp::Add, .. }));
    }

    // ft2. Non-ANSI function: formal declared in the body prefix, hoisted into ports.
    #[test]
    fn ft2_parse_non_ansi_function_def() {
        let it = item_of(
            "function [3:0] f; input [3:0] a; reg [3:0] t; begin t = a; f = t; end endfunction",
        );
        let ModuleItem::Func(f) = it else {
            panic!("not a function: {it:?}");
        };
        assert_eq!(f.name.name, "f");
        // non-ANSI input `a` hoisted into ports
        assert_eq!(f.ports.len(), 1);
        assert_eq!(f.ports[0].dir, PortDir::Input);
        assert_eq!(f.ports[0].name.name, "a");
        // local `reg t` lands in body_decls
        assert_eq!(f.body_decls.len(), 1);
        assert_eq!(f.body_decls[0].names[0].name.name, "t");
        // body is a begin..end with two blocking assigns
        let Stmt::Block { stmts, .. } = &*f.body else {
            panic!("expected begin-end body, got {:?}", f.body);
        };
        assert_eq!(stmts.len(), 2);
    }

    // ft3. Task with input + output formals (ANSI), begin-end body.
    #[test]
    fn ft3_parse_task_def() {
        let it = item_of("task drive(input [7:0] d, output [7:0] q); begin q = d; end endtask");
        let ModuleItem::Task(t) = it else {
            panic!("not a task: {it:?}");
        };
        assert_eq!(t.name.name, "drive");
        assert!(!t.automatic);
        assert_eq!(t.ports.len(), 2);
        assert_eq!(t.ports[0].dir, PortDir::Input);
        assert_eq!(t.ports[0].name.name, "d");
        assert_eq!(t.ports[1].dir, PortDir::Output);
        assert_eq!(t.ports[1].name.name, "q");
        let Stmt::Block { stmts, .. } = &*t.body else {
            panic!("expected begin-end body, got {:?}", t.body);
        };
        assert_eq!(stmts.len(), 1);
    }

    // ft4. Sticky direction across comma-grouped formals: `input a, b` → both Input.
    #[test]
    fn ft4_sticky_direction_and_empty_task() {
        let it = item_of("function f(input a, b); f = a & b; endfunction");
        let ModuleItem::Func(f) = it else {
            panic!("not a function");
        };
        assert_eq!(f.ports.len(), 2);
        assert_eq!(f.ports[0].dir, PortDir::Input);
        assert_eq!(f.ports[1].dir, PortDir::Input);
        assert_eq!(f.ports[1].name.name, "b");

        // empty-bodied task with no port list: `task t; endtask`
        let it2 = item_of("task t; endtask");
        let ModuleItem::Task(t) = it2 else {
            panic!("not a task");
        };
        assert!(t.ports.is_empty());
        assert!(matches!(&*t.body, Stmt::Null(_)));
    }
}
