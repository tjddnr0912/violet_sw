# ROADMAP — Stage C 이후 향후 과제 (vitamin)

> **갱신:** 2026-06-07. 현 단계 = **Stage C 컴파일드 백엔드 C1·C2 완료**(VM MVP, byte-identical) +
> **profile-driven 최적화 4라운드로 누적 ~6x**(eval-heavy 2781→461ms). 이 문서는 *여기서부터 무엇을 할지*를
> 트랙별로 정리한 단일 진실. perf 이력 상세는 [`REMAINING_WORK.md`](REMAINING_WORK.md) Stage C 섹션 +
> [`preview/18-acceleration-analysis.md`](preview/18-acceleration-analysis.md) §실측, 설계는
> [`superpowers/plans/2026-06-06-bytecode-vm-stage-c.md`](superpowers/plans/2026-06-06-bytecode-vm-stage-c.md).

---

## 0. 핵심 발견 — 왜 로드맵이 바뀌었나 (반드시 먼저 읽을 것)

Stage C는 본래 *"컴파일드 백엔드(바이트코드 VM)로 인터프리터를 이긴다"* — eval 트리워크 디스패치와
`Value` 힙할당(doc-18이 지목한 두 병목)을 native-eval(plan C3~C6)로 제거 — 였다. **프로파일링(`/usr/bin/sample`)이
이 전제를 측정으로 뒤집었다:**

- **진짜 병목 = bit-serial bit-by-bit 처리**(net read/write, shift, resize) — 인터프리터·VM **공유** 경로.
- **eval 트리워크 디스패치(`eval_ctx`)는 ~2-4%뿐.** native-eval이 노리는 바로 그 부분이 작다.
- **`Value` 힙할당**은 *2차* 비용이었고, bit-serial 처리가 그것을 가리고 있었다(표면층 제거 후에야 드러남).

→ 결과: **~6x 가속은 전부 공유 경로 word化/inline 최적화**에서 나왔고, **native-eval은 측정으로 저ROI(고위험·수개월·~4% 추격) 확인 → 내려놓음.** VM은 그 위에서 0.84x(eval-heavy)로 약간 더 빠르다 — VM의 perf 가치는 약하다(eval가 작으니). **VM은 "정확한 레퍼런스 + 구조적 마일스톤"으로서 의미가 크다.**

> ⚠️ **미래 세션 경고:** native-eval(plan C3~C6의 핵심)을 perf 목적으로 다시 집어들지 말 것 — 측정으로 막다른 길 확인됨. inline-Value도 "한 번 ~0였다 3차에 1.55x"처럼 *선행 최적화 후* 재측정이 핵심(아래 §교훈).

---

## 1. 트랙별 향후 과제

### A. Perf — 남은 것 (싼 윈 거의 소진)

| 항목 | 위치 | ROI | 비고 |
|---|---|---|---|
| 저빈도 value-op word化 | `eval.rs` `eval_select`/`eval_concat`/`eval_replicate`/`merge_x` (아직 bit-serial) | 낮음 | arith 벤치 영향 0, bit-select/concat 많은 설계에만. 저위험·proven 패턴 |
| `has_xz`/`arith`/`to_u128` 미세 | `value.rs`/`eval.rs` | 낮음 | poison 체크 early-out·64bit fast-path 등. 소소 |
| **스케줄러 축 (별개 도메인)** | `sched.rs` event wheel(BTreeMap)·`propagate_changes`·NBA | **중간** | 클럭구동(codegen-heavy)은 3.2x로 eval-heavy(6x)보다 덜 빨라짐 — 다음 프론티어는 **이벤트 스케줄링**(value 처리와 다른 영역). 클럭 많은 설계에 유효 |
| eval 트리워크 디스패치 | `eval.rs` `eval_ctx` 재귀 | ❌ | = native-eval. ~4% · 고위험 · **비추** |

**판단:** value-처리 perf 스레드는 ~6x에서 사실상 마무리. 추가 perf는 **스케줄러 축**이 가장 유효(다른 도메인).

### B. Correctness 후속 (perf와 독립)

