# CLAUDE.md - 016_claude_rtl (vitamin)

오픈소스 Rust RTL 시뮬레이터. CLI: `vita`(원샷) / `vcmp`(compile) / `velab`(elaborate) / `vrun`(simulate). SystemVerilog 합성가능 RTL 서브셋(Verilog-2005 RTL 전부 포함)이 Phase-1 MVP.

> **상태:** **전 파이프라인 동작** — one-shot `vita design.sv` + staged `vcmp→velab→vrun` 모두 VCD+stdout 산출. Phase-1 합성 RTL 대부분(timescale·다차원 unpacked/packed 배열·casex/casez·fork-join·func/task·SV 자료형 enum/typedef/packed struct) + Phase-2(worklib·package·string·dyn/queue/assoc·정밀화 IR) + Phase-3(SVA 시퀀스 서브셋·deferred immediate asserts·automatic/recursive 콜스택·**HIER-REST 완결**=계층 참조 read+write·element/bit/part-select·whole 다차원 packed·indexed-segment `g[0].x`·Medium 묶음 rank 1-6·NBA repeat-event(N1)·multi-clock/recursive/prop-level and-or SVA(N2)·per-variable lifetime(B4)·**functional coverage 완성(N5+N5-G: explicit bins·iff·cross·option.at_least/weight·real-% per-cp 가중평균·`@(clk)` auto-sample·정밀 expr-coverpoint 폭)**·indexed-part-select underflow 수정(P0-IPU)·잔여 low-pri 4종(SYS-INTRO잔여 `$countbits`/`$typename`/`$exit`·SVPART 2-state 정수타입·GATE 게이트 프리미티브)·**N7 class/OOP 코어+상속+가상**(class·필드·new/ctor·this·handle/null·extends/super·virtual 동적 디스패치 vtable·value+void 메서드·return; 핸들=Integer obj-id + 엔진 `class_heap` RefCell + layout/vtable 사이드카; 적대 6렌즈→8 silent-wrong 수정)·**SVA-REST 완결**(`assume property`·property ops `always`/`not`/`implies`/`iff`/`until`/`s_until`/`s_eventually`/`nexttime`·`cover property`·`let` 매크로·`$assertoff/on/kill` 런타임 게이트·`seq[+]`=`[*1:$]`; liveness=end-of-sim `final` pend 체크)·**dyn array `new[N]` 2-state 원소 기본값 수정**(IEEE §7.5.2: 2-state=0·4-state=X)·**적대 재감사 silent-wrong 4종 수정**(2026-06-22 51탄: class 필드 선언 초기화자 `int x=42`·auto `super.new()`·`%0N` 제로패딩·VCD `real` r-`%.16g` 포맷 — 전부 사이드카/엔진/렌더러라 IR-0)·**하드닝 백로그(32 findings → ROADMAP §5) + 추천순서 1~4 수정**(2026-06-22 52탄: ①STAGED-DROP — staged `velab→vrun`가 누락하던 13종 사이드카=func_table·task_calls·class_*·two_state_nets·assert_*를 14번째 append-only `StagedExtraSidecars` trailer로 직렬화→class/재귀-automatic-fn staged silent-wrong 해소; ②PP-FANOUT-CAP — `PreOpts.max_output_bytes`(256MiB) emit-funnel budget+scan_text early-return으로 더블링-매크로 fan-out DoS(~8GB) loud E1004 차단·u32 오프셋 wrap 동봉 차단; ③VCD-SCRATCH — `VcdWriter.scratch: Vec<u8>` 재사용+`encode_*_into` byte-writer로 값변화당 String alloc 제거(A/B 실측 VCD-write 1.41x·byte-identical); ④CLASS-HEAP-CAP — `SimOpts.max_class_objs`(1M) budget+`F-RUN-CLASS-LIMIT`(F4024, MsgCode 55→56) graceful $finish으로 GC-없는 class 힙 per-cycle `new` 누수 차단; ①~③ out-of-band IR-0·④ sidecar)) + **§5.1 #5~6 + hostile-input cap 묶음 6종**(2026-06-22 53탄: STMT-DEPTH=파서 문장재귀 cap 256·SEQ-DEPTH=SVA 시퀀스재귀 cap 256·ELAB-ERR-CAP=진단 flood soft-cap 200·GEN-NET-CAP=add_net 집계 budget 1<<17·FORK-TIE-CAP=tie-overflow graceful fatal(RunFatal 재사용)·WIDE-ARITH-CAP=광폭 `*//`%`/`**` X-poison+`W-RUN-WIDE-ARITH`/W4025 loud — 전부 hostile-input 자원 cap, 전부 IR-0(WIDE-ARITH만 MsgCode 56→57))·**PARSE-CONCAT-CAP**(사용자 결정=전역 노드 예산: `expr()` `node_count`+`MAX_AST_NODES=1<<21`(2M·168MiB)→초과 시 expr comma-loop 5곳 push 중단+loud parse error로 `{a,…,4M}` flat concat OOM 차단, IR-0) 구현·검증. + **잔여 perf/robustness 17/18**(2026-06-23 54~55탄, ROADMAP §5 잔여 순차 TDD·서브시스템 배치; 앵커 검증은 18-에이전트 read-only 분석 병렬화): LOGEQ-WORD(word-parallel ==/!=/===)·MW-DIV-HOIST·FMT-CACHE(decode 캐시)·MCD-RECLAIM·FD-RECLAIM·FORCE-REEVAL·WAITER-POOL·CLS-FIELD-RD·CLS-CALL-VEC(Vec 인덱스)·VM-WIDEZERO·VM-ARITY-ASSERT(debug 경계 assert)·**POW-LANE**(const n≥2 Mul-chain, `w·n≤128` 가드로 오라클 u128-overflow quirk 회피 + n=1 X-poison 발산 차단)·VM-REGPOOL·**REALG-DEDUP**(단일 `vcd_writer::fmt_g`)·TRAILER-PIN·GEN-3X-STR part b·**RULEV-MTIME**(option A=15번째 append-only trailer `WorkStamps`+vrun mtime fast-path; velab이 content==recorded-hash 재검증 후에만 (mtime,size) stamp=소생결정[velab-write 막연 캡처는 vcmp→velab 윈도우 재개방 unsound]·worklib 전용) — 전부 byte-identical(IR-0/sidecar)·format_version 9·MsgCode 무증가. + **SVA-QUAD 테스트 강화 완료**(2026-06-23 56탄, 사용자 지시=테스트 강화부터): `##[m:n]` 윈도우 매처 특성화 net 13종(`sva_window_hardening.rs`: m=0 overlap·3폭 interior·upper-bound 배제·throughout 윈도우 AND·flat-mid·다중완료·paren honest-loud) + **무오라클 적대검증**(7-에이전트 워크플로: 3 IEEE-verdict 9/9×3 일치 + 4축 fan-out↔collapse divergence hunt). **⚠️ divergence hunt가 silent-wrong 1건 발굴→즉수정**: `##[0:$]`(unbounded m=0)이 d=0 동클럭 완료를 armed-latch 1클럭 지연으로 누락(bounded `##[0:n]`은 fan-out 정상)→`synth_seq_pipeline` AtLeast m==0 분기 this-clock OR(IEEE §16.9.2.1; m≥1·d≥1 byte-identical·format 무변경). **SVA-QUAD perf 리팩터 자체는 deferred·비권고**(런타임 이미 alt-선형, payoff=alt-explosion뿐; collapse 비자명성 입증). **1667 테스트 green**, iverilog 차분 일치(SVA/가상 디스패치는 hand-IEEE=iverilog 13 버그보다 정확), 3-OS CI green, **format_version 9**(SVA-REST=전부 IR-0, AST `.vu`만 재핀). + **Phase A — Tier ⓐ honest-loud 갭 4종 닫기**(2026-06-23, 사용자 결정 "A: 3개 닫기+잔여 2개 권장반영"): `function void`(모듈/free=내부 TaskDef·class=discard-at-call)+typed `parameter int/byte/shortint/longint/logic[W]`·고정크기 `foreach`(선언방향 존중)·leading-`##` SVA consequent·**`return` kw**(투자 전 read-only 검증이 doc의 "format_version bump 동반" 주장 **반증**→IR-0로 닫음, `body_has_return` 게이트=return-free 본문 byte-identical). **닫기 직후 적대 silent-wrong hunt(5-에이전트·라이브 iverilog 차분)가 3종 발굴→즉수정**: param 값 미coercion(`coerce_param_value`=선언폭 truncate+sign-extend, pre-existing `signed[7:0]`도 동일 수정)·foreach 하강범위 순서역전(`array_dim_desc`)·frame-func 2-state 로컬/return-slot 기본값 X(`run_frame/task_call`이 `Value::from_packed(&nv.init)`=2-state 0). **→ pre-existing 광범위 silent-wrong 2종 surface(의사결정 대기·ROADMAP §4.5)**: task output-formal copy-out 위반·SVA 시퀀스 X/Z 불리언을 match 처리. **1694 테스트 green**, 전부 IR-0·format_version 9 불변. + **Phase B — N7-REST 검증 플랫폼 착수**(2026-06-23, 사용자 결정 "B는 검증 플랫폼으로 키워. N7-REST 진행"): **constrained-random verification(B1)** — `rand` class 멤버 + `constraint NAME { FIELD </<=/>/>=/== CONST; … }`(`&&` 결합·`const OP field` 역형) + `obj.randomize()`(문장·`r=…` 대입). 제약→per-field `[lo,hi]` 폴딩(`coerce`式 `apply_constraint_expr`, 상속 체인 union) → **`class_rand` 사이드카(IR-0)**; randomize는 **결정적 seeded `dist_uniform`**(iverilog-pinned·3-OS byte-identical)로 [lo,hi] 균일추출(≤i32=fast path·광폭은 i64 modulo). 유일 IR 추가=`SysTaskId::ClassRandomize`→**format_version 9→10 bump**(골든 4종 재생성: AST hash·sim-ir hash·RON reflection·trailer-pin). 적대 hunt(4-에이전트·무iverilog=IEEE§18+통계 오라클)가 **silent-wrong 1건 발굴→즉수정**: 폭>32/경계>i32 제약필드가 [lo,hi]를 무시하고 full-width 추출(constrained 판정을 `fits-i32`→`(lo,hi)≠type_range`로 교체+i64 draw lane). 상속·다필드·하강·staged sidecar·randc/모순 loud-reject 검증. **B2 deferred(loud-reject)**: `randc`·`inside`·`dist`·implication(`->`)·inter-variable·soft·inline `with`. **1707 테스트 green**, clippy/fmt clean, **format_version 10**, MsgCode 57 무증가. + **Tier0 — pre-existing 광범위 silent-wrong + 적대 hunt 발굴분 전량 수정**(2026-06-23, 사용자 결정 "Tier0→B-CRV→B-breadth 순서·silent issue는 의사결정 없이 모조리 bugfix", **1733 green·전부 IR-0·format_version 10 불변**): **(i) SVA X/Z 불리언=NON-match(§16.13.5)** — `sva_match(e)=(\|e===1'b1)` X-strict 래퍼를 전 consequent 사이트(boolean·sequence·multiclock·crossclock·prop-expr `always`/`implies`/`and`/`or`/`not`/`until`·liveness antecedent)+`disable iff(X)`에 적용(antecedent는 `LogAnd(ante,!match)`로 자연 vacuous). **(ii) task/void-fn output-formal copy-out(§13.5.1/§13.5.3)** — inline-task 직접 aliasing→**formal-폭 local-net copy-in/copy-out** 전면 교체(width/sign coercion·**§13.4.1 static 단일인스턴스 retention**=task당 공유 local·glitch/intermediate-write 제거·input↔output aliasing 해소·narrow-input 절단·nested output threading) + 2-state(int/bit/byte/shortint/longint) **X/Z→0 coercion**(formal-local `intro_kind` 등록) + **2-state 변수 init 1회성화**(`int x=5`가 continuous-driver로 후속 write를 삼키던 pre-existing 버그: `is_var`에 2-state 추가) + **param/expr 상수 init 폴딩**(`int x=P`/`reg x=A+B`가 X/0로 silent-drop하던 pre-existing 버그도 const-eval로 동반 수정). 적대 hunt **2회(24+5 confirmed) 전량 수정**(라이브 iverilog 차분; SVA=hand-IEEE). 잔여 known-limit(별개·pre-existing·희소)=비상수 var-ref init `int x=다른변수`(전 var-type 공통·init-phase ordering 필요)·output/inout actual part-select(loud).
>
> 슬라이스별 개발 이력(Stage C 바이트코드 VM · profile-driven ~6x · native-eval · 1탄~49탄 전부) → **[docs/DEVLOG.md](docs/DEVLOG.md)**. 향후 과제·전략 = **[docs/ROADMAP.md](docs/ROADMAP.md)**, 잔여 작업 트래커 = [docs/REMAINING_WORK.md](docs/REMAINING_WORK.md). SPEC `docs/preview/`가 단일 진실 공급원.

