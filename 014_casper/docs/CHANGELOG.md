# Casper 변경 이력

날짜순 (최신 위). 의사결정과 사고 패치 모두 포함.

---

## 2026-05-14: Scenario B 적용 — 킬존 확장 + 시간대별 RR

PHASE1_PRECHECK의 AM_MACRO-only 결정이 n=11 표본에 기반해 통계적으로 약했고, "AM_LATE 진입 차단으로 23:10~23:55 = 45분간 빈 스캔"이 발생하던 비효율을 해소.

### 변경
- `config/strategy_params.json`:
  - `allowed_killzones`: `["AM_MACRO"]` → `["AM_MACRO", "AM_LATE"]`
  - 신규 `rr_ratio_by_killzone`: `{"AM_MACRO": 3.0, "AM_LATE": 2.0}`
  - 기존 `rr_ratio: 3.0`은 기본값/fallback 으로 유지
- `src/core/strategy.py::scan_for_signal`:
  - 신규 인자 `rr_by_killzone: Optional[dict]`
  - breakout 캔들의 killzone에 따라 effective RR 결정 → `take_profit = entry ± risk × effective_rr`
  - `signal_emit` 로그에 `killzone`/`rr_default`/`rr` 동시 기록 (사후 분석용)
- `src/bot.py`:
  - `scan_for_signal` 호출부에 `rr_by_killzone=entry_params.get("rr_ratio_by_killzone")` 전달
  - 시작 배너 윈도우 종료시각 = `max(KILLZONES[k][1] for k in allowed_killzones)` (이전엔 항상 10:55로 하드코딩)
  - `notify_scan_start`에 `rr_default`/`kz_segments` 전달 → 텔레그램에 zone별 RR 분리 출력
  - `notify_killzone_end_no_signal`에 `kst_window` 동봉
  - `notify_entry`에 `killzone` 인자 추가
- `src/telegram/notifier.py`:
  - `notify_scan_start(kz_segments)`: zone별 KST 윈도우 + RR 라인 추가 출력
  - `notify_bot_started`: `rr_ratio_by_killzone` 노출, allowed_killzones 기준으로 윈도우 끝 시각 정정, zone≥2일 때 zone별 KST/RR breakdown 추가
  - `notify_signal`: `KZ:{name}→RR=1:{rr}` 라벨, reward $/sh 명시
  - `notify_entry`: total risk·reward 금액 + killzone 라벨
  - `notify_killzone_end_no_signal`: kst_window + 탈락 사유 분포(`reasons` dict) 옵션
- `run_casper.sh`:
  - RR_SUMMARY 라인 추가 (`R:R default 1:3 (AM_MACRO=1:3, AM_LATE=1:2)`)
  - WINDOW_INFO 헬퍼가 `allowed_killzones` 기준으로 윈도우 끝 계산 + zone별 KST/RR을 들여쓰기 줄로 출력 (foreground + daemon 양 경로)

### 신규 산출물
- `scripts/killzone_scenarios.py` — 7개 시나리오 백테스트 (BASE/A/B/C1/C2/D1/D2)
- `scripts/check_killzone_rr.py` — Scenario B smoke 검증 helper (macro=3.0, late=2.0, fallback=3.0)
- `docs/CHECKLIST.md` — 16개 항목 검증 체크리스트 (function/scenario/system 3계층)

### 검증
- 542/542 unit tests pass (5분 43초)
- 체크리스트 16/16 pass (1회 fail → helper sys.path 누락 수정 후 2회차 통과)
- 라이브 봇 재기동 확인: PID 96955, KIS warm-up 1회 성공, 배너에 `R:R default 1:3.0 (AM_MACRO=1:3.0, AM_LATE=1:2.0)` 및 zone별 윈도우 정상 출력

### 백테스트 결과 (60일 TQQQ, 참고용)
- BASE(MACRO만, RR=3): 2건, 0% WR, -0.01% — 모두 BE 청산
- A(KZ 확장, RR=3): 4건, 0% WR, -0.02% — AM_LATE 추가분도 BE
- **B(KZ 확장 + split RR)**: 4건, 0% WR, -0.02% — 이 60일 표본에선 RR=2 TP도 도달 X
- BE OFF (D1/D2): 50% WR 나오지만 손실폭 더 큼 → BE shift는 유지 필수

→ 60일 백테스트로는 셋 다 통계 무의미. **선택 근거는 "23:10~23:55 빈 스캔 제거 + RR=2로 TP 도달 가능성 부여"라는 정성적 개선**. 1년 데이터 누적 후 재평가 권장.

### 비고
- `rr_by_killzone=None` (이전 호출 경로, 외부 코드)에서 기존 동작 (`rr_ratio` 단일값) 완전 호환 — fallback 검증됨
- breakout 캔들 시각 기준 zone 분류 (pullback/entry 시각이 다음 zone에 떨어져도 영향 없음)
- 기존 11건 trade history는 Scenario B 적용 전이라 `ict.rr_ratio` 필드 없음 — 다음 시그널부터 적용

---

## 2026-05-13: 장 초반 데이터-부족 reject 해결 워크플로 (Day 1~3) + 1m backfill today-guard

