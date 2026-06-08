//! Event scheduler: time wheel + IEEE-1364 stratified region queues
//! (Active → Inactive → NBA), deterministic ready ordering, the delta loop,
//! the infinite-delta cap, NBA sample/apply, and net-change propagation with
//! edge detection.

use std::collections::BTreeMap;
use std::rc::Rc;

use sim_ir::{
    BitPacked, EdgeKind, EdgeTerm, FourState, Lvalue, RegionTag, SensKind, Terminator, WaitCause,
};

use elaborate::{ForkModeTable, JoinMode};

use crate::builtins::{format_args_str, write_out};
use crate::eval::EvalCtx;
use crate::exec::{run_process, Kernel, Step};
use crate::state::{scalar_bit0, SimState};
use crate::value::Value;

/// A schedulable process resume. `proc` is a runtime ACTIVITY id (index into
/// `Scheduler::activities`), NOT a declaration index: top-level processes seed
/// activities `0..nproc` 1:1, and `fork` APPENDS child activities (id ≥ nproc).
/// `tie` is the deterministic intra-region order key (doc-06 tie-break); for a
/// top-level activity it equals the declaration index, for a fork child it is the
/// composite of `(parent_tie, child_idx)` from [`compose_child_tie`].
#[derive(Clone, Copy, PartialEq, Eq)]
pub(crate) struct Ready {
    pub tie: u32,
    pub proc: u32,
    pub block: u32,
}

/// Per-activity private state. Top-level processes are pre-seeded 1:1 with
/// `ir.processes`; fork children are appended (id ≥ `ir.processes.len()`). The
/// arena only ever GROWS — ids are never reused or reindexed — so any `Ready`
/// stored by value in `wheel`/`waiters`/`net_to_edge` stays valid after a later
/// fork appends.
pub(crate) struct Activity {
    /// Index into `ir.processes` for the body/sensitivity TEMPLATE this activity
    /// runs. Multiple activities may share a template (a child runs a different BB
    /// sub-chain of the SAME `body` Vec as its parent).
    pub template: u32,
    /// Deterministic ordering key (top-level: == template; child: composite).
    pub tie: u32,
    /// If this activity is a fork child, the barrier id it reports completion to.
    /// `None` for top-level processes.
    pub join_ref: Option<u32>,
    /// Role bit: is this a spawned fork child? Children never re-arm.
    pub is_child: bool,
    /// Completion-report guard: set true the FIRST time this child reaches its
    /// barrier's join_bb. A second report is an internal error (double-decrement).
    /// Always `false` for top-level activities.
    pub reported: bool,
}

/// One live fork's join barrier.
pub(crate) struct JoinBarrier {
    /// Activity id of the parent that is (or will be) blocked here.
    pub parent: u32,
    /// The join convergence BB (Fork.join), in the parent's template body. Used as
    /// the child-completion sentinel; NEVER fetched as a real block.
    pub join_bb: u32,
    /// Parent's continuation BB (Fork.resume_bb), in the parent's template body.
    pub resume_bb: u32,
    /// Join mode recovered from the elaborate side table.
    pub mode: JoinMode,
    /// Count of children that have NOT yet reached the join.
    pub outstanding: u32,
    /// Has the parent already been resumed past this barrier? (fire-once guard.)
    pub fired: bool,
}

/// A pending nonblocking LHS update: RHS sampled in Active, applied in NBA.
pub(crate) struct NbaUpdate {
    pub seq: u64,
    pub lhs: Lvalue,
    pub sampled: Value,
    /// Per-chunk `(bit-offset, array-word)` sampled in the ACTIVE region when the
    /// `<=` executed (so `a[i] <= x; i = i+1;` / `m[k] <= x;` use the OLD `i`/`k`),
    /// one per `lhs.chunks`.
    pub offsets: Vec<(u32, u32)>,
}

/// One simulation time's three region buckets. Active/Inactive hold process
/// resumes + continuous-assign re-evals; NBA holds sampled updates.
#[derive(Default)]
struct SlotQueues {
    active: Vec<Ready>,
    inactive: Vec<Ready>,
}

/// A process suspended on a Wait condition.
struct Waiter {
    cause: WaitCause,
    ready: Ready,
    /// For an IN-BODY `@(sig)`/`@(*)` (a `WaitCause::Level` from `suspend_on`):
    /// the net values snapshot AT ARM TIME, one per `Level.nets`. The waiter fires
    /// only when a net differs from this snapshot — so a change that completed
    /// BEFORE the wait armed (e.g. the t0 `X→init` settle done by another initial
    /// block before `@(sig)` suspended) does NOT spuriously trigger it. `None` for
    /// a STATIC always/comb sensitivity (those re-fire on any change, by design).
    arm: Option<Vec<BitPacked>>,
}

/// One transport-delay continuous-assign write: `(lhs, value, per-chunk
/// (offset, word))`, applied when the simulation reaches the scheduled tick.
type DelayedWrite = (Lvalue, Value, Vec<(u32, u32)>);

pub(crate) struct Scheduler<'a, 'ir> {
    pub st: &'a mut SimState<'ir>,
    /// Current time's Active/Inactive buckets.
    cur: SlotQueues,
    /// NBA region (applied as a batch when Active+Inactive empty).
    nba: Vec<NbaUpdate>,
    nba_seq: u64,
    /// Future events keyed by absolute tick.
    wheel: BTreeMap<u64, Vec<(RegionTag, Ready)>>,
    /// Processes blocked on Wait conditions.
    waiters: Vec<Waiter>,
    /// net → edge-sensitive process resumes.
    net_to_edge: Vec<Vec<(EdgeKind, Ready)>>,
    /// Per-activity private state. `index == Ready.proc` (activity id). Seeded 1:1
    /// with `ir.processes` at t0; fork appends children (append-only, never reused).
    activities: Vec<Activity>,
    /// Live fork join barriers. `index == JoinBarrier id` (a child's `join_ref`);
    /// append-only, never reused (so no ABA on the barrier id space).
    barriers: Vec<JoinBarrier>,
    /// Join-mode side table from elaborate, keyed `(template, join_bb)`.
    fork_modes: ForkModeTable,
    /// Last RHS value seen per cont-assign — only used by DELAYED `assign #d`
    /// (change detection, so a delayed write schedules once per RHS change).
    last_ca: Vec<Option<Value>>,
    /// Pending transport-delay cont-assign writes, keyed by absolute apply tick.
    delayed_ca: BTreeMap<u64, Vec<DelayedWrite>>,
    delta_count: u64,
    max_deltas: u64,
    time_limit: Option<u64>,
}

