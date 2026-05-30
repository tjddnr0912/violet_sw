"""Shared test fixtures for Casper Trading Bot tests."""

import logging
import pytest


@pytest.fixture(autouse=True)
def _isolate_trades_and_state(tmp_path, monkeypatch):
    """Redirect every filesystem side-effect tests can produce into tmp_path.

    Five things must be isolated from the production environment:
      1. ``position_state.json`` — written by ``CasperBot`` on crash-recovery
         save paths.
      2. ``trades_YYYY.json`` — written by ``save_trade``. Tests for bot
         states and strategy reviews exercise the Bot lifecycle which may
         invoke ``save_trade`` indirectly; an opt-in fixture is too easy to
         forget and silently contaminates the live trade ledger.
      3. **casper logger** — ``setup_logger`` attaches a ``FileHandler`` to
         ``logs/app/casper_YYYY-MM-DD.log``. Without this fixture, every
         test-triggered log line is appended to the live operator log,
         polluting real incident forensics.
      4. **network** — ``requests.get/post`` calls from within tests must
         never hit real KIS endpoints.
      5. **bucket state files** (``trend_state.json`` / ``gem_state.json`` /
         ``portfolio_state.json``) — the State classes bind their file path
         as a default arg (evaluated at def-time), so reassigning the module
         constant does NOT change the already-bound default. We wrap
         save/load per class to force a per-test temp path; otherwise a live
         deployment's state (e.g. trend_state.json on a running bot) gets
         clobbered with fake test data — which can desync the monthly
         scheduler and leave a sleeve un-traded for a month.

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
            # NOTE: the bot's attribute is `position_state_file` (no leading
            # underscore). A prior version patched `_position_state_file`,
            # which created an unused attribute and left the real
            # data/position_state.json exposed — every test that saved a
            # position then wrote a phantom into the LIVE data dir, which a
            # later bot restart would read as a real open position.
            self.position_state_file = fake_state

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
    #      makes real HTTP calls on startup. Force it to a no-op so the init
    #      path completes without touching the network. The original is
    #      stashed on the class so ``TestWarmUp`` can restore it.
    try:
        from src.api.kis_client import KISClient
        if not hasattr(KISClient, "_original_warm_up"):
            KISClient._original_warm_up = KISClient.warm_up
        monkeypatch.setattr(KISClient, "warm_up", lambda *a, **kw: True)
    except ImportError:
        pass

    # (5) Bucket-state files. Each State class binds its path as a def-time
    #     default arg, so a plain monkeypatch of the module constant is
    #     ineffective. Wrap save/load to force the temp path.
    try:
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
    except (ImportError, AttributeError):
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
