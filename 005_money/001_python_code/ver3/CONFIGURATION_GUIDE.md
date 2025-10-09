# Ver3 설정 가이드

**버전:** Ver3 - Portfolio Multi-Coin Strategy
**최종 업데이트:** 2025-10-08
**설정 파일:** `001_python_code/ver3/config_v3.py`

---

## 기본 설정

### config_v3.py 주요 설정

Ver3의 모든 설정은 `config_v3.py` 파일에서 관리됩니다. 이 파일은 Ver2 설정을 상속받으며, 포트폴리오 관련 설정을 추가합니다.

---

## 1. 포트폴리오 설정 (PORTFOLIO_CONFIG)

### 기본 구조

```python
PORTFOLIO_CONFIG = {
    # 포지션 제한
    'max_positions': 2,
    'max_positions_per_coin': 1,

    # 리스크 관리
    'max_portfolio_risk_pct': 6.0,
    'position_size_equal': True,
    'reserve_cash_pct': 0.20,

    # 코인 선택
    'default_coins': ['BTC', 'ETH', 'XRP'],
    'min_coins': 1,
    'max_coins': 4,

    # 병렬 분석
    'parallel_analysis': True,
    'max_workers': 3,
    'analysis_timeout': 30,

    # 진입 우선순위
    'entry_priority': 'score',
    'coin_rank': {
        'BTC': 4,
        'ETH': 3,
        'XRP': 2,
        'SOL': 1
    },
}
```

### 세부 설명

#### max_positions (최대 포지션 수)

```python
'max_positions': 2  # 동시에 보유 가능한 최대 포지션 수
```

**의미:**
- 포트폴리오 전체에서 동시에 보유할 수 있는 코인 포지션의 최대 개수
- 2로 설정 시: BTC와 ETH를 동시에 보유 가능, XRP는 대기

**기본값:** 2
**권장 범위:** 1-2
**변경 시 영향:**
- 값을 늘리면: 더 많은 코인 동시 거래 → 리스크 증가
- 값을 줄이면: 보수적 운영 → 리스크 감소

**예시:**
```python
# 보수적 (한 번에 하나만)
'max_positions': 1

# 균형적 (기본값)
'max_positions': 2

# 공격적 (권장하지 않음)
'max_positions': 3
```

#### default_coins (기본 모니터링 코인)

```python
'default_coins': ['BTC', 'ETH', 'XRP']  # 시작 시 모니터링할 코인 목록
```

**의미:**
- Ver3 실행 시 자동으로 모니터링을 시작할 코인 목록
- GUI의 체크박스 초기 선택 값

**기본값:** `['BTC', 'ETH', 'XRP']`
**권장 범위:** 2-3개 코인
**변경 시 영향:**
- 코인 수 증가: API 호출 증가, 분석 시간 증가
- 코인 수 감소: 집중 투자, 분산 효과 감소

**추천 조합:**
```python
# 안정형 (변동성 낮음)
'default_coins': ['BTC', 'ETH']

# 균형형 (기본)
'default_coins': ['BTC', 'ETH', 'XRP']

# 공격형 (변동성 높음)
'default_coins': ['ETH', 'XRP', 'SOL']
```

#### max_portfolio_risk_pct (포트폴리오 총 리스크)

```python
'max_portfolio_risk_pct': 6.0  # 포트폴리오 전체 리스크 비율 (%)
```

**의미:**
- 전체 포트폴리오에서 허용하는 최대 리스크 비율
- 모든 포지션의 리스크 합계가 이 값을 초과할 수 없음

**기본값:** 6.0% (포트폴리오의 6%)
**권장 범위:** 4.0% - 8.0%
**변경 시 영향:**
- 값을 늘리면: 더 큰 포지션 가능 → 수익/손실 모두 증가
- 값을 줄이면: 작은 포지션 → 안전하지만 수익 제한

**계산 예시:**
```
포트폴리오 총액: 1,000,000 KRW
max_portfolio_risk_pct: 6.0%
허용 최대 리스크: 60,000 KRW

2개 포지션 진입 시:
- 각 포지션 리스크: 30,000 KRW 이하
- 스톱로스까지 손실: 최대 60,000 KRW
```

#### entry_priority (진입 우선순위 기준)

```python
'entry_priority': 'score'  # 'score' | 'volatility' | 'volume'
```

**의미:**
- 여러 코인이 동시에 진입 신호를 보낼 때 어떤 코인을 우선할지 결정
- 포트폴리오 제한으로 모든 코인에 진입할 수 없을 때 사용

**기본값:** `'score'` (진입 점수 기준)
**권장 값:** `'score'`
**변경 시 영향:**
- `'score'`: 점수 높은 코인 우선 (가장 강한 신호)
- `'volatility'`: 변동성 높은 코인 우선 (고위험 고수익)
- `'volume'`: 거래량 많은 코인 우선 (유동성 중시)

