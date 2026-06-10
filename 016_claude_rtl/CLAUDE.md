# CLAUDE.md - 016_claude_rtl (vitamin)

오픈소스 Rust RTL 시뮬레이터. CLI: `vita`(원샷) / `vcmp`(compile) / `velab`(elaborate) / `vrun`(simulate). SystemVerilog 합성가능 RTL 서브셋(Verilog-2005 RTL 전부 포함)이 Phase-1 MVP.

> **상태:** **전 파이프라인 동작** — one-shot `vita design.sv` + staged `vcmp→velab→vrun` 모두 시뮬레이션해 VCD+stdout 산출. timescale(doc-08 전체 모델)·다차원 unpacked·packed 배열·VCD 계층 naming·casex/casez·fork-join·func/task·**SV 자료형(enum/typedef/packed struct)** 등 Phase-1 합성 RTL 대부분 구현·검증(**460 테스트 green, iverilog 차분 일치**). 6축 감사 52항목+후속 큐 5항목 전부 클리어. 혼합-timescale postponed `$strobe`/`$monitor` multiplier 버그 수정(`fbb869c`) + 멀티-top 다중 root elaborate 수정(미인스턴스 모듈 전부를 root로, 골든 무영향).
>
> **Stage C 컴파일드 백엔드(바이트코드 VM) — C1·C2 완료**(`Backend::Bytecode`가 suspend-free P9 클래스를 VM 실행, P5 차분 게이트가 인터프리터와 byte동일 강제, frozen sim-ir 무변경). **profile-driven 최적화 4R로 누적 ~6x**(eval-heavy 2781→461ms; net I/O·shift·resize word化 + inline-Value, 전부 interp·VM 공유 경로). **🔨 native-eval C4-lite 착수**(`native_eval.rs`): ≤64bit 정수 서브셋(Const·Signal·Add/Sub/Mul·비트연산·Not/Plus/Minus)을 VM 전용 native 레지스터로 평가, 그 외는 `eval_ctx` fallback — **식-바운드 expr-heavy VM 0.92x→0.42x(≈2.3x)**, 클럭-바운드 불변, 인터프리터=오라클·P5 차분게이트 byte동일 강제, frozen sim-ir 무변경. **향후 과제·전략 = [`docs/ROADMAP.md`](docs/ROADMAP.md), 잔여 트래커 = [`docs/REMAINING_WORK.md`](docs/REMAINING_WORK.md)(2026-06-10 7축 감사로 전면 리뉴얼 — P0 silent-wrong 정확성 9 · P1 의미론 9 · P2 운용 12 · P3 메모리 5 · **P4 병렬화 트랙 신설**(`--threads` 설계, byte-identical 계약) · P5 문서부채; Gemini shift fix 검토·채택 포함), perf 이력 = doc-18 §실측.** SPEC `docs/preview/`가 여전히 단일 진실 공급원. **2026-06-10 감사 트래커 전 항목 소진(571 green): P0~P5 전체**(severity `$fatal`=exit1·radix b/o/h·`%m`·in-body @(*)·finish-flush·per-bit 멀티드라이버·E3018/W3056/E-DUP-UNIT·`--help/--version/--threads/--timeout`·VCD/델타 진단·원자적 아티팩트·parser/array 캡·fork free-list 등) **+ P4 T1 `--threads` VCD writer 스레드(byte-identical 게이트) + native-eval 확장(비교/시프트/DivMod/ternary/리덕션/논리 — expr-heavy VM 0.42x) + P2-12 정책(`time` 타입 64-bit unsigned 수용·`` `pragma`` 수용-무시·timescale clamp·implicit-net=E3010 명문화) + P5 문서 동기화(-W* 미래형·예약 codes·exit 0/1/3 실태)**. 사이드테이블 7종은 `Sidecars` 번들로 통합(.velab trailer 세그먼트 append-only). **같은 날 후속 2탄: perf 축 + Phase-1.x 전체 소진(HEAD `8664627`, 611 green)** — 스케줄러축 라운드1(클럭-바운드 ≈1.85x, 핫루프 할당 9원 제거) · native-eval 구조 lane(select/concat/replicate, STRUCT_HEAVY VM 0.36x) · vita-log `-Wno-*`/`-Werror=` 게이트+exit class 2 · filelist `-f`/`-F` · `vita explain` · **format_version 4**(런타임 `#delay`=ExprId 평가, `$dumpflush`/`$dumplimit`, REGEN_GOLDEN 스위치) · force/release(sample-once, per-net forced 플래그). vita-log는 이제 실코드(stub 1개=hdl-builtins만). 다음 후보 = REMAINING_WORK §권장(잔여: +incdir+/+define+ 버킷, dirty-list 스케줄러 라운드2, >64bit/real native lane).

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
| 골든 루트 | `sim_ir::SimIr`. 형상 변경 시 루트 해시 flip → `format_version` bump(현재 **4**, 런타임 delay 진화) + 전 `.velab` 재생성. 엔진-facing 사이드테이블(fork_modes·net_names·proc_multipliers)은 `SimOpts`로 out-of-band → 골든 무영향 |
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
| `vita-artifact`(+derive)·`vita-schema`·`diag` | 산출물 헤더+게이트(`format_version=4`) · SchemaHash · MsgCode(50, doc-15 bijection) | 실코드 |
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
| 구현 계획 | `docs/superpowers/plans/` (PR1-B·PR2·M3 · [Stage C 바이트코드 VM](docs/superpowers/plans/2026-06-06-bytecode-vm-stage-c.md)) |

## 개발 주의

- **동결(freeze) 타입은 verbatim.** sim-ir 직렬화 타입 형상은 SchemaHash로 동결됨 — 필드 추가/삭제/재배열은 루트 해시를 flip시켜 전 `.velab` 무효화. 의도적 변경만(format_version bump 동반).
- **sim-ir cross-type 필드는 `sim_ir::Foo`로 FQ spelling** (`extern crate self as sim_ir`). bare 참조는 body-ref⊆key 가드(`tests/body_refs.rs`)가 거부.
- **멀티세션은 `git worktree`로 분리.** 이 모노레포를 여러 Claude 세션이 단일 체크아웃 공유 시 브랜치/HEAD가 발밑에서 바뀌어 커밋이 strand됨(실제 발생). 커밋은 항상 `git add 016_claude_rtl/<path>`로 스코프(타 프로젝트 누수 금지).
