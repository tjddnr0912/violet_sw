"""Item #41: run_quant_watchdog.sh 문법/필수 요소 검증"""
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).parent.parent
    wd = root / "scripts" / "run_quant_watchdog.sh"
    assert wd.exists(), f"watchdog 스크립트 없음: {wd}"
    assert wd.stat().st_mode & 0o111, "실행 권한 없음"

    # 문법 체크
    r = subprocess.run(["bash", "-n", str(wd)], capture_output=True, text=True)
    assert r.returncode == 0, f"문법 오류: {r.stderr}"

    # 필수 요소
    text = wd.read_text()
    required = [
        "MAX_RESTARTS",
        "RAPID_RESTART_THRESHOLD",
        "HANG_TIMEOUT",
        "notify_telegram",
        "trap cleanup",
        "run_quant.sh daemon",
    ]
    missing = [r for r in required if r not in text]
    assert not missing, f"누락된 요소: {missing}"

    print("PASS: watchdog 문법 및 필수 요소 확인")


if __name__ == "__main__":
    main()
