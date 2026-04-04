"""KIS order execution module.

Handles buy/sell orders for US stocks via KIS REST API.
Supports paper trading (VTS) and live trading modes.
"""

import logging
from typing import Optional

from src.api.kis_client import KISClient

logger = logging.getLogger("casper")


class KISOrder:
    """Order execution via KIS API."""

    def __init__(self, client: KISClient, trading_mode: str = "paper"):
        self.client = client
        self.trading_mode = trading_mode
        # Transaction IDs differ between paper and live
        if trading_mode == "live":
            self.buy_tr_id = "TTTT1002U"   # 미국매수
            self.sell_tr_id = "TTTT1006U"  # 미국매도
        else:
            self.buy_tr_id = "VTTT1002U"   # 모의 미국매수
            self.sell_tr_id = "VTTT1006U"  # 모의 미국매도

    def buy_market(self, symbol: str, qty: int, exchange: str = "NASD") -> Optional[dict]:
        """
        Place a market buy order.

        KIS overseas stocks do not support true market orders on NASD.
        Uses current price as limit price for immediate execution.

        Args:
            symbol: Ticker symbol.
            qty: Number of shares (integer).
            exchange: Exchange code.

        Returns:
            Order result dict or None on failure.
        """
        price = self._get_market_price(symbol)
        if price is None:
            logger.error(f"BUY: Cannot get price for {symbol}")
            return None
        # Bid slightly above current price for immediate fill
        limit_price = round(price * 1.005, 2)  # +0.5% slippage buffer
        return self._place_order(
            symbol=symbol, qty=qty, side="buy",
            exchange=exchange, price=limit_price, order_type="00"
        )

    def sell_market(self, symbol: str, qty: int, exchange: str = "NASD") -> Optional[dict]:
        """
        Place a market sell order.

        KIS overseas stocks: uses current price as limit price.

        Args:
            symbol: Ticker symbol.
            qty: Number of shares (integer).
            exchange: Exchange code.

        Returns:
            Order result dict or None on failure.
        """
        price = self._get_market_price(symbol)
        if price is None:
            logger.error(f"SELL: Cannot get price for {symbol}")
            return None
        # Ask slightly below current price for immediate fill
        limit_price = round(price * 0.995, 2)  # -0.5% slippage buffer
        return self._place_order(
            symbol=symbol, qty=qty, side="sell",
            exchange=exchange, price=limit_price, order_type="00"
        )

    def _get_market_price(self, symbol: str) -> Optional[float]:
        """Get current price for market-like order execution."""
        data = self.client.get_us_price(symbol)
        if data and data.get("price", 0) > 0:
            return data["price"]
        return None

    def buy_limit(self, symbol: str, qty: int, price: float, exchange: str = "NASD") -> Optional[dict]:
        """Place a limit buy order."""
        return self._place_order(
            symbol=symbol, qty=qty, side="buy",
            exchange=exchange, price=price, order_type="00"
        )

    def sell_limit(self, symbol: str, qty: int, price: float, exchange: str = "NASD") -> Optional[dict]:
        """Place a limit sell order."""
        return self._place_order(
            symbol=symbol, qty=qty, side="sell",
            exchange=exchange, price=price, order_type="00"
        )

    def _place_order(
        self, symbol: str, qty: int, side: str,
        exchange: str, price: float, order_type: str
    ) -> Optional[dict]:
        """
        Internal order placement.

        Args:
            symbol: Ticker.
            qty: Shares (must be integer >= 1).
            side: "buy" or "sell".
            exchange: Exchange code.
            price: Limit price (0 for market).
            order_type: "00" for limit/market.
        """
        if qty < 1:
            logger.error(f"Order: Invalid qty {qty} (must be >= 1)")
            return None

        tr_id = self.buy_tr_id if side == "buy" else self.sell_tr_id

        url = f"{self.client.base_url}/uapi/overseas-stock/v1/trading/order"
        headers = {"tr_id": tr_id}
        body = {
            "CANO": self.client.account_no,
            "ACNT_PRDT_CD": self.client.product_code,
            "OVRS_EXCG_CD": exchange,
            "PDNO": symbol,
            "ORD_QTY": str(qty),
            "OVRS_ORD_UNPR": str(price) if price > 0 else "0",
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": order_type,
        }

        logger.info(
            f"ORDER: {side.upper()} {symbol} x{qty} "
            f"@ {'MARKET' if price == 0 else f'${price:.2f}'} "
            f"[{self.trading_mode}]"
        )

        # retry=False: POST 주문은 재시도하지 않음 (중복 주문 방지)
        data = self.client._request("POST", url, headers=headers, json_body=body, retry=False)
        if data and "output" in data:
            output = data["output"]
            order_no = output.get("ODNO", "N/A")
            logger.info(f"ORDER OK: #{order_no}")
            return {"order_no": order_no, "symbol": symbol, "qty": qty, "side": side}

        logger.error(f"ORDER FAILED: {symbol} {side} x{qty}")
        return None
