"""
리스크 관리 및 포트폴리오 모니터링
- 포지션 사이징
- 리스크 한도 관리
- 포트폴리오 모니터링
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
import logging

from .signals import Position


logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """리스크 수준"""
    LOW = "LOW"           # 정상
    MEDIUM = "MEDIUM"     # 주의
    HIGH = "HIGH"         # 경계
    CRITICAL = "CRITICAL" # 위험


@dataclass
class RiskConfig:
    """리스크 관리 설정"""
    # 개별 종목 리스크
    max_single_position: float = 0.10      # 단일 종목 최대 비중 10%
    max_single_loss: float = 0.10          # 단일 종목 최대 손실 10%
    min_single_position: float = 0.03      # 단일 종목 최소 비중 3%

    # 포트폴리오 리스크
    daily_loss_limit: float = 0.02         # 일일 손실 한도 2%
    weekly_loss_limit: float = 0.05        # 주간 손실 한도 5%
    monthly_loss_limit: float = 0.10       # 월간 손실 한도 10%
    mdd_limit: float = 0.20                # MDD 한도 20%

    # 현금 비중
    min_cash_ratio: float = 0.10           # 최소 현금 비중 10%
    crisis_cash_ratio: float = 0.50        # 위기 시 현금 비중 50%

    # 연속 손실 관리
    max_consecutive_losses: int = 3        # 최대 연속 손실 횟수
    pause_duration_days: int = 5           # 거래 중단 기간

    # 섹터 분산
    max_sector_weight: float = 0.30        # 섹터당 최대 비중 30%


@dataclass
class RiskAlert:
    """리스크 경고"""
    level: RiskLevel
    alert_type: str
    message: str
    value: float
    threshold: float
    timestamp: datetime = field(default_factory=datetime.now)
    action_required: str = ""


@dataclass
class PortfolioSnapshot:
    """포트폴리오 스냅샷"""
    timestamp: datetime
    total_value: float
    cash: float
    invested: float
    positions: List[Position]
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    mdd: float = 0.0


@dataclass
class PositionSizing:
    """포지션 사이징 결과"""
    code: str
    recommended_amount: float
    recommended_qty: int
    weight: float
    risk_per_trade: float
    stop_loss_distance: float
    reason: str


class PositionSizer:
    """포지션 사이징 계산기"""

    def __init__(self, config: RiskConfig = None):
        self.config = config or RiskConfig()

    def calculate_equal_weight(
        self,
        total_capital: float,
        target_count: int
    ) -> float:
        """
        동일 비중 계산

        Args:
            total_capital: 총 자본
            target_count: 목표 종목 수

        Returns:
            종목당 투자금액
        """
        investable = total_capital * (1 - self.config.min_cash_ratio)
        return investable / target_count

    def calculate_risk_based(
        self,
        total_capital: float,
        entry_price: float,
        stop_loss: float,
        risk_per_trade: float = 0.02
    ) -> PositionSizing:
        """
        리스크 기반 포지션 사이징

        Args:
            total_capital: 총 자본
            entry_price: 진입가
            stop_loss: 손절가
            risk_per_trade: 거래당 리스크 비율 (기본 2%)

        Returns:
            PositionSizing
        """
        # 최대 손실 금액
        max_loss = total_capital * risk_per_trade

        # 손절 거리 (%)
        stop_distance_pct = (entry_price - stop_loss) / entry_price

        if stop_distance_pct <= 0:
            stop_distance_pct = 0.07  # 기본 7%

        # 포지션 크기 = 최대 손실 / 손절률
        position_size = max_loss / stop_distance_pct

        # 최대/최소 제한
        max_size = total_capital * self.config.max_single_position
        min_size = total_capital * self.config.min_single_position

        position_size = max(min_size, min(max_size, position_size))

        # 수량 계산
        quantity = int(position_size / entry_price)

        # 비중 계산
        weight = position_size / total_capital

        reason = f"리스크 {risk_per_trade*100:.1f}%, 손절거리 {stop_distance_pct*100:.1f}%"

        return PositionSizing(
            code="",
            recommended_amount=position_size,
            recommended_qty=quantity,
            weight=weight,
            risk_per_trade=risk_per_trade,
            stop_loss_distance=stop_distance_pct,
            reason=reason
        )

    def calculate_volatility_adjusted(
        self,
        total_capital: float,
        entry_price: float,
        volatility: float,
        base_position: float = 0.05
    ) -> PositionSizing:
        """
        변동성 조정 포지션 사이징

        변동성이 높으면 작은 포지션, 낮으면 큰 포지션

        Args:
            total_capital: 총 자본
            entry_price: 진입가
            volatility: 연환산 변동성 (%)
            base_position: 기본 비중 (5%)
        """
        # 기준 변동성: 25%
        base_volatility = 25.0

        # 변동성 조정 계수
        if volatility > 0:
            adjustment = base_volatility / volatility
        else:
            adjustment = 1.0

        # 조정된 비중 (0.5x ~ 2x)
        adjusted_weight = base_position * min(2.0, max(0.5, adjustment))

        # 최대/최소 제한
        adjusted_weight = min(self.config.max_single_position, adjusted_weight)
        adjusted_weight = max(self.config.min_single_position, adjusted_weight)

        position_size = total_capital * adjusted_weight
        quantity = int(position_size / entry_price)

        reason = f"변동성 {volatility:.1f}%, 조정계수 {adjustment:.2f}x"

        return PositionSizing(
            code="",
            recommended_amount=position_size,
            recommended_qty=quantity,
            weight=adjusted_weight,
            risk_per_trade=0.02,
            stop_loss_distance=0,
            reason=reason
        )


class RiskMonitor:
    """리스크 모니터링"""

    def __init__(self, config: RiskConfig = None):
        self.config = config or RiskConfig()
        self.history: List[PortfolioSnapshot] = []
        self.trade_history: List[Dict] = []
        self.alerts: List[RiskAlert] = []
        self.peak_value: float = 0
        self.is_trading_paused: bool = False
        self.pause_until: datetime = None

    def update_snapshot(self, snapshot: PortfolioSnapshot):
        """포트폴리오 스냅샷 업데이트"""
        self.history.append(snapshot)

        # 최고점 갱신
        if snapshot.total_value > self.peak_value:
            self.peak_value = snapshot.total_value

        # MDD 계산
        if self.peak_value > 0:
            snapshot.mdd = (self.peak_value - snapshot.total_value) / self.peak_value

    def check_all_risks(self, snapshot: PortfolioSnapshot) -> List[RiskAlert]:
        """
        전체 리스크 체크

        Returns:
            발생한 경고 리스트
        """
        alerts = []

        # 일일 손실 체크
        if snapshot.daily_pnl_pct < -self.config.daily_loss_limit * 100:
            alerts.append(RiskAlert(
                level=RiskLevel.HIGH,
                alert_type="DAILY_LOSS_EXCEEDED",
                message=f"일일 손실 한도 초과: {snapshot.daily_pnl_pct:.2f}%",
                value=snapshot.daily_pnl_pct,
                threshold=-self.config.daily_loss_limit * 100,
                action_required="신규 매수 중단"
            ))

        # MDD 체크
        if snapshot.mdd > self.config.mdd_limit:
            alerts.append(RiskAlert(
                level=RiskLevel.CRITICAL,
                alert_type="MDD_EXCEEDED",
                message=f"MDD 한도 초과: {snapshot.mdd*100:.2f}%",
                value=snapshot.mdd * 100,
                threshold=self.config.mdd_limit * 100,
                action_required="포지션 50% 축소"
            ))

        # 현금 비중 체크
        cash_ratio = snapshot.cash / snapshot.total_value if snapshot.total_value > 0 else 1
        if cash_ratio < self.config.min_cash_ratio:
            alerts.append(RiskAlert(
                level=RiskLevel.MEDIUM,
                alert_type="LOW_CASH",
                message=f"현금 비중 부족: {cash_ratio*100:.1f}%",
                value=cash_ratio * 100,
                threshold=self.config.min_cash_ratio * 100,
                action_required="신규 매수 보류"
            ))

        # 개별 종목 비중 체크
        for position in snapshot.positions:
            weight = position.market_value / snapshot.total_value
            if weight > self.config.max_single_position * 1.5:  # 15% 초과
                alerts.append(RiskAlert(
                    level=RiskLevel.HIGH,
                    alert_type="CONCENTRATION_RISK",
                    message=f"{position.name}: 비중 {weight*100:.1f}% 초과",
                    value=weight * 100,
                    threshold=self.config.max_single_position * 100,
                    action_required=f"{position.name} 일부 매도"
                ))

        self.alerts.extend(alerts)
        return alerts

    def check_consecutive_losses(self) -> Optional[RiskAlert]:
        """연속 손실 체크"""
        if len(self.trade_history) < self.config.max_consecutive_losses:
            return None

        recent_trades = self.trade_history[-self.config.max_consecutive_losses:]
        consecutive_losses = sum(1 for t in recent_trades if t.get("pnl", 0) < 0)

        if consecutive_losses >= self.config.max_consecutive_losses:
            self.is_trading_paused = True
            self.pause_until = datetime.now() + timedelta(days=self.config.pause_duration_days)

            alert = RiskAlert(
                level=RiskLevel.CRITICAL,
                alert_type="CONSECUTIVE_LOSSES",
                message=f"{consecutive_losses}연속 손실 발생",
                value=consecutive_losses,
                threshold=self.config.max_consecutive_losses,
                action_required=f"{self.config.pause_duration_days}일간 거래 중단"
            )
            self.alerts.append(alert)
            return alert

        return None

    def add_trade(self, trade: Dict):
        """거래 기록 추가"""
        self.trade_history.append(trade)

        # 손실 거래인 경우 연속 손실 체크
        if trade.get("pnl", 0) < 0:
            self.check_consecutive_losses()

    def can_trade(self) -> Tuple[bool, str]:
        """
        거래 가능 여부 확인

        Returns:
            (거래 가능 여부, 불가능 사유)
        """
        # 거래 중단 상태 확인
        if self.is_trading_paused:
            if datetime.now() < self.pause_until:
                remaining = (self.pause_until - datetime.now()).days
                return False, f"거래 중단 중 (남은 기간: {remaining}일)"
            else:
                self.is_trading_paused = False
                self.pause_until = None

        # 최근 경고 확인
        critical_alerts = [
            a for a in self.alerts[-10:]
            if a.level == RiskLevel.CRITICAL and
            (datetime.now() - a.timestamp).seconds < 3600
        ]

        if critical_alerts:
            return False, f"위험 경고 발생: {critical_alerts[0].message}"

        return True, ""

    def get_risk_summary(self) -> Dict:
        """리스크 요약 정보"""
        if not self.history:
            return {"status": "NO_DATA"}

        latest = self.history[-1]

        # 최근 경고 수
        recent_alerts = [
            a for a in self.alerts
            if (datetime.now() - a.timestamp).days < 1
        ]

        # 연속 손실 수
        consecutive_losses = 0
        for trade in reversed(self.trade_history):
            if trade.get("pnl", 0) < 0:
                consecutive_losses += 1
            else:
                break

        return {
            "status": "OK" if not self.is_trading_paused else "PAUSED",
            "total_value": latest.total_value,
            "daily_pnl_pct": latest.daily_pnl_pct,
            "mdd": latest.mdd * 100,
            "cash_ratio": (latest.cash / latest.total_value * 100) if latest.total_value > 0 else 100,
            "position_count": len(latest.positions),
            "recent_alerts": len(recent_alerts),
            "consecutive_losses": consecutive_losses,
            "can_trade": self.can_trade()[0]
        }


class PortfolioManager:
    """포트폴리오 관리자"""

    def __init__(
        self,
        total_capital: float,
        config: RiskConfig = None
    ):
        self.total_capital = total_capital
        self.config = config or RiskConfig()
        self.positions: Dict[str, Position] = {}
        self.cash = total_capital
        self.risk_monitor = RiskMonitor(config)
        self.position_sizer = PositionSizer(config)

    @property
    def total_value(self) -> float:
        """총 평가금액"""
        invested = sum(p.market_value for p in self.positions.values())
        return self.cash + invested

    @property
    def invested_ratio(self) -> float:
        """투자 비중"""
        if self.total_value <= 0:
            return 0
        return (self.total_value - self.cash) / self.total_value

    def add_position(self, position: Position):
        """포지션 추가"""
        self.positions[position.code] = position
        self.cash -= position.entry_price * position.quantity

    def remove_position(self, code: str, sell_price: float) -> Optional[Dict]:
        """
        포지션 제거

        Returns:
            거래 기록
        """
        if code not in self.positions:
            return None

        position = self.positions[code]
        pnl = (sell_price - position.entry_price) * position.quantity
        pnl_pct = (sell_price - position.entry_price) / position.entry_price * 100

        self.cash += sell_price * position.quantity
        del self.positions[code]

        trade_record = {
            "code": code,
            "name": position.name,
            "entry_price": position.entry_price,
            "exit_price": sell_price,
            "quantity": position.quantity,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "entry_date": position.entry_date,
            "exit_date": datetime.now()
        }

        self.risk_monitor.add_trade(trade_record)

        return trade_record

    def update_prices(self, price_map: Dict[str, float]):
        """현재가 업데이트"""
        for code, price in price_map.items():
            if code in self.positions:
                self.positions[code].current_price = price

    def get_snapshot(self) -> PortfolioSnapshot:
        """현재 스냅샷 생성"""
        positions_list = list(self.positions.values())
        invested = sum(p.market_value for p in positions_list)

        total_pnl = sum(
            (p.current_price - p.entry_price) * p.quantity
            for p in positions_list
        )

        total_pnl_pct = (total_pnl / self.total_capital * 100) if self.total_capital > 0 else 0

        snapshot = PortfolioSnapshot(
            timestamp=datetime.now(),
            total_value=self.total_value,
            cash=self.cash,
            invested=invested,
            positions=positions_list,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct
        )

        self.risk_monitor.update_snapshot(snapshot)

        return snapshot

    def check_risks(self) -> List[RiskAlert]:
        """리스크 체크"""
        snapshot = self.get_snapshot()
        return self.risk_monitor.check_all_risks(snapshot)

    def get_rebalancing_orders(
        self,
        target_weights: Dict[str, float]
    ) -> List[Dict]:
        """
        리밸런싱 주문 생성

        Args:
            target_weights: 목표 비중 {종목코드: 비중}

        Returns:
            주문 리스트
        """
        orders = []
        current_weights = {}

        # 현재 비중 계산
        for code, position in self.positions.items():
            current_weights[code] = position.market_value / self.total_value

        # 매도 주문 (비중 축소)
        for code in self.positions:
            target = target_weights.get(code, 0)
            current = current_weights.get(code, 0)

            if target < current - 0.02:  # 2%p 이상 차이
                sell_amount = (current - target) * self.total_value
                position = self.positions[code]
                sell_qty = int(sell_amount / position.current_price)

                if sell_qty > 0:
                    orders.append({
                        "type": "SELL",
                        "code": code,
                        "name": position.name,
                        "quantity": sell_qty,
                        "reason": f"비중 축소 {current*100:.1f}% → {target*100:.1f}%"
                    })

        # 매수 주문 (비중 확대 또는 신규)
        for code, target in target_weights.items():
            current = current_weights.get(code, 0)

            if target > current + 0.02:  # 2%p 이상 차이
                buy_amount = (target - current) * self.total_value
                orders.append({
                    "type": "BUY",
                    "code": code,
                    "amount": buy_amount,
                    "reason": f"비중 확대 {current*100:.1f}% → {target*100:.1f}%"
                })

        return orders
