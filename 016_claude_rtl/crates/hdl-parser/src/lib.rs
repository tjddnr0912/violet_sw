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

pub struct Parser<'t, 's> {
    toks: &'t [Spanned],
    src: &'s str,
    pos: usize,
    src_end: u32,
    pub errors: Vec<ParseError>,
    error_limit: usize,
    /// SV user-defined type names (`typedef … name;`) → resolved underlying type.
    /// Accumulates across the source unit; lets `name var;` parse as a typed decl.
    typedefs: std::collections::HashMap<String, TypeInfo>,
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
            typedefs: std::collections::HashMap::new(),
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

    /// `prev = None` ⇒ first ANSI port; a missing direction is then an ERROR
    /// (verdict M4: don't silently default the first port to Input). A comma-continued
    /// port with no direction inherits the previous port's direction; a PURE
    /// continuation (`input [7:0] a, b`) that also omits its own type/range/signed
    /// inherits those too, so both `a` and `b` are `[7:0]` (IEEE 1800 §23.2.2.1).
    fn parse_ansi_port(&mut self, prev: Option<&AnsiPort>) -> AnsiPort {
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
                Kw::Initial | Kw::Always | Kw::AlwaysFf | Kw::AlwaysComb | Kw::AlwaysLatch
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
        // bare ident at module-item position ⇒ module instantiation.
        // (No keyword-led item matched above; in V2005 module scope a leading
        //  bare identifier can ONLY begin an instantiation — there is no
        //  bare-ident contassign/decl. The dispatch position itself is the
        //  disambiguation, so no multi-token lookahead is needed to decide.)
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
        while self.peek() == Some(TokenKind::LBracket) {
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
        self.bump(); // the type-name identifier
        let names = self.parse_decl_name_list()?;
        self.expect(TokenKind::Semi, "';'");
        Some(NetVarDecl {
            kind: info.kind,
            signed: info.signed,
            range: info.range,
            packed: info.packed,
            names,
            span: start.to(self.prev_span()),
        })
    }

    /// `typedef enum [base] { L0, L1 = expr, … } name;` (Phase-2). Registers
    /// `name` in `self.typedefs` (so a later `name var;` parses) and returns the
    /// AST node so elaborate can register the labels as integer constants.
    fn parse_typedef(&mut self) -> Option<ModuleItem> {
        let start = self.cur_span();
        self.bump(); // `typedef`
        if !self.at_kw(Kw::Enum) {
            // typedef-alias and packed-struct forms are later Phase-2 sub-stages.
            self.error("`enum` after `typedef`");
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
                Kw::Repeat => self.parse_repeat(),
                Kw::Forever => self.parse_forever(),
                Kw::Wait => self.parse_wait(),
                Kw::Disable => self.parse_disable(),
                Kw::Assign => self.parse_proc_assign(),
                Kw::Deassign => self.parse_deassign(),
                Kw::Force => self.parse_force(),
                Kw::Release => self.parse_release(),
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
                self.skip_intra_assign_delay(); // M4: discard `#d`/`@(ev)`, one advisory
                let rhs = self.expr(0);
                self.expect(TokenKind::Semi, "';'");
                Stmt::Blocking {
                    lhs,
                    delay: None,
                    rhs,
                    span: start.to(self.prev_span()),
                }
            }
            Some(TokenKind::LtEq) => {
                self.bump();
                self.skip_intra_assign_delay(); // M4: `q <= #1 d;` is extremely common
                let rhs = self.expr(0);
                self.expect(TokenKind::Semi, "';'");
                Stmt::NonBlocking {
                    lhs,
                    delay: None,
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

    /// M4: intra-assignment timing control after `=`/`<=`. DEFERRED — parse-and-DISCARD
    /// with ONE advisory error so the RHS still parses cleanly (no cascade).
    fn skip_intra_assign_delay(&mut self) {
        match self.peek() {
            Some(TokenKind::Hash) => {
                self.error("intra-assignment delay (not yet supported; ignored)");
                let _ = self.parse_delay(); // consumes `#d` / `#(…)`
            }
            Some(TokenKind::At) => {
                self.error("intra-assignment event control (not yet supported; ignored)");
                let _ = self.parse_sensitivity(); // consumes `@(…)`
            }
            _ => {}
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
    //      and intra-assign delay `q <= #1 d;` parses RHS cleanly with an advisory.
    #[test]
    fn s14_event_body_none_and_intra_delay() {
        // M4: intra-assign delay emits ONE advisory error — parse directly (not proc_of).
        let src = "module m;\ninitial begin repeat (8) @(posedge clk); wait (ready); q <= #1 d; end\nendmodule";
        let (su, errs) = p(src);
        assert_eq!(errs.len(), 1, "exactly one advisory for intra-assign delay");
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
        // M4: intra-assign delay discarded, RHS still parses as a NonBlocking to `d`.
        let Stmt::NonBlocking { delay, .. } = &stmts[2] else {
            panic!("not NonBlocking")
        };
        assert!(delay.is_none(), "intra-assign delay is dropped (deferred)");
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
