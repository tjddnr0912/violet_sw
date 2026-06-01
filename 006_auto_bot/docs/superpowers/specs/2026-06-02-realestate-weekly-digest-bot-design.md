# 주간 서울 아파트 시장 흐름 다이제스트 봇 — 설계 문서

- 작성일: 2026-06-02
- 프로젝트: `006_auto_bot` (뉴스/버핏/섹터 봇과 동거)
- 상태: 설계 합의 완료 + 핵심 불확실 요소(claude -p + MCP) **동작 검증 완료(2026-06-02)**, 구현 계획(writing-plans) 대기

## 1. 목표 한 줄

매주 토요일 오전, **서울 25개 구 전체의 아파트 실거래 신고를 조회해 시장 흐름 지표(거래량·중앙가·신고가/신저점 breadth·세그먼트·구간 온도차)를 코드로 계산**하고, AI 해석 시황을 붙여 Telegram·Blogger에 발행한다. "신고가/신저점"은 그 자체가 목적이 아니라 **시장 폭(momentum breadth) 지표**로 흡수된다.

## 2. 데이터 현실 (이 설계의 모든 제약의 근원)

`kr-realestate` MCP는 공공데이터포털 **MOLIT 실거래가 REST API**(`apis.data.go.kr/1613000/RTMSDataSvc...`)의 래퍼다.

- **조회 단위 = 월(YYYYMM) + 구(5자리 법정동코드).** 일 단위·전국 일괄 조회 없음. → 구를 하나씩 돈다.
- **실거래가는 "계약 후 30일 내 신고"** → 같은 달 버킷에 새 거래가 며칠에 걸쳐 추가된다. *데이터 단위는 월이지만 새 레코드는 계속 들어온다.* 주간 실행은 약 1주치 신규 신고를 모은다. **최근 월 거래량은 항상 과소집계(미확정)** → 표/시황에 "확정 아님" 명시.
- **레코드에 신고일 필드가 없다.** "새로 신고된 거래"는 **이번 실행 레코드 집합 − 지난 실행까지 본 집합** 차집합으로만 잡힌다 → 상태 저장 필수.
- **신고가/신저점은 API가 직접 안 준다.** (단지, 평형밴드)별 과거 가격 이력과 비교해 직접 계산 → 이력 캐시 필요.
- **제공 필드**(`get_apartment_trades`): apt_name, dong, area_sqm, floor, price_10k, trade_date, build_year, deal_type + summary(median/min/max, sample_count) + total_count. → 이 필드들로 아래 §3-B 지표가 전부 계산 가능.

## 3. 확정된 설계 결정

| # | 결정 | 선택 | 근거 |
|---|------|------|------|
| 1 | 핵심 컨셉 | **주간 서울 시장 흐름 다이제스트** | 신고가/신저점은 출발점일 뿐. 시장 흐름은 거래량·가격·breadth·세그먼트를 정합성으로 읽어야 함 |
| 2 | 지역 범위 | **서울 25개 구 전체** (강동 포함, 정적 고정) | 코드가 구를 자동 가감하지 않으니 정적 25개 = 관리부담 0. 구간 온도차·확산은 전 구가 있어야 의미 |
| 3 | 지표 범위 | **매매 핵심 세트** (전세가율 제외, v2) | 매매 데이터만으로 흐름의 핵심 포착, claude-p 호출 비용 합리적 |
| 4 | 글 성격 | **하이브리드** (코드가 지표 계산, AI는 해석 시황만) | 실거래 숫자 100% 정확. claude 운반 충실성 검증됨(§8) |
| 5 | 데이터 경로 | **`claude -p` + MCP** (운반책으로만) | 사용자 선택. raw JSON 운반만, 계산은 파이썬. **동작 검증 완료(§8)** |
| 6 | 출력 채널 | **Telegram + Blogger 동시** | 기존 봇과 동일 풀 파이프라인 |

### 3-A. 부수 파라미터 (전부 `config.py`)

