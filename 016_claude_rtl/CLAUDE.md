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
> **현재:** 2724 테스트 green · **format_version 19** · MsgCode 57 · 3-OS CI green. **🟢 SIGPIPE: `vita design.sv | head` no-panic(2026-06-29, branch `feat-sigpipe`, cli-only·sim 무관·IR-0, ROADMAP §4.5.59)** — 외부 리포트 §6 C1. Rust 런타임이 SIGPIPE IGNORE→닫힌 pipe write 시 EPIPE→`println!` panic(exit 101). `main` 진입 시 SIGPIPE를 `SIG_DFL`로 리셋(tiny `#[cfg(unix)]` FFI·libc 없음·Windows no-op)→broken pipe서 SIGPIPE(signal 13) 종료=panic 아님. 1 통합 테스트(returncode -13·panic 없음 assert). **🏁 외부 사용자 리포트 §6 ② 후속 전량 완료(2026-06-29; A1·A3·B1·B2·C1, A2=defer-deep)** — crypto 해시 IP(Xcelium 검증) 사용자 리포트 ② 갭: **A1**(§4.5.55) 모듈 헤더 package import `module m import p::*; (…)`+undefined-name-in-range root fix(적대 2-서브 CONVERGED critical=ambiguous wildcard→silent 1-bit→`nonconst_bound_reason` detection-only loud) · **A3**(§4.5.56) 모듈 port-type을 typedef명으로 `input mode_e m`(공유 `try_port_typedef`·typedef-recognition family 종결) · **B1**(§4.5.57) `if($value$plusargs(…))` if-condition을 synthetic temp statement-form으로 desugar · **B2**(§4.5.58) typedef cast `mode_e'(raw)`=기존 size+signing cast 합성(신규 AST 0) · **C1**(§4.5.59) 위. 전부 IR-0·format 19 불변·적대 2-서브 검증·각 11~17 테스트. **A2**(array param)=저장모델 갭(params=single-i64·package-var prerequisite)=defer-deep(ROADMAP §6). 잔여=D docs sync·E file-I/O TB. **🟢 string element indexing `s[i]` read/write(2026-06-29, `feat-string-index`, IR-0, ROADMAP §4.5.54)**=PRE-EXISTING ① silent-wrong(SV `string`은 byte SEQUENCE라 `s[i]`=front-indexed char[§6.16.2]인데 vita가 read+write 둘 다 BIT-select)→기존 `.getc`/`.putc` byte 프리미티브로 `s[i]` 라우팅·non-blocking/intra-event/concat=honest-loud. 교훈=differential(probe)↔soundness(code-path) COMPLEMENTARY(soundness가 dispatch-chain 우회 MISSING-SITE 4종 발굴). 17 테스트. **🏁 typedef-recognition family 완료(§4.5.40~53, 9 슬라이스)** — 타입명이 올 수 있는 모든 parse-context(block decl·function ret·for-init·struct/union member·chained typedef·tf-port·body typedef DEF·enum base)서 user typedef 인식. ·각 멤버 IR-0·format 19·`.vu` 불변·적대 2-서브 silent-wrong ZERO. **그 외 누적 슬라이스(§4.5.2~52, 상세=ROADMAP·DEVLOG 정본)**: typedef-family 멤버(enum base·block-struct-var-shadow·body-typedef-DEF·tf-port·chained·struct/union-member·func-ret·block-local-decl·inline-func-ret-width·tf-default-args·for-init·multidim-foreach·queue-dyn-decl-init·multidim-array-pattern) · array/struct `'{…}` assignment-pattern cluster(scalar·1-D·struct-array-elem·cast-fill-width·decl-init·comma-sticky tf-port) · format cluster(signed-fieldwidth·`%0s`·`%Ns`·uppercase·`%v`·`%d/%h/%o` unknown-case·`$swrite`) · port 편의(`.name`/`.*`/defparam) · loud→supported(multi-driver/wand-wor wire·net-delay·inc/compound·break/continue·enum methods·bare `@e`·func module-var read·zero-rep `{0{x}}`) · block-local scope-leak honest-loud · 코어 스케줄러 silent-wrong 6종+UDP/N4-multi-event · honest-loud 배치 · SV cast `casting_type'(expr)` · N4 clocking 코어 · N6 real-math 21종+`$dist_*` · SVA empty-match. 전부 IR-0·format 19 불변·적대 2-서브 검증.
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

## 공개 미러 repo — vitamin-rtl-simulator (동기화 절차)

이 `016_claude_rtl`은 **upstream**(개발 원천, violet_sw 모노레포 소속). 공개 배포본은 별도 repo **[vitamin-rtl-simulator](https://github.com/tjddnr0912/vitamin-rtl-simulator)**(PUBLIC)이며 016의 **스냅샷 미러**다. 개발은 항상 여기(violet_sw/016)서 하고, 변경은 아래 절차로 미러에 반영한다.

- **동기화 방식 = snapshot sync, `git subtree`/`merge` 아님.** 미러는 2026-06-29 **단일 커밋**으로 출발 → violet_sw의 016 history와 공통 조상이 없어 subtree push는 non-FF로 거부된다. 016 파일을 미러 체크아웃에 복사 → commit → push 하는 방식만 쓴다.
- **미러에서 제외(미러 `.gitignore` 등록)**: dev-meta `LOOPROMPT.md`·`CLAUDE.md`(이 파일), 그리고 `target/`. 동기화 시 반드시 `--exclude`.
- **push 정책 (미러 main branch protection)**: owner(`tjddnr0912`)는 직접 push 가능(admin 우회 ON), 타인은 fork+PR+**승인 1건** 필수, force-push 금지. 사용자의 미러 반영은 owner 직접 push로 처리.
- **"vitamin(미러)에 sync/merge" 요청 시 절차** (violet_sw 루트에서 실행, `MIRROR`=영구 clone 경로):
  1. 미러가 없으면 영구 위치에 clone: `git clone https://github.com/tjddnr0912/vitamin-rtl-simulator.git "$MIRROR"` (⚠️ scratchpad 등 임시 위치 금지 — 세션 종료 시 소실).
  2. 016→미러 복사(dev-meta·target 제외): `rsync -a --delete --exclude=.git --exclude=target --exclude=LOOPROMPT.md --exclude=CLAUDE.md 016_claude_rtl/ "$MIRROR"/`
  3. `git -C "$MIRROR" add -A && git -C "$MIRROR" commit -m "Sync from monorepo (<원천 커밋 SHA>)" && git -C "$MIRROR" push origin main`
  - 변경 없으면 commit 스킵. 커밋 메시지에 원천 violet_sw 커밋 SHA를 넣어 추적성 확보.
