# Casper 변경 이력

날짜순 (최신 위). 의사결정과 사고 패치 모두 포함.

---

## 2026-06-04: trend 버킷 요약에 BIL(안전자산) 표시 + drift 정상화 (표시 버그 수정)

### 결정 한 줄
vol-target trend sleeve는 TQQQ+BIL을 동시 보유하는데, 포트폴리오 요약의 버킷 값 계산(`_bucket_value`)이 qty>0 **첫 종목(=TQQQ)만 반환**해 BIL leg를 통째로 누락 → 데일리 요약에서 BIL 불가시 + trend 평가금액 과소(예: $524, 실제 TQQQ+BIL $616) + drift 왜곡(−18% 표시, 실제 ~−4%). 두 종목을 **합산**하고 라벨을 `"TQQQ+BIL"`로 결합 반환하도록 수정.

### 변경
- `src/core/portfolio.py`: `_bucket_value`의 trend/tqqq_sma 브랜치 병합 — (TQQQ, BIL) 첫-매치 반환 → **합산 + `"TQQQ+BIL"` 라벨**, 둘 다 `claimed_symbols` 등록.
- `src/telegram/notifier.py`: `notify_portfolio_summary` Symbol 컬럼 폭 6→9(divider 47→50)로 결합 라벨 정렬 보존.
- `tests/test_multi_bucket.py`: 신규 2건(양쪽 보유 합산 / BIL-only 가드). 전체 624 passed.

### 근거
2026-06-04 사용자가 "13시 요약에 BIL이 왜 안 보이나"라고 질문. 로그(`2026-06-01 23:36 BUY BIL x1 @ $92.31`, 이후 매도 0)로 BIL은 보유 중·표시만 누락으로 확정. **표시 전용 수정 — 매매 로직·보유 자산 무관**(trend는 자체 월간 스케줄로만 리밸런스, `needs_rebalance`가 trend 제외). 상세·진단 미스 → [TROUBLESHOOTING.md](TROUBLESHOOTING.md) "데일리 포트폴리오 요약에 trend sleeve의 BIL… 안 보임".

---

## 2026-06-02: 메인 루프 busy-loop 수정 (CPU 100% → idle)

### 결정 한 줄
`run()` 메인 루프의 `time.sleep(sleep_time)`이 `except Exception` 블록 안에만 있어, 정상 틱마다 sleep 없이 무한 질주(한 코어 ~100% 상시 점유)하던 것을 — 루프 바디를 `_loop_iteration()`로 추출하며 sleep을 매 반복 무조건 실행하도록 수정.

### 변경
- `src/bot.py`: `while True: try/except` 인라인 루프 → `while True: self._loop_iteration()`. 신규 `_loop_iteration()`은 tick 후 **항상** sleep(POSITION_OPEN 5초 / 그 외 30초), KeyboardInterrupt·SystemExit는 전파(graceful shutdown), 그 외 예외는 로그+알림 후 sleep.
- 신규 `tests/test_main_loop_sleep.py` (4): 정상 틱 sleep / POSITION_OPEN 5초 / 예외 후 sleep+알림 / SystemExit 전파. 전체 622 passed.

### 근거
2026-06-02 라이브 점검에서 봇 PID가 CPU 생애평균 99%(CPU시간≈경과시간)로 확인됨 — trend 모드는 틱 사이 30초 sleep이라 idle이어야 정상. 재시작 후 검증: CPU시간 0.95초/2분(≈0%), 순간 0%. 상세·진단 미스 → [TROUBLESHOOTING.md](TROUBLESHOOTING.md) "메인 루프가 CPU 한 코어를 100% 상시 점유".

---

## 2026-06-01: GEM/trend 월말 리밸런스 RTH 재시도 (보류분 자동 실행)

### 결정 한 줄
데일리 멀티버킷 틱이 ET 00:00(KST 13:00, 미국장 마감)에 발화해 GEM/trend auto 실행이 보류된 뒤 재시도되지 않던 갭을, `_seed_pending`을 미러한 `_gem_pending`/`_trend_pending` + `_tick` RTH 재시도로 해소.

