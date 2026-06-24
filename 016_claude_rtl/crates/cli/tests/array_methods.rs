//! N7-REST ⓑ-breadth: SystemVerilog array manipulation methods (IEEE 1800 §7.12).
//!
//! iverilog 13 does NOT support array reduction/ordering/locator methods, so the
//! oracle is hand-IEEE §7.12 + determinism. Reduction results take the ELEMENT
//! type (width/sign); arithmetic wraps at the element width.
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn run_full(src: &str) -> (String, String, bool) {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let path = std::env::temp_dir().join(format!("vita_arrm_{}_{n}.sv", std::process::id()));
    std::fs::write(&path, src).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_vita"))
        .arg(&path)
        .output()
        .expect("failed to run vita");
    let _ = std::fs::remove_file(&path);
    (
        String::from_utf8_lossy(&out.stdout).into_owned(),
        String::from_utf8_lossy(&out.stderr).into_owned(),
        out.status.success(),
    )
}

fn run(src: &str) -> String {
    let (out, err, ok) = run_full(src);
    assert!(ok, "vita must succeed; stderr:\n{err}");
    let mut s = String::new();
    for l in out.lines().filter(|l| !l.starts_with("simulation ended")) {
        s.push_str(l);
        s.push('\n');
    }
    s
}

fn assert_loud_reject(src: &str, what: &str) {
    let (_, err, ok) = run_full(src);
    assert!(!ok, "{what}: must exit non-zero (loud reject)");
    assert!(
        err.contains("E3009") || err.contains("E30"),
        "{what}: stderr must carry an elaborate E-code; got:\n{err}"
    );
}

// ── Reduction methods on a queue ─────────────────────────────────────────────

#[test]
fn queue_sum_product() {
    // int q[$] = {1,2,3,4}: sum=10, product=24.
    let out = run("module top; int q[$]; int s; int p;\n\
         initial begin\n\
           q.push_back(1); q.push_back(2); q.push_back(3); q.push_back(4);\n\
           s = q.sum();\n\
           p = q.product();\n\
           $display(\"s=%0d p=%0d\", s, p);\n\
         end endmodule\n");
    assert_eq!(out, "s=10 p=24\n");
}

#[test]
fn queue_bitwise_reductions() {
    // {1,2,3,4}: and=0, or=7, xor=4.
    let out = run("module top; int q[$]; int a; int o; int x;\n\
         initial begin\n\
           q.push_back(1); q.push_back(2); q.push_back(3); q.push_back(4);\n\
           a = q.and(); o = q.or(); x = q.xor();\n\
           $display(\"a=%0d o=%0d x=%0d\", a, o, x);\n\
         end endmodule\n");
    assert_eq!(out, "a=0 o=7 x=4\n");
}

#[test]
fn dyn_array_sum() {
    // dynamic array new[3] then element writes; sum across.
    let out = run("module top; int d[]; int s;\n\
         initial begin\n\
           d = new[3];\n\
           d[0]=10; d[1]=20; d[2]=30;\n\
           s = d.sum();\n\
           $display(\"s=%0d\", s);\n\
         end endmodule\n");
    assert_eq!(out, "s=60\n");
}

#[test]
fn empty_queue_sum_is_zero() {
    // IEEE leaves the empty case to the accumulator default (0) — documented pin.
    let out = run("module top; int q[$]; int s;\n\
         initial begin s = q.sum(); $display(\"s=%0d\", s); end endmodule\n");
    assert_eq!(out, "s=0\n");
}

#[test]
fn sum_wraps_at_element_width() {
    // byte q[$] = {100, 100}: sum 200 wraps to a signed byte → -56.
    let out = run("module top; byte q[$]; int s;\n\
         initial begin\n\
           q.push_back(100); q.push_back(100);\n\
           s = q.sum();\n\
           $display(\"s=%0d\", s);\n\
         end endmodule\n");
    assert_eq!(out, "s=-56\n");
}

#[test]
fn reduction_on_string_handle_is_loud() {
    // `.sum()` on a string is a kind mismatch — must loud-reject, never silent.
    assert_loud_reject(
        "module top; string s; int r;\n\
         initial begin s = \"hi\"; r = s.sum(); end endmodule\n",
        "sum on string",
    );
}
