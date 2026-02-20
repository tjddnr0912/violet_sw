"""
퀀트 전략 통합 자동매매 엔진

운영 흐름:
1. 08:30 - 장 전 스크리닝 → 매매 대상 종목 리스트 저장
2. 09:00 - 장 오픈 → pending_orders 실행 (매수/매도)
3. 09:05~15:15 - 5분마다 손절/익절 모니터링
4. 15:20 - 일일 리포트 발송
5. 매월 첫 거래일 - 리밸런싱 스크리닝
"""

import os
import time
import logging
import schedule
import json
import threading
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
from .utils import is_trading_day, get_trading_hours, get_market_open_time
from .utils.balance_helpers import parse_balance
from .quant_modules import EngineState, SchedulePhase, PendingOrder, EngineStateManager, OrderExecutor, MonthlyTracker, DailyTracker, DailySnapshot, ReportGenerator, PositionMonitor, ScheduleHandler

# 로깅 설정
logger = logging.getLogger(__name__)

# API Rate Limit 설정 (order_executor 정의를 공유)
from .quant_modules.order_executor import API_DELAY_VIRTUAL, API_DELAY_REAL


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

    def __post_init__(self):
        """설정값 검증"""
        errors = []

        # 투자 설정 검증
        if not (1_000_000 <= self.total_capital <= 10_000_000_000):
            errors.append(f"total_capital은 100만~100억 사이여야 합니다: {self.total_capital:,}")
        if not (1 <= self.target_stock_count <= 50):
            errors.append(f"target_stock_count는 1~50 사이여야 합니다: {self.target_stock_count}")

        # 스크리닝 설정 검증
        if not (10 <= self.universe_size <= 500):
            errors.append(f"universe_size는 10~500 사이여야 합니다: {self.universe_size}")
        if self.target_stock_count > self.universe_size:
            errors.append(f"target_stock_count({self.target_stock_count})가 universe_size({self.universe_size})보다 클 수 없습니다")
        if not (100 <= self.min_market_cap <= 100000):
            errors.append(f"min_market_cap은 100~100000억 사이여야 합니다: {self.min_market_cap}")

        # 팩터 가중치 검증
        for name, weight in [
            ("value_weight", self.value_weight),
            ("momentum_weight", self.momentum_weight),
            ("quality_weight", self.quality_weight)
        ]:
            if not (0.0 <= weight <= 1.0):
                errors.append(f"{name}은(는) 0.0~1.0 사이여야 합니다: {weight}")

        weight_sum = self.value_weight + self.momentum_weight + self.quality_weight
        if not (0.99 <= weight_sum <= 1.01):
            errors.append(f"팩터 가중치 합계는 1.0이어야 합니다: {weight_sum:.2f}")

        # 모니터링 간격 검증
        if not (1 <= self.monitoring_interval <= 60):
            errors.append(f"monitoring_interval은 1~60분 사이여야 합니다: {self.monitoring_interval}")

        # 리밸런싱 일 검증
        if not (1 <= self.rebalance_day <= 28):
            errors.append(f"rebalance_day는 1~28 사이여야 합니다: {self.rebalance_day}")

        # 리스크 관리 검증
        if not (0.01 <= self.max_single_weight <= 0.5):
            errors.append(f"max_single_weight는 0.01~0.5 사이여야 합니다: {self.max_single_weight}")
        if not (0.01 <= self.stop_loss_pct <= 0.5):
            errors.append(f"stop_loss_pct는 0.01~0.5 (1%~50%) 사이여야 합니다: {self.stop_loss_pct}")

        if errors:
            raise ValueError("설정 검증 실패:\n" + "\n".join(f"  - {e}" for e in errors))


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

        # 상태 관리자
        self.data_dir = Path(__file__).parent.parent / "data" / "quant"
        self.state_manager = EngineStateManager(
            data_dir=self.data_dir,
            notifier=self.notifier
        )

        # 상태 관리 (state_manager와 동기화)
        self.pending_orders: List[PendingOrder] = []
        self.last_screening_result: Optional[ScreeningResult] = None
        self.daily_trades: List[Dict] = []

        # 이전 상태 로드 (state_manager 사용)
        self.state_manager.load_state(self.portfolio.positions, Position)

        # 동시성 제어 (state_manager의 lock 사용)
        self._position_lock = self.state_manager.acquire_position_lock()
        self._order_lock = self.state_manager.acquire_order_lock()
        self._screening_lock = self.state_manager.acquire_screening_lock()

        # 월간 트래커
        self.monthly_tracker = MonthlyTracker(data_dir=self.data_dir)
        self.monthly_trades: List[Dict] = []  # 월간 거래 추적

        # 일별 트래커
        self.daily_tracker = DailyTracker(data_dir=self.data_dir)
        if not self.daily_tracker.initial_capital:
            self.daily_tracker.initial_capital = self.config.total_capital
            self.daily_tracker._save_history()

        # 주문 실행기
        self.order_executor = OrderExecutor(
            client=self.client,
            portfolio=self.portfolio,
            notifier=self.notifier,
            config=self.config,
            is_virtual=is_virtual,
            daily_tracker=self.daily_tracker
        )

        # 리포트 생성기
        self.report_generator = ReportGenerator(
            client=self.client,
            notifier=self.notifier,
            daily_tracker=self.daily_tracker,
            monthly_tracker=self.monthly_tracker,
            portfolio=self.portfolio,
            config=self.config,
        )

        # 포지션 모니터
        self.position_monitor = PositionMonitor(
            client=self.client,
            portfolio=self.portfolio,
            notifier=self.notifier,
            config=self.config,
            is_virtual=is_virtual,
            order_executor=self.order_executor,
        )

        # 스케줄 핸들러
        self.schedule_handler = ScheduleHandler(engine=self)

        # 긴급 리밸런싱 모드 (보유 70% 미만 시 활성화)
        self._urgent_rebalance_mode = False

        # 제로 포지션 복구 쿨다운 (메모리 전용, 재시작 시 리셋)
        self._last_zero_recovery_date: Optional[str] = None

    # ========== 상태 관리 (state_manager 위임) ==========

    @property
    def failed_orders(self) -> List[PendingOrder]:
        """실패한 주문 목록 (state_manager에서 관리)"""
        return self.state_manager.failed_orders

    @failed_orders.setter
    def failed_orders(self, value: List[PendingOrder]):
        """실패한 주문 목록 설정"""
        self.state_manager.failed_orders = value

    @property
    def last_screening_date(self) -> Optional[datetime]:
        """마지막 스크리닝 날짜"""
        return self.state_manager.last_screening_date

    @last_screening_date.setter
    def last_screening_date(self, value: Optional[datetime]):
        """마지막 스크리닝 날짜 설정"""
        self.state_manager.last_screening_date = value

    @property
    def last_rebalance_date(self) -> Optional[datetime]:
        """마지막 리밸런싱 날짜"""
        return self.state_manager.last_rebalance_date

    @last_rebalance_date.setter
    def last_rebalance_date(self, value: Optional[datetime]):
        """마지막 리밸런싱 날짜 설정"""
        self.state_manager.last_rebalance_date = value

    @property
    def last_rebalance_month(self) -> Optional[str]:
        """마지막 리밸런싱 월 (YYYY-MM)"""
        return self.state_manager.last_rebalance_month

    @last_rebalance_month.setter
    def last_rebalance_month(self, value: Optional[str]):
        """마지막 리밸런싱 월 설정"""
        self.state_manager.last_rebalance_month = value

    @property
    def _screening_in_progress(self) -> bool:
        """스크리닝 진행 중 여부"""
        return self.state_manager.screening_in_progress

    @_screening_in_progress.setter
    def _screening_in_progress(self, value: bool):
        """스크리닝 진행 중 상태 설정"""
        self.state_manager.screening_in_progress = value

    def _save_state(self):
        """현재 상태 저장 (state_manager 위임)"""
        self.state_manager.save_state(
            portfolio_positions=self.portfolio.positions,
            failed_orders=self.failed_orders
        )

    # ========== 시간/스케줄 관리 ==========

    def _get_current_phase(self) -> SchedulePhase:
        """현재 시간 단계 확인"""
        now = datetime.now()

        # 휴장일 체크 (주말 + 공휴일)
        if not is_trading_day(now):
            return SchedulePhase.AFTER_MARKET

        current_time = now.strftime("%H:%M")

        # 특수 개장 시간 적용 (1/2 등 10시 개장)
        market_open, market_close = get_trading_hours(now)
        screening_time = self.config.screening_time

        # 스크리닝 시간을 개장 30분 전으로 동적 조정
        open_dt = datetime.strptime(market_open, "%H:%M")
        pre_market_dt = open_dt - timedelta(minutes=30)
        adjusted_screening = pre_market_dt.strftime("%H:%M")
        if market_open > "09:00":
            screening_time = adjusted_screening

        if current_time < screening_time:
            return SchedulePhase.AFTER_MARKET
        elif current_time < market_open:
            return SchedulePhase.PRE_MARKET
        elif current_time < market_close:  # 실제 마감 시간 사용
            return SchedulePhase.MARKET_HOURS
        else:
            return SchedulePhase.AFTER_MARKET

    def _is_rebalance_day(self) -> bool:
        """리밸런싱 일 확인"""
        now = datetime.now()
        current_month = now.strftime("%Y-%m")

        # 1. 긴급 리밸런싱: 보유 종목이 목표의 70% 미만이면 허용 (월 1회 제한)
        current_count = len(self.portfolio.positions)
        target_count = self.config.target_stock_count
        threshold = target_count * 0.7

        if current_count < threshold:
            if current_count == 0:
                # 포지션 0개 = 위기 상태 → 월간 잠금 무시 (안전망)
                logger.info(
                    f"📢 제로 포지션 긴급 리밸런싱 트리거: 보유 0/{target_count}개"
                )
                self._urgent_rebalance_mode = True
                return True

            # 1개 이상: 이번 달 긴급 리밸런싱 이미 실행했으면 스킵
            if self.state_manager.last_urgent_rebalance_month == current_month:
                logger.debug(f"이번 달({current_month}) 긴급 리밸런싱 이미 완료됨")
                return False

            logger.info(
                f"📢 긴급 리밸런싱 트리거: 보유 {current_count}/{target_count}개 "
                f"({current_count/target_count*100:.0f}% < 70%)"
            )
            self._urgent_rebalance_mode = True
            return True

        # 2. 월초 리밸런싱 중복 방지
        if self.last_rebalance_month == current_month:
            logger.debug(f"이번 달({current_month}) 월초 리밸런싱 이미 완료됨")
            return False

        # 오늘이 거래일이 아니면 리밸런싱 불가
        if not is_trading_day(now):
            return False

        # 매월 첫 거래일 (휴장일 제외)
        if now.day <= 7:  # 연휴 대비 7일까지 체크
            # 1일부터 첫 거래일 찾기
            first_trading_day = now.replace(day=1)
            while not is_trading_day(first_trading_day):
                first_trading_day += timedelta(days=1)

            if now.date() == first_trading_day.date():
                return True

        # 설정된 일자
        if now.day == self.config.rebalance_day:
            return is_trading_day(now)

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
        # 중복 실행 방지
        with self._screening_lock:
            if self._screening_in_progress:
                logger.warning("스크리닝이 이미 진행 중입니다. 중복 실행 스킵.")
                return None
            self._screening_in_progress = True

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
            logger.error(f"스크리닝 실패: {e}", exc_info=True)
            from src.utils.error_formatter import format_user_error
            self.notifier.send_message(format_user_error(e, "스크리닝"))
            return None

        finally:
            # 스크리닝 플래그 해제 (성공/실패 무관)
            with self._screening_lock:
                self._screening_in_progress = False

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

            # 목표 미달 경고
            target_count = self.config.target_stock_count
            selected_count = len(result.selected_stocks)
            shortage_warning = ""

            if selected_count < target_count:
                shortage = target_count - selected_count
                shortage_warning = (
                    f"\n\n⚠️ <b>목표 미달 경고</b>\n"
                    f"목표: {target_count}개 / 선정: {selected_count}개\n"
                    f"부족: {shortage}개 (필터 조건 미충족)"
                )
                logger.warning(f"스크리닝 목표 미달: {target_count}개 목표 중 {selected_count}개만 선정")

            message = (
                f"📊 <b>멀티팩터 스크리닝 완료</b>\n\n"
                f"유니버스: {result.universe_count}개\n"
                f"필터 통과: {result.filtered_count}개\n"
                f"최종 선정: {selected_count}개 / 목표: {target_count}개\n"
                f"소요시간: {result.elapsed_seconds:.1f}초\n\n"
                f"<b>상위 5종목:</b>\n{stocks_text}"
                f"{shortage_warning}"
            )

            self.notifier.send_message(message)

        except Exception as e:
            logger.error(f"스크리닝 알림 실패: {e}")

    # ========== KIS 포지션 동기화 ==========

    def sync_positions_from_kis(self) -> dict:
        """
        KIS 계좌의 보유종목을 내부 포지션으로 동기화

        내부 포지션이 0개인데 KIS에 보유종목이 있을 때 사용.
        손절가/익절가는 매입단가 기준으로 재계산.

        Returns:
            {"success": bool, "message": str, "synced": int}
        """
        try:
            balance_info = self.client.get_balance()
            kis_stocks = balance_info.get('stocks', [])

            if not kis_stocks:
                return {"success": False, "message": "KIS 계좌에 보유종목이 없습니다.", "synced": 0}

            # 이미 내부에 있는 종목은 스킵
            existing_codes = set(self.portfolio.positions.keys())
            new_stocks = [s for s in kis_stocks if s.code not in existing_codes]

            if not new_stocks:
                return {"success": True, "message": "모든 KIS 종목이 이미 동기화되어 있습니다.", "synced": 0}

            synced = 0
            for stock in new_stocks:
                stop_loss = StopLossManager.calculate_fixed_stop(
                    stock.avg_price, self.config.stop_loss_pct
                )
                tp1, tp2 = TakeProfitManager.calculate_targets(
                    stock.avg_price, stop_loss
                )

                position = Position(
                    code=stock.code,
                    name=stock.name,
                    entry_price=float(stock.avg_price),
                    current_price=float(stock.current_price),
                    quantity=stock.qty,
                    entry_date=datetime.now(),
                    stop_loss=stop_loss,
                    take_profit_1=tp1,
                    take_profit_2=tp2,
                    highest_price=float(max(stock.current_price, stock.avg_price))
                )

                self.portfolio.positions[position.code] = position
                synced += 1
                logger.info(
                    f"포지션 동기화: {stock.name} ({stock.code}) "
                    f"{stock.qty}주 @ {stock.avg_price:,}원 "
                    f"(현재가: {stock.current_price:,}원, 수익: {stock.profit_rate:+.1f}%)"
                )

            # 현금도 KIS 기준으로 동기화
            self.portfolio.cash = balance_info.get('cash', self.portfolio.cash)

            self._save_state()

            msg = f"KIS 포지션 {synced}개 동기화 완료 (총 {len(self.portfolio.positions)}종목)"
            logger.info(msg)
            self.notifier.send_message(
                f"🔄 <b>포지션 동기화 완료</b>\n\n"
                f"동기화: {synced}종목\n"
                f"총 보유: {len(self.portfolio.positions)}종목\n"
                f"현금: {self.portfolio.cash:,.0f}원\n\n"
                f"⚠️ 손절/익절가는 매입단가 기준으로 재설정됨"
            )

            return {"success": True, "message": msg, "synced": synced}

        except Exception as e:
            logger.error(f"KIS 포지션 동기화 실패: {e}", exc_info=True)
            return {"success": False, "message": str(e), "synced": 0}

    # ========== 리밸런싱 주문 생성/실행 (order_executor 위임) ==========

    def generate_rebalance_orders(self) -> List[PendingOrder]:
        """리밸런싱 주문 생성 (order_executor 위임)"""
        return self.order_executor.generate_rebalance_orders(
            screening_result=self.last_screening_result,
            pending_orders=self.pending_orders,
            failed_orders=self.failed_orders,
            stop_loss_manager=StopLossManager,
            take_profit_manager=TakeProfitManager,
            save_state_callback=self._save_state
        )

    def retry_failed_orders(self) -> int:
        """실패 주문 재시도 (order_executor 위임)"""
        return self.order_executor.retry_failed_orders(
            failed_orders=self.failed_orders,
            daily_trades=self.daily_trades,
            position_class=Position,
            stop_loss_manager=StopLossManager,
            take_profit_manager=TakeProfitManager,
            save_state_callback=self._save_state
        )

    def execute_pending_orders(self):
        """대기 중인 주문 실행 (order_executor 위임)"""
        self.order_executor.execute_pending_orders(
            pending_orders=self.pending_orders,
            failed_orders=self.failed_orders,
            daily_trades=self.daily_trades,
            order_lock=self._order_lock,
            position_class=Position,
            stop_loss_manager=StopLossManager,
            take_profit_manager=TakeProfitManager,
            save_state_callback=self._save_state
        )

    # ========== 장중 모니터링 (position_monitor 위임) ==========

    def monitor_positions(self):
        """포지션 모니터링 (position_monitor 위임)"""
        self.position_monitor.monitor(
            position_lock=self._position_lock,
            daily_trades=self.daily_trades,
            save_state_fn=self._save_state,
        )

    # ========== 리포트 (report_generator 위임) ==========

    def generate_daily_report(self):
        """일일 리포트 생성 및 발송 (report_generator 위임)"""
        trades_copy = self.report_generator.generate_daily_report(self.daily_trades)
        self.monthly_trades.extend(trades_copy)
        self.daily_trades = []

    def _was_rebalance_today(self) -> bool:
        """오늘 리밸런싱이 실행되었는지 확인"""
        if not self.last_rebalance_date:
            return False
        return self.last_rebalance_date.date() == datetime.now().date()

    def generate_monthly_report(self, save_snapshot: bool = True):
        """월간 리포트 생성 및 발송 (report_generator 위임)"""
        self.report_generator.generate_monthly_report(self.monthly_trades, save_snapshot)
        if save_snapshot:
            self.monthly_trades = []

    # ========== 주간 장부 점검 ==========

    def _on_weekly_reconciliation(self, force: bool = False):
        """주간 장부 점검 (토요일 10:00)"""
        # 토요일에만 실행 (수동 호출 시 force=True로 우회)
        if not force and datetime.now().weekday() != 5:  # 5 = Saturday
            return

        logger.info("=" * 60)
        logger.info("주간 장부 점검 시작")

        try:
            # 1. KIS 잔고 조회
            balance_info = self.client.get_balance()
            kis_data = {
                'cash': balance_info.get('cash', 0),
                'scts_evlu': balance_info.get('scts_evlu', 0),
                'nass': balance_info.get('nass', 0),
                'buy_amount': balance_info.get('buy_amount', 0),
                'stocks': balance_info.get('stocks', []),
                'total_profit': balance_info.get('total_profit', 0),
            }

            # 2. 스냅샷 점검/보정
            initial = self.daily_tracker.initial_capital or self.config.total_capital
            recon_result = self.daily_tracker.reconcile_latest_snapshot(kis_data, initial)

            # 3. 포지션 동기화 점검
            kis_stock_count = len(kis_data['stocks'])
            internal_count = len(self.portfolio.positions)
            pos_synced = kis_stock_count == internal_count

            # 4. 텔레그램 알림
            bs = parse_balance(kis_data)
            kis_total = bs.total_assets
            status_icon = "✅" if not recon_result.get('corrected') and pos_synced else "⚠️"

            message = (
                f"{status_icon} <b>주간 장부 점검</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                f"<b>KIS 실잔고</b>\n"
                f"총 자산: {kis_total:,.0f}원\n"
                f"주식: {kis_data['scts_evlu']:,.0f}원\n"
                f"현금: {kis_data['cash']:,.0f}원\n"
                f"보유: {kis_stock_count}종목\n\n"
                f"<b>장부 점검</b>\n"
                f"{recon_result.get('details', '-')}\n\n"
                f"<b>포지션 동기화</b>\n"
                f"{'✅ 일치' if pos_synced else f'⚠️ 불일치 (KIS: {kis_stock_count} / 내부: {internal_count})'}"
            )
            self.notifier.send_message(message)

            # 5. 포지션 불일치 시 자동 동기화
            if not pos_synced:
                self.sync_positions_from_kis()

            logger.info(f"주간 점검 완료: {recon_result.get('details')}")

        except Exception as e:
            logger.error(f"주간 장부 점검 실패: {e}", exc_info=True)
            from src.utils.error_formatter import format_user_error
            self.notifier.send_message(format_user_error(e, "주간 장부 점검"))

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
        order_mode = "Dry-Run (모의)" if self.config.dry_run else "실제 주문"
        self.notifier.notify_system("퀀트 엔진 시작", {
            "모드": mode,
            "주문": order_mode,
            "목표 종목": f"{self.config.target_stock_count}개",
            "투자금": f"{self.config.total_capital:,}원"
        })

        # KIS 포지션 동기화 (내부 0개 + KIS에 보유종목 있으면)
        if not self.portfolio.positions:
            self.sync_positions_from_kis()

        # 최초 실행 시 자동 스크리닝
        self.schedule_handler.check_initial_setup()

        # 스케줄 설정
        self.schedule_handler.setup_schedule()

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
            "last_screening": self.last_screening_date.isoformat() if self.last_screening_date else None,
            "last_rebalance": self.last_rebalance_date.isoformat() if self.last_rebalance_date else None,
            "last_rebalance_month": self.last_rebalance_month
        }

    # ========== 수동 실행 메서드 ==========

    def manual_screening(self) -> Optional[ScreeningResult]:
        """수동 스크리닝 실행"""
        return self.run_screening()

    def manual_rebalance(self) -> Dict[str, Any]:
        """수동 리밸런싱 실행"""
        if not self._is_trading_time():
            logger.warning("거래 시간이 아닙니다")
            return {"success": False, "message": "거래 시간이 아닙니다"}

        # 스크리닝
        self.notifier.send_message("🔍 스크리닝 진행 중...")
        result = self.run_screening()
        if not result:
            logger.error("스크리닝 실패 - 리밸런싱 중단")
            return {"success": False, "message": "스크리닝 실패"}

        # 주문 생성
        current_count = len(self.portfolio.positions)
        target_count = self.config.target_stock_count
        self.notifier.send_message(
            f"📋 주문 생성 중... (현재 {current_count}개 / 목표 {target_count}개)"
        )
        orders = self.generate_rebalance_orders()
        logger.info(f"리밸런싱 주문 생성: {len(orders)}건")

        if orders:
            sell_count = sum(1 for o in orders if o.order_type == "SELL")
            buy_count = sum(1 for o in orders if o.order_type == "BUY")
            self.notifier.send_message(
                f"📋 주문 생성 완료 (매도 {sell_count}건, 매수 {buy_count}건)"
            )

        # 리밸런싱 날짜 기록
        if orders:
            now = datetime.now()
            self.last_rebalance_date = now
            self.last_rebalance_month = now.strftime("%Y-%m")
            self._save_state()
            logger.info(f"리밸런싱 완료 기록: {self.last_rebalance_month}")

        # 즉시 실행
        self.execute_pending_orders()

        return {
            "success": True,
            "message": f"리밸런싱 완료: {len(orders)}건 주문 생성",
            "orders": len(orders)
        }

    def run_urgent_rebalance(self, force: bool = False) -> Dict[str, Any]:
        """
        긴급 리밸런싱 실행 (부분 매수만)

        Args:
            force: True면 70% 미만 조건 무시하고 강제 실행

        보유 종목이 목표의 70% 미만일 때 호출됨
        - 기존 종목 유지 (매도 없음)
        - 부족분만 스크리닝 결과에서 매수

        Returns:
            Dict with success, buy_count, current_count
        """
        current_count = len(self.portfolio.positions)
        target_count = self.config.target_stock_count
        threshold = target_count * 0.7

        # 70% 미만 조건 확인 (force가 아닌 경우)
        if not force and current_count >= threshold:
            ratio_pct = current_count / target_count * 100
            return {
                "success": True,
                "message": f"리밸런싱 불필요 (보유 {ratio_pct:.0f}% >= 70%)",
                "buy_count": 0,
                "current_count": current_count
            }

        logger.info("=" * 60)
        logger.info(f"📢 긴급 리밸런싱 시작 (부분 매수){' [강제]' if force else ''}")
        logger.info("=" * 60)

        shortage = target_count - current_count

        logger.info(f"현재 보유: {current_count}개, 목표: {target_count}개, 부족: {shortage}개")

        # 스크리닝 실행
        self.notifier.send_message(
            f"🔍 긴급 리밸런싱 스크리닝 시작\n"
            f"현재 {current_count}개 / 목표 {target_count}개 / 부족 {shortage}개"
        )
        result = self.run_screening()
        if not result:
            logger.error("스크리닝 실패 - 긴급 리밸런싱 중단")
            self._urgent_rebalance_mode = False
            return {"success": False, "message": "스크리닝 실패", "buy_count": 0, "current_count": current_count}

        # 부분 리밸런싱 주문 생성 (매수만)
        orders = self.order_executor.generate_partial_rebalance_orders(
            target_stocks=result.selected_stocks,
            shortage=shortage,
            stop_loss_manager=StopLossManager,
            take_profit_manager=TakeProfitManager
        )

        if not orders:
            logger.info("추가 매수 대상 없음")
            self._urgent_rebalance_mode = False
            return {"success": True, "message": "추가 매수 대상 없음", "buy_count": 0, "current_count": current_count}

        logger.info(f"부분 리밸런싱 주문 생성: {len(orders)}건 (매수만)")
        self.notifier.send_message(f"📋 매수 주문 생성 완료: {len(orders)}건")

        # 주문 등록
        self.pending_orders.extend(orders)

        # 주문 실행
        self.execute_pending_orders()

        # 긴급 리밸런싱 월 기록 (월 1회 제한)
        now = datetime.now()
        self.state_manager.last_urgent_rebalance_month = now.strftime("%Y-%m")
        self._save_state()
        logger.info(f"긴급 리밸런싱 완료 기록: {self.state_manager.last_urgent_rebalance_month}")

        # 긴급 모드 해제
        self._urgent_rebalance_mode = False

        # 알림
        self.notifier.send_message(
            f"📢 <b>긴급 리밸런싱 완료</b>\n\n"
            f"• 매수 주문: {len(orders)}건\n"
            f"• 이전 보유: {current_count}개\n"
            f"• 목표: {target_count}개"
        )

        return {
            "success": True,
            "message": f"긴급 리밸런싱 완료: {len(orders)}건 매수",
            "buy_count": len(orders),
            "current_count": len(self.portfolio.positions)
        }

    def manual_monitor(self):
        """수동 모니터링 실행"""
        self.monitor_positions()
