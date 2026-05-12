# Casper 변경 이력

날짜순 (최신 위). 의사결정과 사고 패치 모두 포함.

---

## 2026-05-12 (2): P2 / P0 / P1 priority follow-ups

미구현 점검 결과(`현재 구현 안된 기능들`)를 받아 우선순위 P2 → P0 → P1을 일괄 도입. 모두 default OFF 또는 신규 옵션으로 안전 배포.

### P2 — QQQ primary signal source 일원화
- `config/strategy_params.json`: `mode.qqq_primary` (default `false`) 추가
- `src/bot.py::_handle_orb_forming` — qqq_primary 시 candidates=[QQQ만], dual_scan 무시
- `src/bot.py::_handle_scanning` — qqq_primary 시 `bear_fvg_for_sqqq` / `bull_fvg_for_tqqq`를 effective True로 강제 (TQQQ/SQQQ self-scan skip은 기존 로직 그대로)
- `src/bot.py::run()` 배너 + `strategy_info` dict — `QQQ-PRIMARY` 라벨/플래그
- `src/telegram/notifier.py::notify_bot_started` — `QQQ-PRIMARY` 표시
- `run_bot.py::_ict_status_line` — mode 인자 받아 `--status`에 표시
- `src/utils/config.py` — `ICT_QQQ_PRIMARY` env override
- 의미: bear/bull FVG mapping 둘 다 ON일 때 실질적으로 이미 QQQ-primary로 동작 중이었음. 본 플래그는 (a) TQQQ/SQQQ ORB 계산을 1회로 축소 (b) 흐름 명료화.

### P0 — 백테스트 simulate에 daily_bias 분기 통합
- `scripts/intraday_backtest_compare.py`: `compute_daily_bias` import, `strat_casper(daily_bias_skip_neutral=False)` 인자, `run_strategy`에서 일별 ctx['daily_bias'] 계산
- 신규 strategy variants:
  - `25_Casper_Full_Bias` — Full ICT + Daily Bias skip-neutral
  - `26_QQQ_Bear_Full_Bias` — Bear + Full ICT + Daily Bias skip-neutral
- 60일 표본에서는 25/26 모두 0건 (full ICT가 strict — `BACKTEST_AFTER_ICT.md` 기존 결과와 일치). 1년 데이터 누적 후 PF/MDD 차이 측정 가능.

### P1 — 상시 1분봉 수집 (5m 옆 별도 partition)
- `src/data/store.py`: `save_minute_bars` / `load_minute_bars` / `has_minute_data` — 경로 `<base>/<sym>/1m/<year>/<date>.parquet` (5m와 완전 격리)
- `src/data/collector.py`: `_Job.interval`, `submit(..., interval="5m"|"1m")`, `_run()` 분기
- `src/bot.py::_record_bars_1m` 헬퍼 + cold-start 1m warm-up과 scanning 시점 1m fetch 모두 collector에 제출
- `DATA_COLLECTION=on` 환경에서 5m와 1m 동시 누적
- Multi-TF SL 효과 누적 검증 + 향후 1분봉 백테스트의 기반

### 테스트
- `tests/test_ict_env_override.py` +3 — `ICT_QQQ_PRIMARY` on/off/unset
- `tests/test_data_collector.py` +2 — 1m partition isolation, 5m+1m coexist
- 회귀 73/73 통과 (bot_collector_integration, bot_states, data_collector, data_store, data_store_daily, ict_env_override)

### 운영 영향
- 봇 재시작 시 동작 변화 없음 (모든 신규 플래그 default OFF)
- 활성화 방법:
  - `ICT_QQQ_PRIMARY=on` 또는 `config/strategy_params.json::mode.qqq_primary=true`
  - `DATA_COLLECTION=on` (기존 env) — 자동으로 1m도 누적
  - 백테스트 25/26은 1년 데이터 누적 후 의미 있음

## 2026-05-06 (2): trend label as info-only in dual scan

dual scan 모드에서 QQQ MA20 trend는 거래 결정에 0% 기여하지만 알림·로그에서는 단일 모드와 동일하게 "Trend: BULL → TQQQ"로 표시되어 의도가 모호. 사용자 지적으로 라벨 명시화.

- `src/telegram/notifier.py::notify_pre_market(... dual_scan: bool = False)` — dual_scan=True에서 "Trend (info only): BULL — dual scan ignores this for entry"로 표시
- `src/bot.py::_handle_pre_market` — 로그도 동일 분기. dual=true 시 "trend=BULL (info only — dual scan ignores trend for entry)"
- trend 계산 자체는 유지: `mode.dual_scan=false` fallback 시 거래 방향 결정자로 자동 복귀
- 67건 단위 테스트 통과 (notifier/bot_states/bot_advanced)
- 옵션 검토: A(현재, 라벨만 명시) vs B(dual에서 trend 계산 skip). A 채택 — fallback 안전성 + KIS API 1회 호출은 운영 부담 미미

## 2026-05-06: ORB-FVG strict + dual scan default

원본 영상(Casper SMC / Jesse Rogers, "6 Figure ICT Trading Strategy")의 핵심 트리거 — **FVG가 ORB 라인을 가로지를(intersect) 때만 유효** — 가 코드에 누락돼 있었음. 사용자 지적으로 발견 → 외부 검증(FMZ Quant 공식 정의) → 강화 조건 도입.

