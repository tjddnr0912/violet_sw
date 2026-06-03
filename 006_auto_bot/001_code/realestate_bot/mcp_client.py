"""백필 전용 직접 MCP stdio 클라이언트.

claude -p 운반책(fetcher.py)을 우회해 Python이 kr-realestate MCP 서버를
직접 spawn하고 JSON-RPC(stdio)로 호출한다. 레코드가 Claude 토큰을 전혀
거치지 않으므로 사용량 한도와 무관하며(대량 백필에 적합), 세션 1개로 다수의
(구, 월)을 연속 조회한다. 주간 라이브 런은 fetcher.fetch_region(claude-p) 유지.
"""
import json
import os
import subprocess
import logging

from realestate_bot import config, fetcher

logger = logging.getLogger(__name__)

_PROTOCOL = "2024-11-05"


class MCPClient:
    """.mcp.json에 정의된 MCP 서버를 직접 spawn하는 stdio JSON-RPC 클라이언트.

    컨텍스트 매니저로 사용한다:
        with MCPClient() as c:
            recs = c.fetch_region("11110", "202504")
    """

    def __init__(self, config_path: str = None, server_key: str = "kr-realestate"):
        self.config_path = config_path or config.MCP_CONFIG_PATH
        self.server_key = server_key
        self.proc = None
        self._id = 0

    def __enter__(self):
        with open(self.config_path, encoding="utf-8") as f:
            cfg = json.load(f)
        srv = cfg["mcpServers"][self.server_key]
        cmd = [srv["command"]] + srv.get("args", [])
        env = dict(os.environ)
        env.update(srv.get("env", {}) or {})
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, env=env, bufsize=1)
        self._handshake()
        logger.info("MCPClient connected (%s)", self.server_key)
        return self

    def __exit__(self, *exc):
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                self.proc.kill()
        return False

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _send(self, obj: dict):
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def _recv(self, expected_id: int, max_lines: int = 1000) -> dict:
        """expected_id와 일치하는 JSON-RPC 응답을 읽는다(로그 노이즈·알림은 skip)."""
        for _ in range(max_lines):
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("MCP server closed stream")
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001
                continue  # 서버가 stdout으로 흘린 로그 등 비-JSON은 무시
            if obj.get("id") == expected_id:
                return obj
        raise RuntimeError("MCP response not received")

    def _handshake(self):
        rid = self._next_id()
        self._send({"jsonrpc": "2.0", "id": rid, "method": "initialize", "params": {
            "protocolVersion": _PROTOCOL, "capabilities": {},
            "clientInfo": {"name": "realestate-bot", "version": "1.0"}}})
        resp = self._recv(rid)
        if "result" not in resp:
            raise RuntimeError(f"initialize failed: {resp}")
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call_tool(self, name: str, arguments: dict) -> dict:
        rid = self._next_id()
        self._send({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                    "params": {"name": name, "arguments": arguments}})
        resp = self._recv(rid)
        if "error" in resp:
            raise RuntimeError(f"tool error: {resp['error']}")
        content = resp["result"]["content"]
        return json.loads(content[0]["text"])

    def _fetch(self, tool: str, extract, region_code: str, year_month: str,
               num_of_rows: int = None) -> list:
        payload = self.call_tool(tool, {
            "region_code": region_code, "year_month": year_month,
            "num_of_rows": num_of_rows or config.NUM_OF_ROWS})
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(f"MCP API error {region_code} {year_month}: "
                               f"{payload.get('message') or payload.get('error')}")
        return extract(payload, region_code)

    def fetch_region(self, region_code: str, year_month: str,
                     num_of_rows: int = None) -> list:
        return self._fetch("get_apartment_trades", fetcher.extract_records,
                           region_code, year_month, num_of_rows)

    def fetch_rent(self, region_code: str, year_month: str,
                   num_of_rows: int = None) -> list:
        return self._fetch("get_apartment_rent", fetcher.extract_rent_records,
                           region_code, year_month, num_of_rows)
