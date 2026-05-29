# 설계 스펙 — Casper sleeve를 저빈도 TQQQ Vol-Target 추세로 교체

**작성일**: 2026-05-30
**상태**: 설계(승인 대기 → writing-plans로 전환)
**근거 study**: `docs/strategy/STRATEGY_ZOO_1000USD.md` (30+ 매매법 실측 백테스트), [[casper-1000usd-strategy-zoo]], [[casper-intraday-cost-trap]]
**선행 패턴**: `src/core/gem.py` + `bot._maybe_run_gem` + `gem.should_run_gem` (순수로직 + bot wiring + 월말 grace 스케줄러 3-요소)

---

## 1. 목표 & 배경

### 1.1 한 줄 목표
멀티버킷 봇의 **Casper 20% sleeve의 엔진을 인트라데이 ORB+FVG → 저빈도 "TQQQ Vol-Target 40%" 추세**로 교체한다. 티어 가중치·자본 임계값은 불변. 구 인트라데이 코드는 config 플래그로 비활성(보존, 되돌림 가능).

### 1.2 왜 (study 결론)
- 0.25%/side에서 **고빈도 매매는 구조적으로 적자**다(비용=최종자산의 25~260%). Casper 인트라데이 실거래 11건은 수수료=gross의 116%, net −$9.6.
- **저빈도 추세추종만 엣지를 보존**한다(@0.25%↔@0% 수익률 거의 동일). 블렌드 백테스트(50% SPMO + 30% GEM + 20% sleeve, 2017–26):
  - Casper=노출0(현 상태) → CAGR 11.8% / MDD −23.3% / Sharpe 0.88
  - **Casper→TQQQ Vol-Target → CAGR 19.0% / MDD −31.1% / Sharpe 1.01** (성장률 +7pp, Sharpe ↑)
- Vol-Target이 단순 200SMA보다 위험조정 우월(Sharpe 1.01 vs 0.94, MDD −31 vs −37, 2022 −11% vs −20%).

### 1.3 확정된 설계 결정 (브레인스토밍)
1. **배치**: Casper 엔진 교체, 기존 티어 임계값 유지(20%/20%/5% 그대로).
2. **엔진**: TQQQ Vol-Target 40% (QQQ>200d 게이트, 노출=min(1, 0.40/실현변동성), 월 1회).
3. **구 Casper 코드**: 보존 + config 플래그 기본 OFF(되돌림 가능).
4. **롤아웃**: 소액 sleeve로 바로 live (단 첫 사이클 `mode="alert"` 관찰 권장).

