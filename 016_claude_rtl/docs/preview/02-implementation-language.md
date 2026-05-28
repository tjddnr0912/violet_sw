# 02 · 구현 언어 결정 (Rust)

> 설계 명세 §4 기반. 크레이트 생태계 정보는 `research-log/rust-hdl-ecosystem-2026-05-28.md` 참조.

---

## 결정

**Rust 채택.** 후보는 Rust / C++ / Go 세 가지였다.

---

## 후보 비교

| 후보 | 장점 | 단점 | 판정 |
|---|---|---|---|
| **Rust** | 메모리 안전 + C급 성능; `enum`/패턴매칭이 lexer·parser·elaborator·AST/IR 구현에 이상적; `cargo`로 3-OS 재현 빌드; GC 없어 이산사건 시뮬레이터의 결정론적 타이밍 정밀도 유지 가능 | 러닝커브; 컴파일 시간이 C++ 대비 길 수 있음 | **채택** |
| C / C++ | 검증된 EDA 경로 (Verilator=C++, Icarus=C/C++); 최고 이식성·생태계; 기존 EDA 인력 접근 용이 | 대규모 파서·시뮬레이터를 메모리 안전하게 유지·디버깅하는 부담; 크로스 플랫폼 빌드 마찰(헤더·링커 의존) | 차점 |
| Go | 단순한 언어 모델; 빠른 빌드; 쉬운 크로스컴파일 | GC 지연이 결정론적 타임스케일 정밀도·처리량에 불리; `sum type` 부재로 AST/패턴매칭 표현이 어색 | 코어 부적합 |

---

## 채택 근거

spec §4에서 합의된 근거 다섯 가지:

1. **결정론적 정밀도:** 시뮬레이터 코어는 타이트한 이벤트 루프다. GC 중단(pause)은 결정론적 타임스케일 정밀도와 처리량 모두에 부담이 된다.
2. **패턴매칭 적합성:** 3개 HDL 프론트엔드(lexer/parser/elaborator)는 대용량 BNF 문법을 다루는 영역이다. Rust의 `enum` + 패턴매칭이 AST 노드 정의와 순회에 가장 자연스럽게 맞는다.
3. **버그 = 조용한 오답:** 시뮬레이터 버그는 컴파일 에러가 아니라 잘못된 파형으로 나타난다. 메모리 안전성이 보장된 언어에서 버그 수색 범위가 크게 줄어든다.
4. **3-OS 소스 빌드:** `cargo`는 3-OS 소스 빌드를 1급으로 지원한다. C 라이브러리 의존 없이 순수 Rust 크레이트로 구성하면 크로스 플랫폼 빌드 마찰이 거의 없다.
5. **선례:** `veryl`, `spade`, `sv-parser` 등 Rust로 작성된 HDL/EDA 툴이 이미 운용 중이다.

---

## Rust 생태계 검토 (research 결과 반영)

아래 버전·URL은 2026-05-28 crates.io API 직접 조회 결과다.

### 렉서: `logos`

- **버전:** 0.16.1 (2026-01-30)
- **저장소:** https://github.com/maciejhirsz/logos
- **특징:** `#[derive(Logos)]` 매크로로 토큰 정의를 작성하면 단일 DFA로 컴파일해 수작업 렉서보다 빠른 처리량을 제공한다. 다운로드 5,389만 회 이상으로 Rust 컴파일러 툴 분야의 사실상 표준 렉서 크레이트다.
- **vitamin 적용:** `hdl-lexer` 크레이트에서 언어별(SV/Verilog/VHDL) 토큰 집합을 `logos` 기반으로 구현한다.

### 파서: `chumsky` (권장) vs. `lalrpop` vs. 수작업 RD

| 후보 | 방식 | 오류 복구 | SV 대형 문법 적합성 |
|---|---|---|---|
| **chumsky** (0.13.0) | 파서 콤비네이터 | 내장 — 여러 오류 동시 보고 | 콤비네이터로 규칙을 점진 조합; 재귀·Pratt 지원; API 진화 중 |
| lalrpop (0.23.1) | LR(1) 생성기 | 없음 — 첫 오류에서 중단 | 대형 `.lalrpop` 파일의 빌드 타임 코드 생성 비용이 큼; LR 충돌 가능 |
| 수작업 RD | recursive descent | 전적으로 직접 구현 | 최고 유연성; 유지보수 비용 높음 |

**권장: `chumsky`.** SV 문법은 Annex A 기준 약 1,800개 이상의 규칙을 갖는 대형 BNF다. lalrpop은 오류 복구 부재와 대형 문법에서의 빌드 타임 코드 생성 비용이 단점이다. chumsky는 오류 복구를 1급으로 지원하고, 재귀적 계층 구조·Pratt 표현식 파서를 콤비네이터로 표현할 수 있어 진단 품질 목표에 부합한다. v0.13은 API 안정화 진행 중이므로 고정 버전 핀닝과 API 변경 추적을 병행한다.

