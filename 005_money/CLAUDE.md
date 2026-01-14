# CLAUDE.md - Bithumb Trading Bot

빗썸 거래소 자동매매 봇 프로젝트입니다.

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 거래소 | Bithumb (빗썸) |
| 언어 | Python 3.13+ |
| 현재 버전 | **Ver3** (Portfolio Multi-Coin Strategy) |
| 실행 모드 | CLI / GUI |
| 기본 분석 주기 | 15분 |

## 빠른 시작

```bash
# 권장: Watchdog 모드 (자동 재시작 + hang 감지)
./scripts/run_v3_watchdog.sh

# 단순 CLI 모드
./scripts/run_v3_cli.sh

# GUI 모드
./scripts/run_v3_gui.sh
```

### Watchdog 기능

| 기능 | 설명 |
|------|------|
| Auto-restart | crash 시 자동 재시작 |
| Hang Detection | 10분간 로그 없으면 재시작 |
| Grace Period | 시작 후 2분간 hang 체크 안 함 |

## 디렉토리 구조

```
005_money/
├── 001_python_code/          # 메인 소스 코드
│   ├── ver3/                 # Version 3: 포트폴리오 멀티코인 전략 (프로덕션)
│   │   ├── config_v3.py      # 설정
│   │   ├── config_base.py    # 기본 설정
│   │   ├── trading_bot_v3.py # 메인 봇
│   │   ├── strategy_v3.py    # 매매 전략
│   │   ├── portfolio_manager_v3.py  # 포트폴리오 관리
│   │   ├── live_executor_v3.py      # 주문 실행
│   │   ├── regime_detector.py       # 레짐 분류
│   │   ├── dynamic_factor_manager.py # 동적 파라미터
│   │   └── run_cli.py        # CLI 엔트리포인트
│   └── lib/                  # 공유 라이브러리
│       ├── api/              # Bithumb API 래퍼
│       ├── core/             # 핵심 유틸리티 (로깅, 텔레그램)
│       ├── gui/              # GUI 컴포넌트
│       └── interfaces/       # 인터페이스 정의
├── scripts/                  # 실행 스크립트
├── logs/                     # 로그 파일
├── tests/                    # 테스트 코드
└── .env                      # 환경변수 (API 키, 텔레그램 토큰)
```

## Ver3 핵심 아키텍처

### 주요 컴포넌트

| 파일 | 역할 |
|------|------|
| `trading_bot_v3.py` | 메인 봇 오케스트레이터 |
| `strategy_v3.py` | 매매 전략 (진입/청산 로직) |
| `portfolio_manager_v3.py` | 멀티코인 포트폴리오 관리 |
| `live_executor_v3.py` | 실제 주문 실행 |
| `regime_detector.py` | 6단계 시장 레짐 분류 |
| `dynamic_factor_manager.py` | 동적 파라미터 관리 |
| `monthly_optimizer.py` | 월간 파라미터 최적화 |
| `performance_tracker.py` | 성과 추적 및 분석 |
| `preference_manager_v3.py` | 사용자 설정 관리 |

### 시장 레짐 분류 (6단계)

| 레짐 | EMA50-EMA200 차이 | 전략 |
|------|-------------------|------|
| Strong Bullish | > +5% | 추세추종 (공격적) |
| Bullish | +2% ~ +5% | 추세추종 (표준) |
| Neutral | -2% ~ +2% | 관망 |
| Bearish | -5% ~ -2% | 평균회귀 (보수적) |
| Strong Bearish | < -5% | 평균회귀 (매우 보수적) |
| Ranging | ADX < 20 | 박스권 매매 |

### 진입 스코어 시스템

```
Entry Score = BB Touch (1점) + RSI Oversold (1점) + Stoch Cross (2점)
최대 4점, 레짐별 최소 스코어 충족 시 진입
```

### 청산 전략

- **Chandelier Exit**: ATR 기반 동적 손절
- **Profit Target**: BB Middle (약세장) / BB Upper (강세장)
- **Pyramiding**: 최대 3회 추가 진입 (100% → 50% → 25%)

## 텔레그램 명령어

| 명령어 | 설명 |
|--------|------|
| `/status` | 봇 상태 개요 |
| `/positions` | 포지션 상세 정보 |
| `/factors` | 동적 팩터 현황 |
| `/performance` | 7일 성과 |
| `/close <COIN>` | 특정 코인 청산 |
| `/stop` | 봇 중지 |
| `/reboot` | 봇 재시작 (Watchdog 통해) |

