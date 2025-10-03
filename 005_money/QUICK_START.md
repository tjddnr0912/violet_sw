# 🚀 빠른 시작 가이드

## GUI 실행 (가장 간단한 방법)

### 기본 실행
```bash
cd /Users/seongwookjang/project/git/violet_sw/005_money
./gui
```

### 버전 선택 실행
```bash
# Ver1 (Elite 8-Indicator Strategy)
./gui --version ver1
./gui -v ver1

# Ver2 (구현 예정)
./gui --version ver2
./gui -v ver2
```

## 전체 옵션

| 옵션 | 축약형 | 설명 | 예제 |
|------|--------|------|------|
| `--version` | `-v` | 버전 선택 | `./gui -v ver1` |
| `--help` | `-h` | 도움말 표시 | `./gui --help` |
| `--setup-only` | - | 환경 설정만 | `./gui --setup-only` |
| `--check` | - | 시스템 확인 | `./gui --check` |
| `--force-install` | - | 패키지 재설치 | `./gui --force-install` |

## 사용 예제

### 1. 처음 사용
```bash
# 시스템 확인
./gui --check

# 환경 설정
./gui --setup-only

# GUI 실행
./gui
```

### 2. 빠른 실행
```bash
# Ver1으로 바로 실행
./gui -v ver1
```

### 3. 버전 전환
```bash
# Ver1 실행
./gui --version ver1

# Ver2로 전환 (구현 후)
./gui --version ver2
```

### 4. 문제 해결
```bash
# 패키지 재설치
./gui --force-install

# 시스템 재확인
./gui --check
```

## 버전 정보

### Ver1: Elite 8-Indicator Strategy ✅
**상태**: 구현 완료

**지표** (8개):
- MA (Moving Average) - 이동평균선
- RSI (Relative Strength Index) - 상대강도지수
- Bollinger Bands - 볼린저 밴드
- Volume - 거래량
- MACD - 이동평균수렴확산
- ATR (Average True Range) - 평균진폭
- Stochastic - 스토캐스틱
- ADX (Average Directional Index) - 평균방향지수

**특징**:
- 가중치 기반 신호 (MACD 35%, MA 25%, RSI 20%)
- 시장 상황 인식 (상승/하락/횡보)
- 동적 손절/익절

### Ver2 ⏳
**상태**: 구현 예정

## CLI 실행 (고급)

```bash
cd 001_python_code

# 기본 실행
python main.py

# 버전 선택
python main.py --version ver1
python gui_app.py --version ver1

# 추가 옵션
python main.py -v ver1 --coin BTC
```

## 프로그래밍 방식

```python
from lib.core.version_loader import get_version_loader

loader = get_version_loader()

# 사용 가능한 버전 확인
print(loader.discover_versions())  # ['ver1', 'ver2']

# 버전 로드
ver1 = loader.load_version('ver1')
print(ver1.VERSION_DISPLAY_NAME)  # Elite 8-Indicator Strategy
```

## 문제 해결

### "버전을 찾을 수 없음"
```bash
cd 001_python_code
python -c "from lib.core.version_loader import get_version_loader; \
print(get_version_loader().discover_versions())"
```

### "패키지 오류"
```bash
./gui --force-install
```

### "tkinter 없음"
```bash
# macOS
brew install python-tk

# Ubuntu/Debian
sudo apt-get install python3-tk
```

## 더 알아보기

- **전체 매뉴얼**: `GUI_USAGE.md`
- **버전 시스템**: `VERSION_USAGE.md`
- **Ver1 상세**: `001_python_code/ver1/README.md`
- **전략 분석**: `004_trade_rule/Strategy_v1.md`

---

**빠른 시작**: `./gui -v ver1` 👈 이것만 실행하세요!
