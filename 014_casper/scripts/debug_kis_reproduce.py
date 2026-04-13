#!/usr/bin/env python3
"""Reproduce the bot's KIS HTTP 500 against the same token/URL/params.

Runs as a standalone script from the same working directory that run_bot.py
would, using the same KIS client classes and the same token file. If this
reproduces HTTP 500 while a parallel `python3 -c "..."` inline invocation
succeeds, the difference is process-local (connection pool, import order,
module-global state) rather than server- or key-related.

Invocation:
    python3 scripts/debug_kis_reproduce.py
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import sys
import time

# Match run_bot.py's sys.path setup — project root first so `src.*` resolves.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

# Verbose urllib3 to see the raw TCP / TLS / HTTP frame-level behaviour.
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-5s %(name)-20s | %(message)s",
)
# requests itself is quiet; urllib3 has the useful wire traces.
logging.getLogger("urllib3.connectionpool").setLevel(logging.DEBUG)
logging.getLogger("urllib3.util.retry").setLevel(logging.DEBUG)


def load_env_from_file() -> dict:
    env = {}
    for line in pathlib.Path(ROOT, ".env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().split("#", 1)[0].strip().strip('"').strip("'")
    return env


def main() -> int:
    print("=" * 70)
    print("KIS 500 repro — standalone mirror of run_bot.py init path")
    print("=" * 70)
    env = load_env_from_file()

    # Same import order as bot.py (line 16-18).
    from src.api.kis_auth import KISAuth  # noqa: E402
    from src.api.kis_client import KISClient  # noqa: E402

    auth = KISAuth(env["KIS_APP_KEY"], env["KIS_APP_SECRET"], env["KIS_BASE_URL"])
    client = KISClient(auth, env["KIS_ACCOUNT_NO"])
    print(f"\n[init] auth.base_url = {auth.base_url}")
    print(f"[init] token prefix   = {auth.token[:30]}...")

    # Now run exactly what warm_up would, one call at a time, printing
    # the HTTP status of every single attempt.
    url = f"{env['KIS_BASE_URL']}/uapi/overseas-price/v1/quotations/price"
    for attempt in range(1, 6):
        print(f"\n[attempt {attempt}] GET {url.split('/')[-1]}")
        t0 = time.time()
        data = client._request(
            "GET", url,
            headers={"tr_id": "HHDFS00000300"},
            params={"AUTH": "", "EXCD": "NAS", "SYMB": "QQQ"},
            retry=False,
        )
        dt = time.time() - t0
        verdict = "OK" if data is not None else "FAIL"
        print(f"[attempt {attempt}] → {verdict} in {dt:.2f}s")
        time.sleep(3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
