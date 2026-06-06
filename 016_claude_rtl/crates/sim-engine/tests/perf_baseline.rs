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

#[test]
#[ignore = "perf baseline (DATA, not a gate); run with --ignored --nocapture"]
fn perf_baseline_codegen_heavy() {
    let ir = build(CODEGEN_HEAVY);
    let reps = 5;
    let interp = time_backend(&ir, Backend::Interpreter, reps);
    let vm = time_backend(&ir, Backend::Bytecode, reps);
    let ratio = vm as f64 / interp as f64;
    println!("\n[C3 perf baseline] codegen-heavy design, best-of-{reps}:");
    println!("  interpreter : {:>8.3} ms", interp as f64 / 1e6);
    println!(
        "  bytecode VM : {:>8.3} ms   ({:.2}x interpreter)",
        vm as f64 / 1e6,
        ratio
    );
    println!(
        "  => C2 VM is {} the interpreter (expected at-or-below; C3 must beat interp).\n",
        if ratio <= 1.0 { "at/below" } else { "above" }
    );
}
