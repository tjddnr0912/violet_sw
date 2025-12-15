"""
텔레그램 봇 모듈
- 거래 알림 전송
- 명령어 처리 (잔고, 시세 조회 등)
"""

import os
import asyncio
import logging
from datetime import datetime
from typing import Optional, Callable, Dict, Any
from enum import Enum

from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from dotenv import load_dotenv

load_dotenv()

# 로깅 설정
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class NotificationType(Enum):
    """알림 유형"""
    BUY = "매수"
    SELL = "매도"
    MODIFY = "정정"
    CANCEL = "취소"
    INFO = "정보"
    ERROR = "오류"
    SYSTEM = "시스템"


class TelegramNotifier:
    """텔레그램 알림 전송 클래스 (단방향 알림용)"""

    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self._bot: Optional[Bot] = None

    @property
    def bot(self) -> Bot:
        """Bot 인스턴스 반환 (Lazy initialization)"""
        if self._bot is None:
            if not self.bot_token:
                raise ValueError("TELEGRAM_BOT_TOKEN 환경변수가 설정되지 않았습니다.")
            self._bot = Bot(token=self.bot_token)
        return self._bot

    def validate_config(self) -> bool:
        """설정 유효성 검증"""
        if not self.bot_token:
            logger.error("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")
            return False
        if not self.chat_id:
            logger.error("TELEGRAM_CHAT_ID가 설정되지 않았습니다.")
            return False
        return True

    async def send_message_async(self, message: str) -> bool:
        """비동기 메시지 전송"""
        if not self.validate_config():
            return False

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='HTML'
            )
            return True
        except Exception as e:
            logger.error(f"메시지 전송 실패: {e}")
            return False

    def send_message(self, message: str) -> bool:
        """동기 메시지 전송 (편의 메서드)"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 이미 이벤트 루프가 실행 중인 경우
                future = asyncio.ensure_future(self.send_message_async(message))
                return True  # 비동기로 전송됨
            else:
                return loop.run_until_complete(self.send_message_async(message))
        except RuntimeError:
            # 새 이벤트 루프 생성
            return asyncio.run(self.send_message_async(message))

    def _format_notification(
        self,
        notification_type: NotificationType,
        title: str,
        details: Dict[str, Any]
    ) -> str:
        """알림 메시지 포맷팅"""
        # 아이콘 매핑
        icons = {
            NotificationType.BUY: "🟢",
            NotificationType.SELL: "🔴",
            NotificationType.MODIFY: "🟡",
            NotificationType.CANCEL: "⚪",
            NotificationType.INFO: "ℹ️",
            NotificationType.ERROR: "❌",
            NotificationType.SYSTEM: "⚙️"
        }

        icon = icons.get(notification_type, "📌")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 메시지 구성
        lines = [
            f"{icon} <b>[{notification_type.value}] {title}</b>",
            f"━━━━━━━━━━━━━━━"
        ]

        for key, value in details.items():
            lines.append(f"• {key}: <code>{value}</code>")

        lines.append(f"━━━━━━━━━━━━━━━")
        lines.append(f"🕐 {timestamp}")

        return "\n".join(lines)

    # ========== 거래 알림 메서드 ==========

    def notify_buy(
        self,
        stock_name: str,
        stock_code: str,
        qty: int,
        price: int,
        order_no: str = ""
    ) -> bool:
        """매수 알림"""
        details = {
            "종목": f"{stock_name} ({stock_code})",
            "수량": f"{qty:,}주",
            "가격": f"{price:,}원",
            "총액": f"{qty * price:,}원"
        }
        if order_no:
            details["주문번호"] = order_no

        message = self._format_notification(
            NotificationType.BUY,
            "매수 주문",
            details
        )
        return self.send_message(message)

    def notify_sell(
        self,
        stock_name: str,
        stock_code: str,
        qty: int,
        price: int,
        order_no: str = ""
    ) -> bool:
        """매도 알림"""
        details = {
            "종목": f"{stock_name} ({stock_code})",
            "수량": f"{qty:,}주",
            "가격": f"{price:,}원",
            "총액": f"{qty * price:,}원"
        }
        if order_no:
            details["주문번호"] = order_no

        message = self._format_notification(
            NotificationType.SELL,
            "매도 주문",
            details
        )
        return self.send_message(message)

    def notify_order_filled(
        self,
        order_type: str,
        stock_name: str,
        stock_code: str,
        qty: int,
        price: int
    ) -> bool:
        """체결 알림"""
        notification_type = NotificationType.BUY if order_type == "매수" else NotificationType.SELL
        details = {
            "종목": f"{stock_name} ({stock_code})",
            "체결수량": f"{qty:,}주",
            "체결가격": f"{price:,}원",
            "체결금액": f"{qty * price:,}원"
        }

        message = self._format_notification(
            notification_type,
            f"{order_type} 체결 완료",
            details
        )
        return self.send_message(message)

    def notify_cancel(
        self,
        stock_name: str,
        stock_code: str,
        qty: int,
        reason: str = ""
    ) -> bool:
        """취소 알림"""
        details = {
            "종목": f"{stock_name} ({stock_code})",
            "취소수량": f"{qty:,}주"
        }
        if reason:
            details["사유"] = reason

        message = self._format_notification(
            NotificationType.CANCEL,
            "주문 취소",
            details
        )
        return self.send_message(message)

    def notify_error(self, title: str, error_msg: str) -> bool:
        """오류 알림"""
        message = self._format_notification(
            NotificationType.ERROR,
            title,
            {"오류내용": error_msg}
        )
        return self.send_message(message)

    def notify_system(self, title: str, details: Dict[str, Any]) -> bool:
        """시스템 알림"""
        message = self._format_notification(
            NotificationType.SYSTEM,
            title,
            details
        )
        return self.send_message(message)

    def notify_balance(
        self,
        cash: int,
        total_eval: int,
        total_profit: int,
        profit_rate: float,
        stocks: list
    ) -> bool:
        """잔고 현황 알림"""
        lines = [
            "💰 <b>[잔고 현황]</b>",
            "━━━━━━━━━━━━━━━",
            f"• 예수금: <code>{cash:,}원</code>",
            f"• 총평가: <code>{total_eval:,}원</code>",
            f"• 총손익: <code>{total_profit:+,}원</code>",
            f"• 수익률: <code>{profit_rate:+.2f}%</code>",
            "━━━━━━━━━━━━━━━"
        ]

        if stocks:
            lines.append("<b>보유종목:</b>")
            for stock in stocks[:5]:  # 최대 5개만 표시
                profit_emoji = "📈" if stock.profit >= 0 else "📉"
                lines.append(
                    f"  {profit_emoji} {stock.name}: "
                    f"{stock.qty}주 / {stock.profit_rate:+.2f}%"
                )
            if len(stocks) > 5:
                lines.append(f"  ... 외 {len(stocks) - 5}종목")

        lines.append(f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return self.send_message("\n".join(lines))


class TelegramBot:
    """텔레그램 봇 클래스 (양방향 명령어 처리용)"""

    def __init__(self, kis_client=None):
        """
        Args:
            kis_client: KISClient 인스턴스 (명령어에서 API 호출용)
        """
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.kis_client = kis_client
        self.application: Optional[Application] = None
        self.notifier = TelegramNotifier()

    def validate_config(self) -> bool:
        """설정 유효성 검증"""
        return self.notifier.validate_config()

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """시작 명령어"""
        message = (
            "🤖 <b>주식 자동매매 봇</b>\n\n"
            "사용 가능한 명령어:\n"
            "/잔고 - 계좌 잔고 조회\n"
            "/시세 [종목코드] - 현재가 조회\n"
            "/상태 - 시스템 상태 확인\n"
            "/도움말 - 명령어 도움말"
        )
        await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """도움말 명령어"""
        message = (
            "📚 <b>명령어 도움말</b>\n\n"
            "<b>조회 명령어:</b>\n"
            "/잔고 - 계좌 잔고 및 보유종목 조회\n"
            "/시세 005930 - 종목 현재가 조회\n"
            "/주문내역 - 당일 주문내역 조회\n\n"
            "<b>시스템 명령어:</b>\n"
            "/상태 - 봇 상태 확인\n"
            "/도움말 - 이 도움말 표시"
        )
        await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """잔고 조회 명령어"""
        if not self.kis_client:
            await update.message.reply_text("❌ API 클라이언트가 연결되지 않았습니다.")
            return

        try:
            balance = self.kis_client.get_balance()

            lines = [
                "💰 <b>계좌 잔고</b>",
                "━━━━━━━━━━━━━━━",
                f"예수금: <code>{balance['cash']:,}원</code>",
                f"총평가: <code>{balance['total_eval']:,}원</code>",
                f"총손익: <code>{balance['total_profit']:+,}원</code>",
                "━━━━━━━━━━━━━━━"
            ]

            if balance['stocks']:
                lines.append("\n<b>보유종목:</b>")
                for stock in balance['stocks']:
                    emoji = "📈" if stock.profit >= 0 else "📉"
                    lines.append(
                        f"{emoji} <b>{stock.name}</b>\n"
                        f"   {stock.qty}주 × {stock.current_price:,}원\n"
                        f"   손익: {stock.profit:+,}원 ({stock.profit_rate:+.2f}%)"
                    )
            else:
                lines.append("\n보유종목 없음")

            await update.message.reply_text("\n".join(lines), parse_mode='HTML')

        except Exception as e:
            await update.message.reply_text(f"❌ 잔고 조회 실패: {e}")

    async def cmd_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """시세 조회 명령어"""
        if not self.kis_client:
            await update.message.reply_text("❌ API 클라이언트가 연결되지 않았습니다.")
            return

        if not context.args:
            await update.message.reply_text("사용법: /시세 [종목코드]\n예: /시세 005930")
            return

        stock_code = context.args[0]

        try:
            price = self.kis_client.get_stock_price(stock_code)

            change_emoji = "🔺" if price.change > 0 else ("🔻" if price.change < 0 else "➖")

            message = (
                f"📊 <b>{price.name}</b> ({price.code})\n"
                f"━━━━━━━━━━━━━━━\n"
                f"현재가: <code>{price.price:,}원</code>\n"
                f"전일비: {change_emoji} <code>{price.change:+,}원</code> ({price.change_rate:+.2f}%)\n"
                f"━━━━━━━━━━━━━━━\n"
                f"시가: {price.open:,}원\n"
                f"고가: {price.high:,}원\n"
                f"저가: {price.low:,}원\n"
                f"거래량: {price.volume:,}주"
            )

            await update.message.reply_text(message, parse_mode='HTML')

        except Exception as e:
            await update.message.reply_text(f"❌ 시세 조회 실패: {e}")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """시스템 상태 명령어"""
        api_status = "🟢 연결됨" if self.kis_client else "🔴 미연결"

        message = (
            "⚙️ <b>시스템 상태</b>\n"
            "━━━━━━━━━━━━━━━\n"
            f"• 봇 상태: 🟢 정상\n"
            f"• API 연결: {api_status}\n"
            f"• 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """주문내역 조회 명령어"""
        if not self.kis_client:
            await update.message.reply_text("❌ API 클라이언트가 연결되지 않았습니다.")
            return

        try:
            orders = self.kis_client.get_order_history()

            if not orders:
                await update.message.reply_text("📋 당일 주문내역이 없습니다.")
                return

            lines = ["📋 <b>당일 주문내역</b>", "━━━━━━━━━━━━━━━"]

            for order in orders[:10]:  # 최대 10개
                emoji = "🟢" if order['side'] == "매수" else "🔴"
                lines.append(
                    f"{emoji} <b>{order['name']}</b>\n"
                    f"   {order['side']} {order['qty']}주 × {order['price']:,}원\n"
                    f"   체결: {order['filled_qty']}주 | {order['status']}"
                )

            await update.message.reply_text("\n".join(lines), parse_mode='HTML')

        except Exception as e:
            await update.message.reply_text(f"❌ 주문내역 조회 실패: {e}")

    def build_application(self) -> Application:
        """Application 빌드"""
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")

        self.application = Application.builder().token(self.bot_token).build()

        # 명령어 핸들러 등록
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("도움말", self.cmd_help))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("잔고", self.cmd_balance))
        self.application.add_handler(CommandHandler("balance", self.cmd_balance))
        self.application.add_handler(CommandHandler("시세", self.cmd_price))
        self.application.add_handler(CommandHandler("price", self.cmd_price))
        self.application.add_handler(CommandHandler("상태", self.cmd_status))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("주문내역", self.cmd_orders))
        self.application.add_handler(CommandHandler("orders", self.cmd_orders))

        return self.application

    def run(self):
        """봇 실행 (블로킹)"""
        app = self.build_application()
        logger.info("텔레그램 봇 시작...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


# 싱글톤 인스턴스
_notifier_instance: Optional[TelegramNotifier] = None


def get_notifier() -> TelegramNotifier:
    """알림 인스턴스 반환 (싱글톤)"""
    global _notifier_instance
    if _notifier_instance is None:
        _notifier_instance = TelegramNotifier()
    return _notifier_instance
