//! Differential verification against Icarus Verilog (`iverilog` + `vvp`) — the
//! doc-01 §성공기준 golden. Each representative design is run through BOTH vitamin and
//! iverilog and their `$display` output is compared. If iverilog/vvp are not on PATH
//! (e.g. a minimal CI image) the check SKIPS gracefully (the design still simulates
//! through vitamin so a vitamin-side crash is still caught).

use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

use diag::{LogEvent, LogSink};
use sim_engine::{simulate_capture, SimOpts};

static NEXT: AtomicU64 = AtomicU64::new(0);

#[derive(Default)]
struct DiagSink(std::cell::RefCell<Vec<String>>);
impl LogSink for DiagSink {
    fn emit(&self, e: LogEvent) {
        if let LogEvent::Diagnostic(d) = e {
            self.0
                .borrow_mut()
                .push(format!("{:?}: {}", d.severity, d.message));
        }
    }
}

/// vitamin: lex → parse → elaborate → simulate, returning the captured stdout.
fn vita_out(src: &str) -> String {
    let (toks, le) = hdl_lexer::lex(src);
    assert!(le.is_empty(), "lex errors: {le:?}");
    let (su, pe) = hdl_parser::parse(&toks, src);
    assert!(pe.is_empty(), "parse errors: {pe:?}");
    let sink = DiagSink::default();
    let ir = elaborate::elaborate(&su.expect("source unit"), &sink);
    let hard: Vec<String> = sink
        .0
        .borrow()
        .iter()
        .filter(|d| d.starts_with("Error") || d.starts_with("Fatal"))
        .cloned()
        .collect();
    assert!(hard.is_empty(), "elaborate errors: {hard:?}");
    let (_res, out) = simulate_capture(&ir.expect("ir"), SimOpts::default());
    out
}

