# 006_auto_bot 트러블슈팅

각 항목은 6필드(증상/원인/해결/복구절차/관련 사고/재발 감지) + Claude 진단 미스 기록 구조를 따른다.

---

## 메인 미리보기/메타설명에 CSS(`.gm-lb{display:none…}`)가 노출

- **증상**: 글 본문은 정상인데 **메인 페이지 미리보기(발췌)** 와 검색 메타설명이 `.gm-lb{display:none;position:fixed;…}` 같은 **CSS 텍스트**로 깨져 보임.
- **원인**: 라이트박스/코드 보정용 `<style>` 블록을 본문 **맨 앞에 주입**했는데, `auto_excerpt`가 `<[^>]+>`로 **태그만 벗기고 `<style>` 안 CSS 텍스트는 남겨** 그게 발췌 첫 글자가 됨. (Rank Math meta description도 같은 발췌를 써서 SEO 오염.)
- **해결**: `auto_excerpt`가 발췌 추출 전에 `<style>·<script>·<pre>` 블록을 **내용째 제거**(`_RE_NON_EXCERPT`). 누수된 기존 글은 발췌 재설정+PATCH(전수 탐지: excerpt에 `.gm-lb`/`display:none`/`data-gm-` 시그니처). (2026-06-17)
- **복구 절차**: (a) `GET /posts?context=edit`로 각 글 `excerpt.raw` 점검 (b) 시그니처 매칭 글에 `excerpt=auto_excerpt(content)` 재설정 PATCH (c) 신규 글은 봇 재시작 후 자동.
- **관련 사고**: 2026-06-17.
- **재발 감지**: 발행 후 `excerpt.raw`에 `{`/`display:`/`data-gm-` 포함 여부. 본문에 `<style>`/`<script>`/`<pre>`를 주입할 때는 **반드시 발췌 생성에서 제외**할 것.

> Claude 진단 미스: 없음. 사용자가 미리보기 깨짐 + "내용은 정상"을 정확히 제시 → `excerpt.raw`를 직접 조회해 CSS 텍스트가 발췌로 들어간 것을 즉시 특정. 교훈: 주입한 `<style>`가 **발췌 경로**에 영향(태그만 strip하면 CSS 텍스트 잔존).

---

## 수식/평문 다크 코드박스가 빈 박스처럼 보임(글자 안 보임)

- **증상**: `<pre>` 다크 박스 안 수식("Setup 제약 : T_period ≥ …")이 보이지 않고 빈 박스처럼 깨져 보임.
- **원인**: AI가 `<pre style="background:#2c3e50"><code style="color:#ecf0f1">`로 다크 박스를 만드는데, **테마 CSS `code{background:연한색}`가 안쪽 `<code>`에 적용**돼 밝은 글자가 밝은 배경에 묻힘. (라이브 computed style: preBg=`rgb(44,62,80)` 다크지만 codeBg=`rgb(236,239,243)` 연한색 → light-on-light.)
- **해결**: `create_post`→`fix_styled_code_contrast`가 `pre[style*="background"] code{background:transparent!important;color:inherit!important}` 스코프 `<style>`(`data-gm-codefix`)를 1회 주입 → `<pre>`의 다크 배경이 보이고 글자 가독. 일반(bare) 코드블록은 무관. (2026-06-17)
- **복구 절차**: (a) 브라우저 DevTools/`getComputedStyle(code).backgroundColor`로 code 배경이 pre와 충돌하는지 확인 (b) 기존 글은 `fix_styled_code_contrast(content.raw)` 후 PATCH(post 238 선례) (c) 봇 재시작.
- **관련 사고**: 2026-06-17.
- **재발 감지**: 다크 스타일 코드박스 발행 후 육안(빈 박스 여부). 테마 교체 시 `pre code` 배경 규칙 재확인. 라이브 검증은 브라우저 computed style이 가장 확실(렌더 HTML grep으로는 테마 CSS 적용 결과를 못 봄).

> Claude 진단 미스: 없음. "수식이 깨져 보인다"를 곧장 라이브 `getComputedStyle`로 확인 → code 배경(연한색)이 pre 다크 배경 위에 덮여 light-on-light임을 특정. 교훈: **렌더 결과(테마 CSS 적용)는 HTML grep이 아니라 브라우저 computed style로 진단**.

---

## 다이어그램이 (mermaid 포함) 전부 코드블록으로 발행됨 — <pre style> 미매칭

- **증상**: 어떤 글은 다이어그램이 잘 나오는데 어떤 글은 d2·wavedrom·**mermaid까지 전부** 원본 코드로 노출. "여전히 그림이 아닌 게 많다".
- **원인**: `_RE_DIAGRAM_BLOCK`이 **bare `<pre>`만** 매칭. AI HTML 변환기(`blogger-html` SKILL→Claude)가 **비결정적으로** `<pre style="…">`처럼 속성을 붙여 출력하면 정규식이 0개 매칭 → 모든 다이어그램 미렌더. (잘 되던 글은 우연히 bare `<pre>`였을 뿐 — 타입 문제가 아니라 **컨테이너 태그 형태** 문제.)
- **해결**: `<pre>` → `<pre[^>]*>`(속성 허용). styled-pre 회귀 테스트. (2026-06-17)
- **복구 절차**: (a) `curl -sL <글> | grep -oE 'class="language-[a-z0-9-]+"'` 로 잔존 코드블록 확인 (b) 같은 소스를 `_RE_DIAGRAM_BLOCK.findall`로 매칭되는지 점검 — 안 되면 `<pre>` 형태(속성/래퍼) 의심 (c) 기존 글은 content.raw로 재렌더+PATCH(post 238 선례) (d) **봇 재시작**.
- **관련 사고**: 2026-06-17.
- **재발 감지**: AI 변환기 출력은 비결정적이므로 다이어그램 컨테이너 정규식은 **태그 속성/공백/래퍼에 관대**해야 함. "일부 글만 실패"는 타입이 아니라 **마크업 변형**(`<pre style>` 등)을 먼저 의심. 발행 후 `language-` 잔존 grep 점검.

> Claude 진단 미스: 없음. "mermaid까지 전부 실패"라는 *선택적이지 않은* 실패 패턴을 보고 곧장 마크업 형태를 의심 → `<pre style="…">` 확인. (이전 d2/wavedrom 건의 "일부 타입만 실패=backend 차이" 교훈의 역패턴: *전부* 실패면 공통 경로(정규식/컨테이너)를 의심.)

---

## WaveDrom 파형에 톱니(notch)가 계속 보임

- **증상**: wavedrom 다이어그램에서 신호가 유지(constant)돼야 할 구간에도 매 주기 작은 `∨` 톱니가 반복. 클럭/신호가 깨진 것처럼 보임.
- **원인**: wave 문자열이 같은 레벨을 **리터럴 반복**(`"00110011"`, `"0000…1111"`)으로 표기됨. WaveDrom은 같은 값이 인접 반복되면 경계마다 재샘플 글리치(notch)를 그린다. `.`(이전 상태 유지)로 쓰면 평탄하게 그려짐.
- **해결**: `render_kroki_png`(wavedrom)에서 `_normalize_wavedrom`이 `"wave"` 값의 인접 동일 레벨 기호 `{0,1,x,z}`만 `.`로 접어 결정론적으로 교정. 클럭(`p/n/h/l` 등)·버스데이터(`=`,`2-9`)·gap(`|`)은 미변경(반복에 의미). 의도된 1주기 글리치는 보존. (2026-06-16)
- **복구 절차**: (a) 의심되면 `_collapse_wave("00110011")` 가 `"0.1.0.1."` 인지 확인 (b) 기존 글은 원본 wave 소스로 재렌더 후 이미지 URL 교체+PATCH (post 229 선례) (c) 클럭/버스가 접히면 안 됨 — `_WAVE_LEVEL` 집합 점검.
- **관련 사고**: 2026-06-16.
- **재발 감지**: 발행 글의 wavedrom 이미지 육안 점검(유지 구간 톱니 유무). 테스트 `test_collapse_wave_*`가 글리치/클럭/버스 보존을 회귀 검증.

> Claude 진단 미스: 없음. 사용자가 정확히 원인(리터럴 반복 vs `.` 유지)을 지목했고, 라이브 렌더 비교(orig 톱니 vs dotted 평탄)로 확정 후 결정론적 정규화로 해결.

---

## WaveDrom 파형이 본문 설명과 모순됨 (래치가 D를 안 따라감 등) — AI 의미론 오류

