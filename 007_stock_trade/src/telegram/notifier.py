"""
텔레그램 알림 전송 클래스 (단방향 알림용)
"""

import os
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

from telegram import Bot
from dotenv import load_dotenv
from pathlib import Path

# 프로젝트 루트의 .env 파일 명시적 로드
project_root = Path(__file__).parent.parent.parent
env_path = project_root / ".env"
load_dotenv(env_path, override=True)

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
            error_str = str(e)
            # 일시적/무시 가능한 에러는 간단히 로깅
            if "Event loop is closed" in error_str:
                logger.debug("메시지 전송 스킵 (종료 중)")
            elif "Timed out" in error_str or "ConnectTimeout" in error_str:
                logger.warning("메시지 전송 타임아웃 (네트워크 지연)")
            elif "Conflict" in error_str:
                logger.warning("메시지 전송 충돌 (다른 봇 인스턴스 실행 중)")
            else:
                # 심각한 에러만 traceback 출력
                logger.error(f"메시지 전송 실패: {e}", exc_info=True)
            return False

    def send_message(self, message: str) -> bool:
        """동기 메시지 전송 (편의 메서드)"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 이미 이벤트 루프가 실행 중인 경우
                asyncio.ensure_future(self.send_message_async(message))
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
            "━━━━━━━━━━━━━━━"
        ]

        for key, value in details.items():
            lines.append(f"• {key}: <code>{value}</code>")

        lines.append("━━━━━━━━━━━━━━━")
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


# 싱글톤 인스턴스 (편의 함수)
_notifier_instance: Optional[TelegramNotifier] = None


def get_notifier() -> TelegramNotifier:
    """싱글톤 TelegramNotifier 인스턴스 반환"""
    global _notifier_instance
    if _notifier_instance is None:
        _notifier_instance = TelegramNotifier()
    return _notifier_instance
