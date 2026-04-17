# BTC 단기 스캘핑 봇 설계서 (Ver4 / `scalping/` 모듈)

**문서 버전:** 1.0
**작성일:** 2026-04-17
**작성자:** 브레인스토밍 세션 (Claude + SeongWook Jang)
**상태:** 승인됨 — 구현 계획 작성 대기
**근거:** 기존 Ver3 15분 주기 멀티코인 봇이 6개월 운영에서 지속 손실 (Bearish 레짐 누적 -3% ~ -15%)

---

## 1. 목표 & 제약

### 1.1 비즈니스 목표
- **단일 코인(BTC)** 24시간 단기 스캘핑 자동매매 봇 구축
- **3~5분봉 기반**, 10~60분 보유, 하루 2~15회 거래
- Bithumb 거래소 기준 (기존 API 인프라 재활용)
- Paper Trading을 거쳐 점진적 소량 실전 배포

### 1.2 성능 목표 (백테스트 기준)
| 메트릭 | 목표 | 실패 기준 |
|--------|------|-----------|
| 연환산 Total Return | > +15% | < 0% |
| Sharpe Ratio | > 1.5 | < 0.5 |
| Max Drawdown | < 15% | > 25% |
| Win Rate | 45~65% | < 40% 또는 > 80% (과적합 의심) |
| Profit Factor | > 1.5 | < 1.2 |
| Avg Trade 순수익 | > +0.2% | < 0% |
| Walk-Forward Efficiency (WFE) | > 0.5 | < 0.3 |
| Recovery Factor | > 2.0 | < 1.0 |

### 1.3 리스크 제약
- 거래당 자본 리스크: **0.3~0.5%** (균형)
- 일일 드로다운 하드 스탑: **-2%**
- 연속 5회 손실: 30분 쿨다운
- 자본 50% 소실: 자동 백테스트/실전 중단
- 자본 규모: 소액 (50~200만원)
- 주문: 진입·청산 모두 **시장가**

### 1.4 거래소 결정: **Bithumb 유지**

| 항목 | Bithumb | Upbit |
|------|---------|-------|
| BTC 수수료 (Maker/Taker) | **0.04%** (쿠폰) | 0.05% |
| 왕복 수수료 | 0.08% | 0.10% |
| 500회 누적 비용 차이 | 기준 | **+1%p 불리** |
| BTC 유동성 | 중상 | 최상 |
| 기존 API 연결 | ✅ 완료 | 신규 필요 |

**근거:** 소액·고빈도 BTC 거래에서 수수료 차이가 누적 수익에 결정적. 소액 시장가에서 유동성 격차는 무시 가능.

---

## 2. 리서치 기반 전략 선정

### 2.1 조사한 10개 스캘핑 패러다임

**Tier 1 (퀀트 논문 검증·수학적 근거):**
1. Donchian Breakout (Turtle 변형)
2. Keltner-Bollinger Squeeze (변동성 돌파)
3. VWAP Pullback (평균 회귀)

**Tier 2 (커뮤니티·유튜브 대중화):**
4. EMA 9/21 Crossover + Volume
5. Supertrend(7,2) + VWAP
6. Heikin Ashi + EMA50 Filter

**Tier 3 (주관적·시스템화 어려움):**
7. RSI Divergence
8. ICT/SMC Fair Value Gap
9. Opening Range Breakout
10. (학술 앙상블) ReinforcedSmoothScalp — 지표 다수로 과최적화 의심

### 2.2 선정 3개 접근 (모두 구현 후 비교)
- **A. Triple Screen Ensemble** — Tier 1 3개 전략을 과반 동의로 앙상블
- **B. Squeeze Specialist** — 단일 전략 집중으로 단순성·과적합 저항력
- **C. Adaptive Momentum** — Supertrend + VWAP + EMA 다중 필터

### 2.3 수익성 하한선 분석
```
Bithumb 왕복 수수료 0.08% + 시장가 슬리피지 0.05% = 마찰 0.13%
→ 평균 순수익 > 0.13% 필수
→ 현실적 목표: 0.25%+ 순수익 per trade

TP=0.4%, SL=0.3% 가정:
  - 승률 40% → 기대값 -0.05% (손실)
  - 승률 50% → 기대값 +0.05%
  - 승률 55% → 기대값 +0.085% (최소 기준)
  - 승률 60% → 기대값 +0.12%
```

---

## 3. 아키텍처