fn on_path(tool: &str) -> bool {
    Command::new("sh")
        .arg("-c")
        .arg(format!("command -v {tool}"))
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

/// iverilog + vvp: compile and run, returning the design's `$display` stdout
/// (the vvp `$finish called …` banner line is stripped). `None` ⇒ tool absent.
fn iverilog_out(src: &str) -> Option<String> {
    if !on_path("iverilog") || !on_path("vvp") {
        return None;
    }
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let dir = std::env::temp_dir();
    let sv = dir.join(format!("vita_diff_{}_{n}.sv", std::process::id()));
    let vvp = dir.join(format!("vita_diff_{}_{n}.vvp", std::process::id()));
    std::fs::write(&sv, src).expect("write sv");
    let compile = Command::new("iverilog")
        .args(["-g2012", "-o"])
        .arg(&vvp)
        .arg(&sv)
        .output()
        .expect("run iverilog");
    assert!(
        compile.status.success(),
        "iverilog compile failed: {}",
        String::from_utf8_lossy(&compile.stderr)
    );
    let run = Command::new("vvp").arg(&vvp).output().expect("run vvp");
    let _ = std::fs::remove_file(&sv);
    let _ = std::fs::remove_file(&vvp);
    let stdout = String::from_utf8_lossy(&run.stdout);
    // strip vvp's runtime banner lines (`$finish called …`, etc.)
    let mut filtered = String::new();
    for l in stdout
        .lines()
        .filter(|l| !l.contains("$finish called") && !l.contains("$stop called"))
    {
        filtered.push_str(l);
        filtered.push('\n');
    }
    Some(filtered)
}

/// Assert vitamin and iverilog produce identical `$display` output (skip if iverilog
/// is unavailable). The design must be IEEE-deterministic (no X-dependent output).
fn assert_matches_iverilog(name: &str, src: &str) {
    let v = vita_out(src);
    match iverilog_out(src) {
        None => eprintln!("[{name}] iverilog/vvp not on PATH — differential check skipped"),
        Some(iv) => assert_eq!(
            v.trim_end(),
            iv.trim_end(),
            "[{name}] vitamin vs iverilog divergence"
        ),
    }
}

#[test]
fn diff_alu() {
    assert_matches_iverilog(
        "alu",
        "module alu(input [7:0] a, b, input [1:0] op, output reg [7:0] y); \
           always @* case (op) 2'd0:y=a+b; 2'd1:y=a-b; 2'd2:y=a&b; 2'd3:y=a|b; endcase endmodule \
         module tb; reg [7:0] a, b; reg [1:0] op; wire [7:0] y; alu u(a,b,op,y); \
           initial begin a=8'd10; b=8'd3; \
             op=2'd0; #1 $display(\"%0d\",y); op=2'd1; #1 $display(\"%0d\",y); \
             op=2'd2; #1 $display(\"%0d\",y); op=2'd3; #1 $display(\"%0d\",y); $finish; end endmodule",
    );
}

#[test]
fn diff_counter_with_reset() {
    assert_matches_iverilog(
        "counter",
        "module counter(input clk, rst, output reg [3:0] cnt); \
           always @(posedge clk) if (rst) cnt<=4'd0; else cnt<=cnt+4'd1; endmodule \
         module tb; reg clk, rst; wire [3:0] cnt; counter c(clk,rst,cnt); integer k; \
           initial begin clk=0; rst=1; #5 clk=1; #5 clk=0; rst=0; \
             for (k=0;k<6;k=k+1) begin #5 clk=1; #5 clk=0; end \
             $display(\"%0d\", cnt); $finish; end endmodule",
    );
}

#[test]
fn diff_memory_accumulate() {
    assert_matches_iverilog(
        "memory",
        "module tb; reg [7:0] mem[0:7]; integer i; reg [15:0] sum; \
           initial begin for (i=0;i<8;i=i+1) mem[i]=i*3; \
             sum=0; for (i=0;i<8;i=i+1) sum=sum+mem[i]; \
             $display(\"%0d\", sum); $finish; end endmodule",
    );
}

#[test]
fn diff_shift_and_arith() {
    assert_matches_iverilog(
        "shift",
        "module tb; reg [15:0] x; integer i; \
           initial begin x=16'd1; for (i=0;i<5;i=i+1) x=x<<1; \
             $display(\"%0d %0d %0d\", x, x>>2, x*3); $finish; end endmodule",
    );
}

#[test]
fn diff_packed_struct() {
    assert_matches_iverilog(
        "packed_struct",
        "module tb; typedef struct packed { logic [7:0] hi; logic [7:0] lo; } word_t; \
           word_t w; \
           initial begin w.hi = 8'hDE; w.lo = 8'hAD; \
             $display(\"%h %h %h\", w.hi, w.lo, w); \
             w = 16'hBEEF; $display(\"%h %h\", w.hi, w.lo); $finish; end endmodule",
    );
}

#[test]
fn diff_packed_struct_single_bit_field() {
    // 3 fields incl. a 1-bit member: tag[4](high), valid[1](mid), data[3:0](low).
    // total=9. Exercises odd-boundary offset math against iverilog.
    assert_matches_iverilog(
        "packed_struct_bits",
        "module tb; typedef struct packed { logic [4:0] tag; logic valid; logic [2:0] data; } e_t; \
           e_t e; \
           initial begin e.tag = 5'h1A; e.valid = 1'b1; e.data = 3'h5; \
             $display(\"%h %b %h %h\", e.tag, e.valid, e.data, e); \
             e = 9'h0AB; $display(\"%h %b %h\", e.tag, e.valid, e.data); $finish; end endmodule",
    );
}

#[test]
fn diff_typedef_alias() {
    assert_matches_iverilog(
        "typedef_alias",
        "module tb; typedef logic [7:0] byte_t; typedef reg [3:0] nib_t; \
           byte_t a, b; nib_t n; \
           initial begin a = 8'hF0; b = 8'h0F; n = a[7:4]; \
             $display(\"%h %0d %0d\", a | b, n, a + b); $finish; end endmodule",
    );
}

#[test]
fn diff_enum_labels() {
    assert_matches_iverilog(
        "enum",
        "module tb; typedef enum {RED, GREEN, BLUE} color_t; color_t c; \
           integer i; reg [31:0] acc; \
           initial begin acc = 0; \
             c = RED;   acc = acc + c; \
             c = GREEN; acc = acc + c; \
             c = BLUE;  acc = acc + c; \
             $display(\"%0d %0d %0d\", RED, GREEN, BLUE); \
             $display(\"%0d\", acc); $finish; end endmodule",
    );
}

#[test]
fn diff_wide_reduction_word_boundary() {
    // 100-bit reductions spanning two words — exercises word-level reduce_word
    // (any-0 / any-1 / parity + last-word mask) against iverilog.
    assert_matches_iverilog(
        "wide_reduction",
        "module tb; reg [99:0] v; \
           initial begin v = 100'h0; v[0] = 1'b1; v[50] = 1'b1; v[99] = 1'b1; \
             $display(\"%b %b %b %b\", &v, |v, ^v, ~|v); $finish; end endmodule",
    );
}

#[test]
fn diff_wide_bitwise_word_boundary() {
    // 96-bit bitwise across the 64-bit word boundary — exercises the word-level
    // and_w/or_w/xor_w/not_w paths + last-word masking against iverilog.
    assert_matches_iverilog(
        "wide_bitwise",
        "module tb; reg [95:0] a, b; \
           initial begin a = 96'hFFFF0000_FFFF0000_FFFF0000; \
                         b = 96'h0F0F0F0F_0F0F0F0F_0F0F0F0F; \
             $display(\"%h %h %h %h\", a & b, a | b, a ^ b, ~a); $finish; end endmodule",
    );
}

#[test]
fn diff_casez_priority() {
    assert_matches_iverilog(
        "casez",
        "module tb; reg [3:0] s; reg [7:0] r; \
           initial begin s=4'b0110; \
             casez (s) 4'b1???:r=8'd1; 4'b01??:r=8'd2; default:r=8'd9; endcase \
             $display(\"%0d\", r); $finish; end endmodule",
    );
}

#[test]
fn diff_const_domain_cluster() {
    // P0-5/6/7 (2026-06-10): signed-i64 elaboration const domain — ternary and
    // $clog2 param folding, `1<<32` past the old u32 wrap, signed `>>>`,
    // negative-param display, and a descending generate-for. iverilog parity.
    assert_matches_iverilog(
        "const_domain",
        "module tb; \
           parameter MODE = 1; \
           parameter W = MODE ? 16 : 8; \
           parameter DEPTH = 300; \
           localparam AW = $clog2(DEPTH); \
           parameter [63:0] F = 1 << 32; \
           parameter S = -4; \
           parameter T = S >>> 1; \
           wire [3:0] in_w, out_w; \
           assign in_w = 4'b1010; \
           genvar i; \
           generate for (i = 3; i >= 0; i = i - 1) begin: g \
             assign out_w[i] = in_w[i]; \
           end endgenerate \
           initial begin \
             $display(\"%0d %0d %0d %0d %0d\", W, AW, F, S, T); \
             #1 $display(\"%b\", out_w); \
             $finish; \
           end endmodule",
    );
}

#[test]
fn diff_wide_value_truncation_cluster() {
    // P0-1~4 (2026-06-10): >64-bit relational compare, over-u64 shift amounts,
    // full-width unary minus and wide $clog2 — all formerly truncated to the
    // low word. Locks the fixed semantics against the iverilog oracle.
    assert_matches_iverilog(
        "wide_trunc",
        "module tb; reg [127:0] a, b, n; reg signed [127:0] sa, sb; \
           reg [7:0] x, l, r; reg signed [7:0] sx, sy; reg [127:0] s; \
           initial begin \
             a = 128'h1_0000_0000_0000_0000; b = 128'h1; \
             $display(\"%b %b %b %b\", a > b, a < b, a >= b, a <= b); \
             sa = 128'hffff_ffff_ffff_ffff_ffff_ffff_ffff_ffff; sb = 128'sd1; \
             $display(\"%b %b\", sa < sb, sa > sb); \
             x = 8'hFF; s = 128'h1_0000_0000_0000_0000; \
             l = x << s; r = x >> s; \
             $display(\"%h %h\", l, r); \
             sx = -8'sd2; sy = sx >>> s; \
             $display(\"%b\", sy); \
             n = -128'd1; \
             $display(\"%h\", n); \
             $display(\"%0d %0d\", $clog2(a), $clog2(a + 1)); \
             $finish; end endmodule",
    );
}
