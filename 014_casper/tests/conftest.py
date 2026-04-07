"""Shared test fixtures for Casper Trading Bot tests."""

import os
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def _isolate_position_state(tmp_path, monkeypatch):
    """Prevent tests from writing position_state.json to production data dir."""
    fake_state = str(tmp_path / "position_state.json")
    original_init = None

    try:
        from src.bot import CasperBot
        original_init = CasperBot.__init__

        _real_init = original_init

        def patched_init(self, *args, **kwargs):
            _real_init(self, *args, **kwargs)
            self._position_state_file = fake_state

        monkeypatch.setattr(CasperBot, "__init__", patched_init)
    except ImportError:
        pass

    yield tmp_path


@pytest.fixture
def tmp_trades_dir(tmp_path):
    """Patch TRADES_DIR to use temp directory."""
    with patch("src.data.trade_store.TRADES_DIR", str(tmp_path)):
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
