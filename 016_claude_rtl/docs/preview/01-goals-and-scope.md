# 01 · 목표 · 범위 · 성공 기준

## 목표 (in-scope)

이하 항목이 본 프로젝트의 구현 범위다.

- **HDL 소스 전체 파이프라인**: preprocess → lex → parse → elaboration → simulation.
  각 단계는 독립 크레이트로 분리해 단위 테스트가 가능하다.
- **문법 검사** — parse 단계에서 수행. 오류는 소스 위치와 함께 진단 출력.
- **elaboration 단계 점검 항목** — 파라미터 해소, 계층 연결성, 타입/포트 정합, 미연결 신호, 다중구동(multiple driver) 등.
- **이벤트 구동(event-driven) 시뮬레이션 커널** + `timescale` 기반 정밀 시간 모델 (§6).
- **VCD 파형 생성 (IEEE 1364)** — RTL 내 dump 시스템 태스크 호출 시에만 활성; 자동 항상-덤프 아님.
  CLI 편의 플래그(`vita sim --force-dump`)는 후속 옵션으로만 검토하며, 기본은 RTL이 주도한다.
- **표준 Verilog/SystemVerilog system tasks/functions (`$`로 시작) 전수 지원** — display · I/O · 파일 I/O · 메모리 로드 · 시뮬레이션 제어 · 시간 · 변환 · 비트벡터 · 수학 · random · VCD dump · assertion 샘플링 · introspection 등 전 범주.
  구체 목록과 Phase별 커버리지는 `hdl-reference/system-tasks/00-index.md` 참조.
- **3개 HDL 지원** (로드맵 단계별): SystemVerilog(IEEE 1800) → 그 부분집합인 Verilog(IEEE 1364) → VHDL(IEEE 1076). 단계별 상세는 [로드맵 섹션](#phase-1-mvp-정의) 참조.
- **3-OS 소스 빌드** (cargo) + CI 매트릭스.

## 비목표 (out-of-scope, 현 단계)

현 설계 단계에서 명시적으로 범위 밖으로 지정한 항목들이다.

- **합성(synthesis) 툴 자체 구현** — 단, 참조 문서에는 각 구문의 합성 가능 여부를 명기한다.
- **컴파일드(네이티브/JIT) 시뮬레이션 백엔드** — IR 경계만 열어두고 후속 단계로 미룬다. (`sim-ir` 설계는 이 확장을 고려해 언어 중립으로 유지된다.)
- **파형 GUI 뷰어** — VCD 출력을 GTKWave · Surfer 등 외부 뷰어로 확인한다.
- **FST 등 VCD 외 파형 포맷** — 후속 확장으로만 기록.
- **UPF/전력, SDF 타이밍 백애너테이션, DPI-C, 커버리지/UVM** 등 고급 검증 기능.

## 성공 기준 (측정 가능)

아래 항목을 모두 통과하는 것이 Phase 1 완료 조건이다.

- 대표 RTL 테스트벤치를 **Icarus Verilog(`iverilog` + `vvp`) · Verilator와 차등검증**했을 때 신호값과 천이 시각이 일치한다.
- 생성 VCD가 표준 뷰어(GTKWave 등)에서 오류 없이 로드되고, **golden VCD와 정규화 diff가 일치**한다. (식별자 코드 차이를 흡수하는 정규화기 포함)
- 동일 소스가 **Ubuntu · RHEL · macOS에서 동일 결과**로 빌드·실행된다.
- `timescale`이 다른 모듈이 혼재해도 전역 시간축이 어긋나지 않는다 — 64-bit 정수 시간 + precision 환산 정밀도 테스트 통과 (§6.3).
- **표준 system tasks/functions 컴플라이언스 코퍼스** (범주별 최소 1개 케이스) 전수 통과.

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

**system tasks 핵심 셋 (Phase 1에서 반드시 지원):**

| 범주 | system tasks |
|---|---|
| 출력 (display I/O) | `$display` / `$write` / `$monitor` / `$strobe` |
| 시간 | `$time` / `$realtime` |
| 시뮬레이션 제어 | `$finish` / `$stop` |
| VCD dump 패밀리 | `$dumpfile` / `$dumpvars` / `$dumpon` / `$dumpoff` / `$dumpall` |

각 system task의 전체 시맨틱과 인자 명세는 `hdl-reference/system-tasks/` 섹터 참조.

Phase 2(SV 확장) 이후의 system tasks — 파일 I/O, 메모리 로드, 변환, 비트벡터, 수학, random, assertion 샘플링, introspection 등 — 는 `hdl-reference/system-tasks/00-index.md`의 Phase별 커버리지 매트릭스에 명시된다.

## Sources

- 본 spec §2.1 · §2.2 · §2.3 · §3 · §9 — `docs/superpowers/specs/2026-05-26-vitamin-rtl-simulator-design.md`
