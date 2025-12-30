"""
자동매매 엔진
- 전략 실행 및 주문 처리
- 스케줄링
- 상태 관리
"""

import os
import time
import logging
import schedule
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from dotenv import load_dotenv

from .api import KISClient, StockPrice
from .strategy import (
    BaseStrategy,
    Signal,
    TradeSignal,
    create_strategy,
    StrategyManager
)
from .telegram import TelegramNotifier, get_notifier
from .utils import is_trading_day

load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/trading.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class EngineState(Enum):
    """엔진 상태"""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


@dataclass
class TradeRecord:
    """거래 기록"""
    timestamp: datetime
    stock_code: str
    stock_name: str
    action: str  # BUY, SELL
    qty: int
    price: int
    order_no: str
    signal_reason: str
    pnl: Optional[int] = None  # 손익 (매도 시)


@dataclass
class EngineConfig:
    """엔진 설정"""
    # 거래 대상
    stock_codes: List[str] = field(default_factory=lambda: ["005930"])  # 기본: 삼성전자

    # 투자 설정
    capital: int = 1_000_000  # 투자 자본금
    max_stocks: int = 5       # 최대 보유 종목 수

    # 스케줄링
    interval_minutes: int = 30  # 분석 주기 (분)

    # 거래 시간
    trading_start: str = "09:00"
    trading_end: str = "15:20"

    # 리스크 관리
    max_loss_per_day: float = 0.03  # 일일 최대 손실률 (3%)

    # 모드
    dry_run: bool = True  # True: 모의 실행 (실제 주문 안 함)

    # 전략
    strategy_type: str = "composite"
    strategy_params: Dict[str, Any] = field(default_factory=dict)


