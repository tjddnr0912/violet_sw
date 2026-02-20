"""
리포트 생성 모듈

일일/월간 리포트 생성 및 발송 전담
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from src.utils.balance_helpers import parse_balance

logger = logging.getLogger(__name__)


class ReportGenerator:
    """일일/월간 리포트 생성"""

    def __init__(self, client, notifier, daily_tracker, monthly_tracker, portfolio, config):
        """
        Args:
            client: KISQuantClient
            notifier: TelegramNotifier
            daily_tracker: DailyTracker
            monthly_tracker: MonthlyTracker
            portfolio: PortfolioManager
            config: QuantEngineConfig
        """
        self.client = client
        self.notifier = notifier
        self.daily_tracker = daily_tracker
        self.monthly_tracker = monthly_tracker
        self.portfolio = portfolio
        self.config = config

    def generate_daily_report(self, daily_trades: List[Dict]) -> List[Dict]:
        """
        일일 리포트 생성 및 발송.

        Args:
            daily_trades: 오늘 거래 내역 리스트

        Returns:
            월간 거래에 추가할 daily_trades 복사본 (호출자가 monthly_trades에 extend)
        """
        from src.quant_modules import DailySnapshot

        snapshot = self.portfolio.get_snapshot()

        # KIS API 잔고 조회
        kis_cash = snapshot.cash
        kis_scts_evlu = snapshot.invested
        kis_stocks = []
        total_display = snapshot.total_value
        kis_buy_amount = 0
        kis_available = False

        try:
            balance_info = self.client.get_balance()
            bs = parse_balance(balance_info)
            total_display = bs.total_assets
            kis_cash = bs.cash
            kis_scts_evlu = bs.scts_evlu
            kis_buy_amount = bs.buy_amount
            kis_stocks = balance_info.get('stocks', [])
            kis_available = True
        except Exception as e:
            logger.warning(f"KIS 잔고 조회 실패, 내부 데이터 사용: {e}")

        # 보유 종목 정보 (KIS 데이터 우선)
        positions_text = ""
        position_count = len(snapshot.positions)
        if kis_available and kis_stocks:
            for stock in kis_stocks:
                pnl_rate = stock.profit_rate if hasattr(stock, 'profit_rate') else 0
                pnl_str = f"+{pnl_rate:.1f}" if pnl_rate >= 0 else f"{pnl_rate:.1f}"
                name = stock.name if hasattr(stock, 'name') else str(stock)
                positions_text += f"• {name}: {pnl_str}%\n"
            position_count = len(kis_stocks)
        elif snapshot.positions:
            for pos in snapshot.positions:
                pnl_str = f"+{pos.profit_pct:.1f}" if pos.profit_pct >= 0 else f"{pos.profit_pct:.1f}"
                positions_text += f"• {pos.name}: {pnl_str}%\n"
        else:
            positions_text = "없음"

        # KIS에 주식이 있지만 내부 포지션이 없으면 경고
        sync_warning = ""
        if kis_stocks and not snapshot.positions:
            sync_warning = (
                f"\n⚠️ <b>포지션 불일치</b>\n"
                f"KIS 보유: {len(kis_stocks)}종목 / 내부: 0종목\n"
                f"봇이 관리하지 않는 주식이 있습니다.\n"
            )

        # 오늘 거래 내역
        trades_text = ""
        if daily_trades:
            for t in daily_trades:
                pnl_str = ""
                if t["type"] == "SELL" and "pnl" in t:
                    pnl_str = f" ({t['pnl_pct']:+.1f}%)"
                trades_text += f"• {t['type']} {t['name']}{pnl_str}\n"
        else:
            trades_text = "없음"

        # 총 손익 계산
        initial = self.daily_tracker.initial_capital or self.config.total_capital
        total_pnl = total_display - initial
        total_pnl_pct = (total_pnl / initial * 100) if initial > 0 else 0

        message = (
            f"📈 <b>일일 리포트</b>\n\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"<b>포트폴리오</b>\n"
            f"총 평가: {total_display:,.0f}원\n"
            f"주식: {kis_scts_evlu:,.0f}원\n"
            f"현금: {kis_cash:,.0f}원\n"
            f"총 손익: {total_pnl_pct:+.2f}%\n"
            f"MDD: {snapshot.mdd*100:.1f}%\n\n"
            f"<b>보유 종목 ({position_count}개)</b>\n"
            f"{positions_text}"
            f"{sync_warning}\n"
            f"<b>오늘 거래</b>\n"
            f"{trades_text}"
        )

        self.notifier.send_message(message)

        # 일별 스냅샷 저장
        try:
            total_assets = total_display
            cash = kis_cash
            invested = kis_scts_evlu
            buy_amount = kis_buy_amount

            today_str = datetime.now().strftime("%Y-%m-%d")
            prev = self.daily_tracker.get_previous_day_snapshot(today_str)
            daily_pnl = 0
            daily_pnl_pct = 0
            if prev:
                daily_pnl = total_assets - prev.total_assets
                daily_pnl_pct = (daily_pnl / prev.total_assets * 100) if prev.total_assets > 0 else 0

            total_pnl = total_assets - initial
            total_pnl_pct = (total_pnl / initial * 100) if initial > 0 else 0

            position_data = []
            if kis_available and kis_stocks:
                for stock in kis_stocks:
                    pnl = stock.profit if hasattr(stock, 'profit') else 0
                    pnl_pct = stock.profit_rate if hasattr(stock, 'profit_rate') else 0
                    position_data.append({
                        "code": stock.code if hasattr(stock, 'code') else "",
                        "name": stock.name if hasattr(stock, 'name') else "",
                        "quantity": stock.qty if hasattr(stock, 'qty') else 0,
                        "entry_price": stock.avg_price if hasattr(stock, 'avg_price') else 0,
                        "current_price": stock.current_price if hasattr(stock, 'current_price') else 0,
                        "pnl": pnl,
                        "pnl_pct": pnl_pct
                    })
            else:
                for pos in snapshot.positions:
                    pnl = (pos.current_price - pos.entry_price) * pos.quantity
                    position_data.append({
                        "code": pos.code,
                        "name": pos.name,
                        "quantity": pos.quantity,
                        "entry_price": pos.entry_price,
                        "current_price": pos.current_price,
                        "pnl": pnl,
                        "pnl_pct": pos.profit_pct
                    })

            daily_snapshot = DailySnapshot(
                date=datetime.now().strftime("%Y-%m-%d"),
                total_assets=total_assets,
                cash=cash,
                invested=invested,
                buy_amount=buy_amount,
                position_count=position_count,
                total_pnl=total_pnl,
                total_pnl_pct=total_pnl_pct,
                daily_pnl=daily_pnl,
                daily_pnl_pct=daily_pnl_pct,
                trades_today=len(daily_trades),
                positions=position_data
            )
            self.daily_tracker.save_daily_snapshot(daily_snapshot)
        except Exception as e:
            logger.error(f"일별 스냅샷 저장 실패: {e}", exc_info=True)

        logger.info("일일 리포트 발송 완료")

        # 호출자가 monthly_trades.extend()에 사용할 복사본 반환
        return list(daily_trades)

    def generate_monthly_report(self, monthly_trades: List[Dict], save_snapshot: bool = True):
        """
        월간 리포트 생성 및 발송.

        Args:
            monthly_trades: 월간 거래 내역 리스트
            save_snapshot: 스냅샷 저장 여부 (수동 요청 시 False)
        """
        try:
            logger.info("월간 리포트 생성 시작")

            snapshot = self.portfolio.get_snapshot()

            try:
                balance_info = self.client.get_balance()
                bs = parse_balance(balance_info)
                total_assets = bs.total_assets
                cash = bs.cash
            except Exception as e:
                logger.warning(f"잔고 조회 실패, 포트폴리오 데이터 사용: {e}")
                total_assets = snapshot.total_value
                cash = snapshot.cash

            report_message = self.monthly_tracker.generate_monthly_report(
                portfolio_snapshot=snapshot,
                monthly_trades=monthly_trades,
                total_assets=total_assets,
                cash=cash,
                is_auto_report=save_snapshot
            )

            self.notifier.send_message(report_message)

            if save_snapshot:
                monthly_snapshot = self.monthly_tracker.create_snapshot_from_portfolio(
                    portfolio_snapshot=snapshot,
                    monthly_trades=monthly_trades,
                    total_assets=total_assets,
                    cash=cash
                )
                self.monthly_tracker.save_snapshot(monthly_snapshot)

            logger.info("월간 리포트 발송 완료")

        except Exception as e:
            logger.error(f"월간 리포트 생성 실패: {e}", exc_info=True)
            self.notifier.send_message(
                f"⚠️ <b>월간 리포트 생성 실패</b>\n\n"
                f"오류: {str(e)[:200]}"
            )
