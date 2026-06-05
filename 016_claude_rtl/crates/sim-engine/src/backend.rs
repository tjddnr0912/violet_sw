//! Bytecode backend (P0a) — Stage B scaffolding.
//!
//! Today this houses the **P9 scope predicate** that classifies a process body as
//! codegen-able on the bytecode VM. Stage C grows this module into the bytecode
//! compiler + register VM; the predicate already gates which bodies that VM may
//! claim (everything else permanently uses the reference interpreter).

use sim_ir::{BasicBlock, Stmt, Terminator};

/// **P9 scope predicate.** Is this process `body` codegen-able on the bytecode VM?
///
/// A POSITIVE allow-list — NOT a `Fork`/`Call` deny-list (a deny-list would wrongly
/// admit `Delay`/`Wait`). A body qualifies iff **every** terminator is
/// `Goto`/`Branch`/`Return` and **no** statement is `Disable`.
///
/// Loops are fine: `for`/`while`/`forever` lower to `Branch` back-edges (and a bare
/// self-timed `always` wraps in an implicit `forever`), so a qualifying body still
/// runs to `Return` *atomically*, with no suspension. The excluded terminators are
/// exactly the suspend / spawn points a single straight native call cannot express:
///
/// - `Delay` / `Wait` — the true suspend points; resuming them needs a saved
///   resume-PC state machine. (`Wait` also carries `WaitCause::Named`, which the
///   interpreter parks but never wakes — it must never be "compiled" into a hang.)
/// - `Fork` — spawns child activities and a join barrier (the activity arena).
/// - `Call` — an integer-frame call (v1 inlines tasks, so this should not appear,
///   but it is excluded defensively).
///
/// `Stmt::Disable` is excluded as well: a no-op today, but a Phase-2 control-flow
/// change we will not silently bake into compiled code.
///
/// Anything not on the allow-list falls back to the interpreter, so an unknown or
/// future terminator/statement variant is safe by default.
pub(crate) fn is_codegen_able(stmts: &[Stmt], body: &[BasicBlock]) -> bool {
    body.iter().all(|block| {
        let term_ok = matches!(
            block.term,
            Terminator::Goto { .. } | Terminator::Branch { .. } | Terminator::Return
        );
        let stmts_ok = block
            .stmts
            .iter()
            .all(|&sid| !matches!(stmts[sid as usize], Stmt::Disable { .. }));
        term_ok && stmts_ok
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use sim_ir::{DelayRegion, DisableKind, EdgeKind, Lvalue, WaitCause};

    /// stmts arena: index 0 = a benign blocking assign, index 1 = a `disable`.
    fn arena() -> Vec<Stmt> {
        vec![
            Stmt::BlockingAssign {
                lhs: Lvalue { chunks: vec![] },
                rhs: 0,
            },
            Stmt::Disable {
                scope_kind: DisableKind::Scope,
                target: 0,
            },
        ]
    }

    fn block(stmts: Vec<u32>, term: Terminator) -> BasicBlock {
        BasicBlock { stmts, term }
    }

    /// Straight-line AND looping bodies (Branch back-edge) over Goto/Branch/Return
    /// with only assigns are codegen-able — this is the `always_ff @(posedge clk)`
    /// shape (the edge wait is the process *sensitivity*, not a body terminator).
    #[test]
    fn straight_line_and_loops_are_codegen_able() {
        let a = arena();
        let body = vec![
            block(
                vec![0],
                Terminator::Branch {
                    cond: 0,
                    then_bb: 0, // back-edge: a runtime loop
                    else_bb: 2,
                },
            ),
            block(vec![0], Terminator::Goto { target: 0 }),
            block(vec![0], Terminator::Return),
        ];
        assert!(is_codegen_able(&a, &body));
    }

    #[test]
    fn delay_terminator_is_not_codegen_able() {
        let a = arena();
        let body = vec![block(
            vec![],
            Terminator::Delay {
                amount: 1,
                region: DelayRegion::Active,
                resume: 0,
            },
        )];
        assert!(!is_codegen_able(&a, &body));
    }

    #[test]
    fn wait_terminator_is_not_codegen_able() {
        let a = arena();
        for cond in [
            WaitCause::Edge {
                net: 0,
                kind: EdgeKind::Posedge,
            },
            WaitCause::Level { nets: vec![0] },
            WaitCause::Expr { expr: 0 },
            WaitCause::Named { ev: 0 }, // the never-waking variant — must be excluded
        ] {
            let body = vec![block(vec![], Terminator::Wait { cond, resume: 0 })];
            assert!(!is_codegen_able(&a, &body), "Wait must exclude");
        }
    }

    #[test]
    fn fork_and_call_are_not_codegen_able() {
        let a = arena();
        let fork = vec![block(
            vec![],
            Terminator::Fork {
                children: vec![],
                join: 0,
                resume_bb: 0,
            },
        )];
        assert!(!is_codegen_able(&a, &fork));
        let call = vec![block(
            vec![],
            Terminator::Call {
                target: 0,
                ret_bb: 0,
            },
        )];
        assert!(!is_codegen_able(&a, &call));
    }

    #[test]
    fn disable_statement_is_not_codegen_able() {
        let a = arena();
        // a Goto/Return body, but one block runs the `disable` statement (arena idx 1).
        let body = vec![
            block(vec![1], Terminator::Goto { target: 1 }),
            block(vec![0], Terminator::Return),
        ];
        assert!(!is_codegen_able(&a, &body));
    }

    /// One suspend-bearing block anywhere disqualifies the whole body (the predicate
    /// is `all`, not `any`).
    #[test]
    fn one_bad_block_disqualifies_the_body() {
        let a = arena();
        let body = vec![
            block(vec![0], Terminator::Goto { target: 1 }),
            block(
                vec![],
                Terminator::Delay {
                    amount: 0,
                    region: DelayRegion::Active,
                    resume: 0,
                },
            ),
            block(vec![0], Terminator::Return),
        ];
        assert!(!is_codegen_able(&a, &body));
    }
}
