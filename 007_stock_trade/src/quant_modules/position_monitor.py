"""
포지션 모니터링 모듈

장중 5분마다 포지션 체크 (손절/익절/트레일링 스탑)
"""

import time
import logging

from .state_manager import PendingOrder
from .order_executor import API_DELAY_VIRTUAL, API_DELAY_REAL
from ..strategy.quant import (
    Position,
    StopLossManager,
    TakeProfitManager,
    RiskLevel,
)

logger = logging.getLogger(__name__)

# 디버그 전용 로거 (별도 파일에 상세 로그 기록)
debug_logger = logging.getLogger("quant_debug")
debug_logger.setLevel(logging.DEBUG)
_debug_handler = logging.FileHandler("logs/quant_debug.log", encoding="utf-8")
_debug_handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s"
))
debug_logger.addHandler(_debug_handler)
debug_logger.propagate = False


class PositionMonitor:
    """포지션 모니터링 (손절/익절/트레일링 스탑)"""

    def __init__(self, client, portfolio, notifier, config, is_virtual, order_executor):
        self.client = client
        self.portfolio = portfolio
        self.notifier = notifier
        self.config = config
        self.is_virtual = is_virtual
        self.order_executor = order_executor

    def monitor(self, position_lock, daily_trades, save_state_fn):
        """
        포지션 모니터링 (장중 5분마다 실행)

        Args:
            position_lock: threading.Lock for position access
            daily_trades: mutable list of daily trades
            save_state_fn: callback to save engine state
        """
        with position_lock:
            if not self.portfolio.positions:
                return
            positions_snapshot = list(self.portfolio.positions.items())

        logger.info(f"포지션 모니터링: {len(positions_snapshot)}개")
        debug_logger.info(f"{'='*60}")
        debug_logger.info(f"모니터링 시작: {len(positions_snapshot)}개 포지션")

        api_delay = API_DELAY_VIRTUAL if self.is_virtual else API_DELAY_REAL

        for i, (code, position) in enumerate(positions_snapshot):
            if i > 0:
                time.sleep(api_delay)

            try:
                # 현재가 업데이트 (Rate Limit 시 재시도)
                price_info = None
                for retry in range(3):
                    try:
                        price_info = self.client.get_stock_price(code)
                        break
                    except Exception as e:
                        error_str = str(e)
                        is_rate_limit = any(x in error_str for x in [
                            "EGW00201", "초당 거래건수", "증권사 서버 내부 오류"
                        ])
                        if is_rate_limit and retry < 2:
                            wait_time = 1.0 * (retry + 1)
                            debug_logger.warning(f"[{code}] Rate Limit - {wait_time}초 대기 후 재시도 ({retry+1}/3)")
                            time.sleep(wait_time)
                        else:
                            raise

                if price_info is None:
                    debug_logger.error(f"[{code}] 3회 재시도 실패")
                    continue

                with position_lock:
                    if code not in self.portfolio.positions:
                        continue
                    position.current_price = price_info.price

                # 디버그 로그
                pnl_pct = ((position.current_price - position.entry_price) / position.entry_price) * 100
                to_stop = ((position.current_price - position.stop_loss) / position.current_price) * 100
                to_tp1 = ((position.take_profit_1 - position.current_price) / position.current_price) * 100
                debug_logger.debug(
                    f"[{position.name}({code})] "
                    f"현재가: {position.current_price:,}원 | "
                    f"진입가: {position.entry_price:,}원 | "
                    f"수익률: {pnl_pct:+.2f}% | "
                    f"손절까지: {to_stop:.2f}% | "
                    f"익절1까지: {to_tp1:.2f}%"
                )

                # 손절 체크
                if position.current_price <= position.stop_loss:
                    self._trigger_stop_loss(position, daily_trades)
                    continue

                # 익절 체크
                if not position.tp1_executed and position.current_price >= position.take_profit_1:
                    self._trigger_take_profit(position, stage=1, daily_trades=daily_trades)
                elif not position.tp2_executed and position.current_price >= position.take_profit_2:
                    self._trigger_take_profit(position, stage=2, daily_trades=daily_trades)

                # 트레일링 스탑 업데이트
                if self.config.trailing_stop:
                    new_stop = StopLossManager.update_trailing_stop(
                        position, self.config.stop_loss_pct
                    )
                    with position_lock:
                        if new_stop > position.stop_loss:
                            position.stop_loss = new_stop
                            logger.info(f"{position.name}: 손절가 상향 → {new_stop:,.0f}원")

            except Exception as e:
                logger.error(f"모니터링 오류 ({code}): {e}", exc_info=True)
                debug_logger.error(f"[{code}] 오류: {e}")

        debug_logger.info(f"모니터링 완료")

        # 상태 저장
        save_state_fn()

        # 리스크 체크
        with position_lock:
            alerts = self.portfolio.check_risks()
        for alert in alerts:
            if alert.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                self.notifier.send_message(
                    f"⚠️ <b>리스크 경고</b>\n\n"
                    f"유형: {alert.alert_type}\n"
                    f"내용: {alert.message}\n"
                    f"조치: {alert.action_required}"
                )

    def _trigger_sell_with_retry(self, order, success_msg, failure_msg,
                                  daily_trades, on_success=None):
        """매도 주문 실행 (재시도 포함). 손절/익절 공통."""
        max_retries = 3
        api_delay = API_DELAY_VIRTUAL if self.is_virtual else API_DELAY_REAL

        for attempt in range(max_retries):
            time.sleep(api_delay * (attempt + 1))

            if self.order_executor._execute_order(order, daily_trades, Position, StopLossManager):
                if on_success:
                    on_success()
                self.notifier.send_message(success_msg)
                return

            if attempt < max_retries - 1:
                logger.warning(f"매도 재시도 ({attempt + 2}/{max_retries}): {order.name}")

        logger.error(f"매도 실패 (재시도 소진): {order.name}")
        self.notifier.send_message(failure_msg)

    def _trigger_stop_loss(self, position, daily_trades):
        """손절 실행"""
        logger.warning(f"손절 트리거: {position.name} ({position.profit_pct:+.1f}%)")

        order = PendingOrder(
            code=position.code, name=position.name, order_type="SELL",
            quantity=position.quantity, price=0,
            reason=f"손절 ({position.profit_pct:+.1f}%)"
        )
        self._trigger_sell_with_retry(
            order,
            success_msg=(
                f"🔴 <b>손절 실행</b>\n\n"
                f"종목: {position.name}\n"
                f"수량: {position.quantity}주\n"
                f"손익: {position.profit_pct:+.1f}%"
            ),
            failure_msg=(
                f"🚨 <b>손절 실패</b>\n\n"
                f"종목: {position.name}\n"
                f"수량: {position.quantity}주\n"
                f"⚠️ 수동 확인 필요"
            ),
            daily_trades=daily_trades,
        )

    def _trigger_take_profit(self, position, stage, daily_trades):
        """익절 실행"""
        qty = TakeProfitManager.calculate_staged_sell_qty(position.quantity, stage)
        if qty <= 0:
            return

        logger.info(f"익절 트리거 ({stage}차): {position.name} {qty}주 ({position.profit_pct:+.1f}%)")

        order = PendingOrder(
            code=position.code, name=position.name, order_type="SELL",
            quantity=qty, price=0,
            reason=f"{stage}차 익절 ({position.profit_pct:+.1f}%)"
        )

        def mark_tp():
            if stage == 1:
                position.tp1_executed = True
            else:
                position.tp2_executed = True

        self._trigger_sell_with_retry(
            order,
            success_msg=(
                f"🟢 <b>{stage}차 익절 실행</b>\n\n"
                f"종목: {position.name}\n"
                f"수량: {qty}주\n"
                f"수익: {position.profit_pct:+.1f}%"
            ),
            failure_msg=(
                f"🚨 <b>익절 실패</b>\n\n"
                f"종목: {position.name}\n"
                f"수량: {qty}주\n"
                f"⚠️ 수동 확인 필요"
            ),
            daily_trades=daily_trades,
            on_success=mark_tp,
        )
