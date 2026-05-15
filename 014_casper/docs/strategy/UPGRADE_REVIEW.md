# 업그레이드 후보 상세 검토 — Partial TP / 5m ORB / Range Expansion

> **작성일**: 2026-05-15
> **선행**: [CASPER_SMC_SOURCE_REPORT.md](CASPER_SMC_SOURCE_REPORT.md)
> **목적**: 캐스퍼 SMC 분석에서 도출된 3개 업그레이드 후보 각각의 *이론·구현·차이·효과·리스크* 를 깊이 검토. 코드 변경은 아직 진행하지 않음 — 의사결정용 자료.

---

## 1. Partial TP (50% at 1.5R / 50% at 3R)

### 1.1 이론적 배경

전통적 단일 TP: 한 번에 모든 포지션 청산. 도달하면 풀 RR 수익, 도달 못하면 0 (또는 BE).

부분 TP의 의미: **확률·수익 곡선의 모양 자체를 바꿈**.

```
단일 TP (RR=3):                  부분 TP (50% @ 1.5R, 50% @ 3R):

P(TP)       Payoff               P(TP1)     P(TP2)    Payoff
─────       ──────               ──────     ──────    ──────
0.30        +3R                   0.50       0.20      +0.75R + +1.5R = +2.25R
0.70        -1R (또는 BE 0)       0.30 only  0          +0.75R + (-0.5R or 0) = +0.25R
                                   0.20       0          -1R
expectancy = 0.3×3 - 0.7×1 =       expectancy =
   = +0.20R                          0.20×(2.25) + 0.30×(0.25) + 0.50×(-1.0)
                                   = 0.45 + 0.075 - 0.50 = +0.025R
```

위 표의 확률은 가설 — 진짜 의미는 **TP1=1.5R이 TP=3R보다 *훨씬* 자주 도달한다**는 점. 미장봇이 60일 백테스트에서 **TP=3R 도달 0건**이었던 환경에서 *1.5R 부분 청산*은 작은 양수를 누적할 수 있다.

### 1.2 캐스퍼 community script의 정확한 룰

`hoosn1ck/Casper SMC: 5m ORB + Retest` Pine Script (TradingView)의 원문 옵션:

```pinescript
// 부분 TP 사양 (community script)
tp1_ratio        = 1.5        // 첫 TP는 1.5R
tp1_close_pct    = 50         // TP1에서 포지션의 50% 청산
tp2_ratio        = 3.0        // 두 번째 TP는 3R
move_sl_after_tp1 = true      // TP1 hit 후 SL을 ORB boundary로 이동
```

캐스퍼 본인 영상에서의 표현: *"Take half at 1:1 or 1.5R for breathing room, let the rest ride to 1:3"*. 즉:
- **TP1 = 1.5R** (또는 1R) → 50% close → 심리적 안정 + commission 보상
- **TP2 = 3R** → 나머지 50%
- TP1 hit 후 SL을 ORB high (long 기준) 또는 entry로 이동 → "free trade" 상태

### 1.3 현재 봇 구조

```python
# src/core/position.py (현재)
@dataclass
class Position:
    symbol: str
    entry_price: float
    stop_loss: float
    take_profit: float    # ★ 단일 값
    shares: int
    be_stop_moved: bool
```

```python
# src/bot.py::_handle_position_open (현재)
if bar.High >= self.position.take_profit:
    close_position(self.position)   # ★ 100% 청산
elif bar.Low <= self.position.stop_loss:
    close_position(self.position)
elif time >= 15:50:
    close_position(self.position)
```

### 1.4 구현 변경 영역

**Position dataclass 확장**:
```python
@dataclass
class Position:
    ...
    take_profit: float          # 그대로 (TP2)
    tp1_price: Optional[float]  # 신규
    tp1_ratio: float = 1.5      # 신규
    tp1_close_pct: float = 0.50 # 신규
    tp1_filled: bool = False    # 신규
    shares: int                 # current shares (after partial fills)
    shares_initial: int         # 신규 — 진입 시 shares
    partial_pnl: float = 0.0    # 신규 — 누적 부분 청산 PnL
```

