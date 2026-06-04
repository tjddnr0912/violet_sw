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

/// Execute process `pi` starting at body block `start`.
pub(crate) fn run_process(sched: &mut Scheduler, pi: u32, mut bb: u32) -> Step {
    let mut guard: u64 = 0;
    loop {
        // Snapshot the block's stmt ids + terminator (process-local indexing).
        let (stmt_ids, term) = {
            let body = &sched.st.ir.processes[pi as usize].body;
            let block = &body[bb as usize];
            (block.stmts.clone(), block.term.clone())
        };

        // ── statements ──
        for sid in stmt_ids {
            let stmt = sched.st.ir.stmts[sid as usize].clone();
            match stmt {
                Stmt::BlockingAssign { lhs, rhs } => {
                    let v = sched.eval(rhs);
                    sched.st.write_lvalue(&lhs, v);
                }
                Stmt::NonblockingAssign { lhs, rhs } => {
                    let sampled = sched.eval(rhs); // sample RHS now (Active)
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
            // Deferred v1: fork/join + task call. elaborate lowers fork→sequential,
            // so these should not appear from v1 elaborate; advance to keep liveness.
            Terminator::Fork { resume_bb, .. } => {
                bb = resume_bb;
            }
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
