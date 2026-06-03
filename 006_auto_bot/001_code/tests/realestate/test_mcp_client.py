import json
import importlib

import pytest

mc = importlib.import_module("realestate_bot.mcp_client")


class _FakeStdin:
    def __init__(self):
        self.written = []

    def write(self, s):
        self.written.append(s)

    def flush(self):
        pass


class _FakeStdout:
    def __init__(self, lines):
        self._lines = list(lines)

    def readline(self):
        return self._lines.pop(0) if self._lines else ""


class _FakeProc:
    def __init__(self, lines):
        self.stdin = _FakeStdin()
        self.stdout = _FakeStdout(lines)
        self.killed = False

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True


def _config(tmp_path):
    p = tmp_path / "mcp.json"
    p.write_text(json.dumps({"mcpServers": {"kr-realestate": {
        "command": "dummy", "args": [], "env": {"DATA_GO_KR_API_KEY": "x"}}}}))
    return str(p)


def test_fetch_region_parses_and_injects_region(tmp_path, monkeypatch):
    payload = {"total_count": 1, "items": [
        {"apt_name": "A아파트", "dong": "동", "area_sqm": 84.9, "floor": 3,
         "price_10k": 100000, "trade_date": "2026-05-10",
         "build_year": 2015, "deal_type": "중개거래"}]}
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1,
                    "result": {"protocolVersion": "2024-11-05"}}) + "\n",
        "non-json log noise from server stdout\n",   # → skip 되어야
        json.dumps({"jsonrpc": "2.0", "id": 2, "result": {
            "content": [{"type": "text", "text": json.dumps(payload)}]}}) + "\n",
    ]
    monkeypatch.setattr(mc.subprocess, "Popen", lambda *a, **k: _FakeProc(lines))
    with mc.MCPClient(config_path=_config(tmp_path)) as c:
        recs = c.fetch_region("11110", "202505")
    assert len(recs) == 1
    assert recs[0]["apt_name"] == "A아파트"
    assert recs[0]["region_code"] == "11110"   # region_code 주입 확인


def test_handshake_sends_initialize_then_tool_call(tmp_path, monkeypatch):
    payload = {"total_count": 0, "items": []}
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
        json.dumps({"jsonrpc": "2.0", "id": 2, "result": {
            "content": [{"type": "text", "text": json.dumps(payload)}]}}) + "\n",
    ]
    proc_holder = {}

    def fake_popen(*a, **k):
        proc_holder["p"] = _FakeProc(lines)
        return proc_holder["p"]

    monkeypatch.setattr(mc.subprocess, "Popen", fake_popen)
    with mc.MCPClient(config_path=_config(tmp_path)) as c:
        c.fetch_region("11110", "202505", num_of_rows=50)
    sent = [json.loads(x) for x in proc_holder["p"].stdin.written]
    methods = [m.get("method") for m in sent]
    assert methods == ["initialize", "notifications/initialized", "tools/call"]
    # tools/call 인자 검증
    call = sent[2]["params"]
    assert call["name"] == "get_apartment_trades"
    assert call["arguments"] == {"region_code": "11110", "year_month": "202505",
                                 "num_of_rows": 50}


def test_tool_error_raises(tmp_path, monkeypatch):
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
        json.dumps({"jsonrpc": "2.0", "id": 2,
                    "error": {"code": -1, "message": "boom"}}) + "\n",
    ]
    monkeypatch.setattr(mc.subprocess, "Popen", lambda *a, **k: _FakeProc(lines))
    with pytest.raises(RuntimeError):
        with mc.MCPClient(config_path=_config(tmp_path)) as c:
            c.fetch_region("11110", "202505")