### 3.1 디렉토리 구조
```
001_python_code/scalping/
├── __init__.py
├── config.py                  # 전략 파라미터, 수수료, 리스크 설정
├── data/
│   ├── loader.py              # 데이터 수집·캐싱
│   └── cache/                 # btc_5m_2025_2026.parquet
├── indicators/
│   ├── atr.py
│   ├── bollinger.py
│   ├── keltner.py
│   ├── donchian.py
│   ├── vwap.py
│   ├── supertrend.py
│   └── ema.py
├── strategies/
│   ├── base.py                # StrategyBase 인터페이스
│   ├── triple_screen.py       # 전략 A
│   ├── squeeze_specialist.py  # 전략 B
│   └── adaptive_momentum.py   # 전략 C
├── backtest/
│   ├── engine.py              # 이벤트 드리븐 시뮬레이터
│   ├── walk_forward.py        # Train/Val/Test 분할
│   └── metrics.py             # Sharpe, MaxDD, PF 등
├── reports/
│   ├── chart_plotter.py
│   └── summary_generator.py
├── live_scalper/              # Stage 2, 3
│   ├── paper_trader.py
│   ├── live_executor.py
│   └── telegram_handler.py
└── scripts/
    ├── fetch_data.py          # 1회: 1년 데이터 다운로드
    ├── run_backtest.py        # 전략별 백테스트
    └── compare_strategies.py  # 3개 전략 비교 리포트
```

### 3.2 재활용 인프라
- `lib/api/bithumb_api.py` — `get_candlestick(ticker, interval)` 확장 (1m~5m)
- `lib/core/logger.py` — 공용 로거
- `lib/core/telegram_notifier.py` — 백테스트 완료/거래 알림
- `pybithumb/` — 초기 데이터 수집용

### 3.3 ver3과의 관계
- **완전 격리**: ver3 코드 수정 없음
- **공용 라이브러리만 공유**: lib/ 하위 모듈
- 실전 배포 시 동시 실행 가능 (포지션 충돌 없음 — BTC만 스캘핑, ver3는 중단 상태)

---

## 4. 데이터 레이어

### 4.1 Bithumb Public API 실측 제약
```
 1m:  3,000 candles →   2.1일
 3m:  3,000 candles →   6.2일
 5m:  3,000 candles →  10.4일
10m:  3,000 candles →  21.1일
30m:  3,000 candles →  62.8일
 1h:  5,000 candles → 209.0일
```
- **페이징 미지원**. 한 번 호출로 최신 캔들만 반환.
- **1년치 5m 데이터(105,120개)를 Bithumb 단독으로 수급 불가능**.

### 4.2 선택된 데이터 전략: Hybrid
1. **Binance BTCUSDT 5m 1년치** → 전략 개발·백테스트·Walk-Forward 검증 주 데이터
   - Binance `GET /api/v3/klines` 페이징 지원, 1000개씩 106 requests
2. **Bithumb BTC_KRW 5m 10일치** → 교차 검증
   - Binance USDT × 환율 → Bithumb KRW 대비 오차 분포 리포트
   - 평균 편차, 최대 편차, 김프 영향 수치화
3. **실전 배포 시** → Bithumb 실시간 가격 사용 (교차 검증 + Paper Trading으로 보정)

### 4.3 데이터 무결성
- Gap detection (5m 연속성)
- NaN / 중복 timestamp 체크
- 이상치 (3σ spike) 플래그링
- Forward-fill 금지, 결측 구간은 스킵

### 4.4 캐시
- **Parquet (snappy 압축, pyarrow 엔진)**
- 메타데이터: symbol, interval, start, end, source
- 파일 크기 예상: 1~2 MB

---

## 5. 전략 명세

### 5.1 전략 A: Triple Screen Ensemble

**철학:** 3개 독립 시스템의 과반 동의(2/3 이상) 시에만 진입. 레짐 커버리지 극대화, 단일 전략 실패 리스크 분산.

**구성:**
- **① Donchian Breakout (추세)**
  ```
  [진입 Long]  close > max(high[-20:-1])       # 20봉 고가 돌파
  [볼륨 필터]  volume > volume.rolling(20).mean() * 1.2
  [손절]       entry - (ATR × 2.0)
  ```
- **② Keltner-Bollinger Squeeze (변동성)**
  ```
  [압축]  BB_upper < KC_upper AND BB_lower > KC_lower  (BB가 KC 안으로 수렴)
  [진입]  squeeze 해제 + close > BB_middle + momentum_slope > 0
  [손절]  entry - (ATR × 1.5)
  # BB: period=20, std=2.0 / KC: period=20, ATR_mult=1.5
  ```