**Bot 루프 변경**:
```python
def _handle_position_open(self):
    bar = ... # 최신 가격
    if not self.position.tp1_filled:
        if bar.High >= self.position.tp1_price:
            half_shares = self.position.shares // 2
            order_sell_market(self.position.symbol, half_shares)
            self.position.partial_pnl += (tp1_price - entry) * half_shares
            self.position.shares -= half_shares
            self.position.tp1_filled = True
            # SL을 ORB high로 이동 (BE shift 11:00보다 먼저 적용)
            self.position.stop_loss = max(
                self.position.stop_loss,
                self.position.orb_high  # ← Position에 orb_high 저장 필요
            )
            self.notifier.notify_partial_close(...)
    if bar.High >= self.position.take_profit:
        # 나머지 50% 청산
        order_sell_market(self.position.symbol, self.position.shares)
        ...
```

**Strategy 변경**: TradeSignal에 tp1_price 추가.

```python
take_profit = entry + risk * effective_rr   # 그대로 (TP2)
tp1_price = entry + risk * 1.5              # 신규
```

**Telegram 변경**: `notify_partial_close` 신규 메서드:
```
🟡 PARTIAL CLOSE TQQQ
TP1 ${tp1_price} × {half_shares}sh = +${partial_pnl}
Remaining: {remaining_shares}sh @ entry ${entry}
SL moved to ORB.high ${new_sl} (now free trade)
TP2 still ${target}
```

**Trade store 변경**: 한 매매가 2번 청산되므로 trade record 구조 확장 — `partial_exit_price`, `partial_exit_time`, `partial_exit_pnl`, `final_exit_price` 등.

### 1.5 차이 요약 (단일 TP vs 부분 TP)

| 차원 | 단일 TP (현재) | 부분 TP (제안) |
|---|---|---|
| TP 청산 횟수 | 1번 | 2번 (TP1, TP2) |
| TP1 도달 확률 | — | TP보다 *훨씬* 높음 (덜 멀리 가도 됨) |
| BE shift 시점 | 11:00 ET (고정) | TP1 hit 즉시 SL→ORB.high (TP1 미달 시 11:00 fallback) |
| 60일 백테스트 결과 | 0% WR, -0.01% | 0% WR (TP2 미달 동일), **+0.14% Ret** (TP1 부분 청산 효과) |
| 심리적 안정성 | TP까지 90분+ 기다림 | TP1 도달로 "break-even guaranteed" |
| 수수료 영향 | 1 buy + 1 sell | 1 buy + 2 sell — **수수료 ~50% 증가** |
| 코드 복잡도 | 단순 | Position state machine 확장 필요 |

### 1.6 백테스트 결과 재해석

```
Variant      Trd  WR%   PF    Ret%    AvgR
BASE_S_B      3   0.0%  0.00  -0.01%  -0.01
partial_TP    3   0.0%  15.71 +0.14%  +0.08
```

**같은 3건 매매에서**:
- BASE: TP=3R 미도달 → 11:00 BE에서 3건 모두 끊김. Net = commission 손실 ≈ -$0.07/trade ≈ -0.01%.
- partial_TP: TP1=1.5R 도달 → 50% 청산 (+0.75R × 50% shares). 나머지 50%는 SL=ORB.high로 이동 후 그 자리에서 끊김 (≈ BE) → Net ≈ +0.075R × 1매매 평균 = +$1.5 ~ +$3 / trade.

PF 15.71의 비밀: TP1 부분 청산이 winning side에 +0.075R씩 작은 수익을 만들고, losing side에는 매우 작은 손실(commission만)이라 비율이 15:1까지 벌어진 것. **표본 3건이라 신뢰는 약함**.

### 1.7 리스크 / 주의사항

| 리스크 | 정도 | 완화 |
|---|---|---|
| TP1 도달 후 가격이 다시 떨어져 SL=ORB hit | 중 | 그래도 TP1 부분 청산 +수익 락 |
| 수수료 50% 증가 (3 fills × 0.25%) | 중 | TP1 부분 청산이 commission보다 커야 net positive (현재 60d에서 충족) |
| TP1=1.5R 도달 후 TP2=3R까지 갈 모멘텀 없어 BE에서 끊김 | 높음 | 가장 흔한 시나리오. 부분 청산이 "보험" 역할 |
| 부분 청산 주문 실패 (KIS API 오류) | 낮음 | 기존 order_state_persistence 메커니즘으로 reconcile |
| ICT decision log에 partial_exit 이벤트 추가 필요 | 낮음 | 코드 추가 작업 |

### 1.8 도입 결정 요소

