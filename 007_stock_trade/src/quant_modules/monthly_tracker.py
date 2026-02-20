"""
월간 포트폴리오 트래커

월간 스냅샷 저장, 리포트 생성, 전월 대비 비교 기능 담당
"""

import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, TYPE_CHECKING

from .tracker_base import TrackerBase

if TYPE_CHECKING:
    from ..strategy.quant import PortfolioSnapshot
    from ..api.kis_quant import KISQuantClient

logger = logging.getLogger(__name__)


@dataclass
class MonthlySnapshot:
    """월간 포트폴리오 스냅샷"""
    month: str                          # "2026-01"
    date: str                           # "2026-01-02"
    total_assets: float                 # 총 자산 (예수금 + 평가금)
    cash: float                         # 예수금
    invested: float                     # 투자금 (평가금)
    position_count: int                 # 보유 종목 수
    total_pnl: float                    # 총 손익 (원)
    total_pnl_pct: float               # 총 수익률 (%)
    positions: List[Dict] = field(default_factory=list)   # 종목별 상세
    trades: List[Dict] = field(default_factory=list)      # 이번 달 거래 내역
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환 (JSON 직렬화용)"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MonthlySnapshot':
        """딕셔너리에서 생성"""
        return cls(
            month=data["month"],
            date=data["date"],
            total_assets=data["total_assets"],
            cash=data["cash"],
            invested=data["invested"],
            position_count=data["position_count"],
            total_pnl=data["total_pnl"],
            total_pnl_pct=data["total_pnl_pct"],
            positions=data.get("positions", []),
            trades=data.get("trades", []),
            created_at=data.get("created_at", datetime.now().isoformat())
        )


