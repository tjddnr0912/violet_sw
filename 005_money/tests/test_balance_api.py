#!/usr/bin/env python3
"""
빗썸 잔고조회 API 검증 코드
실제 API 키를 사용하여 잔고조회가 정상 동작하는지 테스트합니다.
"""

import os
import sys
import hmac
import hashlib
import base64
import urllib.parse
import requests
import time

def test_balance_api():
    """잔고조회 API 테스트"""

    # 1. 환경변수에서 API 키 읽기 (pybithumb처럼 bytes로 변환)
    connect_key = os.getenv("BITHUMB_CONNECT_KEY")
    secret_key = os.getenv("BITHUMB_SECRET_KEY")

    connect_key_bytes = connect_key.encode('utf-8') if connect_key else None
    secret_key_bytes = secret_key.encode('utf-8') if secret_key else None

    print("=" * 80)
    print("빗썸 잔고조회 API 검증 테스트")
    print("=" * 80)

    # 2. API 키 확인
    if not connect_key or not secret_key:
        print("❌ 오류: 환경변수에 API 키가 설정되지 않았습니다.")
        print("   export BITHUMB_CONNECT_KEY=\"your_key\"")
        print("   export BITHUMB_SECRET_KEY=\"your_secret\"")
        return False

    if connect_key in ["YOUR_CONNECT_KEY", "your_connect_key"]:
        print("❌ 오류: Connect Key가 기본값입니다.")
        return False

    if secret_key in ["YOUR_SECRET_KEY", "your_secret_key"]:
        print("❌ 오류: Secret Key가 기본값입니다.")
        return False

    print(f"✅ Connect Key: {connect_key[:10]}...{connect_key[-4:]} (길이: {len(connect_key)})")
    print(f"✅ Secret Key: {secret_key[:10]}...{secret_key[-4:]} (길이: {len(secret_key)})")
    print()

    # 3. 엔드포인트 및 파라미터 설정
    endpoint = "/info/balance"
    url = "https://api.bithumb.com" + endpoint
    parameters = {
        'currency': 'BTC',
        'endpoint': endpoint  # pybithumb는 endpoint를 parameters에 포함!
    }

    # 4. Nonce 생성 (밀리초 타임스탬프)
    nonce = str(int(time.time() * 1000))

    print(f"📍 Endpoint: {endpoint}")
    print(f"📦 Parameters: {parameters}")
    print(f"⏰ Nonce: {nonce}")
    print()

    # 5. 서명 생성 (빗썸 공식 방식)
    print("=" * 80)
    print("서명 생성 과정")
    print("=" * 80)

    # Step 1: 서명용 파라미터 (이미 endpoint 포함)
    print(f"Step 1 - 서명용 파라미터: {parameters}")

    # Step 2: URL 인코딩 (pybithumb 방식 - 정렬 없음)
    query_string = urllib.parse.urlencode(parameters)
    print(f"Step 2 - Query String: {query_string}")

    # Step 3: 서명 메시지 구성 (pybithumb 방식: endpoint + chr(0) + query + chr(0) + nonce)
    message = endpoint + chr(0) + query_string + chr(0) + nonce
    print(f"Step 3 - Message: {repr(message)}")
    print(f"         Message (hex): {message.encode('utf-8').hex()}")

    # Step 4: Secret Key는 이미 bytes로 변환됨
    print(f"Step 4 - Secret Key (UTF-8 bytes): {len(secret_key_bytes)} bytes")

    # Step 5: HMAC-SHA512 서명 생성 (pybithumb 방식: hexdigest를 다시 인코딩!)
    h = hmac.new(secret_key_bytes, message.encode('utf-8'), hashlib.sha512)
    signature = base64.b64encode(h.hexdigest().encode('utf-8'))
    print(f"Step 5 - HMAC-SHA512 hexdigest: {h.hexdigest()[:64]}...")
    print(f"         Signature (bytes): {signature[:50]}...")
    print()

    # 6. HTTP 요청 헤더 구성 (pybithumb 방식: API Key와 서명 모두 bytes로 전달)
    headers = {
        'Api-Key': connect_key_bytes,
        'Api-Sign': signature,
        'Api-Nonce': nonce,
    }

    # 7. POST 데이터는 dict로 전달 (pybithumb 방식)
    post_data = parameters

    print("=" * 80)
    print("HTTP 요청 정보")
    print("=" * 80)
    print(f"URL: {url}")
    print(f"Method: POST")
    print(f"Headers:")
    for key, value in headers.items():
        if key == 'Api-Sign':
            print(f"  {key}: {value[:50]}...")
        elif key == 'Api-Key':
            if isinstance(value, bytes):
                value_str = value.decode('utf-8')
                print(f"  {key}: {value_str[:10]}...{value_str[-4:]}")
            else:
                print(f"  {key}: {value[:10]}...{value[-4:]}")
        else:
            print(f"  {key}: {value}")
    print(f"Body (dict - requests will auto encode): {post_data}")
    print()

    # 8. API 요청 전송 (pybithumb 방식: dict를 그대로 전달)
    print("=" * 80)
    print("API 요청 전송 중...")
    print("=" * 80)

    try:
        response = requests.post(url, data=post_data, headers=headers, timeout=10)

        print(f"✅ HTTP Status Code: {response.status_code}")
        print(f"📥 Response Headers: {dict(response.headers)}")
        print()

        # 9. 응답 파싱
        try:
            result = response.json()
            print("=" * 80)
            print("API 응답 결과")
            print("=" * 80)

            import json
            print(json.dumps(result, indent=2, ensure_ascii=False))
            print()

            # 10. 결과 분석
            status = result.get('status')
            message_text = result.get('message', '')

            if status == '0000':
                print("✅ 성공: 잔고조회 API 호출이 정상적으로 완료되었습니다!")
                return True
            else:
                print(f"❌ 실패: API 오류 발생")
                print(f"   오류 코드: {status}")
                print(f"   오류 메시지: {message_text}")

                # 오류 코드별 해결 방법
                error_solutions = {
                    '5100': 'API Key가 잘못되었습니다. 빗썸에서 발급받은 Connect Key를 확인하세요.',
                    '5200': 'API 서명이 잘못되었습니다. Secret Key를 확인하세요.',
                    '5300': 'Nonce 값이 잘못되었습니다. 시스템 시간을 확인하세요.',
                    '5600': 'API 권한이 없습니다. 빗썸 API 설정에서 "자산조회" 권한을 활성화하세요.',
                }

                if status in error_solutions:
                    print(f"   💡 해결방법: {error_solutions[status]}")

                return False

        except ValueError as e:
            print(f"❌ JSON 파싱 실패: {e}")
            print(f"   Raw Response: {response.text}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"❌ HTTP 요청 실패: {e}")
        return False

if __name__ == "__main__":
    success = test_balance_api()
    sys.exit(0 if success else 1)