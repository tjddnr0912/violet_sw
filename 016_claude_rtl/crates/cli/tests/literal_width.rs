//! Unsized integer-literal width (P0-10). IEEE 1364 §3.5.1: an unsized literal
//! is "at least 32 bits", grown to hold its value. Pre-P0-10 every unsized
//! literal was packed to a FIXED 32 bits, so values >= 2^31 silently broke
//! (2^31 -> -2^31, 2^32 -> 0). The literal width also feeds self-determined
//! expression context, so a too-narrow literal corrupted comparisons/shifts.
//!
//! Every expected value/width is pinned LIVE against iverilog 13.0 ($bits).
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn run(src: &str) -> String {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let d = std::env::temp_dir().join(format!("vita_litw_{}_{n}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    let f = d.join("t.sv");
    std::fs::write(&f, src).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_vita"))
        .arg(f.to_str().unwrap())
        .current_dir(&d)
        .output()
        .expect("run vita");
    // Drop the trailing "simulation ended (...)" status line vita prints.
    let raw = String::from_utf8_lossy(&out.stdout);
    let mut s = String::new();
    for l in raw.lines().filter(|l| !l.starts_with("simulation ended")) {
        s.push_str(l);
        s.push('\n');
    }
    s
}

fn run_err(src: &str) -> (String, Option<i32>) {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let d = std::env::temp_dir().join(format!("vita_litw_{}_{n}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    let f = d.join("t.sv");
    std::fs::write(&f, src).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_vita"))
        .arg(f.to_str().unwrap())
        .current_dir(&d)
        .output()
        .expect("run vita");
    (
        String::from_utf8_lossy(&out.stderr).into_owned(),
        out.status.code(),
    )
}

#[test]
fn plain_decimal_value_and_bits_match_iverilog() {
    // boundaries: 2^31-1 (32b), 2^31 (33b), 2^32-1 (33b), 2^32 (34b), 2^33 (35b).
    let out = run("module t; initial begin\n\
         $display(\"%0d %0d\", 2147483647, $bits(2147483647));\n\
         $display(\"%0d %0d\", 2147483648, $bits(2147483648));\n\
         $display(\"%0d %0d\", 4294967295, $bits(4294967295));\n\
         $display(\"%0d %0d\", 4294967296, $bits(4294967296));\n\
         $display(\"%0d %0d\", 8589934592, $bits(8589934592));\n\
         $display(\"%0d %0d\", 42, $bits(42));\n\
         $finish; end endmodule\n");
    assert_eq!(
        out,
        "2147483647 32\n2147483648 33\n4294967295 33\n4294967296 34\n8589934592 35\n42 32\n"
    );
}

#[test]
fn unsized_literal_width_feeds_expression_context() {
    // With truncation these were wrong: 2^32>1 was 0, 2^32>>>1 was 0.
    let out = run("module t; initial begin\n\
         $display(\"%0d\", (4294967296 > 1));\n\
         $display(\"%0d\", 4294967296 >>> 1);\n\
         $finish; end endmodule\n");
    assert_eq!(out, "1\n2147483648\n");
}

#[test]
fn based_decimal_signed_vs_unsigned_width() {
    // 'd (unsigned): 2^31 fits in 32, 2^32 needs 33.  'sd (signed): 2^31 needs 33.
    let out = run("module t; initial begin\n\
         $display(\"%0d %0d\", 'd2147483648, $bits('d2147483648));\n\
         $display(\"%0d %0d\", 'd4294967296, $bits('d4294967296));\n\
         $display(\"%0d %0d\", 'sd2147483648, $bits('sd2147483648));\n\
         $finish; end endmodule\n");
    assert_eq!(out, "2147483648 32\n4294967296 33\n2147483648 33\n");
}

#[test]
fn based_hex_uses_digit_span() {
    // h/b/o width = digit span: 8 hex digits = 32, 9 = 36 (NOT the value MSB 33).
    let out = run("module t; initial begin\n\
         $display(\"%0d %0d\", 'hFFFFFFFF, $bits('hFFFFFFFF));\n\
         $display(\"%0d %0d\", 'h1FFFFFFFF, $bits('h1FFFFFFFF));\n\
         $display(\"%0d %0d\", 'sh1FFFFFFFF, $bits('sh1FFFFFFFF));\n\
         $finish; end endmodule\n");
    assert_eq!(out, "4294967295 32\n8589934591 36\n8589934591 36\n");
}

#[test]
fn oversized_literal_width_is_capped_loud() {
    // P0-10 robustness: now that unsized widths are real, cap them like declared
    // nets (MAX_NET_WIDTH = 1<<20). A literal wider than the cap is rejected loud
    // (E3009), never interned as a giant const. A wide-but-under-cap literal works.
    let (err, code) = run_err(
        "module t; initial begin\n\
         $display(\"%0d\", 1100000'h1);\n\
         #1 $finish; end endmodule\n",
    );
    assert_eq!(
        code,
        Some(1),
        "must reject over-cap literal; stderr:\n{err}"
    );
    assert!(err.contains("VITA-E3009"), "E3009 expected:\n{err}");

    // 1024-bit literal (well under cap) elaborates fine.
    let out =
        run("module t; initial begin $display(\"%0d\", $bits(1024'h1)); $finish; end endmodule\n");
    assert_eq!(out, "1024\n");
}

#[test]
fn small_literals_unchanged() {
    // Regression: ordinary literals stay 32-bit (pre-P0-10 byte-identical).
    let out = run("module t; initial begin\n\
         $display(\"%0d %0d %0d\", $bits(0), $bits(42), $bits(2147483647));\n\
         $display(\"%0d %0d\", $bits('hFF), $bits('hFFFFFFFF));\n\
         $finish; end endmodule\n");
    assert_eq!(out, "32 32 32\n32 32\n");
}
