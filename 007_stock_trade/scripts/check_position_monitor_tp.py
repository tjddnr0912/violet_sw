"""Item #28: 1차 익절 도달 시 부분 매도 트리거"""
import sys
import threading
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.quant_modules.position_monitor import PositionMonitor
from src.strategy.quant import Position


def main():
    pos = Position(
        code="005930",
        name="삼성전자",
        entry_price=50000,
        current_price=50000,
        quantity=10,
        entry_date=datetime.now(),
        stop_loss=46500,
        take_profit_1=62250,
        take_profit_2=71000,
        highest_price=50000,
    )
    portfolio = MagicMock()
    portfolio.positions = {pos.code: pos}

    client = MagicMock()
    price_info = MagicMock()
    price_info.price = 62500  # tp1 도달
    client.get_stock_price.return_value = price_info

    notifier = MagicMock()
    cfg = type("Cfg", (), {"trailing_stop": False, "stop_loss_pct": 0.07})()

    order_executor = MagicMock()
    pm = PositionMonitor(client, portfolio, notifier, cfg, is_virtual=True, order_executor=order_executor)

    triggered = {"tp1": 0, "tp2": 0}
    def spy_tp(position, stage, daily_trades):
        triggered[f"tp{stage}"] += 1
    pm._trigger_take_profit = spy_tp

    lock = threading.Lock()
    daily_trades = []
    pm.monitor(lock, daily_trades, save_state_fn=lambda: None)

    assert triggered["tp1"] == 1, f"tp1 1회 기대, 실제 {triggered}"
    assert triggered["tp2"] == 0
    print("PASS: 1차 익절 도달 시 _trigger_take_profit(stage=1)")


if __name__ == "__main__":
    main()
