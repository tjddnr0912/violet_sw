# 목적
- **vitamin(vita/vcmp/velab/vrun)** 완성 — icarus·verilator·xcelium·vcs급 오픈소스 RTL 시뮬레이터.
- **최우선 원칙 = correct-or-loud**: silent-wrong(틀린 출력·무에러)이 최악. honest-loud(E3009 거부)은 항상 안전. 검증 불가는 구현하지 말 것.

# 매 반복 = 잔여 1개 슬라이스를 끝까지(그라운딩→구현→적대리뷰→문서→커밋·푸시). 아래 순서를 그대로.

## 0. 컨텍스트 고정값 (재발견 금지)
- 빌드/게이트: `cargo build -p cli --locked` (바이너리 `target/debug/vita`) · 전체 게이트 `cargo test --workspace --locked` · `cargo clippy --workspace --all-targets --locked -- -D warnings` · `cargo fmt --all -- --check`.
- 오라클: **iverilog 13.0** `/opt/homebrew/bin/iverilog` (compile `iverilog -g2012 -o x.vvp f.v`, run `vvp x.vvp`). ⚠️ iverilog는 **concurrent assertion(SVA)·clocking block을 거부** → 그 영역은 **vita-내부 차분**(검증된 등가식과 비교)이 teeth. macOS엔 `timeout` 없음 → SV 안에 `#N $finish` 워치독.
- 불변식: **format_version 19**(루트 SchemaHash=sim-ir SimIr). frozen sim-ir 형상 변경만 bump(드묾·골든 재생성 동반). 그 외 전부 **IR-0**(엔진/elaborate-local·사이드카). **3-OS byte-identical**이 perf보다 우선. ⚠️ **AST(hdl-ast) 필드 추가 = `.vu` 스키마 해시만 re-pin**(별개 게이트 `hdl-ast/tests/schema_hash.rs` EXPECTED+doc줄 갱신)·format_version은 불변(sim-ir 아님). 실패하면 새 해시로 갱신=의도된 변경.
- 정본 문서: SPEC=`docs/preview/` · 잔여/전략=`docs/ROADMAP.md` · 이력=`docs/DEVLOG.md`.