| 항목 | 기본값 |
|------|--------|
| 실행 시각 | **매주 토요일 08:00** (`investment_bot.py`에 1줄 등록) |
| 대상 구 | **서울 25개 구** (구명→region_code 매핑, setup 시 `get_region_code`로 1회 확정) |
| 조회 월 | {이번달, 지난달} (30일 신고창 커버) |
| baseline 윈도우 | **36개월** → 신고가 라벨 "최근 3년 최고가" |
| `num_of_rows` | **1000** + `total_count` 초과 시 완전성 경고 로그 |
| 평형밴드 | `round(전용면적_㎡)` (84.96, 84.99 → "84밴드") |
| 신축 기준 | build_year 기준 ≤5년 (config) |
| 대상 블로그 | config `REALESTATE_BLOG`, 기본 **`ogusinvest`** |

### 3-B. 시장 흐름 지표 세트 (전부 코드가 결정적으로 계산)

해석 프레임 순서: **① 거래량(선행) → ② 믹스보정 중앙가(방향) → ③ 신고가/신저점 breadth(모멘텀) → ④ 세그먼트·확산(어디서/무엇이).** 단일 지표 맹신 금지, 거래량–가격–breadth 정합성으로 신뢰도 판단.

- **① 거래량** — (a) 이번 주 신규 신고 건수(구별, 활동 펄스), (b) 월별 거래량 시계열(store 집계, 최근 6~12개월). 최근 월은 provisional 플래그.
- **② 믹스보정 중앙가** — raw median 월비교는 구성효과로 왜곡됨. **(구, 평형밴드)별 median**을 공통 밴드끼리 매칭해 변화율 산출, 구 대표값은 밴드 거래수 가중평균.
- **③ 신고가/신저점 breadth** — 이번 주 신규 중 신고가 건수/비중%, 신저점 건수/비중% (구별 + 서울 종합). 모멘텀·폭 게이지. 개별 신고가 단지는 하이라이트 리스트로.
- **④ 세그먼트** — 신축/구축, 소·중·대 평형, 중개/직거래 비중. **직거래 비중 급증 = 특수관계/증여성 가능 → 가격 왜곡 주의 플래그.**
- **⑤ 구간 순위·온도차** — 구를 거래량·중앙가변화·신고가율로 순위화 → "가장 뜨거운/식은 구" + 상급지 선행→외곽 확산 코멘트 근거.

## 4. 아키텍처 / 주간 파이프라인

```
토요일 08:00 스케줄 (investment_bot.py)
  │
  ├─[1] 수집 — fetcher.py (claude -p + MCP, 운반책)
  │     서울 25구 × {이번달, 지난달} get_apartment_trades 호출 (≈25~50 subprocess)
  │     claude는 raw items JSON만 <<<JSON>>>…<<<END>>> 사이 출력 (계산·요약 금지)
  │     봇이 파싱 + 스키마 검증 → 실패 시 재시도 N회, 구별 부분 실패 허용
  │
  ├─[2] 적재 + diff — store.py (SQLite, 결정적)
  │     record_key = (구,단지,법정동,면적,층,계약일,가격)
  │     new = INSERT OR IGNORE 후 실제 삽입된 행 = "지난 실행 이후 새로 신고된 거래"
  │
  ├─[3] 지표 계산 — detector.py + indicators.py (순수함수, 결정적)
  │     detector: 각 new 레코드를 (단지,평형밴드)별 36개월 baseline과 비교 → 🔼신고가/🔽신저점/신규/일반
  │     indicators: §3-B ①~⑤ 집계 (구별 + 서울 종합)
  │
  ├─[4] 리포트 빌드 — digest.py
  │     서울 종합 순위표 → 주목 구 → 신고가/신저점 TOP → 세그먼트 플래그 → markdown
  │
  ├─[5] AI 시황 — commentary.py (gemini_cli, 1회)
  │     계산 끝난 지표·표만 입력 → 해석 프레임(①~④)으로 시황 (숫자 재계산 금지)
  │
  └─[6] 출력
        markdown → convert_md_to_html_via_claude(Claude가 HTML화) → blogger_uploader (REALESTATE_BLOG)
        + telegram_notifier 요약 알림
```

