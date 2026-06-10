# ROADMAP — Stage C 이후 향후 과제 (vitamin)

> **갱신:** 2026-06-10 — **7축 감사**(Gemini-fix 검토/spec-gap/sim-engine/front-end/메모리/운용성/병렬화) 반영: correctness 트랙 재개(§B), §D 사실관계 정정, **병렬화 트랙 §E 신설**. 잔여 항목의 단일 트래커 = [`REMAINING_WORK.md`](REMAINING_WORK.md)(2026-06-10 전면 리뉴얼: P0 정확성 9 · P1 의미론 9 · P2 운용 12 · P3 메모리 5 · P4 병렬화 · P5 문서부채).
> 직전: 2026-06-08 native-eval C4-lite 랜딩 + 멀티-top 다중 root. 현 단계 = **Stage C C1·C2 완료**(VM MVP, byte-identical) + **native-eval C4-lite(식-바운드 VM 0.42x)** + **profile-driven 최적화 누적 ~6x**(eval-heavy 2781→461ms). 이 문서는 *여기서부터 무엇을 할지*를 트랙별로 정리한 단일 진실. perf 이력 = [`preview/18-acceleration-analysis.md`](preview/18-acceleration-analysis.md) §실측(+구 트래커 git 이력), 설계는
> [`superpowers/plans/2026-06-06-bytecode-vm-stage-c.md`](superpowers/plans/2026-06-06-bytecode-vm-stage-c.md).

---

## 0. 핵심 발견 — 왜 로드맵이 바뀌었나 (반드시 먼저 읽을 것)

Stage C는 본래 *"컴파일드 백엔드(바이트코드 VM)로 인터프리터를 이긴다"* — eval 트리워크 디스패치와
`Value` 힙할당(doc-18이 지목한 두 병목)을 native-eval(plan C3~C6)로 제거 — 였다. **프로파일링(`/usr/bin/sample`)이
이 전제를 측정으로 뒤집었다:**

- **1차 병목 = bit-serial bit-by-bit 처리**(net read/write, shift, resize) — 인터프리터·VM **공유** 경로. word化/inline로 정리해 **~6x**.
- **eval 트리워크 디스패치는 eval-light 벤치에선 ~1.5%뿐**이었다 — 이 한 점으로 "native-eval 저ROI"라 1차 결론. **그 결론은 너무 강했다(아래 정정).**

→ **2차 재평가 (2026-06-07 오후, 오너 제기로 재검토):** eval 비용은 *식 복잡도에 선형*이다. 연산자수 스윕(`t ≈ 0.39s + 0.058s×K`, R²≈1)으로 **eval 비중이 K=8에서 55%, K=16에서 70%, K=32에서 82%**임을 측정. 피연산자당 58ns 중 ~57ns가 Value 생성 + `eval_ctx` 디스패치 오버헤드(net-read ≈ literal로 확인, 환원불가 ALU ~1ns)라 레지스터 native-eval이 제거 가능(~4-6x on eval). **⇒ native-eval ROI = 워크로드 의존:**
> - **식-바운드 RTL**(넓은 ALU·CRC/crypto·깊은 조합 cone): **고ROI**, 설계당 ~2-3x. `EXPR_HEAVY`(K=16)에서 VM은 0.92x뿐 — **문장 컴파일(현 VM)은 식-바운드에 거의 무력, native-eval이 유일한 레버.**
> - **클럭/스케줄러-바운드 RTL**: eval 작음 → **저ROI**, 스케줄러 축이 답.

**결론(settled):** 당초 doc-18의 "코드젠이 진짜 가속 경로"는 **식-바운드 한정으로 옳았다.** native-eval(plan C4~C9)은 **막다른 길이 아니라 식-바운드 perf의 정당한 방향**이며, **P5 차분 게이트(compiled==interp byte동일)+iverilog 오라클이 정확성 리스크를 이미 대폭 상쇄**한다. 비용은 4-state 레지스터 머신(val+unk·width/sign 마스킹·X/Z 전파·>128bit fallback)의 고위험·다세션. 측정 상세 = doc-18 §실측 "native-eval 재평가", 영구 회귀 = `perf_baseline.rs` `EXPR_HEAVY`.

