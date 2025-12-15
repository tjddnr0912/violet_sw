"""
텔레그램 봇 테스트 모듈
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.telegram.bot import (
    TelegramNotifier,
    TelegramBot,
    NotificationType,
    get_notifier
)


class TestNotificationType:
    """NotificationType Enum 테스트"""

    def test_notification_types(self):
        """알림 유형 값 테스트"""
        assert NotificationType.BUY.value == "매수"
        assert NotificationType.SELL.value == "매도"
        assert NotificationType.MODIFY.value == "정정"
        assert NotificationType.CANCEL.value == "취소"
        assert NotificationType.INFO.value == "정보"
        assert NotificationType.ERROR.value == "오류"
        assert NotificationType.SYSTEM.value == "시스템"


class TestTelegramNotifier:
    """TelegramNotifier 클래스 테스트"""

    def test_init(self):
        """초기화 테스트"""
        with patch.dict('os.environ', {
            'TELEGRAM_BOT_TOKEN': 'test_token',
            'TELEGRAM_CHAT_ID': '123456789'
        }):
            notifier = TelegramNotifier()
            assert notifier.bot_token == 'test_token'
            assert notifier.chat_id == '123456789'

    def test_validate_config_success(self):
        """설정 검증 성공 테스트"""
        with patch.dict('os.environ', {
            'TELEGRAM_BOT_TOKEN': 'test_token',
            'TELEGRAM_CHAT_ID': '123456789'
        }):
            notifier = TelegramNotifier()
            assert notifier.validate_config() is True

    def test_validate_config_missing_token(self):
        """토큰 누락 검증 테스트"""
        with patch.dict('os.environ', {
            'TELEGRAM_CHAT_ID': '123456789'
        }, clear=True):
            notifier = TelegramNotifier()
            assert notifier.validate_config() is False

    def test_validate_config_missing_chat_id(self):
        """채팅ID 누락 검증 테스트"""
        with patch.dict('os.environ', {
            'TELEGRAM_BOT_TOKEN': 'test_token'
        }, clear=True):
            notifier = TelegramNotifier()
            assert notifier.validate_config() is False

    def test_format_notification(self):
        """알림 포맷팅 테스트"""
        with patch.dict('os.environ', {
            'TELEGRAM_BOT_TOKEN': 'test_token',
            'TELEGRAM_CHAT_ID': '123456789'
        }):
            notifier = TelegramNotifier()
            message = notifier._format_notification(
                NotificationType.BUY,
                "테스트 제목",
                {"키1": "값1", "키2": "값2"}
            )

            assert "[매수]" in message
            assert "테스트 제목" in message
            assert "키1" in message
            assert "값1" in message

    @pytest.mark.asyncio
    async def test_send_message_async_success(self):
        """비동기 메시지 전송 성공 테스트"""
        with patch.dict('os.environ', {
            'TELEGRAM_BOT_TOKEN': 'test_token',
            'TELEGRAM_CHAT_ID': '123456789'
        }):
            notifier = TelegramNotifier()

            # Mock Bot
            mock_bot = AsyncMock()
            notifier._bot = mock_bot

            result = await notifier.send_message_async("테스트 메시지")

            assert result is True
            mock_bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_async_failure(self):
        """비동기 메시지 전송 실패 테스트"""
        with patch.dict('os.environ', {}, clear=True):
            notifier = TelegramNotifier()
            result = await notifier.send_message_async("테스트 메시지")
            assert result is False


class TestTelegramNotifierMethods:
    """TelegramNotifier 알림 메서드 테스트"""

    @pytest.fixture
    def mock_notifier(self):
        """Mock Notifier 생성"""
        with patch.dict('os.environ', {
            'TELEGRAM_BOT_TOKEN': 'test_token',
            'TELEGRAM_CHAT_ID': '123456789'
        }):
            notifier = TelegramNotifier()
            notifier.send_message = Mock(return_value=True)
            return notifier

    def test_notify_buy(self, mock_notifier):
        """매수 알림 테스트"""
        result = mock_notifier.notify_buy(
            stock_name="삼성전자",
            stock_code="005930",
            qty=10,
            price=70000,
            order_no="0000123456"
        )

        assert result is True
        mock_notifier.send_message.assert_called_once()
        call_args = mock_notifier.send_message.call_args[0][0]
        assert "매수" in call_args
        assert "삼성전자" in call_args
        assert "005930" in call_args

    def test_notify_sell(self, mock_notifier):
        """매도 알림 테스트"""
        result = mock_notifier.notify_sell(
            stock_name="삼성전자",
            stock_code="005930",
            qty=10,
            price=72000
        )

        assert result is True
        mock_notifier.send_message.assert_called_once()
        call_args = mock_notifier.send_message.call_args[0][0]
        assert "매도" in call_args

    def test_notify_cancel(self, mock_notifier):
        """취소 알림 테스트"""
        result = mock_notifier.notify_cancel(
            stock_name="삼성전자",
            stock_code="005930",
            qty=10,
            reason="사용자 요청"
        )

        assert result is True
        call_args = mock_notifier.send_message.call_args[0][0]
        assert "취소" in call_args

    def test_notify_error(self, mock_notifier):
        """오류 알림 테스트"""
        result = mock_notifier.notify_error(
            title="API 오류",
            error_msg="연결 실패"
        )

        assert result is True
        call_args = mock_notifier.send_message.call_args[0][0]
        assert "오류" in call_args
        assert "연결 실패" in call_args

    def test_notify_system(self, mock_notifier):
        """시스템 알림 테스트"""
        result = mock_notifier.notify_system(
            title="시스템 시작",
            details={"상태": "정상", "버전": "1.0.0"}
        )

        assert result is True
        call_args = mock_notifier.send_message.call_args[0][0]
        assert "시스템" in call_args


class TestTelegramBot:
    """TelegramBot 클래스 테스트"""

    def test_init(self):
        """초기화 테스트"""
        with patch.dict('os.environ', {
            'TELEGRAM_BOT_TOKEN': 'test_token',
            'TELEGRAM_CHAT_ID': '123456789'
        }):
            bot = TelegramBot()
            assert bot.bot_token == 'test_token'
            assert bot.chat_id == '123456789'
            assert bot.kis_client is None

    def test_init_with_client(self):
        """API 클라이언트와 함께 초기화 테스트"""
        with patch.dict('os.environ', {
            'TELEGRAM_BOT_TOKEN': 'test_token',
            'TELEGRAM_CHAT_ID': '123456789'
        }):
            mock_client = Mock()
            bot = TelegramBot(kis_client=mock_client)
            assert bot.kis_client is mock_client

    def test_validate_config(self):
        """설정 검증 테스트"""
        with patch.dict('os.environ', {
            'TELEGRAM_BOT_TOKEN': 'test_token',
            'TELEGRAM_CHAT_ID': '123456789'
        }):
            bot = TelegramBot()
            assert bot.validate_config() is True

    @pytest.mark.asyncio
    async def test_cmd_start(self):
        """시작 명령어 테스트"""
        with patch.dict('os.environ', {
            'TELEGRAM_BOT_TOKEN': 'test_token',
            'TELEGRAM_CHAT_ID': '123456789'
        }):
            bot = TelegramBot()

            # Mock Update 및 Context
            update = Mock()
            update.message = AsyncMock()
            context = Mock()

            await bot.cmd_start(update, context)

            update.message.reply_text.assert_called_once()
            call_args = update.message.reply_text.call_args[0][0]
            assert "주식 자동매매 봇" in call_args

    @pytest.mark.asyncio
    async def test_cmd_status(self):
        """상태 명령어 테스트"""
        with patch.dict('os.environ', {
            'TELEGRAM_BOT_TOKEN': 'test_token',
            'TELEGRAM_CHAT_ID': '123456789'
        }):
            bot = TelegramBot()

            update = Mock()
            update.message = AsyncMock()
            context = Mock()

            await bot.cmd_status(update, context)

            update.message.reply_text.assert_called_once()
            call_args = update.message.reply_text.call_args[0][0]
            assert "시스템 상태" in call_args


class TestGetNotifier:
    """get_notifier 싱글톤 테스트"""

    def test_singleton(self):
        """싱글톤 패턴 테스트"""
        import src.telegram.bot as bot_module

        # 기존 인스턴스 초기화
        bot_module._notifier_instance = None

        with patch.dict('os.environ', {
            'TELEGRAM_BOT_TOKEN': 'test_token',
            'TELEGRAM_CHAT_ID': '123456789'
        }):
            notifier1 = get_notifier()
            notifier2 = get_notifier()

            assert notifier1 is notifier2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
