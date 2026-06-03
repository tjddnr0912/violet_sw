# 부동산봇 (주간 전국 부동산 다이제스트)

매주 토 01:00 국토교통부(MOLIT) 실거래가를 수집·분석해 **전국 119시군구 아파트 시장 흐름 다이제스트**를 Blogger(OgusInvest) + Telegram으로 발행. `investment_bot.py` 통합 오케스트레이터가 토 01:00에 트리거(스케줄 태그 "부동산봇").

## 범위

- **수집(백필)**: `config.ALL_REGIONS` = 119시군구 = 서울 25 + 경기 44(시 단위) + 6대 광역시 50(구·군) + 세종 1. 4종(아파트 매매/전월세 + 오피스텔 매매/전월세), 36개월, **392만 행, DB 1.5GB**.
- **주간 발행**: v1은 서울 25구만, **v2(2026-06-04)부터 전국 119시군구** — 전국 단일 글(서울 상세 + 비서울 권역 요약).

## 실행

```bash
cd 006_auto_bot/001_code && source .venv/bin/activate
python weekly_realestate_bot.py --once [--test]   # 즉시 1회 (test=Blogger/HTML 스킵)
python weekly_realestate_bot.py --backfill 36     # 119시군구 × N개월 아파트 매매 백필
python weekly_realestate_bot.py --backfill-rents 36   # 아파트 전월세 백필
python weekly_realestate_bot.py --backfill-all 36     # 4종(아파트·오피스텔 × 매매·전월세) 일괄
```

## 모듈 (`realestate_bot/`)

| 모듈 | 역할 |
|------|------|
| `mcp_client.py` | kr-realestate MCP 서버 직접 spawn(stdio JSON-RPC) — **Claude 토큰 0**. 루트 `.mcp.json`의 `DATA_GO_KR_API_KEY` 사용 |
| `fetcher.py` | `extract_records` 정제(취소·무효 제외). claude-p 운반책은 대안(프로덕션 미사용) |
| `store.py` | SQLite(`data/realestate/molit.db`). diff(`insert_new`), 36개월 baseline, band_medians, `rent_volume` |
| `detector.py` | 신고가/신저점 판정 (단지·평형밴드 36개월 max/min 대비) |
| `indicators.py` | breadth·믹스보정 중앙가·세그먼트·전세가율 + **`rollup_groups`**(권역 집계+top movers) |
| `regions_extra.py` | 경기/광역시/세종 코드 + **`group_of`**(지역코드 2자리 prefix→권역명) |
| `publish_meta.py` | 제목 "날짜, N월 M주차 {AI 헤드라인}" + 7~9 동적 라벨 |
| `digest.py` | 전국 헤더 → 서울 상세 → 권역 요약 markdown |
| `commentary.py` | Gemini 전국 다문단 시황 (실패 시 빈 문자열 degrade) |

엔트리 `weekly_realestate_bot.py`(`build_report`·`synthesize`·`run()`).

## 블로그 글 구조 (전국 단일 글)

1. **전국 헤더** — 총 신규·신고가 비중 + 권역별 한 줄
2. **서울 (상세)** — 25구 온도차 표 + 신고가/신저점 단지 + 전세가율 + 오피스텔(매매+전월세)
3. **경기 (요약)** — 합산 신규·신고가비중·평균 전세가율·오피스텔 건수 + 뜨거운 시군구 top 5 + 하이라이트
4. **6대 광역시 (요약)** — 시별(부산·대구·인천·광주·대전·울산) 한 줄 + top 구 + 하이라이트
5. **세종 (요약)** + **시황 해석(Gemini, 전국 다문단)**

데이터 깊이: 서울 4종 / 경기·광역시 오피스텔 건수 / 세종 오피스텔 제외. 데이터 없는 권역은 degrade(섹션 생략).

## 핵심 개념

- **하이브리드**: 숫자는 전부 코드가 계산, 해석만 Gemini, HTML 변환만 Claude.
- **"신규 신고" = 차집합**: MOLIT엔 신고일 없음 → 이번 fetch ∖ 지난 DB(상태 저장 필수).
- **믹스보정 중앙가**: 같은 평형밴드끼리만 매칭·거래수 가중 MoM (믹스 착시 제거).
- **직접 MCP 경로**가 핵심 — claude-p 운반책은 (구,월)마다 레코드를 Claude 토큰에 2번 태워 한도 병목이었음. `MCPClient` 직접 spawn으로 Claude 0콜·세션 1개 완주.

## 환경변수 / 설정

- `SECTOR_BLOGGER_BLOG_ID`(=`REALESTATE_BLOGGER_BLOG_ID` 기본값 9115231004981625966, OgusInvest), `TELEGRAM_*`, `GEMINI_MODEL`. MOLIT 키는 루트 `.mcp.json`(gitignored).
- `BASELINE_MONTHS=36`("최근 3년"), `SCHEDULE_DAY/TIME`=saturday/01:00.
- **함정**: `load_dotenv(override=True)`가 `.env` 우선 → 실행 시 `TELEGRAM_ENABLED=false` 환경변수 무시(테스트 중 실제 발송 주의). `--test` 모드도 `build_report`는 DB insert함(델타 선점 주의).

## 운영 주의

- **첫 발행/재실행 0신규 가능**: 백필·이전 런이 최근월 델타를 이미 적재하면 `new_total=0` → 블로그 스킵(설계대로 Telegram만). 검증 발행하려면 "최근 완료월 델타 리셋"(예: 서울 아파트 해당월 DELETE 후 재실행 → "이번 델타"로 재분류).
- **incomplete 경고**는 MCP가 취소·무효거래 제외한 정상동작(손실 아님). total_count(원시) > items(정제).
- 백필은 멱등(`has_records_for_month` skip), 연속 5실패 fail-fast.

## 상세 설계·계획

- v1 스펙/계획: `docs/superpowers/{specs,plans}/2026-06-02-realestate-weekly-digest-bot*`
- v2 전국 확장 스펙/계획: `docs/superpowers/{specs,plans}/2026-06-04-realestate-national-digest-expansion*`
