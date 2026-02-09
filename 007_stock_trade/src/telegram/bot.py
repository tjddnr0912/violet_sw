"""
텔레그램 봇 모듈
- 거래 알림 전송
- 명령어 처리 (잔고, 시세 조회 등)
"""

import os
import asyncio
import logging
import time
import json
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from dotenv import load_dotenv

# 분리된 모듈에서 import
from .notifier import TelegramNotifier, NotificationType, get_notifier
from .validators import InputValidator

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

    # ==================== 기본 명령어 ====================

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """시작 명령어"""
        message = (
            "🤖 <b>퀀트 자동매매 봇</b>\n\n"
            "📋 /help - 전체 명령어 보기\n\n"
            "<b>주요 명령어:</b>\n"
            "/status - 시스템 상태\n"
            "/start_trading - 자동매매 시작\n"
            "/stop_trading - 자동매매 중지\n"
            "/positions - 보유 포지션\n"
            "/emergency_stop - 긴급 정지"
        )
        await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """도움말 명령어"""
        message = (
            "📚 <b>명령어 도움말</b>\n\n"
            "<b>🔧 시스템 제어:</b>\n"
            "/start_trading - 자동매매 시작\n"
            "/stop_trading - 자동매매 중지\n"
            "/pause - 일시 정지\n"
            "/resume - 재개\n"
            "/emergency_stop - 긴급 정지\n"
            "/clear_emergency - 긴급 정지 해제\n\n"
            "<b>🔄 수동 실행:</b>\n"
            "/run_screening - 스크리닝 실행\n"
            "/run_rebalance - 리밸런싱 실행\n"
            "/rebalance - 긴급 리밸런싱 (보유 부족 시)\n"
            "/run_optimize - 최적화 실행\n\n"
            "<b>⚙️ 설정 변경:</b>\n"
            "/set_dryrun on|off - Dry-run 모드\n"
            "/set_target [N] - 목표 종목 수\n"
            "/set_stoploss [N] - 손절 비율(%)\n\n"
            "<b>📊 조회:</b>\n"
            "/status - 시스템 상태\n"
            "/positions - 보유 포지션\n"
            "/balance - 계좌 잔고\n"
            "/history [N] - 자산 변동 (N일)\n"
            "/trades [N] - 거래 내역 (N일)\n"
            "/capital - 투자 원금 대비 현황\n"
            "/logs - 최근 로그\n"
            "/report - 일일 리포트\n"
            "/monthly_report - 월간 리포트\n\n"
            "<b>📈 분석:</b>\n"
            "/screening - 스크리닝 결과\n"
            "/signal [코드] - 기술적 분석\n"
            "/price [코드] - 현재가 조회"
        )
        await update.message.reply_text(message, parse_mode='HTML')

    # ==================== 조회 명령어 ====================

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """잔고 조회 명령어"""
        # API 클라이언트가 있으면 실시간 조회
        if self.kis_client:
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
                return

            except Exception as e:
                logger.warning(f"API 잔고 조회 실패, 파일에서 읽기 시도: {e}")

        # API 없거나 실패 시 engine_state.json에서 읽기
        try:
            state_file = Path(__file__).parent.parent.parent / "data" / "quant" / "engine_state.json"

            if not state_file.exists():
                await update.message.reply_text("❌ 잔고 데이터가 없습니다.\n데몬이 실행 중이 아닐 수 있습니다.")
                return

            with open(state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            positions = data.get("positions", [])

            if not positions:
                await update.message.reply_text("💰 보유 포지션이 없습니다.")
                return

            lines = [
                "💰 <b>계좌 잔고</b> (캐시 데이터)",
                "━━━━━━━━━━━━━━━",
                "⚠️ API 미연결 - 저장된 데이터 표시",
                "━━━━━━━━━━━━━━━"
            ]

            total_value = 0
            total_cost = 0
            total_pnl = 0

            lines.append("\n<b>보유종목:</b>")
            for pos in positions:
                entry_price = pos.get("entry_price", 0)
                current_price = pos.get("current_price", entry_price)
                quantity = pos.get("quantity", 0)

                position_value = current_price * quantity
                position_cost = entry_price * quantity
                pnl = position_value - position_cost
                pnl_pct = ((current_price / entry_price) - 1) * 100 if entry_price > 0 else 0

                total_value += position_value
                total_cost += position_cost
                total_pnl += pnl

                emoji = "📈" if pnl >= 0 else "📉"
                lines.append(
                    f"{emoji} <b>{pos.get('name', 'N/A')}</b>\n"
                    f"   {quantity}주 × {current_price:,}원\n"
                    f"   손익: {pnl:+,}원 ({pnl_pct:+.2f}%)"
                )

            lines.append("━━━━━━━━━━━━━━━")
            lines.append(f"총평가: <code>{total_value:,}원</code>")
            lines.append(f"총손익: <code>{total_pnl:+,}원</code>")

            # 업데이트 시간 표시
            updated_at = data.get("updated_at", "")
            if updated_at:
                lines.append(f"\n📅 마지막 업데이트: {updated_at[:19]}")

            await update.message.reply_text("\n".join(lines), parse_mode='HTML')

        except Exception as e:
            await update.message.reply_text(f"❌ 잔고 조회 실패: {e}")

    async def cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """일별 자산 변동 조회"""
        try:
            data_dir = Path(__file__).parent.parent.parent / "data" / "quant"
            history_file = data_dir / "daily_history.json"

            if not history_file.exists():
                await update.message.reply_text("❌ 일별 히스토리 데이터가 없습니다.\n15:20 일일 리포트 후 생성됩니다.")
                return

            with open(history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            initial_capital = data.get("initial_capital", 0)
            snapshots = data.get("snapshots", [])

            if not snapshots:
                await update.message.reply_text("❌ 저장된 스냅샷이 없습니다.")
                return

            # 일수 파라미터
            days = 7
            if context.args:
                try:
                    days = max(1, min(int(context.args[0]), 90))
                except ValueError:
                    pass

            # 최근 N일 필터링
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            recent = sorted(
                [s for s in snapshots if s["date"] >= cutoff],
                key=lambda s: s["date"],
                reverse=True
            )

            if not recent:
                await update.message.reply_text(f"❌ 최근 {days}일 내 데이터가 없습니다.")
                return

            lines = [
                f"📊 <b>자산 변동 (최근 {days}일)</b>",
                "━━━━━━━━━━━━━━━"
            ]

            if initial_capital > 0:
                lines.append(f"초기 투자금: <code>{initial_capital:,.0f}원</code>")
                lines.append("━━━━━━━━━━━━━━━")

            for s in recent:
                date_str = s["date"][5:]  # "02/09"
                total = s["total_assets"]
                d_pnl = s.get("daily_pnl", 0)
                d_pnl_pct = s.get("daily_pnl_pct", 0)
                trades = s.get("trades_today", 0)

                sign = "+" if d_pnl >= 0 else ""
                pct_sign = "+" if d_pnl_pct >= 0 else ""
                trade_str = f" [{trades}건]" if trades > 0 else ""

                lines.append(
                    f"{date_str}: <code>{total:,.0f}원</code>"
                    f" ({sign}{d_pnl:,.0f} / {pct_sign}{d_pnl_pct:.2f}%){trade_str}"
                )

            if initial_capital > 0:
                latest = recent[0]
                total_pnl = latest["total_assets"] - initial_capital
                total_pnl_pct = (total_pnl / initial_capital * 100) if initial_capital > 0 else 0
                sign = "+" if total_pnl >= 0 else ""
                lines.append("━━━━━━━━━━━━━━━")
                lines.append(f"총 수익: <b>{sign}{total_pnl:,.0f}원</b> ({sign}{total_pnl_pct:.1f}%)")

            await update.message.reply_text("\n".join(lines), parse_mode='HTML')

        except Exception as e:
            logger.error(f"히스토리 조회 실패: {e}", exc_info=True)
            await update.message.reply_text(f"❌ 히스토리 조회 실패: {e}")

    async def cmd_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """거래 내역 조회"""
        try:
            data_dir = Path(__file__).parent.parent.parent / "data" / "quant"
            tx_file = data_dir / "transaction_journal.json"

            if not tx_file.exists():
                await update.message.reply_text("❌ 거래 일지 데이터가 없습니다.\n거래 발생 시 자동 기록됩니다.")
                return

            with open(tx_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            transactions = data.get("transactions", [])

            if not transactions:
                await update.message.reply_text("❌ 기록된 거래가 없습니다.")
                return

            # 일수 파라미터
            days = 7
            if context.args:
                try:
                    days = max(1, min(int(context.args[0]), 90))
                except ValueError:
                    pass

            # 최근 N일 필터링
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            recent = sorted(
                [t for t in transactions if t["date"] >= cutoff],
                key=lambda t: t["timestamp"],
                reverse=True
            )

            if not recent:
                await update.message.reply_text(f"❌ 최근 {days}일 내 거래가 없습니다.")
                return

            lines = [
                f"📋 <b>거래 내역 (최근 {days}일)</b>",
                "━━━━━━━━━━━━━━━"
            ]

            buy_count = 0
            sell_count = 0

            for t in recent[:20]:  # 최대 20건 표시
                ts = t["timestamp"]
                date_str = ts[5:10]   # "02/09"
                time_str = ts[11:16]  # "09:00"
                tx_type = t["type"]

                if tx_type == "BUY":
                    emoji = "🟢"
                    buy_count += 1
                else:
                    emoji = "🔴"
                    sell_count += 1

                qty = t.get("quantity", 0)
                price = t.get("price", 0)

                lines.append(f"\n{date_str} {time_str}")
                lines.append(f"  {emoji} {t['name']} {qty}주 × {price:,.0f}원")

                reason = t.get("reason", "")
                if reason:
                    lines.append(f"  사유: {reason[:30]}")

                if tx_type == "SELL":
                    pnl = t.get("pnl", 0)
                    pnl_pct = t.get("pnl_pct", 0)
                    sign = "+" if pnl >= 0 else ""
                    lines.append(f"  손익: {sign}{pnl:,.0f}원 ({sign}{pnl_pct:.1f}%)")

            lines.append("\n━━━━━━━━━━━━━━━")
            total_shown = min(len(recent), 20)
            lines.append(f"총: 매수 {buy_count}건, 매도 {sell_count}건")
            if len(recent) > 20:
                lines.append(f"(최근 {total_shown}건만 표시, 전체 {len(recent)}건)")

            await update.message.reply_text("\n".join(lines), parse_mode='HTML')

        except Exception as e:
            logger.error(f"거래 내역 조회 실패: {e}", exc_info=True)
            await update.message.reply_text(f"❌ 거래 내역 조회 실패: {e}")

    async def cmd_capital(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """초기 투자금 대비 현황"""
        try:
            data_dir = Path(__file__).parent.parent.parent / "data" / "quant"
            history_file = data_dir / "daily_history.json"

            if not history_file.exists():
                await update.message.reply_text("❌ 일별 히스토리 데이터가 없습니다.\n15:20 일일 리포트 후 생성됩니다.")
                return

            with open(history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            initial_capital = data.get("initial_capital", 0)
            snapshots = data.get("snapshots", [])

            if not initial_capital:
                await update.message.reply_text("❌ 초기 투자금 정보가 없습니다.")
                return

            # 실시간 잔고 조회 시도
            total_assets = 0
            cash = 0
            invested = 0
            buy_amount = 0
            position_count = 0

            if self.kis_client:
                try:
                    balance = self.kis_client.get_balance()
                    total_assets = balance.get('total_eval', 0) + balance.get('cash', 0)
                    cash = balance.get('cash', 0)
                    invested = balance.get('total_eval', 0)
                    buy_amount = balance.get('buy_amount', 0)
                    position_count = len(balance.get('stocks', []))
                except Exception as e:
                    logger.warning(f"실시간 잔고 조회 실패: {e}")

            # API 실패 시 최신 스냅샷 사용
            if total_assets == 0 and snapshots:
                latest = sorted(snapshots, key=lambda s: s["date"])[-1]
                total_assets = latest["total_assets"]
                cash = latest["cash"]
                invested = latest["invested"]
                buy_amount = latest.get("buy_amount", 0)
                position_count = latest["position_count"]

            if total_assets == 0:
                await update.message.reply_text("❌ 자산 정보를 가져올 수 없습니다.")
                return

            total_pnl = total_assets - initial_capital
            total_pnl_pct = (total_pnl / initial_capital * 100) if initial_capital > 0 else 0
            sign = "+" if total_pnl >= 0 else ""

            # 운용 기간 계산
            days_str = ""
            if snapshots:
                first_date = sorted(snapshots, key=lambda s: s["date"])[0]["date"]
                try:
                    start = datetime.strptime(first_date, "%Y-%m-%d")
                    days_count = (datetime.now() - start).days
                    days_str = f"\n운용 기간: {days_count}일"
                except ValueError:
                    pass

            lines = [
                "💰 <b>투자 원금 대비 현황</b>",
                "━━━━━━━━━━━━━━━",
                f"초기 투자금: <code>{initial_capital:,.0f}원</code>",
                f"현재 총 자산: <code>{total_assets:,.0f}원</code>",
                "━━━━━━━━━━━━━━━",
                f"예수금: <code>{cash:,.0f}원</code>",
                f"투자금(평가): <code>{invested:,.0f}원</code>",
                f"매입금액: <code>{buy_amount:,.0f}원</code>",
                f"보유 종목: {position_count}개",
                "━━━━━━━━━━━━━━━",
                f"총 수익: <b>{sign}{total_pnl:,.0f}원</b> ({sign}{total_pnl_pct:.1f}%)",
            ]

            if days_str:
                lines.append(days_str)

            await update.message.reply_text("\n".join(lines), parse_mode='HTML')

        except Exception as e:
            logger.error(f"투자 현황 조회 실패: {e}", exc_info=True)
            await update.message.reply_text(f"❌ 투자 현황 조회 실패: {e}")

    async def cmd_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """시세 조회 명령어"""
        if not self.kis_client:
            await update.message.reply_text("❌ API 클라이언트가 연결되지 않았습니다.")
            return

        if not context.args:
            await update.message.reply_text("사용법: /price [종목코드]\n예: /price 005930")
            return

        stock_code = context.args[0]

        # 종목코드 검증
        is_valid, error_msg = InputValidator.validate_stock_code(stock_code)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_msg}")
            return

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
        from src.core import get_controller

        controller = get_controller()
        status = controller.get_status()

        state_icons = {
            "stopped": "⏹️ 중지",
            "running": "▶️ 실행중",
            "paused": "⏸️ 일시정지",
            "emergency_stop": "🚨 긴급정지"
        }
        state_display = state_icons.get(status['state'], status['state'])
        api_status = "🟢 연결됨" if self.kis_client else "🔴 미연결"

        config = status['config']
        dry_run = "✅ 활성화" if config['dry_run'] else "🔴 비활성화"
        mode = "🧪 모의투자" if config['is_virtual'] else "💰 실전투자"

        message = (
            "⚙️ <b>시스템 상태</b>\n"
            "━━━━━━━━━━━━━━━\n"
            f"• 상태: {state_display}\n"
            f"• 모드: {mode}\n"
            f"• Dry-Run: {dry_run}\n"
            f"• API 연결: {api_status}\n"
            "━━━━━━━━━━━━━━━\n"
            f"<b>설정:</b>\n"
            f"• 목표 종목: {config['target_count']}개\n"
            f"• 손절: {config['stop_loss_pct']}%\n"
            f"• 익절: {config['take_profit_pct']}%\n"
            "━━━━━━━━━━━━━━━\n"
            f"<b>가중치:</b>\n"
            f"• 모멘텀: {config['momentum_weight']:.2f}\n"
            f"• 단기모멘텀: {config['short_mom_weight']:.2f}\n"
            f"• 변동성: {config['volatility_weight']:.2f}\n"
            f"• 거래량: {config['volume_weight']:.2f}\n"
            "━━━━━━━━━━━━━━━\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
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

    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """보유 포지션 조회"""
        from src.core import get_controller

        controller = get_controller()
        result = controller.get_positions()

        positions = result.get('positions', [])

        if not positions:
            await update.message.reply_text("📊 보유 포지션이 없습니다.")
            return

        lines = [
            "📊 <b>보유 포지션</b>",
            "━━━━━━━━━━━━━━━"
        ]

        total_value = 0
        total_pnl = 0

        for p in positions:
            pnl_pct = p.get('pnl_pct', 0)
            pnl_emoji = "📈" if pnl_pct >= 0 else "📉"
            lines.append(
                f"{pnl_emoji} <b>{p.get('name', 'N/A')}</b> ({p.get('code', '')})\n"
                f"   {p.get('quantity', 0)}주 × {p.get('current_price', 0):,}원\n"
                f"   손익: {pnl_pct:+.2f}%"
            )
            total_value += p.get('current_price', 0) * p.get('quantity', 0)
            total_pnl += p.get('pnl', 0)

        lines.append("━━━━━━━━━━━━━━━")
        lines.append(f"총 평가: <code>{total_value:,}원</code>")
        lines.append(f"총 손익: <code>{total_pnl:+,}원</code>")
        lines.append(f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        await update.message.reply_text("\n".join(lines), parse_mode='HTML')

    async def cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """최근 로그 조회"""
        from src.core import get_controller

        lines = 10
        if context.args:
            # 줄 수 검증 (1~30)
            is_valid, parsed_lines, error_msg = InputValidator.validate_positive_int(
                context.args[0], min_val=1, max_val=30, field_name="로그 줄 수"
            )
            if not is_valid:
                await update.message.reply_text(f"❌ {error_msg}")
                return
            lines = parsed_lines

        controller = get_controller()
        result = controller.get_logs(lines)

        if result['success']:
            log_lines = result.get('lines', [])
            if log_lines:
                # 로그를 간략화
                formatted = []
                for line in log_lines[-lines:]:
                    # 시간과 메시지만 추출
                    if ' - ' in line:
                        parts = line.split(' - ', 3)
                        if len(parts) >= 4:
                            time_part = parts[0].split(',')[0][-8:]  # HH:MM:SS
                            level = parts[2][:4]
                            msg = parts[3][:50]
                            formatted.append(f"<code>{time_part}</code> [{level}] {msg}")
                        else:
                            formatted.append(f"<code>{line[:60]}</code>")
                    else:
                        formatted.append(f"<code>{line[:60]}</code>")

                message = (
                    f"📋 <b>최근 로그</b> ({result.get('file', '')})\n"
                    "━━━━━━━━━━━━━━━\n" +
                    "\n".join(formatted)
                )
            else:
                message = "로그가 비어있습니다."
        else:
            message = f"❌ {result['message']}"

        await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """일일 리포트 요청"""
        from src.core import get_controller

        controller = get_controller()
        status = controller.get_status()
        positions = controller.get_positions().get('positions', [])

        config = status['config']
        state_icons = {
            "stopped": "⏹️ 중지",
            "running": "▶️ 실행중",
            "paused": "⏸️ 일시정지",
            "emergency_stop": "🚨 긴급정지"
        }

        total_value = sum(p.get('current_price', 0) * p.get('quantity', 0) for p in positions)
        total_pnl = sum(p.get('pnl', 0) for p in positions)
        pnl_emoji = "📈" if total_pnl >= 0 else "📉"

        message = (
            f"📋 <b>일일 리포트</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"<b>시스템 상태:</b>\n"
            f"• 상태: {state_icons.get(status['state'], status['state'])}\n"
            f"• Dry-Run: {'✅' if config['dry_run'] else '🔴'}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"<b>포트폴리오:</b>\n"
            f"• 보유 종목: {len(positions)}개\n"
            f"• 총 평가: <code>{total_value:,}원</code>\n"
            f"• 총 손익: {pnl_emoji} <code>{total_pnl:+,}원</code>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"<b>설정:</b>\n"
            f"• 목표 종목: {config['target_count']}개\n"
            f"• 손절: {config['stop_loss_pct']}%\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_monthly_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """월간 리포트 요청"""
        from src.core import get_controller

        await update.message.reply_text("📊 월간 리포트 생성 중...")

        try:
            controller = get_controller()
            result = controller.run_monthly_report()

            if result['success']:
                await update.message.reply_text(
                    f"✅ {result['message']}",
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(
                    f"❌ {result['message']}",
                    parse_mode='HTML'
                )
        except Exception as e:
            logger.error(f"월간 리포트 명령 실패: {e}")
            await update.message.reply_text(f"❌ 오류 발생: {str(e)[:200]}")

    # ==================== 분석 명령어 ====================

    async def cmd_screening(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """스크리닝 명령어"""
        await update.message.reply_text("🔍 스크리닝 실행 중... 잠시만 기다려주세요.")

        try:
            from src.api.kis_quant import KISQuantClient
            from src.strategy.quant import CompositeScoreCalculator, TechnicalAnalyzer

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
                "━━━━━━━━━━━━━━━",
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
            await update.message.reply_text("사용법: /signal [종목코드]\n예: /signal 005930")
            return

        stock_code = context.args[0]

        # 종목코드 검증
        is_valid, error_msg = InputValidator.validate_stock_code(stock_code)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_msg}")
            return

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

            # 손절/익절가 (설정에서 읽기)
            from src.core import get_controller
            controller = get_controller()
            stop_loss_pct = controller.config.stop_loss_pct
            take_profit_pct = controller.config.take_profit_pct

            stop_loss = int(current_price * (1 - stop_loss_pct / 100))
            take_profit = int(current_price * (1 + take_profit_pct / 100))

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
                f"• 손절가: <code>{stop_loss:,}원</code> (-{stop_loss_pct:.0f}%)\n"
                f"• 익절가: <code>{take_profit:,}원</code> (+{take_profit_pct:.0f}%)"
            )

            await update.message.reply_text(message, parse_mode='HTML')

        except Exception as e:
            await update.message.reply_text(f"❌ 분석 실패: {e}")

    # ==================== 시스템 제어 명령어 ====================

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

    # ==================== 수동 실행 명령어 ====================

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

    async def cmd_run_rebalance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """리밸런싱 수동 실행"""
        from src.core import get_controller

        controller = get_controller()
        result = controller.run_rebalance()

        if result['success']:
            await update.message.reply_text(
                "🔄 <b>리밸런싱 시작</b>\n완료되면 결과가 전송됩니다.",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(f"❌ {result['message']}")

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

    async def cmd_rebalance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """긴급 리밸런싱 (보유 종목 부족 시 부분 매수)"""
        from src.core import get_controller

        # force 인자 확인
        force = False
        if context.args and context.args[0].lower() == 'force':
            force = True

        controller = get_controller()
        result = controller.run_urgent_rebalance(force=force)

        if result['success']:
            message = result.get('message', '긴급 리밸런싱이 실행되었습니다.')
            buy_count = result.get('buy_count', 0)
            current_count = result.get('current_count', 0)

            if buy_count > 0:
                await update.message.reply_text(
                    f"📢 <b>긴급 리밸런싱 완료</b>\n"
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

    # ==================== 설정 변경 명령어 ====================

    async def cmd_set_dryrun(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Dry-run 모드 설정"""
        from src.core import get_controller

        if not context.args:
            await update.message.reply_text("사용법: /set_dryrun on|off")
            return

        # on/off 검증
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

        # 목표 종목 수 검증 (1~50)
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

        # 손절 비율 검증 (1~30%)
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

    # ==================== 포지션 관리 명령어 ====================

    async def cmd_close(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """특정 포지션 청산"""
        from src.core import get_controller

        if not context.args:
            await update.message.reply_text("사용법: /close [종목코드]\n예: /close 005930")
            return

        stock_code = context.args[0]

        # 종목코드 검증
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

    # ==================== Application 관련 ====================

    async def _post_init(self, application: Application) -> None:
        """Application 초기화 후 명령어 등록"""
        try:
            commands = [
                BotCommand("start", "Start bot"),
                BotCommand("help", "Show help"),
                BotCommand("status", "System status"),
                BotCommand("balance", "Account balance"),
                BotCommand("positions", "Position list"),
                BotCommand("start_trading", "Start trading"),
                BotCommand("stop_trading", "Stop trading"),
                BotCommand("pause", "Pause trading"),
                BotCommand("resume", "Resume trading"),
            ]
            await application.bot.set_my_commands(commands)
            logger.info("텔레그램 명령어 목록 등록 완료")
        except Exception as e:
            logger.warning(f"명령어 목록 등록 실패 (무시됨): {e}")

    def build_application(self) -> Application:
        """Application 빌드"""
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")

        self.application = Application.builder().token(self.bot_token).post_init(self._post_init).build()

        # 기본 명령어
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))

        # 시스템 제어 명령어
        self.application.add_handler(CommandHandler("start_trading", self.cmd_start_trading))
        self.application.add_handler(CommandHandler("stop_trading", self.cmd_stop_trading))
        self.application.add_handler(CommandHandler("pause", self.cmd_pause))
        self.application.add_handler(CommandHandler("resume", self.cmd_resume))
        self.application.add_handler(CommandHandler("emergency_stop", self.cmd_emergency_stop))
        self.application.add_handler(CommandHandler("clear_emergency", self.cmd_clear_emergency))

        # 수동 실행 명령어
        self.application.add_handler(CommandHandler("run_screening", self.cmd_run_screening))
        self.application.add_handler(CommandHandler("run_rebalance", self.cmd_run_rebalance))
        self.application.add_handler(CommandHandler("rebalance", self.cmd_rebalance))
        self.application.add_handler(CommandHandler("run_optimize", self.cmd_run_optimize))

        # 설정 변경 명령어
        self.application.add_handler(CommandHandler("set_dryrun", self.cmd_set_dryrun))
        self.application.add_handler(CommandHandler("set_target", self.cmd_set_target))
        self.application.add_handler(CommandHandler("set_stoploss", self.cmd_set_stoploss))

        # 조회 명령어
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("positions", self.cmd_positions))
        self.application.add_handler(CommandHandler("balance", self.cmd_balance))
        self.application.add_handler(CommandHandler("history", self.cmd_history))
        self.application.add_handler(CommandHandler("trades", self.cmd_trades))
        self.application.add_handler(CommandHandler("capital", self.cmd_capital))
        self.application.add_handler(CommandHandler("orders", self.cmd_orders))
        self.application.add_handler(CommandHandler("logs", self.cmd_logs))
        self.application.add_handler(CommandHandler("report", self.cmd_report))
        self.application.add_handler(CommandHandler("monthly_report", self.cmd_monthly_report))

        # 포지션 관리 명령어
        self.application.add_handler(CommandHandler("close", self.cmd_close))
        self.application.add_handler(CommandHandler("close_all", self.cmd_close_all))

        # 분석 명령어
        self.application.add_handler(CommandHandler("screening", self.cmd_screening))
        self.application.add_handler(CommandHandler("signal", self.cmd_signal))
        self.application.add_handler(CommandHandler("price", self.cmd_price))

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
        """봇 시작 (블로킹) - 네트워크 에러 시 자동 재시작"""
        self.running = True
        logger.info("텔레그램 봇 핸들러 시작...")

        max_init_retries = 5
        max_runtime_retries = 10  # 런타임 에러 시 최대 재시작 횟수
        runtime_retry_count = 0

        while self.running and runtime_retry_count < max_runtime_retries:
            retry_delay = 3  # seconds

            for attempt in range(max_init_retries):
                if not self.running:
                    break

                app = None  # finally 블록에서 정리할 수 있도록 미리 선언
                try:
                    app = self.bot.build_application()
                    self._loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(self._loop)

                    # 폴링 시작 (재시도 포함)
                    logger.info(f"텔레그램 봇 초기화 중... (시도 {attempt + 1}/{max_init_retries})")
                    self._loop.run_until_complete(app.initialize())
                    self._loop.run_until_complete(app.start())
                    self._loop.run_until_complete(app.updater.start_polling(
                        allowed_updates=Update.ALL_TYPES,
                        drop_pending_updates=True  # 이전 세션의 pending updates 무시
                    ))
                    logger.info("텔레그램 봇 초기화 성공")

                    # 시작 알림 전송 (실패해도 봇은 계속 실행)
                    if runtime_retry_count == 0:
                        try:
                            self.bot.notifier.send_message("🤖 텔레그램 봇이 시작되었습니다.\n/help 명령어로 사용법을 확인하세요.")
                        except Exception as e:
                            logger.warning(f"시작 알림 전송 실패 (무시): {e}")
                    else:
                        try:
                            self.bot.notifier.send_message(f"🔄 텔레그램 봇 재연결 성공 (재시도 {runtime_retry_count}회)")
                        except Exception:
                            pass

                    # 성공 시 런타임 재시도 카운트 리셋
                    runtime_retry_count = 0

                    # 무한 대기
                    while self.running:
                        self._loop.run_until_complete(asyncio.sleep(1))
                    return  # 정상 종료

                except Exception as e:
                    error_str = str(e)

                    # Conflict: 이전 세션이 아직 활성화된 경우 - 더 긴 딜레이 필요
                    is_conflict_error = "Conflict" in error_str or "terminated by other" in error_str

                    is_network_error = any(x in error_str for x in [
                        "Timed out", "ReadTimeout", "ConnectError",
                        "ConnectTimeout", "NetworkError", "ConnectionError"
                    ])

                    if is_conflict_error:
                        conflict_delay = 10 + (attempt * 5)  # 10s, 15s, 20s...
                        if attempt < max_init_retries - 1:
                            logger.warning(f"텔레그램 봇 Conflict 에러 (시도 {attempt + 1}/{max_init_retries}), {conflict_delay}초 후 재시도...")
                            time.sleep(conflict_delay)
                            continue
                        else:
                            logger.error(f"텔레그램 봇 Conflict 에러 지속: {e}")
                            break
                    elif is_network_error:
                        if attempt < max_init_retries - 1:
                            logger.warning(f"텔레그램 봇 네트워크 에러 (시도 {attempt + 1}/{max_init_retries}), {retry_delay}초 후 재시도...")
                            time.sleep(retry_delay)
                            retry_delay = min(retry_delay * 2, 60)  # 지수 백오프 (최대 60초)
                            continue
                        else:
                            logger.error(f"텔레그램 봇 초기화 실패 (최대 재시도 초과): {e}")
                            break
                    else:
                        logger.error(f"텔레그램 봇 오류: {e}", exc_info=True)
                        break
                finally:
                    # 루프 정리 - 로컬 app 변수 사용
                    if self._loop:
                        try:
                            if app is not None:
                                self._loop.run_until_complete(app.updater.stop())
                                self._loop.run_until_complete(app.stop())
                                self._loop.run_until_complete(app.shutdown())
                        except Exception:
                            pass
                        self.bot.application = None

            # 초기화 실패 후 런타임 재시도
            if self.running:
                runtime_retry_count += 1
                wait_time = min(30 * runtime_retry_count, 300)  # 30초씩 증가, 최대 5분
                logger.warning(f"텔레그램 봇 재시작 대기 {wait_time}초... (런타임 재시도 {runtime_retry_count}/{max_runtime_retries})")
                time.sleep(wait_time)

        if runtime_retry_count >= max_runtime_retries:
            logger.error("텔레그램 봇 최대 재시작 횟수 초과 - 봇 스레드 종료")
        logger.info("텔레그램 봇 핸들러 종료됨")

    def stop(self):
        """봇 중지"""
        self.running = False
        if self._loop and self.bot.application:
            try:
                self._loop.run_until_complete(self.bot.application.updater.stop())
                self._loop.run_until_complete(self.bot.application.stop())
                self._loop.run_until_complete(self.bot.application.shutdown())
            except Exception as e:
                logger.debug(f"봇 종료 중 오류 (무시): {e}")
        logger.info("텔레그램 봇 핸들러 중지 요청됨")
