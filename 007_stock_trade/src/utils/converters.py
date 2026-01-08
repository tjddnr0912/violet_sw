"""
공통 데이터 변환 유틸리티

안전한 타입 변환 및 포맷팅 함수 모음
"""

from typing import Union, Optional


def safe_float(val: Optional[Union[str, int, float]], default: float = 0.0) -> float:
    """
    안전한 float 변환

    Args:
        val: 변환할 값 (None, 빈 문자열, 숫자 등)
        default: 변환 실패 시 반환할 기본값

    Returns:
        변환된 float 값 또는 기본값
    """
    try:
        if val is None or val == "":
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_int(val: Optional[Union[str, int, float]], default: int = 0) -> int:
    """
    안전한 int 변환

    Args:
        val: 변환할 값
        default: 변환 실패 시 반환할 기본값

    Returns:
        변환된 int 값 또는 기본값
    """
    try:
        if val is None or val == "":
            return default
        return int(float(val))  # "123.45" 같은 문자열도 처리
    except (ValueError, TypeError):
        return default


def format_currency(value: Union[int, float], suffix: str = "원") -> str:
    """
    통화 포맷팅 (천 단위 구분자 포함)

    Args:
        value: 금액
        suffix: 단위 (기본: "원")

    Returns:
        포맷팅된 문자열 (예: "1,234,567원")
    """
    return f"{int(value):,}{suffix}"


def format_pct(value: float, signed: bool = True, decimals: int = 2) -> str:
    """
    퍼센트 포맷팅

    Args:
        value: 퍼센트 값 (예: 1.23 = 1.23%)
        signed: 부호 표시 여부 (+ 포함)
        decimals: 소수점 자릿수

    Returns:
        포맷팅된 문자열 (예: "+1.23%" 또는 "1.23%")
    """
    if signed:
        return f"{value:+.{decimals}f}%"
    return f"{value:.{decimals}f}%"


def format_quantity(value: Union[int, float], suffix: str = "주") -> str:
    """
    수량 포맷팅

    Args:
        value: 수량
        suffix: 단위 (기본: "주")

    Returns:
        포맷팅된 문자열 (예: "1,234주")
    """
    return f"{int(value):,}{suffix}"