### 변경
- `src/bot.py`: `_gem_pending`/`_trend_pending` 플래그 추가 — `__init__`에서 `should_run_*`로 arming(재시작·유예창 대응) + 장 마감 defer 시 arming, 실행으로 due 해소 시 disarm(부분 실패면 유지). `_tick`이 `is_market_open()`이면 `_retry_deferred_rebalance()` 호출. `_resolved_trend_mode()` 헬퍼로 TREND_MODE 해석 중복 제거 (e7fd22c).
- 신규 `tests/test_deferred_rebalance.py` (10): defer arms / execute disarms / 부분실패 유지 / alert·not-due disarm / 재시도 선택성 / `_tick` 게이팅. 전체 618 passed.

### 근거
seed만 RTH 재시도(`_seed_pending`)가 있고 GEM/trend엔 없어서, 봇을 계속 켜두면 월말 리밸런스가 영영 미실행(RTH 중 재시작 시에만 우연히 실행). 2026-06-01 실거래에서 5/29 trend 리밸런스가 KST 13:00 틱에서 보류된 채 미실행됨이 드러나 수정. 상세·복구 → [TROUBLESHOOTING.md](TROUBLESHOOTING.md) "trend·GEM 월말 리밸런스가 봇을 계속 켜두면 영영 실행 안 됨".

---

## 2026-05-31: 시작/상태 배너 sleeve_engine 인식 (배너 3곳 통일)

### 결정 한 줄
`sleeve_engine=trend`인데도 시작 로그·`status` 출력이 레거시 인트라데이 전략(ORB+FVG/ICT/Fine-tune)을 설명하던 문제를, 배너가 존재하는 3개 파일 전부에서 모드 분기하도록 수정.

### 변경
- `src/bot.py` `run()`: 인트라데이 상세를 `_log_intraday_startup_detail()`로 추출, trend용 `_log_trend_startup_detail()` 추가 → `sleeve_engine`으로 분기 (7535979, c0aeb58).
- `run_casper.sh`: `show_trend_banner()` 헬퍼 추가, `start_bot`·`start_daemon`이 `sleeve_engine!=intraday`면 호출·레거시는 else (e4a7bc2, 권한복구 25af01f).
- `run_bot.py` `show_status()`: `_print_trend_status()` 추가 → 분기 (ba38900).
- 신규 `tests/test_bot_banner_sleeve.py` (trend=인트라데이 상세 없음+trend 설명 / intraday=레거시 복원). 전략무관 누적통계 라인 유지.

### 근거
trend 전환(2026-05-30) 후 비활성 엔진 설명이 잔존 → 운용자 오인. 상세·진단 미스 → [TROUBLESHOOTING.md](TROUBLESHOOTING.md) "시작/상태 배너가 sleeve_engine=trend인데 레거시 인트라데이 전략을 설명".

---

## 2026-05-28: ICT sweep+CHoCH 게이트 default OFF (옵션 B 단계적 완화)

### 결정 한 줄
`config/strategy_params.json::entry.require_sweep_choch`를 **`true → false`**. env로 즉시 토글 가능(`ICT_REQUIRE_SWEEP_CHOCH=true`로 복구).

### 동기

5/6 마지막 매매 이후 **15거래일 연속 매매 0건** (5/7, 5/10~14, 5/15~16, 5/18~22, 5/26~27). 봇은 6거래일 모두 정상 가동(상태머신·필터·KIS 모두 OK), 차단은 100% ICT 풀스택 시그널 게이트 안.

`data/ict_decisions/*.jsonl` 분석:

| 거래일 | 평가 ~214회 | FVG-with-breakout | sweep_choch | signal_emit |
|---|---:|---:|---:|---:|
| 5/18 | ✓ | 0 | – | 0 |
| 5/19 | ✓ | 525 → 175 disp pass | 175 attempts / **175 fail (100%)** | **0** |
| 5/20 | ✓ | 54 → 18 disp pass | 18 attempts / **18 fail (100%)** | **0** |
| 5/21 | ✓ | 0 | – | 0 |
| 5/22 | ✓ | 0 | – | 0 |
| 5/26 | ✓ | 0 | – | 0 |
| 5/27 | ✓ | 0 | – | 0 |