**동작 예시:**
```
상황: BTC(3점), ETH(4점), XRP(2점) 모두 매수 신호
제한: max_positions = 2 (1개만 진입 가능)

entry_priority: 'score' → ETH 진입 (4점, 최고점)
entry_priority: 'volatility' → 변동성 비교 후 결정
```

#### coin_rank (동점 시 우선순위)

```python
'coin_rank': {
    'BTC': 4,  # 비트코인이 최우선
    'ETH': 3,
    'XRP': 2,
    'SOL': 1
}
```

**의미:**
- 진입 점수가 같을 때 사용하는 타이브레이커
- 숫자가 클수록 우선순위 높음

**기본값:** BTC > ETH > XRP > SOL
**변경 시 영향:**
- 선호하는 코인의 랭크를 높이면 동점 시 해당 코인 우선 선택

---

## 2. 진입/청산 설정

Ver3는 Ver2의 진입/청산 설정을 그대로 사용합니다.

### 진입 점수 설정 (ENTRY_SCORING_CONFIG)

```python
ENTRY_SCORING_CONFIG = {
    'min_entry_score': 2,  # 최소 진입 점수 (2점 이상 진입)

    'scoring_rules': {
        'bb_touch': {
            'enabled': True,
            'points': 1,
            'condition': 'low <= bb_lower',
        },
        'rsi_oversold': {
            'enabled': True,
            'points': 1,
            'condition': 'rsi < 35',
        },
        'stoch_rsi_cross': {
            'enabled': True,
            'points': 2,
            'condition': 'stoch_k crosses above stoch_d below 20',
        },
    },
}
```

#### min_entry_score (최소 진입 점수)

**의미:** 이 점수 이상일 때만 매수 진입
**기본값:** 2점
**권장 범위:** 2-3점
**변경 시 영향:**
- 2점: 더 많은 진입 기회 (공격적)
- 3점: 더 강한 신호만 진입 (보수적)
- 4점: 완벽한 신호만 진입 (매우 보수적, 거의 진입 안 함)

### 청산 설정 (EXIT_CONFIG)

```python
EXIT_CONFIG = {
    'first_target': 'bb_middle',   # 50% 청산: 볼린저 밴드 중간선
    'second_target': 'bb_upper',   # 100% 청산: 볼린저 밴드 상단선
    'stop_loss': 'chandelier_exit', # 손절: 샹들리에 엑시트
    'trail_after_breakeven': True,  # 본전 돌파 후 추적 손절
}
```

---

## 3. 리스크 관리

### 리스크 설정 (RISK_CONFIG)

```python
RISK_CONFIG = {
    # 손절 설정
    'stop_loss_type': 'chandelier',
    'chandelier_atr_multiplier': 3.0,
    'fixed_stop_loss_pct': 5.0,

    # 손절 이동
    'breakeven_after_first_target': True,

    # 일일 제한
    'max_daily_loss_pct': 3.0,
    'max_consecutive_losses': 3,
    'max_daily_trades': 5,

    # 포지션 제한
    'max_position_size_pct': 10.0,
}
```

#### max_daily_loss_pct (일일 최대 손실)

**의미:** 하루에 포트폴리오의 몇 %까지 손실 허용
**기본값:** 3.0%
**권장 범위:** 2.0% - 5.0%
**변경 시 영향:**
- 이 값 초과 시 당일 거래 중단
- 보수적: 2.0%, 공격적: 5.0%

#### max_consecutive_losses (최대 연속 손실)

**의미:** 연속으로 몇 번까지 손실 거래 허용
**기본값:** 3회
**권장 범위:** 2-4회
**변경 시 영향:**
- 이 값 초과 시 1시간 거래 중단 (감정적 판단 방지)

#### max_daily_trades (일일 최대 거래)

**의미:** 하루에 최대 몇 번까지 거래 허용
**기본값:** 5회
**권장 범위:** 3-10회
**변경 시 영향:**
- 과도한 거래 방지 (수수료 최소화)
- 4시간봉 전략이므로 하루 5-6회면 충분

---

## 4. API 설정

### API 설정 (API_CONFIG)

```python
API_CONFIG = {
    'exchange': 'bithumb',
    'check_interval_seconds': 14400,  # 4시간 (4H 봉 주기)
    'rate_limit_seconds': 1.0,
    'timeout_seconds': 15,
}
```

### API 키 설정 방법

#### 방법 1: 환경 변수 (권장)

```bash
# ~/.bashrc 또는 ~/.zshrc에 추가
export BITHUMB_CONNECT_KEY="your_connect_key"
export BITHUMB_SECRET_KEY="your_secret_key"

# 적용
source ~/.bashrc
```

