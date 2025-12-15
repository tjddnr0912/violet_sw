"""
매매 전략 테스트 모듈
"""

import pytest
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.indicators import (
    TechnicalIndicators,
    MACDResult,
    BollingerBands,
    StochasticResult,
    calculate_indicators
)
from src.strategy.base import (
    Signal,
    Position,
    TradeSignal,
    StrategyConfig,
    BaseStrategy,
    StrategyManager
)
from src.strategy.strategies import (
    MACrossoverStrategy,
    RSIStrategy,
    MACDStrategy,
    CompositeStrategy,
    create_strategy
)


# ========== 테스트용 데이터 생성 ==========

def create_sample_df(length: int = 100, trend: str = "up") -> pd.DataFrame:
    """테스트용 OHLCV 데이터 생성"""
    np.random.seed(42)

    if trend == "up":
        base = np.linspace(100, 150, length)
    elif trend == "down":
        base = np.linspace(150, 100, length)
    else:  # sideways
        base = np.ones(length) * 125 + np.random.randn(length) * 5

    noise = np.random.randn(length) * 2

    close = base + noise
    high = close + np.abs(np.random.randn(length)) * 2
    low = close - np.abs(np.random.randn(length)) * 2
    open_ = close + np.random.randn(length) * 1
    volume = np.random.randint(100000, 1000000, length)

    return pd.DataFrame({
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })


def create_crossover_df() -> pd.DataFrame:
    """크로스오버 테스트용 데이터"""
    # 하락 후 상승 패턴 (골든크로스 유도)
    close = np.concatenate([
        np.linspace(100, 80, 20),   # 하락
        np.linspace(80, 120, 30),   # 상승
    ])

    df = pd.DataFrame({
        'open': close + np.random.randn(50) * 0.5,
        'high': close + 2,
        'low': close - 2,
        'close': close,
        'volume': np.random.randint(100000, 1000000, 50)
    })
    return df


# ========== Indicators 테스트 ==========

class TestTechnicalIndicators:
    """기술적 지표 테스트"""

    @pytest.fixture
    def sample_df(self):
        return create_sample_df(100, "up")

    def test_sma(self, sample_df):
        """SMA 테스트"""
        sma = TechnicalIndicators.sma(sample_df['close'], 20)
        assert len(sma) == len(sample_df)
        assert sma.isna().sum() == 19  # 첫 19개는 NaN

    def test_ema(self, sample_df):
        """EMA 테스트"""
        ema = TechnicalIndicators.ema(sample_df['close'], 20)
        assert len(ema) == len(sample_df)
        # EMA는 처음부터 계산됨 (NaN 없음)

    def test_rsi(self, sample_df):
        """RSI 테스트"""
        rsi = TechnicalIndicators.rsi(sample_df['close'], 14)
        assert len(rsi) == len(sample_df)
        # RSI는 0-100 범위
        valid_rsi = rsi.dropna()
        assert (valid_rsi >= 0).all() and (valid_rsi <= 100).all()

    def test_macd(self, sample_df):
        """MACD 테스트"""
        result = TechnicalIndicators.macd(sample_df['close'])
        assert isinstance(result, MACDResult)
        assert len(result.macd) == len(sample_df)
        assert len(result.signal) == len(sample_df)
        assert len(result.histogram) == len(sample_df)

    def test_bollinger_bands(self, sample_df):
        """볼린저 밴드 테스트"""
        result = TechnicalIndicators.bollinger_bands(sample_df['close'])
        assert isinstance(result, BollingerBands)
        # 상단 > 중간 > 하단
        valid_idx = ~result.upper.isna()
        assert (result.upper[valid_idx] >= result.middle[valid_idx]).all()
        assert (result.middle[valid_idx] >= result.lower[valid_idx]).all()

    def test_stochastic(self, sample_df):
        """스토캐스틱 테스트"""
        result = TechnicalIndicators.stochastic(
            sample_df['high'],
            sample_df['low'],
            sample_df['close']
        )
        assert isinstance(result, StochasticResult)
        valid_k = result.k.dropna()
        assert (valid_k >= 0).all() and (valid_k <= 100).all()

    def test_atr(self, sample_df):
        """ATR 테스트"""
        atr = TechnicalIndicators.atr(
            sample_df['high'],
            sample_df['low'],
            sample_df['close']
        )
        assert len(atr) == len(sample_df)
        assert (atr.dropna() >= 0).all()  # ATR은 항상 양수

    def test_calculate_indicators(self, sample_df):
        """전체 지표 계산 테스트"""
        result = calculate_indicators(sample_df)
        assert 'sma_20' in result.columns
        assert 'rsi' in result.columns
        assert 'macd' in result.columns
        assert 'bb_upper' in result.columns


# ========== Base Strategy 테스트 ==========

class TestSignalAndPosition:
    """Signal, Position Enum 테스트"""

    def test_signal_values(self):
        assert Signal.STRONG_BUY.value == 2
        assert Signal.BUY.value == 1
        assert Signal.HOLD.value == 0
        assert Signal.SELL.value == -1
        assert Signal.STRONG_SELL.value == -2

    def test_position_values(self):
        assert Position.NONE.value == 0
        assert Position.LONG.value == 1
        assert Position.SHORT.value == -1


class TestTradeSignal:
    """TradeSignal 테스트"""

    def test_creation(self):
        signal = TradeSignal(
            signal=Signal.BUY,
            strength=0.8,
            price=10000,
            timestamp=datetime.now(),
            reason="테스트"
        )
        assert signal.signal == Signal.BUY
        assert signal.strength == 0.8
        assert signal.price == 10000