### 1.4 코드 현실(탐색 결과)
- `tier_for_capital()`: `<$3k`=GEM 100%, `$3–5k`=spmo .5/gem .3/**casper .2**, `$5–10k`=spmo .4/mtum .1/qual .1/gem .2/**casper .2**, `$10k+`=…/**casper .05**/tqqq_sma .1.
- `tqqq_sma` 버킷은 **스텁**(신호 로직 없음, 현금 보류). `clenow`도 스텁.
- Casper 사이징 캡(`CASPER_MAX_POSITION_USD`)은 이미 존재(개선 #2 부분 충족).
- 버킷 실행 경로: ① initial seed(현금에서 1회), ② 분기 드리프트 리밸런스, ③ GEM 자체 월간 스케줄러, ④ Casper 자체 인트라데이 루프.

---

## 2. 아키텍처 개요

```
config.sleeve_engine = "trend"
        │
        ▼
bot 데일리 멀티버킷 틱  ──►  _maybe_run_trend()  ──►  trend.should_run_trend()  (월말+grace)
   (_run_daily_multibucket_tick)         │                      │ run?
        │  _maybe_run_gem() (기존)         │                      ▼
        │                                 └──► trend.compute_trend_signal()  (yfinance: QQQ 200d, TQQQ vol)
        ▼                                              │  TrendSignal{target, exposure, regime, vol, reason}
   ORB+FVG 상태머신 (sleeve_engine=="intraday"일 때만)     ▼
                                          목표 비중 = {TQQQ: exposure×sleeve_usd, BIL: 잔여}
                                                       │  KIS 잔고 reconcile(정수주, 매도→매수)
                                                       ▼
                                          kis_order  +  trend_state.json  +  텔레그램
```

**격리 원칙**: `trend.py`는 순수 로직(KIS 비호출), bot이 I/O wiring. `gem.py`와 동일 구조 → 단위테스트 + 백테스트 패리티 가능.

---

## 3. 컴포넌트 명세

### 3.1 `src/core/trend.py` (신규, 순수 로직)
**무엇**: 저빈도 추세 신호 계산 + 스케줄 + 상태. **의존**: yfinance, pandas, `src.utils.time_utils`. KIS 비호출.

- `@dataclass TrendSignal`: `signal_date, target_symbol("TQQQ"|"BIL"), exposure(0..1), regime(bool), realized_vol, reason, params_snapshot`.
- `@dataclass TrendState` (`data/trend_state.json`): `last_signal_date, current_symbol, last_exposure`. `load/save` (gem.py 미러).
- `compute_trend_signal(today, params) -> TrendSignal`:
  - QQQ 일봉(≥260일), TQQQ 일봉(≥`vol_lookback`+1) `auto_adjust=True` 다운로드.
  - `regime = QQQ.close[-1] > SMA(QQQ.close, sma_period)[-1]`.
  - regime False → `target="BIL", exposure=0.0`.
  - regime True → `rv = std(TQQQ.pct_change()[-vol_lookback:])×√252`; `exposure = min(1.0, target_vol/rv)`; `target="TQQQ"`.
  - 데이터 결손/NaN → 방어적으로 `target="BIL", exposure=0`(gem.py의 AGG 폴백과 동형).
- `should_run_trend(today, state) -> (run_now, signal_date)`: 월말 마지막 거래일(+grace 3거래일). `gem.should_run_gem`과 동일 로직(중복 시 공용 헬퍼로 추출 검토 — §6 리팩터).

### 3.2 `bot._maybe_run_trend(buckets, total, holdings, mode)` (신규)
**무엇**: trend 신호를 KIS 주문으로 집행. **위치**: `_run_daily_multibucket_tick` 내 `_maybe_run_gem` 호출 옆. **의존**: `trend.py`, `kis_order`, `kis_client`, `portfolio.exchange_for`, `notifier`.

- `should_run_trend` False → return.
- `sleeve_usd = total × (trend 버킷 target_weight)`.
- `sig = compute_trend_signal(...)`; 목표: `TQQQ_usd = sig.exposure×sleeve_usd`, `BIL_usd = sleeve_usd − TQQQ_usd`.
- 현재 holdings(TQQQ, BIL)와 reconcile → 정수주 매도 먼저, 매수 나중. `exchange_for()` venue.
- `mode=="alert"` → 주문 없이 텔레그램 신호만. `mode=="auto"` → 집행. RTH 밖이면 다음 틱 defer(GEM과 동일).
- 성공 시 `TrendState` 저장(멱등 — `last_signal_date`로 월 중복 방지).

### 3.3 `src/core/portfolio.py` 변경 (티어 가중치 불변)
- `tier_for_capital()`: 모든 `"casper"` 키 → `"trend"`로 **리네임**(가중치 .20/.20/.05 그대로). 결정: 버킷 키를 `trend`로 통일(의미 명확). `data/portfolio_state.json`의 구 `casper` 엔트리는 다음 평가 시 티어 키가 바뀌어 자동 재구성되므로 별도 마이그레이션 불필요.
- `BUCKET_DEFAULT_SYMBOL`: `"casper"` 제거, `"trend": "TQQQ"` 추가. `_bucket_value`에 `name=="trend"` 분기 → TQQQ/BIL 보유 조회.
- `needs_rebalance`: `"trend"`를 GEM과 함께 분기-드리프트 경로에서 제외(자체 스케줄러 소유).
- `TICKER_EXCHANGE`: BIL 이미 존재(AMEX). 변경 없음.
- `tqqq_sma` $10k 스텁: **불변**(무회귀). trend과 통합은 backlog(§7).

### 3.4 `config/strategy_params.json` 변경
```jsonc
"sleeve_engine": "trend",        // "trend" | "intraday"(구 Casper, 기본 비활성)
"trend": {
  "signal_symbol": "QQQ", "sma_period": 200,
  "asset": "TQQQ", "safe_asset": "BIL",
  "target_vol": 0.40, "vol_lookback": 20,
  "rebalance": "monthly", "mode": "auto"   // 첫 배포는 "alert" 권장
}
```

### 3.5 bot 메인 루프 가드 (`src/bot.py`)
- 인트라데이 ORB+FVG 상태머신 진입부에서 `if params["sleeve_engine"] != "intraday": skip`. → `"trend"`면 인트라데이 스캔 전체 스킵, trend sleeve가 데일리 틱에서 처리. 구 Casper 코드 = 보존(개선 #1 "비활성" 충족).

---

## 4. 데이터 흐름 & 에러 처리

**흐름**: 데일리 틱 → `should_run_trend`(월말?) → `compute_trend_signal`(yfinance) → 목표 비중 → KIS 잔고 reconcile → 정수주 매도/매수 → `trend_state.json` 저장 → 텔레그램.

**에러**:
- yfinance 실패/NaN → BIL 폴백(현금 보존). 봇 정지 없음.
- KIS 주문 실패 → `notify_order_failed` + 다음 틱 retry(멱등, `last_signal_date` 미저장 시 재시도).
- RTH 밖 → defer(같은 날 다음 틱 재시도).
- 부분 체결/잔고 동기화 → 기존 봇 안전장치 재사용.

---

## 5. 테스트 전략

1. **단위 `tests/test_trend.py`**: regime on/off, vol-target 노출 계산(고변동성→노출↓, 저변동성→1.0 캡), 데이터 결손→BIL 폴백, `should_run_trend` 월말+grace.
2. **Golden 패리티**: `trend.compute_trend_signal`이 과거 일자에 대해 `scripts/strategy_zoo_backtest.make_voltarget_lev`의 월말 결정(target/exposure)과 일치하는지 검증 → 라이브-백테스트 드리프트 방지(개선 #5).
3. **포트폴리오**: `tier_for_capital`에 `casper` 부재 + `trend` 존재, `needs_rebalance`가 trend 제외 확인.
4. **TEST_MODE=on**: 1주 고정으로 실거래 1사이클 검증.

---

## 6. 리팩터 (작업 중 개선, 범위 한정)
- `should_run_gem`/`should_run_trend`의 "월말+grace 스케줄러" 중복 → `time_utils` 또는 공용 헬퍼 `monthly_rebalance_due(today, state_date, grace)`로 추출(선택, 두 모듈이 공유).
- 무관한 리팩터 금지.

## 7. 범위 밖 / 백로그
- **일별 regime 청산**(월말 대신 QQQ<200d 즉시 TQQQ 청산): DD 더 줄일 수 있으나 백테스트 안 됨 → 별도 검증 후(개선 #5 정합). 본 작업은 **월간**(백테스트 충실).
- `tqqq_sma`($10k 스텁) + `clenow` 구현 / trend과 통합.
- 수수료 0.07% 인하(KIS 우대 협상 — 코드 무관).
- 고빈도 sleeve 신규 추가 금지 정책(가드레일 #3) — CLAUDE.md/config 주석으로 문서화(코드 강제 아님).

## 8. 리스크 & 단서
- **레버리지 추세는 2010년 이후(TQQQ 존재) 강세 편향 표본 조건부.** 2000–02·2008형 약세장이면 −80~−90%. → sleeve를 작게(20%↓), Vol-Target+200d 게이트 필수. 무지성 BH_TQQQ 금지.
- 월간 리밸런스라 QQQ가 월 중 200d 하향 돌파해도 월말까지 TQQQ 보유 → 빠른 급락에 노출(백테스트 −60% DD에 이미 반영). 일별 청산은 §7 백로그.
- 소액 sleeve 정수주: TQQQ 저가($85)라 드래그 ~−1%로 미미.

## 9. 성공 기준
- `sleeve_engine="trend"`에서 봇이 인트라데이 스캔을 하지 않고, 월말에 QQQ/TQQQ 신호로 TQQQ↔BIL을 정수주·vol-target 비중으로 리밸런스한다.
- golden 테스트가 백테스트 하네스 결정과 일치한다.
- `sleeve_engine="intraday"`로 되돌리면 구 Casper가 그대로 작동한다(무회귀).
- TEST_MODE 1사이클 실거래 정상.
