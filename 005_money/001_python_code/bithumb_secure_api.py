#!/usr/bin/env python3
"""
보안 강화된 빗썸 API 클래스
모든 보안 기능이 통합된 최종 구현체
"""

import requests
import logging
import time
import json
from typing import Optional, Dict, Any
from datetime import datetime

from secure_api_manager import SecureAPIKeyManager
from secure_signature import SecureSignatureGenerator
from nonce_manager import NonceManager
from security_monitor import SecurityMonitor

class BithumbSecureAPI:
    def __init__(self, connect_key: str = None, secret_key: str = None):
        self.logger = logging.getLogger(__name__)

        # 보안 컴포넌트 초기화
        if connect_key and secret_key:
            # 직접 제공된 키 사용
            self.connect_key = connect_key
            self.secret_key = secret_key
        else:
            # 보안 키 매니저를 통해 로드
            key_manager = SecureAPIKeyManager()
            self.connect_key = key_manager.connect_key
            self.secret_key = key_manager.secret_key

        self.signature_generator = SecureSignatureGenerator()
        self.nonce_manager = NonceManager()
        self.security_monitor = SecurityMonitor()

        # API 설정
        self.base_url = "https://api.bithumb.com"
        self.timeout = 15
        self.max_retries = 3

        self.logger.info("보안 강화된 빗썸 API 초기화 완료")

    def _make_secure_request(self, endpoint: str, parameters: Dict[str, Any] = None,
                           is_private: bool = False) -> Optional[Dict]:
        """보안 강화된 API 요청"""
        if parameters is None:
            parameters = {}

        # 보안 검사
        if not self._pre_request_security_check(endpoint, parameters):
            return None

        try:
            url = f"{self.base_url}{endpoint}"
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}

            if is_private:
                # 인증 헤더 생성
                auth_headers = self._create_auth_headers(endpoint, parameters)
                if not auth_headers:
                    return None
                headers.update(auth_headers)

            # 요청 실행 (재시도 로직 포함)
            response = self._execute_request_with_retry(url, parameters, headers)
            if not response:
                return None

            # 응답 보안 검증
            return self._validate_and_process_response(endpoint, response, parameters)

        except Exception as e:
            self.logger.error(f"API 요청 중 예외 발생: {e}")
            self.security_monitor._record_security_event(
                endpoint, 'REQUEST_EXCEPTION', 'MEDIUM',
                {'error': str(e)}
            )
            return None

    def _pre_request_security_check(self, endpoint: str, parameters: Dict) -> bool:
        """요청 전 보안 검사"""
        # 1. 긴급 정지 상태 확인
        if self.security_monitor.emergency_stop:
            self.logger.warning("긴급 정지 상태로 인해 요청이 차단됩니다.")
            return False

        # 2. API 호출 빈도 제한 확인
        if not self.security_monitor.check_rate_limit(endpoint):
            self.logger.warning(f"API 호출 빈도 제한 초과: {endpoint}")
            return False

        # 3. 의심스러운 패턴 감지
        if not self.security_monitor.detect_suspicious_patterns(endpoint, parameters):
            self.logger.warning(f"의심스러운 거래 패턴 감지: {endpoint}")
            return False

        return True

    def _create_auth_headers(self, endpoint: str, parameters: Dict) -> Optional[Dict[str, str]]:
        """인증 헤더 생성"""
        try:
            # Nonce 생성
            nonce = self.nonce_manager.generate_nonce()

            # 서명 생성
            signature, _ = self.signature_generator.create_signature(
                endpoint, parameters, self.secret_key
            )

            # 헤더 구성
            auth_headers = {
                'Api-Key': self.connect_key,
                'Api-Sign': signature,
                'Api-Nonce': nonce,
                'User-Agent': 'SecureTradingBot/2.0 (Security Enhanced)'
            }

            return auth_headers

        except Exception as e:
            self.logger.error(f"인증 헤더 생성 실패: {e}")
            self.security_monitor._record_security_event(
                endpoint, 'AUTH_HEADER_FAILURE', 'HIGH',
                {'error': str(e)}
            )
            return None

    def _execute_request_with_retry(self, url: str, data: Dict, headers: Dict) -> Optional[requests.Response]:
        """재시도 로직이 포함된 요청 실행"""
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    url, data=data, headers=headers,
                    timeout=self.timeout
                )

                # HTTP 상태 코드 확인
                if response.status_code == 200:
                    return response
                elif response.status_code == 429:  # Too Many Requests
                    wait_time = 2 ** attempt  # 지수 백오프
                    self.logger.warning(f"API 제한 도달, {wait_time}초 대기 후 재시도")
                    time.sleep(wait_time)
                else:
                    self.logger.error(f"HTTP 오류: {response.status_code} - {response.text}")

            except requests.exceptions.Timeout:
                self.logger.warning(f"요청 시간 초과 (시도 {attempt + 1}/{self.max_retries})")
                last_exception = "Timeout"
            except requests.exceptions.ConnectionError:
                self.logger.warning(f"연결 오류 (시도 {attempt + 1}/{self.max_retries})")
                last_exception = "ConnectionError"
            except Exception as e:
                self.logger.error(f"요청 실행 오류: {e}")
                last_exception = str(e)

            # 재시도 전 대기
            if attempt < self.max_retries - 1:
                time.sleep(1)

        self.logger.error(f"모든 재시도 실패. 마지막 오류: {last_exception}")
        return None

    def _validate_and_process_response(self, endpoint: str, response: requests.Response,
                                     request_params: Dict) -> Optional[Dict]:
        """응답 검증 및 처리"""
        try:
            # JSON 파싱
            response_data = response.json()

            # 보안 모니터링
            is_valid = self.security_monitor.check_api_response(
                endpoint, response_data, request_params
            )

            if not is_valid:
                return None

            # 성공 응답 처리
            if response_data.get('status') == '0000':
                self.logger.debug(f"API 요청 성공: {endpoint}")
                return response_data

            # 오류 응답 처리
            error_code = response_data.get('status', 'unknown')
            error_message = response_data.get('message', 'Unknown error')

            self.logger.error(f"API 오류 응답: {error_code} - {error_message}")
            return response_data  # 오류 정보도 반환 (호출자가 처리)

        except json.JSONDecodeError:
            self.logger.error(f"JSON 파싱 실패: {response.text}")
            self.security_monitor._record_security_event(
                endpoint, 'JSON_PARSE_ERROR', 'MEDIUM',
                {'response_text': response.text[:200]}
            )
            return None

    # =============================================================================
    # 공개 API 메서드들
    # =============================================================================

    def get_ticker(self, ticker: str = "ALL") -> Optional[Dict]:
        """현재가 정보 조회 (공개 API)"""
        endpoint = f"/public/ticker/{ticker}_KRW"
        return self._make_secure_request(endpoint, is_private=False)

    def get_candlestick(self, ticker: str, interval: str = "24h") -> Optional[Dict]:
        """캔들스틱 데이터 조회 (공개 API)"""
        endpoint = f"/public/candlestick/{ticker}_KRW/{interval}"
        return self._make_secure_request(endpoint, is_private=False)

    # =============================================================================
    # 거래 API 메서드들 (보안 강화)
    # =============================================================================

    def place_buy_order(self, order_currency: str, payment_currency: str = "KRW",
                       units: float = None, price: int = None,
                       type_order: str = "market") -> Optional[Dict]:
        """매수 주문 (보안 강화)"""
        endpoint = "/trade/place"

        # 거래 파라미터 검증
        if not self._validate_trading_params(order_currency, units, price, type_order):
            return None

        parameters = {
            'order_currency': order_currency,
            'payment_currency': payment_currency,
            'type': type_order
        }

        if type_order == "market":
            if units:
                parameters['units'] = str(units)
            elif price:
                parameters['total'] = str(price)
        else:
            parameters['units'] = str(units)
            parameters['price'] = str(price)

        self.logger.info(f"매수 주문 요청: {order_currency}, {type_order}, units={units}, price={price}")
        return self._make_secure_request(endpoint, parameters, is_private=True)

    def place_sell_order(self, order_currency: str, payment_currency: str = "KRW",
                        units: float = None, price: int = None,
                        type_order: str = "market") -> Optional[Dict]:
        """매도 주문 (보안 강화)"""
        endpoint = "/trade/place"

        # 거래 파라미터 검증
        if not self._validate_trading_params(order_currency, units, price, type_order):
            return None

        parameters = {
            'order_currency': order_currency,
            'payment_currency': payment_currency,
            'type': type_order
        }

        if type_order == "market":
            parameters['units'] = str(units)
        else:
            parameters['units'] = str(units)
            parameters['price'] = str(price)

        self.logger.info(f"매도 주문 요청: {order_currency}, {type_order}, units={units}, price={price}")
        return self._make_secure_request(endpoint, parameters, is_private=True)

    def get_orders(self, order_currency: str, payment_currency: str = "KRW") -> Optional[Dict]:
        """미체결 주문 조회"""
        endpoint = "/info/orders"
        parameters = {
            'order_currency': order_currency,
            'payment_currency': payment_currency
        }
        return self._make_secure_request(endpoint, parameters, is_private=True)

    def get_user_transactions(self, order_currency: str, payment_currency: str = "KRW") -> Optional[Dict]:
        """거래 내역 조회"""
        endpoint = "/info/user_transactions"
        parameters = {
            'order_currency': order_currency,
            'payment_currency': payment_currency
        }
        return self._make_secure_request(endpoint, parameters, is_private=True)

    def _validate_trading_params(self, order_currency: str, units: float,
                                price: int, type_order: str) -> bool:
        """거래 파라미터 보안 검증"""
        # 1. 지원되는 코인인지 확인
        supported_coins = ['BTC', 'ETH', 'XRP', 'ADA', 'DOT', 'LINK', 'LTC', 'BCH', 'EOS', 'TRX']
        if order_currency not in supported_coins:
            self.logger.error(f"지원되지 않는 코인: {order_currency}")
            return False

        # 2. 거래량 한도 확인
        if units and units > 100:  # 예: 최대 100코인
            self.logger.error(f"거래량 한도 초과: {units} > 100")
            self.security_monitor._record_security_event(
                "/trade/place", 'TRADE_LIMIT_EXCEEDED', 'HIGH',
                {'units': units, 'limit': 100}
            )
            return False

        # 3. 거래금액 한도 확인
        if price and price > 50000000:  # 예: 최대 5000만원
            self.logger.error(f"거래금액 한도 초과: {price} > 50,000,000")
            self.security_monitor._record_security_event(
                "/trade/place", 'AMOUNT_LIMIT_EXCEEDED', 'HIGH',
                {'price': price, 'limit': 50000000}
            )
            return False

        # 4. 주문 타입 확인
        if type_order not in ['market', 'limit']:
            self.logger.error(f"잘못된 주문 타입: {type_order}")
            return False

        return True

    # =============================================================================
    # 보안 관리 메서드들
    # =============================================================================

    def get_security_status(self) -> Dict[str, Any]:
        """보안 상태 조회"""
        return {
            'security_monitor': self.security_monitor.get_security_status(),
            'nonce_stats': self.nonce_manager.get_nonce_stats(),
            'api_key_masked': f"{self.connect_key[:6]}...{self.connect_key[-4:]}" if self.connect_key else None,
            'timestamp': datetime.now().isoformat()
        }

    def reset_security(self, confirm_token: str) -> bool:
        """보안 상태 초기화"""
        return self.security_monitor.reset_security_state(confirm_token)

    def enable_emergency_stop(self):
        """긴급 정지 활성화"""
        self.security_monitor.emergency_stop = True
        self.logger.critical("긴급 정지가 수동으로 활성화되었습니다.")

    def disable_emergency_stop(self, confirm_token: str) -> bool:
        """긴급 정지 해제"""
        import os
        expected_token = os.getenv('EMERGENCY_STOP_TOKEN', 'default_emergency_token')

        if confirm_token == expected_token:
            self.security_monitor.emergency_stop = False
            self.logger.info("긴급 정지가 해제되었습니다.")
            return True
        else:
            self.logger.warning("긴급 정지 해제 시도 실패: 잘못된 토큰")
            return False