/// Why the run ended (scheduler precedence order).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FinishReason {
    Finish,
    Stop,
    Quiescent,
    DeltaLimit,
    Error,
}

impl<'a, 'ir> Scheduler<'a, 'ir> {
    pub fn new(
        st: &'a mut SimState<'ir>,
        max_deltas: u64,
        time_limit: Option<u64>,
        fork_modes: ForkModeTable,
    ) -> Self {
        let nnets = st.nets.len();
        let nca = st.ir.cont_assigns.len();
        Scheduler {
            st,
            cur: SlotQueues::default(),
            nba: Vec::new(),
            nba_seq: 0,
            wheel: BTreeMap::new(),
            waiters: Vec::new(),
            net_to_edge: vec![Vec::new(); nnets],
            activities: Vec::new(),
            barriers: Vec::new(),
            fork_modes,
            last_ca: vec![None; nca],
            delayed_ca: BTreeMap::new(),
            delta_count: 0,
            max_deltas,
            time_limit,
        }
    }

    // ── t0 init ──────────────────────────────────────────────────────────

    /// Settle continuous assigns to a fixpoint, re-evaluating every cont-assign in
    /// declaration order until no net changes. `None` ⇒ could not converge within
    /// the delta budget (a cont-assign oscillator) — the caller MUST stop the run,
    /// else an unbounded `assign`-only loop would spin `max_deltas` iters on EVERY
    /// outer delta and the outer `DeltaLimit` would never fire (cur.active stays
    /// empty). `Some(changed)` ⇒ converged; `changed` is whether ANY net moved, so
    /// the caller can run edge/level propagation on the cont-assign-driven nets
    /// (e.g. a port-bound clock `child.clk = parent.c` whose posedge must reach the
    /// child's `always @(posedge clk)`). One delta budget per time-step (doc-06).
    #[must_use]
    pub fn settle_cont_assigns(&mut self) -> Option<bool> {
        let mut any = false;
        loop {
            let mut changed = false;
            for ci in 0..self.st.ir.cont_assigns.len() {
                if self.st.ir.cont_assigns[ci].delay.is_some() {
                    continue; // a delayed `assign #d` is scheduled below, not now
                }
                let ca_rhs = self.st.ir.cont_assigns[ci].rhs;
                let lhs = self.st.ir.cont_assigns[ci].lhs.clone();
                let v = self.eval_for_lvalue(&lhs, ca_rhs); // CONTEXT-SIZED to lhs width
                let offs = self.resolve_lvalue_offsets(&lhs); // dynamic index NOW (settle time)
                changed |= self.st.write_lvalue(&lhs, v, &offs);
            }
            if !changed {
                break;
            }
            any = true;
            self.delta_count += 1;
            if self.delta_count > self.max_deltas {
                self.fatal_delta_limit();
                return None;
            }
        }
        // Delayed `assign #d y = rhs`: the zero-delay fixpoint has settled, so the
        // RHS is stable. On each RHS-value CHANGE, schedule a TRANSPORT-delay write
        // of the new value at `now + d` (inertial pulse-filtering is a v1
        // simplification; the value at the delayed time is correct).
        for ci in 0..self.st.ir.cont_assigns.len() {
            let Some(d) = self.st.ir.cont_assigns[ci].delay else {
                continue;
            };
            let ca_rhs = self.st.ir.cont_assigns[ci].rhs;
            let lhs = self.st.ir.cont_assigns[ci].lhs.clone();
            let v = self.eval_for_lvalue(&lhs, ca_rhs);
            if self.last_ca[ci].as_ref() == Some(&v) {
                continue; // RHS unchanged → no new scheduled write
            }
            self.last_ca[ci] = Some(v.clone());
            let offs = self.resolve_lvalue_offsets(&lhs);
            let tick = self.st.now + d as u64;
            self.delayed_ca
                .entry(tick)
                .or_default()
                .push((lhs, v, offs));
        }
        Some(any)
    }

    /// Arm processes at t0 per Verilog initial/always semantics.
    pub fn arm_processes(&mut self) {
        // Pre-seed top-level activities 1:1 with process declarations. `tie ==
        // template == declaration index` so existing single-process ordering is
        // byte-identical to before the activity-id refactor.
        self.activities = (0..self.st.ir.processes.len() as u32)
            .map(|pi| Activity {
                template: pi,
                tie: pi,
                join_ref: None,
                is_child: false,
                reported: false,
            })
            .collect();

        // TOTAL-OR-FATAL mode gate: every `Terminator::Fork` in every body MUST
        // have a matching `(template, join_bb)` entry in `fork_modes`. A miss means
        // a keying mismatch / lost sidecar — abort loudly at t0, never run with a
        // fabricated default that would silently miscompile join_any/join_none.
        for (proc_id, p) in self.st.ir.processes.iter().enumerate() {
            for blk in &p.body {
                if let Terminator::Fork { join, .. } = &blk.term {
                    assert!(
                        self.fork_modes.contains_key(&(proc_id as u32, *join)),
                        "internal error: Fork in process {proc_id} join_bb {join} has \
                         no ForkModeTable entry (lost/stale mode sidecar?)"
                    );
                }
            }
        }

        for aid in 0..self.activities.len() as u32 {
            let tmpl = self.activities[aid as usize].template as usize;
            let tie = self.activities[aid as usize].tie;
            let entry = self.st.ir.processes[tmpl].entry;
            let ready = Ready {
                tie,
                proc: aid,
                block: entry,
            };
            match self.st.ir.processes[tmpl].sensitivity.kind {
                // initial + combinational/latch blocks run at t0.
                SensKind::Initial | SensKind::Comb | SensKind::Latch => {
                    push_sorted(&mut self.cur.active, ready);
                }
                // edge / level blocks wait for the first event (no t0 run).
                SensKind::Edge | SensKind::Level => self.arm_sensitivity(aid),
            }
        }
    }

