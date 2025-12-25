# 백테스팅 규칙

## 백테스트 설정

### 기본 파라미터
```python
BacktestConfig(
    initial_capital=100_000_000,    # 초기 자본: 1억원
    commission_rate=0.00015,         # 수수료: 0.015%
    slippage_rate=0.001,             # 슬리피지: 0.1%
    max_position_size=0.10,          # 최대 포지션: 10%
    target_position_count=20,        # 목표 종목 수: 20개
    rebalance_frequency="M",         # 리밸런싱: 월간
    stop_loss_pct=0.07,              # 손절: -7%
    take_profit_pct=0.15,            # 익절: +15%
)
```

### 리밸런싱 빈도
```python
FREQUENCY_MAP = {
    "D": "일간",      # 매일 리밸런싱 (비권장)
    "W": "주간",      # 매주 월요일
    "M": "월간",      # 매월 첫 거래일
    "Q": "분기",      # 분기별 (3, 6, 9, 12월)
}
```

## 시뮬레이션 로직

### 거래 시뮬레이션
```python
def simulate_trade(order, market_data):
    # 슬리피지 적용
    if order.side == "BUY":
        execution_price = order.price * (1 + slippage_rate)
    else:
        execution_price = order.price * (1 - slippage_rate)

    # 수수료 계산
    trade_value = order.quantity * execution_price
    commission = trade_value * commission_rate

    # 순 비용/수익
    if order.side == "BUY":
        net_cost = trade_value + commission
    else:
        net_proceeds = trade_value - commission

    return Trade(
        date=order.date,
        stock_code=order.stock_code,
        side=order.side,
        quantity=order.quantity,
        price=execution_price,
        commission=commission,
    )
```

### 일간 평가
```python
def evaluate_daily(date, positions, prices):
    total_value = cash

    for pos in positions:
        current_price = prices[pos.stock_code][date]

        # 손절/익절 체크
        if pos.unrealized_pnl_pct <= -stop_loss_pct:
            execute_stop_loss(pos)
        elif pos.unrealized_pnl_pct >= take_profit_pct:
            execute_take_profit(pos)

        total_value += pos.quantity * current_price

    return DailySnapshot(
        date=date,
        equity=total_value,
        cash=cash,
        positions=len(positions),
    )
```

## 성과 지표 계산

### 수익률
```python
# 총 수익률
total_return = (final_equity - initial_capital) / initial_capital

# 연환산 수익률 (CAGR)
years = (end_date - start_date).days / 365.25
cagr = (final_equity / initial_capital) ** (1 / years) - 1

# 일간 수익률
daily_returns = equity_curve.pct_change()
```

### 리스크 지표
```python
# 변동성 (연환산)
volatility = daily_returns.std() * np.sqrt(252)

# 최대 낙폭 (MDD)
rolling_max = equity_curve.cummax()
drawdown = (equity_curve - rolling_max) / rolling_max
max_drawdown = drawdown.min()

# 낙폭 기간
drawdown_start = drawdown.idxmin()
recovery = equity_curve[drawdown_start:] >= rolling_max[drawdown_start]
if recovery.any():
    drawdown_end = recovery.idxmax()
    drawdown_days = (drawdown_end - drawdown_start).days
```

### 위험조정 수익률
```python
# 샤프 비율 (무위험 수익률 3% 가정)
risk_free_rate = 0.03
excess_return = cagr - risk_free_rate
sharpe_ratio = excess_return / volatility

# 소르티노 비율 (하방 변동성만 고려)
negative_returns = daily_returns[daily_returns < 0]
downside_std = negative_returns.std() * np.sqrt(252)
sortino_ratio = excess_return / downside_std

# 칼마 비율
calmar_ratio = cagr / abs(max_drawdown)
```

### 거래 통계
```python
# 승률
win_trades = [t for t in trades if t.pnl > 0]
lose_trades = [t for t in trades if t.pnl < 0]
win_rate = len(win_trades) / len(trades)

# 손익비
avg_win = np.mean([t.pnl for t in win_trades])
avg_loss = abs(np.mean([t.pnl for t in lose_trades]))
profit_loss_ratio = avg_win / avg_loss

# 수익 팩터
gross_profit = sum(t.pnl for t in win_trades)
gross_loss = abs(sum(t.pnl for t in lose_trades))
profit_factor = gross_profit / gross_loss
```

