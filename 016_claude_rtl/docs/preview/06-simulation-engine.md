# 06 · 시뮬레이션 엔진

## 이벤트 구동 모델 개요

Verilog/SystemVerilog 시뮬레이터는 **이벤트 구동(event-driven)** 모델로 동작한다. 실제 하드웨어는 신호 변화가 있을 때만 논리 게이트가 "깨어나고", 변화가 없으면 전력을 소모하되 출력은 유지된다. 이벤트 구동 시뮬레이터는 이 특성을 그대로 모방한다 — 신호에 변화가 생길 때만 관련 프로세스를 실행하고, 아무것도 안 바뀌면 시간을 건너뛰어 다음 예정된 이벤트로 점프한다.

**클록드(cycle-accurate) 시뮬레이터**와의 차이: 클록드 시뮬레이터는 매 클럭 사이클에서 전체 상태를 평가하므로 구현이 단순하지만, 비동기 회로나 서브-사이클 타이밍을 표현할 수 없다. 이벤트 구동 방식은 delta cycle을 포함해 arbitrary한 시간 해상도로 신호 전파를 추적할 수 있다.

---

## Stratified Event Queue

### IEEE 1364 — 4개 기본 region

IEEE 1364(Verilog)는 한 simulation time slot을 네 단계로 나눈다. 이 순서는 표준이 보장하는 실행 순서이며, 시뮬레이터는 반드시 이를 따라야 한다.

```
┌─────────────────────────────────────────────────────────┐
│  Simulation Time T                                      │
│                                                         │
│  1. Active    ← blocking(=), continuous assign,        │
│                 NBA RHS 평가, 기본 소자 출력 갱신       │
│                 (동일 region 내 순서는 비결정론적)      │
│                                                         │
│  2. Inactive  ← #0 delay가 달린 이벤트                 │
│                                                         │
│  3. NBA       ← non-blocking(<=) LHS 갱신              │
│                 (Active에서 샘플한 RHS 값을 일괄 적용) │
│                                                         │
│  4. Monitor   ← $monitor, $strobe                      │
│                 (시각 내 모든 값 변화 완료 후 실행)     │
└─────────────────────────────────────────────────────────┘
         │ Active/Inactive/NBA 루프가 안정될 때까지 반복
         ↓
   Delta Cycle (0-time 반복) → 안정 → 다음 시각으로
```

NBA region의 존재가 핵심이다. non-blocking assignment(`<=`)의 LHS 갱신은 Active region에서 RHS를 "샘플"한 뒤 NBA region까지 지연된다. 그 사이에 다른 프로세스가 같은 신호를 읽어도 아직 이전 값을 본다. 이 분리가 플립플롭 체인의 결정론적 동작을 보장한다.

### blocking vs non-blocking — 결정론 보장 예시

```systemverilog
// ── 결정론적: NBA region 분리 ──────────────────────────
always_ff @(posedge clk) begin
  b <= a;  // Active: RHS(a) 샘플. NBA: LHS(b) 갱신
  c <= b;  // Active: RHS(b 현재값) 샘플. NBA: LHS(c) 갱신
end
// 결과: 클럭마다 한 단계씩 쉬프트 — a→b, b→c (T 기준값)

// ── 비결정론적 위험: blocking ──────────────────────────
always_ff @(posedge clk) begin
  b = a;   // Active: 즉시 b = a
  c = b;   // Active: 이미 갱신된 b를 읽음 → c = a
end
// 결과: 쉬프트가 아니라 두 레지스터 모두 a가 됨
```

### IEEE 1800 (SystemVerilog) — 17개 region

SV는 assertion, program block, PLI 콜백을 지원하기 위해 4개 region을 17개로 확장했다. Phase 2+ 구현 목표이며, Phase 1에서는 IEEE 1364의 4개 region 구현으로 RTL 시뮬레이션을 충분히 커버한다.

```
Preponed          ← concurrent assertion 신호 샘플링 (time slot 시작 직전)
Pre-Active
Active            ← blocking(=), continuous assign, NBA RHS 평가
Inactive          ← #0 이벤트
Pre-NBA
NBA               ← non-blocking(<=) LHS 갱신
Post-NBA          ← PLI 콜백
Pre-Observed
Observed          ← concurrent assertion property/sequence 평가
Post-Observed
Reactive          ← program block blocking(=), assertion action
Re-Inactive
Pre-Re-NBA
Re-NBA
Post-Re-NBA
Pre-Postponed
Postponed         ← $monitor, $strobe, functional coverage
```

Active region set (Active/Inactive/Pre-NBA/NBA/Post-NBA) = RTL 설계 코드 영역.
Reactive region set (Reactive/Re-Inactive/.../Post-Re-NBA) = testbench(program block) 영역.
이 이원 분리가 DUT와 TB 사이의 race condition을 구조적으로 제거하는 SV의 핵심 설계 의도다.

