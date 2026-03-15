"""
퀀트 엔진 주문 실행 모듈

주문 생성, 실행, 재시도 등 주문 처리 전담
"""

import time
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from .state_manager import PendingOrder

if TYPE_CHECKING:
    from ..api.kis_quant import KISQuantClient
    from ..strategy.quant import (
        Position,
        PortfolioManager,
        ScreeningResult,
        StopLossManager,
        TakeProfitManager
    )

logger = logging.getLogger(__name__)

# API Rate Limit 설정
API_DELAY_VIRTUAL = 0.5    # 모의투자: 500ms
API_DELAY_REAL = 0.1       # 실전투자: 100ms


class OrderExecutor:
    """
    주문 실행기

    리밸런싱 주문 생성, 대기 주문 실행, 실패 주문 재시도 담당
    """

    def __init__(
        self,
        client: 'KISQuantClient',
        portfolio: 'PortfolioManager',
        notifier,
        config,
        is_virtual: bool = True,
        daily_tracker=None
    ):
        """
        Args:
            client: KIS API 클라이언트
            portfolio: 포트폴리오 관리자
            notifier: 텔레그램 알림기
            config: QuantEngineConfig
            is_virtual: 모의투자 여부
            daily_tracker: DailyTracker (거래 즉시 기록용)
        """
        self.client = client
        self.portfolio = portfolio
        self.notifier = notifier
        self.config = config
        self.is_virtual = is_virtual
        self.api_delay = API_DELAY_VIRTUAL if is_virtual else API_DELAY_REAL
        self.daily_tracker = daily_tracker

    def generate_rebalance_orders(
        self,
        screening_result: 'ScreeningResult',
        pending_orders: List[PendingOrder],
        failed_orders: List[PendingOrder],
        stop_loss_manager,
        take_profit_manager,
        save_state_callback
    ) -> List[PendingOrder]:
        """
        리밸런싱 주문 생성

        Args:
            screening_result: 스크리닝 결과
            pending_orders: 대기 주문 리스트 (갱신됨)
            failed_orders: 실패 주문 리스트 (갱신됨)
            stop_loss_manager: StopLossManager 클래스
            take_profit_manager: TakeProfitManager 클래스
            save_state_callback: 상태 저장 콜백 함수

        Returns:
            생성된 주문 리스트
        """
        if not screening_result:
            logger.warning("스크리닝 결과 없음 - 스크리닝 먼저 실행 필요")
            return []

        orders = []

        # 현재 보유 종목
        current_holdings = set(self.portfolio.positions.keys())

        # 목표 종목 (상위 N개)
        target_stocks = {s.code: s for s in screening_result.selected_stocks}
        target_holdings = set(target_stocks.keys())

        # Buffer Rule: 보유 종목이 상위 N위 밖이어도 buffer 이내면 유지
        # 예: target=15일 때 buffer=25 → 16~25위는 기존 보유 시 매도하지 않음
        buffer_size = int(self.config.target_stock_count * 1.67)  # 약 1.67배 (15→25)
        buffer_codes = set()
        if hasattr(screening_result, 'all_scores') and screening_result.all_scores:
            ranked = [s for s in screening_result.all_scores if s.passed_filter]
            ranked.sort(key=lambda x: x.composite_score, reverse=True)
            buffer_codes = {s.code for s in ranked[:buffer_size]}

        # 매도 대상: 보유 중이지만 buffer 범위도 벗어난 종목만
        to_sell = current_holdings - buffer_codes if buffer_codes else current_holdings - target_holdings

        # 매수 대상: 목표에 있지만 미보유 종목
        # P10: Score Gap Threshold — 점수 차이가 미미한 교체 방지
        min_score_gap = 5.0  # 최소 5점 차이 필요
        to_buy = set()
        for code in target_holdings - current_holdings:
            stock = target_stocks[code]
            # 교체할 가치가 있는지: 매수 후보의 점수가 buffer 경계 종목보다 충분히 높은가
            if buffer_codes and ranked:
                buffer_boundary_score = ranked[min(buffer_size - 1, len(ranked) - 1)].composite_score
                if stock.composite_score - buffer_boundary_score < min_score_gap:
                    logger.debug(
                        f"P10 스킵: {stock.name} 점수차 "
                        f"{stock.composite_score - buffer_boundary_score:.1f} < {min_score_gap}"
                    )
                    continue
            to_buy.add(code)

        # 버퍼로 유지되는 종목 로깅
        buffer_kept = current_holdings - target_holdings - to_sell
        if buffer_kept:
            logger.info(f"Buffer Rule: {len(buffer_kept)}개 종목 유지 (순위 이탈했으나 buffer 이내)")
            for code in buffer_kept:
                pos = self.portfolio.positions.get(code)
                if pos:
                    # buffer 내 순위 찾기
                    rank_info = next((s.rank for s in ranked if s.code == code), "?")
                    logger.info(f"  유지: {pos.name} ({code}) - 현재 순위 {rank_info}")

        logger.info(f"리밸런싱: 매도 {len(to_sell)}개, 매수 {len(to_buy)}개, 버퍼유지 {len(buffer_kept)}개")

        # 매도 주문 생성
        for code in to_sell:
            position = self.portfolio.positions.get(code)
            if position:
                orders.append(PendingOrder(
                    code=code,
                    name=position.name,
                    order_type="SELL",
                    quantity=position.quantity,
                    price=0,  # 시장가
                    reason="순위권 이탈 - 리밸런싱 매도"
                ))

        # 매수 주문 생성
        available_capital = self.portfolio.cash * 0.95  # 5% 여유

        # Score-Weighted Allocation: 점수 비례 비중 계산
        buy_stocks = []
        for code in to_buy:
            buy_stocks.append(target_stocks[code])

        total_score = sum(max(s.composite_score, 1) for s in buy_stocks) if buy_stocks else 1
        min_weight = 0.03  # 최소 3%
        max_weight = self.config.max_single_weight  # 최대 10%

        for idx, stock in enumerate(buy_stocks):
            code = stock.code
            if idx > 0:
                time.sleep(self.api_delay)

            # 포지션 사이징 (API 재시도 로직 포함)
            try:
                current_price = self._get_price_with_retry(code)

                if current_price is None:
                    error_msg = "가격 조회 재시도 모두 실패"
                    logger.error(f"가격 조회 최종 실패 ({code}): {error_msg}")
                    failed_orders.append(PendingOrder(
                        code=code,
                        name=stock.name,
                        order_type="BUY",
                        quantity=0,
                        price=0,
                        reason=f"리밸런싱 매수 (순위 {stock.rank}위)",
                        retry_count=0,
                        last_error=error_msg
                    ))
                    continue

                # Score-Weighted 비중: 점수에 비례 (min/max 클리핑)
                raw_weight = max(stock.composite_score, 1) / total_score * (1 - 0.10)  # 현금 10% 보존
                weight = max(min_weight, min(max_weight, raw_weight))

                # 투자금액
                invest_amount = self.config.total_capital * weight
                invest_amount = min(invest_amount, available_capital / max(len(buy_stocks), 1))

                quantity = int(invest_amount / current_price)

                if quantity > 0:
                    # 손절가 계산: 변동성 기반 동적 손절 (fallback: 고정 비율)
                    stock_vol = getattr(stock, 'volatility', 0)
                    if stock_vol > 0:
                        stop_loss = stop_loss_manager.calculate_dynamic_stop(
                            current_price,
                            volatility=stock_vol,
                            fallback_pct=self.config.stop_loss_pct
                        )
                    else:
                        stop_loss = stop_loss_manager.calculate_fixed_stop(
                            current_price,
                            self.config.stop_loss_pct
                        )

                    tp1, tp2 = take_profit_manager.calculate_targets(current_price, stop_loss)

                    orders.append(PendingOrder(
                        code=code,
                        name=stock.name,
                        order_type="BUY",
                        quantity=quantity,
                        price=0,
                        reason=f"리밸런싱 매수 (순위 {stock.rank}위, 점수 {stock.composite_score:.1f})",
                        stop_loss=stop_loss,
                        take_profit_1=tp1,
                        take_profit_2=tp2,
                        weight=weight,
                        order_time_price=current_price,
                    ))

            except Exception as e:
                error_msg = str(e)
                logger.error(f"주문 생성 실패 ({code}): {e}", exc_info=True)
                failed_orders.append(PendingOrder(
                    code=code,
                    name=stock.name,
                    order_type="BUY",
                    quantity=0,
                    price=0,
                    reason=f"리밸런싱 매수 (순위 {stock.rank}위)",
                    retry_count=0,
                    last_error=error_msg[:200]
                ))

        # 실패 주문이 있으면 저장 및 알림
        if failed_orders:
            self._notify_failed_orders(failed_orders)
            save_state_callback()

        pending_orders.clear()
        pending_orders.extend(orders)
        return orders

    def generate_partial_rebalance_orders(
        self,
        target_stocks: list,
        shortage: int,
        stop_loss_manager,
        take_profit_manager,
    ) -> List[PendingOrder]:
        """
        부분 리밸런싱 주문 생성 (매수만, 매도 없음)

        긴급 리밸런싱용 - 기존 보유 종목 유지하고 부족분만 매수

        Args:
            target_stocks: 스크리닝 결과 SelectedStock 리스트
            shortage: 부족한 종목 수
            stop_loss_manager: StopLossManager 클래스
            take_profit_manager: TakeProfitManager 클래스

        Returns:
            생성된 매수 주문 리스트
        """
        if not target_stocks:
            logger.warning("스크리닝 결과 없음 - 부분 리밸런싱 불가")
            return []

        if shortage <= 0:
            logger.info("부족분 없음 - 부분 리밸런싱 불필요")
            return []

        orders = []

        # 현재 보유 종목
        current_holdings = set(self.portfolio.positions.keys())

        # 보유하지 않은 종목 중 상위 순위만 선택
        candidates = [s for s in target_stocks if s.code not in current_holdings]

        if not candidates:
            logger.info("매수 후보 없음 (모두 보유 중)")
            return []

        # 부족분만큼만 매수
        to_buy = candidates[:shortage]

        logger.info(f"부분 리밸런싱: 매수 대상 {len(to_buy)}개 (부족분: {shortage}개)")

        # 매수 주문 생성
        available_capital = self.portfolio.cash * 0.95  # 5% 여유

        for idx, stock in enumerate(to_buy):
            if idx > 0:
                time.sleep(self.api_delay)

            try:
                current_price = self._get_price_with_retry(stock.code)

                if current_price is None:
                    logger.error(f"가격 조회 최종 실패 ({stock.code})")
                    continue

                # 목표 비중 계산
                weight = min(
                    self.config.max_single_weight,
                    1.0 / self.config.target_stock_count
                )

                # 투자금액
                invest_amount = self.config.total_capital * weight
                invest_amount = min(invest_amount, available_capital / len(to_buy))

                quantity = int(invest_amount / current_price)

                if quantity > 0:
                    # 손절가 계산: 변동성 기반 동적 손절
                    stock_vol = getattr(stock, 'volatility', 0)
                    if stock_vol > 0:
                        stop_loss = stop_loss_manager.calculate_dynamic_stop(
                            current_price,
                            volatility=stock_vol,
                            fallback_pct=self.config.stop_loss_pct
                        )
                    else:
                        stop_loss = stop_loss_manager.calculate_fixed_stop(
                            current_price,
                            self.config.stop_loss_pct
                        )

                    tp1, tp2 = take_profit_manager.calculate_targets(current_price, stop_loss)

                    orders.append(PendingOrder(
                        code=stock.code,
                        name=stock.name,
                        order_type="BUY",
                        quantity=quantity,
                        price=0,
                        reason=f"긴급 리밸런싱 매수 (순위 {stock.rank}위, 점수 {stock.composite_score:.1f})",
                        stop_loss=stop_loss,
                        take_profit_1=tp1,
                        take_profit_2=tp2,
                        weight=weight
                    ))
                    logger.info(f"매수 주문 생성: {stock.name} ({stock.code}) {quantity}주")

            except Exception as e:
                logger.error(f"주문 생성 실패 ({stock.code}): {e}", exc_info=True)

        logger.info(f"부분 리밸런싱 주문 생성 완료: {len(orders)}건")
        return orders

    def _get_price_with_retry(self, code: str, max_retries: int = 3) -> Optional[float]:
        """가격 조회 (재시도 포함)"""
        retry_delay = 1.0

        for attempt in range(max_retries):
            try:
                price_info = self.client.get_stock_price(code)
                return price_info.price
            except Exception as e:
                if attempt < max_retries - 1:
                    error_msg = str(e)
                    if "500" in error_msg or "서버" in error_msg:
                        logger.warning(
                            f"가격 조회 재시도 ({code}): {attempt + 1}/{max_retries} - {e}"
                        )
                        time.sleep(retry_delay)
                        retry_delay *= 1.5
                    else:
                        raise
                else:
                    raise

        return None

    def _notify_failed_orders(self, failed_orders: List[PendingOrder]):
        """실패 주문 알림"""
        failed_names = [f"• {o.name} ({o.code})" for o in failed_orders[-5:]]
        failed_text = "\n".join(failed_names)
        if len(failed_orders) > 5:
            failed_text += f"\n... 외 {len(failed_orders) - 5}개"

        self.notifier.send_message(
            f"⚠️ <b>주문 생성 실패</b>\n\n"
            f"실패: {len(failed_orders)}건\n"
            f"다음 장 09:00 재시도 예정\n\n"
            f"<b>실패 종목:</b>\n{failed_text}"
        )
        logger.info(f"실패 주문 {len(failed_orders)}개 - 다음 장 재시도 예정")

    def retry_failed_orders(
        self,
        failed_orders: List[PendingOrder],
        daily_trades: List[Dict],
        position_class,
        stop_loss_manager,
        take_profit_manager,
        save_state_callback
    ) -> int:
        """
        실패 주문 재시도

        Args:
            failed_orders: 실패 주문 리스트 (갱신됨)
            daily_trades: 일일 거래 기록
            position_class: Position 클래스
            stop_loss_manager: StopLossManager 클래스
            take_profit_manager: TakeProfitManager 클래스
            save_state_callback: 상태 저장 콜백

        Returns:
            성공한 주문 수
        """
        if not failed_orders:
            return 0

        logger.info(f"{'=' * 60}")
        logger.info(f"실패 주문 재시도: {len(failed_orders)}건")
        logger.info(f"{'=' * 60}")

        self.notifier.send_message(
            f"🔄 <b>실패 주문 재시도</b>\n\n"
            f"• 재시도 대상: {len(failed_orders)}건\n"
            f"• 최대 재시도: 3회"
        )

        success_count = 0
        still_failed = []
        permanently_failed = []
        max_total_retries = 3

        for i, order in enumerate(failed_orders):
            if i > 0:
                time.sleep(self.api_delay)

            # 이미 보유 중인 종목은 스킵
            if order.code in self.portfolio.positions:
                logger.info(f"이미 보유 중 - 재시도 스킵: {order.name}")
                continue

            # 최대 재시도 횟수 초과
            if order.retry_count >= max_total_retries:
                logger.warning(f"최대 재시도 초과 ({order.name}): {order.retry_count}회")
                permanently_failed.append(order)
                continue

            order.retry_count += 1
            logger.info(f"재시도 {order.retry_count}/{max_total_retries}: {order.name} ({order.code})")

            try:
                current_price = self._get_price_with_retry(order.code)
                if current_price is None:
                    raise Exception("가격 조회 실패")

                # 수량 재계산
                quantity = order.quantity
                if quantity <= 0:
                    weight = 1.0 / self.config.target_stock_count
                    invest_amount = self.config.total_capital * weight
                    quantity = int(invest_amount / current_price)

                if quantity <= 0:
                    logger.warning(f"수량 계산 실패 ({order.name}): 가격 {current_price}")
                    continue

                # 주문 실행
                if self.config.dry_run:
                    logger.info(f"[DRY RUN] 재시도 매수: {order.name} {quantity}주 @ {current_price:,}원")
                    order_no = f"RETRY_{datetime.now().strftime('%H%M%S')}"
                else:
                    result = self.client.buy_stock(order.code, quantity, price=0, order_type="01")
                    if not result.success:
                        raise Exception(f"매수 실패: {result.message}")
                    order_no = result.order_no

                # 포지션 추가
                stop_loss = stop_loss_manager.calculate_fixed_stop(current_price, self.config.stop_loss_pct)
                tp1, tp2 = take_profit_manager.calculate_targets(current_price, stop_loss)

                position = position_class(
                    code=order.code,
                    name=order.name,
                    entry_price=current_price,
                    current_price=current_price,
                    quantity=quantity,
                    entry_date=datetime.now(),
                    stop_loss=stop_loss,
                    take_profit_1=tp1,
                    take_profit_2=tp2,
                    highest_price=current_price
                )
                self.portfolio.add_position(position)

                # 거래 기록
                trade_record = {
                    "type": "BUY",
                    "code": order.code,
                    "name": order.name,
                    "quantity": quantity,
                    "price": current_price,
                    "order_no": order_no,
                    "reason": f"[재시도] {order.reason}",
                    "timestamp": datetime.now().isoformat()
                }
                daily_trades.append(trade_record)

                if self.daily_tracker:
                    self.daily_tracker.log_transaction(trade_record)

                logger.info(f"매수 완료 (재시도): {order.name} {quantity}주 @ {current_price:,}원")
                self.notifier.notify_buy(order.code, order.name, quantity, current_price, order.reason)
                success_count += 1

            except Exception as e:
                order.last_error = str(e)[:200]
                logger.error(f"재시도 실패 ({order.name}): {e}")

                if order.retry_count < max_total_retries:
                    still_failed.append(order)

        # 아직 재시도 가능한 주문만 유지
        failed_orders.clear()
        failed_orders.extend(still_failed)
        save_state_callback()

        # 결과 알림
        if success_count > 0 or still_failed:
            self.notifier.send_message(
                f"✅ <b>재시도 결과</b>\n\n"
                f"• 성공: {success_count}건\n"
                f"• 실패: {len(still_failed)}건"
            )

        # 영구 실패 알림
        if permanently_failed:
            self._notify_permanently_failed(permanently_failed)

        logger.info(f"재시도 완료: 성공 {success_count}건, 실패 {len(still_failed)}건, 포기 {len(permanently_failed)}건")
        return success_count

    def _notify_permanently_failed(self, permanently_failed: List[PendingOrder]):
        """영구 실패 주문 알림"""
        failed_names = [f"• {o.name} ({o.code})" for o in permanently_failed]
        failed_text = "\n".join(failed_names)

        self.notifier.send_message(
            f"🚫 <b>매수 포기 (재시도 초과)</b>\n\n"
            f"다음 종목은 3회 재시도 후 매수 포기되었습니다:\n"
            f"{failed_text}\n\n"
            f"다음 리밸런싱까지 편입되지 않습니다."
        )
        logger.warning(f"매수 포기 (재시도 초과): {[o.name for o in permanently_failed]}")

    def execute_pending_orders(
        self,
        pending_orders: List[PendingOrder],
        failed_orders: List[PendingOrder],
        daily_trades: List[Dict],
        order_lock,
        position_class,
        stop_loss_manager,
        take_profit_manager,
        save_state_callback
    ):
        """
        대기 중인 주문 실행

        Args:
            pending_orders: 대기 주문 리스트
            failed_orders: 실패 주문 리스트
            daily_trades: 일일 거래 기록
            order_lock: 주문 락
            position_class: Position 클래스
            stop_loss_manager: StopLossManager 클래스
            take_profit_manager: TakeProfitManager 클래스
            save_state_callback: 상태 저장 콜백
        """
        # 1. 먼저 실패 주문 재시도
        if failed_orders:
            self.retry_failed_orders(
                failed_orders,
                daily_trades,
                position_class,
                stop_loss_manager,
                take_profit_manager,
                save_state_callback
            )

        # 2. 대기 주문 스냅샷 (Lock 보호)
        with order_lock:
            if not pending_orders:
                logger.info("대기 주문 없음")
                return
            orders_to_execute = list(pending_orders)

        logger.info(f"대기 주문 실행: {len(orders_to_execute)}건")

        # 매도 먼저 실행 (자금 확보)
        sell_orders = [o for o in orders_to_execute if o.order_type == "SELL"]
        buy_orders = [o for o in orders_to_execute if o.order_type == "BUY"]

        executed = []

        for i, order in enumerate(sell_orders):
            if i > 0:
                time.sleep(self.api_delay)
            if self._execute_order(order, daily_trades, position_class, stop_loss_manager):
                executed.append(order)

        # 잠시 대기 (주문 체결 시간)
        if sell_orders:
            time.sleep(3)

        for i, order in enumerate(buy_orders):
            if i > 0:
                time.sleep(self.api_delay)
            if self._execute_order(order, daily_trades, position_class, stop_loss_manager):
                executed.append(order)

        # 대기 주문 업데이트 (Lock 보호)
        with order_lock:
            for order in executed:
                if order in pending_orders:
                    pending_orders.remove(order)

        # 상태 저장
        save_state_callback()

        # 리밸런싱 결과 알림
        if executed:
            self._notify_rebalance_result(executed)

        # 최종 보유 종목 미달 알림
        self._check_position_shortage(failed_orders)

    def _execute_order(
        self,
        order: PendingOrder,
        daily_trades: List[Dict],
        position_class,
        stop_loss_manager
    ) -> bool:
        """개별 주문 실행"""
        try:
            if order.order_type == "SELL":
                return self._execute_sell(order, daily_trades)
            else:
                return self._execute_buy(order, daily_trades, position_class, stop_loss_manager)
        except Exception as e:
            logger.error(f"주문 실행 실패 ({order.code}): {e}", exc_info=True)
            return False

    def _execute_buy(
        self,
        order: PendingOrder,
        daily_trades: List[Dict],
        position_class,
        stop_loss_manager
    ) -> bool:
        """매수 주문 실행"""
        try:
            price_info = self.client.get_stock_price(order.code)
            current_price = price_info.price

            if self.config.dry_run:
                logger.info(f"[DRY RUN] 매수: {order.name} {order.quantity}주 @ {current_price:,}원")
                order_no = f"DRY_{datetime.now().strftime('%H%M%S')}"
            else:
                result = self.client.buy_stock(order.code, order.quantity, price=0, order_type="01")
                if not result.success:
                    logger.error(f"매수 실패: {result.message}")
                    return False
                order_no = result.order_no

            # 포지션 추가
            position = position_class(
                code=order.code,
                name=order.name,
                entry_price=current_price,
                current_price=current_price,
                quantity=order.quantity,
                entry_date=datetime.now(),
                stop_loss=order.stop_loss or stop_loss_manager.calculate_fixed_stop(current_price, self.config.stop_loss_pct),
                take_profit_1=order.take_profit_1,
                take_profit_2=order.take_profit_2,
                highest_price=current_price
            )
            self.portfolio.add_position(position)

            # 거래 기록
            trade_record = {
                "type": "BUY",
                "code": order.code,
                "name": order.name,
                "quantity": order.quantity,
                "price": current_price,
                "order_no": order_no,
                "reason": order.reason,
                "timestamp": datetime.now().isoformat()
            }
            daily_trades.append(trade_record)

            if self.daily_tracker:
                self.daily_tracker.log_transaction(trade_record)

            logger.info(f"매수 완료: {order.name} {order.quantity}주 @ {current_price:,}원")

            self.notifier.notify_buy(
                stock_name=order.name,
                stock_code=order.code,
                qty=order.quantity,
                price=current_price,
                order_no=order_no
            )

            return True

        except Exception as e:
            logger.error(f"매수 실행 오류: {e}", exc_info=True)
            return False

    def _execute_sell(self, order: PendingOrder, daily_trades: List[Dict]) -> bool:
        """매도 주문 실행"""
        if order.code not in self.portfolio.positions:
            return False

        try:
            position = self.portfolio.positions[order.code]
            price_info = self.client.get_stock_price(order.code)
            current_price = price_info.price

            if self.config.dry_run:
                logger.info(f"[DRY RUN] 매도: {order.name} {order.quantity}주 @ {current_price:,}원")
                order_no = f"DRY_{datetime.now().strftime('%H%M%S')}"
            else:
                result = self.client.sell_stock(order.code, order.quantity, price=0, order_type="01")
                if not result.success:
                    logger.error(f"매도 실패: {result.message}")
                    return False
                order_no = result.order_no

            # 손익 계산
            pnl = (current_price - position.entry_price) * order.quantity
            pnl_pct = (current_price - position.entry_price) / position.entry_price * 100

            # 포지션 제거
            self.portfolio.remove_position(order.code, current_price)

            # 거래 기록
            trade_record = {
                "type": "SELL",
                "code": order.code,
                "name": order.name,
                "quantity": order.quantity,
                "price": current_price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "order_no": order_no,
                "reason": order.reason,
                "timestamp": datetime.now().isoformat()
            }
            daily_trades.append(trade_record)

            if self.daily_tracker:
                self.daily_tracker.log_transaction(trade_record)

            pnl_str = f"+{pnl:,.0f}" if pnl >= 0 else f"{pnl:,.0f}"
            logger.info(f"매도 완료: {order.name} {order.quantity}주 @ {current_price:,}원 (손익: {pnl_str}원)")

            self.notifier.notify_sell(
                stock_name=order.name,
                stock_code=order.code,
                qty=order.quantity,
                price=current_price,
                order_no=order_no
            )

            return True

        except Exception as e:
            logger.error(f"매도 실행 오류: {e}", exc_info=True)
            return False

    def _notify_rebalance_result(self, executed_orders: List[PendingOrder]):
        """리밸런싱 결과 알림"""
        try:
            buys = [o for o in executed_orders if o.order_type == "BUY"]
            sells = [o for o in executed_orders if o.order_type == "SELL"]

            snapshot = self.portfolio.get_snapshot()
            portfolio_value = int(snapshot.total_value)

            sell_list = []
            for o in sells:
                pos = self.portfolio.positions.get(o.code)
                pnl_pct = 0
                if pos and pos.entry_price > 0:
                    pnl_pct = (o.price - pos.entry_price) / pos.entry_price * 100
                sell_list.append({'name': o.name, 'pnl_pct': pnl_pct})

            buy_list = []
            for o in buys:
                buy_list.append({'name': o.name, 'weight': o.weight})

            self.notifier.notify_rebalance(
                sells=sell_list,
                buys=buy_list,
                portfolio_value=portfolio_value
            )

        except Exception as e:
            logger.error(f"리밸런싱 알림 실패: {e}")

    def _check_position_shortage(self, failed_orders: List[PendingOrder]):
        """최종 보유 종목 수 미달 체크 및 알림"""
        try:
            target_count = self.config.target_stock_count
            current_count = len(self.portfolio.positions)
            failed_count = len(failed_orders)

            if current_count < target_count:
                shortage = target_count - current_count

                reasons = []
                if failed_count > 0:
                    reasons.append(f"재시도 대기: {failed_count}건")
                if shortage > failed_count:
                    reasons.append(f"스크리닝 미달: {shortage - failed_count}건")

                reason_text = " / ".join(reasons) if reasons else "알 수 없음"

                self.notifier.send_message(
                    f"📉 <b>포트폴리오 목표 미달</b>\n\n"
                    f"목표: {target_count}개\n"
                    f"현재 보유: {current_count}개\n"
                    f"부족: {shortage}개\n\n"
                    f"<b>원인:</b> {reason_text}\n\n"
                    f"다음 리밸런싱 시 자동으로 보충 시도됩니다."
                )
                logger.warning(f"포트폴리오 목표 미달: {target_count}개 목표 중 {current_count}개 보유")

        except Exception as e:
            logger.error(f"포지션 미달 체크 오류: {e}")
