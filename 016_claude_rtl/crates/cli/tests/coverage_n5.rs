//! N5 (MVP): functional coverage — `covergroup NAME; coverpoint EXPR; endgroup`,
//! `cg c = new;`, `c.sample()`, `c.get_coverage()`. iverilog 13.0 REJECTS covergroup
//! entirely, so this is HAND-IEEE: each coverpoint gets auto-bins (min(2^W, 64)); a
//! 64-bit hit-bitmap reg ORs in `1 << (value & 63)` on each sample(); get_coverage()
//! reports `sum($countones(bitmap)) * 100 / sum(num_bins)` (an integer %). Pure IR-0
//! (parser + elaborate bitmap synthesis; AST `.vu` re-pin only, sim-ir/fmt_ver 9
//! unchanged). Every expected % is HAND-COMPUTED from the auto-bin model.
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn run(src: &str) -> (String, Option<i32>) {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let d = std::env::temp_dir().join(format!("vita_cov_{}_{n}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    let f = d.join("t.sv");
    std::fs::write(&f, src).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_vita"))
        .arg(f.to_str().unwrap())
        .current_dir(&d)
        .output()
        .expect("run vita");
    (
        String::from_utf8_lossy(&out.stdout).into_owned(),
        out.status.code(),
    )
}

#[test]
fn single_coverpoint_auto_bins() {
    // x is 4-bit ⇒ 16 auto-bins; values {0,5} hit 2 bins ⇒ 2*100/16 = 12%.
    let (out, _c) = run("module t;\n\
         reg [3:0] x;\n\
         covergroup cg; cp_x: coverpoint x; endgroup\n\
         cg c = new;\n\
         initial begin x=0; c.sample(); x=5; c.sample(); x=5; c.sample();\n\
           $display(\"COV %0d\", c.get_coverage()); end\n\
         endmodule\n");
    assert!(out.contains("COV 12"), "auto-bins coverage:\n{out}");
}

#[test]
fn full_coverage() {
    // x is 2-bit ⇒ 4 bins; sampling all four ⇒ 100%.
    let (out, _c) = run("module t;\n\
         reg [1:0] x;\n\
         covergroup cg; coverpoint x; endgroup\n\
         cg c = new;\n\
         initial begin x=0;c.sample(); x=1;c.sample(); x=2;c.sample(); x=3;c.sample();\n\
           $display(\"F %0d\", c.get_coverage()); end\n\
         endmodule\n");
    assert!(out.contains("F 100"), "full coverage:\n{out}");
}

#[test]
fn quarter_coverage() {
    // a is 3-bit ⇒ 8 bins; {0,1} ⇒ 2*100/8 = 25%.
    let (out, _c) = run("module t;\n\
         reg [2:0] a;\n\
         covergroup cg; coverpoint a; endgroup\n\
         cg c = new;\n\
         initial begin a=0;c.sample(); a=1;c.sample();\n\
           $display(\"Q %0d\", c.get_coverage()); end\n\
         endmodule\n");
    assert!(out.contains("Q 25"), "quarter coverage:\n{out}");
}

#[test]
fn distinct_value_counted_once() {
    // sampling x=1 twice hits ONE bin ⇒ 1*100/4 = 25% (not 50%).
    let (out, _c) = run("module t;\n\
         reg [1:0] x;\n\
         covergroup cg; coverpoint x; endgroup\n\
         cg c = new;\n\
         initial begin x=1; c.sample(); c.sample();\n\
           $display(\"D %0d\", c.get_coverage()); end\n\
         endmodule\n");
    assert!(out.contains("D 25"), "distinct counting:\n{out}");
}

#[test]
fn multi_coverpoint() {
    // two 2-bit coverpoints, each hit 2/4 bins ⇒ (2+2)*100/(4+4) = 50%.
    let (out, _c) = run("module t;\n\
         reg [1:0] a, b;\n\
         covergroup cg; cp_a: coverpoint a; cp_b: coverpoint b; endgroup\n\
         cg c = new;\n\
         initial begin a=0;b=0;c.sample(); a=1;b=1;c.sample();\n\
           $display(\"M %0d\", c.get_coverage()); end\n\
         endmodule\n");
    assert!(out.contains("M 50"), "multi-coverpoint:\n{out}");
}

#[test]
fn sampling_event_header_is_skipped() {
    // a `covergroup cg @(posedge clk);` header is accepted (sampling event not
    // modeled — explicit sample() drives coverage). x=1 once ⇒ 1/4 = 25%.
    let (out, _c) = run("module t;\n\
         reg clk; reg [1:0] x;\n\
         covergroup cg @(posedge clk); coverpoint x; endgroup\n\
         cg c = new;\n\
         initial begin x=1; c.sample();\n\
           $display(\"E %0d\", c.get_coverage()); end\n\
         endmodule\n");
    assert!(out.contains("E 25"), "event-header covergroup:\n{out}");
}

#[test]
fn zero_coverage_before_any_sample() {
    let (out, _c) = run("module t;\n\
         reg [1:0] x;\n\
         covergroup cg; coverpoint x; endgroup\n\
         cg c = new;\n\
         initial $display(\"Z %0d\", c.get_coverage());\n\
         endmodule\n");
    assert!(out.contains("Z 0"), "zero coverage before sample:\n{out}");
}

#[test]
fn unknown_covergroup_type_is_loud() {
    let (out, code) = run("module t;\n\
         nosuch c = new;\n\
         initial $display(\"%0d\", c.get_coverage());\n\
         endmodule\n");
    assert!(
        out.contains("VITA-E") || code == Some(1),
        "unknown covergroup type must be loud: {out} {code:?}"
    );
}
