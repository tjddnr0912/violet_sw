# 목적 (Goals)
- **G1**: vitamin(vita/vcmp/velab/vrun) 완성 — icarus·verilator·xcelium·vcs급 **정확한** 오픈소스 RTL 시뮬레이터.
- **G2 (2026-07-02 신설)**: **AI-Agent 친화 simulator** — LLM이 재실행·파형 없이 실패 국소화·커버리지 즉답·TB 재빌드 없이 프로그램 제어. SPEC=`docs/preview/19-ai-agent-observability.md`, 트랙=ROADMAP §7(OBS-0~6), 요구 원문=`docs/reviews/2026-07-02-ai-sim-observability.md`.
- **최우선 원칙 = correct-or-loud** (→ §S).

# 매 반복 = 잔여 1개 슬라이스를 끝까지: 선택→그라운딩→구현→적대리뷰→게이트→문서→커밋·푸시→§8 자가개선. 아래 순서 그대로.

## S. silent-wrong 대응 (불변 원칙 — 모든 슬라이스에 적용)
- **정의/서열**: silent-wrong(틀린 출력·무에러)=최악 > honest-loud(명시 거부)=항상 안전. **검증 불가면 구현하지 말 것**(오라클도 전제조건도 없으면 loud 유지).
- **대응 프로토콜(5단계)**: ① 구현 **전** 오라클 라이브 그라운딩(§2 — 예측 금지·측정) ② 구현은 byte-identity 논증 선행(§3 — 비대상 디자인 무영향 증명 못 하면 범위 축소/loud) ③ 구현 **후** 적대 병렬 ≥2 서브에이전트(§4 — differential+soundness) ④ silent 1건이라도 발견 → 즉시 수정 후 리뷰 **재시작**, CLEAN까지 반복 ⑤ deep/broad fix가 위험>가치면 **detection-only honest-loud로 대체**(에러만 추가=구조적으로 신규 silent-wrong 불가; full fix는 follow-on 기록).
- **오라클 없는 영역**(SVA·OOP·CRV·clocking·array-param 등 iverilog 거부분)= hand-IEEE 핀 + **vita-내부 등가 차분**(신규 형태 ≡ 검증된 기존 형태 byte-identical)이 teeth.
- **G2 확장**: 관찰 rail(JSONL/로그)도 동일 원칙 — **틀린 로그=silent-wrong**(LLM 오도). 관찰값은 엔진 단일 소스에서만 파생(이중 계산 금지)·미해석 probe/질의=loud·표준 teeth=3-way 차분(JSONL≡VCD≡`$display`)+결정성 골든(동일 입력→byte-identical).
- soundness(hand-proof)와 differential(라이브 실측)이 충돌하면 **differential이 이긴다**. "iverilog와 같다"/"도달 불가"/수치 예시는 주장이 아니라 측정으로만 인정.

## 0. 컨텍스트 고정값 (재발견 금지)
- 빌드/게이트: `cargo build -p cli --locked`(바이너리 `target/debug/vita`) · `cargo test --workspace --locked` · `cargo clippy --workspace --all-targets --locked -- -D warnings` · `cargo fmt --all -- --check`.
- 오라클: **iverilog 13.0** `/opt/homebrew/bin/iverilog`(compile `iverilog -g2012 -o x.vvp f.v`, run `vvp x.vvp`). iverilog가 거부하는 영역(SVA·clocking·assoc·param-class·vif·array-param)=내부 차분. macOS에 `timeout` 없음 → SV 안에 `#N $finish` 워치독.
- 불변식: **format_version 19**(루트 SchemaHash=sim-ir SimIr). frozen sim-ir 형상 변경만 bump(드묾·골든 재생성 동반), 그 외 전부 **IR-0**(엔진/elaborate-local·사이드카). **3-OS byte-identical**이 perf보다 우선. AST(hdl-ast) 필드 추가=`.vu` 스키마 해시만 re-pin(`hdl-ast/tests/schema_hash.rs`)·format 불변. AST 노드 VALUE만 변경(형상 불변)=둘 다 불변·IR-0.
- 정본 문서: SPEC=`docs/preview/`(G2=19) · 전략/잔여=`docs/ROADMAP.md`(§2 착수순서·§4.5.x 슬라이스 로그·§6 외부리포트·§7 OBS) · 상위 스냅샷=`docs/REMAINING_WORK.md` · 이력=`docs/DEVLOG.md`.