이전 활성 기간(5/12~5/15) 같은 풀스택 ON 상태에서 sweep_choch 통과는 day당 3건 → signal_emit 36~52건 발생했던 점과 비교하면 sweep+CHoCH가 5월 후반 저변동성 시장에서 가장 큰 보틀넥. 5/19 175회 / 5/20 18회 모두 `reason="no sweep then CHoCH precursor"` — 단일 사유 100%.

### 적용 범위

- `config/strategy_params.json`: `require_sweep_choch: true → false`
- 코드 수정 없음. `src/core/strategy.py::scan_for_signal`은 이미 이 flag를 읽어 `require_sweep_choch=False`일 때 sweep+CHoCH 게이트를 우회.
- `src/utils/config.py::_apply_ict_env_overrides`의 `ICT_REQUIRE_SWEEP_CHOCH` env override 그대로 — 사용자가 임시 ON 복구 가능.
- `run_casper.sh` 시동 banner는 그대로(`_on('ICT_REQUIRE_SWEEP_CHOCH', ...)` 패턴). config flip만으로 banner의 `+ Sweep` 토큰이 자동 제거.

### 효과 추정 (가설, 다음 거래일에 검증)

5/19/5/20에 `displacement_check` 까지 통과했던 175 + 18 = 193 bar-evaluation이 sweep off 시 후속 게이트(`unicorn / OTE / multi-tf-SL / power_of_3`)로 진입. 이 후속 게이트의 통과율은 미측정이지만 5/12~5/15 비교 데이터로 보면 풀스택 전체 통과 ≈ 5~6%이 정상.

**한계**: 4일(5/18, 5/21, 5/22, 5/26)은 FVG-with-breakout 자체가 0회 → sweep off만으로 해결 X. 이 4일은 시장 변동성 회복(VIX > 20) 또는 `strict_fvg=false` 같은 추가 완화가 필요.

### 회귀 검증

`pytest tests/test_config.py tests/test_ict_env_override.py tests/test_strategy.py tests/test_strategy_phase2.py tests/test_strategy_review.py tests/test_notifier.py tests/test_notifier_stages.py` — 78/78 통과.

Banner 시뮬레이션:
```
AFTER:  ICT : KZ(AM_MACRO,AM_LATE) + Disp + Bias + QQQ->SQQQ + QQQ->TQQQ
              + OTE(0.705) + Unicorn + MTF-SL + P3 + EQH/EQL + SessionPools + PremktHist + PDH/PDL
              (Sweep 자동 제거)
```

### 재활성 가이드 (임시/실험용)

```bash
# 임시 sweep 복구
echo 'ICT_REQUIRE_SWEEP_CHOCH=true' >> .env
./run_casper.sh stop && ./run_casper.sh daemon --yes
# banner 의 ICT 라인에 다시 + Sweep 토큰이 나오는지 확인

# 영구 복구
# config/strategy_params.json::entry.require_sweep_choch 를 true 로 되돌리고 .env 라인 삭제
```

### 모니터링 (다음 7거래일)

- KST 22:30 banner의 `ICT :` 라인에서 `Sweep` 토큰 부재 확인
- KST 23:55 직후 `data/ict_decisions/<date>.jsonl`의 `signal_emit` event count 확인
  - `count > 0` → setup 감지 → telegram `🎯 Setup detected` 알림 발생 예상
  - `count == 0` 가 다시 7일 연속이면 strict_fvg 또는 require_displacement도 검토 대상
- 5건 매매 누적 시 `python scripts/phase1_precheck.py` 재실행으로 ICT phase 보정

### 평가 시점

- **단기**: 다음 5거래일 (5/28 ~ 6/3) 시그널 감지 빈도 vs 직전 7일
- **중기**: 2026-06-30 분기말 — sweep ON vs OFF 라이브 결과 비교 후 영구 결정

---

