import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timedelta
import config  # Compatibility layer for TRADING_CONFIG

# Import from new lib structure
from lib.api.bithumb_api import get_candlestick, get_ticker
from lib.core.logger import TradingLogger
from lib.interfaces.version_interface import VersionInterface

# Import version 1 config
from .config_v1 import (
    get_version_config,
    VERSION_METADATA,
    INDICATOR_CONFIG,
    SIGNAL_WEIGHTS,
    REGIME_CONFIG,
    RISK_CONFIG,
    INTERVAL_PRESETS
)
from lib.core.config_common import merge_configs, get_common_config

def _validate_indicator_series(series: pd.Series, min_val: float = None, max_val: float = None, fill_value: float = 0) -> pd.Series:
    """
    FIX: Validate and clean indicator values to prevent NaN/Inf propagation

    Args:
        series: pandas Series to validate
        min_val: Minimum allowed value (clips below this)
        max_val: Maximum allowed value (clips above this)
        fill_value: Value to use for NaN replacement

    Returns:
        Cleaned series with no NaN or Inf values
    """
    # Remove inf values (replace with NaN first, then fill)
    series = series.replace([np.inf, -np.inf], np.nan)

    # Clip to valid range if specified
    if min_val is not None or max_val is not None:
        series = series.clip(lower=min_val, upper=max_val)

    # Fill remaining NaN values
    series = series.fillna(fill_value)

    return series

def calculate_moving_average(df: pd.DataFrame, window: int) -> pd.Series:
    """
    주어진 데이터프레임과 윈도우 크기를 사용하여 이동평균을 계산합니다.

    :param df: 시세 정보 DataFrame (종가 'close' 컬럼 필요)
    :param window: 이동평균을 계산할 기간(일)
    :return: 이동평균선 데이터 (pandas Series)
    """
    return df['close'].rolling(window=window).mean()

def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    RSI(Relative Strength Index) 계산
    """
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    # FIX: Prevent division by zero and handle edge cases
    # Replace zero loss with small epsilon to avoid Inf
    loss = loss.replace(0, 1e-10)
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    # FIX: Clip to valid range [0, 100] and fill any remaining NaN with neutral value
    rsi = rsi.clip(0, 100)
    rsi = rsi.fillna(50)  # Neutral RSI when insufficient data

    return rsi

def calculate_bollinger_bands(df: pd.DataFrame, window: int = 20, num_std: float = 2) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    볼린저 밴드 계산
    """
    ma = df['close'].rolling(window=window).mean()
    std = df['close'].rolling(window=window).std()

    upper_band = ma + (std * num_std)
    lower_band = ma - (std * num_std)

    return upper_band, ma, lower_band

def calculate_volume_ratio(df: pd.DataFrame, window: int = 10) -> pd.Series:
    """
    거래량 비율 계산 (현재 거래량 / 평균 거래량)
    """
    avg_volume = df['volume'].rolling(window=window).mean()
    return df['volume'] / avg_volume

