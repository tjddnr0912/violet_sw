#!/usr/bin/env python3
"""
빗썸 API 단순 테스트
가장 기본적인 방식으로 API 호출을 시도합니다.
"""

import base64
import hashlib
import hmac
import time
import urllib.parse
import requests
import config

def simple_bithumb_test():
    """단순한 빗썸 API 테스트"""
    print("🔍 빗썸 API 단순 테스트")
    print("=" * 50)

    # API 키 확인
    connect_key = config.BITHUMB_CONNECT_KEY
    secret_key = config.BITHUMB_SECRET_KEY

    if connect_key == "YOUR_CONNECT_KEY" or secret_key == "YOUR_SECRET_KEY":
        print("❌ API 키가 설정되지 않았습니다.")
        return False

    # 테스트 파라미터 (잔고 조회 기능 비활성화로 주문 조회로 변경)
    endpoint = "/info/orders"
    order_currency = "BTC"
    payment_currency = "KRW"
    nonce = str(int(time.time() * 1000))

    # API 키 길이 검증
    print(f"📋 API 키 검증:")
    print(f"   Connect Key 길이: {len(connect_key)} (필요: 32)")
    print(f"   Secret Key 길이: {len(secret_key)}")

    if len(connect_key) != 32:
        print(f"❌ Connect Key 길이 오류! 빗썸은 32자리 API Key를 사용합니다.")
        print(f"   현재: {len(connect_key)}자리, 필요: 32자리")
        return False

    # Secret Key 형식 검증
    if len(secret_key) == 32:
        print("✅ Secret Key 32자리 형식 (빗썸 표준)")
    else:
        try:
            base64.b64decode(secret_key)
            print("✅ Secret Key Base64 형식 검증 성공")
        except Exception as e:
            print(f"❌ Secret Key 형식 오류: {e}")
            return False

    print(f"\n📋 테스트 정보:")
    print(f"   Endpoint: {endpoint}")
    print(f"   Order Currency: {order_currency}")
    print(f"   Payment Currency: {payment_currency}")
    print(f"   Nonce: {nonce}")
    print(f"   Connect Key: {connect_key[:10]}...")
    print(f"   Secret Key: {secret_key[:10]}...")

    # 방법 1: 최소한의 파라미터로 시도
    try:
        print(f"\n🔬 방법 1: 최소 파라미터")

        # 파라미터 구성
        params = {
            "endpoint": endpoint,
            "order_currency": order_currency,
            "payment_currency": payment_currency
        }

        # 쿼리 스트링 생성
        query_string = urllib.parse.urlencode(params)
        print(f"   Query String: {query_string}")

        # 서명 데이터 구성
        message = endpoint + chr(0) + query_string + chr(0) + nonce
        print(f"   Message: {repr(message)}")

        # 서명 생성 (32자리 Secret Key는 직접 사용)
        if len(secret_key) == 32:
            secret_bytes = secret_key.encode('utf-8')
            print(f"   Secret Key Type: 32자리 직접 사용")
        else:
            secret_bytes = base64.b64decode(secret_key)
            print(f"   Secret Key Type: Base64 디코딩")

        signature = base64.b64encode(
            hmac.new(secret_bytes, message.encode('utf-8'), hashlib.sha512).digest()
        ).decode('utf-8')
        print(f"   Signature: {signature[:30]}...")

        # 헤더 구성
        headers = {
            'Api-Key': connect_key,
            'Api-Sign': signature,
            'Api-Nonce': nonce,
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        # 요청 실행 (endpoint 제외하고 전송)
        request_data = {"order_currency": order_currency, "payment_currency": payment_currency}
        url = f"https://api.bithumb.com{endpoint}"

        print(f"   URL: {url}")
        print(f"   Request Data: {request_data}")
        print(f"   Headers: {headers}")

        response = requests.post(url, data=request_data, headers=headers, timeout=10)

        print(f"\n📡 응답:")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text}")

        if response.status_code == 200:
            result = response.json()
            if result.get('status') == '0000':
                print("✅ 성공!")
                return True
            else:
                print(f"❌ API 오류: {result.get('status')} - {result.get('message')}")

    except Exception as e:
        print(f"❌ 오류: {e}")

    # 방법 2: 다른 파라미터 순서
    try:
        print(f"\n🔬 방법 2: 다른 파라미터 순서")

        # 파라미터를 다른 순서로
        params = {
            "order_currency": order_currency,
            "payment_currency": payment_currency,
            "endpoint": endpoint
        }

        query_string = urllib.parse.urlencode(params)
        print(f"   Query String: {query_string}")

        message = endpoint + chr(0) + query_string + chr(0) + nonce
        print(f"   Message: {repr(message)}")

        # 서명 생성 (32자리 Secret Key는 직접 사용)
        if len(secret_key) == 32:
            secret_bytes = secret_key.encode('utf-8')
            print(f"   Secret Key Type: 32자리 직접 사용")
        else:
            secret_bytes = base64.b64decode(secret_key)
            print(f"   Secret Key Type: Base64 디코딩")

        signature = base64.b64encode(
            hmac.new(secret_bytes, message.encode('utf-8'), hashlib.sha512).digest()
        ).decode('utf-8')
        print(f"   Signature: {signature[:30]}...")

        headers = {
            'Api-Key': connect_key,
            'Api-Sign': signature,
            'Api-Nonce': nonce,
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        request_data = {"order_currency": order_currency, "payment_currency": payment_currency}

        response = requests.post(url, data=request_data, headers=headers, timeout=10)

        print(f"\n📡 응답:")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text}")

        if response.status_code == 200:
            result = response.json()
            if result.get('status') == '0000':
                print("✅ 성공!")
                return True
            else:
                print(f"❌ API 오류: {result.get('status')} - {result.get('message')}")

    except Exception as e:
        print(f"❌ 오류: {e}")

    return False

if __name__ == "__main__":
    simple_bithumb_test()