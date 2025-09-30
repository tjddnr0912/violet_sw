#!/usr/bin/env python3
"""
빗썸 API 서명 테스트 - 다양한 방식 시도
"""

import hashlib
import hmac
import base64
import urllib.parse
import time

def test_signature_method_1(endpoint, params, nonce, secret_key):
    """현재 방식: endpoint + \0 + params + \0 + nonce"""
    query_string = urllib.parse.urlencode(params, safe='')
    message = endpoint + '\0' + query_string + '\0' + nonce
    
    secret_key_bytes = base64.b64decode(secret_key)
    signature = base64.b64encode(
        hmac.new(secret_key_bytes, message.encode('utf-8'), hashlib.sha512).digest()
    ).decode('utf-8')
    
    return signature, message

def test_signature_method_2(endpoint, params, nonce, secret_key):
    """방식 2: endpoint + params + nonce (\\0 없이)"""
    query_string = urllib.parse.urlencode(params, safe='')
    message = endpoint + query_string + nonce
    
    secret_key_bytes = base64.b64decode(secret_key)
    signature = base64.b64encode(
        hmac.new(secret_key_bytes, message.encode('utf-8'), hashlib.sha512).digest()
    ).decode('utf-8')
    
    return signature, message

def test_signature_method_3(endpoint, params, nonce, secret_key):
    """방식 3: params + nonce만 (endpoint 제외)"""
    query_string = urllib.parse.urlencode(params, safe='')
    message = query_string + '\0' + nonce
    
    secret_key_bytes = base64.b64decode(secret_key)
    signature = base64.b64encode(
        hmac.new(secret_key_bytes, message.encode('utf-8'), hashlib.sha512).digest()
    ).decode('utf-8')
    
    return signature, message

def test_signature_method_4(endpoint, params, nonce, secret_key):
    """방식 4: endpoint + params (nonce 별도)"""
    query_string = urllib.parse.urlencode(params, safe='')
    message = endpoint + '\0' + query_string
    
    secret_key_bytes = base64.b64decode(secret_key)
    signature = base64.b64encode(
        hmac.new(secret_key_bytes, message.encode('utf-8'), hashlib.sha512).digest()
    ).decode('utf-8')
    
    return signature, message

# 테스트
endpoint = "/info/balance"
params = {"currency": "BTC"}
nonce = str(int(time.time() * 1000))
secret_key = "DUMMY_SECRET_KEY_FOR_TEST"  # Base64 인코딩된 더미 키

print("=" * 80)
print("빗썸 API 서명 생성 방식 테스트")
print("=" * 80)

methods = [
    ("Method 1: endpoint + \\0 + params + \\0 + nonce", test_signature_method_1),
    ("Method 2: endpoint + params + nonce", test_signature_method_2),
    ("Method 3: params + \\0 + nonce", test_signature_method_3),
    ("Method 4: endpoint + \\0 + params", test_signature_method_4),
]

for name, method in methods:
    print(f"\n{name}")
    print("-" * 80)
    try:
        sig, msg = method(endpoint, params, nonce, secret_key)
        print(f"Message: {repr(msg)}")
        print(f"Signature: {sig[:50]}...")
    except Exception as e:
        print(f"Error: {e}")

print("\n" + "=" * 80)
print("✅ 빗썸 공식 문서 확인 필요:")
print("   https://apidocs.bithumb.com")
print("=" * 80)
