//! v5 increment (C)-⑥: dynamic-storage FRONT-END (.sv syntax → engine).
//!
//! End-to-end through the `vita` oneshot binary. Value pins:
//! - dyn array / queue lanes: iverilog -g2012 LIVE oracle (probed 2026-06-11;
//!   exact stdout asserted below).
//! - `q[$-1]` arithmetic: iverilog REJECTS the syntax (its own gap) — hand-IEEE
//!   pin (§7.10: `$` = the last index).
//! - assoc lanes: iverilog rejects assoc declarations outright — hand-IEEE pin
//!   (§7.8/§7.9), same as the engine-layer tests.
//!
//! Loud-reject lanes assert a non-zero exit + an E3009 mention on stderr
//! (the MVP cuts are DELIBERATE: silent-wrong is the one forbidden outcome).
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

/// Write a temp `.sv`, run `vita <file>`, return (stdout, stderr, success).
fn run_vita_full(src: &str) -> (String, String, bool) {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let path = std::env::temp_dir().join(format!("vita_dynfe_{}_{n}.sv", std::process::id()));
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

fn run_vita(src: &str) -> String {
    let (out, err, ok) = run_vita_full(src);
    assert!(ok, "vita must succeed; stderr:\n{err}");
    // Drop vita's own end-of-run epilogue ("simulation ended (…)") so the
    // pins compare the DESIGN's stdout 1:1 with the iverilog oracle.
    let mut s = String::new();
    for l in out.lines().filter(|l| !l.starts_with("simulation ended")) {
        s.push_str(l);
        s.push('\n');
    }
    s
}

/// The design must be REJECTED loudly: non-zero exit + E3009 on stderr.
fn assert_loud_reject(src: &str, what: &str) {
    let (_, err, ok) = run_vita_full(src);
    assert!(!ok, "{what}: must exit non-zero (loud reject)");
    assert!(
        err.contains("E3009") || err.contains("E30"),
        "{what}: stderr must carry an elaborate E-code; got:\n{err}"
    );
}

// ───────────────────────── dyn array (iverilog-pinned) ─────────────────────────

#[test]
fn dyn_array_new_size_index_delete() {
    // Oracle: iverilog live — 3 / 10 20 30 / 5 20 30 / 0.
    let src = r#"
module t;
  integer d [];
  integer e [];
  initial begin
    d = new[3];
    $display("%0d", d.size());
    d[0] = 10; d[1] = 20; d[2] = 30;
    $display("%0d %0d %0d", d[0], d[1], d[2]);
    e = new[5](d);
    $display("%0d %0d %0d", e.size(), e[1], e[2]);
    d.delete();
    $display("%0d", d.size());
  end
endmodule
"#;
    assert_eq!(run_vita(src), "3\n10 20 30\n5 20 30\n0\n");
}

// ───────────────────────── queue (iverilog-pinned) ─────────────────────────

#[test]
fn queue_push_pop_index_size() {
    // Oracle: iverilog live — 3 / 5 10 20 / 20 / 20 2 / 5 1 / 0.
    let src = r#"
module t;
  integer q [$];
  integer x;
  initial begin
    q.push_back(10);
    q.push_back(20);
    q.push_front(5);
    $display("%0d", q.size());
    $display("%0d %0d %0d", q[0], q[1], q[2]);
    $display("%0d", q[$]);
    x = q.pop_back();
    $display("%0d %0d", x, q.size());
    x = q.pop_front();
    $display("%0d %0d", x, q.size());
    q.delete();
    $display("%0d", q.size());
  end
endmodule
"#;
    assert_eq!(run_vita(src), "3\n5 10 20\n20\n20 2\n5 1\n0\n");
}

#[test]
fn dyn_methods_in_expressions() {
    // Oracle: iverilog live — 7 / three. size() participates in arithmetic
    // and conditions like any int expression.
    let src = r#"
module t;
  integer q [$];
  initial begin
    q.push_back(7); q.push_back(8); q.push_back(9);
    $display("%0d", q.size() * 2 + 1);
    if (q.size() == 3) $display("three");
  end
endmodule
"#;
    assert_eq!(run_vita(src), "7\nthree\n");
}

#[test]
fn queue_dollar_arithmetic() {
    // `q[$-1]` — iverilog 13.0 REJECTS the syntax (its own gap); hand-IEEE pin
    // (§7.10.1: `$` = q.size()-1, so `$-1` = the second-to-last element).
    let src = r#"
module t;
  integer q [$];
  initial begin
    q.push_back(7); q.push_back(8); q.push_back(9);
    $display("%0d", q[$]);
    $display("%0d", q[$-1]);
  end
endmodule
"#;
    assert_eq!(run_vita(src), "9\n8\n");
}

#[test]
fn queue_write_at_size_appends() {
    // `q[q.size()] = v` = push_back equivalent (IEEE §7.10.1, legal-SILENT) —
    // iverilog live confirmed at the engine slice (size 1→2).
    let src = r#"
module t;
  integer q [$];
  initial begin
    q[0] = 11;
    q[1] = 22;
    $display("%0d %0d %0d", q.size(), q[0], q[1]);
  end
endmodule
"#;
    assert_eq!(run_vita(src), "2 11 22\n");
}

// ───────────────────────── assoc (hand-IEEE pinned) ─────────────────────────

#[test]
fn assoc_integer_key_roundtrip() {
    // Hand-IEEE (iverilog has no assoc support): negative keys legal,
    // exists 1/0, num counts, delete(k) then delete().
    let src = r#"
module t;
  integer a [integer];
  initial begin
    a[5] = 10;
    a[-3] = 20;
    $display("%0d %0d %0d", a[5], a[-3], a.num());
    $display("%0d %0d", a.exists(5), a.exists(6));
    a.delete(5);
    $display("%0d %0d", a.num(), a.exists(5));
    a.delete();
    $display("%0d", a.num());
  end
endmodule
"#;
    assert_eq!(run_vita(src), "10 20 2\n1 0\n1 0\n0\n");
}

#[test]
fn assoc_time_key_large() {
    // 64-bit `time` keys exercise the beyond-u32 lane through the front-end.
    let src = r#"
module t;
  integer a [time];
  time k;
  initial begin
    k = 64'd1099511627776; // 2^40
    a[k] = 7;
    $display("%0d %0d", a[k], a.size());
  end
endmodule
"#;
    assert_eq!(run_vita(src), "7 1\n");
}

// ───────────────────────── loud-reject lanes (MVP cuts) ─────────────────────────

#[test]
fn pop_outside_direct_rhs_is_loud() {
    // IEEE allows pops anywhere; the MVP pins them to the DIRECT rhs of a
    // blocking assign (engine StmtEffect intercept) — everything else is loud.
    assert_loud_reject(
        r#"
module t;
  integer q [$];
  integer x;
  initial x = q.pop_back() + 1;
endmodule
"#,
        "pop inside arithmetic",
    );
    assert_loud_reject(
        r#"
module t;
  integer q [$];
  integer x;
  initial x <= q.pop_back();
endmodule
"#,
        "pop as NBA rhs",
    );
}

#[test]
fn new_outside_blocking_assign_is_loud() {
    assert_loud_reject(
        r#"
module t;
  integer d [];
  integer x;
  initial x = new[3];
endmodule
"#,
        "new into a non-handle",
    );
}

#[test]
fn dollar_outside_queue_select_is_loud() {
    assert_loud_reject(
        r#"
module t;
  integer x;
  initial x = $;
endmodule
"#,
        "bare $ expression",
    );
}

#[test]
fn wrong_kind_method_is_loud() {
    assert_loud_reject(
        r#"
module t;
  integer d [];
  initial d.push_back(5);
endmodule
"#,
        "push on a dyn array",
    );
    assert_loud_reject(
        r#"
module t;
  integer q [$];
  initial q.delete(0);
endmodule
"#,
        "queue delete(i) (excluded from MVP)",
    );
}

#[test]
fn bounded_queue_and_wildcard_assoc_are_loud() {
    assert_loud_reject(
        r#"
module t;
  integer q [$:4];
  initial q.push_back(1);
endmodule
"#,
        "bounded queue [$:N]",
    );
    let (_, err, ok) = run_vita_full(
        r#"
module t;
  integer a [*];
  initial a[0] = 1;
endmodule
"#,
    );
    assert!(!ok, "wildcard assoc must be rejected; stderr:\n{err}");
}

#[test]
fn handle_misuse_is_loud() {
    // whole-handle copy (`d2 = d`) — IEEE-legal, MVP-deferred → loud.
    assert_loud_reject(
        r#"
module t;
  integer d [];
  integer d2 [];
  initial begin
    d = new[2];
    d2 = d;
  end
endmodule
"#,
        "whole-handle assignment",
    );
    // a handle as a port — excluded. The ANSI header form never parses
    // (E2002), which is the loud surface; the body-decl form is caught by
    // elaborate (E3009 port-dir guard).
    let (_, err, ok) = run_vita_full(
        r#"
module sub(input integer p []);
endmodule
module t;
  integer d [];
  sub s(.p(d));
endmodule
"#,
    );
    assert!(!ok, "dyn handle ANSI port must be rejected");
    assert!(err.contains("VITA-E"), "loud E-code expected; got:\n{err}");
    assert_loud_reject(
        r#"
module sub(p);
  input p;
  integer p [];
endmodule
module t;
  integer d [];
  sub s(.p(d));
endmodule
"#,
        "dyn handle non-ANSI port",
    );
}