## 2026-05-27: 포트폴리오 메시지 'Target/Drift' 용어 명확화

사용자가 일일 portfolio 텔레그램 메시지의 Drift 음수 표시를 손실/매도 트리거로 오해. 계산 버그가 아니라 컬럼 헤더(Current/Target/Drift)의 도메인 용어가 footer 설명 없이 노출돼 발생한 의미 mismatch.

### notify_portfolio_summary footer legend (src/telegram/notifier.py:584~591)

기존: `<i>Tier: {tier_key}</i>` 한 줄만.
변경: 그 위에 1줄 legend 추가 — `Current=평가금액(현재가×수량) · Target=목표배분(자본×weight, 매도가 아님) · Drift=배분편차(분기말 ±10%↑ 리밸런스)`. 컬럼 폭/구조/계산은 모두 그대로 유지(정렬 보존, 기존 notifier 테스트 37/37 통과). 다음 일일 tick부터 자동 적용 — 봇 재기동 불필요.

### 검증

- portfolio_state.json (2026-05-27) 산수 정합: 총액 $3,134.69 = cash $711.70 + SPMO $1,498.00 + VEU $924.99, sum(diff) = -$711.71 ≈ -cash. **계산 정확.**
- 사용자 KIS HTS 평가금액 vs 봇 current: SPMO $1,502 vs $1,498 (-$4), VEU $927 vs $924.99 (-$2). 차이는 가격 호출 timing.
- TROUBLESHOOTING.md에 사고 항목 + Claude 진단 미스 기록 추가 — 다음 세션이 같은 패턴을 만나면 KIS API 필드부터 의심하지 않고 도메인 용어 해석 차이를 먼저 점검하도록.

---

## 2026-05-16: 멀티버킷 운영 안정성 보강 (P0 / P1 / P2)

전날 멀티버킷 시드 디버깅 + 시드 후 정밀 검토에서 발견한 3개 결함을 한 번에 보강. 봇은 어제 시드 매수까지 정상 완료(SPMO 10주 + VEU 11주), 그러나 시드 후 SCANNING 진입 자체를 못해 그날 캐스퍼 거래 0건 — 그 원인 + 재발 방지 + persistence 추가.

### P0 — Scan window late entry (src/bot.py:885~890)

`_handle_waiting`이 `is_pre_market` / `is_orb_forming` 두 시간대만 분기. `is_scan_window` (ET 09:45~10:55) 분기 부재 → SCANNING 시간에 봇 시작 시 `sleep 60`만 무한 반복하며 그 날 캐스퍼 매매 자동 포기. 분기 추가 → PRE_MARKET으로 보내 trend 계산 + `_handle_pre_market`의 "Late join" 경로로 ORB_FORMING → 5분봉 backfill로 ORB 재계산 → SCANNING.

### P1 — Intraday state persistence (src/bot.py:67~73, 810~876, 1009~1010, 1138~1145, 1207~1210)

같은 거래일 내 봇 재시작 시 `self.trend` / `self.orbs` / `self.orb`가 메모리 only라 lost → SCANNING으로 도달해도 시그널 평가 불가. 새 파일 `data/intraday_state.json`에 trend + ORBs 영구 저장.

- `_save_intraday_state()`: PRE_MARKET trend 결정 직후 + ORB_FORMING→SCANNING 전이 직전에 호출
- `_load_intraday_state()`: `_reset_day` 끝에서 호출. `date != today_et()`면 stale로 무시
- `_handle_orb_forming` 시작에 "self.orbs 이미 있으면 SCANNING 직행" 분기 → 재계산 회피

### P2 — Initial seed full-fail lock-out 차단 (src/bot.py:1980~2003, 2156~2179)

`_execute_initial_seed`가 매수 0건이어도 `seeded_at`을 박는 "ALWAYS mark seeded" 정책 + `_daily_portfolio_tick`의 `save_evaluation`이 `last_eval_date=today`까지 박음 → 한 번 fail하면 다음 봇 재시작에서 시드 진입 영구 차단. 어제 KIS exchange mismatch로 시드 0건이 두 번 누적되며 표면화.

