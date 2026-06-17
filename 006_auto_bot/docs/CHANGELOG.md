# 006_auto_bot 변경 이력

날짜순 (최신 위).

---

## 2026-06-17: [fix] WaveDrom 파형 의미론 오류(래치가 D 미추종) + 자기일관성 가드

- **증상**: `flip-flop-vs-latch-chip-design-control`(post 254) 글에서 Latch 파형이 **본문 설명과 모순** — 글은 "레벨 민감 래치는 CLK High 동안 D를 즉시 따라가 글리치까지 새어 나간다"고 하는데, 파형의 Latch는 D의 중간 dip을 무시한 채 High 유지.
- **원인**: 렌더/정규화 버그가 **아님**. AI가 만든 **wave 소스 자체가 의미론적으로 틀림**(Latch wave에 dip이 없음). `_collapse_wave`는 같은 레벨일 때만 `.`로 접어 **전이를 절대 못 지움**(transition-preserving)을 증명 → 파이프라인 무관, AI 콘텐츠 오류로 분류.
- **해결(이 글)**: 올바른 wave 소스(래치=투과+글리치 통과+CLK Low hold, FF=엣지 샘플) 작성→`render_kroki_png`로 재렌더→`upload_media`→post 254 content.raw의 이미지 URL 2곳(썸네일+라이트박스) 교체 PATCH. 라이브 반영.
- **후속 정정 2회(레벨 민감성)**: ①1차본: D 하강이 **CLK Low**라 래치가 다음 엣지까지 hold→엣지 falling=FF처럼 보임(사용자 지적). ②2차본: hold 시연용 **CLK Low 펄스를 래치가 막는** 구간을 넣었더니 "D는 dip인데 Latch는 flat"이 **래치가 D를 안 따라가는 오류처럼** 보임(재지적: "D와 Latch 코드가 같아야 하는 거 아냐?"). **최종본**: 모든 D 전이를 **CLK High 윈도우 안**에만 배치 → 래치가 D를 항상 즉시 추종 → **Latch wave ≡ D wave**(rise·glitch·fall 동일), 유일한 차이는 FF(엣지 샘플·글리치 무시). hold는 본문 텍스트로만 설명(파형엔 비노출). ⭐교훈: 레벨 민감 래치의 **비투과 동작(hold·엣지 catch-up)은 파형에서 거의 항상 오해를 부른다** → 교육용 파형은 D를 CLK High에서만 바꿔 **Latch≡D(투과)**로 그리고 FF와의 대비에만 집중, hold는 글로 설명.
- **SystemVerilog 샘플 검증(non-blocking in always_latch)**: 의도적 래치의 `latch_q <= d;`(non-blocking) 정당성 확인 — `iverilog -g2012` 컴파일 OK + 표준 가이드라인(래치=레벨 민감 **순차** 소자라 FF처럼 non-blocking; 조합 `always_comb`만 blocking). 샘플은 always_ff `<=`·always_comb `=`·always_latch `<=`로 **일관**. 코드를 바꾸지 않고 **설명 주석**을 추가(왜 non-blocking인지 + 시뮬레이션 race/sim-synth 불일치 방지).
- **해결(재발 방지)**: 의미론 정확성은 코드로 강제 불가 → **프롬프트 레버**로 방어. `shared/research_orchestrator.py` `_SYNTH_PROMPT_TEMPLATE` + 글로벌 스킬 `telegram-qa`/`blogger-html`에 **파형 자기일관성 가드** 추가(래치 투과/hold·FF 엣지·글-그림 모순 금지·`0000`→`.`).
- **교훈**: "다이어그램이 이상하다" = ① 렌더 버그(전부 raw·톱니 → 결정론적 코드 수정) vs ② AI 의미론 오류(이미지는 멀쩡, 뜻만 틀림 → 프롬프트만). 그림이 렌더는 됐는데 뜻만 틀리면 소스 데이터(AI 출력)부터 본다. → [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

## 2026-06-17: [fix] 미리보기에 CSS 누수 + 코드 블록 미화(다크 카드)

- **[fix] 메인 미리보기/메타설명에 `.gm-lb{display:none…}` CSS가 노출**: 라이트박스/코드 보정용으로 본문 맨 앞에 주입한 `<style>` 블록을, `auto_excerpt`가 태그만 벗기고 **CSS 텍스트는 남겨** 발췌로 써버림(Rank Math meta description도 오염). `auto_excerpt`가 이제 `<style>·<script>·<pre>` 블록을 **내용째 제거**한 뒤 발췌 생성. 누수된 기존 글 4건(254/238/229/249) 발췌 재설정+PATCH.
- **코드 블록 미화(`beautify_code_blocks`)**: AI가 코드/수식을 bare `<pre><code>` 또는 `<pre style="…dark…">`로 비일관 출력 → (다이어그램 변환 후) 남은 모든 `<pre><code>`를 **일관된 다크 카드 `.gm-code-box`**(언어 라벨 헤더 + 둥근 모서리 + 그림자 + 라이트-온-슬레이트 monospace)로 결정론적 재작성. 인라인 스타일 제거 후 주입 CSS가 모양 통제(글마다 동일). `_LANG_LABEL`로 `systemverilog→SystemVerilog` 등 라벨 prettify. inline `!important` 다크 박스도 카드로 흡수(대비 문제 해소). `create_post`에 배선(`fix_styled_code_contrast`는 잔여 안전망). 라이브 검증(SystemVerilog 카드 렌더). 신규 테스트 +9 (157 통과).

## 2026-06-17: [fix] 다이어그램 전부 코드로 발행되던 버그(<pre style>) + 클릭 확대(라이트박스)

- **증상**: 글의 d2·wavedrom·**mermaid까지 전부** 이미지가 아니라 원본 코드블록으로 발행됨(이전엔 mermaid는 됐었음).
- **원인**: `_RE_DIAGRAM_BLOCK`이 **bare `<pre>`만** 매칭했는데, AI HTML 변환기가 `<pre style="background-color:…">`처럼 **속성을 붙여** 출력하는 경우가 있어(비결정적) 전혀 매칭되지 않음 → 모든 다이어그램 미렌더. mermaid가 됐던 글은 우연히 bare `<pre>`였을 뿐.
- **해결**: 정규식 `<pre>` → `<pre[^>]*>`로 속성 허용. 회귀 테스트 추가(styled-pre 매칭).
- **클릭 확대(라이트박스)**: 다이어그램 이미지가 본문 폭에 맞춰 작게 보이는 문제 → 각 이미지를 **순수 CSS `:target` 라이트박스**로 감쌈(썸네일 클릭=풀스크린 원본, 오버레이 클릭=닫기). **JS 없음(WAF 안전)**, `<style data-gm-lightbox>` 1회 주입(글당). WordPress `unfiltered_html`로 `<style>` 보존 확인(드래프트 프로브 + 라이브 브라우저 `:target` 동작 검증). 기존 글(post 238) 재렌더+PATCH 완료. 신규 테스트 +2 (148 통과).
- **[fix] 다크 코드박스(수식 등) light-on-light로 안 보임**: AI가 `<pre style="background:#2c3e50"><code style="color:#ecf0f1">`로 수식을 넣으면, 테마의 `code{background:연한색}`가 안쪽 `<code>`에 적용돼 **밝은 글자가 밝은 배경에 묻혀** 빈 박스처럼 보임(라이브 computed style로 확인: codeBg `rgb(236,239,243)`). `create_post`가 `fix_styled_code_contrast`로 **`pre[style*="background"] code{background:transparent!important;color:inherit!important}`** 스코프 `<style>`를 1회 주입 → `<pre`의 의도된 배경이 보이게(일반 코드블록 무관). 라이브 재로딩+스크린샷으로 가독 확인. post 238 PATCH 완료. 신규 테스트 +4 (152 통과).

## 2026-06-16: [fix] WaveDrom 톱니(notch) 제거 — wave 리터럴 반복 정규화

- **증상**: wavedrom 파형이 유지 구간에서도 매 주기 작은 `∨` 톱니가 계속 보임(클럭/신호가 깨진 것처럼).
- **원인**: AI가 wave를 `"00110011"`처럼 **같은 레벨을 리터럴로 반복**해 생성 → WaveDrom이 같은 값 반복 경계마다 재샘플 글리치(notch)를 그림. `.`(이전 상태 유지)로 쓰면 깔끔.
- **해결**: 업로더 단일 choke point(`render_kroki_png`, wavedrom일 때)에서 **결정론적 정규화** — `_normalize_wavedrom`/`_collapse_wave`가 `"wave"` 문자열의 인접 동일 **레벨 기호 `{0,1,x,z}`만 `.`로 접음**. AI 준수에 의존하지 않음(출처 누락 때와 같은 비결정성 회피). ⚠️ 클럭(`p/n/P/N/h/l/H/L`)·버스 데이터(`=`,`2~9`; `data[]` 인덱스 결합)·gap(`|`)은 반복에 의미가 있어 **건드리지 않음**. 의도된 1주기 글리치(`101`)는 인접 비동일이라 **보존**. 신규 테스트 5 (146 통과). 기존 글(post 229) wavedrom 2개도 재렌더해 교체.

## 2026-06-16: [fix] d2/wavedrom가 이미지로 안 바뀌던 버그 — kroki svg-only → 로컬 래스터화

- **증상**: 텔레그램봇 발행 글(`clock-switching-pitfalls-glitch-free-mux`)에서 d2 아키텍처·wavedrom 타이밍 블록이 PNG가 아니라 `<pre><code class="language-d2/wavedrom">` 원본 코드 그대로 노출. mermaid는 정상 렌더.
- **원인**: kroki는 **d2·wavedrom(및 nomnoml/pikchr/svgbob/vega 등)에 PNG 출력을 지원하지 않고 SVG만 제공**(`/d2/png` → HTTP 400 "Unsupported output format: png for d2. Must be one of svg"). 기존 `render_kroki_png`는 `/{type}/png`만 호출하고 PNG 매직바이트를 요구해 None 반환 → `_render_diagrams_in_html`이 원본 블록 유지. (인라인 SVG는 WordPress wpautop/sanitize가 깨뜨리므로 SVG 직삽도 불가.)
- **해결**: `render_kroki_png`을 포맷 인지형으로 — png 네이티브 타입은 `/png`, **svg-only 타입(`_KROKI_SVG_ONLY`)은 `/svg`를 받아 headless Chrome(`_svg_to_png`, `CHROME_BIN` override)으로 PNG 래스터화** 후 mermaid와 동일하게 미디어 업로드. png 네이티브가 예외적으로 png 거부 시에도 svg fallback. **Chrome은 이미 설치돼 있어 추가 설치·비용 0**, 한글 라벨도 정상 렌더(라이브 d2+wavedrom 검증). Chrome 부재 시 조용히 None(원본 블록 유지). 신규 테스트 5 (141 통과).

## 2026-06-16: kroki 다중 타입 다이어그램 + 텔레그램 리서치 전제 가드

- **kroki 다이어그램 다중 타입 지원** — 기존 mermaid 전용 렌더를 일반화. `render_mermaid_png` → `render_kroki_png(code, diagram_type)`(언어→kroki 경로 매핑 `_LANG_TO_KROKI`, `dot→graphviz`·`vega-lite→vegalite` 별칭), `_render_diagrams_in_html`이 `language-mermaid`만이 아니라 **지원 다이어그램 펜스 전부**(d2/wavedrom/graphviz/plantuml/blockdiag/nomnoml/erd/pikchr/svgbob 등)를 PNG로 렌더. ⚠️ **일반 코드 블록(python/c/verilog/bash)은 변환 안 함**(다이어그램 언어만 매핑). `render_mermaid_png`은 하위호환 래퍼 유지. 파일명 해시에 타입 포함. SoC/AI 기술 글용: 중첩 아키텍처=d2, 신호/클럭 타이밍=wavedrom. 신규 테스트 6 (140 통과). `blogger-html` SKILL에 d2/wavedrom 등 펜스 안내 추가(글로벌). (commit `68ea391`)
- **텔레그램 리서치 '전제 가드'** — 질문의 부정확한 전제·가정·수치가 발행 글에 사실로 섞여 "AI가 쓴 느낌"을 주던 문제. 누수 지점은 HTML 변환이 **아니라**(변환기는 MD만 받음) **research/합성 단계**(질문 verbatim 임베드 + answer-framing). deep `_SYNTH_PROMPT_TEMPLATE` + quick 프롬프트 + `telegram-qa` SKILL(글로벌) 3곳에 가드: 질문=주제/의도로만, 전제 미확인 시 교정("질문의 전제와 달리…"), 독자는 질문을 못 보므로 독립·자기완결 기사로 작성(인용·되묻기 금지).
- **기술 다이어그램 nudge** — 합성/QA에 "기술 주제(아키텍처·프로토콜·SoC·반도체)면 **본문에 근거가 있는 경우에 한해** 구조=d2·타이밍=wavedrom·흐름=mermaid 펜스를 직접 포함, **지어낸 다이어그램 금지**(특히 wavedrom은 출처에 신호 동작 명시 시에만)" 추가. (commit `e6dc7cf`)

---

## 2026-06-15: 출처 외부 링크 섹션 + 타이틀 카드 대표 이미지 (SEO·AdSense)

- **출처→'참고 자료' 외부 링크 섹션 (근본 수정)** — Rank Math "outbound links" 경고 + E-E-A-T + AdSense 가치. 봇이 이미 보유한 출처(`{title,url}`)를 발행 단계에서 **결정론적으로** 본문 끝에 클릭 가능한 링크로 렌더. `shared/wordpress_uploader.render_sources_section()` 신설(새 탭·**dofollow** `rel="noopener"`·중복 URL 제거·http(s)만·이스케이프·최대 12개), `create_post`/`upload_post`에 `sources` 인자 추가(단일 choke point, 이미 섹션 있으면 중복 안 붙임).
  - 배선: **텔레그램**(기존 마크다운 `## References`는 AI 변환에서 비결정적으로 누락 → 제거하고 업로더로 결정론적 첨부), **섹터**(`orch.sources`), **부동산**(국토부 실거래가 공개시스템 링크 상수). 뉴스(100+ 피드 종합=노이즈)·버핏(구조화 출처 없음)은 제외.
- **타이틀 카드 대표 이미지(featured/og:image) 자동 첨부** — `shared/title_card.py` 신설: 제목·카테고리→1200×630 다크 카드 PNG(Pillow + 시스템 한글 폰트, **비용0·무네트워크·결정론적**, 폰트/렌더 실패 시 None→발행 계속). `create_post`가 `featured_media` 미지정 + `AUTO_FEATURED_CARD=true`면 카드 생성→`upload_media`→대표 이미지로 설정(카테고리 ID→이름 역매핑으로 칩 라벨·색상). og:image(SNS·검색 미리보기)+글목록 썸네일 브랜딩 확보. **PNG 미디어 업로드는 NinjaFirewall을 그대로 통과**(mermaid 파이프라인과 동일, 본문 미전송이라 WAF 무관).
- 단위 변환기 글(id 180)에 실제 도구 스크린샷을 대표 이미지로 설정(헤드리스 Chrome 1200×630 캡처→media id 199, `featured_media`만 PATCH=본문 미전송→방화벽 무관, status publish 유지).
- 검토 결정: Rank Math **포커스 키워드 자동화는 보류**(구글 랭킹 신호 아님=cosmetic, 기계 추출 키워드는 거짓 안심). 무료 AI 이미지(Higgsfield 등)는 무료 한도가 봇 자동발행에 무의미해 채택 안 함.
- 테스트: `tests/test_wordpress_helpers.py`에 sources(7건)+title card(6건) 추가 → 전체 134건 통과.

## 2026-06-14: 자동봇 강제 draft 토글 + 이미지 마커 주석 중첩 버그 수정

- **`AUTO_BOT_DRAFT_ONLY`(default true) 추가** — 애드센스 심사 준비 동안 investment_bot 계열 자동봇(뉴스/버핏/섹터/부동산)이 발행하는 글을 항상 draft로 올린다. `shared/wordpress_uploader.py`에 `force_draft` 옵션 + `auto_draft_enabled()` 헬퍼 추가(`create_post` 단일 choke point에서 status→draft 강제). 자동봇 4종(`buffett_bot`·`weekly_sector_bot`·`weekly_realestate_bot`·`main` 뉴스 3곳)이 `force_draft=auto_draft_enabled()` 연결. **텔레그램 봇은 미연결 → 계속 publish**(별도 프로세스). 복귀 시 `.env`에서 `AUTO_BOT_DRAFT_ONLY=false`.
- **이미지 마커 주석 중첩 버그 수정** — Claude가 `[[IMAGE:...]]` 마커를 `<!-- [[IMAGE:...]] -->`로 감싸 출력하면 strip 시 주석이 중첩(`<!-- <!-- ... --> -->`)돼 본문에 `-->`가 노출되던 문제. `_maybe_inject_images`가 처리 전 주석 래퍼를 먼저 벗기도록 정규화. 기존 발행 글 id 159·92 정리. 상세→[TROUBLESHOOTING.md](TROUBLESHOOTING.md).
- 테스트: `tests/test_wordpress_helpers.py` force_draft 5건 + `tests/test_image_marker_strip.py` 3건 추가.

## 2026-06-13: WordPress SEO 보강 + 텔레그램 로컬 백업 폐지

- 업로더 SEO 헬퍼(`create_post` 자동 적용): `slugify()`(한글 제목→ASCII 슬러그, 로마자 표기), `auto_excerpt()`(본문→메타 description), `demote_body_h1()`(본문 `<h1>`→`<h2>`, Rank Math Single-H1).
- **슬러그를 의미 담긴 영어 번역으로 업그레이드**: `english_slug()`가 한글 제목을 Gemini로 영어 슬러그 번역(예: "양자컴퓨터가 깨뜨릴 암호와 PQC 전환 로드맵"→`quantum-computing-threats-pqc-roadmap`), Gemini 실패/쿼터 소진 시 로마자(`slugify`) 폴백. `create_post` 기본값을 `english_slug`로 교체.
- 버핏봇 제목·태그에서 "버핏의" 제거 → `{날짜} 투자 노트` / 태그 `투자노트`.
- 텔레그램 로컬 백업(`~/blog_posts/`) 폐지: `shared/local_archive.py`·테스트 삭제, 발행 완료 메시지에서 백업 경로 제거. 발행은 WordPress 한 곳으로만.
- **버핏·섹터 저자 박스 중복 버그 수정**: 청크 변환(`convert_long_md_to_html`/`_convert_long_md_to_html`)이 청크마다 박스를 붙여 2청크 이상이면 박스가 글 중간에 중복되던 문제 → 청크엔 `apply_editorial_box=False`, 합친 뒤 `_maybe_apply_editorial`로 1회만 적용. 회귀 테스트 `tests/test_editorial_single_box.py` 추가.
- `tests/test_wordpress_helpers.py` 9건 추가.

## 2026-06-12: 전 봇 Blogger → WordPress(grace-moon.com) 발행 전환

- 신규 `shared/wordpress_uploader.py` — WordPress REST 발행(App Password + HTTP Basic Auth). 카테고리 매핑(`CATEGORY_IDS` 11종), 태그 생성, mermaid→PNG(kroki), AdSense/raw strip, 옛 `BloggerUploader.upload_post` 드롭인 호환 어댑터.
- 뉴스·버핏·섹터·부동산·텔레그램 봇 발행처를 WordPress로 교체. 텔레그램은 발행 시 **WordPress 카테고리 버튼 선택(8종)**, 영문 변환·raw 첨부 폐지(전부 한글 그대로).
- `shared/blogger_uploader.py` **삭제**(504줄). `shared/__init__.py`에서 `BloggerUploader` export 제거.
- `claude_html_converter.py`: 영문 변환(`convert_ko_html_to_english`)·raw 첨부(`append_raw_source_details`)·`translate_markdown_to_english`·AdSense 인라인 삽입 **전부 제거**. `blogger-html` 스킬에서 AdSense 섹션 제거.
- 저자 박스 → **GraceMoon**(grace-moon.com), `config/authors.json` 전 페르소나 갱신.
- 터미널 출력 legacy 문구(Blogger/blogspot/Tistory)를 WordPress 기준으로 갱신.
- 라이브 발행 테스트: 부동산봇(id 55)·뉴스봇(id 56) 정상.

## 2026-06-08: 애드센스 편집 레이어(C1·C3·C4) + 텔레그램 단일 블로그 업로드

- **배경**: Blogger 블로그가 애드센스 심사에서 반복 거부 — 원인은 플랫폼이 아니라 "AI 무편집 대량 생성물(low value)". 구글 공식 입장은 "AI 사용≠위반, 품질이 기준". 콘텐츠에 E-E-A-T·고유 데이터 신호를 주입하는 편집 레이어 도입. 설계=[docs/ADSENSE_EDITORIAL_LAYER.md].
- **운영 결정**: Tistory(이미 승인됨)를 수익처로 유지, Blogger는 공개 미러. **자동 업로드는 Blogger만**(Tistory API 부재) → 사람이 수동 복붙. 광고(인아티클·멀티플렉스)는 Blogger 발행물에 그대로 유지(복붙 시 함께 이동).
- **C1 저자 박스 + C4 면책/투명성** (`shared/editorial/`, `config/authors.json`): 모든 봇 발행물 HTML 끝에 저자(E-E-A-T) 박스 + "데이터·출처 기반 / 최종 업데이트" 라인 자동 삽입. 인라인 스타일만(Tistory sanitize 대비). 면책은 `blogger-html` 스킬이 contextual하게 담당(중복 회피) — 편집 레이어는 기본 미포함(`include_disclaimer` opt-in). 저자명은 티스토리 정체성("마구쓰는 일상공간")으로 통일, 주제별 직함만 차등. AI/자동 언급 없음(스킬 규칙 준수).
- **C3 고유 데이터 표** (`shared/editorial/data_blocks.py`): 봇만 가진 수치를 결정적 마크다운 표로 본문에 박제. 뉴스 일간=`orch.stats`(카테고리별 건수·Tier-1 비중·국내외 비율)를 "이번 호 수집 데이터" 표로(`main.py`). 부동산=`digest.py`가 이미 실거래 표 렌더(준수). 섹터/버핏=구조화 숫자 부재로 보류.
- **중앙 연결**: `convert_md_to_html_via_claude(editorial=...)` — 전 봇 호출부(news/buffett/sector/realestate/telegram) 배선. env `EDITORIAL_ENABLED`(기본 on).
- **텔레그램 단일 블로그 업로드**: `bravebabyogu` default 무조건 업로드 폐지 → **선택한 블로그 1곳만**. 무선택 타임아웃=업로드 취소. `_upload_default_only`/`_upload_dual` → `_upload_single` 통합.
- **폐기**: 세션 중 티스토리 자동 업로드(`tistory_poster.py`) 프로토타입을 구현·검증했으나, **발행이 캡차/봇탐지(`/manage/dkaptcha`)로 게이트**되어 무인 발행 불가(+캡차 우회는 약관 위반·미지원) 판단 → 전량 폐기. 결론: 수동 복붙 유지, 진짜 무인 자동화는 워드프레스가 정공법.
- **테스트**: `tests/test_editorial.py`(8) + `tests/test_data_blocks.py`(4) 신규, full suite **95 pass**.

## 2026-06-07: 섹터봇 분석 모델 3.5-flash 승격 + 분량 floor 상향

- **배경**: 섹터 분석 길이가 모델에 비례(실측 `gemini-3.1-flash-lite` ~2,300자 vs `gemini-3.5-flash` ~7-16k자). 기본이 flash-lite라 보고서가 얇게 나옴(주차별로 flash-lite가 quota로 3.5-flash fallback될 때만 길어짐).
- **변경**:
  - `sector_bot/config.py` — `SECTOR_GEMINI_MODEL` 기본값 `gemini-3.1-flash-lite` → **`gemini-3.5-flash`**(풍성한 분석 primary).
  - `sector_bot/analyzer.py` `_models_chain()` — 섹터 전용 fallback env `SECTOR_GEMINI_FALLBACK_MODELS`(기본 `gemini-3.1-flash-lite,gemini-3-flash-preview,gemini-2.5-flash`) 신설. 요약봇의 글로벌 `GEMINI_FALLBACK_MODELS`와 격리. → 섹터 체인 = `[3.5-flash, 3.1-flash-lite, 3-flash-preview, 2.5-flash]`(3.5-flash 쿼터 소진 시 flash-lite로 무중단 degrade).
  - `~/.claude/skills/sector-analysis/SKILL.md` 분량 floor `2000자` → **`5000자 이상, 길수록 좋음(상한 없음)`**.
- **라이브 검증(2026-06-07 16:22 재시작 후)**: 반도체 섹터 분석 `model=gemini-3.5-flash chars=16,497`(직전 flash-lite 주식시장 1,947자 대비 ~8.5배), HTML 35,780자, 출처 14~15개. agy 검색(Gemini 3.1 Pro High)도 정상.
- **테스트**: `tests/test_sector_model_chain.py` 3개(체인 순서·섹터 전용 fallback 격리·기본값) + full suite 84 pass.
- **주의**: 3.5-flash는 쿼터·시간 소모↑(분석당 ~6-16k자, 섹터당 ~8분). 소진 시 flash-lite fallback.

---

## 2026-06-07: 웹서치 백엔드 agy(Antigravity CLI) 전환 + Claude fallback

- **배경**: 2026-05-27 PM에 grounding 4곳을 Claude WebSearch로 옮겼는데, gemini CLI 종료 대비로 antigravity CLI(`agy`) 설치 → `agy -p`가 `gemini -p` 대체. 웹서치를 agy(Gemini) primary로 되돌리되 Claude는 fallback으로 보존.
- **신규 모듈**: `shared/agy_search.py`(`agy_websearch(prompt, model, timeout)`, `AgySearchError`) + `shared/web_search.py`(`web_search()` 디스패처). agy 모델 캐스케이드 **Gemini 3.1 Pro (High) → 3.5 Flash (High) → 3.5 Flash (Medium)** 순차, 전부 하드실패 시 `claude_websearch` fallback. 반환 타입(`ClaudeSearchResponse`)·`_extract_sources` 재사용 → 호출부는 함수명만 swap.
- **갱신 호출부 4곳**: `telegram_gemini_bot.py`, `news_bot/orchestrator.py`, `shared/research_orchestrator.py`, `sector_bot/searcher.py` (`claude_websearch`→`web_search`, kwargs 그대로라 fallback이 기존 동작 보존). `claude_search.py`는 fallback으로 무수정.
- **신규 env**: `AGY_SEARCH_MODELS`(파이프 구분 캐스케이드 override), `AGY_SEARCH_TIMEOUT`(기본 300s, agy 단계용), `AGY_BIN`(바이너리 경로).
- **agy CLI 함정 3건**(→ TROUBLESHOOTING): `-p`가 상속 stdin에서 무한 행(→`stdin=DEVNULL` 필수) / 기본 모델 auto-routing(→`--model` 명시) / 잘못된 모델명 무시(에러 안 냄). 바이너리 부재 시 `OSError→AgySearchError→Claude fallback`(크래시 X).
- **리서치 스킬**: 봇이 쓰는 `telegram-qa/SKILL.md`는 백엔드 중립(Claude 전용 도구 지시 0건)이라 무수정. `~/.claude/skills/research/SKILL.md`는 봇 미참조(Claude Code 대화형)라 그대로 유지.
- **테스트**: pytest 11개(mock 캐스케이드/fallback/실패모드/argv/stdin/바이너리부재), full suite **81 pass**. 라이브: `web_search()` 24.7s(agy Pro High) / `AGY_BIN=/nonexistent`로 강제 fallback→Claude haiku 35.8s 검증.

---

## 2026-06-04: 부동산봇 전국 확장(v2) + 오피스텔 전월세 노출 + 명명 정리

- **전국 확장(v2)**: 주간 디제스트 발행 범위 서울 25구 → **전국 119시군구**(`ALL_REGIONS`). 전국 단일 글(전국 헤더 → 서울 상세 → 경기·6대광역시·세종 권역 요약). 신규 모듈 `regions_extra.group_of`(코드 prefix→권역) / `indicators.rollup_groups`(권역 집계+top movers) / `publish_meta`(제목 "날짜, N월 M주차 {AI헤드라인}" + 7~9 동적 라벨). `commentary` 전국 다문단. `_convert_html`이 버리던 Claude blog_title 보존. 비서울 오피스텔=경기·광역시 건수(세종 제외). 하이브리드(숫자=코드·해석=Gemini·HTML=Claude) 불변. (브랜치 `realestate-national` → main FF, 69 tests, 라이브 전국 스모크 OK) 스펙/계획 `docs/superpowers/*/2026-06-04-realestate-national-digest-expansion*`.
- **오피스텔 전월세 노출**: `store.rent_volume`(전세/월세 건수 분리) → `synthesize` → digest "오피스텔 시장" 섹션이 매매+전월세 2줄.
- **4종 백필 완료**: 아파트·오피스텔 × 매매·전월세, 119시군구·36개월, **392만 행·DB 1.5GB**(직접 MCP, Claude 0콜).
- **명명 정리**: `investment_bot.py` 스케줄 태그 "RealEstate"→"부동산봇" + docstring/argparse/epilog, `run_investment_bot.sh` 헤더에 부동산봇 추가.
- **첫 발행 완료**: ogusinvest.blogspot.com (0신규라 "최근 완료월 델타 리셋"으로 검증발행, Claude HTML+Blogger OAuth refresh 전구간 확인).

---

## 2026-05-28: 블로그 일러스트 이미지 인프라 추가 (활성화는 사용자 결정 시점)

- **배경**: 봇이 Blogger HTML 글을 발행할 때 본문에 일러스트를 embed하고 싶지만 (a) HTML은 `<img src=URL>` 형태로 외부 URL 필요, (b) 로컬 이미지 파일은 URL이 없어 그대로 못 넣음. 두 가지 단계 (이미지 생성 + 호스팅)가 필요.
- **호스팅 backend 결정**: **Cloudinary** (무료 25GB 저장 + 25GB/월 대역, CDN 전용 안정성, 자동 webp 변환). 자격증명 `~/.zshenv`에 영구 export, 1×1 PNG 업로드/삭제 라이브 검증 완료. 호스팅은 어떤 이미지 생성 backend를 쓰든 동일하게 작동.
- **생성 backend 옵션 조사** (research skill 4-round):
  - **Imagen 4 (Google)**: AI Studio dashboard에 무료 RPD 표시되지만 실제 호출은 `400 INVALID_ARGUMENT: Imagen is only available on paid plans`. ai.dev/projects에서 billing 활성화 시 ~$0.02/장.
  - **Pollinations.ai**: open-source, 진짜 무료. REST + URL endpoint, PNG/JPG bytes 직접 반환, Flux/GPT/Claude/Gemini 모델 라우팅. SLA 없음.
  - OpenAI 무료: $5 일회성 credit + ChatGPT 무료 일 2-3장 web UI. 봇 자동화 부적합.
  - Claude native raster: 2026-05 미지원 (SVG/Artifacts만).
  - Gemini web Chrome 자동화: 가능하지만 anti-bot CDP 감지 + Google ToS 위반 위험 + 6-12배 느림 → 비추천.
- **결정**: 코드는 Pollinations.ai 기준으로 작성·완비, Imagen 옵션도 보존. **활성화는 사용자 결정 시점에 환경변수 두 줄로**.
- **신규 모듈** (`001_code/shared/`):
  - `image_generator.py` (302줄) — backend dispatcher (`IMAGE_GEN_BACKEND` env로 `pollinations`/`imagen` 선택). Pollinations: REST GET `/image/{prompt}` 호출 → PNG bytes. Imagen: google-genai SDK + 모델 fallback chain.
  - `image_uploader.py` (167줄) — Cloudinary wrapper. `upload_to_cdn(bytes, public_id, folder)` → `secure_url`. webp 자동 변환.
  - `blogger_html_inject.py` (187줄) — `[[IMAGE: <english prompt>]]` 마커 post-processing. cap=3장/글. 생성·업로드 실패 시 graceful HTML 주석 대체 (발행 차질 0).
- **claude_html_converter.py 수정** (+60줄): `_maybe_inject_images()` 자동 호출 추가. `BLOGGER_IMAGES_ENABLED=false` (default) 모드에서는 마커를 단순 strip + HTML 주석. 활성화 모드에서만 실제 생성/업로드.
- **SKILL 갱신**: `~/.claude/skills/blogger-html/SKILL.md` (+67줄)에 `[[IMAGE:...]]` 마커 작성 지시 + 카테고리별 스타일 키워드 + 안티패턴.
- **활성화 절차**: `~/.zshenv`에 `POLLINATIONS_API_KEY` (https://enter.pollinations.ai 무료 발급) + `BLOGGER_IMAGES_ENABLED=true` 두 줄 추가 → 봇 재시작.
- **검증**: import smoke + Pollinations URL 형식 검증 + 마커 regex (3건 정확 매칭) + Cloudinary 1×1 PNG 업로드/삭제 라이브 OK. 실제 이미지 생성은 라이브 테스트 단계에 reserve.

---

## 2026-05-27 PM: Grounded 호출 4곳 → Claude CLI + WebSearch 재이전

- **배경**: 오전에 끝낸 "Gemini API + 모델 fallback chain" 마이그레이션 직후 라이브 운영에서 모든 4개 모델이 429를 반환하는 현상 발생. AI Studio dashboard에서는 RPM/TPM/RPD가 거의 0%인데도 grounded call이 거부됨. **원인 진단 결과: Gemini 3.x의 `google_search` grounding은 모델 API quota와 별개의 quota bucket을 사용**하고 dashboard에 노출되지 않음. 무료 티어 한도가 매우 빡빡해 일상 사용으로 즉시 소진됨. (참고: Gemini 2.5-flash만 grounding이 살아남는데 그건 prompt당 과금 모델이라 grounding이 prompt charge에 포함되기 때문.)
- **결정**: 단일 모델(2.5-flash)에 의존하는 구조 대신, grounding이 필요한 4개 호출지점을 **Claude CLI + WebSearch**로 전면 이전. Anthropic의 web_search tool은 별도 quota bucket에서 동작하며 `claude -p` 모드에서 자동 활성화됨. 모델은 `--model haiku/sonnet/opus` + `--fallback-model`로 호출 시점에 선택 가능.
- **신규 모듈**: `shared/claude_search.py` — `claude_websearch(prompt, model, fallback_model, timeout)` wrapper. `ClaudeSearchResponse(text, sources, model_used, elapsed_seconds)` 반환. `Sources:` 푸터에서 URL 자동 추출.
- **갱신 파일 (grounding 호출 4곳)**:
  - `telegram_gemini_bot.py` (quick mode) — Sonnet + Haiku fallback
  - `shared/research_orchestrator.py` (deep mode rounds) — Sonnet + Haiku fallback. 함수명 `_run_gemini_round` + `GeminiRoundError`는 외부 호환 유지
  - `news_bot/orchestrator.py` (gap-fill) — Haiku + Sonnet fallback. JSON 출력 단순
  - `sector_bot/searcher.py` (11개 섹터 검색) — Sonnet + Opus fallback. 섹터별 깊이 요구
- **유지 (Gemini API 잔존, grounding 불필요)**:
  - `news_bot/summarizer.py` — daily/weekly/monthly 요약은 이미 수집된 RSS 처리
  - `sector_bot/analyzer.py` — searcher가 이미 grounding 수행, analyzer는 분석만
- **모델별 환경변수 외부화**: `CLAUDE_SEARCH_MODEL`, `CLAUDE_SEARCH_FALLBACK_MODEL`, `CLAUDE_SEARCH_TIMEOUT`, `CLAUDE_MODEL_SECTOR_SEARCH`, `CLAUDE_MODEL_SECTOR_SEARCH_FALLBACK`
- **테스트**: 5개 갱신 (`test_research_orchestrator` 4개 + `test_news_orchestrator` 1개), safety_blocked 테스트 1개 삭제(Claude는 해당 개념 없음). **72개 전부 pass.**
- **라이브 검증**: Haiku로 grounded 호출 → 36.4s, sources 1개, 정확한 응답("Micron Technology stock surged 19.29% ...") 확인.

---

## 2026-05-27 AM: Gemini `-p` CLI 제거 → API + 모델 fallback chain

- **배경**: Google이 2026-06에 `gemini -p` CLI 종료 예고. 코드 6곳(텔레그램 quick/deep, 뉴스봇 daily/weekly/monthly, 뉴스봇 gap-fill, 섹터봇 search/analyze)이 CLI subprocess를 직간접 호출 중이라 전수 마이그레이션.
- **새 wrapper**: `shared/gemini_cli.py` 완전 재작성. 신규 `call_gemini_with_fallback()` + 기존 `call_gemini_cli`/`is_quota_error`/`extract_urls`/`is_cli_mode_active` backward-compat alias 유지.
- **모델 fallback chain (env-configurable)**:
  - `GEMINI_MODEL` (기본 `gemini-3.1-flash-lite`) → primary
  - `GEMINI_FALLBACK_MODELS` (기본 `gemini-3.5-flash,gemini-3-flash-preview,gemini-2.5-flash`) → 429/503/overloaded 시 좌→우 순서로 fallthrough
  - 모든 단계에서 `google_search` grounding 설정 보존 (검색 필요 호출)
- **갱신 파일**:
  - `shared/gemini_cli.py` (재작성, +305줄)
  - `shared/research_orchestrator.py` (deep mode round 호출 → API)
  - `telegram_gemini_bot.py` (`run_gemini` quick mode → API)
  - `news_bot/summarizer.py` (`_use_cli_fallback` 플래그·`_summarize_via_cli` 메서드 제거, `_summarize()` 단일 경로)
  - `sector_bot/searcher.py` (검색 grounding 호출 wrapper로 일원화, fallback 메서드 제거)
  - `sector_bot/analyzer.py` (분석 호출 wrapper로 일원화)
  - `news_bot/orchestrator.py` (`_gap_fill_via_cli`는 함수명만 보존, 내부적으로 alias 경유로 API 호출)
- **테스트**: 4개 `test_research_orchestrator` 테스트 wrapper monkeypatch로 갱신, `test_shared_gemini_cli` `is_cli_mode_active` 영구 False 검증으로 전환, `test_sector_orchestrator` clamping 제거 검증으로 전환. 신규 2개(safety_blocked, grounding sources append) 추가. **73개 테스트 전부 pass.**
- **연계 작업**: `~/.claude/skills/research/` skill도 동일 패턴으로 마이그레이션 (`scripts/ask_gemini.sh`는 wrapper로 변환, `scripts/ask_gemini.py` 신규, `.venv` + `google-genai` 설치, `~/.zshenv`에 `GEMINI_API_KEY` 영구 export).
- **라이브 검증**: `gemini-3.1-flash-lite → 3.5-flash → 3-flash-preview → 2.5-flash` 순차 fallthrough 실측 확인 (앞 3개 quota 소진 상태에서 마지막 모델로 응답 도달).

---

## 2026-05-18: 봇 다이어그램 출력 Mermaid 전환 (SKILL.md만 변경, 코드 무변경)

- `~/.claude/skills/blogger-html/SKILL.md` 3차 패치 (483줄 → 574줄)
  - 시각화 8번 (의사결정 플로우차트) · 9번 (시스템 도식) → **Mermaid 코드블록 우선**, 인라인 SVG는 fallback으로 강등
  - 노드 수 ≤6, 분기점 ≤2, 한 줄 라벨 ≤12자 강제 (모바일 글자 가독성)
  - RSS·이메일 fallback 의무화: 다이어그램 직후 `📊 다이어그램 요약: …` 1~2문장 자연어 압축. JS 비활성 환경에서도 결론 전달
  - Blogger/Tistory 호환성 체크리스트 신설 (스킨 등록된 Mermaid는 OK 명시, 본문 `<script>` 금지)
- 운영자 직접 작업:
  - Blogger 테마 / Tistory 스킨 `</body>` 위에 Mermaid.js v11 글로벌 등록 (`mermaid.esm.min.mjs`)
  - `<pre><code class="language-mermaid">` 본문 코드블록을 `.mermaid` div로 DOM 치환하는 스킨 스크립트 추가
- 라이브 검증 (buffett_bot --once 4회 발행 in 2026-05-17~18):
  - 5/17 글: Mermaid 코드블록 2개 자동 생성 ✓ (회귀 0건)
  - 5/18 #2 · #3 글: 노드 6·분기 2 룰 정확 작동, RSS fallback 문구 자동 출현 ✓
- 결정 보류: 스킨 스크립트 v2 (fontSize 17px + `useMaxWidth: false` + 모바일 가로 스크롤). 노드 6개 제한만으로 사용자 가독성 만족 → v1 유지
- 효과: 봇 다이어그램 깨짐 해소 (이전 SVG 좌표 수동 계산 → Claude 매번 박스/화살표 어긋남 발생). 코드/봇 재시작 무변경 — SKILL.md는 `shared/claude_html_converter.py`가 *매 호출*마다 새로 로드함
- 상세 → [TROUBLESHOOTING.md](TROUBLESHOOTING.md) ("인라인 SVG 플로우차트 화살표가 박스에 안 닿음"), [CONFIGURATION.md](CONFIGURATION.md) ("Mermaid.js 글로벌 등록")

## 2026-05-16: Gemini 모델 preview → GA 전환

- 구글 공식 정책에 따라 `gemini-3.1-flash-lite-preview` (그리고 `.env`에서 임시로 사용 중이던 `gemini-3-flash-preview`) 폐기. GA 버전 `gemini-3.1-flash-lite`로 통일.
- 변경 지점:
  - `001_code/.env` / `.env.example`: `GEMINI_MODEL=gemini-3.1-flash-lite`
  - `001_code/news_bot/config.py:14`, `001_code/news_bot/summarizer.py:32`: default `gemini-3.1-flash-lite`
  - `001_code/sector_bot/config.py:269`: default `gemini-3.1-flash-lite`
  - 문서: `CLAUDE.md`, `docs/CONFIGURATION.md`, `docs/SECTOR_BOT.md`
- 영향: 뉴스봇 요약, 섹터봇 검색 grounding 모두 GA 모델로 전환. 응답 형식·쿼타 영향 없음 (free-tier 동일).

## 2026-05-10: 통합 봇 일요일 스케줄 정정 + Blogger 업로드 idle 재시도

- `investment_bot.py`: Weekly Summary `18:30 → 19:20`, Comprehensive Report `19:00 → 19:40`. 마지막 섹터 11(필수 소비재) `scheduled_time="18:40"`보다 앞서 트리거되던 문제 수정. `weekly_sector_bot.py`/CLAUDE.md 문서와 일치.
- `shared/blogger_uploader.py`: `_insert_with_retry()` 신설. `BrokenPipeError`/`ConnectionResetError`/`SSLError`/`RemoteDisconnected` 등 idle connection drop 발생 시 service 재생성 후 1회 재시도. 종합 보고서(~118KB HTML)처럼 마지막 정상 업로드 이후 30분+ 간격 호출에서 발생하던 broken pipe 자동 복구.
- 사고 기록: 2026-05-10 일요일 런 — Weekly Summary 10/11 (sector 11 미시작), 종합 보고서 broken pipe → 텔레그램 ❌ 도착.
- 상세 → [TROUBLESHOOTING.md](TROUBLESHOOTING.md) ("Sector Weekly Summary가 N-1/N 으로 나감", "Comprehensive Report 업로드 Broken pipe")

## 2026-05-04: 뉴스봇 5차원 검증 게이트 + Gemini CLI 갭필

- `news_bot/orchestrator.py` 도입: RSS 수집 → 5차원 게이트 → Gemini CLI 갭필 → 요약 시퀀스
- `news_bot/dimensions.py`: 균형/신선도/다양성/출처신뢰/글로벌균형 5차원 정의 + Claude judge (fail-open)
- `news_bot/config.py`: `HOURS_LIMIT_BY_CATEGORY` 추가 (정치/주식/암호화폐 6h, 경제/사회/국제/IT 12h, 문화 24h)
- `news_bot/aggregator.py`: `fetch_news` / `get_daily_news`에 `hours_by_category` 매개변수 추가
- `news_bot/summarizer.py`: Gemini API 429 → CLI fallback 자동 전환 (`_use_cli_fallback` 플래그)
- `main.py`: `run_daily_task` Step 1을 `aggregator.get_daily_news` → `run_news_research` 호출로 교체
- `~/.claude/skills/news-summarizer/SKILL.md`: 모순 명시 제약 추가 → `## 📌 매체 간 시각 차이` 자동 생성
- Hard cap: 12분 (RSS 자체 3-5분 + 갭필 최대 4회)
- 라이브 검증: 2026-05-04 14:18 — 균형/글로벌균형 fail → 정치·주식·암호화폐 갭필 → 보고서에 특검법·프로젝트 프리덤 매체 간 시각 차이 자동 추출 ✓
- 상세 → [NEWS_BOT.md](NEWS_BOT.md)

## 2026-05-03 ~ 2026-05-04: 섹터봇 5차원 검증 게이트

- `sector_bot/orchestrator.py` 도입: 검색 → 5차원 게이트 (정의/현황/근거/반론/적용) → 갭필 → 분석
- `sector_bot/dimensions.py`: 5차원 정량 체크 + Claude judge (fail-open) + 종합 변형 (`claude_judge_comprehensive`)
- `sector_bot/comprehensive_report.py`: 1차 합성 → 5차원 게이트 → 미달 시 1회 재합성
- `weekly_sector_bot.py` 스케줄: 12:00 시작, 40분 간격 (구 13:00/30분), 텔레그램 19:20, 종합 19:40
- `--deep` CLI 플래그: max_rounds=3 (기본 2)
- `~/.claude/skills/sector-analysis/SKILL.md` + `sector-comprehensive/SKILL.md`: 모순 명시 제약 추가
- Hard cap: 8분/섹터, CLI fallback 활성 시 갭필 스킵
- 라이브 검증: 2026-05-04 06:43 (섹터 1) / 06:51 (종합) ✓
- 상세 → [SECTOR_BOT.md](SECTOR_BOT.md)

## 2026-05-04: shared/gemini_cli.py로 이동

- `sector_bot/gemini_cli.py` → `shared/gemini_cli.py` (`git mv`로 이력 보존)
- sector_bot 3개 모듈 + 뉴스봇 신규 모듈이 모두 import — cross-bot 재사용 깔끔하게

## 2026-04-26 ~ 2026-04-30: Deep research 통합

- `shared/research_orchestrator.py` 도입: Gemini × Claude 다라운드 5차원 검증 루프
- `RESEARCH_QUICK_COMMAND`, `RESEARCH_MAX_ROUNDS` env vars 추가
- Telegram Q&A 봇: 평문=Deep research(default), `/quick`=단발 (opt-out 패턴)
- Round-1 broad sweep + Round-N targeted gap-fill 구조
- Early-stop: `verdict=pass`면 즉시 synth 점프
- `_run_gemini_round`, `_evaluate_round`, `_synthesize` 분리 — 한 모델 자기평가 방지
- Live integration smoke test (env-gated `RUN_LIVE_RESEARCH_TEST=1`)
- 상세 → [CONFIGURATION.md#deep-research-동작](CONFIGURATION.md)

## 2026-04-23: blogger-html 스킬 시각화 지원

- `blogger-html/SKILL.md`에 차트·테이블 시각화 패턴 추가
- 섹터봇 종합 보고서에서 활용

## 2026-04: sector_bot CLI fallback

- Gemini API 장애 시 CLI 호출로 retry exhaustion 후에도 한 번 더 fallback
- 일요일 오후 섹터봇 빈 결과 사고 방지

## 2026-03: Buffett persona bot 도입

- `buffett_bot.py` — 워런 버핏 / 찰리 멍거 페르소나 일일 투자 분석
- Claude CLI 기반 (Gemini와 분리)

## 2026-03: Prompt externalization

- 모든 AI 프롬프트를 `~/.claude/skills/<bot>/SKILL.md`로 외부화
- 코드 수정 없이 스킬 파일만 수정으로 품질 개선 가능
- 7개 스킬 정리: news-summarizer, sector-search, sector-analysis, sector-comprehensive, buffett, telegram-qa, blogger-html

## 2026-03: 섹터봇 11개 분리

- `weekly_sector_bot.py` — 11개 섹터 (Tech / Healthcare / Financials / Energy / Industrials / Consumer / Real Estate / Materials / Utilities / Communication / Crypto)
- 일요일 13:00~18:00 분산 실행 (Gemini API quota 분산)
- 19:00 종합 투자 평가 보고서

## 2026-02: 다중 블로그 지원

- `BLOG_LIST` env var로 다중 블로그 등록
- Telegram에서 발행 시 블로그 선택 prompt
- `BLOG_SELECTION_TIMEOUT` (기본 180s) 후 `DEFAULT_BLOG` 사용