- **③ VWAP Pullback (평균 회귀)**
  ```
  [세션 VWAP] 00:00 UTC 리셋
  [추세 확인] close > VWAP AND close > EMA(50)
  [진입]      close가 VWAP 근방 [-0.3%, +0.1%] 재접근 + candle_body > 전봉_body
  [손절]      min(VWAP × 0.997, entry - ATR × 1.0)
  ```

**앙상블:** `sum(signals) >= 2 → enter_long()`

**청산 공통:**
- TP1: +0.6% → 50% 청산
- TP2: +1.2% → 전량 청산
- 트레일링 스탑: TP1 이후 최고가 대비 -0.3%
- 시간 청산: 60분 경과
- 모든 전략 중립/negative → 전량 청산

**예상 특성:** 3~8회/일, 승률 55~65%, R:R 1:1.5~2.0

### 5.2 전략 B: Squeeze Specialist

**철학:** 단일 전략 집중 = 단순성·과적합 저항력. Keltner-BB Squeeze만 사용, 진입 필터·청산 정교화.

```python
bb = bollinger_bands(close, period=20, std=2.0)
kc = keltner_channels(close, period=20, atr_mult=1.5)
atr = true_range.rolling(14).mean()

is_squeeze = (bb.upper < kc.upper) & (bb.lower > kc.lower)
squeeze_bars = is_squeeze.rolling(100).sum()

momentum = (close - ((highest_high_20 + lowest_low_20) / 2 + sma_20) / 2)
momentum_slope = momentum.diff()

squeeze_release = is_squeeze.shift(1) & ~is_squeeze

enter_long = (
    squeeze_release
    & (momentum > 0) & (momentum_slope > 0)
    & (close > bb.middle)
    & (volume > volume.rolling(20).mean() * 1.3)
    & (squeeze_bars.shift(1) >= 6)    # 최소 6봉 이상 압축
)
```

**청산:**
- 스탑로스: entry - (ATR × 1.5) 고정
- TP1: +0.5% → 50% 청산 후 손절선 BE(break-even) 이동
- TP2: BB upper band 터치 → 전량 청산
- 모멘텀 리버설: momentum_slope 3봉 연속 음수 → 전량 청산
- 시간 청산: 45분

**파라미터 그리드:**
```
bb_period:    [15, 20, 25]
bb_std:       [1.8, 2.0, 2.2]
kc_atr_mult:  [1.3, 1.5, 1.7]
min_squeeze:  [4, 6, 8]
tp1_pct:      [0.003, 0.005, 0.007]
sl_atr_mult:  [1.2, 1.5, 1.8]
```

**예상 특성:** 2~5회/일, 승률 55~70%, R:R 1:1.3~2.5

### 5.3 전략 C: Adaptive Momentum

**철학:** 3개 지표 컨펌 로직으로 추세 방향·강도 이중 필터링. 진입 빈도 높음.

```python
st = supertrend(high, low, close, period=10, multiplier=2.5)
vwap_daily = (close * volume).cumsum() / volume.cumsum()   # 00:00 UTC 리셋
ema50 = close.ewm(span=50).mean()

enter_long = (
    (st.direction == 'up')
    & (close > vwap_daily)
    & (close > ema50)
    & (st.direction.shift(1) == 'down')        # flip 순간만
    & (volume > volume.rolling(20).mean())
)

exit_long = (
    (st.direction == 'down')
    | (close < vwap_daily * 0.998)             # VWAP 하향 0.2% 이탈
)
```

**안전장치:**
- 스탑로스: entry - (ATR × 2.0)
- TP 없음 (트레일링 Supertrend로 대체)
- 시간 청산: 120분
- 카운터-트렌드 보호: EMA50이 30봉 이상 하락 시 신규 롱 차단

**파라미터 그리드:**
```
st_period:    [7, 10, 14]
st_multiplier: [2.0, 2.5, 3.0]
ema_period:   [34, 50, 89]
vwap_margin:  [0.001, 0.002, 0.003]
sl_atr_mult:  [1.5, 2.0, 2.5]
```

**예상 특성:** 5~15회/일, 승률 45~55%, R:R 1:1.5~3.0

---

## 6. 백테스트 엔진

### 6.1 이벤트 드리븐 시뮬레이터

