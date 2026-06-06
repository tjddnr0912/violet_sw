# ROADMAP — Stage C 이후 향후 과제 (vitamin)

> **갱신:** 2026-06-07 (C7 timescale 버그 수정 + 문서부채 정리 반영). 현 단계 = **Stage C 컴파일드 백엔드 C1·C2 완료**(VM MVP, byte-identical) +
> **profile-driven 최적화 4라운드로 누적 ~6x**(eval-heavy 2781→461ms). 이 문서는 *여기서부터 무엇을 할지*를
> 트랙별로 정리한 단일 진실. perf 이력 상세는 [`REMAINING_WORK.md`](REMAINING_WORK.md) Stage C 섹션 +
> [`preview/18-acceleration-analysis.md`](preview/18-acceleration-analysis.md) §실측, 설계는
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
| **native-eval (eval 코드젠)** | `eval.rs` `eval_ctx` → 레지스터 VM 확장 | **식-바운드 高 / 그 외 低** | 식-바운드 RTL ~2-3x(아래 §C). 고위험·다세션, P5 게이트가 정확성 상쇄. *(1차 "비추"는 eval-light 벤치 산물 — 정정됨)* |

**판단:** value-처리 bit-serial 스레드는 ~6x에서 마무리. 추가 perf의 두 축 = **스케줄러 축**(클럭-바운드) + **native-eval**(식-바운드). 둘은 상보적(다른 워크로드).

### B. Correctness 후속 (perf와 독립)

- **C7 — ✅ 검증+수정 완료 (2026-06-07, `fbb869c`).** `flush_postponed`가 `$strobe`/`$monitor`를 **마지막 실행 프로세스의 timescale multiplier**로 렌더하던 실버그 확인됨(혼합 timescale: 1ns 서브모듈의 `$strobe`가 같은 tick에 나중 실행된 1ps 형제의 `M`으로 `$time` 렌더). 수정: 등록 시점 `cur_time_mult`를 `FmtCapture.time_mult`에 스냅샷 → flush에서 per-capture로 렌더, 진입값 복원. 회귀 `cli/tests/timescale_postponed.rs`. *(주의: 단일 top만 실험으로 안 됨 — 아래 멀티-top 항목 참조. 반드시 top이 서로 다른 timescale의 서브모듈을 instantiate해야 재현.)*
- **문서부채 — ✅ 정리 완료 (2026-06-07).** doc-01 freeze 표 `enum`/`typedef`/packed `struct`를 IN-MVP로 정정(`union`/`string`/동적배열은 deferred 유지) · `$stime` **미구현**(`VITA-E3009`)을 hdl-ref/06/08에 명기 · `%t` plain-decimal(=`%0d`, `$timeformat`·필드폭 미적용) caveat 추가.
- **🆕 멀티-top-module: 마지막 선언 top만 elaborate (2026-06-07 발견).** 인스턴스화되지 않은 bare top 모듈이 여럿이면 **마지막 선언된 것의 계층만** 시뮬되고 나머지는 조용히 누락(immediate `$display`조차 안 나옴). IEEE는 미인스턴스 모듈 전부를 root로 elaborate(iverilog 동일). 단일-top MVP 가정의 산물로 보이며, 다중 root 지원은 elaborate 진입(`elaborate_with_timescale`)에서 top 집합 선택·각각 lowering이 필요한 중간 규모 작업. **현 회피책: 명시적 top이 서브모듈을 instantiate.** 우선순위 중(유용성·correctness 경계).

### C. 컴파일드 백엔드 전략 — ✅ 결정됨 (2026-06-07, §0 2차 재평가 기반)

1차 질문은 "eval=~4%면 VM 계속 갈 가치 있나?"였고 답은 "동결"이었다. **연산자수 스윕이 그 전제를
뒤집었다**(eval = 식 복잡도에 선형, 식-바운드 70-82%). **결정: native-eval(plan C4~C9)을 식-바운드 perf의
정당한 방향으로 채택** — "동결" 폐기. 단 *지금 당장 착수가 아니라*, perf가 우선순위가 될 때(또는 식-바운드
실사용 설계가 등장할 때) 진행. 근거·리스크:

