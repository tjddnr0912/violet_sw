# Stage C — Bytecode VM Compiled Backend: Spec & Implementation Plan

> **Status:** DRAFT for review (2026-06-06). Stage B (11/11 backend prerequisites)
> complete; this is the `구현` (implementation) design the user's sequence calls for,
> written against the seams Stage B installed. Substrate decided in
> `docs/preview/18-acceleration-analysis.md` §결정 기록: **bytecode VM (P0a)**, in-process,
> no runtime toolchain (P0b = N/A).

**Goal:** Replace `Scheduler::vm_run_body`'s interpreter-delegation with a real
bytecode compiler + register VM that executes a codegen-able (P9 suspend-free) process
body, calling the SAME kernel write phase through the `Kernel` trait — provably
byte-identical to the interpreter (the P5 gate) and faster on the suspend-free class
(P14).

**Non-goals (stay interpreted, by design):** suspend-bearing bodies (Delay/Wait/Fork/
Call), continuous assigns (until P13), the `$display`/`$strobe`/`$monitor` format
engine (P12d — a documented codegen *boundary*, not a target), and Windows.

---

## 1. What Stage B already gives us (the substrate)

| Seam | Where | Stage C uses it for |
|---|---|---|
| `Backend{Interpreter,Bytecode}` + `SimOpts.backend` | lib.rs | selecting the VM; P5 runs both |
| `Scheduler::run_body` dispatch + `vm_run_body` stub | sched.rs | THE entry point to fill in |
| `is_codegen_able(stmts, body)` (P9) | backend.rs | which bodies the VM may claim |
| `Kernel` trait (P7b) | exec.rs | the body→kernel ABI the VM calls (k_eval_for_lvalue / k_resolve_lvalue_offsets / k_write_lvalue / k_schedule_nba / k_dispatch_systask) |
| `StmtEffect` read/write split (P7a) | exec.rs | the per-statement shape the VM mirrors |
| P5 differential gate + P6 corpus | tests/ | byte-identity proof, every phase |
| P8 sampling-moment contract | doc-18 | what order the VM must preserve (only #2/#3 are body-side) |
| P3 float contract | doc-18 | VM reuses the frozen formatters verbatim |

**Critical inheritance:** the VM does NOT reimplement net I/O, VCD, scheduling, NBA,
or formatting. It calls the kernel for all of those (via `Kernel`), so determinism,
VCD bytes, and float output are reproduced *by construction*. The VM's only new code is
**control flow + expression evaluation** lowered to bytecode — and even expression
eval can, in the MVP, call back into the existing evaluator.

---

## 2. VM architecture

A **register bytecode VM**, not a tree-walk and not native codegen. Chosen because it
removes the two measured hot spots (eval tree-walk dispatch, `Value` heap-alloc) while
staying pure Rust with zero toolchain dependency (preserves all determinism pins).

### 2.1 Compiled artifact (per codegen-able Process body)

```
struct CompiledBody {
    regs: u32,                 // number of virtual registers
    blocks: Vec<CompiledBlock>,// 1:1 with the frozen Process.body BBs (same indices)
}
struct CompiledBlock {
    ops: Vec<Op>,              // straight-line ops for this block
    term: CompiledTerm,        // Goto(bb) | Branch(reg, then_bb, else_bb) | Return
}
```

`CompiledTerm` covers ONLY the P9 allow-list (Goto/Branch/Return) — by construction,
`is_codegen_able` guaranteed no other terminator. Block indices match the frozen IR's
so a future debugger maps back (P16).

### 2.2 Opcode set (MVP)

Minimal, register-to-register, each op a flat enum variant (no boxing):

```
enum Op {
    // expression eval — MVP delegates to the existing evaluator (see §3 Phase C2)
    EvalExpr   { dst: Reg, expr: ExprId, ctx_w: u32, ctx_signed: bool }, // -> Value in reg
    EvalForLval{ dst: Reg, lhs: LvalIdx, rhs: ExprId },                  // context-sized
    ResolveOff { dst: OffReg, lhs: LvalIdx },                            // Vec<(u32,u32)>
    Truthy     { dst: Reg, expr: ExprId } -> bool-in-reg,                // for Branch
    // kernel write phase — direct Kernel calls
    WriteLval  { lhs: LvalIdx, val: Reg, off: OffReg },                  // k_write_lvalue
    ScheduleNba{ lhs: LvalIdx, val: Reg },                              // k_schedule_nba
    SysTask    { which: SysTaskId, fmt: Option<ExprId>, args: ArgsIdx }, // k_dispatch_systask
}
```

`LvalIdx`/`ArgsIdx` index small side tables on the `CompiledBody` (the cloned `Lvalue`/
arg vectors), keeping `Op` `Copy`-small. Registers hold `Value` (4-state); the register
file is a `Vec<Value>` reused across activations of the same body (no per-statement
alloc — the P12a heap-alloc win lands here incrementally).

### 2.3 Execution

```
fn vm_exec(kernel: &mut impl Kernel, body: &CompiledBody, regs: &mut RegFile) -> Step {
    let mut bb = entry;
    loop {
        for op in &body.blocks[bb].ops {
            match op {
                EvalForLval{..} => regs[dst] = kernel.k_eval_for_lvalue(lhs, rhs),
                WriteLval{..}   => kernel.k_write_lvalue(lhs, regs[val].take(), off),
                ScheduleNba{..} => kernel.k_schedule_nba(lhs, regs[val].take()),
                SysTask{..}     => match kernel.k_dispatch_systask(..) { Finish=>return.., .. },
                ...
            }
        }
        match body.blocks[bb].term {
            Goto(t)            => bb = t,
            Branch(r,th,el)    => bb = if regs[r].truthy() { th } else { el },
            Return             => { kernel.k_rearm(); return Step::Done } // (k_rearm added in C1)
        }
        // per-activation delta guard (P12c) mirrored here
    }
}
```

The loop is structurally the interpreter's terminator loop MINUS the suspend cases —
which is exactly why P9 restricts to suspend-free bodies. Statement order is preserved
verbatim, satisfying P8 moments #2 (nba_seq) and #3 (offset-at-stmt) for free.

---

## 3. Phased implementation (each phase gated by P5 + 434 existing tests)

Ordered so every phase is independently byte-identical-verifiable. The Kernel trait
grows by exactly two methods (`k_truthy`, `k_rearm`) in C1; nothing else in Stage B
changes.

| Phase | Maps to | Deliverable | Gate |
|---|---|---|---|
| **C1** Terminator-phase ABI | P7b follow-on | Add `k_truthy`/`k_rearm` to `Kernel`; impl on Scheduler. No VM yet. | 434 green (pure addition) |
| **C2** Trivial VM (delegating ops) | P10/P11 scaffolding | `CompiledBody` + `vm_exec` where `EvalForLval`/`Truthy` call the SAME `k_*` evaluator (no native eval yet). Compile pass lowers a body 1:1. `vm_run_body` compiles-once-caches + runs it. | **P5 byte-identical** over corpus + mixed (P9b) |
| **C3** Native value registers | P12a | Replace `Value` heap with ≤128-bit register reps + X/Z plane; structural ops (concat/replicate/select/shift-4096-cap) on registers; >128 heap spill. | P5 + P12a bit-exact |
| **C4** Static width/sign + poison | P10 | Precompute (width,signed,poison-regime) per (ExprId,context); native arithmetic for the common lanes; X-poison thresholds hardcoded identically. | P5 + instrumented-eval cross-check |
| **C5** Index classification | P11 | Static vs runtime index/width/count; reproduce `const_u32_of_expr` SHALLOW fold + each site's exact fallback + OOR sentinel arms (read & write). Do NOT "improve" the fold. | P5 |
| **C6** Real lane | P12b | f64 register lane (is_real, NaN/±inf/±0.0/partial_cmp), reusing P3-frozen formatters. | P5 + float golden |
| **C7** Prologue + format boundary | P12c/P12d | cur_time_mult write-points incl. stale-postponed; dual delta-guard; format engine stays interpreted (explicit boundary). | P5 |
| **C8** Cont-assign codegen | P13 | Extend codegen to the settle fixpoint (declaration order). Not a correctness prereq — speedup on cont-assign-heavy designs. | P5 + P9b |
| **C9** Perf + cache + debug | P14/P15/P16 | speedup baseline+threshold; content-addressed codegen cache key + independent `kernel_abi_version` gate (reuse `composite_input_hash`); ExprId→SourceLoc sidecar. | P14 threshold met |

**MVP terminus = C2** (compiled control flow + cached compile, eval still delegated):
proves the whole pipeline byte-identical with the VM actually executing bodies. C3+ are
the *speedup* phases (incrementally remove the delegated eval/heap-alloc), each guarded
by P5 so a single divergent byte names the offending phase.

---

## 4. Risks & mitigations

| Risk | Mitigation |
|---|---|
| A compiled body reorders kernel calls → nba_seq divergence (P8 #2) | vm_exec executes ops in compile order = statement order; P9b test has teeth (q<=sum;r<=q) |
| Native value rep drifts from `Value` bit-for-bit (mask_top/resize/poison) | C3 reuses the exact value.rs ops as the oracle; P5 over wide-arith corpus |
| const-fold "improvement" computes a different (more correct) width than the shallow interpreter fold | C5 reuses `const_u32_of_expr` verbatim + each site's fallback (P11 acceptance) |
| Compile cost dominates for small designs (no net speedup) | compile-once-cache per body; C9 measures and may keep small bodies interpreted |
| Frozen IR pressure | ZERO IR change in any phase — VM is a SimOpts-selected side path; SchemaHash root stays pinned (gated by existing schema_hash test) |

---

## 5. Acceptance for "Stage C done"

1. `Backend::Bytecode` executes the P9 class on the VM; everything else interprets.
2. P5 gate byte-identical (stdout + VCD) over the full P6 corpus + the P9b mixed design,
   on all CI legs, with no skip.
3. P14 speedup threshold met on the suspend-free class vs the interpreter baseline.
4. `schema_hash::<SimIr>()` root unflipped; `format_version` still 3; `kernel_abi_version`
   gates the VM artifact independently.
5. Documentation: doc-18 updated to SHIPPED; the format-engine boundary (P12d) and the
   interpreter-only constructs (cont-assign pre-C8, suspend-bearing) explicitly stated.
