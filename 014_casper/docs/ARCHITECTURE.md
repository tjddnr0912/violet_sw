# Casper 아키텍처

## 상태머신

```
WAITING → PRE_MARKET → ORB_FORMING → SCANNING → POSITION_OPEN → DONE_TODAY
                                                       ↓
                                              (15:50 강제청산)
                                                       ↓
                                                  DONE_TODAY
```

| 상태 | 진입 조건 | 핵심 동작 |
|------|---------|---------|
| `WAITING` | 봇 기동 | KIS warm-up, 자본 동기화, 트레이드 히스토리 로드 |
| `PRE_MARKET` | ET 09:30 직전 | VIX 필터, 트렌드 점검, 공휴일 체크 |
| `ORB_FORMING` | ET 09:30~09:45 | 15분 ORB 고가/저가 계산 |
| `SCANNING` | ET 09:45~10:55 | FVG 감지, Pullback 진입 시그널 |
| `POSITION_OPEN` | 시그널 + 진입 성공 | SL/TP 모니터링, BE move (11:00) |
| `DONE_TODAY` | 청산 또는 15:50 | 일일 요약, 다음날 대기 |

## 주요 모듈

| 파일 | 역할 |
|------|------|
| `src/bot.py` | 상태머신 + 메인 루프, lifecycle 관리 |
| `src/core/orb.py` | ORB(15분) 고가·저가 계산 |
| `src/core/fvg.py` | Fair Value Gap 감지 |
| `src/core/strategy.py` | 시그널 엔진 (ORB + FVG + Pullback 통합) |
| `src/core/position.py` | 포지션 관리 (entry, SL, TP, BE move) |
| `src/core/risk.py` | VIX 필터, 트렌드, 서킷브레이커 |
| `src/api/kis_order.py` | KIS 주문 실행 (매수/매도, 부분체결, fill polling) |
| `src/api/kis_client.py` | KIS 시세·잔고·체결내역 |
| `src/api/kis_auth.py` | OAuth 토큰 발급, exponential backoff |
| `src/data/market_data.py` | 시세 통합 (KIS 우선 → yfinance 폴백, VIX는 yf 전용) |
| `src/data/trade_store.py` | 일일·누적 거래 기록 (JSON) |
| `src/telegram/notifier.py` | 텔레그램 알림 (큐 + 필터, send-only) |
| `src/utils/config.py` | .env 로드, 파라미터 dict 관리 |
| `src/utils/time_utils.py` | ET 시간대 처리, 공휴일 |
| `scripts/test_telegram_messages.py` | 텔레그램 알림 스모크 테스트 (14건) |
| `scripts/backtest_compare_dual_scan.py` | 백테스트 비교 (commission/RR 토글) |

## 데이터 흐름

```
[KIS API]                       [yfinance]
   ↓                                ↓
KISClient(시세,잔고,체결)      market_data fallback
   ↓                                ↓
       MarketData (통합 인터페이스)
              ↓
      Strategy (ORB+FVG+Pullback)
              ↓
       Risk Filter (VIX/트렌드/CB)
              ↓
        Position (SL/TP/BE)
              ↓
      KISOrder (매수/매도)
              ↓
        TradeStore (JSON)
              ↓
      Telegram Notifier (큐+필터)
```

## 텔레그램 알림 컴포넌트

봇 lifecycle의 핵심 지점에서 텔레그램으로 알림 송출. 수신/명령 처리 없음 (send-only).

### 송출 시점

- bot started / stopped
- pre-market 결과 (트렌드/VIX 통과 여부)
- ORB 형성 (고가·저가 확정)
- signal 발사
- **entry (critical)**
- BE move (11:00 SL을 entry로 끌어올리기)
- **exit (critical)** (SL/TP/만기)
- **order failed (critical)** (KIS 거부, 부분체결 실패 등)
- daily summary (DONE_TODAY 시 오늘 거래 + 누적 통계)

### 핵심 규칙

- **네트워크 오류는 텔레그램으로 안 보냄**: `notify_error`가 timeout/connection/SSL 등 네트워크-class 메시지를 자동 필터(`_is_network_error_text`).
- **거래 중 실패한 critical 메시지는 큐에 쌓고 거래 종료 후 순차 flush**: `begin_trade()`/`end_trade()`로 lifecycle 토글. entry/exit/order_failed 메시지가 텔레그램 네트워크 오류로 실패하면 즉시 retry 안 하고 `_close_and_record` 끝에서 0.5s 간격으로 flush.
- **dedup**: pre-market/ORB/signal은 하루 1회만 알림 (`_notified_*` 플래그, `_reset_day`에서 리셋).

### 검증

```bash
python scripts/test_telegram_messages.py
```

14단계 스모크 테스트. 각 메시지에 `[test i/14]` 태그 → 텔레그램 클라이언트에서 도착 확인. 13/14, 14/14는 의도적 silent drop (필터·큐 unit-style 검증)이라 도착하면 안 됨.

### 토큰 공유

008(미국주식 퀀트)과 동일한 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` 사용 — 한 텔레그램 봇으로 005/006/007/008/014 모든 프로젝트 알림이 같은 채팅으로 들어옴.

## 안전장치

| 장치 | 트리거 | 동작 |
|------|------|------|
| 크래시 복구 | 봇 재기동 | `position_state.json` 읽어 KIS holdings와 reconcile |
| SIGTERM | OS 종료 신호 | 진행 중 거래 finalize, state 저장, exit |
| 포지션 상한 | `max_position_pct` | 기본 0.99 (FX/정산 lag 흡수) |
| 오버나잇 방지 | 15:50 ET | 강제청산 |
| 잔고 동기화 | 새날, 장마감 | KIS 잔고 → `self.capital` 갱신 |
| 부분체결 감지 | 매도 후 `today_executions` | 미체결분만 재매도 |
| 서킷브레이커 | 3연패 / 주간 -3% | 신규 진입 차단 |
| 공휴일 | NYSE 캘린더 | 그날 PRE_MARKET 스킵 |

## 관련 문서

- 상세 디버깅 가이드 → [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- 환경변수·튜닝 → [CONFIGURATION.md](CONFIGURATION.md)
- 명령 카탈로그 → [COMMANDS.md](COMMANDS.md)
- 변경 이력 → [CHANGELOG.md](CHANGELOG.md)
- 코드 리뷰 → [CODE_REVIEW.md](CODE_REVIEW.md)
- 코드 감사 → [CODE_AUDIT_2026-04-11.md](CODE_AUDIT_2026-04-11.md)
- 전략 리뷰 → [strategy/STRATEGY_REVIEW.md](strategy/STRATEGY_REVIEW.md)
- 실행 계획 → [strategy/EXECUTION_PLAN.md](strategy/EXECUTION_PLAN.md)
- Freqtrade 갭 리뷰 → [strategy/FREQTRADE_GAP_REVIEW.md](strategy/FREQTRADE_GAP_REVIEW.md)