## 실행 (cargo-only · build.rs 없음)

```bash
cargo build  --workspace --locked                       # 17-crate 워크스페이스 (15 prod + 2 dev)
cargo test   --workspace --locked                       # 결정성 골든 게이트 포함
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo fmt --all -- --check
```

MSRV **1.82** (`rust-toolchain.toml` 고정), **edition 2021**(edition 2024는 rustc≥1.85라 비호환). `blake3 = "=1.8.2"` 핀. `--locked` 필수(3-OS 재현성).

## 핵심 정보

| 항목 | 값 |
|---|---|
| 파이프라인 | preprocess→lex→parse→elaborate→sim-ir→sim-engine→VCD (parse까지 언어의존, 이후 중립) |
| 결정성 | `#[derive(SchemaHash)]` 구조적 형상 해시로 `.velab`/`.vu` staleness 게이트, 3-OS 바이트 동일 (BTree-only, usize/float 금지, span-free) |
| 골든 루트 | `sim_ir::SimIr`. 형상 변경 시 루트 해시 flip → `format_version` bump(현재 **10**, v10=`SysTaskId::ClassRandomize`(N7-REST randomize); v9=SysFuncId/SysTaskId 확장 file-read·`$dist_*`·`$cast`·`$monitoron/off`·`$writemem*` — AST flip은 .vu 해시 별도) + 전 `.velab` 재생성. 엔진-facing 사이드테이블(fork_modes·net_names·proc_multipliers·final_procs·wait_fork·sva 체커·deferred-assert 마커·frame nets 등)은 `SimOpts`/elaborate IR-0 합성으로 out-of-band → 골든 무영향 |
| 직렬화 | `serde` + `postcard 1.x` 단일 인코더, `blake3` 다이제스트 |