---

## 1. 트랙별 향후 과제

### A. Perf — 남은 것 (싼 윈 거의 소진)

| 항목 | 위치 | ROI | 비고 |
|---|---|---|---|
| 저빈도 value-op word化 | `eval.rs` `eval_select`/`eval_concat`/`eval_replicate`/`merge_x` (아직 bit-serial) | 낮음 | arith 벤치 영향 0, bit-select/concat 많은 설계에만. 저위험·proven 패턴 |
| `has_xz`/`arith`/`to_u128` 미세 | `value.rs`/`eval.rs` | 낮음 | poison 체크 early-out·64bit fast-path 등. 소소 |
| **스케줄러 축 (별개 도메인)** | `sched.rs` event wheel(BTreeMap)·`propagate_changes`·NBA | **중간** | 클럭구동(codegen-heavy)은 3.2x로 eval-heavy(6x)보다 덜 빨라짐 — 다음 프론티어는 **이벤트 스케줄링**(value 처리와 다른 영역). 클럭 많은 설계에 유효 |
| **native-eval (eval 코드젠) — 🔨 C4-lite 착수** | `native_eval.rs`(신규) + `backend.rs` `Op::EvalNative` | **식-바운드 高 / 그 외 低** | **C4-lite 랜딩(2026-06-08): ≤64bit 정수 서브셋**(Const·scalar Signal·Add/Sub/Mul·And/Or/Xor/Xnor·Not/Plus/Minus)을 VM 전용 native 레지스터로 평가, 그 외는 `eval_ctx` fallback. **expr-heavy에서 VM 0.92x→0.42x(≈2.3x), 클럭-바운드 불변(0.94x)** — 식-바운드 ~2-3x 예측 실현. 인터프리터=오라클, P5 차분게이트가 byte동일 강제. **follow-on(다음 증분):** 비교/시프트/Div·Mod/리덕션/ternary/select·concat/>64bit/real |

**판단:** value-처리 bit-serial 스레드는 ~6x에서 마무리. 추가 perf의 두 축 = **스케줄러 축**(클럭-바운드) + **native-eval**(식-바운드·🔨 C4-lite 착수). 둘은 상보적(다른 워크로드).

### B. Correctness 후속 (perf와 독립)

