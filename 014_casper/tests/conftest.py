"""Shared test fixtures for Casper Trading Bot tests."""

import os
import pytest
from unittest.mock import patch


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
