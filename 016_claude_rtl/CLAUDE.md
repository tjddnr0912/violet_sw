# CLAUDE.md - 016_claude_rtl (vitamin)

오픈소스 Rust RTL 시뮬레이터. CLI: `vita`(원샷) / `vcmp`(compile) / `velab`(elaborate) / `vrun`(simulate). SystemVerilog 합성가능 RTL 서브셋(Verilog-2005 RTL 전부 포함)이 Phase-1 MVP.

## 코드 리뷰 방법론 (구현·설계 이후 리뷰 단계)

- **적대적 코드 리뷰** — 라이브 차분(iverilog 등)으로 silent-wrong을 실제 재현해 검증.
- **Fagan Inspection** — 역할(Sub-agent)을 **Author / Moderator / Reviewer / Recorder** 로 분리해 진행.
  - 사전 정의 체크리스트는 **Spec 문서**(`docs/preview/`)로 대체. 별도 체크리스트가 있으면 대체가 아니라 **합산**.
  - 코드의 **논리적 오류**를 검증.
- 리뷰 관점 4축: **Architecture & System Integration** · **Performance & Efficiency** · **Maintainability & Readability** · **Robustness & Testability**.

> **상태:** **전 파이프라인 동작** — one-shot `vita design.sv`, staged `vcmp→velab→vrun` 모두 VCD+stdout 산출. 구현 범위:
> - **Phase-1** 합성 RTL 대부분 — timescale·다차원 unpacked/packed 배열·casex/casez·fork-join·func/task·SV 자료형(enum/typedef/packed struct).
> - **Phase-2** — worklib·package·string·dynamic/queue/assoc 배열·정밀화 IR.
> - **Phase-3+** — SVA 시퀀스·property ops·`cover property`(SVA-REST)·deferred immediate assert·automatic/recursive 콜스택·HIER-REST(계층 참조)·functional coverage·N7 class/OOP(상속+가상 동적 디스패치)·constrained-random verification(rand/constraint/`randomize() with`/dist/randc)·array·string 메서드·program/union/parameterized class/virtual interface·**N6 real-math**(`$ln/$sin/$exp/$sqrt/$pow/$floor/$ceil/…` 21종 §20.8.2 + 비균등 `$dist_normal/exponential/poisson/chi_square/t/erlang`, vendored 순수-Rust libm).
> - **정확성 원칙 = "correct-or-loud"**: silent-wrong은 적대 리뷰(라이브 iverilog 차분)마다 모조리 수정. iverilog 미지원분(SVA·OOP·CRV·param-class·virtual interface)은 hand-IEEE 핀.
>
> **현재:** 2351 테스트 green · **format_version 19** · MsgCode 57 · 3-OS CI green. **🟢 break / continue loop control(2026-06-27, branch `feat-break-continue`, IR-0·format 19·`.vu` 전부 불변, ROADMAP §4.5.13)** — vita가 undeclared-task(E3010)로 거부하던 SV §11.5 `break`/`continue`를 **loud→supported**. 고전 Verilog `disable <label>` idiom으로 **파서 desugar**: `continue` 루프는 바디를 `begin:$continue$N … end`로 감싸고(continue→해당 블록 disable→루프 continue-point로 Goto)·`break` 루프는 전체를 `begin:$break$N … end`로 감쌈(break→루프 past로 Goto). vita의 **기존 `disable`→Goto lowering 재사용**→AST/IR/sim-ir/`.vu` 전부 무변경(기존 `Stmt::Disable`/`Stmt::Block` 노드). break/continue 없는 루프=unwrapped→byte-identical. `LoopLabels` 스택·`parse_loop_body`/`wrap_break`/`parse_break_continue` 헬퍼·dispatcher `break;`/`continue;` 인식(뒤 `;` 한정→`break=x;` 변수 호환). for/while/repeat/forever/foreach/do-while 6 루프 전부. fork-cross·루프밖=loud(disable fork-floor 재사용)·unrolled repeat·중첩·typed-for는 idiom으로 자연 처리. 적대 2-서브에이전트가 **silent-wrong 1종 발굴→수정**: `parse_do_while`만 `parse_loop_body` 미사용→do-while 안 break/continue가 enclosing 루프 타깃(중첩 시 outer 잘못 종료/continue)→`parse_do_while`도 동일 적용. soundness은 이를 'honest-loud'로 분류했으나 differential이 silent-wrong 입증→differential 우선. 재-hunt CLEAN. **🟢 increment/decrement + compound assignment `i++`/`i += e`(2026-06-27, branch `feat-inc-compound`, IR-0·format 19·`.vu` 전부 불변, ROADMAP §4.5.12)** — vita가 PARSE-거부하던 SV §11.4 `i++`/`++i`/`i--`/`--i` + 12 compound op(`+= -= *= /= %= &= |= ^= <<= >>= <<<= >>>=`)를 **loud→supported**. statement/for-init·step 형태는 순수 shorthand(`i+=e`≡`i=i+e`·`i++`≡`i=i+1`·pre/post 폐기 시 동일)라 **파서에서 기존 `Stmt::Blocking`으로 desugar**(신규 AST 타입 없음→AST `.vu` 해시도 불변). expression-embedded(`a=i++`, side-effect ordering)는 honest-loud(Pratt expr 파서 미추가→parse error). 렉서 14 신규 토큰·logos longest-match가 SVA `|=>`/`|->`·unary `+`/`-`·`<=`·`<<<`/`>>>` 분리 보장. 헬퍼 `lvalue_to_expr`(역 `expr_to_lvalue`)·`try_compound_assign`·`parse_pre_incdec`→3 사이트 배선. 적대 2-서브에이전트 differential **CLEAN**(55 probe·전 op/타입/lvalue/for-step/wrap/산술시프트/loud경계/렉서 byte-identity)·soundness **SOUND**(Minor 4 전부 진단/문서·silent-wrong 0); **double-eval 우려를 측정으로 반증**(`arr[f()]+=5`≡explicit byte-identical·`calls=0`은 plain assign도 동일한 pre-existing quirk). honest-loud: generate-for step `g++`(iverilog 자체 all-Z=오라클 부재). **🟢 net-declaration delays `wire #3 w = a;`(2026-06-27, `feat-net-delay`, IR-0·format 19 불변[AST `.vu` re-pin], ROADMAP §4.5.11)**: IEEE §6.1.3 net-decl delay를 등가 `assign #d`로 desugar(파서 `NetVarDecl.delay`+elaborate `fold_ca_delay`→`ca_delays` 사이드카·staged 무료). 적대 differential이 silent-wrong 2종(generate net-init driver drop·procedural delay swallow) 발굴→수정·재-hunt CLEAN·byte-identical. **🟢 wand/wor wired-logic net resolution(2026-06-27, `feat-wand-wor`, IR-0·format 19 불변, ROADMAP §4.5.10)**: §4.5.9 후속—`wand`/`wor` 다중드라이버를 IEEE 1364 wired-AND/OR 4-state resolution **loud→supported**(plain `Wire`+`wired_and/or_nets` 사이드카·3 net-생성 경로 전부+staged trailer). 적대 differential이 CRITICAL 1건(output 포트 사이드카 누락→wire-x) 발굴→수정·재-hunt CLEAN·byte-identical. 잔여: `inout wand/wor`=기존 inout 갭. **🟢 multi-driver continuous-assign wire resolution(2026-06-27, `feat-multidriver`, IR-0·format 19 불변, ROADMAP §4.5.9)**: tristate/양방향 버스(E3001 hard-reject)→IEEE 1364 4-state wire resolution **loud→supported**(whole-net·non-delayed ≥2; partial-overlap loud 잔존). 적대 2-서브(differential 70+ probe·soundness 16-combo 전수증명) 둘 다 CLEAN·byte-identical. **🟢 코어 스케줄러 silent-wrong 연속 수정 + YELLOW 구현 배치(2026-06-26~27, 전부 IR-0·format 19 불변; 상세=ROADMAP §4.5.4~§4.5.8 · git 커밋)**: 스케줄러 #1/#2 글리치 wake-collapse·#3 self-retrigger·#4 gated-clock edge-collapse·narrow→wide 4-state posedge(`feat-sched-*` 5브랜치)·UDP(comb/seq)·N4 multi-event·SVA nested prop-ref/local-var(`feat-yellow-batch` 구현 5+honest-loud 4). **전부 적대 2-서브에이전트가 CRITICAL silent-wrong 발굴→수정**·byte-identical. 잔존 #5 mixed-edge t0·#6 `@*` t0/observer/Comb. **🟢 이전 배치(2026-06-26, 전부 IR-0·format 19 불변; 상세 = ROADMAP §4.5.3 · git 커밋)**: **Honest-loud 배치**(`feat-hlb`, 적대 리뷰 CRITICAL 3종 차단): gate rise/fall/turnoff 지연·real→longint cast·string concat 비대입·typed for-init·패킹구조체 필드폭+ascending write·class local/protected 접근제어 · **SVA/cast+C-perf 배치**(`feat-sva-cast-perf-batch`, 적대 리뷰 critical 1+important 1 차단): SVA empty-match 양측융합·cross-clock multi-term·N2c local-var·SVA-QUAD O(N) collapse(opt-in)·class up-cast·WAITER-POOL/DYN-HEAP-VEC/FORCE-REEVAL. **🟢 이전 배치(2026-06-25, 전부 IR-0·format 19 불변; 상세 = ROADMAP §4.5.2 · DEVLOG)**: ① **SV cast `casting_type'(expr)`**(숫자/size/signing·`N'(e)`·signed'/unsigned'; 4-lens 사전 review + 적대 2-round hunt silent-wrong 3종 수정[광폭 sign-extend·Z보존·real-fn bit-reinterpret]) · ④ **N4 clocking 코어**(Preponed sampler·`cb.sig`=preponed·`@(cb)`; 적대 4종 수정) · **N6 real-math 21종 + 비균등 `$dist_*`**(vendored 순수-Rust libm→3-OS 비트동일·real NaN/-0 표시 fix) · ② **SVA empty-match `##1`-인접**(trailing-`##0` silent-wrong→가드) · **`%d/%h/%o` unknown 대소문자**(§21.2.1.2 UNIFORM-소문자/혼재-대문자).
>
> 슬라이스별 누적 개발 이력(Stage C VM ~ 최신) → **[docs/DEVLOG.md](docs/DEVLOG.md)**(§누적 상태 로그 = 이 블록의 옛 상세를 이관). 향후 과제·전략 = **[docs/ROADMAP.md](docs/ROADMAP.md)**, 잔여 작업 트래커 = [docs/REMAINING_WORK.md](docs/REMAINING_WORK.md). SPEC `docs/preview/`가 단일 진실 공급원.

