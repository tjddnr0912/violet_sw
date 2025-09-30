# 🚀 사용 예시 가이드

## 기본 실행

### 1. 기본 설정으로 실행
```bash
python main.py
# 또는
python run.py
```

### 2. 설정 확인
```bash
python main.py --show-config
```

## 시간 간격 설정

### 1. 초 단위 실행
```bash
# 30초마다 체크
python main.py --interval 30s

# 10초마다 체크 (최소 10초)
python main.py --interval 10s
```

### 2. 분 단위 실행
```bash
# 5분마다 체크
python main.py --interval 5m

# 1분마다 체크
python main.py --interval 1m
```

### 3. 시간 단위 실행
```bash
# 1시간마다 체크
python main.py --interval 1h

# 4시간마다 체크
python main.py --interval 4h
```

## 거래 설정

### 1. 다른 코인 거래
```bash
# 이더리움 거래
python main.py --coin ETH

# 리플 거래
python main.py --coin XRP

# 에이다 거래
python main.py --coin ADA
```

### 2. 거래 금액 설정
```bash
# 5만원씩 거래
python main.py --amount 50000

# 10만원씩 거래
python main.py --amount 100000
```

### 3. 복합 설정
```bash
# 이더리움을 3만원씩, 1분마다 체크
python main.py --coin ETH --amount 30000 --interval 1m
```

## 전략 설정

### 1. 이동평균 조정
```bash
# 단기 3일, 장기 15일 이동평균
python main.py --short-ma 3 --long-ma 15

# 단기 10일, 장기 30일 이동평균
python main.py --short-ma 10 --long-ma 30
```

### 2. RSI 기간 조정
```bash
# RSI 7일 기간
python main.py --rsi-period 7

# RSI 21일 기간
python main.py --rsi-period 21
```

### 3. 전략 전체 조정
```bash
python main.py --short-ma 7 --long-ma 25 --rsi-period 10
```

## 실행 모드

### 1. 모의 거래 (기본값)
```bash
python main.py --dry-run
```

### 2. 실제 거래 (주의!)
```bash
# API 키가 설정되어 있어야 함
python main.py --live
```

## 대화형 설정

### 1. 대화형 메뉴로 설정
```bash
python main.py --interactive
```

대화형 메뉴에서 할 수 있는 작업:
- 거래 코인 변경
- 거래 금액 조정
- 체크 간격 설정 (초/분/시간 단위)
- 거래 모드 변경
- 전략 매개변수 조정
- 설정 저장/로드

## 설정 파일 관리

### 1. 설정 저장
```bash
# 현재 설정을 파일로 저장
python main.py --save-config my_config.json

# 특정 설정으로 저장
python main.py --coin ETH --interval 30s --amount 50000 --save-config eth_config.json
```

### 2. 저장된 설정 사용
```bash
python main.py --config-file my_config.json
```

### 3. 설정 리셋
```bash
python main.py --reset-config
```

## 실전 사용 예시

### 1. 보수적 장기 투자
```bash
# 비트코인, 4시간마다, 소액
python main.py --coin BTC --interval 4h --amount 10000 --long-ma 50
```

### 2. 적극적 단기 투자
```bash
# 이더리움, 5분마다, 중간 금액
python main.py --coin ETH --interval 5m --amount 50000 --short-ma 3 --long-ma 10
```

### 3. 알트코인 실험
```bash
# 다양한 코인으로 소액 테스트
python main.py --coin ADA --interval 1h --amount 20000 --rsi-period 7
```

### 4. 고빈도 모니터링
```bash
# 30초마다 체크하여 빠른 대응
python main.py --interval 30s --short-ma 5 --long-ma 15
```

## 안전 사용법

### 1. 항상 모의 거래로 시작
```bash
# 새로운 설정은 반드시 모의 거래로 테스트
python main.py --coin ETH --interval 1m --dry-run
```

### 2. 소액으로 시작
```bash
# 실제 거래 시 소액부터
python main.py --amount 10000 --live
```

### 3. 로그 모니터링
```bash
# 별도 터미널에서 로그 확인
tail -f logs/trading_$(date +%Y%m%d).log
```

### 4. 수동 중단
- `Ctrl + C`로 언제든 안전하게 중단 가능
- 중단 시 자동으로 거래 리포트 생성

## 고급 사용법

### 1. 설정 조합 실험
```bash
# 여러 설정을 저장해두고 비교 테스트
python main.py --coin BTC --interval 1h --save-config btc_1h.json
python main.py --coin BTC --interval 30m --save-config btc_30m.json

# 각각 테스트해보기
python main.py --config-file btc_1h.json
python main.py --config-file btc_30m.json
```

### 2. 시간대별 전략
```bash
# 주간: 보수적
python main.py --interval 1h --short-ma 10 --long-ma 30

# 야간: 적극적
python main.py --interval 30s --short-ma 3 --long-ma 10
```

### 3. 다중 봇 실행 (고급)
```bash
# 서로 다른 터미널에서
python main.py --coin BTC --interval 1h --config-file btc_config.json
python main.py --coin ETH --interval 30m --config-file eth_config.json
```

## 문제 해결

### 1. 설정이 적용되지 않을 때
```bash
python main.py --show-config  # 현재 설정 확인
python main.py --reset-config # 리셋 후 다시 설정
```

### 2. 봇이 너무 자주/가끔 실행될 때
```bash
# 간격 조정
python main.py --interval 5m  # 더 자주
python main.py --interval 2h  # 덜 자주
```

### 3. 전략이 너무 민감/둔감할 때
```bash
# 더 민감하게
python main.py --short-ma 3 --long-ma 10 --rsi-period 7

# 더 둔감하게
python main.py --short-ma 10 --long-ma 30 --rsi-period 21
```