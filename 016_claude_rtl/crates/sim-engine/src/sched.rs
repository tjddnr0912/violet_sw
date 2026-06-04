//! Event scheduler: time wheel + IEEE-1364 stratified region queues
//! (Active → Inactive → NBA), deterministic ready ordering, the delta loop,
//! the infinite-delta cap, NBA sample/apply, and net-change propagation with
//! edge detection.

use std::collections::BTreeMap;

use sim_ir::{EdgeKind, EdgeTerm, FourState, Lvalue, RegionTag, SensKind, WaitCause};

use crate::eval::EvalCtx;
use crate::exec::{run_process, Step};
use crate::state::{scalar_bit0, SimState};
use crate::value::Value;

/// A schedulable process resume. `tie` = process declaration index → the
/// deterministic intra-region order (doc-06 chosen tie-break).
#[derive(Clone, Copy, PartialEq, Eq)]
pub(crate) struct Ready {
    pub tie: u32,
    pub proc: u32,
    pub block: u32,
}

/// A pending nonblocking LHS update: RHS sampled in Active, applied in NBA.
pub(crate) struct NbaUpdate {
    pub seq: u64,
    pub lhs: Lvalue,
    pub sampled: Value,
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
}

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
    pub fn new(st: &'a mut SimState<'ir>, max_deltas: u64, time_limit: Option<u64>) -> Self {
        let nnets = st.nets.len();
        Scheduler {
            st,
            cur: SlotQueues::default(),
            nba: Vec::new(),
            nba_seq: 0,
            wheel: BTreeMap::new(),
            waiters: Vec::new(),
            net_to_edge: vec![Vec::new(); nnets],
            delta_count: 0,
            max_deltas,
            time_limit,
        }
    }

    // ── t0 init ──────────────────────────────────────────────────────────

    /// Settle continuous assigns to a fixpoint. Re-evaluates every cont-assign in
    /// declaration order until no net changes. Returns `false` if it could not
    /// converge within the delta budget (a cont-assign oscillator) — the caller
    /// MUST stop the run, otherwise an unbounded `assign`-only loop would spin
    /// `max_deltas` iters on EVERY outer delta (effectively `max_deltas²` work)
    /// and the outer `DeltaLimit` would never fire because `cur.active` stays
    /// empty. Sharing one budget keeps the doc-06 contract: one delta budget per
    /// time-step.
    #[must_use]
    pub fn settle_cont_assigns(&mut self) -> bool {
        loop {
            let mut changed = false;
            for ci in 0..self.st.ir.cont_assigns.len() {
                let ca_rhs = self.st.ir.cont_assigns[ci].rhs;
                let lhs = self.st.ir.cont_assigns[ci].lhs.clone();
                let v = self.eval_for_lvalue(&lhs, ca_rhs); // CONTEXT-SIZED to lhs width
                changed |= self.st.write_lvalue(&lhs, v);
            }
            if !changed {
                return true;
            }
            self.delta_count += 1;
            if self.delta_count > self.max_deltas {
                self.fatal_delta_limit();
                return false;
            }
        }
    }

    /// Arm processes at t0 per Verilog initial/always semantics.
    pub fn arm_processes(&mut self) {
        for pi in 0..self.st.ir.processes.len() {
            let p = &self.st.ir.processes[pi];
            let entry = p.entry;
            let ready = Ready {
                tie: pi as u32,
                proc: pi as u32,
                block: entry,
            };
            match p.sensitivity.kind {
                // initial + combinational/latch blocks run at t0.
                SensKind::Initial | SensKind::Comb | SensKind::Latch => {
                    push_sorted(&mut self.cur.active, ready);
                }
                // edge / level blocks wait for the first event (no t0 run).
                SensKind::Edge | SensKind::Level => self.arm_sensitivity(pi as u32),
            }
        }
    }

    /// Register an always block's static sensitivity as waiters / edge map.
    fn arm_sensitivity(&mut self, pi: u32) {
        let p = &self.st.ir.processes[pi as usize];
        let entry = p.entry;
        let ready = Ready {
            tie: pi,
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
            SensKind::Level => {
                let nets: Vec<u32> = p.sensitivity.edges.iter().map(|e| e.net).collect();
                self.waiters.push(Waiter {
                    cause: WaitCause::Level { nets },
                    ready,
                });
            }
            _ => {}
        }
    }

    // ── main loop ────────────────────────────────────────────────────────

    pub fn run(&mut self) -> FinishReason {
        loop {
            if self.st.finished {
                return self.finish_kind();
            }
            // Drain the current time to a stable point.
            self.delta_count = 0;
            loop {
                // ACTIVE: continuous assigns settle, then drain processes.
                if !self.settle_cont_assigns() {
                    return FinishReason::DeltaLimit; // cont-assign oscillator
                }
                if !self.cur.active.is_empty() {
                    let batch = std::mem::take(&mut self.cur.active);
                    for r in batch {
                        if self.st.finished {
                            return self.finish_kind();
                        }
                        match run_process(self, r.proc, r.block) {
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

            // Advance time to the next scheduled tick.
            let next = match self.wheel.keys().next().copied() {
                None => return FinishReason::Quiescent,
                Some(t) => t,
            };
            if let Some(lim) = self.time_limit {
                if next > lim {
                    return FinishReason::Quiescent;
                }
            }
            let events = self.wheel.remove(&next).unwrap();
            self.st.now = next;
            self.st.snapshot_prev();
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

    // ── NBA ──────────────────────────────────────────────────────────────

    fn apply_nba(&mut self) {
        let mut batch = std::mem::take(&mut self.nba);
        batch.sort_by_key(|u| u.seq);
        for u in batch {
            self.st.write_lvalue(&u.lhs, u.sampled);
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

        // (b) wake in-body waiters (Edge consumed-on-fire; Level consumed-on-fire).
        let mut woken: Vec<Ready> = Vec::new();
        self.waiters.retain(|w| match &w.cause {
            WaitCause::Level { nets } => {
                if nets.iter().any(|n| changed_nets.contains(n)) {
                    woken.push(w.ready);
                    false // remove: re-armed on resume
                } else {
                    true
                }
            }
            WaitCause::Edge { net, kind } => {
                if let Some(&(_, prev, new)) = edges.iter().find(|e| e.0 == *net) {
                    if edge_fires(*kind, prev, new) {
                        woken.push(w.ready);
                        return false; // remove: consumed
                    }
                }
                true
            }
            _ => true,
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
        };
        ctx.eval(eid)
    }

    pub(crate) fn truthy(&self, eid: u32) -> bool {
        let ctx = EvalCtx {
            ir: self.st.ir,
            nets: self.st,
            now: self.st.now,
            wt: &self.st.wt,
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

    /// Build an EvalCtx and run eval_ctx (mirror of the `eval` façade).
    pub(crate) fn eval_ctx_top(&self, eid: u32, ctx_width: u32, ctx_signed: bool) -> Value {
        let ctx = EvalCtx {
            ir: self.st.ir,
            nets: self.st,
            now: self.st.now,
            wt: &self.st.wt,
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
        let tie = proc;
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
        let ready = Ready {
            tie: proc,
            proc,
            block,
        };
        self.waiters.push(Waiter { cause, ready });
    }

    pub(crate) fn schedule_nba(&mut self, lhs: Lvalue, sampled: Value) {
        let seq = self.nba_seq;
        self.nba_seq += 1;
        self.nba.push(NbaUpdate { seq, lhs, sampled });
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
        let kind = self.st.ir.processes[proc as usize].sensitivity.kind;
        match kind {
            // permanent net_to_edge entry / one-shot: do NOT re-register.
            SensKind::Edge | SensKind::Initial => {}
            // consumed waiter: must re-register to wake on the next change.
            SensKind::Comb | SensKind::Latch | SensKind::Level => self.arm_sensitivity(proc),
        }
    }
}

// ── helpers ──────────────────────────────────────────────────────────────

/// Insert keeping sorted by `tie` (stable; equal ties keep insertion order).
fn push_sorted(q: &mut Vec<Ready>, r: Ready) {
    let pos = q.partition_point(|x| x.tie <= r.tie);
    q.insert(pos, r);
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
