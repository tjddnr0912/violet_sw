#!/usr/bin/env python3
"""
Bithumb API 인증 수정된 버전
공식 문서를 기반으로 정확한 서명 생성 방법을 구현합니다.
"""

import base64
import hashlib
import hmac
import time
import urllib.parse
import requests
import config

def create_bithumb_signature_v2(endpoint, parameters, nonce, secret_key):
    """
    Bithumb API 서명 생성 (수정된 버전)
    공식 문서 기준으로 다시 구현
    """
    try:
        # 1. 파라미터를 정렬하지 않고 원본 순서 유지
        # endpoint는 서명용으로만 사용, 실제 요청에는 포함하지 않음
        sign_params = parameters.copy()

        # 2. URL 인코딩 (safe='' 사용)
        query_string = urllib.parse.urlencode(sign_params, safe='')

        # 3. 메시지 구성: endpoint + '\0' + query_string + '\0' + nonce
        message = endpoint + '\0' + query_string + '\0' + nonce

        print(f"🔐 서명 생성 정보:")
        print(f"   Parameters: {sign_params}")
        print(f"   Query String: {query_string}")
        print(f"   Message: {repr(message)}")

        # 4. Secret Key 처리 (32자리는 직접 UTF-8 인코딩)
        if len(secret_key) == 32:
            secret_bytes = secret_key.encode('utf-8')
            print(f"   Secret Key: 32자리 직접 사용")
        else:
            # Base64 디코딩 시도
            try:
                secret_bytes = base64.b64decode(secret_key)
                print(f"   Secret Key: Base64 디코딩")
            except:
                secret_bytes = secret_key.encode('utf-8')
                print(f"   Secret Key: Base64 디코딩 실패, UTF-8 사용")

        # 5. HMAC-SHA512 서명 생성
        signature = base64.b64encode(
            hmac.new(secret_bytes, message.encode('utf-8'), hashlib.sha512).digest()
        ).decode('utf-8')

        print(f"   Signature: {signature[:50]}...")

        return signature

    except Exception as e:
        print(f"❌ 서명 생성 오류: {e}")
        raise

def test_balance_api_v2():
    """잔고 API 테스트 (수정된 버전)"""
    print("🔍 Bithumb 잔고 API 테스트 (수정된 버전)")
    print("=" * 60)

    connect_key = config.BITHUMB_CONNECT_KEY
    secret_key = config.BITHUMB_SECRET_KEY

    if connect_key == "YOUR_CONNECT_KEY" or secret_key == "YOUR_SECRET_KEY":
        print("❌ API 키가 설정되지 않았습니다.")
        return False

    # 기본 설정
    endpoint = "/info/balance"
    nonce = str(int(time.time() * 1000))

    # 요청 파라미터 (endpoint는 서명용으로만)
    parameters = {
        "currency": "ALL"
    }

    print(f"\n📋 요청 정보:")
    print(f"   Endpoint: {endpoint}")
    print(f"   Nonce: {nonce}")
    print(f"   Parameters: {parameters}")
    print(f"   Connect Key: {connect_key[:10]}...")
    print(f"   Secret Key: {secret_key[:10]}...")

    try:
        # 서명 생성 (endpoint 포함)
        signature = create_bithumb_signature_v2(endpoint, parameters, nonce, secret_key)

        # HTTP 헤더 구성
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Api-Key': connect_key,
            'Api-Sign': signature,
            'Api-Nonce': nonce
        }

        # API 요청
        url = f"https://api.bithumb.com{endpoint}"

        print(f"\n🌐 HTTP 요청:")
        print(f"   URL: {url}")
        print(f"   Headers: {headers}")
        print(f"   Data: {parameters}")

        response = requests.post(url, data=parameters, headers=headers, timeout=15)

        print(f"\n📡 응답:")
        print(f"   Status Code: {response.status_code}")
        print(f"   Response Headers: {dict(response.headers)}")
        print(f"   Response Text: {response.text}")

        if response.status_code == 200:
            try:
                result = response.json()
                status = result.get('status')

                if status == '0000':
                    print(f"✅ 성공!")

                    # 잔고 정보 출력
                    data = result.get('data', {})
                    krw_available = float(data.get('available_krw', 0))
                    krw_total = float(data.get('total_krw', 0))

                    print(f"💰 KRW 사용가능: {krw_available:,.0f}원")
                    print(f"💼 KRW 총액: {krw_total:,.0f}원")

                    return True
                else:
                    print(f"❌ API 오류: {status} - {result.get('message')}")

                    # 오류 코드별 해결방법
                    error_solutions = {
                        '5100': 'API 키 오류 - Connect Key 확인 필요',
                        '5200': 'API 서명 오류 - Secret Key 또는 서명 로직 확인',
                        '5300': 'Nonce 오류 - 시스템 시간 확인',
                        '5400': 'HTTP Method 오류',
                        '5500': '요청 시간 초과',
                        '5600': 'API 권한 없음'
                    }

                    if status in error_solutions:
                        print(f"💡 해결방법: {error_solutions[status]}")

                    return False

            except ValueError as e:
                print(f"❌ JSON 파싱 오류: {e}")
                return False
        else:
            print(f"❌ HTTP 오류: {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ 요청 중 오류: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_balance_api_v2()

    print(f"\n{'='*60}")
    if success:
        print("🎉 API 테스트 성공!")
    else:
        print("❌ API 테스트 실패!")
        print("\n🔧 추가 디버깅 팁:")
        print("1. API 키가 올바른지 빗썸 홈페이지에서 다시 확인")
        print("2. API 권한이 '잔고조회' 포함되어 있는지 확인")
        print("3. 시스템 시간이 정확한지 확인")
        print("4. 방화벽이나 VPN 설정 확인")