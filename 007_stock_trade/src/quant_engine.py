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
from .quant_modules import EngineState, SchedulePhase, PendingOrder, EngineStateManager, OrderExecutor, MonthlyTracker

# 로깅 설정
logger = logging.getLogger(__name__)

# 디버그 전용 로거 (별도 파일에 상세 로그 기록)
debug_logger = logging.getLogger("quant_debug")
debug_logger.setLevel(logging.DEBUG)
_debug_handler = logging.FileHandler("logs/quant_debug.log", encoding="utf-8")
_debug_handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s"
))
debug_logger.addHandler(_debug_handler)
debug_logger.propagate = False  # 터미널에 출력하지 않음

# API Rate Limit 설정 (한투 API 제한: 실전 20건/초, 모의 5건/초)
API_DELAY_VIRTUAL = 0.5    # 모의투자: 500ms (초당 2건, 충분한 여유)
API_DELAY_REAL = 0.1       # 실전투자: 100ms (초당 ~10건)


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

        # 주문 실행기
        self.order_executor = OrderExecutor(
            client=self.client,
            portfolio=self.portfolio,
            notifier=self.notifier,
            config=self.config,
            is_virtual=is_virtual
        )

        # 월간 트래커
        self.monthly_tracker = MonthlyTracker(data_dir=self.data_dir)
        self.monthly_trades: List[Dict] = []  # 월간 거래 추적

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

        # 이미 이번 달에 리밸런싱을 실행한 경우 스킵
        if self.last_rebalance_month == current_month:
            logger.debug(f"이번 달({current_month}) 리밸런싱 이미 완료됨")
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
            self.notifier.notify_error("스크리닝 실패", str(e))
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

    # ========== 장중 모니터링 ==========

    def monitor_positions(self):
        """
        포지션 모니터링 (손절/익절 체크)

        장중 5분마다 실행
        """
        # 포지션 스냅샷 생성 (Lock 보호)
        with self._position_lock:
            if not self.portfolio.positions:
                return
            # 복사본으로 순회하여 race condition 방지
            positions_snapshot = list(self.portfolio.positions.items())

        logger.info(f"포지션 모니터링: {len(positions_snapshot)}개")
        debug_logger.info(f"{'='*60}")
        debug_logger.info(f"모니터링 시작: {len(positions_snapshot)}개 포지션")

        # API 호출 딜레이 (모의투자: 350ms, 실전: 100ms)
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
                        # Rate Limit 에러 체크 (원본 또는 변환된 메시지)
                        is_rate_limit = any(x in error_str for x in [
                            "EGW00201", "초당 거래건수", "증권사 서버 내부 오류"
                        ])
                        if is_rate_limit and retry < 2:
                            wait_time = 1.0 * (retry + 1)  # 1초, 2초
                            debug_logger.warning(f"[{code}] Rate Limit - {wait_time}초 대기 후 재시도 ({retry+1}/3)")
                            time.sleep(wait_time)
                        else:
                            raise

                if price_info is None:
                    debug_logger.error(f"[{code}] 3회 재시도 실패")
                    continue

                with self._position_lock:
                    # 포지션이 아직 존재하는지 확인
                    if code not in self.portfolio.positions:
                        continue
                    position.current_price = price_info.price

                # 디버그 로그 (별도 파일에 기록)
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
                    with self._position_lock:
                        if new_stop > position.stop_loss:
                            position.stop_loss = new_stop
                            logger.info(f"{position.name}: 손절가 상향 → {new_stop:,.0f}원")

            except Exception as e:
                logger.error(f"모니터링 오류 ({code}): {e}", exc_info=True)
                debug_logger.error(f"[{code}] 오류: {e}")

        debug_logger.info(f"모니터링 완료")

        # 상태 저장
        self._save_state()

        # 리스크 체크
        with self._position_lock:
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
        """손절 실행 (재시도 포함)"""
        logger.warning(f"손절 트리거: {position.name} ({position.profit_pct:+.1f}%)")

        order = PendingOrder(
            code=position.code,
            name=position.name,
            order_type="SELL",
            quantity=position.quantity,
            price=0,
            reason=f"손절 ({position.profit_pct:+.1f}%)"
        )

        # 최대 3회 재시도
        max_retries = 3
        api_delay = API_DELAY_VIRTUAL if self.is_virtual else API_DELAY_REAL

        for attempt in range(max_retries):
            # API Rate Limit 방지 딜레이
            time.sleep(api_delay * (attempt + 1))  # 재시도마다 딜레이 증가

            if self.order_executor._execute_order(order, self.daily_trades, Position, StopLossManager):
                self.notifier.send_message(
                    f"🔴 <b>손절 실행</b>\n\n"
                    f"종목: {position.name}\n"
                    f"수량: {position.quantity}주\n"
                    f"손익: {position.profit_pct:+.1f}%"
                )
                return  # 성공

            if attempt < max_retries - 1:
                logger.warning(f"손절 재시도 ({attempt + 2}/{max_retries}): {position.name}")

        # 모든 재시도 실패
        logger.error(f"손절 실패 (재시도 소진): {position.name}")
        self.notifier.send_message(
            f"🚨 <b>손절 실패</b>\n\n"
            f"종목: {position.name}\n"
            f"수량: {position.quantity}주\n"
            f"⚠️ 수동 확인 필요"
        )

    def _trigger_take_profit(self, position: Position, stage: int):
        """익절 실행 (재시도 포함)"""
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

        # 최대 3회 재시도
        max_retries = 3
        api_delay = API_DELAY_VIRTUAL if self.is_virtual else API_DELAY_REAL

        for attempt in range(max_retries):
            # API Rate Limit 방지 딜레이
            time.sleep(api_delay * (attempt + 1))  # 재시도마다 딜레이 증가

            if self.order_executor._execute_order(order, self.daily_trades, Position, StopLossManager):
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
                return  # 성공

            if attempt < max_retries - 1:
                logger.warning(f"익절 재시도 ({attempt + 2}/{max_retries}): {position.name}")

        # 모든 재시도 실패
        logger.error(f"익절 실패 (재시도 소진): {position.name}")
        self.notifier.send_message(
            f"🚨 <b>익절 실패</b>\n\n"
            f"종목: {position.name}\n"
            f"수량: {qty}주\n"
            f"⚠️ 수동 확인 필요"
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
            for t in self.daily_trades:
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

        # 월간 거래에 추가 (일일 거래 초기화 전)
        self.monthly_trades.extend(self.daily_trades)

        # 일일 거래 초기화
        self.daily_trades = []

        logger.info("일일 리포트 발송 완료")

    # ========== 월간 리포트 ==========

    def _was_rebalance_today(self) -> bool:
        """오늘 리밸런싱이 실행되었는지 확인"""
        if not self.last_rebalance_date:
            return False
        return self.last_rebalance_date.date() == datetime.now().date()

    def generate_monthly_report(self, save_snapshot: bool = True):
        """
        월간 리포트 생성 및 발송

        Args:
            save_snapshot: 스냅샷 저장 여부 (수동 요청 시 False)
        """
        try:
            logger.info("월간 리포트 생성 시작")

            # 포트폴리오 스냅샷
            snapshot = self.portfolio.get_snapshot()

            # 계좌 잔고 조회 (API)
            try:
                balance_info = self.client.get_balance()
                total_assets = balance_info.get('total_eval', 0) + balance_info.get('cash', 0)
                cash = balance_info.get('cash', 0)
            except Exception as e:
                logger.warning(f"잔고 조회 실패, 포트폴리오 데이터 사용: {e}")
                total_assets = snapshot.total_value
                cash = snapshot.cash

            # 리포트 생성
            report_message = self.monthly_tracker.generate_monthly_report(
                portfolio_snapshot=snapshot,
                monthly_trades=self.monthly_trades,
                total_assets=total_assets,
                cash=cash,
                is_auto_report=save_snapshot
            )

            # 텔레그램 발송
            self.notifier.send_message(report_message)

            # 스냅샷 저장 (자동 리포트인 경우만)
            if save_snapshot:
                monthly_snapshot = self.monthly_tracker.create_snapshot_from_portfolio(
                    portfolio_snapshot=snapshot,
                    monthly_trades=self.monthly_trades,
                    total_assets=total_assets,
                    cash=cash
                )
                self.monthly_tracker.save_snapshot(monthly_snapshot)

                # 월간 거래 리셋
                self.monthly_trades = []

            logger.info("월간 리포트 발송 완료")

        except Exception as e:
            logger.error(f"월간 리포트 생성 실패: {e}", exc_info=True)
            self.notifier.send_message(
                f"⚠️ <b>월간 리포트 생성 실패</b>\n\n"
                f"오류: {str(e)[:200]}"
            )

    # ========== 스케줄러 ==========

    def _check_initial_setup(self):
        """
        최초 실행 시 자동 스크리닝

        조건:
        1. 보유 포지션이 없음
        2. 이번 달 리밸런싱을 아직 하지 않음
        """
        current_month = datetime.now().strftime("%Y-%m")

        # 이미 이번 달 리밸런싱을 완료한 경우 스킵
        if self.last_rebalance_month == current_month:
            logger.info(f"이번 달({current_month}) 리밸런싱 완료됨 - 초기 스크리닝 스킵")
            return

        # 보유 포지션이 있으면 스킵
        if self.portfolio.positions:
            logger.info(f"보유 포지션 {len(self.portfolio.positions)}개 - 초기 스크리닝 스킵")
            return

        # 휴장일이면 스킵
        if not is_trading_day():
            logger.info("휴장일 - 초기 스크리닝 스킵 (다음 거래일에 자동 실행)")
            return

        logger.info("=" * 60)
        logger.info("🚀 최초 실행 감지 - 초기 스크리닝 시작")
        logger.info("=" * 60)

        self.notifier.send_message(
            "🚀 <b>최초 실행 감지</b>\n\n"
            "보유 포지션이 없어 초기 스크리닝을 시작합니다.\n"
            "스크리닝 완료 후 리밸런싱 주문이 생성됩니다."
        )

        try:
            # 스크리닝 실행
            screening_result = self.run_screening()
            if screening_result is None:
                logger.error("초기 스크리닝 실패")
                self.notifier.send_message(
                    "⚠️ <b>초기 스크리닝 실패</b>\n\n"
                    "수동으로 /run_screening 명령을 실행해주세요."
                )
                return

            # 리밸런싱 주문 생성
            orders = self.generate_rebalance_orders()

            if orders:
                now = datetime.now()
                self.last_rebalance_date = now
                self.last_rebalance_month = now.strftime("%Y-%m")
                self._save_state()

                logger.info(f"초기 설정 완료: {len(orders)}개 주문 생성")

                # 장 시간인 경우 즉시 실행
                if self._is_trading_time():
                    self.notifier.send_message(
                        f"✅ <b>초기 스크리닝 완료</b>\n\n"
                        f"• 생성된 주문: {len(orders)}개\n\n"
                        f"현재 장 시간입니다. 즉시 주문을 실행합니다."
                    )
                    logger.info("장중 초기 스크리닝 - 즉시 주문 실행")
                    self.execute_pending_orders()
                else:
                    self.notifier.send_message(
                        f"✅ <b>초기 스크리닝 완료</b>\n\n"
                        f"• 생성된 주문: {len(orders)}개\n\n"
                        f"다음 거래일 09:00 장 시작 시 자동 실행됩니다."
                    )
            else:
                logger.info("초기 설정 완료: 생성된 주문 없음")

        except Exception as e:
            logger.error(f"초기 스크리닝 오류: {e}", exc_info=True)
            self.notifier.notify_error("초기 스크리닝 오류", str(e))

    def _setup_schedule(self):
        """스케줄 설정"""
        # 장 전 스크리닝 (리밸런싱 일에만)
        schedule.every().day.at(self.config.screening_time).do(self._on_pre_market)
        schedule.every().day.at("09:30").do(self._on_pre_market)  # 10시 개장일 대비

        # 장 시작 - 주문 실행 (특수 개장일 대비 여러 시간 등록)
        schedule.every().day.at(self.config.market_open_time).do(self._on_market_open)
        schedule.every().day.at("10:00").do(self._on_market_open)  # 1/2 등 10시 개장

        # 장중 모니터링
        schedule.every(self.config.monitoring_interval).minutes.do(self._on_monitoring)

        # 장 마감 리포트
        schedule.every().day.at(self.config.market_close_time).do(self._on_market_close)

        logger.info("스케줄 설정 완료")
        logger.info(f"  - 스크리닝: {self.config.screening_time} (리밸런싱 일)")
        logger.info(f"  - 주문 실행: {self.config.market_open_time} (특수일: 10:00)")
        logger.info(f"  - 모니터링: {self.config.monitoring_interval}분 간격")
        logger.info(f"  - 리포트: {self.config.market_close_time}")

    def _on_pre_market(self):
        """장 전 이벤트"""
        if self.state != EngineState.RUNNING:
            return

        # 휴장일 제외
        if not is_trading_day():
            return

        # 이미 장 전 처리가 완료된 경우 스킵 (중복 실행 방지)
        if self.current_phase in [SchedulePhase.PRE_MARKET, SchedulePhase.MARKET_OPEN, SchedulePhase.MARKET_HOURS]:
            return

        # 실제 개장 시간 확인 (특수 개장일 대응)
        market_open_time = get_market_open_time()
        current_time = datetime.now().strftime("%H:%M")

        # 개장 30분 전부터 장 전 처리 가능
        open_dt = datetime.strptime(market_open_time, "%H:%M")
        pre_market_dt = open_dt - timedelta(minutes=30)
        pre_market_start = pre_market_dt.strftime("%H:%M")

        # 현재 시간이 장 전 처리 시간보다 이전이면 스킵
        if current_time < pre_market_start:
            logger.debug(f"장 전 처리 시간 전 ({current_time} < {pre_market_start}) - 스킵")
            return

        self.current_phase = SchedulePhase.PRE_MARKET
        logger.info("=" * 60)
        logger.info(f"장 전 처리 시작 (개장: {market_open_time})")
        self.notifier.send_message(
            f"🌅 <b>장 전 처리 시작</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
            f"📅 개장: {market_open_time}"
        )

        # 포지션이 없으면 초기 스크리닝 실행 (주말 시작 후 첫 평일 대응)
        if not self.portfolio.positions:
            current_month = datetime.now().strftime("%Y-%m")
            if self.last_rebalance_month != current_month:
                logger.info("포지션 없음 - 초기 스크리닝 실행")
                self.notifier.send_message(
                    "📋 <b>포지션 없음</b> - 초기 스크리닝을 실행합니다."
                )
                self._check_initial_setup()
                return

        # 리밸런싱 일인 경우 스크리닝 실행
        if self._is_rebalance_day():
            logger.info("리밸런싱 일 - 스크리닝 실행")
            self.notifier.send_message(
                "📆 <b>리밸런싱 일</b> - 스크리닝을 실행합니다."
            )

            # 스크리닝 실행 및 결과 체크
            screening_result = self.run_screening()
            if screening_result is None:
                logger.error("스크리닝 실패 - 리밸런싱 중단")
                self.notifier.send_message(
                    "⚠️ <b>스크리닝 실패</b>\n\n"
                    "리밸런싱 일이지만 스크리닝이 실패했습니다.\n"
                    "수동으로 /run_screening 명령을 실행하거나\n"
                    "로그를 확인해주세요."
                )
                return

            # 리밸런싱 주문 생성
            orders = self.generate_rebalance_orders()

            # 리밸런싱 날짜 기록 (중복 실행 방지)
            if orders:
                now = datetime.now()
                self.last_rebalance_date = now
                self.last_rebalance_month = now.strftime("%Y-%m")
                self._save_state()
                logger.info(f"리밸런싱 완료 기록: {self.last_rebalance_month}")
            else:
                logger.info("생성된 리밸런싱 주문 없음 (포트폴리오 유지)")
        else:
            logger.info("리밸런싱 일 아님 - 스크리닝 스킵")

    def _on_market_open(self):
        """장 시작 이벤트"""
        if self.state != EngineState.RUNNING:
            return

        if not is_trading_day():
            return

        # 이미 장 시작 처리가 완료된 경우 스킵 (중복 실행 방지)
        if self.current_phase in [SchedulePhase.MARKET_OPEN, SchedulePhase.MARKET_HOURS]:
            return

        # 실제 개장 시간 확인 (특수 개장일 대응)
        market_open_time = get_market_open_time()
        current_time = datetime.now().strftime("%H:%M")

        # 현재 시간이 개장 시간보다 이전이면 스킵
        if current_time < market_open_time:
            logger.debug(f"개장 전 ({current_time} < {market_open_time}) - 스킵")
            return

        self.current_phase = SchedulePhase.MARKET_OPEN
        logger.info("=" * 60)
        logger.info(f"장 시작 ({market_open_time}) - 대기 주문 실행")

        pending_count = len(self.pending_orders)
        if pending_count > 0:
            self.notifier.send_message(
                f"🔔 <b>장 시작</b> ({market_open_time})\n"
                f"━━━━━━━━━━━━━━━\n"
                f"대기 주문 {pending_count}개 실행 중..."
            )
        else:
            self.notifier.send_message(
                f"🔔 <b>장 시작</b> ({market_open_time})\n"
                f"━━━━━━━━━━━━━━━\n"
                f"대기 주문 없음 - 모니터링 모드"
            )

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

        if not is_trading_day():
            return

        self.current_phase = SchedulePhase.MARKET_CLOSE
        logger.info("=" * 60)
        logger.info("장 마감 - 일일 리포트 생성")
        self.notifier.send_message(
            f"🌙 <b>장 마감</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"일일 리포트를 생성합니다..."
        )

        # 일일 리포트
        self.generate_daily_report()

        # 리밸런싱 일이면 월간 리포트 발송
        if self._was_rebalance_today():
            logger.info("리밸런싱 일 - 월간 리포트 생성")
            self.generate_monthly_report(save_snapshot=True)

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
        order_mode = "Dry-Run (모의)" if self.config.dry_run else "실제 주문"
        self.notifier.notify_system("퀀트 엔진 시작", {
            "모드": mode,
            "주문": order_mode,
            "목표 종목": f"{self.config.target_stock_count}개",
            "투자금": f"{self.config.total_capital:,}원"
        })

        # 최초 실행 시 자동 스크리닝
        self._check_initial_setup()

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
        result = self.run_screening()
        if not result:
            logger.error("스크리닝 실패 - 리밸런싱 중단")
            return {"success": False, "message": "스크리닝 실패"}

        # 주문 생성
        orders = self.generate_rebalance_orders()
        logger.info(f"리밸런싱 주문 생성: {len(orders)}건")

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

    def manual_monitor(self):
        """수동 모니터링 실행"""
        self.monitor_positions()