class TradingEngine:
    """자동매매 엔진"""

    def __init__(
        self,
        config: Optional[EngineConfig] = None,
        is_virtual: bool = True
    ):
        """
        Args:
            config: 엔진 설정
            is_virtual: True=모의투자, False=실전투자
        """
        self.config = config or EngineConfig()
        self.is_virtual = is_virtual
        self.state = EngineState.STOPPED

        # 클라이언트 초기화
        self.client = KISClient(is_virtual=is_virtual)
        self.notifier = get_notifier()

        # 전략 초기화
        self.strategy = create_strategy(
            self.config.strategy_type,
            **self.config.strategy_params
        )

        # 상태 관리
        self.positions: Dict[str, Dict] = {}  # 보유 포지션
        self.trade_history: List[TradeRecord] = []
        self.daily_pnl: int = 0
        self.last_analysis_time: Optional[datetime] = None

    def _is_trading_time(self) -> bool:
        """거래 시간 확인"""
        now = datetime.now()

        # 휴장일 체크 (주말 + 공휴일)
        if not is_trading_day(now):
            return False

        start_time = datetime.strptime(self.config.trading_start, "%H:%M").time()
        end_time = datetime.strptime(self.config.trading_end, "%H:%M").time()

        return start_time <= now.time() <= end_time

    def _check_daily_loss_limit(self) -> bool:
        """일일 손실 한도 확인"""
        max_loss = self.config.capital * self.config.max_loss_per_day
        return self.daily_pnl > -max_loss

    def _get_stock_data(self, stock_code: str, count: int = 60) -> Optional[pd.DataFrame]:
        """주식 데이터 가져오기"""
        try:
            history = self.client.get_stock_history(stock_code, period="D", count=count)

            if not history:
                return None

            df = pd.DataFrame(history)
            # 컬럼명 표준화
            df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
            df = df.sort_values('date').reset_index(drop=True)

            # 숫자형 변환
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])

            return df

        except Exception as e:
            logger.error(f"데이터 조회 실패 ({stock_code}): {e}")
            return None

    def _execute_buy(self, stock_code: str, signal: TradeSignal) -> bool:
        """매수 실행"""
        try:
            # 현재가 조회
            price_info = self.client.get_stock_price(stock_code)
            current_price = price_info.price

            # 수량 계산
            available_capital = self.config.capital / self.config.max_stocks
            qty = self.strategy.calculate_position_size(
                available_capital,
                current_price,
                signal.strength
            )

            if qty <= 0:
                logger.info(f"매수 수량 0 - 스킵 ({stock_code})")
                return False

            # Dry run 모드
            if self.config.dry_run:
                logger.info(f"[DRY RUN] 매수: {price_info.name} {qty}주 @ {current_price:,}원")
                order_no = f"DRY_{datetime.now().strftime('%H%M%S')}"
            else:
                # 실제 주문
                result = self.client.buy_stock(stock_code, qty, price=0, order_type="01")

                if not result.success:
                    logger.error(f"매수 주문 실패: {result.message}")
                    return False

                order_no = result.order_no

            # 포지션 기록
            self.positions[stock_code] = {
                "name": price_info.name,
                "qty": qty,
                "entry_price": current_price,
                "entry_time": datetime.now()
            }

            # 거래 기록
            self.trade_history.append(TradeRecord(
                timestamp=datetime.now(),
                stock_code=stock_code,
                stock_name=price_info.name,
                action="BUY",
                qty=qty,
                price=current_price,
                order_no=order_no,
                signal_reason=signal.reason
            ))

            # 전략 상태 업데이트
            self.strategy.enter_position(current_price)

            # 알림 전송
            self.notifier.notify_buy(
                stock_name=price_info.name,
                stock_code=stock_code,
                qty=qty,
                price=current_price,
                order_no=order_no
            )

            logger.info(f"매수 완료: {price_info.name} {qty}주 @ {current_price:,}원")
            return True

        except Exception as e:
            logger.error(f"매수 실행 오류: {e}")
            self.notifier.notify_error("매수 오류", str(e))
            return False

    def _execute_sell(self, stock_code: str, signal: TradeSignal) -> bool:
        """매도 실행"""
        if stock_code not in self.positions:
            return False

        try:
            position = self.positions[stock_code]
            price_info = self.client.get_stock_price(stock_code)
            current_price = price_info.price
            qty = position["qty"]

            # Dry run 모드
            if self.config.dry_run:
                logger.info(f"[DRY RUN] 매도: {position['name']} {qty}주 @ {current_price:,}원")
                order_no = f"DRY_{datetime.now().strftime('%H%M%S')}"
            else:
                # 실제 주문
                result = self.client.sell_stock(stock_code, qty, price=0, order_type="01")

                if not result.success:
                    logger.error(f"매도 주문 실패: {result.message}")
                    return False

                order_no = result.order_no

            # 손익 계산
            pnl = (current_price - position["entry_price"]) * qty
            self.daily_pnl += pnl

            # 거래 기록
            self.trade_history.append(TradeRecord(
                timestamp=datetime.now(),
                stock_code=stock_code,
                stock_name=position["name"],
                action="SELL",
                qty=qty,
                price=current_price,
                order_no=order_no,
                signal_reason=signal.reason,
                pnl=pnl
            ))

            # 전략 상태 업데이트
            self.strategy.exit_position()

            # 포지션 삭제
            del self.positions[stock_code]

            # 알림 전송
            self.notifier.notify_sell(
                stock_name=position["name"],
                stock_code=stock_code,
                qty=qty,
                price=current_price,
                order_no=order_no
            )

            pnl_str = f"+{pnl:,}" if pnl >= 0 else f"{pnl:,}"
            logger.info(f"매도 완료: {position['name']} {qty}주 @ {current_price:,}원 (손익: {pnl_str}원)")
            return True

        except Exception as e:
            logger.error(f"매도 실행 오류: {e}")
            self.notifier.notify_error("매도 오류", str(e))
            return False

    def analyze_and_trade(self):
        """분석 및 거래 실행"""
        if self.state != EngineState.RUNNING:
            return

        if not self._is_trading_time():
            logger.debug("거래 시간 외")
            return

        if not self._check_daily_loss_limit():
            logger.warning("일일 손실 한도 도달 - 거래 중지")
            self.notifier.notify_system("거래 중지", {"사유": "일일 손실 한도 도달"})
            return

        logger.info("=" * 50)
        logger.info(f"분석 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        for stock_code in self.config.stock_codes:
            try:
                # 데이터 가져오기
                df = self._get_stock_data(stock_code)
                if df is None or len(df) < 30:
                    continue

                # 현재가 조회
                price_info = self.client.get_stock_price(stock_code)

                # 전략 분석
                signal = self.strategy.analyze(df)

                logger.info(
                    f"[{price_info.name}] 현재가: {price_info.price:,}원 | "
                    f"신호: {signal.signal.name} | 강도: {signal.strength:.2f} | "
                    f"사유: {signal.reason}"
                )

                # 보유 중인 경우
                if stock_code in self.positions:
                    if self.strategy.should_exit(signal, price_info.price):
                        self._execute_sell(stock_code, signal)

                # 미보유 + 매수 신호
                elif len(self.positions) < self.config.max_stocks:
                    if self.strategy.should_enter(signal):
                        self._execute_buy(stock_code, signal)

            except Exception as e:
                logger.error(f"분석 오류 ({stock_code}): {e}")

        self.last_analysis_time = datetime.now()
        logger.info("분석 완료")

    def start(self):
        """엔진 시작"""
        if self.state == EngineState.RUNNING:
            logger.warning("엔진이 이미 실행 중입니다.")
            return

        # API 키 검증
        if not self.client.auth.validate_credentials():
            logger.error("API 키가 설정되지 않았습니다.")
            return

        self.state = EngineState.RUNNING

        mode = "모의투자" if self.is_virtual else "실전투자"
        dry_run = "[DRY RUN] " if self.config.dry_run else ""

        logger.info(f"{dry_run}자동매매 엔진 시작 ({mode})")
        logger.info(f"전략: {self.strategy.config.name}")
        logger.info(f"대상 종목: {self.config.stock_codes}")
        logger.info(f"분석 주기: {self.config.interval_minutes}분")

        self.notifier.notify_system("엔진 시작", {
            "모드": mode,
            "전략": self.strategy.config.name,
            "종목": ", ".join(self.config.stock_codes)
        })

        # 스케줄 등록
        schedule.every(self.config.interval_minutes).minutes.do(self.analyze_and_trade)

        # 즉시 1회 실행
        self.analyze_and_trade()

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

        logger.info("자동매매 엔진 정지")
        self.notifier.notify_system("엔진 정지", {
            "일일손익": f"{self.daily_pnl:+,}원",
            "거래횟수": len(self.trade_history)
        })

    def pause(self):
        """엔진 일시정지"""
        self.state = EngineState.PAUSED
        logger.info("자동매매 엔진 일시정지")

    def resume(self):
        """엔진 재개"""
        if self.state == EngineState.PAUSED:
            self.state = EngineState.RUNNING
            logger.info("자동매매 엔진 재개")

    def get_status(self) -> Dict[str, Any]:
        """엔진 상태 반환"""
        return {
            "state": self.state.value,
            "mode": "모의투자" if self.is_virtual else "실전투자",
            "dry_run": self.config.dry_run,
            "strategy": self.strategy.config.name,
            "positions": len(self.positions),
            "daily_pnl": self.daily_pnl,
            "trades_today": len([
                t for t in self.trade_history
                if t.timestamp.date() == datetime.now().date()
            ]),
            "last_analysis": self.last_analysis_time.isoformat() if self.last_analysis_time else None
        }

    def get_positions(self) -> List[Dict]:
        """보유 포지션 반환"""
        result = []
        for code, pos in self.positions.items():
            try:
                current = self.client.get_stock_price(code)
                pnl = (current.price - pos["entry_price"]) * pos["qty"]
                pnl_pct = (current.price - pos["entry_price"]) / pos["entry_price"] * 100

                result.append({
                    "code": code,
                    "name": pos["name"],
                    "qty": pos["qty"],
                    "entry_price": pos["entry_price"],
                    "current_price": current.price,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct
                })
            except:
                result.append({
                    "code": code,
                    "name": pos["name"],
                    "qty": pos["qty"],
                    "entry_price": pos["entry_price"],
                    "current_price": 0,
                    "pnl": 0,
                    "pnl_pct": 0
                })
        return result