전날 09:55 KST 22:55 QQQ bear setup이 Sweep+CHoCH 단계에서 reject된 사고 분석 결과 — 당일 09:30 이후 5분봉 5개로는 fractal swing 0~1개라 CHoCH 게이트 자체가 동작 불가. 보강 4단계 진행.

### Day 1 — yfinance prepost=True + premkt swing fractal (default ON)
- `src/data/market_data.py::get_intraday_bars(..., prepost=False)` 인자 추가. `_get_intraday_yf`로 propagate (prepost=True 시 KIS 우회, yfinance 04:00~20:00 ET 커버리지)
- `src/bot.py::_handle_scanning`에서 `entry.use_premkt_history=true`면 별도 `get_intraday_bars(prepost=True)` 호출 후 06:00 cutoff로 ghost wick 차단 → `history_bars`로 전달
- 효과: 09:55 시점 swing source가 5바 → ~60바로 확장. CHoCH 게이트가 의미 있게 동작 (premkt swing low를 break하는 본격 ICT bear reversal 검출 가능)
- `ICT_USE_PREMKT_HISTORY` env override + 4-channel sync (logger / status / telegram / bash header에 `PremktHist` flag)

### Day 2 — NQ session pools 단위 fix (잠재 버그 해결)
- 이전 M4 활성화에서 NQ futures 가격(30,000pt scale)을 QQQ 차트(700pt scale) `levels_up/down`에 그대로 prepend → `is_sweep_bar` 검증에서 single 조건(`c <= level`)으로 자동 reject. 실질 효과 0
- Fix: `_handle_pre_market`에서 `ratio = qqq_close / nq_last` 계산, asia/london/premkt 모두 변환 후 `self._session_pools` 저장
- 결정 로그(`session_pools_computed`)에 ratio/nq_last/qqq_close 포함 → 사후 감사 가능