- `_execute_initial_seed` → `bool` 반환. 매수 ≥ 1건일 때만 `seeded_at` 박음
- `_daily_portfolio_tick`이 False 받으면 `save_evaluation` + `_portfolio_tick_done_for=today` 둘 다 건너뛰고 일찍 return
- 결과: KIS API 일시 outage가 영구 lock으로 번지지 않음. 다음 `_tick`/`_reset_day`에서 자동 재시도.

---

## 2026-05-15 (PM, 두 번째 패치): KIS exchange code mismatch fix + 시드 retry 안정화

같은 날 멀티버킷 첫 가동 후 시드가 SPMO/VEU 가격 조회 자체에서 silent fail. 원인: KIS overseas API는 거래소 코드를 정확히 받아야 하는데 `get_us_price`/`buy_market`/`sell_market` 모두 default `exchange="NASD"`. SPMO/VEU/MTUM/QUAL/SPY/AGG/BIL은 NYSE Arca-listed라 `"AMEX"` 필요.

### 코드 변경

- **`src/core/portfolio.py`** — `TICKER_EXCHANGE` 매핑 (TQQQ/SQQQ/QQQ→NASD, 그 외 7 ETF→AMEX) + `exchange_for(symbol)` 헬퍼 추가
- **`src/api/kis_order.py`** — `_get_market_price`/`buy_market`/`sell_market` 모두 exchange 인자 전파 (내부 helper의 hidden default 함정 layer 제거)
- **`src/bot.py`** — multi-bucket KIS 호출 9곳 (snapshot 1, 시드 2, GEM rotation 2, drift rebalance 4)에 `exchange=exchange_for(symbol)` 명시. Casper의 TQQQ/SQQQ 호출 4곳은 NASD default 그대로 유지 (의도된 동작)
- **`src/telegram/notifier.py`** — `bucket_cap_usd`/`casper_cap_usd` 파라미터 추가, GEM mode/cap을 startup banner에 노출
- **`src/bot.py`** `_daily_portfolio_tick` deferred seed 분기에 `return` 추가 — in-memory `_seed_pending`이 restart로 lost되어 retry 영구 차단되는 잠재 버그 제거

### 실측 검증