---

## Delta Cycle

delta cycle은 동일 simulation time 내에서 신호가 안정될 때까지 Active→Inactive→NBA 루프를 반복하는 **0-time 이터레이션**이다. 시각은 전진하지 않지만 delta 카운터가 하나씩 올라간다.

```
T=10 : a = 1 (새 이벤트 발생)
  delta 1: always @(a) b = a  → b가 1로 바뀜 → b 이벤트 추가
  delta 2: always @(b) c = b  → c가 1로 바뀜 → c 이벤트 추가
  delta 3: c 변화로 트리거되는 추가 always 없음 → Active queue 비어 있음
  → T=10 안정. T=다음 이벤트 시각으로 전진
```

### 무한 delta 검출

피드백이 있는 조합 논리는 무한 delta를 유발할 수 있다:

```verilog
// 위험: 조합 루프
assign a = ~a;  // a 변경 → 다시 a 트리거 → 무한
```

시뮬레이터 대응:
- 상용 툴(VCS, QuestaSim 등): 이벤트 카운트가 threshold(예: 10M)를 초과하면 경고/중단
- Icarus Verilog: 자동 감지 없음 — 사용자가 `$finish` watchdog을 별도로 삽입해야 한다
- 본 프로젝트 구현 목표: delta 카운트를 IR 실행 루프에서 추적하고, configurable threshold 초과 시 진단 메시지와 함께 시뮬레이션 중단. 기본값 1,000,000 delta/time-step 제안

---

## Process와 Sensitivity

RTL 소스의 각 behavioral block은 IR에서 **process 노드**로 표현된다.

- `always @(a, b)` → sensitivity list에 `a`, `b` 등록
- `always @(posedge clk)` → `clk` 상승 에지에만 트리거
- `always_comb` / `always @(*)` → 블록 내에서 읽히는 모든 신호 자동 sensitivity. 시뮬레이터 구현 시에는 IR 분석으로 미리 sensitivity set을 계산해 등록
- `initial` 블록 → time 0에서 한 번 Active queue에 삽입, 이후 `#delay` 또는 이벤트 대기로 진행

신호 값 변화 이벤트가 발생하면 해당 신호를 sensitivity list에 가진 모든 process가 Active queue에 삽입된다. continuous assign(`assign`)도 동일 메커니즘 — 드라이빙 신호 변화 시 RHS 재평가 후 LHS 갱신 이벤트 발행.

---

## 프로세스 실행 모델 — basic-block PC 상태기계 (결정 2026-06-01)

절차 블록(`initial`/`always*`/task/fork-join)은 `#delay`·`@(event)`·`wait(expr)`에서 **본문 중간에 멈췄다가 나중에 그 자리에서 재개**해야 한다. 이 suspend/resume을 **수작업 program-counter 상태기계**로 구현한다 — OS 스레드·stackful 코루틴·async/await·`gen` 블록은 모두 배제했다.

- **lowering:** 엘라보레이터가 블록 본문을 **구조화된 basic-block 시퀀스**로 평탄화한다. 모든 wait 지점(`#`/`@`/`wait`/`join`)이 basic-block 경계가 되도록 분할한다(바이트코드 ISA가 아니라 구조화 IR).
- **재개 상태:** 멈춘 프로세스는 `{ resume_pc: u32, locals: Vec<FourState>, join_state, wake_key }`로 표현된다. `resume_pc`는 **basic-block 인덱스(정수)** 이지 네이티브 PC·포인터가 아니다.
- **왜 이 모델인가:** 재개 상태가 `sim-ir`의 serde/postcard 직렬화 형상과 **동일한 표현**(평탄 u32-arena, 순서 안정 `Vec`, span-free)이라 새 직렬화 기계가 0이고, 정수 pc + 순서 벡터는 OS/arch 무관 **바이트 동일**이라 3-OS 결정성을 by construction 충족한다. 또 `resume_pc`(= 노드 인덱스)가 14 §7 위치 side-table과 13 vita-log를 통해 "Process tb.dut.u_alu blocked at line 42"로 곧장 매핑돼 디버깅 추적이 공짜로 떨어진다. (async executor 대안은 결정성·실행성능은 동등하나 멈춘 future가 non-serde라 디스크 mid-run 체크포인트를 영구히 닫고, 정지상태 추적에 executor 계측이 필요하다.)
- **wake_key와 region:** 깨어남 조건(에지/레벨/시각)과 **재개 region**(Active/Inactive/NBA/Monitor — 위 stratified queue)을 `wake_key`에 싣고, region 내 tie-break 순서를 고정해 결정성을 유지한다.
- **잠그는 것:** 이 결정은 `sim-ir`의 `process` 노드 형상을 잠근다(상세 [14-staged-artifacts.md](14-staged-artifacts.md) §1·§5). `disable`/`disable fork`의 서브트리 teardown, fork-join 인코딩, wait 포함 task의 call-frame 표현은 sim-ir freeze 전 확정할 하위 결정으로 남는다.

