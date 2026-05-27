# News Bot

매일 06:00 RSS 수집 → 5차원 검증 게이트 → Gemini CLI 갭필 → AI 요약 → Blogger 업로드.

## 실행

```bash
python main.py --mode daily       # 일간 즉시 1회
python main.py --mode weekly      # 주간 (게이트 적용 안 함)
python main.py --mode monthly     # 월간 (게이트 적용 안 함)
```

## 8개 카테고리

정치, 경제, 사회, 국제, 문화, IT/과학, 주식, 암호화폐 — 각 카테고리당 3-8개 RSS feed.

## 오케스트레이터 (5차원 검증)

`news_bot/orchestrator.py`가 RSS 수집 → 5차원 게이트 → Gemini API 갭필(google_search grounding 활성) → 요약을 시퀀싱한다.

> 2026-05 migration: 옛 `gemini -p` CLI 호출은 모두 `shared.gemini_cli.call_gemini_with_fallback`로 교체됨. 갭필 채널 컬럼의 "gemini -p"는 이제 API + 모델 fallback chain(3.1-flash-lite → 3.5-flash → 3-flash-preview → 2.5-flash) + `google_search` grounding을 의미한다.

### 5차원 체크리스트 (collection-level)

| 차원 | 통과 기준 (정량) | Claude 2차 | 갭필 채널 |
|------|---------------|-----------|----------|
| 균형 | 8개 카테고리 모두 ≥3개 항목 | 항상 (quant fail 시) | Gemini API + grounding (missing 카테고리 검색) |
| 신선도 | ≥80% 항목이 카테고리별 한도 내 | ↑ | Gemini API + grounding (6시간 내 breaking news) |
| 다양성 | 같은 주제 매체 중복 ≤2개 | ↑ | (갭필 없음 — aggregator dedup) |
| 출처신뢰 | Tier-1 출처(Bloomberg/Reuters/FT/WSJ/연합뉴스/SBS/YTN) ≥40% | ↑ | Gemini API + grounding (Tier-1 source coverage) |
| 글로벌균형 | 한국 매체 비율 40~60% | ↑ | Gemini API + grounding (국제 시각) |

OR-semantics: 한 차원이 정량 OR Claude 중 하나라도 통과하면 그 차원은 통과 처리.

### 카테고리별 신선도 한도 (`HOURS_LIMIT_BY_CATEGORY`)

| 카테고리 | 한도 (h) | 환경변수 |
|---------|---------|---------|
| 정치 | 6 | `NEWS_HOURS_정치` |
| 경제 | 12 | `NEWS_HOURS_경제` |
| 사회 | 12 | `NEWS_HOURS_사회` |
| 국제 | 12 | `NEWS_HOURS_국제` |
| 문화 | 24 | `NEWS_HOURS_문화` |
| IT/과학 | 12 | `NEWS_HOURS_IT` |
| 주식 | 6 | `NEWS_HOURS_주식` |
| 암호화폐 | 6 | `NEWS_HOURS_암호화폐` |

### 라운드 예산

- Round 1: RSS 수집 (3-5분)
- Gap-fill: 카테고리별 1회씩, 최대 4회 (`max_gap_fills`)
- Hard cap: **12분** (총 wall time)

### 갭필 결과 통합

Gemini CLI는 JSON 배열로 응답:

```json
[{"title": "...", "summary": "...", "url": "...", "date": "YYYY-MM-DD", "source": "..."}, ...]
```

Orchestrator가 이를 news_item dict로 변환해 기존 풀에 합침. 별도 섹션 없음.

### 모순 명시

요약 출력에 `## 📌 매체 간 시각 차이` 섹션이 자동 생성됨 (`news-summarizer/SKILL.md`의 추가 제약).

## Gemini CLI Fallback

Gemini API 429 RESOURCE_EXHAUSTED 발생 시 `shared/gemini_cli.py`로 자동 전환 (sector_bot과 공유).