- **증상**: 다이어그램은 이미지로 잘 렌더되는데 **파형의 의미가 틀림**. 예: 글은 "레벨 민감 래치는 CLK High 동안 D를 즉시 따라가 글리치까지 새어 나간다"고 써놓고, 정작 Latch 파형은 D의 중간 dip을 무시한 채 High를 유지. **글과 그림이 모순**.
- **원인**: 렌더/정규화 버그가 **아님**. AI가 생성한 **wave 소스 데이터 자체가 의미론적으로 틀림**(Latch wave에 D의 dip이 애초에 없었음). `_collapse_wave`는 `ch == held`(같은 레벨)일 때만 `.`로 접으므로 **전이를 절대 제거하지 못함**(transition-preserving) → 파이프라인이 dip을 지운 게 아니라 소스에 dip이 없던 것.
- **해결**: (의미론 정확성은 코드로 강제 불가) 프롬프트 레버로만 방어 — `research_orchestrator.py` `_SYNTH_PROMPT_TEMPLATE` + 글로벌 스킬 `telegram-qa`/`blogger-html`에 **파형 자기일관성 가드** 추가: 레벨 민감 래치=High 동안 D 즉시 추종(글리치·하강 통과)·Low면 hold / 엣지 FF=엣지의 D만 포착 / 글-그림 모순 금지. (2026-06-17)
- **복구 절차**: (a) 렌더 PNG를 받아 육안으로 파형 의미 검증 (b) `_collapse_wave`가 transition-preserving임을 재확인(원본 소스 결함이지 정규화 결함 아님) (c) 올바른 wave 소스를 작성→`render_kroki_png(src,"wavedrom")`로 재렌더→`upload_media`로 새 PNG→`GET /posts?slug=…&context=edit`의 content.raw에서 이미지 URL 2곳(썸네일+라이트박스) 교체→`POST /posts/{id}` PATCH. (라이트박스 `href`/`id`(digest)는 서로 일치만 하면 되니 건드릴 필요 없음 — post 254 선례.)
- **관련 사고**: 2026-06-17.
- **레벨 민감성 함정(2회 재지적)**: 래치는 **CLK High 동안만** D를 추종(투과), Low면 hold. 비투과 동작은 파형에서 오해를 부른다 — ①D 전이가 CLK Low면 래치가 다음 엣지까지 hold→**엣지 전이**해 FF처럼 보임("왜 latch가 FF처럼 엣지에서 떨어지지?"), ②hold 시연용 CLK-Low 펄스 차단은 "D는 dip인데 Latch flat"이 **래치가 D를 안 따라가는 오류처럼** 보임("D와 Latch 코드가 같아야 하는 거 아냐?"). ⭐교훈: 교육용 파형은 **모든 D 전이를 CLK High 안에** 두어 **Latch wave ≡ D wave(투과)**로 그리고 FF(엣지 샘플)와의 대비에만 집중, hold는 **본문 텍스트로** 설명. 그림 바꾸면 본문도 맞춤.
- **연관(SystemVerilog non-blocking)**: `always_latch`의 `q <= d`(non-blocking)는 **올바름** — 래치=레벨 민감 **순차** 소자라 FF처럼 non-blocking, 조합 `always_comb`만 blocking(`=`). `iverilog -g2012`로 컴파일 검증 가능. 코드 트집 전에 이 규칙(조합=blocking / 순차·래치=non-blocking) 확인.
- **재발 감지**: 발행된 wavedrom 이미지의 **의미**를 본문 설명과 대조(특히 래치 투과/hold, FF 엣지 샘플, 글리치 누설). 톱니/raw-코드 같은 *렌더* 버그와 달리 테스트로 못 잡음 — 검토 시 그림 의미를 직접 읽을 것.

> Claude 진단 미스: 없음. 단, **교훈**: "다이어그램이 이상하다"는 두 부류로 갈림 — ① 렌더/파이프라인 버그(전부 raw·톱니 → `_RE_DIAGRAM_BLOCK`/`_collapse_wave` 등 **결정론적 코드 수정** 가능) vs ② AI 의미론 콘텐츠 오류(이미지는 멀쩡한데 파형 뜻이 틀림 → **프롬프트 레버만** 가능). 이번 건은 이전 렌더 버그 연쇄 뒤라 정규화(`_collapse_wave`)를 의심할 유혹이 있었으나, **transition-preserving임을 증명**해 ②로 곧장 분류. 첫 의심: 그림이 렌더는 됐는데 *뜻*만 틀리면 정규화/렌더가 아니라 **소스 데이터(AI 출력)**부터 본다.

---

## d2/wavedrom 다이어그램이 이미지가 아니라 원본 코드로 발행됨

- **증상**: 발행 글에서 d2(아키텍처)·wavedrom(타이밍) 코드블록이 PNG로 안 바뀌고 `<pre><code class="language-d2/wavedrom">` 원본 그대로 노출. 같은 글의 mermaid는 정상 이미지.
- **원인**: **kroki가 d2·wavedrom(및 nomnoml/pikchr/svgbob/vega 등)에 PNG 출력을 지원하지 않음** — `/d2/png`·`/wavedrom/png`는 HTTP 400 "Unsupported output format: png … Must be one of svg" 반환. 옛 `render_kroki_png`는 `/{type}/png`만 호출+PNG 매직바이트 요구 → None → `_render_diagrams_in_html`이 원본 블록 유지. (인라인 SVG는 WordPress가 깨므로 SVG 직삽도 불가.)
- **해결**: `render_kroki_png` 포맷 인지형 — svg-only 타입(`_KROKI_SVG_ONLY`)은 `/svg`를 받아 **headless Chrome(`_svg_to_png`, `CHROME_BIN`)으로 PNG 래스터화**. png 네이티브 타입은 종전대로 `/png`(거부 시 svg fallback). 라이브 d2+wavedrom로 검증(한글 라벨 OK). (2026-06-16)
- **복구 절차**: (a) `curl -sL <글> | grep -o 'language-[a-z0-9-]*'` 로 잔존 다이어그램 펜스 확인 (b) `curl -X POST --data-binary @x.d2 https://kroki.io/d2/png` 로 kroki가 png 주는지 직접 확인(400이면 svg-only) (c) `CHROME_BIN` 경로/존재 확인 (d) **봇 재시작** 후 재발행 또는 기존 글 재렌더.
- **관련 사고**: 2026-06-16.
- **재발 감지**: 신규 kroki 타입 추가 시 `curl .../<type>/png`로 PNG 지원 여부 먼저 확인. PNG 미지원이면 `_KROKI_SVG_ONLY`에 추가(누락해도 png 1회 시도 후 svg fallback으로 동작은 함). 발행 글에 `language-` 잔존 grep으로 점검.

> Claude 진단 미스: **초기 가설이 "봇이 옛 코드로 구동 중(미재시작)"이었으나 증거로 반증됨** — 렌더된 PNG 파일명이 `diagram-mermaid-…`(신naming `diagram-{type}-{hash}`)이고 봇 시작시각(22:29)이 코드 커밋(22:04) 이후라 **신 코드가 돌고 있었음**이 확정. mermaid만 되고 d2/wavedrom만 안 되는 *선택적* 실패가 핵심 단서였는데 "재시작 누락"으로 오인할 뻔함. 교훈: **"일부 타입만 실패"는 코드 버전이 아니라 타입별 backend(여기선 kroki png 지원) 차이를 먼저 의심**할 것. 결정 명령 = `curl -X POST --data-binary @src https://kroki.io/<type>/png`(라이브로 png 지원 직접 확인).

---

## d2가 코드로 발행됨 — kroki 컴파일 실패(문법 오류) + 조용한 폴백 (위 Chrome 케이스와 구분)

- **증상**: 한 글 안에서 **일부** d2만 PNG로 안 바뀌고 `<pre><code class="language-d2">` 원본 코드로 노출. 같은 글의 mermaid·다른 d2는 정상 이미지. (위 "d2/wavedrom…" 항목은 *모든* svg-only 타입이 Chrome 부재로 실패하는 케이스 — 여기는 **특정 d2 블록만** 실패.)
- **원인**: 해당 d2 소스의 **문법 오류** → kroki가 HTTP 400(컴파일 실패) 반환 → `render_kroki_png`=None → `_render_diagrams_in_html._repl`이 **아무 경고 없이** 원본 코드블록 유지(조용한 폴백). 실제 2건: ① `shape: database`(mermaid엔 있으나 d2엔 없는 shape — d2는 `cylinder`/`stored_data`) ② `font-weight: bold`(CSS 키워드 — d2는 `bold: true`). LLM이 d2 문법을 다른 다이어그램/CSS 방언과 혼동해 생성. 같은 글 mermaid가 정상 렌더돼 문제를 가림.
- **해결**: (1) **loud 실패**(2026-06-19): `render_kroki_png(errors=[...])`가 kroki 400 본문 캡처 → `_render_diagrams_in_html`이 `_last_diagram_failures` 수집·`logger.error` → `create_post`가 `_alert_diagram_failures`로 운영자 텔레그램 경보(best-effort, 발행 불차단). (2) **생성 가드**: `_SYNTH_PROMPT_TEMPLATE`·`telegram-qa/SKILL.md`에 유효 d2 shape 목록·`database`→`cylinder/stored_data`·`font-weight`→`bold:true` 명시. (3) 라이브 글은 d2 소스 교정→`_render_diagrams_in_html` 재실행→`POST /posts/{id}` content 갱신.
- **복구 절차**: (a) `curl -X POST --data-binary @x.d2 https://kroki.io/d2/svg` 로 **컴파일 상태 직접 확인** — 400이면 본문에 `unknown shape "…"`·`invalid style keyword "…"` 등 정확한 위치·사유가 그대로 옴 (b) 사유대로 소스 교정 후 재-POST가 200인지 확인 (c) 라이브 글이면 content만 PUT 재발행.
- **관련 사고**: 2026-06-19 (post 292, why-soc-bandwidth-designed-narrow).
- **재발 감지**: 발행 후 `다이어그램 발행 경보` 로그·텔레그램 알림이 1차 신호(이제 조용히 안 묻힘). 글에 `language-d2` 잔존 grep도 보조 점검.

