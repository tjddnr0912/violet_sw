# GUI 실행 방법 가이드

## 개요

현재 시스템에는 두 가지 버전의 GUI가 있습니다:
- **ver1**: Elite 8-Indicator Strategy (기존)
- **ver2**: 비트코인 다중 시간대 전략 (신규)

---

## 🎯 Version 2 실행 (권장)

### 방법 1: GUI 스크립트 + 버전 인수 (가장 쉬움) ⭐

```bash
cd 005_money
./gui --version ver2
```

또는 축약형:

```bash
cd 005_money
./gui -v ver2
```

### 방법 2: Python 직접 실행

```bash
cd 005_money
python3 003_Execution_script/run_gui.py --version ver2
```

### 방법 3: v2 전용 스크립트 (백업)

```bash
cd 005_money
./gui_v2
```

---

## 🔧 Version 1 실행

### 방법 1: 기본 GUI 스크립트

```bash
cd 005_money
./gui
```

### 방법 2: Python 실행

```bash
cd 005_money
python3 run_gui.py
```

---

## 📊 두 버전의 차이점

### Version 1 (Elite 8-Indicator Strategy)
- **지표**: MA, RSI, BB, Volume, MACD, ATR, Stochastic, ADX
- **전략**: 가중치 기반 신호 조합 (각 지표가 -1.0 ~ +1.0 점수)
- **시장 인식**: Trending/Ranging/Transitional 감지
- **실행 시간대**: 1시간 (기본)

**GUI 특징:**
- 거래 현황: 8개 지표 실시간 값, 가중치 점수
- 실시간 차트: 8개 지표 체크박스로 선택 표시
- 신호 히스토리: 각 거래의 지표별 점수 기록

### Version 2 (다중 시간대 전략) ⭐ 신규
- **시장 체제 필터**: 일봉 EMA 50/200 골든크로스
- **진입 신호**: 4시간봉 점수 시스템 (3점 이상 필요)
  - BB 하단 터치: +1점
  - RSI < 30: +1점
  - 스토캐스틱 RSI 교차 (<20): +2점
- **포지션 관리**: 50% 분할 진입/청산
- **손절매**: 샹들리에 엑시트 (ATR 3배 추적)
- **위험 관리**: 연속 손실 5회 / 일일 손실 5% / 하루 2회 거래 제한

**GUI 특징:**
- **거래 현황**:
  - 시장 체제 상태 (강세/약세/중립)
  - 진입 점수 실시간 (0/4)
  - 각 조건별 점수 분해 표시
  - 샹들리에 손절가 표시
  - 포지션 단계 (초기/1차목표/러너)
  - 회로차단기 상태
- **실시간 차트**: 멀티 타임프레임 지원 (1h/4h/1d)
- **신호 히스토리**: 진입 점수 세부 내역 기록
- **설정 패널**: 모든 파라미터 실시간 수정 가능

---

## 🚀 처음 사용자를 위한 가이드

### 1단계: 의존성 설치

```bash
cd 005_money
pip install -r requirements.txt
```

### 2단계: 환경 설정 (선택사항)

```bash
# 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 의존성 설치
pip install -r requirements.txt
```

### 3단계: GUI 실행

**v2 실행 (권장):**
```bash
./gui_v2
```

**v1 실행:**
```bash
./gui
```

---

## 🔍 문제 해결

### "tkinter 모듈을 찾을 수 없습니다"

**macOS:**
```bash
brew install python-tk
```

**Ubuntu/Debian:**
```bash
sudo apt-get install python3-tk
```

### "파일을 찾을 수 없습니다"

현재 디렉토리를 확인하세요:
```bash
pwd  # /Users/seongwookjang/project/git/violet_sw/005_money 여야 함
ls   # gui, gui_v2 파일이 보여야 함
```

### "실행 권한이 없습니다"

```bash
chmod +x gui_v2
chmod +x gui
```

### v2 GUI가 v1과 똑같이 보입니다

**확인사항:**
1. `./gui --version ver2` 또는 `./gui -v ver2`로 실행했는지 확인
2. 시작 화면에 "v2 - 다중 시간대 전략"이 표시되는지 확인
3. GUI 창 제목에 버전 정보가 표시되는지 확인

**해결책:**
```bash
./gui --version ver2  # 반드시 --version 옵션 사용
```

---

## 📝 각 실행 방법 비교표

| 명령어 | 버전 | 디렉토리 | 비고 |
|--------|------|----------|------|
| `./gui` | v1 | 005_money | 기본 GUI (8 지표) |
| `./gui --version ver2` | v2 | 005_money | **v2 실행** (다중 시간대) ⭐ |
| `./gui -v ver2` | v2 | 005_money | v2 실행 (축약형) ⭐ |
| `./gui_v2` | v2 | 005_money | v2 전용 스크립트 (백업) |
| `python3 003_Execution_script/run_gui.py` | v1 | 005_money | v1 Python 실행 |
| `python3 003_Execution_script/run_gui.py --version ver2` | v2 | 005_money | v2 Python 실행 |
| `python3 001_python_code/ver2/run_gui_v2.py` | v2 | 005_money | v2 직접 실행 |

---

## 💡 권장 사용법

### 일반 사용자
```bash
cd 005_money
./gui --version ver2  # v2 GUI 실행 ⭐ 권장
./gui -v ver2         # v2 GUI 실행 (축약형)
./gui                 # v1 GUI 실행 (기본)
```

### 개발자
```bash
cd 005_money
python3 003_Execution_script/run_gui.py --version ver2  # v2 디버깅
python3 003_Execution_script/run_gui.py                 # v1 디버깅
```

---

## 📚 추가 문서

- **v2 사용 설명서**: `001_python_code/ver2/사용설명서_v2.md`
- **v2 전략 명세**: `004_trade_rule/Strategy_v2_final.md`
- **v1 전략**: `001_python_code/ver1/` 디렉토리

---

## ⚠️ 주의사항

1. **모의 거래 모드**: 두 버전 모두 기본적으로 모의 거래로 실행됩니다
2. **실제 거래**: config 파일에서 `dry_run: False`로 변경 시 실제 자금 손실 위험
3. **동시 실행 금지**: v1과 v2를 동시에 실행하지 마세요 (API 충돌)
4. **백테스트 먼저**: 실제 거래 전에 반드시 백테스팅으로 검증

---

## 🎯 빠른 시작

### v2 실행 (다중 시간대 전략)

```bash
cd 005_money
./gui --version ver2
```

1. 시작 화면에서 "v2 - 다중 시간대 전략" 확인
2. "🚀 GUI 시작" 버튼 클릭
3. **거래 현황 탭:**
   - 시장 체제 상태 확인 (강세/약세/중립)
   - 진입 점수 확인 (3점 이상 = 진입 가능)
   - 각 조건별 점수 세부 내역 확인
4. **실시간 차트 탭:**
   - 타임프레임 선택 (1h/4h/1d)
   - 지표 체크박스로 표시/숨김
5. **신호 히스토리 탭:**
   - 과거 진입/청산 신호 분석
   - 점수 세부 내역 확인

### v1 실행 (Elite 8-Indicator)

```bash
cd 005_money
./gui
```

즐거운 트레이딩 되세요! 🚀
