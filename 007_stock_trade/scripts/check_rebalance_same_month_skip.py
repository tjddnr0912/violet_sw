"""Item #23: 동일 월 중복 리밸런싱 스킵"""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


def _mk_engine():
    import src.quant_engine as qe

    eng = qe.QuantTradingEngine.__new__(qe.QuantTradingEngine)
    eng.config = type("Cfg", (), {"target_stock_count": 15, "rebalance_day": 1})()
    eng.portfolio = type("P", (), {"positions": {f"c{i}": None for i in range(15)}})()
    eng._urgent_rebalance_mode = False
    sm = type("SM", (), {})()
    sm.last_urgent_rebalance_month = None
    sm.last_rebalance_month = None
    sm.last_rebalance_date = None
    eng.state_manager = sm
    return eng


def main():
    eng = _mk_engine()
    eng.last_rebalance_month = "2026-05"
    with patch("src.quant_engine.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 4, 9, 0, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        with patch("src.quant_engine.is_trading_day", return_value=True):
            r = eng._is_rebalance_day()
    assert r is False, f"같은 월 스킵 기대 False, 실제 {r}"
    print("PASS: 동일 월 리밸런싱 스킵")


if __name__ == "__main__":
    main()