찬성 근거:
- 60일 백테스트 유일 양수 수익
- 캐스퍼 community script의 표준 옵션 (Reference Implementation)
- 60일 0% WR 환경에서 작은 양수 추출 메커니즘 — 통계적 의미 약하지만 *방향성 명확*
- 1.5R 도달은 3R보다 *훨씬 자주* — 캐스퍼 영상에서도 강조

반대 근거:
- 표본 3건 → 통계 무의미
- 코드 변경 영역 큼 (Position + bot 루프 + notifier + trade store)
- 수수료 부담 증가
- "TP1 후 SL=ORB.high"의 정확한 동작이 production에서 KIS 부분 체결과 어떻게 상호작용하는지 검증 필요

**제안**: paper 모드에서 1주~2주 검증 후 live 도입. 또는 신규 `entry.partial_tp_enabled` config 토글로 즉시 ON/OFF 가능하게 설계.

---

## 2. 5m ORB 옵션

### 2.1 ORB 길이의 의미

ORB(Opening Range Breakout)는 *개장 직후 N분간의 high/low* 를 reference로 사용. N 값에 따라 setup 특성이 크게 달라짐.

| N | 봉 수 | ORB 시간 | 첫 진입 가능 시각 | 캐스퍼 자료에서 |
|---|:---:|---|---|---|
| **5분** | 1봉 | 09:30~09:34 | 09:35 | hoosn1ck community script |
| **15분** | 3봉 | 09:30~09:44 | 09:45 | **현재 봇** + ICT 정통 |
| **30분** | 6봉 | 09:30~09:59 | 10:00 | First Candle Rule (TikTok) |

### 2.2 ORB 길이가 setup에 미치는 영향

#### (a) Range 폭

```
일반적인 NQ/QQQ 변동성에서:
5분 ORB:   ATR ≈ 0.30R (작음)
15분 ORB:  ATR ≈ 0.70R (중간)
30분 ORB:  ATR ≈ 1.20R (큼)
```

→ ORB가 짧을수록 *range가 좁고*, 돌파가 *자주* 발생하지만 *false breakout 위험* 증가.

#### (b) 진입 윈도우

미장봇 scan_window = ORB 종료 ~ 10:55. ORB 길이에 따라:

```
5분 ORB:   09:35 ~ 10:55 = 80분 진입 가능
15분 ORB:  09:45 ~ 10:55 = 70분 진입 가능 (현재)
30분 ORB:  10:00 ~ 10:55 = 55분 진입 가능
```

#### (c) ICT Killzone 정렬 (Scenario B 영향)

```
AM_MACRO = 09:30~10:10
AM_LATE  = 10:10~10:55

5분 ORB:   AM_MACRO 안 후보 봉 7개 (09:35~10:09)
15분 ORB:  AM_MACRO 안 후보 봉 5개 (09:45~10:09) ★ 현재
30분 ORB:  AM_MACRO 안 후보 봉 2개 (10:00~10:09)
```

→ **5분 ORB는 AM_MACRO setup 후보를 40% 더 확보**. 캐스퍼의 "AM Macro killzone 핵심" 철학과 더 잘 맞음.

### 2.3 현재 봇 구조

`src/core/orb.py`에서 ORB 계산:

```python
def calculate_orb(bars: pd.DataFrame, date: str,
                 start_time: str = "09:30",
                 end_time: str = "09:45") -> Optional[OpeningRange]:
    orb_bars = bars.between_time(start_time, end_time_minus_1)
    if len(orb_bars) < 3:
        return None
    return OpeningRange(
        date=date,
        high=float(orb_bars["High"].max()),
        low=float(orb_bars["Low"].min()),
        range_size=...
    )
```

봇 상태머신:
```python
# bot.py
def is_orb_forming() -> bool:
    return dtime(9, 30) <= now < dtime(9, 45)

def is_scan_window() -> bool:
    return dtime(9, 45) <= now <= dtime(10, 55)
```

### 2.4 구현 변경 영역

**config 변경**:
```json
{
    "orb": {
        "start_time": "09:30",
        "end_time": "09:45",        // 현재
        "minutes": 15,               // 현재
        // 신규
        "window_minutes": 15        // 5 | 15 | 30 중 선택
    }
}
```

또는 더 단순히 `minutes` 키만 사용하고 `end_time`을 derive.

