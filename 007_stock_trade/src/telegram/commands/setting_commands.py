"""
설정 변경 명령어 Mixin

cmd_set_dryrun, cmd_set_target, cmd_set_stoploss
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from ..validators import InputValidator

logger = logging.getLogger(__name__)


class SettingCommandsMixin:
    """설정 변경 명령어 모음"""

    async def cmd_set_dryrun(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Dry-run 모드 설정"""
        from src.core import get_controller

        if not context.args:
            await update.message.reply_text("사용법: /set_dryrun on|off")
            return

        is_valid, enabled, error_msg = InputValidator.validate_on_off(context.args[0])
        if not is_valid:
            await update.message.reply_text(f"❌ {error_msg}")
            return

        controller = get_controller()
        result = controller.set_dry_run(enabled)

        if result['success']:
            status = "✅ 활성화" if enabled else "🔴 비활성화 (실제 주문!)"
            message = (
                f"⚙️ <b>Dry-Run 모드 변경</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"상태: {status}\n"
                f"━━━━━━━━━━━━━━━"
            )
            if not enabled:
                message += "\n⚠️ <b>주의: 실제 주문이 실행됩니다!</b>"
        else:
            message = f"❌ {result['message']}"

        await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_set_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """목표 종목 수 설정"""
        from src.core import get_controller

        if not context.args:
            await update.message.reply_text("사용법: /set_target [숫자]\n예: /set_target 15")
            return

        is_valid, count, error_msg = InputValidator.validate_positive_int(
            context.args[0], min_val=1, max_val=50, field_name="목표 종목 수"
        )
        if not is_valid:
            await update.message.reply_text(f"❌ {error_msg}")
            return

        controller = get_controller()
        result = controller.set_target_count(count)

        if result['success']:
            message = (
                f"⚙️ <b>목표 종목 수 변경</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"이전: {result['previous']}개\n"
                f"현재: {result['current']}개\n"
                f"━━━━━━━━━━━━━━━"
            )
        else:
            message = f"❌ {result['message']}"

        await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_set_stoploss(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """손절 비율 설정"""
        from src.core import get_controller

        if not context.args:
            await update.message.reply_text("사용법: /set_stoploss [비율]\n예: /set_stoploss 7")
            return

        is_valid, pct, error_msg = InputValidator.validate_positive_float(
            context.args[0], min_val=1.0, max_val=30.0, field_name="손절 비율"
        )
        if not is_valid:
            await update.message.reply_text(f"❌ {error_msg}")
            return

        controller = get_controller()
        result = controller.set_stop_loss(pct)

        if result['success']:
            message = (
                f"⚙️ <b>손절 비율 변경</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"이전: {result['previous']}%\n"
                f"현재: {result['current']}%\n"
                f"━━━━━━━━━━━━━━━"
            )
        else:
            message = f"❌ {result['message']}"

        await update.message.reply_text(message, parse_mode='HTML')