class TestStrategyConfig:
    """StrategyConfig 테스트"""

    def test_default_values(self):
        config = StrategyConfig(name="Test")
        assert config.name == "Test"
        assert config.risk_per_trade == 0.02
        assert config.stop_loss_pct == 0.03


# ========== Strategies 테스트 ==========

class TestMACrossoverStrategy:
    """이동평균 크로스오버 전략 테스트"""

    @pytest.fixture
    def strategy(self):
        return MACrossoverStrategy()

    def test_default_config(self, strategy):
        assert strategy.config.name == "MA Crossover"
        assert "fast_period" in strategy.config.params
        assert "slow_period" in strategy.config.params

    def test_analyze_insufficient_data(self, strategy):
        df = create_sample_df(1)
        signal = strategy.analyze(df)
        assert signal.signal == Signal.HOLD
        assert "데이터 부족" in signal.reason

    def test_analyze_uptrend(self, strategy):
        df = create_sample_df(50, "up")
        signal = strategy.analyze(df)
        assert isinstance(signal, TradeSignal)
        assert signal.price > 0

    def test_get_indicators(self, strategy):
        df = create_sample_df(50, "up")
        indicators = strategy.get_indicators(df)
        assert "fast_ma" in indicators
        assert "slow_ma" in indicators
        assert "price" in indicators


class TestRSIStrategy:
    """RSI 전략 테스트"""

    @pytest.fixture
    def strategy(self):
        return RSIStrategy()

    def test_default_config(self, strategy):
        assert strategy.config.name == "RSI Strategy"
        assert strategy.config.params["rsi_period"] == 14

    def test_analyze(self, strategy):
        df = create_sample_df(50, "up")
        signal = strategy.analyze(df)
        assert isinstance(signal, TradeSignal)
        assert "rsi" in signal.indicators

    def test_oversold_signal(self, strategy):
        # 하락 추세 데이터 (RSI가 낮아지도록)
        df = create_sample_df(50, "down")
        signal = strategy.analyze(df)
        # RSI가 과매도 구간에 있을 가능성
        assert signal.indicators["rsi"] is not None


class TestMACDStrategy:
    """MACD 전략 테스트"""

    @pytest.fixture
    def strategy(self):
        return MACDStrategy()

    def test_default_config(self, strategy):
        assert strategy.config.name == "MACD Strategy"
        assert strategy.config.params["fast_period"] == 12
        assert strategy.config.params["slow_period"] == 26

    def test_analyze(self, strategy):
        df = create_sample_df(50, "up")
        signal = strategy.analyze(df)
        assert isinstance(signal, TradeSignal)
        assert "macd" in signal.indicators
        assert "signal" in signal.indicators
        assert "histogram" in signal.indicators


class TestCompositeStrategy:
    """복합 전략 테스트"""

    @pytest.fixture
    def strategy(self):
        return CompositeStrategy()

    def test_default_config(self, strategy):
        assert strategy.config.name == "Composite Strategy"
        assert "weight_ma" in strategy.config.params
        assert "weight_rsi" in strategy.config.params
        assert "weight_macd" in strategy.config.params

    def test_weights_sum_to_one(self, strategy):
        params = strategy.config.params
        total_weight = (
            params["weight_ma"] +
            params["weight_rsi"] +
            params["weight_macd"]
        )
        assert abs(total_weight - 1.0) < 0.001

    def test_analyze(self, strategy):
        df = create_sample_df(50, "up")
        signal = strategy.analyze(df)
        assert isinstance(signal, TradeSignal)
        assert "total_score" in signal.indicators


class TestCreateStrategy:
    """전략 팩토리 테스트"""

    def test_create_ma_crossover(self):
        strategy = create_strategy("ma_crossover")
        assert isinstance(strategy, MACrossoverStrategy)

    def test_create_rsi(self):
        strategy = create_strategy("rsi")
        assert isinstance(strategy, RSIStrategy)

    def test_create_macd(self):
        strategy = create_strategy("macd")
        assert isinstance(strategy, MACDStrategy)

    def test_create_composite(self):
        strategy = create_strategy("composite")
        assert isinstance(strategy, CompositeStrategy)

    def test_create_with_params(self):
        strategy = create_strategy("rsi", rsi_period=21, oversold=25)
        assert strategy.config.params["rsi_period"] == 21
        assert strategy.config.params["oversold"] == 25

    def test_create_unknown_strategy(self):
        with pytest.raises(ValueError):
            create_strategy("unknown_strategy")


class TestStrategyManager:
    """전략 매니저 테스트"""

    @pytest.fixture
    def manager(self):
        return StrategyManager()

    def test_register_strategy(self, manager):
        strategy = create_strategy("rsi")
        manager.register("rsi_strategy", strategy)
        assert "rsi_strategy" in manager.list_strategies()

    def test_set_active(self, manager):
        strategy = create_strategy("macd")
        manager.register("macd_strategy", strategy)
        manager.set_active("macd_strategy")
        assert manager.active_strategy == "macd_strategy"

    def test_get_active(self, manager):
        strategy = create_strategy("composite")
        manager.register("composite", strategy)
        manager.set_active("composite")
        active = manager.get_active()
        assert isinstance(active, CompositeStrategy)

    def test_set_active_unknown(self, manager):
        with pytest.raises(ValueError):
            manager.set_active("unknown")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
