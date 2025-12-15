"""
한국투자증권 API 인증 모듈
- 접근토큰 발급 및 관리
- 실전투자/모의투자 환경 전환
"""

import os
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()


class KISAuth:
    """한국투자증권 API 인증 클래스"""

    # API 도메인
    DOMAIN_REAL = "https://openapi.koreainvestment.com:9443"  # 실전투자
    DOMAIN_VIRTUAL = "https://openapivts.koreainvestment.com:29443"  # 모의투자

    # 토큰 저장 경로
    TOKEN_FILE = Path(__file__).parent.parent.parent / "config" / "token.json"

    def __init__(self, is_virtual: bool = True):
        """
        Args:
            is_virtual: True=모의투자, False=실전투자
        """
        self.is_virtual = is_virtual
        self.base_url = self.DOMAIN_VIRTUAL if is_virtual else self.DOMAIN_REAL

        # API 키 로드
        self.app_key = os.getenv("KIS_APP_KEY")
        self.app_secret = os.getenv("KIS_APP_SECRET")
        self.account_no = os.getenv("KIS_ACCOUNT_NO")  # 계좌번호 (8자리-2자리)

        # 토큰 정보
        self.access_token = None
        self.token_expires_at = None

        # 저장된 토큰 로드 시도
        self._load_token()

    def _load_token(self) -> bool:
        """저장된 토큰 파일 로드"""
        if not self.TOKEN_FILE.exists():
            return False

        try:
            with open(self.TOKEN_FILE, 'r') as f:
                data = json.load(f)

            # 환경(실전/모의) 확인
            if data.get("is_virtual") != self.is_virtual:
                return False

            # 만료 시간 확인
            expires_at = datetime.fromisoformat(data.get("expires_at", ""))
            if datetime.now() >= expires_at - timedelta(hours=1):  # 1시간 여유
                return False

            self.access_token = data.get("access_token")
            self.token_expires_at = expires_at
            return True

        except (json.JSONDecodeError, ValueError, KeyError):
            return False

    def _save_token(self):
        """토큰을 파일에 저장"""
        self.TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "access_token": self.access_token,
            "expires_at": self.token_expires_at.isoformat(),
            "is_virtual": self.is_virtual
        }

        with open(self.TOKEN_FILE, 'w') as f:
            json.dump(data, f, indent=2)

    def get_access_token(self, force_refresh: bool = False) -> str:
        """
        접근토큰 반환 (필요시 발급)

        Args:
            force_refresh: True면 강제로 새 토큰 발급

        Returns:
            접근토큰 문자열
        """
        # 유효한 토큰이 있으면 반환
        if not force_refresh and self.access_token and self.token_expires_at:
            if datetime.now() < self.token_expires_at - timedelta(hours=1):
                return self.access_token

        # 새 토큰 발급
        return self._issue_token()

    def _issue_token(self) -> str:
        """새 접근토큰 발급"""
        url = f"{self.base_url}/oauth2/tokenP"

        headers = {
            "Content-Type": "application/json"
        }

        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }

        response = requests.post(url, headers=headers, json=body)
        response.raise_for_status()

        data = response.json()

        self.access_token = data["access_token"]
        # 토큰 유효기간: 발급 후 약 24시간
        self.token_expires_at = datetime.now() + timedelta(hours=23)

        # 토큰 저장
        self._save_token()

        return self.access_token

    def get_headers(self, tr_id: str) -> dict:
        """
        API 호출용 공통 헤더 생성

        Args:
            tr_id: 거래ID (API마다 다름)

        Returns:
            헤더 딕셔너리
        """
        return {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.get_access_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id
        }

    def get_account_info(self) -> tuple:
        """
        계좌번호 정보 반환

        Returns:
            (계좌번호 앞 8자리, 계좌번호 뒤 2자리)
        """
        if not self.account_no:
            raise ValueError("KIS_ACCOUNT_NO 환경변수가 설정되지 않았습니다.")

        parts = self.account_no.split("-")
        if len(parts) != 2:
            raise ValueError("계좌번호 형식이 올바르지 않습니다. (예: 12345678-01)")

        return parts[0], parts[1]

    def validate_credentials(self) -> bool:
        """API 키 유효성 검증"""
        if not self.app_key:
            print("Error: KIS_APP_KEY 환경변수가 설정되지 않았습니다.")
            return False
        if not self.app_secret:
            print("Error: KIS_APP_SECRET 환경변수가 설정되지 않았습니다.")
            return False
        if not self.account_no:
            print("Error: KIS_ACCOUNT_NO 환경변수가 설정되지 않았습니다.")
            return False
        return True


# 싱글톤 인스턴스 (모의투자 기본)
_auth_instance = None


def get_auth(is_virtual: bool = True) -> KISAuth:
    """
    인증 인스턴스 반환 (싱글톤)

    Args:
        is_virtual: True=모의투자, False=실전투자
    """
    global _auth_instance

    if _auth_instance is None or _auth_instance.is_virtual != is_virtual:
        _auth_instance = KISAuth(is_virtual=is_virtual)

    return _auth_instance