## 환경변수 (.env)

```bash
# Bithumb API
BITHUMB_API_KEY=your_api_key
BITHUMB_SECRET_KEY=your_secret_key

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_NOTIFICATIONS_ENABLED=True
```

## 개발 가이드라인

### 코드 수정 시 주의사항

1. **ver3 전용**: 현재 프로덕션은 ver3만 사용
2. **lib/ 수정 시**: ver3와의 호환성 테스트 필요
3. **전략 수정 시**: `strategy_v3.py`와 `config_v3.py` 동시 수정

### 테스트 실행

```bash
# 단일 분석 테스트
python -c "
from ver3.config_v3 import get_version_config
from ver3.trading_bot_v3 import TradingBotV3
config = get_version_config()
bot = TradingBotV3(config)
result = bot.analyze_market('BTC')
print(result)
"
```

### 로그 확인

```bash
# 오늘 로그
tail -f logs/ver3_cli_$(date +%Y%m%d).log

# 에러만 확인
grep -i error logs/ver3_cli_*.log
```

## 주요 설정값 (config_v3.py)

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `check_interval` | 900 (15분) | 분석 주기 |
| `coins` | BTC, ETH, XRP | 모니터링 코인 |
| `max_positions` | 2 | 최대 동시 포지션 |
| `dry_run` | True | 시뮬레이션 모드 |
| `chandelier_multiplier` | 3.0 | ATR 손절 배수 |

## 트러블슈팅

### telegram.error.Conflict 에러

`start_all_bots.sh`로 실행 시 3개의 봇이 서로 다른 프로젝트/토큰을 사용:

| 탭 | 프로젝트 | 토큰 |
|----|---------|------|
| Trading Bot | 005_money | `859...` |
| News Bot | 006_auto_bot | `843...` |
| Telegram Bot | 006_auto_bot | `843...` |

→ **프로젝트 간 토큰 충돌 아님**. Conflict 발생 시 같은 프로젝트 내 중복 실행 확인:
```bash
ps aux | grep "ver3/run_cli.py"
```

### 봇이 멈추고 API 조회 안 됨

로그에서 Cycle 시작 후 분석 결과가 없으면 **Bithumb API hang** 의심:
- 네트워크 문제 또는 API 서버 응답 지연
- Mac sleep 상태에서 발생 가능

## Hang 방지 시스템

다층 Timeout 보호 체계로 hang 발생 시 자동 복구:

```
Layer 1: API Timeout (5s connect + 15~30s read)
    ↓
Layer 2: ThreadPoolExecutor (60s/coin, 120s total)
    ↓  + Non-blocking shutdown (wait=False, cancel_futures=True)
Layer 3: Analysis Cycle Warning (180s)
    ↓
Layer 4: Consecutive Timeout (3회 연속 → 자동 재시작)
    ↓
Layer 5: Watchdog (600s → kill & restart)
```

### Timeout 설정값

| 레이어 | 위치 | 값 |
|--------|------|-----|
| API (Public) | `bithumb_api.py` | connect=5s, read=30s |
| API (Private) | `bithumb_api.py` | connect=5s, read=15s |
| ThreadPool (per coin) | `portfolio_manager_v3.py` | 60s |
| ThreadPool (total) | `portfolio_manager_v3.py` | 120s |
| Consecutive Timeout | `trading_bot_v3.py` | 3회 |
| Telegram | `telegram_notifier.py` | connect=5s, read=10s |
| Watchdog | `run_v3_watchdog.sh` | 600s |

### Timeout 발생 시 동작

- **API Timeout**: 해당 요청 실패, 재시도 로직
- **ThreadPool Timeout**: 해당 코인 HOLD 처리, 이전 유효 레짐 보존 (`REGIME (⏱)` 표시), 즉시 다음 사이클 진행
- **Consecutive Timeout (3회)**: 🚨 Telegram 알림 + 봇 종료 → Watchdog 재시작
- **Telegram Timeout**: 메시지 드롭, 봇 동작 영향 없음
- **Watchdog Timeout**: 봇 강제 종료 후 재시작

## 참고 문서

- `ver3/VER3_CLI_OPERATION_GUIDE.md` - CLI 운영 가이드
- `002_Doc/` - 상세 문서
- `.claude/rules/` - 코드 분석 규칙
