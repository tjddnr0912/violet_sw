"""
퀀트 전략 통합 자동매매 엔진

운영 흐름:
1. 08:30 - 장 전 스크리닝 → 매매 대상 종목 리스트 저장
2. 09:00 - 장 오픈 → pending_orders 실행 (매수/매도)
3. 09:05~15:15 - 5분마다 손절/익절 모니터링
4. 15:20 - 일일 리포트 발송
5. 매월 첫 거래일 - 리밸런싱 스크리닝
"""

import time
import logging
import schedule
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from enum import Enum

from .api import KISClient
from .api.kis_quant import KISQuantClient
from .strategy.quant import (
    MultiFactorScreener,
    ScreeningConfig,
    ScreeningResult,
    CompositeScore,
    TechnicalAnalyzer,
    SignalGenerator,
    SignalType,
    Position,
    StopLossManager,
    TakeProfitManager,
    PositionSizer,
    RiskConfig,
    RiskMonitor,
    PortfolioManager,
    RiskLevel
)
from .telegram import TelegramNotifier, get_notifier

# 로깅 설정
logger = logging.getLogger(__name__)


class EngineState(Enum):
    """엔진 상태"""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


class SchedulePhase(Enum):
    """스케줄 단계"""
    PRE_MARKET = "장 전"
    MARKET_OPEN = "장 오픈"
    MARKET_HOURS = "장중"
    MARKET_CLOSE = "장 마감"
    AFTER_MARKET = "장 후"


@dataclass
class PendingOrder:
    """대기 주문"""
    code: str
    name: str
    order_type: str  # "BUY", "SELL"
    quantity: int
    price: float  # 0 = 시장가
    reason: str
    stop_loss: float = 0
    take_profit_1: float = 0
    take_profit_2: float = 0
    weight: float = 0  # 목표 비중
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class QuantEngineConfig:
    """퀀트 엔진 설정"""
    # 투자 설정
    total_capital: int = 100_000_000  # 총 투자금
    target_stock_count: int = 20      # 목표 종목 수

    # 스크리닝 설정
    universe_size: int = 100          # 유니버스 크기
    min_market_cap: int = 3000        # 최소 시가총액 (억원)

    # 팩터 가중치
    value_weight: float = 0.40
    momentum_weight: float = 0.30
    quality_weight: float = 0.30

    # 스케줄 시간 (HH:MM)
    screening_time: str = "08:30"     # 스크리닝 시간
    market_open_time: str = "09:00"   # 장 시작
    market_close_time: str = "15:20"  # 장 종료
    monitoring_interval: int = 5       # 모니터링 간격 (분)

    # 리밸런싱
    rebalance_day: int = 1            # 리밸런싱 일 (매월 N일)

    # 리스크 관리
    max_single_weight: float = 0.10   # 단일 종목 최대 비중
    stop_loss_pct: float = 0.07       # 손절 비율
    trailing_stop: bool = True        # 트레일링 스탑 사용

    # 모드
    dry_run: bool = True              # True: 모의 실행


