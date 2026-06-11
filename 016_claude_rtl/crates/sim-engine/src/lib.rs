//! sim-engine — event-driven kernel that EXECUTES a frozen `sim_ir::SimIr`.
//!
//! Pipeline position: preprocess → lex → parse → elaborate → sim-ir → **ENGINE**
//! → VCD. v1 entry: [`simulate`] inits the net table from `NetVar.init`, runs the
//! IEEE-1364 stratified scheduler (Active → Inactive → NBA delta loop), evaluates
//! 4-state expressions, drives `vcd-writer` on `$dumpfile`/`$dumpvars`, prints
//! `$display`/`$write`, and stops on `$finish`/`$stop`.
//!
//! DETERMINISM: same `SimIr` → byte-identical VCD + stdout on all 3 OSes. No
//! HashMap iteration ever decides execution order; every ready set is a sorted
//! `Vec` keyed by `tie` = process declaration index; the time wheel is a
//! `BTreeMap`; cont-assigns settle in declaration order; NBA applies in sample
//! (`seq`) order.
//!
//! IMPLEMENTED: fork/join (via `SimOpts.fork_modes`), `$monitor`/`$strobe`
//! postponed-region semantics, real numbers, inlined user task/func, multi-instance
//! hierarchy with hierarchical VCD `$scope`/`$var` names (`SimOpts.net_names`), and
//! per-module timescale scaling of `#delay`/`$time`/`$realtime` (`SimOpts.proc_multipliers`).
//! Arithmetic is a 128-bit lane (unsigned); any operand X/Z poisons the result to X,
//! as does a signed result wider than 64 bits or an unsigned one wider than 128.
//! DEFERRED (Phase-2): `force`/`release`, the full SV 17-region scheduler, full
//! multi-word arithmetic. All three engine-facing side tables ride out-of-band in
//! `SimOpts` and never enter the frozen `SimIr`.

mod backend;
mod builtins;
mod eval;
mod exec;
mod native_eval;
mod sched;
mod state;
mod value;
mod vcd_thread;
mod width;

#[cfg(test)]
mod width_tests;

use std::cell::RefCell;
use std::io::Write;
use std::rc::Rc;

use diag::{LogEvent, LogSink, ProgressEvent, RtlText};
use sim_ir::SimIr;

/// Re-exported from `elaborate` so callers thread the join-mode side table into
/// `SimOpts.fork_modes` without naming the `elaborate` crate directly.
pub use elaborate::{
    AssignRankTable, ForkModeTable, JoinMode, NetNameTable, QueueBoundTable, RadixTable,
    SeverityKind, SeverityTable, Sidecars,
};
pub use sched::FinishReason;

use sched::Scheduler;
use state::SimState;

/// Process exit classification (CLI maps this to a numeric exit code).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExitClass {
    /// Clean: finished/quiescent with no error-or-fatal diagnostics.
    Ok,
    /// At least one Error-severity diagnostic was emitted (sim still ran).
    HadErrors,
    /// A Fatal diagnostic ended the run.
    Fatal,
}

/// Process-body execution backend (P0a). Selected out-of-band via [`SimOpts`];
/// NEVER enters the frozen `sim_ir::SimIr` (schema hash unaffected). The shared
/// net-write and VCD choke point (`state.rs::write_lvalue`/`emit_vcd_change`) stays
/// on the SHARED side across backends, so only process-body *control flow* differs —
/// VCD/stdout bytes cannot diverge in a backend-specific way (enforced by the P5 gate).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum Backend {
    /// Tree-walking interpreter (`exec.rs::run_process`) — the reference semantics.
    #[default]
    Interpreter,
    /// Bytecode VM (P0a, opt-in acceleration). Codegen-able bodies (the P9
    /// suspend-free allow-list) run on the VM; every other body falls back to the
    /// interpreter. STAGE-B STATE: the VM is not yet built, so ALL bodies fall back
    /// — Bytecode is therefore byte-identical to Interpreter today. That equivalence
    /// is exactly what the P5 gate locks as Stage C incrementally moves bodies onto
    /// the VM.
    Bytecode,
}

