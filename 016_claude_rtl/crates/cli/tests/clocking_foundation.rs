//! N4 clocking block — FRONT-END FOUNDATION (2026-06-25). The lexer/parser/AST
//! now accept `clocking … endclocking` (§14); the functional lowering (a
//! preponed-region sampler synthesizing holding nets + a marked commit handler)
//! is the pending engine slice, so elaborate HONEST-LOUDs (E3009) — never a
//! silent drop (a dropped clocking block would leave `cb.sig` unresolved and the
//! design silently mis-sampled). These tests pin the foundation: the syntax
//! PARSES (no E2002), and elaboration is cleanly loud (E3009), not silent.
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn run(src: &str) -> (String, String, Option<i32>) {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let d = std::env::temp_dir().join(format!("vita_ckf_{}_{n}", std::process::id()));
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

/// Parses (no E2002 parse error) but is loud at ELABORATE (E3009) — never silent.
fn parses_but_elab_loud(src: &str, ctx: &str) {
    let (out, err, code) = run(src);
    let all = format!("{err}{out}");
    assert_ne!(
        code,
        Some(0),
        "{ctx}: must be loud, not silently pass.\n{all}"
    );
    assert!(
        !all.contains("VITA-E2002"),
        "{ctx}: must PARSE (no E2002 parse error).\n{all}"
    );
    assert!(
        all.contains("VITA-E3009") && all.to_lowercase().contains("clocking"),
        "{ctx}: expected a clean elaborate loud (E3009 clocking).\n{all}"
    );
}

#[test]
fn named_input_clocking_parses_loud_at_elab() {
    parses_but_elab_loud(
        "module t;\n\
         logic clk=0, a=0;\n\
         always #5 clk=~clk;\n\
         clocking cb @(posedge clk); input a; endclocking\n\
         initial begin #100 $finish; end\n\
         endmodule\n",
        "named clocking with one input",
    );
}

#[test]
fn default_clocking_parses_loud_at_elab() {
    parses_but_elab_loud(
        "module t;\n\
         logic clk=0, a=0, b=0;\n\
         always #5 clk=~clk;\n\
         default clocking cb @(posedge clk); input a, b; endclocking\n\
         initial begin #100 $finish; end\n\
         endmodule\n",
        "default clocking, multi-input list",
    );
}

#[test]
fn input_output_with_bind_expr_parses_loud_at_elab() {
    parses_but_elab_loud(
        "module t;\n\
         logic clk=0; logic [7:0] q=0, drv=0;\n\
         always #5 clk=~clk;\n\
         clocking cb @(posedge clk);\n\
           input sampled_q = q;\n\
           output drv;\n\
         endclocking\n\
         initial begin #100 $finish; end\n\
         endmodule\n",
        "input bind-expr + output",
    );
}

#[test]
fn clocking_with_label_and_negedge_parses() {
    parses_but_elab_loud(
        "module t;\n\
         logic clk=0, a=0;\n\
         always #5 clk=~clk;\n\
         clocking cb @(negedge clk); input a; endclocking : cb\n\
         initial begin #100 $finish; end\n\
         endmodule\n",
        "negedge event + `: label`",
    );
}
