//! Process executor: the FROZEN basic-block PC state machine. Runs a
//! `Process.body` from a resume block, executing each block's statements then
//! its terminator, suspending on Delay/Wait and completing on Return.
//!
//! Operates on the [`Scheduler`] so a single `&mut` reaches both the net table
//! (`sched.st`) for immediate blocking writes and the scheduler queues for
//! NBA/Delay/Wait scheduling.

use sim_ir::{DelayRegion, Lvalue, Stmt, SysTaskId, Terminator, WaitCause};

use crate::builtins::Ctl;
use crate::sched::Scheduler;
use crate::value::Value;

/// Outcome of one process activation.
pub(crate) enum Step {
    Done,
    Suspended,
    Finish,
    Stop,
    Fatal,
}

/// The body↔kernel ABI seam (P7b): the calls a process body — the tree-walking
/// interpreter OR a Stage-C compiled body — makes to drive the simulation kernel.
/// A READ phase (`k_eval_for_lvalue`/`k_resolve_lvalue_offsets`, no mutation) then a
/// WRITE phase (`k_write_lvalue`/`k_schedule_nba`/`k_dispatch_systask`). The
/// interpreter's statement executor ([`compute_effect`]/[`apply_effect`]) is GENERIC
/// over this trait, so it already runs against the seam — proving the surface is
/// sufficient for a compiled VM to reuse verbatim (the kernel never knows which body
/// drove it; only its control flow differs).
///
/// SCOPE: the STATEMENT-phase ABI for the suspend-free P9 class plus the C1
/// terminator/control surface. Method names are `k_*`-prefixed to stay distinct from
/// `Scheduler`'s inherent methods (the impl just forwards). Suspend / resume
/// (Delay/Wait) and fork are deliberately ABSENT: those bodies stay on the
/// interpreter, which owns the resume-PC state machine (a compiled body runs
/// atomically entry→Return and never suspends — see the P9 predicate).
pub(crate) trait Kernel {
    /// READ: evaluate `rhs` context-sized to `lhs`'s width (IEEE assignment rule).
    fn k_eval_for_lvalue(&self, lhs: &Lvalue, rhs: u32) -> Value;
    /// READ: evaluate a pre-compiled native expression program (VM-only fast path,
    /// [C4-lite]). Byte-identical to `k_eval_for_lvalue` for the bounded subset
    /// `native_eval::try_compile` accepts; the compiler only emits this where it does.
    fn k_eval_native(&self, prog: &crate::native_eval::NativeProg) -> Value;
    /// READ: resolve each LHS chunk's `(bit-offset, array-word)` NOW (dynamic index).
    fn k_resolve_lvalue_offsets(&self, lhs: &Lvalue) -> Vec<(u32, u32)>;
    /// WRITE: blocking write of `value` into `lhs` at the resolved `offsets`.
    fn k_write_lvalue(&mut self, lhs: &Lvalue, value: Value, offsets: &[(u32, u32)]);
    /// WRITE: schedule a nonblocking update (LHS index sampled at schedule time).
    fn k_schedule_nba(&mut self, lhs: Lvalue, value: Value);
    /// WRITE: run a system task, returning its control outcome. `sid` is the
    /// StmtId — the severity side table (`$fatal`/`$error`/…, P1-1) is keyed by it.
    fn k_dispatch_systask(
        &mut self,
        which: SysTaskId,
        fmt: Option<u32>,
        args: &[u32],
        sid: u32,
    ) -> Ctl;

    // ── terminator / control surface (C1) ──
    // The control-flow ABI a compiled body needs beyond the statement surface above:
    // `Branch` truthiness, `Return` re-arm, and the per-activation termination guard.
    // All FORWARD verbatim to the interpreter's inherent methods (the VM reproduces
    // control flow bit-for-bit through the SAME kernel — it never reimplements it).

    /// CONTROL: tri-valued truthiness of `eid` for a `Branch` (X/Z → false), built on
    /// the same `EvalCtx` the interpreter's `Terminator::Branch` uses (exec.rs:120).
    fn k_truthy(&self, eid: u32) -> bool;
    /// CONTROL: re-arm the process after `Return`, preserving the Edge/Level/Initial
    /// asymmetry (NOT reimplemented). TOTAL on the codegen-able class: such a body has
    /// no `Fork` terminator, so it can never be entered as a fork child (a child's
    /// `Return` is routed to `on_child_complete`, never to `rearm`) — `is_codegen_able`
    /// scans the WHOLE body, so the VM only ever drives top-level activities here.
    fn k_rearm(&mut self, proc: u32);
    /// CONTROL: the infinite-delta termination-guard ceiling (mirror exec.rs:177).
    fn k_max_deltas(&self) -> u64;
    /// CONTROL: flag a fatal (delta-limit) termination (mirror exec.rs:178).
    fn k_mark_fatal(&mut self);
}