#### 방법 2: 시스템 환경 변수 (macOS)

```bash
# 현재 터미널 세션에서만 유효
export BITHUMB_CONNECT_KEY="your_connect_key"
export BITHUMB_SECRET_KEY="your_secret_key"

# Ver3 실행
python 001_python_code/main.py --version ver3
```

#### 방법 3: 설정 파일 (권장하지 않음)

```python
# config_v3.py에 직접 입력 (보안 취약)
API_CONFIG = {
    'connect_key': 'your_key',  # 절대 깃허브에 올리지 말 것!
    'secret_key': 'your_secret',
}
```

⚠️ **보안 권장사항:**
- 절대 API 키를 코드에 하드코딩하지 마세요
- .gitignore에 설정 파일 추가
- 환경 변수 사용 필수
- API 키 권한은 "거래" 권한만 부여 (출금 권한 제거)

---

## 고급 설정

### 포트폴리오 최적화

#### 코인 조합 전략

**상관관계를 고려한 코인 선택:**

```python
# 낮은 상관관계 조합 (권장)
'default_coins': ['BTC', 'XRP']  # BTC와 XRP는 상관관계 낮음

# 높은 상관관계 조합 (비권장)
'default_coins': ['BTC', 'ETH']  # BTC와 ETH는 높은 상관관계
```

**변동성 고려:**
```python
# 안정형 (낮은 변동성)
'default_coins': ['BTC']

# 균형형
'default_coins': ['BTC', 'ETH']

# 공격형 (높은 변동성)
'default_coins': ['XRP', 'SOL']
```

#### 리스크 분산

```python
# 2개 코인, 각 3% 리스크 = 총 6% 리스크
PORTFOLIO_CONFIG = {
    'max_positions': 2,
    'max_portfolio_risk_pct': 6.0,
}

# 포지션당 리스크 = 6% / 2 = 3%
```

#### 포지션 크기 조정

```python
POSITION_SIZING_CONFIG = {
    'base_amount_krw': 50000,    # 기본 포지션 크기
    'min_amount_krw': 10000,     # 최소 주문 금액 (빗썸 제한)
    'max_amount_krw': 100000,    # 최대 포지션 크기
    'use_atr_scaling': True,     # ATR 기반 동적 조정
}
```

**ATR 기반 동적 조정:**
- `use_atr_scaling: True`이면 변동성에 따라 포지션 크기 자동 조정
- 변동성 높을 때 → 포지션 크기 감소
- 변동성 낮을 때 → 포지션 크기 증가

### 성능 튜닝

#### 분석 간격 조정

```python
SCHEDULE_CONFIG = {
    'check_interval_seconds': 900,   # 15분마다 분석 (기본값)
}
```

**권장 값:**
- **15분 (900초):** 기본값, 4시간봉 전략에 적합
- **30분 (1800초):** API 호출 절약
- **60분 (3600초):** 매우 보수적, 놓치는 신호 증가

#### 스레드 풀 크기

```python
PORTFOLIO_CONFIG = {
    'max_workers': 3,  # 동시 분석 스레드 수
}
```

**권장 값:**
- 코인 수와 동일하게 설정 (3개 코인 = 3 workers)
- 너무 크게 설정 시 API 호출 제한 위반 가능

#### 메모리 사용량

```python
TIMEFRAME_CONFIG = {
    'execution_candles': 200,  # 4시간봉 데이터 수
    'regime_candles': 250,     # 일봉 데이터 수
}
```

**메모리 절약:**
- 캔들 수를 줄이면 메모리 절약 (하지만 지표 정확도 감소)
- 최소 200개는 유지 (EMA 200 계산 위해)

---

## 설정 예시

### 보수적 설정 (초보자)

```python
# config_v3.py

PORTFOLIO_CONFIG = {
    'max_positions': 1,              # 한 번에 1개만
    'default_coins': ['BTC', 'ETH'], # 안정적인 코인
    'max_portfolio_risk_pct': 4.0,   # 낮은 리스크
}

POSITION_SIZING_CONFIG = {
    'base_amount_krw': 30000,  # 소액 시작
}

ENTRY_SCORING_CONFIG = {
    'min_entry_score': 3,  # 강한 신호만 진입
}

RISK_CONFIG = {
    'max_daily_loss_pct': 2.0,      # 일일 손실 2%
    'max_consecutive_losses': 2,     # 연속 손실 2회
    'max_daily_trades': 3,           # 일일 3회 제한
}

EXECUTION_CONFIG = {
    'dry_run': True,  # 시뮬레이션 모드
}
```

**특징:**
- 안전성 최우선
- 진입 기회 적음
- 손실 제한 엄격
- 실거래 전 충분한 테스트

