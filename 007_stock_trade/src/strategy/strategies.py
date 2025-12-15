"""
구체적인 매매 전략 구현
- 이동평균 크로스오버 전략
- RSI 기반 전략
- MACD 전략
- 복합 전략
"""

import pandas as pd
from datetime import datetime
from typing import Dict, Any, Optional

from .base import (
    BaseStrategy,
    StrategyConfig,
    TradeSignal,
    Signal
)
from .indicators import TechnicalIndicators, calculate_indicators


class MACrossoverStrategy(BaseStrategy):
    """
    이동평균 크로스오버 전략

    - 단기 MA가 장기 MA를 상향 돌파: 매수
    - 단기 MA가 장기 MA를 하향 돌파: 매도
    """

    def _default_config(self) -> StrategyConfig:
        return StrategyConfig(
            name="MA Crossover",
            description="이동평균 크로스오버 전략",
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            params={
                "fast_period": 5,   # 단기 MA
                "slow_period": 20,  # 장기 MA
                "use_ema": False    # EMA 사용 여부
            }
        )

    def get_indicators(self, df: pd.DataFrame) -> Dict[str, float]:
        fast_period = self.config.params.get("fast_period", 5)
        slow_period = self.config.params.get("slow_period", 20)
        use_ema = self.config.params.get("use_ema", False)

        ti = TechnicalIndicators

        if use_ema:
            fast_ma = ti.ema(df['close'], fast_period)
            slow_ma = ti.ema(df['close'], slow_period)
        else:
            fast_ma = ti.sma(df['close'], fast_period)
            slow_ma = ti.sma(df['close'], slow_period)

        return {
            "fast_ma": fast_ma.iloc[-1] if len(fast_ma) > 0 else 0,
            "slow_ma": slow_ma.iloc[-1] if len(slow_ma) > 0 else 0,
            "price": df['close'].iloc[-1] if len(df) > 0 else 0
        }

    def analyze(self, df: pd.DataFrame) -> TradeSignal:
        if len(df) < 2:
            return TradeSignal(
                signal=Signal.HOLD,
                strength=0.0,
                price=df['close'].iloc[-1] if len(df) > 0 else 0,
                timestamp=datetime.now(),
                reason="데이터 부족"
            )

        fast_period = self.config.params.get("fast_period", 5)
        slow_period = self.config.params.get("slow_period", 20)
        use_ema = self.config.params.get("use_ema", False)

        ti = TechnicalIndicators

        if use_ema:
            fast_ma = ti.ema(df['close'], fast_period)
            slow_ma = ti.ema(df['close'], slow_period)
        else:
            fast_ma = ti.sma(df['close'], fast_period)
            slow_ma = ti.sma(df['close'], slow_period)

        current_price = df['close'].iloc[-1]
        indicators = {
            "fast_ma": fast_ma.iloc[-1],
            "slow_ma": slow_ma.iloc[-1]
        }

        # 크로스오버 감지
        if len(fast_ma) >= 2 and len(slow_ma) >= 2:
            prev_fast = fast_ma.iloc[-2]
            prev_slow = slow_ma.iloc[-2]
            curr_fast = fast_ma.iloc[-1]
            curr_slow = slow_ma.iloc[-1]

            # 골든 크로스 (상향 돌파)
            if prev_fast <= prev_slow and curr_fast > curr_slow:
                gap_pct = (curr_fast - curr_slow) / curr_slow * 100
                strength = min(1.0, gap_pct / 2)  # 갭이 클수록 강한 시그널

                signal = TradeSignal(
                    signal=Signal.STRONG_BUY if strength > 0.7 else Signal.BUY,
                    strength=strength,
                    price=current_price,
                    timestamp=datetime.now(),
                    reason=f"골든크로스 발생 (갭: {gap_pct:.2f}%)",
                    indicators=indicators
                )
                self.record_signal(signal)
                return signal

            # 데드 크로스 (하향 돌파)
            elif prev_fast >= prev_slow and curr_fast < curr_slow:
                gap_pct = (curr_slow - curr_fast) / curr_slow * 100
                strength = min(1.0, gap_pct / 2)

                signal = TradeSignal(
                    signal=Signal.STRONG_SELL if strength > 0.7 else Signal.SELL,
                    strength=strength,
                    price=current_price,
                    timestamp=datetime.now(),
                    reason=f"데드크로스 발생 (갭: {gap_pct:.2f}%)",
                    indicators=indicators
                )
                self.record_signal(signal)
                return signal

        return TradeSignal(
            signal=Signal.HOLD,
            strength=0.0,
            price=current_price,
            timestamp=datetime.now(),
            reason="크로스오버 없음",
            indicators=indicators
        )


