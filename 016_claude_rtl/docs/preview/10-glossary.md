# 10 · 용어집

본 문서에서 반복적으로 사용되는 용어를 정의한다. 표준 IEEE 1800/1364 용어는
해당 조항 번호를 병기하며, 본 프로젝트 고유 용어는 별도 표시한다.

---

## 시뮬레이션 핵심

**Compile** — 전처리(preprocess) + 어휘 분석(lex) + 구문 분석(parse) + 문법 검사.
결과물은 AST(Abstract Syntax Tree). 오류는 이 단계에서 최초 보고된다.

**Elaboration** — AST를 시뮬레이션 가능한 형태로 변환하는 단계.
파라미터 해소, 모듈 계층 인스턴스화, 타입 검사, 포트 연결성 검사,
다중 구동(multi-driver) 검사를 포함한다. 결과물은 sim-ir.
IEEE 1800 §23.10 참조.

**Event-driven simulation** — 신호 값의 변화(이벤트)가 발생할 때만
관련 프로세스를 실행하는 시뮬레이션 방식.
클록 주기마다 전체를 평가하는 cycle-accurate 방식과 대비된다.
IEEE 1800 §4 참조.

**Delta cycle** — 동일한 시뮬레이션 시각(simulation time)에서
신호들이 안정 상태에 도달할 때까지 반복되는 0-시간 평가 단계.
`#0` 지연이나 논리 연쇄가 복수의 delta를 유발한다.
`$time`은 delta 사이에서 증가하지 않는다. IEEE 1800 §4.5 참조.

**Stratified event queue** — IEEE 1800/1364가 정의하는 영역 분리 이벤트 큐.
같은 시각의 이벤트를 Active / Inactive / NBA / Observed / Reactive /
Re-Inactive / Re-NBA / Postponed 영역으로 구분하여 실행 순서를 결정적으로 정의한다.
IEEE 1800 §4.4 참조.

**NBA** — Non-Blocking Assignment(`<=`) 갱신 수집 영역.
`<=` 우변은 Active 영역에서 평가되고, 좌변 갱신은 NBA 영역에서 일괄 커밋된다.
이를 통해 클록 에지에서의 레지스터 교환(swap)이 정확하게 동작한다.
IEEE 1800 §10.4.2 참조.

---

## 시간

**timescale** — `` `timescale <단위>/<정밀도> `` 디렉티브.
단위(unit)는 `#1`이 나타내는 실제 시간, 정밀도(precision)는 내부 표현의
최소 분해능을 결정한다. 예: `` `timescale 1ns/1ps ``.
IEEE 1364 §19.2 / IEEE 1800 §3.14 참조.

**Time wheel** — 미래 이벤트를 시각별로 보관하는 내부 자료구조.
각 버킷은 특정 시뮬레이션 시각에 실행될 이벤트 목록을 담는다.
시간 진행은 다음 이벤트가 존재하는 버킷으로 점프(time advance)하는 방식이다.

**`$time`** — 현재 시뮬레이션 시각을 timescale 단위의 정수로 반환하는 시스템 함수.
64비트 정수. `$time`은 precision이 아닌 unit 기준이므로 정밀도가 손실될 수 있다.
IEEE 1800 §20.3 참조.

**`$realtime`** — 현재 시뮬레이션 시각을 timescale 정밀도를 반영한 실수(real)로 반환.
`$time`과 달리 소수점 이하 시각을 표현한다.
IEEE 1800 §20.3 참조.

---

## 파형

**VCD** — Value Change Dump. IEEE 1364 §18에서 정의된 ASCII 기반 파형 덤프 포맷.
헤더(선언 섹션)와 본문(시각별 값 변화 섹션)으로 구성된다.
본 프로젝트의 1차 출력 포맷.

**Identifier code** — VCD에서 신호를 참조하는 짧은 ASCII 코드.
`!`, `"`, `#` 등 가독 ASCII 문자로 구성되며, 헤더의 `$var` 선언에서
신호명과 매핑된다. 도구마다 생성 방식이 다르므로 VCD 비교 시 정규화가 필요하다.
IEEE 1364 §18.2 참조.

