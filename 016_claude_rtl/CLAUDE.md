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
> **현재:** 2269 테스트 green · **format_version 19** · MsgCode 57 · 3-OS CI green. **🟢 YELLOW 구현 배치(2026-06-26, branch `feat-yellow-batch`, 전부 IR-0·format 19 불변; §4.5.3 YELLOW 9종을 1→9→2→4→5→8→3→6→7 순서로 슬라이스별 사전 그라운딩→구현→사후 적대 리뷰→커밋, ROADMAP §4.5.4)**: **구현 5종** — ① **comb UDP** `primitive…endprimitive`(`20a2170`, 파서 desugar→합성 module·casez 미사용·4-state `===`·충돌 0>1>x·미매치→x; 리뷰가 **CRITICAL z→x 입력변환 누락 §29.3.4 차단**) · ② **sequential UDP**(`afe842c`, 리터럴 §29 상태표 평가기[level-first→edge→no-match→x·shadow-reg·`-`=hold]; self-fuzz ~4150 + 독립 5-렌즈 리뷰 0 real div·**wire출력+seq테이블 loud-gap 수정**) · ③ **N4 multi-event clock** `@(posedge c1 or c2)`(`09a2ee7`, 가드 N≥1 all-edge + **pre-existing 코어 스케줄러 버그 수정**: 일반 multi-edge always 동시-엣지 2회 실행[vita 5 vs iverilog 4]→`propagate_changes` per-delta 디둡) · ④ **SVA nested prop-ref skew**(`0b8535a`, 깊은 동종 `|=>` 체인 재귀 peel[§16.12 `|=>`당 `##1` 1개]; 오라클 없음→vita-내부 차분 ~2000 fuzz 0 skew miscount; 리뷰가 **CRITICAL prop-op obligation silent-drop 차단**) · ⑤ **SVA local-var later-antecedent read**(`ae5a920`, `data_chain[S-1]` 치환[S=고정hop합=컴파일타임상수]; vita-내부 차분 0 stage miscount). **honest-loud 유지 4종**(정확도 최우선상 오라클 없이 강행 거부) — N4 inout·N4 cross-hier `@(u0.cb)`·N4 `#0` skew·SVA empty-match `##0` 융합. **부수 발굴: pre-existing 코어 스케줄러 silent-wrong 6종**(블로킹 글리치 wake-collapse·self-retrigger·gated-clock cross-delta double-fire·mixed-edge t0·`always @*` t0 kick — 각 별개 슬라이스). 적대 방법론: **iverilog가 모든 concurrent assertion 거부→SVA는 vita-내부 차분**을 teeth로 사용. **🟢 이전 Honest-loud 배치(2026-06-26, branch `feat-hlb`, 전부 IR-0·format 19 불변; 트리아지 24항목→GREEN 구현·YELLOW/RED는 ROADMAP §4.5.3 문서화→사람 재결정)**: 슬라이스마다 구현→iverilog 차분→적대 리뷰→커밋, **적대 리뷰가 CRITICAL silent-wrong 3종 차단**. (1) **gate/assign rise·fall·turnoff 지연 silent-wrong 수정**(`080c424`): vita가 `#(rise,fall[,turnoff])`를 파싱하나 모든 전이에 rise만 적용하던 broad silent-wrong→IR-0 `ca_delays` 사이드카(값 다를 때만=byte-identical), atomic-at-max per-bit dest-delay(→1 rise/→0 fall/→z turnoff/→x min), baseline=gate 자체 last-landed 출력(`last_ca_drv`)=inertial supersede 정확(적대 리뷰가 prev-RHS baseline supersede CRITICAL 발굴→수정). (2) **real→longint/time cast**(`5a2836d`): IR-0 hi/lo real-도메인 분해(trunc-toward-zero·`{hi,lo}`)·bit-exact; 적대 리뷰가 `+0.5` pre-add의 odd-int [2^52,2^53) off-by-one CRITICAL 발굴→frac 직접계산 수정. (3) **string concat 비대입 컨텍스트**(`c4e371b`): `{a,b}` in $display/비교/중첩/replicate→공유 헬퍼·`$sformatf` 표현식 평가기. (4) **typed for-init**(`6282c9c`): `for(int i=0;…)`=parser-only synthetic-rename block-local(동명 모듈넷 alias 방지). (5) **named-type 패킹구조체 필드 폭 silent-wrong 수정 + ascending 멤버 write**(`d681f04`): `int a;` 멤버가 1-bit로 깔리던 silent-wrong→kind 기반 폭(int=32 등)·signedness·2-state init; ascending part-select WRITE(상수 range/bit, field-bounded). (6) **class local/protected 접근제어**(`f39b816`, AST flip `.vu` 재핀·format 19 불변): IEEE §8.18 강제(elaborate accessing-class context); iverilog under-enforce→correct-or-loud-stricter. 발견된 pre-existing silent-wrong 2종(NaN/inf real→int=garbage·struct ascending indexed READ `s.f[2+:2]`)=§4.5.3 기록. **🟢 SVA/cast 기능 + C-perf 승격 배치(2026-06-26, branch `feat-sva-cast-perf-batch`, 전부 IR-0·format 19 불변)**: ② SVA 잔여 대부분 완료 — empty-match 고정 비-`##1` 양측 융합 P1(`a ##h_in b[*0:n] ##h_out c`, 순지연 D=(h_in-1)+h_out, `d6eb523`)·cross-clock multi-term segment(segment별 `synth_seq_match` per-clock 파이프라인+핸드오프, `af527fc`, 부수로 paren subsequence·grouped rep 파서)·prop-ref skew seq-antecedent(`seq\|->q`≡`(seq##0 b)\|=>c`·`seq\|=>q`≡`(seq##1 b)\|=>c`, `677461d`). **N2c seq local var 단일-capture(`374f7cd`+`493fe10`)**=병렬 데이터 시프트 레지스터(`(req,d=data)##1 grant\|->(rdata==d)`·attempt별 stage 분리=back-to-back 정확·고정-delay만, 범위형=loud; 적대 리뷰가 real/string type 1-bit silent-truncation 발굴→type 가드 fix). **SVA-QUAD collapse(`7826c84`+`95bd154`)**=O(N²)→O(N) sliding-OR(`SeqHop::Range`)·`VITA_SVA_COLLAPSE` opt-in flag·default OFF=byte-identical shipped·old-impl-as-oracle 차분 17종 0 divergence(directed+800-fuzz+fault-injection)·cap-boundary fix. ⑤ class cast `Base'(d)` UP-CAST(`f84df82`, 핸들 identity·down-cast/미해소/cast-as-receiver=loud). **C-perf 3종 사용자규칙 승격·구현(전부 byte-identical)**: WAITER-POOL part2(`06db8ce`)·DYN-HEAP-VEC(`768b5c7`, BTreeMap→Vec)·FORCE-REEVAL part2(`b66c708`+`331056a`; **적대 리뷰가 force-chain freeze critical silent-wrong 발굴→fixpoint fix**). 22-에이전트 순차 워크플로(slice별 implement→적대 review→fix; 적대 리뷰가 critical 1·important 1 silent-wrong 차단). **🟢 unknown-value `%d/%h/%o` 대소문자 silent-wrong 수정(2026-06-25, IR-0)**: IEEE §21.2.1.2 — unknown 필드는 UNIFORM(known 없고 단일 종류)일 때만 소문자(all-x→`x`·all-z→`z`), 섞이면(known+unknown 또는 x+z) 대문자(`X`/`Z`). vita가 모든 unknown을 소문자 `x`로 뭉개던 broad pre-existing 버그(`fmt_dec`/`fmt_radix`, all-z=`x`·partial=소문자·mixed=소문자). cast 적대 hunt가 부수 발견→별도 슬라이스로 수정(iverilog-pinned, %h/%o는 per-digit). **🟢 ① SV cast `casting_type'(expr)` 완성(2026-06-25, 2041 green, IR-0·format_version 19 불변·`.vu` 재핀)**: 숫자/size/signing 전부(int/byte/shortint/longint/integer/bit/logic/reg/time/real·`N'(e)`·`W'(e)` 파라미터 폭·signed'/unsigned'). 렉서 `'` 토큰(longest-match additive=기존 `8'hFF`/`'0` 불변)+파서 2-hook(keyword arm+postfix)+elaborate IR-0 lowering(size=`Concat`-extend로 sign·Z 보존+sign 상속·real round-half-away `$rtoi(e±0.5)`·2-state X→0 per-bit `===1'b1` case-eq). 구현 전 4-lens deep-review(spec+live iverilog oracle)로 계획 보강. **구현 후 적대 2-round hunt가 silent-wrong 3종 발굴→전량 수정**: 광폭-signed가 zero-extend되던 것(→sign-extend)·extend가 Z→X 손상(`z\|0=x` 회피, `Concat` 4-state 보존)·real-fn-call 미감지(`int'(real_fn())`/`int'(-real_fn())`가 IEEE-754 bit-reinterpret→AST real-call 감지+unary/arith 재귀). class/typedef-name cast `Base'(d)`·real→longint=오라클 부재/스코프 honest-loud(잔여). (cast hunt가 부수 발견한 pre-existing `%d/%h/%o` 대소문자 silent-wrong=상단 별도 슬라이스로 수정 완료). **🟢 ④ N4 clocking 기능 코어 완성**(2026-06-25, 입력 샘플링 + `@(cb)`): elaborate `lower_clocking_blocks`(holding net + 사이드카) + engine **Preponed 리전 sampler**(time-advance 스냅샷→`preponed_buf`·clocking edge 감지 시점 `propagate_changes`에서 holding net commit=tie 무관·모든 same-slot reader 일치). `cb.sig`=preponed(슬롯 진입값·race 면역)·`@(cb)`=clocking event. v1=default-skew INPUT; output/skew/multi-clock/anonymous/non-net-bind/input-drive(계층 포함)=honest-loud. 비-clocking 코퍼스 byte-identical. 적대 2-round 리뷰 silent-wrong/loud-gap 4종 발굴→전량 수정(write-input·cross-hier stale·계층 drive·event 메시지). N6는 **vendored 순수-Rust libm**(`third_party/libm`, `default-features=false` → arch intrinsic 없음 → 3-OS 비트 동일)로 계산. 동반 silent-wrong fix: real `%f/%e/%g`의 NaN 대문자(`NaN`→`nan`)·음의 0(`-0.0`→`0`) 표시. `$dist_*` 비균등은 **seed 스트림=iverilog 바이트 동일**(정수 Annex LCG)·**결과 int=3-OS hand-IEEE 핀**(D3=내부 결정성 우선, iverilog 대비 ±1 가능). **🟡 ② SVA empty-match `[*0:n]`/`[*0:$]`/`[*]` `##1`-인접 슬라이스 완료**(2026-06-25, IR-0): `a ##1 b[*0:n] ##1 c`(≡`a ##1 c`)·suffix·multi-empty 지원; 적대 2-round 리뷰가 trailing-`##0` silent-wrong 발굴→`##1`-인접 가드로 correct-or-loud(비-`##1` 인접 융합은 §16.9.2.1 미묘+오라클 부재라 honest-loud).
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