class RSIStrategy(BaseStrategy):
    """
    RSI 기반 전략

    - RSI < oversold: 과매도 → 매수
    - RSI > overbought: 과매수 → 매도
    """

    def _default_config(self) -> StrategyConfig:
        return StrategyConfig(
            name="RSI Strategy",
            description="RSI 과매수/과매도 전략",
            stop_loss_pct=0.03,
            take_profit_pct=0.05,
            params={
                "rsi_period": 14,
                "oversold": 30,
                "overbought": 70
            }
        )

    def get_indicators(self, df: pd.DataFrame) -> Dict[str, float]:
        rsi_period = self.config.params.get("rsi_period", 14)
        rsi = TechnicalIndicators.rsi(df['close'], rsi_period)

        return {
            "rsi": rsi.iloc[-1] if len(rsi) > 0 else 50,
            "price": df['close'].iloc[-1] if len(df) > 0 else 0
        }

    def analyze(self, df: pd.DataFrame) -> TradeSignal:
        if len(df) < 2:
            return TradeSignal(
                signal=Signal.HOLD,
                strength=0.0,
                price=df['close'].iloc[-1] if len(df) > 0 else 0,
                timestamp=datetime.now(),
                reason="데이터 부족"
            )

        rsi_period = self.config.params.get("rsi_period", 14)
        oversold = self.config.params.get("oversold", 30)
        overbought = self.config.params.get("overbought", 70)

        rsi = TechnicalIndicators.rsi(df['close'], rsi_period)
        current_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-2] if len(rsi) >= 2 else current_rsi
        current_price = df['close'].iloc[-1]

        indicators = {"rsi": current_rsi}

        # 과매도에서 반등
        if prev_rsi < oversold and current_rsi >= oversold:
            strength = (oversold - prev_rsi) / oversold
            signal = TradeSignal(
                signal=Signal.BUY,
                strength=min(1.0, strength),
                price=current_price,
                timestamp=datetime.now(),
                reason=f"RSI 과매도 반등 ({prev_rsi:.1f} → {current_rsi:.1f})",
                indicators=indicators
            )
            self.record_signal(signal)
            return signal

        # 극단적 과매도
        if current_rsi < oversold - 10:
            strength = (oversold - current_rsi) / oversold
            signal = TradeSignal(
                signal=Signal.STRONG_BUY,
                strength=min(1.0, strength),
                price=current_price,
                timestamp=datetime.now(),
                reason=f"RSI 극단적 과매도 ({current_rsi:.1f})",
                indicators=indicators
            )
            self.record_signal(signal)
            return signal

        # 과매수에서 하락
        if prev_rsi > overbought and current_rsi <= overbought:
            strength = (prev_rsi - overbought) / (100 - overbought)
            signal = TradeSignal(
                signal=Signal.SELL,
                strength=min(1.0, strength),
                price=current_price,
                timestamp=datetime.now(),
                reason=f"RSI 과매수 하락 ({prev_rsi:.1f} → {current_rsi:.1f})",
                indicators=indicators
            )
            self.record_signal(signal)
            return signal

        # 극단적 과매수
        if current_rsi > overbought + 10:
            strength = (current_rsi - overbought) / (100 - overbought)
            signal = TradeSignal(
                signal=Signal.STRONG_SELL,
                strength=min(1.0, strength),
                price=current_price,
                timestamp=datetime.now(),
                reason=f"RSI 극단적 과매수 ({current_rsi:.1f})",
                indicators=indicators
            )
            self.record_signal(signal)
            return signal

        return TradeSignal(
            signal=Signal.HOLD,
            strength=0.0,
            price=current_price,
            timestamp=datetime.now(),
            reason=f"RSI 중립 ({current_rsi:.1f})",
            indicators=indicators
        )