### 균형 설정 (기본)

```python
# config_v3.py (기본값)

PORTFOLIO_CONFIG = {
    'max_positions': 2,
    'default_coins': ['BTC', 'ETH', 'XRP'],
    'max_portfolio_risk_pct': 6.0,
}

POSITION_SIZING_CONFIG = {
    'base_amount_krw': 50000,
}

ENTRY_SCORING_CONFIG = {
    'min_entry_score': 2,  # 중간 신호도 진입
}

RISK_CONFIG = {
    'max_daily_loss_pct': 3.0,
    'max_consecutive_losses': 3,
    'max_daily_trades': 5,
}

EXECUTION_CONFIG = {
    'dry_run': False,  # 실거래
}
```

**특징:**
- 안정성과 수익성 균형
- 적절한 진입 기회
- 표준 리스크 관리
- 대부분의 사용자에게 권장

### 공격적 설정 (경험자)

```python
# config_v3.py

PORTFOLIO_CONFIG = {
    'max_positions': 2,  # 3은 너무 위험
    'default_coins': ['ETH', 'XRP', 'SOL'],  # 변동성 큰 코인
    'max_portfolio_risk_pct': 8.0,   # 높은 리스크
}

POSITION_SIZING_CONFIG = {
    'base_amount_krw': 100000,  # 큰 포지션
}

ENTRY_SCORING_CONFIG = {
    'min_entry_score': 2,  # 더 많은 진입
}

RISK_CONFIG = {
    'max_daily_loss_pct': 5.0,      # 손실 여유
    'max_consecutive_losses': 4,
    'max_daily_trades': 8,
}

EXECUTION_CONFIG = {
    'dry_run': False,
}
```

**특징:**
- 높은 수익 가능성
- 높은 손실 위험
- 많은 진입 기회
- 경험 많은 트레이더에게만 권장

---

## 설정 검증

### 설정 유효성 확인

Ver3 실행 전 설정을 검증하려면:

```bash
cd /Users/seongwookjang/project/git/violet_sw/005_money
python 001_python_code/ver3/test_portfolio_v3.py
```

**검증 항목:**
- ✅ 포트폴리오 설정 유효성
- ✅ 코인 목록 유효성
- ✅ 리스크 설정 논리성
- ✅ API 연결 가능성

### 일반적인 설정 오류

**오류 1: max_positions > default_coins 개수**
```python
# 잘못된 설정
'max_positions': 3,
'default_coins': ['BTC', 'ETH'],  # 2개만 모니터링
```
**해결:** max_positions를 코인 수 이하로 설정

**오류 2: min_entry_score가 max score보다 높음**
```python
# 잘못된 설정
'min_entry_score': 5,  # 최대 4점인데 5점 요구
```
**해결:** min_entry_score를 2-4 사이로 설정

**오류 3: max_daily_loss_pct가 너무 높음**
```python
# 위험한 설정
'max_daily_loss_pct': 20.0,  # 하루에 20% 손실 허용
```
**해결:** 2-5% 사이로 설정 (권장: 3%)

---

## 설정 팁

### 시작 단계별 권장 설정

**1주차: Dry-run 테스트**
```python
EXECUTION_CONFIG = {'dry_run': True}
PORTFOLIO_CONFIG = {'max_positions': 1}
POSITION_SIZING_CONFIG = {'base_amount_krw': 10000}
```

**2주차: 소액 실거래**
```python
EXECUTION_CONFIG = {'dry_run': False}
PORTFOLIO_CONFIG = {'max_positions': 1}
POSITION_SIZING_CONFIG = {'base_amount_krw': 20000}
```

**3주차: 포지션 증가**
```python
PORTFOLIO_CONFIG = {'max_positions': 2}
POSITION_SIZING_CONFIG = {'base_amount_krw': 30000}
```

**4주차: 정상 운영**
```python
PORTFOLIO_CONFIG = {'max_positions': 2}
POSITION_SIZING_CONFIG = {'base_amount_krw': 50000}
```

### 상황별 설정 조정

**시장이 불안정할 때:**
```python
PORTFOLIO_CONFIG = {
    'max_positions': 1,  # 포지션 수 감소
    'default_coins': ['BTC'],  # BTC만 거래
}
ENTRY_SCORING_CONFIG = {
    'min_entry_score': 3,  # 진입 조건 강화
}
```

**시장이 안정적일 때:**
```python
PORTFOLIO_CONFIG = {
    'max_positions': 2,
    'default_coins': ['BTC', 'ETH', 'XRP'],
}
ENTRY_SCORING_CONFIG = {
    'min_entry_score': 2,
}
```

---

**Ver3 설정 가이드 끝**

설정 변경 후에는 반드시 Dry-run 테스트를 먼저 실행하세요! 🛠️
