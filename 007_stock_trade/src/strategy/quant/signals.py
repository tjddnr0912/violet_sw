"""
매매 신호 생성 및 타이밍 판단
- 매수/매도 신호
- 손절/익절 관리
- 기술적 분석 보조
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
from datetime import datetime
import statistics


class SignalType(Enum):
    """신호 유형"""
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


class MarketCondition(Enum):
    """시장 상태"""
    BULLISH = "BULLISH"       # 상승장
    NEUTRAL = "NEUTRAL"       # 횡보장
    BEARISH = "BEARISH"       # 하락장


@dataclass
class TechnicalSignal:
    """기술적 분석 신호"""
    signal_type: SignalType
    score: float  # 0~100
    rsi: float = 0.0
    macd_signal: str = ""     # "BULLISH", "BEARISH", "NEUTRAL"
    ma_signal: str = ""       # "ABOVE", "BELOW"
    bb_signal: str = ""       # "UPPER", "MIDDLE", "LOWER"
    details: Dict = field(default_factory=dict)


@dataclass
class TradeSignal:
    """매매 신호"""
    code: str
    name: str
    signal_type: SignalType
    confidence: float         # 신뢰도 0~100
    reason: str
    target_weight: float      # 목표 비중
    stop_loss: float = 0.0    # 손절가
    take_profit: float = 0.0  # 익절가
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Position:
    """보유 포지션"""
    code: str
    name: str
    entry_price: float
    current_price: float
    quantity: int
    entry_date: datetime
    stop_loss: float
    take_profit_1: float      # 1차 익절가
    take_profit_2: float      # 2차 익절가
    highest_price: float = 0.0  # 트레일링 스탑용 최고가
    tp1_executed: bool = False
    tp2_executed: bool = False

    @property
    def profit_pct(self) -> float:
        """수익률"""
        if self.entry_price <= 0:
            return 0
        return (self.current_price - self.entry_price) / self.entry_price * 100

    @property
    def market_value(self) -> float:
        """평가금액"""
        return self.current_price * self.quantity


class TechnicalAnalyzer:
    """기술적 분석기"""

    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> float:
        """
        RSI 계산

        Args:
            prices: 종가 리스트 (최신이 앞)
            period: 기간

        Returns:
            RSI 값 (0~100)
        """
        if len(prices) < period + 1:
            return 50.0  # 기본값

        gains = []
        losses = []

        for i in range(period):
            change = prices[i] - prices[i + 1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    @staticmethod
    def calculate_ma(prices: List[float], period: int) -> float:
        """이동평균 계산"""
        if len(prices) < period:
            return prices[0] if prices else 0
        return sum(prices[:period]) / period

    @staticmethod
    def calculate_macd(
        prices: List[float],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Tuple[float, float, float]:
        """
        MACD 계산

        Returns:
            (MACD선, 시그널선, 히스토그램)
        """
        if len(prices) < slow:
            return 0, 0, 0

        def ema(data: List[float], period: int) -> float:
            if len(data) < period:
                return data[0] if data else 0
            multiplier = 2 / (period + 1)
            ema_val = sum(data[:period]) / period
            for price in data[period:]:
                ema_val = (price * multiplier) + (ema_val * (1 - multiplier))
            return ema_val

        # 가격 역순 (오래된 것이 앞)
        reversed_prices = list(reversed(prices))

        ema_fast = ema(reversed_prices, fast)
        ema_slow = ema(reversed_prices, slow)

        macd_line = ema_fast - ema_slow
        signal_line = macd_line * 0.2  # 간략화된 시그널

        return macd_line, signal_line, macd_line - signal_line

    @staticmethod
    def calculate_bollinger(
        prices: List[float],
        period: int = 20,
        std_mult: float = 2.0
    ) -> Tuple[float, float, float]:
        """
        볼린저밴드 계산

        Returns:
            (상단, 중단, 하단)
        """
        if len(prices) < period:
            return prices[0], prices[0], prices[0]

        ma = sum(prices[:period]) / period
        std = statistics.stdev(prices[:period])

        upper = ma + (std * std_mult)
        lower = ma - (std * std_mult)

        return upper, ma, lower

    def analyze(self, prices: List[float]) -> TechnicalSignal:
        """
        기술적 분석 수행

        Args:
            prices: 종가 리스트 (최신이 앞)

        Returns:
            TechnicalSignal
        """
        if len(prices) < 30:
            return TechnicalSignal(
                signal_type=SignalType.HOLD,
                score=50,
                details={"error": "데이터 부족"}
            )

        score = 50
        details = {}

        # RSI 분석
        rsi = self.calculate_rsi(prices)
        details["rsi"] = rsi

        if rsi < 30:
            score += 20
            details["rsi_signal"] = "OVERSOLD"
        elif rsi < 40:
            score += 10
            details["rsi_signal"] = "LOW"
        elif rsi > 70:
            score -= 15
            details["rsi_signal"] = "OVERBOUGHT"
        elif rsi > 60:
            score -= 5
            details["rsi_signal"] = "HIGH"
        else:
            details["rsi_signal"] = "NEUTRAL"

        # 이동평균 분석
        current = prices[0]
        ma20 = self.calculate_ma(prices, 20)
        ma60 = self.calculate_ma(prices, 60)

        details["ma20"] = ma20
        details["ma60"] = ma60

        if current > ma20 > ma60:
            score += 15
            ma_signal = "ABOVE"
            details["ma_trend"] = "BULLISH"
        elif current < ma20 < ma60:
            score -= 15
            ma_signal = "BELOW"
            details["ma_trend"] = "BEARISH"
        else:
            ma_signal = "MIXED"
            details["ma_trend"] = "NEUTRAL"

        # MACD 분석
        macd, signal_line, histogram = self.calculate_macd(prices)
        details["macd"] = macd
        details["macd_histogram"] = histogram

        if histogram > 0:
            score += 10
            macd_signal = "BULLISH"
        elif histogram < 0:
            score -= 10
            macd_signal = "BEARISH"
        else:
            macd_signal = "NEUTRAL"

        # 볼린저밴드 분석
        upper, middle, lower = self.calculate_bollinger(prices)
        details["bb_upper"] = upper
        details["bb_lower"] = lower

        if current < lower:
            score += 10
            bb_signal = "LOWER"
        elif current > upper:
            score -= 10
            bb_signal = "UPPER"
        else:
            bb_signal = "MIDDLE"

        # 신호 유형 결정
        score = max(0, min(100, score))

        if score >= 75:
            signal_type = SignalType.STRONG_BUY
        elif score >= 60:
            signal_type = SignalType.BUY
        elif score <= 25:
            signal_type = SignalType.STRONG_SELL
        elif score <= 40:
            signal_type = SignalType.SELL
        else:
            signal_type = SignalType.HOLD

        return TechnicalSignal(
            signal_type=signal_type,
            score=score,
            rsi=rsi,
            macd_signal=macd_signal,
            ma_signal=ma_signal,
            bb_signal=bb_signal,
            details=details
        )


class MarketAnalyzer:
    """시장 환경 분석기"""

    def __init__(self, api_client):
        self.client = api_client

    def get_market_condition(self, index_prices: List[float] = None) -> MarketCondition:
        """
        시장 상태 판단

        Args:
            index_prices: 지수 종가 리스트 (최신이 앞)
        """
        if not index_prices or len(index_prices) < 60:
            return MarketCondition.NEUTRAL

        current = index_prices[0]
        ma20 = sum(index_prices[:20]) / 20
        ma60 = sum(index_prices[:60]) / 60

        # 상승장: 지수 > 20일선 > 60일선
        if current > ma20 > ma60:
            return MarketCondition.BULLISH

        # 하락장: 지수 < 20일선 < 60일선
        if current < ma20 < ma60:
            return MarketCondition.BEARISH

        return MarketCondition.NEUTRAL


class SignalGenerator:
    """매매 신호 생성기"""

    def __init__(self, api_client):
        self.client = api_client
        self.tech_analyzer = TechnicalAnalyzer()
        self.market_analyzer = MarketAnalyzer(api_client)

    def generate_buy_signal(
        self,
        code: str,
        name: str,
        composite_score: float,
        prices: List[float],
        market_condition: MarketCondition = MarketCondition.NEUTRAL,
        current_price: float = 0
    ) -> TradeSignal:
        """
        매수 신호 생성

        Args:
            code: 종목코드
            name: 종목명
            composite_score: 복합 점수
            prices: 종가 리스트
            market_condition: 시장 상태
            current_price: 현재가
        """
        # 기술적 분석
        tech_signal = self.tech_analyzer.analyze(prices)

        # 기본 신뢰도 (복합 점수 기반)
        confidence = composite_score

        # 기술적 신호 반영
        confidence = (confidence * 0.6) + (tech_signal.score * 0.4)

        # 시장 상태 반영
        if market_condition == MarketCondition.BULLISH:
            confidence += 10
        elif market_condition == MarketCondition.BEARISH:
            confidence -= 15

        confidence = max(0, min(100, confidence))

        # 신호 유형 결정
        if confidence >= 70:
            signal_type = SignalType.STRONG_BUY
            target_weight = 0.10  # 10% 비중
            reason = "복합 점수 우수 + 기술적 매수 신호"
        elif confidence >= 55:
            signal_type = SignalType.BUY
            target_weight = 0.07  # 7% 비중
            reason = "복합 점수 양호"
        else:
            signal_type = SignalType.HOLD
            target_weight = 0.0
            reason = "매수 조건 미충족"

        # 시장 하락장에서는 보수적
        if market_condition == MarketCondition.BEARISH:
            target_weight *= 0.5
            reason += " (하락장 주의)"

        # 손절/익절가 계산
        if current_price > 0:
            stop_loss = current_price * 0.93  # -7%
            take_profit = current_price * 1.15  # +15%
        else:
            stop_loss = 0
            take_profit = 0

        return TradeSignal(
            code=code,
            name=name,
            signal_type=signal_type,
            confidence=confidence,
            reason=reason,
            target_weight=target_weight,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

    def generate_sell_signal(
        self,
        position: Position,
        prices: List[float],
        current_rank: int = 0,
        prev_rank: int = 0
    ) -> TradeSignal:
        """
        매도 신호 생성

        Args:
            position: 보유 포지션
            prices: 종가 리스트
            current_rank: 현재 순위
            prev_rank: 이전 순위
        """
        signal_type = SignalType.HOLD
        confidence = 50
        reason = ""

        # 1. 손절 조건 확인
        if position.current_price <= position.stop_loss:
            signal_type = SignalType.STRONG_SELL
            confidence = 100
            reason = f"손절가 도달 ({position.profit_pct:+.1f}%)"
            return TradeSignal(
                code=position.code,
                name=position.name,
                signal_type=signal_type,
                confidence=confidence,
                reason=reason,
                target_weight=0
            )

        # 2. 익절 조건 확인
        if position.current_price >= position.take_profit_1 and not position.tp1_executed:
            signal_type = SignalType.SELL
            confidence = 80
            reason = f"1차 익절가 도달 ({position.profit_pct:+.1f}%)"
        elif position.current_price >= position.take_profit_2 and not position.tp2_executed:
            signal_type = SignalType.STRONG_SELL
            confidence = 90
            reason = f"2차 익절가 도달 ({position.profit_pct:+.1f}%)"

        # 3. 순위 하락 확인
        if current_rank > 0 and prev_rank > 0:
            if current_rank > 30:  # 순위권 이탈
                signal_type = SignalType.STRONG_SELL
                confidence = 85
                reason = f"순위권 이탈 ({prev_rank}위 → {current_rank}위)"
            elif current_rank > prev_rank * 2:  # 순위 급락
                signal_type = SignalType.SELL
                confidence = 70
                reason = f"순위 급락 ({prev_rank}위 → {current_rank}위)"

        # 4. 기술적 매도 신호
        if len(prices) >= 30:
            tech_signal = self.tech_analyzer.analyze(prices)

            if tech_signal.signal_type == SignalType.STRONG_SELL:
                if signal_type == SignalType.HOLD:
                    signal_type = SignalType.SELL
                    confidence = 65
                    reason = "기술적 매도 신호 (RSI 과매수, MACD 하락)"
                else:
                    confidence = min(100, confidence + 10)
                    reason += " + 기술적 매도 신호"

        return TradeSignal(
            code=position.code,
            name=position.name,
            signal_type=signal_type,
            confidence=confidence,
            reason=reason if reason else "보유 유지",
            target_weight=0 if signal_type in [SignalType.SELL, SignalType.STRONG_SELL] else -1
        )


class StopLossManager:
    """손절 관리자"""

    @staticmethod
    def calculate_fixed_stop(entry_price: float, loss_pct: float = 0.07) -> float:
        """고정 비율 손절가"""
        return entry_price * (1 - loss_pct)

    @staticmethod
    def calculate_atr_stop(entry_price: float, atr: float, multiplier: float = 2.0) -> float:
        """ATR 기반 손절가"""
        return entry_price - (atr * multiplier)

    @staticmethod
    def update_trailing_stop(
        position: Position,
        trailing_pct: float = 0.07
    ) -> float:
        """
        트레일링 스탑 업데이트

        Returns:
            새로운 손절가
        """
        # 신고가 갱신
        if position.current_price > position.highest_price:
            position.highest_price = position.current_price

        # 새로운 손절가 계산
        new_stop = position.highest_price * (1 - trailing_pct)

        # 손절가는 상향만 가능
        if new_stop > position.stop_loss:
            return new_stop

        return position.stop_loss


class TakeProfitManager:
    """익절 관리자"""

    @staticmethod
    def calculate_targets(
        entry_price: float,
        stop_loss: float
    ) -> Tuple[float, float]:
        """
        익절 목표가 계산 (손익비 기반)

        Returns:
            (1차 익절가, 2차 익절가)
        """
        risk = entry_price - stop_loss

        # 1차: 손익비 1.5:1
        tp1 = entry_price + (risk * 1.5)

        # 2차: 손익비 2.5:1
        tp2 = entry_price + (risk * 2.5)

        return tp1, tp2

    @staticmethod
    def calculate_staged_sell_qty(
        total_qty: int,
        stage: int
    ) -> int:
        """
        단계별 매도 수량 계산

        Args:
            total_qty: 총 수량
            stage: 단계 (1 또는 2)

        Returns:
            매도 수량
        """
        if stage == 1:
            return int(total_qty * 0.30)  # 30%
        elif stage == 2:
            return int(total_qty * 0.50)  # 남은 것의 50%
        else:
            return total_qty  # 전량
