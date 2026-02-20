"""
시스템 제어 명령어 Mixin

cmd_start_trading, cmd_stop_trading, cmd_pause, cmd_resume,
cmd_emergency_stop, cmd_clear_emergency
"""

import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class ControlCommandsMixin:
    """시스템 제어 명령어 모음"""

    async def cmd_start_trading(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """자동매매 시작"""
        from src.core import get_controller

        controller = get_controller()
        result = controller.start_trading()

        if result['success']:
            config = result.get('config', {})
            message = (
                "▶️ <b>자동매매 시작</b>\n"
                "━━━━━━━━━━━━━━━\n"
                f"• Dry-Run: {'✅' if config.get('dry_run') else '🔴 실제주문'}\n"
                f"• 목표 종목: {config.get('target_count', 15)}개\n"
                "━━━━━━━━━━━━━━━\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            message = f"❌ {result['message']}"

        await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_stop_trading(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """자동매매 중지"""
        from src.core import get_controller

        controller = get_controller()
        result = controller.stop_trading()

        if result['success']:
            message = (
                "⏹️ <b>자동매매 중지</b>\n"
                "━━━━━━━━━━━━━━━\n"
                f"이전 상태: {result.get('previous_state', 'N/A')}\n"
                "━━━━━━━━━━━━━━━\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            message = f"❌ {result['message']}"

        await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """자동매매 일시정지"""
        from src.core import get_controller

        controller = get_controller()
        result = controller.pause_trading()

        if result['success']:
            message = (
                "⏸️ <b>자동매매 일시정지</b>\n"
                "━━━━━━━━━━━━━━━\n"
                "신규 주문이 중지됩니다.\n"
                "/resume 명령으로 재개할 수 있습니다.\n"
                "━━━━━━━━━━━━━━━\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            message = f"❌ {result['message']}"

        await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """자동매매 재개"""
        from src.core import get_controller

        controller = get_controller()
        result = controller.resume_trading()

        if result['success']:
            message = (
                "▶️ <b>자동매매 재개</b>\n"
                "━━━━━━━━━━━━━━━\n"
                "자동매매가 재개되었습니다.\n"
                "━━━━━━━━━━━━━━━\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            message = f"❌ {result['message']}"

        await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_emergency_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """긴급 정지"""
        from src.core import get_controller

        controller = get_controller()
        result = controller.emergency_stop()

        message = (
            "🚨 <b>긴급 정지 실행</b>\n"
            "━━━━━━━━━━━━━━━\n"
            "모든 거래가 즉시 중단됩니다.\n"
            "━━━━━━━━━━━━━━━\n"
            f"이전 상태: {result.get('previous_state', 'N/A')}\n"
            "━━━━━━━━━━━━━━━\n"
            "/clear_emergency 명령으로 해제\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_clear_emergency(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """긴급 정지 해제"""
        from src.core import get_controller

        controller = get_controller()
        result = controller.clear_emergency()

        if result['success']:
            message = (
                "✅ <b>긴급 정지 해제</b>\n"
                "━━━━━━━━━━━━━━━\n"
                "/start_trading 명령으로\n"
                "거래를 재개할 수 있습니다.\n"
                "━━━━━━━━━━━━━━━\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            message = f"❌ {result['message']}"

        await update.message.reply_text(message, parse_mode='HTML')