## 5. 모듈 구조 (news_bot/·sector_bot/ 컨벤션)

```
006_auto_bot/001_code/
├── realestate_bot.py          # RealEstateBot 클래스 + --once/--test/--backfill, main()
├── realestate_bot/
│   ├── __init__.py
│   ├── config.py              # 25구 watchlist, 평형밴드, baseline 윈도우, 신축기준, 실행시각, REALESTATE_BLOG
│   ├── fetcher.py             # claude -p + MCP 운반책: (region,ym)→raw items[] JSON, 검증·재시도
│   ├── store.py               # SQLite: transactions 단일 테이블, diff·baseline·거래량 시계열 도출
│   ├── detector.py            # 신고가/신저점 per-record 판정 — 순수함수 (단위테스트 핵심)
│   ├── indicators.py          # 구별·서울종합 지표 집계(§3-B ①~⑤) — 순수함수 (단위테스트 핵심)
│   ├── digest.py              # 다층 리포트 빌드 + 정렬 → markdown
│   └── commentary.py          # AI 시황 (해석 프레임 적용)
└── data/realestate/molit.db   # 상태 저장 (루트 .gitignore의 data/ 패턴이 커버)
```

기존 `shared/` 재사용 (신규 제작 없음):

| 용도 | 재사용 |
|------|--------|
| MD→HTML | `shared/claude_html_converter.convert_md_to_html_via_claude` (최종 HTML은 Claude가 변환) |
| Blogger 업로드 | `shared/blogger_uploader` + `shared/blogger_html_inject` |
| Telegram 알림 | `shared/telegram_notifier` |
| AI 시황 | `shared/gemini_cli.call_gemini_with_fallback` |

유닛 책임/인터페이스:

- **fetcher.py** — `fetch_region(region_code, year_month) -> list[dict]`. 운반책, 상태 없음.
- **store.py** — `insert_new(records) -> list[record]`(신규), `baseline_snapshot(groups) -> dict`, `monthly_volume(region, months) -> list`, `band_medians(region, ym) -> dict`. SQLite만 의존.
- **detector.py** — `classify(record, baseline) -> Verdict(kind∈{HIGH,LOW,NEW,NORMAL}, pct, ref_price, ref_date)`. 순수.
- **indicators.py** — `compute(new_records, store_views) -> {per_gu, seoul}` (거래량·breadth·믹스보정중앙가·세그먼트·순위). 순수.
- **digest.py** — `build(indicators, classified) -> Digest(markdown, telegram_text, counts)`. 순수.
- **commentary.py** — `comment(indicators_summary) -> str`. gemini 1회.
- **realestate_bot.py** — 오케스트레이션 + `--once/--test/--backfill`.

## 6. 상태 모델 (SQLite 단일 테이블)

```sql
CREATE TABLE IF NOT EXISTS transactions (
  record_key TEXT PRIMARY KEY,   -- hash(region|apt|dong|area|floor|trade_date|price)
  region_code TEXT, apt_name TEXT, dong TEXT,
  area_sqm REAL, area_band INTEGER,   -- round(area_sqm)
  floor INTEGER, price_10k INTEGER,
  trade_date TEXT,               -- 계약일 YYYY-MM-DD
  build_year INTEGER, deal_type TEXT,
  first_seen_date TEXT           -- 봇이 처음 본 날
);
CREATE INDEX IF NOT EXISTS idx_group ON transactions(region_code, apt_name, area_band, trade_date);
CREATE INDEX IF NOT EXISTS idx_vol ON transactions(region_code, trade_date);
```

