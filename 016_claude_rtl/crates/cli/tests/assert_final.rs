//! `assert final (expr) [action]` — a FINAL deferred immediate assertion (IEEE
//! 1800-2017 §16.4). A deferred assertion is evaluated WHEN REACHED (like a simple
//! immediate assertion) but its pass/fail report is "matured" in a later region —
//! the Reactive region for `final`, the Observed region for `#0` — so transient
//! intra-time-step glitches are filtered out.
//!
//! vita has no Observed/Reactive-region maturation (assertions evaluate inline in
//! the Active region), so `assert final` is approximated as evaluate-when-reached,
//! i.e. it desugars to the SAME `Stmt::If` as a simple immediate `assert`. This is
//! exact for a condition that is stable when the statement executes (the common
//! case) and a documented hand-IEEE approximation under an intra-step glitch.
//! iverilog 13.0 rejects deferred assertions outright ("Deferred assertions are not
//! supported") → NULL oracle, hand-IEEE. The `#0` (Observed deferred) form stays a
//! loud parse error (see assert_hash0_is_loud).
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn run(src: &str) -> (String, String, Option<i32>) {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let d = std::env::temp_dir().join(format!("vita_af_{}_{n}", std::process::id()));
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
        String::from_utf8_lossy(&out.stderr).into_owned(),
        out.status.code(),
    )
}

#[test]
fn assert_final_holds_clean() {
    // x is always 1 → `assert final (x==1)` holds at every posedge → clean exit.
    let (out, err, code) = run("module top;\n\
         reg clk=0; reg x=1;\n\
         always #5 clk=~clk;\n\
         always @(posedge clk) assert final (x == 1);\n\
         initial #20 $finish;\n\
         endmodule\n");
    assert_eq!(
        code,
        Some(0),
        "stable holding final-assert → clean. stderr:\n{err}\nout:\n{out}"
    );
    assert!(!err.contains("VITA-E"), "must not be loud:\n{err}");
}

#[test]
fn assert_final_violation_default_error_fires() {
    // x==0 is false (x=1); no else clause → IEEE default `$error` → exit 1.
    let (out, err, code) = run("module top;\n\
         reg clk=0; reg x=1;\n\
         always #5 clk=~clk;\n\
         always @(posedge clk) assert final (x == 0);\n\
         initial #20 $finish;\n\
         endmodule\n");
    assert_eq!(
        code,
        Some(1),
        "failing final-assert (default $error) must fire. stderr:\n{err}\nout:\n{out}"
    );
    assert!(
        format!("{err}{out}").to_lowercase().contains("assert"),
        "expected an assertion failure:\n{err}\n{out}"
    );
}

#[test]
fn assert_final_custom_fail_action() {
    // Custom else action ($display, not $error) → prints, no error exit.
    let (out, err, code) = run("module top;\n\
         reg clk=0; reg x=1;\n\
         always #5 clk=~clk;\n\
         always @(posedge clk) assert final (x == 0) else $display(\"FAIL t=%0t\", $time);\n\
         initial #12 $finish;\n\
         endmodule\n");
    assert_eq!(
        code,
        Some(0),
        "custom $display fail action → no error exit. stderr:\n{err}\nout:\n{out}"
    );
    assert!(
        out.contains("FAIL"),
        "the else action must run. out:\n{out}\nerr:\n{err}"
    );
}

#[test]
fn assert_final_pass_and_fail_actions() {
    // `assert final (c) pass; else fail;` — pass action runs when the condition holds.
    let (out, err, code) = run("module top;\n\
         reg clk=0; reg x=1;\n\
         always #5 clk=~clk;\n\
         always @(posedge clk) assert final (x == 1) $display(\"PASS\"); else $display(\"FAIL\");\n\
         initial #7 $finish;\n\
         endmodule\n");
    assert_eq!(
        code,
        Some(0),
        "pass action path → clean. stderr:\n{err}\nout:\n{out}"
    );
    assert!(
        out.contains("PASS") && !out.contains("FAIL"),
        "pass action runs, fail does not. out:\n{out}"
    );
}

#[test]
fn assert_hash0_is_loud() {
    // The `#0` (Observed deferred) form stays a loud parse error in this subset.
    let (_o, err, code) = run("module top;\n\
         reg clk=0, a=0; always #5 clk=~clk;\n\
         always @(posedge clk) assert #0 (a);\n\
         initial #10 $finish;\n\
         endmodule\n");
    assert_eq!(code, Some(1), "`assert #0` must be loud. {err}");
    assert!(err.contains("VITA-E"), "{err}");
}

#[test]
fn assert_final_runs_deterministically() {
    let src = "module top;\n\
         reg clk=0; reg x=1;\n\
         always #5 clk=~clk;\n\
         always @(posedge clk) assert final (x == 1);\n\
         initial #20 $finish;\n\
         endmodule\n";
    let (o1, e1, c1) = run(src);
    let (o2, e2, c2) = run(src);
    assert_eq!((o1, e1, c1), (o2, e2, c2), "must be deterministic");
}
