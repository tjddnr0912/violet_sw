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
from pathlib import Path

# 프로젝트 루트의 .env 파일 명시적 로드
project_root = Path(__file__).parent.parent.parent
env_path = project_root / ".env"
load_dotenv(env_path, override=True)

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
    # 퀀트 전략 알림 유형
    SCREENING = "스크리닝"
    SIGNAL = "신호"
    REBALANCE = "리밸런싱"
    RISK = "리스크"
    STOP_LOSS = "손절"
    TAKE_PROFIT = "익절"


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
            NotificationType.SYSTEM: "⚙️",
            NotificationType.SCREENING: "🔍",
            NotificationType.SIGNAL: "📊",
            NotificationType.REBALANCE: "🔄",
            NotificationType.RISK: "⚠️",
            NotificationType.STOP_LOSS: "🛑",
            NotificationType.TAKE_PROFIT: "🎯"
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

    # ========== 퀀트 전략 알림 메서드 ==========

    def notify_screening_result(
        self,
        top_stocks: list,
        total_screened: int,
        passed_filter: int
    ) -> bool:
        """스크리닝 결과 알림"""
        lines = [
            "🔍 <b>[스크리닝 완료]</b>",
            "━━━━━━━━━━━━━━━",
            f"• 분석 종목: <code>{total_screened}개</code>",
            f"• 필터 통과: <code>{passed_filter}개</code>",
            "━━━━━━━━━━━━━━━",
            "<b>상위 종목:</b>"
        ]

        for i, stock in enumerate(top_stocks[:5], 1):
            score = stock.get('score', stock.get('composite_score', 0))
            name = stock.get('name', '')[:8]
            code = stock.get('code', '')
            lines.append(
                f"  {i}. <b>{name}</b> ({code})\n"
                f"     점수: {score:.1f} | 12M: {stock.get('return_12m', 0):+.1f}%"
            )

        lines.append(f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return self.send_message("\n".join(lines))

    def notify_buy_signal(
        self,
        stock_name: str,
        stock_code: str,
        signal_type: str,
        score: float,
        price: int,
        stop_loss: int,
        take_profit: int,
        reason: str = ""
    ) -> bool:
        """매수 신호 알림"""
        signal_emoji = "🟢" if "STRONG" in signal_type else "🔵"

        lines = [
            f"{signal_emoji} <b>[매수 신호] {stock_name}</b>",
            "━━━━━━━━━━━━━━━",
            f"• 종목: <code>{stock_name} ({stock_code})</code>",
            f"• 신호: <code>{signal_type}</code>",
            f"• 점수: <code>{score:.1f}/100</code>",
            f"• 현재가: <code>{price:,}원</code>",
            "━━━━━━━━━━━━━━━",
            f"• 손절가: <code>{stop_loss:,}원</code> ({(stop_loss/price-1)*100:+.1f}%)",
            f"• 익절가: <code>{take_profit:,}원</code> ({(take_profit/price-1)*100:+.1f}%)"
        ]

        if reason:
            lines.append(f"• 사유: {reason}")

        lines.append(f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return self.send_message("\n".join(lines))

    def notify_sell_signal(
        self,
        stock_name: str,
        stock_code: str,
        signal_type: str,
        current_price: int,
        entry_price: int,
        reason: str = ""
    ) -> bool:
        """매도 신호 알림"""
        pnl_pct = (current_price / entry_price - 1) * 100
        pnl_emoji = "📈" if pnl_pct >= 0 else "📉"

        lines = [
            f"🔴 <b>[매도 신호] {stock_name}</b>",
            "━━━━━━━━━━━━━━━",
            f"• 종목: <code>{stock_name} ({stock_code})</code>",
            f"• 신호: <code>{signal_type}</code>",
            f"• 매입가: <code>{entry_price:,}원</code>",
            f"• 현재가: <code>{current_price:,}원</code>",
            f"• 수익률: {pnl_emoji} <code>{pnl_pct:+.1f}%</code>"
        ]

        if reason:
            lines.append(f"• 사유: {reason}")

        lines.append(f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return self.send_message("\n".join(lines))

    def notify_stop_loss(
        self,
        stock_name: str,
        stock_code: str,
        entry_price: int,
        stop_price: int,
        qty: int
    ) -> bool:
        """손절 알림"""
        loss_pct = (stop_price / entry_price - 1) * 100
        loss_amount = (stop_price - entry_price) * qty

        lines = [
            f"🛑 <b>[손절 실행] {stock_name}</b>",
            "━━━━━━━━━━━━━━━",
            f"• 종목: <code>{stock_name} ({stock_code})</code>",
            f"• 수량: <code>{qty:,}주</code>",
            f"• 매입가: <code>{entry_price:,}원</code>",
            f"• 손절가: <code>{stop_price:,}원</code>",
            "━━━━━━━━━━━━━━━",
            f"• 손실률: <code>{loss_pct:+.1f}%</code>",
            f"• 손실금액: <code>{loss_amount:+,}원</code>",
            f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ]

        return self.send_message("\n".join(lines))

    def notify_take_profit(
        self,
        stock_name: str,
        stock_code: str,
        entry_price: int,
        sell_price: int,
        qty: int,
        stage: int = 1
    ) -> bool:
        """익절 알림"""
        profit_pct = (sell_price / entry_price - 1) * 100
        profit_amount = (sell_price - entry_price) * qty

        lines = [
            f"🎯 <b>[익절 실행] {stock_name}</b> ({stage}차)",
            "━━━━━━━━━━━━━━━",
            f"• 종목: <code>{stock_name} ({stock_code})</code>",
            f"• 수량: <code>{qty:,}주</code>",
            f"• 매입가: <code>{entry_price:,}원</code>",
            f"• 매도가: <code>{sell_price:,}원</code>",
            "━━━━━━━━━━━━━━━",
            f"• 수익률: <code>{profit_pct:+.1f}%</code>",
            f"• 수익금액: <code>{profit_amount:+,}원</code>",
            f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ]

        return self.send_message("\n".join(lines))

    def notify_rebalance(
        self,
        sells: list,
        buys: list,
        portfolio_value: int
    ) -> bool:
        """리밸런싱 알림"""
        lines = [
            "🔄 <b>[리밸런싱 실행]</b>",
            "━━━━━━━━━━━━━━━",
            f"• 포트폴리오: <code>{portfolio_value:,}원</code>",
            ""
        ]

        if sells:
            lines.append("<b>매도 종목:</b>")
            for s in sells[:3]:
                lines.append(f"  🔴 {s['name']} ({s.get('pnl_pct', 0):+.1f}%)")

        if buys:
            lines.append("<b>매수 종목:</b>")
            for b in buys[:3]:
                lines.append(f"  🟢 {b['name']} ({b.get('weight', 0)*100:.1f}%)")

        lines.append(f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return self.send_message("\n".join(lines))

    def notify_risk_alert(
        self,
        alert_type: str,
        current_value: float,
        threshold: float,
        message: str = ""
    ) -> bool:
        """리스크 경고 알림"""
        lines = [
            "⚠️ <b>[리스크 경고]</b>",
            "━━━━━━━━━━━━━━━",
            f"• 유형: <code>{alert_type}</code>",
            f"• 현재값: <code>{current_value:.1f}%</code>",
            f"• 기준값: <code>{threshold:.1f}%</code>"
        ]

        if message:
            lines.append(f"• 상세: {message}")

        lines.append(f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return self.send_message("\n".join(lines))

    def notify_daily_report(
        self,
        date: str,
        starting_value: int,
        ending_value: int,
        daily_pnl: int,
        trades_count: int,
        positions: list
    ) -> bool:
        """일일 리포트 알림"""
        daily_return = (ending_value / starting_value - 1) * 100 if starting_value > 0 else 0
        return_emoji = "📈" if daily_return >= 0 else "📉"

        lines = [
            f"📋 <b>[일일 리포트] {date}</b>",
            "━━━━━━━━━━━━━━━",
            f"• 시작 자산: <code>{starting_value:,}원</code>",
            f"• 종료 자산: <code>{ending_value:,}원</code>",
            f"• 일일 손익: {return_emoji} <code>{daily_pnl:+,}원</code>",
            f"• 수익률: <code>{daily_return:+.2f}%</code>",
            f"• 거래 횟수: <code>{trades_count}회</code>",
            "━━━━━━━━━━━━━━━"
        ]

        if positions:
            lines.append("<b>보유 종목:</b>")
            for p in positions[:5]:
                pnl_emoji = "📈" if p.get('pnl_pct', 0) >= 0 else "📉"
                lines.append(
                    f"  {pnl_emoji} {p['name']}: {p.get('pnl_pct', 0):+.1f}%"
                )

        lines.append(f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return self.send_message("\n".join(lines))

    def notify_technical_signal(
        self,
        stock_name: str,
        stock_code: str,
        signal_type: str,
        score: float,
        rsi: float,
        macd_signal: str,
        trend: str
    ) -> bool:
        """기술적 분석 신호 알림"""
        signal_emoji = {
            "STRONG_BUY": "🟢",
            "BUY": "🔵",
            "HOLD": "⚪",
            "SELL": "🟠",
            "STRONG_SELL": "🔴"
        }.get(signal_type, "⚪")

        lines = [
            f"📊 <b>[기술적 신호] {stock_name}</b>",
            "━━━━━━━━━━━━━━━",
            f"• 종목: <code>{stock_name} ({stock_code})</code>",
            f"• 신호: {signal_emoji} <code>{signal_type}</code>",
            f"• 점수: <code>{score:.0f}/100</code>",
            "━━━━━━━━━━━━━━━",
            f"• RSI: <code>{rsi:.1f}</code>",
            f"• MACD: <code>{macd_signal}</code>",
            f"• 추세: <code>{trend}</code>",
            f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ]

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
            "/balance - 계좌 잔고 조회\n"
            "/price [종목코드] - 현재가 조회\n"
            "/screening - 멀티팩터 스크리닝\n"
            "/signal [종목코드] - 기술적 분석\n"
            "/status - 시스템 상태 확인\n"
            "/help - 명령어 도움말"
        )
        await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """도움말 명령어"""
        message = (
            "📚 <b>명령어 도움말</b>\n\n"
            "<b>조회 명령어:</b>\n"
            "/balance - 계좌 잔고 및 보유종목 조회\n"
            "/price 005930 - 종목 현재가 조회\n"
            "/orders - 당일 주문내역 조회\n\n"
            "<b>퀀트 전략:</b>\n"
            "/screening - 멀티팩터 종목 스크리닝\n"
            "/signal 005930 - 기술적 분석 신호\n\n"
            "<b>시스템 명령어:</b>\n"
            "/status - 봇 상태 확인\n"
            "/help - 이 도움말 표시"
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

    async def cmd_screening(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """스크리닝 명령어"""
        await update.message.reply_text("🔍 스크리닝 실행 중... 잠시만 기다려주세요.")

        try:
            from src.api.kis_quant import KISQuantClient
            from src.strategy.quant import CompositeScoreCalculator, TechnicalAnalyzer
            import time

            client = KISQuantClient()
            score_calc = CompositeScoreCalculator()
            analyzer = TechnicalAnalyzer()

            # 시가총액 상위 종목 조회
            rankings = client.get_market_cap_ranking(count=20)

            scores = []
            for r in rankings:
                if r.code.endswith("5"):  # 우선주 제외
                    continue

                try:
                    ratio = client.get_financial_ratio_ext(r.code)
                    momentum = client.calculate_momentum(r.code)

                    score = score_calc.calculate(
                        code=r.code,
                        name=r.name,
                        per=ratio.per,
                        pbr=ratio.pbr,
                        roe=ratio.roe,
                        return_1m=momentum.return_1m,
                        return_3m=momentum.return_3m,
                        return_6m=momentum.return_6m,
                        return_12m=momentum.return_12m,
                        distance_from_high=momentum.distance_from_high,
                        volatility=momentum.volatility_20d,
                        market_cap=r.market_cap
                    )

                    if score.passed_filter:
                        # 기술적 분석
                        prices = client.get_daily_prices(r.code, count=60)
                        closes = [p.close for p in prices]
                        tech = analyzer.analyze(closes)

                        scores.append({
                            "code": r.code,
                            "name": r.name,
                            "composite_score": score.composite_score,
                            "return_12m": momentum.return_12m,
                            "per": ratio.per,
                            "tech_score": tech.score,
                            "tech_signal": tech.signal_type.value,
                            "price": prices[0].close
                        })

                    time.sleep(0.05)

                except Exception:
                    continue

            # 정렬
            scores.sort(key=lambda x: x["composite_score"], reverse=True)

            # 결과 메시지
            lines = [
                "🔍 <b>[스크리닝 결과]</b>",
                f"━━━━━━━━━━━━━━━",
                f"• 분석: {len(rankings)}개 → 통과: {len(scores)}개",
                "━━━━━━━━━━━━━━━",
                ""
            ]

            for i, s in enumerate(scores[:8], 1):
                signal_emoji = {
                    "STRONG_BUY": "🟢",
                    "BUY": "🔵",
                    "HOLD": "⚪",
                    "SELL": "🟠",
                    "STRONG_SELL": "🔴"
                }.get(s["tech_signal"], "⚪")

                lines.append(
                    f"<b>{i}. {s['name']}</b> ({s['code']})\n"
                    f"   복합: {s['composite_score']:.1f} | 기술: {signal_emoji} {s['tech_score']:.0f}\n"
                    f"   PER: {s['per']:.1f} | 12M: {s['return_12m']:+.1f}%\n"
                    f"   현재가: {s['price']:,}원"
                )

            lines.append(f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            await update.message.reply_text("\n".join(lines), parse_mode='HTML')

        except Exception as e:
            await update.message.reply_text(f"❌ 스크리닝 실패: {e}")

    async def cmd_signal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """기술적 분석 신호 명령어"""
        if not context.args:
            await update.message.reply_text("사용법: /신호 [종목코드]\n예: /신호 005930")
            return

        stock_code = context.args[0]

        try:
            from src.api.kis_quant import KISQuantClient
            from src.strategy.quant import TechnicalAnalyzer

            client = KISQuantClient()
            analyzer = TechnicalAnalyzer()

            # 가격 데이터 조회
            prices_data = client.get_daily_prices(stock_code, count=100)
            ratio = client.get_financial_ratio_ext(stock_code)

            closes = [p.close for p in prices_data]
            current_price = closes[0]

            # 기술적 분석
            signal = analyzer.analyze(closes)

            # 이동평균
            ma5 = analyzer.calculate_ma(closes, 5)
            ma20 = analyzer.calculate_ma(closes, 20)
            ma60 = analyzer.calculate_ma(closes, 60)

            # 추세 판단
            if current_price > ma20 > ma60:
                trend = "상승 ↑"
            elif current_price < ma20 < ma60:
                trend = "하락 ↓"
            else:
                trend = "횡보 →"

            signal_emoji = {
                "STRONG_BUY": "🟢 강력매수",
                "BUY": "🔵 매수",
                "HOLD": "⚪ 관망",
                "SELL": "🟠 매도",
                "STRONG_SELL": "🔴 강력매도"
            }.get(signal.signal_type.value, "⚪")

            # 손절/익절가
            stop_loss = int(current_price * 0.93)
            take_profit = int(current_price * 1.10)

            message = (
                f"📊 <b>[기술적 분석] {ratio.name}</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"• 현재가: <code>{current_price:,}원</code>\n"
                f"• 추세: <code>{trend}</code>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"• 신호: {signal_emoji}\n"
                f"• 점수: <code>{signal.score:.0f}/100</code>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"• RSI: <code>{signal.rsi:.1f}</code>\n"
                f"• MACD: <code>{signal.macd_signal}</code>\n"
                f"• MA: <code>{signal.ma_signal}</code>\n"
                f"• BB: <code>{signal.bb_signal}</code>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"• MA5: {ma5:,.0f} | MA20: {ma20:,.0f}\n"
                f"• 손절가: <code>{stop_loss:,}원</code> (-7%)\n"
                f"• 익절가: <code>{take_profit:,}원</code> (+10%)"
            )

            await update.message.reply_text(message, parse_mode='HTML')

        except Exception as e:
            await update.message.reply_text(f"❌ 분석 실패: {e}")

    def build_application(self) -> Application:
        """Application 빌드"""
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")

        self.application = Application.builder().token(self.bot_token).build()

        # 명령어 핸들러 등록 (영문만 지원)
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("balance", self.cmd_balance))
        self.application.add_handler(CommandHandler("price", self.cmd_price))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("orders", self.cmd_orders))
        # 퀀트 전략 명령어
        self.application.add_handler(CommandHandler("screening", self.cmd_screening))
        self.application.add_handler(CommandHandler("signal", self.cmd_signal))

        return self.application

    def run(self):
        """봇 실행 (블로킹)"""
        app = self.build_application()
        logger.info("텔레그램 봇 시작...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


class TelegramBotHandler:
    """데몬용 텔레그램 봇 핸들러 (스레드 안전)"""

    def __init__(self, kis_client=None):
        self.bot = TelegramBot(kis_client=kis_client)
        self.running = False
        self._loop = None

    def start(self):
        """봇 시작 (블로킹)"""
        self.running = True
        logger.info("텔레그램 봇 핸들러 시작...")

        try:
            app = self.bot.build_application()
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            # 시작 알림 전송
            self.bot.notifier.send_message("🤖 텔레그램 봇이 시작되었습니다.\n/help 명령어로 사용법을 확인하세요.")

            # 폴링 시작
            self._loop.run_until_complete(app.initialize())
            self._loop.run_until_complete(app.start())
            self._loop.run_until_complete(app.updater.start_polling(allowed_updates=Update.ALL_TYPES))

            # 무한 대기
            while self.running:
                self._loop.run_until_complete(asyncio.sleep(1))

        except Exception as e:
            logger.error(f"텔레그램 봇 오류: {e}")
        finally:
            self.stop()

    def stop(self):
        """봇 중지"""
        self.running = False
        if self._loop and self.bot.application:
            try:
                self._loop.run_until_complete(self.bot.application.updater.stop())
                self._loop.run_until_complete(self.bot.application.stop())
                self._loop.run_until_complete(self.bot.application.shutdown())
            except Exception as e:
                logger.error(f"봇 종료 오류: {e}")
        logger.info("텔레그램 봇 핸들러 종료됨")


# 싱글톤 인스턴스
_notifier_instance: Optional[TelegramNotifier] = None


def get_notifier() -> TelegramNotifier:
    """알림 인스턴스 반환 (싱글톤)"""
    global _notifier_instance
    if _notifier_instance is None:
        _notifier_instance = TelegramNotifier()
    return _notifier_instance