## 주요 크레이트 (거의 전부 실코드; stub은 2개)

| crate | 역할 | 상태 |
|---|---|---|
| `cli` | `vita`/`vcmp`/`velab`/`vrun` multicall — 전 파이프라인 구동 + timescale 배선 | **실코드** |
| `hdl-preprocess` | `` `define ``/`` `include ``/`` `ifdef ``/`` `timescale `` 파싱 + SourceMap | **실코드** |
| `hdl-lexer`·`hdl-parser`·`hdl-ast` | logos 토크나이저 · hand-RD+Pratt 파서 · AST | **실코드** |
| `elaborate` | AST→sim-ir lowering(모듈/generate/func-task/다차원배열/timescale 등) | **실코드** |
| `sim-engine` | 이벤트구동 IEEE-1364 스케줄러 + eval + VCD 방출 | **실코드** |
| `vcd-writer` | 계층 `$scope`/`$var` VCD 출력 | **실코드** |
| `sim-ir` | 언어중립 IR(Expr/Stmt/Terminator/NetVar/SimIr 루트) | 실코드 |
| `vita-artifact`(+derive)·`vita-schema`·`diag` | 산출물 헤더+게이트(`format_version=10`) · SchemaHash · MsgCode(57, doc-15 bijection) | 실코드 |
| `vita-log` | 진단 게이트(GatePolicy/GatedSink — `-Wno-*`/`-Werror=`) | **실코드** (2026-06-10) |
| `hdl-builtins` | $task 핸들러 추출 대상 | **stub** (1줄; 기능은 sim-engine 인라인) |

