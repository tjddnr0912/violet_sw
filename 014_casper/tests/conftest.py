"""Shared test fixtures for Casper Trading Bot tests."""

import logging
import os
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def _isolate_trades_and_state(tmp_path, monkeypatch):
    """Redirect every filesystem side-effect tests can produce into tmp_path.

    Four things must be isolated from the production environment:
      1. ``position_state.json`` — written by ``CasperBot`` on crash-recovery
         save paths.
      2. ``trades_YYYY.json`` — written by ``save_trade``. Tests for bot
         states and strategy reviews exercise the Bot lifecycle which may
         invoke ``save_trade`` indirectly; an opt-in fixture is too easy to
         forget and silently contaminates the live trade ledger.
      3. **casper logger** — ``setup_logger`` attaches a ``FileHandler`` to
         ``logs/app/casper_YYYY-MM-DD.log``. Without this fixture, every
         test-triggered log line (including fake "HTTP 500 to openapivts"
         entries from mocked paper-mode Bot inits) is appended to the live
         operator log, polluting real incident forensics.
      4. **network** — ``requests.get/post`` calls from within tests must
         never hit real KIS endpoints. Mock-env fixtures sometimes route
         through ``get_kis_urls('paper')`` which otherwise reaches out to
         ``openapivts`` and burns rate-limit budget while returning 403.

    Making this autouse guarantees no test run can pollute live data.
    Tests that want explicit tmp access can still use ``tmp_trades_dir``.
    """
    # (1) trades dir
    monkeypatch.setattr("src.data.trade_store.TRADES_DIR", str(tmp_path))

    # (2) position_state.json
    try:
        from src.bot import CasperBot
        _real_init = CasperBot.__init__
        fake_state = str(tmp_path / "position_state.json")

        def patched_init(self, *args, **kwargs):
            _real_init(self, *args, **kwargs)
            self._position_state_file = fake_state

        monkeypatch.setattr(CasperBot, "__init__", patched_init)
    except ImportError:
        pass

    # (3) Strip any FileHandler from the casper logger so tests cannot
    #     append to prod log files. Re-attach a NullHandler so the logger
    #     still "works" during tests without producing any output.
    casper_logger = logging.getLogger("casper")
    saved_handlers = list(casper_logger.handlers)
    casper_logger.handlers = [logging.NullHandler()]

    # (4) Block accidental outbound network calls. Tests that need HTTP
    #     should patch ``requests.get``/``requests.post`` explicitly; this
    #     net is a last-ditch guard against forgotten mocks.
    def _block_network(*args, **kwargs):
        target = args[0] if args else kwargs.get("url", "?")
        raise RuntimeError(
            f"Test attempted real HTTP call to {target}. "
            f"Patch requests.get/post in the test instead."
        )
    monkeypatch.setattr("requests.get", _block_network)
    monkeypatch.setattr("requests.post", _block_network)

    # (4b) ``KISClient.warm_up`` is invoked inside ``Bot._init_kis`` and
    #      makes real HTTP calls on startup. Tests that construct a Bot
    #      (via ``_make_bot`` helpers or direct instantiation) should not
    #      pay that cost. Force it to a no-op that reports success so the
    #      init path completes without touching the network. The original
    #      is stashed on the class so ``TestWarmUp`` can restore it.
    try:
        from src.api.kis_client import KISClient
        if not hasattr(KISClient, "_original_warm_up"):
            KISClient._original_warm_up = KISClient.warm_up
        monkeypatch.setattr(KISClient, "warm_up", lambda *a, **kw: True)
    except ImportError:
        pass

    yield tmp_path

    # Restore logger handlers after the test, so interactive sessions
    # (e.g. the skill script poking around) keep a working logger.
    casper_logger.handlers = saved_handlers


@pytest.fixture
def tmp_trades_dir(tmp_path, monkeypatch):
    """Explicit handle to the isolated TRADES_DIR (for tests that assert on files)."""
    monkeypatch.setattr("src.data.trade_store.TRADES_DIR", str(tmp_path))
    yield tmp_path


@pytest.fixture
def mock_env():
    """Standard mock environment for bot tests."""
    return {
        "kis_app_key": "", "kis_app_secret": "", "kis_account_no": "",
        "kis_account_product": "01", "kis_base_url": "",
        "telegram_bot_token": "", "telegram_chat_id": "",
        "trading_mode": "paper", "test_mode": False,
        "log_level": "WARNING", "timezone": "US/Eastern",
    }
