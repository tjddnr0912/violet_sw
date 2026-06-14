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
| ~~저빈도 value-op word化~~ ✅ 2026-06-11 | `eval.rs` 4종 word-parallel(`copy_bits` funnel) | 실현: STRUCT_HEAVY interp ≈1.44x | OOB-혼합 select만 bit-serial 폴백 잔존 |
| ~~`has_xz`/`arith`/`to_u128` 미세~~ | `value.rs`/`eval.rs` | — | ✅ 2026-06-11 **검사-폐기**: inline-Value 라운드 때 이미 word-parallel(마스크된 word 로드, bit 루프 0) — 남은 게 없음 |
| **스케줄러 축 — ✅ 라운드 1 완료(2026-06-10)** | `sched.rs`·`exec.rs`·`state.rs` 핫루프 할당 제거 | **실현: 클럭-바운드 ≈1.85x** | profile 결과 "스케줄러-바운드"의 ~45%가 malloc/free였음 — snapshot_prev/refresh-prev `clone_from`化, propagate 스크래치 재사용, wheel 버킷 풀, active/nba capacity 반납, `&'ir` reborrow로 Stmt/블록/Lvalue/args 클론 0, `Offsets` 인라인 enum. interp 61.8→33.4ms·VM 56.0→30.3ms, eval-heavy interp도 1.27x 부수개선. **잔여(라운드 2 후보): per-delta 전체-넷 스캔 → dirty-list**(넷 수 선형 — 대형 디자인용; 쓰기 훅+정렬로 byte-identity). 상세 = [doc-18 §실측 스케줄러축](preview/18-acceleration-analysis.md) |
| **native-eval (eval 코드젠) — 🔨 C4-lite 착수** | `native_eval.rs`(신규) + `backend.rs` `Op::EvalNative` | **식-바운드 高 / 그 외 低** | **C4-lite 랜딩(2026-06-08): ≤64bit 정수 서브셋**(Const·scalar Signal·Add/Sub/Mul·And/Or/Xor/Xnor·Not/Plus/Minus)을 VM 전용 native 레지스터로 평가, 그 외는 `eval_ctx` fallback. **expr-heavy에서 VM 0.92x→0.42x(≈2.3x), 클럭-바운드 불변(0.94x)** — 식-바운드 ~2-3x 예측 실현. 인터프리터=오라클, P5 차분게이트가 byte동일 강제. **follow-on 2탄(2026-06-10): select/concat/replicate 합류 — 신규 STRUCT_HEAVY 벤치 VM 0.36x(≈2.8x)**. **C6 lane(2026-06-10): array-indexed Signal(`LoadIndexed`, OOR/X 인덱스 sentinel 오라클 패리티) + 65..=128bit wide lane(별도 u128-pair 스택, narrow 무변경)** — WIDE_HEAVY 0.59x(≈1.7x)·MEM_HEAVY 0.72x(≈1.4x). **v6 ④(2026-06-11): wide 구조 트리오 랜딩**(WSelect/WConcatPair/WRepl, 65..=128bit 혼합-스택 — WIDE_STRUCT_HEAVY **VM 0.44x ≈2.3x**) + **real lane 측정-폐기**(REAL_HEAVY VM 0.90x — real은 합성 핫패스에 부재, 프로브 영구 잔류). 잔여 lane = signed >64 arith(오라클 X-poison 영역)·>128bit·sysfunc — 전부 컴파일-시 오라클 bail, 저ROI 박제 |

**판단(2026-06-10 갱신):** 세 축 모두 1라운드 수확 완료 — value word化 ~6x(eval-heavy) · 스케줄러축 ≈1.85x(클럭-바운드)+dirty-list R2(NETS_HEAVY ≈19.7x) · native-eval ≈1.4~2.8x(식/구조/wide/mem-바운드 VM, C6 포함). **~~①저빈도 value-op word化~~ ✅ 2026-06-11 — `eval_select`(in-range 단일 copy)/`eval_concat`/`eval_replicate`/`merge_x`를 word-parallel `copy_bits`(64-bit 두-워드 funnel 윈도)로 전환: STRUCT_HEAVY **인터프리터 551→382ms ≈1.44x**(VM 불변 — native lane 별개), 타 lane 회귀 0(725 green·iverilog 차분 포함). 잔여 perf 후보: `has_xz`/`to_u128` 미세(소소)·wide 구조 트리오·real native lane(좁은 영역, 저ROI).** *(C6 array-indexed + 128-bit lane ✅ 2026-06-10 — doc-18 §실측. net_to_edge/waiter 다넷 후보는 `perf_nets_scaling` 프로브(512→8192 평탄)로 **무근거 판명·폐기** — 같은 날.)*

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