### 진단: `ariadne` / `codespan-reporting`

- **ariadne** 0.6.0 (2025-10-28, MIT): 인라인·멀티라인 레이블, 팬시 터미널 출력. chumsky와 같은 저자(zesterer)라 두 크레이트의 오류 타입 연동이 자연스럽다. MSRV 1.85.
- **codespan-reporting** 0.13.1 (2025-10-22, Apache-2.0): 성숙도 높고(1억+ 다운로드) note 복수 첨부 가능.
- **vitamin 방침:** `diag` 크레이트 설계 단계에서 최종 선택. chumsky를 파서로 쓸 경우 ariadne 연동이 더 매끄럽다.

### SystemVerilog 파싱 선례: `sv-parser`

- **버전:** 0.13.5 (2026-03-30, MIT OR Apache-2.0)
- **저장소:** https://github.com/dalance/sv-parser (472 stars)
- **특징:** IEEE 1800-2017 완전 준수 표방. Annex A 문법 규칙 이름과 1:1 대응하는 CST(구체 구문 트리) 반환. `svlint` 등 다운스트림 도구에서 사용 중.
- **활용:** vitamin은 sv-parser를 직접 의존성으로 쓰지 않는다(자체 파이프라인 구축). 그러나 SV 문법 규칙 명세 대조 시 이 크레이트의 규칙 이름 매핑을 참고 자료로 활용한다.

### 신규 HDL 선례: `veryl`, `spade`

- **veryl** 0.20.0 (2026-05-01, MIT OR Apache-2.0): 942 stars. SV를 transpile 대상으로 삼는 현대적 HDL. Rust로 전체 파이프라인(lexer/parser/elaborator/codegen) 구현. 프론트엔드 아키텍처 참고.
- **spade**: Rust + Clash 영감의 HDL. GitLab 주 저장소(GitHub mirror 65 stars). Rust 타입 시스템 기반 HDL 컴파일러 구현 사례. Surfer 파형 뷰어(Rust)도 동반 개발 중.

### VCD 참고: `vcd` 크레이트

- **버전:** 0.7.0 (MIT, 마지막 업데이트 2023-07-15)
- **저장소:** https://github.com/kevinmehall/rust-vcd
- **특징:** IEEE 1364 VCD 읽기/쓰기 API 제공. `Writer` 타입으로 헤더·`$var`·값 변화(`0/1/X/Z`) 직렬화를 지원한다.
- **vitamin 방침:** 직접 채택하지 않는다. 2023년 이후 업데이트가 없어 유지보수 정체 상태이므로, vitamin은 `vcd-writer` 크레이트를 자체 구현한다. API 설계 선례로 참고.

---

## MSRV / Toolchain

- **계획 MSRV:** Rust **1.80** (stable, 2024-07-25 릴리스). `std::sync::LazyLock` 안정화를 포함하는 세대다 (참고: `OnceLock`은 1.70, `let-else`는 1.65에 각각 안정화됐다). 실제 기능 사용 패턴에 따라 상향 조정할 수 있으며, `rust-toolchain.toml`에 명시한다.
- **`rust-toolchain.toml` 사용:** 저장소 루트에 고정해 `cargo build`/`cargo test` 실행 시 자동으로 toolchain을 맞춘다. CI 및 로컬 개발 환경이 동일한 Rust 버전을 사용하도록 보장한다.
- **ariadne MSRV 참고:** ariadne v0.6.0의 MSRV가 1.85이므로, ariadne를 채택할 경우 MSRV를 1.85 이상으로 올려야 한다. 최종 MSRV는 채택 크레이트 MSRV 집합의 상한으로 결정한다.

---

## Sources

- 본 spec §4 — `/docs/superpowers/specs/2026-05-26-vitamin-rtl-simulator-design.md`
- research-log: `research-log/rust-hdl-ecosystem-2026-05-28.md`
- crates.io API: https://crates.io/api/v1/crates/{sv-parser,logos,chumsky,lalrpop,ariadne,codespan-reporting,vcd,veryl}
- GitHub: https://github.com/dalance/sv-parser, https://github.com/maciejhirsz/logos
- Codeberg: https://codeberg.org/zesterer/chumsky
- GitHub: https://github.com/lalrpop/lalrpop, https://github.com/zesterer/ariadne
- GitHub: https://github.com/brendanzab/codespan, https://github.com/kevinmehall/rust-vcd
- GitHub: https://github.com/veryl-lang/veryl, https://gitlab.com/spade-lang/spade