    /// Register an always block's static sensitivity as waiters / edge map. `pi`
    /// is an ACTIVITY id; the body/sensitivity is resolved through its template.
    /// Only ever called for TOP-LEVEL activities (children have no static
    /// sensitivity — they run a sub-chain of their template body).
    fn arm_sensitivity(&mut self, pi: u32) {
        let tmpl = self.activities[pi as usize].template as usize;
        let tie = self.activities[pi as usize].tie;
        let p = &self.st.ir.processes[tmpl];
        let entry = p.entry;
        let ready = Ready {
            tie,
            proc: pi,
            block: entry,
        };
        match p.sensitivity.kind {
            SensKind::Edge => {
                let edges: Vec<EdgeTerm> = p.sensitivity.edges.clone();
                for et in edges {
                    self.net_to_edge[et.net as usize].push((et.kind, ready));
                }
            }
            // Level AND inferred-combinational (`@*`/`always_comb`/`always_latch`,
            // whose `Comb`/`Latch` edges hold the elaborate-inferred read-set):
            // re-fire on ANY change of a read net. Empty edges (e.g. a bare
            // self-timed `always` that re-arms via in-body #/@) register nothing.
            SensKind::Level | SensKind::Comb | SensKind::Latch => {
                let nets: Vec<u32> = p.sensitivity.edges.iter().map(|e| e.net).collect();
                if !nets.is_empty() {
                    self.waiters.push(Waiter {
                        cause: WaitCause::Level { nets },
                        ready,
                        arm: None, // static sensitivity: re-fire on any change
                    });
                }
            }
            _ => {}
        }
    }

    // ── main loop ────────────────────────────────────────────────────────

    /// THE single process-body dispatch seam (P4). The interpreter is the
    /// always-available reference; the Bytecode backend (P0a) routes codegen-able
    /// bodies (the P9 suspend-free allow-list) to the VM and falls back to the
    /// interpreter for the rest. A design routinely MIXES the two — e.g. `always_ff` is
    /// codegen-able while its testbench's `initial #1 …` is not (P9b proves the mix is
    /// byte-identical to all-interpreter). The codegen-ability decision + compile is
    /// memoized per template by `vm_compiled` (decide-once cache).
    fn run_body(&mut self, proc: u32, block: u32) -> Step {
        match self.st.backend {
            crate::Backend::Interpreter => run_process(self, proc, block),
            crate::Backend::Bytecode => {
                let tmpl = self.activity_template(proc) as usize;
                match self.st.vm_compiled(tmpl) {
                    Some(body) => self.vm_run_body(proc, tmpl, block, body),
                    None => run_process(self, proc, block),
                }
            }
        }
    }

    /// Bytecode-VM body entry (Stage C / C2). The P9 predicate (via `vm_compiled`) has
    /// confirmed this body is suspend-free; `body` is its compiled form, handed in as an
    /// owned `Rc` so this `&mut self` kernel call cannot alias the cache (§2.3).
    ///
    /// The VM bypasses `run_process` — the SOLE writer of `cur_time_mult` — so the
    /// PROLOGUE sets it from THIS process's module multiplier exactly as exec.rs:80-87
    /// does, before `vm_exec` evaluates any `$time`/`$realtime`. The per-activation
    /// termination guard then lives inside `vm_exec` (mirror of exec.rs:176-180).
    fn vm_run_body(
        &mut self,
        proc: u32,
        tmpl: usize,
        block: u32,
        body: Rc<crate::backend::CompiledBody>,
    ) -> Step {
        self.st.cur_time_mult = self
            .st
            .proc_multipliers
            .get(tmpl)
            .copied()
            .unwrap_or(1)
            .max(1) as u64;
        crate::backend::vm_exec(self, &body, proc, block)
    }

    pub fn run(&mut self) -> FinishReason {
        loop {
            if self.st.finished {
                return self.finish_kind();
            }
            // Drain the current time to a stable point.
            self.delta_count = 0;
            loop {
                // ACTIVE: continuous assigns settle, then drain processes.
                match self.settle_cont_assigns() {
                    None => return FinishReason::DeltaLimit, // cont-assign oscillator
                    // A settle that moved nets may have produced an EDGE on a
                    // cont-assign-driven net (a port-bound clock). Run change
                    // propagation so those edges/level-waiters fire before we
                    // decide the timestep is stable.
                    Some(true) => self.propagate_changes(),
                    Some(false) => {}
                }
                if !self.cur.active.is_empty() {
                    let batch = std::mem::take(&mut self.cur.active);
                    for r in batch {
                        if self.st.finished {
                            return self.finish_kind();
                        }
                        match self.run_body(r.proc, r.block) {
                            Step::Finish => {
                                self.st.finished = true;
                                return FinishReason::Finish;
                            }
                            Step::Stop => {
                                self.st.finished = true;
                                return FinishReason::Stop;
                            }
                            Step::Fatal => {
                                self.st.finished = true;
                                self.st.had_fatal = true;
                                return FinishReason::Error;
                            }
                            Step::Suspended | Step::Done => {}
                        }
                    }
                    self.propagate_changes();
                    self.delta_count += 1;
                    if self.delta_count > self.max_deltas {
                        self.fatal_delta_limit();
                        return FinishReason::DeltaLimit;
                    }
                    continue;
                }
                // INACTIVE (#0): promote to Active.
                if !self.cur.inactive.is_empty() {
                    self.cur.active = std::mem::take(&mut self.cur.inactive);
                    self.delta_count += 1;
                    if self.delta_count > self.max_deltas {
                        self.fatal_delta_limit();
                        return FinishReason::DeltaLimit;
                    }
                    continue;
                }
                // NBA: apply the sampled batch.
                if !self.nba.is_empty() {
                    self.apply_nba();
                    self.propagate_changes();
                    self.delta_count += 1;
                    if self.delta_count > self.max_deltas {
                        self.fatal_delta_limit();
                        return FinishReason::DeltaLimit;
                    }
                    continue;
                }
                break; // time-step stable
            }

            // POSTPONED REGION (IEEE 1364-2005 §5.4): now == settled time, all
            // region buckets (Active/Inactive/NBA) empty, cont-assigns at
            // fixpoint, time NOT yet advanced. Reads settled `cur` net values.
            // Drain strobes (call order) then the monitor (print-on-change).
            self.flush_postponed();

            // Advance time to the next scheduled tick — the earliest of a wheel
            // event OR a pending transport-delay cont-assign write.
            let next = match (
                self.wheel.keys().next().copied(),
                self.delayed_ca.keys().next().copied(),
            ) {
                (None, None) => return FinishReason::Quiescent,
                (Some(a), None) => a,
                (None, Some(b)) => b,
                (Some(a), Some(b)) => a.min(b),
            };
            if let Some(lim) = self.time_limit {
                if next > lim {
                    return FinishReason::Quiescent;
                }
            }
            self.st.now = next;
            self.st.snapshot_prev();
            // Apply transport-delay cont-assign writes due at this tick; propagate
            // so edges/level-waiters on the delayed net fire (these are NET writes,
            // not process resumes, so the loop-top settle would not see them).
            if let Some(writes) = self.delayed_ca.remove(&next) {
                let mut moved = false;
                for (lhs, v, offs) in writes {
                    moved |= self.st.write_lvalue(&lhs, v, &offs);
                }
                if moved {
                    self.propagate_changes();
                }
            }
            let events = self.wheel.remove(&next).unwrap_or_default();
            for (region, ready) in events {
                match region {
                    RegionTag::Inactive => push_sorted(&mut self.cur.inactive, ready),
                    _ => push_sorted(&mut self.cur.active, ready),
                }
            }
            // a fresh time may also need cont-assign settle before draining (loop top).
        }
    }

