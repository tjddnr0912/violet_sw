"""Item #30: ScheduleHandler.check_initial_setup - 휴장일에 스크리닝 미트리거"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.quant_modules.schedule_handler import ScheduleHandler


def main():
    engine = MagicMock()
    engine.last_rebalance_month = None
    engine.portfolio.positions = {}
    sh = ScheduleHandler(engine)

    # 휴장일 mock
    with patch("src.quant_modules.schedule_handler.is_trading_day", return_value=False):
        sh.check_initial_setup()

    engine.run_screening.assert_not_called()
    print("PASS: 휴장일 데몬 시작 시 자동 스크리닝 미실행")


if __name__ == "__main__":
    main()