- **신규(diff)**: `INSERT OR IGNORE` 후 실제 삽입된 행. 별도 seen_keys 불필요.
- **baseline**: `... WHERE region=? AND apt=? AND area_band=? AND trade_date >= date('now','-36 months')`.
- **거래량/중앙가**: 같은 테이블 GROUP BY 집계로 도출.
- **멱등성**: PK가 record_key → 재실행/backfill 중복 0.
- **자기치유**: 한 주 한 구를 못 가져와도 누적만 하므로 다음 주 "새 신고"로 포착.

## 7. 신고가/신저점 판정 (정밀, §3-B③의 입력)

1. 이번 실행 레코드를 `(region, apt, area_band)`로 묶는다.
2. **삽입 전** 각 그룹의 36개월 baseline(max/min + 달성 계약일) 스냅샷.
3. 각 신규 레코드 비교: `price>base_max`→🔼신고가(경신율, "최근 3년 최고가") / `price<base_min`→🔽신저점 / 이력없음→신규 단지·평형(판정 보류) / 그 외 일반.
4. 판정 후 INSERT (같은 실행 내 상호 오염 방지).
5. indicators.py가 이 판정 결과를 구별·서울 종합 breadth(건수·비중%)로 집계.

정직성: 보유 이력 ~3년 → "역대" 아닌 **"최근 3년"**. raw median 변화 단독 주장 금지(믹스보정 사용). 최근 월 거래량 미확정 명시. (사용자 피드백 `feedback-no-hanja-narrative-headers` 정신과 동일선.)

## 8. fetcher: `claude -p` + MCP (유일한 신규 통합점) — ✅ 동작 검증 완료(2026-06-02)

- 프롬프트(요지): *"get_apartment_trades 를 region_code=X, year_month=Y, num_of_rows=1000 으로 호출하라. 받은 raw JSON 객체만 `<<<JSON>>>`…`<<<END>>>` 사이에 그대로 출력하라. 요약·계산·코멘트 금지."*
- 한 호출에 한 구의 한 달(가장 단순·견고). 주간 25구 × 2개월 ≈ **50회 subprocess** (구당 2개월 묶으면 25회 — 최적화 옵션).
- 파싱: sentinel 사이 JSON 추출 → `items[]` 필수필드 스키마 검증 → 실패 시 재시도 N회.
- **완전성**: `total_count > len(items)` 면 누락 → 경고 로그 (마포구 202605 실측 total_count=122; 그래서 1000). 침묵 truncation 금지.

> ✅ **검증 결과 (2026-06-02).** 아래로 서브프로세스가 kr-realestate MCP를 실제 로드·호출하고 **직접 호출과 byte-identical한 raw JSON**을 반환함을 확인 (운반책 충실성 입증, `--allowedTools` 불필요):
> ```
> claude -p --mcp-config <루트 .mcp.json> --dangerously-skip-permissions - <<'PROMPT'
> ...get_apartment_trades(region_code=11440, year_month=202605, num_of_rows=5) 호출 후
>    raw JSON만 <<<JSON>>>…<<<END>>> 사이에 출력...
> PROMPT
> ```
> 결과: `rc=0`, 출력 3줄, JSON은 직접 호출과 완전 동일(total_count=122, 5건·summary 일치).
>
> **함정(봇 코드에 박제):** `--mcp-config <file>` 는 뒤따르는 토큰을 설정파일로 *greedy하게* 먹는다. stdin 마커 `-`를 바로 뒤에 두면 `MCP config file not found: -` 에러. → **`--mcp-config` 값 뒤엔 반드시 다른 플래그를 두고 `-`는 맨 끝.**

## 9. 리포트 구조 (digest)

25개 구를 다 나열하지 않고 **요약→하이라이트→상세** 깔때기:

1. **헤더** — 기준 주차 + 서울 종합 한 줄(총 신규건수·신고가 비중·중앙가 방향).
2. **서울 종합 순위표** — 25구 × {이번주 신규건수, 신고가 비중%, 믹스보정 중앙가 변화율}, 가장 뜨거운 순 정렬.
3. **주목 구 하이라이트 3~5** — 가장 움직인 구 짧은 해설(AI).
4. **신고가/신저점 TOP** — 개별 단지(경신율 큰 순), "최근 3년 최고가" 라벨.
5. **세그먼트/직거래 플래그** — 신축·구축, 직거래 급증 주의(있을 때).
6. **AI 시황** — 해석 프레임(①거래량→②중앙가→③breadth→④세그먼트·확산).
7. **푸터** — 출처(MOLIT) + "최근 월 미확정" caveat.

