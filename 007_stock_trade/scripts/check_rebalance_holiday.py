"""Item #21: 휴장일에는 _is_rebalance_day가 항상 False (긴급 포함)

5/1 사고의 second smoking gun:
긴급 리밸런싱 분기가 휴장일 체크보다 먼저 실행되어 휴장일에도 True 반환 가능.
"""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils import market_calendar


def _mk_engine(positions_count: int):
    """경량 엔진 mock - _is_rebalance_day만 검증"""
    import src.quant_engine as qe

    eng = qe.QuantTradingEngine.__new__(qe.QuantTradingEngine)
    eng.config = type("Cfg", (), {"target_stock_count": 15, "rebalance_day": 1})()
    eng.portfolio = type("P", (), {"positions": {f"c{i}": None for i in range(positions_count)}})()
    eng._urgent_rebalance_mode = False

    sm = type("SM", (), {})()
    sm.last_urgent_rebalance_month = None
    sm.last_rebalance_month = None
    sm.last_rebalance_date = None
    eng.state_manager = sm
    return eng


def main():
    # 휴장일 모킹: 2026-05-01 (근로자의 날)
    holiday = datetime(2026, 5, 1, 9, 0, 0)

    cases = [
        ("zero_positions_holiday", 0),
        ("low_positions_holiday", 5),  # 5/15 = 33%, urgent trigger
        ("full_positions_holiday", 15),
    ]

    failed = []
    for name, cnt in cases:
        eng = _mk_engine(cnt)
        with patch("src.quant_engine.datetime") as mock_dt:
            mock_dt.now.return_value = holiday
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            with patch("src.quant_engine.is_trading_day", return_value=False):
                result = eng._is_rebalance_day()
        if result is not False:
            failed.append((name, result))

    if failed:
        for n, r in failed:
            print(f"FAIL: {n} → {r}")
        sys.exit(1)
    print("PASS: 휴장일에는 _is_rebalance_day가 모든 케이스에서 False")


if __name__ == "__main__":
    main()
