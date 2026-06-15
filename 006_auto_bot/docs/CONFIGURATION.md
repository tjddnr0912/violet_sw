# 006_auto_bot 설정

## 환경변수 (`.env`)

| 이름 | 필수 | 기본값 | 설명 |
|------|------|------|------|
| `GEMINI_API_KEY` | ✅ | — | Google AI Studio API key |
| `TELEGRAM_BOT_TOKEN` | ✅ | — | Telegram bot token |
| `TELEGRAM_CHAT_ID` | ✅ | — | Telegram chat ID |
| `WORDPRESS_URL` | ✅ | — | WordPress 사이트 URL (`https://grace-moon.com`). **2026-06-12~ 전 봇 발행처**. |
| `WORDPRESS_USER` | ✅ | — | WP 로그인 ID |
| `WORDPRESS_APP_PASSWORD` | ✅ | — | WP 애플리케이션 비밀번호(공백 자동 제거). **절대 Git 커밋 금지**. |
| `WORDPRESS_DEFAULT_STATUS` | ❌ | `publish` | 발행 상태. `publish` 또는 `draft`. |
| `AUTO_BOT_DRAFT_ONLY` | ❌ | `true` | `true`이면 investment_bot 계열 자동봇(뉴스/버핏/섹터/부동산)이 발행하는 글을 status 인자와 무관하게 **항상 draft**로 올린다(`WordPressUploader(force_draft=...)`, `create_post` 단일 choke point에서 강제). **텔레그램 봇은 이 값을 읽지 않아 영향 없음(계속 publish)**. 애드센스 심사 준비 동안 자동 발행 일시정지용. 자동 publish 복귀 시 `false`. (2026-06-14~) |
| `AUTO_FEATURED_CARD` | ❌ | `false`(.env=`true`) | `true`이면 `featured_media` 미지정 글에 제목·카테고리 기반 **타이틀 카드(1200×630 다크)** 를 자동 생성해 대표 이미지(og:image/썸네일)로 첨부(`create_post`→`shared/title_card.make_title_card`→`upload_media`). **비용0·무네트워크**(Pillow + 시스템 한글 폰트). 폰트/렌더 실패 시 조용히 생략하고 발행은 계속. 명시 `featured_media`가 있으면 그게 우선. (2026-06-15~) |
| `TITLE_CARD_FONT` | ❌ | (자동탐지) | 타이틀 카드 폰트 경로 override. 미지정 시 AppleSDGothicNeo→AppleGothic→NanumGothic→NotoSansCJK 순으로 탐지. |
| `KROKI_URL` | ❌ | `https://kroki.io` | mermaid→PNG 렌더 서버. WordPress 발행 시 코드블록을 이미지로 변환. |
| `BLOGGER_ENABLED` / `NEWS_BLOGGER_ENABLED` | ❌ | — | 각 봇 발행 게이트(레거시 이름, 실제 발행처=WordPress). `false`면 발행 스킵. |
| `BLOGGER_BLOG_ID` | (레거시) | — | Blogger 시절 잔재. 2026-06-12 WordPress 전환 후 미사용(일부 config 검증에만 잔존). |
| `BLOG_LIST` | (레거시) | — | 옛 다중 블로그(blogspot) 등록. WordPress 전환 후 미사용(텔레그램 self.blogs 잔재). |
| `DEFAULT_BLOG` | (레거시) | `brave_ogu` | 옛 단일 블로그 모드 대상 key. WordPress 전환 후 미사용. |
| `BLOG_SELECTION_TIMEOUT` | ❌ | 180 | 텔레그램 **WordPress 카테고리** 선택 prompt timeout (초). 무선택 시 발행 취소. |
| `EDITORIAL_ENABLED` | ❌ | `true` | 편집 레이어(저자 박스 + 면책/투명성 라인) on/off. 모든 봇 발행물 HTML 끝에 적용. 저자 페르소나=`config/authors.json`. |
| `EDITORIAL_AUTHOR` | ❌ | `default` | 호출부가 `editorial={"author":...}` 미지정 시 기본 author key. |
| `EDITORIAL_CONTENT_TYPE` | ❌ | `general` | 호출부 미지정 시 기본 content_type(면책 결정용). |
| `SECTOR_BLOGGER_BLOG_ID` | (레거시) | `9115231004981625966` | 옛 섹터봇 Blogger 블로그 ID. WordPress 전환 후 섹터봇은 카테고리 7로 발행(일부 config 검증에만 잔존). |
| `SECTOR_GEMINI_MODEL` | ❌ | `gemini-3.5-flash` | 섹터 **분석**(`sector_bot/analyzer.py`) primary 모델. 2026-06-07 `gemini-3.1-flash-lite`→`gemini-3.5-flash`로 승격(분석 길이가 모델 비례, flash-lite ~2.3천자 vs 3.5-flash ~6-16천자). 검색은 별도 agy(`AGY_SEARCH_MODELS`). |
| `SECTOR_GEMINI_FALLBACK_MODELS` | ❌ | `gemini-3.1-flash-lite,gemini-3-flash-preview,gemini-2.5-flash` | 섹터 분석 전용 fallback chain(요약봇의 글로벌 `GEMINI_FALLBACK_MODELS`와 격리). 3.5-flash 쿼터 소진(429/503) 시 순차 — flash-lite 우선. |
| `CLAUDE_SEARCH_MODEL` | ❌ | `sonnet` | `shared.claude_search.claude_websearch`의 default 모델. alias(`haiku`/`sonnet`/`opus`) 또는 full ID. |
| `CLAUDE_SEARCH_FALLBACK_MODEL` | ❌ | `haiku` | Primary가 overloaded 시 Claude CLI가 자동 retry 모델. `None` 효과를 원하면 빈 문자열. |
| `CLAUDE_SEARCH_TIMEOUT` | ❌ | `900` | claude subprocess timeout (초). (주: 2026-06-07 이후 `claude_search`는 웹서치 **fallback** 단계. primary는 agy — 아래 `AGY_*`.) |
| `AGY_SEARCH_MODELS` | ❌ | `Gemini 3.1 Pro (High)\|Gemini 3.5 Flash (High)\|Gemini 3.5 Flash (Medium)` | `shared.web_search`의 agy 웹서치 모델 캐스케이드(파이프 `\|` 구분). 순차 시도 후 전부 하드실패면 Claude(`CLAUDE_SEARCH_*`)로 fallback. |
| `AGY_SEARCH_TIMEOUT` | ❌ | `300` | agy 단계별 subprocess timeout(초). 실측 ~15-25s라 빠른 실패용. Claude fallback은 caller의 긴 timeout 유지. |
| `AGY_BIN` | ❌ | (`which agy` → `~/.local/bin/agy`) | agy 바이너리 경로 override. 봇 PATH에 `~/.local/bin` 누락 시 대비. 부재 시 Claude fallback. |
| `CLAUDE_MODEL_SECTOR_SEARCH` | ❌ | `sonnet` | 섹터봇 searcher 전용 primary 모델 (섹터별 깊이 필요). |
| `CLAUDE_MODEL_SECTOR_SEARCH_FALLBACK` | ❌ | `opus` | 섹터봇 searcher fallback 모델. |
| `BLOGGER_IMAGES_ENABLED` | ❌ | `false` | 블로그 HTML 본문의 `[[IMAGE:...]]` 마커 처리 활성화. `false`(default)이면 마커를 HTML 주석으로 strip. `true`이면 Imagen/Pollinations 호출 → Cloudinary 업로드 → `<img>` 교체. (2026-05-28~) |
| `BLOGGER_MAX_IMAGES_PER_POST` | ❌ | `3` | 한 글당 생성할 이미지 최대 개수 (cap). Imagen 일일 한도 + Cloudinary 무료 대역 보호. |
| `BLOGGER_IMAGE_RUN_ID` | ❌ | (auto) | Cloudinary 폴더 그룹용 run-id. 미설정 시 timestamp 자동 생성. |
| `IMAGE_GEN_BACKEND` | ❌ | `pollinations` | 이미지 생성 backend. `pollinations`(권장, 진짜 무료) 또는 `imagen`(paid only, ai.dev/projects billing 필요). |
| `POLLINATIONS_API_KEY` | ❌ (활성화 시 권장) | — | Pollinations.ai 무료 API key (https://enter.pollinations.ai 발급). 없어도 anonymous URL 호출 가능하지만 rate limit 매우 빡빡. |
| `POLLINATIONS_MODEL` | ❌ | `flux` | Pollinations 모델. 선택지: `flux`, `gptimage`, `kontext`, `seedream5`, `nanobanana-pro`, `klein` 등. |
| `POLLINATIONS_BASE_URL` | ❌ | `https://gen.pollinations.ai` | Pollinations REST endpoint base. 셀프 호스트 시 override. |
| `POLLINATIONS_TIMEOUT` | ❌ | `120` | Pollinations HTTP 요청 timeout (초). |
| `IMAGEN_MODEL` | ❌ | `imagen-4.0-fast-generate-001` | Imagen 4 primary 모델 (`IMAGE_GEN_BACKEND=imagen`일 때만 유효). |
| `IMAGEN_FALLBACK_MODELS` | ❌ | `imagen-4.0-generate-001,imagen-4.0-ultra-generate-001` | Imagen 4 fallback chain. |
| `CLOUDINARY_CLOUD_NAME` | ❌ (이미지 활성화 시 필수) | — | Cloudinary cloud name (https://cloudinary.com/console). |
| `CLOUDINARY_API_KEY` | ❌ (동일) | — | Cloudinary API Key. |
| `CLOUDINARY_API_SECRET` | ❌ (동일) | — | Cloudinary API Secret (`~/.zshenv` chmod 600 권장). |
| `CLOUDINARY_FOLDER` | ❌ | `006_auto_bot` | Cloudinary 업로드 기본 폴더 (자동 sub-folder는 `<folder>/<run_id>/`). |
| `CLOUDINARY_FORMAT` | ❌ | `webp` | Cloudinary 자동 변환 포맷. webp가 ~30% 더 작음. |
| `CLOUDINARY_QUALITY` | ❌ | `auto:good` | Cloudinary 품질 설정. |
| `GEMINI_MODEL` | ❌ | `gemini-3.1-flash-lite` | `shared.gemini_cli.call_gemini_with_fallback`의 기본 primary 모델 (뉴스봇 summarizer + research orchestrator + telegram quick mode에서 사용). 섹터봇은 `SECTOR_GEMINI_MODEL`을 별도 보유. |
| `GEMINI_FALLBACK_MODELS` | ❌ | `gemini-3.5-flash,gemini-3-flash-preview,gemini-2.5-flash` | 쉼표 구분 fallback chain. primary가 429 `RESOURCE_EXHAUSTED` / 503 `UNAVAILABLE` / `overloaded` 반환 시 왼→오 순으로 시도. 모든 모델 소진 시 `RuntimeError`. 2026-06 `gemini -p` CLI 종료 대응으로 도입(2026-05-27). |
| `RESEARCH_QUICK_COMMAND` | ❌ | `/quick` | Telegram Q&A 단발 모드 트리거 prefix |
| `RESEARCH_MAX_ROUNDS` | ❌ | 3 | Deep research 라운드 상한 (1~4 clamp) |
| `RUN_LIVE_RESEARCH_TEST` | ❌ | (unset) | 라이브 통합 테스트 활성화 (`1`) |
| `NEWS_HOURS_LIMIT` | ❌ | 24 | 뉴스봇 RSS 글로벌 신선도 한도 (시간) — 카테고리별 한도 미설정 시 fallback |
| `NEWS_HOURS_정치` | ❌ | 6 | 뉴스봇 정치 카테고리 신선도 한도 |
| `NEWS_HOURS_경제` | ❌ | 12 | 뉴스봇 경제 카테고리 신선도 한도 |
| `NEWS_HOURS_사회` | ❌ | 12 | 뉴스봇 사회 카테고리 신선도 한도 |
| `NEWS_HOURS_국제` | ❌ | 12 | 뉴스봇 국제 카테고리 신선도 한도 |
| `NEWS_HOURS_문화` | ❌ | 24 | 뉴스봇 문화 카테고리 신선도 한도 |
| `NEWS_HOURS_IT` | ❌ | 12 | 뉴스봇 IT/과학 카테고리 신선도 한도 |
| `NEWS_HOURS_주식` | ❌ | 6 | 뉴스봇 주식 카테고리 신선도 한도 |
| `NEWS_HOURS_암호화폐` | ❌ | 6 | 뉴스봇 암호화폐 카테고리 신선도 한도 |

## OAuth 자격 (`credentials/`)

| 파일 | 용도 |
|------|------|
| `credentials/blogger_token.pkl` | Blogger OAuth refresh token (자동 생성/갱신) |
| `credentials/client_secret.json` | Google OAuth client secret (수동 다운로드) |

## 다중 블로그 등록 형식

`.env`의 `BLOG_LIST`:

```json
[
  {"key": "brave_ogu", "id": "1234567890", "name": "Brave Ogu"},
  {"key": "ogus_invest", "id": "0987654321", "name": "Ogus Invest"},
  {"key": "tech_blog", "id": "1122334455", "name": "Tech Notes"}
]
```

Telegram에서 발행 시 사용자에게 블로그 key 선택 prompt 전송. timeout 시 `DEFAULT_BLOG` 사용.

## AI 스킬 외부화

모든 AI 프롬프트(Claude + Gemini)는 `~/.claude/skills/`에서 로드. 스킬 파일 수정만으로 코드 변경 없이 품질 개선 가능.

| 봇 | 스킬 파일 |
|----|----------|
| 뉴스봇 (일간/주간/월간) | `news-summarizer/SKILL.md` |
| 섹터봇 검색 | `sector-search/SKILL.md` |
| 섹터봇 분석 | `sector-analysis/SKILL.md` |
| 섹터 종합 보고서 | `sector-comprehensive/SKILL.md` |
| 버핏봇 분석 | `buffett/SKILL.md` |
| 텔레그램 Q&A | `telegram-qa/SKILL.md` |
| HTML 변환 (공유) | `blogger-html/SKILL.md` |

## 시크릿 마스킹 정책

- 로그·스택트레이스에 `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN` 직접 노출 금지
- `.env`, `credentials/*.pkl`, `credentials/client_secret.json` 모두 git commit 금지 (`.gitignore` 등재됨)

## Mermaid 다이어그램 (WordPress: 서버측 PNG 렌더)

봇이 만든 `<pre><code class="language-mermaid">` 코드블록은 **발행 시 `WordPressUploader`가 kroki(`KROKI_URL`)로 PNG를 렌더**해 미디어 업로드 후 `<img>`로 치환한다. 테마/스킨에 Mermaid.js를 등록할 필요가 없다(코드 변경 없이 모든 봇 적용).

- 인라인 `<svg>`/`<script>` 방식은 WordPress(wpautop·sanitize)가 도형을 깨뜨려 **PNG로 결정**(2026-06-12). 옛 Blogger/Tistory용 테마 Mermaid.js v11 등록 절차는 폐지.
- 중복 다이어그램은 `hashlib.md5`로 dedup해 미디어를 1회만 업로드.

### 검증

```bash
curl -sL -A "Mozilla/5.0" "$POST_URL" | grep -ciE "<img[^>]+mermaid|kroki"
```

- 발행물 raw 확인엔 `curl` 사용. WebFetch 도구는 inline `<svg>`/`<script>`/style을 markdown 변환에서 소실시키므로 사용 금지 (→ TROUBLESHOOTING의 "인라인 SVG 플로우차트" Claude 진단 미스 참조).

## Deep research 동작

- Gemini × Claude 다라운드 5차원 검증 — Round 1 broad sweep + Round 2~N targeted gap-fill
- early-stop: verdict=pass면 즉시 synth로 점프 (평균 1~2 라운드)
- Gemini 단발 / 평가 / synth 분리 — 한 모델이 자기 평가하지 않음
- 모든 실패 모드(timeout, JSON parse 실패, 비정상 verdict)에서 누적 결과로 fallback synth
- 상세 → [ARCHITECTURE.md](ARCHITECTURE.md) + Obsidian `knowledge/ai/multi-round-research-orchestration`

## 변경 이력

상세는 [CHANGELOG.md](CHANGELOG.md).
