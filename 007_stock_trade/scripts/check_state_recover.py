"""Item #13: state_manager 손상 JSON 복구"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.quant_modules.state_manager import EngineStateManager


def main():
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        sm = EngineStateManager(data_dir=data_dir)

        # 손상된 JSON 파일 생성
        sm.state_file.write_text("{ corrupt", encoding="utf-8")

        sm.load_state(portfolio_positions={}, position_class=None)

        # 손상 파일이 삭제되고 backup 생성됐는지
        backups = list(data_dir.glob("engine_state.backup.*.json"))
        assert backups, f"백업 파일 없음: {list(data_dir.iterdir())}"
        assert not sm.state_file.exists(), "손상 파일이 삭제되지 않음"

    print("PASS: 손상 state 파일 복구 (백업 생성, 원본 삭제)")


if __name__ == "__main__":
    main()
