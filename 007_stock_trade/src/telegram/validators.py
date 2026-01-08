"""
텔레그램 명령어 입력 검증 유틸리티
"""

import re
from typing import Tuple


class InputValidator:
    """명령어 인자 검증 유틸리티"""

    # 종목코드 패턴 (6자리 숫자)
    STOCK_CODE_PATTERN = re.compile(r'^\d{6}$')

    @staticmethod
    def validate_stock_code(code: str) -> Tuple[bool, str]:
        """
        종목코드 유효성 검증

        Returns:
            (유효여부, 에러메시지)
        """
        if not code:
            return False, "종목코드를 입력해주세요."
        if not InputValidator.STOCK_CODE_PATTERN.match(code):
            return False, f"올바른 종목코드를 입력하세요 (6자리 숫자). 입력값: {code}"
        return True, ""

    @staticmethod
    def validate_positive_int(value: str, min_val: int = 1, max_val: int = 100,
                               field_name: str = "값") -> Tuple[bool, int, str]:
        """
        양의 정수 검증

        Returns:
            (유효여부, 파싱된값, 에러메시지)
        """
        try:
            num = int(value)
            if num < min_val or num > max_val:
                return False, 0, f"{field_name}은(는) {min_val}~{max_val} 사이여야 합니다. 입력값: {num}"
            return True, num, ""
        except ValueError:
            return False, 0, f"{field_name}은(는) 숫자로 입력해주세요. 입력값: {value}"

    @staticmethod
    def validate_positive_float(value: str, min_val: float = 0.0, max_val: float = 100.0,
                                  field_name: str = "값") -> Tuple[bool, float, str]:
        """
        양의 실수 검증

        Returns:
            (유효여부, 파싱된값, 에러메시지)
        """
        try:
            num = float(value)
            if num < min_val or num > max_val:
                return False, 0.0, f"{field_name}은(는) {min_val}~{max_val} 사이여야 합니다. 입력값: {num}"
            return True, num, ""
        except ValueError:
            return False, 0.0, f"{field_name}은(는) 숫자로 입력해주세요. 입력값: {value}"

    @staticmethod
    def validate_on_off(value: str) -> Tuple[bool, bool, str]:
        """
        on/off 값 검증

        Returns:
            (유효여부, 불리언값, 에러메시지)
        """
        value_lower = value.lower()
        if value_lower in ('on', 'true', '1', 'yes', '활성'):
            return True, True, ""
        elif value_lower in ('off', 'false', '0', 'no', '비활성'):
            return True, False, ""
        else:
            return False, False, f"on 또는 off로 입력해주세요. 입력값: {value}"
