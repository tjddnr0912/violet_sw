"""
멀티팩터 퀀트 전략 테스트
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.quant import (
    # Factors
    CompositeScoreCalculator,
    ValueFactorCalculator,
    MomentumFactorCalculator,
    QualityFactorCalculator,
    FactorType,
    # Signals
    TechnicalAnalyzer,
    SignalType,
    Position,
    StopLossManager,
    TakeProfitManager,
    # Risk
    PositionSizer,
    RiskConfig,
    RiskMonitor,
    PortfolioManager,
    PortfolioSnapshot,
    RiskLevel
)


class TestValueFactorCalculator:
    """가치 팩터 테스트"""

    def test_low_per_high_score(self):
        """낮은 PER은 높은 점수"""
        calc = ValueFactorCalculator()
        score = calc.calculate(per=8.0, pbr=1.0)

        assert score.score >= 60
        assert score.factor_type == FactorType.VALUE

    def test_high_per_low_score(self):
        """높은 PER은 낮은 점수"""
        calc = ValueFactorCalculator()
        score = calc.calculate(per=40.0, pbr=3.0)

        assert score.score <= 50

    def test_invalid_per(self):
        """유효하지 않은 PER"""
        calc = ValueFactorCalculator()
        score = calc.calculate(per=-5.0, pbr=1.0)

        assert score.score == 0


class TestMomentumFactorCalculator:
    """모멘텀 팩터 테스트"""

    def test_strong_momentum(self):
        """강한 상승 모멘텀"""
        calc = MomentumFactorCalculator()
        score = calc.calculate(
            return_1m=5.0,
            return_3m=15.0,
            return_6m=25.0,
            return_12m=40.0,
            distance_from_high=-3.0
        )

        assert score.score >= 70

    def test_weak_momentum(self):
        """약한 모멘텀"""
        calc = MomentumFactorCalculator()
        score = calc.calculate(
            return_1m=-5.0,
            return_3m=-10.0,
            return_6m=-15.0,
            return_12m=-20.0,
            distance_from_high=-30.0
        )

        assert score.score <= 40

    def test_short_term_overheat_penalty(self):
        """단기 과열 페널티"""
        calc = MomentumFactorCalculator()
        score = calc.calculate(
            return_1m=30.0,  # 과열
            return_3m=15.0,
            return_6m=20.0,
            return_12m=25.0
        )

        assert "short_term_overheat_penalty" in score.details


class TestQualityFactorCalculator:
    """퀄리티 팩터 테스트"""

    def test_high_quality(self):
        """고퀄리티 기업"""
        calc = QualityFactorCalculator()
        score = calc.calculate(
            roe=20.0,
            operating_margin=15.0,
            debt_ratio=30.0,
            eps_growth=20.0
        )

        assert score.score >= 70

    def test_low_quality(self):
        """저퀄리티 기업"""
        calc = QualityFactorCalculator()
        score = calc.calculate(
            roe=-5.0,  # 적자
            operating_margin=-3.0,  # 영업적자
            debt_ratio=250.0,  # 고부채
            eps_growth=-10.0
        )

        assert score.score <= 30


class TestCompositeScoreCalculator:
    """복합 점수 테스트"""

    def test_calculate_composite_score(self):
        """복합 점수 계산"""
        calc = CompositeScoreCalculator()
        score = calc.calculate(
            code="005930",
            name="삼성전자",
            per=12.0,
            pbr=1.2,
            return_12m=20.0,
            roe=15.0,
            market_cap=5000000
        )

        assert score.passed_filter is True
        assert 0 <= score.composite_score <= 100
        assert score.code == "005930"

    def test_filter_negative_per(self):
        """적자 기업 필터"""
        calc = CompositeScoreCalculator()
        score = calc.calculate(
            code="000000",
            name="적자기업",
            per=-10.0,
            pbr=1.0,
            roe=5.0
        )

        assert score.passed_filter is False
        assert "적자" in score.filter_reason

    def test_filter_high_debt(self):
        """고부채 기업 필터"""
        calc = CompositeScoreCalculator()
        score = calc.calculate(
            code="000001",
            name="고부채기업",
            per=10.0,
            pbr=1.0,
            roe=5.0,
            debt_ratio=350.0  # 300% 초과
        )

        assert score.passed_filter is False
        assert "부채비율" in score.filter_reason

    def test_rank_stocks(self):
        """종목 순위 매기기"""
        calc = CompositeScoreCalculator()

        scores = [
            calc.calculate(code="A", name="A", per=10, pbr=1.0, roe=15, return_12m=30),
            calc.calculate(code="B", name="B", per=15, pbr=1.5, roe=10, return_12m=15),
            calc.calculate(code="C", name="C", per=20, pbr=2.0, roe=8, return_12m=5),
        ]

        ranked = calc.rank_stocks(scores)

        assert ranked[0].rank == 1
        assert ranked[0].composite_score >= ranked[1].composite_score


class TestTechnicalAnalyzer:
    """기술적 분석 테스트"""

    def test_calculate_rsi(self):
        """RSI 계산"""
        analyzer = TechnicalAnalyzer()

        # 상승 추세 가격
        prices = [100 + i for i in range(20)]
        prices.reverse()

        rsi = analyzer.calculate_rsi(prices)
        assert rsi > 50  # 상승 추세면 RSI > 50

    def test_calculate_ma(self):
        """이동평균 계산"""
        analyzer = TechnicalAnalyzer()
        prices = [100, 102, 98, 105, 103]

        ma5 = analyzer.calculate_ma(prices, 5)
        assert ma5 == 101.6  # (100+102+98+105+103) / 5

    def test_analyze_bullish(self):
        """상승 신호 분석"""
        analyzer = TechnicalAnalyzer()

        # 상승 추세 가격 (최신이 앞)
        prices = list(reversed([50 + i * 0.5 for i in range(60)]))

        signal = analyzer.analyze(prices)

        assert signal.signal_type in [SignalType.BUY, SignalType.STRONG_BUY, SignalType.HOLD]
        assert signal.score >= 50


class TestStopLossManager:
    """손절 관리 테스트"""

    def test_fixed_stop_loss(self):
        """고정 비율 손절"""
        stop = StopLossManager.calculate_fixed_stop(50000, 0.07)
        assert stop == 46500  # 50000 * 0.93

    def test_atr_stop_loss(self):
        """ATR 기반 손절"""
        stop = StopLossManager.calculate_atr_stop(50000, 1500, 2.0)
        assert stop == 47000  # 50000 - (1500 * 2)

    def test_trailing_stop_update(self):
        """트레일링 스탑 업데이트"""
        position = Position(
            code="005930",
            name="삼성전자",
            entry_price=50000,
            current_price=55000,  # 상승
            quantity=100,
            entry_date=datetime.now(),
            stop_loss=46500,
            take_profit_1=55000,
            take_profit_2=60000,
            highest_price=50000
        )

        new_stop = StopLossManager.update_trailing_stop(position, 0.07)

        # 신고가 갱신되어 손절가 상향
        assert new_stop > position.stop_loss


class TestTakeProfitManager:
    """익절 관리 테스트"""

    def test_calculate_targets(self):
        """익절 목표가 계산"""
        tp1, tp2 = TakeProfitManager.calculate_targets(
            entry_price=50000,
            stop_loss=46500  # 3500원 리스크
        )

        assert tp1 == 55250  # 50000 + (3500 * 1.5)
        assert tp2 == 58750  # 50000 + (3500 * 2.5)

    def test_staged_sell_qty(self):
        """단계별 매도 수량"""
        qty1 = TakeProfitManager.calculate_staged_sell_qty(100, stage=1)
        qty2 = TakeProfitManager.calculate_staged_sell_qty(100, stage=2)

        assert qty1 == 30  # 30%
        assert qty2 == 50  # 50%


class TestPositionSizer:
    """포지션 사이징 테스트"""

    def test_equal_weight(self):
        """동일 비중"""
        sizer = PositionSizer()
        amount = sizer.calculate_equal_weight(100000000, 20)

        # 1억 * 0.9 (현금 제외) / 20 = 450만원
        assert amount == 4500000

    def test_risk_based_sizing(self):
        """리스크 기반 사이징"""
        sizer = PositionSizer()
        sizing = sizer.calculate_risk_based(
            total_capital=100000000,
            entry_price=50000,
            stop_loss=46500,
            risk_per_trade=0.02
        )

        # 2% 리스크, 7% 손절 → 약 28% 비중이지만 max 10%로 제한
        assert sizing.weight <= 0.10
        assert sizing.recommended_qty > 0

    def test_volatility_adjusted(self):
        """변동성 조정 사이징"""
        sizer = PositionSizer()

        # 낮은 변동성 → 큰 포지션
        low_vol = sizer.calculate_volatility_adjusted(
            total_capital=100000000,
            entry_price=50000,
            volatility=15.0
        )

        # 높은 변동성 → 작은 포지션
        high_vol = sizer.calculate_volatility_adjusted(
            total_capital=100000000,
            entry_price=50000,
            volatility=50.0
        )

        assert low_vol.weight > high_vol.weight


class TestRiskMonitor:
    """리스크 모니터링 테스트"""

    def test_mdd_alert(self):
        """MDD 경고"""
        config = RiskConfig(mdd_limit=0.20)
        monitor = RiskMonitor(config)

        snapshot = PortfolioSnapshot(
            timestamp=datetime.now(),
            total_value=80000000,  # 20% 하락
            cash=10000000,
            invested=70000000,
            positions=[],
            mdd=0.25  # 25% MDD
        )

        alerts = monitor.check_all_risks(snapshot)

        assert len(alerts) > 0
        mdd_alerts = [a for a in alerts if a.alert_type == "MDD_EXCEEDED"]
        assert len(mdd_alerts) > 0
        assert mdd_alerts[0].level == RiskLevel.CRITICAL

    def test_consecutive_losses(self):
        """연속 손실 체크"""
        config = RiskConfig(max_consecutive_losses=3)
        monitor = RiskMonitor(config)

        # 3연속 손실 추가
        for i in range(3):
            monitor.add_trade({"pnl": -100000, "code": f"TEST{i}"})

        assert monitor.is_trading_paused is True


class TestPortfolioManager:
    """포트폴리오 관리 테스트"""

    def test_add_position(self):
        """포지션 추가"""
        pm = PortfolioManager(total_capital=100000000)

        position = Position(
            code="005930",
            name="삼성전자",
            entry_price=50000,
            current_price=50000,
            quantity=100,
            entry_date=datetime.now(),
            stop_loss=46500,
            take_profit_1=55000,
            take_profit_2=60000
        )

        pm.add_position(position)

        assert "005930" in pm.positions
        assert pm.cash == 95000000  # 1억 - 500만원

    def test_remove_position(self):
        """포지션 제거"""
        pm = PortfolioManager(total_capital=100000000)

        position = Position(
            code="005930",
            name="삼성전자",
            entry_price=50000,
            current_price=55000,
            quantity=100,
            entry_date=datetime.now(),
            stop_loss=46500,
            take_profit_1=55000,
            take_profit_2=60000
        )

        pm.add_position(position)
        trade = pm.remove_position("005930", sell_price=55000)

        assert "005930" not in pm.positions
        assert trade["pnl"] == 500000  # 5000원 * 100주
        assert trade["pnl_pct"] == 10.0  # +10%

    def test_get_snapshot(self):
        """스냅샷 생성"""
        pm = PortfolioManager(total_capital=100000000)

        position = Position(
            code="005930",
            name="삼성전자",
            entry_price=50000,
            current_price=55000,
            quantity=100,
            entry_date=datetime.now(),
            stop_loss=46500,
            take_profit_1=55000,
            take_profit_2=60000
        )

        pm.add_position(position)
        snapshot = pm.get_snapshot()

        assert snapshot.total_value == 100500000  # 95M + 5.5M
        assert snapshot.invested == 5500000
        assert len(snapshot.positions) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
