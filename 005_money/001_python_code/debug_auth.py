#!/usr/bin/env python3
"""
Bithumb API 인증 디버그 스크립트
다양한 시그니처 생성 방법을 테스트합니다.
"""

import base64
import hashlib
import hmac
import time
import urllib.parse
import requests
import config

def test_bithumb_auth_methods():
    """다양한 인증 방법 테스트"""
    print("🔍 Bithumb API 인증 방법 테스트")
    print("=" * 60)

    connect_key = config.BITHUMB_CONNECT_KEY
    secret_key = config.BITHUMB_SECRET_KEY

    if connect_key == "YOUR_CONNECT_KEY" or secret_key == "YOUR_SECRET_KEY":
        print("❌ API 키가 설정되지 않았습니다.")
        return

    print(f"🔑 Connect Key: {connect_key[:10]}... (길이: {len(connect_key)})")
    print(f"🔐 Secret Key: {secret_key[:10]}... (길이: {len(secret_key)})")

    endpoint = "/info/balance"
    currency = "ALL"
    nonce = str(int(time.time() * 1000))

    print(f"\n📋 테스트 파라미터:")
    print(f"   Endpoint: {endpoint}")
    print(f"   Currency: {currency}")
    print(f"   Nonce: {nonce}")

    # 방법 1: 표준 Bithumb 방식 (현재 구현)
    test_method_1(connect_key, secret_key, endpoint, currency, nonce)

    # 방법 2: 파라미터 순서 변경
    test_method_2(connect_key, secret_key, endpoint, currency, nonce)

    # 방법 3: Secret Key를 Base64로 처리
    test_method_3(connect_key, secret_key, endpoint, currency, nonce)

def test_method_1(connect_key, secret_key, endpoint, currency, nonce):
    """방법 1: 표준 Bithumb 방식"""
    print(f"\n🧪 방법 1: 표준 Bithumb 방식")
    print("-" * 40)

    try:
        # 파라미터 구성
        params = {
            "endpoint": endpoint,
            "currency": currency
        }

        # 쿼리 스트링 생성
        query_string = urllib.parse.urlencode(params)
        print(f"   Query String: {query_string}")

        # 메시지 구성
        message = endpoint + chr(0) + query_string + chr(0) + nonce
        print(f"   Message: {repr(message)}")

        # Secret Key 처리 (32자리는 직접 사용)
        secret_bytes = secret_key.encode('utf-8')

        # 서명 생성
        signature = base64.b64encode(
            hmac.new(secret_bytes, message.encode('utf-8'), hashlib.sha512).digest()
        ).decode('utf-8')

        print(f"   Signature: {signature[:40]}...")

        # 헤더 구성
        headers = {
            'Api-Key': connect_key,
            'Api-Sign': signature,
            'Api-Nonce': nonce,
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        # 요청 실행
        url = f"https://api.bithumb.com{endpoint}"
        request_data = {"currency": currency}

        response = requests.post(url, data=request_data, headers=headers, timeout=10)

        print(f"   ✅ 응답 상태: {response.status_code}")
        print(f"   📝 응답 내용: {response.text[:100]}...")

        if response.status_code == 200:
            result = response.json()
            if result.get('status') == '0000':
                print(f"   🎉 성공!")
                return True
            else:
                print(f"   ❌ API 오류: {result.get('status')} - {result.get('message')}")

    except Exception as e:
        print(f"   ❌ 오류: {e}")

    return False

def test_method_2(connect_key, secret_key, endpoint, currency, nonce):
    """방법 2: 파라미터를 알파벳 순으로 정렬"""
    print(f"\n🧪 방법 2: 파라미터 알파벳 순 정렬")
    print("-" * 40)

    try:
        # 파라미터를 알파벳 순으로 정렬
        params = [
            ("currency", currency),
            ("endpoint", endpoint)
        ]

        # 쿼리 스트링 생성 (정렬된 순서)
        query_string = urllib.parse.urlencode(params)
        print(f"   Query String: {query_string}")

        # 메시지 구성
        message = endpoint + chr(0) + query_string + chr(0) + nonce
        print(f"   Message: {repr(message)}")

        # Secret Key 처리
        secret_bytes = secret_key.encode('utf-8')

        # 서명 생성
        signature = base64.b64encode(
            hmac.new(secret_bytes, message.encode('utf-8'), hashlib.sha512).digest()
        ).decode('utf-8')

        print(f"   Signature: {signature[:40]}...")

        # 헤더 구성
        headers = {
            'Api-Key': connect_key,
            'Api-Sign': signature,
            'Api-Nonce': nonce,
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        # 요청 실행
        url = f"https://api.bithumb.com{endpoint}"
        request_data = {"currency": currency}

        response = requests.post(url, data=request_data, headers=headers, timeout=10)

        print(f"   ✅ 응답 상태: {response.status_code}")
        print(f"   📝 응답 내용: {response.text[:100]}...")

        if response.status_code == 200:
            result = response.json()
            if result.get('status') == '0000':
                print(f"   🎉 성공!")
                return True
            else:
                print(f"   ❌ API 오류: {result.get('status')} - {result.get('message')}")

    except Exception as e:
        print(f"   ❌ 오류: {e}")

    return False

def test_method_3(connect_key, secret_key, endpoint, currency, nonce):
    """방법 3: Secret Key를 Base64 디코딩하여 시도"""
    print(f"\n🧪 방법 3: Secret Key Base64 디코딩")
    print("-" * 40)

    try:
        # 파라미터 구성
        params = {
            "endpoint": endpoint,
            "currency": currency
        }

        # 쿼리 스트링 생성
        query_string = urllib.parse.urlencode(params)
        print(f"   Query String: {query_string}")

        # 메시지 구성
        message = endpoint + chr(0) + query_string + chr(0) + nonce
        print(f"   Message: {repr(message)}")

        # Secret Key를 Base64로 디코딩 시도
        try:
            secret_bytes = base64.b64decode(secret_key)
            print(f"   Secret Key: Base64 디코딩 성공")
        except:
            # Base64 디코딩 실패하면 원본 사용
            secret_bytes = secret_key.encode('utf-8')
            print(f"   Secret Key: Base64 디코딩 실패, 원본 사용")

        # 서명 생성
        signature = base64.b64encode(
            hmac.new(secret_bytes, message.encode('utf-8'), hashlib.sha512).digest()
        ).decode('utf-8')

        print(f"   Signature: {signature[:40]}...")

        # 헤더 구성
        headers = {
            'Api-Key': connect_key,
            'Api-Sign': signature,
            'Api-Nonce': nonce,
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        # 요청 실행
        url = f"https://api.bithumb.com{endpoint}"
        request_data = {"currency": currency}

        response = requests.post(url, data=request_data, headers=headers, timeout=10)

        print(f"   ✅ 응답 상태: {response.status_code}")
        print(f"   📝 응답 내용: {response.text[:100]}...")

        if response.status_code == 200:
            result = response.json()
            if result.get('status') == '0000':
                print(f"   🎉 성공!")
                return True
            else:
                print(f"   ❌ API 오류: {result.get('status')} - {result.get('message')}")

    except Exception as e:
        print(f"   ❌ 오류: {e}")

    return False

if __name__ == "__main__":
    test_bithumb_auth_methods()