**time_utils 변경**:
```python
def is_orb_forming(minutes: int = 15) -> bool:
    end_h = 9
    end_m = 30 + minutes
    if end_m >= 60:
        end_h += end_m // 60
        end_m %= 60
    return dtime(9, 30) <= now < dtime(end_h, end_m)

def is_scan_window(orb_minutes: int = 15) -> bool:
    # scan starts at ORB end
    end_h = 9; end_m = 30 + orb_minutes
    ...
    return dtime(end_h, end_m) <= now <= dtime(10, 55)
```

**state machine 변경**: 상수 dtime을 minutes config 의존으로 변경.

**Killzone 영향**: `sessions.py`의 AM_MACRO 09:30~10:10 정의는 *그대로 유지* — ORB 길이와 무관한 ICT 정통 시간대.

### 2.5 차이 요약 (15m vs 5m vs 30m)

| 차원 | 15m (현재) | 5m | 30m |
|---|---|---|---|
| ORB 형성 시간 | 09:30~09:44 | 09:30~09:34 | 09:30~09:59 |
| Scan window 시작 | 09:45 | **09:35** | 10:00 |
| Scan window 길이 | 70분 | **80분** | 55분 |
| AM_MACRO 안 후보 | 5봉 | **7봉** | 2봉 |
| AM_LATE 안 후보 | 9봉 | 9봉 | 9봉 |
| ORB range 크기 | 중 | **작음 (fake breakout↑)** | 큼 (안정) |
| Strict S2 충족 빈도 | 중 | 낮음 (좁은 range가 ORB.high와 FVG.top 겹치기 어려움) | 높음 |
| 60일 백테스트 매매 | 3건 | **6건** | 2건 |
| WR | 0% | **16.7%** | 0% |
| PF | 0.00 | 0.83 | 0.00 |
| Net Ret | -0.01% | -0.35% | -0.01% |

### 2.6 백테스트 결과 깊이 해석

**5m_ORB 매매 6건, WR 16.7% (1승 5패)**:
- 매매 빈도 2배 → 데이터 누적 속도 2배 → AM_LATE PRECHECK 재검증 시점이 빨라짐
- WR 16.7%는 BASE 0%보다 *수치상* 나음. 단 표본 6건 → 1승이 만든 차이라 통계 의미 약함
- Net Ret -0.35% → 추가 5건의 loss가 commission 누적
- **트레이드오프 명확**: 빈도 ↑ / 품질 ↓

**30m_ORB는 5m와 정반대**: 매매 2건, 빈도 ↓. 둘 다 BASE보다 못함.

### 2.7 리스크 / 주의사항

| 리스크 | 정도 | 메모 |
|---|---|---|
| 5분 ORB의 좁은 range → fake breakout | 높음 | strict S2 (FVG-ORB intersect)가 자연 필터 |
| 매매 빈도 ↑로 commission 누적 (-0.35%) | 중 | 60d 표본만 — 1년 데이터에서 PF가 1.0+ 가능성 있음 |
| AM_MACRO 후보 봉 수↑로 displacement filter reject도 ↑ | 중 | ICT decision log에 더 풍부한 표본 누적 |
| 30분 ORB는 AM_MACRO 후보 거의 없음 | 높음 | 채택 비추천 — Scenario B와 충돌 |

### 2.8 도입 결정 요소

찬성:
- 캐스퍼 community script가 5m 사용 — Reference Implementation
- AM_MACRO 후보 40% 증가 → 캐스퍼 철학과 정합성 ↑
- 라이브 표본 누적 가속 → PRECHECK 재검증 시점 단축
- 코드 변경 최소 (`time_utils.py` + `config.orb.minutes` 만)

반대:
- 60일 백테스트에서 Net Ret 악화 (-0.01% → -0.35%)
- WR은 올라가지만 PF는 0.83 (1.0 미만 = 손실 우세)
- 좁은 range가 false breakout 위험 ↑

**제안**: A/B 옵션으로 config만 추가하고 paper 모드에서 1~2주 테스트. 5m ORB 후보 봉의 ict_decisions JSONL 분석 후 *어느 시간대*에서 5m가 15m보다 나은지 확인 가능.

---

## 3. Range Expansion Strategy (Phase 5)

### 3.1 이론적 배경

ICT 본가(Michael Huddleston)의 multi-timeframe 분석에서 출발:

> "Higher timeframe(HTF) tells you the *story*, lower timeframe(LTF) gives you the *entry*."

**Range Expansion = HTF의 임펄스 캔들이 직전 range를 *확장* 하는 사건**. 일반적 통합(consolidation) 구간을 break하며 큰 body로 close하는 캔들. 그 *방향*이 institutional flow의 signal이라는 가설.

| 시간대 | 의미 | 미장봇 현재 사용 |
|---|---|---|
| Monthly | 거시 추세 | ✗ |
| Weekly | 중기 추세 | ✗ |
| Daily | 일별 bias | ✓ (compute_daily_bias) |
| **4H** | **세션 내 expansion** | **✗ — Phase 5 후보** |
| **1H** | **세션 내 expansion** | **✗ — Phase 5 후보** |
| 15m | mid-frequency | ✗ |
| 5m | breakout candle | ✓ (FVG breakout) |
| 1m | swing/SL refinement | ✓ (multi_tf_sl) |

### 3.2 알고리즘 (캐스퍼 Mastery Course 재구성)

#### (a) HTF Range 정의

```
HTF candle = 1H (또는 4H)
range_period = 직전 N개 캔들 (default N=10)
range_high = max(close of last N candles)
range_low  = min(close of last N candles)
range_size = range_high - range_low

is_consolidation:
    range_size < avg_candle_body × 2.0    # 좁은 range
```

#### (b) Expansion 감지

```
expansion_candle = 현재 닫힌 1H candle
body = |Close - Open|
total = High - Low

is_expansion:
    body > range_size × 1.5                # range를 1.5배 넘는 큰 body
    body > avg_body × 2.0                  # 평균 body의 2배 이상
    wick < 0.40                            # 종가 우세 (꼬리 < 40%)

expansion_direction:
    'bull' if Close > Open
    'bear' if Close < Open
```

#### (c) LTF Entry Alignment

```
이번 5분봉 setup의 direction (bull/bear)이
expansion_direction과 일치할 때만 진입.

if bot detected ORB breakout (bull):
    if last_4H_expansion_direction == 'bull':
        proceed with signal
    else:
        reject (HTF/LTF misalignment)
```

#### (d) 캐스퍼 영상에서의 강조

캐스퍼의 가르침 골자: *"한 번에 큰 움직임이 나오는 시간대로 거래해라"*. Range Expansion은 그 시간대를 정량적으로 식별하는 도구. 매매 빈도가 추가로 줄어들지만 *남은 매매의 quality는 매우 높다*고 주장.

### 3.3 봇과의 차이

#### 현재 봇의 multi-timeframe

```
Daily Bias (compute_daily_bias):
  PDH/PDL + PWH/PWL + MA20/50 + Power of 3 (NQ)
  → score → bull/bear/neutral

Multi-TF SL (use_multi_tf_sl):
  5분봉 진입 setup → 1분봉 swing 사용해 SL 단축

[누락된 차원]
  1H/4H expansion → 일중 *방향성 강도* 검증
```

#### Range Expansion 추가 시

```
ORB breakout detected (5m) →
  ↓ direction 캡처 (bull/bear)
Killzone check ✓
Displacement check ✓
Sweep+CHoCH check ✓
FVG strict check ✓
  ↓ ★ Range Expansion check (신규)
  4H candles 최근 12개 → 가장 최근 expansion 식별
  if expansion_direction != setup_direction: REJECT
  ↓
OTE / Unicorn / MTF-SL
Signal emit
```

#### Daily Bias와의 차이

| 차원 | Daily Bias (현재) | Range Expansion (신규) |
|---|---|---|
| 시간대 | 1일 단위 | 1H/4H 단위 (intra-day) |
| Input | PDH/PDL/PWH/PWL/MA20/50 | 최근 10~12개 HTF candle |
| 산출물 | bull/bear/neutral + score | bull/bear/none (single direction) |
| 빈도 | 매일 1회 (pre-market) | 1H 또는 4H bar close마다 갱신 |
| Reject 강도 | neutral인 날만 매매 skip | direction mismatch면 매매 skip |

→ **Daily Bias = "오늘의 전반적 분위기"**, **Range Expansion = "지금 방향성이 활발한가"**. 보완적 — 둘 다 통과해야 진입.

### 3.4 구현 영역

신규 모듈: `src/core/range_expansion.py`

