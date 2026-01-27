"""
QuantEngine 상태 관리 모듈

상태 저장/로드, Lock 관리 등 엔진 상태 관련 기능 담당
"""

import os
import json
import shutil
import logging
import threading
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..strategy.quant import Position

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
    retry_count: int = 0  # 재시도 횟수
    last_error: str = ""  # 마지막 에러 메시지

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환 (JSON 직렬화용)"""
        return {
            "code": self.code,
            "name": self.name,
            "order_type": self.order_type,
            "quantity": self.quantity,
            "price": self.price,
            "reason": self.reason,
            "stop_loss": self.stop_loss,
            "take_profit_1": self.take_profit_1,
            "take_profit_2": self.take_profit_2,
            "weight": self.weight,
            "created_at": self.created_at.isoformat(),
            "retry_count": self.retry_count,
            "last_error": self.last_error
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PendingOrder':
        """딕셔너리에서 생성"""
        return cls(
            code=data["code"],
            name=data["name"],
            order_type=data["order_type"],
            quantity=data["quantity"],
            price=data["price"],
            reason=data["reason"],
            stop_loss=data.get("stop_loss", 0),
            take_profit_1=data.get("take_profit_1", 0),
            take_profit_2=data.get("take_profit_2", 0),
            weight=data.get("weight", 0),
            created_at=datetime.fromisoformat(data["created_at"]),
            retry_count=data.get("retry_count", 0),
            last_error=data.get("last_error", "")
        )


class EngineStateManager:
    """
    엔진 상태 관리자

    포지션, 주문, 스크리닝 결과 등 엔진 상태의 영속화를 담당
    Thread-safe한 상태 저장/로드 제공
    """

    def __init__(self, data_dir: Optional[Path] = None, notifier=None):
        """
        Args:
            data_dir: 상태 파일 저장 경로
            notifier: TelegramNotifier 인스턴스 (에러 알림용)
        """
        if data_dir is None:
            data_dir = Path(__file__).parent.parent.parent / "data" / "quant"
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.notifier = notifier

        # 상태 데이터
        self.failed_orders: List[PendingOrder] = []
        self.last_screening_date: Optional[datetime] = None
        self.last_rebalance_date: Optional[datetime] = None
        self.last_rebalance_month: Optional[str] = None
        self.last_urgent_rebalance_month: Optional[str] = None  # 긴급 리밸런싱 월 추적

        # 동시성 제어
        self._position_lock = threading.Lock()
        self._order_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._screening_lock = threading.Lock()
        self._screening_in_progress = False

    @property
    def state_file(self) -> Path:
        """상태 파일 경로"""
        return self.data_dir / "engine_state.json"

    def load_state(self, portfolio_positions: Dict[str, 'Position'], position_class) -> None:
        """
        저장된 상태 로드 (손상된 파일 복구 포함)

        Args:
            portfolio_positions: 포트폴리오의 positions 딕셔너리 (직접 업데이트)
            position_class: Position 클래스 (동적 import 문제 회피)
        """
        if not self.state_file.exists():
            logger.info("저장된 상태 파일 없음. 새로 시작합니다.")
            return

        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 포지션 복원
            restored_count = 0
            for pos_data in data.get("positions", []):
                try:
                    position = position_class(
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
                    portfolio_positions[position.code] = position
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

            # 긴급 리밸런싱 월 복원
            if data.get("last_urgent_rebalance_month"):
                self.last_urgent_rebalance_month = data["last_urgent_rebalance_month"]

            # 실패 주문 복원
            failed_count = 0
            for order_data in data.get("failed_orders", []):
                try:
                    order = PendingOrder.from_dict(order_data)
                    self.failed_orders.append(order)
                    failed_count += 1
                except (KeyError, TypeError, ValueError) as e:
                    logger.warning(f"실패 주문 복원 실패 ({order_data.get('code', 'unknown')}): {e}")

            logger.info(f"상태 로드 완료: {restored_count}개 포지션, {failed_count}개 실패 주문")
            if self.last_rebalance_date:
                logger.info(f"마지막 리밸런싱: {self.last_rebalance_date.strftime('%Y-%m-%d')}")

        except json.JSONDecodeError as e:
            # JSON 파싱 오류: 파일 손상
            self._handle_corrupted_state_file(f"JSON 파싱 오류: {e}")

        except Exception as e:
            logger.error(f"상태 로드 실패: {e}", exc_info=True)
            if self.notifier:
                self.notifier.notify_error(
                    "상태 로드 실패",
                    f"이전 거래 정보를 복구하지 못했습니다. 신규 시작됩니다. 오류: {str(e)[:100]}"
                )

    def _handle_corrupted_state_file(self, reason: str) -> None:
        """손상된 상태 파일 처리"""
        backup_file = self.data_dir / f"engine_state.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        try:
            # 손상된 파일 백업
            shutil.copy2(self.state_file, backup_file)
            logger.warning(f"손상된 상태 파일을 백업했습니다: {backup_file}")

            # 손상된 원본 파일 삭제
            self.state_file.unlink()
            logger.info("손상된 상태 파일을 삭제했습니다.")

        except Exception as backup_error:
            logger.error(f"손상된 파일 백업 실패: {backup_error}")

        # 사용자 알림
        logger.error(f"상태 파일 손상: {reason}")
        if self.notifier:
            self.notifier.notify_error(
                "상태 파일 손상",
                f"이전 거래 정보가 손상되어 신규 시작됩니다.\n백업: {backup_file.name}\n원인: {reason[:100]}"
            )

    def save_state(
        self,
        portfolio_positions: Dict[str, 'Position'],
        failed_orders: Optional[List[PendingOrder]] = None
    ) -> None:
        """
        현재 상태 저장 (Thread-safe, Atomic write)

        Args:
            portfolio_positions: 포트폴리오의 positions 딕셔너리
            failed_orders: 실패한 주문 목록 (None이면 self.failed_orders 사용)
        """
        temp_file = self.data_dir / "engine_state.json.tmp"

        if failed_orders is not None:
            self.failed_orders = failed_orders

        with self._state_lock:
            try:
                # 포지션 데이터 수집 (position lock 보호)
                with self._position_lock:
                    positions_data = []
                    for code, pos in portfolio_positions.items():
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
                failed_orders_data = [order.to_dict() for order in self.failed_orders]

                data = {
                    "positions": positions_data,
                    "failed_orders": failed_orders_data,
                    "last_screening_date": self.last_screening_date.isoformat() if self.last_screening_date else None,
                    "last_rebalance_date": self.last_rebalance_date.isoformat() if self.last_rebalance_date else None,
                    "last_rebalance_month": self.last_rebalance_month,
                    "last_urgent_rebalance_month": self.last_urgent_rebalance_month,
                    "updated_at": datetime.now().isoformat()
                }

                # Atomic write: 임시 파일에 쓰고 이름 변경
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                os.replace(str(temp_file), str(self.state_file))  # atomic on POSIX

            except Exception as e:
                logger.error(f"상태 저장 실패: {e}", exc_info=True)

    def acquire_position_lock(self):
        """포지션 락 획득 (컨텍스트 매니저용)"""
        return self._position_lock

    def acquire_order_lock(self):
        """주문 락 획득 (컨텍스트 매니저용)"""
        return self._order_lock

    def acquire_screening_lock(self):
        """스크리닝 락 획득"""
        return self._screening_lock

    @property
    def screening_in_progress(self) -> bool:
        """스크리닝 진행 중 여부"""
        return self._screening_in_progress

    @screening_in_progress.setter
    def screening_in_progress(self, value: bool):
        """스크리닝 진행 중 상태 설정"""
        self._screening_in_progress = value
