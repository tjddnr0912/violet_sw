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
use sim_engine::{simulate_capture, Backend, ExitClass, SimOpts, SimResult};

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

// ── C2 targeted teeth: seams the round-robin corpus does NOT exercise ──────────
// The P6 corpus runs every codegen-able body through BOTH backends (byte-identity),
// but with proc-multiplier 1 everywhere and no infinite loops — so the two pieces of
// run_process-only state the VM must reproduce itself (the cur_time_mult PROLOGUE and
// the per-activation termination GUARD, review must-fix #1/#2) are UNTESTED by it.
// These designs add that coverage with teeth.

/// Run `ir` on `backend` with explicit `proc_multipliers` + `max_deltas`, capturing
/// stdout + summary. No VCD — these teeth live in stdout / finish_reason / exit_class.
fn run_opts(
    ir: &sim_ir::SimIr,
    backend: Backend,
    mults: Vec<u32>,
    max_deltas: u64,
) -> (SimResult, String) {
    let opts = SimOpts {
        backend,
        proc_multipliers: mults,
        max_deltas,
        ..SimOpts::default()
    };
    simulate_capture(ir, opts)
}

/// [C2 PROLOGUE teeth] A codegen-able `always @(posedge clk)` body reads `$time`, run
/// under per-process-DISTINCT non-unit multipliers. `$time = now / M` where M is THIS
/// process's multiplier — set by `run_process` for the interpreter and by the VM's
/// `vm_run_body` prologue for the bytecode backend. If the VM dropped the prologue, the
/// always body would render `$time` with whatever multiplier the previously-run
/// (interpreted `initial`) process left in `cur_time_mult` — a DIFFERENT value — and the
/// backends would diverge. Distinct multipliers make the divergence guaranteed,
/// independent of which ProcId the always body received.
#[test]
fn timescale_prologue_equals_across_backends() {
    let src = "module top;\n\
      reg clk;\n\
      reg [31:0] t0;\n\
      always @(posedge clk) t0 = $time;\n\
      initial begin\n\
        clk = 0;\n\
        #5000 clk = 1; #5000 clk = 0;\n\
        #5000 $display(\"%0d\", t0); $finish;\n\
      end\n\
    endmodule";
    let ir = build(src);
    // Distinct, non-unit multiplier per process so a stale cur_time_mult on the VM path
    // can never coincidentally match the correct one.
    let mults: Vec<u32> = (0..ir.processes.len() as u32)
        .map(|i| (i + 1) * 10)
        .collect();
    let (ri, oi) = run_opts(&ir, Backend::Interpreter, mults.clone(), 1_000_000);
    let (rb, ob) = run_opts(&ir, Backend::Bytecode, mults, 1_000_000);
    assert_eq!(
        oi, ob,
        "$time (scaled by per-process multiplier) must match across backends"
    );
    assert_eq!(ri.sim_time, rb.sim_time);
    assert_eq!(ri.finish_reason, rb.finish_reason);
    // Teeth: a scaled, non-zero $time was actually printed (5000/M ∈ {500,250}).
    let v: u64 = oi
        .trim()
        .parse()
        .unwrap_or_else(|_| panic!("expected numeric $time, got {oi:?}"));
    assert!(v > 0, "scaled $time must be non-zero (teeth), got {v}");
}

/// [C2 GUARD teeth] A codegen-able body with a delay-free `forever` loops forever in ONE
/// activation. Both backends must trip the per-activation termination guard at the SAME
/// point and report the same fatal summary — `run_process` does it (exec.rs:176-180) and
/// `vm_exec` mirrors it. If the VM dropped the guard this test would HANG instead of
/// failing, so its mere existence is the teeth; a small `max_deltas` keeps it fast.
#[test]
fn runaway_codegenable_loop_equal_and_fatal() {
    let src = "module top;\n\
      reg [7:0] y;\n\
      initial forever y = y + 1;\n\
    endmodule";
    let ir = build(src);
    let unit = vec![1u32; ir.processes.len()];
    let (ri, oi) = run_opts(&ir, Backend::Interpreter, unit.clone(), 256);
    let (rb, ob) = run_opts(&ir, Backend::Bytecode, unit, 256);
    assert_eq!(oi, ob, "runaway stdout must match");
    assert_eq!(
        ri.finish_reason, rb.finish_reason,
        "finish_reason must match"
    );
    assert_eq!(ri.exit_class, rb.exit_class, "exit_class must match");
    // Teeth: the guard actually fired (fatal class), not a clean exit.
    assert_eq!(
        rb.exit_class,
        ExitClass::Fatal,
        "the per-activation guard must fire on the VM path"
    );
}

/// [C2 / P8 #3 teeth] A codegen-able body runs `a[i] = K; i = i + 1;` — the blocking LHS
/// index must be SAMPLED (`ResolveOff`) before `i` is bumped, so the write lands at the
/// OLD `i`. The compile pass emits ResolveOff-immediately-before-WriteLval and lowers
/// statements in textual order; a reorder would write `a[1]` instead of `a[0]`. Both
/// backends must agree, and the witnessed value pins the sample moment.
#[test]
fn blocking_index_sample_equals_across_backends() {
    let src = "module top;\n\
      reg clk;\n\
      reg [7:0] a [0:3];\n\
      integer i;\n\
      always @(posedge clk) begin a[i] = 8'hAB; i = i + 1; end\n\
      initial begin\n\
        i = 0; a[0] = 0; a[1] = 0; a[2] = 0; a[3] = 0;\n\
        #1 clk = 1; #1 clk = 0;\n\
        #1 $display(\"%0d %0d %0d\", a[0], a[1], i); $finish;\n\
      end\n\
    endmodule";
    let ir = build(src);
    let unit = vec![1u32; ir.processes.len()];
    let (ri, oi) = run_opts(&ir, Backend::Interpreter, unit.clone(), 1_000_000);
    let (rb, ob) = run_opts(&ir, Backend::Bytecode, unit, 1_000_000);
    assert_eq!(oi, ob, "blocking-index stdout must match across backends");
    assert_eq!(ri.finish_reason, rb.finish_reason);
    // Teeth: a[0] got 0xAB (171) via the OLD i=0; a[1] stayed 0; i bumped to 1.
    assert_eq!(oi.trim(), "171 0 1", "a[i]=K must sample i BEFORE i=i+1");
}
