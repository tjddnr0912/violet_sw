//! SVA-REST. Current scope: `assume property` — in SIMULATION an assumption is
//! VERIFIED exactly like an assertion (IEEE 1800-2017 §16.12; the assert/assume
//! distinction matters only for formal tools), so it reuses the synthesized
//! concurrent-assertion checker. Pure IR-0 (parser routes `assume property` to
//! the same path as `assert property`; no sim-ir / AST shape change).
//!
//! Remaining SVA-REST items (`until`/`implies`/`always`/`s_eventually`,
//! `cover property`, multi-term cross-clock, sequence local var, `let`,
//! `$assertoff/on/kill`) stay loud-reject / deferred — see docs/ROADMAP.md.
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn run(src: &str) -> (String, Option<i32>) {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let d = std::env::temp_dir().join(format!("vita_svar_{}_{n}", std::process::id()));
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
fn assume_property_violation_is_reported() {
    // An assumption violated in simulation IS reported (checked like an assert).
    let (_out, code) = run("module t;\n\
        logic clk=0, a=0, b=0;\n\
        always #5 clk = ~clk;\n\
        assume property(@(posedge clk) a |-> b);\n\
        initial begin #10 a=1; b=1; #10 a=1; b=0; #10 $finish; end\n\
        endmodule\n");
    assert_eq!(
        code,
        Some(1),
        "violated assume must exit 1 (checked like assert)"
    );
}

#[test]
fn assume_property_satisfied_is_clean() {
    // A satisfied assumption produces no violation (exit 0).
    let (out, code) = run("module t;\n\
        logic clk=0, a=0, b=0;\n\
        always #5 clk = ~clk;\n\
        assume property(@(posedge clk) a |-> b);\n\
        initial begin #10 a=1; b=1; #10 a=0; b=0; #10 $finish; end\n\
        endmodule\n");
    assert_eq!(code, Some(0), "satisfied assume exits 0:\n{out}");
}

#[test]
fn procedural_assume_property() {
    // `assume property` inside an initial/always block (procedural placement).
    let (_out, code) = run("module t;\n\
        logic clk=0, a=0, b=0;\n\
        always #5 clk = ~clk;\n\
        initial assume property(@(posedge clk) a |-> b);\n\
        initial begin #10 a=1; b=1; #10 a=1; b=0; #10 $finish; end\n\
        endmodule\n");
    assert_eq!(code, Some(1), "procedural assume violation exits 1");
}
