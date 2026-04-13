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

    def warm_up(self, max_secs: int = 90, poll_interval: int = 10) -> bool:
        """Poll a cheap quote endpoint until KIS accepts it (cold-start guard).

        KIS returns HTTP 500 with an empty ``rt_cd:"1"`` body on the first
        API calls issued within ~15-60s of a fresh process + token handshake
        (observed on ``inquire-present-balance``, ``price`` equally). The
        fast internal 1/2/4s retry in ``_request`` exhausts long before the
        server warms, so ``_sync_capital`` — the first real caller — lands
        on a still-cold path and leaves ``self.capital`` at 0.0, which in
        turn disables position sizing for the whole day.

        This helper polls at a longer cadence (no internal retry, one shot
        per attempt) until a 200 comes back. Returns ``True`` on success,
        ``False`` on timeout; the caller can proceed either way since all
        other KIS calls have their own retry paths — but a successful warm
        up means the subsequent ``_sync_capital`` will almost certainly
        succeed.
        """
        url = f"{self.base_url}/uapi/overseas-price/v1/quotations/price"
        deadline = time.time() + max_secs
        attempt = 0
        t0 = time.time()
        while time.time() < deadline:
            attempt += 1
            data = self._request(
                "GET", url,
                headers={"tr_id": "HHDFS00000300"},
                params={"AUTH": "", "EXCD": "NAS", "SYMB": "QQQ"},
                retry=False,
            )
            if data is not None:
                logger.info(
                    f"KIS warm-up succeeded in {time.time() - t0:.0f}s "
                    f"(attempt {attempt})"
                )
                return True
            time.sleep(poll_interval)
        logger.warning(
            f"KIS warm-up timed out after {max_secs}s ({attempt} attempts); "
            f"proceeding with cold state (real calls will still retry)"
        )
        return False

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

                # Include endpoint + response body for diagnosis. KIS
                # frequently returns 4xx/5xx with a JSON body whose msg_cd/msg1
                # is the real cause (e.g. APBN0746 "상품이 없습니다"). Logging
                # only the status code or even just the body — without knowing
                # *which* endpoint/tr_id failed — still wastes debugging time
                # when multiple KIS calls happen in quick succession.
                endpoint = url.rsplit("/", 1)[-1]
                tr_id = hdrs.get("tr_id", "?")
                body_snip = resp.text[:300].replace("\n", " ")
                logger.warning(
                    f"KIS HTTP {resp.status_code} [{endpoint} tr_id={tr_id}] "
                    f"(attempt {attempt}/{max_attempts}): {body_snip}"
                )

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
                             exchange: str = "NASD",
                             max_attempts: int = 5) -> Optional[float]:
        """
        Query fill price of a completed order.

        Uses the overseas order execution inquiry API (체결내역조회).

        Args:
            order_no: Order number from the order response.
            symbol: Ticker symbol.
            exchange: Exchange code.
            max_attempts: Number of polling attempts (2s interval). Use 1 for retry calls.

        Returns:
            Fill price as float, or None if not found.
        """
        for attempt in range(max_attempts):
            if attempt > 0:
                time.sleep(2)
            item = self._query_execution(order_no, symbol, exchange)
            if item:
                try:
                    fill_price = float(item.get("ft_ccld_unpr3")
                                       or item.get("ft_ccld_unpr")
                                       or item.get("CCLD_PRIC") or 0)
                    if fill_price > 0:
                        logger.info(f"Fill price for #{order_no}: ${fill_price:.4f}")
                        return fill_price
                except (ValueError, TypeError):
                    pass

        if max_attempts > 1:
            logger.warning(f"Fill price not found for order #{order_no}")
        return None

    def get_us_today_executions(self, symbol: str,
                                 exchange: str = "NASD") -> list:
        """
        Query all of today's filled orders for a symbol.

        Returns list of dicts with: order_no, side (buy/sell), fill_price,
        fill_amount, order_qty, order_price.
        """
        data = self._query_executions_raw(symbol, exchange)
        if not data or "output" not in data:
            return []

        results = []
        for item in data["output"]:
            try:
                fill_qty = int(item.get("ft_ccld_qty") or 0)
                if fill_qty <= 0:
                    continue
                results.append({
                    "order_no": item.get("odno", ""),
                    "side": "buy" if item.get("sll_buy_dvsn_cd") == "02" else "sell",
                    "fill_price": float(item.get("ft_ccld_unpr3") or 0),
                    "fill_amount": float(item.get("ft_ccld_amt3") or 0),
                    "fill_qty": fill_qty,
                    "order_price": float(item.get("ft_ord_unpr3") or 0),
                    "status": item.get("prcs_stat_name", ""),
                })
            except (ValueError, TypeError):
                continue
        return results

    def _query_execution(self, order_no: str, symbol: str,
                          exchange: str = "NASD") -> Optional[dict]:
        """Query a single execution by order number (single attempt)."""
        data = self._query_executions_raw(symbol, exchange)
        if not data or "output" not in data:
            return None
        for item in data["output"]:
            if item.get("odno") == order_no:
                return item
        return None

    def _query_executions_raw(self, symbol: str,
                               exchange: str = "NASD") -> Optional[dict]:
        """Raw API call for today's executions."""
        url = f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-ccnl"
        headers = {"tr_id": "TTTS3035R"}
        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.product_code,
            "PDNO": "",
            "ORD_STRT_DT": "",
            "ORD_END_DT": "",
            "SLL_BUY_DVSN": "00",
            "CCLD_NCCS_DVSN": "01",
            "OVRS_EXCG_CD": exchange,
            "SORT_SQN": "DS",
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }
        return self._request("GET", url, headers=headers, params=params)

    def get_us_minute_chart(self, symbol: str, nmin: int = 5,
                             exchange: str = "NASD",
                             nrec: int = 120) -> Optional[list]:
        """
        Fetch intraday minute bars for US stock.

        Uses overseas minute chart API (해외주식분봉조회).

        Args:
            symbol: Ticker symbol (e.g., "TQQQ").
            nmin: Minute interval (1, 5, 10, 30, 60).
            exchange: Exchange code (4-char, auto-mapped to 3-char).
            nrec: Number of records to fetch (max 120).

        Returns:
            List of bar dicts [{date, time, open, high, low, close, volume}, ...]
            sorted ascending by time, or None on error.
        """
        url = f"{self.base_url}/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice"
        headers = {"tr_id": "HHDFS76950200"}
        excd = _EXCHANGE_MAP_4TO3.get(exchange, exchange)
        params = {
            "AUTH": "",
            "EXCD": excd,
            "SYMB": symbol,
            "NMIN": str(nmin),
            "PINC": "1",
            "NEXT": "",
            "NREC": str(nrec),
            "FILL": "",
            "KEYB": "",
        }

        data = self._request("GET", url, headers=headers, params=params)
        if not data:
            return None

        # Response uses output2 for bar array
        bars_raw = data.get("output2", data.get("output", []))
        if not bars_raw or not isinstance(bars_raw, list):
            logger.warning(f"KIS minute chart: no bars for {symbol}")
            return None

        bars = []
        for item in bars_raw:
            try:
                close_val = float(item.get("last") or item.get("clos") or 0)
                if close_val <= 0:
                    continue
                bars.append({
                    "date": item.get("xymd", item.get("tymd", "")),
                    "time": item.get("xhms", item.get("khms", "")),
                    "open": float(item.get("open") or 0),
                    "high": float(item.get("high") or 0),
                    "low": float(item.get("low") or 0),
                    "close": close_val,
                    "volume": int(item.get("evol") or item.get("tvol") or 0),
                })
            except (ValueError, TypeError):
                continue

        if not bars:
            return None

        # KIS returns newest first — reverse to ascending
        bars.reverse()
        logger.debug(f"KIS minute chart: {symbol} {len(bars)} bars ({nmin}min)")
        return bars

    def get_us_daily_chart(self, symbol: str, exchange: str = "NASD",
                            count: int = 60) -> Optional[list]:
        """
        Fetch daily OHLCV bars for US stock.

        Uses overseas daily price API (해외주식 기간별시세).

        Args:
            symbol: Ticker symbol.
            exchange: Exchange code.
            count: Number of days to fetch.

        Returns:
            List of bar dicts [{date, open, high, low, close, volume}, ...]
            sorted ascending by date, or None on error.
        """
        url = f"{self.base_url}/uapi/overseas-price/v1/quotations/dailyprice"
        headers = {"tr_id": "HHDFS76240000"}
        excd = _EXCHANGE_MAP_4TO3.get(exchange, exchange)
        params = {
            "AUTH": "",
            "EXCD": excd,
            "SYMB": symbol,
            "GUBN": "0",  # 0=일, 1=주, 2=월
            "BYMD": "",   # 기준일 (빈값=최근)
            "MODP": "1",  # 수정주가 반영
        }

        data = self._request("GET", url, headers=headers, params=params)
        if not data:
            return None

        bars_raw = data.get("output2", data.get("output", []))
        if not bars_raw or not isinstance(bars_raw, list):
            logger.warning(f"KIS daily chart: no bars for {symbol}")
            return None

        bars = []
        for item in bars_raw:
            try:
                close_val = float(item.get("clos") or item.get("last") or 0)
                if close_val <= 0:
                    continue
                bars.append({
                    "date": item.get("xymd", ""),
                    "open": float(item.get("open") or 0),
                    "high": float(item.get("high") or 0),
                    "low": float(item.get("low") or 0),
                    "close": close_val,
                    "volume": int(item.get("tvol") or 0),
                })
            except (ValueError, TypeError):
                continue

        if not bars:
            return None

        # KIS returns newest first — reverse to ascending
        bars.reverse()
        # Trim to requested count
        if len(bars) > count:
            bars = bars[-count:]
        logger.debug(f"KIS daily chart: {symbol} {len(bars)} bars")
        return bars

    def get_us_holdings(self, exchange: str = "NASD") -> Optional[list]:
        """
        Get current US stock holdings.

        Args:
            exchange: Exchange code.

        Returns:
            List of holding dicts [{symbol, qty, avg_price}, ...] or None.
        """
        url = f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-balance"
        headers = {"tr_id": "TTTS3012R"}
        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.product_code,
            "OVRS_EXCG_CD": exchange,
            "TR_CRCY_CD": "USD",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }

        data = self._request("GET", url, headers=headers, params=params)
        if not data:
            return None

        output = data.get("output1", data.get("output", []))
        if not isinstance(output, list):
            return None

        holdings = []
        for item in output:
            try:
                qty = int(item.get("ovrs_cblc_qty") or item.get("hldg_qty") or 0)
                if qty > 0:
                    holdings.append({
                        "symbol": item.get("ovrs_pdno", item.get("pdno", "")),
                        "qty": qty,
                        "avg_price": float(item.get("pchs_avg_pric") or 0),
                    })
            except (ValueError, TypeError):
                continue

        return holdings

    def get_us_balance(self, symbol: str = "", unit_price: float = 0.0) -> Optional[dict]:
        """
        Get US stock account balance (available cash in USD).

        KIS has two distinct APIs here and the right choice depends on intent:
          - inquire-present-balance (CTRP6504R): unconditional USD cash balance.
            No ITEM_CD needed. Use this for generic capital sync.
          - inquire-psamount (TTTS3007R): "how many shares can I buy of X at
            price P" — requires a concrete ITEM_CD and non-zero unit price.
            Passing ITEM_CD="" returns APBN0746 "상품이 없습니다" (sometimes
            surfaced as HTTP 500), which was the source of an outage where
            _sync_capital() looped forever.

        Args:
            symbol: Ticker for order-sizing context. If empty, a pure cash
                    balance query is used instead.
            unit_price: Price used when symbol is specified (required by KIS).

        Returns:
            Dict with ``available_cash`` (float, USD). Includes ``max_qty``
            when symbol/unit_price are provided. ``None`` on failure.
        """
        if symbol:
            if unit_price <= 0:
                logger.error("KIS balance: symbol given but unit_price missing")
                return None
            url = f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-psamount"
            headers = {"tr_id": "TTTS3007R"}
            params = {
                "CANO": self.account_no,
                "ACNT_PRDT_CD": self.product_code,
                "OVRS_EXCG_CD": "NASD",
                "OVRS_ORD_UNPR": f"{unit_price:.4f}",
                "ITEM_CD": symbol,
            }
            data = self._request("GET", url, headers=headers, params=params)
            if data and "output" in data:
                out = data["output"]
                try:
                    return {
                        "available_cash": float(out.get("ovrs_ord_psbl_amt") or 0),
                        "max_qty": int(out.get("max_ord_psbl_qty") or 0),
                    }
                except (ValueError, TypeError) as e:
                    logger.error(f"KIS balance parse error: {e}")
                    return None
            return None

        # No symbol → unconditional USD cash balance.
        url = f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-present-balance"
        headers = {"tr_id": "CTRP6504R"}
        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.product_code,
            "WCRC_FRCR_DVSN_CD": "02",   # 원화/외화 구분: 02 = 외화
            "NATN_CD": "840",            # 미국
            "TR_MKET_CD": "00",
            "INQR_DVSN_CD": "00",
        }
        data = self._request("GET", url, headers=headers, params=params)
        if not data or "output2" not in data:
            return None
        for row in data["output2"]:
            if row.get("crcy_cd") == "USD":
                try:
                    return {
                        "available_cash": float(row.get("frcr_drwg_psbl_amt_1") or 0),
                    }
                except (ValueError, TypeError) as e:
                    logger.error(f"KIS balance parse error: {e}")
                    return None
        return None