class MonthlyTracker(TrackerBase):
    """
    월간 포트폴리오 트래커

    월간 스냅샷 저장/로드, 리포트 생성 담당
    """

    def __init__(self, data_dir: Path):
        """
        Args:
            data_dir: 데이터 저장 디렉토리 (예: data/quant)
        """
        super().__init__(data_dir)
        self.history_file = self.data_dir / "monthly_history.json"
        self.snapshots: List[MonthlySnapshot] = []
        self._load_history()

    def _load_history(self):
        """월간 히스토리 로드"""
        data = self._load_json(self.history_file, "월간 히스토리")
        if data is None:
            self.snapshots = []
            return

        self.snapshots = [
            MonthlySnapshot.from_dict(s) for s in data.get("snapshots", [])
        ]
        logger.info(f"월간 히스토리 로드: {len(self.snapshots)}개월")

    def _save_history(self):
        """월간 히스토리 저장"""
        data = {
            "snapshots": [s.to_dict() for s in self.snapshots],
            "updated_at": datetime.now().isoformat()
        }
        if self._save_json(self.history_file, data, "월간 히스토리"):
            logger.info(f"월간 히스토리 저장: {len(self.snapshots)}개월")

    def get_previous_month_snapshot(self, current_month: str) -> Optional[MonthlySnapshot]:
        """
        이전 달 스냅샷 조회

        Args:
            current_month: 현재 월 (YYYY-MM)

        Returns:
            이전 달 스냅샷 또는 None
        """
        # 스냅샷을 날짜순으로 정렬
        sorted_snapshots = sorted(self.snapshots, key=lambda s: s.month)

        for snapshot in reversed(sorted_snapshots):
            if snapshot.month < current_month:
                return snapshot

        return None

    def save_snapshot(self, snapshot: MonthlySnapshot):
        """
        월간 스냅샷 저장

        같은 월의 스냅샷이 있으면 업데이트, 없으면 추가
        """
        # 같은 월 스냅샷이 있으면 업데이트
        for i, s in enumerate(self.snapshots):
            if s.month == snapshot.month:
                self.snapshots[i] = snapshot
                logger.info(f"월간 스냅샷 업데이트: {snapshot.month}")
                self._save_history()
                return

        # 새 스냅샷 추가
        self.snapshots.append(snapshot)
        logger.info(f"새 월간 스냅샷 저장: {snapshot.month}")
        self._save_history()

    def generate_monthly_report(
        self,
        portfolio_snapshot: 'PortfolioSnapshot',
        monthly_trades: List[Dict],
        total_assets: float,
        cash: float,
        is_auto_report: bool = True
    ) -> str:
        """
        월간 리포트 메시지 생성

        Args:
            portfolio_snapshot: 현재 포트폴리오 스냅샷
            monthly_trades: 이번 달 거래 내역
            total_assets: 총 자산 (예수금 + 평가금)
            cash: 예수금
            is_auto_report: 자동 리포트 여부 (False면 수동 요청)

        Returns:
            HTML 형식의 리포트 메시지
        """
        now = datetime.now()
        current_month = now.strftime("%Y-%m")
        month_display = now.strftime("%Y년 %m월")

        # 이전 달 스냅샷
        prev_snapshot = self.get_previous_month_snapshot(current_month)

        # 포지션 정보 추출
        positions = portfolio_snapshot.positions if portfolio_snapshot else []
        position_count = len(positions)
        invested = sum(p.market_value for p in positions) if positions else 0

        # 총 손익 계산
        total_pnl = sum((p.current_price - p.entry_price) * p.quantity for p in positions) if positions else 0
        total_pnl_pct = portfolio_snapshot.total_pnl_pct if portfolio_snapshot else 0

        # 거래 통계
        buy_trades = [t for t in monthly_trades if t.get('type') == 'BUY']
        sell_trades = [t for t in monthly_trades if t.get('type') == 'SELL']

        # 메시지 구성
        lines = []
        lines.append("📊 <b>월간 포트폴리오 리포트</b>")
        lines.append("")
        lines.append(f"📅 {month_display}")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        # 종합 현황
        lines.append("<b>📈 종합 현황</b>")
        lines.append(f"• 총 자산: {total_assets:,.0f}원")
        lines.append(f"• 현금: {cash:,.0f}원")
        lines.append(f"• 투자금: {invested:,.0f}원")
        lines.append(f"• 보유 종목: {position_count}개")
        lines.append("")

        # 수익 현황
        lines.append("<b>💰 수익 현황</b>")
        pnl_sign = "+" if total_pnl >= 0 else ""
        pct_sign = "+" if total_pnl_pct >= 0 else ""
        lines.append(f"• 총 손익: {pnl_sign}{total_pnl:,.0f}원 ({pct_sign}{total_pnl_pct:.2f}%)")

        # 전월 대비 (있는 경우)
        if prev_snapshot:
            asset_change = total_assets - prev_snapshot.total_assets
            asset_change_pct = (asset_change / prev_snapshot.total_assets * 100) if prev_snapshot.total_assets > 0 else 0
            change_sign = "+" if asset_change >= 0 else ""
            arrow = "↑" if asset_change >= 0 else "↓"
            lines.append(f"• 전월 대비: {change_sign}{asset_change:,.0f}원 ({arrow}{abs(asset_change_pct):.2f}%)")
        else:
            lines.append("• 전월 대비: 첫 월간 리포트입니다")
        lines.append("")

        # 종목별 손익
        if positions:
            # 손익 기준 정렬
            sorted_positions = sorted(
                positions,
                key=lambda p: (p.current_price - p.entry_price) * p.quantity,
                reverse=True
            )

            # 상위 5개
            lines.append("<b>📊 종목별 손익 (상위)</b>")
            for i, pos in enumerate(sorted_positions[:5], 1):
                pnl = (pos.current_price - pos.entry_price) * pos.quantity
                pnl_sign = "+" if pnl >= 0 else ""
                pct_sign = "+" if pos.profit_pct >= 0 else ""
                lines.append(f"{i}. {pos.name}: {pnl_sign}{pnl:,.0f}원 ({pct_sign}{pos.profit_pct:.1f}%)")
            lines.append("")

            # 하위 3개 (손실 종목이 있는 경우)
            bottom_positions = [p for p in sorted_positions[-3:] if (p.current_price - p.entry_price) * p.quantity < 0]
            if bottom_positions:
                lines.append("<b>📉 종목별 손익 (하위)</b>")
                for pos in bottom_positions:
                    pnl = (pos.current_price - pos.entry_price) * pos.quantity
                    lines.append(f"• {pos.name}: {pnl:,.0f}원 ({pos.profit_pct:+.1f}%)")
                lines.append("")
        else:
            lines.append("<b>📊 종목별 손익</b>")
            lines.append("• 현재 보유 종목 없음")
            lines.append("")

        # 거래 내역
        lines.append("<b>🔄 거래 내역</b>")
        if monthly_trades:
            lines.append(f"• 총 매수: {len(buy_trades)}건")
            lines.append(f"• 총 매도: {len(sell_trades)}건")
        else:
            lines.append("• 이번 달 거래 없음")
        lines.append("")

        # 전월 대비 변화 (상세)
        if prev_snapshot:
            lines.append("<b>💹 전월 대비 변화</b>")
            lines.append(f"• 총 자산: {prev_snapshot.total_assets:,.0f} → {total_assets:,.0f}원")
            asset_change = total_assets - prev_snapshot.total_assets
            change_sign = "+" if asset_change >= 0 else ""
            asset_change_pct = (asset_change / prev_snapshot.total_assets * 100) if prev_snapshot.total_assets > 0 else 0
            lines.append(f"• 증감: {change_sign}{asset_change:,.0f}원 ({change_sign}{asset_change_pct:.2f}%)")
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"🕐 {now.strftime('%Y-%m-%d %H:%M:%S')}")

        return "\n".join(lines)

    def create_snapshot_from_portfolio(
        self,
        portfolio_snapshot: 'PortfolioSnapshot',
        monthly_trades: List[Dict],
        total_assets: float,
        cash: float
    ) -> MonthlySnapshot:
        """
        포트폴리오 스냅샷에서 월간 스냅샷 생성

        Args:
            portfolio_snapshot: 현재 포트폴리오 스냅샷
            monthly_trades: 이번 달 거래 내역
            total_assets: 총 자산
            cash: 예수금

        Returns:
            MonthlySnapshot 객체
        """
        now = datetime.now()
        positions = portfolio_snapshot.positions if portfolio_snapshot else []
        invested = sum(p.market_value for p in positions) if positions else 0
        total_pnl = sum((p.current_price - p.entry_price) * p.quantity for p in positions) if positions else 0
        total_pnl_pct = portfolio_snapshot.total_pnl_pct if portfolio_snapshot else 0

        position_data = []
        for p in positions:
            pnl = (p.current_price - p.entry_price) * p.quantity
            position_data.append({
                "code": p.code,
                "name": p.name,
                "quantity": p.quantity,
                "entry_price": p.entry_price,
                "current_price": p.current_price,
                "market_value": p.market_value,
                "pnl": pnl,
                "pnl_pct": p.profit_pct
            })

        return MonthlySnapshot(
            month=now.strftime("%Y-%m"),
            date=now.strftime("%Y-%m-%d"),
            total_assets=total_assets,
            cash=cash,
            invested=invested,
            position_count=len(positions),
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            positions=position_data,
            trades=monthly_trades.copy(),
            created_at=now.isoformat()
        )
