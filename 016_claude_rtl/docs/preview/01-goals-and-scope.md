# 01 · 목표 · 범위 · 성공 기준

## 목표 (in-scope)

이하 항목이 본 프로젝트의 구현 범위다.

- **HDL 소스 전체 파이프라인**: preprocess → lex → parse → elaboration → simulation.
  각 단계는 독립 크레이트로 분리해 단위 테스트가 가능하다.
- **단계별 실행 모델**: `vita` 원샷(compile→elaborate→simulation 일괄) 외에, 단계별 명령
  `vcmp`(compile)·`velab`(elaborate, vcmp 산출물 소비)·`vrun`(simulation, velab 산출물 소비)으로
  나눠 실행할 수 있다. 단계별 독립 빌드·디버깅, 변경 없는 단계 스킵(산출물 재사용)을 지원하며,
  상용 EDA(Cadence·Synopsys)의 compile/elaborate/simulate 분리에 대응한다 (§4 아키텍처).
- **문법 검사** — parse 단계에서 수행. 오류는 소스 위치와 함께 진단 출력.
- **elaboration 단계 점검 항목** — 파라미터 해소, 계층 연결성, 타입/포트 정합, 미연결 신호, 다중구동(multiple driver) 등.
- **이벤트 구동(event-driven) 시뮬레이션 커널** + `timescale` 기반 정밀 시간 모델 (§6).
- **VCD 파형 생성 (IEEE 1364)** — RTL 내 dump 시스템 태스크 호출 시에만 활성; 자동 항상-덤프 아님.
  CLI 편의 플래그(`vrun --force-dump`)는 후속 옵션으로만 검토하며, 기본은 RTL이 주도한다.
- **표준 Verilog/SystemVerilog system tasks/functions (`$`로 시작) 전수 지원** — display · I/O · 파일 I/O · 메모리 로드 · 시뮬레이션 제어 · 시간 · 변환 · 비트벡터 · 수학 · random · VCD dump · assertion 샘플링 · introspection 등 전 범주.
  구체 목록과 Phase별 커버리지는 `hdl-reference/system-tasks/00-index.md` 참조.
