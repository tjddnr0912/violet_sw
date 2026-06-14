//! SVA concurrent-assertion subset (v8, Phase-3): `assert property(@(clk) a
//! |-> b)` / `|=>`. iverilog 13.0 does NOT support concurrent assertions OR the
//! sampled-value functions ($past/$rose/$fell/$stable) — it rejects them with
//! "sorry: concurrent_assertion_item not supported" / "not defined by any
//! module". So this whole subset is HAND-IEEE pinned (no differential oracle),
//! like assoc arrays / interfaces / string methods. The desugar is a synthesized
//! clocked checker: `assert property(@(clk) a |-> b)` ≡ `always @(clk) if (a &&
//! !b) $error(...)`; `|=>` delays the antecedent one clock via a pending reg.
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn run(src: &str) -> (String, String, Option<i32>) {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let d = std::env::temp_dir().join(format!("vita_sva_{}_{n}", std::process::id()));
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
fn sva_overlap_holds_no_error() {
    // a |-> b holds at every posedge where a is high → no $error, clean exit.
    let (out, err, code) = run("module top;\n\
         reg clk=0, a=0, b=0;\n\
         always #5 clk=~clk;\n\
         initial assert property(@(posedge clk) a |-> b);\n\
         initial begin\n\
           #10 a=1; b=1;\n\
           #20 $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(
        code,
        Some(0),
        "should pass cleanly. stderr:\n{err}\nout:\n{out}"
    );
    assert!(
        !err.to_lowercase().contains("assertion") && !out.to_lowercase().contains("assertion"),
        "no assertion violation expected:\nstderr={err}\nout={out}"
    );
}

#[test]
fn sva_overlap_violation_fires_error() {
    // at t=25 a=1,b=0 → a |-> b is violated → $error (exit class 1).
    let (out, err, code) = run("module top;\n\
         reg clk=0, a=0, b=0;\n\
         always #5 clk=~clk;\n\
         initial assert property(@(posedge clk) a |-> b);\n\
         initial begin\n\
           #10 a=1; b=1;\n\
           #10 a=1; b=0;\n\
           #10 $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(
        code,
        Some(1),
        "a violation must set exit class 1. stderr:\n{err}\nout:\n{out}"
    );
    let blob = format!("{err}{out}").to_lowercase();
    assert!(
        blob.contains("assertion"),
        "a violation diagnostic was expected:\nstderr={err}\nout={out}"
    );
}

#[test]
fn sva_nonoverlap_delays_one_clock() {
    // a |=> b: antecedent at clock T requires consequent at clock T+1. a is high
    // only at t=15; b must hold at t=25. Here b is LOW at t=25 → violation.
    let (out, err, code) = run("module top;\n\
         reg clk=0, a=0, b=0;\n\
         always #5 clk=~clk;\n\
         initial assert property(@(posedge clk) a |=> b);\n\
         initial begin\n\
           #10 a=1; b=0;\n\
           #10 a=0; b=0;\n\
           #10 $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(
        code,
        Some(1),
        "nonoverlap violation must set exit 1. stderr:\n{err}\nout:\n{out}"
    );
    let blob = format!("{err}{out}").to_lowercase();
    assert!(
        blob.contains("assertion"),
        "violation diagnostic expected:\n{err}\n{out}"
    );
}

#[test]
fn sva_nonoverlap_holds_no_error() {
    // a |=> b: a high at t=15, b high at t=25 (next clock) → holds, no $error.
    let (out, err, code) = run("module top;\n\
         reg clk=0, a=0, b=0;\n\
         always #5 clk=~clk;\n\
         initial assert property(@(posedge clk) a |=> b);\n\
         initial begin\n\
           #10 a=1; b=0;\n\
           #10 a=0; b=1;\n\
           #10 $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(
        code,
        Some(0),
        "nonoverlap should hold. stderr:\n{err}\nout:\n{out}"
    );
    assert!(
        !format!("{err}{out}").to_lowercase().contains("assertion"),
        "no violation expected:\n{err}\n{out}"
    );
}

// ── sampled-value functions (slice S3, hand-IEEE) ────────────────────────────
// $past(x)=value 1 clock ago; $rose/$fell=LSB 0→1 / 1→0; $stable=no change.
// Synthesized as prev-registers NBA-updated each clock in the checker process.

#[test]
fn sva_rose_fires_when_consequent_low() {
    // a rises (0→1) seen at the t=15 posedge while b is still 0 → $rose(a) |-> b
    // is violated exactly once.
    let (out, err, code) = run("module top;\n\
         reg clk=0, a=0, b=0;\n\
         always #5 clk=~clk;\n\
         initial assert property(@(posedge clk) $rose(a) |-> b);\n\
         initial begin\n\
           #12 a=1;\n\
           #30 $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(
        code,
        Some(1),
        "rose with low consequent must fire. stderr:\n{err}\nout:\n{out}"
    );
    assert!(
        format!("{err}{out}").to_lowercase().contains("assertion"),
        "{err}\n{out}"
    );
}

#[test]
fn sva_rose_holds_when_consequent_high() {
    // a rises while b is high → $rose(a) |-> b holds, and a STABLE a (no rise)
    // imposes no obligation (vacuous pass) even when b is low later.
    let (out, err, code) = run("module top;\n\
         reg clk=0, a=0, b=0;\n\
         always #5 clk=~clk;\n\
         initial assert property(@(posedge clk) $rose(a) |-> b);\n\
         initial begin\n\
           #12 a=1; b=1;\n\
           #10 b=0;\n\
           #20 $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(
        code,
        Some(0),
        "rose with high consequent holds. stderr:\n{err}\nout:\n{out}"
    );
    assert!(
        !format!("{err}{out}").to_lowercase().contains("assertion"),
        "no violation expected:\n{err}\n{out}"
    );
}

#[test]
fn sva_past_tracks_previous_value() {
    // b must equal a's value one clock earlier. Wired so it HOLDS, proving $past
    // delivers the prior sampled value (not the current one).
    let (out, err, code) = run("module top;\n\
         reg clk=0;\n\
         reg [3:0] a=0, b=0;\n\
         always #5 clk=~clk;\n\
         initial assert property(@(posedge clk) (b == $past(a)));\n\
         initial begin\n\
           a=4'd3; b=4'd0;\n\
           #10 a=4'd7; b=4'd3;\n\
           #10 a=4'd9; b=4'd7;\n\
           #10 $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(
        code,
        Some(0),
        "$past tracking should hold. stderr:\n{err}\nout:\n{out}"
    );
}

#[test]
fn sva_past_mismatch_fires() {
    // b deliberately does NOT equal a's previous value → violation.
    let (out, err, code) = run("module top;\n\
         reg clk=0;\n\
         reg [3:0] a=0, b=0;\n\
         always #5 clk=~clk;\n\
         initial assert property(@(posedge clk) (b == $past(a)));\n\
         initial begin\n\
           a=4'd3; b=4'd0;\n\
           #10 a=4'd7; b=4'd9;\n\
           #20 $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(
        code,
        Some(1),
        "$past mismatch must fire. stderr:\n{err}\nout:\n{out}"
    );
    assert!(
        format!("{err}{out}").to_lowercase().contains("assertion"),
        "{err}\n{out}"
    );
}

#[test]
fn sva_stable_detects_change() {
    // $stable(a) |-> b: when a is unchanged across a clock, b must hold. Make a
    // change so the antecedent is false (vacuous) at the change, then a stable
    // window with b low → violation.
    let (out, err, code) = run("module top;\n\
         reg clk=0, a=0, b=0;\n\
         always #5 clk=~clk;\n\
         initial assert property(@(posedge clk) $stable(a) |-> b);\n\
         initial begin\n\
           a=1; b=1;\n\
           #20 b=0;\n\
           #20 $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(
        code,
        Some(1),
        "stable a with low b must fire. stderr:\n{err}\nout:\n{out}"
    );
    assert!(
        format!("{err}{out}").to_lowercase().contains("assertion"),
        "{err}\n{out}"
    );
}

// ── adversarial-review regressions (2026-06-14) ──────────────────────────────
// NOTE on X/Z (deliberate subset choice, NOT a bug): vitamin treats an X/Z
// antecedent OR consequent as "don't-fire" (a consistent X=don't-know policy).
// Strict IEEE 1800 §16.4.2 reads an X boolean as false (so an X consequent would
// fail), but the subset has no `disable iff`/reset qualification, so strict
// X-fail would make every $past-based assertion fire spuriously on its first
// clock (when $past is X). The lenient policy is documented and intentional.

#[test]
fn sva_nonoverlap_multibit_antecedent_is_boolean() {
    // Review F1: a multi-bit antecedent is a BOOLEAN (any nonzero = true), not its
    // LSB. `a=2'b10` (nonzero) must impose the |=> obligation; b low next clock
    // → violation. (The bug stored a's LSB=0 into the 1-bit pending reg → silent
    // pass.) Fixed by sampling reduction-OR of the antecedent.
    let (out, err, code) = run("module top;\n\
         reg clk=0; reg [1:0] a=0; reg b=0;\n\
         always #5 clk=~clk;\n\
         initial assert property(@(posedge clk) a |=> b);\n\
         initial begin a=2'b10; b=0; #30 $finish; end\n\
         endmodule\n");
    assert_eq!(
        code,
        Some(1),
        "multi-bit |=> antecedent must fire. stderr:\n{err}\nout:\n{out}"
    );
    assert!(
        format!("{err}{out}").to_lowercase().contains("assertion"),
        "{err}\n{out}"
    );
}

#[test]
fn sva_sampled_hierarchical_signal_is_loud() {
    // Review F3: a hierarchical signal in a sampled-value function would be keyed
    // only by its last segment, silently aliasing two distinct signals onto one
    // prev-register. It must be a LOUD error instead.
    let (_out, err, code) = run("module sub; reg [7:0] x = 8'hAA; endmodule\n\
         module top;\n\
         reg clk=0; reg [3:0] x = 4'h3; sub u();\n\
         always #5 clk=~clk;\n\
         initial assert property(@(posedge clk) (x==4'h3) |-> ($past(x) != $past(u.x)));\n\
         initial begin #30 $finish; end\n\
         endmodule\n");
    assert_ne!(
        code,
        Some(0),
        "hierarchical sampled arg must not silently pass. stderr:\n{err}"
    );
    assert!(
        err.to_lowercase().contains("hierarchical"),
        "expected a loud hierarchical-signal diagnostic:\n{err}"
    );
}
