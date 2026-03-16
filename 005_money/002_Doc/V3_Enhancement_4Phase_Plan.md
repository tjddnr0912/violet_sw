# V3 Trading Bot - 4-Phase Enhancement Plan

> 작성일: 2026-03-16
> 목적: 하락장 수익성 개선을 위한 알고리즘 근본 재설계

---

## 현재 문제 진단

| 취약점 | 현상 | 근본 원인 |
|--------|------|-----------|
| 하락장 동면 | Bear 레짐에서 진입 0건 | 4중 게이트(Crash/Momentum/Score/ExtremeOS) |
| R:R 역전 | 손실 > 수익 구조 | profit +0.8% vs stop -1.5% |
| 후행 진입 | 반등 후 한참 뒤 진입 | BB/RSI/StochRSI 모두 후행 지표 |
| 레짐 지연 | 전환 시점 15분+ 지연 | 일봉 EMA50/200 단일 레짐 |
| 상관 리스크 | BTC+ETH 동시 손절 | correlation check 비활성화 |

---

## Phase 구조 및 의존성

```
Phase 1 (Multi-TF Regime)     ← 가장 임팩트 큼, 최우선
    ↓
Phase 2 (VWAP + MACD)         ← Phase 1과 독립 배포 가능
    ↓
Phase 3 (Adaptive Weights)    ← Phase 1+2 완료 후 효과 극대화
    ↓
Phase 4 (Orderbook + Volume Profile)  ← 완전 독립, 어느 시점에도 가능
```

---

## Phase 1: 멀티 타임프레임 레짐 엔진 재설계

### 목표
일봉이 bearish라도 1H가 반등 중이면 진입 허용. "매크로 + 마이크로" 2레이어 레짐.

### 핵심 변경

**현재:**
```
일봉 EMA50/200 → 단일 레짐(6단계) → entry_threshold_modifier 고정
```

**개선:**
```
일봉 EMA50/200 → 매크로 레짐(6단계)
1H EMA9/21    → 마이크로 레짐(3단계: micro_bullish/neutral/bearish)
                    ↓
              조합 매트릭스 → 세밀한 modifier + position_size
```

### 매크로×마이크로 조합 매트릭스 (핵심 개선 영역)

| 매크로 | 마이크로 | modifier | pos_mult | extreme_os 필요 |
|--------|----------|----------|----------|-----------------|
| bearish | micro_bullish | **1.1** | 0.6 | **No** |
| bearish | micro_neutral | 1.3 | 0.5 | Yes |
| bearish | micro_bearish | 2.0 | 0.3 | Yes |
| strong_bearish | micro_bullish | **1.3** | 0.4 | Yes |
| strong_bearish | micro_neutral | 1.8 | 0.3 | Yes |
| strong_bearish | micro_bearish | 2.5 | 0.2 | Yes |

> **핵심:** `bearish + micro_bullish`에서 extreme_oversold 게이트 제거 → 하락장 반등 진입 가능

### 마이크로 레짐 판단 로직

```
EMA9(1H) vs EMA21(1H):
  - EMA9 > EMA21 AND 기울기 양수 → MICRO_BULLISH
  - EMA9 < EMA21 AND 기울기 음수 → MICRO_BEARISH
  - 그 외 → MICRO_NEUTRAL

+ Multi-TF RSI 컨버전스 보너스:
  - 일봉 RSI<40 AND 1H RSI<35 → convergence_score +1.0
  - 일봉 RSI 하락 중인데 1H RSI 상승 → divergence_score +0.5
```

### 수정 파일

| 파일 | 작업 |
|------|------|
| `regime_detector.py` | `MicroRegimeDetector`, `get_composite_strategy()` 추가 (~200줄) |
| `config_base.py` | `MULTI_TF_REGIME_CONFIG` 섹션 추가 |
| `config_v3.py` | `enable_multi_tf_regime: bool` 플래그 |
| `strategy_v3.py` | `analyze_market()` Step 4 이후 마이크로 레짐 통합 (~30줄) |
| `dynamic_factor_manager.py` | `DynamicFactors`에 마이크로 레짐 필드 추가 |

### 호환성
- `enable_multi_tf_regime: False` 기본값 → 기존 동작 100% 유지
- 기존 `ExtendedRegime`, `get_regime_strategy()` 인터페이스 변경 없음
- `exec_df`(1H 데이터)는 이미 fetch되므로 추가 API 호출 없음

