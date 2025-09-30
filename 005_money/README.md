# 빗썸 자동매매 봇

빗썸 거래소의 API를 활용한 암호화폐 자동매매 프로그램입니다.

## 주요 기능

### 🔐 인증 및 로그인
- 빗썸 API 키를 통한 안전한 인증
- 환경변수를 통한 API 키 관리
- 잔고 조회 기능 비활성화 (보안 강화)

### 📈 고도화된 거래 전략
- **이동평균선 교차 전략**: 골든크로스/데드크로스 감지
- **RSI 지표**: 과매수/과매도 구간 판별
- **볼린저 밴드**: 가격 변동성 기반 매매신호
- **거래량 분석**: 비정상적 거래량 감지
- **종합 신호 시스템**: 여러 지표를 조합한 신뢰도 기반 결정

### 💰 매수/매도 기능
- 시장가 주문 자동 실행
- 안전 장치 (최소/최대 거래금액, 일일 거래 한도)
- 모의 거래 모드 지원
- 수수료 자동 계산

### 📊 포괄적 로깅 시스템
- **거래 결정 로그**: 매매 신호 및 근거 기록
- **거래 실행 로그**: 실제 주문 내역 추적
- **전략 분석 로그**: 기술적 지표 분석 결과
- **거래 이력 로그**: 거래 내역 변동 추적
- **에러 로그**: 시스템 오류 및 예외상황 기록
- **📊 마크다운 테이블 로그**: 거래 내역을 표 형태로 시각적 기록

### 📈 거래 내역 추적 및 리포트
- **JSON 형태 거래 내역 저장**: 모든 거래 정보 영구 보관
- **마크다운 테이블 형태 기록**: 매수/매도 내역을 표 형태로 누적 저장
- **FIFO 수익 계산**: 매도 시 선입선출 방식으로 정확한 수익률 계산
- **일일/기간별 거래 요약**: 수익성 분석 리포트
- **거래 통계**: 매수/매도 횟수, 총 거래량, 수수료 집계
- **성과 분석**: 성공/실패 거래 비율 추적

### 📈 거래 내역 관리 (계정 정보 비활성화)
- **거래 내역 추적**: 매수/매도 내역의 상세 기록
- **FIFO 수익 계산**: 매도 시 선입선출 방식으로 수익률 계산
- **거래 내역 내보내기**: 거래 데이터를 JSON/마크다운 형태로 백업
- **GUI 거래 내역 탭**: 전용 탭에서 상세한 거래 내역 확인
- ⚠️ **주의**: 보안상의 이유로 잔고 조회 기능은 비활성화되었습니다

## 파일 구조

```
005_money/
├── main.py              # 메인 실행 파일
├── config.py            # 설정 파일 (API 키, 거래 설정)
├── config_manager.py    # 동적 설정 관리
├── bithumb_api.py       # 빗썸 API 클래스
├── strategy.py          # 거래 전략 로직
├── trading_bot.py       # 통합 거래 봇 클래스
├── portfolio_manager.py # 거래 내역 관리 (계정 정보 기능 비활성화)
├── logger.py            # 로깅 및 거래내역 관리
├── gui_app.py           # GUI 애플리케이션
├── run.py / run.sh      # 편리한 실행 스크립트
├── requirements.txt     # Python 패키지 의존성
└── logs/               # 로그 파일 저장 디렉토리
    ├── trading_YYYYMMDD.log        # 일일 거래 텍스트 로그
    ├── trading_history.md          # 마크다운 테이블 거래 내역
    └── transaction_history.json    # JSON 형태 거래 내역
```

## 설치 및 설정

### 1. 의존성 설치
```bash
cd 005_money
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. API 키 설정

⚠️ **보안 중요**: API 키는 절대 Git에 커밋하지 마세요!

#### 방법 1: 환경변수 설정 (권장)

**macOS/Linux:**
```bash
# ~/.zshrc 또는 ~/.bashrc에 추가
export BITHUMB_CONNECT_KEY="your_connect_key"
export BITHUMB_SECRET_KEY="your_secret_key"

# 적용
source ~/.zshrc
```

**Windows (PowerShell):**
```powershell
$env:BITHUMB_CONNECT_KEY="your_connect_key"
$env:BITHUMB_SECRET_KEY="your_secret_key"
```

#### 방법 2: .env 파일 사용

```bash
# .env.example을 .env로 복사
cp .env.example .env

# .env 파일 편집하여 실제 키 입력
BITHUMB_CONNECT_KEY=your_actual_connect_key
BITHUMB_SECRET_KEY=your_actual_secret_key
```

✅ `.env` 파일은 `.gitignore`에 포함되어 있어 Git에 업로드되지 않습니다.

#### API 키 발급 방법

1. [빗썸 API 관리](https://www.bithumb.com/mypage/api) 페이지 접속
2. "API 생성" 클릭
3. 권한 설정:
   - ✅ **자산 조회**: 필수 (잔고 확인용)
   - ⚠️  **거래**: 실제 거래 시에만 활성화
   - ❌ **출금**: 절대 활성화 금지 (보안 위험)
4. Connect Key와 Secret Key 복사

### 3. 설정 수정
`config.py` 파일에서 다음 설정들을 조정할 수 있습니다:

```python
TRADING_CONFIG = {
    'target_ticker': 'BTC',           # 거래 대상 코인
    'trade_amount_krw': 10000,        # 거래 금액 (원)
    'stop_loss_percent': 5.0,         # 손절매 비율
    'take_profit_percent': 10.0,      # 익절 비율
}

