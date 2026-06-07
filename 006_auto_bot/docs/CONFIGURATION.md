# 006_auto_bot 설정

## 환경변수 (`.env`)

| 이름 | 필수 | 기본값 | 설명 |
|------|------|------|------|
| `GEMINI_API_KEY` | ✅ | — | Google AI Studio API key |
| `BLOGGER_BLOG_ID` | ✅ | — | 메인 블로그 ID |
| `TELEGRAM_BOT_TOKEN` | ✅ | — | Telegram bot token |
| `TELEGRAM_CHAT_ID` | ✅ | — | Telegram chat ID |
| `BLOG_LIST` | ❌ | — | JSON 배열, 다중 블로그 등록 (`[{"key":"...","id":"...","name":"..."}, ...]`) |
| `DEFAULT_BLOG` | ❌ | `brave_ogu` | 단일 블로그 모드(`len(blogs)==1`) 대상 key. **2026-06-08~ 텔레그램은 더 이상 default 자동 업로드 안 함**(선택 블로그 1곳만). |
| `BLOG_SELECTION_TIMEOUT` | ❌ | 180 | 블로그 선택 prompt timeout (초). 무선택 시 업로드 취소. |
| `EDITORIAL_ENABLED` | ❌ | `true` | 편집 레이어(저자 박스 + 면책/투명성 라인) on/off. 모든 봇 발행물 HTML 끝에 적용. 저자 페르소나=`config/authors.json`. |
| `EDITORIAL_AUTHOR` | ❌ | `default` | 호출부가 `editorial={"author":...}` 미지정 시 기본 author key. |
| `EDITORIAL_CONTENT_TYPE` | ❌ | `general` | 호출부 미지정 시 기본 content_type(면책 결정용). |
| `SECTOR_BLOGGER_BLOG_ID` | ❌ | `9115231004981625966` | 섹터봇 전용 블로그 |
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

## Mermaid.js 글로벌 등록 (Blogger / Tistory)

봇이 만든 `<pre><code class="language-mermaid">` 코드블록을 다이어그램으로 자동 렌더링하려면 발행 플랫폼의 **테마/스킨에 Mermaid.js v11을 1회 등록**해야 한다. 등록 후에는 봇 출력 무변경으로 모든 글에서 작동.

### Blogger 등록

1. `blogger.com` → 좌측 메뉴 **테마** → 적용된 테마 박스 우측 `▼` → **HTML 편집** (`맞춤설정`이 아니라 *그 옆* ▼)
2. `</body>` 바로 위에 아래 스크립트 추가 → 저장 (위젯 보존 경고 시 *유지* 선택)

Blogger는 XML 파서를 사용하므로 인라인 스크립트 내 `<`/`>`/`&`는 `//<![CDATA[ … //]]>` 로 감싸야 한다.

### Tistory 등록

1. `관리` → `꾸미기` → **스킨 편집** → 우측 상단 **html 편집** 탭 → `HTML` 탭
2. `</body>` 바로 위에 동일 스크립트 추가 → **[적용]**
3. 본문 단의 `<script>`는 Tistory가 sanitize함 → 스킨 단에만 박을 것

Tistory는 일반 HTML 파서라 CDATA 불필요. 외부 `https://` CDN 호출 허용 (무료 도메인 포함).

### 등록 스크립트 (양쪽 호환, v1)

```html
<script type='module'>
//<![CDATA[
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
mermaid.initialize({ startOnLoad: false, securityLevel: 'loose' });
document.addEventListener('DOMContentLoaded', async () => {
  document.querySelectorAll('pre > code.language-mermaid, pre.mermaid-code').forEach(block => {
    const pre = block.parentElement;
    const div = document.createElement('div');
    div.className = 'mermaid';
    div.textContent = block.textContent;
    pre.parentNode.replaceChild(div, pre);
  });
  await mermaid.run({ querySelector: '.mermaid' });
});
//]]>
</script>
<style>.mermaid { overflow-x: auto; max-width: 100%; text-align: center; margin: 16px 0; }</style>
```

### v2 옵션 (사용자 결정에 따라 보류 — 필요 시 추가)

큰 다이어그램에서 글자가 작아지는 문제를 *완전히* 제거하려면 v1 대신 UMD 빌드 + `useMaxWidth: false` + `fontSize: '17px'` + 모바일 가로 스크롤을 적용한 v2 스크립트로 교체한다. SKILL.md의 노드 6개 제한만으로 가독성이 충분하면 v1 유지가 권장. v2 전체 코드는 git 히스토리의 PR 또는 별도 메모로 보관.

### 검증

발행물 raw HTML을 다음 명령으로 확인:

```bash
curl -sL -A "Mozilla/5.0" "$URL" | grep -ciE "language-mermaid|import mermaid|mermaid\.run"
```

- 봇이 만든 코드블록 카운트 + 스킨 스크립트 시그니처가 양수면 정상.
- WebFetch 도구는 inline `<svg>`/`<script>`/style을 markdown 변환에서 소실시키므로 사용 금지 (→ TROUBLESHOOTING의 "인라인 SVG 플로우차트" Claude 진단 미스 참조).

## Deep research 동작

- Gemini × Claude 다라운드 5차원 검증 — Round 1 broad sweep + Round 2~N targeted gap-fill
- early-stop: verdict=pass면 즉시 synth로 점프 (평균 1~2 라운드)
- Gemini 단발 / 평가 / synth 분리 — 한 모델이 자기 평가하지 않음
- 모든 실패 모드(timeout, JSON parse 실패, 비정상 verdict)에서 누적 결과로 fallback synth
- 상세 → [ARCHITECTURE.md](ARCHITECTURE.md) + Obsidian `knowledge/ai/multi-round-research-orchestration`

## 변경 이력

상세는 [CHANGELOG.md](CHANGELOG.md).
