//! P1-2/3/9: legality promotions (REMAINING_WORK 2026-06-10).
//!
//! These constructs previously WARNED and then misbehaved: `force/release`,
//! procedural `assign/deassign`, `->event` were warn+no-op (values never
//! changed; an `@(ev)` waited forever), a non-constant `#delay` silently
//! degraded to `#0` (turning `forever #x` into a delta-limit blowup), and
//! net-vs-variable assignment legality was never checked (iverilog rejects
//! both directions; doc-02 documents them as errors). All are LOUD now:
//! `E-ELAB-UNSUPPORTED` for the v1 cuts, `E-ELAB-LVALUE-KIND` (VITA-E3018,
//! promoted from doc-15 Appendix A) for the kind violations.

use diag::{LogEvent, LogSink};

#[derive(Default)]
struct DiagSink(std::cell::RefCell<Vec<String>>);
impl LogSink for DiagSink {
    fn emit(&self, e: LogEvent) {
        if let LogEvent::Diagnostic(d) = e {
            self.0.borrow_mut().push(format!(
                "{}[{}]: {}",
                d.severity.token(),
                d.code.code_num(),
                d.message
            ));
        }
    }
}

/// lex → parse → elaborate; returns (ir present?, diagnostics).
fn elab(src: &str) -> (bool, Vec<String>) {
    let (toks, le) = hdl_lexer::lex(src);
    assert!(le.is_empty(), "lex errors: {le:?}");
    let (su, pe) = hdl_parser::parse(&toks, src);
    assert!(pe.is_empty(), "parse errors: {pe:?}");
    let sink = DiagSink::default();
    let ir = elaborate::elaborate(&su.expect("source unit"), &sink);
    (ir.is_some(), sink.0.into_inner())
}

fn assert_rejected(src: &str, needle: &str) {
    let (ok, diags) = elab(src);
    assert!(
        !ok,
        "elaborate must FAIL (was warn+no-op); diags: {diags:?}"
    );
    assert!(
        diags
            .iter()
            .any(|d| d.starts_with("error[") && d.contains(needle)),
        "expected an error mentioning {needle:?}; got {diags:?}"
    );
}

/// `->event` was a no-op while `@(ev)` waited forever — now a hard error.
/// (`event` declarations don't parse in v1, so the trigger statement is the
/// reachable surface.)
#[test]
fn event_trigger_is_rejected() {
    assert_rejected(
        r#"
module t;
  initial -> ev;
endmodule
"#,
        "event",
    );
}

/// `force`/`release` silently changed nothing.
#[test]
fn force_release_is_rejected() {
    assert_rejected(
        r#"
module t;
  reg a;
  initial begin
    force a = 1'b1;
    release a;
  end
endmodule
"#,
        "force",
    );
}

/// procedural `assign`/`deassign` silently changed nothing.
#[test]
fn procedural_assign_is_rejected() {
    assert_rejected(
        r#"
module t;
  reg a;
  initial begin
    assign a = 1'b1;
    deassign a;
  end
endmodule
"#,
        "assign",
    );
}

/// A non-constant `#delay` degraded to `#0`, turning `forever #x` into a
/// delta-limit blowup — now a hard error naming the construct.
#[test]
fn nonconstant_delay_is_rejected() {
    assert_rejected(
        r#"
module t;
  reg clk;
  integer d;
  initial begin
    d = 5;
    forever #d clk = ~clk;
  end
endmodule
"#,
        "delay",
    );
}

/// E3018: a continuous assign may not drive a variable (reg).
#[test]
fn cont_assign_to_reg_is_rejected() {
    let (ok, diags) = elab(
        r#"
module t;
  reg r;
  assign r = 1'b1;
endmodule
"#,
    );
    assert!(!ok, "must fail; diags: {diags:?}");
    assert!(
        diags.iter().any(|d| d.contains("VITA-E3018")),
        "expected E-ELAB-LVALUE-KIND; got {diags:?}"
    );
}

/// E3018: a procedural assignment may not target a net (wire).
#[test]
fn procedural_assign_to_wire_is_rejected() {
    let (ok, diags) = elab(
        r#"
module t;
  wire w;
  initial w = 1'b1;
endmodule
"#,
    );
    assert!(!ok, "must fail; diags: {diags:?}");
    assert!(
        diags.iter().any(|d| d.contains("VITA-E3018")),
        "expected E-ELAB-LVALUE-KIND; got {diags:?}"
    );
}

/// Sanity: the legal pairings stay accepted (wire ⇐ assign, reg ⇐ procedural).
#[test]
fn legal_kinds_still_accepted() {
    let (ok, diags) = elab(
        r#"
module t;
  wire w;
  reg r;
  assign w = r;
  initial begin
    r = 1'b1;
    #1 $finish;
  end
endmodule
"#,
    );
    let errs: Vec<&String> = diags.iter().filter(|d| d.starts_with("error[")).collect();
    assert!(
        ok && errs.is_empty(),
        "legal design must elaborate: {errs:?}"
    );
}

// ── P1-8: part/bit-select multi-driver accounting ───────────────────────────

/// Overlapping part-selects from two `assign`s were silently last-write-wins —
/// now E-ELAB-MULTIDRIVER (the v1 policy: no resolution, loud reject).
#[test]
fn overlapping_part_select_drivers_rejected() {
    let (ok, diags) = elab(
        r#"
module t;
  wire [7:0] y;
  reg [7:0] a, b;
  assign y[3:0] = a[3:0];
  assign y[4:2] = b[2:0];
endmodule
"#,
    );
    assert!(!ok, "overlap must fail; diags: {diags:?}");
    assert!(
        diags
            .iter()
            .any(|d| d.contains("E-ELAB-MULTIDRIVER") || d.contains("VITA-E3001")),
        "expected multidriver error; got {diags:?}"
    );
}

/// Whole-net + bit-select on the same net overlaps too.
#[test]
fn whole_net_plus_bit_select_rejected() {
    let (ok, diags) = elab(
        r#"
module t;
  wire [7:0] y;
  reg [7:0] a;
  reg c;
  assign y = a;
  assign y[0] = c;
endmodule
"#,
    );
    assert!(!ok, "overlap must fail; diags: {diags:?}");
    assert!(
        diags.iter().any(|d| d.contains("VITA-E3001")),
        "got {diags:?}"
    );
}

/// DISJOINT part-selects are a legal, common idiom — must stay accepted.
#[test]
fn disjoint_part_selects_accepted() {
    let (ok, diags) = elab(
        r#"
module t;
  wire [7:0] y;
  reg [3:0] a, b;
  assign y[3:0] = a;
  assign y[7:4] = b;
endmodule
"#,
    );
    let errs: Vec<&String> = diags.iter().filter(|d| d.starts_with("error[")).collect();
    assert!(
        ok && errs.is_empty(),
        "disjoint selects are legal: {errs:?}"
    );
}
