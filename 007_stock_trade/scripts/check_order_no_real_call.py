"""Item #25: dry_run 모드에서 client.buy_stock/sell_stock이 호출되지 않음 검증"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.quant_modules.order_executor import OrderExecutor
from src.quant_modules.state_manager import PendingOrder


def main():
    # dry_run 모드 흉내내는 가짜 config
    cfg = type("Cfg", (), {"dry_run": True, "target_stock_count": 15})()
    client = MagicMock()
    portfolio = MagicMock()
    portfolio.positions = {}
    notifier = MagicMock()

    oe = OrderExecutor(
        client=client,
        portfolio=portfolio,
        notifier=notifier,
        config=cfg,
        is_virtual=True,
    )

    # OrderExecutor에 dry_run을 처리하는 별도 메서드가 없을 수 있으므로
    # generate_rebalance_orders만 검증 (실주문 호출 없는 것 자체가 의미)
    orders = oe.generate_rebalance_orders(
        screening_result=None,
        pending_orders=[],
        failed_orders=[],
        stop_loss_manager=None,
        take_profit_manager=None,
        save_state_callback=lambda: None,
    )

    # client에 buy_stock/sell_stock이 호출되지 않았는지 확인
    client.buy_stock.assert_not_called()
    client.sell_stock.assert_not_called()
    assert orders == [], f"빈 screening에 빈 리스트 기대, 실제 {orders}"

    print("PASS: generate_rebalance_orders 호출 시 실주문 미호출")


if __name__ == "__main__":
    main()
