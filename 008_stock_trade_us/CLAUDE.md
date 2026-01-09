# CLAUDE.md - 미국 주식 퀀트 자동매매 시스템

이 문서는 Claude Code가 코드 작업 시 참조하는 프로젝트 가이드입니다.

## 프로젝트 개요

한국투자증권(KIS) Open API를 활용한 **미국 주식** 멀티팩터 퀀트 자동매매 시스템입니다.
- **전략**: 모멘텀(20%) + 단기모멘텀(10%) + 저변동성(50%) + 거래량(0%)
- **유니버스**: S&P500 구성종목
- **목표**: 상위 15개 종목 선정 및 자동 리밸런싱
- **참고**: 007_stock_trade (한국 주식) 버전과 동일한 아키텍처 기반

## 프로젝트 구조

```
008_stock_trade_us/
├── src/
│   ├── __init__.py
│   ├── quant_engine.py          # 퀀트 자동매매 엔진 (기본)
│   ├── us_quant_engine.py       # 미국 주식 전용 퀀트 엔진
│   ├── engine.py                # 엔진 기본 클래스
│   ├── api/
│   │   ├── __init__.py
│   │   ├── kis_client.py        # KIS API 기본 클라이언트
│   │   ├── kis_us_client.py     # 미국 주식 전용 클라이언트
│   │   ├── kis_auth.py          # 인증 모듈
│   │   ├── kis_quant.py         # 퀀트용 확장 클라이언트
│   │   └── kis_websocket.py     # WebSocket 실시간 시세
│   ├── core/
│   │   ├── __init__.py
│   │   └── system_controller.py # 시스템 원격 제어 (싱글톤)
│   ├── scheduler/
│   │   ├── __init__.py
│   │   └── auto_manager.py      # 월간 모니터링, 반기 최적화
│   ├── strategy/
│   │   ├── __init__.py
│   │   ├── base.py              # 전략 기본 클래스
│   │   ├── indicators.py        # 기술적 지표
│   │   ├── strategies.py        # 전략 구현
│   │   ├── us_screener.py       # 미국 주식 스크리너
│   │   ├── us_universe.py       # 미국 주식 유니버스 (S&P500)
│   │   └── quant/
│   │       ├── __init__.py
│   │       ├── factors.py       # 팩터 계산기
│   │       ├── screener.py      # 멀티팩터 스크리너
│   │       ├── signals.py       # 기술적 신호 생성
│   │       ├── risk.py          # 리스크 관리
│   │       ├── backtest.py      # 백테스팅
│   │       ├── analytics.py     # 성과 분석
│   │       └── sector.py        # 섹터 분산
│   ├── telegram/
│   │   ├── __init__.py
│   │   └── bot.py               # 텔레그램 봇 (알림 + 명령어)
│   └── utils/
│       └── __init__.py
├── scripts/
│   ├── run_daemon.py            # 통합 데몬 (권장)
│   ├── run_backtest.py          # 백테스트
│   └── ...
├── config/
│   ├── optimal_weights.json     # 최적 가중치
│   ├── system_config.json       # 시스템 설정
│   └── token.json               # KIS API 토큰
├── data/
│   └── quant/                   # 상태/포지션 데이터
├── logs/                        # 로그 파일
├── run_quant.sh                 # 메인 실행 스크립트
├── requirements.txt
└── CLAUDE.md
```

## 텔레그램 원격 제어 (핵심 기능)

### 시스템 제어
| 명령어 | 설명 |
|--------|------|
| `/start_trading` | 자동매매 시작 |
| `/stop_trading` | 자동매매 중지 |
| `/pause` | 일시 정지 |
| `/resume` | 재개 |
| `/emergency_stop` | 🚨 긴급 정지 (모든 거래 즉시 중단) |
| `/clear_emergency` | 긴급 정지 해제 |

### 수동 실행
| 명령어 | 설명 |
|--------|------|
| `/run_screening` | 스크리닝 즉시 실행 |
| `/run_rebalance` | 리밸런싱 즉시 실행 |
| `/run_optimize` | 가중치 최적화 실행 |

### 설정 변경
| 명령어 | 설명 |
|--------|------|
| `/set_dryrun on\|off` | Dry-run 모드 변경 |
| `/set_target [N]` | 목표 종목 수 변경 |
| `/set_stoploss [N]` | 손절 비율(%) 변경 |

### 조회
| 명령어 | 설명 |
|--------|------|
| `/status` | 시스템 상태 (상태, 설정, 가중치) |
| `/positions` | 보유 포지션 |
| `/balance` | 계좌 잔고 |
| `/logs` | 최근 로그 |
| `/report` | 일일 리포트 |

### 포지션 관리
| 명령어 | 설명 |
|--------|------|
| `/close [종목코드]` | 특정 종목 청산 |
| `/close_all` | 전체 청산 |

