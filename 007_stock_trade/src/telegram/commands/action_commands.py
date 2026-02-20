"""
수동 실행 / 포지션 관리 명령어 Mixin

cmd_run_screening, cmd_run_rebalance, cmd_rebalance,
cmd_reconcile, cmd_run_optimize, cmd_sync_positions,
cmd_close, cmd_close_all
"""

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from ._base import with_error_handling
from ..validators import InputValidator

logger = logging.getLogger(__name__)


class ActionCommandsMixin:
    """수동 실행 / 포지션 관리 명령어 모음"""

    async def cmd_run_screening(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """스크리닝 수동 실행"""
        from src.core import get_controller

        controller = get_controller()
        result = controller.run_screening()

        if result['success']:
            await update.message.reply_text(
                "🔍 <b>스크리닝 시작</b>\n완료되면 결과가 전송됩니다.",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(f"❌ {result['message']}")

    @with_error_handling("리밸런싱")
    async def cmd_run_rebalance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """리밸런싱 수동 실행"""
        from src.core import get_controller

        if not self._rebalance_lock.acquire(blocking=False):
            await update.message.reply_text("⏳ 리밸런싱이 이미 진행 중입니다. 완료될 때까지 기다려주세요.")
            return

        await update.message.reply_text(
            "🔄 <b>리밸런싱 요청 접수</b>\n스크리닝 → 주문 생성 → 실행 순으로 진행됩니다.",
            parse_mode='HTML'
        )

        try:
            controller = get_controller()
            result = await asyncio.to_thread(controller.run_rebalance)

            if result['success']:
                orders = result.get('orders', 0)
                await update.message.reply_text(
                    f"✅ <b>리밸런싱 완료</b>\n주문 {orders}건 처리됨",
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(f"❌ {result['message']}")
        finally:
            self._rebalance_lock.release()

    async def cmd_run_optimize(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """최적화 수동 실행"""
        from src.core import get_controller

        controller = get_controller()
        controller.run_optimize()

        await update.message.reply_text(
            "🔧 <b>최적화 시작</b>\n"
            "━━━━━━━━━━━━━━━\n"
            "팩터 가중치 최적화가 시작되었습니다.\n"
            "완료되면 결과가 전송됩니다.\n"
            "(약 5~10분 소요)",
            parse_mode='HTML'
        )

    @with_error_handling("긴급 리밸런싱")
    async def cmd_rebalance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """긴급 리밸런싱 (보유 종목 부족 시 부분 매수)"""
        from src.core import get_controller

        if not self._rebalance_lock.acquire(blocking=False):
            await update.message.reply_text("⏳ 리밸런싱이 이미 진행 중입니다. 완료될 때까지 기다려주세요.")
            return

        force = False
        if context.args and context.args[0].lower() == 'force':
            force = True

        await update.message.reply_text(
            "📢 <b>긴급 리밸런싱 요청 접수</b>\n스크리닝 → 부분 매수 순으로 진행됩니다.",
            parse_mode='HTML'
        )

        try:
            controller = get_controller()
            result = await asyncio.to_thread(controller.run_urgent_rebalance, force=force)

            if result['success']:
                message = result.get('message', '긴급 리밸런싱이 실행되었습니다.')
                buy_count = result.get('buy_count', 0)
                current_count = result.get('current_count', 0)

                if buy_count > 0:
                    await update.message.reply_text(
                        f"✅ <b>긴급 리밸런싱 완료</b>\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"• 매수 주문: {buy_count}건\n"
                        f"• 현재 보유: {current_count}개\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"{message}",
                        parse_mode='HTML'
                    )
                else:
                    await update.message.reply_text(
                        f"ℹ️ <b>긴급 리밸런싱</b>\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"{message}\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"• 현재 보유: {current_count}개\n"
                        f"• 추가 매수 불필요",
                        parse_mode='HTML'
                    )
            else:
                await update.message.reply_text(f"❌ {result['message']}")
        finally:
            self._rebalance_lock.release()

    @with_error_handling("장부 점검")
    async def cmd_reconcile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """장부 점검 수동 실행"""
        from src.core import get_controller

        controller = get_controller()
        await update.message.reply_text("🔍 장부 점검 중...")

        callback = controller.callbacks.get('on_reconcile')
        if callback:
            callback(force=True)
            await update.message.reply_text("✅ 장부 점검 완료 (결과는 위 메시지 참고)")
        else:
            await update.message.reply_text("❌ 점검 콜백 미등록. 엔진이 실행 중인지 확인하세요.")

    @with_error_handling("포지션 동기화")
    async def cmd_sync_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """KIS 포지션 동기화"""
        from src.core import get_controller

        controller = get_controller()

        await update.message.reply_text("🔄 KIS 포지션 동기화 중...")

        callback = controller.callbacks.get('sync_positions')
        if not callback:
            await update.message.reply_text("❌ 동기화 콜백이 등록되지 않았습니다. 엔진이 실행 중인지 확인하세요.")
            return

        result = callback()

        if result['success']:
            await update.message.reply_text(
                f"✅ <b>동기화 완료</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"{result['message']}\n"
                f"동기화 종목: {result.get('synced', 0)}개\n"
                f"━━━━━━━━━━━━━━━",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(f"❌ {result['message']}")

    async def cmd_close(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """특정 포지션 청산"""
        from src.core import get_controller

        if not context.args:
            await update.message.reply_text("사용법: /close [종목코드]\n예: /close 005930")
            return

        stock_code = context.args[0]

        is_valid, error_msg = InputValidator.validate_stock_code(stock_code)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_msg}")
            return

        controller = get_controller()
        result = controller.close_position(stock_code)

        if result['success']:
            await update.message.reply_text(
                f"🔴 <b>{stock_code} 청산 요청</b>\n체결되면 알림이 전송됩니다.",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(f"❌ {result['message']}")

    async def cmd_close_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """전체 포지션 청산"""
        from src.core import get_controller

        controller = get_controller()
        result = controller.close_all_positions()

        if result['success']:
            await update.message.reply_text(
                f"🔴 <b>전체 청산 요청</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"{result['message']}\n"
                f"체결되면 알림이 전송됩니다.\n"
                f"━━━━━━━━━━━━━━━",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(f"❌ {result['message']}")
