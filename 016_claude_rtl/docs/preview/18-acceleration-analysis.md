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

## 결정 기록 — 코드젠 substrate (P0a/P0b · 2026-06-06)

> 컴파일드 백엔드 선결 체크리스트(`docs/REMAINING_WORK.md` Stage B)의 P0a/P0b를 확정한다. 출처: 워크플로 `wzeyxgedk` 6-매핑/3-비평 + 사용자 결정(2026-06-06).

### P0a — target form = **바이트코드 VM** (확정)

세 후보를 프로젝트 hard-constraint(cargo-only · `build.rs` 금지 · MSRV-1.82 핀 · `--locked` 3-OS 바이트동일) 기준으로 평가:

| 형식 | 속도 | 신규 의존 | 결정성 핀 | 판정 |
|---|---|---|---|---|
| 바이트코드 VM | ~2-5× | 없음(순수 Rust) | ✅ 전부 보존 | **선택** |
| 네이티브 Rust 방출 | 10-100× | 런타임 rustc/cc + libloading | ⚠️ host LLVM 재증명 필요 | 탈락(핀 충돌) |
| 타입드 IR-2 | ~3-8× | 없음 | ✅ 보존 | 차선(작업량 대비 이득 작음) |

**근거:** 네이티브 방출은 헤드라인 10-100×지만 런타임 호스트 툴체인 의존을 도입해 cargo-only·헤르메틱 `.velab→VCD`·3-OS 결정성 핀과 정면충돌한다(`build.rs`조차 금지하는 저장소에 런타임 `rustc`는 모순). vitamin의 goal #1은 *결정성*(README)이므로, 그 정체성을 깨지 않으면서 `doc-18:63`의 두 실측 병목 — **eval 트리워크 디스패치**(`run_process`의 `Stmt/Terminator` 재귀 + `EvalCtx::eval_ctx` 재귀)와 **`Value` 힙할당**(`Vec<u64>` per 연산) — 을 제거하는 바이트코드 VM을 선택한다. 인터프리터는 항상-가용 레퍼런스로 잔류, 바이트코드는 opt-in 가속 모드.

**바이트코드에서 "compile-time constant"(P10) 표현:** 정적 width/sign·폴드된 index/width/count는 **상수 풀(immediate operand 또는 const-pool 인덱스)** 로 인코딩 — 별도 노드 타입(IR-2)이나 Rust 리터럴(emit-Rust)이 아니라 op의 즉치 피연산자. P11의 shallow-fold·사이트별 fallback은 바이트코드 *컴파일 시점*에 한 번 계산해 immediate로 굳힌다.

### P0b — compile+load 메커니즘 = **N/A (in-process 바이트코드 인터프리터)**

바이트코드 VM은 런타임 코드 생성·로드가 없다. `.vu`/`.velab` 산출물·`vita`/`vrun` 실행경로·헤르메틱 계약 전부 무변경. P0b의 "런타임 rustc / cdylib+dlopen / static dispatch" 분기는 발생하지 않음(기록상 N/A). **결정성 따름정리:** VM opcode는 `value.rs`/`eval.rs`의 *동일한* 4-state·f64 프리미티브를 디스패치하므로(재구현 아님), float 포맷·산술 축이 인터프리터와 byte-for-byte 일치 — P3의 부담을 구조적으로 축소한다.

### 골든 영향 = 없음

바이트코드·VM·backend seam은 전부 `sim_ir::SimIr` 밖(SimOpts 사이드테이블/별도 크레이트). `schema_hash::<SimIr>()` 루트 불변, `format_version` 3 유지. P15의 kernel-ABI 버전은 `format_version`과 **독립** 필드로 별도 게이트.

## P3 — float/host-toolchain 결정성 계약 (2026-06-06)

> 컴파일드 백엔드의 정당성은 "3-OS 바이트동일 유지"인데, **float 경로가 최대 미고정 축**이다. 바이트코드 substrate(P0a) 덕분에 위험은 구조적으로 축소되지만(VM이 동일 함수 호출), 그 *reuse-only 규칙*을 계약으로 동결한다.

**동결된 float-path 표면 (바이트코드 경로는 재구현 금지 · verbatim 재사용 · no fast-math):**

| 함수 | 파일 | 결정성 근거 |
|---|---|---|
| `dec_field_width(n)` | builtins.rs:436 | ≤128은 u128 정수; >128만 `n·LOG10_2` f64 — 유일한 float-multiply(컬럼폭 힌트). 양 경로 동일 함수 |
| `fmt_dec` (real arm) | builtins.rs:454 | `x.round() as i64` saturating; NaN→0 |
| `fmt_real`(`%f`) | builtins.rs:480 | Rust `{:.*}` (libm 아님) |
| `fmt_real_e`(`%e`) | builtins.rs:499 | Rust `{:.p$e}` + 2자리 지수 패딩 |
| `format_g`(`%g`) | builtins.rs:520 | Rust `{:e}`로 지수 도출(**log10 의도적 회피** — libm transcendental은 3-OS 바이트동일 아님), ±0.0 canon |
| `Value::{from_f64,to_f64}`·`real_to_int_round` | value.rs:255,269,303 | int↔real `as f64`/round-half-away |