```python
class BacktestEngine:
    def __init__(self, df, strategy, config):
        self.df = df                  # 5m OHLCV
        self.strategy = strategy
        self.config = config
        self.capital = config.initial_capital
        self.position = None
        self.trades = []
        self.equity_curve = []

    def run(self):
        for i in range(max_lookback, len(self.df)):
            # 신호 생성 (현재 봉 close까지만 참조)
            signal = self.strategy.generate_signal(self.df.iloc[:i+1])

            if self.position:
                self._manage_position(self.df.iloc[i], signal)

            if not self.position and signal.action == 'BUY':
                # 다음 봉 시가에 체결 (룩어헤드 방지)
                self._open_position_next_open(i, signal)

            self._record_equity(self.df.iloc[i])
```

### 6.2 현실성 레이어

| 항목 | 가정 |
|------|------|
| 수수료 (왕복) | 0.08% (Bithumb 쿠폰) |
| 시장가 슬리피지 | 0.05% (소액 기준) |
| 체결 타이밍 | **다음 봉 시가** 체결 (룩어헤드 방지) |
| 일일 자본 스탑 | -2% 도달 시 당일 신규 진입 중단 |
| 파산 보호 | 자본 50% 소실 시 중단 |
| 결측 데이터 | Forward-fill 금지, 스킵 |

### 6.3 Walk-Forward 검증

```
전체 1년 데이터 (105,120 × 5m 캔들)
├── Segment 1: 2025-04 ~ 2025-10 (6개월 Train) → 2025-10 ~ 2025-11 (1개월 Test)
├── Segment 2: 2025-05 ~ 2025-11 (6개월 Train) → 2025-11 ~ 2025-12 (1개월 Test)
├── ...
└── Segment 7: 2025-10 ~ 2026-03 (6개월 Train) → 2026-03 ~ 2026-04 (1개월 Test)

→ 7개 Out-of-Sample 구간에서 일관되게 유효해야 함
→ WFE (OOS Return / IS Return) > 0.5 목표
```

### 6.4 파라미터 최적화
```
전략 B 예시:
param_grid = {
    'bb_period':    [15, 20, 25],
    'bb_std':       [1.8, 2.0, 2.2],
    'kc_atr_mult':  [1.3, 1.5, 1.7],
    'tp1_pct':      [0.003, 0.005, 0.007],
    'sl_atr_mult':  [1.2, 1.5, 1.8],
}
# 3^5 = 243 조합 × 7 WF 세그먼트 = 1,701 백테스트 ≈ 20~40분
```

최적화 목적함수: **Sharpe Ratio** (최소 거래수 20회 필터)

---

## 7. 리포팅 & 시각화

### 7.1 전략별 산출물
```
reports/{strategy}_{timestamp}/
├── summary.md                # 최상위 요약
├── equity_curve.png
├── drawdown.png
├── monthly_returns.png       # 월별 수익 히트맵
├── trade_distribution.png    # 거래 수익 분포
├── walk_forward_results.csv
├── parameter_sensitivity.png
└── trades.csv
```

### 7.2 비교 리포트
`reports/strategy_comparison_{timestamp}.md`:
- 3개 전략 성과 매트릭스
- 레짐별 성과 분석 (추세/횡보/변동성)
- Bithumb 교차 검증 결과 (10일 데이터)
- 실전 배포 추천 (상위 1~2개)

### 7.3 Telegram 알림
```
📊 Scalping Backtest Complete

Strategy A (Triple Ensemble):
  Return: +18.5% | Sharpe: 1.87 | MaxDD: -8.2%
  WinRate: 58% | Trades: 1,852 | WFE: 0.67

Strategy B (Squeeze):
  Return: +12.3% | Sharpe: 2.12 | MaxDD: -5.5%
  ...

🏆 Recommended for Paper Trading: [A|B|C]
📄 Full Report: /path/to/comparison.md
```

---

## 8. 배포 경로

### 8.1 Stage 1: 백테스트 검증 (1~2주)
- [ ] 3개 전략 모두 백테스트 실행
- [ ] Walk-Forward WFE > 0.5 확인
- [ ] Bithumb 10일 교차 검증
- [ ] 비교 리포트로 상위 1~2개 전략 선정

### 8.2 Stage 2: Paper Trading (2~4주)
```python
class PaperTrader:
    """Bithumb 실시간 가격 + 가상 주문"""
    def run(self):
        while True:
            df = self._fetch_latest_5m()
            signal = self.strategy.generate_signal(df)

            if signal.action == 'BUY' and not self.position:
                entry = df['close'].iloc[-1]
                self.position = VirtualPosition(entry, signal.stop)
                self.telegram.send(f"📝 Paper BUY @ {entry:,.0f}")

            self._check_virtual_exits(df['close'].iloc[-1])
            time.sleep(60)
```