- **왜 채택:** 식-바운드 RTL(ALU·crypto·깊은 조합)에서 native-eval 설계당 ~2-3x. 현 VM(문장 컴파일)은
  이 영역에 무력(`EXPR_HEAVY` 0.92x). 스케줄러 축(§A)과 상보 — 클럭-바운드는 스케줄러, 식-바운드는 native-eval.
- **왜 안전:** P5 차분 게이트(compiled==interp byte동일) + iverilog 오라클이 4-state 정확성 리스크를 강제.
  새 백엔드가 한 비트라도 틀리면 게이트가 즉시 red — native-eval을 "정확성 by-construction"으로 시도 가능.
- **비용/순서:** 4-state 레지스터 머신(val+unk 평면·width/sign 마스킹·X/Z 전파·>128bit heap fallback·
  signed/real)은 다세션 고위험. plan C4~C9가 이 단계를 정의. 선행 인프라(C9: content-addressed codegen 캐시·
  `kernel_abi_version` 헤더·ExprId→SourceLoc 사이드카)는 native-eval 본체보다 먼저/병행 가능.

### D. 언어/기능 커버리지 (perf 아님 — "유용성" 트랙)

vitamin은 **서브셋** 시뮬레이터. 실사용 가치는 "더 빠르게"보다 **"더 많은 RTL 지원"**일 수 있다. 의도적 deferral 목록(전부 loud-reject 확인됨):

- 프랙셔널 `#2.5`/`$realtime` 정밀(timescale precision ratio 일부)
- dynamic/associative array, queue (정적 평탄화 불가 → 새 IR 노드 필요)
- `disable` 실동작(현재 no-op), `for (int i = ...)` SV inline-decl
- 추가 SV 구문 (interface, package, assertion 등 — Phase-2+)

---

## 2. 추천 우선순위 (다음 세션)

- ~~C7 `cur_time_mult`-during-postponed 버그 검증~~ — ✅ 완료 (`fbb869c`).
- ~~문서부채 정리~~ — ✅ 완료 (doc-01/05/06/08/display-io).
- ~~컴파일드 백엔드 전략 결정 (§C)~~ — ✅ 결정됨: **native-eval 채택**(식-바운드 perf), "동결" 폐기. 착수는 perf 우선화 시점.

1. **멀티-top-module 다중 root elaborate (§B 🆕)** — correctness+유용성. 현 단일-top 가정이 IEEE 표준과 어긋남. 중간 규모.
2. **perf 트랙 (워크로드로 분기, §A/§C):**
   - 식-바운드(ALU·crypto·깊은 조합) 목표면 → **native-eval (plan C4~C9)** — P5 게이트가 정확성 강제. 다세션·고위험.
   - 클럭-바운드 목표면 → **스케줄러 축** (`sched.rs` event wheel·`propagate_changes`·NBA).
3. **언어 커버리지 (§D)** — 시뮬레이터 유용성 확장 (perf 아님).

---

## 3. 교훈 (방법론 — 재사용 가치)

- **병목은 양파다.** doc-18의 두 예측(Value-alloc·tree-walk)이 첫 측정엔 둘 다 "아님"이었지만, 실은 bit-serial 처리가 alloc을 가리고 있었을 뿐. 표면층 제거 → 재측정 → 다음 층. **최적화는 한 번 측정으로 끝나지 않는다.**
- **"실패한" 실험도 선행 최적화 후 재시도 가치.** inline-Value가 1차엔 ~0(net-write per-bit 루프가 alloc 가리고 Deref 오버헤드 상쇄) → 그 루프 word化 후 3차엔 1.55x.
- **사이클 = profile → 최소 fix → re-profile 반복.** 각 fix는 항상 bit-exact(suite + iverilog 차분이 스펙). `cargo test -p sim-engine --test perf_baseline -- --ignored --nocapture`로 before/after 측정, `/usr/bin/sample`(macOS, sudo 불요)로 self-time 히스토그램.
- **공유 경로 최적화가 backend-전용보다 유리했다** — interp·VM 둘 다 빨라지고 위험도 낮음.
