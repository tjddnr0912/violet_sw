"""Item #39: 월 첫 영업일에 리밸런싱 누락 시 알림 발송"""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.quant_modules.schedule_handler import ScheduleHandler


def _mk_engine(last_rebal_month: str = None, urgent_month: str = None):
    engine = MagicMock()
    engine.last_rebalance_month = last_rebal_month
    engine.state_manager.last_urgent_rebalance_month = urgent_month
    return engine


def main():
    # 케이스 1: 첫 영업일이고 리밸런싱 미완료 → 알림 발송
    eng = _mk_engine(last_rebal_month="2026-04")
    sh = ScheduleHandler(eng)

    # 5/4 (월) = 5월 첫 영업일 (5/1 휴장)
    with patch("src.quant_modules.schedule_handler.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 4, 15, 25, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        with patch(
            "src.quant_modules.schedule_handler.is_trading_day",
            side_effect=lambda d=None: (d is None) or (d.weekday() < 5 and d.strftime("%Y%m%d") != "20260501"),
        ):
            sh._check_missed_rebalance()
    assert eng.notifier.send_message.called, "리밸런싱 누락 알림이 발송되지 않음"

    # 케이스 2: 첫 영업일이지만 이번 달 리밸런싱 완료 → 알림 없음
    eng2 = _mk_engine(last_rebal_month="2026-05")
    sh2 = ScheduleHandler(eng2)
    with patch("src.quant_modules.schedule_handler.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 4, 15, 25, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        with patch(
            "src.quant_modules.schedule_handler.is_trading_day",
            side_effect=lambda d=None: (d is None) or (d.weekday() < 5 and d.strftime("%Y%m%d") != "20260501"),
        ):
            sh2._check_missed_rebalance()
    assert not eng2.notifier.send_message.called, "완료 상태에서 알림이 잘못 발송됨"

    # 케이스 3: 첫 영업일 아님 → 알림 없음
    eng3 = _mk_engine(last_rebal_month=None)
    sh3 = ScheduleHandler(eng3)
    with patch("src.quant_modules.schedule_handler.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 6, 15, 25, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        with patch(
            "src.quant_modules.schedule_handler.is_trading_day",
            side_effect=lambda d=None: True,
        ):
            sh3._check_missed_rebalance()
    assert not eng3.notifier.send_message.called, "비-첫영업일에 알림이 잘못 발송됨"

    # 케이스 4: 긴급 리밸런싱으로 이번 달 완료한 경우 → 알림 없음
    eng4 = _mk_engine(last_rebal_month=None, urgent_month="2026-05")
    sh4 = ScheduleHandler(eng4)
    with patch("src.quant_modules.schedule_handler.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 4, 15, 25, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        with patch(
            "src.quant_modules.schedule_handler.is_trading_day",
            side_effect=lambda d=None: (d is None) or (d.weekday() < 5 and d.strftime("%Y%m%d") != "20260501"),
        ):
            sh4._check_missed_rebalance()
    assert not eng4.notifier.send_message.called, "긴급 완료 상태에서 알림이 잘못 발송됨"

    print("PASS: 리밸런싱 누락 알림 4 케이스 (누락 / 완료 / 비-첫영업일 / 긴급완료)")


if __name__ == "__main__":
    main()
