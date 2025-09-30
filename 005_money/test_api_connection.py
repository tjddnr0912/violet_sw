#!/usr/bin/env python3
"""
빗썸 API 연결 테스트 스크립트
API 키 설정이 올바른지 확인하고 연결 상태를 진단합니다.
"""

import sys
import os
import logging
from bithumb_api import BithumbAPI
import config

def test_api_connection():
    """API 연결 테스트"""
    print("🔍 빗썸 API 연결 테스트")
    print("=" * 50)

    # 디버깅을 위한 로깅 활성화
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(message)s')

    # 1. API 키 확인
    print("\n1️⃣ API 키 설정 확인:")
    connect_key = config.BITHUMB_CONNECT_KEY
    secret_key = config.BITHUMB_SECRET_KEY

    if connect_key == "YOUR_CONNECT_KEY" or secret_key == "YOUR_SECRET_KEY":
        print("❌ API 키가 설정되지 않았습니다.")
        print("   환경변수 또는 config.py에서 API 키를 설정하세요.")
        return False

    # API 키 형식 검증
    print(f"🔍 API 키 형식 검증:")
    print(f"   Connect Key 길이: {len(connect_key)} (예상: 32)")
    print(f"   Secret Key 길이: {len(secret_key)} (예상: 32)")

    # 빗썸 Connect Key는 32자리 영숫자
    if len(connect_key) != 32:
        print("⚠️  Connect Key 길이가 비정상적입니다. 빗썸 API는 32자리입니다.")
        print(f"   현재 길이: {len(connect_key)}, 필요 길이: 32")
        return False

    # Secret Key 검증 (빗썸은 32자리 또는 Base64 형식)
    if len(secret_key) == 32:
        print("✅ Secret Key 32자리 형식 (빗썸 구 버전)")
    else:
        try:
            import base64
            base64.b64decode(secret_key)
            print("✅ Secret Key Base64 형식 유효")
        except Exception as e:
            print(f"❌ Secret Key 형식 오류: {e}")
            print(f"   길이가 32자리가 아니고 Base64도 아닙니다.")
            return False

    # API 키 마스킹하여 표시
    masked_connect = connect_key[:8] + "*" * (len(connect_key) - 8) if len(connect_key) > 8 else connect_key
    masked_secret = secret_key[:8] + "*" * (len(secret_key) - 8) if len(secret_key) > 8 else secret_key

    print(f"✅ Connect Key: {masked_connect}")
    print(f"✅ Secret Key: {masked_secret}")

    # 2. API 객체 생성
    print("\n2️⃣ API 객체 생성:")
    try:
        api = BithumbAPI(connect_key, secret_key)
        print("✅ BithumbAPI 객체 생성 성공")
    except Exception as e:
        print(f"❌ API 객체 생성 실패: {e}")
        return False

    # 3. 공개 API 테스트 (API 키 불필요)
    print("\n3️⃣ 공개 API 테스트 (현재가 조회):")
    try:
        # 공개 API로 BTC 현재가 조회
        import requests
        response = requests.get("https://api.bithumb.com/public/ticker/BTC_KRW")
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == '0000':
                btc_price = float(data['data']['closing_price'])
                print(f"✅ BTC 현재가: {btc_price:,.0f}원")
            else:
                print(f"❌ API 응답 오류: {data.get('message', 'Unknown error')}")
                return False
        else:
            print(f"❌ HTTP 오류: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 공개 API 테스트 실패: {e}")
        return False

    # 4. 개인 API 테스트 (잔고 조회 기능 비활성화)
    print("\n4️⃣ 개인 API 테스트:")
    print("⚠️  잔고 조회 기능이 보안상의 이유로 비활성화되었습니다.")
    print("   → API 키 검증은 실제 거래를 통해서만 확인 가능합니다.")
    print("   → 모의 거래 모드에서 봇을 실행하여 API 키를 테스트하세요.")
    print("   → python main.py --dry-run 명령을 사용하세요.")
    return True

def main():
    """메인 함수"""
    print("빗썸 자동매매 봇 - API 연결 테스트")
    print()

    success = test_api_connection()

    print("\n" + "=" * 50)
    if success:
        print("🎉 API 연결 테스트 성공!")
        print("   → 실제 거래 모드를 사용할 수 있습니다.")
        print("   → python main.py --live 명령으로 실제 거래를 시작하세요.")
    else:
        print("❌ API 연결 테스트 실패!")
        print("   → API 키 설정을 다시 확인하세요.")
        print("   → 모의 거래 모드를 사용하세요: python main.py --dry-run")

    print("\n💡 테스트 및 실험 시에는 다음 명령을 사용하세요:")
    print("   python main.py --test-mode  (거래 내역 기록 안함)")

if __name__ == "__main__":
    main()