# Version-Based Trading Bot - Usage Guide

## 개요

이 거래 봇은 버전 기반 구조로 재구성되어, 여러 거래 전략을 쉽게 관리하고 전환할 수 있습니다.

## 폴더 구조

```
001_python_code/
├── lib/                     # 공통 라이브러리
│   ├── api/                # API 래퍼
│   ├── core/               # 핵심 기능
│   ├── gui/                # GUI 컴포넌트
│   └── interfaces/         # 인터페이스 정의
├── ver1/                    # 버전 1 전략
│   ├── strategy_v1.py      # Elite 8-지표 전략
│   ├── config_v1.py        # 버전 1 설정
│   └── ...
├── ver2/                    # 버전 2 (구현 대기)
├── main.py                  # CLI 진입점
└── gui_app.py              # GUI 진입점
```

## 사용 방법

### 1. 기본 실행 (버전 1)

```bash
# CLI 모드
python main.py

# GUI 모드
python gui_app.py

# 또는 편의 스크립트
./run.sh
python run_gui.py
```

### 2. 버전 선택 실행

```bash
# Ver1으로 실행 (명시적)
python main.py --version ver1
python gui_app.py --version ver1

# Ver2로 실행 (구현 완료 후)
python main.py --version ver2
python gui_app.py --version ver2
```

### 3. 추가 옵션과 함께 실행

```bash
# 특정 코인으로 실행
python main.py --version ver1 --coin ETH

# GUI에서 버전 선택
python gui_app.py --version ver1
```

## 버전 정보

### Ver1: Elite 8-Indicator Strategy
- **상태**: ✅ 구현 완료
- **지표**: MA, RSI, Bollinger Bands, Volume, MACD, ATR, Stochastic, ADX
- **특징**: 
  - 가중치 기반 신호 조합
  - 시장 상황 인식 (Trending/Ranging/Transitional)
  - ATR 기반 동적 손절/익절
- **지원 간격**: 30m, 1h, 6h, 12h, 24h

### Ver2: (구현 대기)
- **상태**: ⏳ 미구현
- **설명**: ver2/README.md 참조

## 개발자 가이드

### 새 버전 추가하기

1. **폴더 생성**
   ```bash
   mkdir ver2
   touch ver2/__init__.py
   ```

2. **필수 파일 작성**
   - `ver2/strategy_v2.py` - VersionInterface 구현
   - `ver2/config_v2.py` - 버전별 설정
   - `ver2/__init__.py` - get_version_instance() 함수

3. **인터페이스 구현**
   ```python
   from lib.interfaces.version_interface import VersionInterface
   
   class StrategyV2(VersionInterface):
       VERSION_NAME = "ver2"
       VERSION_DISPLAY_NAME = "Your Strategy Name"
       # ... 모든 필수 메서드 구현
   ```

4. **테스트**
   ```bash
   python -c "from lib.core.version_loader import get_version_loader; \
   loader = get_version_loader(); \
   ver2 = loader.load_version('ver2'); \
   print(ver2.VERSION_DISPLAY_NAME)"
   ```

### 프로그래밍 방식으로 버전 로드

```python
from lib.core.version_loader import get_version_loader

# 버전 로더 인스턴스 가져오기
loader = get_version_loader()

# 사용 가능한 버전 확인
versions = loader.discover_versions()
print(versions)  # ['ver1', 'ver2']

# 버전 로드
ver1 = loader.load_version('ver1')
print(ver1.VERSION_DISPLAY_NAME)  # Elite 8-Indicator Strategy

# 설정 오버라이드와 함께 로드
custom_config = {
    'INDICATOR_CONFIG': {
        'ma_short_period': 15
    }
}
ver1_custom = loader.load_version('ver1', config_override=custom_config)
```

## 트러블슈팅

### "Version 'verX' not found" 에러
- `loader.discover_versions()`로 사용 가능한 버전 확인
- 버전 폴더에 `__init__.py` 파일이 있는지 확인

### Import 에러
- venv 활성화 확인: `source .venv/bin/activate`
- 의존성 설치 확인: `pip install -r requirements.txt`

### 버전 로드 실패
- 해당 버전이 `VersionInterface`를 올바르게 구현했는지 확인
- `get_version_instance()` 함수가 `__init__.py`에 있는지 확인

## 참고 문서

- **Ver1 상세**: `ver1/README.md`
- **Ver2 구현 가이드**: `ver2/README.md`
- **전략 문서**: `../004_trade_rule/Strategy_v1.md`

## 변경 이력

- **2025-10-03**: 버전 기반 구조로 재구성 완료
- **2025-10**: Ver1 (Elite 8-Indicator Strategy) 구현
