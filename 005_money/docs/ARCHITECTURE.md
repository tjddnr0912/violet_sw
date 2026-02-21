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

## 시장 레짐 분류 (6단계)

| 레짐 | EMA50-EMA200 차이 | 전략 |
|------|-------------------|------|
| Strong Bullish | > +5% | 추세추종 (공격적) |
| Bullish | +2% ~ +5% | 추세추종 (표준) |
| Neutral | -2% ~ +2% | 관망 |
| Bearish | -5% ~ -2% | 평균회귀 (보수적) |
| Strong Bearish | < -5% | 평균회귀 (매우 보수적) |
| Ranging | ADX < 20 | 박스권 매매 |

## 진입 스코어 시스템

```
Entry Score = BB Touch (1점) + RSI Oversold (1점) + Stoch Cross (2점)
최대 4점, 레짐별 최소 스코어 충족 시 진입
```

## 청산 전략

- **Chandelier Exit**: ATR 기반 동적 손절
- **Trailing Stop**: TP1 도달 후 최고가 추적 (2% 하락 시 손절)
- **Profit Target**: BB Middle (약세장) / BB Upper (강세장)
- **Pyramiding**: 최대 3회 추가 진입 (100% → 50% → 25%)

## 리스크 관리

- **관찰 모드**: 연속 손실 시 새 진입 일시 중단 (손절/익절은 정상 처리)

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
