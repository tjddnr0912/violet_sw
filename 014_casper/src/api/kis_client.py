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


class KISClient:
    """KIS REST API client."""

    def __init__(self, auth: KISAuth, account_no: str, product_code: str = "01"):
        self.auth = auth
        self.account_no = account_no
        self.product_code = product_code
        self.base_url = auth.base_url

    def _request(self, method: str, url: str, headers: dict = None,
                 params: dict = None, json_body: dict = None) -> Optional[dict]:
        """Make an API request with retry logic."""
        hdrs = {**self.auth.headers, **(headers or {})}

        for attempt in range(1, MAX_RETRIES + 1):
            try:
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

                logger.warning(f"KIS HTTP {resp.status_code} (attempt {attempt}/{MAX_RETRIES})")

            except requests.RequestException as e:
                logger.warning(f"KIS request error (attempt {attempt}/{MAX_RETRIES}): {e}")

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)

        logger.error(f"KIS request failed after {MAX_RETRIES} attempts")
        return None

    def get_us_price(self, symbol: str, exchange: str = "NAS") -> Optional[dict]:
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
        params = {"AUTH": "", "EXCD": exchange, "SYMB": symbol}

        data = self._request("GET", url, headers=headers, params=params)
        if data and "output" in data:
            output = data["output"]
            return {
                "price": float(output.get("last", 0)),
                "open": float(output.get("open", 0)),
                "high": float(output.get("high", 0)),
                "low": float(output.get("low", 0)),
                "volume": int(output.get("tvol", 0)),
            }
        return None

    def get_us_balance(self) -> Optional[dict]:
        """
        Get US stock account balance.

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
            "ITEM_CD": "TQQQ",
        }

        data = self._request("GET", url, headers=headers, params=params)
        if data and "output" in data:
            output = data["output"]
            return {
                "available_cash": float(output.get("ovrs_ord_psbl_amt", 0)),
                "total_value": float(output.get("frcr_pchs_amt1", 0)),
            }
        return None