- `src/core/fvg.py::check_breakout_with_fvg(..., strict=False)` — strict=True에서 두 조건 추가:
  - (S1) displacement 캔들 몸통이 ORB 가로지르기: `Open <= orb_high <= Close`
  - (S2) FVG zone이 ORB 라인 포함: `fvg.bottom <= orb_high <= fvg.top`
- `src/bot.py::_handle_orb_forming` / `_handle_scanning` — dual leg(TQQQ+SQQQ) 동시 ORB 계산 및 스캔, 첫 풀백 측 진입. trend mode는 `mode.dual_scan=false`로 fallback 가능
- `config/strategy_params.json`: `entry.strict_fvg=true`, `mode.dual_scan=true` 추가. R:R 1:3 유지
- `run_casper.sh` 헤더 + 텔레그램 BOT STARTED — scan/fvg 모드 표시
- 백테스트(60일, R:R 1:3, 비대칭 수수료 0.65%):
  | 모드 | 거래 | 승률 | PF | 순손익 | MDD |
  |------|---:|---:|---:|---:|---:|
  | dual baseline | 37 | 18.9% | 1.10 | +$5.41 | -5.78% |
  | dual + strict | **13** | **23.1%** | **2.01** | **+$18.94** | **-2.83%** |
- 가짜 시그널 ~70% 제거. SQQQ Long FVG = QQQ Bearish FVG 의미 검증됨 (strict dual에서 SQQQ 6/13건 정상 작동)
- 단위 테스트 310건 전부 통과. `test_overnight.py::TestOrbRetry`만 dual leg semantics에 맞춰 assertion 업데이트 (call_count 2→4)
- 상세 → [STRATEGY_REVIEW.md](strategy/STRATEGY_REVIEW.md), 진단 미스 → [TROUBLESHOOTING.md](TROUBLESHOOTING.md#전략-문서의-핵심-조건이-구현에서-누락)

## 2026-05-01: commission 0.25% + R:R 1:3

- `commission.rate_per_side`: 0.0009 → 0.0025 (사용자 실계좌 기준)
- `entry.rr_ratio`: 2.0 → 3.0
- BE move 자동 영향: BE target이 entry × 1.00180 → 1.00501로 상승, 실 commission cover
- 백테스트 검증 (60일): trend 1:2 PF 2.64 → trend 1:3 PF 3.19, 순손익 +34%
- 상세 분석 → [CONFIGURATION.md#rr-13--commission-025-튜닝](CONFIGURATION.md)

## 2026-04-30: KIS multi-lens 감사 + 4개 패치

`superpowers:dispatching-parallel-agents`로 4-lens(API 계약 / 자본 수학 / 상태머신 / 거래소 규칙) 동시 감사. 40 findings 중 5건 패치:

- `eff_price`에 commission 포함 (`price × (1 + slip + comm_rate)`)
- `max_position_pct`: 1.0 → 0.99 (안전 floor)
- `sell_slippage_pct`: 0.01 → 0.03 (fast-drop 미체결 방지)
- 매수 성공 직후 `_save_position_state()` 즉시 호출 (orphan 방지)
- 부분체결 재매도 시 `get_us_today_executions(order_no)` 합산 (더블 매도 방지)
- Token backoff 중 stale 토큰 silent 사용 → 빈 문자열 + CRITICAL 로그

## 2026-04-29: 포지션 사이징 vs limit price mismatch 수정

- `int(capital/price)` → `int(capital/eff_price)` (`eff_price = price × (1 + buy_slippage)`)
- TQQQ signal $61.01 / 사이징 51주 / 주문 51 × $61.66 = $3144 > 자본 $3128.22 → 거부 → DONE_TODAY 사고 재발 방지
- 백테스트 영향: 25거래 중 2거래 1주 감소, 60일 자본 차이 0.04%

## 2026-04-23: Freqtrade gap review 작성

- `docs/strategy/FREQTRADE_GAP_REVIEW.md` 추가
- E1~E4 실전 사고 기반 운영 격차 평가 (전략 불변, 운영 완성도만 검토)
- 핵심 제안: launchd watchdog, Telegram `/halt`, Pydantic config 검증, filter verdict 로그

## 2026-04-14: .env IFS='=' trailing-byte 수정

- `run_casper.sh`의 `while IFS='=' read` → `while IFS= read` + parameter expansion
- base64 padding으로 끝나는 secret이 1 byte 잘리는 함정 제거
- 이중 방어: Python `load_dotenv(env_path, override=True)` 추가

## 2026-04-13: KIS cold-start lockout 대응

- `KISClient.warm_up(max_secs=90, poll_interval=10)` 추가
- 봇 기동 후 첫 15~60초 KIS HTTP 500 priming 지연 우회
- 내장 retry(7s)로 못 뚫던 lockout 해결

## 2026-04-11: KIS 토큰 backoff 도입

- `kis_auth.py`에 `_BACKOFF_SCHEDULE` (60s→5m→15m→30m→1h)
- KIS 일시 장애에서 재시도 루프가 rate limit을 때려서 며칠간 lockout되던 사고(2026-04-13) 패치
- 성공 시 카운트/백오프 자동 리셋

## 2026-04-02: 초기 설계

- ORB(15분) + FVG + Pullback 전략
- TQQQ/SQQQ Long-Only
- R:R 1:2, commission 0.0009 (초기 가정)
- 09:45~10:55 ET 스캔, 15:50 강제청산
- 상세 → [superpowers/specs/2026-04-02-casper-bot-design.md](superpowers/specs/2026-04-02-casper-bot-design.md)
