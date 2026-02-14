"""
사용자 친화적 에러 메시지 포맷터

에러를 분류하고 텔레그램/터미널용 친화적 메시지로 변환.
로그 파일에는 raw exception이 그대로 기록됨 (디버깅용).
"""

from typing import Tuple


# 에러 카테고리별 템플릿: (아이콘, 제목, 상황, 조치, 안심)
ERROR_TEMPLATES = {
    "timeout": (
        "\u23F1\uFE0F",  # ⏱️
        "{context} 지연",
        "증권사 서버 응답이 지연되고 있습니다.",
        "자동으로 재시도합니다.",
        "시스템은 정상 운영 중입니다.",
    ),
    "connection": (
        "\U0001F50C",  # 🔌
        "{context} 연결 끊김",
        "서버 연결이 일시적으로 끊겼습니다.",
        "자동으로 재연결을 시도합니다.",
        "보유 포지션에 영향 없습니다.",
    ),
    "rate_limit": (
        "\u23F3",  # ⏳
        "{context} 일시 제한",
        "API 호출이 일시적으로 제한되었습니다.",
        "잠시 후 자동으로 재시도합니다.",
        "정상적인 보호 동작입니다.",
    ),
    "server_error": (
        "\U0001F527",  # 🔧
        "{context} 서버 오류",
        "증권사 서버에 일시적인 문제가 있습니다.",
        "자동으로 재시도합니다.",
        "시스템은 정상 운영 중입니다.",
    ),
    "auth": (
        "\U0001F511",  # 🔑
        "{context} 인증 실패",
        "API 인증에 실패했습니다.",
        "API 키 및 토큰 확인이 필요합니다.",
        "거래가 중단되었습니다. 확인 후 재시작해주세요.",
    ),
    "data": (
        "\U0001F4CA",  # 📊
        "{context} 데이터 오류",
        "데이터 처리 중 일부 항목이 누락되었습니다.",
        "다음 실행 시 자동으로 재시도합니다.",
        "기존 데이터에는 영향 없습니다.",
    ),
    "file": (
        "\U0001F4C1",  # 📁
        "{context} 파일 오류",
        "데이터 파일을 읽거나 쓸 수 없습니다.",
        "데몬 실행 상태를 확인해주세요.",
        "재시작으로 복구 가능합니다.",
    ),
    "unknown": (
        "\u26A0\uFE0F",  # ⚠️
        "{context} 오류",
        "예상치 못한 오류가 발생했습니다.",
        "자동 복구를 시도합니다.",
        "모니터링 중입니다.",
    ),
}


def classify_error(error: Exception) -> str:
    """
    Exception을 카테고리로 분류.

    우선순위:
    1. KIS 커스텀 예외 타입
    2. 표준 예외 타입
    3. 문자열 패턴 매칭
    """
    # 클래스 이름으로 빠르게 분류
    cls_name = type(error).__name__

    # 1. KIS 커스텀 예외
    if cls_name == "KISTimeoutError":
        return "timeout"
    if cls_name == "KISConnectionError":
        return "connection"
    if cls_name == "KISRateLimitError":
        return "rate_limit"
    if cls_name == "KISHTTPError":
        status = getattr(error, "status_code", 0)
        if status == 401 or status == 403:
            return "auth"
        if 500 <= status < 600:
            return "server_error"
        return "unknown"
    if cls_name == "KISBusinessError":
        error_str = str(error)
        if "EGW00201" in error_str or "초당 거래건수" in error_str:
            return "rate_limit"
        return "server_error"

    # 2. 표준 예외 타입
    if isinstance(error, (KeyError, IndexError, ValueError, TypeError)):
        return "data"
    if isinstance(error, (FileNotFoundError, PermissionError, OSError)):
        # OSError이지만 네트워크 관련인 경우 분리
        error_str = str(error)
        if any(x in error_str for x in ["Connection", "Network", "timed out"]):
            return "connection"
        return "file"

    # 3. 문자열 패턴 매칭
    error_str = str(error)

    # 타임아웃
    if any(x in error_str for x in [
        "Timeout", "timed out", "Read timed out", "TimeoutError",
        "ReadTimeout", "ConnectTimeout"
    ]):
        return "timeout"

    # 연결 오류
    if any(x in error_str for x in [
        "Connection", "ConnectError", "ConnectionError",
        "ConnectionRefused", "ConnectionReset", "NetworkError",
        "HTTPSConnectionPool", "MaxRetryError"
    ]):
        return "connection"

    # Rate Limit
    if any(x in error_str for x in [
        "EGW00201", "초당 거래건수", "rate limit", "Too Many Requests", "429"
    ]):
        return "rate_limit"

    # 서버 오류
    if any(x in error_str for x in [
        "500", "502", "503", "504", "Internal Server Error",
        "Service Unavailable", "Bad Gateway"
    ]):
        return "server_error"

    # 인증 오류
    if any(x in error_str for x in [
        "401", "403", "Unauthorized", "Forbidden",
        "인증", "토큰", "token", "credential"
    ]):
        return "auth"

    return "unknown"


def format_user_error(error: Exception, context: str) -> str:
    """
    에러를 사용자 친화적 HTML 메시지로 변환.

    Args:
        error: 발생한 예외
        context: 어떤 작업 중 발생했는지 (예: "잔고 조회", "스크리닝")

    Returns:
        HTML 포맷된 사용자 친화적 메시지
    """
    category = classify_error(error)
    icon, title_tmpl, situation, action, reassure = ERROR_TEMPLATES[category]

    title = title_tmpl.format(context=context)

    return (
        f"{icon} <b>{title}</b>\n"
        f"\n"
        f"\U0001F4CB 상황: {situation}\n"
        f"\U0001F527 조치: {action}\n"
        f"\u2705 {reassure}"
    )