    fn finish_kind(&self) -> FinishReason {
        if self.st.had_fatal {
            FinishReason::Error
        } else {
            FinishReason::Finish
        }
    }

    // ── postponed region ($strobe FIFO drain + $monitor change-detect) ─────

    /// IEEE 1364-2005 §5.4 postponed region. Called at the settled point of each
    /// timestep (Active/Inactive/NBA empty, cont-assigns at fixpoint, `now` =
    /// settled time, time NOT yet advanced). Read-only w.r.t. net state: it only
    /// EVALUATES ExprIds (reading settled `cur` net values via `NetReader`) and
    /// writes to `self.st.out`. NOTE: this flush has nothing to do with
    /// `prev`/`snapshot_prev` — those are edge-detection state that `run()` rolls
    /// at the *start of the next* timestep (after time advance); the postponed
    /// render reads only the settled `cur` values and is independent of edge state.
    ///
    /// ORDER (frozen, documented for the golden gate): all strobes first in call
    /// order, then the single monitor line. IEEE leaves this tie-break
    /// implementation-defined; vita freezes strobes-then-monitor for byte-stable
    /// 3-OS golden output.
    fn flush_postponed(&mut self) {
        // `$time`/`$realtime` inside a postponed render must scale by the
        // REGISTERING module's multiplier, not the scheduler's live
        // `cur_time_mult` (which now holds the LAST-run process's `M` — a
        // different module under mixed timescales). Each `FmtCapture` carries its
        // own `time_mult`; we drive `cur_time_mult` from it per render and RESTORE
        // the entering value on exit so nothing downstream (e.g. a cont-assign
        // `$time` at the next loop-top settle) observes a render's multiplier.
        let saved_mult = self.st.cur_time_mult;
        // (a) STROBES — drain the FIFO in call order, render NOW (settled values),
        //     print, then CLEAR (one-shot per call: a strobe never repeats next
        //     step unless its statement re-executes and re-registers).
        if !self.st.postponed.strobes.is_empty() {
            // `mem::take` first to end the immutable borrow that `format_args_str`
            // needs against `&self` (mirrors `apply_nba`'s `mem::take(&mut nba)`).
            let batch = std::mem::take(&mut self.st.postponed.strobes);
            for cap in &batch {
                self.st.cur_time_mult = cap.time_mult; // registering module's M
                let mut line = format_args_str(self, cap.fmt, &cap.args);
                line.push('\n');
                write_out(self.st, &line);
            }
            // `batch` dropped here; `self.st.postponed.strobes` is now empty.
        }

        // (b) MONITOR — IEEE 1364-2005 §17.1: reprint whenever any monitored
        //     expression VALUE changes (4-state-aware), NOT when the rendered
        //     string changes. We therefore evaluate the arg ExprIds to a
        //     `Vec<Value>` and compare against the stored baseline with
        //     `Value`'s derived `PartialEq` (exact `(val, unk)` bit-plane
        //     equality). Only when the value list differs (or was never seeded:
        //     establishment / replace) do we render + print and re-seed.
        //
        //     Borrow shape: hoist EVERYTHING out of the `&self.st.postponed`
        //     borrow into locals (copy `enabled`, copy `fmt`, clone `args`,
        //     `take` the previous `last_vals`) and DROP that borrow before any
        //     `&self`-eval / `&mut self.st`-write. No NLL dependence on a binding
        //     surviving across the render — render-then-record, zero overlap.
        //     `Option::take` is used so the old baseline is moved out (not
        //     cloned) and the slot is rewritten unconditionally below.
        let mon = match self.st.postponed.monitor.as_mut() {
            Some(m) if m.enabled => {
                let fmt = m.cap.fmt;
                let args = m.cap.args.clone();
                let tmult = m.cap.time_mult; // monitoring module's M (see (a) above)
                let prev = m.last_vals.take(); // moves baseline out; slot now None
                Some((fmt, args, tmult, prev))
            }
            // disabled (`$monitoroff`) or no monitor established → nothing to do.
            _ => None,
        };
        if let Some((fmt, args, tmult, prev)) = mon {
            if fmt.is_none() && args.is_empty() {
                // No-arg monitor (`$monitor;` → fmt=None, args=[]) prints nothing —
                // not even a bare newline. Guarded so a future bare-`$monitor`
                // lowering cannot silently inject a lone "\n" into golden RTL output
                // (see §7.4). Seed an empty baseline (`[]` == `[]` keeps it silent
                // forever); a zero-expression monitor has no value to track.
                if let Some(m) = self.st.postponed.monitor.as_mut() {
                    m.last_vals = Some(Vec::new());
                }
            } else {
                // Evaluate every monitored expression to a settled 4-state Value,
                // scaling `$time`/`$realtime` by the monitoring module's M.
                // `self.eval` builds `EvalCtx` from `self.st`, reading settled `cur`.
                self.st.cur_time_mult = tmult;
                let cur_vals: Vec<Value> = args.iter().map(|&eid| self.eval(eid)).collect();
                let changed = match &prev {
                    None => true,                  // establishment / replace → print
                    Some(old) => *old != cur_vals, // 4-state value-level change
                };
                if changed {
                    let mut line = format_args_str(self, fmt, &args);
                    line.push('\n');
                    write_out(self.st, &line);
                }
                // Re-seed the baseline with the freshly-evaluated values regardless
                // of whether we printed: an unchanged step must keep the same
                // baseline, and a printed step adopts the new one.
                if let Some(m) = self.st.postponed.monitor.as_mut() {
                    m.last_vals = Some(cur_vals);
                }
            }
        }
        // Restore the entering multiplier (see the save at the top of this fn).
        self.st.cur_time_mult = saved_mult;
    }

