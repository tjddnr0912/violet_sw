# Ver3 CLI 운영 가이드

## 목차
1. [개요](#1-개요)
2. [실행 방법](#2-실행-방법)
3. [분석 주기 및 리밸런싱](#3-분석-주기-및-리밸런싱)
4. [시장 레짐 분류](#4-시장-레짐-분류)
5. [매수 전략](#5-매수-전략)
6. [매도 전략](#6-매도-전략)
7. [동적 팩터 시스템](#7-동적-팩터-시스템)
8. [텔레그램 알림](#8-텔레그램-알림)
9. [로그 파일](#9-로그-파일)
10. [설정값 요약](#10-설정값-요약)

---

## 1. 개요

Ver3는 **멀티코인 포트폴리오 트레이딩 전략**으로, 다음 특징을 가집니다:

- **듀얼 타임프레임 분석**: Daily(레짐 판단) + 4H(진입 신호)
- **6단계 레짐 분류**: 강한 상승, 상승, 중립, 하락, 강한 하락, 횡보
- **동적 파라미터 조정**: 변동성, 성과에 따른 자동 조정
- **하락장 평균회귀 전략**: 베어마켓에서도 엄격한 조건 하에 매매

### 아키텍처

```
TradingBotV3
    ├── PortfolioManagerV3 (멀티코인 조율)
    │   ├── CoinMonitor (BTC)
    │   ├── CoinMonitor (ETH)
    │   └── CoinMonitor (XRP)
    │
    ├── StrategyV3 (듀얼 타임프레임 전략)
    │   ├── RegimeDetector (6-레짐 분류)
    │   └── DynamicFactorManager (동적 파라미터)
    │
    ├── LiveExecutorV3 (주문 실행)
    └── PerformanceTracker (성과 추적)
```

---

## 2. 실행 방법

### CLI 실행

```bash
# 기본 실행 (권장)
cd 005_money
./run.sh

# 또는 직접 실행
cd 001_python_code
python main.py --version ver3

# 특정 코인만 실행
python main.py --version ver3 --coins BTC,ETH
```

### 환경 변수 설정

```bash
# .env 파일에 설정 필요
BITHUMB_CONNECT_KEY=your_connect_key
BITHUMB_SECRET_KEY=your_secret_key
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_NOTIFICATIONS_ENABLED=True
```

---

## 3. 분석 주기 및 리밸런싱

### 분석 주기

| 주기 | 간격 | 업데이트 내용 |
|------|------|--------------|
| **실시간** | 15분 | ATR 기반 스탑로스, 포지션 크기 조정 |
| **4시간** | ATR 15%+ 변동 시 | RSI/Stoch 임계값 조정 |
| **일간** | 매일 00:00 | 레짐 파라미터, BB 설정 |
| **주간** | 일요일 00:00 | 진입 가중치 (성과 기반) |
| **월간** | 월초 | 전체 파라미터 최적화 (Walk-Forward) |

### 분석 사이클 흐름

```
매 15분마다:
1. 모든 코인 병렬 분석 (ThreadPoolExecutor)
2. 레짐 변경 감지 → 텔레그램 알림
3. 포트폴리오 레벨 결정
   - 스탑로스 체크 (최우선)
   - 익절 목표 체크
   - 신규 진입 검토
4. 주문 실행
5. 요약 로깅
```

### 포지션 리밸런싱

- **최대 동시 포지션**: 2개
- **코인당 최대 포지션**: 1개 (피라미딩 시 최대 3개 진입)
- **현금 보유율**: 20%
- **포지션 크기**: 코인당 50,000 KRW (변동성에 따라 조정)

---

## 4. 시장 레짐 분류

### 6단계 레짐 시스템

Daily EMA(50/200) 기반으로 시장 상태를 6단계로 분류합니다:

| 레짐 | 조건 | 전략 모드 | 진입 난이도 |
|------|------|----------|------------|
| **Strong Bullish** | EMA50 > EMA200 +5% | Trend Following | 쉬움 (0.8x) |
| **Bullish** | EMA50 > EMA200 | Trend Following | 보통 (1.0x) |
| **Neutral** | EMAs 근접 (1% 이내) | Oscillation | 보통 (1.2x) |
| **Bearish** | EMA50 < EMA200 | Mean Reversion | 어려움 (1.5x) |
| **Strong Bearish** | EMA50 < EMA200 -5% | Mean Reversion | 매우 어려움 (2.0x) |
| **Ranging** | ADX < 15 | Oscillation | 보통 (1.0x) |

### 레짐별 전략 파라미터

```
Strong Bullish:
  - 스탑로스: 넓음 (1.2x)
  - 목표가: BB Upper
  - 익절: 50%→BB Middle, 50%→BB Upper

Bearish/Strong Bearish:
  - 스탑로스: 타이트 (0.5~0.7x)
  - 목표가: BB Middle
  - 익절: BB Middle에서 100% 전량 매도 (보수적)
  - 추가 조건: Extreme Oversold 필수
```

---

## 5. 매수 전략

### 진입 점수 시스템 (4점 만점)

4H 타임프레임에서 다음 조건을 점수화합니다:

| 조건 | 기본 점수 | 설명 |
|------|----------|------|
| **BB Lower Touch** | 1점 | 가격이 BB 하단에 터치 |
| **RSI Oversold** | 1점 | RSI < 30 (동적 조정) |
| **Stoch Cross** | 2점 | K가 D 상향돌파 + 둘 다 < 20 |

### 진입 조건

```python
# 기본 조건
if entry_score >= min_entry_score:  # 기본 2점
    allow_entry = True

# 레짐별 조정
adjusted_min_score = base_min_score * regime_modifier
# Strong Bearish: 2 * 2.0 = 4점 필요 (모든 조건 충족)
# Bullish: 2 * 1.0 = 2점 필요
```

### 하락장 진입 추가 조건

Bearish/Strong Bearish 레짐에서는 **Extreme Oversold** 조건 필수:

```
3개 중 2개 이상 충족 필요:
1. RSI < 20 (극단적 과매도)
2. Stochastic K < 10
3. 가격이 BB Lower 이하
```

### 피라미딩 (추가 진입)

기존 포지션이 있을 때 추가 진입 조건:

- 피라미딩 활성화 (config)
- 최대 3회 진입 (1차 + 2회 추가)
- 점수 3점 이상
- 신호 강도 0.7 이상
- 이전 진입가 대비 2%+ 상승
- Bullish 또는 Neutral 레짐에서만

포지션 크기: 1차 100%, 2차 50%, 3차 25%

---

## 6. 매도 전략

### 스탑로스 (Chandelier Exit)

```python
stop_price = highest_high - (ATR × multiplier × regime_modifier × volatility_modifier)

# 예시 (Bearish 레짐, High 변동성)
base_multiplier = 3.0
regime_modifier = 0.7    # Bearish
volatility_modifier = 1.2  # High volatility
final_multiplier = 3.0 * 0.7 * 1.2 = 2.52

stop_price = 최근14봉_최고가 - (ATR × 2.52)
```

### 익절 목표

**Bullish 레짐:**
```
1차 목표 (50% 매도): BB Middle
  → 달성 시 스탑로스를 진입가(손익분기)로 이동
2차 목표 (나머지 전량): BB Upper
```

**Bearish 레짐:**
```
1차 목표 (100% 전량 매도): BB Middle
  → 보수적 전략으로 빠른 청산
```

### 매도 우선순위

```
1. 스탑로스 체크 (최우선)
2. 익절 목표 체크
3. 전략 신호에 의한 매도
```

---

## 7. 동적 팩터 시스템

### 변동성 분류

ATR%에 따라 변동성을 4단계로 분류합니다:

| 레벨 | ATR% 범위 | 스탑로스 배수 | 포지션 크기 |
|------|----------|--------------|------------|
| LOW | < 1.5% | 0.8x (타이트) | 1.2x (크게) |
| NORMAL | 1.5~3% | 1.0x | 1.0x |
| HIGH | 3~5% | 1.2x (넓게) | 0.7x (작게) |
| EXTREME | > 5% | 1.5x (매우 넓게) | 0.5x (매우 작게) |

### 팩터 업데이트 스케줄

| 업데이트 | 시점 | 조정 항목 |
|---------|------|----------|
| **실시간** | 매 분석 사이클 | ATR 스탑로스 배수, 포지션 크기 |
| **4시간** | ATR 15%+ 변동 시 | RSI/Stoch 임계값 |
| **일간** | 00:00~00:15 | BB 기간, 레짐 파라미터 |
| **주간** | 일요일 00:00 | 진입 가중치 (성과 기반) |

### 주간 성과 기반 조정

최근 7일 거래 성과를 분석하여 진입 가중치를 조정합니다:

```python
# 각 조건별 승률 계산
bb_win_rate = BB터치_승리 / BB터치_총거래
rsi_win_rate = RSI과매도_승리 / RSI과매도_총거래
stoch_win_rate = Stoch크로스_승리 / Stoch크로스_총거래

# 가중치 재분배 (합계 4점 유지)
# 승률 높은 조건에 더 높은 가중치 부여

# 전체 승률에 따른 진입 난이도 조정
if win_rate < 0.4:
    min_entry_score = 3  # 보수적
elif win_rate > 0.6:
    min_entry_score = 2  # 적극적
```

---

## 8. 텔레그램 알림

### 사용 가능한 명령어

| 명령어 | 설명 |
|--------|------|
| `/start` | 시작 메시지 |
| `/help` | 명령어 목록 |
| `/status` | 봇 상태, 포지션, 사이클 정보 |
| `/positions` | 상세 포지션 정보 |
| `/summary` | 당일 거래 요약 |
| `/factors` | 동적 팩터 현황 |
| `/performance` | 7일 성과 요약 |
| `/stop` | 봇 중지 (확인 필요) |

### 자동 알림

| 이벤트 | 알림 내용 |
|--------|----------|
| **봇 시작/종료** | 상태, 포지션 수, 모니터링 코인 |
| **레짐 변경** | 이전→현재 레짐, EMA 격차 |
| **거래 실행** | BUY/SELL 성공/실패, 가격, 수량 |
| **일일 팩터 업데이트** | Chandelier 배수, 포지션 크기, RSI 임계값 |
| **주간 팩터 업데이트** | 진입 가중치, 최소 스코어 |
| **일일 요약** | 23:50에 당일 거래 요약 |

### 알림 예시

```
🚨 중요 레짐 전환!

⏰ 시각: 2025-12-28 15:00:00
🪙 대상: BTC

변경 내역
이전: 📈 상승장
현재: 📉 하락장

EMA 격차: -3.50%

_전략이 새 레짐에 맞게 조정됩니다._
```

---

## 9. 로그 파일

### 로그 위치

```
005_money/logs/
├── ver3_cli_YYYYMMDD.log      # 메인 로그
├── transaction_history.json    # 거래 내역
├── dynamic_factors_v3.json     # 동적 팩터 상태
├── performance_history_v3.json # 성과 기록
├── positions_v3.json           # 현재 포지션
└── last_executed_actions_v3.json # 마지막 실행 액션
```

### 로그 레벨

- **INFO**: 분석 사이클, 거래 결정, 팩터 업데이트
- **WARNING**: API 오류, 텔레그램 실패, 스탑로스 트리거
- **ERROR**: 치명적 오류, 거래 실패

---

## 10. 설정값 요약

### 포트폴리오 설정

| 항목 | 값 | 설명 |
|------|---|------|
| `max_positions` | 2 | 최대 동시 포지션 |
| `default_coins` | BTC, ETH, XRP | 기본 모니터링 코인 |
| `reserve_cash_pct` | 20% | 현금 보유 비율 |
| `check_interval` | 900초 (15분) | 분석 주기 |

### 진입 설정

| 항목 | 값 | 설명 |
|------|---|------|
| `min_entry_score` | 2 | 기본 최소 진입 점수 |
| `bb_touch_points` | 1 | BB 터치 점수 |
| `rsi_oversold_points` | 1 | RSI 과매도 점수 |
| `stoch_cross_points` | 2 | Stoch 크로스 점수 |
| `rsi_oversold` | 30 | RSI 과매도 기준 |
| `stoch_oversold` | 20 | Stoch 과매도 기준 |

### 리스크 관리

| 항목 | 값 | 설명 |
|------|---|------|
| `trade_amount_krw` | 50,000 | 기본 거래 금액 |
| `chandelier_multiplier` | 3.0 | ATR 배수 |
| `max_portfolio_risk_pct` | 6% | 포트폴리오 총 리스크 |

### 동적 팩터 범위

| 항목 | 범위 | 설명 |
|------|------|------|
| `chandelier_multiplier` | 2.0~5.0 | ATR 배수 범위 |
| `position_size_multiplier` | 0.3~1.5 | 포지션 크기 배율 |
| `rsi_threshold` | 20~40 | RSI 임계값 범위 |
| `min_entry_score` | 1~4 | 최소 진입 점수 범위 |

---

## 참고: 레짐별 전략 요약 테이블

| 레짐 | 진입 모드 | 스탑 | 목표 | 익절 방식 | 진입 난이도 |
|------|----------|------|------|----------|------------|
| Strong Bullish | Trend | 넓음 | BB Upper | 50%→50% | 쉬움 |
| Bullish | Trend | 보통 | BB Upper | 50%→50% | 보통 |
| Neutral | Oscillation | 좁음 | BB Middle | 50%→50% | 보통 |
| Bearish | Reversion | 타이트 | BB Middle | **100% 전량** | 어려움 |
| Strong Bearish | Reversion | 매우 타이트 | BB Middle | **100% 전량** | 매우 어려움 |
| Ranging | Oscillation | 타이트 | BB Middle | 50%→50% | 보통 |

---

*마지막 업데이트: 2025-12-28*
