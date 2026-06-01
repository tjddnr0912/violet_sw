# 부동산 주간 신규신고 다이제스트 봇 — 설계 문서

- 작성일: 2026-06-02
- 프로젝트: `006_auto_bot` (뉴스/버핏/섹터 봇과 동거)
- 상태: 설계 합의 완료 + 핵심 불확실 요소(claude -p + MCP) **동작 검증 완료(2026-06-02)**, 구현 계획(writing-plans) 대기

## 1. 목표 한 줄

매주 토요일 오전, **관심 구(區)의 아파트 실거래 신고를 조회해, "지난주 실행 이후 새로 신고된 거래"를 추려 그 중 신고가/신저점을 판정**하고, 표 + 짧은 AI 시황으로 묶어 Telegram·Blogger에 발행한다.

## 2. 데이터 현실 (이 설계의 모든 제약의 근원)

`kr-realestate` MCP는 공공데이터포털 **MOLIT 실거래가 REST API**(`apis.data.go.kr/1613000/RTMSDataSvc...`)의 래퍼다.

- **조회 단위 = 월(YYYYMM) + 구(5자리 법정동코드).** 일 단위 조회 없음, 전국 일괄 조회 없음.
- **실거래가는 "계약 후 30일 내 신고"** → 같은 달 버킷에 새 거래가 며칠에 걸쳐 추가된다. *데이터 단위는 월이지만 새 레코드는 계속 들어온다.* 주간 실행은 약 1주치 신규 신고를 모아 잡는다.
- **레코드에 신고일(접수일) 필드가 없다.** 따라서 "새로 신고된 거래"는 날짜 필드로 못 잡고, **이번 실행에서 받은 레코드 집합 − 지난 실행까지 본 집합**의 차집합으로만 잡힌다. → 상태 저장이 필수.
- **신고가/신저점은 API가 직접 안 준다.** 특정 단지+평형의 과거 가격 이력과 비교해 직접 계산해야 한다. → 관심 단지의 이력 캐시가 필요.

## 3. 확정된 설계 결정

| # | 결정 | 선택 | 근거 |
|---|------|------|------|
| 1 | 핵심 컨셉 | **주간 신규신고 다이제스트** | 매주 토요일, 지난주 이후 새 신고를 집계. 월 데이터지만 새 신고가 계속 누적되는 점 활용. 부동산은 주간 주기가 신호/노이즈 균형에 적합 |
| 2 | 지역 범위 | **핵심 관심구 5~10개** | 단지별 신고가 추적이 현실적, 쿼리·이력 캐시 부담 작음 |
| 3 | 글 성격 | **하이브리드** (코드가 표·숫자 계산, AI는 짧은 시황만) | 실거래 숫자는 100% 정확해야 함. AI 숫자 hallucination 차단 (검증에서 claude 운반 충실성 확인됨) |
| 4 | 데이터 경로 | **`claude -p` + MCP** (운반책으로만) | 사용자 선택. claude는 raw JSON 운반만, 계산은 파이썬이 → 하이브리드 원칙 유지. **동작 검증 완료(§8)** |
| 5 | 출력 채널 | **Telegram + Blogger 동시** | 기존 봇과 동일한 풀 파이프라인 |

부수 파라미터(전부 `config.py`에서 수정 가능):

| 항목 | 기본값 |
|------|--------|
| 실행 시각 | **매주 토요일 08:00** (`investment_bot.py`에 1줄 등록) |
| 관심구 기본 | 서울 강남·서초·송파·마포·용산·성동 (6개) |
| baseline 윈도우 | **36개월** → 신고가 라벨은 "최근 3년 최고가"로 정직하게 |
| `num_of_rows` | **1000** (월 거래 누락 방지) + `total_count` 초과 시 완전성 경고 로그 |
| 평형밴드 | `round(전용면적_㎡)` 그룹 (84.96, 84.99 → 같은 "84밴드") |
| 대상 블로그 | config `REALESTATE_BLOG`, 기본 **`ogusinvest`** (투자 블로그) |

### 관심구 선정 모델

