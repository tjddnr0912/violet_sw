"""Shared pytest fixtures.

Critical safety fixture: `_isolate_state_files` redirects every persisted
bot state file (trend / gem / portfolio) to a per-test temp directory so the
test suite can NEVER clobber the live `data/*.json` of a running deployment.

Why a method wrapper and not a simple monkeypatch of the module constant:
each State class binds its file path as a default argument
(`def save(self, path=TREND_STATE_FILE)`), which Python evaluates once at
definition time. Reassigning the module constant afterwards does NOT change
that already-bound default, so we wrap save/load to force the temp path.
"""
import pytest


@pytest.fixture(autouse=True)
def _isolate_state_files(tmp_path, monkeypatch):
    from src.core import trend as _trend
    from src.core import gem as _gem
    from src.core import portfolio as _pf

    specs = [
        (_trend.TrendState, "trend_state.json"),
        (_gem.GemState, "gem_state.json"),
        (_pf.PortfolioState, "portfolio_state.json"),
    ]
    for cls, fname in specs:
        p = str(tmp_path / fname)
        orig_save = cls.save
        orig_load = cls.load.__func__  # unwrap classmethod

        def make_save(orig, path):
            def _save(self, _path=None):
                return orig(self, path)
            return _save

        def make_load(orig, path):
            def _load(c, _path=None):
                return orig(c, path)
            return classmethod(_load)

        monkeypatch.setattr(cls, "save", make_save(orig_save, p))
        monkeypatch.setattr(cls, "load", make_load(orig_load, p))
    yield
