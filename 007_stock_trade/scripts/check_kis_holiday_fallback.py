"""Item #40: KIS 모의계좌의 휴장일 API는 빈 리스트 반환 (의도된 동작)

모의투자에서는 CTCA0903R(휴장일조회) TR이 지원되지 않으므로
get_holiday_schedule이 빈 리스트를 반환해야 한다.
이 fallback이 깨지면 KNOWN_HOLIDAYS가 single source가 아니게 되어
누락된 휴장일을 막을 안전망이 사라진다.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.kis_client import KISClient


def main():
    # 모의계좌 인스턴스
    c = KISClient.__new__(KISClient)
    c.is_virtual = True
    holidays = c.get_holiday_schedule()
    assert holidays == [], f"모의계좌는 빈 리스트 기대, 실제 {holidays}"
    print("PASS: 모의계좌 get_holiday_schedule() → [] (의도된 fallback)")


if __name__ == "__main__":
    main()
