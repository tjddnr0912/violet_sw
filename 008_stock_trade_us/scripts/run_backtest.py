#!/usr/bin/env python3
"""
멀티팩터 전략 백테스트 실행 스크립트
- pykrx로 과거 가격 데이터 수집
- 간단한 팩터 기반 신호 생성
- 백테스트 실행 및 결과 분석
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pykrx import stock
import warnings
warnings.filterwarnings('ignore')

from src.strategy.quant.backtest import Backtester, BacktestConfig
from src.strategy.quant.analytics import PerformanceAnalyzer, ChartGenerator


def get_kospi200_stocks(date_str: str) -> list:
    """KOSPI200 구성종목 조회"""
    try:
        tickers = stock.get_index_portfolio_deposit_file("1028", date_str)
        return list(tickers)[:50]  # 상위 50개만 사용 (속도)
    except:
        return []


def get_price_data(ticker: str, start: str, end: str) -> pd.DataFrame:
    """종목 가격 데이터 조회"""
    try:
        df = stock.get_market_ohlcv(start, end, ticker)
        if df.empty:
            return None

        # pykrx returns Korean column names: 시가, 고가, 저가, 종가, 거래량, 등락률
        df = df.rename(columns={
            '시가': 'open',
            '고가': 'high',
            '저가': 'low',
            '종가': 'close',
            '거래량': 'volume'
        })
        df = df.reset_index()
        df = df.rename(columns={'날짜': 'date'})
        df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
        df['date'] = pd.to_datetime(df['date'])
        return df
    except Exception as e:
        return None


def calculate_momentum(prices: pd.Series, period: int = 60) -> float:
    """모멘텀 점수 계산"""
    if len(prices) < period:
        return 0
    return (prices.iloc[-1] / prices.iloc[-period] - 1) * 100


def calculate_volatility(prices: pd.Series, period: int = 20) -> float:
    """변동성 계산"""
    if len(prices) < period:
        return 999
    returns = prices.pct_change().dropna()
    return returns.tail(period).std() * np.sqrt(252) * 100


def generate_signals(price_data: dict, date: datetime, top_n: int = 20) -> pd.DataFrame:
    """팩터 기반 신호 생성"""
    scores = []

    for code, df in price_data.items():
        if df is None or df.empty:
            continue

        # 해당 날짜까지의 데이터만 사용
        df_until = df[df['date'] <= date]
        if len(df_until) < 60:
            continue

        prices = df_until['close']

        # 모멘텀 (60일)
        momentum = calculate_momentum(prices, 60)

        # 단기 모멘텀 (20일)
        short_momentum = calculate_momentum(prices, 20)

        # 변동성 (낮을수록 좋음)
        volatility = calculate_volatility(prices, 20)

        # 종합 점수 (모멘텀 높고 변동성 낮은 종목)
        score = momentum * 0.4 + short_momentum * 0.3 - volatility * 0.3

        scores.append({
            'code': code,
            'name': code,  # 이름 대신 코드 사용
            'score': score,
            'momentum': momentum,
            'volatility': volatility
        })

    if not scores:
        return pd.DataFrame()

    df = pd.DataFrame(scores)
    df = df.nlargest(top_n, 'score')
    df['date'] = date
    df['signal'] = 'BUY'
    df['weight'] = 1.0 / len(df)

    return df


def print_result(result):
    """결과 출력"""
    print("\n" + "=" * 60)
    print("         멀티팩터 전략 백테스트 결과")
    print("=" * 60)
    print()
    print(f"  기간: {result.start_date.strftime('%Y-%m-%d')} ~ {result.end_date.strftime('%Y-%m-%d')}")
    print(f"  초기 자본: ₩{result.initial_capital:,.0f}")
    print(f"  최종 자산: ₩{result.final_value:,.0f}")
    print()
    print("-" * 60)
    print("  [수익률]")
    print(f"  총 수익률: {result.total_return:+.2f}%")
    print(f"  연환산(CAGR): {result.annualized_return:+.2f}%")
    print()
    print("  [리스크]")
    print(f"  연간 변동성: {result.volatility:.2f}%")
    print(f"  최대 낙폭(MDD): {result.max_drawdown:.2f}%")
    print(f"  낙폭 기간: {result.max_drawdown_duration}일")
    print()
    print("  [위험조정 수익률]")
    print(f"  샤프비율: {result.sharpe_ratio:.2f}")
    print(f"  소르티노비율: {result.sortino_ratio:.2f}")
    print(f"  칼마비율: {result.calmar_ratio:.2f}")
    print()
    print("-" * 60)
    print("  [거래 통계]")
    print(f"  총 거래 수: {result.total_trades}회")
    print(f"  승률: {result.win_rate:.1f}%")
    print(f"  평균 수익: ₩{result.avg_win:,.0f}")
    print(f"  평균 손실: ₩{result.avg_loss:,.0f}")
    print(f"  수익 팩터: {result.profit_factor:.2f}")
    print()
    print("-" * 60)
    print("  [월별 수익률]")
    for month, ret in sorted(result.monthly_returns.items())[-6:]:
        print(f"  {month}: {ret:+.2f}%")
    print()
    print("=" * 60)


def main():
    print("\n" + "=" * 60)
    print("     멀티팩터 전략 백테스트 시작")
    print("=" * 60)

    # 기간 설정 (최근 6개월 - 데이터 가용성 고려)
    end_date = datetime.now() - timedelta(days=2)  # 어제까지
    start_date = end_date - timedelta(days=180)    # 6개월

    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")

    print(f"\n기간: {start_str} ~ {end_str}")

    # 1. KOSPI200 종목 조회
    print("\n[1/4] KOSPI200 종목 조회 중...")

    # 최근 거래일 찾기
    for i in range(7):
        check_date = (end_date - timedelta(days=i)).strftime("%Y%m%d")
        tickers = get_kospi200_stocks(check_date)
        if tickers:
            break

    if not tickers:
        print("종목 조회 실패")
        return

    print(f"  → {len(tickers)}개 종목 조회됨")

    # 2. 가격 데이터 수집
    print("\n[2/4] 가격 데이터 수집 중...")
    price_data = {}
    success = 0

    for i, ticker in enumerate(tickers):
        df = get_price_data(ticker, start_str, end_str)
        if df is not None and len(df) >= 60:
            price_data[ticker] = df
            success += 1

        if (i + 1) % 10 == 0:
            print(f"  진행: {i+1}/{len(tickers)} ({success}개 성공)")

    print(f"  → {success}개 종목 데이터 수집 완료")

    if success < 10:
        print("데이터 부족으로 백테스트 불가")
        return

    # 3. 신호 생성 및 백테스트 실행
    print("\n[3/4] 백테스트 실행 중...")

    config = BacktestConfig(
        initial_capital=100_000_000,
        commission_rate=0.00015,
        slippage_rate=0.001,
        target_position_count=15,
        max_position_size=0.10,
        rebalance_frequency="M",
        stop_loss_pct=0.07,
        take_profit_pct=0.15
    )

    # 모든 리밸런싱 날짜의 신호 생성
    all_signals = []

    # 실제 거래일 추출
    sample_df = list(price_data.values())[0]
    trading_dates = sample_df['date'].tolist()

    rebalance_count = 0
    for date in trading_dates:
        # 월초 리밸런싱 (1~3일 중 첫 거래일)
        if date.day <= 3:
            signals = generate_signals(price_data, date, config.target_position_count)
            if not signals.empty:
                all_signals.append(signals)
                rebalance_count += 1
                print(f"  리밸런싱 {rebalance_count}: {date.strftime('%Y-%m-%d')} ({len(signals)}종목)")

    if not all_signals:
        print("신호 생성 실패")
        return

    signals_df = pd.concat(all_signals, ignore_index=True)
    print(f"  → 총 {len(signals_df)}개 신호 생성")

    # 백테스트 실행
    backtester = Backtester(config)
    result = backtester.run(price_data, signals_df, start_date, end_date)

    # 4. 결과 출력
    print("\n[4/4] 결과 분석 중...")
    print_result(result)

    # 성과 분석
    if result.daily_snapshots:
        analyzer = PerformanceAnalyzer()
        equity_curve = pd.Series(
            [s.total_value for s in result.daily_snapshots],
            index=[s.date for s in result.daily_snapshots]
        )

        # 차트 저장
        try:
            chart = ChartGenerator()
            chart_path = "data/backtest_result.png"
            os.makedirs("data", exist_ok=True)
            chart.plot_equity_curve(equity_curve, save_path=chart_path)
            print(f"\n차트 저장: {chart_path}")
        except Exception as e:
            print(f"차트 저장 실패: {e}")

    return result


if __name__ == "__main__":
    main()
