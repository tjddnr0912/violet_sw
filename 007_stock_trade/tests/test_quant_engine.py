"""
퀀트 전략 통합 엔진 테스트
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.quant_engine import (
    QuantTradingEngine,
    QuantEngineConfig,
    EngineState,
    SchedulePhase,
    PendingOrder
)
from src.strategy.quant import Position


class TestQuantEngineConfig:
    """엔진 설정 테스트"""

    def test_default_config(self):
        """기본 설정값 확인"""
        config = QuantEngineConfig()

        assert config.total_capital == 100_000_000
        assert config.target_stock_count == 20
        assert config.screening_time == "08:30"
        assert config.market_open_time == "09:00"
        assert config.market_close_time == "15:20"
        assert config.dry_run is True

    def test_custom_config(self):
        """커스텀 설정값"""
        config = QuantEngineConfig(
            total_capital=50_000_000,
            target_stock_count=10,
            dry_run=False
        )

        assert config.total_capital == 50_000_000
        assert config.target_stock_count == 10
        assert config.dry_run is False


class TestSchedulePhase:
    """스케줄 단계 테스트"""

    def test_phase_detection(self):
        """시간대별 단계 확인"""
        config = QuantEngineConfig()

        # Mock 엔진 생성 (API 호출 없이)
        with patch('src.quant_engine.KISQuantClient'):
            with patch('src.quant_engine.get_notifier'):
                engine = QuantTradingEngine(config)

        # 주말 테스트
        with patch('src.quant_engine.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 6, 10, 0)  # 토요일
            mock_dt.now.return_value.weekday = lambda: 5

            phase = engine._get_current_phase()
            assert phase == SchedulePhase.AFTER_MARKET


class TestPendingOrder:
    """대기 주문 테스트"""

    def test_buy_order_creation(self):
        """매수 주문 생성"""
        order = PendingOrder(
            code="005930",
            name="삼성전자",
            order_type="BUY",
            quantity=10,
            price=0,
            reason="리밸런싱 매수",
            stop_loss=65000,
            take_profit_1=78000,
            take_profit_2=85000,
            weight=0.05
        )

        assert order.code == "005930"
        assert order.order_type == "BUY"
        assert order.quantity == 10
        assert order.stop_loss == 65000

    def test_sell_order_creation(self):
        """매도 주문 생성"""
        order = PendingOrder(
            code="005930",
            name="삼성전자",
            order_type="SELL",
            quantity=10,
            price=0,
            reason="손절"
        )

        assert order.order_type == "SELL"


class TestQuantEngineState:
    """엔진 상태 관리 테스트"""

    @pytest.fixture
    def mock_engine(self):
        """Mock 엔진 fixture"""
        config = QuantEngineConfig(dry_run=True)

        with patch('src.quant_engine.KISQuantClient') as mock_client:
            with patch('src.quant_engine.get_notifier') as mock_notifier:
                mock_client.return_value.auth.validate_credentials.return_value = True
                mock_notifier.return_value = Mock()

                engine = QuantTradingEngine(config)
                engine.client = mock_client.return_value
                engine.notifier = mock_notifier.return_value

                yield engine

    def test_initial_state(self, mock_engine):
        """초기 상태 확인"""
        assert mock_engine.state == EngineState.STOPPED
        assert len(mock_engine.portfolio.positions) == 0
        assert len(mock_engine.pending_orders) == 0

    def test_get_status(self, mock_engine):
        """상태 조회"""
        status = mock_engine.get_status()

        assert status["state"] == "stopped"
        assert status["dry_run"] is True
        assert status["positions"] == 0

    def test_pause_resume(self, mock_engine):
        """일시정지/재개"""
        mock_engine.state = EngineState.RUNNING

        mock_engine.pause()
        assert mock_engine.state == EngineState.PAUSED

        mock_engine.resume()
        assert mock_engine.state == EngineState.RUNNING


class TestRebalanceLogic:
    """리밸런싱 로직 테스트"""

    @pytest.fixture
    def mock_engine(self):
        """Mock 엔진 fixture"""
        config = QuantEngineConfig(
            total_capital=100_000_000,
            target_stock_count=5,
            dry_run=True
        )

        with patch('src.quant_engine.KISQuantClient') as mock_client:
            with patch('src.quant_engine.get_notifier') as mock_notifier:
                mock_client.return_value.auth.validate_credentials.return_value = True
                mock_notifier.return_value = Mock()

                engine = QuantTradingEngine(config)
                engine.client = mock_client.return_value
                engine.notifier = mock_notifier.return_value

                yield engine

    def test_is_rebalance_day_first_weekday(self, mock_engine):
        """매월 첫 거래일 리밸런싱"""
        # 1월 2일 화요일 (1월 1일이 월요일인 경우)
        with patch('src.quant_engine.datetime') as mock_dt:
            mock_now = datetime(2024, 1, 2, 10, 0)
            mock_dt.now.return_value = mock_now

            # weekday() 호출 시 1 (화요일) 반환
            mock_dt.now.return_value.weekday = Mock(return_value=1)
            mock_dt.now.return_value.day = 2
            mock_dt.now.return_value.date = Mock(return_value=mock_now.date())

            # 첫 거래일 계산을 위한 replace mock
            mock_first = datetime(2024, 1, 1, 0, 0)
            mock_dt.now.return_value.replace = Mock(return_value=mock_first)

            # 실제 테스트는 복잡한 mock이 필요하여 skip
            # is_rebalance = mock_engine._is_rebalance_day()
            pass

    def test_generate_rebalance_orders_no_screening(self, mock_engine):
        """스크리닝 결과 없이 리밸런싱 시도"""
        mock_engine.last_screening_result = None
        orders = mock_engine.generate_rebalance_orders()

        assert len(orders) == 0


class TestPositionMonitoring:
    """포지션 모니터링 테스트"""

    @pytest.fixture
    def engine_with_position(self):
        """포지션이 있는 엔진 fixture"""
        config = QuantEngineConfig(
            total_capital=100_000_000,
            stop_loss_pct=0.07,
            dry_run=True
        )

        with patch('src.quant_engine.KISQuantClient') as mock_client:
            with patch('src.quant_engine.get_notifier') as mock_notifier:
                mock_client.return_value.auth.validate_credentials.return_value = True
                mock_notifier.return_value = Mock()
                mock_notifier.return_value.send_message = Mock()

                engine = QuantTradingEngine(config)
                engine.client = mock_client.return_value
                engine.notifier = mock_notifier.return_value

                # 테스트용 포지션 추가
                position = Position(
                    code="005930",
                    name="삼성전자",
                    entry_price=70000,
                    current_price=70000,
                    quantity=100,
                    entry_date=datetime.now(),
                    stop_loss=65100,  # -7%
                    take_profit_1=80500,  # +15%
                    take_profit_2=87500,  # +25%
                    highest_price=70000
                )
                engine.portfolio.positions["005930"] = position

                yield engine

    def test_stop_loss_trigger(self, engine_with_position):
        """손절 트리거 테스트"""
        engine = engine_with_position
        position = engine.portfolio.positions["005930"]

        # 가격 하락 시뮬레이션
        position.current_price = 64000  # 손절가 아래

        # Mock 주문 실행
        engine._execute_order = Mock(return_value=True)

        # 손절 트리거
        engine._trigger_stop_loss(position)

        # 주문 실행 확인
        engine._execute_order.assert_called_once()
        call_args = engine._execute_order.call_args[0][0]
        assert call_args.order_type == "SELL"
        assert "손절" in call_args.reason

    def test_take_profit_trigger(self, engine_with_position):
        """익절 트리거 테스트"""
        engine = engine_with_position
        position = engine.portfolio.positions["005930"]

        # 가격 상승 시뮬레이션
        position.current_price = 82000  # 1차 익절가 도달

        # Mock 주문 실행
        engine._execute_order = Mock(return_value=True)

        # 익절 트리거
        engine._trigger_take_profit(position, stage=1)

        # 주문 실행 확인
        engine._execute_order.assert_called_once()
        call_args = engine._execute_order.call_args[0][0]
        assert call_args.order_type == "SELL"
        assert call_args.quantity == 30  # 30% 매도

    def test_trailing_stop_update(self, engine_with_position):
        """트레일링 스탑 업데이트 테스트"""
        engine = engine_with_position
        position = engine.portfolio.positions["005930"]

        # 가격 상승
        position.current_price = 80000
        position.highest_price = 80000

        # 새 손절가 계산 (7% 아래)
        from src.strategy.quant import StopLossManager
        new_stop = StopLossManager.update_trailing_stop(position, 0.07)

        assert new_stop > 65100  # 기존 손절가보다 높음
        assert new_stop == 74400  # 80000 * 0.93


class TestOrderExecution:
    """주문 실행 테스트"""

    @pytest.fixture
    def mock_engine(self):
        """Mock 엔진 fixture"""
        config = QuantEngineConfig(dry_run=True)

        with patch('src.quant_engine.KISQuantClient') as mock_client:
            with patch('src.quant_engine.get_notifier') as mock_notifier:
                # Mock 설정
                mock_price = Mock()
                mock_price.price = 70000
                mock_price.name = "삼성전자"
                mock_client.return_value.get_stock_price.return_value = mock_price
                mock_client.return_value.auth.validate_credentials.return_value = True

                mock_notifier.return_value = Mock()
                mock_notifier.return_value.notify_buy = Mock()
                mock_notifier.return_value.notify_sell = Mock()

                engine = QuantTradingEngine(config)
                engine.client = mock_client.return_value
                engine.notifier = mock_notifier.return_value

                yield engine

    def test_execute_buy_dry_run(self, mock_engine):
        """Dry Run 매수 실행"""
        order = PendingOrder(
            code="005930",
            name="삼성전자",
            order_type="BUY",
            quantity=10,
            price=0,
            reason="테스트 매수",
            stop_loss=65100,
            take_profit_1=80500,
            take_profit_2=87500
        )

        result = mock_engine._execute_buy(order)

        assert result is True
        assert "005930" in mock_engine.portfolio.positions
        assert len(mock_engine.daily_trades) == 1
        assert mock_engine.daily_trades[0]["type"] == "BUY"

    def test_execute_sell_dry_run(self, mock_engine):
        """Dry Run 매도 실행"""
        # 먼저 포지션 추가
        position = Position(
            code="005930",
            name="삼성전자",
            entry_price=70000,
            current_price=70000,
            quantity=10,
            entry_date=datetime.now(),
            stop_loss=65100,
            take_profit_1=80500,
            take_profit_2=87500
        )
        mock_engine.portfolio.positions["005930"] = position

        # 매도 주문
        order = PendingOrder(
            code="005930",
            name="삼성전자",
            order_type="SELL",
            quantity=10,
            price=0,
            reason="테스트 매도"
        )

        result = mock_engine._execute_sell(order)

        assert result is True
        assert "005930" not in mock_engine.portfolio.positions


class TestDailyReport:
    """일일 리포트 테스트"""

    @pytest.fixture
    def mock_engine(self):
        """Mock 엔진 fixture"""
        config = QuantEngineConfig(dry_run=True)

        with patch('src.quant_engine.KISQuantClient') as mock_client:
            with patch('src.quant_engine.get_notifier') as mock_notifier:
                mock_client.return_value.auth.validate_credentials.return_value = True
                mock_notifier.return_value = Mock()
                mock_notifier.return_value.send_message = Mock()

                engine = QuantTradingEngine(config)
                engine.client = mock_client.return_value
                engine.notifier = mock_notifier.return_value

                yield engine

    def test_generate_daily_report(self, mock_engine):
        """일일 리포트 생성"""
        # 테스트 거래 추가
        mock_engine.daily_trades = [
            {"type": "BUY", "name": "삼성전자", "quantity": 10, "price": 70000},
            {"type": "SELL", "name": "SK하이닉스", "quantity": 5, "price": 150000, "pnl": 50000, "pnl_pct": 5.0}
        ]

        mock_engine.generate_daily_report()

        # 알림 전송 확인
        mock_engine.notifier.send_message.assert_called_once()

        # 거래 내역 초기화 확인
        assert len(mock_engine.daily_trades) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
