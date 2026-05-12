"""Probe KIS overseas 5-min chart pagination depth.

KEYB 파라미터로 과거 방향 페이지네이션을 반복하며, 빈 응답이 오는
시점까지의 가장 오래된 bar 일자를 기록한다. 매 페이지마다 호출 시간·
받은 bar 수·oldest date를 출력해 한계를 시각적으로 확인할 수 있게 한다.
"""

import os
import sys
import time

# Make src.* importable when run from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.api.kis_auth import KISAuth
from src.api.kis_client import KISClient
from src.utils.config import load_env


SYMBOL = os.getenv("PROBE_SYMBOL", "TQQQ")
EXCD = os.getenv("PROBE_EXCD", "NAS")
NMIN = int(os.getenv("PROBE_NMIN", "5"))
NREC = int(os.getenv("PROBE_NREC", "120"))
MAX_PAGES = int(os.getenv("PROBE_MAX_PAGES", "400"))
SLEEP = float(os.getenv("PROBE_SLEEP", "0.4"))


def _fetch_page(client: KISClient, keyb: str) -> list:
    """Single raw call so we control KEYB ourselves."""
    url = f"{client.base_url}/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice"
    headers = {"tr_id": "HHDFS76950200"}
    params = {
        "AUTH": "",
        "EXCD": EXCD,
        "SYMB": SYMBOL,
        "NMIN": str(NMIN),
        "PINC": "1",
        "NEXT": "",
        "NREC": str(NREC),
        "FILL": "",
        "KEYB": keyb,
    }
    data = client._request("GET", url, headers=headers, params=params)
    if not data:
        return []
    bars_raw = data.get("output2", data.get("output", []))
    if not isinstance(bars_raw, list):
        return []
    out = []
    for it in bars_raw:
        try:
            close_val = float(it.get("last") or it.get("clos") or 0)
            if close_val <= 0:
                continue
            out.append({
                "date": it.get("xymd", it.get("tymd", "")),
                "time": it.get("xhms", it.get("khms", "")),
                "close": close_val,
            })
        except (ValueError, TypeError):
            continue
    # KIS returns newest-first. Keep that ordering for KEYB derivation.
    return out


def main() -> int:
    env = load_env()
    if not env["kis_app_key"] or not env["kis_app_secret"]:
        print("ERROR: KIS_APP_KEY / KIS_APP_SECRET not set in .env", file=sys.stderr)
        return 2

    base_url = env["kis_base_url"] or ("https://openapi.koreainvestment.com:9443"
                                       if env["trading_mode"] == "live"
                                       else "https://openapivts.koreainvestment.com:29443")
    auth = KISAuth(env["kis_app_key"], env["kis_app_secret"], base_url)
    if not auth.token:
        print("ERROR: KIS token not acquired (backoff or bad credentials)", file=sys.stderr)
        return 3

    client = KISClient(auth, env["kis_account_no"], env["kis_account_product"])

    print(f"Probe: SYMBOL={SYMBOL} EXCD={EXCD} NMIN={NMIN} NREC={NREC}")
    print(f"Base URL: {base_url}")
    print(f"Trading mode: {env['trading_mode']}")
    print("-" * 70)

    keyb = ""
    seen_oldest = None
    pages = 0
    total_bars = 0
    duplicate_streak = 0
    t_start = time.time()

    while pages < MAX_PAGES:
        pages += 1
        t0 = time.time()
        bars = _fetch_page(client, keyb)
        dt = time.time() - t0

        if not bars:
            print(f"[page {pages:3d}] EMPTY response after {dt:.2f}s — stop")
            break

        # KIS returns newest-first; oldest bar in this page is the LAST item
        oldest = bars[-1]
        newest = bars[0]
        oldest_key = f"{oldest['date']}{oldest['time']}"

        total_bars += len(bars)
        print(
            f"[page {pages:3d}] {len(bars):3d} bars  "
            f"newest={newest['date']} {newest['time']}  "
            f"oldest={oldest['date']} {oldest['time']}  "
            f"({dt:.2f}s, total={total_bars})"
        )

        # Stop conditions
        if seen_oldest == oldest_key:
            duplicate_streak += 1
            if duplicate_streak >= 2:
                print(f"[page {pages}] KEYB no longer advances (oldest unchanged) — stop")
                break
        else:
            duplicate_streak = 0
            seen_oldest = oldest_key

        # KEYB for next page = oldest bar's full timestamp
        keyb = oldest_key
        time.sleep(SLEEP)

    elapsed = time.time() - t_start
    print("-" * 70)
    print(f"Pages fetched     : {pages}")
    print(f"Total bars        : {total_bars}")
    print(f"Oldest reached    : {seen_oldest}")
    print(f"Elapsed           : {elapsed:.1f}s")

    # Estimate calendar coverage: 78 bars/day for 5-min regular session
    bars_per_day = (390 // NMIN) if NMIN <= 60 else 1
    if total_bars and bars_per_day:
        approx_days = total_bars / bars_per_day
        print(f"Approx coverage   : ~{approx_days:.1f} trading days "
              f"(={approx_days/21:.1f} months / {approx_days/252:.2f} years)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