/// Execute activity `pi` starting at body block `start`. `pi` is a runtime
/// ACTIVITY id (index into `Scheduler::activities`), NOT a declaration index —
/// the body/sensitivity are resolved through `activities[pi].template`.
pub(crate) fn run_process(sched: &mut Scheduler, pi: u32, mut bb: u32) -> Step {
    let mut guard: u64 = 0;
    loop {
        // ── CENTRALIZED CHILD-COMPLETION INTERCEPT (terminator-agnostic) ──
        // If this activity is a fork child and the NEXT bb to fetch is its barrier's
        // join_bb, the child has completed. Report + die BEFORE the join_bb block is
        // ever fetched (join_bb is a never-executed sentinel). This catches the child
        // whether it arrives via Goto, Branch, or a resumed Delay/Wait, so a child
        // whose last statement is an if/case/delay/wait into join_bb is handled.
        if sched.activity_is_child(pi) {
            if let Some(jr) = sched.activity_join_ref(pi) {
                if bb == sched.barrier_join_bb(jr) {
                    sched.on_child_complete(jr, pi);
                    return Step::Done; // child dead; rearm skips it (is_child)
                }
            }
        }
        // Defense-in-depth: a non-child must NEVER fetch a live barrier's join_bb.
        #[cfg(debug_assertions)]
        sched.assert_not_parent_at_join(pi, bb);

        // Snapshot the block's stmt ids + terminator (process-local indexing,
        // resolved through this activity's template).
        let tmpl = sched.activity_template(pi) as usize;
        // $time/$realtime evaluated in this process scale by its module multiplier.
        sched.st.cur_time_mult = sched
            .st
            .proc_multipliers
            .get(tmpl)
            .copied()
            .unwrap_or(1)
            .max(1) as u64;
        // `%m` scope of this process (P2-11); flat "top" when no sidecar.
        sched.st.cur_scope = sched
            .st
            .proc_scopes
            .get(tmpl)
            .cloned()
            .unwrap_or_else(|| "top".to_string());
        let (stmt_ids, term) = {
            let body = &sched.st.ir.processes[tmpl].body;
            let block = &body[bb as usize];
            (block.stmts.clone(), block.term.clone())
        };

        // ── statements (P7a read/write-phase split) ──
        // Each statement executes in two explicit phases: a READ phase
        // (`compute_effect`, pure eval over `&Scheduler` — no mutation) that produces
        // a self-contained [`StmtEffect`], then a WRITE phase (`apply_effect`, the
        // `&mut Scheduler` kernel calls). This is the seam a codegen body needs: it
        // inlines the read phase as native code and routes the write phase through the
        // kernel (P7b puts apply_effect's calls behind a trait). Behaviour is
        // byte-identical to the prior inline form — same evals, same writes, same order.
        for sid in stmt_ids {
            let stmt = sched.st.ir.stmts[sid as usize].clone();
            let effect = compute_effect(&*sched, &stmt, sid); // READ phase via Kernel seam
            if let Some(step) = apply_effect(sched, effect) {
                return step; // a SysTask returned Finish/Stop/Fatal
            }
        }

        // ── terminator ──
        match term {
            Terminator::Goto { target } => {
                bb = target;
            }
            Terminator::Branch {
                cond,
                then_bb,
                else_bb,
            } => {
                bb = if sched.truthy(cond) { then_bb } else { else_bb };
            }
            Terminator::Delay {
                amount,
                region,
                resume,
            } => {
                // `amount` is a literal tick count (FROZEN IR: u32, NOT an ExprId).
                let inactive = matches!(region, DelayRegion::Inactive) || amount == 0;
                let tick = sched.now() + amount as u64;
                sched.schedule_resume(pi, resume, tick, inactive);
                return Step::Suspended;
            }
            Terminator::Wait { cond, resume } => {
                match &cond {
                    WaitCause::Expr { expr } => {
                        if sched.truthy(*expr) {
                            bb = resume; // already true → fall through
                            guard += 1;
                            if guard > sched.max_deltas_guard() {
                                sched.mark_fatal();
                                return Step::Fatal;
                            }
                            continue;
                        }
                        sched.suspend_on(pi, resume, cond);
                    }
                    _ => sched.suspend_on(pi, resume, cond),
                }
                return Step::Suspended;
            }
            Terminator::Return => {
                sched.rearm(pi);
                return Step::Done;
            }
            // fork/join/join_any/join_none: register the barrier, spawn each child as
            // a new activity (runnable THIS instant), then either continue at
            // resume_bb (join_none, or zero children) or suspend on the barrier
            // (join/join_any with ≥1 child). The parent is re-enqueued by
            // on_child_complete when the join condition fires.
            Terminator::Fork {
                children,
                join,
                resume_bb,
            } => match sched.exec_fork(pi, &children, join, resume_bb) {
                Some(cont) => {
                    bb = cont;
                }
                None => return Step::Suspended,
            },
            // Deferred v1: user task/func `Call`. elaborate inlines tasks, so this
            // should not appear from v1 elaborate; advance to keep liveness.
            Terminator::Call { ret_bb, .. } => {
                bb = ret_bb;
            }
        }

        guard += 1;
        if guard > sched.max_deltas_guard() {
            sched.mark_fatal();
            return Step::Fatal;
        }
    }
}

