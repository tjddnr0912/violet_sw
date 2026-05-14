"""Item #27: 손절가 도달 시 매도 트리거 (실주문 mock)"""
import sys
import threading
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.quant_modules.position_monitor import PositionMonitor
from src.strategy.quant import Position


def main():
    # 포지션 1개, 손절가 아래로 떨어뜨림
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

    # client.get_stock_price → 손절가 아래 가격 반환
    client = MagicMock()
    price_info = MagicMock()
    price_info.price = 45000  # 손절 트리거
    client.get_stock_price.return_value = price_info

    notifier = MagicMock()
    cfg = type("Cfg", (), {"trailing_stop": False, "stop_loss_pct": 0.07})()

    order_executor = MagicMock()
    pm = PositionMonitor(client, portfolio, notifier, cfg, is_virtual=True, order_executor=order_executor)

    # _trigger_stop_loss를 spy
    triggered = {"n": 0}
    orig = pm._trigger_stop_loss
    def spy(position, daily_trades):
        triggered["n"] += 1
        # 실제 주문 호출 차단 (실주문 방지)
        # 내부적으로 order_executor._execute_sell_or_similar 호출되더라도 MagicMock
    pm._trigger_stop_loss = spy

    lock = threading.Lock()
    daily_trades = []
    pm.monitor(lock, daily_trades, save_state_fn=lambda: None)

    assert triggered["n"] == 1, f"손절 트리거 1회 기대, 실제 {triggered['n']}"
    print("PASS: 손절가 도달 시 _trigger_stop_loss 호출")


if __name__ == "__main__":
    main()
