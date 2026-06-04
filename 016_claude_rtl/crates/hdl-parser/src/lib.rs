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
pub struct Parser<'t, 's> {
    toks: &'t [Spanned],
    src: &'s str,
    pos: usize,
    src_end: u32,
    pub errors: Vec<ParseError>,
    error_limit: usize,
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

    // -- cursor primitives --
    #[inline]
    fn peek(&self) -> Option<TokenKind> {
        self.toks.get(self.pos).map(|t| t.kind)
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
    pub fn expr(&mut self, min_bp: u8) -> Expr {
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
        while self.peek() == Some(TokenKind::LBracket) {
            e = self.parse_select(e);
        }
        e
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
            // identifier / hierarchical name / function call
            _ if self.is_ident() => {
                let path = self.hier_path().unwrap();
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
    /// Unpacked dimension `[hi:lo]` (Range) or `[N]` (Size) — verdict M3.
    fn parse_dim(&mut self) -> Option<Dim> {
        if self.peek() != Some(TokenKind::LBracket) {
            return None;
        }
        self.bump(); // '['
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
        let start = self.cur_span();
        let is_macromodule = self.at_kw(Kw::Macromodule);
        self.bump(); // module / macromodule
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

        // body until endmodule — with forward-progress guard (BLOCKER B3)
        let mut body = Vec::new();
        while !self.at_eof() && !self.at_kw(Kw::Endmodule) {
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
            TokenKind::Word(WordKind::Keyword(Kw::Endmodule)),
            "'endmodule'",
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
        );
        if ansi {
            let mut ports = Vec::new();
            let mut prev_dir: Option<PortDir> = None; // None ⇒ this is the FIRST port
            loop {
                let port = self.parse_ansi_port(prev_dir);
                prev_dir = Some(port.dir);
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

    /// `inherited = None` ⇒ first ANSI port; a missing direction is then an ERROR
    /// (verdict M4: don't silently default the first port to Input). Subsequent
    /// ports inherit the previous direction when omitted.
    fn parse_ansi_port(&mut self, inherited: Option<PortDir>) -> AnsiPort {
        let start = self.cur_span();
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
        let dir = match (explicit_dir, inherited) {
            (Some(d), _) => d,
            (None, Some(prev)) => prev, // inherit
            (None, None) => {
                self.error("port direction (first ANSI port must specify one)");
                PortDir::Input
            } // recover as Input
        };
        let net_or_var = self.net_var_kind();
        if net_or_var.is_some() {
            self.bump();
        }
        let signed = self.opt_signed();
        let range = self.opt_range();
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
            name,
            default,
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
        // net/var declaration
        if self.net_var_kind().is_some() {
            return self.parse_net_var().map(ModuleItem::NetVar);
        }
        // procedural blocks / generate / genvar → recovering STUB (types exist)
        if matches!(
            self.peek(),
            Some(TokenKind::Word(WordKind::Keyword(
                Kw::Initial
                    | Kw::Always
                    | Kw::AlwaysFf
                    | Kw::AlwaysComb
                    | Kw::AlwaysLatch
                    | Kw::Generate
                    | Kw::Genvar
            )))
        ) {
            let s = self.cur_span();
            self.error("(procedural/generate parsing not yet implemented)");
            self.skip_balanced_block(); // consume @(…) begin…end / generate…endgenerate
            return Some(ModuleItem::Error(s));
        }
        // bare ident ⇒ likely a module instance (deferred) → stub
        if self.is_ident() {
            let s = self.cur_span();
            self.error("(module instantiation parsing not yet implemented)");
            self.synchronize();
            return Some(ModuleItem::Error(s));
        }
        self.error("module item");
        None
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
        let mut names = Vec::new();
        loop {
            let n_start = self.cur_span();
            let name = self.ident()?;
            let mut unpacked = Vec::new();
            while self.peek() == Some(TokenKind::LBracket) {
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
        self.expect(TokenKind::Semi, "';'");
        Some(NetVarDecl {
            kind,
            signed,
            range,
            names,
            span: start.to(self.prev_span()),
        })
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
        let mut lv = Lvalue::Ident(path);
        while self.peek() == Some(TokenKind::LBracket) {
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
        }
        lv
    }

    /// STUB (PR1): consume an `@(…) begin … end` / single stmt / `generate …
    /// endgenerate` body without parsing it, balancing depth so we land cleanly
    /// past it. Has its own forward-progress safety via `at_eof` checks.
    fn skip_balanced_block(&mut self) {
        // skip leading `@(...)` sensitivity if present
        if self.peek() == Some(TokenKind::At) {
            self.bump();
            if self.eat(TokenKind::LParen) {
                let mut depth = 1;
                while depth > 0 {
                    match self.bump().map(|t| t.kind) {
                        Some(TokenKind::LParen) => depth += 1,
                        Some(TokenKind::RParen) => depth -= 1,
                        None => return,
                        _ => {}
                    }
                }
            } else if self.eat(TokenKind::Star) { /* @* */
            }
        }
        // begin/end OR generate/endgenerate block, else a single procedural stmt
        let opener_closer = if self.at_kw(Kw::Begin) {
            Some((Kw::Begin, Kw::End))
        } else if self.at_kw(Kw::Generate) {
            Some((Kw::Generate, Kw::Endgenerate))
        } else {
            None
        };
        if let Some((opener, closer)) = opener_closer {
            self.bump();
            let mut depth = 1;
            while depth > 0 && !self.at_eof() {
                if self.at_kw(opener) {
                    depth += 1;
                    self.bump();
                } else if self.at_kw(closer) {
                    depth -= 1;
                    self.bump();
                } else {
                    self.bump();
                }
            }
        } else {
            self.synchronize(); // single procedural stmt → sync to ';'
        }
    }
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

#[cfg(test)]
mod tests {
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
}