## 상세 문서 (`docs/preview/`)

| 주제 | 파일 |
|---|---|
| 개요·목표·범위 | [00-overview](docs/preview/00-overview.md) · [01-goals-and-scope](docs/preview/01-goals-and-scope.md) |
| 언어·빌드·아키텍처 | [02-implementation-language](docs/preview/02-implementation-language.md) · [03-build-and-portability](docs/preview/03-build-and-portability.md) · [04-architecture](docs/preview/04-architecture.md) |
| 전략·시뮬엔진·VCD·timescale | 05-strategy-and-roadmap · 06-simulation-engine · 07-vcd-format · 08-timescale-and-timing |
| 테스트·진단·산출물 | 09-testing-and-verification · 13-diagnostics-and-logging · [14-staged-artifacts](docs/preview/14-staged-artifacts.md) |
| 에러코드·SchemaHash·IR백본 freeze | [15-error-code-reference](docs/preview/15-error-code-reference.md) · [16-schema-hash-spec](docs/preview/16-schema-hash-spec.md) · [17-sim-ir-ir-backbone-freeze](docs/preview/17-sim-ir-ir-backbone-freeze.md) |
| HDL 레퍼런스 | `docs/preview/hdl-reference/{verilog,systemverilog,vhdl,system-tasks}` |
| 가속 분석·실측 | [18-acceleration-analysis](docs/preview/18-acceleration-analysis.md) (§실측 = profile-driven ~6x 이력) |
| **향후 과제·로드맵** | **[ROADMAP](docs/ROADMAP.md)** · 잔여작업 트래커 [REMAINING_WORK](docs/REMAINING_WORK.md) |
| 개발 이력 (슬라이스별) | [DEVLOG](docs/DEVLOG.md) (Stage C VM ~ 46탄 누적 로그) |
| 구현 계획 | `docs/superpowers/plans/` (PR1-B·PR2·M3 · [Stage C 바이트코드 VM](docs/superpowers/plans/2026-06-06-bytecode-vm-stage-c.md)) |

## 개발 주의

- **동결(freeze) 타입은 verbatim.** sim-ir 직렬화 타입 형상은 SchemaHash로 동결됨 — 필드 추가/삭제/재배열은 루트 해시를 flip시켜 전 `.velab` 무효화. 의도적 변경만(format_version bump 동반).
- **sim-ir cross-type 필드는 `sim_ir::Foo`로 FQ spelling** (`extern crate self as sim_ir`). bare 참조는 body-ref⊆key 가드(`tests/body_refs.rs`)가 거부.
- **멀티세션은 `git worktree`로 분리.** 이 모노레포를 여러 Claude 세션이 단일 체크아웃 공유 시 브랜치/HEAD가 발밑에서 바뀌어 커밋이 strand됨(실제 발생). 커밋은 항상 `git add 016_claude_rtl/<path>`로 스코프(타 프로젝트 누수 금지).
