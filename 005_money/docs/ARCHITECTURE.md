# Architecture

## 디렉토리 구조

```
005_money/
├── 001_python_code/
│   ├── ver3/                        # Version 3: 포트폴리오 멀티코인 전략 (프로덕션)
│   │   ├── config_v3.py             # 설정
│   │   ├── config_base.py           # 기본 설정
│   │   ├── trading_bot_v3.py        # 메인 봇
│   │   ├── strategy_v3.py           # 매매 전략
│   │   ├── portfolio_manager_v3.py  # 포트폴리오 관리
│   │   ├── live_executor_v3.py      # 주문 실행
│   │   ├── regime_detector.py       # 레짐 분류
│   │   ├── dynamic_factor_manager.py # 동적 파라미터
│   │   ├── monthly_optimizer.py     # 월간 파라미터 최적화
│   │   ├── performance_tracker.py   # 성과 추적
│   │   ├── preference_manager_v3.py # 사용자 설정 관리
│   │   └── run_cli.py              # CLI 엔트리포인트
│   └── lib/                         # 공유 라이브러리
│       ├── api/                     # Bithumb API 래퍼
│       ├── core/                    # 로깅, 텔레그램
│       ├── gui/                     # GUI 컴포넌트
│       └── interfaces/              # 인터페이스 정의
├── scripts/                         # 실행 스크립트
├── logs/                            # 로그 파일
├── tests/                           # 테스트 코드
└── .env                             # 환경변수
```

## 시장 레짐 분류 (매크로 6단계 + 마이크로 3단계)

### 매크로 레짐 (일봉 EMA50/EMA200)

| 레짐 | EMA50-EMA200 차이 | 전략 |
|------|-------------------|------|
| Strong Bullish | > +5% | 추세추종 (공격적) |
| Bullish | +2% ~ +5% | 추세추종 (표준) |
| Neutral | -2% ~ +2% | 관망 |
| Bearish | -5% ~ -2% | 평균회귀 (보수적) |
| Strong Bearish | < -5% | 평균회귀 (매우 보수적) |
| Ranging | ADX < 20 | 박스권 매매 |

### 마이크로 레짐 (1H EMA9/EMA21) — Phase 1

| 마이크로 | 조건 | 역할 |
|----------|------|------|
| Micro Bullish | EMA9 > EMA21, 기울기 양수 | 단기 반등 감지 |
| Micro Neutral | EMA 수렴/횡보 | 방향 미확정 |
| Micro Bearish | EMA9 < EMA21, 기울기 음수 | 단기 하락 지속 |

### 매크로×마이크로 조합 (Bear 구간 핵심)

| 매크로 | 마이크로 | modifier | extreme_os | 모멘텀 필터 |
|--------|----------|----------|------------|------------|
| bearish | micro_bullish | **1.1** | **No** | **No** |
| bearish | micro_neutral | 1.3 | Yes | Yes |
| bearish | micro_bearish | 2.0 | Yes | Yes |
| strong_bearish | micro_bullish | **1.3** | Yes | **No** |

## 진입 스코어 시스템 (6점 체계)

```
기본 지표 (4점):
  BB Touch (1점) + RSI Oversold (1점) + Stoch Cross (2점)

Phase 2 지표 (2점):
  VWAP Cross (1점) + MACD Cross (1점)

보너스: Deep BB (0.5) + RSI Divergence (1.0) + Vol Confirm (0.5) + RSI Convergence (0~2.0)
```

## Phase별 피처 플래그 (config_base.py)

| Phase | 플래그 | 설명 |
|-------|--------|------|
| 1 | `enable_multi_tf_regime` | 매크로+마이크로 듀얼 레짐 |
| 2 | `enable_vwap_macd` | VWAP+MACD 지표 (6점 체계) |
| 3 | `enable_adaptive_weights` | 승률 기반 자동 가중치 조정 |
| 4 | `enable_orderbook_analysis` | 호가창 매수/매도 압력 분석 |
| 4 | `enable_volume_profile` | Volume Profile 참고 지표 |

## 청산 전략

- **Chandelier Exit**: ATR 기반 동적 손절
- **Trailing Stop**: TP1 도달 후 최고가 추적 (2% 하락 시 손절)
- **Profit Target**: BB Middle (약세장) / BB Upper (강세장)
- **Pyramiding**: 최대 3회 추가 진입 (100% → 50% → 25%)
- **Orderbook Block**: BUY 시 매도벽 감지 시 진입 차단 (Phase 4)

## 리스크 관리

- **관찰 모드**: 연속 손실 시 새 진입 일시 중단 (손절/익절은 정상 처리)
- **적응형 가중치**: 지표별 승률 기반 자동 가중치 조정 (Phase 3)

## Watchdog 기능

| 기능 | 설명 |
|------|------|
| Auto-restart | crash 시 자동 재시작 |
| Hang Detection | 10분간 로그 없으면 재시작 |
| Grace Period | 시작 후 2분간 hang 체크 안 함 |

## 주요 설정값 (config_v3.py)

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `check_interval` | 900 (15분) | 분석 주기 |
| `coins` | BTC, ETH, XRP | 모니터링 코인 |
| `max_positions` | 2 | 최대 동시 포지션 |
| `dry_run` | True | 시뮬레이션 모드 |
| `chandelier_multiplier` | 3.0 | ATR 손절 배수 |

## 테스트

```bash
python -c "
from ver3.config_v3 import get_version_config
from ver3.trading_bot_v3 import TradingBotV3
config = get_version_config()
bot = TradingBotV3(config)
result = bot.analyze_market('BTC')
print(result)
"
```

## 로그 확인

```bash
tail -f logs/ver3_cli_$(date +%Y%m%d).log
grep -i error logs/ver3_cli_*.log
```
