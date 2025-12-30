"""
한국 주식시장 휴장일 및 특수 개장 시간 관리

pykrx를 활용하여 실제 거래일 여부를 판단합니다.
"""

import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, Tuple
from functools import lru_cache

logger = logging.getLogger(__name__)

# 알려진 휴장일 (매년 업데이트 필요)
# 형식: "YYYYMMDD"
KNOWN_HOLIDAYS = {
    # 2025년 휴장일
    "20250101",  # 신정
    "20250128",  # 설날 연휴
    "20250129",  # 설날
    "20250130",  # 설날 연휴
    "20250301",  # 삼일절 (토요일이지만 기록)
    "20250303",  # 삼일절 대체휴일
    "20250505",  # 어린이날 + 부처님오신날 (겹침)
    "20250506",  # 대체휴일 (어린이날/부처님오신날)
    "20250606",  # 현충일
    "20250815",  # 광복절
    "20251003",  # 개천절
    "20251005",  # 추석 연휴
    "20251006",  # 추석
    "20251007",  # 추석 연휴
    "20251008",  # 추석 대체휴일
    "20251009",  # 한글날
    "20251225",  # 성탄절
    "20251231",  # 연말 휴장
    # 2026년 휴장일
    "20260101",  # 신정
    "20260216",  # 설날 연휴
    "20260217",  # 설날
    "20260218",  # 설날 연휴
    "20260301",  # 삼일절 (일요일)
    "20260302",  # 삼일절 대체휴일
    "20260505",  # 어린이날
    "20260524",  # 부처님오신날
    "20260525",  # 부처님오신날 대체휴일
    "20260606",  # 현충일 (토요일)
    "20260815",  # 광복절 (토요일)
    "20260817",  # 광복절 대체휴일
    "20260924",  # 추석 연휴
    "20260925",  # 추석
    "20260926",  # 추석 연휴
    "20261003",  # 개천절 (토요일)
    "20261005",  # 개천절 대체휴일
    "20261009",  # 한글날
    "20261225",  # 성탄절
    "20261231",  # 연말 휴장
}

# 특수 개장 시간 (매년 업데이트 필요)
# 형식: "MMDD": ("개장시간", "마감시간")
SPECIAL_TRADING_HOURS = {
    # 1월 2일 - 10시 개장 (매년 적용)
    "0102": ("10:00", "15:30"),
}

# 캐시된 거래일 정보 (일별) - 스레드 안전
_trading_day_cache = {}
_cache_lock = threading.Lock()


def is_trading_day(date: Optional[datetime] = None) -> bool:
    """
    해당 날짜가 거래일인지 확인 (스레드 안전)

    Args:
        date: 확인할 날짜 (None이면 오늘)

    Returns:
        bool: 거래일이면 True
    """
    if date is None:
        date = datetime.now()

    date_str = date.strftime("%Y%m%d")

    # 캐시 확인 (스레드 안전)
    with _cache_lock:
        if date_str in _trading_day_cache:
            return _trading_day_cache[date_str]

    # 주말은 무조건 휴장
    if date.weekday() >= 5:
        with _cache_lock:
            _trading_day_cache[date_str] = False
        return False

    # 알려진 휴장일 체크
    if date_str in KNOWN_HOLIDAYS:
        with _cache_lock:
            _trading_day_cache[date_str] = False
        logger.info(f"{date_str}: 휴장일 (사전 등록됨)")
        return False

    # 미래 날짜는 pykrx로 확인 불가 - 알려진 휴장일이 아니면 거래일로 가정
    if date.date() > datetime.now().date():
        logger.debug(f"{date_str}: 미래 날짜 - 평일이므로 거래일로 가정")
        return True

    # pykrx로 실제 거래 데이터 확인
    try:
        from pykrx import stock as pykrx_stock

        # 삼성전자(005930)로 거래일 확인
        df = pykrx_stock.get_market_ohlcv_by_date(date_str, date_str, "005930")
        is_trading = len(df) > 0 and df['거래량'].sum() > 0

        with _cache_lock:
            _trading_day_cache[date_str] = is_trading

        if not is_trading:
            logger.info(f"{date_str}: 휴장일 (pykrx 확인)")

        return is_trading

    except Exception as e:
        logger.warning(f"pykrx 거래일 확인 실패 ({date_str}): {e}")
        # 실패 시 평일이면 거래일로 가정
        return date.weekday() < 5


def get_trading_hours(date: Optional[datetime] = None) -> Tuple[str, str]:
    """
    해당 날짜의 거래 시간 반환

    Args:
        date: 확인할 날짜 (None이면 오늘)

    Returns:
        Tuple[str, str]: (개장시간, 마감시간) 예: ("09:00", "15:30")
    """
    if date is None:
        date = datetime.now()

    mmdd = date.strftime("%m%d")

    # 특수 개장 시간 확인
    if mmdd in SPECIAL_TRADING_HOURS:
        hours = SPECIAL_TRADING_HOURS[mmdd]
        logger.info(f"{date.strftime('%Y-%m-%d')}: 특수 거래 시간 {hours[0]}~{hours[1]}")
        return hours

    # 기본 거래 시간
    return ("09:00", "15:30")


def get_market_open_time(date: Optional[datetime] = None) -> str:
    """개장 시간 반환"""
    return get_trading_hours(date)[0]


def get_market_close_time(date: Optional[datetime] = None) -> str:
    """마감 시간 반환"""
    return get_trading_hours(date)[1]


def get_next_trading_day(date: Optional[datetime] = None) -> datetime:
    """
    다음 거래일 반환

    Args:
        date: 기준 날짜 (None이면 오늘)

    Returns:
        datetime: 다음 거래일
    """
    if date is None:
        date = datetime.now()

    next_day = date + timedelta(days=1)

    # 최대 14일까지 탐색 (연휴 대비)
    for _ in range(14):
        if is_trading_day(next_day):
            return next_day
        next_day += timedelta(days=1)

    # 찾지 못하면 다음 평일 반환
    while next_day.weekday() >= 5:
        next_day += timedelta(days=1)

    return next_day


def get_previous_trading_day(date: Optional[datetime] = None) -> datetime:
    """
    이전 거래일 반환

    Args:
        date: 기준 날짜 (None이면 오늘)

    Returns:
        datetime: 이전 거래일
    """
    if date is None:
        date = datetime.now()

    prev_day = date - timedelta(days=1)

    # 최대 14일까지 탐색
    for _ in range(14):
        if is_trading_day(prev_day):
            return prev_day
        prev_day -= timedelta(days=1)

    return prev_day


def clear_cache():
    """캐시 초기화 (스레드 안전)"""
    global _trading_day_cache
    with _cache_lock:
        _trading_day_cache = {}
    logger.info("거래일 캐시 초기화됨")


# 테스트용
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=== 거래일 테스트 ===")

    # 오늘
    today = datetime.now()
    print(f"오늘 ({today.strftime('%Y-%m-%d')}): 거래일={is_trading_day()}")

    # 12/31 (휴장)
    dec31 = datetime(2025, 12, 31)
    print(f"12/31 (화): 거래일={is_trading_day(dec31)}")

    # 1/1 (휴장)
    jan1 = datetime(2026, 1, 1)
    print(f"1/1 (수): 거래일={is_trading_day(jan1)}")

    # 1/2 (10시 개장)
    jan2 = datetime(2026, 1, 2)
    print(f"1/2 (목): 거래일={is_trading_day(jan2)}, 거래시간={get_trading_hours(jan2)}")

    # 다음 거래일
    print(f"다음 거래일: {get_next_trading_day().strftime('%Y-%m-%d')}")