### Day 3 — PDH/PDL을 sweep pool에 추가 (default ON)
- `scan_for_signal(..., use_pdh_pdl_pool, pdh_pdl)` 신규 인자
- `levels_up.insert(0, pdh)`, `levels_down.insert(0, pdl)` — sweep 검출기 first-hit 최우선순위
- `pdh_pdl_pool` 결정 로그 이벤트
- `self._daily_bias.pdh/.pdl` 자동 재사용 (Daily Bias 계산 시 추출된 값)
- ICT 정통 흐름의 가장 핵심 풀(yesterday's RTH high/low). Phase 1 사전 검증의 약한 상관은 11건 표본 한계로 추정 — 30~50건 누적 후 재검증
- `ICT_USE_PDH_PDL_POOL` env override

### premkt 5분봉 누적 저장 (분석/백테스트 인프라)
- `src/data/store.py::save_premkt_bars/load_premkt_bars/has_premkt_data` — 5m partition과 격리된 `data/marketdata/<sym>/5m_premkt/<year>/<date>.parquet` 신규 partition
- BarCollector `interval="5m_premkt"` 분기 추가 (`save_premkt_bars` 라우팅)
- `_record_bars_premkt` 헬퍼 + scan loop에서 06:00~09:29 슬라이스만 submit
- 매 매매 사이클마다 자동 누적 → 향후 backtest engine에 premkt history 통합 시 활용 가능

### Minor — 1m yfinance backfill `today` skip 가드
- 봇 cold start 시 `possibly delisted; no price data found (1m 2026-05-13 -> 2026-05-14)` 경고 발생
- 원인: yfinance는 미국장 RTH 시작 전 오늘 1m 데이터를 빈 응답 + 잘못된 "delisted" 경고로 반환
- 두 단계 가드:
  - `fill_minute_gaps_from_yfinance` 내부: `day >= today` skip (호출자 보호)
  - `_cold_start_backfill`: `end_1m = end - 1` (오늘 제외, 8일 retention 유지)
- 오늘 1m 데이터는 live streaming 경로(scan-window fetch + `_record_bars_1m`)가 자동 누적
- 신규 단위 test: `_fetch_yf` mock이 today에 대해 호출되지 않음 검증

### 4-channel sync (logger / strategy_info / telegram / bash header)
모든 신규 flag (`PremktHist`, `PDH/PDL`)가 4채널 모두 동일 라벨로 표시. 봇 재시작 시 BOT_STARTED에서 14개 ICT 플래그 모두 가시화.

### 활성화
- `config/strategy_params.json`: `use_premkt_history=true`, `use_pdh_pdl_pool=true` 설정
- `use_session_pools=true`는 이미 ON이라 Day 2 fix는 봇 재시작 시 자동 적용
- 봇 재시작 후 검증 완료 (2026-05-13 15:36:58 KST): 14개 ICT 라벨 4채널 일치, 1m delisted 경고 사라짐

### 테스트
- env override +4 (premkt_history on/off, pdh_pdl_pool on/off)
- market_data prepost +2 (KIS bypass when prepost=True, default RTH preserved)
- 1m today-skip 가드 +1
- collector premkt partition +2 (격리, 3종 partition 공존)
- 통합 회귀 118/118 (영향 모듈)

## 2026-05-12 (3): M3/M4 활성화 + 헤더 동기화 + 백테스트 측정 도구

거래 영향 없는 측정·검증 인프라 보강 일괄 도입. 모든 사용자 확정에 따라 M3/M4는 default ON으로 활성화 후 봇 재시작.

### M3 — EQH/EQL pools를 sweep 로직에 결합 (활성화됨)
- `src/core/strategy.py`: `equal_levels` import, `scan_for_signal`에 `use_eqh_eql_pools` / `eqh_eql_pct` 인자. EQH (두 swing high 0.05% 이내) 평균 가격 → `levels_up` 앞쪽, EQL → `levels_down` 앞쪽 prepend. sweep 검출기 first-hit 우선
- `config/strategy_params.json`: `entry.use_eqh_eql_pools=true` / `entry.eqh_eql_pct=0.0005` (default ON)
- `ICT_USE_EQH_EQL_POOLS` / `ICT_EQH_EQL_PCT` env override
- `ict_log` 이벤트: `eqh_eql_pools`

### M4 — 세션 풀 (Asia/London/Premkt) (활성화됨)
- `src/data/futures.py`: `premarket_session_range()` 신규 (06:00~09:30 ET)
- `src/bot.py::_handle_pre_market`: `use_power_of_3` 또는 `use_session_pools=true`일 때 NQ futures 1회 fetch, asia/london/premkt high·low 계산 → `self._session_pools`. P3와 NQ 데이터 공유 (재호출 0)
- `src/core/strategy.py`: `scan_for_signal`에 `use_session_pools` / `session_high_low` 인자. 세션별 high → `levels_up` 앞, low → `levels_down` 앞
- `config/strategy_params.json`: `entry.use_session_pools=true` (default ON)
- `ICT_USE_SESSION_POOLS` env override
- `ict_log` 이벤트: `session_pools_computed`, `session_pools`

### 봇 가동 확인 (22:14:51 KST)
- `Session pools: asia=(29455.75,29227.00) london=(29292.25,29174.00) premkt=(29250.25,29113.00)`
- `ICT : KZ(AM_MACRO) + Disp + Sweep + Bias + QQQ→SQQQ + QQQ→TQQQ + OTE(0.705) + Unicorn + MTF-SL + P3 + EQH/EQL + SessionPools`

### run_casper.sh 헤더 4-channel sync
- start/daemon 두 path 모두 동일한 ICT flag logic으로 통일 — 옛 5개 라벨 → **신규 12개 플래그 모두 표시**
- scan_mode 표시에 `QQQ-PRIMARY` 우선 분기 추가
- 이전 사고(`TROUBLESHOOTING.md`의 "Telegram 4-channel UI sync 누락")와 같은 패턴 재발 — bash 헤더가 logger보다 뒤늦게 갱신된 케이스. 4-channel sync는 단발성 cleanup가 아니라 라벨 추가 시 매번 확인 필요.

### H1 — 백테스트 SQQQ leverage 매핑 (거래 미영향)
- `scripts/intraday_backtest_compare.py::Sig` 에 `leverage_multiplier: float = 1.0` 필드
- `simulate_trade`: net/gross/slip을 `leverage_multiplier`로 scale, r_multiple은 ratio 보존 (분자/분모 모두 scale)
- 신규 strategy variants: `27_QQQ_Bear_SQQQ_Lev`, `28_QQQ_Bear_FullICT_Lev` (LEV_FACTOR=2.85, `src/core/exec_mapper.py`와 일치)
- 검증: 23번 `QQQ_Bear_Short` `Ret -2.89%` → 27번 `QQQ_Bear_SQQQ_Lev` `Ret -8.04%` ≈ **2.78× scale** (≈2.85 leverage)

### M2 — 1m yfinance 부분 backfill (거래 미영향)
- `src/data/backfill.py`: `_fetch_yf(interval=)` 인자 추가, `fill_minute_gaps_from_yfinance` 신규, `YF_1M_RETENTION_DAYS=8`
- `src/data/gap_finder.py`: `find_minute_gaps` — 1m 파티션 독립 점검
- `src/bot.py::_cold_start_backfill`: TQQQ/QQQ/SQQQ 1m 8일 gap 자동 backfill (DATA_COLLECTION 무관, always-on)
- 1m partition `data/marketdata/<sym>/1m/<year>/<date>.parquet`에 적재 — 5m partition 미영향

### 테스트
- `tests/test_ict_env_override.py` +3 (eqh_eql, session_pools, both off)
- `tests/test_futures.py` +2 (premarket_session_range)
- `tests/test_data_backfill.py` +2 (1m write, 8일 한계)
- `tests/test_data_gap_finder.py` +2 (1m partition independence)
- 회귀 86/86 (bot_states, bot_advanced, integration, strategy, strategy_phase2/3, overnight, collector_integration)

### 운영 영향
- M3/M4 활성화 후 봇 재시작 (LIVE PID 96986 종료 → 신 PID로 22:14:45 시작)
- H1/M2는 백테스트·데이터 인프라 — live 미영향
- 헤더 동기화는 다음 봇 재시작부터 신규 라벨 표시

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
