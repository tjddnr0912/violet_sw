"""Item #24: 긴급 리밸런싱 - 70% 미만 트리거, 0개일 때 월 잠금 무시, 영업일 한정"""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


def _mk_engine(positions_count: int, urgent_month: str = None):
    import src.quant_engine as qe

    eng = qe.QuantTradingEngine.__new__(qe.QuantTradingEngine)
    eng.config = type("Cfg", (), {"target_stock_count": 15, "rebalance_day": 1})()
    eng.portfolio = type("P", (), {"positions": {f"c{i}": None for i in range(positions_count)}})()
    eng._urgent_rebalance_mode = False
    sm = type("SM", (), {})()
    sm.last_urgent_rebalance_month = urgent_month
    sm.last_rebalance_month = "2026-05"
    sm.last_rebalance_date = None
    eng.state_manager = sm
    return eng


def _run(eng, now):
    with patch("src.quant_engine.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        with patch("src.quant_engine.is_trading_day", return_value=True):
            return eng._is_rebalance_day()


def main():
    busi = datetime(2026, 5, 14, 9, 0, 0)

    # 보유 0 → 영업일 + 월 잠금 무시 → True
    eng = _mk_engine(0, urgent_month="2026-05")
    assert _run(eng, busi) is True, "보유 0 긴급 트리거 실패"

    # 보유 5/15=33% < 70%, 같은 달 긴급 미완료 → True
    eng = _mk_engine(5, urgent_month=None)
    assert _run(eng, busi) is True, "보유 5 긴급 트리거 실패"

    # 보유 5/15 < 70%, 같은 달 긴급 완료 → False
    eng = _mk_engine(5, urgent_month="2026-05")
    assert _run(eng, busi) is False, "긴급 월 1회 제한 실패"

    # 보유 11/15=73% >= 70%, 월초 리밸런싱 완료 → False
    eng = _mk_engine(11, urgent_month=None)
    assert _run(eng, busi) is False, "70% 이상은 긴급 미트리거"

    print("PASS: 긴급 리밸런싱 70% 룰 + 0개 안전망 + 월 1회 제한")


if __name__ == "__main__":
    main()
