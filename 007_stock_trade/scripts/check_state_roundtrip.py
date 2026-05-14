"""Item #29: state save/load 라운드트립"""
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.quant_modules.state_manager import EngineStateManager
from src.strategy.quant import Position


def main():
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        sm = EngineStateManager(data_dir=data_dir)

        # 포지션 1개 + 리밸런싱 월 세팅
        pos = Position(
            code="005930",
            name="삼성전자",
            entry_price=50000,
            current_price=51000,
            quantity=10,
            entry_date=datetime(2026, 4, 1, 9, 0, 0),
            stop_loss=46500,
            take_profit_1=62250,
            take_profit_2=71000,
            highest_price=51000,
        )
        positions = {pos.code: pos}
        sm.last_rebalance_month = "2026-04"
        sm.last_urgent_rebalance_month = "2026-03"
        sm.last_rebalance_date = datetime(2026, 4, 1, 9, 0, 0)
        sm.last_screening_date = datetime(2026, 4, 1, 8, 30, 0)
        sm.save_state(positions)

        # 새 인스턴스로 로드
        sm2 = EngineStateManager(data_dir=data_dir)
        restored = {}
        sm2.load_state(restored, Position)

        assert "005930" in restored, f"포지션 복원 실패: {restored}"
        assert restored["005930"].entry_price == 50000
        assert sm2.last_rebalance_month == "2026-04"
        assert sm2.last_urgent_rebalance_month == "2026-03"

    print("PASS: state save/load 라운드트립 (포지션 + 리밸런싱 월)")


if __name__ == "__main__":
    main()