watchlist는 코드 로직이 아니라 `config.py`의 **명시 리스트(구명 → region_code)**다. 선정 기준은 **사용자의 관심/시장 중요도**이며, 미리 전부 확정할 필요 없이 언제든 **코드 변경 0**으로 추가·삭제한다 (`get_region_code`로 코드 조회 후 등록). 경기도 주요 시도 동일하게 **시군구 단위 region_code**로 추가 가능 (예: 성남 분당, 수원 영통, 고양 일산동/서, 용인 수지, 안양 동안 — 구 단위). 단 대상이 늘수록 주간 claude-p 호출 수가 비례 증가하므로 "핵심 집중"을 권장.

**자동 선정(거래량/평균가 상위 K개 동적 선택)은 v1에서 제외:** ① 신고가 추적은 대상이 고정돼야 일관성 유지, ② 후보 풀 전체를 매주 조회해야 해 호출 비용 폭발, ③ "주요"의 기준이 주관적. → v2 후보.

## 4. 아키텍처 / 주간 파이프라인

```
토요일 08:00 스케줄 (investment_bot.py)
  │
  ├─[1] 수집 — fetcher.py (claude -p + MCP, 운반책)
  │     관심구 N개 × {이번달, 지난달} get_apartment_trades 호출 (30일 신고창 커버)
  │     claude는 raw items JSON만 <<<JSON>>>…<<<END>>> 사이에 그대로 출력 (계산·요약 금지)
  │     봇이 sentinel 사이 JSON 파싱 + 스키마 검증 → 실패 시 재시도 N회
  │
  ├─[2] diff + 신고가 판정 — store.py + detector.py (파이썬, 결정적)
  │     baseline 스냅샷(삽입 前) 확보
  │     record_key = (구,단지,법정동,면적,층,계약일,가격)
  │     new = INSERT OR IGNORE 후 실제 삽입된 행 = "지난 실행 이후 새로 신고된 거래"
  │     각 new 레코드를 (단지,평형밴드)별 36개월 max/min 과 비교:
  │        price > max → 🔼 신고가 (경신 %, "최근 3년 최고가")
  │        price < min → 🔽 신저점
  │        이력 없음   → "신규 단지/평형" (판정 보류)
  │
  ├─[3] 표·집계 빌드 — digest.py
  │     신고가→신저점→일반 순 정렬, 구별 그룹핑, markdown 표
  │
  ├─[4] AI 시황 — commentary.py (gemini_cli, 1회, 짧게)
  │     계산 끝난 표·집계만 입력 → 2~3문단 코멘트 (숫자 재계산 금지)
  │
  └─[5] 출력
        markdown → convert_md_to_html_via_claude(Claude가 HTML화) → blogger_uploader (REALESTATE_BLOG)
        + telegram_notifier 요약 알림
```

## 5. 모듈 구조 (news_bot/·sector_bot/ 컨벤션)

```
006_auto_bot/001_code/
├── realestate_bot.py          # RealEstateBot 클래스 + --once/--test/--backfill, main()
├── realestate_bot/
│   ├── __init__.py
│   ├── config.py              # 관심구 watchlist, 평형밴드, baseline 윈도우, 실행시각, REALESTATE_BLOG
│   ├── fetcher.py             # claude -p + MCP 운반책: (region,ym)→raw items[] JSON, 검증·재시도
│   ├── store.py               # SQLite: transactions 단일 테이블, diff·baseline 도출
│   ├── detector.py            # 신고가/신저점 판정 — 순수함수, 결정적 (단위테스트 핵심)
│   ├── digest.py              # 표·집계 빌드 + 정렬 → markdown
│   └── commentary.py          # AI 시황 (gemini_cli, 계산된 표만 입력)
└── data/realestate/molit.db   # 상태 저장 (루트 .gitignore의 data/ 패턴이 커버)
```

기존 `shared/` 재사용 (신규 제작 없음):

| 용도 | 재사용 |
|------|--------|
| MD→HTML | `shared/claude_html_converter.convert_md_to_html_via_claude` (최종 HTML은 Claude가 변환) |
| Blogger 업로드 | `shared/blogger_uploader` + `shared/blogger_html_inject` |
| Telegram 알림 | `shared/telegram_notifier` |
| AI 시황 | `shared/gemini_cli.call_gemini_with_fallback` |

각 유닛의 책임/인터페이스:

