# CLAUDE.md - 016_claude_rtl (vitamin)

오픈소스 Rust RTL 시뮬레이터. CLI: `vita`(원샷) / `vcmp`(compile) / `velab`(elaborate) / `vrun`(simulate). SystemVerilog 합성가능 RTL 서브셋(Verilog-2005 RTL 전부 포함)이 Phase-1 MVP.

> **상태:** 설계 문서 완비(`docs/preview/00–17`) + 첫 코드 구현 진행 중. **PR1-B·PR2·M3 origin/main 머지 완료.** SPEC이 코드를 앞서며, `docs/preview/`가 단일 진실 공급원.

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
| 골든 루트 | `sim_ir::SimIr` (M3). 형상 변경 시 루트 해시 flip → `format_version` bump + 전 `.velab` 재생성 |
| 직렬화 | `serde` + `postcard 1.x` 단일 인코더, `blake3` 다이제스트 |

## 주요 크레이트 (실코드 / stub)

| crate | 역할 | 상태 |
|---|---|---|
| `diag` | Severity + MsgCode(36, doc-15 bijection 게이트) + LogEvent/LogSink (leaf, IO-free) | 실코드 |
| `vita-schema` | SchemaShape trait + ShapeRegistry + blake3 `schema_hash` (leaf) | 실코드 |
| `vita-artifact-derive` | `#[derive(SchemaHash)]` proc-macro (usize/f32 거부 가드) | 실코드 |
| `sim-ir` | 언어중립 IR — SuspendState 폐포 + IR 백본(Expr/Stmt/Terminator/NetVar/SimIr 루트) | 실코드 (M3) |
| `vita-artifact` | 단계 산출물 컨테이너 헤더 + schema_hash 게이트 (`format_version=2`) | 실코드 (헤더; 본문 M3+) |
| `cli` | `vita`/`vcmp`/`velab`/`vrun` multicall (argv[0] 디스패치) | stub |
| 나머지 9개 | hdl-preprocess/lexer/parser/ast · elaborate · sim-engine · hdl-builtins · vcd-writer · vita-log | stub |

## 상세 문서 (`docs/preview/`)

| 주제 | 파일 |
|---|---|
| 개요·목표·범위 | [00-overview](docs/preview/00-overview.md) · [01-goals-and-scope](docs/preview/01-goals-and-scope.md) |
| 언어·빌드·아키텍처 | [02-implementation-language](docs/preview/02-implementation-language.md) · [03-build-and-portability](docs/preview/03-build-and-portability.md) · [04-architecture](docs/preview/04-architecture.md) |
| 전략·시뮬엔진·VCD·timescale | 05-strategy-and-roadmap · 06-simulation-engine · 07-vcd-format · 08-timescale-and-timing |
| 테스트·진단·산출물 | 09-testing-and-verification · 13-diagnostics-and-logging · [14-staged-artifacts](docs/preview/14-staged-artifacts.md) |
| 에러코드·SchemaHash·IR백본 freeze | [15-error-code-reference](docs/preview/15-error-code-reference.md) · [16-schema-hash-spec](docs/preview/16-schema-hash-spec.md) · [17-sim-ir-ir-backbone-freeze](docs/preview/17-sim-ir-ir-backbone-freeze.md) |
| HDL 레퍼런스 | `docs/preview/hdl-reference/{verilog,systemverilog,vhdl,system-tasks}` |
| 구현 계획 | `docs/superpowers/plans/` (PR1-B·PR2·M3) |

## 개발 주의

- **동결(freeze) 타입은 verbatim.** sim-ir 직렬화 타입 형상은 SchemaHash로 동결됨 — 필드 추가/삭제/재배열은 루트 해시를 flip시켜 전 `.velab` 무효화. 의도적 변경만(format_version bump 동반).
- **sim-ir cross-type 필드는 `sim_ir::Foo`로 FQ spelling** (`extern crate self as sim_ir`). bare 참조는 body-ref⊆key 가드(`tests/body_refs.rs`)가 거부.
- **멀티세션은 `git worktree`로 분리.** 이 모노레포를 여러 Claude 세션이 단일 체크아웃 공유 시 브랜치/HEAD가 발밑에서 바뀌어 커밋이 strand됨(실제 발생). 커밋은 항상 `git add 016_claude_rtl/<path>`로 스코프(타 프로젝트 누수 금지).
