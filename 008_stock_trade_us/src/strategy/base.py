"""
매매 전략 기본 클래스
- 전략 인터페이스 정의
- 시그널 생성 로직
- 포지션 관리
"""

from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
import pandas as pd


class Signal(Enum):
    """매매 시그널"""
    STRONG_BUY = 2    # 강력 매수
    BUY = 1           # 매수
    HOLD = 0          # 관망
    SELL = -1         # 매도
    STRONG_SELL = -2  # 강력 매도


class Position(Enum):
    """포지션 상태"""
    NONE = 0    # 미보유
    LONG = 1    # 매수 보유
    SHORT = -1  # 매도 보유 (공매도)


@dataclass
class TradeSignal:
    """매매 시그널 정보"""
    signal: Signal                    # 시그널
    strength: float                   # 시그널 강도 (0.0 ~ 1.0)
    price: float                      # 현재가
    timestamp: datetime               # 시간
    reason: str = ""                  # 시그널 사유
    indicators: Dict[str, float] = field(default_factory=dict)  # 지표값


@dataclass
class StrategyConfig:
    """전략 설정"""
    name: str                         # 전략명
    description: str = ""             # 설명
    risk_per_trade: float = 0.02      # 거래당 리스크 비율 (2%)
    max_position_size: float = 0.3    # 최대 포지션 비율 (30%)
    stop_loss_pct: float = 0.03       # 손절 비율 (3%)
    take_profit_pct: float = 0.06     # 익절 비율 (6%)
    params: Dict[str, Any] = field(default_factory=dict)  # 추가 파라미터


class BaseStrategy(ABC):
    """매매 전략 기본 추상 클래스"""

    def __init__(self, config: Optional[StrategyConfig] = None):
        """
        Args:
            config: 전략 설정
        """
        self.config = config or self._default_config()
        self.position = Position.NONE
        self.entry_price: Optional[float] = None
        self.entry_time: Optional[datetime] = None
        self.signals_history: List[TradeSignal] = []

    @abstractmethod
    def _default_config(self) -> StrategyConfig:
        """기본 설정 반환"""
        pass

    @abstractmethod
    def analyze(self, df: pd.DataFrame) -> TradeSignal:
        """
        데이터 분석 및 시그널 생성

        Args:
            df: OHLCV DataFrame

        Returns:
            TradeSignal
        """
        pass

    @abstractmethod
    def get_indicators(self, df: pd.DataFrame) -> Dict[str, float]:
        """
        현재 지표값 반환

        Args:
            df: OHLCV DataFrame

        Returns:
            지표값 딕셔너리
        """
        pass

    def should_enter(self, signal: TradeSignal) -> bool:
        """
        진입 여부 판단

        Args:
            signal: 매매 시그널

        Returns:
            진입 여부
        """
        if self.position != Position.NONE:
            return False

        return signal.signal in [Signal.BUY, Signal.STRONG_BUY]

    def should_exit(self, signal: TradeSignal, current_price: float) -> bool:
        """
        청산 여부 판단

        Args:
            signal: 매매 시그널
            current_price: 현재가

        Returns:
            청산 여부
        """
        if self.position == Position.NONE:
            return False

        # 손절/익절 체크
        if self.entry_price:
            pnl_pct = (current_price - self.entry_price) / self.entry_price

            # 손절
            if pnl_pct <= -self.config.stop_loss_pct:
                return True

            # 익절
            if pnl_pct >= self.config.take_profit_pct:
                return True

        # 시그널 기반 청산
        return signal.signal in [Signal.SELL, Signal.STRONG_SELL]

    def enter_position(self, price: float, timestamp: Optional[datetime] = None):
        """포지션 진입"""
        self.position = Position.LONG
        self.entry_price = price
        self.entry_time = timestamp or datetime.now()

    def exit_position(self) -> Optional[float]:
        """
        포지션 청산

        Returns:
            진입가 (청산 계산용)
        """
        entry_price = self.entry_price
        self.position = Position.NONE
        self.entry_price = None
        self.entry_time = None
        return entry_price

    def calculate_position_size(
        self,
        capital: float,
        current_price: float,
        signal_strength: float = 1.0
    ) -> int:
        """
        포지션 크기 계산

        Args:
            capital: 투자 자본
            current_price: 현재가
            signal_strength: 시그널 강도

        Returns:
            매수 수량
        """
        # 최대 투자금액
        max_amount = capital * self.config.max_position_size

        # 시그널 강도에 따른 조정
        adjusted_amount = max_amount * signal_strength

        # 수량 계산
        qty = int(adjusted_amount / current_price)

        return max(0, qty)

    def calculate_stop_loss(self, entry_price: float) -> float:
        """손절가 계산"""
        return entry_price * (1 - self.config.stop_loss_pct)

    def calculate_take_profit(self, entry_price: float) -> float:
        """익절가 계산"""
        return entry_price * (1 + self.config.take_profit_pct)

    def record_signal(self, signal: TradeSignal):
        """시그널 기록"""
        self.signals_history.append(signal)

        # 최근 100개만 유지
        if len(self.signals_history) > 100:
            self.signals_history = self.signals_history[-100:]

    def get_recent_signals(self, count: int = 10) -> List[TradeSignal]:
        """최근 시그널 반환"""
        return self.signals_history[-count:]

    def reset(self):
        """전략 상태 초기화"""
        self.position = Position.NONE
        self.entry_price = None
        self.entry_time = None
        self.signals_history = []


class StrategyManager:
    """전략 관리자"""

    def __init__(self):
        self.strategies: Dict[str, BaseStrategy] = {}
        self.active_strategy: Optional[str] = None

    def register(self, name: str, strategy: BaseStrategy):
        """전략 등록"""
        self.strategies[name] = strategy

    def set_active(self, name: str):
        """활성 전략 설정"""
        if name not in self.strategies:
            raise ValueError(f"전략 '{name}'이 등록되지 않았습니다.")
        self.active_strategy = name

    def get_active(self) -> Optional[BaseStrategy]:
        """활성 전략 반환"""
        if self.active_strategy:
            return self.strategies.get(self.active_strategy)
        return None

    def analyze(self, df: pd.DataFrame) -> Optional[TradeSignal]:
        """활성 전략으로 분석"""
        strategy = self.get_active()
        if strategy:
            return strategy.analyze(df)
        return None

    def list_strategies(self) -> List[str]:
        """등록된 전략 목록"""
        return list(self.strategies.keys())
