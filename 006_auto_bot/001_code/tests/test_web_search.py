"""Tests for the agy-primary / claude-fallback web search dispatcher.

Covers:
  - shared.agy_search.agy_websearch  (single agy CLI call + parsing + errors)
  - shared.web_search.web_search      (agy model cascade -> claude fallback)

All subprocess / backend calls are mocked; no live agy/claude invocation.
"""

import subprocess
from unittest import mock

import pytest

from shared.agy_search import agy_websearch, AgySearchError
from shared import web_search as ws
from shared.claude_search import ClaudeSearchResponse


def _fake_run(stdout, returncode=0, stderr=""):
    m = mock.Mock()
    m.stdout = stdout
    m.stderr = stderr
    m.returncode = returncode
    return m


SAMPLE = (
    "오늘 시장 요약입니다.\n\n"
    "Sources:\n"
    "- [BLS](https://www.bls.gov/cpi/)\n"
    "- [Fed](https://www.federalreserve.gov)\n"
)


# --------------------------- agy_websearch ---------------------------

def test_agy_websearch_success_parses_text_and_sources():
    with mock.patch("shared.agy_search.subprocess.run", return_value=_fake_run(SAMPLE)):
        resp = agy_websearch("질문", model="Gemini 3.5 Flash (Medium)", timeout=300)
    assert isinstance(resp, ClaudeSearchResponse)
    assert "오늘 시장 요약" in resp.text
    assert "https://www.bls.gov/cpi/" in resp.sources
    assert "https://www.federalreserve.gov" in resp.sources
    assert resp.model_used == "agy:Gemini 3.5 Flash (Medium)"


