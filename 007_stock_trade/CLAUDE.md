# CLAUDE.md - 퀀트 자동매매 시스템

KIS Open API 기반 멀티팩터 퀀트 자동매매 시스템.

## 핵심 정보

| 항목 | 값 |
|------|-----|
| 전략 | 모멘텀(20%) + 단기모멘텀(10%) + 저변동성(50%) |
| 유니버스 | KOSPI200 |
| 목표 종목 | 15개 |
| 손절/익절 | -7% / +10% |

## 실행

```bash
./run_quant.sh daemon          # 통합 데몬 (권장)
./run_quant.sh screen          # 스크리닝만
./run_quant.sh backtest        # 백테스트
```

## 프로젝트 구조

```
src/
├── quant_engine.py              # 자동매매 엔진 (오케스트레이션)
├── quant_modules/               # 퀀트 엔진 모듈 (2026-01 리팩토링)
│   ├── state_manager.py         # 상태 저장/로드, Lock 관리
│   └── order_executor.py        # 주문 생성/실행/재시도
├── api/
│   ├── kis_client.py            # KIS API 클라이언트
│   └── kis_quant.py             # 퀀트용 API 확장
├── core/system_controller.py    # 원격 제어 (싱글톤)
├── scheduler/auto_manager.py    # 월간 모니터링, 반기 최적화
├── telegram/
│   ├── bot.py                   # 텔레그램 봇 (20+ 명령어)
│   ├── notifier.py              # 알림 전송 전담
│   └── validators.py            # 입력 검증 유틸리티
├── strategy/quant/              # 팩터, 스크리너, 리스크
└── utils/
    ├── converters.py            # 타입 변환, 포맷팅
    ├── retry.py                 # 재시도 데코레이터/설정
    └── market_calendar.py       # 휴장일 판단
scripts/run_daemon.py            # 통합 데몬
config/
├── optimal_weights.json         # 팩터 가중치
└── system_config.json           # 시스템 설정
```

## 텔레그램 명령어

### 제어
| 명령어 | 설명 |
|--------|------|
| `/start_trading` | 시작 |
| `/stop_trading` | 중지 |
| `/emergency_stop` | 긴급정지 |
| `/run_screening` | 스크리닝 실행 |
| `/run_rebalance` | 리밸런싱 실행 |

### 조회/설정
| 명령어 | 설명 |
|--------|------|
| `/status` | 상태 확인 |
| `/positions` | 보유 종목 |
| `/set_target N` | 목표 종목 수 |
| `/set_dryrun on\|off` | Dry-run 모드 |

## 일일 스케줄

| 시간 | 동작 |
|------|------|
| 08:30 | 장 전 스크리닝 (리밸런싱 일) |
| 09:00 | 주문 실행 |
| 5분마다 | 포지션 모니터링 |
| 15:20 | 일일 리포트 |

## 환경 변수 (.env)

```
KIS_APP_KEY=xxx
KIS_APP_SECRET=xxx
KIS_ACCOUNT_NO=12345678-01
TRADING_MODE=VIRTUAL
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
```

## 설정 파일

### config/system_config.json
텔레그램 명령으로 변경한 설정 저장. 데몬 재시작 후에도 유지.

### config/optimal_weights.json
팩터 가중치. 반기 최적화 시 자동 업데이트.

## 트러블슈팅

### API Rate Limit (EGW00201)
- 증상: `초당 거래건수를 초과하였습니다`
- 원인: API 호출이 너무 빠름

**한국투자증권 API 호출 제한:**
| 모드 | API 제한 | 적용 딜레이 | 초당 호출 |
|------|----------|-------------|----------|
| 모의투자 | 5건/초 | 500ms | ~2건 |
| 실전투자 | 20건/초 | 100ms | ~10건 |

**관련 코드:**
- `src/quant_modules/order_executor.py`: `API_DELAY_VIRTUAL`, `API_DELAY_REAL`
- `src/api/kis_quant.py`: `_min_interval` (생성자에서 설정)

**주의:** 슬라이딩 윈도우 방식으로 계산되므로 한계치에 딱 맞추면 초과될 수 있음. 충분한 여유 필요.

### 텔레그램 네트워크 에러 (httpx.ConnectError)
- 원인: 네트워크 연결 문제 (토큰 충돌 아님)
- 해결: 자동 복구됨 - 최대 10회 재시도 + 스레드 자동 재시작 (2026-01)

### 텔레그램 Conflict 에러 (409 Error)
- 증상: `telegram.error.Conflict: terminated by other getUpdates request`
- 원인: 이전 봇 세션이 완전히 종료되지 않은 상태에서 새 세션 시작
- 해결: 자동 복구됨 - Conflict 감지 시 10+5n초 딜레이 후 재시도 (2026-01)

**예방 조치:**
- `run_quant.sh daemon`은 SIGTERM으로 graceful shutdown 후 3초 대기
- `drop_pending_updates=True`로 이전 세션의 pending updates 무시

**관련 코드:** `src/telegram/bot.py`, `run_quant.sh`

### 목표 종목 미달
- 스크리닝 결과 < 목표: 필터 조건 미충족
- 매수 실패: 다음 장 09:00 재시도 (최대 3회)
- 텔레그램으로 미달 알림 발송 (2026-01)

### pykrx 스크리닝 실패 (2026-01-27 발생/해결)

**증상:**
- `유니버스: 0개` 스크리닝 실패
- `KeyError: "None of [Index(['종가', '시가총액', '거래량', '거래대금']..."`
- `IndexError: index -1 is out of bounds for axis 0 with size 0`

**원인:** KRX 웹사이트 API 응답 형식 변경으로 pykrx 1.0.x 호환성 문제

