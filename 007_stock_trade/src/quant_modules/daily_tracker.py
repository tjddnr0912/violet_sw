"""
일별 자산 추적 및 거래 일지

일별 스냅샷 저장, 거래 즉시 기록, 조회 기능 담당
"""

import logging
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

from .tracker_base import TrackerBase

logger = logging.getLogger(__name__)

# 보관 기간 (일)
MAX_HISTORY_DAYS = 365


@dataclass
class DailySnapshot:
    """일별 자산 스냅샷"""
    date: str                           # "2026-02-09"
    total_assets: float                 # 총 자산 (예수금 + 평가금)
    cash: float                         # 예수금
    invested: float                     # 투자금 (평가금)
    buy_amount: float                   # 매입금액 합계
    position_count: int                 # 보유 종목 수
    total_pnl: float                    # 총 손익 (원)
    total_pnl_pct: float               # 총 수익률 (%)
    daily_pnl: float                    # 전일 대비 손익
    daily_pnl_pct: float               # 전일 대비 수익률
    trades_today: int                   # 당일 거래 횟수
    positions: List[Dict] = field(default_factory=list)  # 종목별 상세
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DailySnapshot':
        return cls(
            date=data["date"],
            total_assets=data["total_assets"],
            cash=data["cash"],
            invested=data["invested"],
            buy_amount=data.get("buy_amount", 0),
            position_count=data["position_count"],
            total_pnl=data["total_pnl"],
            total_pnl_pct=data["total_pnl_pct"],
            daily_pnl=data.get("daily_pnl", 0),
            daily_pnl_pct=data.get("daily_pnl_pct", 0),
            trades_today=data.get("trades_today", 0),
            positions=data.get("positions", []),
            created_at=data.get("created_at", datetime.now().isoformat())
        )


@dataclass
class TransactionRecord:
    """거래 기록"""
    timestamp: str                      # ISO format
    date: str                           # "2026-02-09"
    type: str                           # "BUY" | "SELL"
    code: str                           # 종목코드
    name: str                           # 종목명
    quantity: int
    price: float                        # 체결가
    amount: float                       # 총 금액
    order_no: str
    reason: str
    pnl: float = 0                      # 손익 (SELL만)
    pnl_pct: float = 0                  # 수익률 (SELL만)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TransactionRecord':
        return cls(
            timestamp=data["timestamp"],
            date=data["date"],
            type=data["type"],
            code=data["code"],
            name=data["name"],
            quantity=data["quantity"],
            price=data["price"],
            amount=data.get("amount", data["quantity"] * data["price"]),
            order_no=data.get("order_no", ""),
            reason=data.get("reason", ""),
            pnl=data.get("pnl", 0),
            pnl_pct=data.get("pnl_pct", 0)
        )