**FST** — Fast Signal Trace. GTKWave 및 Verilator에서 지원하는 이진 파형 포맷.
VCD 대비 파일 크기가 훨씬 작고 쓰기 효율이 높다.
본 프로젝트의 비목표 포맷 (VCD 우선).

---

## 언어

**HDL** — Hardware Description Language. 하드웨어 구조와 동작을 기술하는 언어.
본 프로젝트의 입력 언어는 Verilog(IEEE 1364-2005) 및 SystemVerilog(IEEE 1800)의
시뮬레이션 서브셋이다.

**System task / function** — `$`로 시작하는 표준 내장 서브루틴.
`$display`, `$monitor`, `$time`, `$finish`, `$dumpfile`, `$dumpvars` 등.
task는 값을 반환하지 않으며, function은 값을 반환한다.
IEEE 1800 §20~21 참조.

**Synthesizability** — RTL 코드가 논리 합성 도구로 게이트 네트리스트로 변환 가능한지
여부. 본 프로젝트는 합성이 아닌 시뮬레이션을 대상으로 하므로,
합성 불가 구문(지연, 초기화 블록 등)도 시뮬레이션 범위에서는 지원한다.

**4-state logic** — 신호가 0 / 1 / X(unknown) / Z(high-impedance) 네 가지 값을
가질 수 있는 표현 모델. IEEE 표준 시뮬레이션의 기본 모델.
Icarus Verilog와 본 프로젝트가 구현하는 모델.

**2-state logic** — 0과 1만 존재하는 단순화된 표현 모델.
Verilator의 기본 모델이며, X/Z를 0으로 처리해 성능을 높이지만
초기화 오류 탐지 능력이 낮아진다.

---

## 본 프로젝트

**Vitamin** — 본 프로젝트 코드네임 (임시). 메모리 안전·이식성·정밀도를 갖춘
Rust 기반 RTL 시뮬레이터.

**vita** — CLI 작업명 (placeholder). `vita sim`, `vita check` 등의 서브커맨드를
통해 시뮬레이션·정적 분석·VCD 조회를 수행하는 진입점.

**sim-ir** — 언어 비의존 시뮬레이션 IR(Intermediate Representation).
elaboration 단계의 출력이자 시뮬레이션 엔진의 입력.
Verilog / SystemVerilog 의미론을 IR 수준에서 추상화하여, 향후 컴파일드/JIT
백엔드를 재작성 없이 추가할 수 있는 경계를 제공한다.

**hdl-builtins** — `$`로 시작하는 system tasks/functions를 구현하는 크레이트.
`$display`, `$write`, `$monitor`, `$time`, `$realtime`, `$finish`, `$stop`,
`$dumpfile`, `$dumpvars`, `$dumpon`, `$dumpoff` 등.

**vcd-writer** — VCD 파형 파일 출력을 담당하는 크레이트.
RTL의 `$dumpfile`/`$dumpvars` 호출 시에만 활성화되며,
자동 전체 덤프는 지원하지 않는다.

**diag** — 오류 · 경고 · 진단 메시지 포맷과 소스 위치 정보를 담당하는 크레이트.
Rust 컴파일러 스타일(파일:줄:열 + 시각적 언더라인)을 목표로 한다.

**corpus runner** — `tests/corpus/` 전체를 자동으로 실행하여 PASS/FAIL/WARN을
집계하는 CI 도구. VCD diff 결과를 표준 출력 + JUnit XML 포맷으로 리포트한다.

**vcd-diff** — 두 VCD 파일을 정규화하여 신호값 · 천이 시각 차이를 비교하는
내부 도구. 식별자 코드 재매핑, Z→0 정규화, 계층명 매핑을 수행한다.

---

## Sources

- 본 spec §13 (용어 요약) + IEEE 1800-2017 / IEEE 1364-2005 표준 용어
- IEEE 1800 §4 (스케줄링 의미론), §10.4.2 (NBA), §18 (VCD), §20~21 (system tasks)
- IEEE 1364 §18 (VCD 원형 정의), §19.2 (timescale)
- Verilator 공식 문서: https://verilator.org/guide/latest/
- Icarus Verilog 공식 문서: https://steveicarus.github.io/iverilog/
