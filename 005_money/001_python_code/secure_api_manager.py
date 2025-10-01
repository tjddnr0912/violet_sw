#!/usr/bin/env python3
"""
보안 강화된 API 키 관리 시스템
"""

import os
import re
import base64
import json
from typing import Optional, Dict
from cryptography.fernet import Fernet
import keyring
import logging

class SecureAPIKeyManager:
    def __init__(self):
        self.connect_key: Optional[str] = None
        self.secret_key: Optional[str] = None
        self.logger = logging.getLogger(__name__)
        self._load_credentials()

    def _load_credentials(self):
        """다단계 API 키 로딩 (보안 우선순위 순)"""
        try:
            # 1순위: 환경변수
            self._load_from_env()

            # 2순위: 시스템 키체인 (macOS Keychain, Linux Keyring)
            if not self.connect_key:
                self._load_from_keystore()

            # 3순위: 암호화된 설정 파일
            if not self.connect_key:
                self._load_from_encrypted_file()

            # 검증
            self.validate_credentials()

        except Exception as e:
            self.logger.error(f"API 키 로딩 실패: {e}")
            raise

    def _load_from_env(self):
        """환경변수에서 API 키 로딩"""
        self.connect_key = os.getenv("BITHUMB_CONNECT_KEY")
        self.secret_key = os.getenv("BITHUMB_SECRET_KEY")

        if self.connect_key and self.secret_key:
            self.logger.info("환경변수에서 API 키를 성공적으로 로드했습니다.")

    def _load_from_keystore(self):
        """시스템 키체인에서 API 키 로딩"""
        try:
            self.connect_key = keyring.get_password("bithumb_api", "connect_key")
            self.secret_key = keyring.get_password("bithumb_api", "secret_key")

            if self.connect_key and self.secret_key:
                self.logger.info("시스템 키체인에서 API 키를 로드했습니다.")
        except Exception as e:
            self.logger.warning(f"키체인 접근 실패: {e}")

    def _load_from_encrypted_file(self):
        """암호화된 파일에서 API 키 로딩"""
        try:
            config_file = "config_encrypted.json"
            if os.path.exists(config_file):
                with open(config_file, 'rb') as f:
                    encrypted_data = f.read()

                # 암호화 키는 환경변수에서 가져오기
                encryption_key = os.getenv("CONFIG_ENCRYPTION_KEY")
                if encryption_key:
                    fernet = Fernet(encryption_key.encode())
                    decrypted_data = fernet.decrypt(encrypted_data)
                    config_data = json.loads(decrypted_data.decode())

                    self.connect_key = config_data.get("connect_key")
                    self.secret_key = config_data.get("secret_key")

                    if self.connect_key and self.secret_key:
                        self.logger.info("암호화된 파일에서 API 키를 로드했습니다.")
        except Exception as e:
            self.logger.warning(f"암호화된 파일 로딩 실패: {e}")

    def validate_credentials(self):
        """API 키 유효성 검증"""
        if not self.connect_key or not self.secret_key:
            raise ValueError("API 키가 설정되지 않았습니다.")

        # Connect Key 형식 검증 (빗썸: 영숫자 20-50자)
        if not re.match(r'^[a-zA-Z0-9]{20,50}$', self.connect_key):
            raise ValueError("Connect Key 형식이 올바르지 않습니다.")

        # Secret Key 형식 검증
        if len(self.secret_key) < 20:
            raise ValueError("Secret Key가 너무 짧습니다.")

        # 기본값 확인
        if self.connect_key in ["YOUR_CONNECT_KEY", "your_connect_key"]:
            raise ValueError("API 키가 기본값으로 설정되어 있습니다.")

        if self.secret_key in ["YOUR_SECRET_KEY", "your_secret_key"]:
            raise ValueError("Secret Key가 기본값으로 설정되어 있습니다.")

        self.logger.info("API 키 검증이 완료되었습니다.")

    def save_to_keystore(self, connect_key: str, secret_key: str):
        """API 키를 시스템 키체인에 안전하게 저장"""
        try:
            keyring.set_password("bithumb_api", "connect_key", connect_key)
            keyring.set_password("bithumb_api", "secret_key", secret_key)
            self.logger.info("API 키가 시스템 키체인에 저장되었습니다.")
        except Exception as e:
            self.logger.error(f"키체인 저장 실패: {e}")
            raise

    def get_masked_keys(self) -> Dict[str, str]:
        """마스킹된 키 정보 반환 (로깅용)"""
        return {
            "connect_key": f"{self.connect_key[:6]}...{self.connect_key[-4:]}" if self.connect_key else "None",
            "secret_key": f"{self.secret_key[:6]}...{self.secret_key[-4:]}" if self.secret_key else "None"
        }