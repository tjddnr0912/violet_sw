#!/usr/bin/env python3
"""
빗썸 API 보안 강화된 서명 생성 시스템
"""

import base64
import hashlib
import hmac
import time
import urllib.parse
import secrets
import logging
from typing import Dict, Any
from collections import defaultdict

class SecureSignatureGenerator:
    def __init__(self):
        self.nonce_tracker = set()
        self.logger = logging.getLogger(__name__)
        self.failed_attempts = defaultdict(int)

    def create_signature(self, endpoint: str, parameters: Dict[str, Any], secret_key: str) -> tuple:
        """
        빗썸 공식 서명 알고리즘에 따른 안전한 서명 생성
        Returns: (signature, nonce)
        """
        try:
            # 1. 보안 강화된 Nonce 생성
            nonce = self._generate_secure_nonce()

            # 2. 파라미터 정규화 및 정렬
            normalized_params = self._normalize_parameters(parameters)

            # 3. 쿼리 스트링 생성 (빗썸 공식 방식)
            query_string = self._create_query_string(normalized_params)

            # 4. 서명 메시지 구성
            message = self._create_signature_message(endpoint, query_string, nonce)

            # 5. Secret Key 처리
            secret_bytes = self._process_secret_key(secret_key)

            # 6. HMAC-SHA512 서명 생성
            signature = self._generate_hmac_signature(message, secret_bytes)

            self.logger.debug(f"서명 생성 완료: endpoint={endpoint}, nonce={nonce}")
            return signature, nonce

        except Exception as e:
            self.logger.error(f"서명 생성 실패: {e}")
            raise

    def _generate_secure_nonce(self) -> str:
        """보안 강화된 Nonce 생성"""
        # 마이크로초 + 랜덤 값으로 중복 방지
        timestamp = int(time.time() * 1000000)  # 마이크로초
        random_suffix = secrets.randbelow(10000)  # 0-9999 랜덤

        nonce = f"{timestamp}{random_suffix:04d}"

        # 중복 확인 및 재생성
        max_attempts = 10
        attempts = 0
        while nonce in self.nonce_tracker and attempts < max_attempts:
            timestamp = int(time.time() * 1000000)
            random_suffix = secrets.randbelow(10000)
            nonce = f"{timestamp}{random_suffix:04d}"
            attempts += 1

        if attempts >= max_attempts:
            raise RuntimeError("Nonce 생성 실패: 중복 제거 한계 초과")

        # 메모리 관리 (최근 1000개만 유지)
        if len(self.nonce_tracker) > 1000:
            self.nonce_tracker.clear()

        self.nonce_tracker.add(nonce)
        return nonce

    def _normalize_parameters(self, parameters: Dict[str, Any]) -> Dict[str, str]:
        """파라미터 정규화"""
        normalized = {}
        for key, value in parameters.items():
            if value is not None:
                # 모든 값을 문자열로 변환
                normalized[key] = str(value)
        return normalized

    def _create_query_string(self, parameters: Dict[str, str]) -> str:
        """빗썸 공식 쿼리 스트링 생성"""
        # 빗썸 API: 파라미터를 키 이름 순으로 정렬
        sorted_params = sorted(parameters.items())

        # URL 인코딩 (safe='' 사용으로 모든 특수문자 인코딩)
        query_string = urllib.parse.urlencode(sorted_params, safe='')
        return query_string

    def _create_signature_message(self, endpoint: str, query_string: str, nonce: str) -> str:
        """빗썸 공식 서명 메시지 생성"""
        # 빗썸 공식 형식: endpoint + '\0' + query_string + '\0' + nonce
        message = endpoint + '\0' + query_string + '\0' + nonce
        return message

    def _process_secret_key(self, secret_key: str) -> bytes:
        """Secret Key 처리 (자동 형식 감지)"""
        try:
            # 1. Base64 디코딩 시도
            if self._is_base64(secret_key):
                return base64.b64decode(secret_key)

            # 2. 16진수 디코딩 시도
            elif self._is_hex(secret_key):
                return bytes.fromhex(secret_key)

            # 3. 일반 문자열로 처리
            else:
                return secret_key.encode('utf-8')

        except Exception as e:
            self.logger.warning(f"Secret Key 처리 중 오류, UTF-8로 처리: {e}")
            return secret_key.encode('utf-8')

    def _is_base64(self, s: str) -> bool:
        """Base64 형식 확인"""
        try:
            if len(s) % 4 != 0:
                return False
            base64.b64decode(s)
            return True
        except:
            return False

    def _is_hex(self, s: str) -> bool:
        """16진수 형식 확인"""
        try:
            int(s, 16)
            return len(s) % 2 == 0
        except:
            return False

    def _generate_hmac_signature(self, message: str, secret_bytes: bytes) -> str:
        """HMAC-SHA512 서명 생성"""
        signature_bytes = hmac.new(
            secret_bytes,
            message.encode('utf-8'),
            hashlib.sha512
        ).digest()

        return base64.b64encode(signature_bytes).decode('utf-8')

    def verify_signature_format(self, signature: str) -> bool:
        """서명 형식 검증"""
        try:
            # Base64 디코딩 테스트
            decoded = base64.b64decode(signature)
            # SHA512 결과는 64바이트여야 함
            return len(decoded) == 64
        except:
            return False

# 사용 예시
class BithumbSecureAPI:
    def __init__(self, connect_key: str, secret_key: str):
        self.connect_key = connect_key
        self.secret_key = secret_key
        self.signature_generator = SecureSignatureGenerator()
        self.logger = logging.getLogger(__name__)

    def create_authenticated_request(self, endpoint: str, parameters: Dict[str, Any]) -> Dict[str, str]:
        """인증된 요청 헤더 생성"""
        try:
            # 서명 생성
            signature, nonce = self.signature_generator.create_signature(
                endpoint, parameters, self.secret_key
            )

            # 헤더 구성
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Api-Key': self.connect_key,
                'Api-Sign': signature,
                'Api-Nonce': nonce,
                'User-Agent': 'SecureTradingBot/1.0'
            }

            self.logger.info(f"인증 헤더 생성 완료: {endpoint}")
            return headers

        except Exception as e:
            self.logger.error(f"인증 헤더 생성 실패: {e}")
            raise