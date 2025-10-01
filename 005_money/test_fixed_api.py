#!/usr/bin/env python3
"""
수정된 bithumb_api.py로 잔고조회 테스트
"""

import os
import sys
from bithumb_api import BithumbAPI

# API 키 확인
connect_key = os.getenv("BITHUMB_CONNECT_KEY")
secret_key = os.getenv("BITHUMB_SECRET_KEY")

print("=" * 80)
print("수정된 BithumbAPI 클래스 테스트")
print("=" * 80)
print(f"Connect Key: {connect_key[:10]}...{connect_key[-4:]}")
print(f"Secret Key: {secret_key[:10]}...{secret_key[-4:]}")
print()

# BithumbAPI 인스턴스 생성
api = BithumbAPI(connect_key, secret_key)

# 잔고조회 테스트
print("=" * 80)
print("잔고조회 API 호출 테스트")
print("=" * 80)
result = api.get_balance('BTC')

if result:
    print(f"\n✅ 성공!")
    print(f"Status: {result.get('status')}")
    print(f"Data: {result.get('data')}")
else:
    print("\n❌ 실패!")
    sys.exit(1)