    // ── NBA ──────────────────────────────────────────────────────────────

    fn apply_nba(&mut self) {
        let mut batch = std::mem::take(&mut self.nba);
        batch.sort_by_key(|u| u.seq);
        for u in batch {
            self.st.write_lvalue(&u.lhs, u.sampled, &u.offsets);
        }
    }

    // ── change propagation + edge detection ──────────────────────────────

    /// Diff prev→cur for every net; fire static edge-sensitive `always` blocks,
    /// in-body `Wait{Edge}`/`Wait{Level}` waiters; then refresh prev. Dependent
    /// continuous assigns are covered by `settle_cont_assigns` (re-evaluated each
    /// delta), so no explicit re-enqueue is needed here.
    ///
    /// ORDER IS LOAD-BEARING: every edge comparison (static map AND waiters) must
    /// read the PRE-change `prev`, so the prev-refresh is deferred to the very end
    /// of this pass. (A previous version refreshed prev per-net inside the static
    /// loop, which silently masked all in-body `@(edge)` waits — their later
    /// `prev`/`cur` read saw `prev == cur` → no edge.)
    fn propagate_changes(&mut self) {
        let nnets = self.st.nets.len();
        let mut changed_nets: Vec<u32> = Vec::new();
        for i in 0..nnets {
            if self.st.nets[i].cur != self.st.nets[i].prev {
                changed_nets.push(i as u32);
            }
        }
        if changed_nets.is_empty() {
            return;
        }

        // Precompute scalar (bit0) prev→new for each changed net (still pre-refresh).
        let edges: Vec<(u32, FourState, FourState)> = changed_nets
            .iter()
            .map(|&net| {
                let i = net as usize;
                (
                    net,
                    scalar_bit0(&self.st.nets[i].prev),
                    scalar_bit0(&self.st.nets[i].cur),
                )
            })
            .collect();

        // (a) wake statically edge-sensitive `always` processes.
        for &(net, prev, new) in &edges {
            let edge_list = self.net_to_edge[net as usize].clone();
            for (kind, ready) in edge_list {
                if edge_fires(kind, prev, new) {
                    push_sorted(&mut self.cur.active, ready);
                }
            }
        }

        // (b) wake in-body waiters. `wait(expr)` (WaitCause::Expr) RE-CHECKS its
        // predicate against the post-change net values and resumes only when it
        // becomes true — pre-evaluated here because the `retain` closure cannot
        // also borrow `&self` for `truthy`. (Previously Expr fell through `_ =>
        // true` and never woke, so a `false→true` transition hung the process.)
        let expr_now: Vec<bool> = self
            .waiters
            .iter()
            .map(|w| match &w.cause {
                WaitCause::Expr { expr } => self.truthy(*expr),
                _ => false,
            })
            .collect();
        // Pre-compute Level firing (the retain closure cannot also borrow `&self`):
        // an in-body `@(sig)` (arm=Some) fires when a net differs from its ARM-TIME
        // value; a static sensitivity (arm=None) fires on any net change.
        let level_fire: Vec<bool> = self
            .waiters
            .iter()
            .map(|w| match (&w.cause, &w.arm) {
                (WaitCause::Level { nets }, Some(arm)) => nets
                    .iter()
                    .zip(arm)
                    .any(|(&n, av)| self.st.nets[n as usize].cur != *av),
                (WaitCause::Level { nets }, None) => nets.iter().any(|n| changed_nets.contains(n)),
                _ => false,
            })
            .collect();
        let mut woken: Vec<Ready> = Vec::new();
        let mut wi = 0usize;
        self.waiters.retain(|w| {
            let keep = match &w.cause {
                // Level + inferred-comb: fire per the pre-computed arm/any-change test.
                WaitCause::Level { .. } => !level_fire[wi],
                WaitCause::Edge { net, kind } => !edges
                    .iter()
                    .any(|&(en, prev, new)| en == *net && edge_fires(*kind, prev, new)),
                // wait(expr): consume + resume only when the predicate is now true.
                WaitCause::Expr { .. } => !expr_now[wi],
                _ => true,
            };
            if !keep {
                woken.push(w.ready); // re-armed on resume (Level/Expr) or consumed (Edge)
            }
            wi += 1;
            keep
        });
        for r in woken {
            push_sorted(&mut self.cur.active, r);
        }

        // (c) refresh prev LAST, now that every edge observer has run.
        for &net in &changed_nets {
            let i = net as usize;
            let cur = self.st.nets[i].cur.clone();
            self.st.nets[i].prev = cur;
        }
    }