### 분석
| 명령어 | 설명 |
|--------|------|
| `/screening` | 스크리닝 결과 조회 |
| `/signal [종목코드]` | 기술적 분석 |
| `/price [종목코드]` | 현재가 조회 |

## 핵심 모듈 설명

### 1. SystemController (`src/core/system_controller.py`)

텔레그램을 통한 원격 제어 싱글톤 컨트롤러입니다.

```python
from src.core import get_controller

controller = get_controller()

# 상태 관리
controller.start_trading()      # 시작
controller.stop_trading()       # 중지
controller.pause_trading()      # 일시정지
controller.resume_trading()     # 재개
controller.emergency_stop()     # 긴급정지

# 설정 변경
controller.set_dry_run(True)    # Dry-run 모드
controller.set_target_count(15) # 목표 종목 수
controller.set_stop_loss(7.0)   # 손절 비율

# 콜백 등록 (엔진 연동)
controller.register_callback('on_start', engine.start)
controller.register_callback('on_screening', engine.run_screening)
```

**시스템 상태**:
- `STOPPED` - 중지됨
- `RUNNING` - 실행중
- `PAUSED` - 일시정지
- `EMERGENCY_STOP` - 긴급정지

### 2. AutoStrategyManager (`src/scheduler/auto_manager.py`)

자동화된 전략 관리:
- **월간 모니터링**: 매월 1일 09:00 자동 실행
- **반기 최적화**: 1월, 7월 첫째주 자동 실행
- **가중치 자동 업데이트**: 최적화 결과 자동 반영

```python
from src.scheduler import AutoStrategyManager

manager = AutoStrategyManager()
manager.start()  # 스케줄러 시작

# 수동 실행
manager.run_monitoring()   # 모니터링
manager.run_optimization() # 최적화
```

### 3. TelegramBot (`src/telegram/bot.py`)

20+ 명령어를 지원하는 양방향 텔레그램 봇:

```python
from src.telegram.bot import TelegramBotHandler

handler = TelegramBotHandler()
handler.start()  # 폴링 시작
```

**새 명령어 추가 방법**:
1. `TelegramBot` 클래스에 `async def cmd_XXX(self, update, context)` 메서드 추가
2. `build_application()`에 핸들러 등록:
   ```python
   self.application.add_handler(CommandHandler("xxx", self.cmd_xxx))
   ```
3. `cmd_help()` 도움말 업데이트

### 4. QuantTradingEngine (`src/quant_engine.py`)

```python
config = QuantEngineConfig(
    universe_size=200,
    target_stock_count=15,
    dry_run=True
)
engine = QuantTradingEngine(config, is_virtual=True)
engine.start()  # 스케줄 기반 자동 실행
```

## 실행 방법

```bash
# 통합 데몬 실행 (권장)
./run_quant.sh daemon

# 개별 명령어
./run_quant.sh screen        # 1회 스크리닝
./run_quant.sh screen-full   # 전체 스크리닝 + 엑셀
./run_quant.sh backtest      # 백테스트
./run_quant.sh optimize      # 가중치 최적화
./run_quant.sh monitor       # 전략 모니터링
./run_quant.sh status        # 상태 확인
./run_quant.sh test          # API 테스트
./run_quant.sh telegram      # 텔레그램 테스트

# 옵션
--dry-run / --no-dry-run     # Dry-run 모드
--virtual / --real           # 모의투자 / 실전투자
--universe 100               # 유니버스 크기
--target 15                  # 목표 종목 수
```

## 팩터 가중치 (최적화 결과)

`config/optimal_weights.json`:
```json
{
  "momentum_weight": 0.20,
  "short_mom_weight": 0.10,
  "volatility_weight": 0.50,
  "volume_weight": 0.00,
  "target_count": 15,
  "baseline_sharpe": 2.39,
  "baseline_return": 8.99,
  "baseline_mdd": -2.14,
  "auto_update": true
}
```

## 환경 변수

```bash
# .env 파일
KIS_APP_KEY=your_app_key
KIS_APP_SECRET=your_app_secret
KIS_ACCOUNT_NO=12345678-01
TRADING_MODE=VIRTUAL          # VIRTUAL or REAL
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

## 의존성

```
requests>=2.28.0
pandas>=2.0.0
numpy>=1.24.0
schedule>=1.2.0
python-telegram-bot>=20.0
python-dotenv>=1.0.0
pykrx>=1.0.0
openpyxl>=3.1.0
matplotlib>=3.6.0
```

## 데이터 흐름

```
1. 유니버스 구성 (pykrx → KOSPI200)
       ↓
2. 가격/재무 데이터 수집 (KIS API)
       ↓
3. 팩터 점수 계산 (모멘텀 + 저변동성)
       ↓
