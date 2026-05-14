"""Item #22: 월초 리밸런싱 - 첫 거래일에만 True"""
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
    # 2026-05-04(월): 첫 영업일 (5/1 휴장, 5/2~3 주말)
    # 2026-05-06(수): 첫 영업일 아님
    eng = _mk_engine()

    with patch("src.quant_engine.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 4, 9, 0, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        # 5/1, 5/2, 5/3 모두 휴장 → 5/4가 첫 거래일
        def is_td(d):
            return d.weekday() < 5 and d.strftime("%Y%m%d") not in {"20260501"}
        with patch("src.quant_engine.is_trading_day", side_effect=is_td):
            r1 = eng._is_rebalance_day()
    assert r1 is True, f"첫 거래일 True 기대했으나 {r1}"

    eng = _mk_engine()
    with patch("src.quant_engine.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 6, 9, 0, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        with patch("src.quant_engine.is_trading_day", side_effect=lambda d: True):
            r2 = eng._is_rebalance_day()
    assert r2 is False, f"첫 거래일 아님 False 기대했으나 {r2}"

    print("PASS: 월초 첫 거래일에만 True (5/4 True, 5/6 False)")


if __name__ == "__main__":
    main()
