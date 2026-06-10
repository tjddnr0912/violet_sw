# ROADMAP — Stage C 이후 향후 과제 (vitamin)

> **갱신:** 2026-06-10 — **7축 감사**(Gemini-fix 검토/spec-gap/sim-engine/front-end/메모리/운용성/병렬화) 반영: correctness 트랙 재개(§B), §D 사실관계 정정, **병렬화 트랙 §E 신설**. 잔여 항목의 단일 트래커 = [`REMAINING_WORK.md`](REMAINING_WORK.md).
>
> **동일자 후속(HEAD `0945dfe`, 566 green): 감사 발견 항목 일괄 처리 완료** — P0 정확성 9 · P1 의미론 9(severity/radix/`%m` 사이드테이블, in-body @(*), finish-flush, per-bit 멀티드라이버, E3018) · P2 운용 11/12(`--help/--version`·`--threads`·`--timeout`, VCD/델타 진단, 원자적 아티팩트, parser/array 캡, W3056 taxonomy) · P3 메모리 4(fork free-list·monitor in-place·clone 제거·native 고정스택) · P4 T0a/T0b/T1(`--threads` VCD writer 스레드, byte-identical 게이트, 실측 VCD 비중 40.9%) · native-eval follow-on(비교/시프트/DivMod/ternary/리덕션/논리 — expr-heavy VM 0.42x, eval-heavy 0.54x). **이후 P2-12 정책 소항목(`time` 64-bit unsigned 수용·`` `pragma`` 수용-무시·timescale clamp·implicit-net 명문화·same_path 회귀)과 P5 문서 동기화(-W* 미래형·예약 codes·exit 0/1/3)까지 같은 날 소진(571 green) — 트래커 완결.** 잔여 = §C/§E perf 축 + Phase-1.x.
> **2탄(같은 날, HEAD `8664627`, 611 green): perf 축 + Phase-1.x 전부 소진** — ①스케줄러축 라운드1(클럭-바운드 **≈1.85x**: "스케줄러-바운드"의 ~45%가 malloc/free였음 → 핫루프 할당 9원 제거) ②native-eval 구조 lane(select/concat/replicate — 신규 STRUCT_HEAVY 벤치 **VM 0.36x ≈2.8x**) ③vita-log 실코드화(`-Wno-*`/`-Werror=` 게이트 + exit class 2) ④filelist `-f`/`-F`(argv-레벨 전개) ⑤`vita explain` ⑥**format_version 4**(런타임 `#delay`=ExprId suspension-time 평가·`$dumpflush`/`$dumplimit`·`REGEN_GOLDEN=1` 골든 재생성 스위치) ⑦force/release(sample-once, per-net forced 플래그 — iverilog 오라클 동일 모델). **남은 트랙 = §1 잔여 표(아래) + Phase-2.**
> 직전: 2026-06-08 native-eval C4-lite 랜딩 + 멀티-top 다중 root. 현 단계 = **Stage C C1·C2 완료**(VM MVP, byte-identical) + **profile-driven 최적화 누적 ~6x**(eval-heavy 2781→461ms). 이 문서는 *여기서부터 무엇을 할지*를 트랙별로 정리한 단일 진실. perf 이력 = [`preview/18-acceleration-analysis.md`](preview/18-acceleration-analysis.md) §실측(+구 트래커 git 이력), 설계는
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
| **스케줄러 축 — ✅ 라운드 1 완료(2026-06-10)** | `sched.rs`·`exec.rs`·`state.rs` 핫루프 할당 제거 | **실현: 클럭-바운드 ≈1.85x** | profile 결과 "스케줄러-바운드"의 ~45%가 malloc/free였음 — snapshot_prev/refresh-prev `clone_from`化, propagate 스크래치 재사용, wheel 버킷 풀, active/nba capacity 반납, `&'ir` reborrow로 Stmt/블록/Lvalue/args 클론 0, `Offsets` 인라인 enum. interp 61.8→33.4ms·VM 56.0→30.3ms, eval-heavy interp도 1.27x 부수개선. **잔여(라운드 2 후보): per-delta 전체-넷 스캔 → dirty-list**(넷 수 선형 — 대형 디자인용; 쓰기 훅+정렬로 byte-identity). 상세 = [doc-18 §실측 스케줄러축](preview/18-acceleration-analysis.md) |
| **native-eval (eval 코드젠) — 🔨 C4-lite 착수** | `native_eval.rs`(신규) + `backend.rs` `Op::EvalNative` | **식-바운드 高 / 그 외 低** | **C4-lite 랜딩(2026-06-08): ≤64bit 정수 서브셋**(Const·scalar Signal·Add/Sub/Mul·And/Or/Xor/Xnor·Not/Plus/Minus)을 VM 전용 native 레지스터로 평가, 그 외는 `eval_ctx` fallback. **expr-heavy에서 VM 0.92x→0.42x(≈2.3x), 클럭-바운드 불변(0.94x)** — 식-바운드 ~2-3x 예측 실현. 인터프리터=오라클, P5 차분게이트가 byte동일 강제. **follow-on 2탄(2026-06-10): select/concat/replicate 합류 — 신규 STRUCT_HEAVY 벤치 VM 0.36x(≈2.8x)**, 잔여 lane = >64bit/real/array-indexed/sysfunc |

**판단(2026-06-10 갱신):** 세 축 모두 1라운드 수확 완료 — value word化 ~6x(eval-heavy) · 스케줄러축 ≈1.85x(클럭-바운드) · native-eval ≈2.4~2.8x(식/구조-바운드 VM). **잔여 perf 후보(ROI 순): ①native >64bit/real/array-indexed lane**(C6 — 멀티워드 레지스터 파일, 고위험) ②저빈도 value-op word化·미세최적화(위 표 1·2행) ③net_to_edge/waiter 자료구조(다음 다넷 스케일링 층). *(dirty-list R2는 2026-06-10 완료 — NETS_HEAVY ≈19.7x.)*

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

vitamin은 **서브셋** 시뮬레이터. 실사용 가치는 "더 빠르게"보다 **"더 많은 RTL 지원"**일 수 있다.
2026-06-10 2탄까지의 결과: ~~force/release~~(✅ sample-once 구현) · ~~비상수 `#delay`~~(✅ 런타임 평가, v4) ·
~~`$fatal` 계열·b/o/h·`%m`~~(✅) · ~~`time` 타입~~(✅) · ~~`$dumpflush/$dumplimit`~~(✅) — **잔여 deferral은 전부
loud-reject로 확인됨(이제 참):**

- proc-`assign`/`deassign` · `->event`+`@(ev)` · `disable` 실동작 — loud-reject 유지(Phase-2 제어흐름)
- force/release **full 재평가 모델**(IEEE 절차적 연속 대입 — 현 sample-once는 iverilog 동일 모델, doc-01 v1 단순화 표)
- intra-assignment delay(`a = #d b`) — warn+drop → 실semantics(Phase-1.x 후순위)
- dynamic/associative array, queue (정적 평탄화 불가 → 새 IR 노드 = 차기 format bump 후보)
- `+incdir+`/`+define+` filelist 버킷(PreOpts 플러밍), implicit-net 추론(W2003 활성화), `-Wwarn=`/`--log` tee
- 추가 SV 구문 (interface, package, assertion 등 — Phase-2+)

### E. 병렬화 (신규 트랙 · 2026-06-10)

현황: 스레딩 0·계획 0이었음(doc-18:19가 PDES만 "결정성 충돌·장기"로 박제). 감사 결론 — **엔진 내부 병렬(PDES/Verilator식 파티셔닝)은 결정성 invariant(3-OS byte-identical, tie 순서, eager VCD)와 정면충돌이라 최저 ROI(연구 트랙 유지)**, 실질 윈은 엔진 밖:

| 단계 | 내용 | 리스크/공수 |
|---|---|---|
| T0a | P5 차분(interp·VM) `thread::scope` 동시 실행 + Send sink | 0 / 시간 |
| T0b | VCD `BufWriter`(현 레코드당 ~1 syscall!) + dump-heavy perf 측정 | 0 / 시간 |
| ✅T1 | ~~`--threads ≥2`: VCD 전용 writer 스레드~~ — 완료(2026-06-10, byte-identical 게이트) | — |
| T2+ | front-end per-CU(보류) · parallel elaborate(비추천: arena ID=골든 계약) · PDES(연구) | 中~最高 |

**옵션 설계:** `--threads N`/`-j N`(vita·vrun), 기본 auto=`min(available_parallelism,8)`, env `VITA_THREADS`, `--threads 1`=현행 동일. **계약 = "모든 N에서 출력 byte-identical"**, corpus `--threads 1` vs `4` byte-diff 게이트로 강제. SimOpts out-of-band(골든 무영향). 상세 = REMAINING_WORK §P4.

---

## 2. 추천 우선순위 (다음 세션)

- ~~C7 `cur_time_mult`-during-postponed 버그 검증~~ — ✅ 완료 (`fbb869c`).
- ~~문서부채 정리~~ — ✅ 완료 (doc-01/05/06/08/display-io).
- ~~컴파일드 백엔드 전략 결정 (§C)~~ — ✅ 결정됨: **native-eval 채택**(식-바운드 perf), "동결" 폐기. 착수는 perf 우선화 시점.
- ~~멀티-top-module 다중 root elaborate (§B)~~ — ✅ 완료 (2026-06-08): `pick_roots`+generate 재귀 스캔, 골든 무영향, 447 tests.
- ~~native-eval 착수 (식-바운드 perf, §A/§C)~~ — 🔨 **C4-lite 랜딩 (2026-06-08): ≤64bit 정수 서브셋, expr-heavy VM 0.42x(≈2.3x), 460 tests, frozen sim-ir 무변경.**

**(2026-06-10 2탄 갱신 — 위 1~8 전부 완료. 다음 후보:)**

1. ~~스케줄러 라운드 2: dirty-list 넷 스캔~~ — ✅ 2026-06-10. dirty-list + `snapshot_prev` 삭제(증명된 no-op)로 **NETS_HEAVY 305→15.5ms ≈19.7x**(idle-넷 세금 제거), byte-identity 스위트 전부 green. 다음 스케일링 후보 = net_to_edge/waiter 자료구조.
2. ~~filelist typed 버킷~~ — ✅ 2026-06-10. `-D`/`-I` + `+define+`/`+incdir+`(verbatim/베이스해소) → PreOpts, `E-FLIST-WRONG-STAGE`(velab/vrun), `W-FLIST-OVERRIDE`(단일값 knob last-wins 경고). 잔여=DUP-CTX(sticky 도입 시)·--dump-filelist.
3. **native-eval C6 lane** — >64bit(멀티워드 레지스터)·real·array-indexed Signal·sysfunc. 고위험(P5 게이트 필수), 식-바운드 적용폭 확대.
4. **vita-log 2단계** — `--log` tee(단일 writer 불변식, doc-13)·`-q`/`-v` verbosity·counts summary epilogue.
5. **언어 커버리지(§D 잔여)** — intra-assignment delay 실semantics · force full 재평가 · implicit-net 추론(W2003).
6. **Phase-2 관문** — dynamic array/queue·interface·assertion은 새 IR 노드 = 차기 format bump로 묶어서.
7. **운영 인프라** — 3-OS CI 매트릭스 실구동(doc-09 §285 스케치 → 실 워크플로), `--dump-filelist`, RULE-V composite 해시(Phase-2).

---

## 3. 교훈 (방법론 — 재사용 가치)

- **병목은 양파다.** doc-18의 두 예측(Value-alloc·tree-walk)이 첫 측정엔 둘 다 "아님"이었지만, 실은 bit-serial 처리가 alloc을 가리고 있었을 뿐. 표면층 제거 → 재측정 → 다음 층. **최적화는 한 번 측정으로 끝나지 않는다.**
- **"실패한" 실험도 선행 최적화 후 재시도 가치.** inline-Value가 1차엔 ~0(net-write per-bit 루프가 alloc 가리고 Deref 오버헤드 상쇄) → 그 루프 word化 후 3차엔 1.55x.
- **사이클 = profile → 최소 fix → re-profile 반복.** 각 fix는 항상 bit-exact(suite + iverilog 차분이 스펙). `cargo test -p sim-engine --test perf_baseline -- --ignored --nocapture`로 before/after 측정, `/usr/bin/sample`(macOS, sudo 불요)로 self-time 히스토그램.
- **공유 경로 최적화가 backend-전용보다 유리했다** — interp·VM 둘 다 빨라지고 위험도 낮음.
- **타 모델 수정 리뷰는 "코드 ≠ 서술" (2026-06-10).** Gemini shift fix는 코드는 옳았지만 근거 두 건이 틀렸다(존재하지 않는 "중복 매치 암", 오라클 미확인 "0이 정답" — iverilog는 4294967296). 리뷰는 diff만 읽지 말고 **오라클 라이브 차분**(t1/t2)으로 닫을 것. 또: "warn 떴으니 loud-reject"라고 믿지 말 것 — warn+no-op는 silent-wrong의 사촌(§D 정정 사례).
