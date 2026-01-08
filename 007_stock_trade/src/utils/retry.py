"""
재시도 로직 유틸리티

API 호출 및 네트워크 작업의 재시도 처리를 위한 데코레이터 및 클래스
"""

import time
import logging
from typing import Callable, TypeVar, Tuple, Optional, Any
from functools import wraps
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class RetryConfig:
    """재시도 설정"""

    max_retries: int = 3
    """최대 재시도 횟수"""

    base_delay: float = 1.0
    """기본 대기 시간 (초)"""

    backoff_factor: float = 1.5
    """백오프 배수 (지수적 증가)"""

    max_delay: float = 60.0
    """최대 대기 시간 (초)"""

    retriable_errors: Tuple[str, ...] = field(default_factory=tuple)
    """재시도 가능한 에러 메시지 패턴"""

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """
        재시도 여부 판단

        Args:
            error: 발생한 예외
            attempt: 현재 시도 횟수 (0부터 시작)

        Returns:
            재시도 가능 여부
        """
        if attempt >= self.max_retries - 1:
            return False

        if not self.retriable_errors:
            return True  # 에러 패턴이 지정되지 않으면 모든 에러에 재시도

        error_str = str(error)
        return any(pattern in error_str for pattern in self.retriable_errors)

    def get_delay(self, attempt: int) -> float:
        """
        현재 시도에 대한 대기 시간 계산

        Args:
            attempt: 현재 시도 횟수 (0부터 시작)

        Returns:
            대기 시간 (초)
        """
        delay = self.base_delay * (self.backoff_factor ** attempt)
        return min(delay, self.max_delay)


# 사전 정의된 설정들
API_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    base_delay=1.0,
    backoff_factor=1.5,
    retriable_errors=("EGW00201", "초당 거래건수", "500", "서버", "Timeout", "Connection")
)
"""KIS API 호출용 재시도 설정"""

TELEGRAM_RETRY_CONFIG = RetryConfig(
    max_retries=10,
    base_delay=3.0,
    backoff_factor=2.0,
    max_delay=60.0,
    retriable_errors=("Timed out", "ConnectTimeout", "Network", "Connection")
)
"""Telegram 봇 재시도 설정"""

ORDER_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    base_delay=1.0,
    backoff_factor=1.5,
    retriable_errors=("EGW00201", "초당 거래건수", "서버")
)
"""주문 실행 재시도 설정"""


def with_retry(config: Optional[RetryConfig] = None):
    """
    재시도 데코레이터

    Args:
        config: 재시도 설정 (None이면 기본 설정 사용)

    Returns:
        데코레이터 함수

    Example:
        @with_retry(API_RETRY_CONFIG)
        def call_api():
            ...
    """
    config = config or RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_error: Optional[Exception] = None

            for attempt in range(config.max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e

                    if not config.should_retry(e, attempt):
                        raise

                    delay = config.get_delay(attempt)
                    logger.warning(
                        f"재시도 {attempt + 1}/{config.max_retries}: {func.__name__} - "
                        f"{e} ({delay:.1f}초 대기)"
                    )
                    time.sleep(delay)

            # 모든 재시도 실패
            if last_error:
                raise last_error
            raise RuntimeError("알 수 없는 재시도 실패")

        return wrapper
    return decorator


class RetryExecutor:
    """
    재시도 실행기

    복잡한 재시도 로직이 필요한 경우 사용

    Example:
        executor = RetryExecutor(API_RETRY_CONFIG)
        result = executor.execute(api_call, code="005930")
    """

    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()

    def execute(
        self,
        func: Callable[..., T],
        *args,
        on_retry: Optional[Callable[[int, Exception], None]] = None,
        **kwargs
    ) -> T:
        """
        함수 실행 (재시도 포함)

        Args:
            func: 실행할 함수
            *args: 함수 인자
            on_retry: 재시도 시 호출할 콜백 (attempt, error)
            **kwargs: 함수 키워드 인자

        Returns:
            함수 실행 결과

        Raises:
            Exception: 모든 재시도 실패 시 마지막 예외
        """
        last_error: Optional[Exception] = None

        for attempt in range(self.config.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e

                if not self.config.should_retry(e, attempt):
                    raise

                delay = self.config.get_delay(attempt)

                if on_retry:
                    on_retry(attempt, e)

                logger.warning(
                    f"재시도 {attempt + 1}/{self.config.max_retries}: "
                    f"{func.__name__} - {e} ({delay:.1f}초 대기)"
                )
                time.sleep(delay)

        if last_error:
            raise last_error
        raise RuntimeError("알 수 없는 재시도 실패")
