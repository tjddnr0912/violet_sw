#!/usr/bin/env python3
"""Tests for shared.gemini_cli helper functions."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '001_code'))

from shared.gemini_cli import is_cli_mode_active


class _FakeFlagHolder:
    def __init__(self, flag: bool):
        self._use_cli_fallback = flag


def test_is_cli_mode_active_true_when_any_instance_in_fallback():
    a = _FakeFlagHolder(False)
    b = _FakeFlagHolder(True)
    assert is_cli_mode_active(a, b) is True


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
