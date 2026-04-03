"""Tests for trade_store module."""

import json
import os
import pytest
import tempfile
from unittest.mock import patch

from src.data.trade_store import load_trades, save_trade, get_cumulative_stats


@pytest.fixture
def tmp_trades_dir(tmp_path):
    """Patch TRADES_DIR to use temp directory."""
    with patch("src.data.trade_store.TRADES_DIR", str(tmp_path)):
        yield tmp_path


class TestLoadSave:
    def test_empty_load(self, tmp_trades_dir):
        trades = load_trades(2026)
        assert trades == []

    def test_save_and_load(self, tmp_trades_dir):
        trade = {"date": "2026-04-06", "symbol": "TQQQ", "result": "WIN", "net_pnl": 20.0}
        save_trade(trade, 2026)
        loaded = load_trades(2026)
        assert len(loaded) == 1
        assert loaded[0]["symbol"] == "TQQQ"

    def test_append_multiple(self, tmp_trades_dir):
        save_trade({"result": "WIN", "net_pnl": 10}, 2026)
        save_trade({"result": "LOSS", "net_pnl": -5}, 2026)
        save_trade({"result": "BE", "net_pnl": 0}, 2026)
        loaded = load_trades(2026)
        assert len(loaded) == 3

    def test_corrupt_file(self, tmp_trades_dir):
        filepath = os.path.join(str(tmp_trades_dir), "trades_2026.json")
        with open(filepath, "w") as f:
            f.write("not json{{{")
        trades = load_trades(2026)
        assert trades == []


class TestCumulativeStats:
    def test_empty(self):
        stats = get_cumulative_stats([])
        assert stats["total_trades"] == 0
        assert stats["win_rate"] == 0.0

    def test_basic_stats(self):
        trades = [
            {"result": "WIN", "net_pnl": 20.0},
            {"result": "WIN", "net_pnl": 15.0},
            {"result": "LOSS", "net_pnl": -10.0},
            {"result": "BE", "net_pnl": 0.0},
        ]
        stats = get_cumulative_stats(trades)
        assert stats["total_trades"] == 4
        assert stats["wins"] == 2
        assert stats["losses"] == 1
        assert stats["bes"] == 1
        assert stats["win_rate"] == 50.0
        assert stats["total_pnl"] == 25.0
        assert stats["profit_factor"] == 3.5  # 35/10

    def test_all_wins(self):
        trades = [{"result": "WIN", "net_pnl": 10.0}]
        stats = get_cumulative_stats(trades)
        assert stats["profit_factor"] == float("inf")
