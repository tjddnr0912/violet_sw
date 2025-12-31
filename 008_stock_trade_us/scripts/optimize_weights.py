#!/usr/bin/env python3
"""
팩터 가중치 최적화 스크립트
- 다양한 가중치 조합 테스트
- 샤프비율 최대화
- 그리드 서치 + 미세 조정
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pykrx import stock
from itertools import product
import warnings
warnings.filterwarnings('ignore')

from src.strategy.quant.backtest import Backtester, BacktestConfig


class WeightOptimizer:
    """팩터 가중치 최적화기"""

    def __init__(self, price_data: dict, start_date: datetime, end_date: datetime):
        self.price_data = price_data
        self.start_date = start_date
        self.end_date = end_date
        self.results = []

    def generate_signals(
        self,
        date: datetime,
        momentum_weight: float,
        short_mom_weight: float,
        volatility_weight: float,
        volume_weight: float = 0.0,
        top_n: int = 15
    ) -> pd.DataFrame:
        """팩터 기반 신호 생성"""
        scores = []

        for code, df in self.price_data.items():
            if df is None or df.empty:
                continue

            df_until = df[df['date'] <= date]
            if len(df_until) < 60:
                continue

            prices = df_until['close']
            volumes = df_until['volume']

            # 모멘텀 (60일)
            momentum = self._calc_momentum(prices, 60)

            # 단기 모멘텀 (20일)
            short_momentum = self._calc_momentum(prices, 20)

            # 변동성 (낮을수록 좋음)
            volatility = self._calc_volatility(prices, 20)

            # 거래량 증가율
            volume_change = self._calc_volume_change(volumes, 20)

            # 52주 고점 대비
            high_52w = prices.tail(252).max() if len(prices) >= 252 else prices.max()
            from_high = (prices.iloc[-1] / high_52w) if high_52w > 0 else 0

            # 종합 점수
            score = (
                momentum * momentum_weight +
                short_momentum * short_mom_weight -
                volatility * volatility_weight +
                volume_change * volume_weight +
                from_high * 10  # 고점 근접 보너스
            )

            scores.append({
                'code': code,
                'name': code,
                'score': score,
                'momentum': momentum,
                'short_momentum': short_momentum,
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

    def _calc_momentum(self, prices: pd.Series, period: int) -> float:
        if len(prices) < period:
            return 0
        return (prices.iloc[-1] / prices.iloc[-period] - 1) * 100

    def _calc_volatility(self, prices: pd.Series, period: int) -> float:
        if len(prices) < period:
            return 999
        returns = prices.pct_change().dropna()
        return returns.tail(period).std() * np.sqrt(252) * 100

    def _calc_volume_change(self, volumes: pd.Series, period: int) -> float:
        if len(volumes) < period * 2:
            return 0
        recent = volumes.tail(period).mean()
        prev = volumes.tail(period * 2).head(period).mean()
        return (recent / prev - 1) * 100 if prev > 0 else 0

    def run_backtest(
        self,
        momentum_weight: float,
        short_mom_weight: float,
        volatility_weight: float,
        volume_weight: float = 0.0,
        target_count: int = 15
    ) -> dict:
        """단일 가중치 조합으로 백테스트 실행"""

        config = BacktestConfig(
            initial_capital=100_000_000,
            commission_rate=0.00015,
            slippage_rate=0.001,
            target_position_count=target_count,
            max_position_size=0.10,
            rebalance_frequency="M",
            stop_loss_pct=0.07,
            take_profit_pct=0.15
        )

        # 신호 생성
        sample_df = list(self.price_data.values())[0]
        trading_dates = sample_df['date'].tolist()

        all_signals = []
        for date in trading_dates:
            if date < self.start_date or date > self.end_date:
                continue
            if date.day <= 3:  # 월초 리밸런싱
                signals = self.generate_signals(
                    date, momentum_weight, short_mom_weight,
                    volatility_weight, volume_weight, target_count
                )
                if not signals.empty:
                    all_signals.append(signals)

        if not all_signals:
            return None

        signals_df = pd.concat(all_signals, ignore_index=True)

        # 백테스트 실행
        backtester = Backtester(config)
        result = backtester.run(self.price_data, signals_df, self.start_date, self.end_date)

        return {
            'momentum_weight': momentum_weight,
            'short_mom_weight': short_mom_weight,
            'volatility_weight': volatility_weight,
            'volume_weight': volume_weight,
            'target_count': target_count,
            'total_return': result.total_return,
            'sharpe_ratio': result.sharpe_ratio,
            'sortino_ratio': result.sortino_ratio,
            'max_drawdown': result.max_drawdown,
            'win_rate': result.win_rate,
            'profit_factor': result.profit_factor,
            'calmar_ratio': result.calmar_ratio,
            'volatility': result.volatility
        }

    def grid_search(self, verbose: bool = True) -> pd.DataFrame:
        """그리드 서치로 최적 가중치 탐색"""

        # 가중치 범위 정의
        momentum_range = [0.2, 0.3, 0.4, 0.5, 0.6]
        short_mom_range = [0.1, 0.2, 0.3, 0.4]
        volatility_range = [0.1, 0.2, 0.3, 0.4, 0.5]
        volume_range = [0.0, 0.1, 0.2]
        target_count_range = [10, 15, 20]

        total = (len(momentum_range) * len(short_mom_range) *
                 len(volatility_range) * len(volume_range) * len(target_count_range))

        if verbose:
            print(f"\n총 {total}개 조합 테스트 시작...\n")

        count = 0
        for mom, short_mom, vol, volume, target in product(
            momentum_range, short_mom_range, volatility_range,
            volume_range, target_count_range
        ):
            count += 1
            try:
                result = self.run_backtest(mom, short_mom, vol, volume, target)
                if result:
                    self.results.append(result)

                    if verbose and count % 50 == 0:
                        print(f"진행: {count}/{total} ({count*100//total}%)")

            except Exception as e:
                continue

        df = pd.DataFrame(self.results)
        return df.sort_values('sharpe_ratio', ascending=False)


def get_price_data(ticker: str, start: str, end: str) -> pd.DataFrame:
    """종목 가격 데이터 조회"""
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


def main():
    print("\n" + "=" * 60)
    print("     팩터 가중치 최적화 시작")
    print("=" * 60)

    # 기간 설정
    end_date = datetime.now() - timedelta(days=2)
    start_date = end_date - timedelta(days=180)

    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")

    print(f"\n기간: {start_str} ~ {end_str}")

    # KOSPI200 종목 조회
    print("\n[1/3] 데이터 수집 중...")

    for i in range(7):
        check_date = (end_date - timedelta(days=i)).strftime("%Y%m%d")
        tickers = stock.get_index_portfolio_deposit_file("1028", check_date)
        if tickers is not None and len(tickers) > 0:
            break

    tickers = list(tickers)[:50]
    print(f"  → {len(tickers)}개 종목")

    # 가격 데이터 수집
    price_data = {}
    for i, ticker in enumerate(tickers):
        df = get_price_data(ticker, start_str, end_str)
        if df is not None and len(df) >= 60:
            price_data[ticker] = df
        if (i + 1) % 10 == 0:
            print(f"  진행: {i+1}/{len(tickers)}")

    print(f"  → {len(price_data)}개 종목 데이터 수집 완료")

    # 최적화 실행
    print("\n[2/3] 가중치 최적화 중...")

    optimizer = WeightOptimizer(price_data, start_date, end_date)
    results_df = optimizer.grid_search(verbose=True)

    # 결과 출력
    print("\n[3/3] 최적화 결과")
    print("=" * 60)

    print("\n📊 상위 10개 가중치 조합 (샤프비율 기준):\n")
    print("-" * 90)
    print(f"{'순위':^4} {'모멘텀':^8} {'단기모멘텀':^10} {'변동성':^8} {'거래량':^8} {'종목수':^6} {'샤프':^8} {'수익률':^10} {'MDD':^8}")
    print("-" * 90)

    for i, row in results_df.head(10).iterrows():
        rank = results_df.index.get_loc(i) + 1
        print(f"{rank:^4} {row['momentum_weight']:^8.2f} {row['short_mom_weight']:^10.2f} "
              f"{row['volatility_weight']:^8.2f} {row['volume_weight']:^8.2f} "
              f"{int(row['target_count']):^6} {row['sharpe_ratio']:^8.2f} "
              f"{row['total_return']:^+10.2f}% {row['max_drawdown']:^8.2f}%")

    print("-" * 90)

    # 최적 가중치
    best = results_df.iloc[0]

    print("\n" + "=" * 60)
    print("     🏆 최적 가중치 발견!")
    print("=" * 60)
    print(f"""
  모멘텀 가중치:      {best['momentum_weight']:.2f}
  단기모멘텀 가중치:  {best['short_mom_weight']:.2f}
  변동성 가중치:      {best['volatility_weight']:.2f}
  거래량 가중치:      {best['volume_weight']:.2f}
  목표 종목 수:       {int(best['target_count'])}개

  ──────────────────────────────
  샤프비율:     {best['sharpe_ratio']:.2f}
  소르티노비율: {best['sortino_ratio']:.2f}
  총 수익률:    {best['total_return']:+.2f}%
  최대 낙폭:    {best['max_drawdown']:.2f}%
  승률:         {best['win_rate']:.1f}%
  수익 팩터:    {best['profit_factor']:.2f}
""")
    print("=" * 60)

    # 기존 대비 개선율
    baseline_sharpe = 0.46  # 기존 샤프비율
    improvement = (best['sharpe_ratio'] - baseline_sharpe) / baseline_sharpe * 100

    print(f"\n📈 기존 대비 샤프비율 개선: {baseline_sharpe:.2f} → {best['sharpe_ratio']:.2f} ({improvement:+.1f}%)")

    # 결과 저장
    os.makedirs("data", exist_ok=True)
    results_df.to_csv("data/optimization_results.csv", index=False)
    print(f"\n결과 저장: data/optimization_results.csv")

    return results_df


if __name__ == "__main__":
    main()