## 1. 아이템 선택
- **NEXT 큐(아래) 최상단부터.** 선택 전 후보를 오라클로 재현(이전 슬라이스가 부수 수정했거나 misdiagnosed일 수 있음 — 재현 안 되면 비목표 기록 후 다음). recorded 후보는 mechanism-level 재그라운딩(기록된 증상이 실제보다 좁을 수 있음 — 변수 공간 sweep으로 정확한 룰 핀).
- 우선순위 룰: **① 오라클 있는 CRITICAL silent-wrong > ② 오라클 있는 loud→supported(additive=저위험) > ③ 전제조건 충족된 honest-loud 승격 > ④ G2 OBS 슬라이스**. ②는 elaborate 허용집합=엔진 처리집합 EXACT 일치 필수(불일치=silent).
- 후보 탐색은 time-box(3~4 probe). probing이 deep/high-stakes 드러내면 즉시 기록·defer 후 pivot(**defer ≠ fix가 크다** — root-cause 추적 후에만 크기 추정). 연속 2회 defer=다음 반복은 deferred 1개에 전념(=정확한 그라운딩+SAFE 해소, deep fix rush 아님). 코어 견고+잔여 전부 moderate면 그라운딩-기록 iteration도 valid.
- '거부된다'고 새 인프라로 잡기 전에 **기존 부분지원 grep**(갭은 feature 전체가 아니라 sub-form 1개인 경우 흔함). '지원되는 듯한'(무에러) system task도 empty/blank 출력을 적극 의심(미매핑 $task=W3056 silent-skip). documented caveat도 ① 후보.
- **additive 파서처럼 보여도 STORAGE/eval-모델 갭일 수 있음** — 값이 어디 저장·어떻게 해소되는지 먼저 grep(single-scalar 모델에 aggregate 욱여넣기=deep, 전용 멀티파트 슬라이스).
- 선택 즉시 격리 브랜치 `git checkout -b feat-<slug>`(**첫 EDIT 전**=절차 1순위, main 직접 구현 금지·`git rev-parse --abbrev-ref HEAD` 확인).

### NEXT 큐 (2026-07-02 갱신 — A2a ✅ 완료(§4.5.69), 잔여 체인 계속)
1. **A2b-prereq — package-level 변수/집합-상수 저장** (현재 E3009 "(v7)"): 단일 인스턴스 lowering(예약 scope NetVar=format 불변)·t0-이전 init·`pkg::x`+import 해소·VCD 제외 v1·MVP-CUT package-var 동시 해제. **iverilog가 package var 지원(2026-07-02 그라운딩)=라이브 차분 오라클** → ② 이상형.
2. **A2b — package array parameter** = A2a(✅) 메커니즘+prereq 결합. acceptance=sha3_pkg `RC_TABLE[0:23]` → **ROADMAP §6 리포트 CLOSE**.
3. **generate/interface 스코프 배열 `'{…}` decl-init 영구 silent-drop 수정**(§4.5.69 ㉮, **①급 — iverilog 40 vs vita 0 라이브 차분**): §6.8 수집 pass가 module body만 walk. 수집을 scope-qualified로 확장(pending lvalue가 bare-name이라 prefix 문제 주의)+완료 시 A2a scope-gate 2곳(generate 16735·interface 5102 부근) 해제. var에도 적용되는 진짜 silent-wrong.
4. **OBS-1 — G2 MVP**: `--obs-dir` → run.json+results.jsonl+coverage.json(기존 카운터 직렬화). teeth=결정성 골든(2-run byte-diff)+3-way 대조. SPEC=doc-19 §4.
5. **OBS-2**: `--probe`→trace.jsonl(transition-only·미해석=loud)+sva.jsonl. 이후 OBS-3~6은 ROADMAP §7 순.
6. **소형 정확성 슬라이스(사이 슬롯)**: scalar `int unsigned` param 부호 silent-wrong(§4.5.69 ㉲, iverilog ✓) · 계단식 CA 체인 t0 전파 그라운딩(vita eager vs Icarus z) · 계층 함수호출 `u1.f(x)` · compound-const `==?` fold · `%-` 좌측정렬 family · `$fflush` accept · loud-message 품질(`[bit]` 캐스케이드·typedef-키·typedef-요소 param) · hier-write sentinel cont_assigns/out_binds 미패치 panic→진단화(㉱).
7. **deep 잔여(저우선)**: 크로스모듈 t0 decl-init race(㉯, iverilog ✓·ProcId 순서=golden 리스크 M~L) · SYS-READ hier-element dest 실지원(㉰, iverilog ✓·현 honest-loud) · repl-count 변수/param-element→0(㉳, §4.5.26) · inline body NON-fill context-width(§4.5.42)·STDIN read·runtime `==?`·string queue·block-local queue decl·modport 방향 강제·force part-select.

