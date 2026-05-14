"""Item #11: retry 데코레이터 max_retries 동작"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.retry import RetryConfig, with_retry, API_RETRY_CONFIG


def main():
    cnt = [0]

    @with_retry(RetryConfig(max_retries=3, base_delay=0, retriable_errors=("boom",)))
    def f():
        cnt[0] += 1
        raise ValueError("boom")

    try:
        f()
    except ValueError:
        pass

    assert cnt[0] == 3, f"expected 3 attempts, got {cnt[0]}"
    assert API_RETRY_CONFIG.max_retries > 0
    print(f"PASS: max_retries=3 → 시도 {cnt[0]}회 후 예외")


if __name__ == "__main__":
    main()