```python
@dataclass
class RangeExpansion:
    """1H or 4H expansion candle detection."""
    timeframe: str            # "1h" or "4h"
    expansion_time: pd.Timestamp
    direction: str            # "bull" or "bear"
    body_ratio: float         # body / avg_body
    range_break_ratio: float  # body / range_size
    wick_ratio: float


def detect_recent_expansion(
    htf_bars: pd.DataFrame,
    lookback: int = 12,
    range_period: int = 10,
    min_body_range_ratio: float = 1.5,
    min_body_avg_ratio: float = 2.0,
    max_wick: float = 0.40,
) -> Optional[RangeExpansion]:
    """Find the most recent expansion candle in HTF bars."""
    ...
```

데이터 fetch: `src/data/market_data.py`에 `get_intraday_bars(symbol, interval="1h")` 추가. yfinance는 1h 데이터를 730일까지 제공 (5m의 60일보다 훨씬 김).

`scan_for_signal` 통합:
```python
def scan_for_signal(
    bars_5m, orb, symbol, ...,
    require_range_expansion: bool = False,
    htf_bars: Optional[pd.DataFrame] = None,
    htf_timeframe: str = "4h",
    range_expansion_lookback: int = 12,
):
    ...
    if require_range_expansion and htf_bars is not None:
        expansion = detect_recent_expansion(htf_bars, lookback=range_expansion_lookback)
        if expansion is None:
            _log_decision(event="range_expansion", passed=False,
                          reason="no recent expansion")
            continue
        if expansion.direction != direction:
            _log_decision(event="range_expansion", passed=False,
                          reason=f"misalign {expansion.direction} vs {direction}")
            continue
        _log_decision(event="range_expansion", passed=True,
                      details={"htf": htf_timeframe, "body_ratio": expansion.body_ratio})
```

`bot.py` 변경: pre-market에서 1H/4H bars fetch + cache:
```python
def _handle_pre_market(self):
    ...
    if entry_params.get("require_range_expansion"):
        self._htf_bars = get_intraday_bars(
            self.params["symbols"]["trend_filter"],
            period="60d", interval=entry_params.get("htf_timeframe", "1h")
        )
```

`config/strategy_params.json`:
```json
"entry": {
    ...
    "require_range_expansion": false,    // default OFF (Phase 5 도입 시 ON)
    "htf_timeframe": "4h",
    "range_expansion_lookback": 12,
    "range_expansion_min_body_range_ratio": 1.5,
    "range_expansion_min_body_avg_ratio": 2.0,
    "range_expansion_max_wick": 0.40
}
```

### 3.5 백테스트 가능성

- **데이터 가용성**: yfinance 1H 730일, 4H 730일 — 60일 한도 없음. **장기 백테스트 가능**.
- **합성 도구**: `scripts/range_expansion_backtest.py` (신규 작성 필요):
  ```
  for each day in 1년 데이터:
      4H candles 최근 12개 fetch
      expansion 감지
      → 만약 expansion 있고, 그 방향과 일치하는 5분봉 setup이 그날 발생했는가?
  ```
- **예상 결과**: 매매 빈도 추가 감소 (필터 강화). 60일 baseline에서 0~4건이었던 게 0~2건 수준 가능. **표본 부족 문제가 더 심해질 수 있음**.

### 3.6 효과 가설

| 시나리오 | 가설 |
|---|---|
| 가장 낙관적 | HTF/LTF 정렬된 매매는 WR ≥ 70%, AvgR ≥ 1.0R (캐스퍼 마케팅 주장 수준) |
| 중간 | WR 50~60%, AvgR 0.3~0.5R (PHASE1_PRECHECK 수준) |
| 가장 비관적 | 매매 0건. PHASE2/3 백테스트 0건과 동일 운명 |

이 가설의 정량 검증이 Phase 5의 첫 작업.

### 3.7 리스크 / 주의사항

| 리스크 | 정도 | 완화 |
|---|---|---|
| 매매 빈도 추가 감소 → 0건 가능성 | 매우 높음 | 데이터 누적 1년+ 필요. 짧은 백테스트로 의미 없는 결과 |
| HTF expansion 정의의 임계값(1.5, 2.0, 0.40)이 자의적 | 중 | PRECHECK처럼 작은 표본으로 임계값 결정하면 함정 |
| 4H 데이터의 timezone 처리 (한국 broker vs ET 시장 시간) | 낮음 | 이미 정립된 패턴 (tz_convert) |
| Daily Bias와의 중복 — 둘 다 같은 방향 정보 | 중 | Daily Bias = 일별, Range Expansion = 일중. 보완적이지만 *높은 상관* 가능 |
| ICT decision log 이벤트 추가 (range_expansion) | 낮음 | 코드 라인 ~10줄 |