## 2. 사전 리뷰 = 오라클 그라운딩
- 최소 SV repro 여러 개를 iverilog와 vita 양쪽에 돌려 **정확한 IEEE 규칙을 핀**. 엣지(x/z·멀티비트·NBA·경계·0/min/max) 변형 probe.
- murky하면 stimulus 경로를 바꿔 재그라운딩(whole-assign vs part-select·리터럴 vs 변수 — murkiness가 probe artifact일 수 있음). multi-construct repro는 축별 **BISECT**(한 축씩 변화)로 정확한 failing 조합 핀. **probe 전 baseline(built-in 등가)이 PASS함을 먼저 확인**(baseline도 실패하면 잘못된 갭을 probe 중).
- 관련 코드(파이프라인 해당 단계) 정독 → **byte-identity 논증**을 먼저 세움. 못 세우면 범위 축소 또는 honest-loud.
- desugar 슬라이스는 desugar가 생성할 EXPRESSION 자체를 sim에서 사전 검증(building block이 돌아도 의미가 틀릴 수 있음). context-determined 기능(의미가 타깃 타입 의존)은 ALL 변종을 구현 전 전수 핀. 큰 의미공간=전용 슬라이스 분리(rush 금지=불완전 슬라이스보다 깨끗한 defer).
- 계획을 scratchpad에 durable 기록(파일·메커니즘·테스트 매트릭스·loud 유지선).

## 3. 구현
- 가능한 IR-0. 공통경로 funnel(인터프리터+VM 청크포인트 단일 여부) 먼저 확인. 비대상 디자인 byte-identical(가드/사이드카=값 다를 때만).
- **최저위험 순서**: 순수 파서 desugar(기존 AST 재사용) > 기존 메커니즘 라우팅(disable→Goto·$swrite→$sformat처럼 grep로 등가 기구 먼저) > 단일-속성 primitive **COMPOSE**(예: typedef cast=`Signing(Size(e))`, 신규 결합 primitive는 골든 영향) > 신규 인프라.
- **ALL-sites 전수(최다 재발 패턴)**: 공유 함수/desugar가 도는 **모든** 스코프·caller·parser 변종(`grep 'fn parse_'`)·assign-site(≥7: `=`,`<=`,decl-init,assign,proc-assign,force,for)·net 생성 경로(`grep add_net`)·statement-dispatch 진입점을 전수 열거. **eligibility-set ≡ process-set**(허용집합=처리집합, 차집합=silent-drop). 미검증 스코프는 `allow_*` scope-gate로 loud 격리. dispatch-chain hook은 최상단(detection-FIRST)에.
- **쓰기-거부(deny) 훅 신설 체크리스트**: ① lvalue 퍼널(collect_lval_chunks) 훅만으론 부족 — 문서화된 우회 `grep 'bypassing collect_lval_chunks'`(array_assign_special) ② **deferred hier 2-pass**(sentinel이라 퍼널이 실net 못 봄 → resolve 패스에도 훅) ③ SYS-READ dest placeholder(`Signal{POISON_NET}`+pending 레코드 eid로 판별) ④ 엔진-사이드 사이드카 쓰기(clocking_outputs·assoc iter key=bare Signal) ⑤ 합성 §6.8 pre-sweep initial은 **면제 플래그**(자기 decl-init도 일반 stmt lowering 경유=면제 없으면 자기 초기화를 거부) ⑥ 포트-이름 충돌(dir≠Internal)·다중 스코프(generate/interface=decl-init 미수집→scope-gate).
- 확장은 discriminator-BRANCH(기존 경로 verbatim 보존·재구성 금지)·신규 eligibility set은 기존과 disjoint 증명. 1-D→N-D 확장 전 기존 offset/stride 테이블이 이미 N-D 처리하는지 확인(DIRECTION은 정확히 1곳만 적용=double-flip 방지). control-flow(break/continue) 타깃은 오라클로 핀(nested=innermost).
- **width/type 축**: self-width table(`width.rs`)과 eval 양쪽 일치 확인. target-width 컨텍스트의 fill(`'1/'x/'z`)은 `lower_ctx_or_plain(e,width)`(bare `lower_expr`=1-bit zero-extend silent-wrong; **bare fill probe 필수**, sized론 안 잡힘). typed→untyped desugar는 per-element 2-state coercion/sign 명시 복원. 4-state raw byte 추출은 `val & !unk`. resize는 RHS 부호로 extend·TARGET 부호로 stamp.
- **name/scope 축**: comma-list sticky 속성(dir·type·sign·range) 전부 스레드. flat map에 nested scope 도입=lazy snapshot/restore(**TYPE+VAR keyed 맵 모두**·ALL decl-region: block_body+tf_body). alias/copy 등록=그 이름 keyed ALL 사이드맵 전수+**set-or-CLEAR**(stale 잔존 방지). collect→match-apply는 consumption-tracking(leftover=loud/warn, 레벨은 오라클에 맞춤). 합성 name-ref는 referent KIND 명시 검증(일반 해소는 too-permissive). synthetic name은 duplicate collision 검사. name-scanning guard는 traversal이 ALL expr variant 커버하는지(`Cast` 등 `_=>false` 누락=우회).
- **인프라 선례**: 신규 runtime statement task=SysTaskId(bump) 대신 no-op Display+StmtId 사이드테이블(단, 선행 StmtId 인터셉터·`cur_defer` 훅 전수 확인). side-effect sysfunc의 expression 지원=statement-form desugar(synthetic temp·single-eval). 엔진-facing 사이드카는 `StagedExtraSidecars` trailer에 append-only(**staged velab→vrun 패리티 필수** — "한계로 문서화" 금지=경로별 불일치는 silent-wrong). 렉서 토큰 추가=prefix 공유 ALL 기존 토큰과 longest-match 대조.