SAFETY_CONFIG = {
    'dry_run': True,                  # 모의 거래 모드
    'max_daily_trades': 10,           # 일일 최대 거래 횟수
    'emergency_stop': False,          # 긴급 정지
}
```

## 실행 방법

### 🚀 간편 실행 (권장)
```bash
# Python 스크립트로 실행
python run.py

# 또는 Bash 스크립트로 실행 (macOS/Linux)
./run.sh
# 또는
bash run.sh
```

### 📋 실행 스크립트 기능
- Python 버전 자동 확인
- 가상환경 자동 생성 및 활성화
- 의존성 패키지 자동 설치
- 설정 파일 검증
- API 키 설정 상태 확인
- 안전한 프로그램 시작

### 수동 실행
```bash
# 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 프로그램 실행
python main.py
```

### 📈 거래 내역 조회 명령어
```bash
# 거래 내역 조회
python main.py --show-transactions

# 거래 내역 내보내기
python main.py --export-transactions trading_history.json

# 실행 스크립트와 함께 사용
./run.sh --show-transactions

# 주의: 보안상의 이유로 잔고 조회 기능은 비활성화되었습니다
```

### 모의 거래 모드 (기본값)
- 실제 돈을 사용하지 않고 거래 로직을 테스트
- 모든 거래 내역이 시뮬레이션으로 기록됨

### 🧪 테스트 모드 (개발/실험용)
```bash
# 테스트 모드로 실행 (거래 내역 기록 안함)
python main.py --test-mode

# 모의 거래 + 테스트 모드
python main.py --dry-run --test-mode
```
- **코드 테스트나 실험 시 사용**
- **거래 내역이 JSON/마크다운 파일에 기록되지 않음**
- 로그에는 "[TEST MODE] 거래 내역 기록 건너뜀" 메시지 표시

### 실제 거래 모드
```bash
# 명령행에서 실제 거래 모드로 실행
python main.py --live

# 또는 config.py에서 설정 변경
```
```python
# config.py에서 설정 변경
SAFETY_CONFIG = {
    'dry_run': False,  # 실제 거래 활성화
    'test_mode': False,  # 거래 내역 기록
    # ...
}
```

## 거래 전략 상세

### 신호 생성 로직
1. **이동평균선 신호** (가중치: 1)
   - 단기 MA > 장기 MA: 매수 신호
   - 단기 MA < 장기 MA: 매도 신호

2. **RSI 신호** (가중치: 1)
   - RSI < 30: 과매도 → 매수 신호
   - RSI > 70: 과매수 → 매도 신호

3. **볼린저 밴드 신호** (가중치: 1)
   - 가격이 하단 밴드 근처(20% 이하): 매수 신호
   - 가격이 상단 밴드 근처(80% 이상): 매도 신호

4. **거래량 신호** (가중치: 1)
   - 평균 거래량 대비 1.5배 이상: 신호 강화

### 최종 결정
- 총합 신호 >= 2 & 신뢰도 > 0.6: 매수
- 총합 신호 <= -2 & 신뢰도 > 0.6: 매도
- 그 외: 관망

## 로그 및 리포트 확인

### 로그 파일 위치
- `logs/trading_YYYYMMDD.log`: 일일 거래 텍스트 로그
- `logs/trading_history.md`: 마크다운 테이블 형태 거래 내역
- `transaction_history.json`: JSON 형태 거래 내역

### 📊 마크다운 거래 내역 테이블
마크다운 테이블 형태로 거래 내역이 기록되며, 매도 시 FIFO 방식으로 수익률이 자동 계산됩니다:

```markdown
| 날짜 | 시간 | 코인 | 거래유형 | 수량 | 단가 | 총금액 | 수수료 | 수익금액 | 수익률 | 메모 |
|------|------|------|----------|------|------|--------|--------|----------|--------|------|
| 2025-09-28 | 14:30:15 | BTC | 🔵 매수 | 0.001000 | 50,000,000원 | 50,000원 | 250원 | - | - | ✅ 성공 |
| 2025-09-28 | 15:45:23 | BTC | 🔴 매도 | 0.000500 | 55,000,000원 | 27,500원 | 138원 | +2,500원 | +10.00% | ✅ 성공 |
```

### JSON 리포트 예시
```
=== 거래 내역 리포트 ===
조회 기간: 30일
대상 코인: BTC

총 거래 횟수: 15회
성공한 거래: 14회
매수 횟수: 7회
매도 횟수: 7회
총 거래량: 1,450,000 KRW
총 수수료: 3,625 KRW

=== 현재 잔고 정보 ===
KRW 잔고: 985,430 원
BTC 잔고: 0.012450 개
일일 거래 횟수: 3회
```

## 안전 기능

### 1. 모의 거래 모드
- 기본값으로 활성화
- 실제 자금 손실 없이 전략 테스트 가능

### 2. 거래 제한
- 일일 최대 거래 횟수 제한
- 최소/최대 거래 금액 설정
- 긴급 정지 기능

### 3. 오류 처리
- API 오류 시 자동 재시도
- 네트워크 오류 처리
- 예외 상황 로깅

## 주의사항

⚠️ **중요**: 이 프로그램은 교육 및 연구 목적으로 제작되었습니다.
- 실제 거래 시 자금 손실 위험이 있습니다
- 충분한 테스트 후 소액으로 시작하세요
- API 키를 안전하게 관리하세요
- 시장 상황을 지속적으로 모니터링하세요

## 라이선스

이 프로젝트는 교육 목적으로 제작되었으며, 사용에 따른 책임은 사용자에게 있습니다.