class QuantTradingEngine:
    """퀀트 전략 통합 자동매매 엔진"""

    def __init__(
        self,
        config: Optional[QuantEngineConfig] = None,
        is_virtual: bool = True
    ):
        """
        Args:
            config: 엔진 설정
            is_virtual: True=모의투자, False=실전투자
        """
        self.config = config or QuantEngineConfig()
        self.is_virtual = is_virtual
        self.state = EngineState.STOPPED
        self.current_phase = SchedulePhase.AFTER_MARKET

        # 클라이언트 초기화
        self.client = KISQuantClient(is_virtual=is_virtual)
        self.notifier = get_notifier()

        # 스크리너 초기화
        screening_config = ScreeningConfig(
            universe_size=self.config.universe_size,
            min_market_cap=self.config.min_market_cap,
            target_count=self.config.target_stock_count,
            value_weight=self.config.value_weight,
            momentum_weight=self.config.momentum_weight,
            quality_weight=self.config.quality_weight
        )
        self.screener = MultiFactorScreener(self.client, screening_config)

        # 리스크 설정
        risk_config = RiskConfig(
            max_single_position=self.config.max_single_weight,
            max_single_loss=self.config.stop_loss_pct
        )

        # 포트폴리오 관리자
        self.portfolio = PortfolioManager(
            total_capital=self.config.total_capital,
            config=risk_config
        )
        self.position_sizer = PositionSizer(risk_config)
        self.signal_generator = SignalGenerator(self.client)

        # 상태 관리
        self.pending_orders: List[PendingOrder] = []
        self.last_screening_result: Optional[ScreeningResult] = None
        self.last_screening_date: Optional[datetime] = None
        self.daily_trades: List[Dict] = []

        # 데이터 저장 경로
        self.data_dir = Path(__file__).parent.parent / "data" / "quant"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 이전 상태 로드
        self._load_state()

    # ========== 상태 관리 ==========

    def _load_state(self):
        """저장된 상태 로드"""
        state_file = self.data_dir / "engine_state.json"
        if state_file.exists():
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 포지션 복원
                for pos_data in data.get("positions", []):
                    position = Position(
                        code=pos_data["code"],
                        name=pos_data["name"],
                        entry_price=pos_data["entry_price"],
                        current_price=pos_data["current_price"],
                        quantity=pos_data["quantity"],
                        entry_date=datetime.fromisoformat(pos_data["entry_date"]),
                        stop_loss=pos_data["stop_loss"],
                        take_profit_1=pos_data["take_profit_1"],
                        take_profit_2=pos_data["take_profit_2"],
                        highest_price=pos_data.get("highest_price", pos_data["entry_price"])
                    )
                    self.portfolio.positions[position.code] = position

                # 마지막 스크리닝 날짜
                if data.get("last_screening_date"):
                    self.last_screening_date = datetime.fromisoformat(data["last_screening_date"])

                logger.info(f"상태 로드 완료: {len(self.portfolio.positions)}개 포지션")

            except Exception as e:
                logger.error(f"상태 로드 실패: {e}")

    def _save_state(self):
        """현재 상태 저장"""
        state_file = self.data_dir / "engine_state.json"

        try:
            positions_data = []
            for code, pos in self.portfolio.positions.items():
                positions_data.append({
                    "code": pos.code,
                    "name": pos.name,
                    "entry_price": pos.entry_price,
                    "current_price": pos.current_price,
                    "quantity": pos.quantity,
                    "entry_date": pos.entry_date.isoformat(),
                    "stop_loss": pos.stop_loss,
                    "take_profit_1": pos.take_profit_1,
                    "take_profit_2": pos.take_profit_2,
                    "highest_price": pos.highest_price
                })

            data = {
                "positions": positions_data,
                "last_screening_date": self.last_screening_date.isoformat() if self.last_screening_date else None,
                "updated_at": datetime.now().isoformat()
            }

            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"상태 저장 실패: {e}")

    # ========== 시간/스케줄 관리 ==========

    def _get_current_phase(self) -> SchedulePhase:
        """현재 시간 단계 확인"""
        now = datetime.now()

        # 주말 체크
        if now.weekday() >= 5:
            return SchedulePhase.AFTER_MARKET

        current_time = now.strftime("%H:%M")

        if current_time < self.config.screening_time:
            return SchedulePhase.AFTER_MARKET
        elif current_time < self.config.market_open_time:
            return SchedulePhase.PRE_MARKET
        elif current_time < self.config.market_close_time:
            return SchedulePhase.MARKET_HOURS
        elif current_time < "15:30":
            return SchedulePhase.MARKET_CLOSE
        else:
            return SchedulePhase.AFTER_MARKET

    def _is_rebalance_day(self) -> bool:
        """리밸런싱 일 확인"""
        now = datetime.now()

        # 매월 첫 거래일 (주말 제외)
        if now.day <= 3:
            # 1~3일 중 첫 평일
            first_weekday = now.replace(day=1)
            while first_weekday.weekday() >= 5:
                first_weekday += timedelta(days=1)

            if now.date() == first_weekday.date():
                return True

        # 설정된 일자
        if now.day == self.config.rebalance_day:
            return now.weekday() < 5  # 평일만

        return False

    def _is_trading_time(self) -> bool:
        """거래 시간 확인"""
        phase = self._get_current_phase()
        return phase in [SchedulePhase.MARKET_HOURS, SchedulePhase.MARKET_OPEN]

    # ========== 스크리닝 ==========

    def run_screening(self) -> Optional[ScreeningResult]:
        """
        멀티팩터 스크리닝 실행

        장 전(08:30) 또는 리밸런싱 일에 실행
        """
        logger.info("=" * 60)
        logger.info("멀티팩터 스크리닝 시작")
        logger.info("=" * 60)

        try:
            # 스크리닝 실행
            result = self.screener.run_screening(
                progress_callback=lambda cur, total, code:
                    logger.info(f"스크리닝 진행: {cur}/{total} ({code})")
            )

            self.last_screening_result = result
            self.last_screening_date = datetime.now()

            # 결과 저장
            self._save_screening_result(result)

            # 텔레그램 알림
            self._notify_screening_result(result)

            logger.info(f"스크리닝 완료: {len(result.selected_stocks)}개 종목 선정")

            return result

        except Exception as e:
            logger.error(f"스크리닝 실패: {e}")
            self.notifier.notify_error("스크리닝 실패", str(e))
            return None

    def _save_screening_result(self, result: ScreeningResult):
        """스크리닝 결과 저장"""
        try:
            filename = f"screening_{result.timestamp.strftime('%Y%m%d_%H%M')}.json"
            filepath = self.data_dir / filename

            data = {
                "timestamp": result.timestamp.isoformat(),
                "universe_count": result.universe_count,
                "filtered_count": result.filtered_count,
                "elapsed_seconds": result.elapsed_seconds,
                "selected_stocks": [
                    {
                        "rank": s.rank,
                        "code": s.code,
                        "name": s.name,
                        "composite_score": s.composite_score,
                        "value_score": s.value_score,
                        "momentum_score": s.momentum_score,
                        "quality_score": s.quality_score,
                        "per": s.per,
                        "pbr": s.pbr,
                        "roe": s.roe,
                        "return_12m": s.return_12m
                    }
                    for s in result.selected_stocks
                ]
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"스크리닝 결과 저장 실패: {e}")

    def _notify_screening_result(self, result: ScreeningResult):
        """스크리닝 결과 텔레그램 알림"""
        try:
            top_5 = result.selected_stocks[:5]
            stocks_text = "\n".join([
                f"{s.rank}. {s.name} ({s.code}) - 점수: {s.composite_score:.1f}"
                for s in top_5
            ])

            message = (
                f"📊 <b>멀티팩터 스크리닝 완료</b>\n\n"
                f"유니버스: {result.universe_count}개\n"
                f"필터 통과: {result.filtered_count}개\n"
                f"최종 선정: {len(result.selected_stocks)}개\n"
                f"소요시간: {result.elapsed_seconds:.1f}초\n\n"
                f"<b>상위 5종목:</b>\n{stocks_text}"
            )

            self.notifier.send_message(message)

        except Exception as e:
            logger.error(f"스크리닝 알림 실패: {e}")

    # ========== 리밸런싱 주문 생성 ==========

    def generate_rebalance_orders(self) -> List[PendingOrder]:
        """
        리밸런싱 주문 생성

        스크리닝 결과 기반으로 매수/매도 주문 생성
        """
        if not self.last_screening_result:
            logger.warning("스크리닝 결과 없음 - 스크리닝 먼저 실행 필요")
            return []

        orders = []
        result = self.last_screening_result

        # 현재 보유 종목
        current_holdings = set(self.portfolio.positions.keys())

        # 목표 종목
        target_stocks = {s.code: s for s in result.selected_stocks}
        target_holdings = set(target_stocks.keys())

        # 매도 대상: 보유 중이지만 목표에 없는 종목
        to_sell = current_holdings - target_holdings

        # 매수 대상: 목표에 있지만 미보유 종목
        to_buy = target_holdings - current_holdings

        logger.info(f"리밸런싱: 매도 {len(to_sell)}개, 매수 {len(to_buy)}개")

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

        for code in to_buy:
            stock = target_stocks[code]

            # 포지션 사이징
            try:
                price_info = self.client.get_stock_price(code)
                current_price = price_info.price

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
                    # 손절/익절가 계산
                    stop_loss = StopLossManager.calculate_fixed_stop(
                        current_price,
                        self.config.stop_loss_pct
                    )
                    tp1, tp2 = TakeProfitManager.calculate_targets(current_price, stop_loss)

                    orders.append(PendingOrder(
                        code=code,
                        name=stock.name,
                        order_type="BUY",
                        quantity=quantity,
                        price=0,  # 시장가
                        reason=f"리밸런싱 매수 (순위 {stock.rank}위, 점수 {stock.composite_score:.1f})",
                        stop_loss=stop_loss,
                        take_profit_1=tp1,
                        take_profit_2=tp2,
                        weight=weight
                    ))

            except Exception as e:
                logger.error(f"주문 생성 실패 ({code}): {e}")

        self.pending_orders = orders
        return orders

    # ========== 주문 실행 ==========

    def execute_pending_orders(self):
        """
        대기 중인 주문 실행

        장 시작 시(09:00) 호출
        """
        if not self.pending_orders:
            logger.info("대기 주문 없음")
            return

        logger.info(f"대기 주문 실행: {len(self.pending_orders)}건")

        # 매도 먼저 실행 (자금 확보)
        sell_orders = [o for o in self.pending_orders if o.order_type == "SELL"]
        buy_orders = [o for o in self.pending_orders if o.order_type == "BUY"]

        executed = []

        for order in sell_orders:
            if self._execute_order(order):
                executed.append(order)

        # 잠시 대기 (주문 체결 시간)
        if sell_orders:
            time.sleep(3)

        for order in buy_orders:
            if self._execute_order(order):
                executed.append(order)

        # 대기 주문 초기화
        self.pending_orders = [o for o in self.pending_orders if o not in executed]

        # 상태 저장
        self._save_state()

        # 리밸런싱 결과 알림
        if executed:
            self._notify_rebalance_result(executed)

    def _execute_order(self, order: PendingOrder) -> bool:
        """개별 주문 실행"""
        try:
            if order.order_type == "SELL":
                return self._execute_sell(order)
            else:
                return self._execute_buy(order)
        except Exception as e:
            logger.error(f"주문 실행 실패 ({order.code}): {e}")
            return False

    def _execute_buy(self, order: PendingOrder) -> bool:
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
            position = Position(
                code=order.code,
                name=order.name,
                entry_price=current_price,
                current_price=current_price,
                quantity=order.quantity,
                entry_date=datetime.now(),
                stop_loss=order.stop_loss or StopLossManager.calculate_fixed_stop(current_price, self.config.stop_loss_pct),
                take_profit_1=order.take_profit_1,
                take_profit_2=order.take_profit_2,
                highest_price=current_price
            )
            self.portfolio.add_position(position)

            # 거래 기록
            self.daily_trades.append({
                "type": "BUY",
                "code": order.code,
                "name": order.name,
                "quantity": order.quantity,
                "price": current_price,
                "order_no": order_no,
                "reason": order.reason,
                "timestamp": datetime.now().isoformat()
            })

            logger.info(f"매수 완료: {order.name} {order.quantity}주 @ {current_price:,}원")

            # 알림
            self.notifier.notify_buy(
                stock_name=order.name,
                stock_code=order.code,
                qty=order.quantity,
                price=current_price,
                order_no=order_no
            )

            return True

        except Exception as e:
            logger.error(f"매수 실행 오류: {e}")
            return False

    def _execute_sell(self, order: PendingOrder) -> bool:
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
            self.daily_trades.append({
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
            })

            pnl_str = f"+{pnl:,.0f}" if pnl >= 0 else f"{pnl:,.0f}"
            logger.info(f"매도 완료: {order.name} {order.quantity}주 @ {current_price:,}원 (손익: {pnl_str}원)")

            # 알림
            self.notifier.notify_sell(
                stock_name=order.name,
                stock_code=order.code,
                qty=order.quantity,
                price=current_price,
                order_no=order_no
            )

            return True

        except Exception as e:
            logger.error(f"매도 실행 오류: {e}")
            return False

    def _notify_rebalance_result(self, executed_orders: List[PendingOrder]):
        """리밸런싱 결과 알림"""
        try:
            buys = [o for o in executed_orders if o.order_type == "BUY"]
            sells = [o for o in executed_orders if o.order_type == "SELL"]

            message = (
                f"🔄 <b>리밸런싱 완료</b>\n\n"
                f"매수: {len(buys)}종목\n"
                f"매도: {len(sells)}종목\n\n"
            )

            if sells:
                message += "<b>매도:</b>\n"
                for o in sells[:5]:
                    message += f"• {o.name}\n"
                if len(sells) > 5:
                    message += f"...외 {len(sells)-5}종목\n"
                message += "\n"

            if buys:
                message += "<b>매수:</b>\n"
                for o in buys[:5]:
                    message += f"• {o.name} ({o.quantity}주)\n"
                if len(buys) > 5:
                    message += f"...외 {len(buys)-5}종목\n"

            self.notifier.send_message(message)

        except Exception as e:
            logger.error(f"리밸런싱 알림 실패: {e}")

    # ========== 장중 모니터링 ==========

    def monitor_positions(self):
        """
        포지션 모니터링 (손절/익절 체크)

        장중 5분마다 실행
        """
        if not self.portfolio.positions:
            return

        logger.info(f"포지션 모니터링: {len(self.portfolio.positions)}개")

        for code, position in list(self.portfolio.positions.items()):
            try:
                # 현재가 업데이트
                price_info = self.client.get_stock_price(code)
                position.current_price = price_info.price

                # 손절 체크
                if position.current_price <= position.stop_loss:
                    self._trigger_stop_loss(position)
                    continue

                # 익절 체크
                if not position.tp1_executed and position.current_price >= position.take_profit_1:
                    self._trigger_take_profit(position, stage=1)
                elif not position.tp2_executed and position.current_price >= position.take_profit_2:
                    self._trigger_take_profit(position, stage=2)

                # 트레일링 스탑 업데이트
                if self.config.trailing_stop:
                    new_stop = StopLossManager.update_trailing_stop(
                        position,
                        self.config.stop_loss_pct
                    )
                    if new_stop > position.stop_loss:
                        position.stop_loss = new_stop
                        logger.info(f"{position.name}: 손절가 상향 → {new_stop:,.0f}원")

            except Exception as e:
                logger.error(f"모니터링 오류 ({code}): {e}")

        # 상태 저장
        self._save_state()

        # 리스크 체크
        alerts = self.portfolio.check_risks()
        for alert in alerts:
            if alert.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                self.notifier.send_message(
                    f"⚠️ <b>리스크 경고</b>\n\n"
                    f"유형: {alert.alert_type}\n"
                    f"내용: {alert.message}\n"
                    f"조치: {alert.action_required}"
                )

    def _trigger_stop_loss(self, position: Position):
        """손절 실행"""
        logger.warning(f"손절 트리거: {position.name} ({position.profit_pct:+.1f}%)")

        order = PendingOrder(
            code=position.code,
            name=position.name,
            order_type="SELL",
            quantity=position.quantity,
            price=0,
            reason=f"손절 ({position.profit_pct:+.1f}%)"
        )

        if self._execute_order(order):
            self.notifier.send_message(
                f"🔴 <b>손절 실행</b>\n\n"
                f"종목: {position.name}\n"
                f"수량: {position.quantity}주\n"
                f"손익: {position.profit_pct:+.1f}%"
            )

    def _trigger_take_profit(self, position: Position, stage: int):
        """익절 실행"""
        qty = TakeProfitManager.calculate_staged_sell_qty(position.quantity, stage)

        if qty <= 0:
            return

        logger.info(f"익절 트리거 ({stage}차): {position.name} {qty}주 ({position.profit_pct:+.1f}%)")

        order = PendingOrder(
            code=position.code,
            name=position.name,
            order_type="SELL",
            quantity=qty,
            price=0,
            reason=f"{stage}차 익절 ({position.profit_pct:+.1f}%)"
        )

        if self._execute_order(order):
            if stage == 1:
                position.tp1_executed = True
            else:
                position.tp2_executed = True

            self.notifier.send_message(
                f"🟢 <b>{stage}차 익절 실행</b>\n\n"
                f"종목: {position.name}\n"
                f"수량: {qty}주\n"
                f"수익: {position.profit_pct:+.1f}%"
            )

    # ========== 일일 리포트 ==========

    def generate_daily_report(self):
        """일일 리포트 생성 및 발송"""
        snapshot = self.portfolio.get_snapshot()

        # 보유 종목 정보
        positions_text = ""
        if snapshot.positions:
            for pos in snapshot.positions:
                pnl_str = f"+{pos.profit_pct:.1f}" if pos.profit_pct >= 0 else f"{pos.profit_pct:.1f}"
                positions_text += f"• {pos.name}: {pnl_str}%\n"
        else:
            positions_text = "없음"

        # 오늘 거래 내역
        trades_text = ""
        if self.daily_trades:
            for t in self.daily_trades[-5:]:
                pnl_str = ""
                if t["type"] == "SELL" and "pnl" in t:
                    pnl_str = f" ({t['pnl_pct']:+.1f}%)"
                trades_text += f"• {t['type']} {t['name']}{pnl_str}\n"
        else:
            trades_text = "없음"

        message = (
            f"📈 <b>일일 리포트</b>\n\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"<b>포트폴리오</b>\n"
            f"총 평가: {snapshot.total_value:,.0f}원\n"
            f"투자금: {snapshot.invested:,.0f}원\n"
            f"현금: {snapshot.cash:,.0f}원\n"
            f"총 손익: {snapshot.total_pnl_pct:+.2f}%\n"
            f"MDD: {snapshot.mdd*100:.1f}%\n\n"
            f"<b>보유 종목 ({len(snapshot.positions)}개)</b>\n"
            f"{positions_text}\n"
            f"<b>오늘 거래</b>\n"
            f"{trades_text}"
        )

        self.notifier.send_message(message)

        # 일일 거래 초기화
        self.daily_trades = []

        logger.info("일일 리포트 발송 완료")

    # ========== 스케줄러 ==========

    def _setup_schedule(self):
        """스케줄 설정"""
        # 장 전 스크리닝 (리밸런싱 일에만)
        schedule.every().day.at(self.config.screening_time).do(self._on_pre_market)

        # 장 시작 - 주문 실행
        schedule.every().day.at(self.config.market_open_time).do(self._on_market_open)

        # 장중 모니터링
        schedule.every(self.config.monitoring_interval).minutes.do(self._on_monitoring)

        # 장 마감 리포트
        schedule.every().day.at(self.config.market_close_time).do(self._on_market_close)

        logger.info("스케줄 설정 완료")
        logger.info(f"  - 스크리닝: {self.config.screening_time} (리밸런싱 일)")
        logger.info(f"  - 주문 실행: {self.config.market_open_time}")
        logger.info(f"  - 모니터링: {self.config.monitoring_interval}분 간격")
        logger.info(f"  - 리포트: {self.config.market_close_time}")

    def _on_pre_market(self):
        """장 전 이벤트"""
        if self.state != EngineState.RUNNING:
            return

        # 주말 제외
        if datetime.now().weekday() >= 5:
            return

        self.current_phase = SchedulePhase.PRE_MARKET
        logger.info("=" * 60)
        logger.info("장 전 처리 시작")

        # 리밸런싱 일인 경우 스크리닝 실행
        if self._is_rebalance_day():
            logger.info("리밸런싱 일 - 스크리닝 실행")
            self.run_screening()
            self.generate_rebalance_orders()
        else:
            logger.info("리밸런싱 일 아님 - 스크리닝 스킵")

    def _on_market_open(self):
        """장 시작 이벤트"""
        if self.state != EngineState.RUNNING:
            return

        if datetime.now().weekday() >= 5:
            return

        self.current_phase = SchedulePhase.MARKET_OPEN
        logger.info("=" * 60)
        logger.info("장 시작 - 대기 주문 실행")

        # 대기 주문 실행
        self.execute_pending_orders()

        self.current_phase = SchedulePhase.MARKET_HOURS

    def _on_monitoring(self):
        """모니터링 이벤트"""
        if self.state != EngineState.RUNNING:
            return

        if not self._is_trading_time():
            return

        self.monitor_positions()

    def _on_market_close(self):
        """장 마감 이벤트"""
        if self.state != EngineState.RUNNING:
            return

        if datetime.now().weekday() >= 5:
            return

        self.current_phase = SchedulePhase.MARKET_CLOSE
        logger.info("=" * 60)
        logger.info("장 마감 - 일일 리포트 생성")

        # 일일 리포트
        self.generate_daily_report()

        # 상태 저장
        self._save_state()

        self.current_phase = SchedulePhase.AFTER_MARKET

    # ========== 엔진 제어 ==========

    def start(self):
        """엔진 시작"""
        if self.state == EngineState.RUNNING:
            logger.warning("엔진이 이미 실행 중입니다")
            return

        # API 키 검증
        if not self.client.auth.validate_credentials():
            logger.error("API 키가 설정되지 않았습니다")
            return

        self.state = EngineState.RUNNING

        mode = "모의투자" if self.is_virtual else "실전투자"
        dry_run = "[DRY RUN] " if self.config.dry_run else ""

        logger.info("=" * 60)
        logger.info(f"{dry_run}퀀트 자동매매 엔진 시작 ({mode})")
        logger.info(f"목표 종목 수: {self.config.target_stock_count}")
        logger.info(f"총 투자금: {self.config.total_capital:,}원")
        logger.info(f"현재 보유: {len(self.portfolio.positions)}종목")
        logger.info("=" * 60)

        # 알림
        self.notifier.notify_system("퀀트 엔진 시작", {
            "모드": mode,
            "목표 종목": self.config.target_stock_count,
            "투자금": f"{self.config.total_capital:,}원"
        })

        # 스케줄 설정
        self._setup_schedule()

        # 스케줄 루프
        try:
            while self.state == EngineState.RUNNING:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """엔진 정지"""
        self.state = EngineState.STOPPED
        schedule.clear()

        # 상태 저장
        self._save_state()

        logger.info("퀀트 자동매매 엔진 정지")

        self.notifier.notify_system("퀀트 엔진 정지", {
            "보유 종목": len(self.portfolio.positions),
            "오늘 거래": len(self.daily_trades)
        })

    def pause(self):
        """엔진 일시정지"""
        self.state = EngineState.PAUSED
        logger.info("퀀트 엔진 일시정지")

    def resume(self):
        """엔진 재개"""
        if self.state == EngineState.PAUSED:
            self.state = EngineState.RUNNING
            logger.info("퀀트 엔진 재개")

    def get_status(self) -> Dict[str, Any]:
        """엔진 상태 반환"""
        snapshot = self.portfolio.get_snapshot()

        return {
            "state": self.state.value,
            "phase": self.current_phase.value,
            "mode": "모의투자" if self.is_virtual else "실전투자",
            "dry_run": self.config.dry_run,
            "total_value": snapshot.total_value,
            "cash": snapshot.cash,
            "positions": len(self.portfolio.positions),
            "pending_orders": len(self.pending_orders),
            "total_pnl_pct": snapshot.total_pnl_pct,
            "last_screening": self.last_screening_date.isoformat() if self.last_screening_date else None
        }

    # ========== 수동 실행 메서드 ==========

    def manual_screening(self) -> Optional[ScreeningResult]:
        """수동 스크리닝 실행"""
        return self.run_screening()

    def manual_rebalance(self):
        """수동 리밸런싱 실행"""
        if not self._is_trading_time():
            logger.warning("거래 시간이 아닙니다")
            return

        # 스크리닝
        result = self.run_screening()
        if not result:
            return

        # 주문 생성
        orders = self.generate_rebalance_orders()
        logger.info(f"리밸런싱 주문 생성: {len(orders)}건")

        # 즉시 실행
        self.execute_pending_orders()

    def manual_monitor(self):
        """수동 모니터링 실행"""
        self.monitor_positions()
