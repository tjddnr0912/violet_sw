# 006_auto_bot 설정

## 환경변수 (`.env`)

| 이름 | 필수 | 기본값 | 설명 |
|------|------|------|------|
| `GEMINI_API_KEY` | ✅ | — | Google AI Studio API key |
| `BLOGGER_BLOG_ID` | ✅ | — | 메인 블로그 ID |
| `TELEGRAM_BOT_TOKEN` | ✅ | — | Telegram bot token |
| `TELEGRAM_CHAT_ID` | ✅ | — | Telegram chat ID |
| `BLOG_LIST` | ❌ | — | JSON 배열, 다중 블로그 등록 (`[{"key":"...","id":"...","name":"..."}, ...]`) |
| `DEFAULT_BLOG` | ❌ | `brave_ogu` | timeout 시 사용할 default blog key |
| `BLOG_SELECTION_TIMEOUT` | ❌ | 180 | 블로그 선택 prompt timeout (초) |
| `SECTOR_BLOGGER_BLOG_ID` | ❌ | `9115231004981625966` | 섹터봇 전용 블로그 |
| `SECTOR_GEMINI_MODEL` | ❌ | `gemini-3.1-flash-lite-preview` | 섹터봇 Gemini 모델 (검색 grounding 지원) |
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

## Deep research 동작

- Gemini × Claude 다라운드 5차원 검증 — Round 1 broad sweep + Round 2~N targeted gap-fill
- early-stop: verdict=pass면 즉시 synth로 점프 (평균 1~2 라운드)
- Gemini 단발 / 평가 / synth 분리 — 한 모델이 자기 평가하지 않음
- 모든 실패 모드(timeout, JSON parse 실패, 비정상 verdict)에서 누적 결과로 fallback synth
- 상세 → [ARCHITECTURE.md](ARCHITECTURE.md) + Obsidian `knowledge/ai/multi-round-research-orchestration`

## 변경 이력

상세는 [CHANGELOG.md](CHANGELOG.md).