23:27 KST 봇 재기동 → 23:27:41 시드 완료: SPMO 10주 @ $145.72 (#0032012408), VEU 11주 @ $81.99 (#0032012464). Casper sleeve $609.94는 cash로 보관 (intraday signal 대기). `portfolio_state.json::seeded_at=2026-05-15`, `gem_state.json::current_holding=VEU` 모두 정상 저장.

---

## 2026-05-15 (PM): Multi-Bucket Portfolio (P0~P4) 통합 — Casper 데이트레이딩 + 저빈도 퀀트 자동 운용

자본 $3,000 환경에서 Casper만으로는 자본 효율이 20% (60일에 3건 매매 = 95% 일자 유휴)인 문제를 해결. Casper의 KIS/상태머신/Telegram 인프라를 그대로 재사용해서 단일 봇 안에 **GEM (Antonacci Dual Momentum) + SPMO 매수보유 + 분기 SPMO drift + 자본 tier 자동 활성화**를 추가. `GEM_MODE=off`이면 기존 Casper 동작 100% 그대로 유지 (역호환 안전).

### 신규 모듈
- `src/core/gem.py` — Antonacci GEM 신호 계산 (SPY/VEU/AGG/BIL 12개월 수익률 비교) + state 파일 + 3-거래일 grace 스케줄러
- `src/core/portfolio.py` — Bucket dataclass + `tier_for_capital(usd)` (P4 자동 활성화: <$3k=GEM only, $3k=SPMO/GEM/Casper, $5k=+MTUM/QUAL, $10k=+Clenow/TQQQ_SMA) + 분기말 drift 감지
- `src/utils/time_utils.py` — 공휴일 안전망: `get_last_trading_day_of_month`, `was_last_trading_day_of_month_within(N)` (크래시·휴장일 회복용 grace window), `is_last_trading_day_of_quarter`

### 변경된 모듈
- `src/utils/config.py` — env 변수 3종 추가 (`CASPER_MAX_POSITION_USD`, `GEM_MODE`, `PORTFOLIO_CONFIG`)
- `src/bot.py`
  - `_execute_entry`: `CASPER_MAX_POSITION_USD` cap 적용 (P0). 자본 $3k 중 $600만 Casper에 할당 가능
  - `__init__`: GemState + PortfolioState load (graceful default)
  - `_reset_day`: `_daily_portfolio_tick(today)` 1회 호출 (idempotent guard)
  - 신규: `_fetch_full_portfolio_snapshot()`, `_daily_portfolio_tick()`, `_maybe_run_gem()`, `_execute_gem_rotation()`, `_execute_bucket_drift_rebalance()`
- `src/telegram/notifier.py` — 6개 신규 메서드: `notify_gem_signal`, `notify_gem_executed`, `notify_portfolio_summary`, `notify_tier_change`, `notify_bucket_drift`, `notify_etf_rebalance`

### 운영 모드 (GEM_MODE env)
- `off`  (default) — 기존 Casper 단독 동작. 추가 로직 0
- `alert` — GEM 신호 + portfolio drift를 매일 텔레그램으로만 알림. 매매는 사람이 수동 (P1)
- `auto` — GEM 자동 매매 + 분기말 SPMO/MTUM/QUAL drift 자동 리밸런스 (P2 + P3)

### 공휴일 안전망 (사용자 요구)
- `is_last_trading_day_of_month(d)`: NYSE 공휴일 + 주말 제외해서 월의 진짜 마지막 거래일 판단 (예: 2026-05 → 5/29 Fri, Memorial Day 5/25 자동 제외)
- `was_last_trading_day_of_month_within(N=3)`: 봇 크래시·재시작·휴가 등으로 마지막 거래일을 놓쳐도 다음 3 거래일 내 자동 회복
- `GemState.last_signal_date` 영속화: grace window 안에서도 한 번 실행하면 다음에 안 함 (중복 방지)
- `_check_holiday_data_loaded()` 모듈 로드 시 경고: `config/us_holidays.json` 누락 시 명시적 warning

### 테스트
- `tests/test_multi_bucket.py` 신규 27개 (TradingDayHelpers 8 + GemScheduler 5 + PortfolioTier 5 + PortfolioEvaluation 6 + StatePersistence 3) — **27/27 pass**
- 기존 회귀: 551/551 pass (Casper RR3 production 영향 없음)

### CHECKLIST 항목 추가 (#17~#24)
- function: time_utils helpers (#17), GEM API (#18), tier_for_capital (#19), env vars (#20)
- scenario: GEM 스케줄러 grace+dedup (#21), bot.py hooks (#22)
- system: multi-bucket pytest (#23), GEM_MODE=off 역호환 (#24)

### 백테스트 가정 (US_QUANT_STRATEGIES.md §9 참조)
- 자본 $3,000, KIS 0.25% × 2, 세금 외부화, 환전 무시
- 시나리오 D (SPMO 50% + GEM 30% + Casper 20%): 기대 CAGR 14~16%, MaxDD −18% (Casper 단독 ~5%, MaxDD −2% 대비 자본 효율 5배)
- 자본 $5k 도달 시 자동 MTUM/QUAL 활성화, $10k 도달 시 자동 Clenow/TQQQ_SMA 활성화

### 출처 / 알고리즘
- Antonacci, G. (2014) *Dual Momentum Investing*. 1974-2023 백테스트 CAGR +14.8% / MaxDD −20.5%
- 자세한 알고리즘·시나리오·비교: [docs/strategy/US_QUANT_STRATEGIES.md](strategy/US_QUANT_STRATEGIES.md) §3~§11 + §12 (운영 매뉴얼)

---

## 2026-05-15: Partial TP 도입 + Casper SMC 출처 분석 + Phase 5.0 데이터 분석

캐스퍼 SMC 원본(YouTube `@caspersmc`, 본명 Jesse Rogers — Trading Nut 팟캐스트 EP 302 확인)의 community script `hoosn1ck/Casper SMC: 5m ORB + Retest` 룰을 재구성. 7개 변형 비교 백테스트 후 **Partial TP만 즉시 도입**, 5m ORB는 백로그에 보류, Phase 5는 데이터 부족으로 보류.

### Partial TP 구현 (코드)
- `config/strategy_params.json`: `partial_tp_enabled=true`, `tp1_rr=1.5`, `tp1_close_pct=0.50`, `move_sl_to_orb_high_after_tp1=true`
- `src/core/strategy.py::TradeSignal.tp1_price` 필드 신규 + `scan_for_signal(tp1_rr=...)` 파라미터
- `src/core/position.py::Position` 7개 필드 추가 (tp1_price, tp1_close_pct, tp1_filled, partial_shares_initial, partial_shares_closed, partial_exit_price/time, orb_high). gross_pnl/commission/r_multiple을 2-leg 합산 정확화. 신규 helper `check_tp1_fill()`, `apply_partial_fill()`
- `src/bot.py::_handle_position_open`: TP1 모니터링 + KIS 부분 매도 + 실제 fill price 조회 + state save + ORB.high SL 이동
- `src/telegram/notifier.py::notify_partial_close()` critical 큐 메시지 신규
- `tests/test_position.py::TestPartialTP` 9개 신규 (필드 초기화, TP1 fill 트리거, SL 이동, idempotent, 2-leg PnL, R-multiple)

### 백테스트 결과 (60일 TQQQ, 7개 변형 비교)
- **partial_TP만 양수 수익** (+0.14%, AvgR +0.08)
- 5m ORB: 매매 2배 빈도(3→6), WR 16.7%, Net -0.35% — 백로그 보류
- SL_midpoint / 30m ORB: BASE와 무차이
- ADX(>25) / 4H VWAP 필터: 매매 0~1건, 너무 빡빡

### Casper SMC 출처 분석
- 본명 Jesse Rogers (Trading Nut EP 302 확인)
- Primary 매매: NQ futures, TQQQ/SQQQ는 retail용 변형 — 사용자(선물 미운용)에게 현재 봇 구성이 정확히 부합
- ICT Mastery Course 3대 모듈: Unicorn Model (✓ 봇 구현), STBP Daily Bias (✓ 봇 구현), Range Expansion (☆ Phase 5 후보)
- 외부 정량 검증 자료 없음 + ImanTrading SIM 위장 폭로 → **알고리즘 룰은 참고, 본인 수익률은 신뢰 불가**

### Phase 5.0 데이터 분석 (Range Expansion)
- 18건 매매(라이브 11 + 백테스트 7) × 1H/4H expansion 정렬 검증
- 4H expansion = 0건, 1H expansion = 4건 (모두 misaligned)
- 4건의 1H bear expansion + bull setup 매매는 *모두 LOSS/BE* — 표본 부족이라 결정 불가
- **Phase 5 보류**, 6개월+ 데이터 누적 + 임계값 ablation 후 재검토

### 신규 산출물
- `docs/strategy/CASPER_SMC_SOURCE_REPORT.md` — 캐스퍼 출처·알고리즘·종목·검증 종합 (530줄)
- `docs/strategy/UPGRADE_REVIEW.md` — Partial TP / 5m ORB / Phase 5 상세 검토 + 트레이드오프
- `docs/strategy/BACKLOG.md` — 5m ORB 보류 + 재검토 트리거
- `docs/strategy/PHASE5_DATA_ANALYSIS.md` — Phase 5.0 데이터 분석 결과
- `scripts/casper_variants_backtest.py` — 7개 변형 비교
- `scripts/displacement_distribution.py` — displacement reject 분포 누적 분석 (backtest+live)
- `scripts/range_expansion_data_analysis.py` — Phase 5.0 재실행 가능

### 검증
- 551/551 unit test pass (5분 59초). 기존 542 + 신규 9 partial TP
- Casper community script `hoosn1ck/Casper SMC: 5m ORB + Retest` 룰과 정합성 검증

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