## 4. 사후 리뷰 = 적대 서브에이전트 (절대 생략 금지)
- **병렬 ≥2, 렌즈 분리**: (a) **differential** = 오라클로 수십 케이스 라이브 차분(경계값 0/min/max/width 전수·byte-identity 위반·신규 divergence) (b) **soundness** = code-path 완전성(ALL-sites enumeration·staleness·reset·통합지점 force/clocking/NBA). 4축(Architecture·Perf·Maintainability·Robustness) 포함. **둘은 COMPLEMENTARY — SOUND 판정≠correct(오라클 질문은 hand-proof 불가), differential CLEAN도 soundness가 code-path에서 잡음.** 두 reviewer가 SAME finding으로 CONVERGE=고신뢰 critical.
- soundness에게 **명시 의뢰**할 것: ALL-sites/variant 열거·disjoint 증명·index/offset은 enumeration-order 구조 증명·duplicate-name collision·guard traversal 완전성·'제외 정당' 주장의 반례. soundness의 이론 제기·'도달 불가' 논거·수치/트리거 예시는 **전부 측정으로 검증 후 채택**(리포트 기대문자열 복사 금지=실측 후 핀).
- 발견 분류: (a) 신규 silent-wrong=**즉시 수정** (b) pre-existing 무관=별개 슬라이스 후보로 ROADMAP 기록(동일 검증된 메커니즘으로 1-line에 닫히면 같은 슬라이스 fold 가능) (c) out-of-scope=문서화. DIFF는 '동등 기존 구문'으로 (a/b) 판별하되 **SEMANTIC 등가**(desugar SOURCE)로 차분(STRUCTURAL 등가는 버그 은폐). probe의 DIFFER는 4-way 분류 후에만 착수: 진짜 갭 / no-oracle(iverilog도 거부=skip) / vita-ahead(유지) / harness-formatting(norm() 필터로 finish/sorry 라인 strip 후 재비교). iverilog가 자기 자신과 INCONSISTENT면 vita의 spec-correct가 타깃.
- 신규 경로가 기존 헬퍼 호출하면 헬퍼 잠복 버그 감사(unchecked 산술→`checked_*`·unk 무시·copy된 함수는 원본 버그 상속→공유 헬퍼로 리팩터). write-access 서브에이전트(debug-master)의 직접 수정은 `git diff` 전수 확인+오라클 재검증.
- **silent 1건이라도 → 수정 후 리뷰 재시작, CLEAN까지 반복**(fix가 유발한 2차 회귀를 2nd round가 잡은 실증 다수). detection-only 패스는 false-positive(valid 오거부)에 정조준(false-negative=pre-existing 유지=무회귀).

