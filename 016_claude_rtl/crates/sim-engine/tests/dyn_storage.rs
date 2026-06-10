//! v5 increment (C)-③: dynamic-array ENGINE layer (heap + new/size/delete).
//!
//! No front-end syntax exists yet (that is increment ⑥, batched with the .vu
//! flip), so these tests HAND-BUILD a frozen `SimIr` and drive it through the
//! public `simulate`/`simulate_capture` seam — exactly what elaborate will emit
//! once the syntax lands. Semantics oracle: iverilog -g2012 probed live
//! (`new[5]`→size 5, `delete()`→0, copy form `new[6](d)`→6).

use std::cell::RefCell;

use diag::{LogEvent, LogSink};
use sim_engine::{simulate, simulate_capture, FinishReason, SimOpts};
use sim_ir::{
    BasicBlock, BitPacked, ConstRepr, ConstVal, Expr, Instance, JoinState, NetKind, NetVar,
    PortDir, ProcFlags, Process, RegionTag, SensKind, Sensitivity, SimIr, Stmt, SuspendState,
    SysFuncId, SysTaskId, Terminator, WakeCond, WakeKey,
};

/// Diagnostic collector (runtime warns ride the LogSink, not stdout).
#[derive(Default)]
struct DiagSink(RefCell<Vec<String>>);
impl LogSink for DiagSink {
    fn emit(&self, e: LogEvent) {
        if let LogEvent::Diagnostic(d) = e {
            self.0.borrow_mut().push(format!(
                "{}[{}]: {}",
                d.severity.token(),
                d.code.code_num(),
                d.message
            ));
        }
    }
}

fn suspend0() -> SuspendState {
    SuspendState {
        resume_pc: 0,
        locals: Vec::new(),
        join_state: JoinState {
            parent: None,
            children: Vec::new(),
            detached: Vec::new(),
            flags: ProcFlags(0),
        },
        wake_key: WakeKey {
            cond: WakeCond::Level { nets: Vec::new() },
            region: RegionTag::Active,
            tie_break: 0,
        },
        call_stack: Vec::new(),
        frame_arena: Vec::new(),
    }
}

/// 8-bit dyn-array HANDLE net: element width 8, `array_len 0`, flat-store cell
/// is a well-formed all-X byte the engine never reads through the dyn path.
fn dyn_handle() -> NetVar {
    NetVar {
        kind: NetKind::DynArray,
        width: 8,
        msb: 7,
        lsb: 0,
        signed: false,
        array_len: 0,
        dir: PortDir::Internal,
        init: BitPacked {
            val: vec![0],
            unk: vec![0xff],
        },
    }
}

fn int_const(v: u64) -> ConstVal {
    ConstVal {
        width: 32,
        signed: true,
        repr: ConstRepr::Numeric,
        bits: BitPacked {
            val: vec![v],
            unk: vec![0],
        },
    }
}

fn x_const() -> ConstVal {
    ConstVal {
        width: 32,
        signed: true,
        repr: ConstRepr::Numeric,
        bits: BitPacked {
            val: vec![0],
            unk: vec![0xffff_ffff],
        },
    }
}

/// One initial process over the given arenas; every stmt in one BB → Return.
fn ir_of(nets: Vec<NetVar>, consts: Vec<ConstVal>, exprs: Vec<Expr>, stmts: Vec<Stmt>) -> SimIr {
    let stmt_ids: Vec<u32> = (0..stmts.len() as u32).collect();
    SimIr {
        instances: vec![Instance {
            parent: None,
            module: 0,
            first_net: 0,
            net_count: nets.len() as u32,
        }],
        nets,
        processes: vec![Process {
            sensitivity: Sensitivity {
                kind: SensKind::Initial,
                edges: Vec::new(),
            },
            body: vec![BasicBlock {
                stmts: stmt_ids,
                term: Terminator::Return,
            }],
            entry: 0,
            suspend: suspend0(),
        }],
        cont_assigns: Vec::new(),
        funcs: Vec::new(),
        exprs,
        stmts,
        blocks: Vec::new(),
        consts,
    }
}

fn systask(which: SysTaskId, args: Vec<u32>) -> Stmt {
    Stmt::SysTask {
        which,
        fmt: None,
        args,
    }
}

