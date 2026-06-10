//! [C3] Perf BASELINE harness — DATA, not a gate (plan/review: "Add a perf harness
//! (DATA, not a gate yet)"). `#[ignore]`d so it NEVER runs in the normal suite and can
//! never fail CI on timing variance; run it explicitly:
//!
//! ```text
//! cargo test -p sim-engine --test perf_baseline -- --ignored --nocapture
//! ```
//!
//! It times a codegen-able-heavy design on BOTH backends. At C2 the bytecode VM
//! DELEGATES expression eval to the SAME kernel the interpreter uses, so it is expected
//! AT-OR-BELOW the interpreter (a compile pass + op-dispatch loop on top of identical
//! eval cost) — this run records that honest structural-milestone baseline and pins the
//! interpreter time that C3 (native value registers, removing the `Value` heap-alloc and
//! eval tree-walk) must beat. It is intentionally NOT an assertion on the ratio.

mod common;

use std::time::Instant;

use common::build;
use diag::{LogEvent, LogSink};
use sim_engine::{simulate, Backend, FinishReason, SimOpts};

/// Discards all output so wall-time reflects the engine, not the sink.
struct NullSink;
impl LogSink for NullSink {
    fn emit(&self, _e: LogEvent) {}
}

/// Best-of-`reps` wall-time (ns) of a full `simulate` on `backend` (min = least noise).
fn time_backend(ir: &sim_ir::SimIr, backend: Backend, reps: u32) -> u128 {
    let sink = NullSink;
    let mut best = u128::MAX;
    for _ in 0..reps {
        let opts = SimOpts {
            backend,
            ..SimOpts::default()
        };
        let t = Instant::now();
        let res = simulate(ir, &sink, opts);
        best = best.min(t.elapsed().as_nanos());
        assert_eq!(
            res.finish_reason,
            FinishReason::Finish,
            "perf design must $finish"
        );
    }
    best
}

/// A datapath dominated by ONE codegen-able `always @(posedge clk)` body running many
/// thousands of cycles, each doing five 64-bit nonblocking assigns with arithmetic /
/// shifts / xor — heavy on both measured hot spots (eval dispatch + `Value` heap-alloc).
/// The clock-driving `initial` is interpreted in BOTH backends (common overhead), so the
/// interp-vs-VM delta isolates the always-body path.
const CODEGEN_HEAVY: &str = "module top;\n\
  reg clk;\n\
  reg [63:0] a, b, c, d, e;\n\
  integer k;\n\
  always @(posedge clk) begin\n\
    a <= a + 64'd3;\n\
    b <= b ^ a;\n\
    c <= c + b;\n\
    d <= (d << 1) | (d >> 63);\n\
    e <= e + d + a;\n\
  end\n\
  initial begin\n\
    clk = 0; a = 1; b = 2; c = 3; d = 4; e = 5;\n\
    for (k = 0; k < 20000; k = k + 1) begin #1 clk = 1; #1 clk = 0; end\n\
    $finish;\n\
  end\n\
endmodule";

/// EVAL-dominated: one codegen-able `always @(posedge clk)` body with a heavy inner
/// `for` loop (a Branch back-edge — all inside ONE activation, no suspension), driven by
/// only a few hundred clock edges. Each clock runs thousands of 64-bit arithmetic /
/// shift / xor evals, so wall-time is dominated by the eval + `Value`-alloc path (NOT the
/// scheduler/clock churn that swamps `CODEGEN_HEAVY`) — this is the case the `Value`
/// inline-storage change (and later native eval) is meant to move.
const EVAL_HEAVY: &str = "module top;\n\
  reg clk;\n\
  reg [63:0] acc;\n\
  integer i;\n\
  integer j;\n\
  always @(posedge clk) begin\n\
    for (i = 0; i < 3000; i = i + 1) begin\n\
      acc = acc + (acc << 1) + 64'd7;\n\
      acc = acc ^ (acc >> 3);\n\
    end\n\
  end\n\
  initial begin\n\
    clk = 0; acc = 1;\n\
    for (j = 0; j < 200; j = j + 1) begin #1 clk = 1; #1 clk = 0; end\n\
    $finish;\n\
  end\n\
endmodule";

/// EXPRESSION-bound: a deep operator chain (16 `acc` reads + adds) per statement, so
/// the per-statement EVAL cost dwarfs the fixed net-write/loop/scheduling cost. This is
/// the case `EVAL_HEAVY` (only ~3 ops/stmt) under-represents — and the one native-eval
/// actually moves. Measured scaling law (release, 1M statements, K = ops/stmt):
/// `t ≈ 0.39 s (fixed) + 0.058 s × K`, with the per-operand 58 ns being ~98% Value-
/// construct + `eval_ctx` dispatch overhead (net-read ≈ literal; irreducible u64 ALU
/// ≈ 1 ns). ⇒ eval is 55 % of runtime at K=8, 70 % at K=16, 82 % at K=32. Realistic
/// expression-bound RTL (wide ALUs, CRC/crypto datapaths, deep combinational cones)
/// lives in this regime; clock/scheduler-bound designs (see `CODEGEN_HEAVY`) do not.
///
/// [C4-lite] With the native-eval VM fast path (`native_eval`) live, the bytecode VM
/// now runs this body's `+` chain on native u64 registers instead of delegating each
/// operator to `eval_ctx`: measured **VM ≈ 0.42x interpreter** here (was 0.92x at C2 —
/// statement compilation alone was nearly useless for an expression-bound body), i.e.
/// ~2.3x on the VM path, realizing the "expression-bound ~2-3x" prediction. `EVAL_HEAVY`
/// (mixed) improves to ~0.77x; `CODEGEN_HEAVY` (scheduler-bound) stays ~0.94x (eval is
/// not its bottleneck — native-eval correctly does not help there).
const EXPR_HEAVY: &str = "module top;\n\
  reg clk;\n\
  reg [63:0] acc;\n\
  integer i;\n\
  integer j;\n\
  always @(posedge clk) begin\n\
    for (i = 0; i < 10000; i = i + 1) begin\n\
      acc = acc + acc + acc + acc + acc + acc + acc + acc\n\
          + acc + acc + acc + acc + acc + acc + acc + acc + 64'd1;\n\
    end\n\
  end\n\
  initial begin\n\
    clk = 0; acc = 1;\n\
    for (j = 0; j < 100; j = j + 1) begin #1 clk = 1; #1 clk = 0; end\n\
    $finish;\n\
  end\n\
endmodule";

