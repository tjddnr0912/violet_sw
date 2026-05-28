# 05 · Time Functions

## 개요

시뮬레이션 현재 시각을 조회하는 시스템 함수 카테고리다.
`$time`과 `$realtime`은 `$display` 포맷 specifier `%t`와 함께 가장 빈번하게 사용된다.
내부 시간 표현에 대한 배경은 [08-timescale-and-timing.md](../../08-timescale-and-timing.md) 참조.

## 지원 Phase

- **Phase 1**: `$time`, `$stime`, `$realtime`

---

## 항목 상세

### `$time`

- **시그니처**: `$time` (인자 없음)
- **표준**: IEEE 1800-2017 §20.3 / IEEE 1364-2005 §17.7.1
- **반환 타입**: 64-bit unsigned integer
- **의미**: 호출 모듈의 `timescale` unit 단위로 현재 시뮬 시각을 정수 반환한다.
  정밀도(precision)에 따라 반올림된 후 unit으로 변환한 값이다.

```sv
`timescale 1ns / 100ps
initial begin
  #5;                                  // 5ns 지연
  $display("time = %0d ns", $time);   // time = 5 ns
  #0.3;                                // 300ps 지연 → precision 반올림 → 300ps
  $display("time = %0d ns", $time);   // time = 5 ns  (300ps < 1ns → 정수 변환 시 0 추가)
  // 주의: $time은 ns 단위 정수 → 5.3ns는 5로 표현
end
```

**정수 변환 규칙**: precision 경계로 반올림된 시각을 unit으로 나눈 후 정수 변환(truncation이 아닌 반올림).
예: `1ns/100ps` timescale에서 5.25ns → precision 반올림 → 5.3ns → `$time` = 5 (ns 단위, fractional 버림).
`$realtime`과 달리 fractional 부분을 볼 수 없다.

---

### `$stime`

- **시그니처**: `$stime` (인자 없음)
- **표준**: IEEE 1800-2017 §20.3 / IEEE 1364-2005 §17.7.2
- **반환 타입**: 32-bit unsigned integer
- **의미**: `$time`의 **하위 32비트**를 반환한다.
  값이 2³² − 1 (~4.3 billion)을 초과하면 wrap-around가 발생한다.
  현대적인 용도에서는 거의 사용하지 않는 legacy 함수.

```sv
// wrap-around 위험 예시 (1ns 단위, 4.3초 이상 시뮬)
$display("stime=%0d", $stime);   // 하위 32비트만 반환
$display("time=%0d", $time);     // 64비트 전체 반환 (권장)
```

**권장**: `$stime` 대신 `$time`을 사용한다.
`$stime`은 하드웨어 레지스터처럼 32비트 정수를 기대하는 레거시 코드와의 호환 목적으로만 남아 있다.

---

### `$realtime`

- **시그니처**: `$realtime` (인자 없음)
- **표준**: IEEE 1800-2017 §20.3 / IEEE 1364-2005 §17.7.3
- **반환 타입**: `real` (IEEE 754 double-precision floating-point)
- **의미**: 현재 시뮬 시각을 **소수**로 반환한다.
  timescale precision이 반영되어 fractional 시각을 정확히 표현한다.

```sv
`timescale 1ns / 100ps
initial begin
  #2.5;                                       // 2.5ns
  $display("time=%0d realtime=%g", $time, $realtime);
  // time=2  realtime=2.5
  // ($time은 ns 단위 정수 → 2, $realtime은 소수 → 2.5)
end
```

**정밀도 한계**: `real`은 IEEE 754 double (약 15~17 유효 자릿수)이므로
극히 긴 시뮬레이션에서는 정밀도 손실이 생길 수 있다.
일반적인 RTL 시뮬레이션 범위에서는 문제없다.

---

## $time vs $realtime 비교

| 항목 | `$time` | `$realtime` |
|------|---------|-------------|
| 반환 타입 | 64-bit unsigned int | real (double) |
| 소수 표현 | ❌ (정수만) | ✅ (precision 반영) |
| %t specifier | 사용 권장 | 사용 가능 |
| 오버플로우 | 64비트 한계 (~1.8×10¹⁹) | double 정밀도 한계 |
| 사용 빈도 | 높음 (기본) | fractional 확인 시 |

---

## 변환 예시 (timescale 상호작용)

```sv
`timescale 10ns / 1ns   // unit=10ns, precision=1ns

initial begin
  #1.5;     // 1.5 × 10ns = 15ns → precision 반올림 → 15ns → $time = 1 (unit=10ns 단위)
  $display("time=%0d (×10ns)  realtime=%g (×10ns)", $time, $realtime);
  // time=1  realtime=1.5    (unit=10ns 기준 소수값)

  #3;       // 3 × 10ns = 30ns 추가
  $display("time=%0d  realtime=%g", $time, $realtime);
  // time=4  realtime=4.5
end
```

timescale 반올림·변환 규칙의 전체 정의는
[08-timescale-and-timing.md](../../08-timescale-and-timing.md) 참조.

---

## Icarus / Verilator 지원

| 함수 | Icarus | Verilator |
|------|--------|-----------|
| `$time` | 완전 지원 | Generally supported |
| `$stime` | 완전 지원 | Generally supported |
| `$realtime` | 완전 지원 | Generally supported |

Verilator 공식 문서는 세 함수 모두 "Generally supported"로 분류한다.
동작 차이는 timescale 처리 정밀도에서 나타날 수 있으며,
차등검증 시 `$realtime` 소수 비교는 epsilon 허용 범위를 적용하는 것을 권장한다.

---

## 합성 가능성

❌ 비합성 — 시뮬레이션 전용 함수.
합성 도구는 `$time`/`$realtime` 호출을 무시하거나 오류를 발생시킨다.

---

## 본 프로젝트 구현 메모

- `hdl-builtins` 크레이트 `time` 카테고리가 담당
- 내부 시간 모델: 64비트 정수 (§08 timescale 참조)
- `$time`: 내부 64비트 정수를 호출 모듈의 timescale unit으로 변환 후 반환
- `$stime`: `$time` 결과의 하위 32비트 (as_u32() truncation)
- `$realtime`: 내부 정수를 unit 기준 f64로 변환 후 반환

## Sources

- IEEE 1800-2017 §20.3
- IEEE 1364-2005 §17.7
- [08-timescale-and-timing.md](../../08-timescale-and-timing.md) (내부 문서, timescale 변환 규칙)
- research-log: [system-tasks-display-time-2026-05-28.md](../../research-log/system-tasks-display-time-2026-05-28.md)
- [circuitcove.com Time Functions](https://circuitcove.com/system-tasks-time/)
- [chipverify.com Verilog Timescale](https://www.chipverify.com/verilog/verilog-timescale)
- [verilator.org Input Languages](https://verilator.org/guide/latest/languages.html)
