"""
조회 명령어 Mixin

cmd_balance, cmd_positions, cmd_status, cmd_capital,
cmd_history, cmd_trades, cmd_orders, cmd_logs,
cmd_report, cmd_monthly_report
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from ._base import DATA_DIR, parse_days_arg, with_error_handling

logger = logging.getLogger(__name__)


class QueryCommandsMixin:
    """조회 명령어 모음"""

    @with_error_handling("잔고 조회")
    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """잔고 조회 명령어"""
        if self.kis_client:
            try:
                balance = self.kis_client.get_balance()
                from src.utils.balance_helpers import parse_balance
                bs = parse_balance(balance)

                lines = [
                    "💰 <b>계좌 잔고</b>",
                    "━━━━━━━━━━━━━━━",
                    f"예수금: <code>{bs.cash:,.0f}원</code>",
                    f"총평가: <code>{bs.total_assets:,.0f}원</code>",
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
        state_file = DATA_DIR / "engine_state.json"

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

        updated_at = data.get("updated_at", "")
        if updated_at:
            lines.append(f"\n📅 마지막 업데이트: {updated_at[:19]}")

        await update.message.reply_text("\n".join(lines), parse_mode='HTML')

    @with_error_handling("히스토리 조회")
    async def cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """일별 자산 변동 조회"""
        history_file = DATA_DIR / "daily_history.json"

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

        days = parse_days_arg(context)

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
            date_str = s["date"][5:]
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

    @with_error_handling("거래 내역 조회")
    async def cmd_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """거래 내역 조회"""
        tx_file = DATA_DIR / "transaction_journal.json"

        if not tx_file.exists():
            await update.message.reply_text("❌ 거래 일지 데이터가 없습니다.\n거래 발생 시 자동 기록됩니다.")
            return

        with open(tx_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        transactions = data.get("transactions", [])

        if not transactions:
            await update.message.reply_text("❌ 기록된 거래가 없습니다.")
            return

        days = parse_days_arg(context)

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

        for t in recent[:20]:
            ts = t["timestamp"]
            date_str = ts[5:10]
            time_str = ts[11:16]
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

    @with_error_handling("투자 현황 조회")
    async def cmd_capital(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """초기 투자금 대비 현황"""
        history_file = DATA_DIR / "daily_history.json"

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
                from src.utils.balance_helpers import parse_balance
                bs = parse_balance(balance)
                total_assets = bs.total_assets
                cash = bs.cash
                invested = bs.scts_evlu
                buy_amount = bs.buy_amount
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

    @with_error_handling("주문내역 조회")
    async def cmd_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """주문내역 조회 명령어"""
        if not self.kis_client:
            await update.message.reply_text("❌ API 클라이언트가 연결되지 않았습니다.")
            return

        days = 1
        if context.args:
            try:
                days = max(1, min(int(context.args[0]), 90))
            except ValueError:
                await update.message.reply_text("사용법: /orders [일수]\n예: /orders 7")
                return

        if days == 1:
            orders = self.kis_client.get_order_history()

            if not orders:
                await update.message.reply_text("📋 당일 주문내역이 없습니다.")
                return

            lines = ["📋 <b>당일 주문내역</b>", "━━━━━━━━━━━━━━━"]

            for order in orders[:10]:
                emoji = "🟢" if order['side'] == "매수" else "🔴"
                lines.append(
                    f"{emoji} <b>{order['name']}</b>\n"
                    f"   {order['side']} {order['qty']}주 × {order['price']:,}원\n"
                    f"   체결: {order['filled_qty']}주 | {order['status']}"
                )

            await update.message.reply_text("\n".join(lines), parse_mode='HTML')
        else:
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=days - 1)).strftime("%Y%m%d")

            orders = self.kis_client.get_execution_history(start_date, end_date)

            if not orders:
                await update.message.reply_text(f"📋 최근 {days}일간 체결 내역이 없습니다.")
                return

            from collections import OrderedDict
            by_date = OrderedDict()
            for order in orders:
                date_key = order.get("order_date", "")
                if date_key not in by_date:
                    by_date[date_key] = []
                by_date[date_key].append(order)

            lines = [
                f"📋 <b>체결 내역 (최근 {days}일)</b>",
                "━━━━━━━━━━━━━━━"
            ]

            shown = 0
            for date_str, date_orders in by_date.items():
                if shown >= 20:
                    break

                display_date = f"{date_str[4:6]}/{date_str[6:8]}" if len(date_str) == 8 else date_str
                lines.append(f"\n📅 <b>{display_date}</b>")

                for order in date_orders:
                    if shown >= 20:
                        break

                    emoji = "🟢" if order['side'] == "매수" else "🔴"
                    avg_price = order.get('avg_price', 0)
                    price_str = f"{avg_price:,}" if avg_price > 0 else f"{order['price']:,}"

                    lines.append(
                        f"  {emoji} {order['name']} "
                        f"{order['side']} {order['filled_qty']}주 × {price_str}원"
                    )
                    shown += 1

            total = len(orders)
            lines.append("\n━━━━━━━━━━━━━━━")
            lines.append(f"총 {total}건")
            if total > 20:
                lines.append(f"(최근 20건만 표시)")

            await update.message.reply_text("\n".join(lines), parse_mode='HTML')

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

    async def cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """최근 로그 조회"""
        from src.core import get_controller
        from ..validators import InputValidator

        lines = 10
        if context.args:
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
                formatted = []
                for line in log_lines[-lines:]:
                    if ' - ' in line:
                        parts = line.split(' - ', 3)
                        if len(parts) >= 4:
                            time_part = parts[0].split(',')[0][-8:]
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

    @with_error_handling("월간 리포트")
    async def cmd_monthly_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """월간 리포트 요청"""
        from src.core import get_controller

        await update.message.reply_text("📊 월간 리포트 생성 중...")

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