> Claude 진단 미스: **초기 가설이 "d2는 svg-only라 Chrome 래스터화 단계에서 실패(바로 위 항목의 원인)"였으나, kroki에 소스를 직접 POST해보니 래스터화 이전에 HTTP 400 컴파일 실패**(`unknown shape "database"`)였음 — Chrome은 정상 탐지·동작. 방향 전환 지점 = 두 d2 소스를 `render_kroki_png`/kroki에 직접 통과시킨 Bash 테스트. 교훈: **"다이어그램이 코드로 박힘" 디버깅 시 Chrome/래스터화(위 항목)보다 먼저 `curl kroki/<type>/svg` 컴파일 상태(400 여부+에러 본문)를 본다.** *일부* d2만 실패=환경(Chrome)이 아니라 **그 소스의 문법** 문제일 가능성이 높다(환경 문제면 같은 타입 전부 실패). 결정 명령 = `curl -X POST --data-binary @src https://kroki.io/d2/svg`.

---

## 발행 글이 "AI가 쓴 느낌" / 질문의 부정확한 전제가 사실처럼 섞임

- **증상**: 텔레그램봇으로 질문해 발행한 글에서, 내가 질문에 담았던 (틀릴 수도 있는) 전제·가정·수치가 검증 없이 사실처럼 본문에 들어감. 글이 "주제에 대한 독립 기사"가 아니라 "내 질문에 대한 답변"처럼 읽혀 AI 생성 티가 남.
- **원인**: 누수 지점은 직관과 달리 **HTML 변환이 아니다.** `convert_md_to_html_via_claude`는 **MD 본문만** 받고 원 질문은 전달받지 않는다(`telegram_gemini_bot.py:635`). 실제 원인은 그 앞 **research/합성 단계** — quick `run_gemini` 프롬프트, deep `_build_round1_prompt`/`_synthesize`(`_SYNTH_PROMPT_TEMPLATE`)가 **질문을 verbatim 임베드**하고 작업을 "사용자 질문에 대한 답변/보고서 작성"으로 프레이밍 → 모델이 질문 전제를 사실로 받아들이고(premise-echoing/sycophancy) 질문 틀을 그대로 따라감.
- **해결**: 질문을 '주제·의도'로만 쓰도록 **3곳에 전제 가드** 추가(2026-06-16): deep `_SYNTH_PROMPT_TEMPLATE`(`research_orchestrator.py`), quick 프롬프트(`telegram_gemini_bot.py`), `telegram-qa/SKILL.md` 핵심 원칙. "전제 미확인 시 교정('질문의 전제와 달리…'), 독자는 질문 미열람→인용·되묻기 금지, 독립 기사로 작성." HTML 변환기는 손대지 않음(이미 깨끗).
- **복구 절차**: (a) 발행 글이 "~라는 질문을 주셨는데" 류로 시작/되묻으면 가드 미적용 의심 (b) **research 프롬프트**(`_SYNTH_PROMPT_TEMPLATE`·quick prompt)와 `telegram-qa/SKILL.md`를 확인 — HTML 변환기/blogger-html SKILL은 **이 증상의 원인이 아니다** (c) 봇 재시작 후 다음 발행부터 반영.
- **관련 사고**: 2026-06-16.
- **재발 감지**: 발행 글 도입부가 질문을 인용/되묻는지, 검증 안 된 질문 전제가 단정형으로 들어갔는지 육안 점검. **"AI 느낌/부정확 정보" 디버깅 시 HTML 변환부터 보지 말 것 — 질문 텍스트는 거기 도달하지 않는다.** research/합성 프롬프트가 1순위 의심 영역.

> Claude 진단 미스: 없음. 이번엔 사용자가 Claude를 정정한 게 아니라 **사용자 가설("HTML 변환 과정에서 질문이 참조되는 것 같다")을 Claude가 코드 추적으로 반증**(실제 누수=research 단계, HTML 변환기는 MD만 수신). 교훈은 위 "재발 감지"에 박제 — 직관적으로 HTML 변환을 의심하기 쉬우나 데이터 흐름상 틀림.

---

## 발행 글에 출처(외부 링크)가 안 보임 — AI HTML 변환이 비결정적으로 삭제

- **증상**: 봇이 조사한 출처가 있는데도 발행된 WordPress 글에 클릭 가능한 외부 링크(`<a href>`)가 없음. Rank Math가 "outbound links 없음 / 전부 nofollow" 경고. 텔레그램 글은 어떤 날은 링크가 있고 어떤 날은 없음(들쭉날쭉).
- **원인**: 출처는 데이터로 존재했으나(`research_orchestrator`가 `{title,url}`로 파싱) 본문 HTML로 만드는 경로가 **AI 변환(`blogger-html` SKILL)** 을 거치는데, SKILL의 "연구 과정 흔적 제거" 단계가 출처/References를 **비결정적으로 누락**시킴. 텔레그램은 마크다운 `## References`를 붙였지만 그게 AI 변환에서 살아남을지가 모델 출력마다 달랐음.
- **해결**: AI에 맡기지 말고 **모든 봇이 거치는 발행 단계(`wordpress_uploader`)에서 결정론적으로** 렌더. `render_sources_section()`(dofollow `rel="noopener"`·새 탭·중복 제거·http only) + `create_post`/`upload_post`에 `sources` 인자. 텔레그램은 마크다운 References 주입을 제거하고 `sources`만 업로더로 전달(중복 방지). (2026-06-15)
- **복구 절차**: (a) 발행 글 본문에 `data-sources-section` 마커 유무 확인 (b) 없으면 해당 봇 호출부가 `upload_post(..., sources=...)`로 넘기는지 확인 (c) 출처가 구조화 안 된 봇(뉴스 종합·버핏)은 의도적 제외임을 기억.
- **관련 사고**: 2026-06-15.
- **재발 감지**: 발행 직후 글 HTML에 `data-sources-section`/`참고 자료`가 있는지, 또는 Rank Math outbound-links 항목으로 점검. AI 변환 SKILL을 고쳤다고 출처가 보장되는 게 아님(그 경로는 비결정적) — 항상 업로더 결정론 경로로 확인.

> Claude 진단 미스: 이번 작업엔 사용자 corrective 신호 없음(기능 추가, 헛발질 아님). 단 교훈 1건 — 서브에이전트(Explore)가 "출처는 완전히 stripped"라고 단정했으나 직접 코드를 읽으니 텔레그램엔 (불안정한) References 경로가 있었음. **서브에이전트의 "전혀 없다"류 단정은 직접 grep으로 검증**할 것.

---

## 섹터봇 분석이 주차별로 묘하게 짧아짐

- **증상**: 섹터 주간 보고서가 어떤 주는 풍성하고 어떤 주는 얇음. 사용자가 "지난주보다 짧은 느낌".
- **원인**: 섹터 분석 길이는 **순전히 어느 Gemini 모델이 그 섹터를 처리했냐**에 좌우(실측 `gemini-3.1-flash-lite` ~2,300자 vs `gemini-3.5-flash` ~7-16천자, 3~8배). 기본이 flash-lite라 평소엔 얇고, flash-lite가 quota로 3.5-flash fallback될 때만 길어짐. `sector-analysis/SKILL.md` 분량 floor가 `2000자`로 낮아 flash-lite가 바닥에 밀착. (검색은 별개 — agy/Gemini Pro로 ~6천자 잘 가져옴, 짧음은 검색이 아니라 **분석 모델** 문제.)
- **해결**: `SECTOR_GEMINI_MODEL` 기본값을 `gemini-3.5-flash`로 승격 + 섹터 전용 `SECTOR_GEMINI_FALLBACK_MODELS`(flash-lite 우선)로 무중단 degrade + SKILL 분량 floor `5000자 이상(상한 없음)`. (2026-06-07, [[agy-websearch-migration]] 후속)
- **복구 절차**: (a) 짧으면 로그 `grep "Analysis completed: model="`로 모델 확인 (b) flash-lite면 `SECTOR_GEMINI_MODEL=gemini-3.5-flash` 적용 (c) **봇 재시작** 후 다음 섹터부터 반영(`SectorAnalyzer initialized (primary model: ...)` 로그로 확인).
- **관련 사고**: 2026-06-07.
- **재발 감지**: `grep "Analysis completed: model=" logs/*.log` 에서 chars 값이 2천대로 떨어지면 flash-lite로 처리 중(3.5-flash 쿼터 소진 가능성).

### Claude 진단 미스