- **🔴 2026-06-10 7축 감사 — correctness 트랙 재개.** silent-wrong 신규 확정(라이브 재현+iverilog 차분): **P0 클러스터 2개** — ①런타임 >64bit 절단(`to_u64`가 절단값 반환: relational `2^64>1`→0, shift-amount, negate, part-select offset, delay) ②elaborate 상수 도메인(미폴딩 param→**silent 0**(`W=MODE?16:8`→0), u32 도메인의 `1<<32` 오라클 발산·signed AShr·하강 genvar 폭주) + **P1 의미론**(`$fatal` no-op→**실패 TB exit 0**, force/release no-op, 비상수 `#delay`→#0, `$display("a=",a)` 인자 유실 등). Gemini shift fix(2026-06-10)는 검토 후 채택 — 단 근거 오류·잔존 한계는 P0-6으로 이관. **전 항목·증거·수정방향 = [REMAINING_WORK](REMAINING_WORK.md) P0/P1/P2.**
- **C7 — ✅ 검증+수정 완료 (2026-06-07, `fbb869c`).** `flush_postponed`가 `$strobe`/`$monitor`를 **마지막 실행 프로세스의 timescale multiplier**로 렌더하던 실버그 확인됨(혼합 timescale: 1ns 서브모듈의 `$strobe`가 같은 tick에 나중 실행된 1ps 형제의 `M`으로 `$time` 렌더). 수정: 등록 시점 `cur_time_mult`를 `FmtCapture.time_mult`에 스냅샷 → flush에서 per-capture로 렌더, 진입값 복원. 회귀 `cli/tests/timescale_postponed.rs`. *(주의: 단일 top만 실험으로 안 됨 — 아래 멀티-top 항목 참조. 반드시 top이 서로 다른 timescale의 서브모듈을 instantiate해야 재현.)*
- **문서부채 — ✅ 정리 완료 (2026-06-07).** doc-01 freeze 표 `enum`/`typedef`/packed `struct`를 IN-MVP로 정정(`union`/`string`/동적배열은 deferred 유지) · `$stime` **미구현**(`VITA-E3009`)을 hdl-ref/06/08에 명기 · `%t` plain-decimal(=`%0d`, `$timeformat`·필드폭 미적용) caveat 추가.
- **멀티-top-module 다중 root elaborate — ✅ 검증+수정 완료 (2026-06-08).** 인스턴스화되지 않은 bare top 모듈이 여럿이면 **마지막 선언된 것의 계층만** 시뮬되고 나머지는 조용히 누락하던 실버그 확인(immediate `$display`조차 안 나옴). 수정: `pick_top`(단일)→`pick_roots`(미인스턴스 **전부**를 선언순 root로) + `collect_instantiated`(generate 블록 재귀 스캔으로 generate-nested 자식이 spurious root 되는 것 방지) + `run`이 root마다 `elaborate_instance` 호출. **골든 무영향**(단일-top 설계는 root 1개 → byte-identical; sim-ir 타입 무변경, format_version 3 유지). VCD는 다중 top-level `$scope`로 정확 방출(범용 sorted-leaf 트리 walk가 단일 root 미가정). 중복 모듈명은 canonical(first-decl)로 dedup, cycle/pure-library는 last-declared fallback. 회귀: `elaborate` `v3_2b`(두 root)·`v3_2c`(generate-nested ≠ root), `cli/tests/multi_top.rs`(end-to-end 두 top + hierarchy 공존). IEEE 1364/iverilog 기본(미인스턴스=root) 일치. *(447 tests green, differential 7 + backend_equiv 11.)*

### C. 컴파일드 백엔드 전략 — ✅ 결정 + 🔨 C4-lite 착수 (2026-06-08)

1차 질문은 "eval=~4%면 VM 계속 갈 가치 있나?"였고 답은 "동결"이었다. **연산자수 스윕이 그 전제를
뒤집었다**(eval = 식 복잡도에 선형, 식-바운드 70-82%). **결정: native-eval(plan C4~C9)을 식-바운드 perf의
정당한 방향으로 채택** — "동결" 폐기. **→ 2026-06-08 C4-lite 첫 증분 랜딩**(아래).

- **왜 채택:** 식-바운드 RTL(ALU·crypto·깊은 조합)에서 native-eval 설계당 ~2-3x. 현 VM(문장 컴파일)은
  이 영역에 무력(`EXPR_HEAVY` 0.92x). 스케줄러 축(§A)과 상보 — 클럭-바운드는 스케줄러, 식-바운드는 native-eval.
- **왜 안전:** P5 차분 게이트(compiled==interp byte동일) + iverilog 오라클이 4-state 정확성 리스크를 강제.
  새 백엔드가 한 비트라도 틀리면 게이트가 즉시 red — native-eval을 "정확성 by-construction"으로 시도 가능.
- **🔨 C4-lite 착수 (랜딩됨):** **VM 전용 native 평가기 `native_eval.rs`** — codegen-able 바디의 assign RHS를
  post-order 레지스터 프로그램으로 컴파일(노드당 `Value` 미생성). **지원 서브셋: ≤64bit 정수** Const·scalar Signal·
  Add/Sub/Mul·BitAnd/Or/Xor/Xnor·BitNot/Plus/Minus. 그 외(real·>64bit·array-index·Div/Mod/Pow/시프트/비교/리덕션/
  ternary/concat/select/sysfunc/call)는 `try_compile`이 `None`→`eval_ctx` fallback. **인터프리터=오라클**,
  leaf는 `read_net`+`resize_keep_sign` 정확 재사용, 산술은 X/Z poison+u64 wrapping(w≤64는 sign-무관), bitwise는
  `value::{and,or,xor,xnor,not}_w` 동일 primitive. 측정: **expr-heavy VM 0.42x(≈2.3x), 클럭-바운드 0.94x 불변**.
  검증: native_eval 오라클 대조 단위 8 + backend_equiv native teeth 5 + 72-design P5 차분 + iverilog 차분, 460 green.
- **follow-on(다음 증분):** 비교/시프트/Div·Mod/리덕션/ternary/select·concat → 각각 의미론 추가; >128bit·signed-lane·real(C6);
  C9 인프라(content-addressed codegen 캐시·`kernel_abi_version` 헤더·ExprId→SourceLoc). frozen sim-ir 0줄 변경 유지.

### D. 언어/기능 커버리지 (perf 아님 — "유용성" 트랙)

vitamin은 **서브셋** 시뮬레이터. 실사용 가치는 "더 빠르게"보다 **"더 많은 RTL 지원"**일 수 있다. 의도적 deferral 목록 — ~~전부 loud-reject 확인됨~~ **(2026-06-10 감사 정정: 거짓이었음.** `force/release`/proc-`assign`/`->event`/`disable`은 **warn+no-op로 계속 시뮬**(값 불변·`@(ev)` 행), 비상수 `#delay`는 **silent `#0` 강등**. loud-reject 승격 항목 = REMAINING_WORK P1-2/P1-3.**)**

- 프랙셔널 `#2.5`/`$realtime` 정밀(timescale precision ratio 일부)
- dynamic/associative array, queue (정적 평탄화 불가 → 새 IR 노드 필요)
- `disable` 실동작(현재 no-op), `for (int i = ...)` SV inline-decl
- 추가 SV 구문 (interface, package, assertion 등 — Phase-2+)
- `$fatal/$error/$warning/$info`·`$displayb/o/h` 16종·`%m` 실경로·implicit net — 감사로 갭 확정, REMAINING_WORK P1/P2에 등재

### E. 병렬화 (신규 트랙 · 2026-06-10)

현황: 스레딩 0·계획 0이었음(doc-18:19가 PDES만 "결정성 충돌·장기"로 박제). 감사 결론 — **엔진 내부 병렬(PDES/Verilator식 파티셔닝)은 결정성 invariant(3-OS byte-identical, tie 순서, eager VCD)와 정면충돌이라 최저 ROI(연구 트랙 유지)**, 실질 윈은 엔진 밖:

| 단계 | 내용 | 리스크/공수 |
|---|---|---|
| T0a | P5 차분(interp·VM) `thread::scope` 동시 실행 + Send sink | 0 / 시간 |
| T0b | VCD `BufWriter`(현 레코드당 ~1 syscall!) + dump-heavy perf 측정 | 0 / 시간 |
| T1 | `--threads ≥2`: VCD 전용 writer 스레드(bounded FIFO, byte 순서 보존) | 低 / 일 |
| T2+ | front-end per-CU(보류) · parallel elaborate(비추천: arena ID=골든 계약) · PDES(연구) | 中~最高 |

**옵션 설계:** `--threads N`/`-j N`(vita·vrun), 기본 auto=`min(available_parallelism,8)`, env `VITA_THREADS`, `--threads 1`=현행 동일. **계약 = "모든 N에서 출력 byte-identical"**, corpus `--threads 1` vs `4` byte-diff 게이트로 강제. SimOpts out-of-band(골든 무영향). 상세 = REMAINING_WORK §P4.

---

## 2. 추천 우선순위 (다음 세션)

- ~~C7 `cur_time_mult`-during-postponed 버그 검증~~ — ✅ 완료 (`fbb869c`).
- ~~문서부채 정리~~ — ✅ 완료 (doc-01/05/06/08/display-io).
- ~~컴파일드 백엔드 전략 결정 (§C)~~ — ✅ 결정됨: **native-eval 채택**(식-바운드 perf), "동결" 폐기. 착수는 perf 우선화 시점.
- ~~멀티-top-module 다중 root elaborate (§B)~~ — ✅ 완료 (2026-06-08): `pick_roots`+generate 재귀 스캔, 골든 무영향, 447 tests.
- ~~native-eval 착수 (식-바운드 perf, §A/§C)~~ — 🔨 **C4-lite 랜딩 (2026-06-08): ≤64bit 정수 서브셋, expr-heavy VM 0.42x(≈2.3x), 460 tests, frozen sim-ir 무변경.**

**(2026-06-10 재구성 — 감사 결과로 correctness가 perf보다 앞으로.)**

1. **P0 정확성 클러스터 (§B 감사)** — ①`to_u64` 계약 수정+호출부 10곳(relational/shift/negate/offset/delay) ②elaborate silent-0 박멸(Cond·$clog2 폴딩+미폴딩=Error) ③const 도메인 부호 i64 확대(하강 genvar 포함). 전부 소~중규모·고가치. = REMAINING_WORK P0-1~7.
2. **P1-1 `$fatal` 계열** — 최소 $fatal→error-exit 브리지(실패 TB가 exit 0인 현재는 CI 신뢰 불가). + P0-8 `$display` 인자 의미론.
3. **P2 운용 quick wins** — VCD open/flush 진단·delta-limit 진단·`--help/--version`·아티팩트 temp+rename·parser depth cap·array_len cap.
4. **병렬화 T0a/T0b → T1 (§E)** — 측정 게이트(T0b) 통과 시 `--threads` writer 스레드.
5. **native-eval 연산자 커버리지 확장 (§C follow-on)** — 비교/시프트/Div·Mod/리덕션/ternary/select·concat(각 P5 게이트 byte동일). 식-바운드 적용폭 확대.
6. **perf 트랙 (워크로드 분기)** — 클럭-바운드 → **스케줄러 축**(event wheel·propagate·NBA) / >64bit·real native lane(C6, 고위험).
7. **언어 커버리지 (§D)** + P1 나머지(force/release 승격, in-body @(*), b/o/h radix) — 유용성 확장.
8. **저빈도 perf 잔여 (§A)** + P3 메모리(fork 아레나 컴팩션 등).

---

## 3. 교훈 (방법론 — 재사용 가치)

- **병목은 양파다.** doc-18의 두 예측(Value-alloc·tree-walk)이 첫 측정엔 둘 다 "아님"이었지만, 실은 bit-serial 처리가 alloc을 가리고 있었을 뿐. 표면층 제거 → 재측정 → 다음 층. **최적화는 한 번 측정으로 끝나지 않는다.**
- **"실패한" 실험도 선행 최적화 후 재시도 가치.** inline-Value가 1차엔 ~0(net-write per-bit 루프가 alloc 가리고 Deref 오버헤드 상쇄) → 그 루프 word化 후 3차엔 1.55x.
- **사이클 = profile → 최소 fix → re-profile 반복.** 각 fix는 항상 bit-exact(suite + iverilog 차분이 스펙). `cargo test -p sim-engine --test perf_baseline -- --ignored --nocapture`로 before/after 측정, `/usr/bin/sample`(macOS, sudo 불요)로 self-time 히스토그램.
- **공유 경로 최적화가 backend-전용보다 유리했다** — interp·VM 둘 다 빨라지고 위험도 낮음.
- **타 모델 수정 리뷰는 "코드 ≠ 서술" (2026-06-10).** Gemini shift fix는 코드는 옳았지만 근거 두 건이 틀렸다(존재하지 않는 "중복 매치 암", 오라클 미확인 "0이 정답" — iverilog는 4294967296). 리뷰는 diff만 읽지 말고 **오라클 라이브 차분**(t1/t2)으로 닫을 것. 또: "warn 떴으니 loud-reject"라고 믿지 말 것 — warn+no-op는 silent-wrong의 사촌(§D 정정 사례).