/// The self-contained result of a statement's READ phase — everything the WRITE
/// phase needs, with no further reads of net state. Computing this is pure (reads
/// only, via `&Scheduler`); applying it is where all mutation happens. This is the
/// P7a boundary: a compiled body produces the same effects from native code, and
/// [`apply_effect`]'s kernel calls become the trait surface in P7b.
enum StmtEffect {
    /// Blocking assign: RHS evaluated context-sized, per-chunk `(offset, word)`
    /// resolved NOW (dynamic-index sample at statement time).
    Blocking {
        lhs: Lvalue,
        value: Value,
        offsets: Vec<(u32, u32)>,
    },
    /// Nonblocking assign: RHS SAMPLED now; the LHS index is sampled inside
    /// `schedule_nba` at schedule time (Active region), so it is NOT resolved here —
    /// preserving `a[i] <= x; i = i + 1;` using the old `i`.
    Nonblocking { lhs: Lvalue, value: Value },
    /// System task: a kernel call (its own read+write happen inside `dispatch`).
    /// `sid` keys the severity side table (P1-1).
    SysTask {
        which: SysTaskId,
        fmt: Option<u32>,
        args: Vec<u32>,
        sid: u32,
    },
    /// `disable`: no-op in v1 (fork/disable deferred).
    Nop,
}

/// READ phase: evaluate `stmt` through the read-only half of the [`Kernel`] seam,
/// producing a [`StmtEffect`] that captures everything the write phase will apply. No
/// net state is mutated here. Generic over `K: Kernel`, so the SAME executor serves
/// the interpreter (`Scheduler`) and a Stage-C compiled body.
fn compute_effect<K: Kernel>(k: &K, stmt: &Stmt, sid: u32) -> StmtEffect {
    match stmt {
        Stmt::BlockingAssign { lhs, rhs } => {
            let value = k.k_eval_for_lvalue(lhs, *rhs); // CONTEXT-SIZED to lhs width
            let offsets = k.k_resolve_lvalue_offsets(lhs); // dynamic index NOW
            StmtEffect::Blocking {
                lhs: lhs.clone(),
                value,
                offsets,
            }
        }
        Stmt::NonblockingAssign { lhs, rhs } => {
            let value = k.k_eval_for_lvalue(lhs, *rhs); // CONTEXT-SIZED, sampled now
            StmtEffect::Nonblocking {
                lhs: lhs.clone(),
                value,
            }
        }
        Stmt::SysTask { which, fmt, args } => StmtEffect::SysTask {
            which: *which,
            fmt: *fmt,
            args: args.clone(),
            sid,
        },
        Stmt::Disable { .. } => StmtEffect::Nop,
    }
}

/// WRITE phase: apply a [`StmtEffect`] through the mutating half of the [`Kernel`]
/// seam. Returns `Some(Step)` only when a `$finish`/`$stop`/fatal system task ends the
/// activation. Generic over `K: Kernel` (same executor for interpreter + compiled VM).
fn apply_effect<K: Kernel>(k: &mut K, effect: StmtEffect) -> Option<Step> {
    match effect {
        StmtEffect::Blocking {
            lhs,
            value,
            offsets,
        } => {
            k.k_write_lvalue(&lhs, value, &offsets);
            None
        }
        StmtEffect::Nonblocking { lhs, value } => {
            k.k_schedule_nba(lhs, value);
            None
        }
        StmtEffect::SysTask {
            which,
            fmt,
            args,
            sid,
        } => match k.k_dispatch_systask(which, fmt, &args, sid) {
            Ctl::Finish => Some(Step::Finish),
            Ctl::Stop => Some(Step::Stop),
            Ctl::Fatal => Some(Step::Fatal),
            Ctl::Continue => None,
        },
        StmtEffect::Nop => None,
    }
}
