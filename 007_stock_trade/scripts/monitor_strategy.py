#!/usr/bin/env python3
"""
전략 성과 모니터링 스크립트
- 현재 가중치의 유효성 검증
- 재조정 필요 여부 판단
- 경고 알림
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pykrx import stock
import json
import warnings
warnings.filterwarnings('ignore')

from src.strategy.quant.backtest import Backtester, BacktestConfig


# 현재 최적 가중치 (2025-12 최적화 결과)
CURRENT_WEIGHTS = {
    "momentum_weight": 0.20,
    "short_mom_weight": 0.10,
    "volatility_weight": 0.50,
    "volume_weight": 0.00,
    "target_count": 15,
    "optimized_date": "2025-12-27",
    "baseline_sharpe": 2.39,
    "baseline_return": 8.99,
    "baseline_mdd": -2.14
}

# 경고 임계값
ALERT_THRESHOLDS = {
    "sharpe_min": 1.0,          # 샤프비율 최소
    "mdd_max": -10.0,           # MDD 최대
    "win_rate_min": 40.0,       # 승률 최소
    "profit_factor_min": 1.0,   # 수익팩터 최소
    "sharpe_drop_pct": 50.0,    # 샤프비율 하락률 최대
}


def get_price_data(ticker: str, start: str, end: str) -> pd.DataFrame:
    """가격 데이터 조회"""
    try:
        df = stock.get_market_ohlcv(start, end, ticker)
        if df.empty:
            return None
        df = df.rename(columns={
            '시가': 'open', '고가': 'high', '저가': 'low',
            '종가': 'close', '거래량': 'volume'
        })
        df = df.reset_index()
        df = df.rename(columns={'날짜': 'date'})
        df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
        df['date'] = pd.to_datetime(df['date'])
        return df
    except:
        return None


def generate_signals(price_data, date, weights, top_n=15):
    """신호 생성"""
    scores = []

    for code, df in price_data.items():
        if df is None or df.empty:
            continue
        df_until = df[df['date'] <= date]
        if len(df_until) < 60:
            continue

        prices = df_until['close']

        # 모멘텀
        mom_60 = (prices.iloc[-1] / prices.iloc[-60] - 1) * 100 if len(prices) >= 60 else 0
        mom_20 = (prices.iloc[-1] / prices.iloc[-20] - 1) * 100 if len(prices) >= 20 else 0

        # 변동성
        returns = prices.pct_change().dropna()
        vol = returns.tail(20).std() * np.sqrt(252) * 100 if len(returns) >= 20 else 999

        # 52주 고점
        high_52w = prices.tail(252).max() if len(prices) >= 252 else prices.max()
        from_high = (prices.iloc[-1] / high_52w) if high_52w > 0 else 0

        score = (
            mom_60 * weights["momentum_weight"] +
            mom_20 * weights["short_mom_weight"] -
            vol * weights["volatility_weight"] +
            from_high * 10
        )

        scores.append({'code': code, 'name': code, 'score': score})

    if not scores:
        return pd.DataFrame()

    df = pd.DataFrame(scores)
    df = df.nlargest(top_n, 'score')
    df['date'] = date
    df['signal'] = 'BUY'
    df['weight'] = 1.0 / len(df)
    return df


def run_validation(months: int = 3) -> dict:
    """최근 N개월 성과 검증"""

    end_date = datetime.now() - timedelta(days=2)
    # 백테스트를 위해 충분한 lookback 기간 확보 (60일 + 검증 기간)
    data_start = end_date - timedelta(days=months * 30 + 90)
    start_date = end_date - timedelta(days=months * 30)

    data_start_str = data_start.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")

    # 데이터 수집
    for i in range(7):
        check_date = (end_date - timedelta(days=i)).strftime("%Y%m%d")
        tickers = stock.get_index_portfolio_deposit_file("1028", check_date)
        if tickers is not None and len(tickers) > 0:
            break

    tickers = list(tickers)[:50]

    price_data = {}
    for ticker in tickers:
        df = get_price_data(ticker, data_start_str, end_str)
        if df is not None and len(df) >= 60:
            price_data[ticker] = df

    if len(price_data) < 10:
        return {"error": "데이터 부족"}

    # 백테스트
    config = BacktestConfig(
        initial_capital=100_000_000,
        target_position_count=CURRENT_WEIGHTS["target_count"],
        rebalance_frequency="M",
    )

    sample_df = list(price_data.values())[0]
    trading_dates = sample_df['date'].tolist()

    all_signals = []
    for date in trading_dates:
        if date < start_date or date > end_date:
            continue
        if date.day <= 3:
            signals = generate_signals(price_data, date, CURRENT_WEIGHTS,
                                       CURRENT_WEIGHTS["target_count"])
            if not signals.empty:
                all_signals.append(signals)

    if not all_signals:
        return {"error": "신호 생성 실패"}

    signals_df = pd.concat(all_signals, ignore_index=True)

    backtester = Backtester(config)
    result = backtester.run(price_data, signals_df, start_date, end_date)

    return {
        "period_months": months,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "total_return": result.total_return,
        "sharpe_ratio": result.sharpe_ratio,
        "sortino_ratio": result.sortino_ratio,
        "max_drawdown": result.max_drawdown,
        "win_rate": result.win_rate,
        "profit_factor": result.profit_factor,
        "total_trades": result.total_trades
    }


def check_alerts(metrics: dict) -> list:
    """경고 체크"""
    alerts = []

    # 샤프비율 체크
    if metrics.get("sharpe_ratio", 0) < ALERT_THRESHOLDS["sharpe_min"]:
        alerts.append({
            "level": "CRITICAL",
            "message": f"샤프비율 {metrics['sharpe_ratio']:.2f} < {ALERT_THRESHOLDS['sharpe_min']}",
            "action": "즉시 재최적화 필요"
        })

    # 샤프비율 하락률 체크
    baseline = CURRENT_WEIGHTS["baseline_sharpe"]
    current = metrics.get("sharpe_ratio", 0)
    drop_pct = (baseline - current) / baseline * 100 if baseline > 0 else 0
    if drop_pct > ALERT_THRESHOLDS["sharpe_drop_pct"]:
        alerts.append({
            "level": "WARNING",
            "message": f"샤프비율 {drop_pct:.1f}% 하락 (기준: {baseline:.2f} → 현재: {current:.2f})",
            "action": "재최적화 검토"
        })

    # MDD 체크
    if metrics.get("max_drawdown", 0) < ALERT_THRESHOLDS["mdd_max"]:
        alerts.append({
            "level": "CRITICAL",
            "message": f"MDD {metrics['max_drawdown']:.2f}% < {ALERT_THRESHOLDS['mdd_max']}%",
            "action": "리스크 관리 점검"
        })

    # 승률 체크
    if metrics.get("win_rate", 0) < ALERT_THRESHOLDS["win_rate_min"]:
        alerts.append({
            "level": "WARNING",
            "message": f"승률 {metrics['win_rate']:.1f}% < {ALERT_THRESHOLDS['win_rate_min']}%",
            "action": "전략 검토"
        })

    # 수익팩터 체크
    if metrics.get("profit_factor", 0) < ALERT_THRESHOLDS["profit_factor_min"]:
        alerts.append({
            "level": "CRITICAL",
            "message": f"수익팩터 {metrics['profit_factor']:.2f} < {ALERT_THRESHOLDS['profit_factor_min']}",
            "action": "손실 > 수익, 즉시 점검"
        })

    return alerts


def main():
    print("\n" + "=" * 60)
    print("     전략 성과 모니터링")
    print("=" * 60)

    print(f"\n현재 설정된 가중치 (최적화일: {CURRENT_WEIGHTS['optimized_date']})")
    print(f"  모멘텀: {CURRENT_WEIGHTS['momentum_weight']}")
    print(f"  단기모멘텀: {CURRENT_WEIGHTS['short_mom_weight']}")
    print(f"  변동성: {CURRENT_WEIGHTS['volatility_weight']}")
    print(f"  목표종목: {CURRENT_WEIGHTS['target_count']}개")
    print(f"\n  기준 샤프비율: {CURRENT_WEIGHTS['baseline_sharpe']}")

    print("\n" + "-" * 60)
    print("최근 3개월 성과 검증 중...")

    metrics = run_validation(months=3)

    if "error" in metrics:
        print(f"❌ 오류: {metrics['error']}")
        return

    print(f"\n검증 기간: {metrics['start_date']} ~ {metrics['end_date']}")
    print(f"\n  총 수익률:   {metrics['total_return']:+.2f}%")
    print(f"  샤프비율:    {metrics['sharpe_ratio']:.2f}")
    print(f"  소르티노:    {metrics['sortino_ratio']:.2f}")
    print(f"  MDD:         {metrics['max_drawdown']:.2f}%")
    print(f"  승률:        {metrics['win_rate']:.1f}%")
    print(f"  수익팩터:    {metrics['profit_factor']:.2f}")
    print(f"  거래 수:     {metrics['total_trades']}회")

    # 경고 체크
    alerts = check_alerts(metrics)

    print("\n" + "-" * 60)

    if not alerts:
        print("✅ 전략 상태: 정상")
        print("   현재 가중치 유지 권장")

        # 다음 재검토일 계산
        opt_date = datetime.strptime(CURRENT_WEIGHTS["optimized_date"], "%Y-%m-%d")
        next_review = opt_date + timedelta(days=90)  # 분기
        next_reopt = opt_date + timedelta(days=180)  # 반기

        print(f"\n📅 다음 일정:")
        print(f"   분기 검토: {next_review.strftime('%Y-%m-%d')}")
        print(f"   반기 재최적화: {next_reopt.strftime('%Y-%m-%d')}")
    else:
        print("⚠️ 경고 발생!")
        for alert in alerts:
            icon = "🔴" if alert["level"] == "CRITICAL" else "🟡"
            print(f"\n{icon} [{alert['level']}] {alert['message']}")
            print(f"   → 권장 조치: {alert['action']}")

        print("\n" + "=" * 60)
        print("💡 재최적화 실행: python3 scripts/optimize_weights.py")

    print("\n" + "=" * 60)

    # 결과 저장
    os.makedirs("data", exist_ok=True)
    with open("data/strategy_monitor.json", "w") as f:
        json.dump({
            "check_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "current_weights": CURRENT_WEIGHTS,
            "metrics": metrics,
            "alerts": alerts,
            "status": "OK" if not alerts else "ALERT"
        }, f, indent=2, ensure_ascii=False)

    print(f"결과 저장: data/strategy_monitor.json")


if __name__ == "__main__":
    main()