fn report(name: &str, src: &str, reps: u32) {
    let ir = build(src);
    let interp = time_backend(&ir, Backend::Interpreter, reps);
    let vm = time_backend(&ir, Backend::Bytecode, reps);
    println!("\n[C3 perf] {name} (best-of-{reps}):");
    println!("  interpreter : {:>8.3} ms", interp as f64 / 1e6);
    println!(
        "  bytecode VM : {:>8.3} ms   ({:.2}x interpreter)",
        vm as f64 / 1e6,
        vm as f64 / interp as f64
    );
}

#[test]
#[ignore = "perf baseline (DATA, not a gate); run with --ignored --nocapture"]
fn perf_baseline_codegen_heavy() {
    report("codegen-heavy (scheduler-dominated)", CODEGEN_HEAVY, 5);
    report("eval-heavy (eval/Value-dominated)", EVAL_HEAVY, 5);
    report(
        "expr-heavy (deep operator chain; native-eval target)",
        EXPR_HEAVY,
        5,
    );
}

/// [P4-T0b] DUMP-heavy: many VCD value-change records (8 nets toggling every tick
/// for 20k ticks ≈ 320k records) with trivially cheap eval, so wall-time isolates
/// the VCD encode+write path. The no-dump twin is byte-for-byte the same design
/// minus `$dumpfile/$dumpvars` — the delta is the VCD share that a writer THREAD
/// (T1, `--threads ≥2`) can hide. Measures, does not gate.
const DUMP_HEAVY: &str = "module top;\n\
  reg clk;\n\
  reg [63:0] a, b, c, d, e, f, g;\n\
  integer k;\n\
  always @(posedge clk) begin\n\
    a <= a + 64'd1; b <= b + 64'd2; c <= c + 64'd3; d <= d + 64'd5;\n\
    e <= e + 64'd7; f <= f + 64'd11; g <= g + 64'd13;\n\
  end\n\
  initial begin\n\
    DUMP\n\
    clk = 0; a = 0; b = 0; c = 0; d = 0; e = 0; f = 0; g = 0;\n\
    for (k = 0; k < 20000; k = k + 1) begin #1 clk = 1; #1 clk = 0; end\n\
    $finish;\n\
  end\n\
endmodule";

/// Best-of-`reps` wall-time (ns) of `simulate` with an optional real-file VCD dump.
fn time_dump(ir: &sim_ir::SimIr, vcd_path: Option<&std::path::Path>, reps: u32) -> u128 {
    let sink = NullSink;
    let mut best = u128::MAX;
    for _ in 0..reps {
        let opts = SimOpts {
            vcd_path_override: vcd_path.map(|p| p.to_string_lossy().into_owned()),
            ..SimOpts::default()
        };
        let t = Instant::now();
        let res = simulate(ir, &sink, opts);
        best = best.min(t.elapsed().as_nanos());
        assert_eq!(res.finish_reason, FinishReason::Finish);
    }
    best
}

#[test]
#[ignore = "perf data (VCD share measurement for P4-T1); run with --ignored --nocapture"]
fn perf_dump_share() {
    let with_dump_src = DUMP_HEAVY.replace("DUMP", "$dumpfile(\"x.vcd\"); $dumpvars;");
    let no_dump_src = DUMP_HEAVY.replace("DUMP", "");
    let ir_dump = build(&with_dump_src);
    let ir_plain = build(&no_dump_src);
    let path = std::env::temp_dir().join(format!("vita_perf_dump_{}.vcd", std::process::id()));
    let t_dump = time_dump(&ir_dump, Some(&path), 5);
    let t_plain = time_dump(&ir_plain, None, 5);
    let bytes = std::fs::metadata(&path).map(|m| m.len()).unwrap_or(0);
    let _ = std::fs::remove_file(&path);
    let share = 1.0 - (t_plain as f64 / t_dump as f64);
    println!("\n[T0b] dump-heavy VCD share (best-of-5, {bytes} VCD bytes):");
    println!("  with dump   : {:>8.3} ms", t_dump as f64 / 1e6);
    println!("  without dump: {:>8.3} ms", t_plain as f64 / 1e6);
    println!(
        "  VCD share   : {:>7.1}%   (T1 writer-thread ceiling ≤ {:.2}x)",
        share * 100.0,
        1.0 / (1.0 - share)
    );
}
