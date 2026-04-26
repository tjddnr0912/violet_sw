#!/usr/bin/env python3
"""
Test script for research_orchestrator module.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '001_code'))

from shared.research_orchestrator import ResearchResult, run_research


def test_research_result_fields():
    r = ResearchResult(
        content="body",
        title="t",
        labels=["a"],
        sources=[{"title": "s", "url": "https://x"}],
        rounds_completed=1,
        contradictions_noted=[],
    )
    assert r.content == "body"
    assert r.rounds_completed == 1
    assert r.contradictions_noted == []

    # default_factory creates an independent list per instance
    r2 = ResearchResult(content="x", title="y", labels=[], sources=[], rounds_completed=0)
    assert r2.contradictions_noted == []
    assert r2.contradictions_noted is not r.contradictions_noted


def test_run_research_signature():
    # Should accept question, max_rounds, progress_callback
    import inspect
    sig = inspect.signature(run_research)
    params = list(sig.parameters.keys())
    assert params[0] == "question"
    assert "max_rounds" in params
    assert "progress_callback" in params


def test_gemini_round_returns_stdout_on_success():
    from shared import research_orchestrator as ro

    class FakeCompleted:
        returncode = 0
        stdout = "round 1 output"
        stderr = ""

    captured = {}
    def fake_run(cmd, capture_output, text, timeout):
        captured["cmd"] = cmd
        captured["timeout"] = timeout
        return FakeCompleted()

    original = ro.subprocess.run
    ro.subprocess.run = fake_run
    try:
        text = ro._run_gemini_round("hello world prompt", timeout=42)
    finally:
        ro.subprocess.run = original

    assert text == "round 1 output"
    assert captured["cmd"][0] == "gemini"
    assert captured["timeout"] == 42


def test_gemini_round_raises_on_failure():
    from shared import research_orchestrator as ro

    class FakeCompleted:
        returncode = 1
        stdout = ""
        stderr = "429 quota"

    original = ro.subprocess.run
    ro.subprocess.run = lambda *a, **kw: FakeCompleted()
    try:
        try:
            ro._run_gemini_round("p", timeout=10)
            assert False, "should have raised"
        except ro.GeminiRoundError as e:
            assert "429" in str(e)
    finally:
        ro.subprocess.run = original


if __name__ == "__main__":
    test_research_result_fields()
    test_run_research_signature()
    test_gemini_round_returns_stdout_on_success()
    test_gemini_round_raises_on_failure()
    print("OK")