    fn fatal_delta_limit(&mut self) {
        self.st.had_fatal = true;
    }

    // ── expression eval + executor-facing API (called from exec.rs) ──────

    pub(crate) fn eval(&self, eid: u32) -> Value {
        let ctx = EvalCtx {
            ir: self.st.ir,
            nets: self.st,
            now: self.st.now,
            wt: &self.st.wt,
            time_mult: self.st.cur_time_mult,
        };
        ctx.eval(eid)
    }

    pub(crate) fn truthy(&self, eid: u32) -> bool {
        let ctx = EvalCtx {
            ir: self.st.ir,
            nets: self.st,
            now: self.st.now,
            wt: &self.st.wt,
            time_mult: self.st.cur_time_mult,
        };
        ctx.truthy(eid)
    }

    /// Evaluate `rhs` in the context of `lhs`'s width (IEEE assignment rule):
    /// width = max(lhs_width, self_width(rhs)); sign = rhs self-sign (lhs sign
    /// does NOT propagate).
    pub(crate) fn eval_for_lvalue(&self, lhs: &Lvalue, rhs: u32) -> Value {
        let lw = self.st.lvalue_width(lhs);
        let sw = self.st.wt.get(rhs);
        let ctx_w = lw.max(sw.width);
        self.eval_ctx_top(rhs, ctx_w, sw.signed)
    }

    /// Evaluate each LHS chunk's bit-offset expression NOW (read-only EvalCtx),
    /// returning one offset per chunk (0 for a whole-net `None` chunk). The
    /// `&mut self` write path has no EvalCtx, so dynamic indices like `a[i]` are
    /// resolved here at the correct sampling moment. An X/Z or unresolvable index
    /// yields the `u32::MAX` sentinel → `write_chunk` drops the bit (out-of-range
    /// no-op), matching the READ side where `eval_select` returns X for `a[x]`.
    pub(crate) fn resolve_lvalue_offsets(&self, lhs: &Lvalue) -> Vec<(u32, u32)> {
        let ev = |eid: u32| {
            self.eval(eid)
                .to_u64()
                .map(|v| v as u32)
                .unwrap_or(u32::MAX)
        };
        lhs.chunks
            .iter()
            .map(|c| {
                let off = c.offset.map(ev).unwrap_or(0);
                // `word` is an ExprId array index (`mem[k] = …`); resolve NOW.
                let word = c.word.map(ev).unwrap_or(0);
                (off, word)
            })
            .collect()
    }

    /// Run a pre-compiled native expression program against the net table (VM-only
    /// fast path). `self.st` is the same `NetReader` `eval_ctx_top` builds its EvalCtx
    /// over, so a native leaf load reads exactly what the interpreter would.
    pub(crate) fn eval_native(&self, prog: &crate::native_eval::NativeProg) -> Value {
        crate::native_eval::run(prog, self.st)
    }

    /// Build an EvalCtx and run eval_ctx (mirror of the `eval` façade).
    pub(crate) fn eval_ctx_top(&self, eid: u32, ctx_width: u32, ctx_signed: bool) -> Value {
        let ctx = EvalCtx {
            ir: self.st.ir,
            nets: self.st,
            now: self.st.now,
            wt: &self.st.wt,
            time_mult: self.st.cur_time_mult,
        };
        ctx.eval_ctx(eid, ctx_width, ctx_signed)
    }

    pub(crate) fn now(&self) -> u64 {
        self.st.now
    }

    pub(crate) fn max_deltas_guard(&self) -> u64 {
        self.max_deltas
    }

    pub(crate) fn mark_fatal(&mut self) {
        self.st.had_fatal = true;
    }

    pub(crate) fn schedule_resume(&mut self, proc: u32, block: u32, tick: u64, inactive: bool) {
        // `proc` is an activity id; read its deterministic tie (NOT the id) so two
        // sibling children land in distinct-tie wheel slots in declaration order.
        let tie = self.activities[proc as usize].tie;
        let ready = Ready { tie, proc, block };
        if tick == self.st.now {
            if inactive {
                push_sorted(&mut self.cur.inactive, ready);
            } else {
                push_sorted(&mut self.cur.active, ready);
            }
        } else {
            let region = if inactive {
                RegionTag::Inactive
            } else {
                RegionTag::Active
            };
            self.wheel.entry(tick).or_default().push((region, ready));
        }
    }

    /// Suspend a process on an in-body `@(...)`/`wait(...)`. (The `wait(expr)`
    /// already-true short-circuit is handled in the executor.)
    ///
    /// An in-body `Wait{Edge}` is registered ONLY as a `waiter`, NOT in
    /// `net_to_edge`. `waiters` entries are consumed when they fire
    /// (`propagate_changes` `retain`s them out); `net_to_edge` entries are
    /// permanent. Registering in both would leave an orphan `net_to_edge` entry
    /// that re-fires the process on every future edge of that net for the rest of
    /// the sim (resuming a block it already passed) — an unbounded leak and a
    /// correctness bug for any process that loops back through the same wait. The
    /// `waiters` Edge arm in `propagate_changes` performs the exact same edge test.
    pub(crate) fn suspend_on(&mut self, proc: u32, block: u32, cause: WaitCause) {
        // `proc` is an activity id; carry its distinct tie so two siblings waiting
        // on the same event are distinguishable (neither lost nor double-counted).
        let tie = self.activities[proc as usize].tie;
        let ready = Ready { tie, proc, block };
        // Snapshot the watched nets so an in-body `@(sig)` fires on the next change
        // AFTER this point, not on one already applied this delta before it armed.
        let arm = match &cause {
            WaitCause::Level { nets } => Some(
                nets.iter()
                    .map(|&n| self.st.nets[n as usize].cur.clone())
                    .collect(),
            ),
            _ => None,
        };
        self.waiters.push(Waiter { cause, ready, arm });
    }

    pub(crate) fn schedule_nba(&mut self, lhs: Lvalue, sampled: Value) {
        // Sample the dynamic LHS index NOW (Active region), BEFORE the mutable
        // push, so a later same-step write to the index net cannot move the target.
        let offsets = self.resolve_lvalue_offsets(&lhs);
        let seq = self.nba_seq;
        self.nba_seq += 1;
        self.nba.push(NbaUpdate {
            seq,
            lhs,
            sampled,
            offsets,
        });
    }