- **Claude 처음 가설**: 섹터 짧음을 진단하며 "agy 변경은 **아직 미배포**(일요일 실행이라 다음 주에나 반영) + 섹터 짧음과 무관"이라고 단정.
- **실제 원인 (사용자 지적)**: 사용자가 "11:47에 봇을 재시작했다"고 지적 → 로그(`grep agy_websearch`) 확인 결과 **agy는 이미 배포·작동 중**이었음(섹터 검색이 `agy:Gemini 3.1 Pro (High)`로 동작). 짧음의 진단(analyzer 모델) 자체는 맞았으나 "미배포" 사실관계가 틀림.
- **방향 전환 지점**: 사용자의 "11:47에 재시작했어" 메시지 직후 로그를 직접 확인.
- **교훈 (다음에 같은 패턴이면)**:
  - 첫 의심 영역: 배포 여부는 **추정 금지** — 파일 mtime + 재시작 로그(`SectorAnalyzer initialized`)/호출 로그(`agy_websearch`)로 **반드시 확인**.
  - 빨리 배제할 가설: "스케줄이 일요일이니 안 돌았을 것" — `--once` 수동 실행/요일 착각 가능. 로그 타임스탬프가 진실.
  - 핵심 진단 명령: `grep -E "initialized \(primary model|Analysis completed: model=" logs/investment_bot_$(date +%Y%m%d).log | tail`

---

## 데이터 파이프라인 봇 "완료" 보고 시 발행 범위 ≠ 수집 범위 간과

- **증상**: 부동산봇이 백필로 119시군구 4종을 적재했는데 주간 블로그 디제스트는 서울 25구만 발행. 코드는 정상 동작(설계상 v1 발행 범위가 `SEOUL_GU`).
- **원인**: 수집(`ALL_REGIONS`=119)과 발행(`run()`→`SEOUL_GU`=25)의 범위가 분리돼 있었음(v1 의도). `config.py`에 명시돼 있으나 "작업 완료" 보고 시 그 불일치를 사용자에게 안 짚음.
- **해결**: v2(2026-06-04)에서 `run()`을 `ALL_REGIONS`로 확장(전국 단일 글, 권역 요약). → [docs/REALESTATE_BOT.md](REALESTATE_BOT.md).
- **복구 절차**: (a) 발행물에서 비서울 권역 섹션 존재 확인 (b) 없으면 `run()`이 SEOUL_GU로 도는지 점검 (c) ALL_REGIONS로 배선.
- **관련 사고**: 2026-06-04
- **재발 감지**: 디제스트 발행 후 `## 경기`/`## 6대 광역시` 섹션 grep. 없으면 발행 범위가 수집보다 좁아진 것.

### Claude 진단 미스 (2026-06-04 세션, 부동산봇 완성도 보고)

- **Claude 처음 가설**: 오피스텔 전월세 노출 + 부동산봇 명명 정리를 마치고 "부동산봇 작업 완료"로 보고. 주간 발행이 서울 25구 한정인 점을 "미완성"으로 플래그하지 않음(백필은 119구인데).
- **실제 원인 (사용자 지적)**: "봇이 완성이 안된것 같아 ... 블로그 게시글이 서울에 한정되어있어." 수집(119구)과 발행(서울25)의 범위 불일치를 사용자가 포착.
- **방향 전환 지점**: 사용자의 "블로그 게시글이 서울에 한정되어있어" 메시지 → 전국 확장(v2) 브레인스토밍·구현 착수.
- **교훈 (데이터 수집·가공·발행 파이프라인 봇 "완료" 보고 전)**:
  - 첫 의심 영역: **발행/출력 범위 == 수집/적재 범위인지** 대조. 수집만 광범위하고 발행이 좁으면 사용자는 "미완성"으로 본다.
  - 빨리 배제할 가설: "코드가 에러 없이 돈다 = 완료" — 설계상 범위 분리는 정상 동작이지만 사용자 기대(수집한 데이터를 다 활용)와 어긋날 수 있음.
  - 핵심 진단 명령: `grep -n "SEOUL_GU\|ALL_REGIONS" weekly_realestate_bot.py` (백필과 발행 `run()`이 같은 범위인지).

---

## 마이그레이션 옵션 비교 시 원본 설계의 implicit value 무시

- **증상**: Gemini grounding hidden quota 발견 후 backend 마이그레이션 옵션을 비교할 때, Claude가 "Native WebSearch 단순 재작성"(옵션 B)을 운영 단순성·인프라 일관성 근거로 강하게 추천. 사용자가 직접 "여기서 chain 구조가 없어지는건 아쉬워. 이게 포함됐던 이유는 할루시네이션을 없애고, 여러 각도에서의 의견을 더 담아보려고 했던 목적이 있었어"라고 corrective 지적할 때까지 chain의 본래 설계 가치(다관점 검증 + hallucination 방지)를 옵션 비교에 명시적으로 반영하지 않음.
- **원인**: 마이그레이션 옵션 분석 시 "기능적 동등성"(quota 회피, 같은 결과)에 집중하고 **원본 설계가 가졌던 implicit value**(왜 이 chain/wrapper/패턴이 만들어졌나? 단순 fallback 외에 다른 의도는?)를 옵션 표 trade-off에 명시 안 함. Chain은 단순 quota fallback이 아니라 모델·각도 다양화로 hallucination을 감소시키는 도구였는데, 이를 옵션 B 단순 적용에서 잃음.
- **해결**: 옵션 B+로 확장 — Native WebSearch + WebFetch + **Phase 1.5(1차 source 검증)** + Phase 3 query 다양화로 원본 chain의 가치를 다른 방식으로 보존. `~/.claude/skills/research/SKILL.md` 재작성에 NEW Phase 1.5 추가 (WebFetch로 핵심 출처 원문 직접 fetch → snippet vs 원문 대조 → hallucination 검출), Phase 3 다양화 축(키워드/언어/시각/도구) 명시. 라이브 테스트로 검증.
- **복구 절차**:
  - (a) 마이그레이션 또는 큰 리팩토링 옵션 비교 시, 원본 설계가 가졌던 **명시되지 않은 implicit value**를 먼저 식별: "왜 이 chain/wrapper/패턴이 만들어졌나? 단순 quota fallback 외에 다른 의도는?"
  - (b) 사용자에게 옵션 제시할 때 그 가치 보존 여부를 명시적 trade-off 컬럼에 추가 ("Pros/Cons" 외에 "원본 설계의 implicit value 보존 여부" 컬럼)
  - (c) 만약 옵션 채택 후 사용자가 "아쉬워" / "원래 의도는 X였는데" 류 corrective 발화하면 즉시 옵션 확장(예: B+) 또는 재설계
- **관련 사고**: 2026-05-27 PM (research skill backend 마이그레이션, [[research-skill-websearch]])
- **재발 감지**: 마이그레이션 plan에서 옵션 표가 "기능적 동등성"에만 만족할 때 — Pros/Cons 컬럼에 "원본 설계의 implicit 가치 보존 여부"가 없으면 의심. 사용자 corrective 발화 후에 옵션을 재구성하지 말고, 옵션 제시 전에 implicit value 자문할 것.

### Claude 진단 미스 (2026-05-27 PM 세션, research skill 옵션 비교)

- **Claude 처음 가설**: research skill 마이그레이션 옵션 B(Native WebSearch 단순 재작성)가 (i) self-call 어색함 없음, (ii) 봇과 인프라 일관, (iii) ask_gemini.sh 외부 wrapper 불필요 — 따라서 "옵션 B (추천)"으로 강하게 push. 사용자에게 비교 옵션 4개(A/B/C/D) 제시했지만 그 표의 어느 컬럼도 "chain의 본래 가치 보존 여부"를 명시하지 않음. Trade-off는 "운영 단순성", "subprocess overhead", "self-call 어색함" 같은 inrastructure 차원에 머무름.
- **실제 원인 (사용자 지적)**: chain의 본래 목적은 (a) 다관점 cross-check, (b) hallucination 방지였는데, 옵션 B 단순 적용 시 단발 WebSearch 호출 1회로 끝나서 두 효과 모두 잃음. 사용자가 "여기서 chain 구조가 없어지는건 아쉬워. 이게 포함됐던 이유는 할루시네이션을 없애고, 여러 각도에서의 의견을 더 담아보려고 했던 목적이 있었어"라고 명시한 후 Claude가 우려 정당성 인정하고 옵션 B+(WebFetch 1차 source 검증 + query 다양화)로 재설계.
- **방향 전환 지점**: 사용자 메시지 "추천 B가 마음에 들긴 하는데, 여기서 chain 구조가 없어지는건 아쉬워. 이게 포함됐던 이유는 할루시네이션을 없애고, 여러 각도에서의 의견을 더 담아보려고 했던 목적이 있었어". 이 발화 이후 Claude가 옵션 표를 재구성(B+/E/F/G) + "Chain의 진짜 가치 재정리" 섹션 신설.
- **교훈 (다음에 같은 패턴이 보이면)**:
  - 첫 의심 영역: 마이그레이션 옵션 표 작성 시 "**원본 설계의 implicit value**" 컬럼 의무. quota/성능/비용/인프라 차원 외에 "이 wrapper/chain/패턴이 가졌던 다른 가치는?"을 자문하고 답을 trade-off에 명시
  - 빨리 배제할 가설: "기능적으로 같은 결과를 내면 OK" — implicit value(예: hallucination 방지, 다관점 cross-check, 재현성, 학습 효과)가 사라지는 옵션은 그것만으로 정당화 불가. 보존 여부를 별도 검토해야 함
  - 핵심 진단 명령: 옵션 제시 **전**에 사용자에게 "이 [chain/wrapper/패턴]을 처음 만든 의도가 뭐였어요? 단순 [quota fallback / 비용 절감 / X] 외에 다른 목적이 있었나요?"를 한 번 물어볼 것. 사용자 의도와 implicit value를 명시화하면 옵션 비교가 정확해짐
  - 안티패턴: 옵션 제시 후에야 사용자 corrective 받고 재구성. 사전에 묻는 게 훨씬 효율적이고 신뢰도 높음

