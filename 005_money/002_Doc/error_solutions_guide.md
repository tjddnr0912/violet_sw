# 빗썸 API 토큰 오류 해결 가이드

## 🚨 주요 오류 코드별 해결 방안

### 1. **5100 - 잘못된 API 키**

#### 문제 증상
```
HTTP 오류: 400
응답 내용: {"status":"5100","message":"Bad Request.(Auth Data)"}
```

#### 원인 분석
- API 키가 올바르게 설정되지 않음
- 환경변수 로딩 실패
- API 키 형식 불일치
- 기본값("YOUR_CONNECT_KEY") 그대로 사용

#### 해결 방법
1. **환경변수 설정 확인**
   ```bash
   export BITHUMB_CONNECT_KEY="your_actual_connect_key"
   export BITHUMB_SECRET_KEY="your_actual_secret_key"
   ```

2. **API 키 형식 검증**
   ```python
   # Connect Key: 32자리 영숫자
   # Secret Key: 32자리 또는 Base64 형식
   ```

3. **보안 키 매니저 사용**
   ```python
   from secure_api_manager import SecureAPIKeyManager
   key_manager = SecureAPIKeyManager()
   ```

---

### 2. **5200 - API 서명 오류**

#### 문제 증상
```
{"status":"5200","message":"Bad Request.(signature)"}
```

#### 원인 분석
- 서명 알고리즘이 빗썸 공식 방식과 불일치
- 파라미터 순서 오류
- Secret Key 처리 방식 불일치
- 인코딩 방식 오류

#### 해결 방법
1. **올바른 서명 알고리즘 사용**
   ```python
   from secure_signature import SecureSignatureGenerator
   sig_gen = SecureSignatureGenerator()
   signature, nonce = sig_gen.create_signature(endpoint, params, secret_key)
   ```

2. **파라미터 정렬 확인**
   - 키 이름 순으로 알파벳 정렬
   - URL 인코딩 시 safe='' 사용

3. **서명 메시지 형식**
   ```
   endpoint + '\0' + query_string + '\0' + nonce
   ```

---

### 3. **5300 - Nonce 값 오류**

#### 문제 증상
```
{"status":"5300","message":"Bad Request.(nonce)"}
```

#### 원인 분석
- 동일한 Nonce 값 재사용
- 시스템 시간 동기화 문제
- Nonce 값이 너무 과거나 미래

#### 해결 방법
1. **고유한 Nonce 생성**
   ```python
   from nonce_manager import NonceManager
   nonce_mgr = NonceManager()
   nonce = nonce_mgr.generate_nonce()
   ```

2. **시간 동기화 확인**
   - NTP 서버와 시간 동기화
   - 마이크로초 정밀도 사용

3. **중복 방지 메커니즘**
   - 사용된 Nonce 추적
   - 데이터베이스 기반 중복 검사

---

### 4. **5600 - API 권한 없음**

#### 문제 증상
```
{"status":"5600","message":"Bad Request.(permission)"}
```

#### 해결 방법
1. **빗썸 홈페이지에서 API 권한 확인**
   - 거래 권한 활성화
   - 필요한 권한만 최소한으로 설정

2. **IP 주소 화이트리스트 확인**
   - 현재 서버 IP 등록 여부 확인

---

### 5. **5500 - 요청 시간 초과**

#### 해결 방법
1. **타임아웃 설정 조정**
   ```python
   response = requests.post(url, timeout=15)
   ```

2. **재시도 로직 구현**
   ```python
   # 지수 백오프로 재시도
   for attempt in range(3):
       try:
           response = make_request()
           break
       except Timeout:
           time.sleep(2 ** attempt)
   ```

---

## 🛡️ 예방적 보안 조치

### 1. **API 키 보안 강화**
```python
# 환경변수 우선 사용
os.getenv("BITHUMB_CONNECT_KEY")

# 키체인 저장 (권장)
import keyring
keyring.set_password("bithumb_api", "connect_key", api_key)

# 암호화된 설정 파일
from cryptography.fernet import Fernet
```

### 2. **요청 빈도 제한**
```python
# 1분에 최대 20회 요청
rate_limiter = RateLimiter(max_requests=20, window=60)
```

### 3. **보안 모니터링**
```python
from security_monitor import SecurityMonitor
monitor = SecurityMonitor()

# 각 요청 후 보안 검사
monitor.check_api_response(endpoint, response_data)
```

### 4. **거래 한도 설정**
```python
# 최대 거래량 제한
MAX_UNITS = 10.0
MAX_AMOUNT = 10000000  # 1000만원

# 의심스러운 패턴 감지
monitor.detect_suspicious_patterns(endpoint, parameters)
```

---

## 🔧 통합 사용 예시

### 보안 강화된 API 사용법
```python
from bithumb_secure_api import BithumbSecureAPI

# 1. 보안 API 초기화
api = BithumbSecureAPI()

# 2. 보안 상태 확인
security_status = api.get_security_status()
print(f"보안 상태: {security_status}")

# 3. 안전한 거래 실행
try:
    # 매수 주문
    response = api.place_buy_order(
        order_currency="BTC",
        units=0.001,
        type_order="market"
    )

    if response and response.get('status') == '0000':
        print("거래 성공!")
    else:
        print(f"거래 실패: {response}")

except Exception as e:
    print(f"거래 중 오류: {e}")

# 4. 긴급 상황 시 정지
if emergency_detected:
    api.enable_emergency_stop()
```

### 기존 코드 마이그레이션
```python
# 기존 코드
# from bithumb_api import BithumbAPI
# api = BithumbAPI(connect_key, secret_key)

# 보안 강화 버전으로 교체
from bithumb_secure_api import BithumbSecureAPI
api = BithumbSecureAPI()  # 자동으로 보안 키 매니저 사용

# 나머지 코드는 동일하게 사용 가능
response = api.place_buy_order("BTC", units=0.001)
```

---

## 🎯 체크리스트

### 설치 전 확인사항
- [ ] Python 3.8 이상
- [ ] 필요한 패키지 설치: `cryptography`, `keyring`, `ntplib`
- [ ] 환경변수 설정
- [ ] 빗썸 API 권한 확인

### 보안 설정 확인
- [ ] API 키 환경변수 설정
- [ ] 키체인 저장 (선택사항)
- [ ] 보안 알림 이메일 설정
- [ ] 거래 한도 설정
- [ ] 긴급 정지 토큰 설정

### 운영 중 모니터링
- [ ] 보안 이벤트 로그 확인
- [ ] API 호출 빈도 모니터링
- [ ] 의심스러운 거래 패턴 감지
- [ ] 정기적인 API 키 교체

---

## 🆘 문제 해결 순서

1. **즉시 조치**
   - 긴급 정지 활성화
   - 현재 거래 중단
   - 로그 수집

2. **원인 분석**
   - 오류 코드 확인
   - 보안 이벤트 로그 분석
   - API 호출 패턴 검토

3. **해결 및 복구**
   - 해당 오류 코드별 해결책 적용
   - 보안 설정 점검
   - 테스트 후 서비스 재개

4. **예방 조치**
   - 보안 정책 업데이트
   - 모니터링 강화
   - 정기적인 보안 점검