#[test]
fn dyn_new_size_delete_roundtrip() {
    // new[5] → size 5; delete() → size 0. (Oracle: iverilog live.)
    let exprs = vec![
        Expr::Signal { net: 0, word: None }, // 0: handle (DynNew)
        Expr::Const { val: 0 },              // 1: 5
        Expr::Signal { net: 0, word: None }, // 2: handle (size #1)
        Expr::SysFunc {
            which: SysFuncId::DynSize,
            args: vec![2],
        }, // 3
        Expr::Signal { net: 0, word: None }, // 4: handle (DynDelete)
        Expr::Signal { net: 0, word: None }, // 5: handle (size #2)
        Expr::SysFunc {
            which: SysFuncId::DynSize,
            args: vec![5],
        }, // 6
    ];
    let stmts = vec![
        systask(SysTaskId::DynNew, vec![0, 1]),
        systask(SysTaskId::Display, vec![3]),
        systask(SysTaskId::DynDelete, vec![4]),
        systask(SysTaskId::Display, vec![6]),
        systask(SysTaskId::Finish, vec![]),
    ];
    let ir = ir_of(vec![dyn_handle()], vec![int_const(5)], exprs, stmts);
    let (res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(res.finish_reason, FinishReason::Finish);
    assert_eq!(out, "         5\n         0\n"); // unformatted arg = default-width decimal
}

#[test]
fn dyn_new_copy_form_sizes_by_n() {
    // d = new[3]; q = new[6](d) → q.size() == 6 (sized by n, NOT by src —
    // oracle: iverilog live). Element-content checks land with the indexed
    // read/write slice.
    let exprs = vec![
        Expr::Signal { net: 0, word: None }, // 0: d
        Expr::Const { val: 0 },              // 1: 3
        Expr::Signal { net: 1, word: None }, // 2: q
        Expr::Const { val: 1 },              // 3: 6
        Expr::Signal { net: 0, word: None }, // 4: src d
        Expr::Signal { net: 1, word: None }, // 5: q (size)
        Expr::SysFunc {
            which: SysFuncId::DynSize,
            args: vec![5],
        }, // 6
    ];
    let stmts = vec![
        systask(SysTaskId::DynNew, vec![0, 1]),
        systask(SysTaskId::DynNew, vec![2, 3, 4]),
        systask(SysTaskId::Display, vec![6]),
        systask(SysTaskId::Finish, vec![]),
    ];
    let ir = ir_of(
        vec![dyn_handle(), dyn_handle()],
        vec![int_const(3), int_const(6)],
        exprs,
        stmts,
    );
    let (res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(res.finish_reason, FinishReason::Finish);
    assert_eq!(out, "         6\n");
}

#[test]
fn dyn_new_x_size_degrades_to_empty_with_one_warn() {
    // new[n] with an X/Z n → EMPTY array + a single W-RUN-DYN-DEGRADE warning
    // (warn-once per net); new[0] is legal-silent (IEEE §7.5.1, design §4).
    let exprs = vec![
        Expr::Signal { net: 0, word: None }, // 0: handle
        Expr::Const { val: 0 },              // 1: X const
        Expr::Signal { net: 0, word: None }, // 2: handle (X again — same net)
        Expr::Const { val: 0 },              // 3
        Expr::Signal { net: 0, word: None }, // 4: handle (size)
        Expr::SysFunc {
            which: SysFuncId::DynSize,
            args: vec![4],
        }, // 5
    ];
    let stmts = vec![
        systask(SysTaskId::DynNew, vec![0, 1]),
        systask(SysTaskId::DynNew, vec![2, 3]),
        systask(SysTaskId::Display, vec![5]),
        systask(SysTaskId::Finish, vec![]),
    ];
    let ir = ir_of(vec![dyn_handle()], vec![x_const()], exprs, stmts);
    let sink = DiagSink::default();
    let res = simulate(&ir, &sink, SimOpts::default());
    assert_eq!(res.finish_reason, FinishReason::Finish);
    let diags = sink.0.into_inner();
    let dyn_warns: Vec<&String> = diags.iter().filter(|d| d.contains("W4020")).collect();
    assert_eq!(
        dyn_warns.len(),
        1,
        "X-size new[] must warn EXACTLY once per net: {diags:?}"
    );
}