**계약:** 위 함수는 인터프리터와 바이트코드 VM이 *동일 인스턴스*를 호출한다(opcode가 별도 float 로직을 갖지 않음). 따라서 `%f/%e/%g/%t/%d-on-real` 및 >128bit `%d` 폭이 두 경로 byte-for-byte 일치 — 이는 P5(컴파일드==인터프리티드)로 강제되고, **단일-OS 체크인 골든**(`float_format_determinism_golden`, end_to_end.rs)이 cross-OS 재현성을 잠근다(모든 OS가 동일 리터럴 매칭 = cross-OS diff와 등가). CI는 ubuntu+macos에서 같은 골든을 돌려 OS별 발산 시 해당 leg 실패.

**잔여(릴리스 신뢰도, 코드젠 비차단):** CI에 OS-간 산출물 직접 diff 잡(별도 leg 출력 비교)은 골든-리터럴 방식으로 이미 등가 달성 — 추가는 nice-to-have.

## P8 — 커널-콜 순서 / 샘플링-모먼트 계약 (2026-06-06)

> 컴파일드 바디가 인터프리터와 byte-for-byte 일치하려면, "언제 무엇을 읽고/쓰는가"가 **계약**이어야 한다. 아래 7 모먼트를 동결한다 — P5 바이트-diff가 *버그 vs 의도*인지 분류하는 기준이자, Stage C VM이 반드시 재현(또는 위임)해야 할 목록.
>
> **핵심 구조적 사실:** 이 모먼트 대부분은 **커널측**(`write_lvalue`/`schedule_nba`/`propagate_changes`/`emit_vcd_change`)에 있다. 컴파일드 바디는 `Kernel` trait(P7b)로 *동일* 커널 메서드를 호출하므로 이들을 **공짜로** 재현한다. VM이 보존해야 할 유일한 바디측 불변식은 **문장 실행 순서**(→ `schedule_nba`가 텍스트 순서로 호출되어 `nba_seq`가 같게 부여됨)이다.

| # | 모먼트 | 위치 | 분류 | VM 의무 |
|---|---|---|---|---|
| 1 | cont-assign **선언순** fixpoint | sched.rs `settle_cont_assigns`:190 | 인터프리터-only | cont-assign은 프로세스 바디 아님(P13 전까지 항상 인터프리트) → VM 무관 |
| 2 | NBA: LHS 인덱스 **schedule-time 샘플** + `nba_seq` **정렬 적용** | sched.rs `schedule_nba`:802 / `apply_nba`:554 | 커널측 + **바디순서** | VM은 `k_schedule_nba`를 **문장 텍스트 순서**로 호출만 하면 됨(순서가 nba_seq) |
| 3 | blocking offset **statement-time 해석** | exec.rs `compute_effect`(P7a) | 바디(READ phase) | VM이 write 전에 `k_resolve_lvalue_offsets` 호출 — 이미 StmtEffect에 캡처 |
| 4 | in-body `@(sig)` **arm-snapshot**(Level만 arm=Some) | sched.rs `suspend_on`:791 | 인터프리터-only | `@`=Wait=suspend → **non-codegen**(P9 제외) → VM 무관 |
| 5 | delayed `assign #d` **last_ca 변화 키잉** | sched.rs:218 | 인터프리터-only | delayed cont-assign(P13) → VM 무관 |
| 6 | `propagate_changes` **prev-refresh-LAST** | sched.rs:658 | 커널측 | 스케줄러 내부 — 양 backend 공통, VM 무관 |
| 7 | **eager per-write VCD** 방출(글리치 충실) | state.rs `write_chunk`:386 | 커널측 | `k_write_lvalue`→`emit_vcd_change` 공유측(P4) → VM 공짜 재현 |

**결론:** 7 모먼트 중 VM이 *능동적으로* 책임지는 것은 **#2/#3 (NBA 순서·blocking offset)** 뿐이며, 둘 다 "문장을 인터프리터와 같은 순서로 실행"하면 자동 충족된다(StmtEffect가 #3을 캡처, 텍스트순 실행이 #2를 보장). 나머지(#1/#4/#5 인터프리터-only, #6/#7 커널측)는 backend-중립이다. 이 계약이 깨지면 P5가 즉시 red.

**corpus 커버리지(P6):** #2=`nba_sample`(`a[i]<=v; i=i+1`), #3=`mem_oob`/배열 쓰기, #7=`multi_write_glitch`(동일 delta 3회 쓰기), #1/#5=`cont_assign_mixed`(연속할당+클럭 프로세스 혼재). #4(in-body `@`)는 non-codegen이라 코드젠 corpus 비대상(인터프리터 433 테스트가 커버).