**Paper → Live 전환 기준:**
- 2주 연속 양(+) 주간 수익
- 실측 슬리피지 < 0.1% (중앙값)
- 백테스트 대비 성과 편차 < 30%
- Max DD 백테스트 대비 ≤ 150%

### 8.3 Stage 3: 소량 실전
```
Week 1-2: 포지션당 50,000 KRW
Week 3-4: 포지션당 100,000 KRW (안정 시)
Week 5+:  리스크 기반 정상 사이즈 (자본 × 0.3%)
```

### 8.4 안전 장치
- 일일 -2% 하드 스탑
- 연속 5회 손실 30분 쿨다운
- API 오류 3회 연속 → 봇 자동 재시작 (Watchdog)
- 1분 내 ±3% 급변동 감지 → 30분 진입 중단
- 수동 Kill Switch: Telegram `/emergency_stop`

### 8.5 Telegram 명령어
기존 Ver3 명령어 패턴 재사용:
- `/status`, `/positions`, `/stop`, `/pause`, `/resume`, `/emergency_stop`
- `/performance` (주간 성과), `/factors` (현재 파라미터)

---

## 9. 실패 시 대응 플랜

### 9.1 3개 전략 모두 백테스트 실패 시
- 원인 분석: 전략 본질 문제 vs 파라미터 미세조정 필요
- 원인이 본질 → Tier 2 전략(Supertrend+VWAP, Heikin Ashi)로 재도전
- 원인이 미세조정 → 파라미터 그리드 확장 후 재실행
- 최악 시나리오: 스캘핑 포기, Ver3 개선 방향으로 회귀

### 9.2 Paper Trading 성과 저조 시
- 백테스트 대비 편차 분석 (수수료? 슬리피지? 시장 레짐?)
- Bithumb 실측 슬리피지 분포 리포트
- 전략 수정 또는 보수적 파라미터 재적용
- Paper 2주 추가 연장 판단

### 9.3 실전 배포 중 큰 손실 시
- `/emergency_stop`으로 즉시 중단
- 원인 분석 후 백테스트 재실행
- 파라미터 조정 or Paper Trading 복귀

---

## 10. 위험 & 한계

### 10.1 인지된 위험
1. **Binance vs Bithumb 데이터 차이**: 김프/환율 변동으로 실전에서 백테스트 대비 편차 발생 가능
   → Paper Trading 2~4주로 보정
2. **5m 캔들의 노이즈**: 가짜 신호 빈도 높음
   → 볼륨·모멘텀 필터 다중 적용
3. **수수료 민감도**: 0.08% 왕복이 누적 시 큰 부담
   → 평균 순수익 > 0.25% 엄격 준수
4. **과적합**: 파라미터 그리드 최적화로 과최적화 위험
   → Walk-Forward 7 세그먼트 + WFE > 0.5 필수
5. **레짐 변화**: BTC 시장 체제 급변 시 전략 무력화
   → 월간 파라미터 재평가, 일일 자본 -2% 하드 스탑

### 10.2 구현 한계
- 1초 단위 틱 데이터 없음 → 초 단위 미세 신호 활용 불가
- 호가창 데이터 제외 → 유동성 생김새(OFI) 기반 전략 제외
- 선물 데이터 제외 → Funding Rate, OI 기반 전략 제외
- 단일 거래소 → 거래소 간 차익거래 제외

---

## 11. 승인 기록

| 섹션 | 승인 |
|------|-----|
| 1. 목표 & 제약 | ✅ 2026-04-17 |
| 2. 전략 선정 | ✅ 2026-04-17 |
| 3. 아키텍처 | ✅ 2026-04-17 |
| 4. 데이터 레이어 | ✅ 2026-04-17 |
| 5. 전략 명세 (A·B·C) | ✅ 2026-04-17 |
| 6. 백테스트 엔진 | ✅ 2026-04-17 |
| 7. 리포팅 | ✅ 2026-04-17 |
| 8. 배포 경로 | ✅ 2026-04-17 |

---

## 12. 다음 단계

1. 본 설계서 사용자 최종 리뷰
2. `writing-plans` 스킬로 상세 구현 계획 수립
3. 구현 순서 (예상):
   - Phase 1: 데이터 레이어 + 지표 라이브러리 (2~3일)
   - Phase 2: 전략 3개 구현 + 단위 테스트 (3~5일)
   - Phase 3: 백테스트 엔진 + Walk-Forward (2~3일)
   - Phase 4: 리포팅 + Telegram 알림 (1~2일)
   - Phase 5: 백테스트 실행 + 비교 리포트 (1일)
   - Phase 6: Paper Trader + 실전 Executor (3~5일)

---

**문서 끝.**
