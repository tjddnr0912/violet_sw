#!/usr/bin/env python3
"""
빗썸 API 서명 생성 테스트
다양한 방식을 시도해서 올바른 서명 방식을 찾습니다.
"""

import base64
import hashlib
import hmac
import time
import urllib.parse
import config

def test_signature_method_1(endpoint, parameters, nonce, secret_key):
    """방법 1: 기본 방식"""
    query_string = urllib.parse.urlencode(parameters)
    message = endpoint + chr(0) + query_string + chr(0) + nonce
    secret_key_bytes = base64.b64decode(secret_key)
    signature = base64.b64encode(
        hmac.new(secret_key_bytes, message.encode('utf-8'), hashlib.sha512).digest()
    ).decode('utf-8')
    return signature

def test_signature_method_2(endpoint, parameters, nonce, secret_key):
    """방법 2: 파라미터 정렬"""
    sorted_params = sorted(parameters.items())
    query_string = urllib.parse.urlencode(sorted_params)
    message = endpoint + chr(0) + query_string + chr(0) + nonce
    secret_key_bytes = base64.b64decode(secret_key)
    signature = base64.b64encode(
        hmac.new(secret_key_bytes, message.encode('utf-8'), hashlib.sha512).digest()
    ).decode('utf-8')
    return signature

def test_signature_method_3(endpoint, parameters, nonce, secret_key):
    """방법 3: 엔드포인트 없이"""
    query_string = urllib.parse.urlencode(parameters)
    message = query_string + chr(0) + nonce
    secret_key_bytes = base64.b64decode(secret_key)
    signature = base64.b64encode(
        hmac.new(secret_key_bytes, message.encode('utf-8'), hashlib.sha512).digest()
    ).decode('utf-8')
    return signature

def test_signature_method_4(endpoint, parameters, nonce, secret_key):
    """방법 4: 다른 구분자"""
    query_string = urllib.parse.urlencode(parameters)
    message = endpoint + "&" + query_string + "&" + nonce
    secret_key_bytes = base64.b64decode(secret_key)
    signature = base64.b64encode(
        hmac.new(secret_key_bytes, message.encode('utf-8'), hashlib.sha512).digest()
    ).decode('utf-8')
    return signature

def main():
    print("🔍 빗썸 API 서명 방식 테스트")
    print("=" * 50)

    # 테스트 데이터 (잔고 조회 기능 비활성화로 주문 조회로 변경)
    endpoint = "/info/orders"
    parameters = {
        'endpoint': '/info/orders',
        'order_currency': 'BTC',
        'payment_currency': 'KRW'
    }
    nonce = str(int(time.time() * 1000))
    secret_key = config.BITHUMB_SECRET_KEY

    if secret_key == "YOUR_SECRET_KEY":
        print("❌ Secret Key가 설정되지 않았습니다.")
        return

    print(f"엔드포인트: {endpoint}")
    print(f"파라미터: {parameters}")
    print(f"Nonce: {nonce}")
    print(f"Secret Key: {secret_key[:10]}...")
    print()

    # 다양한 방법으로 서명 생성
    methods = [
        ("방법 1: 기본 방식", test_signature_method_1),
        ("방법 2: 파라미터 정렬", test_signature_method_2),
        ("방법 3: 엔드포인트 없이", test_signature_method_3),
        ("방법 4: 다른 구분자", test_signature_method_4),
    ]

    for method_name, method_func in methods:
        try:
            signature = method_func(endpoint, parameters, nonce, secret_key)
            print(f"{method_name}:")
            print(f"  서명: {signature[:50]}...")
            print()
        except Exception as e:
            print(f"{method_name}: 오류 - {e}")
            print()

if __name__ == "__main__":
    main()