/// Caller-tunable knobs. All have deterministic, documented defaults.
#[derive(Debug, Clone)]
pub struct SimOpts {
    /// Overrides the `$dumpfile` path (e.g. CLI `-o`). `None` ⇒ use the RTL's
    /// `$dumpfile` argument.
    pub vcd_path_override: Option<String>,
    /// `$timescale` unit string for the VCD preamble (e.g. `"1ns"`).
    pub timescale_unit: String,
    /// VCD `$date` stamp — taken verbatim so output stays deterministic.
    pub vcd_date: String,
    /// Max delta cycles per time-step before the infinite-delta guard fires.
    pub max_deltas: u64,
    /// Hard cap on advanced simulation time (ticks). `None` ⇒ unbounded.
    pub time_limit: Option<u64>,
    /// Join-mode side table from `elaborate::elaborate_with_modes`, keyed
    /// `(template ProcId, join_bb)`. EMPTY for fork-free designs (the default), so
    /// every existing `SimOpts::default()` caller is unaffected. The engine's
    /// fork-mode lookup is total-or-fatal: a `Terminator::Fork` with no matching
    /// entry aborts the run at t0 rather than fabricating a (wrong) mode.
    pub fork_modes: ForkModeTable,
    /// Per-NetId hierarchical name table from `elaborate::elaborate_with_sidecars`.
    /// EMPTY by default (every existing caller unaffected): the VCD writer then
    /// falls back to a flat `top` scope + synthetic `n{i}` names. When populated it
    /// drives real hierarchical `$scope`/`$var` output. Never enters the golden IR.
    pub net_names: NetNameTable,
    /// Per-ProcId time multiplier `M = 10^(unit_exp − global_prec_exp)` from
    /// `elaborate::elaborate_with_timescale`, for `$time`/`$realtime` scaling
    /// (`$time = now / M`). EMPTY ⇒ multiplier 1 (the 1ns/1ns base). Never golden.
    pub proc_multipliers: Vec<u32>,
    /// Process-body execution backend (P0a). Default [`Backend::Interpreter`] so
    /// every existing caller is byte-identical. Rides out-of-band (never enters the
    /// frozen `SimIr`).
    pub backend: Backend,
    /// Severity side table from `elaborate::elaborate_with_timescale`, keyed by
    /// StmtId: marks `$fatal`/`$error`/`$warning`/`$info` statements (lowered as
    /// `SysTaskId::Display`). EMPTY for severity-free designs (the default), so
    /// every existing caller is unaffected. Never enters the golden IR.
    pub severities: SeverityTable,
    /// Default-radix side table (P1-5): StmtId → 2/8/16 for the b/o/h print
    /// variants. EMPTY by default (decimal everywhere). Never enters the IR.
    pub radixes: RadixTable,
    /// Assign-rank side table (§9.3.1): StmtIds of Force/Release stmts that are
    /// procedural `assign`/`deassign` (weak rank — a real force overrides them;
    /// release hands control back). EMPTY by default. Never enters the IR.
    pub assign_ranks: AssignRankTable,
    /// Bounded-queue side table (v6 ③): handle NetId → declared bound N
    /// (`[$:N]`, max size N+1). Any queue op that ends beyond the bound has
    /// its TAIL truncated + W4020 (iverilog live). EMPTY ⇒ all unbounded.
    pub queue_bounds: QueueBoundTable,
    /// Per-ProcId instance path (`"tb.u1"`) for `%m` (P2-11). EMPTY ⇒ `%m`
    /// renders the legacy flat `top`. Never enters the IR.
    pub proc_scopes: Vec<String>,
    /// Worker-thread budget (P4-T1, CLI `--threads`/`-j`). `1` (the default) is
    /// the exact single-thread path; `≥2` moves VCD file writes onto a dedicated
    /// writer thread behind an order-preserving bounded FIFO. CONTRACT: output
    /// (VCD/stdout/exit) is byte-identical for every value — N changes
    /// wall-clock only (enforced by `tests/threads.rs`).
    pub threads: u32,
}