class MACDStrategy(BaseStrategy):
    """
    MACD 전략

    - MACD가 시그널선 상향 돌파: 매수
    - MACD가 시그널선 하향 돌파: 매도
    - 히스토그램 기울기로 강도 판단
    """

    def _default_config(self) -> StrategyConfig:
        return StrategyConfig(
            name="MACD Strategy",
            description="MACD 크로스오버 전략",
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            params={
                "fast_period": 12,
                "slow_period": 26,
                "signal_period": 9
            }
        )

    def get_indicators(self, df: pd.DataFrame) -> Dict[str, float]:
        fast = self.config.params.get("fast_period", 12)
        slow = self.config.params.get("slow_period", 26)
        signal_period = self.config.params.get("signal_period", 9)

        macd_result = TechnicalIndicators.macd(
            df['close'], fast, slow, signal_period
        )

        return {
            "macd": macd_result.macd.iloc[-1] if len(macd_result.macd) > 0 else 0,
            "signal": macd_result.signal.iloc[-1] if len(macd_result.signal) > 0 else 0,
            "histogram": macd_result.histogram.iloc[-1] if len(macd_result.histogram) > 0 else 0,
            "price": df['close'].iloc[-1] if len(df) > 0 else 0
        }

    def analyze(self, df: pd.DataFrame) -> TradeSignal:
        if len(df) < 2:
            return TradeSignal(
                signal=Signal.HOLD,
                strength=0.0,
                price=df['close'].iloc[-1] if len(df) > 0 else 0,
                timestamp=datetime.now(),
                reason="데이터 부족"
            )

        fast = self.config.params.get("fast_period", 12)
        slow = self.config.params.get("slow_period", 26)
        signal_period = self.config.params.get("signal_period", 9)

        macd_result = TechnicalIndicators.macd(
            df['close'], fast, slow, signal_period
        )

        macd_line = macd_result.macd
        signal_line = macd_result.signal
        histogram = macd_result.histogram

        current_price = df['close'].iloc[-1]
        indicators = {
            "macd": macd_line.iloc[-1],
            "signal": signal_line.iloc[-1],
            "histogram": histogram.iloc[-1]
        }

        if len(macd_line) >= 2:
            prev_macd = macd_line.iloc[-2]
            prev_signal = signal_line.iloc[-2]
            curr_macd = macd_line.iloc[-1]
            curr_signal = signal_line.iloc[-1]

            # MACD 상향 돌파
            if prev_macd <= prev_signal and curr_macd > curr_signal:
                # 히스토그램 기울기로 강도 계산
                hist_slope = histogram.iloc[-1] - histogram.iloc[-2] if len(histogram) >= 2 else 0
                strength = min(1.0, abs(hist_slope) / (abs(curr_macd) + 0.001) * 10)

                signal = TradeSignal(
                    signal=Signal.STRONG_BUY if strength > 0.7 else Signal.BUY,
                    strength=strength,
                    price=current_price,
                    timestamp=datetime.now(),
                    reason="MACD 골든크로스",
                    indicators=indicators
                )
                self.record_signal(signal)
                return signal

            # MACD 하향 돌파
            elif prev_macd >= prev_signal and curr_macd < curr_signal:
                hist_slope = histogram.iloc[-2] - histogram.iloc[-1] if len(histogram) >= 2 else 0
                strength = min(1.0, abs(hist_slope) / (abs(curr_macd) + 0.001) * 10)

                signal = TradeSignal(
                    signal=Signal.STRONG_SELL if strength > 0.7 else Signal.SELL,
                    strength=strength,
                    price=current_price,
                    timestamp=datetime.now(),
                    reason="MACD 데드크로스",
                    indicators=indicators
                )
                self.record_signal(signal)
                return signal

        return TradeSignal(
            signal=Signal.HOLD,
            strength=0.0,
            price=current_price,
            timestamp=datetime.now(),
            reason="MACD 크로스오버 없음",
            indicators=indicators
        )