**해결:** pykrx 1.2.3 이상으로 업그레이드
```bash
pip install pykrx>=1.2.3 --break-system-packages  # Homebrew Python
```

**폴백 동작 (pykrx 실패 시):**
1. KIS API로 시가총액 상위 30개 조회
2. pykrx로 KOSPI200 확장 시도
3. pykrx 실패 시 → KIS 30개로 진행

**관련 코드:** `src/strategy/quant/screener.py` - `_build_universe()`

**참고:** pykrx는 KRX 웹 크롤링 기반이라 KRX 사이트 변경 시 영향받음. 유사 문제 발생 시 pykrx 업데이트 먼저 확인.

### 긴급 리밸런싱 무한 반복 (2026-01 수정)
- 증상: 매일 08:30에 "긴급 리밸런싱 트리거" 메시지 반복
- 원인: 긴급 리밸런싱이 월초 중복 방지 로직을 우회
- 해결: `last_urgent_rebalance_month`로 별도 추적, 월 1회 제한

**리밸런싱 동작:**
| 유형 | 추적 변수 | 조건 | 제한 |
|------|----------|------|------|
| 월초 리밸런싱 | `last_rebalance_month` | 매월 첫 거래일 | 월 1회 |
| 긴급 리밸런싱 | `last_urgent_rebalance_month` | 보유 < 목표의 70% | 월 1회 |

**관련 코드:** `src/quant_engine.py` - `_is_rebalance_day()`

### 휴장일 오판단 (2026-01 수정)
- 증상: 평일(거래일)인데 휴장일로 판단하여 봇 미동작
- 원인: pykrx가 자정에 당일 거래 데이터 조회 시 데이터 없음 → 휴장일로 잘못 판단
- 해결: 오늘/미래 날짜는 pykrx 조회 생략, KNOWN_HOLIDAYS 기반 판단

**휴장일 판단 우선순위:**
1. 주말(토/일) → 휴장
2. KNOWN_HOLIDAYS (하드코딩) → 휴장
3. 오늘/미래 날짜 → 평일이면 거래일로 가정
4. 과거 날짜 → pykrx로 실제 거래 데이터 확인

**관련 코드:** `src/utils/market_calendar.py`

**참고:** KIS API 휴장일조회(CTCA0903R)는 실전투자에서만 지원. 모의투자에서는 KNOWN_HOLIDAYS 사용.

### 긴급 정지 해제
```
/clear_emergency
/start_trading
```

## 개발 가이드

### 텔레그램 명령어 추가
1. `src/telegram/bot.py`에 `async def cmd_XXX()` 추가
2. `build_application()`에 핸들러 등록
3. `cmd_help()` 업데이트

### 알림 전송
```python
from src.telegram import get_notifier
notifier = get_notifier()
notifier.notify_buy(code, name, qty, price, reason)
notifier.notify_error("제목", "상세 내용")
```

### 콜백 등록
```python
controller = get_controller()
controller.register_callback('on_screening', engine.run_screening)
```

### 유틸리티 사용
```python
from src.utils import safe_float, safe_int, format_currency
from src.utils.retry import with_retry, API_RETRY_CONFIG

# 안전한 타입 변환
price = safe_float(data.get('price'), 0)

# 재시도 데코레이터
@with_retry(API_RETRY_CONFIG)
def api_call():
    ...
```

## 봇 운영 구조

| 봇 | 실행 방식 | 토큰 |
|----|----------|------|
| 주식봇 (007_stock_trade) | 수동 터미널 | 별도 .env |
| 암호화폐봇 (005_money) | start_all_bots.sh | 별도 .env |

각 봇은 독립 터미널/토큰 사용 → 토큰 충돌 없음.

## 의존성 요구사항

| 패키지 | 최소 버전 | 용도 | 비고 |
|--------|----------|------|------|
| pykrx | **1.2.3** | KOSPI200 유니버스 조회 | 1.0.x는 KRX API 변경으로 실패 |
| python-telegram-bot | 20.0+ | 텔레그램 봇 | async 지원 필수 |
| schedule | 1.0+ | 스케줄러 | - |
| pandas | 1.5+ | 데이터 처리 | - |

**pykrx 버전 주의:** KRX 웹사이트 구조 변경 시 pykrx가 영향받음. 스크리닝 실패 시 pykrx 업데이트 먼저 확인.

---

## 변경 히스토리

### 2026-01-27: pykrx 호환성 문제 및 긴급 리밸런싱 버그 수정

**문제 1: pykrx 스크리닝 실패**
- 현상: 08:30 스크리닝 시 유니버스 0개, `KeyError` 발생
- 원인: KRX 웹사이트 API 응답 형식 변경 → pykrx 1.0.51 호환성 깨짐
- 영향: KOSPI200 조회 실패 → KIS API 폴백(30개)으로 진행
- 해결: pykrx 1.0.51 → 1.2.3 업그레이드
- 결과: 유니버스 30개 → 200개 정상화

**문제 2: 긴급 리밸런싱 무한 반복**
- 현상: 매일 08:30에 "긴급 리밸런싱 트리거" 반복 실행
- 원인: 긴급 리밸런싱이 `last_rebalance_month` 체크를 우회
- 영향: 월초 외에도 매일 리밸런싱 시도 → 스크리닝 실패와 맞물려 매도만 발생
- 해결: `last_urgent_rebalance_month` 별도 추적, 월 1회 제한
- 관련 커밋: `0b10b36`, `627c4fd`, `aeeae65`

**교훈:**
1. pykrx는 KRX 웹 크롤링 기반이라 외부 변경에 취약 → 폴백 로직 필수
2. 긴급 리밸런싱 같은 예외 로직은 별도 추적 변수로 제한 필요