## 벤치마크 비교

### KOSPI 지수 비교
```python
def compare_with_benchmark(strategy_returns, benchmark_returns):
    # 베타
    covariance = np.cov(strategy_returns, benchmark_returns)[0][1]
    benchmark_variance = np.var(benchmark_returns)
    beta = covariance / benchmark_variance

    # 알파 (Jensen's Alpha)
    strategy_avg = np.mean(strategy_returns) * 252
    benchmark_avg = np.mean(benchmark_returns) * 252
    alpha = strategy_avg - (risk_free_rate + beta * (benchmark_avg - risk_free_rate))

    # 정보 비율
    tracking_error = (strategy_returns - benchmark_returns).std() * np.sqrt(252)
    information_ratio = (strategy_avg - benchmark_avg) / tracking_error

    return BenchmarkComparison(
        alpha=alpha,
        beta=beta,
        information_ratio=information_ratio,
        correlation=np.corrcoef(strategy_returns, benchmark_returns)[0][1],
    )
```

## 결과 리포트

### 텍스트 리포트
```
═══════════════════════════════════════════════════════
           멀티팩터 전략 백테스트 결과
═══════════════════════════════════════════════════════

기간: 2023-01-01 ~ 2024-12-31 (2년)
초기 자본: ₩100,000,000
최종 자산: ₩123,456,789

[수익률]
총 수익률: +23.46%
연환산(CAGR): +11.08%
벤치마크 대비: +5.32%

[리스크]
연간 변동성: 15.23%
최대 낙폭(MDD): -12.45%
낙폭 기간: 45일

[위험조정 수익률]
샤프 비율: 0.85
소르티노 비율: 1.23
칼마 비율: 0.89

[거래 통계]
총 거래 수: 248회
승률: 58.5%
손익비: 1.45
수익 팩터: 1.82
평균 보유 기간: 22일

═══════════════════════════════════════════════════════
```

### 차트 생성
```python
# 1. 자산 곡선
chart.plot_equity_curve(equity_curve, benchmark)

# 2. 낙폭 차트
chart.plot_drawdown(equity_curve)

# 3. 월간 수익률 히트맵
chart.plot_monthly_returns(equity_curve)

# 4. 섹터별 수익 기여도
chart.plot_sector_attribution(positions)
```

## 검증 규칙

### 데이터 검증
```python
VALIDATION_RULES = [
    # 가격 데이터
    "no_negative_prices",
    "no_zero_prices",
    "no_missing_dates",

    # 재무 데이터
    "valid_per_range",      # PER: 0 < x < 100
    "valid_roe_range",      # ROE: -100% < x < 100%

    # 거래 데이터
    "no_future_trades",     # 미래 데이터 사용 금지
    "valid_trade_dates",    # 거래일에만 거래
]
```

### Look-Ahead Bias 방지
```python
# 잘못된 예 (미래 데이터 사용)
today_close = prices[today]
signal = calculate_signal(today_close)  # ❌ 오늘 종가로 오늘 매매

# 올바른 예
yesterday_close = prices[yesterday]
signal = calculate_signal(yesterday_close)  # ✅ 어제 종가로 오늘 매매
```

### Survivorship Bias 방지
```python
# 상장폐지 종목 포함
def get_universe(date):
    # 해당 시점에 상장되어 있던 종목 반환
    # (현재 상장 종목이 아닌 당시 상장 종목)
    return get_historical_universe(date)
```

## 백테스트 실행 예시

```python
from src.strategy.quant import (
    Backtester, BacktestConfig,
    PerformanceAnalyzer, ChartGenerator
)

# 1. 설정
config = BacktestConfig(
    initial_capital=100_000_000,
    rebalance_frequency="M",
)

# 2. 백테스트 실행
backtester = Backtester(config)
result = backtester.run(
    price_data=prices,
    signals=signals,
    start_date="2023-01-01",
    end_date="2024-12-31"
)

# 3. 성과 분석
analyzer = PerformanceAnalyzer()
metrics = analyzer.calculate_metrics(result.equity_curve)

# 4. 리포트 생성
print(analyzer.generate_report(metrics))

# 5. 차트 저장
chart = ChartGenerator()
chart.plot_equity_curve(result.equity_curve)
chart.save("backtest_result.png")
```
