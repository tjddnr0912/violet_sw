"""
백테스팅 프레임워크
- 과거 데이터 기반 전략 검증
- 성과 지표 계산 (수익률, 샤프비율, MDD 등)
- 거래 시뮬레이션
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    """주문 방향"""
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class BacktestConfig:
    """백테스트 설정"""
    initial_capital: float = 100_000_000  # 초기 자본금
    commission_rate: float = 0.00015      # 수수료율 (0.015%)
    slippage_rate: float = 0.001          # 슬리피지 (0.1%)
    max_position_size: float = 0.10       # 최대 단일 포지션 비중 (10%)
    target_position_count: int = 20       # 목표 보유 종목 수
    rebalance_frequency: str = "M"        # 리밸런싱 주기 (D:일, W:주, M:월)
    stop_loss_pct: float = 0.07           # 손절 비율
    take_profit_pct: float = 0.15         # 익절 비율


@dataclass
class Trade:
    """거래 기록"""
    date: datetime
    code: str
    name: str
    side: OrderSide
    price: float
    quantity: int
    amount: float
    commission: float
    pnl: float = 0.0
    pnl_pct: float = 0.0
    reason: str = ""


@dataclass
class BacktestPosition:
    """백테스트 포지션"""
    code: str
    name: str
    entry_date: datetime
    entry_price: float
    quantity: int
    current_price: float = 0.0
    highest_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0

    @property
    def market_value(self) -> float:
        return self.current_price * self.quantity

    @property
    def cost_basis(self) -> float:
        return self.entry_price * self.quantity

    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - self.cost_basis

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.cost_basis == 0:
            return 0
        return (self.current_price / self.entry_price - 1) * 100


@dataclass
class DailySnapshot:
    """일별 스냅샷"""
    date: datetime
    cash: float
    positions_value: float
    total_value: float
    daily_return: float = 0.0
    cumulative_return: float = 0.0
    drawdown: float = 0.0
    position_count: int = 0


@dataclass
class BacktestResult:
    """백테스트 결과"""
    config: BacktestConfig
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_value: float

    # 성과 지표
    total_return: float = 0.0           # 총 수익률
    annualized_return: float = 0.0      # 연환산 수익률
    volatility: float = 0.0             # 변동성
    sharpe_ratio: float = 0.0           # 샤프비율
    sortino_ratio: float = 0.0          # 소르티노비율
    max_drawdown: float = 0.0           # 최대 낙폭
    max_drawdown_duration: int = 0      # 최대 낙폭 기간 (일)
    calmar_ratio: float = 0.0           # 칼마비율

    # 거래 통계
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    avg_holding_days: float = 0.0

    # 상세 데이터
    trades: List[Trade] = field(default_factory=list)
    daily_snapshots: List[DailySnapshot] = field(default_factory=list)
    monthly_returns: Dict[str, float] = field(default_factory=dict)


class Backtester:
    """백테스팅 엔진"""

    def __init__(self, config: BacktestConfig = None):
        self.config = config or BacktestConfig()
        self.cash = self.config.initial_capital
        self.positions: Dict[str, BacktestPosition] = {}
        self.trades: List[Trade] = []
        self.daily_snapshots: List[DailySnapshot] = []
        self.peak_value = self.config.initial_capital

    def reset(self):
        """상태 초기화"""
        self.cash = self.config.initial_capital
        self.positions = {}
        self.trades = []
        self.daily_snapshots = []
        self.peak_value = self.config.initial_capital

    def run(
        self,
        price_data: Dict[str, pd.DataFrame],
        signals: pd.DataFrame,
        start_date: datetime = None,
        end_date: datetime = None
    ) -> BacktestResult:
        """
        백테스트 실행

        Args:
            price_data: 종목별 가격 데이터 {code: DataFrame}
                       DataFrame columns: date, open, high, low, close, volume
            signals: 매매 신호 DataFrame
                    columns: date, code, name, signal, score, weight
            start_date: 시작일
            end_date: 종료일

        Returns:
            BacktestResult
        """
        self.reset()

        # 날짜 범위 설정
        all_dates = set()
        for code, df in price_data.items():
            all_dates.update(df['date'].tolist())

        all_dates = sorted(all_dates)

        if start_date:
            all_dates = [d for d in all_dates if d >= start_date]
        if end_date:
            all_dates = [d for d in all_dates if d <= end_date]

        if not all_dates:
            raise ValueError("유효한 거래일이 없습니다.")

        logger.info(f"백테스트 시작: {all_dates[0]} ~ {all_dates[-1]}")

        # 일별 시뮬레이션
        for date in all_dates:
            self._process_day(date, price_data, signals)

        # 결과 계산
        result = self._calculate_result(all_dates[0], all_dates[-1])

        logger.info(f"백테스트 완료: 총 수익률 {result.total_return:.2f}%")

        return result

    def _process_day(
        self,
        date: datetime,
        price_data: Dict[str, pd.DataFrame],
        signals: pd.DataFrame
    ):
        """일별 처리"""
        # 1. 포지션 가격 업데이트
        self._update_prices(date, price_data)

        # 2. 손절/익절 체크
        self._check_stop_orders(date, price_data)

        # 3. 리밸런싱 체크
        if self._should_rebalance(date):
            day_signals = signals[signals['date'] == date] if 'date' in signals.columns else signals
            if not day_signals.empty:
                self._rebalance(date, day_signals, price_data)

        # 4. 일별 스냅샷 저장
        self._save_snapshot(date)

    def _update_prices(self, date: datetime, price_data: Dict[str, pd.DataFrame]):
        """포지션 가격 업데이트"""
        for code, pos in list(self.positions.items()):
            if code in price_data:
                df = price_data[code]
                day_data = df[df['date'] == date]
                if not day_data.empty:
                    pos.current_price = day_data.iloc[0]['close']
                    if pos.current_price > pos.highest_price:
                        pos.highest_price = pos.current_price

    def _check_stop_orders(self, date: datetime, price_data: Dict[str, pd.DataFrame]):
        """손절/익절 체크"""
        for code, pos in list(self.positions.items()):
            if code not in price_data:
                continue

            df = price_data[code]
            day_data = df[df['date'] == date]
            if day_data.empty:
                continue

            low = day_data.iloc[0]['low']
            high = day_data.iloc[0]['high']

            # 손절 체크
            if pos.stop_loss > 0 and low <= pos.stop_loss:
                self._close_position(date, code, pos.stop_loss, "손절")
                continue

            # 익절 체크
            if pos.take_profit > 0 and high >= pos.take_profit:
                self._close_position(date, code, pos.take_profit, "익절")

    def _should_rebalance(self, date: datetime) -> bool:
        """리밸런싱 여부 확인"""
        freq = self.config.rebalance_frequency

        if freq == "D":
            return True
        elif freq == "W":
            return date.weekday() == 0  # 월요일
        elif freq == "M":
            return date.day <= 3 and date.weekday() < 5  # 매월 초 첫 거래일
        return False

    def _rebalance(
        self,
        date: datetime,
        signals: pd.DataFrame,
        price_data: Dict[str, pd.DataFrame]
    ):
        """리밸런싱 실행"""
        # 현재 보유 종목
        current_holdings = set(self.positions.keys())

        # 목표 종목 (상위 N개)
        target_stocks = signals.nlargest(self.config.target_position_count, 'score')
        target_holdings = set(target_stocks['code'].tolist())

        # 매도: 목표에 없는 종목
        to_sell = current_holdings - target_holdings
        for code in to_sell:
            if code in price_data:
                df = price_data[code]
                day_data = df[df['date'] == date]
                if not day_data.empty:
                    price = day_data.iloc[0]['close']
                    self._close_position(date, code, price, "리밸런싱 매도")

        # 매수: 새로 진입할 종목
        to_buy = target_holdings - current_holdings
        available_cash = self.cash * 0.95  # 5% 여유

        for _, row in target_stocks[target_stocks['code'].isin(to_buy)].iterrows():
            code = row['code']
            name = row.get('name', code)
            weight = row.get('weight', 1.0 / self.config.target_position_count)

            if code not in price_data:
                continue

            df = price_data[code]
            day_data = df[df['date'] == date]
            if day_data.empty:
                continue

            price = day_data.iloc[0]['close']

            # 투자금액 계산
            target_amount = self._total_value * min(weight, self.config.max_position_size)
            invest_amount = min(target_amount, available_cash / len(to_buy))

            if invest_amount < price:
                continue

            quantity = int(invest_amount / price)
            if quantity > 0:
                self._open_position(date, code, name, price, quantity)
                available_cash -= quantity * price

    def _open_position(
        self,
        date: datetime,
        code: str,
        name: str,
        price: float,
        quantity: int
    ):
        """포지션 진입"""
        # 슬리피지 적용
        actual_price = price * (1 + self.config.slippage_rate)
        amount = actual_price * quantity
        commission = amount * self.config.commission_rate

        if self.cash < amount + commission:
            return

        self.cash -= (amount + commission)

        # 손절/익절가 계산
        stop_loss = actual_price * (1 - self.config.stop_loss_pct)
        take_profit = actual_price * (1 + self.config.take_profit_pct)

        self.positions[code] = BacktestPosition(
            code=code,
            name=name,
            entry_date=date,
            entry_price=actual_price,
            quantity=quantity,
            current_price=actual_price,
            highest_price=actual_price,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        self.trades.append(Trade(
            date=date,
            code=code,
            name=name,
            side=OrderSide.BUY,
            price=actual_price,
            quantity=quantity,
            amount=amount,
            commission=commission,
            reason="매수"
        ))

        logger.debug(f"[{date}] 매수: {name} {quantity}주 @ {actual_price:,.0f}원")

    def _close_position(
        self,
        date: datetime,
        code: str,
        price: float,
        reason: str = ""
    ):
        """포지션 청산"""
        if code not in self.positions:
            return

        pos = self.positions[code]

        # 슬리피지 적용
        actual_price = price * (1 - self.config.slippage_rate)
        amount = actual_price * pos.quantity
        commission = amount * self.config.commission_rate

        pnl = (actual_price - pos.entry_price) * pos.quantity - commission
        pnl_pct = (actual_price / pos.entry_price - 1) * 100

        self.cash += (amount - commission)

        self.trades.append(Trade(
            date=date,
            code=code,
            name=pos.name,
            side=OrderSide.SELL,
            price=actual_price,
            quantity=pos.quantity,
            amount=amount,
            commission=commission,
            pnl=pnl,
            pnl_pct=pnl_pct,
            reason=reason
        ))

        del self.positions[code]

        logger.debug(f"[{date}] 매도: {pos.name} {pos.quantity}주 @ {actual_price:,.0f}원 (손익: {pnl:+,.0f}원)")

    @property
    def _total_value(self) -> float:
        """총 평가금액"""
        positions_value = sum(p.market_value for p in self.positions.values())
        return self.cash + positions_value

    def _save_snapshot(self, date: datetime):
        """일별 스냅샷 저장"""
        positions_value = sum(p.market_value for p in self.positions.values())
        total_value = self.cash + positions_value

        # 수익률 계산
        if self.daily_snapshots:
            prev = self.daily_snapshots[-1]
            daily_return = (total_value / prev.total_value - 1) * 100 if prev.total_value > 0 else 0
        else:
            daily_return = 0

        cumulative_return = (total_value / self.config.initial_capital - 1) * 100

        # 최대 낙폭 계산
        if total_value > self.peak_value:
            self.peak_value = total_value
        drawdown = (total_value / self.peak_value - 1) * 100 if self.peak_value > 0 else 0

        self.daily_snapshots.append(DailySnapshot(
            date=date,
            cash=self.cash,
            positions_value=positions_value,
            total_value=total_value,
            daily_return=daily_return,
            cumulative_return=cumulative_return,
            drawdown=drawdown,
            position_count=len(self.positions)
        ))

    def _calculate_result(self, start_date: datetime, end_date: datetime) -> BacktestResult:
        """결과 계산"""
        result = BacktestResult(
            config=self.config,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.config.initial_capital,
            final_value=self._total_value,
            trades=self.trades,
            daily_snapshots=self.daily_snapshots
        )

        if not self.daily_snapshots:
            return result

        # 수익률 지표
        result.total_return = (self._total_value / self.config.initial_capital - 1) * 100

        # 연환산 수익률
        days = (end_date - start_date).days
        if days > 0:
            years = days / 365
            result.annualized_return = ((1 + result.total_return / 100) ** (1 / years) - 1) * 100

        # 일별 수익률
        daily_returns = [s.daily_return / 100 for s in self.daily_snapshots]

        if daily_returns:
            # 변동성 (연환산)
            result.volatility = np.std(daily_returns) * np.sqrt(252) * 100

            # 샤프비율 (무위험이자율 3% 가정)
            risk_free_rate = 0.03 / 252  # 일별
            excess_returns = [r - risk_free_rate for r in daily_returns]
            if np.std(excess_returns) > 0:
                result.sharpe_ratio = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)

            # 소르티노비율 (하방 변동성만 고려)
            negative_returns = [r for r in excess_returns if r < 0]
            if negative_returns:
                downside_std = np.std(negative_returns) * np.sqrt(252)
                if downside_std > 0:
                    result.sortino_ratio = result.annualized_return / 100 / downside_std

        # 최대 낙폭
        result.max_drawdown = min(s.drawdown for s in self.daily_snapshots)

        # 최대 낙폭 기간
        max_dd_duration = 0
        current_dd_duration = 0
        for s in self.daily_snapshots:
            if s.drawdown < 0:
                current_dd_duration += 1
                max_dd_duration = max(max_dd_duration, current_dd_duration)
            else:
                current_dd_duration = 0
        result.max_drawdown_duration = max_dd_duration

        # 칼마비율
        if result.max_drawdown != 0:
            result.calmar_ratio = result.annualized_return / abs(result.max_drawdown)

        # 거래 통계
        sell_trades = [t for t in self.trades if t.side == OrderSide.SELL]
        result.total_trades = len(sell_trades)

        if sell_trades:
            winning = [t for t in sell_trades if t.pnl > 0]
            losing = [t for t in sell_trades if t.pnl < 0]

            result.winning_trades = len(winning)
            result.losing_trades = len(losing)
            result.win_rate = len(winning) / len(sell_trades) * 100

            if winning:
                result.avg_win = np.mean([t.pnl for t in winning])
            if losing:
                result.avg_loss = np.mean([t.pnl for t in losing])

            total_wins = sum(t.pnl for t in winning)
            total_losses = abs(sum(t.pnl for t in losing))
            if total_losses > 0:
                result.profit_factor = total_wins / total_losses

        # 월별 수익률
        for snapshot in self.daily_snapshots:
            month_key = snapshot.date.strftime("%Y-%m")
            if month_key not in result.monthly_returns:
                result.monthly_returns[month_key] = 0
            result.monthly_returns[month_key] = snapshot.cumulative_return

        return result


def run_simple_backtest(
    screener,
    price_data: Dict[str, pd.DataFrame],
    start_date: datetime,
    end_date: datetime,
    config: BacktestConfig = None
) -> BacktestResult:
    """
    간단한 백테스트 실행 헬퍼 함수

    Args:
        screener: MultiFactorScreener 인스턴스
        price_data: 종목별 가격 데이터
        start_date: 시작일
        end_date: 종료일
        config: 백테스트 설정

    Returns:
        BacktestResult
    """
    backtester = Backtester(config)

    # 모든 리밸런싱 일자의 신호 생성
    signals_list = []
    current_date = start_date

    while current_date <= end_date:
        # 월초 리밸런싱
        if current_date.day <= 3:
            try:
                result = screener.run_screening()
                for stock in result.selected_stocks:
                    signals_list.append({
                        'date': current_date,
                        'code': stock.code,
                        'name': stock.name,
                        'signal': 'BUY',
                        'score': stock.composite_score,
                        'weight': 1.0 / len(result.selected_stocks)
                    })
            except Exception as e:
                logger.warning(f"스크리닝 실패 ({current_date}): {e}")

        current_date += timedelta(days=1)

    signals_df = pd.DataFrame(signals_list)

    return backtester.run(price_data, signals_df, start_date, end_date)