    /// Re-arm a process after it Returns. The Edge/Level asymmetry is
    /// LOAD-BEARING (verified):
    /// - `SensKind::Edge` registers a *permanent* entry in `net_to_edge` that is
    ///   read-not-consumed on fire (`propagate_changes` clones, never removes).
    ///   Re-pushing it on every Return would duplicate the registration → the
    ///   process fires 2^k times on edge k (wrong results for blocking edge
    ///   bodies + a 2^k termination hazard). So Edge MUST NOT re-arm.
    /// - `SensKind::Level` waiters ARE consumed on fire (`waiters.retain` returns
    ///   `false`), so Level MUST re-arm or it would never wake again — and the
    ///   `infinite_delta_guard_trips` test depends on this re-registration.
    /// - `Initial` is one-shot (dead after its single run).
    pub(crate) fn rearm(&mut self, proc: u32) {
        // Fork children NEVER re-arm: a child's reaching its join is a one-shot
        // completion, routed by the run_process loop-top intercept to
        // on_child_complete. (A child has no static sensitivity of its own anyway.)
        if self.activities[proc as usize].is_child {
            return;
        }
        let tmpl = self.activities[proc as usize].template as usize;
        let kind = self.st.ir.processes[tmpl].sensitivity.kind;
        match kind {
            // permanent net_to_edge entry / one-shot: do NOT re-register.
            SensKind::Edge | SensKind::Initial => {}
            // consumed waiter: must re-register to wake on the next change.
            SensKind::Comb | SensKind::Latch | SensKind::Level => self.arm_sensitivity(proc),
        }
    }

    // ── fork/join support (activity arena + join barriers) ────────────────

    /// Recover a fork's join mode from the elaborate side table. TOTAL-OR-FATAL:
    /// a miss is impossible after the `arm_processes` gate, but we never default to
    /// a blocking join — a fabricated `All` would silently turn a lost-side-channel
    /// `join_none`/`join_any` into a deadlock with no diagnostic. Panic instead.
    pub(crate) fn fork_mode(&self, template: u32, join_bb: u32) -> JoinMode {
        *self
            .fork_modes
            .get(&(template, join_bb))
            .unwrap_or_else(|| {
                panic!(
                    "internal error: no ForkModeTable entry for (template={template}, \
                 join_bb={join_bb}) — mode sidecar lost/stale?"
                )
            })
    }

    /// Accessors the executor's loop-top intercept + body fetch use (the
    /// `activities`/`barriers` fields are private to sched.rs).
    pub(crate) fn activity_template(&self, aid: u32) -> u32 {
        self.activities[aid as usize].template
    }
    pub(crate) fn activity_is_child(&self, aid: u32) -> bool {
        self.activities[aid as usize].is_child
    }
    /// The barrier's completion-sentinel join_bb (for the loop-top intercept).
    pub(crate) fn barrier_join_bb(&self, jr: u32) -> u32 {
        self.barriers[jr as usize].join_bb
    }
    pub(crate) fn activity_join_ref(&self, aid: u32) -> Option<u32> {
        self.activities[aid as usize].join_ref
    }

    /// Debug-only: assert no LIVE barrier (same template) has its join_bb equal to
    /// `bb` for a non-child activity. A non-child fetching a live join_bb would mean
    /// the parent walked the never-executed sentinel — a builder/engine bug.
    #[cfg(debug_assertions)]
    pub(crate) fn assert_not_parent_at_join(&self, aid: u32, bb: u32) {
        if self.activities[aid as usize].is_child {
            return;
        }
        let tmpl = self.activities[aid as usize].template;
        let bad = self.barriers.iter().any(|b| {
            !b.fired && b.join_bb == bb && self.activities[b.parent as usize].template == tmpl
        });
        debug_assert!(
            !bad,
            "parent/top-level activity {aid} fetched a live barrier join_bb sentinel {bb}"
        );
    }

    /// Execute a `Terminator::Fork`: register the barrier, spawn each child as a new
    /// activity (sharing the parent's template, entering at its own child-entry BB),
    /// and either suspend the parent (All/Any with ≥1 child) or fall through to
    /// `resume_bb` (None, or zero children). Returns `Some(resume_bb)` when the
    /// parent continues THIS activation (the executor sets `bb = resume_bb`), or
    /// `None` when the parent suspends on the barrier.
    pub(crate) fn exec_fork(
        &mut self,
        parent_aid: u32,
        children: &[u32],
        join: u32,
        resume_bb: u32,
    ) -> Option<u32> {
        let parent_tmpl = self.activities[parent_aid as usize].template;
        let mode = self.fork_mode(parent_tmpl, join); // total-or-fatal; never defaults

        // Register the barrier (append-only id space → no ABA).
        let join_ref = self.barriers.len() as u32;
        self.barriers.push(JoinBarrier {
            parent: parent_aid,
            join_bb: join,
            resume_bb,
            mode,
            outstanding: children.len() as u32,
            fired: false,
        });

        // Spawn each child as a NEW activity. Deterministic: declaration order ==
        // the order of `children`; each child's tie composes parent.tie + child idx.
        // NOTE: nested fork is an elaborate ERROR, so `parent_tmpl` here is always a
        // TOP-LEVEL process and `parent.tie` a small dense top-level index —
        // compose_child_tie can never overflow or alias (one shift, never chained).
        let parent_tie = self.activities[parent_aid as usize].tie;
        for (child_idx, &child_entry) in children.iter().enumerate() {
            let child_tie = compose_child_tie(parent_tie, child_idx as u32);
            let child_aid = self.activities.len() as u32;
            self.activities.push(Activity {
                template: parent_tmpl,
                tie: child_tie,
                join_ref: Some(join_ref),
                is_child: true,
                reported: false,
            });
            // Make the child runnable NOW (same instant, Active region); push_sorted
            // by the composed tie keeps siblings in declaration order.
            push_sorted(
                &mut self.cur.active,
                Ready {
                    tie: child_tie,
                    proc: child_aid,
                    block: child_entry,
                },
            );
        }

        match mode {
            JoinMode::None => {
                // join_none: parent does NOT block. Mark fired (never resumes via the
                // barrier) and continue at resume_bb THIS instant; children run on as
                // background activities concurrently with the continuation.
                self.barriers[join_ref as usize].fired = true;
                Some(resume_bb)
            }
            JoinMode::All | JoinMode::Any => {
                if children.is_empty() {
                    // fork join / fork join_any with zero children: resume now.
                    self.barriers[join_ref as usize].fired = true;
                    Some(resume_bb)
                } else {
                    // Parent blocks on the join. It holds NO cur/wheel/waiter entry —
                    // it is parked solely by the barrier and re-enqueued by
                    // on_child_complete when the join condition fires.
                    None
                }
            }
        }
    }

