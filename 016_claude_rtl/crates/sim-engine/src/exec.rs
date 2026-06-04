//! Process executor: the FROZEN basic-block PC state machine. Runs a
//! `Process.body` from a resume block, executing each block's statements then
//! its terminator, suspending on Delay/Wait and completing on Return.
//!
//! Operates on the [`Scheduler`] so a single `&mut` reaches both the net table
//! (`sched.st`) for immediate blocking writes and the scheduler queues for
//! NBA/Delay/Wait scheduling.

use sim_ir::{DelayRegion, Stmt, Terminator, WaitCause};

use crate::builtins::{self, Ctl};
use crate::sched::Scheduler;

/// Outcome of one process activation.
pub(crate) enum Step {
    Done,
    Suspended,
    Finish,
    Stop,
    Fatal,
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
        let (stmt_ids, term) = {
            let body = &sched.st.ir.processes[tmpl].body;
            let block = &body[bb as usize];
            (block.stmts.clone(), block.term.clone())
        };

        // ── statements ──
        for sid in stmt_ids {
            let stmt = sched.st.ir.stmts[sid as usize].clone();
            match stmt {
                Stmt::BlockingAssign { lhs, rhs } => {
                    let v = sched.eval_for_lvalue(&lhs, rhs); // CONTEXT-SIZED to lhs width
                    sched.st.write_lvalue(&lhs, v);
                }
                Stmt::NonblockingAssign { lhs, rhs } => {
                    let sampled = sched.eval_for_lvalue(&lhs, rhs); // CONTEXT-SIZED, sampled now
                    sched.schedule_nba(lhs, sampled);
                }
                Stmt::SysTask { which, fmt, args } => {
                    match builtins::dispatch(sched, which, fmt, &args) {
                        Ctl::Finish => return Step::Finish,
                        Ctl::Stop => return Step::Stop,
                        Ctl::Fatal => return Step::Fatal,
                        Ctl::Continue => {}
                    }
                }
                Stmt::Disable { .. } => { /* v1: no-op (fork/disable deferred) */ }
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
