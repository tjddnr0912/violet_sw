"""KIS REST API client for US stock trading.

Provides methods for price queries, balance checks, and daily candles.
"""

import logging
import time
from typing import Optional

import requests

from src.api.kis_auth import KISAuth

logger = logging.getLogger("casper")

MAX_RETRIES = 3
RETRY_DELAY = 2
API_DELAY = 0.3  # Minimum interval between API calls (rate limiting)

# KIS exchange code mapping: order API uses 4-char, price API uses 3-char
_EXCHANGE_MAP_4TO3 = {"NASD": "NAS", "NYSE": "NYS", "AMEX": "AMS"}
_EXCHANGE_MAP_3TO4 = {v: k for k, v in _EXCHANGE_MAP_4TO3.items()}


class KISClient:
    """KIS REST API client."""

    def __init__(self, auth: KISAuth, account_no: str, product_code: str = "01"):
        self.auth = auth
        self.account_no = account_no
        self.product_code = product_code
        self.base_url = auth.base_url
        self._last_call_time: float = 0

    def _request(self, method: str, url: str, headers: dict = None,
                 params: dict = None, json_body: dict = None,
                 retry: bool = True) -> Optional[dict]:
        """Make an API request with retry logic.

        Args:
            retry: If False, do not retry on failure (use for POST orders
                   to prevent duplicate submissions).
        """
        hdrs = {**self.auth.headers, **(headers or {})}
        max_attempts = MAX_RETRIES if retry else 1

        # Rate limiting: enforce minimum interval between API calls
        elapsed = time.time() - self._last_call_time
        if elapsed < API_DELAY:
            time.sleep(API_DELAY - elapsed)

        for attempt in range(1, max_attempts + 1):
            try:
                self._last_call_time = time.time()
                if method == "GET":
                    resp = requests.get(url, headers=hdrs, params=params, timeout=10)
                else:
                    resp = requests.post(url, headers=hdrs, json=json_body, timeout=10)

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("rt_cd") == "0":
                        return data
                    else:
                        msg = data.get("msg1", "Unknown error")
                        logger.error(f"KIS API error: {msg}")
                        return None

                logger.warning(f"KIS HTTP {resp.status_code} (attempt {attempt}/{max_attempts})")

            except requests.RequestException as e:
                logger.warning(f"KIS request error (attempt {attempt}/{max_attempts}): {e}")

            if attempt < max_attempts:
                time.sleep(RETRY_DELAY * attempt)

        logger.error(f"KIS request failed after {max_attempts} attempt(s)")
        return None

    def get_us_price(self, symbol: str, exchange: str = "NASD") -> Optional[dict]:
        """
        Get current US stock price.

        Args:
            symbol: Ticker symbol (e.g., "TQQQ").
            exchange: Exchange code (NAS=Nasdaq, NYS=NYSE, AMS=AMEX).

        Returns:
            Price data dict or None.
        """
        url = f"{self.base_url}/uapi/overseas-price/v1/quotations/price"
        headers = {"tr_id": "HHDFS00000300"}
        # Price API uses 3-char exchange code
        excd = _EXCHANGE_MAP_4TO3.get(exchange, exchange)
        params = {"AUTH": "", "EXCD": excd, "SYMB": symbol}

        data = self._request("GET", url, headers=headers, params=params)
        if data and "output" in data:
            output = data["output"]
            try:
                return {
                    "price": float(output.get("last") or 0),
                    "open": float(output.get("open") or 0),
                    "high": float(output.get("high") or 0),
                    "low": float(output.get("low") or 0),
                    "volume": int(output.get("tvol") or 0),
                }
            except (ValueError, TypeError) as e:
                logger.error(f"KIS price parse error: {e}")
                return None
        return None

    def get_us_filled_price(self, order_no: str, symbol: str,
                             exchange: str = "NASD") -> Optional[float]:
        """
        Query fill price of a completed order.

        Uses the overseas order execution inquiry API (체결내역조회).
        Waits up to 10 seconds for the fill to appear.

        Args:
            order_no: Order number from the order response.
            symbol: Ticker symbol.
            exchange: Exchange code.

        Returns:
            Fill price as float, or None if not found.
        """
        url = f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-ccnl"
        headers = {"tr_id": "TTTS3035R"}
        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.product_code,
            "PDNO": symbol,
            "ORD_STRT_DT": "",  # Today
            "ORD_END_DT": "",
            "SLL_BUY_DVSN": "00",  # All
            "CCLD_NCCS_DVSN": "01",  # Filled only
            "OVRS_EXCG_CD": exchange,
            "SORT_SQN": "DS",  # Latest first
            "ORD_GNO_BRNO": "",
            "ODNO": order_no,
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }

        # Poll up to 3 times (order fill may take a moment)
        for attempt in range(3):
            if attempt > 0:
                time.sleep(2)
            data = self._request("GET", url, headers=headers, params=params)
            if data and "output" in data:
                for item in data["output"]:
                    if item.get("odno") == order_no or item.get("ODNO") == order_no:
                        try:
                            fill_price = float(item.get("ft_ccld_unpr")
                                               or item.get("CCLD_PRIC")
                                               or item.get("avg_prvs") or 0)
                            if fill_price > 0:
                                logger.info(f"Fill price for #{order_no}: ${fill_price:.2f}")
                                return fill_price
                        except (ValueError, TypeError):
                            pass
                # Do NOT fall back to first item — could be a different order

        logger.warning(f"Fill price not found for order #{order_no}")
        return None

    def get_us_balance(self, symbol: str = "") -> Optional[dict]:
        """
        Get US stock account balance.

        Args:
            symbol: Ticker for context (defaults to empty for general query).

        Returns:
            Balance dict with available cash and holdings, or None.
        """
        url = f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-psamount"
        headers = {"tr_id": "TTTS3007R"}
        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.product_code,
            "OVRS_EXCG_CD": "NASD",
            "OVRS_ORD_UNPR": "0",
            "ITEM_CD": symbol or "",
        }

        data = self._request("GET", url, headers=headers, params=params)
        if data and "output" in data:
            output = data["output"]
            try:
                return {
                    "available_cash": float(output.get("ovrs_ord_psbl_amt") or 0),
                    "total_value": float(output.get("frcr_pchs_amt1") or 0),
                }
            except (ValueError, TypeError) as e:
                logger.error(f"KIS balance parse error: {e}")
                return None
        return None