def test_agy_websearch_builds_expected_argv():
    captured = {}

    def _capture(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _fake_run(SAMPLE)

    with mock.patch("shared.agy_search.subprocess.run", side_effect=_capture):
        agy_websearch("내 프롬프트", model="Gemini 3.1 Pro (High)", timeout=123)

    cmd = captured["cmd"]
    import os as _os
    assert _os.path.basename(cmd[0]) == "agy"     # bare "agy" or a resolved path
    assert "-p" in cmd
    assert "내 프롬프트" in cmd                       # prompt passed via argv (no shell)
    assert "--model" in cmd
    assert "Gemini 3.1 Pro (High)" in cmd
    assert "--dangerously-skip-permissions" in cmd
    assert captured["kwargs"].get("timeout") == 123
    # agy `-p` blocks on an inherited stdin pipe (e.g. a bot daemon) and hangs;
    # it must read /dev/null so it gets immediate EOF and proceeds.
    assert captured["kwargs"].get("stdin") == subprocess.DEVNULL


def test_agy_websearch_raises_on_nonzero_exit():
    with mock.patch("shared.agy_search.subprocess.run",
                    return_value=_fake_run("", returncode=1, stderr="boom")):
        with pytest.raises(AgySearchError):
            agy_websearch("q", model="Gemini 3.5 Flash (Low)", timeout=10)


def test_agy_websearch_raises_on_empty_stdout():
    with mock.patch("shared.agy_search.subprocess.run", return_value=_fake_run("   ")):
        with pytest.raises(AgySearchError):
            agy_websearch("q", model="Gemini 3.5 Flash (Low)", timeout=10)


def test_agy_websearch_raises_on_timeout():
    with mock.patch("shared.agy_search.subprocess.run",
                    side_effect=subprocess.TimeoutExpired(cmd="agy", timeout=10)):
        with pytest.raises(AgySearchError):
            agy_websearch("q", model="Gemini 3.5 Flash (Low)", timeout=10)


def test_agy_websearch_raises_on_missing_binary():
    # agy not installed / not on PATH must degrade to AgySearchError so the
    # dispatcher can fall back to Claude instead of crashing the bot.
    with mock.patch("shared.agy_search.subprocess.run",
                    side_effect=FileNotFoundError("no such file: agy")):
        with pytest.raises(AgySearchError):
            agy_websearch("q", model="Gemini 3.5 Flash (Low)", timeout=10)


# ----------------------------- web_search -----------------------------

def _resp(text, model):
    return ClaudeSearchResponse(text=text, sources=[], model_used=model, elapsed_seconds=1.0)


def test_default_cascade_order_is_pro_high_flash_high_flash_medium():
    assert ws.DEFAULT_AGY_MODELS == [
        "Gemini 3.1 Pro (High)",
        "Gemini 3.5 Flash (High)",
        "Gemini 3.5 Flash (Medium)",
    ]


def test_web_search_first_model_succeeds_no_fallback():
    agy = mock.Mock(return_value=_resp("ok", "agy:Gemini 3.1 Pro (High)"))
    claude = mock.Mock()
    with mock.patch("shared.web_search.agy_websearch", agy), \
         mock.patch("shared.web_search.claude_websearch", claude):
        resp = ws.web_search("q", model="sonnet", fallback_model="haiku", timeout=900)
    assert resp.model_used == "agy:Gemini 3.1 Pro (High)"
    assert agy.call_count == 1
    assert agy.call_args.kwargs["model"] == "Gemini 3.1 Pro (High)"
    claude.assert_not_called()


def test_web_search_cascades_first_two_fail_then_third_succeeds():
    def _side(prompt, *, model, timeout):
        if model in ("Gemini 3.1 Pro (High)", "Gemini 3.5 Flash (High)"):
            raise AgySearchError(f"{model} down")
        return _resp("ok3", f"agy:{model}")

    agy = mock.Mock(side_effect=_side)
    claude = mock.Mock()
    with mock.patch("shared.web_search.agy_websearch", agy), \
         mock.patch("shared.web_search.claude_websearch", claude):
        resp = ws.web_search("q", model="sonnet", fallback_model="haiku", timeout=900)
    tried = [c.kwargs["model"] for c in agy.call_args_list]
    assert tried == [
        "Gemini 3.1 Pro (High)",
        "Gemini 3.5 Flash (High)",
        "Gemini 3.5 Flash (Medium)",
    ]
    assert resp.model_used == "agy:Gemini 3.5 Flash (Medium)"
    claude.assert_not_called()


def test_web_search_falls_back_to_claude_when_all_agy_fail():
    agy = mock.Mock(side_effect=AgySearchError("all down"))
    claude = mock.Mock(return_value=_resp("from claude", "sonnet"))
    with mock.patch("shared.web_search.agy_websearch", agy), \
         mock.patch("shared.web_search.claude_websearch", claude):
        resp = ws.web_search("q", model="sonnet", fallback_model="haiku", timeout=600)
    assert agy.call_count == 3
    claude.assert_called_once()
    assert claude.call_args.kwargs["model"] == "sonnet"
    assert claude.call_args.kwargs["fallback_model"] == "haiku"
    assert claude.call_args.kwargs["timeout"] == 600
    assert resp.model_used == "sonnet"


def test_web_search_uses_agy_timeout_not_caller_timeout_for_agy():
    captured = {}

    def _side(prompt, *, model, timeout):
        captured.setdefault("agy_timeouts", []).append(timeout)
        raise AgySearchError("down")

    agy = mock.Mock(side_effect=_side)
    claude = mock.Mock(return_value=_resp("c", "sonnet"))
    with mock.patch("shared.web_search.agy_websearch", agy), \
         mock.patch("shared.web_search.claude_websearch", claude):
        ws.web_search("q", model="sonnet", fallback_model="haiku", timeout=900)
    # agy stages use the bounded AGY timeout, not the caller's long 900s
    assert all(t == ws.AGY_SEARCH_TIMEOUT for t in captured["agy_timeouts"])
    # claude fallback keeps the caller's long timeout
    assert claude.call_args.kwargs["timeout"] == 900