## 실행 (cargo-only · vita 자체 크레이트엔 build.rs 없음)

```bash
cargo build  --workspace --locked                       # 17-crate 워크스페이스 (15 prod + 2 dev)
cargo test   --workspace --locked                       # 결정성 골든 게이트 포함
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo fmt --all -- --check
```

MSRV **1.82** (`rust-toolchain.toml` 고정), **edition 2021**(edition 2024는 rustc≥1.85라 비호환). `blake3 = "=1.8.2"` 핀. `--locked` 필수(3-OS 재현성). **vendored libm**: `third_party/libm`(libm 0.2.16, MIT)는 path dep지만 `[workspace].exclude`로 **member 아님**(clippy `--workspace -D warnings`가 third-party 미린트). build.rs는 vita 자체 17 크레이트엔 없음 — vendored libm은 타겟 cfg 감지 build.rs를 가지나(deterministic), blake3/serde 등 기존 의존성도 이미 build script 보유.

## 핵심 정보

| 항목 | 값 |
|---|---|
| 파이프라인 | preprocess→lex→parse→elaborate→sim-ir→sim-engine→VCD (parse까지 언어의존, 이후 중립) |
| 결정성 | `#[derive(SchemaHash)]` 구조적 형상 해시로 `.velab`/`.vu` staleness 게이트, 3-OS 바이트 동일 (BTree-only, usize/float 금지, span-free) |
| 골든 루트 | `sim_ir::SimIr`. 형상 변경 시 루트 해시 flip → `format_version` bump(현재 **19**, 정의·버전별 주석은 `crates/vita-artifact/src/header.rs::CURRENT_FORMAT_VERSION`) + 전 `.velab` 재생성. 엔진-facing 사이드테이블(fork_modes·net_names·proc_multipliers·final_procs·wait_fork·sva 체커·deferred-assert 마커·frame nets·class_rand/constraints/dist/randc 등)은 `SimOpts`/elaborate IR-0 합성으로 out-of-band → 골든 무영향 |
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
| `vita-artifact`(+derive)·`vita-schema`·`diag` | 산출물 헤더+게이트(`format_version=18`) · SchemaHash · MsgCode(57, doc-15 bijection) | 실코드 |
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
| 개발 이력 (슬라이스별) | [DEVLOG](docs/DEVLOG.md) (Stage C VM ~ 51탄 + §누적 상태 로그=옛 상태 블록 이관분) |
| 구현 계획 | `docs/superpowers/plans/` (PR1-B·PR2·M3 · [Stage C 바이트코드 VM](docs/superpowers/plans/2026-06-06-bytecode-vm-stage-c.md)) |

## 개발 주의

- **동결(freeze) 타입은 verbatim.** sim-ir 직렬화 타입 형상은 SchemaHash로 동결됨 — 필드 추가/삭제/재배열은 루트 해시를 flip시켜 전 `.velab` 무효화. 의도적 변경만(format_version bump 동반).
- **sim-ir cross-type 필드는 `sim_ir::Foo`로 FQ spelling** (`extern crate self as sim_ir`). bare 참조는 body-ref⊆key 가드(`tests/body_refs.rs`)가 거부.
- **멀티세션은 `git worktree`로 분리.** 이 모노레포를 여러 Claude 세션이 단일 체크아웃 공유 시 브랜치/HEAD가 발밑에서 바뀌어 커밋이 strand됨(실제 발생). 커밋은 항상 `git add 016_claude_rtl/<path>`로 스코프(타 프로젝트 누수 금지).