---

## Gemini 3.x `google_search` grounding 별도 quota 발견 → Claude WebSearch 전환

- **증상**: 2026-05-27 PM, Telegram deep research 호출이 4개 모델(`gemini-3.1-flash-lite` → `gemini-3.5-flash` → `gemini-3-flash-preview` → `gemini-2.5-flash`)에서 순차로 429 반환. fallback chain 마지막 모델만 성공. AI Studio dashboard의 RPM/TPM/RPD는 거의 0%인데도 거부.
- **원인**: **Gemini 3.x의 `google_search` grounding tool은 모델 generate_content API와 별개의 quota bucket을 사용한다.** 무료 티어 한도가 매우 빡빡해 일상 사용으로 즉시 소진. Dashboard에는 모델 API quota만 노출되고 grounding quota는 표시 안 됨. 2.5-flash만 살아남는 이유는 per-prompt pricing이라 grounding이 prompt charge에 포함되기 때문 ([공식 docs](https://ai.google.dev/gemini-api/docs/google-search)).
- **해결**: grounding 호출 4곳(telegram quick/deep, news gap-fill, sector search) 모두 **Claude CLI + WebSearch**로 이전. `claude -p` 모드에서 web_search 도구 자동 활성화. 모델은 호출 시점 `--model` flag로 선택 + `--fallback-model`로 overload 자동 대비. 신규 wrapper `shared/claude_search.py`.
- **복구 절차**:
  - (a) Anthropic API key가 Claude CLI 인증으로 설정되어 있는지 확인 (`claude --version` 후 `claude -p "test"` 성공 여부)
  - (b) `printf 'tiny prompt' | python -c "from shared.claude_search import claude_websearch; r=claude_websearch('Use web search. What day is today?', model='haiku'); print(r.text[:100], len(r.sources))"`로 라이브 검증
  - (c) `pytest 003_test_code/` 72 pass 확인
  - (d) 봇 재시작 후 텔레그램 deep research로 실호출 검증
- **관련 사고**: 2026-05-27 PM (사용자 텔레그램 deep research에서 4개 모델 동시 429 보고 → dashboard 검토 → 모든 quota 여유 확인 → grounding 별도 quota 가설 → grounding ON/OFF 분리 실측으로 확정)
- **재발 감지**: `tail -f logs/telegram_bot_*.log | grep -E "quota/unavailable|429"` 로 모니터링. grounding 호출이 다시 다수 429 누적되면 quota 정책 변경 가능성.

### Claude 진단 미스 (2026-05-27 PM 세션)

**미스 #3 — Dashboard 신호 과신, grounding 별도 quota 가능성 무시**

- **Claude 처음 가설**: 오전에 만든 모델 fallback chain의 첫 모델(`gemini-3.1-flash-lite`)이 429라 "무료 티어 quota 소진" → "PST midnight reset 또는 billing 활성화" 권장. Dashboard 보고도 "각 모델별 quota bucket 별개라 4개 다 동시에 소진 가능"으로만 설명.
- **실제 원인**: 사용자가 dashboard 스크린샷을 직접 보여줌 — `gemini-3.1-flash-lite` 10/500 RPD, `gemini-3.5-flash` 0/20 RPD, `gemini-2.5-flash` 6/20 RPD로 모두 여유. 즉 quota가 비어있는데도 429. **원인은 grounding tool 자체의 별도 quota bucket이었고, 이건 dashboard에 노출 안 됨.** 사용자 지적 후 grounding ON/OFF로 분리해 단발 호출 → grounding OFF 시 4개 모두 정상, grounding ON 시 3.x 계열 전부 429 → 확정.
- **방향 전환 지점**: 사용자가 "이거 이상한데 한번 검토해봐"라며 dashboard 이미지 첨부한 시점. 그 전엔 "free tier quota 소진"이라는 일반 설명에 머물러 있었음.
- **교훈 (다음에 같은 패턴이 보이면)**:
  - 첫 의심 영역: 429가 났는데 dashboard quota가 비어있으면 **도구별 hidden quota** 또는 **feature-specific quota** 의심. 모델 API quota 외에 grounding/code execution/file API 등이 별개 bucket인 경우 흔함
  - 빨리 배제할 가설: "각 모델 quota가 동시에 우연히 소진" — 4개가 0.5초 안에 다 429라는 건 모델 API quota가 아니라 **공통 의존성**(여기선 google_search grounding) 거부 신호
  - 핵심 진단 명령:
    ```python
    # 가설 검증: tool ON/OFF 분리해서 단발 호출
    for tid in CHAIN:
        for grounding in (False, True):
            try:
                r = client.models.generate_content(
                    model=tid, contents="Reply '1'.",
                    config=types.GenerateContentConfig(
                        max_output_tokens=8,
                        **({"tools":[types.Tool(google_search=types.GoogleSearch())]}
                           if grounding else {})
                    ),
                )
                print(f"{tid} grounding={grounding}: OK")
            except Exception as e:
                code = "429" if "429" in str(e) else "other"
                print(f"{tid} grounding={grounding}: {code}")
    ```
    이렇게 grid로 돌리면 hidden quota를 즉시 isolate. dashboard만 보면 안 보이는 패턴.

---

## Gemini `-p` CLI 종료 대응 — API + 모델 fallback chain 마이그레이션

- **증상**: 2026-06에 Google이 `gemini` CLI binary를 종료 예고. 그 전까지 봇 6개 경로가 `subprocess.run(["gemini", "-p", ...])` 또는 `shared.gemini_cli.call_gemini_cli`(내부적으로 subprocess)에 의존 중이라 종료 직후 다음 호출이 다음과 같이 깨짐:
  - 텔레그램 deep mode round 1부터 `FileNotFoundError` 또는 exit 127
  - 텔레그램 `/quick` 동일
  - 뉴스봇 `_gap_fill_via_cli` → 5차원 게이트가 영구 fail
  - 섹터봇 quota 초과 시 fallback이 사라져 그냥 API 실패로 종료
- **원인**: CLI는 단순 subprocess wrapper일 뿐, Google API의 직접 호출 가능 경로(`google-genai` SDK)가 이미 더 안정적. CLI를 1차 정보원으로 둔 설계가 시한부였음.
- **해결**:
  - `shared/gemini_cli.py` 완전 재작성: `call_gemini_with_fallback()` 신규 + 기존 함수명들은 backward-compat alias로 보존. 내부는 `google-genai` SDK + `types.Tool(google_search=types.GoogleSearch())` grounding + 모델 fallback chain (`gemini-3.1-flash-lite` → `gemini-3.5-flash` → `gemini-3-flash-preview` → `gemini-2.5-flash`).
  - `shared/research_orchestrator._run_gemini_round` + `telegram_gemini_bot.run_gemini` subprocess 호출 제거.
  - `news_bot/summarizer.py`, `sector_bot/searcher.py`, `sector_bot/analyzer.py`의 `_use_cli_fallback` 플래그·`_*_via_cli` 메서드 제거 → wrapper로 일원화.
  - `~/.claude/skills/research/scripts/ask_gemini.sh`도 동일 패턴으로 변환 (내부적으로 isolated venv의 `ask_gemini.py` 호출).
- **복구 절차**:
  - (a) `GEMINI_API_KEY`가 ENV 또는 `~/.gemini/api_key` 파일에 있는지 확인 (`zsh -c 'echo ${GEMINI_API_KEY:0:6}...${GEMINI_API_KEY: -4}'`)
  - (b) 운영 코드에서 subprocess 잔존 0건 검증: `grep -rnE 'subprocess\.(run|Popen)\s*\(\s*\[\s*["'\'']gemini["'\'']' 001_code/ --include="*.py"`
  - (c) `pytest 003_test_code/ --ignore=003_test_code/test_news_fetch.py` → 73 pass 확인
  - (d) 라이브 smoke: `printf '한 줄로만 답하라. 1+1?' | python -c "from shared.gemini_cli import call_gemini_with_fallback; print(call_gemini_with_fallback('1+1?', use_grounding=False).text)"`
- **관련 사고**: 2026-05-27 (예방적 마이그레이션, 6월 CLI 종료 D-30+ 시점)
- **재발 감지**: `import subprocess` + `gemini` 같은 줄에 등장하면 grep으로 즉시 검출. CI에 `! grep -rqE 'subprocess.*\bgemini\b' 001_code/ --include="*.py"` 추가 권장.

### Claude 진단 미스 (2026-05-27 세션)

**미스 #1 — 잔여 점검 범위 누락**

- **Claude 처음 가설**: 1차 grep으로 운영 코드(`001_code/`)의 `subprocess + gemini` 호출 0건을 확인하고 "마이그레이션 완료, 잔존 없음"으로 보고.
- **실제 원인**: 사용자가 "다시 한번 전체 점검 해봐"라고 요청한 뒤 광범위 grep을 돌렸을 때 (a) 테스트 코드 4개(`test_research_orchestrator.py`)가 옛 subprocess monkeypatch에 의존해 fail, (b) `test_shared_gemini_cli.py` + `test_sector_orchestrator.py`의 `_use_cli_fallback` sentinel 테스트 2개도 의미 상실, (c) `docs/ARCHITECTURE.md`·`SECTOR_BOT.md`·`NEWS_BOT.md`에 옛 CLI fallback 설명 잔존, (d) `research_orchestrator.py` 2곳의 `except (GeminiRoundError, subprocess.TimeoutExpired, FileNotFoundError)`에서 subprocess 예외가 dead 분기로 남아있음을 발견. 6 failed / 65 passed.
- **방향 전환 지점**: 사용자가 "다시한번 전체 점검 해봐"라고 명시한 시점. 1차 grep이 너무 좁았음(`001_code/` + `--include="*.py"`만 봄).
- **교훈 (다음에 같은 패턴이 보이면)**:
  - 첫 의심 영역: 마이그레이션 후 "잔존 없음" 선언 전에 **테스트 코드 + docs/ + dead except 분기**까지 grep 필수
  - 빨리 배제할 가설: "운영 코드만 깨끗하면 완료" — 회귀 테스트가 옛 가정에 묶여 있으면 CI 깨짐. 문서가 옛 동작 설명하면 신규 합류자 헷갈림
  - 핵심 진단 명령:
    ```bash
    # 운영 + 테스트 + docs 모두
    grep -rnE 'subprocess\.(run|Popen).*<old-cmd>|<old-cmd>\s+-<flag>' \
      001_code/ 003_test_code/ docs/ --include='*.py' --include='*.md' --include='*.sh'
    # 죽은 except 분기
    grep -rnE 'except\s*\([^)]*subprocess\.[A-Z]' 001_code/ --include='*.py'
    # 실제 회귀 테스트
    pytest 003_test_code/ --tb=line -q
    ```

**미스 #2 — `.zshenv` 자동 로드 사실을 설명에서 누락**

- **Claude 처음 가설**: `~/.zshenv`에 `GEMINI_API_KEY` export 추가 안내 후 "새 shell 띄우거나 `source ~/.zshenv`" 라고 단순 안내. 결과: 사용자가 ".zshenv는 내가 항상 source 해줘야해? 그렇다면 .zshrc에서 자동으로 source 해주는 것을 추가해" 라고 잘못된 가정에 도달.
- **실제 원인**: `~/.zshenv`는 zsh가 모든 invocation(interactive/non-interactive/login)에서 **자동 로드**하는 startup file. `~/.zshrc`(interactive 전용)와 명확히 구분되는데 Claude 첫 안내에 그 차이를 적지 않아 사용자가 수동 source 또는 .zshrc 추가가 필요하다고 오해.
- **방향 전환 지점**: 사용자가 .zshrc 추가 요청. Claude가 `zsh -c '...'` / `zsh -lc` / `zsh -ic` 세 모드 전부에서 auto-load 검증 후 "추가 불필요" 정정.
- **교훈 (다음에 같은 패턴이 보이면)**:
  - 첫 의심 영역: shell startup file을 추천할 때 **자동 로드 메커니즘을 한 줄로 명시**. "추가만 하면 됨, source 불필요, 모든 새 zsh가 자동 로드" 식으로
  - 빨리 배제할 가설: "사용자가 dotfile 동작을 알 것이다" — `.zshenv`는 macOS default 환경에서도 자주 모름
  - 핵심 진단 명령:
    ```bash
    # 자동 로드 검증 (3 mode)
    zsh -c  'echo ${VAR:-NOT_LOADED}'   # non-interactive
    zsh -lc 'echo ${VAR:-NOT_LOADED}'   # login
    zsh -ic 'echo ${VAR:-NOT_LOADED}'   # interactive
    ```
  - 안티패턴: `.zshrc`에 `source ~/.zshenv` 추가 권유 → 중복 실행이고 zshenv가 zshrc보다 먼저 실행되므로 의미 없음

---

## agy(Antigravity CLI) `-p` 웹서치가 subprocess에서 무한 행 / 모델 미고정

- **증상**: `agy -p` 웹서치가 터미널 직접 호출은 ~15-25s에 정상인데, 봇 코드(`subprocess.run`)에서 호출하면 응답 없이 timeout(180s+). 또 `--model` 없이 호출하면 같은 코드가 호출마다 다른 모델(Claude Sonnet ↔ Gemini Pro)로 응답.
- **원인**: (1) `agy -p`는 상속받은 stdin 파이프에서 입력을 기다리며 **블록**한다 — 봇 데몬/heredoc처럼 stdin이 EOF가 아니면 행. (2) `agy`의 default 모델은 가용성/쿼터 기반 **auto-routing**이라 비결정적. (3) `--model`에 잘못된 이름을 주면 **에러 없이 default로 조용히 라우팅**(exit 0 + 엉뚱한 응답).
- **해결**: `subprocess.run(..., stdin=subprocess.DEVNULL)`로 즉시 EOF 부여(필수). `--model`로 모델 명시 고정(캐스케이드 `shared/web_search.py`). 바이너리는 `_agy_bin()`이 `AGY_BIN`→`which agy`→`~/.local/bin/agy` 순 해석, 부재 시 `OSError→AgySearchError`로 묶어 Claude fallback.
- **복구 절차**: (a) 웹서치 응답 지연/공백이면 `agy_search.py`의 `stdin=DEVNULL` 존재 확인 (b) 봇 PATH에 `~/.local/bin` 있는지 / `AGY_BIN` 설정 (c) `AGY_BIN=/nonexistent`로 강제하면 Claude fallback이 도는지 점검.
- **관련 사고**: 2026-06-07 (agy 웹서치 마이그레이션, [[agy-websearch-migration]])
- **재발 감지**: 텔레그램/뉴스/섹터 웹서치 응답이 갑자기 전부 Claude fallback 모델(`model_used`에 `agy:` prefix 없음)로 바뀌면 agy 호출이 전부 실패 중 — 로그 `grep "agy model .* failed"`.

### Claude 진단 미스

- **Claude 처음 가설**: CLI에서 `agy -p "..."`가 ~24s에 깔끔히 동작하는 것을 보고, 같은 명령을 `subprocess.run([...argv...])`로 옮기면 그대로 동작할 것이라 가정(설계 단계에서 "출력 깔끔, ~24s"로 단정).
- **실제 원인**: 첫 라이브 subprocess 테스트가 180s 타임아웃. CLI(대화형 셸)와 subprocess(상속 stdin 파이프)의 stdin 컨텍스트 차이 때문. `stdin=DEVNULL` 부여로 즉시 해결. (사용자 corrective 아님 — 라이브 테스트가 잡음.)
- **방향 전환 지점**: 라이브 스모크 [A] 타임아웃 직후, CLI vs subprocess / 단일행 vs 멀티행 / stdin 변수를 분리 실측해 stdin이 원인임을 확정.
- **교훈 (다음에 같은 패턴이면)**:
  - 첫 의심 영역: 에이전트 CLI를 subprocess로 부를 때 행하면 **stdin 처리부터** 본다(`stdin=subprocess.DEVNULL`). **CLI 테스트 통과 ≠ subprocess 동작.**
  - 빨리 배제할 가설: "프롬프트 멀티라인/argv 길이 문제" — 실측상 멀티라인은 무관, stdin이 범인.
  - 핵심 진단 명령: `python -c "import subprocess as s; print(s.run(['agy','-p','test','--dangerously-skip-permissions'], stdin=s.DEVNULL, timeout=60, capture_output=True, text=True).returncode)"`

---

## 인라인 SVG 플로우차트 화살표가 박스에 안 닿음 / 다이어그램 깨짐

- **증상**: 봇이 만든 글의 의사결정 흐름 다이어그램에서 다이아몬드 옆구리에서 출발한 YES/NO 화살표가 결과 박스에 *연결되지 않고 허공에서 끝남*. 결과 박스가 SVG 영역 밖 별도 div로 빠지면서 시각적으로 어긋남.
- **원인**: SKILL.md 8번/9번 가이드가 "인라인 SVG로 노드+화살표 직접 좌표 계산"이었음. Claude가 매 호출마다 좌표를 재계산하면서 다음 3가지 실수 누적:
  - (A) 다이아몬드·화살표는 SVG, 결과 박스는 외부 HTML div로 *좌표계 분리* → 가장 빈번
  - (B) viewBox 고정인데 라벨 텍스트 길이 가변 → 시작점/끝점 어긋남
  - (C) 분기 ≥3이면 전체 레이아웃 재계산 필요한데 일부만 손봄
- **해결**: SKILL.md를 **Mermaid 코드블록 우선**으로 패치 (`flowchart TD` / `graph LR`). Blogger 테마와 Tistory 스킨에 Mermaid.js v11 글로벌 등록. 본문은 `<pre><code class="language-mermaid">` 양식만 작성 → JS가 자동 렌더. SVG 좌표 계산 0줄.
- **복구 절차**:
  - (a) `~/.claude/skills/blogger-html/SKILL.md` 8번/9번 섹션이 Mermaid 우선인지 확인
  - (b) Blogger 테마 → HTML 편집 → `</body>` 위 Mermaid CDN 스크립트 존재 확인 (`useMaxWidth` 또는 `import mermaid` 검색)
  - (c) Tistory: 꾸미기 → 스킨 편집 → html 편집 → 동일 확인
  - (d) 다음 봇 자동 실행 결과에서 `language-mermaid` 코드블록이 다이어그램으로 렌더링되는지
- **관련 사고**: 2026-05-17 (사용자 보고: 석회성건염 의사결정 다이어그램 — 화살표 박스 미연결), 2026-05-18 (검증 발행 4회로 Mermaid 도입 작동 확인)
- **재발 감지**: 발행물 raw HTML에서 `language-mermaid` 카운트 0이고 `<polygon`/`<line` 다수면 SVG 좌표 노가다로 회귀한 것. SKILL.md의 "Mermaid 코드블록을 우선 사용" 문구가 8번/9번 가이드에 남아있는지 확인.

### Claude 진단 미스 (2026-05-17 세션)

- **Claude 처음 가설 (도구 분석)**: 발행물의 다이어그램 상태를 *WebFetch* 도구로 확인 → "SVG 0개, Mermaid 스크립트 없음, border-left 카드 없음"이라는 잘못된 보고. 봇이 만든 시각화 자체가 빈약하다고 판단할 뻔함.
- **실제 원인**: WebFetch는 HTML→markdown 변환을 거치면서 인라인 `<svg>`, `<script>`, 인라인 style div를 모두 소실시킴. raw HTML 자체에는 SVG 27개·카드 24개가 멀쩡히 들어있었음.
- **방향 전환 지점**: 봇 출력 HTML 길이(50,000자+)와 WebFetch 결과(시각화 0)의 모순을 인지 → `curl -sL`로 raw HTML 직접 확인 후 정확한 카운트 확보.
- **교훈 (다음에 같은 패턴이 보이면)**:
  - 첫 의심 영역: **Blogger·Tistory 발행물 분석에는 WebFetch 사용 금지**. raw HTML이 필요한 모든 검증은 `curl -sL -A "Mozilla/5.0" "$URL"` 로 가져온 뒤 `grep`/`python3 -c "import re"`로 추출
  - 빨리 배제할 가설: "봇 출력이 변경됐다" — WebFetch에서 시각화가 0개로 보여도 *도구 한계*일 가능성이 90%. 봇 코드 변경 없이 출력만 빈약해지는 일은 드뭄
  - 핵심 진단 명령:
    ```bash
    curl -sL -A "Mozilla/5.0" "$URL" | grep -ciE "language-mermaid|<svg|border-left"
    ```

---

## Gemini 429 (서버 용량 부족)

- **증상**: Gemini API가 `429 ResourceExhausted` 또는 "서버 용량 부족" 메시지 반환. 라운드/요약 도중 일부 호출만 실패.
- **원인**: Google 서버 일시적 과부하 또는 quota 초과 (Code Assist tier 일일 한도).
- **해결**: 자동 재시도 (지수 백오프 3회). 누적 결과로 fallback 요약 메시지 자동 전송.
- **복구 절차**: 자동 복구. 429가 1시간 이상 지속 시 → quota 초과 가능성, Google AI Studio 콘솔에서 잔여량 확인.
- **관련 사고**: 2026-03-13 (gemini-free-tier-quota), 2026-04-04 (gemini-empty-response), 2026-04-20 (gemini-503-cli-fallback)
- **재발 감지**: `logs/*_$(date +%Y%m%d).log`에서 `429`/`503`/`empty response` 빈도. 일일 5회 이상이면 quota 한계 의심.

---

## Claude CLI empty response

- **증상**: Claude CLI 호출이 성공 코드(0) 반환하지만 stdout 비어 있음. 분석 결과 누락.
- **원인**: Claude API 일시 장애 또는 CLI 내부 timeout.
- **해결**: 자동 재시도 (3회, 30초 간격). 모두 실패 시 fallback synthesis로 진행 (raw rounds concatenation).
- **복구 절차**: 자동. 수동 검증은 `claude --version` 후 단순 호출 (`echo hi | claude -p "echo back"`).
- **관련 사고**: 2026-03-26 (claude-cli-empty-retry), 2026-04-04
- **재발 감지**: `Claude CLI returned empty` 로그 빈도. 일일 0~1건이 정상.

### Claude 진단 미스 (이전 세션에서 있었음)
- **Claude 처음 가설**: CLI 인스톨 문제 또는 PATH 미설정
- **실제 원인**: Anthropic API 측 일시 장애. CLI 자체는 정상.
- **방향 전환 지점**: 같은 명령을 30초 후 재실행하면 성공 — 인스톨 문제 아님 인식
- **교훈**:
  - 첫 의심 영역: **재시도 시 응답 변화 여부**
  - 빨리 배제할 가설: "CLI 설치 문제" — 한번이라도 정상 응답 받았으면 인스톨은 OK
  - 핵심 진단 명령: `echo "test" | claude -p "echo"` 로 minimal call 검증

---

## Blogger OAuth 인증 실패 (보존 — 2026-06-12 WordPress 전환으로 폐지)

> 2026-06-12부터 전 봇이 WordPress(grace-moon.com) 발행으로 전환되어 Blogger 발행은 사용하지 않는다(`shared/blogger_uploader.py` 삭제됨). 아래는 이력 보존. 현행 발행 이슈는 "WordPress(grace-moon.com) 발행물…" 항목 참조.

- **증상**: Blogger 업로드 시 `invalid_grant` 또는 토큰 만료 에러.
- **원인**: 저장된 OAuth refresh token이 무효화됨 (장기간 미사용 또는 사용자가 권한 회수).
- **해결**: `credentials/blogger_token.pkl` 삭제 후 다음 실행 시 OAuth 플로우 재진행.
- **복구 절차**:
  ```bash
  rm credentials/blogger_token.pkl
  python news_bot/blogger_uploader.py --auth   # 또는 통합 봇 실행 시 자동 재인증
  ```
- **관련 사고**: 정기적 (refresh token 만료, 분기 단위)
- **재발 감지**: `invalid_grant` 로그 발생 즉시 알림.

---

## WordPress(grace-moon.com) 발행물·소유권 검증이 옛 페이지로 남음 (Cafe24 캐시)

- **증상**: WordPress 설정/메타태그를 바꿔 발행·재검증했는데도 페이지 소스가 **옛 값**을 계속 내보냄. 구글/네이버 서치콘솔 메타태그 소유확인이 "메타태그가 잘못됨"으로 반복 실패.
- **원인**: Cafe24(openresty) **엣지 캐시 + WP Super Cache**가 홈페이지 정적 스냅샷을 물고 있어, 클라이언트 `no-cache`·쿼리스트링 우회·관리바 "캐시 삭제"로도 갱신 안 됨. (구글 인증 `<meta>`는 Rank Math가 **홈페이지에만** 출력 → 홈 캐시가 박제되면 영영 옛 값.)
- **해결**:
  - 소유권 검증은 캐시를 안 타는 **DNS TXT(도메인 속성)** 또는 **HTML 파일 업로드**로 우회. 메타태그 방식은 이 스택에서 불안정.
  - Rank Math 사이트맵이 갑자기 404면 **설정→고유주소→저장**(rewrite flush). WP Super Cache 토글 직후 흔함.
  - 봇 발행물이 스테일하게 보일 때도 동일 원인 — WP Super Cache 캐시 삭제.
- **복구 절차**: (a) WP Super Cache 캐싱 끄기+삭제 (b) 그래도 옛 값이면 엣지 캐시로 판단→DNS/파일 방식 전환 (c) 사이트맵 404면 퍼머링크 재저장.
- **관련 사고**: 2026-06-12 (블로그 WordPress 이관 + 서치콘솔 등록)
- **재발 감지**: 발행/설정 변경 직후 `curl -s -L "https://grace-moon.com/?cb=$RANDOM"`로 라이브 값이 바뀌는지 확인. 안 바뀌면 캐시 의심.

### Claude 진단 미스 (2026-06-12 세션, 서치콘솔 메타태그 소유확인)

- **Claude 처음 가설**: ①속성 유형이 "도메인"이라 메타태그 무시 → ②GSC 코드값 불일치 → ③WP Super Cache stale, 순으로 추정.
- **실제 원인**: ①②는 아니었고(URL 접두어 맞고 값도 일치), WP Super Cache를 꺼도 안 바뀐 것으로 보아 **Cafe24 openresty 엣지 캐시**가 홈 스냅샷을 유지. 메타태그 방식 자체가 이 호스트에서 비현실적이었음.
- **방향 전환 지점**: 캐싱 끈 뒤에도 `curl` 라이브 값이 옛 값이고, 404 페이지엔 태그가 아예 없던(=홈에만 출력) 것을 확인한 순간 → "메타태그 우회, DNS로" 결정.
- **교훈 (다음에 같은 패턴이 보이면)**:
  - 첫 의심 영역: **호스트/엣지 캐시**부터 본다(`curl ...?cb=$RANDOM` 라이브 비교). WordPress 플러그인 설정보다 위 계층.
  - 빨리 배제할 가설: "플러그인에 값을 잘못 넣었다"는 보통 원인 아님 — `curl`로 태그가 살아있으면 입력은 정상.
  - 핵심 진단 명령: <kbd>curl -s -L "https://grace-moon.com/?cb=$RANDOM" | grep -i site-verification</kbd> / <kbd>dig +short TXT &lt;domain&gt; @8.8.8.8</kbd>
  - 검증 방법 우선순위: **DNS TXT > HTML 파일 > 메타태그**(캐시 무관 순).

---

## Telegram HTML parse error

- **증상**: Telegram 메시지가 도착 안 함 또는 plain text로만 도착.
- **원인**: 메시지 본문에 `<`, `>` 같은 HTML 메타 문자가 escape 안 됨, 또는 닫히지 않은 `<b>` 태그.
- **해결**: HTML parse 에러 감지 시 plain text fallback으로 자동 재전송.
- **복구 절차**: 자동. 수동 검증은 `python -c "from shared.telegram_bot import send_text; send_text('test &<>')"`.
- **관련 사고**: 2026-03-20 (telegram-underscore-escape), 2025-12-20 (telegram-html-parsing-error)
- **재발 감지**: `Telegram HTML parse error` 로그 빈도. 일일 0건이 정상.

---

## Sector Weekly Summary가 N-1/N 으로 나감 (스케줄 충돌)

- **증상**: 일요일 텔레그램 Weekly Summary가 `10/11` 등 마지막 섹터 1개 빠진 상태로 도착. 직후 마지막 섹터가 정상 업로드됨.
- **원인**: `investment_bot.py`의 Weekly Summary 시각이 마지막 섹터 시작 시각보다 **앞**에 등록돼 있었음. `config.py`의 sector 11(필수 소비재) `scheduled_time="18:40"` vs 통합 봇의 Weekly Summary `18:30` → summary가 sector 11 시작 전에 트리거. (단독 실행 모드 `weekly_sector_bot.py:263`은 `19:20`으로 올바름.)
- **해결**: `investment_bot.py:127`의 Weekly Summary `18:30 → 19:20`, `:132`의 Comprehensive Report `19:00 → 19:40`. 단독 실행·문서·통합 모드 3자 일치.
- **복구 절차**: 코드 수정 후 다음 일요일까지 대기 (당일 데이터는 sector 파일 모두 정상이므로 `python weekly_sector_bot.py --comprehensive`로 수동 재생성 가능).
- **관련 사고**: 2026-05-10
- **재발 감지**: `[WeeklySummary] Triggered` 로그 시각이 마지막 섹터 `Completed` 시각보다 앞이면 alert. `tail logs/investment_bot_*.log | grep -E "Sector-11.*Completed|WeeklySummary] Triggered"`로 순서 확인.

---

## Comprehensive Report 업로드 Broken pipe

- **증상**: 종합 투자 평가 보고서 단계에서 `Upload failed: [Errno 32] Broken pipe`. 텔레그램으로 ❌ 실패 메시지 도착. 섹터 파일과 종합 MD/HTML은 정상 생성됨.
- **원인**: 마지막 섹터 업로드 이후 30분 이상 idle 후 cached `service.posts().insert()`를 그대로 호출. 그 사이 HTTP/2 keep-alive 또는 SSL 세션이 서버 측에서 종료된 상태에서 종합 HTML(타 섹터의 4-5배, ~118KB)을 한 번에 송신 → 첫 패킷 직후 broken pipe. `is_authenticated()`는 토큰 유효성만 검사하고 실제 connection은 검증하지 않음.
- **해결**: `shared/blogger_uploader.py`에 `_insert_with_retry()` 추가. `BrokenPipeError`/`ConnectionResetError`/`ConnectionError`/`RemoteDisconnected`/`SSLError`/`socket.error` 발생 시 `self.service = None` 후 `authenticate()` 재호출하고 1회 재시도. 모든 호출자(섹터/뉴스/버핏/종합) 적용.
- **복구 절차**: 일시적 실패면 자동 재시도로 복구. 재시도도 실패하면 sector 파일이 모두 살아있는지 확인 후 `python weekly_sector_bot.py --comprehensive`로 수동 재생성.
- **관련 사고**: 2026-05-10
- **재발 감지**: `Connection lost` WARNING 로그 (재시도 발생 신호). 동일 세션에 2회 이상이면 네트워크 또는 Blogger 서버 이슈 의심.

---

## Sector bot resume 실패

- **증상**: `weekly_sector_bot.py --once` 실행 시 "다른 주에 시작" 메시지로 거부.
- **원인**: `state.json`이 이전 주에 시작된 상태 보존. 일요일이 아닌 시점에 `--once` 호출 시 state 충돌.
- **해결**: `--reset` 후 `--once` 실행.
- **복구 절차**:
  ```bash
  python weekly_sector_bot.py --reset
  python weekly_sector_bot.py --once
  ```
- **관련 사고**: 정기적 (수동 호출 시 빈번)
- **재발 감지**: `state mismatch` 로그.

---

## Sector state 손상

- **증상**: 섹터 봇 시작 시 JSON parse error 또는 비정상 상태.
- **원인**: `state.json`이 비정상 종료(SIGKILL, 디스크 full)로 손상.
- **해결**: state 파일 reset.
- **복구 절차**: `python weekly_sector_bot.py --reset` 후 다음 일요일 13:00 자동 실행 또는 즉시 `--once`.
- **관련 사고**: 드뭄
- **재발 감지**: 시작 시 JSON parse error 즉시 alert.

---

## Blog selection timeout

- **증상**: 사용자에게 블로그 선택 prompt 보냈는데 응답 없음 → 봇이 timeout 후 default blog 사용.
- **원인**: `BLOG_SELECTION_TIMEOUT`(기본 180초) 내 응답 없음. 정상 동작이지만 default blog가 의도와 다를 수 있음.
- **해결**: `.env`에서 `BLOG_SELECTION_TIMEOUT` 값 조정 또는 `DEFAULT_BLOG`를 가장 자주 쓰는 블로그로 설정.
- **복구 절차**: 잘못 업로드된 블로그에서 글 삭제 후 정확한 블로그에 재업로드.
- **관련 사고**: 사용자 운영 패턴
- **재발 감지**: 일일 default blog 사용 비율 추적.

---

## ModuleNotFoundError

- **증상**: 봇 시작 시 import 에러.
- **원인**: venv 미활성화 또는 dependency 누락.
- **해결**:
  ```bash
  cd 006_auto_bot/001_code
  source .venv/bin/activate
  pip install -r requirements.txt
  ```
- **복구 절차**: venv 재생성 필요 시 `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.
- **관련 사고**: 환경 설정
- **재발 감지**: 시작 직후 ImportError → 즉시 fail-fast.

---

## 발행 글 본문에 `-->` 텍스트 노출 + 빈 공간 (이미지 마커 주석 중첩)

- **증상**: 발행된 글 본문 중간에 `-->`(화면상 `->`처럼 보임) 텍스트가 노출되고 그 주변에 빈 공간이 생김. (2026-06-14 미스트랄·LLM 토큰 글 id 159·92에서 발견)
- **원인**: `[[IMAGE: ...]]` 마커를 Claude HTML 변환이 안전하게 HTML 주석으로 감싸 `<!-- [[IMAGE: ...]] -->`로 출력한 경우, `_maybe_inject_images` strip 모드가 안쪽 `[[IMAGE:...]]`만 `<!-- image marker stripped ... -->`로 치환 → 주석이 **중첩**(`<!-- <!-- ... --> -->`). HTML은 주석 중첩을 허용하지 않아 브라우저가 첫 `-->`에서 주석을 닫고 남은 ` -->`를 본문 텍스트로 렌더. 빈 공간은 이미지가 들어갈 자리(`BLOGGER_IMAGES_ENABLED=false`라 마커만 제거된 상태).
- **해결**: `shared/claude_html_converter.py` `_maybe_inject_images`가 strip/inject 전에 마커를 감싼 주석 래퍼(`<!-- [[IMAGE:...]] -->`)를 먼저 벗기도록 정규화 추가 → 중첩 불가. 회귀 테스트 `tests/test_image_marker_strip.py`(중첩 방지/bare 마커/무마커).
- **복구 절차**: (a) WP REST `context=edit` raw에서 `<!--\s*<!--.*?-->\s*-->` 패턴으로 영향 글 식별 (b) 해당 패턴 제거 후 `content` 업데이트 (c) Cafe24 캐시로 화면 반영 지연 가능 → 캐시 만료 대기.
- **관련 사고**: 2026-06-14.
- **재발 감지**: 발행 후 raw에서 `'<!-- <!--'` 또는 `-->` 중복(`-->\s*-->`)·`[[IMAGE` 잔존이 0인지 확인. ⚠️ 진단 팁: HTML에서 리터럴 `->`/`-->`를 찾을 땐 정규식 `-\s*>`가 태그 내부 `>`를 오인하므로 **literal substring 검색**(`raw.count('-->')`)부터 쓸 것.

---

## 로그 파일 위치

```
logs/
├── investment_bot_YYYYMMDD.log  # 통합 오케스트레이터
├── news_bot_YYYYMMDD.log        # 뉴스봇
├── buffett_bot_YYYYMMDD.log     # 버핏봇
└── sector_bot_YYYYMMDD.log      # 섹터봇
```