## 5. 게이트
- `cargo test --workspace --locked` 0 fail·카운트 증가(신규 회귀 테스트=오라클 핀, 없으면 내부 차분 핀). **fmt/clippy는 test와 별개 게이트** — 커밋 전 둘 다(doc comment는 prose로=`doc_lazy_continuation` 회피·신규 테스트 파일은 `cargo fmt --all` 선적용). format_version 의도대로 불변.
- **최강 회귀 테스트 = vita-내부 등가 차분**(신규 형태 ≡ 등가 기존 형태 byte-identical stdout, **미지원 케이스는 둘 다 동일 loud**까지 assert=신규 semantics 0 증명). staged 패리티는 `$fatal`-on-wrong+`cli::run_vcmp/velab/vrun` exit-code로.
- full-suite 실패는 isolation 재실행+직전 run 대조로 flake 판별(패닉 귀속 금지). 실패 테스트=옛 버그 동작 인코딩 의심(오라클과 불일치면 갱신·삭제 금지·주석에 이유). deferred 갭 닫을 때 `grep -rn 'is_loud\|deferred'`로 loud-assert 테스트 선제 flip. big blast-radius 갱신은 mechanically-verifiable invariant(script+assert)로.

## 6. 문서
- **ROADMAP**: 완료=✅(이력 보존·삭제 금지)·신규 슬라이스/부수 발굴은 별개 후보로 기록. §4.5.x에 슬라이스 로그 등재.
- SPEC(`docs/preview/`): 구현이 계획 벗어나면 2회+ 검토 후 타당할 때만 수정. G2 스키마 변경=doc-19+`schema_ver`로만.
- **CLAUDE.md 상태줄**: 최신 1~2 배치만 상세, 이전은 ROADMAP/DEVLOG 포인터로 압축. **REMAINING_WORK.md**: 재계획 시점마다 통째 갱신(상위 스냅샷).

## 7. 커밋 & 푸시 (사용자 의사 무관 진행 OK)
- 스코프: `git add 016_claude_rtl/<path>`(타 프로젝트 누수 금지·.env 금지·.superpowers/scratch 금지).
- 메시지 = `Fix/Add/Update/Refactor <요약>` + 본문(버그·메커니즘·byte-identity·리뷰결과·out-of-scope) + 푸터 2줄(현재 세션 하네스가 지정한 모델명·세션 URL).
- main FF 병합(`git checkout main && git merge --ff-only feat-<slug>`) → 브랜치 삭제 → `git push origin main`.

## 8. 자가 발전 (self-improvement — 이 파일 자체가 산출물)
- **매 반복 종료 시 이 파일을 갱신한다**: ① NEXT 큐 최신화(완료 제거·발굴 후보 삽입·재정렬) ② 이번 반복의 교훈을 §1~5의 **해당 룰에 1줄로 병합**(신규 항목 추가 전 기존 룰과 중복 확인 — 일화·앵커·커밋 SHA는 넣지 않는다, 상세는 ROADMAP §4.5.x/DEVLOG/git이 보존) ③ 반복 실수를 유발한 모호 문구를 발견 즉시 재작성.
- **크기 상한 ~18KB**: 초과하면 다음 반복의 첫 작업=압축(룰만 유지·중복 병합). 히스토리는 이 파일에 쌓지 않는다(2026-07-02 콤팩트화: 82KB→룰 중심, 원문은 git 이력).
- 프롬프트 품질 기준: 다음 반복이 이 파일만 읽고 (a) 무엇을 (b) 어떤 순서로 (c) 어떤 함정을 피해 (d) 어떻게 검증하는지 즉시 알 수 있어야 한다.
- 다음 반복 예약(자기 페이싱·루프 모드일 때만). 보고는 한글·간결.