### 검증
1. 코드 배포 (기능 OFF)
2. dry_run에서 1주일 로그 관찰: `[REGIME] macro=bearish micro=micro_bullish`
3. bearish 구간 진입 건수 변화 확인 후 live 전환

### 규모: ~250-300줄

---

## Phase 2: VWAP + MACD 지표 플러그인

### 목표
선행 지표 추가로 진입 타이밍 개선. 스코어 4점 → 6점 체계로 확장.

### 핵심 변경

**스코어 시스템 확장:**
```
[기존 4점]                    [Phase 2: 6점]
BB Touch:     1점              BB Touch:     1점
RSI Oversold: 1점              RSI Oversold: 1점
Stoch Cross:  2점              Stoch Cross:  2점
                               VWAP Cross:   1점 (신규)
                               MACD Cross:   1점 (신규)
```

### VWAP 계산
- 빗썸은 세션 개념 없음 → **24봉 롤링 VWAP** 사용 (24/7 암호화폐 표준)
- `VWAP = Sum(TP × Volume, 24) / Sum(Volume, 24)` (TP = (H+L+C)/3)

**VWAP 스코어 조건:**
```
VWAP 상향 돌파 (이전봉 VWAP 아래 → 현재봉 위)  → 1.0점
VWAP 아래 2% 이내 + RSI<35 (지지 구간)           → 0.5점
```

### MACD 계산
- EMA12/26/Signal9 (표준 설정)

**MACD 스코어 조건:**
```
MACD 시그널 상향 돌파 + 0선 아래  → 1.0점 (강한 반등 신호)
MACD 시그널 상향 돌파 + 0선 위    → 0.7점
히스토그램 반전(음→덜 음) + 0선 아래 → 0.5점
```

### min_score 재조정
- 6점 체계에서 `min_entry_score: 2.5`로 상향
- 피처 플래그 OFF 시 기존 2점 기준 유지

### 수정 파일

| 파일 | 작업 |
|------|------|
| `strategy_v3.py` | VWAP/MACD 계산 함수, 스코어 확장 (~140줄) |
| `config_base.py` | VWAP/MACD 파라미터 추가 |
| `config_v3.py` | `enable_vwap_macd: bool` 플래그 |
| `dynamic_factor_manager.py` | `entry_weight_vwap`, `entry_weight_macd` 추가 |
| `performance_tracker.py` | `entry_conditions`에 `vwap_cross`, `macd_cross` 추가 |

### 검증
- 지난 30일 데이터로 VWAP 신호 소급: 돌파 후 4시간 내 상승 비율 >60% 확인
- MACD 0선 아래 크로스 후 8시간 내 상승 비율 >55% 확인
- TradingView 수치와 ±0.5% 오차 이내 비교

### 규모: ~200-250줄

---

## Phase 3: 적응형 가중치 시스템

### 목표
지표별 승률을 추적하여 자동으로 가중치 조정. "잘 맞는 지표는 올리고, 안 맞는 지표는 낮추는" 자기 교정.

### 핵심 변경

**현재 (수동 규칙):**
```python
# dynamic_factor_manager.py - update_weekly_factors()
if win_rate > 0.6: min_score = 2    # 하드코딩
if win_rate < 0.4: min_score = 3    # 하드코딩
```

**개선 (데이터 기반):**
```
최근 50거래에서 지표별 승률 계산
    ↓
win_rate > 55% → 가중치 상향
win_rate < 45% → 가중치 하향
    ↓
EMA 스무딩 (0.3 × new + 0.7 × current)으로 급변 방지
    ↓
레짐별 독립 가중치 테이블 유지
```

### 가중치 계산 공식
```
raw_weight = 0.5 + (win_rate - 0.5) × 2.0

예시:
  win_rate 0.30 → weight 0.6
  win_rate 0.50 → weight 1.0 (중립)
  win_rate 0.60 → weight 1.2
  win_rate 0.75 → weight 1.5

클램핑: [0.4, 2.0]
```

### 레짐별 독립 가중치

```json
// adaptive_weights_v3.json
{
  "by_macro_regime": {
    "bearish": {
      "bb_touch": 1.2, "vwap_cross": 1.5, "macd_cross": 0.6,
      "sample_size": 8
    },
    "bullish": {
      "bb_touch": 0.8, "stoch_cross": 1.4,
      "sample_size": 15
    }
  },
  "global_fallback": { ... }  // sample_size < min_trades인 레짐용
}
```