- **fetcher.py** — `fetch_region(region_code, year_month) -> list[dict]`. claude -p 운반책. 입력 외엔 상태 없음. 실패는 예외로.
- **store.py** — `RealEstateStore(db_path)`: `baseline_snapshot(group_keys) -> dict`, `insert_new(records) -> list[record]`(실제 삽입분=신규), `prune/window` 헬퍼. SQLite만 의존.
- **detector.py** — `classify(record, baseline) -> Verdict(kind∈{HIGH,LOW,NEW,NORMAL}, pct, ref_price, ref_date)`. 순수함수, I/O 없음.
- **digest.py** — `build(classified_records) -> Digest(markdown, telegram_text, counts)`. 순수 변환.
- **commentary.py** — `comment(digest_summary) -> str`. gemini 1회.
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
  first_seen_date TEXT           -- 봇이 처음 본 날 (=신고 포착일 근사)
);
CREATE INDEX IF NOT EXISTS idx_group ON transactions(region_code, apt_name, area_band, trade_date);
```

- **신규(diff)**: `INSERT OR IGNORE` 후 `changes()`/RETURNING 으로 실제 삽입된 행 = 새로 신고된 거래. 별도 seen_keys 집합 불필요.
- **baseline**: `SELECT max(price_10k), min(price_10k), ... FROM transactions WHERE region_code=? AND apt_name=? AND area_band=? AND trade_date >= date('now','-36 months')`.
- **멱등성**: PK가 record_key → 같은 실행을 두 번 돌려도 신규 0건.
- **자기치유**: 어느 주에 한 구를 못 가져와도 상태는 누적만 하므로, 그 거래는 다음 정상 실행 때 "새 신고"로 포착된다.

## 7. 신고가/신저점 판정 알고리즘 (정밀)

1. 이번 실행에서 받은 레코드들을 그룹 `(region, apt, area_band)`로 묶는다.
2. **삽입 전에** 각 그룹의 36개월 baseline(max/min + 달성 계약일) 스냅샷을 뜬다.
3. 각 신규 레코드를 그 스냅샷과 비교:
   - `price > base_max` → **🔼 신고가**, 경신율 `=(price/base_max−1)×100%`, 비교 대상 "직전 최고 base_max(달성일)". 라벨 "최근 3년 최고가".
   - `price < base_min` → **🔽 신저점**, 동일 방식.
   - 그룹에 36개월 이력 없음 → **신규 단지/평형** (신고가 판정 보류, 표엔 포함).
   - 그 외 → 일반 신규 거래.
4. 판정이 끝난 뒤 신규 레코드를 INSERT (스냅샷 이후 삽입이므로 같은 실행 내 두 레코드가 서로의 판정을 오염시키지 않음).

정직성 규칙: 보유 이력이 약 3년이므로 "역대"가 아니라 **"최근 3년"**으로만 주장한다 (과장 금지 — 사용자 피드백 `feedback-no-hanja-narrative-headers` 정신과 동일선).

## 8. fetcher: `claude -p` + MCP (유일한 신규 통합점) — ✅ 동작 검증 완료(2026-06-02)

- 프롬프트(요지): *"get_apartment_trades 를 region_code=X, year_month=Y, num_of_rows=1000 으로 호출하라. 받은 raw JSON 객체만 `<<<JSON>>>` 와 `<<<END>>>` 사이에 그대로 출력하라. 요약·계산·코멘트 절대 금지."*
- 한 호출에 한 구의 한 달을 처리(가장 단순·견고). 주간 × 관심구 6개 × {이번달·지난달} ≈ 12회 subprocess. (2개월을 1호출에 묶는 건 최적화 옵션)
- 파싱: sentinel 사이 JSON만 추출 → `items[]` 필수필드(apt_name, area_sqm, floor, price_10k, trade_date) 스키마 검증 → 실패 시 재시도 N회.
- **완전성**: 응답의 `total_count > len(items)` 면 그 구·월은 일부 누락 → 경고 로그 (마포구 202605 실측 total_count=122; `num_of_rows`를 넉넉히 1000으로). 침묵 truncation 금지.

> ✅ **검증 결과 (2026-06-02).** 아래로 서브프로세스가 kr-realestate MCP를 실제 로드·호출하고, **직접 호출과 byte-identical한 raw JSON**을 sentinel 사이에 반환함을 확인 (운반책 충실성 입증, `--allowedTools` 불필요):
> ```
> claude -p --mcp-config <루트 .mcp.json> --dangerously-skip-permissions - <<'PROMPT'
> ...get_apartment_trades(region_code=11440, year_month=202605, num_of_rows=5) 호출 후
>    raw JSON만 <<<JSON>>>…<<<END>>> 사이에 출력...
> PROMPT
> ```
> 결과: `rc=0`, 출력 3줄(`<<<JSON>>>`/JSON/`<<<END>>>`), JSON은 직접 호출과 완전 동일(total_count=122 외 5건·summary 일치).
>
> **함정(봇 코드에 박제):** `--mcp-config <file>` 는 뒤따르는 토큰을 설정파일로 *greedy하게* 먹는다. stdin 마커 `-`(또는 프롬프트)를 바로 뒤에 두면 `MCP config file not found: -` 에러. → **`--mcp-config` 값 뒤엔 반드시 다른 플래그(`--dangerously-skip-permissions`)를 두고 `-`는 맨 끝에 배치.**

## 9. 빈 주 / 분량 정책

- 신규 신고 0건 → Telegram 1줄 "이번 주 신규 신고 없음", Blogger 발행 스킵.
- 신규는 있되 신고가/신저점 0건 → "이번 주 신고가 없음" + 신규 거래 요약. Blogger 발행은 신규 건수 임계치(config) 이상일 때만.
- 신고가/신저점 ≥1 → 풀 다이제스트 발행.

## 10. 에러 처리

- `investment_bot.py`의 `_safe_run`이 잡 전체를 감싼다 → 봇 실패가 다른 봇을 안 죽임.
- 구별 부분 실패 허용: fetcher가 한 구에서 N회 재시도 후에도 실패하면 그 구만 skip+로그, 나머지 구 진행. 누락분은 자기치유로 다음 주 포착.
- Gemini 429/503 → `call_gemini_with_fallback` 폴백 체인. 그래도 실패면 **시황 없이 표만 발행** (숫자는 항상 살아있음).
- claude -p 빈 출력/타임아웃/JSON 깨짐 → 재시도; 한 구 전부 실패면 그 구 skip.
- 멱등성으로 재실행 안전.

## 11. 테스트

- **detector.py** (핵심, 순수함수): 신고가 경계(`price>max`), 신저점(`price<min`), 동일가 tie, 이력 없음, 평형밴드 그룹핑, 경신율 계산.
- **store.py**: diff(신규=이번−지난), INSERT OR IGNORE 멱등성, baseline GROUP BY + 36개월 윈도우 정확성.
- **fetcher.py**: claude 출력 mock(정상/truncated/non-JSON/sentinel 누락) → 파싱·재시도. 실제 claude -p 미호출.
- **digest.py**: 정렬·그룹핑·빈 입력.
- **통합 스모크**: `--once --test`(업로드 스킵)로 1구 backfill→diff→digest 까지 무오류.

## 12. 단계적 구현 순서 (writing-plans 입력)

1. ✅ **spike (완료 2026-06-02)**: `claude -p --mcp-config` 로 한 구 1회 조회·파싱 성공 + 직접 호출과 동일 데이터 확인. (§8)
2. store.py + detector.py (+ 단위테스트) — 데이터 엔진 코어.
3. fetcher.py (운반책 + 검증·재시도, §8 함정 반영).
4. digest.py + commentary.py.
5. `--backfill` 로 관심구 36개월 초기 적재.
6. realestate_bot.py 오케스트레이션 + Telegram 출력 → `--once --test` 스모크.
7. Blogger 출력 결선.
8. `investment_bot.py` 에 `schedule.every().saturday.at("08:00").do(_safe_run, "RealEstate", bot.run)` 등록.

## 13. 의도적으로 제외 (YAGNI / v2 후보)

- 관심구 자동 선정(거래량 상위 동적 선택) — §3.1 사유. v2.
- 거래취소(계약 해제) 감지 — 지난주 있던 key가 이번 주 사라짐 diff. v2.
- 전월세(전세가율), 오피스텔/빌라 — 아파트 매매부터. v2.
- 청약·온비드 공매 (이벤트성, 별도 봇 컨셉).
- 관심구 동적 로테이션 / 전국 확장.
