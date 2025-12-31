"""
미국 주식 퀀트 자동매매 엔진
- 한국 시간 기준 미국 장 운영 시간에 맞춰 동작
- 멀티팩터 전략 기반 자동 리밸런싱
"""

import os
import json
import logging
import schedule
import time
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from enum import Enum
import pytz

logger = logging.getLogger(__name__)


# ========== 타임존 설정 ==========

KST = pytz.timezone('Asia/Seoul')
EST = pytz.timezone('US/Eastern')


def get_kst_now() -> datetime:
    """현재 한국 시간"""
    return datetime.now(KST)


def get_est_now() -> datetime:
    """현재 미국 동부 시간"""
    return datetime.now(EST)


def is_summer_time() -> bool:
    """미국 써머타임 여부"""
    est_now = get_est_now()
    return est_now.dst() != timedelta(0)


class USMarketHours:
    """미국 시장 운영 시간 (한국 시간 기준)"""

    # 정규장 시간 (KST)
    # 써머타임 적용 시: 22:30 ~ 05:00 (다음날)
    # 써머타임 미적용 시: 23:30 ~ 06:00 (다음날)

    @classmethod
    def get_market_open_kst(cls) -> tuple:
        """장 시작 시간 (시, 분)"""
        if is_summer_time():
            return (22, 30)
        else:
            return (23, 30)

    @classmethod
    def get_market_close_kst(cls) -> tuple:
        """장 마감 시간 (시, 분) - 다음날"""
        if is_summer_time():
            return (5, 0)
        else:
            return (6, 0)

    @classmethod
    def is_market_open(cls, kst_time: datetime = None) -> bool:
        """장 운영 중 여부 (한국 시간 기준)"""
        if kst_time is None:
            kst_time = get_kst_now()

        hour, minute = kst_time.hour, kst_time.minute

        open_h, open_m = cls.get_market_open_kst()
        close_h, close_m = cls.get_market_close_kst()

        # 주말 체크
        weekday = kst_time.weekday()
        # 토요일 오전 (금요일 장 마감 후)
        if weekday == 5 and hour >= close_h:
            return False
        # 일요일 전체
        if weekday == 6:
            return False
        # 월요일 장 시작 전
        if weekday == 0 and hour < open_h:
            return False

        # 시간 체크 (자정을 걸쳐서 운영)
        if hour >= open_h or hour < close_h:
            if hour == open_h and minute < open_m:
                return False
            if hour == close_h and minute > close_m:
                return False
            return True

        return False

    @classmethod
    def is_pre_market(cls, kst_time: datetime = None) -> bool:
        """장 시작 전 준비 시간 (장 시작 30분 전)"""
        if kst_time is None:
            kst_time = get_kst_now()

        open_h, open_m = cls.get_market_open_kst()

        # 장 시작 30분 전
        pre_market_h = open_h
        pre_market_m = open_m - 30
        if pre_market_m < 0:
            pre_market_h -= 1
            pre_market_m += 60

        hour, minute = kst_time.hour, kst_time.minute

        if hour == pre_market_h and minute >= pre_market_m:
            return True
        if hour == open_h and minute < open_m:
            return True

        return False


# ========== 설정 ==========

@dataclass
class USQuantEngineConfig:
    """미국 퀀트 엔진 설정"""
    # 유니버스
    universe_type: str = "sp500"
    universe_size: int = 100
    target_stock_count: int = 15

    # 자본금
    total_capital: float = 100000.0  # USD

    # 리스크 관리
    stop_loss_pct: float = 7.0
    take_profit_pct: float = 10.0
    max_position_pct: float = 10.0  # 종목당 최대 비중

    # 팩터 가중치
    momentum_weight: float = 0.20
    short_mom_weight: float = 0.10
    volatility_weight: float = 0.50
    volume_weight: float = 0.00
    value_weight: float = 0.20

    # 리밸런싱
    rebalance_day: int = 1  # 매월 1일
    rebalance_weekday: int = 0  # 매주 월요일 (선택사항)

    # 운영 모드
    dry_run: bool = True

    # 스케줄 (한국 시간)
    # 미국 장 시작 30분 전 스크리닝
    # 장 시작 시 주문 실행
    screening_minutes_before: int = 30
    monitoring_interval_minutes: int = 10


@dataclass
class USPosition:
    """보유 포지션"""
    symbol: str
    name: str
    qty: int
    avg_price: float  # USD
    current_price: float = 0.0
    profit_pct: float = 0.0
    exchange: str = "NAS"
    entry_date: str = ""


@dataclass
class USPendingOrder:
    """대기 주문"""
    symbol: str
    side: str  # "BUY" or "SELL"
    qty: int
    price: float
    exchange: str = "NAS"
    reason: str = ""


