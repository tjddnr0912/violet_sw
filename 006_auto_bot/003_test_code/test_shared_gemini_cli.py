#!/usr/bin/env python3
"""Tests for shared.gemini_cli helper functions.

History note: the `_use_cli_fallback` sentinel and `is_cli_mode_active()`
helper used to drive runtime branching when API quota was exhausted and the
code fell back to the `gemini -p` CLI binary. The CLI fallback path was
removed in May 2026 (ahead of Google's June 2026 CLI shutdown), and quota
handling is now done in-process via a model fallback chain inside
`call_gemini_with_fallback`. `is_cli_mode_active()` is kept as a no-op
for import compatibility — these tests pin that contract."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '001_code'))

from shared.gemini_cli import is_cli_mode_active


class _FakeFlagHolder:
    def __init__(self, flag: bool):
        self._use_cli_fallback = flag


def test_is_cli_mode_active_is_permanently_false_after_cli_removal():
    """Even when an instance still carries `_use_cli_fallback=True` (e.g. from
    legacy test fixtures), is_cli_mode_active must return False because the
    CLI fallback path no longer exists. This pins the post-migration contract."""
    a = _FakeFlagHolder(False)
    b = _FakeFlagHolder(True)
    assert is_cli_mode_active(a, b) is False


def test_is_cli_mode_active_false_when_all_normal():
    a = _FakeFlagHolder(False)
    b = _FakeFlagHolder(False)
    assert is_cli_mode_active(a, b) is False


def test_is_cli_mode_active_handles_missing_attribute():
    class NoAttr:
        pass
    assert is_cli_mode_active(NoAttr()) is False


def test_is_cli_mode_active_empty_args():
    assert is_cli_mode_active() is False