class DailyTracker(TrackerBase):
    """
    일별 자산 추적기

    일별 스냅샷 저장/로드, 거래 즉시 기록 담당
    """

    def __init__(self, data_dir: Path):
        super().__init__(data_dir)
        self.history_file = self.data_dir / "daily_history.json"
        self.transaction_file = self.data_dir / "transaction_journal.json"

        self.snapshots: List[DailySnapshot] = []
        self.transactions: List[TransactionRecord] = []
        self.initial_capital: float = 0

        self._load_history()
        self._load_transactions()

    # ========== 히스토리 (일별 스냅샷) ==========

    def _load_history(self):
        data = self._load_json(self.history_file, "일별 히스토리")
        if data is None:
            self.snapshots = []
            return

        self.initial_capital = data.get("initial_capital", 0)
        self.snapshots = [
            DailySnapshot.from_dict(s) for s in data.get("snapshots", [])
        ]
        logger.info(f"일별 히스토리 로드: {len(self.snapshots)}일, 초기자본: {self.initial_capital:,.0f}원")

    def _save_history(self):
        data = {
            "initial_capital": self.initial_capital,
            "snapshots": [s.to_dict() for s in self.snapshots],
            "updated_at": datetime.now().isoformat()
        }
        if self._save_json(self.history_file, data, "일별 히스토리"):
            logger.debug(f"일별 히스토리 저장: {len(self.snapshots)}일")

    # ========== 거래 일지 ==========

    def _load_transactions(self):
        data = self._load_json(self.transaction_file, "거래 일지")
        if data is None:
            self.transactions = []
            return

        self.transactions = [
            TransactionRecord.from_dict(t) for t in data.get("transactions", [])
        ]
        logger.info(f"거래 일지 로드: {len(self.transactions)}건")

    def _save_transactions(self):
        data = {
            "transactions": [t.to_dict() for t in self.transactions],
            "updated_at": datetime.now().isoformat()
        }
        if self._save_json(self.transaction_file, data, "거래 일지"):
            logger.debug(f"거래 일지 저장: {len(self.transactions)}건")

    # ========== 공개 API ==========

    def save_daily_snapshot(self, snapshot: DailySnapshot):
        """일별 스냅샷 저장 (같은 날짜면 업데이트)"""
        for i, s in enumerate(self.snapshots):
            if s.date == snapshot.date:
                self.snapshots[i] = snapshot
                logger.info(f"일별 스냅샷 업데이트: {snapshot.date}")
                self._cleanup_old_snapshots()
                self._save_history()
                return

        self.snapshots.append(snapshot)
        logger.info(f"새 일별 스냅샷 저장: {snapshot.date}")
        self._cleanup_old_snapshots()
        self._save_history()

    def log_transaction(self, trade_dict: Dict[str, Any]):
        """
        거래 즉시 기록

        order_executor의 daily_trades.append() 형식 그대로 수용
        """
        try:
            timestamp = trade_dict.get("timestamp", datetime.now().isoformat())
            date_str = timestamp[:10]  # "2026-02-09T09:00:00" → "2026-02-09"

            record = TransactionRecord(
                timestamp=timestamp,
                date=date_str,
                type=trade_dict.get("type", ""),
                code=trade_dict.get("code", ""),
                name=trade_dict.get("name", ""),
                quantity=trade_dict.get("quantity", 0),
                price=trade_dict.get("price", 0),
                amount=trade_dict.get("quantity", 0) * trade_dict.get("price", 0),
                order_no=trade_dict.get("order_no", ""),
                reason=trade_dict.get("reason", ""),
                pnl=trade_dict.get("pnl", 0),
                pnl_pct=trade_dict.get("pnl_pct", 0)
            )

            self.transactions.append(record)
            self._cleanup_old_transactions()
            self._save_transactions()
            logger.info(f"거래 기록: {record.type} {record.name} {record.quantity}주 @ {record.price:,.0f}원")

        except Exception as e:
            logger.error(f"거래 기록 실패: {e}", exc_info=True)

    def get_previous_snapshot(self) -> Optional[DailySnapshot]:
        """직전 일 스냅샷 조회"""
        sorted_snapshots = sorted(self.snapshots, key=lambda s: s.date)
        if len(sorted_snapshots) >= 2:
            return sorted_snapshots[-2]
        return None

    def get_latest_snapshot(self) -> Optional[DailySnapshot]:
        """최신 스냅샷 조회"""
        if not self.snapshots:
            return None
        return sorted(self.snapshots, key=lambda s: s.date)[-1]

    def get_previous_day_snapshot(self, today: str) -> Optional[DailySnapshot]:
        """오늘 이전 날짜의 가장 최근 스냅샷 조회 (daily_pnl 계산용)"""
        candidates = [s for s in self.snapshots if s.date < today]
        if not candidates:
            return None
        return sorted(candidates, key=lambda s: s.date)[-1]

    def get_recent_snapshots(self, days: int = 7) -> List[DailySnapshot]:
        """최근 N일 스냅샷 (최신순)"""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        recent = [s for s in self.snapshots if s.date >= cutoff]
        return sorted(recent, key=lambda s: s.date, reverse=True)

    def get_recent_transactions(self, days: int = 7) -> List[TransactionRecord]:
        """최근 N일 거래 (최신순)"""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        recent = [t for t in self.transactions if t.date >= cutoff]
        return sorted(recent, key=lambda t: t.timestamp, reverse=True)

    def get_first_snapshot_date(self) -> Optional[str]:
        """최초 스냅샷 날짜"""
        if not self.snapshots:
            return None
        return sorted(self.snapshots, key=lambda s: s.date)[0].date

    # ========== 장부 점검 (Reconciliation) ==========

    def reconcile_latest_snapshot(self, kis_data: dict, initial_capital: float) -> dict:
        """
        최근 스냅샷을 KIS 실잔고와 대조하여 보정

        Args:
            kis_data: {cash, scts_evlu, buy_amount, stocks, total_profit}
            initial_capital: 초기 투자금

        Returns:
            {"checked": bool, "corrected": bool, "diff": float, "details": str}
        """
        from src.utils.balance_helpers import parse_balance

        latest = self.get_latest_snapshot()
        if not latest:
            return {"checked": False, "corrected": False, "diff": 0, "details": "스냅샷 없음"}

        bs = parse_balance(kis_data)
        kis_total = bs.total_assets
        kis_cash = bs.cash
        kis_scts = bs.scts_evlu
        kis_buy_amount = bs.buy_amount
        kis_stocks = kis_data.get('stocks', [])

        diff = abs(latest.total_assets - kis_total)
        threshold = kis_total * 0.01 if kis_total > 0 else 0  # 1% 오차 허용

        result = {
            "checked": True,
            "corrected": False,
            "diff": latest.total_assets - kis_total,
            "snapshot_date": latest.date,
            "snapshot_total": latest.total_assets,
            "kis_total": kis_total,
            "details": ""
        }

        if diff <= threshold:
            pct = (diff / kis_total * 100) if kis_total > 0 else 0
            result["details"] = f"정상 (편차 {diff:,.0f}원, {pct:.2f}%)"
            return result

        # 편차 발견 → 최근 스냅샷 보정
        old_total = latest.total_assets
        latest.total_assets = kis_total
        latest.cash = kis_cash
        latest.invested = kis_scts
        latest.buy_amount = kis_buy_amount
        latest.position_count = len(kis_stocks)

        # PnL 재계산
        latest.total_pnl = kis_total - initial_capital
        latest.total_pnl_pct = (latest.total_pnl / initial_capital * 100) if initial_capital > 0 else 0

        # daily_pnl 재계산 (직전 스냅샷 대비)
        prev = self.get_previous_day_snapshot(latest.date)
        if prev:
            latest.daily_pnl = kis_total - prev.total_assets
            latest.daily_pnl_pct = (latest.daily_pnl / prev.total_assets * 100) if prev.total_assets > 0 else 0

        self._save_history()

        result["corrected"] = True
        result["details"] = f"보정 완료: {old_total:,.0f} → {kis_total:,.0f} (편차 {old_total - kis_total:+,.0f}원)"
        logger.info(f"장부 보정: {result['details']}")
        return result

    # ========== 내부 유틸 ==========

    def _cleanup_old_snapshots(self):
        """365일 초과 스냅샷 정리"""
        if len(self.snapshots) <= MAX_HISTORY_DAYS:
            return

        cutoff = (datetime.now() - timedelta(days=MAX_HISTORY_DAYS)).strftime("%Y-%m-%d")
        before = len(self.snapshots)
        self.snapshots = [s for s in self.snapshots if s.date >= cutoff]
        removed = before - len(self.snapshots)
        if removed > 0:
            logger.info(f"오래된 스냅샷 {removed}개 정리")

    def _cleanup_old_transactions(self):
        """365일 초과 거래 정리"""
        if len(self.transactions) <= MAX_HISTORY_DAYS * 10:
            return

        cutoff = (datetime.now() - timedelta(days=MAX_HISTORY_DAYS)).strftime("%Y-%m-%d")
        before = len(self.transactions)
        self.transactions = [t for t in self.transactions if t.date >= cutoff]
        removed = before - len(self.transactions)
        if removed > 0:
            logger.info(f"오래된 거래 기록 {removed}개 정리")
