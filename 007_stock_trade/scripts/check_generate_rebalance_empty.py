"""Item #26: generate_rebalance_orders가 screening_result=None일 때 빈 결과"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.quant_modules.order_executor import OrderExecutor


def main():
    client = MagicMock()
    portfolio = MagicMock()
    portfolio.positions = {}
    notifier = MagicMock()
    cfg = MagicMock()

    oe = OrderExecutor(client, portfolio, notifier, cfg, is_virtual=True)
    out = oe.generate_rebalance_orders(
        screening_result=None,
        pending_orders=[],
        failed_orders=[],
        stop_loss_manager=None,
        take_profit_manager=None,
        save_state_callback=lambda: None,
    )
    assert out == [], f"None 입력에 [] 기대, 실제 {out}"
    print("PASS: generate_rebalance_orders(None) → []")


if __name__ == "__main__":
    main()
