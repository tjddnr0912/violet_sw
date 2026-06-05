//! [P5] The compiled-vs-interpreter differential gate.
//!
//! For every design in the deterministic P6 corpus, run it on BOTH the interpreter
//! and the bytecode backend from the SAME elaborated `SimIr`, and assert the two
//! runs are byte-identical: stdout, VCD bytes, and the `SimResult` summary
//! (sim_time / finish_reason / exit_class).
//!
//! This is vita-self-contained — it does NOT shell out to iverilog (that oracle
//! lives separately in `differential.rs` and is graceful-skippable). Being a plain
//! `#[test]` in the default suite, it runs under `cargo test --workspace --locked`
//! on every CI leg with no skip → a HARD equivalence gate.
//!
//! STAGE-B STATE: the bytecode backend currently falls back to the interpreter for
//! every body, so this passes by construction today. That is exactly the point —
//! the gate is wired and green BEFORE the kernel refactor (P7a/P7b) and BEFORE any
//! VM lowering (Stage C), so the moment a real VM body diverges in stdout or a
//! single VCD byte, this test goes red and names the offending design.

mod common;

use common::{build, corpus, run_capture};
use sim_engine::Backend;

/// A wide, fixed-seed sweep: every corpus design must produce byte-identical
/// stdout + VCD + summary across the two backends.
#[test]
fn compiled_equals_interpreter_over_corpus() {
    // 72 designs over the 9 templates (8 repeats each, varied params). Fixed seed →
    // reproducible on every OS.
    for d in corpus(0x5EED_F00D, 72) {
        let ir = build(&d.src);
        let (ri, oi, vi) = run_capture(&ir, Backend::Interpreter, &d.name);
        let (rb, ob, vb) = run_capture(&ir, Backend::Bytecode, &d.name);

        assert_eq!(oi, ob, "stdout differs across backends for `{}`", d.name);
        assert_eq!(
            vi,
            vb,
            "VCD bytes differ across backends for `{}` ({} vs {} bytes)",
            d.name,
            vi.as_ref().map_or(0, |v| v.len()),
            vb.as_ref().map_or(0, |v| v.len()),
        );
        assert_eq!(
            ri.sim_time, rb.sim_time,
            "sim_time differs for `{}`",
            d.name
        );
        assert_eq!(
            ri.finish_reason, rb.finish_reason,
            "finish_reason differs for `{}`",
            d.name
        );
        assert_eq!(
            ri.exit_class, rb.exit_class,
            "exit_class differs for `{}`",
            d.name
        );
    }
}

/// Sanity that the gate has TEETH: a design that actually dumps VCD yields non-empty
/// VCD bytes on both backends (so an all-`None` VCD comparison can't vacuously pass).
#[test]
fn gate_actually_compares_vcd_bytes() {
    // The `counter_*` template always `$dumpvars` — find one and assert real bytes.
    let d = corpus(0x5EED_F00D, 8)
        .into_iter()
        .find(|d| d.name.starts_with("counter_"))
        .expect("corpus must contain a counter design");
    let ir = build(&d.src);
    let (_ri, _oi, vi) = run_capture(&ir, Backend::Interpreter, &d.name);
    let (_rb, _ob, vb) = run_capture(&ir, Backend::Bytecode, &d.name);
    let bytes = vi.expect("counter design must emit a VCD");
    assert!(bytes.len() > 32, "VCD should be non-trivial");
    assert!(
        bytes.starts_with(b"$date") || bytes.starts_with(b"$version") || bytes.starts_with(b"$"),
        "VCD should start with a $-keyword preamble"
    );
    assert_eq!(Some(bytes), vb, "counter VCD must match across backends");
}

/// [P9b] A single run MIXES backends. In the Bytecode backend the codegen-able
/// `always @(posedge clk)` body takes the VM path (P9), while the interpreted
/// `initial #1 …` and BOTH continuous assigns fall back to the interpreter — all
/// writing SHARED nets (`a`/`sum`/`q`/`r`). Prove the mixed run is byte-identical
/// (stdout AND VCD) to an all-interpreter run.
///
/// nba_seq ordering is verified IMPLICITLY and with teeth: the always body issues two
/// nonblocking writes (`q <= sum; r <= q;`), so `r` must see the OLD `q` (a one-cycle
/// lag). If a compiled body ever called `schedule_nba` in a different order, `apply_nba`
/// would sort differently, `r` would capture the NEW `q`, and the shared-net values —
/// hence stdout + VCD bytes — would diverge from the interpreter. (Stage B: the VM
/// delegates, so this is byte-identical now; Stage C makes it the live gate.)
#[test]
fn mixed_backend_run_equals_all_interpreter() {
    let src = "module top;\n\
      reg clk;\n\
      reg [7:0] a, b;\n\
      wire [7:0] sum;\n\
      reg [7:0] q, r;\n\
      integer k;\n\
      assign sum = a + b;                                 // cont-assign: interpreted\n\
      always @(posedge clk) begin q <= sum; r <= q; end   // codegen-able: VM path\n\
      initial begin                                       // initial #1: interpreted\n\
        $dumpfile(\"x.vcd\"); $dumpvars(0, top);\n\
        clk = 0; a = 8'd10; b = 8'd20;\n\
        for (k = 0; k < 4; k = k + 1) begin #1 clk = 1; #1 clk = 0; #1 a = a + 1; end\n\
        $display(\"%0d %0d %0d\", sum, q, r); $finish;\n\
      end\n\
    endmodule";
    let ir = build(src);
    let (ri, oi, vi) = run_capture(&ir, Backend::Interpreter, "p9b_mixed");
    let (rb, ob, vb) = run_capture(&ir, Backend::Bytecode, "p9b_mixed");

    assert_eq!(oi, ob, "mixed-backend stdout must equal all-interpreter");
    assert_eq!(vi, vb, "mixed-backend VCD must equal all-interpreter");
    assert!(
        vi.as_ref().is_some_and(|v| v.len() > 32),
        "the mixed design must emit a non-trivial VCD (teeth — not a vacuous None==None)"
    );
    assert_eq!(ri.sim_time, rb.sim_time, "sim_time must match");
    assert_eq!(
        ri.finish_reason, rb.finish_reason,
        "finish_reason must match"
    );
    assert_eq!(ri.exit_class, rb.exit_class, "exit_class must match");
}
