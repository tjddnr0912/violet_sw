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
    assert captured["cmd"] == ["gemini", "-p", "hello world prompt"]
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


def test_round1_prompt_includes_question_and_skill():
    from shared.research_orchestrator import _build_round1_prompt
    p = _build_round1_prompt("티스토리 API 종료 현황")
    assert "티스토리 API 종료 현황" in p
    # Skill content marker — telegram-qa SKILL.md contains this Korean phrase
    assert "싱크탱크" in p or "리서치" in p
    # Metadata trailer instruction
    assert "TITLE:" in p
    assert "LABELS:" in p
    assert "SOURCES:" in p


def test_evaluate_round_parses_pass_decision():
    from shared import research_orchestrator as ro

    fake_json = '''
    Some preamble.
    ```json
    {
      "verdict": "pass",
      "missing_dimensions": [],
      "next_query": null,
      "contradictions": ["A claims X, B claims Y"]
    }
    ```
    trailing noise.
    '''

    class FakeCompleted:
        returncode = 0
        stdout = fake_json
        stderr = ""

    original = ro.subprocess.run
    ro.subprocess.run = lambda *a, **kw: FakeCompleted()
    try:
        decision = ro._evaluate_round(
            question="q",
            accumulated_rounds=[("Round 1", "content...")],
        )
    finally:
        ro.subprocess.run = original

    assert decision["verdict"] == "pass"
    assert decision["missing_dimensions"] == []
    assert decision["contradictions"] == ["A claims X, B claims Y"]


def test_evaluate_round_parses_continue_with_query():
    from shared import research_orchestrator as ro

    fake_json = '''```json
{"verdict": "continue", "missing_dimensions": ["evidence"], "next_query": "Find primary source for X", "contradictions": []}
```'''

    class FakeCompleted:
        returncode = 0
        stdout = fake_json
        stderr = ""

    captured = {}

    def fake_run(cmd, capture_output, text, timeout):
        captured["cmd"] = cmd
        return FakeCompleted()

    original = ro.subprocess.run
    ro.subprocess.run = fake_run
    try:
        decision = ro._evaluate_round(question="q", accumulated_rounds=[("R1", "x")])
    finally:
        ro.subprocess.run = original

    assert decision["verdict"] == "continue"
    assert decision["next_query"] == "Find primary source for X"
    # cmd argv contract: ["claude", "-p", <prompt>]
    assert captured["cmd"][0] == "claude"
    assert captured["cmd"][1] == "-p"
    assert "5차원" in captured["cmd"][2]


def test_evaluate_round_returns_safe_default_on_nonzero_exit():
    from shared import research_orchestrator as ro

    class FakeCompleted:
        returncode = 1
        stdout = ""
        stderr = "auth error"

    original = ro.subprocess.run
    ro.subprocess.run = lambda *a, **kw: FakeCompleted()
    try:
        decision = ro._evaluate_round(question="q", accumulated_rounds=[("R1", "x")])
    finally:
        ro.subprocess.run = original

    assert decision["verdict"] == "pass"
    assert decision["missing_dimensions"] == []
    assert decision["next_query"] is None
    assert decision["contradictions"] == []


def test_extract_eval_json_no_match_returns_safe_default():
    from shared.research_orchestrator import _extract_eval_json
    decision = _extract_eval_json("Claude returned a casual paragraph with no JSON at all.")
    assert decision["verdict"] == "pass"
    assert decision["next_query"] is None


def test_extract_eval_json_invalid_json_returns_safe_default():
    from shared.research_orchestrator import _extract_eval_json
    bad = '''```json
{"verdict": "continue", "missing_dimensions": [unclosed
```'''
    decision = _extract_eval_json(bad)
    assert decision["verdict"] == "pass"
    assert decision["missing_dimensions"] == []


def test_extract_eval_json_bare_fallback_regex():
    from shared.research_orchestrator import _extract_eval_json
    # No fenced block at all — bare regex must catch it
    bare = 'Sure, here it is: {"verdict": "continue", "missing_dimensions": ["근거"], "next_query": "find primary", "contradictions": []} thanks!'
    decision = _extract_eval_json(bare)
    assert decision["verdict"] == "continue"
    assert decision["next_query"] == "find primary"


def test_round_n_prompt_includes_targeted_query():
    from shared.research_orchestrator import _build_round_n_prompt
    p = _build_round_n_prompt(
        original_question="티스토리 API 종료",
        targeted_query="공식 공지의 정확한 종료일을 찾아라",
        round_number=2,
    )
    assert "Round 2" in p or "라운드 2" in p
    assert "공식 공지의 정확한 종료일을 찾아라" in p
    assert "티스토리 API 종료" in p


def test_synthesize_returns_markdown_with_metadata():
    from shared import research_orchestrator as ro

    fake_md = """# 정리

본문 내용입니다.

TITLE: 티스토리 API 종료 정리
LABELS: 티스토리, API, 자동화
SOURCES: 공식 공지|https://notice.tistory.com/2664
"""
    class FakeCompleted:
        returncode = 0
        stdout = fake_md
        stderr = ""

    original = ro.subprocess.run
    ro.subprocess.run = lambda *a, **kw: FakeCompleted()
    try:
        md = ro._synthesize(
            question="q",
            accumulated_rounds=[("R1", "x")],
            contradictions=["사례 충돌 1"],
        )
    finally:
        ro.subprocess.run = original

    assert "TITLE:" in md
    assert "LABELS:" in md
    assert "SOURCES:" in md
    assert "본문 내용입니다." in md


if __name__ == "__main__":
    test_research_result_fields()
    test_run_research_signature()
    test_gemini_round_returns_stdout_on_success()
    test_gemini_round_raises_on_failure()
    test_round1_prompt_includes_question_and_skill()
    test_evaluate_round_parses_pass_decision()
    test_evaluate_round_parses_continue_with_query()
    test_evaluate_round_returns_safe_default_on_nonzero_exit()
    test_extract_eval_json_no_match_returns_safe_default()
    test_extract_eval_json_invalid_json_returns_safe_default()
    test_extract_eval_json_bare_fallback_regex()
    test_round_n_prompt_includes_targeted_query()
    test_synthesize_returns_markdown_with_metadata()
    print("OK")