---

## Builtin-Call 처리

IR의 `builtin-call` 노드(시스템 태스크/함수 호출)를 만나면 `hdl-builtins` 디스패치 테이블에서 해당 핸들러를 호출한다.

주요 분류:

| 종류 | 대상 | 처리 |
|------|------|------|
| I/O | `$display`, `$write`, `$strobe` | 포맷 문자열 평가 후 표준 출력 |
| 시간 | `$time`, `$realtime`, `$stime` | 시간 레지스터 읽기 (08-timescale 참조) |
| 덤프 | `$dumpfile`, `$dumpvars`, `$dumpflush` | vcd-writer로 라우팅 (07-vcd-format 참조) |
| 제어 | `$finish`, `$stop` | 시뮬레이션 종료/정지 |
| 난수 | `$random` | PRNG 호출 |
| 파일 | `$fopen`, `$fclose`, `$fdisplay` | 파일 핸들 관리 |

`$strobe`는 Active region이 아닌 Monitor region에서 실행되어야 하므로, 이벤트를 즉시 처리하지 않고 현재 time-step의 Monitor queue에 예약한다(one-shot).

### `$monitor` 라이프사이클 (지속 재트리거)

`$monitor`는 `$strobe`의 one-shot과 달리 **영구 등록형**이다 — Phase 1 필수 태스크이므로 엔진이 다음 상태를 소유한다:

- **단일 활성 슬롯:** 시뮬레이션 전체에 `$monitor` 인스턴스는 **하나만** 활성이다. 새 `$monitor` 호출은 이전 등록을 **교체(replace-on-reinstall)** 한다. `$monitoroff`/`$monitoron`으로 활성 슬롯을 비활성/재활성한다.
- **동적 sensitivity:** 인자 식에서 읽히는 모든 신호를 sensitivity로 등록한다(net 변화 감시). `always_comb` auto-sensitivity와 같은 IR 분석으로 신호 집합을 계산한다.
- **time-step 내 1회 출력:** 한 time-step에서 인자 신호가 여러 번 바뀌어도 출력은 **time-step 끝(Monitor region)에 한 번**만 — 같은 시각 중복 발화를 억제하고 안정값을 출력한다.
- **엔진 상태로 소유:** 활성 슬롯·sensitivity·"이번 step에 변화 있었나" 플래그는 sim-engine 상태다(`hdl-builtins`는 등록/해제 호출만 디스패치). 동작 의미 상세는 `hdl-reference/system-tasks/01-display-io.md`.

---

## 성능 고려

인터프리터 핫 루프에서 반복 실행되는 IR 노드의 접근 패턴을 최적화해야 한다.

**캐시 친화적 SoA(Structure of Arrays)**: IR을 AoS(Array of Structs)가 아닌 SoA로 저장하면 동일 필드(예: opcode 배열, operand 배열)가 연속 메모리에 위치해 SIMD/prefetch 효율이 높아진다.

**64-bit 정수 time wheel**: 전체 시뮬레이션 시각을 64-bit 정수 카운터 하나로 관리. 부동소수 누적 오차 없음. 상세는 [08-timescale-and-timing.md](08-timescale-and-timing.md) 참조.

**이벤트 큐 구조**: 우선순위 큐(skip list 또는 binary heap)로 "다음 이벤트 시각"을 O(log n) 검색. Icarus vvp는 skip list 사용. 현재 시각 내 이벤트(delta)는 별도 FIFO로 O(1) 처리.

**후속 컴파일드/JIT 백엔드의 분기점**: Phase 1에서는 인터프리터로 정확성을 확보하고, IR 노드 타입과 인터페이스를 안정화한다. Phase 3+에서 동일 IR을 입력받는 컴파일드 백엔드(예: LLVM IR 생성)나 JIT 백엔드를 추가할 수 있도록 `Simulator` trait(또는 enum 기반 dispatch)로 추상화한다.

---

## Sources

- 본 spec §6 (Simulation Engine)
- research-log: [`sv-scheduling-2026-05-28.md`](research-log/sv-scheduling-2026-05-28.md)
- IEEE 1800-2012 §4 (Scheduling semantics), §9 (Processes)
- IEEE 1364-2005 §5 (Scheduling semantics)
- https://verificationguide.com/systemverilog/systemverilog-scheduling-semantics/
- https://vlsiverify.com/verilog/verilog-scheduling-semantics/
- https://24x7fpga.com/sv_directory/2025_01_14_scheduling_semantics/