class CompositeStrategy(BaseStrategy):
    """
    복합 전략 (MA + RSI + MACD)

    - 여러 지표의 시그널을 종합하여 판단
    - 가중치 기반 점수 계산
    """

    def _default_config(self) -> StrategyConfig:
        return StrategyConfig(
            name="Composite Strategy",
            description="MA + RSI + MACD 복합 전략",
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            params={
                # MA 설정
                "ma_fast": 5,
                "ma_slow": 20,
                # RSI 설정
                "rsi_period": 14,
                "rsi_oversold": 30,
                "rsi_overbought": 70,
                # MACD 설정
                "macd_fast": 12,
                "macd_slow": 26,
                "macd_signal": 9,
                # 가중치
                "weight_ma": 0.3,
                "weight_rsi": 0.3,
                "weight_macd": 0.4,
                # 진입 임계값
                "entry_threshold": 0.6
            }
        )

    def get_indicators(self, df: pd.DataFrame) -> Dict[str, float]:
        ti = TechnicalIndicators
        params = self.config.params

        # MA
        fast_ma = ti.sma(df['close'], params["ma_fast"])
        slow_ma = ti.sma(df['close'], params["ma_slow"])

        # RSI
        rsi = ti.rsi(df['close'], params["rsi_period"])

        # MACD
        macd_result = ti.macd(
            df['close'],
            params["macd_fast"],
            params["macd_slow"],
            params["macd_signal"]
        )

        return {
            "fast_ma": fast_ma.iloc[-1] if len(fast_ma) > 0 else 0,
            "slow_ma": slow_ma.iloc[-1] if len(slow_ma) > 0 else 0,
            "rsi": rsi.iloc[-1] if len(rsi) > 0 else 50,
            "macd": macd_result.macd.iloc[-1] if len(macd_result.macd) > 0 else 0,
            "macd_signal": macd_result.signal.iloc[-1] if len(macd_result.signal) > 0 else 0,
            "price": df['close'].iloc[-1] if len(df) > 0 else 0
        }

    def _calculate_ma_score(self, df: pd.DataFrame) -> float:
        """MA 점수 계산 (-1 ~ 1)"""
        params = self.config.params
        ti = TechnicalIndicators

        fast_ma = ti.sma(df['close'], params["ma_fast"])
        slow_ma = ti.sma(df['close'], params["ma_slow"])

        if len(fast_ma) < 2 or len(slow_ma) < 2:
            return 0.0

        curr_fast = fast_ma.iloc[-1]
        curr_slow = slow_ma.iloc[-1]
        prev_fast = fast_ma.iloc[-2]
        prev_slow = slow_ma.iloc[-2]

        # 골든크로스: +1, 데드크로스: -1, 그 외: 위치에 따른 점수
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return 1.0
        elif prev_fast >= prev_slow and curr_fast < curr_slow:
            return -1.0
        else:
            # 상대 위치
            gap_pct = (curr_fast - curr_slow) / curr_slow
            return max(-1.0, min(1.0, gap_pct * 10))

    def _calculate_rsi_score(self, df: pd.DataFrame) -> float:
        """RSI 점수 계산 (-1 ~ 1)"""
        params = self.config.params
        rsi = TechnicalIndicators.rsi(df['close'], params["rsi_period"])

        if len(rsi) == 0:
            return 0.0

        current_rsi = rsi.iloc[-1]
        oversold = params["rsi_oversold"]
        overbought = params["rsi_overbought"]

        if current_rsi < oversold:
            # 과매도: 매수 신호
            return (oversold - current_rsi) / oversold
        elif current_rsi > overbought:
            # 과매수: 매도 신호
            return -(current_rsi - overbought) / (100 - overbought)
        else:
            # 중립 구간
            mid = (oversold + overbought) / 2
            return (mid - current_rsi) / (overbought - oversold) * 0.5

    def _calculate_macd_score(self, df: pd.DataFrame) -> float:
        """MACD 점수 계산 (-1 ~ 1)"""
        params = self.config.params
        macd_result = TechnicalIndicators.macd(
            df['close'],
            params["macd_fast"],
            params["macd_slow"],
            params["macd_signal"]
        )

        macd_line = macd_result.macd
        signal_line = macd_result.signal
        histogram = macd_result.histogram

        if len(macd_line) < 2:
            return 0.0

        prev_macd = macd_line.iloc[-2]
        prev_signal = signal_line.iloc[-2]
        curr_macd = macd_line.iloc[-1]
        curr_signal = signal_line.iloc[-1]
        curr_hist = histogram.iloc[-1]

        # 크로스오버
        if prev_macd <= prev_signal and curr_macd > curr_signal:
            return 1.0
        elif prev_macd >= prev_signal and curr_macd < curr_signal:
            return -1.0
        else:
            # 히스토그램 방향
            if len(histogram) >= 2:
                hist_direction = histogram.iloc[-1] - histogram.iloc[-2]
                return max(-1.0, min(1.0, hist_direction / (abs(curr_macd) + 0.001) * 5))
            return 0.0

    def analyze(self, df: pd.DataFrame) -> TradeSignal:
        if len(df) < 30:  # 충분한 데이터 필요
            return TradeSignal(
                signal=Signal.HOLD,
                strength=0.0,
                price=df['close'].iloc[-1] if len(df) > 0 else 0,
                timestamp=datetime.now(),
                reason="데이터 부족"
            )

        params = self.config.params

        # 각 지표 점수 계산
        ma_score = self._calculate_ma_score(df)
        rsi_score = self._calculate_rsi_score(df)
        macd_score = self._calculate_macd_score(df)

        # 가중 평균 점수
        total_score = (
            ma_score * params["weight_ma"] +
            rsi_score * params["weight_rsi"] +
            macd_score * params["weight_macd"]
        )

        current_price = df['close'].iloc[-1]
        indicators = self.get_indicators(df)
        indicators.update({
            "ma_score": ma_score,
            "rsi_score": rsi_score,
            "macd_score": macd_score,
            "total_score": total_score
        })

        threshold = params["entry_threshold"]
        strength = abs(total_score)

        # 시그널 결정
        if total_score >= threshold:
            signal_type = Signal.STRONG_BUY if total_score >= 0.8 else Signal.BUY
            reason = f"복합 매수 신호 (점수: {total_score:.2f})"
        elif total_score <= -threshold:
            signal_type = Signal.STRONG_SELL if total_score <= -0.8 else Signal.SELL
            reason = f"복합 매도 신호 (점수: {total_score:.2f})"
        else:
            signal_type = Signal.HOLD
            reason = f"중립 (점수: {total_score:.2f})"

        signal = TradeSignal(
            signal=signal_type,
            strength=strength,
            price=current_price,
            timestamp=datetime.now(),
            reason=reason,
            indicators=indicators
        )

        if signal_type != Signal.HOLD:
            self.record_signal(signal)

        return signal


# 전략 팩토리
def create_strategy(strategy_type: str, **kwargs) -> BaseStrategy:
    """
    전략 생성 팩토리

    Args:
        strategy_type: 전략 유형 (ma_crossover, rsi, macd, composite)
        **kwargs: 추가 설정

    Returns:
        전략 인스턴스
    """
    strategies = {
        "ma_crossover": MACrossoverStrategy,
        "rsi": RSIStrategy,
        "macd": MACDStrategy,
        "composite": CompositeStrategy
    }

    if strategy_type not in strategies:
        raise ValueError(f"알 수 없는 전략: {strategy_type}. 사용 가능: {list(strategies.keys())}")

    strategy_class = strategies[strategy_type]
    strategy = strategy_class()

    # 추가 파라미터 적용
    if kwargs:
        strategy.config.params.update(kwargs)

    return strategy