- **3개 HDL 지원** (로드맵 단계별): SystemVerilog(IEEE 1800) → 그 부분집합인 Verilog(IEEE 1364) → VHDL(IEEE 1076). 단계별 상세는 [로드맵 섹션](#phase-1-mvp-정의) 참조.
- **3-OS 소스 빌드** (cargo) + CI 매트릭스.
- **멀티 라이브러리** — 단위를 `library:unit` 논리 키로 주소화하고 논리명→디렉터리 매핑(`cds.lib`/`synopsys_sim.setup` 계열)을 지원 (D3, §14).
- **단계 산출물 온디스크 포맷 + staleness 재검증** — `vcmp`의 `work/` 라이브러리 + `velab`의 `.velab` 스냅샷을 해시 결합으로 묶어, 상류가 바뀐 stale 산출물에 대한 `vrun`을 거부한다 (RULE V, §14).
- **filelist** — `-f`/`-F` 재귀 중첩 + `+incdir+`/`+define+` 집계 (§14 §3.1).
- **진단/로깅 서브시스템** — transcript + 로그파일 tee, severity 라우팅, 소스 위치 추적 (§13).
- **에러 코드 카탈로그** — 안정 `MsgCode`(mnemonic + `VITA-####`) + `vita explain`, CI 1:1 동기 (§15).

## 비목표 (out-of-scope, 현 단계)

현 설계 단계에서 명시적으로 범위 밖으로 지정한 항목들이다.

- **합성(synthesis) 툴 자체 구현** — 단, 참조 문서에는 각 구문의 합성 가능 여부를 명기한다.
- **컴파일드(네이티브/JIT) 시뮬레이션 백엔드** — IR 경계만 열어두고 후속 단계로 미룬다. (`sim-ir` 설계는 이 확장을 고려해 언어 중립으로 유지된다.)
- **파형 GUI 뷰어** — VCD 출력을 GTKWave · Surfer 등 외부 뷰어로 확인한다.
- **FST 등 VCD 외 파형 포맷** — 후속 확장으로만 기록.
- **UPF/전력, SDF 타이밍 백애너테이션, DPI-C, 커버리지/UVM** 등 고급 검증 기능.

## 성공 기준 (측정 가능)

아래 항목을 모두 통과하는 것이 Phase 1 완료 조건이다.

- 대표 RTL 테스트벤치를 **Icarus Verilog(`iverilog` + `vvp`)를 golden으로 차등검증**했을 때 신호값과 천이 시각이 일치한다. Verilator는 **보정된(calibrated) 부분집합**에서 비교한다 — 2-state·X-init·조합 `$display` 등 비-IEEE 차이는 `known_quirks`로 carve-out (§9). 도구 충돌 시 IEEE LRM이 최종 권위.
- 생성 VCD가 표준 뷰어(GTKWave 등)에서 오류 없이 로드되고, **golden VCD와 정규화 diff가 일치**한다. (식별자 코드 차이를 흡수하는 정규화기 포함)
- 동일 소스가 **Ubuntu · RHEL · macOS에서 동일 결과**로 빌드·실행된다.
- `timescale`이 다른 모듈이 혼재해도 전역 시간축이 어긋나지 않는다 — 64-bit 정수 시간 + precision 환산 정밀도 테스트 통과 (§6.3).
- **표준 system tasks/functions 컴플라이언스 코퍼스** (범주별 최소 1개 케이스) 전수 통과.
- **staleness 재검증이 동작한다** — 상류 소스가 바뀐 stale `.velab` 스냅샷에 대한 `vrun`은 거부된다(`E-ART-STALE-UPSTREAM`, exit class 2 — RULE V). 이 동작을 최소 1회 테스트한다(mtime이 아닌 해시 기반).
- **진단 코퍼스는 메시지 텍스트가 아니라 `MsgCode`로 assert**하며(`expect_codes`, §9), 모든 코드가 §15 카탈로그와 1:1 동기(CI 게이트)다.

## 타깃 환경

| OS | 버전 |
|---|---|
| Ubuntu | LTS |
| RHEL | 8 / 9 계열 |
| macOS | Apple Silicon + Intel |

빌드 철학: 원문 소스 → 각 OS에서 `cargo build`. 사전 빌드 바이너리 배포에 의존하지 않는다.

**순수 Rust 코어 + 최소/제로 C 의존성.** 외부 C 라이브러리 의존을 피해 3-OS 빌드 마찰을 제거한다.

**MSRV(최소 지원 Rust 버전) 고정** + `rust-toolchain.toml`로 재현성 확보.

## Phase 1 (MVP) 정의

Phase 1의 범위는 **SystemVerilog 합성가능 RTL 서브셋** — Verilog-2005 RTL 전부를 포함한다.

**파이프라인:** preprocess → lex → parse → elaborate → event-driven sim → VCD

**백엔드:** 인터프리터 방식 (IR-walking). 정확성 · VCD · timescale 정밀도를 먼저 확보한 뒤, 후속 단계에서 컴파일드 백엔드를 `sim-ir` 경계 너머에 추가한다.

**Phase 1 구문 동결 (IN-MVP / deferred):** Phase 1 경계는 합성가능성 범례가 아니라 아래 표가 단일 기준으로 정의한다.

| 분류 | IN-MVP (Phase 1) | deferred (Phase 2+) |
|---|---|---|
| 설계 단위 | `module`/`endmodule`, 포트, `parameter`/`localparam`, `generate`/`genvar` | `interface`/`modport`, `package`, `program`, `class` |
| 자료형 | `wire`/`reg`/`logic`/`integer`, 벡터·packed array | `struct`/`union`/`enum`/`typedef`, `string`, 동적/연관 배열 |
| 절차 블록 | `initial`, `always`, `always_ff`/`always_comb`/`always_latch` | `final`, fork-join 고급 |
| 문장 | blocking `=` / nonblocking `<=`, `if`/`case`/`casez`/`casex`, `for`/`while`/`repeat`/`forever`, `begin`/`end` | `foreach`, `unique`/`priority`, `do-while` |
| 타이밍 | `#delay`, `@(event)`, `wait`(테스트벤치) | clocking block, intra-assignment delay 고급 |
| 연속 대입 | `assign`(+지연) | — |
| system tasks | 아래 핵심 셋 | 파일 I/O·메모리 로드·변환·random·assertion 샘플링 등 (Phase 2) |

> **합성가능성 마커는 구현 경계가 아니다.** `hdl-reference/`의 합성가능성 범례는 RTL→게이트 *합성* 가능 여부를 표기할 뿐이다. `initial`·`#delay`·`$display`·`$finish`는 합성 불가로 표기되지만 **시뮬레이터에 필수**이므로 Phase 1 IN이다. MVP의 IN/OUT 경계는 위 동결 표가 단일 기준이다.

**system tasks 핵심 셋 (Phase 1에서 반드시 지원):**

| 범주 | system tasks |
|---|---|
| 출력 (display I/O) | `$display` / `$write` / `$monitor` / `$strobe` |
| 시간 | `$time` / `$realtime` |
| 시뮬레이션 제어 | `$finish` / `$stop` |
| VCD dump 패밀리 | `$dumpfile` / `$dumpvars` / `$dumpon` / `$dumpoff` / `$dumpall` |

각 system task의 전체 시맨틱과 인자 명세는 `hdl-reference/system-tasks/` 섹터 참조.

Phase 2(SV 확장) 이후의 system tasks — 파일 I/O, 메모리 로드, 변환, 비트벡터, 수학, random, assertion 샘플링, introspection 등 — 는 `hdl-reference/system-tasks/00-index.md`의 Phase별 커버리지 매트릭스에 명시된다.

## 알려진 v1 단순화 (IN-MVP이되 의도적 한계 — 결함 아님)

아래는 Phase-1 IN 기능이지만 **의도적으로 단순화**한 동작이다. 모두 결정적·문서화됨이며, 정밀화는 Phase-1.x/Phase-2에서. (구현 검증 중 확인된 항목; 상세는 저장소 `docs/REMAINING_WORK.md`.)

| 영역 | v1 동작 | 정밀 동작(향후) |
|---|---|---|
| `casez`/`casex` 와일드카드 | scrutinee·label의 **모든** x/z를 don't-care로 마스킹(`reduction_or(scrut^label)!==1`) | `casez`는 z/?만, `casex`는 x/z만 (explicit-x-in-casez 분리) |
| 배열/벡터 인덱스 범위초과 | 읽기 all-X / 쓰기 무시(클램프 아님) — 진단 미발행 | `E-RUN-RANGE`(VITA-E4002) 런타임 진단 발행(엔진 diag-sink 도입 시) |
| unpacked 배열 *서브차원* 인덱스 초과 | 평탄공간 alias (per-dim bounds 미검사; lo-정규화는 적용) | per-dim 범위 검사 |
| X/Z 인덱스 | 읽기 all-X / 쓰기 no-op | 동일(이미 정밀) |
| `$time`/`$realtime` 멀티-timescale | per-process 단위로 정확 | 동일(이미 정밀) |
| `assign #d` 지연 | transport-delay만(inertial pulse 거부 없음) | inertial 모델 |
| `$stop` | 배치 종료(에서 `$finish`와 별개 exit class) | 대화형 브레이크포인트는 비지원(배치 시뮬레이터) |
| `$dumpvars`/`$dump*` 배열 | 배열은 word 0만 VCD 덤프, depth/scope 인자 무시(전체 덤프) | per-element 덤프 + scope 한정 |
| `>128bit` unsigned / `>64bit` signed 산술 | X로 poison(fail-safe) | full multi-word 산술 |

## Sources

- 본 spec §2.1 · §2.2 · §2.3 · §3 · §9 — `docs/superpowers/specs/2026-05-26-vitamin-rtl-simulator-design.md`
