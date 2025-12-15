"""
기술적 지표 계산 모듈
- 이동평균 (SMA, EMA)
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- 볼린저 밴드 (Bollinger Bands)
- 스토캐스틱 (Stochastic)
- ATR (Average True Range)
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional
from dataclasses import dataclass


@dataclass
class MACDResult:
    """MACD 계산 결과"""
    macd: pd.Series       # MACD 라인
    signal: pd.Series     # 시그널 라인
    histogram: pd.Series  # 히스토그램


@dataclass
class BollingerBands:
    """볼린저 밴드 계산 결과"""
    upper: pd.Series   # 상단 밴드
    middle: pd.Series  # 중간 밴드 (SMA)
    lower: pd.Series   # 하단 밴드
    width: pd.Series   # 밴드 폭


@dataclass
class StochasticResult:
    """스토캐스틱 계산 결과"""
    k: pd.Series  # %K
    d: pd.Series  # %D


class TechnicalIndicators:
    """기술적 지표 계산 클래스"""

    @staticmethod
    def sma(data: pd.Series, period: int) -> pd.Series:
        """
        단순 이동평균 (Simple Moving Average)

        Args:
            data: 가격 데이터 시리즈
            period: 기간

        Returns:
            SMA 시리즈
        """
        return data.rolling(window=period).mean()

    @staticmethod
    def ema(data: pd.Series, period: int) -> pd.Series:
        """
        지수 이동평균 (Exponential Moving Average)

        Args:
            data: 가격 데이터 시리즈
            period: 기간

        Returns:
            EMA 시리즈
        """
        return data.ewm(span=period, adjust=False).mean()

    @staticmethod
    def rsi(data: pd.Series, period: int = 14) -> pd.Series:
        """
        RSI (Relative Strength Index)

        Args:
            data: 가격 데이터 시리즈
            period: 기간 (기본값: 14)

        Returns:
            RSI 시리즈 (0-100)
        """
        delta = data.diff()

        gain = delta.where(delta > 0, 0)
        loss = (-delta).where(delta < 0, 0)

        avg_gain = gain.ewm(span=period, adjust=False).mean()
        avg_loss = loss.ewm(span=period, adjust=False).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    @staticmethod
    def macd(
        data: pd.Series,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> MACDResult:
        """
        MACD (Moving Average Convergence Divergence)

        Args:
            data: 가격 데이터 시리즈
            fast_period: 빠른 EMA 기간 (기본값: 12)
            slow_period: 느린 EMA 기간 (기본값: 26)
            signal_period: 시그널 EMA 기간 (기본값: 9)

        Returns:
            MACDResult (macd, signal, histogram)
        """
        fast_ema = TechnicalIndicators.ema(data, fast_period)
        slow_ema = TechnicalIndicators.ema(data, slow_period)

        macd_line = fast_ema - slow_ema
        signal_line = TechnicalIndicators.ema(macd_line, signal_period)
        histogram = macd_line - signal_line

        return MACDResult(
            macd=macd_line,
            signal=signal_line,
            histogram=histogram
        )

    @staticmethod
    def bollinger_bands(
        data: pd.Series,
        period: int = 20,
        std_dev: float = 2.0
    ) -> BollingerBands:
        """
        볼린저 밴드

        Args:
            data: 가격 데이터 시리즈
            period: 이동평균 기간 (기본값: 20)
            std_dev: 표준편차 배수 (기본값: 2.0)

        Returns:
            BollingerBands (upper, middle, lower, width)
        """
        middle = TechnicalIndicators.sma(data, period)
        std = data.rolling(window=period).std()

        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        width = (upper - lower) / middle * 100  # 밴드 폭 (%)

        return BollingerBands(
            upper=upper,
            middle=middle,
            lower=lower,
            width=width
        )

    @staticmethod
    def stochastic(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        k_period: int = 14,
        d_period: int = 3
    ) -> StochasticResult:
        """
        스토캐스틱 오실레이터

        Args:
            high: 고가 시리즈
            low: 저가 시리즈
            close: 종가 시리즈
            k_period: %K 기간 (기본값: 14)
            d_period: %D 기간 (기본값: 3)

        Returns:
            StochasticResult (%K, %D)
        """
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()

        k = 100 * (close - lowest_low) / (highest_high - lowest_low)
        d = k.rolling(window=d_period).mean()

        return StochasticResult(k=k, d=d)

    @staticmethod
    def atr(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14
    ) -> pd.Series:
        """
        ATR (Average True Range)

        Args:
            high: 고가 시리즈
            low: 저가 시리즈
            close: 종가 시리즈
            period: 기간 (기본값: 14)

        Returns:
            ATR 시리즈
        """
        prev_close = close.shift(1)

        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)

        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = true_range.ewm(span=period, adjust=False).mean()

        return atr

    @staticmethod
    def adx(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14
    ) -> pd.Series:
        """
        ADX (Average Directional Index) - 추세 강도

        Args:
            high: 고가 시리즈
            low: 저가 시리즈
            close: 종가 시리즈
            period: 기간 (기본값: 14)

        Returns:
            ADX 시리즈
        """
        # +DM, -DM 계산
        plus_dm = high.diff()
        minus_dm = -low.diff()

        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        # ATR 계산
        atr = TechnicalIndicators.atr(high, low, close, period)

        # +DI, -DI 계산
        plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)

        # DX 계산
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)

        # ADX 계산
        adx = dx.ewm(span=period, adjust=False).mean()

        return adx

    @staticmethod
    def volume_ma(volume: pd.Series, period: int = 20) -> pd.Series:
        """
        거래량 이동평균

        Args:
            volume: 거래량 시리즈
            period: 기간 (기본값: 20)

        Returns:
            거래량 MA 시리즈
        """
        return TechnicalIndicators.sma(volume, period)

    @staticmethod
    def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        """
        OBV (On Balance Volume)

        Args:
            close: 종가 시리즈
            volume: 거래량 시리즈

        Returns:
            OBV 시리즈
        """
        direction = np.sign(close.diff())
        direction.iloc[0] = 0
        return (direction * volume).cumsum()


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    DataFrame에 모든 기술적 지표 추가

    Args:
        df: OHLCV DataFrame (open, high, low, close, volume 컬럼 필요)

    Returns:
        지표가 추가된 DataFrame
    """
    result = df.copy()
    ti = TechnicalIndicators

    # 이동평균
    result['sma_5'] = ti.sma(df['close'], 5)
    result['sma_20'] = ti.sma(df['close'], 20)
    result['sma_60'] = ti.sma(df['close'], 60)
    result['ema_12'] = ti.ema(df['close'], 12)
    result['ema_26'] = ti.ema(df['close'], 26)

    # RSI
    result['rsi'] = ti.rsi(df['close'], 14)

    # MACD
    macd = ti.macd(df['close'])
    result['macd'] = macd.macd
    result['macd_signal'] = macd.signal
    result['macd_hist'] = macd.histogram

    # 볼린저 밴드
    bb = ti.bollinger_bands(df['close'])
    result['bb_upper'] = bb.upper
    result['bb_middle'] = bb.middle
    result['bb_lower'] = bb.lower
    result['bb_width'] = bb.width

    # 스토캐스틱
    stoch = ti.stochastic(df['high'], df['low'], df['close'])
    result['stoch_k'] = stoch.k
    result['stoch_d'] = stoch.d

    # ATR
    result['atr'] = ti.atr(df['high'], df['low'], df['close'])

    # ADX
    result['adx'] = ti.adx(df['high'], df['low'], df['close'])

    # 거래량 지표
    result['volume_ma'] = ti.volume_ma(df['volume'])
    result['obv'] = ti.obv(df['close'], df['volume'])

    return result