빈 주 정책: 신규 0건 → Telegram 1줄("이번 주 신규 신고 없음"), Blogger 스킵. 신규는 있되 신고가/신저점 0 → 거래량·중앙가 흐름은 발행(흐름 다이제스트라 신고가 없어도 가치 있음).

## 10. 백필 (`--backfill`)

- 최초 1회: 서울 25구 × 36개월 ≈ **900 쿼리**(claude -p). 구별/연도별 청크로 실행, 중간 실패 시 재개 가능(멱등).
- 이후 주간 실행은 증분만(§4).

## 11. 에러 처리

- `investment_bot.py`의 `_safe_run`이 잡 전체를 감쌈.
- 구별 부분 실패 허용: fetcher가 한 구 N회 재시도 후 실패 시 그 구만 skip+로그, 나머지 진행. 누락분은 다음 주 자기치유 포착.
- Gemini 429/503 → `call_gemini_with_fallback` 폴백. 실패해도 **시황 없이 표만 발행**(숫자 보존).
- claude -p 빈출력/타임아웃/JSON 깨짐 → 재시도; 전부 실패 구는 skip.
- 멱등성으로 재실행·backfill 안전.

## 12. 테스트

- **detector.py**(핵심): 신고가 경계, 신저점, 동일가 tie, 이력없음, 평형밴드 그룹핑, 경신율.
- **indicators.py**(핵심): breadth 비중 계산, 월별 거래량 집계, 믹스보정 중앙가(공통밴드 매칭·가중), 세그먼트 비중, 구간 순위 정렬, 직거래 급증 플래그.
- **store.py**: diff 멱등성, baseline 36개월 윈도우, 거래량/중앙가 GROUP BY.
- **fetcher.py**: claude 출력 mock(정상/truncated/non-JSON/sentinel 누락) → 파싱·재시도. 실제 claude 미호출.
- **digest.py**: 순위표 정렬·빈 입력·깔때기 구조.
- **통합 스모크**: `--once --test`로 3~5구 backfill→diff→지표→digest 무오류.

## 13. 단계적 구현 순서 (writing-plans 입력)

1. ✅ **spike (완료 2026-06-02)**: claude -p + MCP 1구 조회·파싱 + 직접호출 동일 확인 (§8).
2. config.py: 서울 25구 region_code 확정(`get_region_code` 1회 수집).
3. store.py + detector.py (+ 단위테스트) — 데이터 엔진 코어.
4. indicators.py (+ 단위테스트) — 지표 집계.
5. fetcher.py (운반책 + 검증·재시도, §8 함정 반영).
6. digest.py + commentary.py (깔때기 리포트 + 해석 프레임).
7. `--backfill` 25구 × 36개월 청크 적재.
8. realestate_bot.py 오케스트레이션 + Telegram 출력 → `--once --test` 스모크.
9. Blogger 출력 결선.
10. `investment_bot.py`에 `schedule.every().saturday.at("08:00").do(_safe_run, "RealEstate", bot.run)` 등록.

## 14. 의도적으로 제외 (YAGNI / v2 후보)

- **전세가율** (rent 조회) — 사용자가 매매 핵심 세트 선택. 호출량 2배라 v2.
- 관심구 자동 선정(동적 선택) — 신고가 추적 일관성·호출비용·주관성. v2.
- 경기도/광역시 확장 — config에 region_code만 추가하면 되나 v1은 서울 25구.
- 거래취소(계약 해제) 감지 diff — v2.
- 오피스텔/빌라/단독 — 아파트 매매부터.
- 청약·온비드 공매 (이벤트성, 별도 봇 컨셉).