def calculate_macd(df: pd.DataFrame, fast: int = 8, slow: int = 17, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    MACD 계산 (1시간봉 최적화)

    Args:
        df: OHLCV 데이터프레임
        fast: 단기 EMA 기간 (기본값: 8, 1h 기준 8시간)
        slow: 장기 EMA 기간 (기본값: 17, 1h 기준 17시간)
        signal: 시그널선 EMA 기간 (기본값: 9, 1h 기준 9시간)

    Returns:
        macd_line: MACD선 (fast EMA - slow EMA)
        signal_line: 시그널선 (MACD의 signal 기간 EMA)
        histogram: 히스토그램 (MACD - Signal)
    """
    exp1 = df['close'].ewm(span=fast, adjust=False).mean()
    exp2 = df['close'].ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    ATR (Average True Range) 계산

    30분봉/1시간봉 권장: 14주기 (7시간/14시간 데이터)

    Args:
        df: OHLCV 데이터프레임
        period: ATR 계산 기간

    Returns:
        ATR 값 (pandas Series)
    """
    high = df['high']
    low = df['low']
    close = df['close']

    # True Range 계산
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()

    return atr

def calculate_atr_percent(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    ATR을 가격 대비 퍼센트로 계산 (더 직관적)

    Args:
        df: OHLCV 데이터프레임
        period: ATR 계산 기간

    Returns:
        ATR 퍼센트 값
    """
    atr = calculate_atr(df, period)
    atr_percent = (atr / df['close']) * 100
    return atr_percent

def calculate_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
    """
    Stochastic Oscillator 계산

    30분봉/1시간봉 권장: K=14 (7시간/14시간), D=3 (1.5시간/3시간)

    Args:
        df: OHLCV 데이터프레임
        k_period: %K 계산 기간
        d_period: %D 계산 기간 (%K의 이동평균)

    Returns:
        k_percent: %K 값
        d_percent: %D 값
    """
    low_min = df['low'].rolling(window=k_period).min()
    high_max = df['high'].rolling(window=k_period).max()

    # %K 계산
    k_percent = 100 * ((df['close'] - low_min) / (high_max - low_min))

    # %D 계산 (K의 이동평균)
    d_percent = k_percent.rolling(window=d_period).mean()

    return k_percent, d_percent

def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    ADX (Average Directional Index) 계산
    추세의 강도를 측정 (0~100, 높을수록 강한 추세)

    Args:
        df: OHLCV 데이터프레임
        period: ADX 계산 기간

    Returns:
        ADX 값 (pandas Series)
    """
    high = df['high']
    low = df['low']
    close = df['close']

    # +DM, -DM 계산
    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0

    # True Range
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # ATR
    atr = tr.rolling(period).mean()

    # +DI, -DI
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)

    # DX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)

    # ADX
    adx = dx.rolling(period).mean()

    return adx

def detect_candlestick_patterns(df: pd.DataFrame) -> Dict[str, Any]:
    """
    촛대 패턴 인식 (Candlestick Pattern Recognition)

    주요 패턴:
    - Bullish/Bearish Engulfing (강세/약세 포용형)
    - Hammer/Inverted Hammer (망치형/역망치형)
    - Dragonfly/Gravestone Doji (잠자리/비석형 도지)

    Args:
        df: OHLCV 데이터프레임 (최소 3개 캔들 필요)

    Returns:
        pattern_type: 감지된 패턴 이름
        pattern_score: 패턴 신호 강도 (-1.0 ~ +1.0)
        pattern_confidence: 패턴 신뢰도 (0.0 ~ 1.0)
        pattern_description: 패턴 설명
    """
    if len(df) < 3:
        return {
            'pattern_type': 'none',
            'pattern_score': 0.0,
            'pattern_confidence': 0.0,
            'pattern_description': '데이터 부족'
        }

    try:
        # 최근 3개 캔들 추출
        last_candle = df.iloc[-1]
        prev_candle = df.iloc[-2]
        prev_prev_candle = df.iloc[-3] if len(df) >= 3 else None

        open_price = last_candle['open']
        close_price = last_candle['close']
        high_price = last_candle['high']
        low_price = last_candle['low']

        prev_open = prev_candle['open']
        prev_close = prev_candle['close']
        prev_high = prev_candle['high']
        prev_low = prev_candle['low']

        # 캔들 바디와 꼬리 크기 계산
        body_size = abs(close_price - open_price)
        candle_range = high_price - low_price
        upper_shadow = high_price - max(open_price, close_price)
        lower_shadow = min(open_price, close_price) - low_price

        prev_body_size = abs(prev_close - prev_open)

        # NaN 체크 및 제로 디비전 방지
        if candle_range == 0 or pd.isna(candle_range):
            candle_range = 0.0001
        if prev_body_size == 0 or pd.isna(prev_body_size):
            prev_body_size = 0.0001

        body_ratio = body_size / candle_range

        # 패턴 감지 변수 초기화
        pattern_type = 'none'
        pattern_score = 0.0
        pattern_confidence = 0.0
        pattern_description = '패턴 없음'

        # 1. Bullish Engulfing (강세 포용형)
        # 이전 캔들이 음봉, 현재 캔들이 양봉이면서 이전 캔들을 완전히 포용
        if (prev_close < prev_open and  # 이전 캔들이 음봉
            close_price > open_price and  # 현재 캔들이 양봉
            open_price < prev_close and   # 현재 시가가 이전 종가보다 낮음
            close_price > prev_open):     # 현재 종가가 이전 시가보다 높음

            # 포용 강도 계산 (현재 바디가 이전 바디를 얼마나 초과하는지)
            engulfing_strength = min(body_size / prev_body_size, 2.0) / 2.0
            pattern_type = 'bullish_engulfing'
            pattern_score = 0.7 + (engulfing_strength * 0.3)  # 0.7 ~ 1.0
            pattern_confidence = 0.8 if engulfing_strength > 1.5 else 0.6
            pattern_description = '강세 포용형 (Bullish Engulfing) - 반등 신호'

        # 2. Bearish Engulfing (약세 포용형)
        elif (prev_close > prev_open and  # 이전 캔들이 양봉
              close_price < open_price and  # 현재 캔들이 음봉
              open_price > prev_close and   # 현재 시가가 이전 종가보다 높음
              close_price < prev_open):     # 현재 종가가 이전 시가보다 낮음

            engulfing_strength = min(body_size / prev_body_size, 2.0) / 2.0
            pattern_type = 'bearish_engulfing'
            pattern_score = -(0.7 + (engulfing_strength * 0.3))  # -1.0 ~ -0.7
            pattern_confidence = 0.8 if engulfing_strength > 1.5 else 0.6
            pattern_description = '약세 포용형 (Bearish Engulfing) - 하락 신호'

        # 3. Hammer (망치형) - 하락 추세에서 반등 신호
        elif (body_ratio < 0.3 and  # 작은 바디
              lower_shadow > body_size * 2 and  # 긴 아래 꼬리 (바디의 2배 이상)
              upper_shadow < body_size * 0.5):  # 짧은 위 꼬리

            # 하락 추세 확인 (이전 2개 캔들이 하락)
            is_downtrend = (prev_close < prev_open and
                           (prev_prev_candle is not None and prev_prev_candle['close'] > prev_open))

            pattern_type = 'hammer'
            pattern_score = 0.6 if is_downtrend else 0.4
            pattern_confidence = 0.7 if is_downtrend else 0.5
            pattern_description = '망치형 (Hammer) - 하락 후 반등 가능'

        # 4. Inverted Hammer (역망치형) - 하락 추세에서 반등 신호
        elif (body_ratio < 0.3 and
              upper_shadow > body_size * 2 and  # 긴 위 꼬리
              lower_shadow < body_size * 0.5):  # 짧은 아래 꼬리

            is_downtrend = (prev_close < prev_open and
                           (prev_prev_candle is not None and prev_prev_candle['close'] > prev_open))

            pattern_type = 'inverted_hammer'
            pattern_score = 0.5 if is_downtrend else 0.3
            pattern_confidence = 0.6 if is_downtrend else 0.4
            pattern_description = '역망치형 (Inverted Hammer) - 반등 시도'

        # 5. Dragonfly Doji (잠자리 도지) - 강한 반등 신호
        elif (body_size < candle_range * 0.1 and  # 매우 작은 바디
              lower_shadow > candle_range * 0.7 and  # 긴 아래 꼬리
              upper_shadow < candle_range * 0.1):  # 거의 없는 위 꼬리

            pattern_type = 'dragonfly_doji'
            pattern_score = 0.7
            pattern_confidence = 0.75
            pattern_description = '잠자리 도지 (Dragonfly Doji) - 강한 반등 신호'

        # 6. Gravestone Doji (비석 도지) - 강한 하락 신호
        elif (body_size < candle_range * 0.1 and
              upper_shadow > candle_range * 0.7 and  # 긴 위 꼬리
              lower_shadow < candle_range * 0.1):  # 거의 없는 아래 꼬리

            pattern_type = 'gravestone_doji'
            pattern_score = -0.7
            pattern_confidence = 0.75
            pattern_description = '비석 도지 (Gravestone Doji) - 강한 하락 신호'

        return {
            'pattern_type': pattern_type,
            'pattern_score': float(pattern_score),
            'pattern_confidence': float(pattern_confidence),
            'pattern_description': pattern_description,
            'body_ratio': float(body_ratio),
            'upper_shadow_ratio': float(upper_shadow / candle_range) if candle_range > 0 else 0.0,
            'lower_shadow_ratio': float(lower_shadow / candle_range) if candle_range > 0 else 0.0
        }

    except Exception as e:
        # 오류 발생 시 안전하게 중립 반환
        return {
            'pattern_type': 'error',
            'pattern_score': 0.0,
            'pattern_confidence': 0.0,
            'pattern_description': f'패턴 감지 오류: {str(e)}'
        }

def detect_rsi_divergence(df: pd.DataFrame, lookback: int = 30, rsi_period: int = 14) -> Dict[str, Any]:
    """
    RSI 다이버전스 감지 (RSI Divergence Detection)

    Bullish Divergence (강세 다이버전스):
    - 가격은 lower low를 만들지만, RSI는 higher low를 만드는 경우
    - 하락 추세의 약화, 반등 가능성 시사

    Bearish Divergence (약세 다이버전스):
    - 가격은 higher high를 만들지만, RSI는 lower high를 만드는 경우
    - 상승 추세의 약화, 하락 가능성 시사

    Args:
        df: OHLCV 데이터프레임
        lookback: 다이버전스 탐지 기간 (기본 30 캔들)
        rsi_period: RSI 계산 기간 (기본 14)

    Returns:
        divergence_type: 'bullish', 'bearish', 'none'
        strength: 다이버전스 강도 (0.0 ~ 1.0)
        price_change: 가격 변화율 (%)
        rsi_change: RSI 변화율
        description: 설명
    """
    if len(df) < lookback + rsi_period:
        return {
            'divergence_type': 'none',
            'strength': 0.0,
            'price_change': 0.0,
            'rsi_change': 0.0,
            'description': '데이터 부족'
        }

    try:
        # RSI 계산 (아직 계산되지 않은 경우)
        if 'rsi' not in df.columns:
            df['rsi'] = calculate_rsi(df, rsi_period)

        # 최근 lookback 기간의 데이터 추출
        recent_df = df.tail(lookback).copy()

        # 가격과 RSI의 고점/저점 찾기
        close_prices = recent_df['close'].values
        rsi_values = recent_df['rsi'].values

        # NaN 제거
        valid_indices = ~(pd.isna(close_prices) | pd.isna(rsi_values))
        if valid_indices.sum() < 10:  # 최소 10개 데이터 필요
            return {
                'divergence_type': 'none',
                'strength': 0.0,
                'price_change': 0.0,
                'rsi_change': 0.0,
                'description': '유효 데이터 부족'
            }

        close_prices = close_prices[valid_indices]
        rsi_values = rsi_values[valid_indices]

        # 고점과 저점 찾기 (rolling window 사용)
        window = 5  # 전후 5개 캔들 범위에서 고점/저점 검색

        # 가격 고점/저점 인덱스
        price_highs = []
        price_lows = []
        rsi_highs = []
        rsi_lows = []

        for i in range(window, len(close_prices) - window):
            # 가격 고점
            if close_prices[i] == max(close_prices[i-window:i+window+1]):
                price_highs.append((i, close_prices[i]))
            # 가격 저점
            if close_prices[i] == min(close_prices[i-window:i+window+1]):
                price_lows.append((i, close_prices[i]))

            # RSI 고점
            if rsi_values[i] == max(rsi_values[i-window:i+window+1]):
                rsi_highs.append((i, rsi_values[i]))
            # RSI 저점
            if rsi_values[i] == min(rsi_values[i-window:i+window+1]):
                rsi_lows.append((i, rsi_values[i]))

        # Bullish Divergence 확인 (가격 lower low, RSI higher low)
        if len(price_lows) >= 2 and len(rsi_lows) >= 2:
            # 최근 2개 저점 비교
            recent_price_lows = sorted(price_lows, key=lambda x: x[0])[-2:]
            recent_rsi_lows = sorted(rsi_lows, key=lambda x: x[0])[-2:]

            price_low_1, price_low_2 = recent_price_lows[0][1], recent_price_lows[1][1]
            rsi_low_1, rsi_low_2 = recent_rsi_lows[0][1], recent_rsi_lows[1][1]

            # 가격은 하락했지만 RSI는 상승 (bullish divergence)
            if price_low_2 < price_low_1 and rsi_low_2 > rsi_low_1:
                price_change = ((price_low_2 - price_low_1) / price_low_1) * 100
                rsi_change = rsi_low_2 - rsi_low_1

                # 강도 계산: RSI 상승폭과 가격 하락폭의 비율
                strength = min(abs(rsi_change) / 10.0, 1.0) * min(abs(price_change) / 5.0, 1.0)

                return {
                    'divergence_type': 'bullish',
                    'strength': float(strength),
                    'price_change': float(price_change),
                    'rsi_change': float(rsi_change),
                    'description': f'강세 다이버전스: 가격 {price_change:.2f}% 하락, RSI {rsi_change:.1f} 상승'
                }

        # Bearish Divergence 확인 (가격 higher high, RSI lower high)
        if len(price_highs) >= 2 and len(rsi_highs) >= 2:
            recent_price_highs = sorted(price_highs, key=lambda x: x[0])[-2:]
            recent_rsi_highs = sorted(rsi_highs, key=lambda x: x[0])[-2:]

            price_high_1, price_high_2 = recent_price_highs[0][1], recent_price_highs[1][1]
            rsi_high_1, rsi_high_2 = recent_rsi_highs[0][1], recent_rsi_highs[1][1]

            # 가격은 상승했지만 RSI는 하락 (bearish divergence)
            if price_high_2 > price_high_1 and rsi_high_2 < rsi_high_1:
                price_change = ((price_high_2 - price_high_1) / price_high_1) * 100
                rsi_change = rsi_high_2 - rsi_high_1

                strength = min(abs(rsi_change) / 10.0, 1.0) * min(abs(price_change) / 5.0, 1.0)

                return {
                    'divergence_type': 'bearish',
                    'strength': float(strength),
                    'price_change': float(price_change),
                    'rsi_change': float(rsi_change),
                    'description': f'약세 다이버전스: 가격 {price_change:.2f}% 상승, RSI {rsi_change:.1f} 하락'
                }

        # 다이버전스 없음
        return {
            'divergence_type': 'none',
            'strength': 0.0,
            'price_change': 0.0,
            'rsi_change': 0.0,
            'description': '다이버전스 없음'
        }

    except Exception as e:
        return {
            'divergence_type': 'error',
            'strength': 0.0,
            'price_change': 0.0,
            'rsi_change': 0.0,
            'description': f'RSI 다이버전스 감지 오류: {str(e)}'
        }

def detect_macd_divergence(df: pd.DataFrame, lookback: int = 30,
                          macd_fast: int = 8, macd_slow: int = 17, macd_signal: int = 9) -> Dict[str, Any]:
    """
    MACD 다이버전스 감지 (MACD Divergence Detection)

    RSI 다이버전스와 유사하게 동작하지만 MACD 라인을 사용

    Bullish Divergence:
    - 가격은 lower low, MACD는 higher low
    - 강한 반등 신호

    Bearish Divergence:
    - 가격은 higher high, MACD는 lower high
    - 강한 하락 신호

    Args:
        df: OHLCV 데이터프레임
        lookback: 다이버전스 탐지 기간
        macd_fast: MACD 단기 EMA
        macd_slow: MACD 장기 EMA
        macd_signal: MACD 시그널선 EMA

    Returns:
        divergence_type: 'bullish', 'bearish', 'none'
        strength: 다이버전스 강도 (0.0 ~ 1.0)
        price_change: 가격 변화율 (%)
        macd_change: MACD 변화값
        description: 설명
    """
    if len(df) < lookback + max(macd_fast, macd_slow):
        return {
            'divergence_type': 'none',
            'strength': 0.0,
            'price_change': 0.0,
            'macd_change': 0.0,
            'description': '데이터 부족'
        }

    try:
        # MACD 계산 (아직 계산되지 않은 경우)
        if 'macd_line' not in df.columns:
            macd_line, signal_line, histogram = calculate_macd(df, macd_fast, macd_slow, macd_signal)
            df['macd_line'] = macd_line
            df['macd_signal'] = signal_line
            df['macd_histogram'] = histogram

        # 최근 lookback 기간의 데이터 추출
        recent_df = df.tail(lookback).copy()

        # 가격과 MACD 값 추출
        close_prices = recent_df['close'].values
        macd_values = recent_df['macd_line'].values

        # NaN 제거
        valid_indices = ~(pd.isna(close_prices) | pd.isna(macd_values))
        if valid_indices.sum() < 10:
            return {
                'divergence_type': 'none',
                'strength': 0.0,
                'price_change': 0.0,
                'macd_change': 0.0,
                'description': '유효 데이터 부족'
            }

        close_prices = close_prices[valid_indices]
        macd_values = macd_values[valid_indices]

        # 고점과 저점 찾기
        window = 5

        price_highs = []
        price_lows = []
        macd_highs = []
        macd_lows = []

        for i in range(window, len(close_prices) - window):
            # 가격 고점
            if close_prices[i] == max(close_prices[i-window:i+window+1]):
                price_highs.append((i, close_prices[i]))
            # 가격 저점
            if close_prices[i] == min(close_prices[i-window:i+window+1]):
                price_lows.append((i, close_prices[i]))

            # MACD 고점
            if macd_values[i] == max(macd_values[i-window:i+window+1]):
                macd_highs.append((i, macd_values[i]))
            # MACD 저점
            if macd_values[i] == min(macd_values[i-window:i+window+1]):
                macd_lows.append((i, macd_values[i]))

        # Bullish Divergence 확인 (가격 lower low, MACD higher low)
        if len(price_lows) >= 2 and len(macd_lows) >= 2:
            recent_price_lows = sorted(price_lows, key=lambda x: x[0])[-2:]
            recent_macd_lows = sorted(macd_lows, key=lambda x: x[0])[-2:]

            price_low_1, price_low_2 = recent_price_lows[0][1], recent_price_lows[1][1]
            macd_low_1, macd_low_2 = recent_macd_lows[0][1], recent_macd_lows[1][1]

            # 가격은 하락했지만 MACD는 상승 (bullish divergence)
            if price_low_2 < price_low_1 and macd_low_2 > macd_low_1:
                price_change = ((price_low_2 - price_low_1) / price_low_1) * 100
                macd_change = macd_low_2 - macd_low_1

                # 강도 계산 (MACD 변화가 클수록, 가격 하락이 클수록 강함)
                macd_strength = min(abs(macd_change) / (abs(macd_low_1) + 0.0001), 1.0)
                price_strength = min(abs(price_change) / 5.0, 1.0)
                strength = (macd_strength + price_strength) / 2.0

                return {
                    'divergence_type': 'bullish',
                    'strength': float(strength),
                    'price_change': float(price_change),
                    'macd_change': float(macd_change),
                    'description': f'MACD 강세 다이버전스: 가격 {price_change:.2f}% 하락, MACD {macd_change:.4f} 상승'
                }

        # Bearish Divergence 확인 (가격 higher high, MACD lower high)
        if len(price_highs) >= 2 and len(macd_highs) >= 2:
            recent_price_highs = sorted(price_highs, key=lambda x: x[0])[-2:]
            recent_macd_highs = sorted(macd_highs, key=lambda x: x[0])[-2:]

            price_high_1, price_high_2 = recent_price_highs[0][1], recent_price_highs[1][1]
            macd_high_1, macd_high_2 = recent_macd_highs[0][1], recent_macd_highs[1][1]

            # 가격은 상승했지만 MACD는 하락 (bearish divergence)
            if price_high_2 > price_high_1 and macd_high_2 < macd_high_1:
                price_change = ((price_high_2 - price_high_1) / price_high_1) * 100
                macd_change = macd_high_2 - macd_high_1

                macd_strength = min(abs(macd_change) / (abs(macd_high_1) + 0.0001), 1.0)
                price_strength = min(abs(price_change) / 5.0, 1.0)
                strength = (macd_strength + price_strength) / 2.0

                return {
                    'divergence_type': 'bearish',
                    'strength': float(strength),
                    'price_change': float(price_change),
                    'macd_change': float(macd_change),
                    'description': f'MACD 약세 다이버전스: 가격 {price_change:.2f}% 상승, MACD {macd_change:.4f} 하락'
                }

        # 다이버전스 없음
        return {
            'divergence_type': 'none',
            'strength': 0.0,
            'price_change': 0.0,
            'macd_change': 0.0,
            'description': 'MACD 다이버전스 없음'
        }

    except Exception as e:
        return {
            'divergence_type': 'error',
            'strength': 0.0,
            'price_change': 0.0,
            'macd_change': 0.0,
            'description': f'MACD 다이버전스 감지 오류: {str(e)}'
        }

def calculate_chandelier_exit(df: pd.DataFrame, entry_price: float = None,
                             atr_period: int = 14, atr_multiplier: float = 3.0,
                             direction: str = 'LONG') -> Dict[str, Any]:
    """
    Chandelier Exit 계산 (트레일링 스톱-로스)

    기존 ATR 기반 고정 손절보다 우수한 트레일링 스톱 방식:
    - LONG: Stop = Highest High (since entry) - (ATR × multiplier)
    - SHORT: Stop = Lowest Low (since entry) + (ATR × multiplier)

    특징:
    - 가격이 상승하면 손절가도 따라 상승 (이익 보호)
    - 변동성에 따라 자동 조정
    - 급락 시 손절 회피 가능 (ATR 배수가 적절하면)

    Args:
        df: OHLCV 데이터프레임
        entry_price: 진입 가격 (None이면 현재가 기준으로 계산)
        atr_period: ATR 계산 기간 (기본 14)
        atr_multiplier: ATR 배수 (기본 3.0, 2.0보다 여유있음)
        direction: 'LONG' or 'SHORT'

    Returns:
        stop_price: 현재 손절가
        highest_high: 진입 후 최고가 (LONG의 경우)
        lowest_low: 진입 후 최저가 (SHORT의 경우)
        atr_value: 현재 ATR 값
        distance_percent: 현재가 대비 손절가 거리 (%)
        trailing_status: 'active', 'triggered', 'initial'
    """
    if len(df) < atr_period:
        return {
            'stop_price': 0.0,
            'highest_high': 0.0,
            'lowest_low': 0.0,
            'atr_value': 0.0,
            'distance_percent': 0.0,
            'trailing_status': 'initial',
            'description': '데이터 부족'
        }

    try:
        # ATR 계산
        if 'atr' not in df.columns:
            df['atr'] = calculate_atr(df, atr_period)

        current_atr = df['atr'].iloc[-1]
        current_price = df['close'].iloc[-1]

        # NaN 체크
        if pd.isna(current_atr) or pd.isna(current_price):
            return {
                'stop_price': 0.0,
                'highest_high': 0.0,
                'lowest_low': 0.0,
                'atr_value': 0.0,
                'distance_percent': 0.0,
                'trailing_status': 'initial',
                'description': 'ATR 또는 가격 데이터 없음'
            }

        # 진입가가 없으면 현재가 사용 (initial setup)
        if entry_price is None:
            entry_price = current_price

        if direction == 'LONG':
            # LONG 포지션: 진입 후 최고가 찾기
            # 실제 트레이딩에서는 진입 시점을 기록해야 함
            # 여기서는 최근 데이터에서 최고가 사용
            highest_high = df['high'].tail(atr_period * 2).max()  # 최근 기간의 최고가

            # Chandelier Exit 계산
            stop_price = highest_high - (current_atr * atr_multiplier)

            # 현재가 대비 거리
            distance_percent = ((current_price - stop_price) / current_price) * 100

            # 손절 트리거 여부
            trailing_status = 'triggered' if current_price <= stop_price else 'active'

            return {
                'stop_price': float(stop_price),
                'highest_high': float(highest_high),
                'lowest_low': 0.0,
                'atr_value': float(current_atr),
                'distance_percent': float(distance_percent),
                'trailing_status': trailing_status,
                'description': f'LONG Chandelier Exit: 손절가 {stop_price:,.0f} (최고가 {highest_high:,.0f} - {atr_multiplier}×ATR)'
            }

        else:  # SHORT
            # SHORT 포지션: 진입 후 최저가 찾기
            lowest_low = df['low'].tail(atr_period * 2).min()

            stop_price = lowest_low + (current_atr * atr_multiplier)
            distance_percent = ((stop_price - current_price) / current_price) * 100

            trailing_status = 'triggered' if current_price >= stop_price else 'active'

            return {
                'stop_price': float(stop_price),
                'highest_high': 0.0,
                'lowest_low': float(lowest_low),
                'atr_value': float(current_atr),
                'distance_percent': float(distance_percent),
                'trailing_status': trailing_status,
                'description': f'SHORT Chandelier Exit: 손절가 {stop_price:,.0f} (최저가 {lowest_low:,.0f} + {atr_multiplier}×ATR)'
            }

    except Exception as e:
        return {
            'stop_price': 0.0,
            'highest_high': 0.0,
            'lowest_low': 0.0,
            'atr_value': 0.0,
            'distance_percent': 0.0,
            'trailing_status': 'error',
            'description': f'Chandelier Exit 계산 오류: {str(e)}'
        }

def detect_bb_squeeze(df: pd.DataFrame, bb_period: int = 20, bb_std: float = 2.0,
                     squeeze_threshold: float = 0.8, lookback: int = 50) -> Dict[str, Any]:
    """
    볼린저 밴드 스퀴즈 감지 (Bollinger Band Squeeze Detection)

    스퀴즈 (Squeeze):
    - 볼린저 밴드 폭이 역사적 평균 대비 좁아진 상태
    - 변동성 수축 → 곧 변동성 확대 (브레이크아웃) 예상
    - 매매 기회 포착의 신호

    Args:
        df: OHLCV 데이터프레임
        bb_period: 볼린저 밴드 기간
        bb_std: 볼린저 밴드 표준편차 배수
        squeeze_threshold: 스퀴즈 판단 임계값 (0.8 = 평균의 80% 이하)
        lookback: 역사적 평균 계산 기간

    Returns:
        is_squeezing: 스퀴즈 상태 여부 (bool)
        squeeze_duration: 스퀴즈 지속 캔들 수
        bb_width_ratio: 현재 BB 폭 / 평균 BB 폭 비율
        breakout_direction: 브레이크아웃 방향 예측 ('up', 'down', 'neutral')
        potential_move: 예상 변동폭 (%)
        description: 설명
    """
    if len(df) < bb_period + lookback:
        return {
            'is_squeezing': False,
            'squeeze_duration': 0,
            'bb_width_ratio': 1.0,
            'breakout_direction': 'neutral',
            'potential_move': 0.0,
            'description': '데이터 부족'
        }

    try:
        # 볼린저 밴드 계산
        if 'bb_upper' not in df.columns or 'bb_lower' not in df.columns:
            upper_bb, middle_bb, lower_bb = calculate_bollinger_bands(df, bb_period, bb_std)
            df['bb_upper'] = upper_bb
            df['bb_middle'] = middle_bb
            df['bb_lower'] = lower_bb

        # BB 폭 계산 (상단 - 하단)
        df['bb_width'] = df['bb_upper'] - df['bb_lower']

        # 최근 lookback 기간의 평균 BB 폭
        avg_bb_width = df['bb_width'].tail(lookback).mean()
        current_bb_width = df['bb_width'].iloc[-1]

        # NaN 체크
        if pd.isna(avg_bb_width) or pd.isna(current_bb_width) or avg_bb_width == 0:
            return {
                'is_squeezing': False,
                'squeeze_duration': 0,
                'bb_width_ratio': 1.0,
                'breakout_direction': 'neutral',
                'potential_move': 0.0,
                'description': 'BB 폭 데이터 없음'
            }

        # BB 폭 비율 계산
        bb_width_ratio = current_bb_width / avg_bb_width

        # 스퀴즈 여부 판단 (현재 폭이 평균의 80% 이하)
        is_squeezing = bb_width_ratio < squeeze_threshold

        # 스퀴즈 지속 기간 계산
        squeeze_duration = 0
        if is_squeezing:
            for i in range(len(df) - 1, max(0, len(df) - 20), -1):
                width_at_i = df['bb_width'].iloc[i]
                avg_at_i = df['bb_width'].iloc[max(0, i-lookback):i].mean()
                if width_at_i < avg_at_i * squeeze_threshold:
                    squeeze_duration += 1
                else:
                    break

        # 브레이크아웃 방향 예측
        # 현재 가격이 BB 중심선 대비 어디에 있는지 확인
        current_price = df['close'].iloc[-1]
        bb_middle = df['bb_middle'].iloc[-1]

        # 최근 추세 확인 (단기 MA vs 장기 MA)
        if len(df) >= 20:
            recent_trend = df['close'].tail(10).mean() - df['close'].tail(20).mean()
            if current_price > bb_middle and recent_trend > 0:
                breakout_direction = 'up'
            elif current_price < bb_middle and recent_trend < 0:
                breakout_direction = 'down'
            else:
                breakout_direction = 'neutral'
        else:
            breakout_direction = 'neutral'

        # 예상 변동폭 (과거 평균 BB 폭을 기준으로)
        potential_move = (avg_bb_width / current_price) * 100 if current_price > 0 else 0.0

        description = '볼린저 밴드 스퀴즈 없음'
        if is_squeezing:
            description = f'볼린저 밴드 스퀴즈 감지 ({squeeze_duration}캔들 지속, 폭 비율 {bb_width_ratio:.2f})'
            if breakout_direction != 'neutral':
                description += f' - {breakout_direction.upper()} 브레이크아웃 가능성'

        return {
            'is_squeezing': bool(is_squeezing),
            'squeeze_duration': int(squeeze_duration),
            'bb_width_ratio': float(bb_width_ratio),
            'breakout_direction': breakout_direction,
            'potential_move': float(potential_move),
            'description': description
        }

    except Exception as e:
        return {
            'is_squeezing': False,
            'squeeze_duration': 0,
            'bb_width_ratio': 1.0,
            'breakout_direction': 'neutral',
            'potential_move': 0.0,
            'description': f'BB 스퀴즈 감지 오류: {str(e)}'
        }

def detect_market_regime(df: pd.DataFrame, atr_period: int = 14, adx_period: int = 14) -> Dict[str, Any]:
    """
    시장 국면 감지: 추세장 vs 횡보장

    Args:
        df: OHLCV 데이터프레임
        atr_period: ATR 계산 기간
        adx_period: ADX 계산 기간

    Returns:
        regime: 'trending', 'ranging', 'transitional'
        trend_strength: 0.0~1.0 (추세 강도)
        volatility_level: 'low', 'normal', 'high'
        recommendation: 'TREND_FOLLOW', 'MEAN_REVERSION', 'REDUCE_SIZE', 'WAIT'
    """
    # 1. ADX 계산 (추세 강도 측정)
    adx = calculate_adx(df, adx_period)
    current_adx = adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else 15

    # 2. ATR 퍼센트 계산 (변동성 측정)
    atr_pct = calculate_atr_percent(df, atr_period)
    current_atr_pct = atr_pct.iloc[-1] if not pd.isna(atr_pct.iloc[-1]) else 2.0
    avg_atr_pct = atr_pct.rolling(50).mean().iloc[-1] if len(atr_pct) >= 50 and not pd.isna(atr_pct.rolling(50).mean().iloc[-1]) else current_atr_pct

    # 3. 추세 vs 횡보 판단
    if current_adx > 25:
        regime = 'trending'
        trend_strength = min(current_adx / 50, 1.0)
    elif current_adx < 15:
        regime = 'ranging'
        trend_strength = 0.0
    else:
        regime = 'transitional'
        trend_strength = (current_adx - 15) / 10

    # 4. 변동성 수준 판단
    if current_atr_pct > avg_atr_pct * 1.5:
        volatility_level = 'high'
    elif current_atr_pct < avg_atr_pct * 0.7:
        volatility_level = 'low'
    else:
        volatility_level = 'normal'

    # 5. 거래 권장 사항
    if regime == 'trending' and volatility_level == 'normal':
        recommendation = 'TREND_FOLLOW'
        indicator_preference = ['macd', 'ma']  # 추세 지표 우선
    elif regime == 'ranging' and volatility_level == 'normal':
        recommendation = 'MEAN_REVERSION'
        indicator_preference = ['rsi', 'bb']  # 평균회귀 지표 우선
    elif volatility_level == 'high':
        recommendation = 'REDUCE_SIZE'
        indicator_preference = []
    else:
        recommendation = 'WAIT'
        indicator_preference = []

    return {
        'regime': regime,
        'trend_strength': trend_strength,
        'volatility_level': volatility_level,
        'current_adx': current_adx,
        'current_atr_pct': current_atr_pct,
        'avg_atr_pct': avg_atr_pct,
        'recommendation': recommendation,
        'indicator_preference': indicator_preference
    }

def calculate_position_size_by_atr(account_balance: float, risk_percent: float,
                                   entry_price: float, atr: float,
                                   atr_multiplier: float = 2.0) -> float:
    """
    ATR 기반 포지션 사이징

    Example:
        계좌 잔고: 1,000,000원
        위험률: 1% (10,000원까지 손실 가능)
        진입가: 50,000,000원
        ATR: 1,000,000원 (2%)
        ATR 배수: 2.0

        손절 거리 = 1,000,000 × 2.0 = 2,000,000원
        포지션 크기 = 10,000 / 2,000,000 = 0.005 BTC

    Args:
        account_balance: 계좌 잔고 (원)
        risk_percent: 위험 비율 (%)
        entry_price: 진입 가격
        atr: ATR 값
        atr_multiplier: ATR 배수 (손절 거리 계산용)

    Returns:
        포지션 크기 (코인 수량)
    """
    risk_amount = account_balance * (risk_percent / 100)
    stop_distance = atr * atr_multiplier

    # 손절 거리 대비 위험 금액으로 포지션 크기 계산
    if stop_distance > 0:
        position_size = risk_amount / stop_distance
    else:
        position_size = 0.0

    return position_size

def calculate_dynamic_stop_loss(entry_price: float, atr: float,
                               direction: str = 'LONG',
                               multiplier: float = 2.0) -> float:
    """
    ATR 기반 동적 손절가 계산

    Args:
        entry_price: 진입 가격
        atr: ATR 값
        direction: 'LONG' or 'SHORT'
        multiplier: ATR 배수 (2.0 = 정상 변동성의 2배에서 손절)

    Returns:
        stop_loss_price: 손절 가격
    """
    stop_distance = atr * multiplier

    if direction == 'LONG':
        stop_loss_price = entry_price - stop_distance
    else:  # SHORT
        stop_loss_price = entry_price + stop_distance

    return stop_loss_price

def calculate_exit_levels(entry_price: float, atr: float,
                         direction: str = 'LONG',
                         volatility_level: str = 'normal') -> Dict[str, float]:
    """
    진입가 기반 청산 레벨 계산 (다단계 익절/손절)

    Args:
        entry_price: 진입 가격
        atr: ATR 값
        direction: 'LONG' or 'SHORT'
        volatility_level: 'low', 'normal', 'high'

    Returns:
        stop_loss: 손절가
        take_profit_1: 1차 익절가 (50% 청산)
        take_profit_2: 2차 익절가 (나머지 청산)
        rr_ratio_1: 1차 익절 Risk:Reward 비율
        rr_ratio_2: 2차 익절 Risk:Reward 비율
    """
    # ATR 배수는 변동성에 따라 조정
    if volatility_level == 'high':
        stop_atr_mult = 2.5
        tp1_atr_mult = 3.0
        tp2_atr_mult = 5.0
    elif volatility_level == 'low':
        stop_atr_mult = 1.5
        tp1_atr_mult = 2.0
        tp2_atr_mult = 3.5
    else:  # normal
        stop_atr_mult = 2.0
        tp1_atr_mult = 2.5
        tp2_atr_mult = 4.0

    if direction == 'LONG':
        stop_loss = entry_price - (atr * stop_atr_mult)
        take_profit_1 = entry_price + (atr * tp1_atr_mult)
        take_profit_2 = entry_price + (atr * tp2_atr_mult)
    else:  # SHORT
        stop_loss = entry_price + (atr * stop_atr_mult)
        take_profit_1 = entry_price - (atr * tp1_atr_mult)
        take_profit_2 = entry_price - (atr * tp2_atr_mult)

    # Risk:Reward 비율 계산
    risk = abs(entry_price - stop_loss)
    reward_1 = abs(take_profit_1 - entry_price)
    reward_2 = abs(take_profit_2 - entry_price)

    rr_ratio_1 = reward_1 / risk if risk > 0 else 0
    rr_ratio_2 = reward_2 / risk if risk > 0 else 0

    return {
        'stop_loss': stop_loss,
        'take_profit_1': take_profit_1,
        'take_profit_2': take_profit_2,
        'risk_amount': risk,
        'reward_1': reward_1,
        'reward_2': reward_2,
        'rr_ratio_1': rr_ratio_1,
        'rr_ratio_2': rr_ratio_2
    }

class StrategyV1(VersionInterface):
    """
    Version 1: Elite 8-Indicator Trading Strategy

    Uses 8 technical indicators with weighted signal combination:
    MA, RSI, Bollinger Bands, Volume, MACD, ATR, Stochastic, ADX
    """

    # Version metadata (required by VersionInterface)
    VERSION_NAME = "ver1"
    VERSION_DISPLAY_NAME = "Elite 8-Indicator Strategy"
    VERSION_DESCRIPTION = "Advanced strategy using 8 technical indicators with weighted signal combination"
    VERSION_AUTHOR = "Trading Bot Team"
    VERSION_DATE = "2025-10"

    def __init__(self, config: Optional[Dict[str, Any]] = None, logger: TradingLogger = None, config_manager=None):
        # Call parent init
        super().__init__(config)

        self.logger = logger or TradingLogger()
        self.config_manager = config_manager

        # Merge configurations: common + version + override
        if config is None:
            # Use default version config
            version_config = get_version_config()
            self.strategy_config = version_config.get('INDICATOR_CONFIG', INDICATOR_CONFIG)
        elif 'INDICATOR_CONFIG' in config:
            # Config already structured
            self.strategy_config = config['INDICATOR_CONFIG']
        else:
            # Assume flat config structure (backward compatibility)
            self.strategy_config = config

    def get_current_config(self):
        """현재 설정 가져오기 (동적 설정 우선)"""
        if self.config_manager:
            return self.config_manager.get_config()
        return {
            'strategy': self.strategy_config,
            'trading': config.TRADING_CONFIG
        }

    def _get_indicator_config_for_interval(self, interval: str) -> Dict[str, int]:
        """
        캔들 간격에 맞는 지표 설정 반환
        :param interval: 캔들스틱 간격 ('1h', '6h', '12h', '24h')
        :return: 지표 설정 딕셔너리
        """
        # 간격별 프리셋이 있으면 사용
        presets = self.strategy_config.get('interval_presets', {})
        if interval in presets:
            return presets[interval]

        # 프리셋이 없으면 기본값 사용
        return {
            'short_ma_window': self.strategy_config['short_ma_window'],
            'long_ma_window': self.strategy_config['long_ma_window'],
            'rsi_period': self.strategy_config['rsi_period'],
            'analysis_period': self.strategy_config.get('analysis_period', 20)
        }

    def analyze_market_data(self, ticker: str, interval: str = None) -> Optional[Dict[str, Any]]:
        """
        시장 데이터 분석 (엘리트 전략: MACD, ATR, Stochastic, ADX 포함)
        :param ticker: 코인 티커 (예: 'BTC')
        :param interval: 캔들스틱 간격 ('30m', '1h', '6h', '12h', '24h'). None이면 config에서 가져옴
        """
        try:
            # interval이 지정되지 않으면 config에서 가져오기
            if interval is None:
                interval = self.strategy_config.get('candlestick_interval', '1h')

            # 간격에 맞는 지표 설정 적용
            indicator_config = self._get_indicator_config_for_interval(interval)

            # 가격 데이터 가져오기
            price_data = get_candlestick(ticker, interval)
            if price_data is None or len(price_data) < indicator_config['long_ma_window']:
                self.logger.log_error(f"데이터가 부족합니다: {ticker} (interval: {interval})")
                return None

            # 기본 기술적 지표 계산
            short_ma_window = indicator_config['short_ma_window']
            bb_period = indicator_config.get('bb_period', 20)

            # Calculate short MA
            price_data['short_ma'] = calculate_moving_average(
                price_data, short_ma_window
            )
            price_data['long_ma'] = calculate_moving_average(
                price_data, indicator_config['long_ma_window']
            )
            price_data['rsi'] = calculate_rsi(
                price_data, indicator_config.get('rsi_period', 14)
            )

            # Optimization: Reuse short_ma for BB middle band if same window
            if short_ma_window == bb_period:
                # Reuse already calculated short_ma as BB middle band
                bb_middle = price_data['short_ma']
                bb_std = price_data['close'].rolling(window=bb_period).std()
                num_std = indicator_config.get('bb_std', 2.0)
                price_data['bb_upper'] = bb_middle + (bb_std * num_std)
                price_data['bb_middle'] = bb_middle
                price_data['bb_lower'] = bb_middle - (bb_std * num_std)
            else:
                # Different windows, calculate separately
                upper_bb, middle_bb, lower_bb = calculate_bollinger_bands(
                    price_data,
                    window=bb_period,
                    num_std=indicator_config.get('bb_std', 2.0)
                )
                price_data['bb_upper'] = upper_bb
                price_data['bb_middle'] = middle_bb
                price_data['bb_lower'] = lower_bb

            price_data['volume_ratio'] = calculate_volume_ratio(
                price_data,
                window=indicator_config.get('volume_window', 10)
            )

            # 엘리트 지표 계산
            macd_line, signal_line, histogram = calculate_macd(
                price_data,
                fast=indicator_config.get('macd_fast', 8),
                slow=indicator_config.get('macd_slow', 17),
                signal=indicator_config.get('macd_signal', 9)
            )
            price_data['macd_line'] = macd_line
            price_data['macd_signal'] = signal_line
            price_data['macd_histogram'] = histogram

            price_data['atr'] = calculate_atr(
                price_data,
                period=indicator_config.get('atr_period', 14)
            )
            price_data['atr_percent'] = calculate_atr_percent(
                price_data,
                period=indicator_config.get('atr_period', 14)
            )

            stoch_k, stoch_d = calculate_stochastic(
                price_data,
                k_period=indicator_config.get('stoch_k_period', 14),
                d_period=indicator_config.get('stoch_d_period', 3)
            )
            price_data['stoch_k'] = stoch_k
            price_data['stoch_d'] = stoch_d

            price_data['adx'] = calculate_adx(
                price_data,
                period=indicator_config.get('adx_period', 14)
            )

            # 시장 국면 감지
            regime = detect_market_regime(
                price_data,
                atr_period=indicator_config.get('atr_period', 14),
                adx_period=indicator_config.get('adx_period', 14)
            )

            # 엘리트 전략 확장: 촛대 패턴 감지
            candlestick_pattern = detect_candlestick_patterns(price_data)

            # 엘리트 전략 확장: RSI 다이버전스 감지
            rsi_divergence = detect_rsi_divergence(
                price_data,
                lookback=indicator_config.get('divergence_lookback', 30),
                rsi_period=indicator_config.get('rsi_period', 14)
            )

            # 엘리트 전략 확장: MACD 다이버전스 감지
            macd_divergence = detect_macd_divergence(
                price_data,
                lookback=indicator_config.get('divergence_lookback', 30),
                macd_fast=indicator_config.get('macd_fast', 8),
                macd_slow=indicator_config.get('macd_slow', 17),
                macd_signal=indicator_config.get('macd_signal', 9)
            )

            # 엘리트 전략 확장: Chandelier Exit (트레일링 스톱)
            chandelier_exit = calculate_chandelier_exit(
                price_data,
                entry_price=None,  # None이면 현재가 기준
                atr_period=indicator_config.get('atr_period', 14),
                atr_multiplier=indicator_config.get('chandelier_atr_multiplier', 3.0),
                direction='LONG'
            )

            # 엘리트 전략 확장: BB 스퀴즈 감지
            bb_squeeze = detect_bb_squeeze(
                price_data,
                bb_period=indicator_config.get('bb_period', 20),
                bb_std=indicator_config.get('bb_std', 2.0),
                squeeze_threshold=indicator_config.get('bb_squeeze_threshold', 0.8),
                lookback=50
            )

            # 현재 가격 정보
            current_price = price_data['close'].iloc[-1]
            current_volume = price_data['volume'].iloc[-1]

            # 분석 결과
            analysis = {
                'ticker': ticker,
                'interval': interval,
                'timestamp': datetime.now().isoformat(),
                'current_price': current_price,
                'current_volume': current_volume,

                # 기본 지표
                'short_ma': price_data['short_ma'].iloc[-1],
                'long_ma': price_data['long_ma'].iloc[-1],
                'rsi': price_data['rsi'].iloc[-1],
                'bb_position': (current_price - price_data['bb_lower'].iloc[-1]) /
                              (price_data['bb_upper'].iloc[-1] - price_data['bb_lower'].iloc[-1])
                              if (price_data['bb_upper'].iloc[-1] - price_data['bb_lower'].iloc[-1]) > 0 else 0.5,
                'bb_upper': price_data['bb_upper'].iloc[-1],
                'bb_middle': price_data['bb_middle'].iloc[-1],
                'bb_lower': price_data['bb_lower'].iloc[-1],
                'volume_ratio': price_data['volume_ratio'].iloc[-1],

                # 엘리트 지표
                'macd_line': price_data['macd_line'].iloc[-1] if not pd.isna(price_data['macd_line'].iloc[-1]) else 0,
                'macd_signal': price_data['macd_signal'].iloc[-1] if not pd.isna(price_data['macd_signal'].iloc[-1]) else 0,
                'macd_histogram': price_data['macd_histogram'].iloc[-1] if not pd.isna(price_data['macd_histogram'].iloc[-1]) else 0,
                'atr': price_data['atr'].iloc[-1] if not pd.isna(price_data['atr'].iloc[-1]) else 0,
                'atr_percent': price_data['atr_percent'].iloc[-1] if not pd.isna(price_data['atr_percent'].iloc[-1]) else 0,
                'stoch_k': price_data['stoch_k'].iloc[-1] if not pd.isna(price_data['stoch_k'].iloc[-1]) else 50,
                'stoch_d': price_data['stoch_d'].iloc[-1] if not pd.isna(price_data['stoch_d'].iloc[-1]) else 50,
                'adx': price_data['adx'].iloc[-1] if not pd.isna(price_data['adx'].iloc[-1]) else 15,

                # 시장 국면
                'regime': regime,

                # 엘리트 전략 확장: 촛대 패턴
                'candlestick_pattern': candlestick_pattern,

                # 엘리트 전략 확장: RSI 다이버전스
                'rsi_divergence': rsi_divergence,

                # 엘리트 전략 확장: MACD 다이버전스
                'macd_divergence': macd_divergence,

                # 엘리트 전략 확장: Chandelier Exit
                'chandelier_exit': chandelier_exit,

                # 엘리트 전략 확장: BB 스퀴즈
                'bb_squeeze': bb_squeeze,

                # 가격 변화
                'price_change_24h': ((current_price - price_data['close'].iloc[-24]) /
                                   price_data['close'].iloc[-24]) * 100 if len(price_data) >= 24 else 0,

                # 사용된 지표 설정 정보
                'indicator_config': indicator_config,

                # 원본 데이터 (고급 분석용)
                'price_data': price_data
            }

            return analysis

        except Exception as e:
            self.logger.log_error(f"시장 데이터 분석 오류: {ticker}", e)
            return None

    def generate_signals(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        거래 신호 생성 (동적 설정 적용 및 선택된 지표만 사용)
        """
        current_config = self.get_current_config()
        strategy_config = current_config.get('strategy', self.strategy_config)

        # 활성화된 지표 가져오기 (기본값: 모두 활성화)
        enabled_indicators = strategy_config.get('enabled_indicators', {
            'ma': True,
            'rsi': True,
            'bb': True,
            'volume': True
        })

        signals = {
            'ma_signal': 0,     # -1: 매도, 0: 중립, 1: 매수
            'rsi_signal': 0,
            'bb_signal': 0,
            'volume_signal': 0,
            'overall_signal': 0,
            'confidence': 0.0
        }

        # 이동평균 신호 (활성화된 경우에만)
        if enabled_indicators.get('ma', True):
            if analysis['short_ma'] > analysis['long_ma']:
                signals['ma_signal'] = 1
            elif analysis['short_ma'] < analysis['long_ma']:
                signals['ma_signal'] = -1

        # RSI 신호 (활성화된 경우에만, 동적 임계값 사용)
        if enabled_indicators.get('rsi', True):
            rsi = analysis['rsi']
            rsi_buy_threshold = strategy_config.get('rsi_buy_threshold', 30)
            rsi_sell_threshold = strategy_config.get('rsi_sell_threshold', 70)

            if rsi <= rsi_buy_threshold:
                signals['rsi_signal'] = 1  # 과매도 -> 매수
            elif rsi >= rsi_sell_threshold:
                signals['rsi_signal'] = -1  # 과매수 -> 매도

        # 볼린저 밴드 신호 (활성화된 경우에만)
        if enabled_indicators.get('bb', True):
            bb_pos = analysis['bb_position']
            if bb_pos < 0.2:  # 하단 근처
                signals['bb_signal'] = 1
            elif bb_pos > 0.8:  # 상단 근처
                signals['bb_signal'] = -1

        # 거래량 신호 (활성화된 경우에만)
        if enabled_indicators.get('volume', True):
            if analysis['volume_ratio'] > self.strategy_config['volume_threshold']:
                signals['volume_signal'] = 1

        # 종합 신호 계산 (활성화된 지표만 합산)
        signal_sum = (signals['ma_signal'] + signals['rsi_signal'] +
                     signals['bb_signal'] + signals['volume_signal'])

        # 활성화된 지표 개수 계산
        enabled_count = sum(1 for key, value in enabled_indicators.items() if value)

        # 최소 활성화 지표 개수 확인 (안전장치)
        if enabled_count < 2:
            self.logger.logger.warning("경고: 활성화된 지표가 2개 미만입니다. 최소 2개 이상의 지표를 선택하세요.")
            signals['overall_signal'] = 0  # 관망
            signals['confidence'] = 0.0
            return signals

        # 신뢰도 계산 시 활성화된 지표 개수 기준으로 계산
        if signal_sum >= 2:
            signals['overall_signal'] = 1  # 매수
            signals['confidence'] = min(abs(signal_sum) / enabled_count, 1.0)
        elif signal_sum <= -2:
            signals['overall_signal'] = -1  # 매도
            signals['confidence'] = min(abs(signal_sum) / enabled_count, 1.0)
        else:
            signals['overall_signal'] = 0  # 관망
            signals['confidence'] = 0.3

        return signals

    def generate_weighted_signals(self, analysis: Dict[str, Any],
                                  weights_override: Dict[str, float] = None) -> Dict[str, Any]:
        """
        가중치 기반 신호 생성 (엘리트 전략: 1시간봉 최적화)

        신호 강도: -1.0 (강한 매도) ~ +1.0 (강한 매수)

        Args:
            analysis: analyze_market_data()의 결과
            weights_override: 가중치 덮어쓰기 (시장 국면별로 다른 가중치 적용 가능)

        Returns:
            신호 딕셔너리 (각 지표별 신호 + 종합 신호 + 신뢰도)
        """
        current_config = self.get_current_config()
        strategy_config = current_config.get('strategy', self.strategy_config)

        # 기본 신호 가중치 (합계 = 1.0)
        default_weights = strategy_config.get('signal_weights', {
            'macd': 0.35,      # 추세 신호에 가장 높은 가중치
            'ma': 0.25,        # 추세 확인
            'rsi': 0.20,       # 과매수/과매도 필터
            'bb': 0.10,        # 평균회귀 신호
            'volume': 0.10     # 거래량 확인
        })

        # 가중치 덮어쓰기 (시장 국면별 조정)
        weights = weights_override if weights_override else default_weights

        signals = {}

        # 1. MA 신호 (강도 포함)
        ma_diff = analysis['short_ma'] - analysis['long_ma']
        ma_diff_percent = (ma_diff / analysis['long_ma']) * 100 if analysis['long_ma'] > 0 else 0

        # 0.5% 이상 차이나면 명확한 신호
        ma_signal = np.clip(ma_diff_percent / 0.5, -1.0, 1.0)
        signals['ma_signal'] = ma_signal
        signals['ma_strength'] = abs(ma_signal)

        # 2. RSI 신호 (비선형 스케일링)
        rsi = analysis['rsi']

        if rsi <= 30:
            # 과매도: RSI가 낮을수록 강한 매수 신호
            rsi_signal = np.clip((30 - rsi) / 15, 0, 1.0)  # RSI 15에서 최대값
        elif rsi >= 70:
            # 과매수: RSI가 높을수록 강한 매도 신호
            rsi_signal = -np.clip((rsi - 70) / 15, 0, 1.0)  # RSI 85에서 최대값
        else:
            # 중립 구간: 50에서 멀어질수록 약한 신호
            rsi_signal = (50 - rsi) / 20  # 약한 신호

        signals['rsi_signal'] = rsi_signal
        signals['rsi_strength'] = abs(rsi_signal)

        # 3. MACD 신호 (크로스오버 + 히스토그램 강도)
        macd_line = analysis.get('macd_line', 0)
        macd_signal_line = analysis.get('macd_signal', 0)
        macd_histogram = analysis.get('macd_histogram', 0)

        # MACD 신호 생성
        if macd_line > macd_signal_line:
            # 골든 크로스 (매수 신호)
            macd_strength = min(abs(macd_histogram) / (abs(macd_line) + 0.0001), 1.0)
            macd_signal = macd_strength
        elif macd_line < macd_signal_line:
            # 데드 크로스 (매도 신호)
            macd_strength = min(abs(macd_histogram) / (abs(macd_line) + 0.0001), 1.0)
            macd_signal = -macd_strength
        else:
            macd_signal = 0
            macd_strength = 0

        signals['macd_signal'] = macd_signal
        signals['macd_strength'] = abs(macd_signal)
        signals['macd_histogram'] = macd_histogram

        # 4. Bollinger Bands 신호
        bb_pos = analysis['bb_position']

        if bb_pos < 0.2:
            # 하단 근처: 강도는 0에 가까울수록 강함
            bb_signal = (0.2 - bb_pos) / 0.2  # 0~1.0
        elif bb_pos > 0.8:
            # 상단 근처: 강도는 1에 가까울수록 강함
            bb_signal = -((bb_pos - 0.8) / 0.2)  # -1.0~0
        else:
            # 중간 구간: 약한 신호
            bb_signal = (0.5 - bb_pos) / 0.3

        signals['bb_signal'] = np.clip(bb_signal, -1.0, 1.0)
        signals['bb_strength'] = abs(signals['bb_signal'])

        # 5. Volume 신호
        vol_ratio = analysis['volume_ratio']

        if vol_ratio > 1.5:
            # 높은 거래량: 다른 신호를 강화
            volume_signal = min((vol_ratio - 1.0) / 2.0, 1.0)
        elif vol_ratio > 1.0:
            # 정상 거래량
            volume_signal = 0.2
        else:
            # 낮은 거래량: 신뢰도 감소
            volume_signal = -0.3

        signals['volume_signal'] = np.clip(volume_signal, -1.0, 1.0)
        signals['volume_strength'] = abs(volume_signal)

        # 6. Stochastic 신호 (추가 확인용)
        stoch_k = analysis.get('stoch_k', 50)
        stoch_d = analysis.get('stoch_d', 50)

        if stoch_k < 20 and stoch_d < 20:
            # 과매도
            stoch_signal = 0.7
        elif stoch_k > 80 and stoch_d > 80:
            # 과매수
            stoch_signal = -0.7
        elif stoch_k > stoch_d:
            # 상승 모멘텀
            stoch_signal = 0.3
        else:
            # 하락 모멘텀
            stoch_signal = -0.3

        signals['stoch_signal'] = stoch_signal
        signals['stoch_strength'] = abs(stoch_signal)

        # 7. 엘리트 확장: 촛대 패턴 신호
        candlestick = analysis.get('candlestick_pattern', {})
        pattern_signal = candlestick.get('pattern_score', 0.0)
        pattern_confidence = candlestick.get('pattern_confidence', 0.0)

        signals['pattern_signal'] = pattern_signal
        signals['pattern_strength'] = abs(pattern_signal) * pattern_confidence  # 신뢰도로 가중
        signals['pattern_type'] = candlestick.get('pattern_type', 'none')

        # 8. 엘리트 확장: 다이버전스 보너스 (신뢰도 향상 효과)
        rsi_div = analysis.get('rsi_divergence', {})
        macd_div = analysis.get('macd_divergence', {})

        # 다이버전스 신호 통합 (강도 평균)
        divergence_signal = 0.0
        divergence_bonus = 0.0

        if rsi_div.get('divergence_type') == 'bullish':
            divergence_signal += rsi_div.get('strength', 0.0)
            divergence_bonus += 0.15  # 신뢰도 보너스
        elif rsi_div.get('divergence_type') == 'bearish':
            divergence_signal -= rsi_div.get('strength', 0.0)
            divergence_bonus += 0.15

        if macd_div.get('divergence_type') == 'bullish':
            divergence_signal += macd_div.get('strength', 0.0)
            divergence_bonus += 0.20  # MACD 다이버전스는 더 강력
        elif macd_div.get('divergence_type') == 'bearish':
            divergence_signal -= macd_div.get('strength', 0.0)
            divergence_bonus += 0.20

        signals['divergence_signal'] = np.clip(divergence_signal, -1.0, 1.0)
        signals['divergence_bonus'] = min(divergence_bonus, 0.25)  # 최대 25% 보너스
        signals['rsi_divergence_type'] = rsi_div.get('divergence_type', 'none')
        signals['macd_divergence_type'] = macd_div.get('divergence_type', 'none')

        # 9. BB 스퀴즈 정보 (거래 타이밍 참고용)
        bb_squeeze = analysis.get('bb_squeeze', {})
        signals['is_squeezing'] = bb_squeeze.get('is_squeezing', False)
        signals['breakout_direction'] = bb_squeeze.get('breakout_direction', 'neutral')

        # 10. 최종 가중 합산 (패턴 가중치 추가)
        overall_signal = (
            weights.get('ma', 0.25) * signals['ma_signal'] +
            weights.get('rsi', 0.20) * signals['rsi_signal'] +
            weights.get('macd', 0.35) * signals['macd_signal'] +
            weights.get('bb', 0.10) * signals['bb_signal'] +
            weights.get('volume', 0.10) * signals['volume_signal'] +
            weights.get('pattern', 0.0) * signals['pattern_signal']  # 패턴 가중치 (기본 0, config에서 설정 가능)
        )

        # 다이버전스 신호 추가 (별도 가중치 또는 보너스로 적용)
        # 다이버전스는 신호 자체보다는 다른 신호의 신뢰도를 높이는 역할
        if abs(signals['divergence_signal']) > 0.3:
            overall_signal += signals['divergence_signal'] * 0.1  # 10% 가중치로 추가

        signals['overall_signal'] = overall_signal

        # 11. 신뢰도 계산 (각 신호의 강도 기반 + 다이버전스 보너스)
        avg_strength = (
            weights.get('ma', 0.25) * signals['ma_strength'] +
            weights.get('rsi', 0.20) * signals['rsi_strength'] +
            weights.get('macd', 0.35) * signals['macd_strength'] +
            weights.get('bb', 0.10) * signals['bb_strength'] +
            weights.get('volume', 0.10) * signals['volume_strength'] +
            weights.get('pattern', 0.0) * signals['pattern_strength']  # 패턴 강도 추가
        )

        # 다이버전스 보너스 적용 (최대 신뢰도 1.0 제한)
        confidence_with_bonus = min(avg_strength + signals['divergence_bonus'], 1.0)

        signals['confidence'] = confidence_with_bonus
        signals['base_confidence'] = avg_strength  # 보너스 적용 전 기본 신뢰도

        # 12. 시장 국면 정보 포함
        regime = analysis.get('regime', {})
        signals['regime'] = regime.get('regime', 'unknown')
        signals['volatility_level'] = regime.get('volatility_level', 'normal')
        signals['trend_strength'] = regime.get('trend_strength', 0.0)

        # 13. 최종 판단 (1시간봉 특성상 높은 임계값 사용)
        confidence_threshold = strategy_config.get('confidence_threshold', 0.6)
        signal_threshold = strategy_config.get('signal_threshold', 0.5)

        if overall_signal >= signal_threshold and confidence_with_bonus >= confidence_threshold:
            signals['final_action'] = 'BUY'
        elif overall_signal <= -signal_threshold and confidence_with_bonus >= confidence_threshold:
            signals['final_action'] = 'SELL'
        else:
            signals['final_action'] = 'HOLD'

        # 14. 상세 설명 (패턴과 다이버전스 정보 포함)
        signals['reason'] = self._generate_signal_reason(signals, analysis)

        return signals

    def _generate_signal_reason(self, signals: Dict[str, Any], analysis: Dict[str, Any]) -> str:
        """신호에 대한 상세 설명 생성"""
        action = signals['final_action']
        confidence = signals['confidence']

        if action == 'HOLD':
            return f"관망 (신호강도: {signals['overall_signal']:+.2f}, 신뢰도: {confidence:.2f})"

        # 강한 신호 찾기
        strong_signals = []
        if abs(signals['macd_signal']) > 0.5:
            strong_signals.append(f"MACD({signals['macd_signal']:+.2f})")
        if abs(signals['rsi_signal']) > 0.5:
            strong_signals.append(f"RSI({signals['rsi_signal']:+.2f})")
        if abs(signals['ma_signal']) > 0.5:
            strong_signals.append(f"MA({signals['ma_signal']:+.2f})")

        signal_str = ", ".join(strong_signals) if strong_signals else "종합신호"

        return f"{action} 신호 - {signal_str} | 신뢰도: {confidence:.2f} | 국면: {signals['regime']}"

    def decide_action(self, ticker: str) -> Tuple[str, Dict[str, Any]]:
        """
        종합적 분석을 통한 매매 결정
        """
        # 시장 데이터 분석
        analysis = self.analyze_market_data(ticker)
        if not analysis:
            return "HOLD", {}

        # 신호 생성
        signals = self.generate_signals(analysis)

        # 결정 로직
        action = "HOLD"
        reason = "추세 유지"

        if signals['overall_signal'] == 1 and signals['confidence'] > 0.6:
            action = "BUY"
            reason = f"매수 신호 감지 (신뢰도: {signals['confidence']:.2f})"
        elif signals['overall_signal'] == -1 and signals['confidence'] > 0.6:
            action = "SELL"
            reason = f"매도 신호 감지 (신뢰도: {signals['confidence']:.2f})"

        # 로깅
        self.logger.log_strategy_analysis(ticker, {
            'analysis': analysis,
            'signals': signals,
            'action': action,
            'reason': reason
        })

        self.logger.log_trade_decision(ticker, action, reason, analysis)

        return action, {'analysis': analysis, 'signals': signals, 'reason': reason}

    def check_stop_loss_take_profit(self, ticker: str, current_price: float,
                                   holdings: float, avg_buy_price: float) -> Tuple[str, str]:
        """
        손절/익절 조건 확인

        Args:
            ticker: 거래 코인
            current_price: 현재 가격
            holdings: 보유 수량
            avg_buy_price: 평균 매수가

        Returns:
            Tuple[action, reason]: 거래 액션과 이유
        """
        if holdings <= 0 or avg_buy_price <= 0:
            return "HOLD", "보유 물량 없음"

        current_config = self.get_current_config()
        trading_config = current_config.get('trading', {})

        stop_loss_percent = trading_config.get('stop_loss_percent', 5.0)
        take_profit_percent = trading_config.get('take_profit_percent', 3.0)

        # 수익률 계산
        profit_percent = ((current_price - avg_buy_price) / avg_buy_price) * 100

        # 손절 조건 확인
        if profit_percent <= -stop_loss_percent:
            reason = f"손절 실행: {profit_percent:.2f}% 손실 (기준: -{stop_loss_percent}%)"
            self.logger.logger.warning(f"[{ticker}] {reason}")
            return "SELL", reason

        # 익절 조건 확인
        if profit_percent >= take_profit_percent:
            reason = f"익절 실행: {profit_percent:.2f}% 수익 (기준: +{take_profit_percent}%)"
            self.logger.logger.info(f"[{ticker}] {reason}")
            return "SELL", reason

        return "HOLD", f"현재 수익률: {profit_percent:.2f}% (손절: -{stop_loss_percent}%, 익절: +{take_profit_percent}%)"

    def enhanced_decide_action(self, ticker: str, holdings: float = 0,
                             avg_buy_price: float = 0, interval: str = None) -> Tuple[str, Dict[str, Any]]:
        """
        향상된 거래 결정 (손절/익절 포함)
        :param ticker: 코인 티커
        :param holdings: 보유 수량
        :param avg_buy_price: 평균 매수가
        :param interval: 캔들스틱 간격 (None이면 config에서 가져옴)
        """
        # 1. 시장 분석 (지정된 간격으로)
        analysis = self.analyze_market_data(ticker, interval)
        if analysis is None:
            return "HOLD", {"reason": "시장 데이터 분석 실패"}

        current_price = analysis['current_price']

        # 2. 손절/익절 우선 확인
        if holdings > 0 and avg_buy_price > 0:
            stop_action, stop_reason = self.check_stop_loss_take_profit(
                ticker, current_price, holdings, avg_buy_price
            )
            if stop_action == "SELL":
                return stop_action, {"reason": stop_reason, "analysis": analysis}

        # 3. 일반 전략 신호 확인
        signals = self.generate_signals(analysis)

        # 4. 최종 결정
        confidence_threshold = 0.6

        if signals['overall_signal'] >= 2 and signals['confidence'] >= confidence_threshold:
            action = "BUY"
            reason = f"매수 신호 감지 (신뢰도: {signals['confidence']:.2f}, RSI: {analysis['rsi']:.1f})"
        elif signals['overall_signal'] <= -2 and signals['confidence'] >= confidence_threshold:
            action = "SELL"
            reason = f"매도 신호 감지 (신뢰도: {signals['confidence']:.2f}, RSI: {analysis['rsi']:.1f})"
        else:
            action = "HOLD"
            reason = f"관망 (신호: {signals['overall_signal']}, 신뢰도: {signals['confidence']:.2f})"

        # 로깅
        self.logger.log_trade_decision(ticker, action, reason, analysis)

        return action, {'analysis': analysis, 'signals': signals, 'reason': reason}

    # ========================================
    # VersionInterface Required Methods
    # ========================================

    def analyze_market(self, symbol: str, interval: str = "1h") -> Dict[str, Any]:
        """
        Analyze market data and generate trading signals (VersionInterface implementation).

        Args:
            symbol: Trading pair symbol (e.g., "BTC", "ETH")
            interval: Candlestick interval (e.g., "1h", "30m", "24h")

        Returns:
            Dictionary containing:
                - signal: Trading signal (gradual value from -1.0 to +1.0)
                - confidence: Signal confidence (0.0 to 1.0)
                - analysis: Detailed analysis results
                - indicators: Calculated technical indicators
                - price_data: Market price data (DataFrame)
        """
        analysis_result = self.analyze_market_data(symbol, interval)

        if analysis_result is None:
            return {
                'signal': 0.0,
                'confidence': 0.0,
                'analysis': {},
                'indicators': {},
                'price_data': None,
                'error': 'Failed to analyze market data'
            }

        # Generate signals using the weighted system
        signals = self.generate_weighted_signals(analysis_result)

        return {
            'signal': signals['weighted_signal'],
            'confidence': signals['confidence'],
            'analysis': analysis_result,
            'indicators': {
                'ma': {'short': analysis_result.get('short_ma'), 'long': analysis_result.get('long_ma')},
                'rsi': analysis_result.get('rsi'),
                'macd': {
                    'line': analysis_result.get('macd_line'),
                    'signal': analysis_result.get('macd_signal'),
                    'histogram': analysis_result.get('macd_histogram')
                },
                'bollinger': {
                    'upper': analysis_result.get('bb_upper'),
                    'middle': analysis_result.get('bb_middle'),
                    'lower': analysis_result.get('bb_lower')
                },
                'atr': analysis_result.get('atr'),
                'stochastic': {
                    'k': analysis_result.get('stoch_k'),
                    'd': analysis_result.get('stoch_d')
                },
                'adx': analysis_result.get('adx'),
                'volume_ratio': analysis_result.get('volume_ratio')
            },
            'price_data': analysis_result.get('price_data'),
            'regime': analysis_result.get('regime', 'Unknown')
        }

    def get_strategy_description(self) -> str:
        """Get human-readable description of the strategy."""
        return (
            "Elite 8-Indicator Strategy v1.0\n\n"
            "This advanced trading strategy combines 8 technical indicators with a weighted signal system:\n\n"
            "Core Indicators:\n"
            "  - Moving Averages (MA): Trend identification\n"
            "  - RSI: Overbought/oversold conditions\n"
            "  - Bollinger Bands: Volatility and mean reversion\n"
            "  - Volume: Confirmation of price movements\n\n"
            "Elite Indicators:\n"
            "  - MACD: Momentum and trend convergence/divergence\n"
            "  - ATR: Volatility measurement for dynamic stop-loss\n"
            "  - Stochastic: Price momentum oscillator\n"
            "  - ADX: Trend strength measurement\n\n"
            "Features:\n"
            "  - Market regime detection (Trending/Ranging/Transitional)\n"
            "  - Weighted signal combination (MACD 35%, MA 25%, RSI 20%, BB 10%, Volume 10%)\n"
            "  - ATR-based risk management with dynamic position sizing\n"
            "  - Candlestick pattern recognition (optional)\n"
            "  - Divergence detection between price and indicators\n"
            "  - Bollinger Band squeeze detection for volatility breakouts\n\n"
            "Optimized for multiple timeframes: 30m, 1h, 6h, 12h, 24h"
        )

    def get_version_info(self) -> Dict[str, str]:
        """Get version metadata information."""
        return {
            'name': self.VERSION_NAME,
            'display_name': self.VERSION_DISPLAY_NAME,
            'description': self.VERSION_DESCRIPTION,
            'author': self.VERSION_AUTHOR,
            'date': self.VERSION_DATE,
        }

    def get_supported_intervals(self) -> List[str]:
        """Get list of supported candlestick intervals."""
        return list(INTERVAL_PRESETS.keys())

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate configuration parameters.

        Args:
            config: Configuration dictionary to validate

        Returns:
            True if configuration is valid, False otherwise
        """
        # Check if required config sections exist
        if 'INDICATOR_CONFIG' in config:
            indicator_cfg = config['INDICATOR_CONFIG']

            # Validate indicator periods are positive integers
            required_int_params = [
                'short_ma_window', 'long_ma_window', 'rsi_period',
                'bb_period', 'macd_fast', 'macd_slow', 'macd_signal',
                'atr_period', 'stoch_k_period', 'stoch_d_period', 'adx_period'
            ]

            for param in required_int_params:
                if param in indicator_cfg:
                    value = indicator_cfg[param]
                    if not isinstance(value, int) or value <= 0:
                        self.logger.log_error(f"Invalid {param}: {value} (must be positive integer)")
                        return False

        # Validate signal weights if present
        if 'SIGNAL_WEIGHTS' in config:
            weights = config['SIGNAL_WEIGHTS']
            total = sum(weights.values())
            if not (0.9 <= total <= 1.1):
                self.logger.log_error(f"Signal weights sum to {total:.2f}, expected ~1.0")
                return False

        return True

    def get_indicator_list(self) -> List[str]:
        """Get list of technical indicators used by this version."""
        return ['MA', 'RSI', 'Bollinger Bands', 'Volume', 'MACD', 'ATR', 'Stochastic', 'ADX']

    def get_risk_parameters(self) -> Dict[str, Any]:
        """Get risk management parameters."""
        return RISK_CONFIG.copy()

    # VersionInterface required methods
    def get_config(self) -> Dict[str, Any]:
        """Return complete configuration"""
        return self.get_current_config()

    def get_indicator_names(self) -> List[str]:
        """Return list of indicators used"""
        return ['MA', 'RSI', 'Bollinger Bands', 'Volume', 'MACD', 'ATR', 'Stochastic', 'ADX']

    def get_supported_intervals(self) -> List[str]:
        """Return supported candlestick intervals"""
        return ['30m', '1h', '6h', '12h', '24h']

    def validate_configuration(self) -> Tuple[bool, List[str]]:
        """Validate configuration"""
        errors = []
        if not self.strategy_config:
            errors.append("Strategy config is missing")
        return (len(errors) == 0, errors)

    def get_chart_config(self) -> Dict[str, Any]:
        """Return chart display configuration"""
        return {
            'indicators': ['MA', 'RSI', 'BB', 'Volume', 'MACD', 'Stochastic', 'ATR', 'ADX'],
            'overlays': ['MA', 'BB'],
            'subplots': ['RSI', 'MACD', 'Volume'],
            'colors': {
                'MA_short': '#FF8C00',
                'MA_long': '#9370DB',
                'BB_upper': '#808080',
                'BB_lower': '#808080',
                'RSI': '#00CED1',
                'MACD_line': '#1E90FF',
                'MACD_signal': '#FF6347',
                'Volume_up': '#00FF00',
                'Volume_down': '#FF0000',
            },
            'default_visible': [],
        }


# Backward compatibility: Keep TradingStrategy as alias
TradingStrategy = StrategyV1


def decide_action(ticker: str, short_window: int = None, long_window: int = None) -> str:
    """
    기존 인터페이스 유지를 위한 래퍼 함수
    """
    strategy = TradingStrategy()
    action, _ = strategy.decide_action(ticker)
    return action


if __name__ == "__main__":
    strategy = TradingStrategy()
    action, details = strategy.decide_action("BTC")
    print(f"최종 결정: {action}")
    if details:
        print(f"이유: {details['reason']}")
        print(f"분석 데이터: {details['analysis']}")
        print(f"신호: {details['signals']}")