# ========== 퀀트 엔진 ==========

class USQuantTradingEngine:
    """미국 주식 퀀트 자동매매 엔진"""

    def __init__(
        self,
        config: USQuantEngineConfig = None,
        is_virtual: bool = True
    ):
        """
        Args:
            config: 엔진 설정
            is_virtual: 모의투자 여부
        """
        self.config = config or USQuantEngineConfig()
        self.is_virtual = is_virtual

        # 상태
        self.positions: List[USPosition] = []
        self.pending_orders: List[USPendingOrder] = []
        self.last_screening_result: List[Dict] = []
        self.last_screening_time: Optional[datetime] = None

        # 데이터 디렉토리
        self.data_dir = os.path.join(
            os.path.dirname(__file__), "..", "data", "us_quant"
        )
        os.makedirs(self.data_dir, exist_ok=True)

        # 상태 로드
        self._load_state()

        logger.info(f"미국 퀀트 엔진 초기화 완료 (모의투자: {is_virtual})")

    def _get_client(self):
        """KIS US 클라이언트 반환"""
        from src.api.kis_us_client import get_us_client
        return get_us_client(self.is_virtual)

    def _get_screener(self):
        """스크리너 반환"""
        from src.strategy.us_screener import USMultiFactorScreener, USFactorWeights

        weights = USFactorWeights(
            momentum_weight=self.config.momentum_weight,
            short_mom_weight=self.config.short_mom_weight,
            volatility_weight=self.config.volatility_weight,
            volume_weight=self.config.volume_weight,
            value_weight=self.config.value_weight
        )

        return USMultiFactorScreener(weights=weights)

    def _get_notifier(self):
        """텔레그램 알림 반환"""
        try:
            from src.telegram.bot import TelegramNotifier
            return TelegramNotifier()
        except Exception:
            return None

    # ========== 스케줄링 ==========

    def start(self):
        """엔진 시작 (스케줄러 등록)"""
        logger.info("미국 퀀트 엔진 스케줄러 시작")

        # 매분 체크 (미국 장 시간에 맞춰 동작)
        schedule.every(1).minutes.do(self._check_and_execute)

        # 무한 루프
        self._notify("🚀 미국 퀀트 시스템 시작")

        try:
            while True:
                schedule.run_pending()
                time.sleep(10)
        except KeyboardInterrupt:
            logger.info("엔진 종료 요청")
            self._notify("🛑 미국 퀀트 시스템 종료")

    def _check_and_execute(self):
        """매분 체크하여 적절한 작업 수행"""
        kst_now = get_kst_now()

        # 장 시작 전 스크리닝
        if USMarketHours.is_pre_market(kst_now):
            if self._should_run_screening(kst_now):
                self.run_screening()

        # 장 시작 시 주문 실행
        if self._is_market_just_opened(kst_now):
            self.execute_pending_orders()

        # 장 중 모니터링
        if USMarketHours.is_market_open(kst_now):
            if self._should_monitor(kst_now):
                self.monitor_positions()

    def _should_run_screening(self, kst_now: datetime) -> bool:
        """스크리닝 실행 여부"""
        # 오늘 이미 스크리닝 했으면 스킵
        if self.last_screening_time:
            if self.last_screening_time.date() == kst_now.date():
                return False

        # 리밸런싱 일인지 확인
        if kst_now.day == self.config.rebalance_day:
            return True

        # 포지션이 없으면 항상 스크리닝
        if not self.positions:
            return True

        return False

    def _is_market_just_opened(self, kst_now: datetime) -> bool:
        """장 막 시작했는지 확인"""
        open_h, open_m = USMarketHours.get_market_open_kst()

        if kst_now.hour == open_h and kst_now.minute == open_m:
            return True

        return False

    def _should_monitor(self, kst_now: datetime) -> bool:
        """모니터링 실행 여부"""
        return kst_now.minute % self.config.monitoring_interval_minutes == 0

    # ========== 핵심 기능 ==========

    def run_screening(self) -> List[Dict]:
        """스크리닝 실행"""
        logger.info("미국 주식 스크리닝 시작")
        self._notify("📋 스크리닝 실행 중...")

        try:
            screener = self._get_screener()
            results = screener.screen(
                universe_type=self.config.universe_type,
                universe_size=self.config.universe_size,
                target_count=self.config.target_stock_count
            )

            # 결과 저장
            self.last_screening_result = [
                {
                    "symbol": r.symbol,
                    "name": r.name,
                    "score": r.composite_score,
                    "momentum": r.momentum_score,
                    "volatility": r.volatility_score,
                    "value": r.value_score,
                    "return_12m": r.return_12m,
                    "sector": r.sector,
                    "exchange": r.exchange
                }
                for r in results
            ]
            self.last_screening_time = get_kst_now()

            # 주문 생성
            self._generate_orders(results)

            # 결과 저장
            self._save_state()

            # 알림
            msg = f"✅ 스크리닝 완료\n"
            msg += f"• 선정 종목: {len(results)}개\n"
            msg += f"• 대기 주문: {len(self.pending_orders)}개\n\n"
            msg += "📊 상위 5종목:\n"
            for i, r in enumerate(results[:5], 1):
                msg += f"{i}. {r.symbol} ({r.composite_score:.1f}점)\n"

            self._notify(msg)

            logger.info(f"스크리닝 완료: {len(results)}개 종목")
            return self.last_screening_result

        except Exception as e:
            logger.error(f"스크리닝 실패: {e}")
            self._notify(f"❌ 스크리닝 실패: {e}")
            return []

    def _generate_orders(self, screening_results: list):
        """스크리닝 결과로 주문 생성"""
        self.pending_orders = []

        # 현재 보유 종목
        current_symbols = {p.symbol for p in self.positions}

        # 목표 종목
        target_symbols = {r.symbol for r in screening_results}

        # 매도 대상 (보유 중이지만 목표에 없음)
        for pos in self.positions:
            if pos.symbol not in target_symbols:
                self.pending_orders.append(USPendingOrder(
                    symbol=pos.symbol,
                    side="SELL",
                    qty=pos.qty,
                    price=0,  # 시장가
                    exchange=pos.exchange,
                    reason="리밸런싱 매도"
                ))

        # 매수 대상 (목표에 있지만 보유 안함)
        capital_per_stock = self.config.total_capital / self.config.target_stock_count

        for result in screening_results:
            if result.symbol not in current_symbols:
                # 예상 가격으로 수량 계산 (실제 주문 시 갱신)
                estimated_price = 100.0  # 임시값
                qty = int(capital_per_stock / estimated_price)

                if qty > 0:
                    self.pending_orders.append(USPendingOrder(
                        symbol=result.symbol,
                        side="BUY",
                        qty=qty,
                        price=0,  # 시장가
                        exchange=result.exchange,
                        reason="리밸런싱 매수"
                    ))

        logger.info(f"주문 생성: {len(self.pending_orders)}개")

    def execute_pending_orders(self):
        """대기 주문 실행"""
        if not self.pending_orders:
            logger.info("실행할 대기 주문 없음")
            return

        logger.info(f"대기 주문 실행: {len(self.pending_orders)}개")
        self._notify(f"🔔 장 시작 - {len(self.pending_orders)}개 주문 실행")

        if self.config.dry_run:
            logger.info("Dry-run 모드: 실제 주문 스킵")
            self._notify("⚠️ Dry-run 모드: 실제 주문 미실행")
            self.pending_orders = []
            return

        client = self._get_client()
        executed = []

        for order in self.pending_orders:
            try:
                if order.side == "BUY":
                    result = client.buy_stock(
                        symbol=order.symbol,
                        qty=order.qty,
                        price=order.price,
                        exchange=order.exchange
                    )
                else:
                    result = client.sell_stock(
                        symbol=order.symbol,
                        qty=order.qty,
                        price=order.price,
                        exchange=order.exchange
                    )

                if result.success:
                    executed.append(order)
                    logger.info(f"주문 성공: {order.side} {order.symbol} x{order.qty}")
                else:
                    logger.warning(f"주문 실패: {order.symbol} - {result.message}")

            except Exception as e:
                logger.error(f"주문 실행 오류 ({order.symbol}): {e}")

        # 포지션 갱신
        self._update_positions()

        # 실행된 주문 제거
        self.pending_orders = [o for o in self.pending_orders if o not in executed]

        self._save_state()
        self._notify(f"✅ 주문 실행 완료: {len(executed)}개 성공")

    def monitor_positions(self):
        """포지션 모니터링"""
        if not self.positions:
            return

        logger.debug(f"포지션 모니터링: {len(self.positions)}개")

        client = self._get_client()

        for pos in self.positions:
            try:
                price_info = client.get_stock_price(pos.symbol, pos.exchange)
                pos.current_price = price_info.price

                if pos.avg_price > 0:
                    pos.profit_pct = (pos.current_price / pos.avg_price - 1) * 100

                # 손절/익절 체크
                if pos.profit_pct <= -self.config.stop_loss_pct:
                    self._execute_stop_loss(pos)
                elif pos.profit_pct >= self.config.take_profit_pct:
                    self._execute_take_profit(pos)

            except Exception as e:
                logger.warning(f"모니터링 실패 ({pos.symbol}): {e}")

    def _execute_stop_loss(self, pos: USPosition):
        """손절 실행"""
        logger.warning(f"손절 발동: {pos.symbol} ({pos.profit_pct:.1f}%)")
        self._notify(f"🔴 손절: {pos.symbol} ({pos.profit_pct:.1f}%)")

        if not self.config.dry_run:
            client = self._get_client()
            result = client.sell_stock(
                symbol=pos.symbol,
                qty=pos.qty,
                price=0,
                exchange=pos.exchange
            )
            if result.success:
                self.positions.remove(pos)
                self._save_state()

    def _execute_take_profit(self, pos: USPosition):
        """익절 실행"""
        logger.info(f"익절 발동: {pos.symbol} ({pos.profit_pct:.1f}%)")
        self._notify(f"🟢 익절: {pos.symbol} (+{pos.profit_pct:.1f}%)")

        if not self.config.dry_run:
            client = self._get_client()
            result = client.sell_stock(
                symbol=pos.symbol,
                qty=pos.qty,
                price=0,
                exchange=pos.exchange
            )
            if result.success:
                self.positions.remove(pos)
                self._save_state()

    def _update_positions(self):
        """포지션 갱신"""
        try:
            client = self._get_client()
            balance = client.get_balance()

            self.positions = [
                USPosition(
                    symbol=s.symbol,
                    name=s.name,
                    qty=s.qty,
                    avg_price=s.avg_price,
                    current_price=s.current_price,
                    profit_pct=s.profit_rate,
                    exchange=s.exchange,
                    entry_date=datetime.now().strftime("%Y-%m-%d")
                )
                for s in balance.get("stocks", [])
            ]

            self._save_state()

        except Exception as e:
            logger.error(f"포지션 갱신 실패: {e}")

    # ========== 상태 관리 ==========

    def _save_state(self):
        """상태 저장"""
        state = {
            "positions": [asdict(p) for p in self.positions],
            "pending_orders": [asdict(o) for o in self.pending_orders],
            "last_screening_result": self.last_screening_result,
            "last_screening_time": self.last_screening_time.isoformat() if self.last_screening_time else None,
            "updated_at": datetime.now().isoformat()
        }

        state_file = os.path.join(self.data_dir, "engine_state.json")
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def _load_state(self):
        """상태 로드"""
        state_file = os.path.join(self.data_dir, "engine_state.json")

        if not os.path.exists(state_file):
            return

        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)

            self.positions = [USPosition(**p) for p in state.get("positions", [])]
            self.pending_orders = [USPendingOrder(**o) for o in state.get("pending_orders", [])]
            self.last_screening_result = state.get("last_screening_result", [])

            if state.get("last_screening_time"):
                self.last_screening_time = datetime.fromisoformat(state["last_screening_time"])

            logger.info(f"상태 로드: 포지션 {len(self.positions)}개")

        except Exception as e:
            logger.warning(f"상태 로드 실패: {e}")

    # ========== 알림 ==========

    def _notify(self, message: str):
        """텔레그램 알림"""
        try:
            notifier = self._get_notifier()
            if notifier:
                notifier.send_message(f"[미국퀀트] {message}")
        except Exception as e:
            logger.warning(f"알림 전송 실패: {e}")

    # ========== 외부 인터페이스 ==========

    def get_status(self) -> Dict[str, Any]:
        """현재 상태 반환"""
        kst_now = get_kst_now()

        return {
            "is_market_open": USMarketHours.is_market_open(kst_now),
            "is_summer_time": is_summer_time(),
            "kst_time": kst_now.strftime("%Y-%m-%d %H:%M:%S"),
            "positions_count": len(self.positions),
            "pending_orders_count": len(self.pending_orders),
            "last_screening": self.last_screening_time.strftime("%Y-%m-%d %H:%M") if self.last_screening_time else "없음",
            "dry_run": self.config.dry_run,
            "is_virtual": self.is_virtual
        }

    def get_positions(self) -> List[Dict]:
        """보유 포지션 반환"""
        return [asdict(p) for p in self.positions]

    def get_screening_result(self) -> List[Dict]:
        """최근 스크리닝 결과 반환"""
        return self.last_screening_result


# ========== 편의 함수 ==========

def create_us_engine(
    dry_run: bool = True,
    is_virtual: bool = True
) -> USQuantTradingEngine:
    """미국 퀀트 엔진 생성"""
    config = USQuantEngineConfig(dry_run=dry_run)
    return USQuantTradingEngine(config, is_virtual)
