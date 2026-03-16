import requests
import pandas as pd
import hashlib
import hmac
import base64
import time
import urllib.parse
import logging
from typing import Optional, Dict, Any

# 빗썸 API URL
PUBLIC_URL = "https://api.bithumb.com/public"
PRIVATE_URL = "https://api.bithumb.com"

# Timeout settings (connect_timeout, read_timeout) in seconds
# - connect_timeout: Time to establish connection (DNS + TCP handshake + SSL)
# - read_timeout: Time to wait for server response after connection established
API_TIMEOUT_PUBLIC = (5, 30)   # Public API: 5s connect, 30s read
API_TIMEOUT_PRIVATE = (5, 15)  # Private API: 5s connect, 15s read

class BithumbAPI:
    def __init__(self, connect_key: str = None, secret_key: str = None):
        self.connect_key = connect_key
        self.secret_key = secret_key
        self.logger = logging.getLogger(__name__)

        # FIX: Add connection pooling for 20-50ms faster requests
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=3
        )
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)

        # API 키 유효성 초기 검증
        if connect_key and secret_key:
            self._validate_api_keys()

    def _validate_api_keys(self) -> bool:
        """API 키 유효성 검증"""
        try:
            # 1. 기본 존재 여부 확인
            if not self.connect_key or not self.secret_key:
                self.logger.error("API 키가 설정되지 않았습니다.")
                return False

            # 2. 기본값 확인
            if self.connect_key in ["YOUR_CONNECT_KEY", "your_connect_key"]:
                self.logger.error("Connect Key가 기본값으로 설정되어 있습니다.")
                return False

            if self.secret_key in ["YOUR_SECRET_KEY", "your_secret_key"]:
                self.logger.error("Secret Key가 기본값으로 설정되어 있습니다.")
                return False

            # 3. 길이 검증
            if len(self.connect_key) < 20:
                self.logger.error(f"Connect Key 길이가 너무 짧습니다: {len(self.connect_key)}")
                return False

            if len(self.secret_key) < 20:
                self.logger.error(f"Secret Key 길이가 너무 짧습니다: {len(self.secret_key)}")
                return False

            # 4. 형식 검증 (영숫자만 허용)
            import re
            if not re.match(r'^[a-zA-Z0-9]+$', self.connect_key):
                self.logger.error("Connect Key에 유효하지 않은 문자가 포함되어 있습니다.")
                return False

            self.logger.debug("API 키 검증 완료")
            return True

        except Exception as e:
            self.logger.error(f"API 키 검증 중 오류: {e}")
            return False

    def _validate_secret_key(self) -> bool:
        """Secret Key 추가 검증"""
        try:
            if not self.secret_key or len(self.secret_key) < 20:
                return False

            # Base64 디코딩 테스트 (32자리가 아닌 경우)
            if len(self.secret_key) != 32:
                try:
                    base64.b64decode(self.secret_key)
                except Exception:
                    return False

            return True
        except Exception:
            return False

    def _get_signature(self, endpoint: str, parameters: Dict[str, Any], nonce: str) -> bytes:
        """빗썸 API 서명 생성 (pybithumb 방식)"""
        if not self.secret_key:
            raise ValueError("Secret key is required for private API calls")

        try:
            # 1. 파라미터는 이미 endpoint를 포함하고 있음 (pybithumb 방식)
            # 2. URL 인코딩
            query_string = urllib.parse.urlencode(parameters)

            # 3. 서명 메시지 구성: endpoint + chr(0) + query_string + chr(0) + nonce
            message = endpoint + chr(0) + query_string + chr(0) + nonce

            # 4. Secret Key를 UTF-8로 인코딩
            secret_key_bytes = self.secret_key.encode('utf-8')

            # 5. HMAC-SHA512 서명 생성 (pybithumb 방식: hexdigest를 다시 인코딩!)
            h = hmac.new(secret_key_bytes, message.encode('utf-8'), hashlib.sha512)
            signature = base64.b64encode(h.hexdigest().encode('utf-8'))

            # 디버깅 출력
            self.logger.debug(f"🔐 빗썸 API 서명 생성:")
            self.logger.debug(f"   📍 Endpoint: {endpoint}")
            self.logger.debug(f"   📝 Parameters: {parameters}")
            self.logger.debug(f"   🔗 Query String: {query_string}")
            self.logger.debug(f"   📋 Message: {repr(message)}")
            self.logger.debug(f"   🔒 Signature: {signature[:50]}...")

            return signature

        except Exception as e:
            self.logger.error(f"❌ 서명 생성 오류: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _make_request(self, url: str, endpoint: str = None, parameters: Dict[str, Any] = None, is_private: bool = False) -> Optional[Dict]:
        """API 요청 실행"""
        try:
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}

            if is_private:
                # API 키 검증 실패 시 즉시 반환
                if not self._validate_api_keys():
                    self.logger.error("API 키 검증 실패로 요청을 중단합니다.")
                    return None

                # 빗썸 API용 Nonce - 밀리초 단위 (표준)
                nonce = str(int(time.time() * 1000))
                if parameters is None:
                    parameters = {}

                # endpoint를 파라미터에 추가 (pybithumb 방식)
                parameters['endpoint'] = endpoint

                # 서명 생성
                try:
                    signature = self._get_signature(endpoint, parameters, nonce)
                except Exception as e:
                    self.logger.error(f"서명 생성 실패: {e}")
                    return None

                # API 키를 bytes로 변환 (pybithumb 방식)
                connect_key_bytes = self.connect_key.encode('utf-8')

                # HTTP 헤더 구성 (pybithumb 방식)
                headers = {
                    'Api-Key': connect_key_bytes,
                    'Api-Sign': signature,
                    'Api-Nonce': nonce,
                }

                # 디버깅 정보
                print(f"\n🌐 HTTP 요청 정보:")
                print(f"   📡 URL: {url}")
                print(f"   🔑 API Key: {self.connect_key[:10]}...")
                print(f"   ⏰ Nonce: {nonce}")
                print(f"   📦 Request Data: {parameters}")

                # POST 요청 (dict를 그대로 전달 - requests가 자동으로 form-urlencoded로 변환)
                # FIX: Use session for connection pooling + separate connect/read timeout
                response = self.session.post(url, data=parameters, headers=headers, timeout=API_TIMEOUT_PRIVATE)

                # 응답 정보 상세 출력
                print(f"📡 API 응답 정보:")
                print(f"   Status Code: {response.status_code}")
                print(f"   Response Headers: {dict(response.headers)}")

                if response.status_code != 200:
                    print(f"❌ HTTP 오류: {response.status_code}")
                    print(f"   응답 내용: {response.text}")

                # JSON 파싱 시도
                try:
                    result = response.json()
                    print(f"   응답 JSON: {result}")
                except ValueError as e:
                    print(f"❌ JSON 파싱 실패: {e}")
                    print(f"   Raw Response: {response.text}")
                    return None

            else:
                # FIX: Use session for connection pooling + separate connect/read timeout
                response = self.session.get(url, timeout=API_TIMEOUT_PUBLIC)
                try:
                    result = response.json()
                except ValueError:
                    return None

            # 빗썸 API 응답 상태 확인
            if isinstance(result, dict):
                status = result.get('status')
                if status != '0000':
                    error_msg = result.get('message', 'Unknown API error')
                    print(f"❌ 빗썸 API 오류:")
                    print(f"   오류 코드: {status}")
                    print(f"   오류 메시지: {error_msg}")

                    # 일반적인 오류 코드 해석
                    error_solutions = {
                        '5100': '잘못된 API 키 - API 키를 다시 확인하세요',
                        '5200': 'API 서명 오류 - Secret Key를 확인하세요',
                        '5300': 'Nonce 값 오류 - 시스템 시간을 확인하세요',
                        '5400': 'HTTP Method 오류',
                        '5500': '요청 시간 초과 - 네트워크를 확인하세요',
                        '5600': 'API 권한 없음 - 빗썸에서 API 권한을 확인하세요'
                    }

                    if status in error_solutions:
                        print(f"   💡 해결방법: {error_solutions[status]}")

            return result

        except requests.exceptions.RequestException as e:
            self.logger.error(f"HTTP Request Error: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            return None


    def place_buy_order(self, order_currency: str, payment_currency: str = "KRW", units: float = None, price: int = None, type_order: str = "market") -> Optional[Dict]:
        """매수 주문 (Bithumb API 1.2.0)"""
        # 사전 검증
        if not self._validate_api_keys():
            self.logger.error("매수 주문 실패: API 키 검증 실패")
            return None

        # 빗썸 API 1.2.0: 시장가/지정가 별도 엔드포인트 사용
        if type_order == "market":
            endpoint = "/trade/market_buy"
        else:
            endpoint = "/trade/place"  # 지정가 주문

        url = PRIVATE_URL + endpoint

        # 빗썸 API 1.2.0 파라미터 구조
        parameters = {
            'order_currency': order_currency,
            'payment_currency': payment_currency
        }

        # 시장가 매수: units (코인 수량) 필수
        if type_order == "market":
            if units:
                parameters['units'] = str(units)
            else:
                self.logger.error("시장가 매수: units 파라미터 필수")
                return None
        # 지정가 주문
        else:
            parameters['type'] = type_order
            parameters['units'] = str(units)
            parameters['price'] = str(price)

        return self._make_request(url, endpoint, parameters, is_private=True)

    def place_sell_order(self, order_currency: str, payment_currency: str = "KRW", units: float = None, price: int = None, type_order: str = "market") -> Optional[Dict]:
        """매도 주문 (Bithumb API 1.2.0)"""
        # 사전 검증
        if not self._validate_api_keys():
            self.logger.error("매도 주문 실패: API 키 검증 실패")
            return None

        # 빗썸 API 1.2.0: 시장가/지정가 별도 엔드포인트 사용
        if type_order == "market":
            endpoint = "/trade/market_sell"
        else:
            endpoint = "/trade/place"  # 지정가 주문

        url = PRIVATE_URL + endpoint

        # 빗썸 API 1.2.0 파라미터 구조
        parameters = {
            'order_currency': order_currency,
            'payment_currency': payment_currency
        }

        # 시장가 매도: units (코인 수량) 필수
        if type_order == "market":
            if units:
                parameters['units'] = str(units)
            else:
                self.logger.error("시장가 매도: units 파라미터 필수")
                return None
        # 지정가 주문
        else:
            parameters['type'] = type_order
            parameters['units'] = str(units)
            parameters['price'] = str(price)

        return self._make_request(url, endpoint, parameters, is_private=True)

    def get_orders(self, order_currency: str, payment_currency: str = "KRW") -> Optional[Dict]:
        """미체결 주문 조회"""
        # 사전 검증
        if not self._validate_api_keys():
            self.logger.error("미체결 주문 조회 실패: API 키 검증 실패")
            return None

        endpoint = "/info/orders"
        url = PRIVATE_URL + endpoint
        parameters = {
            'order_currency': order_currency,
            'payment_currency': payment_currency
        }

        return self._make_request(url, endpoint, parameters, is_private=True)

    def get_user_transactions(self, order_currency: str, payment_currency: str = "KRW") -> Optional[Dict]:
        """거래 내역 조회"""
        # 사전 검증
        if not self._validate_api_keys():
            self.logger.error("거래 내역 조회 실패: API 키 검증 실패")
            return None

        endpoint = "/info/user_transactions"
        url = PRIVATE_URL + endpoint
        parameters = {
            'order_currency': order_currency,
            'payment_currency': payment_currency
        }

        return self._make_request(url, endpoint, parameters, is_private=True)

    def get_balance(self, currency: str = "ALL") -> Optional[Dict]:
        """잔고 조회"""
        # 사전 검증
        if not self._validate_api_keys():
            self.logger.error("잔고 조회 실패: API 키 검증 실패")
            return None

        endpoint = "/info/balance"
        url = PRIVATE_URL + endpoint
        parameters = {
            'currency': currency
        }

        return self._make_request(url, endpoint, parameters, is_private=True)

def get_candlestick(ticker: str, interval: str = "24h") -> pd.DataFrame:
    """
    빗썸 API를 통해 특정 코인의 시세 정보(Candlestick)를 가져옵니다.

    :param ticker: 코인 티커 (예: "BTC")
    :param interval: 차트 간격 (예: "1h", "6h", "12h", "24h")
    :return: 시세 정보가 담긴 pandas DataFrame. 실패 시 None 반환.
             컬럼: [time, open, close, high, low, volume]
    """
    try:
        # API 요청 URL 생성
        url = f"{PUBLIC_URL}/candlestick/{ticker}_KRW/{interval}"
        # Use isolated session to prevent connection pool contamination
        # Each request gets its own session that is properly closed after use
        with requests.Session() as session:
            response = session.get(url, timeout=API_TIMEOUT_PUBLIC)
            response.raise_for_status()  # HTTP 에러 발생 시 예외 발생
            data = response.json()

        if data.get("status") == "0000":
            # API 응답이 성공적일 경우 DataFrame으로 변환
            df = pd.DataFrame(data['data'], columns=['time', 'open', 'close', 'high', 'low', 'volume'])
            # 데이터 타입 변환
            df = df.astype({
                'time': 'datetime64[ms]',
                'open': 'float',
                'close': 'float',
                'high': 'float',
                'low': 'float',
                'volume': 'float'
            })
            # 시간을 인덱스로 설정
            df.set_index('time', inplace=True)
            return df
        else:
            print(f"API Error: {data.get('message')}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"HTTP Request Error: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

def get_orderbook(ticker: str, count: int = 30) -> Optional[Dict]:
    """
    Fetch orderbook data from Bithumb public API.

    Endpoint: GET https://api.bithumb.com/public/orderbook/{ticker}_KRW

    Args:
        ticker: Coin symbol (e.g., 'BTC')
        count: Number of orderbook levels to fetch (1-30, default 30)

    Returns:
        Dictionary with keys:
            'timestamp': str,
            'order_currency': str,
            'payment_currency': 'KRW',
            'bids': [{'price': str, 'quantity': str}, ...],
            'asks': [{'price': str, 'quantity': str}, ...]
        or None on error
    """
    try:
        count = max(1, min(30, count))  # Clamp to valid range
        url = f"{PUBLIC_URL}/orderbook/{ticker}_KRW"
        params = {'count': count}
        # Use isolated session to prevent connection pool contamination
        with requests.Session() as session:
            response = session.get(url, params=params, timeout=API_TIMEOUT_PUBLIC)
            response.raise_for_status()
            data = response.json()

        if data.get("status") == "0000":
            return data['data']
        else:
            print(f"Orderbook API Error: {data.get('message')}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"HTTP Request Error (orderbook): {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred (orderbook): {e}")
        return None


def get_ticker(ticker: str = "ALL") -> Optional[Dict]:
    """
    현재가 정보 조회
    """
    try:
        url = f"{PUBLIC_URL}/ticker/{ticker}_KRW"
        # Use isolated session to prevent connection pool contamination
        with requests.Session() as session:
            response = session.get(url, timeout=API_TIMEOUT_PUBLIC)
            response.raise_for_status()
            data = response.json()

        if data.get("status") == "0000":
            return data['data']
        else:
            print(f"API Error: {data.get('message')}")
            return None

    except Exception as e:
        print(f"Error getting ticker: {e}")
        return None

# # 예제: 비트코인 24시간 봉 데이터 가져오기
# if __name__ == "__main__":
#     btc_df = get_candlestick("BTC")
#     if btc_df is not None:
#         print("BTC 24시간 차트 데이터 (최근 5개)")
#         print(btc_df.tail())