- **C7 nuance 검증 — 우선:** `flush_postponed`가 `$strobe`/`$monitor`를 **마지막 실행 프로세스의 timescale multiplier**로 렌더하는 잠재 버그(plan C7 항목, `sched.rs` postponed). 비단위 timescale + 멀티모듈 `$strobe`에서 실버그인지 확인 필요.
- **문서부채(잔여 in-scope):** doc-01 freeze 표가 `enum`/`typedef`/`packed struct`를 DEFERRED로 표기(실구현됨, 매뉴얼 003 정확) · `%t` 기본필드폭/`$timeformat` 미구현(값은 정확) · hdl-reference/system-tasks `$stime` 표기 오류. 전부 minor·문서.

### C. 컴파일드 백엔드 전략 결정 (오너 판단 필요)

프로파일링이 던진 질문: **VM이 eval로 interp를 크게 못 앞지른다면(eval=~4%), 바이트코드 VM을 계속 갈 가치가 있나?**

- **(a) C2에서 동결 — 권장.** VM=정확한 레퍼런스 + P9 클래스 실행·byte동일·약간 빠름. 추가 노력은 공유 최적화/언어 커버리지/스케줄러로. *(데이터상 합리적)*
- **(b) native-eval 강행 (plan C4~C9).** 고위험·수개월·~4% 추격. **비추.**
- **(c) C9 인프라만.** content-addressed codegen 캐시 · `kernel_abi_version` 헤더(format_version과 독립 4th 게이트) · ExprId→SourceLoc 사이드카(P16 디버깅). VM을 프로덕션화/디버깅 가능하게 할 때만 의미.

### D. 언어/기능 커버리지 (perf 아님 — "유용성" 트랙)

vitamin은 **서브셋** 시뮬레이터. 실사용 가치는 "더 빠르게"보다 **"더 많은 RTL 지원"**일 수 있다. 의도적 deferral 목록(전부 loud-reject 확인됨):

- 프랙셔널 `#2.5`/`$realtime` 정밀(timescale precision ratio 일부)
- dynamic/associative array, queue (정적 평탄화 불가 → 새 IR 노드 필요)
- `disable` 실동작(현재 no-op), `for (int i = ...)` SV inline-decl
- 추가 SV 구문 (interface, package, assertion 등 — Phase-2+)

---

## 2. 추천 우선순위 (다음 세션)

1. **C7 `cur_time_mult`-during-postponed 버그 검증** — 실버그면 correctness 최우선.
2. **전략 결정 (§C)** — 오너가 VM 방향(동결 vs native-eval vs 인프라)을 확정해야 이후가 명확해짐. **권장 = (a) C2 동결.**
3. 그 다음 가치 높은 쪽:
   - **스케줄러 최적화 (§A)** — 클럭구동 설계 perf 다음 프론티어, 또는
   - **언어 커버리지 (§D)** — 시뮬레이터 유용성 확장.

---

## 3. 교훈 (방법론 — 재사용 가치)

- **병목은 양파다.** doc-18의 두 예측(Value-alloc·tree-walk)이 첫 측정엔 둘 다 "아님"이었지만, 실은 bit-serial 처리가 alloc을 가리고 있었을 뿐. 표면층 제거 → 재측정 → 다음 층. **최적화는 한 번 측정으로 끝나지 않는다.**
- **"실패한" 실험도 선행 최적화 후 재시도 가치.** inline-Value가 1차엔 ~0(net-write per-bit 루프가 alloc 가리고 Deref 오버헤드 상쇄) → 그 루프 word化 후 3차엔 1.55x.
- **사이클 = profile → 최소 fix → re-profile 반복.** 각 fix는 항상 bit-exact(suite + iverilog 차분이 스펙). `cargo test -p sim-engine --test perf_baseline -- --ignored --nocapture`로 before/after 측정, `/usr/bin/sample`(macOS, sudo 불요)로 self-time 히스토그램.
- **공유 경로 최적화가 backend-전용보다 유리했다** — interp·VM 둘 다 빨라지고 위험도 낮음.
