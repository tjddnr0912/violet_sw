# 빗썸 API 5100 오류 수정 완료

## 문제점
빗썸 잔고조회 API 호출 시 **5100 오류 (Bad Request - Auth Data)** 지속 발생

## 원인 분석
1. **서명 생성 방식 오류**: `h.digest()` 대신 `h.hexdigest().encode('utf-8')`를 사용해야 함
2. **POST 데이터 전송 방식 오류**: URL-encoded 문자열이 아닌 **dict를 그대로** 전달해야 함
3. **endpoint 파라미터 누락**: parameters에 'endpoint' 키를 포함해야 함

## 수정 내용

### 1. `_get_signature()` 메서드 (bithumb_api.py:81-118)
```python
# ❌ 이전 (잘못된 방식)
signature = base64.b64encode(h.digest()).decode('utf-8')

# ✅ 수정 (pybithumb 방식)
signature = base64.b64encode(h.hexdigest().encode('utf-8'))
```

### 2. `_make_request()` 메서드 (bithumb_api.py:120-217)
```python
# ✅ endpoint를 parameters에 추가
parameters['endpoint'] = endpoint

# ✅ API 키를 bytes로 변환
connect_key_bytes = self.connect_key.encode('utf-8')

# ✅ 헤더 구성 (pybithumb 방식)
headers = {
    'Api-Key': connect_key_bytes,
    'Api-Sign': signature,
    'Api-Nonce': nonce,
}

# ✅ dict를 그대로 전달 (requests가 자동으로 form-urlencoded 변환)
response = requests.post(url, data=parameters, headers=headers, timeout=15)
```

## 검증 결과

### 테스트 1: 잔고조회 (BTC)
```bash
python test_fixed_api.py
```
**결과**: ✅ 성공 (Status: 0000)

### 테스트 2: pybithumb 라이브러리와 비교
```bash
python test_pybithumb.py
```
**결과**: ✅ 동일하게 작동

### 테스트 3: 실제 통합 테스트
```python
api = BithumbAPI(connect_key, secret_key)
result = api.get_balance('BTC')  # ✅ 성공
result = api.get_balance('ALL')  # ✅ 성공
```

## 핵심 교훈

### 빗썸 API 서명 생성 규칙 (pybithumb 공식 방식)
1. **서명 메시지 구성**: `endpoint + chr(0) + urlencode(parameters) + chr(0) + nonce`
2. **parameters에 'endpoint' 키 포함** (서명 및 POST 데이터 모두)
3. **HMAC-SHA512 생성**: `h.hexdigest().encode('utf-8')`를 Base64 인코딩
4. **HTTP 헤더**: API Key와 서명을 bytes로 전달
5. **POST 데이터**: dict를 그대로 전달 (requests가 자동 변환)

## 참고 자료
- pybithumb 공식 라이브러리: https://github.com/sharebook-kr/pybithumb
- 핵심 코드: `pybithumb/pybithumb/core.py:149-157`

## 수정 파일
- `bithumb_api.py`: 서명 생성 및 요청 로직 수정
- `test_balance_api.py`: 검증 테스트 코드
- `test_fixed_api.py`: 통합 테스트 코드

## 적용일시
- 2025-10-01 00:10 (KST)
- 검증 완료: 모든 잔고조회 API 정상 작동 확인