impl Default for SimOpts {
    fn default() -> Self {
        SimOpts {
            vcd_path_override: None,
            timescale_unit: "1ns".to_string(),
            vcd_date: "vitamin-sim".to_string(),
            max_deltas: 1_000_000,
            time_limit: None,
            fork_modes: ForkModeTable::new(),
            net_names: Vec::new(),
            proc_multipliers: Vec::new(),
            backend: Backend::Interpreter,
            severities: SeverityTable::new(),
            radixes: RadixTable::new(),
            assign_ranks: AssignRankTable::new(),
            queue_bounds: QueueBoundTable::new(),
            proc_scopes: Vec::new(),
            threads: 1,
        }
    }
}

/// Outcome of a run. The VCD + stdout are the side effects; this is the summary.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SimResult {
    pub finish_reason: FinishReason,
    pub sim_time: u64,
    pub exit_class: ExitClass,
    pub vcd_path: Option<String>,
}

/// A `Write` sink that forwards RTL text to a `LogSink` as `RtlOutput` events.
/// This is the default `$display` sink so output is captured through `diag`.
/// (v1: `sim_time` is left `None` — threading live time through a `Write`
/// adapter is a minor follow-up; each `$display` is one write.)
struct LogWrite<'a> {
    sink: &'a dyn LogSink,
}

impl<'a> Write for LogWrite<'a> {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        let text = String::from_utf8_lossy(buf).into_owned();
        self.sink.emit(LogEvent::RtlOutput(RtlText {
            text,
            sim_time: None,
        }));
        Ok(buf.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

/// THE entry point. Executes `ir`, driving the VCD file + RTL output through
/// `sink`. `$display`/`$write` text is emitted as `LogEvent::RtlOutput`.
pub fn simulate(ir: &SimIr, sink: &dyn LogSink, opts: SimOpts) -> SimResult {
    // RTL output sink routes $display/$write text through the LogSink.
    let out: Box<dyn Write + '_> = Box::new(LogWrite { sink });

    let mut st = SimState::new(
        ir,
        out,
        sink,
        opts.timescale_unit.clone(),
        opts.vcd_date.clone(),
        opts.vcd_path_override.clone(),
    );
    st.net_names = opts.net_names.clone();
    st.proc_multipliers = opts.proc_multipliers.clone();
    st.backend = opts.backend;
    st.severities = opts.severities.clone();
    st.radixes = opts.radixes.clone();
    st.assign_ranks = opts.assign_ranks.clone();
    st.queue_bounds = opts.queue_bounds.clone();
    st.proc_scopes = opts.proc_scopes.clone();
    st.threads = opts.threads;

    let reason = {
        let mut sched = Scheduler::new(&mut st, opts.max_deltas, opts.time_limit, opts.fork_modes);
        // t0 structural settle. If it can't converge (cont-assign oscillator),
        // stop immediately with DeltaLimit rather than running on a divergent t0.
        if sched.settle_cont_assigns().is_some() {
            sched.arm_processes();
            sched.run()
        } else {
            FinishReason::DeltaLimit
        }
    };

    st.finalize_vcd();

    let exit_class = if st.had_fatal {
        ExitClass::Fatal
    } else if st.had_error {
        ExitClass::HadErrors
    } else {
        ExitClass::Ok
    };

    sink.emit(LogEvent::Progress(ProgressEvent {
        message: format!("simulation ended ({:?}) at time {}", reason, st.now),
    }));

    SimResult {
        finish_reason: reason,
        sim_time: st.now,
        exit_class,
        vcd_path: st.vcd_path.clone(),
    }
}

/// Convenience: run a simulation capturing RTL output into a `String` and the
/// VCD into the file named by `$dumpfile`/`override`. Returns (result, stdout).
/// Primarily for tests + a simple CLI path.
pub fn simulate_capture(ir: &SimIr, opts: SimOpts) -> (SimResult, String) {
    let buf = Rc::new(RefCell::new(String::new()));
    let sink = CaptureSink { buf: buf.clone() };
    let result = simulate(ir, &sink, opts);
    let s = buf.borrow().clone();
    (result, s)
}

struct CaptureSink {
    buf: Rc<RefCell<String>>,
}

impl LogSink for CaptureSink {
    fn emit(&self, event: LogEvent) {
        if let LogEvent::RtlOutput(t) = event {
            self.buf.borrow_mut().push_str(&t.text);
        }
    }
}
