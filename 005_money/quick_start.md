# 🚀 빠른 시작 가이드

## 1. 프로그램 실행

### 방법 1: 자동 설정 스크립트 (권장)
```bash
# Python 스크립트
python run.py

# 또는 Bash 스크립트 (macOS/Linux)
./run.sh
```

### 방법 2: 수동 설정
```bash
cd 005_money
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## 2. 첫 실행 시 확인사항

### ✅ 모의 거래 모드 확인
- 기본값으로 `dry_run: True`로 설정됨
- 실제 돈을 사용하지 않고 안전하게 테스트

### ⚠️ API 키 경고 메시지
```
⚠️ 경고: API 키가 설정되지 않았습니다. 실제 거래를 위해서는 API 키를 설정해주세요.
```
- 정상적인 메시지입니다
- 모의 거래로 먼저 테스트하세요

## 3. 프로그램 동작 확인

### 실행 로그 예시
```
코인 자동매매 봇을 시작합니다.
매매 대상: BTC
모드: ⚠️ 모의 거래

========== 2024-01-01 09:05:00 ===========
[BTC] 현재 단기 MA: 45000.00, 장기 MA: 44500.00
매수 신호 감지 (신뢰도: 0.75)
거래 성공: BUY 0.000222 BTC at 45,000 KRW
```

### 로그 파일 확인
```bash
# 일일 거래 로그
tail -f logs/trading_20240101.log

# 거래 내역 JSON
cat transaction_history.json
```

## 4. 중단 방법

### 안전한 종료
- `Ctrl + C` 키를 누르면 안전하게 종료
- 최종 리포트가 자동으로 생성됨

## 5. 다음 단계

### API 키 설정 (실제 거래용)
```bash
# 환경변수로 설정 (권장)
export BITHUMB_CONNECT_KEY="your_key"
export BITHUMB_SECRET_KEY="your_secret"

# config.py에서 설정 변경
SAFETY_CONFIG = {
    'dry_run': False,  # 실제 거래 활성화
}
```

### 거래 설정 조정
```python
# config.py에서 수정
TRADING_CONFIG = {
    'target_ticker': 'BTC',      # 거래할 코인
    'trade_amount_krw': 10000,   # 거래 금액
}

STRATEGY_CONFIG = {
    'short_ma_window': 5,        # 단기 이동평균
    'long_ma_window': 20,        # 장기 이동평균
}
```

## 문제 해결

### 자주 발생하는 문제

1. **ModuleNotFoundError**
   ```bash
   pip install pandas requests schedule numpy
   ```

2. **가상환경 활성화 실패**
   ```bash
   python3 -m venv .venv --clear
   ```

3. **API 연결 오류**
   - 인터넷 연결 확인
   - 모의 거래 모드에서는 정상 동작

### 로그 확인
```bash
# 최근 로그 확인
tail -20 logs/trading_$(date +%Y%m%d).log

# 에러 로그만 확인
grep "ERROR" logs/trading_*.log
```

## 📞 지원

문제가 발생하면:
1. 로그 파일 확인
2. 설정 파일 검토
3. 모의 거래 모드에서 테스트
4. README.md 전체 문서 참조