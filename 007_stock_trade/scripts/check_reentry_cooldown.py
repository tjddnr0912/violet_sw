"""Item #42: 재진입 쿨다운 - 최근 손절 종목 재매수 차단"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.quant_modules.order_executor import (
    OrderExecutor,
    COOLDOWN_DAYS,
    COOLDOWN_OVERRIDE_DROP_PCT,
)


def _mk(daily_tracker, current_price):
    client = MagicMock()
    price_info = MagicMock()
    price_info.price = current_price
    client.get_stock_price.return_value = price_info
    oe = OrderExecutor(
        client=client,
        portfolio=MagicMock(),
        notifier=MagicMock(),
        config=MagicMock(),
        is_virtual=True,
        daily_tracker=daily_tracker,
    )
    return oe


def main():
    today = datetime.now().strftime("%Y-%m-%d")

    # 케이스 1: 최근 손절 + 현재가 미회복(=손절가 근처) → 차단
    dt1 = MagicMock()
    dt1.get_recent_transactions.return_value = [
        {"type": "SELL", "code": "015760", "date": today, "price": 50000, "pnl": -5000},
    ]
    oe1 = _mk(dt1, current_price=49500)  # 손절가 50000 → 현재 49500 (1% 하락)
    codes = oe1._build_cooldown_codes()
    assert oe1._is_blocked_by_cooldown("015760", codes) is True

    # 케이스 2: 손절 후 추가 5%+ 하락 → 쿨다운 해제 (재매수 허용)
    oe2 = _mk(dt1, current_price=47000)  # 50000 → 47000 (6% 하락)
    codes2 = oe2._build_cooldown_codes()
    assert oe2._is_blocked_by_cooldown("015760", codes2) is False

    # 케이스 3: 다른 종목 → 차단 안 됨
    assert oe2._is_blocked_by_cooldown("005930", codes2) is False

    # 케이스 4: 손절이 아니라 익절(pnl>0) → 차단 안 됨
    dt4 = MagicMock()
    dt4.get_recent_transactions.return_value = [
        {"type": "SELL", "code": "088350", "date": today, "price": 50000, "pnl": 10000},
    ]
    oe4 = _mk(dt4, current_price=49500)
    codes4 = oe4._build_cooldown_codes()
    assert "088350" not in codes4
    assert oe4._is_blocked_by_cooldown("088350", codes4) is False

    print(f"PASS: 쿨다운 {COOLDOWN_DAYS}일, 추가 하락 {COOLDOWN_OVERRIDE_DROP_PCT*100:.0f}%로 해제")


if __name__ == "__main__":
    main()