- ~~proc-`assign`/`deassign` · `disable` 실동작~~ ✅ 2026-06-10 (§F-(F)) — **disable**: 동봉 named block의 break/continue 이디엄 실구현(doc-17 "Disable 후 Goto", lazy exit-BB로 기존 디자인 byte-불변; 크로스-프로세스/task/fork-경계/계층 경로=loud). **proc-assign/deassign**: force 기계 weak-rank 재사용(`assign_ranks` 사이드카 — force가 assign을 latent로 밀어내고 release가 복귀; iverilog const-rhs 차분 일치, 식-RHS는 iverilog "evaluated once" 자인이라 hand-IEEE 핀). `->event`+`@(ev)`만 잔존 — **단, 카운터-desugar 설계로 bump 불요 가능성 확인(§F-(B) 참조)**
- ~~force/release **full 재평가 모델**~~ ✅ 2026-06-10 — expression force는 IEEE §9.3.2 연속 재평가(`active_forces` 레지스트리, delta마다 재핀·BTree 결정성·mult 스냅샷). **iverilog와 의도적 발산**(iverilog는 "sorry: evaluated once" 자인 — const-rhs 차분만 유지, expression lane은 hand-IEEE end_to_end 핀)
- ~~intra-assignment delay(`a = #d b`)~~ ✅ 2026-06-10 — **blocking 형은 실semantics**(capture-now/write-later: tmp(폭=lhs 정확) → `Terminator::Delay` → write; `#0`=inactive·런타임 d 지원, iverilog 차분 일치). **NBA 형(`<= #d`)은 loud E3009로 이관** — 값-운반 delayed NBA 이벤트가 없으면 겹침 활성화(transport delay)에서 silent-wrong이라 차기 format bump 묶음
- ~~dynamic/associative array, queue~~ ✅ v5+⑥로 전부 랜딩(엔진+문법) · **`foreach(arr[i])` ✅**(파서 desugar — v6에서 uniform first/next 워크로 재작업) · **v6 bump ✅ 2026-06-11**: queue `insert/delete(i)`·assoc `first/next/prev/last`(+assoc-foreach)·string 키·bounded queue `[$:N]`(사이드카) 전부 랜딩. 잔여 = full `string` 타입(Phase-3 — string-키 foreach의 8-byte ref-var 한계 해소용)
- `+incdir+`/`+define+` filelist 버킷(PreOpts 플러밍), implicit-net 추론(W2003 활성화), `-Wwarn=`/`--log` tee
- 추가 SV 구문 (interface, package, assertion 등 — Phase-2+)

### E. 병렬화 (신규 트랙 · 2026-06-10)

현황: 스레딩 0·계획 0이었음(doc-18:19가 PDES만 "결정성 충돌·장기"로 박제). 감사 결론 — **엔진 내부 병렬(PDES/Verilator식 파티셔닝)은 결정성 invariant(3-OS byte-identical, tie 순서, eager VCD)와 정면충돌이라 최저 ROI(연구 트랙 유지)**, 실질 윈은 엔진 밖. *(→ 2026-06-11 T4 연구가 이 프레임을 정정: 결정성은 보존 설계가 존재해 차단 요인이 아님 — 진짜 제약은 워크로드 폭·직렬 몫·공수. 아래 T4.)*:

| 단계 | 내용 | 리스크/공수 |
|---|---|---|
| T0a | P5 차분(interp·VM) `thread::scope` 동시 실행 + Send sink | 0 / 시간 |
| T0b | VCD `BufWriter`(현 레코드당 ~1 syscall!) + dump-heavy perf 측정 | 0 / 시간 |
| ✅T1 | ~~`--threads ≥2`: VCD 전용 writer 스레드~~ — 완료(2026-06-10, byte-identical 게이트) | — |
| ❎T2+ | ~~front-end per-CU~~ — **2026-06-11 측정 폐기**: 400모듈/12k라인 vcmp(전 front-end)=**~10ms**(비병목) + vita는 단일-CU concat 모델(파일 간 `` `define `` 가시성)이라 per-CU 분할은 의미론 변경 없이 불가. parallel elaborate(비추천: arena ID=골든 계약) 결론 유지 | 폐기(측정) |
| ❎T4 | ~~엔진 내 PDES~~ — **2026-06-11 타당성 연구 종결(조건부 NO-GO)**: 프로브 3종 실측(τ 상주풀 0.3~0.5µs/delta·naive spawn 31~93µs 즉사, g≈700ns/activation, BSP mock 디스패치 측 최대 3.9x@T4) + sample 분류(직렬 잔류 ~20% → **Amdahl 상한 T4 ≈2.5x**) → 이상적 wide-synchronous(W≥64)에서만 2~3x, **corpus 워크로드(W=1~8)는 0~손해**. byte-identical은 보존 설계 존재(NBA-pure 클래스+run-splitting+per-process 로그 머지 — by construction)로 차단 요인 아님. **재진입 조건 핀: 지속 W≥64 + grain≥200ns 실워크로드 출현 시 BSP v1 착수.** 상세 = [doc-18 §PDES 타당성 연구](preview/18-acceleration-analysis.md#pdes-타당성-연구-2026-06-11--p4-t4-종결) | 종결(연구) |

**옵션 설계:** `--threads N`/`-j N`(vita·vrun), 기본 auto=`min(available_parallelism,8)`, env `VITA_THREADS`, `--threads 1`=현행 동일. **계약 = "모든 N에서 출력 byte-identical"**, corpus `--threads 1` vs `4` byte-diff 게이트로 강제. SimOpts out-of-band(골든 무영향). 상세 = REMAINING_WORK §P4.

### F. Phase-2 관문 — 차기 format bump 묶음 (2026-06-10 평가)

**원칙:** SchemaHash flip(=전 `.velab` 무효 + REGEN_GOLDEN 절차)은 비용이므로 frozen-IR 형상 변경은
**한 번의 v5 bump에 일괄**. v4 절차(REGEN_GOLDEN=1 스위치·canonical txt·RON 재생성)가 그대로 재사용된다.
반대로 **IR-무변경으로 가능한 Phase-2 항목은 bump를 기다릴 이유가 없다** — front-end/사이드테이블만으로 먼저 간다.

| 항목 | IR 영향 | 평가 |
|---|---|---|
| ✅**(A) NBA delayed write** `q <= #d rhs` | **완료 2026-06-10 (v5)** — `NonblockingAssign.delay`(ExprId, 실행 시 평가·mult 스케일) + `delayed_nba` wheel(값-운반, `apply_nba` 전역 seq 정렬로 문장순 보존) | iverilog 차분 4레인(NBA-region 착지·겹침 transport·`#0` 문장순·인덱스 동결). finish-vs-due-update 동시-틱 tie는 도구-발산 영역으로 핀 |
| ✅**(B) named event + `->`/`@(ev)`** | **완료 2026-06-11, sim-ir 0** — 카운터 desugar(64-bit Reg init 0, `->e`=`e=e+1`, `@(e)`=AnyEdge; 같은-슬롯 이중 trigger도 edge 보존). 값-표면 전부 loud(읽기/쓰기/range/init) | iverilog 차분 3레인(trigger/wake·혼합 리스트·no-latch). `.vu` AST 해시 재핀(NetVarKind::Event) |
| **(C) dynamic array / queue / assoc array — 📐 설계 완료(2026-06-10)** | handle-net + 엔진 힙(`dyn_heap: BTreeMap<NetId, DynObj>`, BitPacked 스토어 비침투): `NetKind` +3, `SysFuncId` +5, `SysTaskId` +5, `Signal/LvalChunk` word 재사용 — **v5 형상 diff 전량 확정** | 설계 = [`superpowers/plans/2026-06-10-dynamic-storage-design.md`](superpowers/plans/2026-06-10-dynamic-storage-design.md) (MVP 컷·OOB=X+warn-once·VCD 미덤프·결정성 계약·bump 체크리스트 포함) |
| ✅(D) interface / modport — **스파이크 완료(GO)** | **SimIr 무변경 확정** — 신호=평범한 net + 심볼 aliasing(cont-assign 금지: 방향 없음), `.vu` AST 해시만 1회 flip(핀 골든 0) | 설계 = [`superpowers/plans/2026-06-10-interface-flattening-spike.md`](superpowers/plans/2026-06-10-interface-flattening-spike.md). 구현은 v5 묶음과 같은 시기 권장(AST flip 1회로 수렴) |
| ✅(E) immediate assertion `assert(e) else $error` | **무변경** — 파서가 `Stmt::If`로 desugar(AST 동결 유지) + 디폴트 실패는 `$error("Assertion failed")` 합성(severity 테이블 경유 stderr+exit1) | **완료 2026-06-10** (654 green, iverilog 차분 일치 — X-cond=fail 포함). concurrent SVA는 별개(거대, Phase-3), `assert property`/`#0`/`final`=loud |
| ✅(F) `disable` 실동작 / proc-`assign`/`deassign` | **완료 2026-06-10, bump 0** — disable=동봉 named block Goto(lazy exit-BB, 기존 CFG byte-불변·비동봉은 loud); proc-assign=Force/Release 재사용+`assign_ranks` 사이드카(weak rank·latent 복귀, `.velab` trailer 세그먼트 append) | 665 green, iverilog 차분(disable 3종·assign const-rhs 2종)+staged trailer 왕복 |

**진입 시퀀스(권장):** ① IR-무변경부터 — ~~(E) immediate assert~~✅ → ~~(D) interface 스파이크~~✅ → ~~(F)~~✅ ②
~~(C) dynamic storage **설계 문서**~~✅ ③ ~~v5 bump 일괄~~✅ **완주(2026-06-10/11)**: bump(형상+REGEN, `e7f08e8`) → (A) 구현(`1617980`) → (B) 구현(`0a39dec`). **(C) 엔진 증분 ~~③dyn array~~✅·~~④queue~~✅·~~⑤assoc~~✅·~~⑥front-end 일괄~~✅(2026-06-11, 722 green — dyn/queue 문법은 iverilog 차분, assoc·interface는 iverilog 자체 미지원이라 hand-IEEE 핀; SimIr 무변경·.vu 재핀 1회). §F 전 항목 소진 — 잔여 후속 = modport 방향 강제·iface 파라미터·dyn 슬라이스/중첩 등 MVP cut 명시분** — [설계 문서 §6](superpowers/plans/2026-06-10-dynamic-storage-design.md) 순서.

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
3. ~~native-eval C6 lane~~ — ✅ 2026-06-10. array-indexed Signal(`LoadIndexed`/`WLoadIndexed`, OOR/X→sentinel) + 65..=128bit wide lane(별도 u128-pair 스택 — narrow 무변경·무세금, WIDE_STACK=8). WIDE_HEAVY 0.59x·MEM_HEAVY 0.72x. 잔여 native lane(저ROI 문서화): signed >64 arith/divmod(오라클 X-poison 영역)·wide 구조 트리오·>128bit·real·sysfunc.
4. **vita-log 2단계** — `--log` tee(단일 writer 불변식, doc-13)·`-q`/`-v` verbosity·counts summary epilogue.
5. ~~언어 커버리지(§D 잔여)~~ — ✅ 2026-06-10 intra-assignment delay(blocking 실구현·NBA는 loud-defer→bump 묶음) · force 연속 재평가. implicit-net은 P2-12에서 **E3010 정책으로 확정**(추론 대신 명시적 에러 — `default_nettype` 지원이 미래 옵션) — 항목 종결.
6. ~~Phase-2 관문~~ — ✅ 2026-06-10/11 §F 진입 시퀀스 완주: (E) assert·(D) 스파이크·(F) disable/proc-assign·(C) 설계·v5 bump·(A) NBA-delay·(B) named-event. 잔여 = (C) 엔진 증분(③④⑤)+⑥ front-end.
7. **운영 인프라** — 3-OS CI 매트릭스 실구동(doc-09 §285 스케치 → 실 워크플로), `--dump-filelist`, RULE-V composite 해시(Phase-2).

---

## 3. 교훈 (방법론 — 재사용 가치)

- **병목은 양파다.** doc-18의 두 예측(Value-alloc·tree-walk)이 첫 측정엔 둘 다 "아님"이었지만, 실은 bit-serial 처리가 alloc을 가리고 있었을 뿐. 표면층 제거 → 재측정 → 다음 층. **최적화는 한 번 측정으로 끝나지 않는다.**
- **"실패한" 실험도 선행 최적화 후 재시도 가치.** inline-Value가 1차엔 ~0(net-write per-bit 루프가 alloc 가리고 Deref 오버헤드 상쇄) → 그 루프 word化 후 3차엔 1.55x.
- **사이클 = profile → 최소 fix → re-profile 반복.** 각 fix는 항상 bit-exact(suite + iverilog 차분이 스펙). `cargo test -p sim-engine --test perf_baseline -- --ignored --nocapture`로 before/after 측정, `/usr/bin/sample`(macOS, sudo 불요)로 self-time 히스토그램.
- **공유 경로 최적화가 backend-전용보다 유리했다** — interp·VM 둘 다 빨라지고 위험도 낮음.
- **타 모델 수정 리뷰는 "코드 ≠ 서술" (2026-06-10).** Gemini shift fix는 코드는 옳았지만 근거 두 건이 틀렸다(존재하지 않는 "중복 매치 암", 오라클 미확인 "0이 정답" — iverilog는 4294967296). 리뷰는 diff만 읽지 말고 **오라클 라이브 차분**(t1/t2)으로 닫을 것. 또: "warn 떴으니 loud-reject"라고 믿지 말 것 — warn+no-op는 silent-wrong의 사촌(§D 정정 사례).

---

## 4. Phase-2+ 퓨처 플랜 (2026-06-11 — Phase-1 작업 큐 소진 후 스코프 결정용)

> Phase-1 큐 소진(765 green, format_version 6, PDES 연구 종결) 시점의 **전체 잔여 지형도**.
> 두 축으로 펼친다: §4.1 스코프 확장 트랙(결정 대기) · §4.2 의도적 MVP 컷 인벤토리(전부 loud/문서화 —
> 해제 시 합류 트랙 매핑). 원칙은 그대로: **frozen-IR 변경은 한 번의 v7 bump에 일괄**(§F 선례),
> IR-무변경 항목 선행, 오라클(iverilog) 차분 가능 영역 우선, 진입 전 §F식 관문 평가(스파이크→설계→bump).

### 4.1 스코프 확장 트랙

| 트랙 | 내용 | IR/AST 영향 | 오라클 | 공수 | 비고 |
|---|---|---|---|---|---|
| ~~**P2-A worklib**~~ ✅ **2026-06-12 v1 완료**(`33ec95c`+`db48aa1`) | `vcmp --work`(lib.toml 정규형+content-addressed CU blob, E2001 dup·소스경로 재컴파일=교체·GC) + `velab -L/--top`(클로저 로딩·**unit_map 승자 기반 머지** — passenger 그림자가 로드 순서로 이기는 결함을 자가 리뷰로 적발·수정) + **vrun RULE-V 자동 게이트**(매니페스트/blob/소스·include raw 재해시=E9003 exit 2) + E9005 신설. 적대 리뷰 9불변식 PASS. 디퍼: `-y`/`-v`/`-P`/`--lib-map`·per-unit blob·vrun -L 재배치. E8003 sticky 일반화=**N/A 판정**(sticky 표면이 timescale뿐 — 이미 커버) | 0 (bump 0, 골든 불변) | e2e 11 | 완료 | lib-모드 .velab의 경로 문자열은 same-machine 스코프(리뷰 D-9: cross-OS 복사는 loud exit 2) |
| ~~**P2-B Phase-2 system tasks**~~ ✅ **2026-06-12 완료**(v7 슬라이스 2~7) | casez/casex 정밀(`CasezEq/CasexEq` — x는 strict, redor 공식 폐기) · bit-vector(`$countones/$onehot(0)/$isunknown` 4-state, `$bits`=elaborate const-fold 3-레인: array view/ir_bits_of/decl-order prescan) · `$random`=**Annex N 핀**(LCG+float-mantissa, dist_uniform의 end+1 스케일 2^32+floor-캐스트 — 어구 그대로 읽으면 양음 둘 다 ±1 발산, 4-draw 라이브 핀)·`$urandom(_range)`=splitmix64 자체 계약 · `$stime` · plusargs(CLI `+args`→SimOpts, test=prefix probe·value=인터셉트) · 파일 I/O(fd=0x8000_0003…·MCD bit1…·W4022) · `$readmemb/h`(선언-인덱스 도메인 @addr·W4023) | v7 bump #1 소진 | iverilog 차분 전량(+$urandom 자체핀) | 완료 | **시드-부작용 함수 = StmtEffect 인터셉트 패밀리**(seeded $random/$value$plusargs/$fopen — direct-rhs만, 그 외 loud) |
| ~~**P2-C full `string` 타입**~~ ✅ **2026-06-12 완료**(v7 슬라이스 8·10) | `NetKind::String`=힙 핸들(dyn 선례) — read=**is_str packed 구체화**(ctx resize 바이패스, is_real 선례)·write=leading-NUL strip(§6.16) · 메서드 len/getc/substr/toupper/tolower/compare(+putc=SysTask) · **모든 비교 = StrCmp 라우팅**(packed zero-ext는 비사전식·정적 사이징은 절단) · `$sformat(f)`(렌더=커널측 인터셉트) · concat=loud($sformatf 우회) | v7 묶음 #2 + AST flip 1회 | iverilog 부분 차분(decl/len/substr/비교/$sformatf)+hand-IEEE(toupper/getc/putc/compare — iverilog 미지원; string NBA=vvp 내부에러) | 완료 | string-키 foreach 한계 해소는 후속(8byte ref-var 표면 그대로) |
| ~~**P2-D package**~~ ✅ **2026-06-12 완료**(v7 슬라이스 9) | run() 진입시 패키지 일괄 fold($pkg$ 합성 스코프) → import(CU+module)가 const는 (3b) 전·func/task는 (3.5) 후 skip-if-present 바인딩(**로컬 승리** iverilog 핀) · `pkg::sym`=expr/const 양쪽 fold · typedef 타입명=파서 unit-global 맵 편승(문서화) | IR **0** 확정(interface 선례) | iverilog 차분 | 완료 | 패키지 변수/패키지내 import/scoped 함수콜=loud 디퍼 |
| ~~**P2-E 절차 고급**~~ ✅ **2026-06-12 완료**(914 green) | ⭐관문 적발: join_any/join_none은 **이미 전체 동작**(파서+사이드카+배리어 — 차분 핀만 추가) · `disable fork`=자손 transitive kill(activity `dead` 마킹+`run_body` 단일 초크 드롭, DisableKind::Fork 기존 IR=IR-0) · `do-while`=파스 desugar · `unique/priority` if/case=위반(no-match) 표면을 `$warning` else/default arm으로 desugar(iverilog 핀; priority-if 문법은 iverilog 거부→hand-IEEE; 다중-match 검사=문서화 컷) · `final`=ProcKind::Final(.vu 재핀)+final_procs 사이드카(11번째 trailer)+종료 시퀀스(타이밍=loud §9.2.3) | AST flip 1회(.vu), IR 0 | iverilog 차분+hand-IEEE 2핀 | 완료 | **✅ `wait fork` 2026-06-14 v8로 완료**(`bb0c5ba` — Activity.wait_fork 누적 직계자식 배리어, disable-fork 훅 불요, iverilog 차분 5; ⭐동봉: edge-sensitive always mid-body 재발화 일반 엔진 버그=Activity.busy 가드). **잔여 디퍼: automatic/recursive frame-call=콜스택 모델 필요(v1 인라인 한계)=E3009 유지** |
| ~~**P2-F concurrent SVA 서브셋**~~ ✅ **2026-06-14 완료(Phase-3 진입, 933 green)** | 단일 클럭 `assert property(@(clk) a \|-> b)`/`\|=>` + `$past/$rose/$fell/$stable` + 무-implication(`property(@(clk) e)`=`1'b1 \|-> e`). **노선 확정대로 전부 desugar(IR-0)**: ConcurrentAssert→합성 clocked always 체커(`materialize_sva_checkers`, named-event/foreach 선례), `\|->`=`if(ante&&!cons)$error`·`\|=>`=1-bit X-init pend reg 1-클럭 지연·$error=immediate-assert severity 재사용; sampled fn→prev-reg(signal당 공유·NBA `prev<=sig`). **⭐iverilog 13.0이 concurrent assert AND $past류 둘 다 거부→전면 hand-IEEE 핀**(S1 `cf8a6f1`/S2 `b09e7b7`/S3 `34354ac`). 적대 리뷰 3렌즈: F1(`\|=>` 다중비트 절단→reduction-OR)·F3(hierarchical aliasing→E3009) 수정, F2(lenient-X) 문서화, determinism CLEAN | AST flip(v8 일괄)·IR 0(순수 합성) | hand-IEEE(iverilog 미지원) | 완료 | **잔여(full SVA, Phase-3 후속): ✅ 슬라이스 S4(2026-06-15 `c4efbd5`)=상수 `##n`+`[*n]` antecedent(시프트레지스터 파이프라인 desugar, IR-0, fmt_ver 8 유지) — 잔여=범위 `##[m:n]`/`[*m:n]`·unbounded `[*0:$]`/`[->n]`/`[=n]`=관찰 오토마타 트랙(大)·throughout/within·sequence consequent·multi-clock·disable iff·action block(else $fatal)·module-level assert property 문법** |
| 조건부① PDES BSP v1 | 재진입 조건(지속 W≥64 + grain≥200ns 실워크로드) 충족 시 — doc-18 §PDES 스케치 + T1식 byte-diff 게이트 | SimOpts out-of-band | byte-diff 게이트 | 大 | 트리거 대기 |
| 조건부② cycle-based 컴파일드 모드 | Verilator-lane(2-state·정적 스케줄) 옵트인 — doc-18 §2b | 별도 백엔드 | 자체 차분 | 大 | 사실상 별제품 — 수요 확인 후 |
| 조건부③ native-eval 잔여 lane | signed>64 arith·>128bit·sysfunc lane | 0 (VM 전용) | P5 게이트 | 小~中 | 저ROI 박제 — 워크로드 증거 시 |
| 장기④ VHDL front-end | parse까지 언어의존 구조라 시임 준비됨 — lexer/parser/AST→elaborate 신규 | sim-ir 무변경이 설계 목표 | GHDL 차분 | 大大 | Phase-4+/별도 결정 |

### 4.2 MVP 컷 인벤토리 → 해제 매핑 (현재 전부 loud-reject 또는 문서화된 degrade)

| 컷 (현재 동작) | 해제 트랙 |
|---|---|
| `class`/OOP · `program` · `union` (parse/elab loud) | Phase-3+ (P2-F 이후 — 검증 생태계 일괄) |
| ~~full `string` 타입~~ ✅ v7(잔여 컷: concat=loud→$sformatf 우회·decl init·port·string-키 foreach ref-var·atoi/itoa류 메서드=loud) · wildcard assoc `[*]`(loud) | ~~P2-C~~ 잔여 컷만 후속 |
| ~~파일 I/O · `$readmem*` · random · plusargs · `$stime`~~ ✅ v7 | math transcendentals만 잔존(libm 3-OS 리스크 — 순수-Rust libm 핀 결정 대기) |
| `final` · fork 고급 · automatic/recursive frame-call (E3009) | P2-E |
| `assert property`/`#0`/`final` assertion · clocking block · repeat-event intra-assign 고급 (loud) | P2-F |
| ~~instance array · 다차원 슬라이스/whole-array 대입 · per-dim bounds · `$dump*` 배열 · casez/casex 정밀 · `assign #d` inertial · wide 산술~~ ✅ Phase-1.x 정밀화 소묶음 전량(2026-06-12) + casez/casex는 v7 슬라이스 2 | 완료 — 잔여는 doc-01 표 정본 |
| `defparam` (E3009) | **해제 안 함 권장** — IEEE deprecated, `#(.param())` override로 충분(정책 박제) |
| hierarchical 이름/함수/태스크 참조 (E3009) | P2 소항목(읽기 한정 검토) 또는 유지 |
| `` `default_nettype`` (implicit-net=E3010 정책) | 유지(명시적 에러가 정책) — worklib 후 옵션 재평가 |

### 4.3 권장 진입 순서 (제안 → 진행 중)

1. ~~**P2-A worklib**~~ ✅ 2026-06-12 완료(§4.1 행 참조).
2. ~~**v7 bump 묶음**~~ ✅ **2026-06-12 전량 완료(10 슬라이스, 851→903 green)** = 형상 bump(fmt_ver 7, 기능 0) → casez/casex → bit-vector+$bits → random/$stime → plusargs → 파일 I/O → readmem → AST flip(.vu 재핀 1회) → P2-D package → P2-C string. math transcendentals만 잔존 디퍼(libm 3-OS 리스크 — 순수-Rust libm 핀 결정 대기).
   **관문 평가(2026-06-12) 결과:**
   - **IR-0 선행분**(bump 불요 — 즉시 진행): ~~①instance array 언롤~~ ✅ 2026-06-12(`00ae25e` — iverilog 핀: 선언순 첫 인덱스=MSB 청크·W=P 공유/N·P 슬라이스·`[-1:0]`은 합법 2-원소 발견) → ~~②다차원 부분 슬라이스/whole-array 대입~~ ✅ 2026-06-12(IEEE §7.6 위치 대응 element-wise desugar; **iverilog가 기능 미지원→hand-IEEE 핀 레인**; 대입 외 whole-array=silent word-0→loud 승격, `$dump*` 인자만 현상 유지; 잔여 컷은 doc-01 표 정본) → ~~③per-dim bounds~~ ✅ 2026-06-12(d≥2 인덱스마다 `lo≤idx≤hi` 가드 IR 합성, 1-D byte-불변; **⚠️ iverilog도 inner-dim alias라 hand-IEEE §7.4.6 핀**; unpacked=X+E4002·packed=silent-X 벡터 계약 일치) → ~~④`assign #d` inertial~~ ✅ 2026-06-12(세대 카운터로 pending 무효화 — 좁은 펄스 필터·경계 펄스 생존, iverilog 차분 5핀; 엔진-로컬, IR 0) → ~~⑤`$dump*` 배열 per-element/depth~~ ✅ 2026-06-12(원소당 `$var`+dims 10번째 trailer 사이드카·depth/scope/net 인자 선별(level=iverilog 핀, 배열 인자=iverilog가 에러라 hand-확장)·W4021 신설(53 codes)) → ~~⑥>64 signed/>128 unsigned multi-word 산술~~ ✅ 2026-06-12(`arith_wide`+mw 커널(add/sub/mul/divmod/pow)+`%d` 임의 폭 십진 — 전부 iverilog 차분, VM=커널 공유 parity). **정밀화 소묶음 ①~⑥ 전량 소진 — 다음 = v7 bump 일괄.**
   - **bump 합류 확정분**: casez/casex 정밀 분리는 **IR-0 불가 판정** — scrutinee 측 z 식별에 per-bit `===`가 필요해 `BinOp::CasezEq/CasexEq` 신설(현 `redor(xor)!==1`은 casex엔 정확, casez엔 over-lenient). + SysFunc/SysTask 다수(파일 I/O·readmem·**random=IEEE Annex 알고리즘 핀**(iverilog 차분 가능; `$urandom`은 구현정의→hand-pin)·bit-vector·plusargs·`$stime`·`$sformat(f)`) + `NetKind::String` + AST flip 1회(string 타입+package+`pkg::` scope expr).
   - **측정-디퍼**: math transcendentals(`$ln`/`$sin`…)는 **3-OS libm 발산 리스크** — 순수-Rust `libm` 핀 도입 결정 전까지 loud 유지.
3. ~~**P2-E 절차 고급**~~ ✅ 2026-06-12 완료(§4.1 행 — wait fork=v8 합류·automatic/recursive=콜스택 디퍼).
4. ~~**P2-F SVA 관문 평가**~~ ✅ 2026-06-12 — **조건부 GO 박제**(§4.1 행: desugar 서브셋 노선 확정, 구현은 Phase-3 진입 결정 시).
5. ~~**v8 bump 묶음 + Phase-3 진입(wait fork + SVA 서브셋)**~~ ✅ **2026-06-14 완료(933 green, 5커밋, 3-OS CI green)** — ②v8 bump(`WaitCause::Fork`+AST flip, format_version 8, inert) → ①wait fork(IEEE §9.6.1, +edge-sensitive-always 재발화 일반 엔진 버그 수정) → ①SVA 서브셋(S1 파서·S2 체커 desugar·S3 sampled fn, **전면 hand-IEEE**=iverilog 미지원, 적대 리뷰 F1/F3 수정·F2 문서화). §4.1 P2-E/P2-F 행 참조. **→ §4.3 권장 진입 순서 + Phase-3 진입 슬라이스 전 항목 소진.**
6. **full SVA 시퀀스 (사용자 스코프=오토마타 트랙까지, 多슬라이스 진행 중)**:
   - ~~**S4 상수 `##n`+`[*n]`**~~ ✅ 2026-06-15(945 green, `c4efbd5`) — `expand_sequence`→`synth_seq_pipeline` 시프트레지스터, fmt_ver 8 유지·`.vu` 재핀. 적대 4렌즈 CLEAN, MEDIUM 1건(`[*` 토큰 wildcard 진단 degrade) 수정.
   - ~~**S5 유계 범위 `##[m:n]`/`[*m:n]`**~~ ✅ 2026-06-15(950 green, `d1c8120`) — disjunction(병렬 파이프라인 OR-reduce), AST/IR 무변경(min/max 재사용), flat byte-identical, `SVA_SEQ_ALT_CAP=256`. 적대 3렌즈 CLEAN(terminal repeat 상한=run≥m·mid-seq 윈도 독립).
   - ~~**S6 unbounded delay `##[m:$]`**~~ ✅ 2026-06-15(955 green, `85f7f10`) — `SeqHop::{Fixed,AtLeast}` + never-reset armed latch(`armed<=armed|cur`), `seq_delay_reg` 헬퍼로 Fixed byte-identical. 적대 3렌즈 CLEAN(16/16 latch·X-propagation safe·`|=>` 연동).
   - ~~**S7 `throughout`**~~ ✅ 2026-06-15(958 green, `c609b86`) — `Sequence::Throughout` variant(AST flip, sim-ir 골든 무변경), `expand_sequence`가 `SeqAlt=(terms,Option<guard>)` 반환, guard=`|cond`를 seed+모든 shift stage에 AND(`guard_and`). bounded inner만(unbounded→loud E3009), flat byte-identical(guard=None=identity). contextual keyword(`wire throughout;` 안전). 적대 2렌즈 CLEAN(start/gap/end kill·range per-alt·|=>·multi-bit reduction-OR).
   - ~~**S8 `[->n]` goto + `[=n]` nonconsec**~~ ✅ 2026-06-15(964 green, `eb1499f`) — **existence-latch FSM**(goto: `reg_s` 단계별+b-gated advance·match=`b&avail_{n-1}`; nonconsec: goto+`ext` latch `cur=match_g|(ext&~b)`). ⭐**정정 확정: IR-0 tractable**(`|->`=any-completion만 필요, exact-count 불요; 이전 "single-bit 머지 불가→infeasible"는 오판). 렉서 `[->`/`[=`·AST `RepeatKind` flip(sim-ir 골든 무변경)·single count·boolean operand만. 적대 3렌즈 CLEAN(overlap-divergence·n-th-b boundary·렉서 무충돌).
   - ~~**S9 `within`**~~ ✅ 2026-06-15(967 green, `eb2b4bd`) — `synth_within`이 `match(seq2) & OR_{i=0}^{L-k1} reg^i(match(seq1))`로 desugar(`Sequence::Within` variant·AST flip·sim-ir 골든 무변경). contextual keyword·top-level 한정·bounded boolean operand만. 적대 2렌즈 CLEAN(윈도-엣지 off-by-one 정확·straddle 거부·byte-identity).
   - **🏁 full SVA 시퀀스 서브셋 완성(S4-S9, 2026-06-15)**: `##n`·`##[m:n]`·`##[m:$]`·`[*n]`·`[*m:n]`·`throughout`·`[->n]`·`[=n]`·`within` 전부 순수 IR-0(트랙 전체 sim-ir 무변경=format_version 8 유지, `.vu` AST-hash 재핀만), 슬라이스별 적대 리뷰 통과, 3-OS CI green. ⭐핵심 교훈: `|->`=any-completion 의미론이라 exact-count 불요→**existence-latch FSM**(goto/nonconsec)·**OR-window**(within)으로 오토마타까지 전부 합성 RTL로 표현(이전 "오토마타=infeasible/새 IR 필요" 우려 반증).
   - **잔여(Phase-3 후속, 별도 결정)**: `[*m:$]` unbounded repeat(mid, gated run-latch)·sequence consequent·multi-clock·disable iff·action block·module-level assert property 문법.
- **그 외 결정 후보**(스코프 결정 영역): class/OOP·`program`·union(검증 생태계) · 커버리지 · automatic/recursive 콜스택 모델 · math transcendentals(순수-Rust libm 핀).
- 조건부/장기 트랙(PDES·cycle-based·native lane·VHDL)은 각자의 트리거(워크로드 증거/수요) 충족 시에만.
