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
    retry_count: int = 0  # 재시도 횟수
    last_error: str = ""  # 마지막 에러 메시지


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

        # 상태 관리
        self.pending_orders: List[PendingOrder] = []
        self.failed_orders: List[PendingOrder] = []  # 실패한 주문 (다음 장 재시도)
        self.last_screening_result: Optional[ScreeningResult] = None
        self.last_screening_date: Optional[datetime] = None
        self.last_rebalance_date: Optional[datetime] = None  # 마지막 리밸런싱 날짜
        self.last_rebalance_month: Optional[str] = None      # 마지막 리밸런싱 월 (YYYY-MM)
        self.daily_trades: List[Dict] = []

        # 동시성 제어
        self._position_lock = threading.Lock()  # 포지션 접근 보호
        self._order_lock = threading.Lock()     # 주문 접근 보호
        self._state_lock = threading.Lock()     # 상태 저장 보호
        self._screening_lock = threading.Lock() # 스크리닝 중복 실행 방지
        self._screening_in_progress = False     # 스크리닝 진행 중 플래그

        # 데이터 저장 경로
        self.data_dir = Path(__file__).parent.parent / "data" / "quant"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 이전 상태 로드
        self._load_state()

    # ========== 상태 관리 ==========

    def _load_state(self):
        """저장된 상태 로드 (손상된 파일 복구 포함)"""
        state_file = self.data_dir / "engine_state.json"
        if not state_file.exists():
            logger.info("저장된 상태 파일 없음. 새로 시작합니다.")
            return

        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 포지션 복원
            restored_count = 0
            for pos_data in data.get("positions", []):
                try:
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
                    restored_count += 1
                except (KeyError, TypeError, ValueError) as e:
                    logger.warning(f"포지션 복원 실패 ({pos_data.get('code', 'unknown')}): {e}")

            # 마지막 스크리닝 날짜
            if data.get("last_screening_date"):
                try:
                    self.last_screening_date = datetime.fromisoformat(data["last_screening_date"])
                except ValueError as e:
                    logger.warning(f"스크리닝 날짜 복원 실패: {e}")

            # 마지막 리밸런싱 날짜
            if data.get("last_rebalance_date"):
                try:
                    self.last_rebalance_date = datetime.fromisoformat(data["last_rebalance_date"])
                except ValueError as e:
                    logger.warning(f"리밸런싱 날짜 복원 실패: {e}")
            if data.get("last_rebalance_month"):
                self.last_rebalance_month = data["last_rebalance_month"]

            # 실패 주문 복원
            failed_count = 0
            for order_data in data.get("failed_orders", []):
                try:
                    order = PendingOrder(
                        code=order_data["code"],
                        name=order_data["name"],
                        order_type=order_data["order_type"],
                        quantity=order_data["quantity"],
                        price=order_data["price"],
                        reason=order_data["reason"],
                        stop_loss=order_data.get("stop_loss", 0),
                        take_profit_1=order_data.get("take_profit_1", 0),
                        take_profit_2=order_data.get("take_profit_2", 0),
                        weight=order_data.get("weight", 0),
                        created_at=datetime.fromisoformat(order_data["created_at"]),
                        retry_count=order_data.get("retry_count", 0),
                        last_error=order_data.get("last_error", "")
                    )
                    self.failed_orders.append(order)
                    failed_count += 1
                except (KeyError, TypeError, ValueError) as e:
                    logger.warning(f"실패 주문 복원 실패 ({order_data.get('code', 'unknown')}): {e}")

            logger.info(f"상태 로드 완료: {restored_count}개 포지션, {failed_count}개 실패 주문")
            if self.last_rebalance_date:
                logger.info(f"마지막 리밸런싱: {self.last_rebalance_date.strftime('%Y-%m-%d')}")

        except json.JSONDecodeError as e:
            # JSON 파싱 오류: 파일 손상
            self._handle_corrupted_state_file(state_file, f"JSON 파싱 오류: {e}")

        except Exception as e:
            logger.error(f"상태 로드 실패: {e}", exc_info=True)
            self.notifier.notify_error(
                "상태 로드 실패",
                f"이전 거래 정보를 복구하지 못했습니다. 신규 시작됩니다. 오류: {str(e)[:100]}"
            )

    def _handle_corrupted_state_file(self, state_file: Path, reason: str):
        """손상된 상태 파일 처리"""
        backup_file = self.data_dir / f"engine_state.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        try:
            # 손상된 파일 백업
            import shutil
            shutil.copy2(state_file, backup_file)
            logger.warning(f"손상된 상태 파일을 백업했습니다: {backup_file}")

            # 손상된 원본 파일 삭제
            state_file.unlink()
            logger.info("손상된 상태 파일을 삭제했습니다.")

        except Exception as backup_error:
            logger.error(f"손상된 파일 백업 실패: {backup_error}")

        # 사용자 알림
        logger.error(f"상태 파일 손상: {reason}")
        self.notifier.notify_error(
            "상태 파일 손상",
            f"이전 거래 정보가 손상되어 신규 시작됩니다.\n백업: {backup_file.name}\n원인: {reason[:100]}"
        )

    def _save_state(self):
        """현재 상태 저장 (Thread-safe, Atomic write)"""
        state_file = self.data_dir / "engine_state.json"
        temp_file = self.data_dir / "engine_state.json.tmp"

        with self._state_lock:
            try:
                # 포지션 데이터 수집 (position lock 보호)
                with self._position_lock:
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

                # 실패 주문 데이터 수집
                failed_orders_data = []
                for order in self.failed_orders:
                    failed_orders_data.append({
                        "code": order.code,
                        "name": order.name,
                        "order_type": order.order_type,
                        "quantity": order.quantity,
                        "price": order.price,
                        "reason": order.reason,
                        "stop_loss": order.stop_loss,
                        "take_profit_1": order.take_profit_1,
                        "take_profit_2": order.take_profit_2,
                        "weight": order.weight,
                        "created_at": order.created_at.isoformat(),
                        "retry_count": order.retry_count,
                        "last_error": order.last_error
                    })

                data = {
                    "positions": positions_data,
                    "failed_orders": failed_orders_data,  # 실패 주문 저장
                    "last_screening_date": self.last_screening_date.isoformat() if self.last_screening_date else None,
                    "last_rebalance_date": self.last_rebalance_date.isoformat() if self.last_rebalance_date else None,
                    "last_rebalance_month": self.last_rebalance_month,
                    "updated_at": datetime.now().isoformat()
                }

                # Atomic write: 임시 파일에 쓰고 이름 변경
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                os.replace(str(temp_file), str(state_file))  # atomic on POSIX

            except Exception as e:
                logger.error(f"상태 저장 실패: {e}", exc_info=True)

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

        api_delay = API_DELAY_VIRTUAL if self.is_virtual else API_DELAY_REAL

        for idx, code in enumerate(to_buy):
            if idx > 0:
                time.sleep(api_delay)

            stock = target_stocks[code]

            # 포지션 사이징 (API 재시도 로직 포함)
            try:
                # 가격 조회 (최대 3회 재시도, 1초 간격)
                current_price = None
                max_retries = 3
                retry_delay = 1.0

                for attempt in range(max_retries):
                    try:
                        price_info = self.client.get_stock_price(code)
                        current_price = price_info.price
                        break  # 성공 시 루프 탈출
                    except Exception as retry_error:
                        if attempt < max_retries - 1:
                            error_msg = str(retry_error)
                            if "500" in error_msg or "서버" in error_msg:
                                logger.warning(
                                    f"가격 조회 재시도 ({code}): {attempt + 1}/{max_retries} - {retry_error}"
                                )
                                import time
                                time.sleep(retry_delay)
                                retry_delay *= 1.5  # 백오프
                            else:
                                raise  # 500 에러가 아니면 즉시 재발생
                        else:
                            raise  # 최대 재시도 횟수 초과

                if current_price is None:
                    error_msg = "가격 조회 재시도 모두 실패"
                    logger.error(f"가격 조회 최종 실패 ({code}): {error_msg}")
                    # 실패 주문으로 기록 (다음 장 재시도)
                    self.failed_orders.append(PendingOrder(
                        code=code,
                        name=stock.name,
                        order_type="BUY",
                        quantity=0,  # 나중에 다시 계산
                        price=0,
                        reason=f"리밸런싱 매수 (순위 {stock.rank}위)",
                        retry_count=0,
                        last_error=error_msg
                    ))
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
                error_msg = str(e)
                logger.error(f"주문 생성 실패 ({code}): {e}", exc_info=True)
                # 실패 주문으로 기록 (다음 장 재시도)
                self.failed_orders.append(PendingOrder(
                    code=code,
                    name=stock.name,
                    order_type="BUY",
                    quantity=0,  # 나중에 다시 계산
                    price=0,
                    reason=f"리밸런싱 매수 (순위 {stock.rank}위)",
                    retry_count=0,
                    last_error=error_msg[:200]  # 에러 메시지 제한
                ))

        # 실패 주문이 있으면 저장 및 알림
        if self.failed_orders:
            failed_names = [f"• {o.name} ({o.code})" for o in self.failed_orders[-5:]]  # 최근 5개
            failed_text = "\n".join(failed_names)
            if len(self.failed_orders) > 5:
                failed_text += f"\n... 외 {len(self.failed_orders) - 5}개"

            self.notifier.send_message(
                f"⚠️ <b>주문 생성 실패</b>\n\n"
                f"실패: {len(self.failed_orders)}건\n"
                f"다음 장 09:00 재시도 예정\n\n"
                f"<b>실패 종목:</b>\n{failed_text}"
            )
            logger.info(f"실패 주문 {len(self.failed_orders)}개 - 다음 장 재시도 예정")
            self._save_state()

        self.pending_orders = orders
        return orders

    # ========== 주문 실행 ==========

    def retry_failed_orders(self) -> int:
        """
        실패 주문 재시도

        장 시작 시(09:00) 호출, 이전에 실패한 주문을 다시 시도
        Returns: 성공한 주문 수
        """
        if not self.failed_orders:
            return 0

        logger.info(f"=" * 60)
        logger.info(f"실패 주문 재시도: {len(self.failed_orders)}건")
        logger.info(f"=" * 60)

        # 텔레그램 알림
        self.notifier.send_message(
            f"🔄 <b>실패 주문 재시도</b>\n\n"
            f"• 재시도 대상: {len(self.failed_orders)}건\n"
            f"• 최대 재시도: 3회"
        )

        success_count = 0
        still_failed = []
        permanently_failed = []  # 최대 재시도 초과로 포기한 주문
        max_total_retries = 3  # 최대 재시도 횟수

        api_delay = API_DELAY_VIRTUAL if self.is_virtual else API_DELAY_REAL

        for i, order in enumerate(self.failed_orders):
            if i > 0:
                time.sleep(api_delay)

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
                # 현재가 조회 (재시도 로직 포함)
                current_price = None
                for attempt in range(3):
                    try:
                        price_info = self.client.get_stock_price(order.code)
                        current_price = price_info.price
                        break
                    except Exception as e:
                        if attempt < 2:
                            logger.warning(f"가격 조회 재시도 ({order.code}): {e}")
                            time.sleep(1.5 ** attempt)
                        else:
                            raise

                if current_price is None:
                    raise Exception("가격 조회 실패")

                # 수량 재계산 (처음 실패 시 quantity가 0일 수 있음)
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
                stop_loss = StopLossManager.calculate_fixed_stop(current_price, self.config.stop_loss_pct)
                tp1, tp2 = TakeProfitManager.calculate_targets(current_price, stop_loss)

                position = Position(
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
                self.daily_trades.append({
                    "type": "BUY",
                    "code": order.code,
                    "name": order.name,
                    "quantity": quantity,
                    "price": current_price,
                    "order_no": order_no,
                    "reason": f"[재시도] {order.reason}",
                    "timestamp": datetime.now().isoformat()
                })

                logger.info(f"매수 완료 (재시도): {order.name} {quantity}주 @ {current_price:,}원")
                self.notifier.notify_buy(order.code, order.name, quantity, current_price, order.reason)
                success_count += 1

            except Exception as e:
                order.last_error = str(e)[:200]
                logger.error(f"재시도 실패 ({order.name}): {e}")

                # 아직 재시도 가능하면 다시 저장
                if order.retry_count < max_total_retries:
                    still_failed.append(order)

        # 아직 재시도 가능한 주문만 유지
        self.failed_orders = still_failed
        self._save_state()

        # 결과 알림
        if success_count > 0 or still_failed:
            self.notifier.send_message(
                f"✅ <b>재시도 결과</b>\n\n"
                f"• 성공: {success_count}건\n"
                f"• 실패: {len(still_failed)}건"
            )

        # 영구 실패 (최대 재시도 초과) 알림
        if permanently_failed:
            failed_names = [f"• {o.name} ({o.code})" for o in permanently_failed]
            failed_text = "\n".join(failed_names)

            self.notifier.send_message(
                f"🚫 <b>매수 포기 (재시도 초과)</b>\n\n"
                f"다음 종목은 3회 재시도 후 매수 포기되었습니다:\n"
                f"{failed_text}\n\n"
                f"다음 리밸런싱까지 편입되지 않습니다."
            )
            logger.warning(f"매수 포기 (재시도 초과): {[o.name for o in permanently_failed]}")

        logger.info(f"재시도 완료: 성공 {success_count}건, 실패 {len(still_failed)}건, 포기 {len(permanently_failed)}건")
        return success_count

    def execute_pending_orders(self):
        """
        대기 중인 주문 실행

        장 시작 시(09:00) 호출
        """
        # 1. 먼저 실패 주문 재시도
        if self.failed_orders:
            self.retry_failed_orders()

        # 2. 대기 주문 스냅샷 (Lock 보호)
        with self._order_lock:
            if not self.pending_orders:
                logger.info("대기 주문 없음")
                return
            # 복사본으로 작업
            orders_to_execute = list(self.pending_orders)

        logger.info(f"대기 주문 실행: {len(orders_to_execute)}건")

        # 매도 먼저 실행 (자금 확보)
        sell_orders = [o for o in orders_to_execute if o.order_type == "SELL"]
        buy_orders = [o for o in orders_to_execute if o.order_type == "BUY"]

        executed = []
        api_delay = API_DELAY_VIRTUAL if self.is_virtual else API_DELAY_REAL

        for i, order in enumerate(sell_orders):
            if i > 0:
                time.sleep(api_delay)
            if self._execute_order(order):
                executed.append(order)

        # 잠시 대기 (주문 체결 시간)
        if sell_orders:
            time.sleep(3)

        for i, order in enumerate(buy_orders):
            if i > 0:
                time.sleep(api_delay)
            if self._execute_order(order):
                executed.append(order)

        # 대기 주문 업데이트 (Lock 보호)
        with self._order_lock:
            self.pending_orders = [o for o in self.pending_orders if o not in executed]

        # 상태 저장
        self._save_state()

        # 리밸런싱 결과 알림
        if executed:
            self._notify_rebalance_result(executed)

        # 최종 보유 종목 미달 알림
        self._check_position_shortage()

    def _execute_order(self, order: PendingOrder) -> bool:
        """개별 주문 실행"""
        try:
            if order.order_type == "SELL":
                return self._execute_sell(order)
            else:
                return self._execute_buy(order)
        except Exception as e:
            logger.error(f"주문 실행 실패 ({order.code}): {e}", exc_info=True)
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
            logger.error(f"매수 실행 오류: {e}", exc_info=True)
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
            logger.error(f"매도 실행 오류: {e}", exc_info=True)
            return False

    def _notify_rebalance_result(self, executed_orders: List[PendingOrder]):
        """리밸런싱 결과 알림"""
        try:
            buys = [o for o in executed_orders if o.order_type == "BUY"]
            sells = [o for o in executed_orders if o.order_type == "SELL"]

            # 포트폴리오 현재 가치
            snapshot = self.portfolio.get_snapshot()
            portfolio_value = int(snapshot.total_value)

            # 매도 종목 정보 (손익률 포함)
            sell_list = []
            for o in sells:
                pos = self.portfolio.positions.get(o.code)
                pnl_pct = 0
                if pos and pos.entry_price > 0:
                    pnl_pct = (o.price - pos.entry_price) / pos.entry_price * 100
                sell_list.append({
                    'name': o.name,
                    'pnl_pct': pnl_pct
                })

            # 매수 종목 정보 (비중 포함)
            buy_list = []
            for o in buys:
                buy_list.append({
                    'name': o.name,
                    'weight': o.weight
                })

            # 통합된 알림 메서드 사용
            self.notifier.notify_rebalance(
                sells=sell_list,
                buys=buy_list,
                portfolio_value=portfolio_value
            )

        except Exception as e:
            logger.error(f"리밸런싱 알림 실패: {e}")

    def _check_position_shortage(self):
        """최종 보유 종목 수 미달 체크 및 알림"""
        try:
            target_count = self.config.target_stock_count
            current_count = len(self.portfolio.positions)
            failed_count = len(self.failed_orders)

            # 미달이면 알림
            if current_count < target_count:
                shortage = target_count - current_count

                # 원인 분석
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
        """손절 실행"""
        logger.warning(f"손절 트리거: {position.name} ({position.profit_pct:+.1f}%)")

        # API Rate Limit 방지: 가격 조회 후 딜레이
        api_delay = API_DELAY_VIRTUAL if self.is_virtual else API_DELAY_REAL
        time.sleep(api_delay)

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

        # API Rate Limit 방지: 가격 조회 후 딜레이
        api_delay = API_DELAY_VIRTUAL if self.is_virtual else API_DELAY_REAL
        time.sleep(api_delay)

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

        # 일일 거래 초기화
        self.daily_trades = []

        logger.info("일일 리포트 발송 완료")

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
