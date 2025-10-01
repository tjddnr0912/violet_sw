#!/usr/bin/env python3
"""
pybithumb 라이브러리로 직접 테스트
"""

import sys
sys.path.insert(0, 'pybithumb')

import os
from pybithumb import Bithumb

# API 키 확인
connect_key = os.getenv('BITHUMB_CONNECT_KEY')
secret_key = os.getenv('BITHUMB_SECRET_KEY')

print(f'API 키 길이: Connect={len(connect_key)}, Secret={len(secret_key)}')
print(f'Connect Key: {connect_key[:10]}...{connect_key[-4:]}')
print(f'Secret Key: {secret_key[:10]}...{secret_key[-4:]}')

# pybithumb로 잔고조회 시도
print('\npybithumb로 잔고조회 시도...')
bithumb = Bithumb(connect_key, secret_key)
balance = bithumb.get_balance('BTC')
print(f'\n결과: {balance}')