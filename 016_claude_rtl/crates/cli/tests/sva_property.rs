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
