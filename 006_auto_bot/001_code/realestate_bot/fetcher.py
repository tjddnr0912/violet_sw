"""claude -p + kr-realestate MCP 운반책: (region, ym) -> raw items[]."""
import json
import re
import subprocess
import time
import logging

from realestate_bot import config

logger = logging.getLogger(__name__)

CLAUDE_TIMEOUT = 300
RETRY_DELAY = 15
REQUIRED_FIELDS = ("apt_name", "area_sqm", "floor", "price_10k", "trade_date")
_SENTINEL = re.compile(r"<<<JSON>>>\s*(.*?)\s*<<<END>>>", re.DOTALL)


def _build_prompt(region_code: str, year_month: str) -> str:
    return (
        "You have access to the kr-realestate MCP server tools. "
        f"Call the get_apartment_trades tool exactly once with arguments: "
        f"region_code={region_code}, year_month={year_month}, num_of_rows={config.NUM_OF_ROWS}. "
        "Then output ONLY the raw JSON object the tool returned, verbatim, "
        "between a line containing <<<JSON>>> and a line containing <<<END>>>. "
        "Do not summarize, reformat, compute, or add commentary."
    )


def _invoke_claude(prompt: str) -> str:
    # 함정: --mcp-config 값 뒤에 반드시 플래그를 두고 stdin 마커 '-'는 맨 끝.
    cmd = ["claude", "-p", "--mcp-config", config.MCP_CONFIG_PATH,
           "--dangerously-skip-permissions", "-"]
    result = subprocess.run(cmd, input=prompt, capture_output=True,
                            text=True, timeout=CLAUDE_TIMEOUT)
    if result.returncode != 0:
        raise RuntimeError(f"claude -p failed: {(result.stderr or '')[:300]}")
    return result.stdout or ""


def extract_records(payload: dict, region_code: str) -> list:
    """get_apartment_trades 페이로드 → 검증된 레코드 리스트(region_code 주입).
    claude-p 운반책(_parse)과 직접 MCP 클라이언트(mcp_client)가 공유한다."""
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("items missing")
    total = payload.get("total_count")
    if isinstance(total, int) and total > len(items):
        logger.warning("incomplete: %s items < total_count %s (region %s)",
                       len(items), total, region_code)
    out = []
    for it in items:
        for f in REQUIRED_FIELDS:
            if f not in it:
                raise ValueError(f"missing field {f}")
        rec = dict(it)
        rec["region_code"] = region_code
        out.append(rec)
    return out


def _parse(output: str, region_code: str) -> list:
    m = _SENTINEL.search(output)
    if not m:
        raise ValueError("sentinel not found")
    return extract_records(json.loads(m.group(1)), region_code)


def fetch_region(region_code: str, year_month: str, max_retries: int = 3) -> list:
    prompt = _build_prompt(region_code, year_month)
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            output = _invoke_claude(prompt)
            return _parse(output, region_code)
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning("fetch %s %s attempt %s/%s failed: %s",
                           region_code, year_month, attempt, max_retries, e)
            if attempt < max_retries:
                time.sleep(RETRY_DELAY)
    raise RuntimeError(f"fetch_region failed {region_code} {year_month}: {last_err}")