4. 종합 점수 순위화
       ↓
5. 섹터 분산 적용
       ↓
6. 상위 15개 종목 선정
       ↓
7. 리밸런싱 계산
       ↓
8. 주문 실행 (Dry-run 해제 시)
       ↓
9. 텔레그램 알림
```

## 일일 운영 스케줄 (2024-12 업데이트)

```
┌────────────────────────────────────────────────────────────┐
│                      Trading Day Schedule                   │
├──────────┬─────────────────────────────────────────────────┤
│  08:30   │  🌅 장 전 처리 (_on_pre_market)                  │
│          │  • 평일 여부 확인                                 │
│          │  • 포지션 없음 → 초기 스크리닝 실행                │
│          │  • 리밸런싱 일 → 종목 교체 스크리닝                │
├──────────┼─────────────────────────────────────────────────┤
│  09:00   │  🔔 장 시작 (execute_pending_orders)             │
│          │  • 대기 주문 일괄 실행                            │
│          │  • 포지션 업데이트                                │
├──────────┼─────────────────────────────────────────────────┤
│  09:05~  │  📊 포지션 모니터링 (5분 간격)                    │
│          │  • 손익률 체크 (손절 -7% / 익절 +10%)             │
│          │  • 조건 충족 시 자동 매도                         │
├──────────┼─────────────────────────────────────────────────┤
│  15:20   │  🌙 장 마감 (_on_market_close)                   │
│          │  • 일일 리포트 생성                               │
│          │  • 텔레그램 알림                                  │
└──────────┴─────────────────────────────────────────────────┘
```

### 주말/휴일 처리
- 데몬이 주말에 시작되면 초기 스크리닝 스킵
- 다음 평일 08:30에 자동으로 스크리닝 실행
- 포지션 없음 감지 시 즉시 초기 설정 수행

### 텔레그램 알림 이벤트

| 시점 | 알림 |
|------|------|
| 데몬 시작 | 🚀 퀀트 시스템 시작 |
| 장 전 처리 | 🌅 장 전 처리 시작 |
| 초기 스크리닝 | 📋 포지션 없음 - 초기 스크리닝 실행 |
| 스크리닝 완료 | ✅ 초기 스크리닝 완료 |
| 장 시작 | 🔔 장 시작 - N개 주문 실행 |
| 매수/매도 | 🟢/🔴 종목 매수/매도 알림 |
| 장 마감 | 🌙 장 마감 - 일일 리포트 |
| 데몬 종료 | 🛑 퀀트 시스템 종료 |

## 설정 동기화 (2024-12 추가)

텔레그램 명령으로 변경한 설정이 데몬 재시작 후에도 유지됩니다.

```
Telegram → SystemController → system_config.json → QuantEngine
```

**동작 원리:**
1. 텔레그램 명령 (`/set_target 20`) 수신
2. `SystemController`가 설정 변경 및 `system_config.json` 저장
3. 데몬 재시작 시 `SystemController`에서 설정 로드
4. `QuantEngine`은 `SystemController` 설정 사용

**설정 파일 (`config/system_config.json`):**
```json
{
  "dry_run": true,
  "is_virtual": true,
  "target_count": 15,
  "universe_size": 200,
  "stop_loss_pct": 7.0,
  "take_profit_pct": 10.0,
  "momentum_weight": 0.2,
  "short_mom_weight": 0.1,
  "volatility_weight": 0.5,
  "volume_weight": 0.0
}
```

## 개발 가이드

### 새 텔레그램 명령어 추가
1. `src/telegram/bot.py`에 `cmd_XXX` 메서드 추가
2. `build_application()`에 핸들러 등록
3. `cmd_help()` 도움말 업데이트
4. 필요시 `SystemController`에 기능 추가

### 콜백 연동
```python
controller = get_controller()
controller.register_callback('on_start', my_start_function)
controller.register_callback('on_stop', my_stop_function)
controller.register_callback('on_screening', my_screening_function)
controller.register_callback('on_rebalance', my_rebalance_function)
```

### 설정 저장/로드
```python
# SystemController가 자동 관리
controller.config.dry_run = True
controller.save_config()  # config/system_config.json에 저장
```

## 트러블슈팅

### ModuleNotFoundError
```bash
pip install -r requirements.txt
pip install pykrx python-telegram-bot python-dotenv
```

### 텔레그램 명령어 오류
- 명령어는 **영문 소문자**만 지원 (Telegram API 제한)
- 한글 명령어 사용 불가

### API 인증 오류
1. `.env` 파일 확인
2. `config/token.json` 삭제 후 재시도
3. KIS 개발자센터에서 API 키 상태 확인

### 긴급 정지 해제 안됨
```
/clear_emergency
/start_trading
```
순서대로 실행