## 1. 아이템 선택 (ROADMAP에서 1개)
- `docs/ROADMAP.md` 잔여 항목 확인(특히 §4.5.x의 발굴된 pre-existing silent-wrong·개발예정 목록).
- **선택 전 후보를 오라클로 재현 검증**: 문서화된 "미수정 버그"가 이미 오라클과 일치할 수 있음(misdiagnosed·이전 슬라이스가 부수 수정·특정 트리거 필요). 재현 안 되면 비목표로 기록하고 다음 후보로. (이번 루프: `@*` t0·`@*` Comb self-write·#5 mixed-edge가 전부 이미 일치였음.)
- **우선순위: ① 오라클 있는 CRITICAL silent-wrong > ② 오라클 있는 기능 갭(loud→supported) > ③ 전제조건 충족된 honest-loud 승격.** 오라클 없음·전제조건 미충족(예: arm-slot 추적·deferred hier-edge-sens 필요)은 **건드리지 말고 honest-loud 유지**.
- **쉬운 silent-wrong 소진 시 ②(loud→supported)로 전환**: vita가 loud-reject하나 iverilog가 지원하는 흔한 구문을 오라클로 찾을 것(예: multi-driver tristate). **loud→supported는 additive라 byte-identity가 강력**(거부되던 구문은 기존 디자인에 전무)=silent-wrong 수정보다 저위험. ⚠️ **단, elaborate가 허용을 시작하는 집합 = 엔진이 실제 처리하는 집합이 EXACTLY 동일해야 함**(불일치=허용됐으나 미처리=last-wins silent-wrong). 둘의 eligibility 술어를 같게 쓰고 적대 리뷰로 집합 동일성을 검증.
- **"byte-identity 리스크가 커 보여 defer"는 측정으로 검증**: 우려가 과대평가일 수 있음(이번 루프: narrow-posedge 와이드화의 "다수 골든 flip" 우려가 측정상 미현실화=t0 무영향·전체 스위트 무회귀). defer 전 실제 영향 케이스를 오라클로 핀.
- 선택 즉시 격리 브랜치: `git checkout -b feat-<slug>` (main에서 직접 구현 금지).

## 2. 사전 리뷰 = 오라클 그라운딩 (브레인스토밍)
- **버그/기능을 오라클로 라이브 재현**: 최소 SV repro 여러 개를 iverilog와 vita 양쪽에 돌려 **정확한 IEEE 규칙을 핀**(예측 금지·측정). 엣지/x·z/멀티비트/NBA/경계까지 변형 probe.
- 관련 코드(파이프라인 해당 단계)를 정독 → **byte-identity 논증**(이 변경이 비대상 디자인서 왜 무영향인지)을 먼저 세움. 못 세우면 범위를 좁히거나 honest-loud.
- 계획을 scratchpad에 durable 기록(파일·메커니즘·테스트 매트릭스·loud 유지선).

## 3. 구현
- 가능한 IR-0. 단일 write/엣지 등 **공통경로엔 청크포인트가 하나인지 먼저 확인**(인터프리터+VM 공유 funnel 여부). 모든 동치 경로를 빠짐없이 커버.
- 비-대상 디자인은 byte-identical 유지(가드/사이드카=값 다를 때만).
- **순수 파서 desugar(기존 AST 노드 재사용)는 최저위험 loud→supported**(inc/compound·break/continue): 신규 구문이 기존 구문의 shorthand면(`i+=e`≡`i=i+e`·`i++`≡`i=i+1`) elaborate/IR 손대지 말고 **파서서 기존 `Stmt::Blocking` 등으로 desugar**→AST/sim-ir/`.vu` 해시 전부 불변(신규 AST 타입 0). lvalue가 양변에 등장하면 `lvalue_to_expr`(역 `expr_to_lvalue`)로 rhs 합성·precedence는 operand를 `expr(0)` 전체 파스 후 wrap. 부수효과 expr 형태(`a=i++`)는 Pratt expr 파서에 미추가→loud 유지(scope 분리).
- **AST 노드 추가 전에 "기존 end-to-end 메커니즘이 이미 그 일을 하는지" 확인**(이번 루프 break/continue): control-flow도 기존 구문으로 표현되면 재사용=elaborate/engine 신규 경로 0. 예: `break`/`continue`는 `disable <label>`→Goto(파서+elaborate+engine 完備)로 desugar→IR/엔진 무변경(AST 노드+loop-target-stack 설계보다 우위). 사전에 `grep`로 등가 메커니즘(disable·goto·기존 desugar) 존재 확인.
- **같은 구문의 N개 parser 변종은 ALL을 공유 헬퍼로 라우팅**(이번 루프 do-while 누락=silent-wrong): 루프처럼 변종이 여러 파서 함수면(for/while/repeat/forever/foreach + **do-while**=별도 `parse_do_while`) `grep 'fn parse_'`로 전수 열거→하나라도 공유 헬퍼(`parse_loop_body`) 미경유 시 그 변종서 desugar 미적용=잘못된 타깃/드롭(do-while 안 break가 enclosing 루프 종료=silent-wrong). = §3 'ALL elaborate 컨텍스트 전수'의 **parser-변종판**. (이번 루프 soundness은 do-while을 'honest-loud'로 분류했으나 differential이 중첩 시 silent-wrong 입증→differential 우선.)
- **렉서 토큰 추가 시 logos longest-match를 prefix 공유 ALL 기존 토큰과 대조**(이번 루프 14 토큰): 다char 연산자 충돌 전수(SVA `|=>`/`|->` vs 신규 `|=`·`<<=` vs `<=`/`<<`/`<<<`·`>>>=` vs `>>>`). **필요한 모든 길이가 정의돼야** longest-match가 기존 스트림 보존(공백 없는 `a++b`만 신규 융합=iverilog도 loud=무해). SVA/unary-`+`/shift/reduction repro로 byte-identity 실측.
- **per-net 사이드카는 net 생성하는 ALL 경로에 populate**(이번 루프 CRITICAL): body decl·**ANSI `elaborate_ports`**·**non-ANSI `PortDecl` 루프**·heap-handle/dyn-array 분기가 전부 별개 add_net 사이트. body decl 한 곳만 채우면 `output wand` 등 포트 net이 사이드카 누락→default 처리로 silent-wrong. 구현 전 `grep add_net`로 사이트 전수 열거.
- **staged 경로(velab→vrun) 패리티는 필수, "한계로 문서화"는 금지**(정정): 엔진-facing 사이드카가 one-shot `vita`만 타고 staged서 드롭되면 = 경로별 결과 불일치 = silent-wrong. `StagedExtraSidecars` 14th `.velab` 트레일러에 **append-only**로 추가(struct 필드·`from_sidecars` clone·vrun apply 3곳)+`staged_extra_sidecars_wire_shape_is_pinned` 픽스처 갱신+`REGEN_GOLDEN=1`로 핀 해시 재생성. out-of-band 트레일러라 **format_version bump 불필요**(선례=clocking/ca_delays). staged 회귀 테스트=`$fatal`-on-wrong로 exit-code 검증(`cli::run_vcmp/velab/vrun` lib API). **단 기존 사이드카(예: `ca_delays`)로 desugar하면 staged는 무료**(이미 trailer에 있음).
- **"기존 path로 desugar" 슬라이스는 그 path가 도는 ALL elaborate 컨텍스트를 전수**(이번 루프 generate silent-wrong): 같은 desugar 함수(예: `elaborate_net_init_drivers`)가 module-item body 루프엔 연결됐어도 **generate-Logic phase·block-local 등 다른 컨텍스트의 dispatch arm이 누락**이면 그 컨텍스트서 driver가 silently drop. 신규 구문이 거기서 파스되면 pre-existing drop이 신규 silent-wrong로 노출. `grep '<desugar_fn>'`·`grep 'GenPhase::Logic'`로 호출 컨텍스트 전수 확인 → 누락 arm 추가(무delay pre-existing도 동시 수정됨).
- **파서가 새 구문을 수용하면 그 파서 경로가 도는 ALL 스코프 점검**(이번 루프 procedural delay-swallow): 한 파서 함수(예: `parse_net_var`)가 module/generate/block/func/task/class 6곳서 호출되면, 새 구문이 elaborate가 **실제 처리하는 스코프**서만 수용되도록 플래그(`allow_*: bool`) 스코핑. 안 그러면 미처리 스코프서 silently 삼킴(=이전 parse-error를 silent로 격하). = §1 eligibility-set parity의 **스코프판**.

## 4. 사후 리뷰 = 적대 서브에이전트 (이번 루프서 CRITICAL 회귀 1건을 여기서 잡음=`output wand` 포트 net이 body-decl과 별개 생성 경로라 사이드카 누락→wire-x silent-wrong; differential이 포트/계층/generate 변형 probe로 발굴 — 절대 생략 금지)
- **병렬 ≥2 서브에이전트**, 각 다른 렌즈: (a) **differential silent-wrong 헌트**(오라클로 수십 케이스 차분, byte-identity 위반·신규 divergence) (b) **로직 soundness**(staleness·reset 타이밍·완전성·통합지점=force/clocking/NBA/다른 write 경로). 4축(Architecture·Performance·Maintainability·Robustness) 포함.
- 각 발견을 (a)신규 silent-wrong (b)pre-existing 무관 (c)문서화된 out-of-scope로 분류. **(a)는 즉시 디버깅·수정**.
- **soundness(hand-proof)와 differential(라이브 오라클)이 충돌하면 differential이 이긴다.** (이번 루프: soundness가 per-timestep 디둡을 "SOUND"라 했으나 differential이 CRITICAL 회귀 발굴→옳았음. hand-proof는 가정 누락 가능, 라이브 차분은 실측.) 수정 후엔 라이브 오라클로 재확인.
- **fix 입도(granularity)는 경계 케이스로 측정해 확정**(예측 금지): 같은 버그군서 collapse돼야 할 케이스 vs 재발화해야 할 케이스를 둘 다 오라클로 핀해 정확한 축(per-net? per-timestep? region/cluster 경계?)을 찾을 것.
- **soundness의 이론적 silent-wrong 제기는 측정으로 검증(가정 금지)**(이번 루프 "double-eval"): desugar 슬라이스면 ① 신규형 ≡ explicit-desugar-target byte-identical 확인(=transform 정확) ② 의심 quirk가 explicit 단독서도 재현되는지 격리(재현=pre-existing·무관). 둘 다 통과면 신규 silent-wrong 아님(별개 pre-existing 후보로만 기록).
- **silent issue 1건이라도 → 수정 후 사후 리뷰 재시작. CLEAN 나올 때까지 반복.** stash 차분으로 pre/post 회귀를 실증.

## 5. 게이트
- `cargo test --workspace --locked` 0 fail·카운트 증가(신규 회귀 테스트 포함, 오라클 핀; 오라클 없으면 vita-내부 차분 핀). clippy·fmt clean. format_version 의도대로 불변.
- **"기존 구문으로 desugar" 슬라이스의 최강 회귀 테스트 = vita-내부 등가 differential**(이번 루프): 신규 형태가 등가 기존 형태와 **byte-identical stdout**임을 assert(`wire #3 w=a` ≡ `wire w; assign #3 w=a`). 오라클 비의존+pre-existing 양자(예: delay pre-drive z/x)에 견고=구현이 정확히 그 path로 가는지 직접 증명. 오라클 차분은 settled 값만(pre-drive 윈도 회피).
- **실패 테스트 = 옛 버그 동작 인코딩 의심**(의미론/스케줄러 수정 시 흔함): 수정 중인 구문(예: `a=~a` 오실레이터·글리치)을 기존 테스트에서 grep해 **선제 점검**. 실패 테스트가 오라클과 불일치하면 **올바른 구조로 갱신**(삭제 말고)·주석에 옛 가정이 왜 틀렸는지 명시. (이번 루프: differential 리뷰가 옛-무한루프 테스트 2건 발굴.)

## 6. 문서
- **ROADMAP**: 완료 항목을 ✅로 표시(이력 보존·삭제 금지)·새 슬라이스 항목 추가. 사후 리뷰가 부수 발굴한 별개 silent-wrong은 **각 별개 슬라이스 후보로 신규 기록**(서두르지 말 것).
- SPEC(`docs/preview/`): 구현이 계획서 벗어나면 2회+ 검토 후 타당할 때만 수정.
- **CLAUDE.md 상태줄**: 최신 1~2 배치만 상세, 그 이전은 **ROADMAP §x·DEVLOG 포인터로 압축**(무한 증식 방지 = context 낭비 절감). 압축 전 해당 상세가 ROADMAP/DEVLOG/git-커밋에 있는지 확인.

## 7. 커밋 & 푸시 (사용자 의사 무관 진행 OK)
- 스코프: `git add 016_claude_rtl/<path>`(타 프로젝트 누수 금지·.env 금지·.superpowers/scratch 금지).
- 커밋 메시지 = `Fix/Add/Update/Refactor <요약>` + 본문(버그·메커니즘·byte-identity·리뷰결과·out-of-scope) + 푸터 2줄:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` / `Claude-Session: https://claude.ai/code/session_015e8bYmYjqLGoqzYi8oD2P4`.
- main FF 병합(`git checkout main && git merge --ff-only feat-<slug>`) → 브랜치 삭제 → `git push origin main`.

## 8. 루프 유지
- 본 LOOPROMPT.md를 이번 반복서 배운 점으로 더 핀포인트하게 보강(이 항목 포함).
- 다음 반복 예약(자기 페이싱). 보고는 한글·간결.