### 동적 트리거 (주간 외 추가)
- 최근 5건 중 3건 이상 동일 지표 실패 → 즉시 해당 지표 가중치 0.6으로 임시 하향
- 10건 거래 후 주간 업데이트로 복구 가능

### 수정 파일

| 파일 | 작업 |
|------|------|
| `dynamic_factor_manager.py` | `AdaptiveWeightEngine` 내부 클래스, 주간 업데이트 교체 (~200줄) |
| `performance_tracker.py` | `get_indicator_performance()` 메서드 추가 (~50줄) |
| `config_base.py` | `ADAPTIVE_WEIGHT_CONFIG` 섹션 |
| `config_v3.py` | `enable_adaptive_weights: bool` 플래그 |

### 전제 조건
- Phase 1+2 완료 후 최소 30거래 기록 필요
- `min_trades` 미충족 레짐은 자동으로 `global_fallback` 사용

### 규모: ~250-300줄

---

## Phase 4: 호가창 분석 + Volume Profile

### 목표
캔들 데이터를 넘어서 실시간 매수/매도 압력과 과거 거래량 분포로 진입 정밀도 향상.

### 핵심 변경

**호가창 분석 (OrderbookAnalyzer):**
```
Bithumb API: GET /public/orderbook/{coin}_KRW (count=30)
    ↓
매수/매도 잔량 비율(bid_ask_ratio) 계산
대형 매수 벽/매도 벽 감지 (현재가 ±3% 이내)
    ↓
BUY 신호 직전에만 실행 (불필요한 API 요청 방지)
    ↓
매도 벽 감지 시 진입 차단
매수 압력 > 1.5배 시 signal_strength 강화
```

**Volume Profile:**
```
1H OHLCV 최근 50봉
    ↓
가격대별 거래량 분포 계산 (30 bins)
    ↓
POC (최대 거래 가격), Value Area (70% 거래량 구간) 식별
    ↓
현재가가 VA Low 근처 → 지지 구간 확인
    ↓
참고 지표로만 사용 (스코어 미반영, GUI/로그 표시)
```

### 수정 파일

| 파일 | 작업 |
|------|------|
| `lib/api/bithumb_api.py` | `get_orderbook()` 함수 추가 (~30줄) |
| `strategy_v3.py` | `OrderbookAnalyzer`, `VolumeProfileAnalyzer` 추가 (~220줄) |
| `config_base.py` | `ORDERBOOK_CONFIG`, `VOLUME_PROFILE_CONFIG` 섹션 |
| `config_v3.py` | `enable_orderbook_analysis`, `enable_volume_profile` 플래그 |

### 위험 요소
- 호가창 스푸핑(허위 매수 벽) → `bid_ask_ratio`(전체 압력)를 주 신호로 사용
- API Rate Limit → BUY 신호 시에만 호출 + 100ms 간격
- Volume Profile 근사치 → OHLCV 균등분배 (정밀 지표가 아닌 참고용)

### 규모: ~280-320줄

---

## 배포 로드맵

```
Week 1-2:  Phase 1 구현 + 코드 배포 (OFF)
Week 3:    Phase 1 dry_run 검증
Week 4:    Phase 1 live 전환
Week 5-6:  Phase 2 구현 + 코드 배포 (OFF)
Week 7:    Phase 2 dry_run 검증 + live 전환
Week 8-10: 거래 데이터 축적 (최소 30건)
Week 11:   Phase 3 구현 + 배포
Week 12+:  Phase 4 구현 (독립 일정)
```

## 총 구현 규모

| Phase | 순수 로직 | 핵심 파일 |
|-------|-----------|-----------|
| 1 | ~300줄 | regime_detector.py |
| 2 | ~250줄 | strategy_v3.py |
| 3 | ~300줄 | dynamic_factor_manager.py |
| 4 | ~320줄 | strategy_v3.py, bithumb_api.py |
| **합계** | **~1,170줄** | |

## 공통 안전장치

- 모든 Phase는 **피처 플래그**로 보호 → 배포 후에도 기존 동작 유지
- 기존 인터페이스(`ExtendedRegime`, `get_regime_strategy()`, `analyze_market()` 반환 구조) 변경 없음
- 프로덕션 봇 운영 중 breaking change 없음
