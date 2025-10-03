# GUI 실행 가이드

## 기본 사용법

```bash
# 기본 실행 (ver1)
./gui

# 버전 지정 실행
./gui --version ver1
./gui -v ver1
./gui --version ver2
./gui -v ver2
```

## 전체 옵션

### 버전 선택
```bash
./gui --version ver1    # Ver1 (Elite 8-Indicator Strategy)으로 실행
./gui -v ver1           # 축약형

./gui --version ver2    # Ver2로 실행 (구현 완료 후)
./gui -v ver2           # 축약형
```

### 환경 관리
```bash
./gui --setup-only      # 환경 설정만 수행 (GUI 실행 안함)
./gui --check           # 시스템 요구사항만 확인
./gui --force-install   # 패키지 강제 재설치
```

### 도움말
```bash
./gui --help            # 전체 도움말 표시
./gui -h                # 축약형
```

## 옵션 조합

```bash
# Ver2로 실행하고 패키지 강제 재설치
./gui --version ver2 --force-install

# Ver1으로 실행 (축약형)
./gui -v ver1
```

## 버전별 특징

### Ver1: Elite 8-Indicator Strategy
**상태**: ✅ 구현 완료

**기술 지표** (8개):
- MA (Moving Average)
- RSI (Relative Strength Index)
- Bollinger Bands
- Volume
- MACD (Moving Average Convergence Divergence)
- ATR (Average True Range)
- Stochastic Oscillator
- ADX (Average Directional Index)

**주요 기능**:
- 가중치 기반 신호 조합 (MACD 35%, MA 25%, RSI 20%, BB 10%, Volume 10%)
- 시장 상황 인식 (Trending/Ranging/Transitional)
- ATR 기반 동적 손절/익절
- 다중 타임프레임 지원 (30m, 1h, 6h, 12h, 24h)

### Ver2: (구현 예정)
**상태**: ⏳ 미구현

구현 방법은 `ver2/README.md` 참조

## GUI 기능

### 🎮 실시간 제어
- 원클릭 봇 시작/정지
- 실시간 설정 변경 (재시작 없이)
- 안전한 종료 및 상태 저장

### 📊 실시간 모니터링
- 현재 거래 코인 및 실시간 가격 표시
- 평균 매수가 및 보유 수량 현황
- 체결 대기 주문 상태
- 실시간 로그 스트림

### 💰 수익 대시보드
- 일일/총 수익 실시간 계산
- 거래 횟수 및 성공률 통계
- 최근 거래 내역 차트
- 평가손익 실시간 업데이트

### 📊 멀티 타임프레임 차트
- 3개 컬럼 동시 표시 (가변/4시간/일봉)
- 각 차트별 독립적인 지표 선택
- 8개 기술 지표 on/off 제어
- 실시간 차트 업데이트

### ⚙️ 드롭다운 설정
- 거래 코인 선택: BTC, ETH, XRP, ADA, DOT, LINK 등
- 체크 간격 변경: 10초 ~ 4시간
- 거래 금액 조정: 실시간 입력
- 즉시 적용: 봇 재시작 없이 설정 변경

## 트러블슈팅

### "알 수 없는 옵션" 에러
```bash
# 잘못된 사용
./gui --ver ver1    # ✗ --ver 대신 --version 사용

# 올바른 사용
./gui --version ver1  # ✓
./gui -v ver1         # ✓
```

### 버전이 로드되지 않음
```bash
# 사용 가능한 버전 확인
cd 001_python_code
python -c "from lib.core.version_loader import get_version_loader; \
loader = get_version_loader(); \
print('Available:', loader.discover_versions())"
```

### 패키지 오류
```bash
# 강제 재설치
./gui --force-install

# 또는 수동 설치
source .venv/bin/activate
pip install -r requirements.txt
```

## 예제

### 예제 1: 처음 사용자
```bash
# 1. 시스템 확인
./gui --check

# 2. 환경 설정
./gui --setup-only

# 3. GUI 실행 (기본 ver1)
./gui
```

### 예제 2: 버전 전환
```bash
# Ver1으로 실행
./gui --version ver1

# Ver2로 전환 (구현 후)
./gui --version ver2
```

### 예제 3: 문제 해결
```bash
# 패키지 문제 시 강제 재설치
./gui --force-install

# 시스템 요구사항 재확인
./gui --check
```

## 주의사항

⚠️ **중요**
- 기본적으로 **모의 거래 모드**로 실행됩니다
- 실제 거래 모드 사용 시 자금 손실 위험이 있습니다
- GUI에서 Ctrl+C를 눌러 안전하게 종료할 수 있습니다
- 버전 변경 시 전략이 완전히 바뀌므로 주의하세요

## 추가 정보

- **전체 문서**: `VERSION_USAGE.md`
- **Ver1 상세**: `ver1/README.md`
- **전략 분석**: `../004_trade_rule/Strategy_v1.md`
- **코드 구조**: 프로젝트 루트의 `CLAUDE.md`