    /// A fork child has reached its barrier's join_bb. Decrement and, on the firing
    /// condition for the mode, re-enqueue the parent at `resume_bb` exactly once.
    pub(crate) fn on_child_complete(&mut self, join_ref: u32, child_aid: u32) {
        // Per-child fire-once: a child may reach its join at most once. A second
        // report would under-decrement `outstanding` and fire an All-barrier EARLY.
        debug_assert!(
            !self.activities[child_aid as usize].reported,
            "internal error: child {child_aid} reported completion twice"
        );
        self.activities[child_aid as usize].reported = true;

        let b = &mut self.barriers[join_ref as usize];
        debug_assert!(
            b.outstanding > 0,
            "internal error: barrier {join_ref} outstanding underflow"
        );
        b.outstanding -= 1;
        let fire = match b.mode {
            JoinMode::All => b.outstanding == 0, // last child
            JoinMode::Any => true,               // first child (later guarded by `fired`)
            JoinMode::None => false,             // never (parent already continued)
        };
        if fire && !b.fired {
            b.fired = true;
            let parent = b.parent;
            let resume_bb = b.resume_bb;
            let tie = self.activities[parent as usize].tie;
            // Re-enqueue the parent at resume_bb THIS instant (Active region).
            // Surplus children (join_any) stay live and run to completion; their
            // later on_child_complete sees `fired == true` → no-op.
            push_sorted(
                &mut self.cur.active,
                Ready {
                    tie,
                    proc: parent,
                    block: resume_bb,
                },
            );
        }
    }
}

/// [P7b] `Scheduler` is the interpreter's implementation of the body↔kernel ABI:
/// each method forwards to the inherent method of the same purpose (the `k_*` prefix
/// keeps the trait surface distinct from the inherent one, so there is no shadowing).
/// The statement executor (`exec::compute_effect`/`apply_effect`) drives the
/// interpreter through exactly this surface, so the existing suite already exercises
/// the seam byte-identically — and a Stage-C compiled body will call the same methods.
impl Kernel for Scheduler<'_, '_> {
    fn k_eval_for_lvalue(&self, lhs: &Lvalue, rhs: u32) -> Value {
        self.eval_for_lvalue(lhs, rhs)
    }
    fn k_eval_native(&self, prog: &crate::native_eval::NativeProg) -> Value {
        self.eval_native(prog)
    }
    fn k_resolve_lvalue_offsets(&self, lhs: &Lvalue) -> Vec<(u32, u32)> {
        self.resolve_lvalue_offsets(lhs)
    }
    fn k_write_lvalue(&mut self, lhs: &Lvalue, value: Value, offsets: &[(u32, u32)]) {
        self.st.write_lvalue(lhs, value, offsets);
    }
    fn k_schedule_nba(&mut self, lhs: Lvalue, value: Value) {
        self.schedule_nba(lhs, value);
    }
    fn k_dispatch_systask(
        &mut self,
        which: sim_ir::SysTaskId,
        fmt: Option<u32>,
        args: &[u32],
    ) -> crate::builtins::Ctl {
        crate::builtins::dispatch(self, which, fmt, args)
    }

    // ── terminator / control surface (C1) — pure forwarders ──
    fn k_truthy(&self, eid: u32) -> bool {
        self.truthy(eid)
    }
    fn k_rearm(&mut self, proc: u32) {
        self.rearm(proc);
    }
    fn k_max_deltas(&self) -> u64 {
        self.max_deltas_guard()
    }
    fn k_mark_fatal(&mut self) {
        self.mark_fatal();
    }
}

// ── helpers ──────────────────────────────────────────────────────────────

/// Insert keeping sorted by `tie` (stable; equal ties keep insertion order).
fn push_sorted(q: &mut Vec<Ready>, r: Ready) {
    let pos = q.partition_point(|x| x.tie <= r.tie);
    q.insert(pos, r);
}

/// Child tie = `(parent_tie+1)` in the high 16 bits, child declaration index in
/// the low 16. `parent` is ALWAYS a top-level process (nested fork is an
/// elaborate ERROR), so `parent_tie ∈ [0, nproc)` is a small dense int and the
/// shift is applied EXACTLY ONCE — never chained — so it can never overflow or
/// alias. The `+1` offset makes children sort STRICTLY AFTER their parent for all
/// `parent_tie` (including 0), while preserving relative parent ordering and
/// declaration order among siblings. v1 limits: ≤ 65534 top-level processes,
/// ≤ 65535 children per fork (far above any MVP testbench).
fn compose_child_tie(parent_tie: u32, child_idx: u32) -> u32 {
    ((parent_tie + 1) << 16) | (child_idx & 0xFFFF)
}

fn is_posedge(prev: FourState, new: FourState) -> bool {
    new == FourState::One && prev != FourState::One
}
fn is_negedge(prev: FourState, new: FourState) -> bool {
    new == FourState::Zero && prev != FourState::Zero
}
fn edge_fires(kind: EdgeKind, prev: FourState, new: FourState) -> bool {
    match kind {
        EdgeKind::Posedge => is_posedge(prev, new),
        EdgeKind::Negedge => is_negedge(prev, new),
        EdgeKind::AnyEdge => prev != new,
    }
}
