# 18 · 병렬/GPU 가속 분석

> 2026-06-05 코드 기반 분석. 결론: **이벤트구동 RTL sim 코어는 GPU 비적합**; CPU word化+SIMD와 컴파일드 백엔드가 실질 가속 경로.

## 요약 판정

| 방향 | 평가 | 이유 |
|---|---|---|
| GPU(Metal/CUDA/일반) 코어 엔진 | ❌ 비권장 | 이벤트구동 RTL은 분기발산·희소활성·시간인과·포인터추적으로 GPU-적대적 |
| CPU word-level + SIMD(NEON/AVX) | ✅ 실질 이득, 저위험 | 4-state 비트연산이 현재 bit-by-bit → word化만으로 ~64×, SIMD 추가 |
| 멀티코어 PDES(timestep 내) | ⚠️ 큰 작업 + 결정성 충돌 | 3-OS byte-identical 보장과 상충 |
| 컴파일드 백엔드(코드젠) | ✅ 진짜 가속 경로(로드맵) | IR-walking→네이티브 10~100×, GPU 불요 |
| stimulus-parallel GPU(Monte-Carlo) | 별개 제품 | branch-free cycle-based 엔진 신규 필요 |

## 왜 이벤트구동 RTL은 GPU-적대적인가
1. **분기 발산**: 프로세스마다 데이터의존 if/case/loop → GPU SIMT warp 발산 = 처리량 붕괴.
2. **희소 활성도**: 매 timestep 변한 net/process만 재평가(극소수). GPU는 조밀·균일 작업을 원함.
3. **시간 인과성**: 시각 T는 T-1 의존 → timestep *간* 병렬 불가. timestep *내* 독립 프로세스만(곧 희소·발산).
4. **포인터 추적**: IR이 index-edge arena → 재귀 트리 평가 = uncoalesced 메모리.
5. **세밀 동기화**: NBA·델타·계층화 리전 = 배리어/atomic.
6. 상용(VCS/Xcelium/Questa) 전부 CPU. GPU sim 연구는 cycle-based 대규모 게이트넷·stimulus 병렬(회귀팜) 같은 *다른* 문제 대상.

## 코드에서 찾은 병렬화 기회

### ⭐ (1) 4-state 비트연산 word化 + SIMD — 최우선 — ✅ **구현 완료(2026-06-05)**
- (이전) `eval.rs` `bitwise()`/`BitNot`/6 리덕션이 **bit-by-bit** (`for i in 0..w { f(get_vu(i), …) }`, 64bit AND가 64회).
- (구현) val/unk 2-plane **word-parallel 공식**으로 교체 — `value.rs`의 `and_w`/`or_w`/`xor_w`/`xnor_w`/`not_w` + `eval.rs`의 `reduce_word`/`RedKind`.
  AND: known-0 = `(~av&~au)|(~bv&~bu)`, known-1 = `(~au&av)&(~bu&bv)`, rv=known1·ru=`~known0&~known1`.
  라스트 부분워드는 `low_mask`로 마스킹(not_w/xnor_w가 high 0&0→1). per-bit `*1`은 `#[cfg(test)]` 오라클로 보존(`word_vs_bit_parity`가 4×4 입력×NOT을 bit-exact 대조).
- 효과: 64비트당 64회→1회 + 브랜치리스 → LLVM 자동벡터화(NEON/AVX). wide 버스 큰 이득, 좁은 설계 무손해(1 word).
- **`std::simd` 미도입:** portable_simd는 **nightly 전용**이라 MSRV-1.82 stable + `--locked` 3-OS 바이트동일 핀과 충돌. 안정 u64 워드 루프가 이미 SIMD-친화형(64-lane/워드)이며 LLVM이 자동벡터화하므로 명시 SIMD 불요. 도입하려면 nightly 또는 `wide` 크레이트가 필요한데 둘 다 핵심 불변식을 깸 → 의도적 제외.
- 비교(`eval.rs` relational/eq)는 산술 레인(64/128bit 정수)이라 별개 경로 — 워드化 대상 아님.

### (2) for-loop copy block (사용자 지목)
- const-bound for/repeat는 elaborate서 UNROLL(straight-line, cap). 펼친 바디는 순차 실행.
- 일반 병렬화는 iteration 의존성 분석 필요(blocking `=` 시퀀스). 거대 메모리 init/`$readmemh`만 데이터병렬이나 GPU 런치 오버헤드가 패배 → CPU SIMD/threads 적합.

### (3) timestep 내 프로세스 병렬 (PDES)
- `sched.rs` active `batch`를 `for r in batch` 순차. 공유 net 쓰기 동기화 + `tie`(선언순) 결정성 충돌 → 결정적 merge 필요(큰 엔지니어링).

### (4) 대용량 메모리/init
- `state.rs:412` `expand_init`, VCD 대용량 배열 덤프 — 데이터병렬이나 일회성·폭 제한. CPU SIMD 적합.

## 권고 로드맵 (GPU-free 우선)
1. ✅ **완료(2026-06-05)**: 비트연산/reduction word化 (안정 u64; std::simd는 nightly 충돌로 제외, LLVM 자동벡터화로 흡수).
2. **중기·진짜 가속**: 컴파일드 백엔드(IR→네이티브 코드젠). 아래 §컴파일드 백엔드 참조 — vitamin은 **2a(컴파일드 이벤트구동)부터**.
3. **장기·선택**: 멀티코어 PDES(결정성 재설계) 또는 stimulus-parallel GPU(별개 모드).
4. **GPU 코어 엔진: 권장 안 함**.

## 컴파일드 백엔드 — 두 갈래 ("컴파일드" ≠ "사이클기반")

상용 시뮬레이터 계보로 보면 "컴파일드"와 "사이클기반"은 **직교**한다:

| | 인터프리티드 | 컴파일드 |
|---|---|---|
| **이벤트구동 (full 4-state)** | Cadence Verilog-XL, **현재 vitamin** | Synopsys VCS, Cadence Xcelium, Siemens Questa |
| **사이클기반 (보통 2-state)** | (드묾) | Verilator |

- **VCS**(*Verilog **C**ompiled-code **S**imulator*)가 컴파일드의 원조 — Verilog-XL(인터프리티드 레퍼런스)을 속도로 밀어냄. Cadence도 NC-Verilog(**N**ative **C**ompiled)→Incisive→Xcelium으로 컴파일드 전환. **상용 사인오프 시뮬레이터는 컴파일드이되 이벤트구동·4-state·타이밍을 그대로 유지**(글리치/X/Z 정확).
- **Verilator**는 컴파일드 **+ 사이클기반(2-state 기본)** — 인트라사이클 스케줄링을 버리고 클럭당 일괄 평가 → 10~100×지만 미세 타이밍/일부 4-state 포기(사인오프 부적합).

### vitamin 경로
- **2a. 컴파일드 이벤트구동 (VCS/Xcelium 길) — 먼저.** 기존 이벤트 커널·`val`/`unk` 4-state·word化(①)를 **그대로 두고** 프로세스 바디(BB의 Stmt/Expr)만 네이티브(Rust) 코드로 lowering. eval-디스패치/트리워크/Value 힙할당 제거. **의미 100% 보존**(인터프리터가 골든), 중간 가속. vitamin의 이벤트구동 코어와 자연 정합.
- **2b. 사이클기반 컴파일드 (Verilator 길) — 별도 공격적 모드.** combinational rank 정적 스케줄 + 클럭당 일괄 평가. 최대 가속이나 합성가능 서브셋·사이클 의미 제약. 2a 이후 옵트인 모드로.