### 3.8 단계별 도입 plan

#### Phase 5.0 — 데이터 분석 (1주)
- yfinance 1H/4H 1년 fetch
- 미장봇이 60일 백테스트에서 발견했던 모든 매매(현재 3건 + 추가)에 대해 *그 시점의 expansion이 같은 방향이었는가* 검증
- 만약 *모두 정렬* 또는 *완전 미스* 같은 극단이면 Phase 5 가치 자동 판정

#### Phase 5.1 — 단독 백테스트 (1주)
- `scripts/range_expansion_backtest.py` 작성
- baseline(현재 Scenario B) vs +Range Expansion 비교
- 60일·1년 두 기간 모두 측정

#### Phase 5.2 — 모듈 통합 (1~2주)
- `src/core/range_expansion.py` 신규
- `src/data/market_data.py::get_intraday_bars` 1H/4H 지원 확장
- `scan_for_signal` 게이트 추가 (default OFF)
- 봇 pre-market에 HTF cache 로드
- ICT decision log 이벤트 추가

#### Phase 5.3 — paper 검증 (2~4주)
- `entry.require_range_expansion=true` paper 모드 운용
- ict_decisions/*.jsonl 누적
- 매매 빈도가 0건 가까이면 임계값 완화 vs 폐기 결정

#### Phase 5.4 — live 도입 또는 기각

만약 Phase 5.3에서 paper 매매가 baseline 대비 *유의미한 개선*을 보이면 live 도입. 그렇지 않으면 **모듈은 유지하되 config default OFF로 dormant** — 미래 임계값 튜닝 시 활용 가능.

### 3.9 캐스퍼 마케팅 vs 현실 (회의적 평가)

캐스퍼는 Range Expansion이 그의 mastery course의 핵심 모듈이라 강조. 하지만:

1. **PHASE1_PRECHECK n=11에서 HTF expansion 차원은 검증 안 됨** — 실거래 데이터로 효과 측정된 적 없음
2. **ImanTrading의 SIM 위장 의혹**과 동일 맥락 — 캐스퍼가 보여주는 winning examples는 cherry-pick일 가능성
3. **60일 백테스트에서 매매 0~4건** — 추가 필터는 그 빈도를 더 떨어뜨릴 위험

→ **Phase 5는 가르침의 원본을 *충실히 구현*하는 데 의의가 있고, 그것이 실제로 *수익을 보장*하지는 않는다는 점을 명시**. 모듈 추가 후에도 default OFF 유지가 안전.

---

## 4. 종합 우선순위 (재정리)

| 우선순위 | 후보 | 60일 결과 | 도입 비용 | 즉시 권고 |
|:---:|---|---|---|---|
| 1 | **Partial TP** | **+0.14% (유일 양수)** | 중 (Position+bot+notifier 변경) | paper 1~2주 후 live |
| 2 | **5m ORB** | Net -0.35% but 빈도 2배 | 낮 (config + time_utils) | A/B 옵션으로 추가, paper 비교 |
| 3 | **Range Expansion** | 미실행 (Phase 5) | 높 (신규 모듈 + 데이터 + 통합) | Phase 5.0 데이터 분석부터 |
| - | ADX / 4H VWAP 필터 | 매매 0~1건 | 낮 | **보류** — 60일에 정량 평가 불가 |
| - | SL = ORB midpoint | BASE와 무차이 | 중 | **보류** |

---

## 5. 다음 결정 사항

선생님께서 결정해주실 부분:

1. **Partial TP 즉시 도입?** — config 토글로 추가 + paper 1~2주 테스트 후 live, 또는 바로 live 시도
2. **5m ORB A/B 추가?** — config만 추가하면 즉시 가능. 라이브 표본 누적 가속 부수효과
3. **Phase 5 (Range Expansion) 시작?** — Phase 5.0 (1주 데이터 분석)부터 진행 가능. 또는 deferred

각각 별도 결정 가능 — 모두 ON, 일부만, 전체 deferred 모두 옵션.
