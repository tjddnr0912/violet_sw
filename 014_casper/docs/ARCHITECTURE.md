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
| `PRE_MARKET` | ET 09:30 직전 | VIX 필터, 트렌드 점검 (dual scan 모드에서는 정보용 — 알림에 "Trend (info only)" 라벨 + 진입 결정에 무관, fallback 시 결정자), 공휴일 체크 |
| `ORB_FORMING` | ET 09:30~09:45 | 15분 ORB 계산 (dual scan: TQQQ+SQQQ 양쪽, single: trend leg만) |
| `SCANNING` | ET 09:45~10:55 | FVG 감지(strict: 몸통 가로지르기 + FVG-ORB intersect), Pullback 진입 시그널. dual scan: 첫 풀백 측 진입 |
| `POSITION_OPEN` | 시그널 + 진입 성공 | SL/TP 모니터링, BE move (11:00) |
| `DONE_TODAY` | 청산 또는 15:50 | 일일 요약, 다음날 대기 |

### Scan 모드 — `mode.dual_scan`

| 값 | 동작 |
|---|------|
| `true` (default) | TQQQ + SQQQ 양쪽 ORB 동시 계산. 양쪽 leg를 9:45~10:55 동안 스캔. 첫 풀백 발생한 leg가 그날의 단일 거래를 차지. trend(QQQ MA20)는 정보용으로만 보존 |
| `false` | 기존 trend mode — QQQ MA20 기준으로 BULL→TQQQ 또는 BEAR→SQQQ 한 심볼만 스캔 |

dual scan 채택 근거: 60일 백테스트에서 단일 trend(±$5.41)보다 거래 기회 확대 + 승률·PF 동시 개선(+$18.94, PF 2.01, MDD -2.83%, 2026-05-06 결과). SQQQ에서 잡힌 Long FVG는 의미적으로 QQQ에서의 Bearish FVG(하락 displacement)에 대응 — 인버스 ETF 매핑이 자연스럽게 양방향 매매를 제공.

### FVG strict 조건 — `entry.strict_fvg`

원본 전략(Casper SMC / FMZ Quant 정의)의 핵심: "bullish FVG가 upper ORB boundary와 **intersect** 해야 함". `strict=true`(default)에서 두 조건 동시 검증:

```
(S1) displacement 캔들의 몸통이 ORB 라인을 가로지름:
     candle.Open  <= orb_high <= candle.Close

(S2) 검출된 FVG zone이 ORB 라인을 포함:
     fvg.bottom   <= orb_high <= fvg.top
```

`strict=false`로 두면 기존 baseline(`Close > orb_high`만 검증) 동작. 백테스트에서 가짜 시그널 ~70% 제거.

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
| `src/data/store.py` | Parquet 영구 저장 (5m / 1m / daily, Snappy 압축, 심볼별 격리) |
| `src/data/collector.py` | 백그라운드 스레드 Parquet writer (queue 기반, `interval="5m"|"1m"`) |
| `src/data/ict_log.py` | JSONL 결정 로그 (`data/ict_decisions/<YYYY-MM-DD>.jsonl`, append-only) |
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
      Strategy (ORB+FVG+Pullback + 10 ICT 필터)
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

## 영구 저장소 레이아웃 (DATA_COLLECTION=on)

```
data/
├── marketdata/
│   ├── <SYM>/                  # TQQQ, SQQQ, QQQ, NQ=F (→ NQ_F), _VIX
│   │   ├── <year>/             # 5분봉 RTH: YYYY/<date>.parquet  (Snappy)
│   │   ├── 1m/<year>/          # 1분봉: 별도 partition (2026-05-12 P1)
│   │   ├── 5m_premkt/<year>/   # 5분봉 06:00~09:29: (2026-05-13 Day 1)
│   │   └── daily/              # 일봉: yearly merge parquet
├── ict_decisions/              # 매 필터 결정 JSONL (오디트, append-only)
│   └── <YYYY-MM-DD>.jsonl
├── trades/trades_<YYYY>.json   # 영구 매매 기록
└── position_state.json         # 크래시 복구용 진행 중 포지션
```

- `BarCollector`는 백그라운드 스레드. `submit(interval="5m"|"1m"|"5m_premkt")`로 비동기 큐잉.
- 3종 partition은 완전 분리 → 같은 symbol/date에 5m·1m·premkt 동시 저장 충돌 없음.
- `data/marketdata/`는 5m·1m·5m_premkt·daily 모두 atomic write (`.tmp → rename`).

## NQ→QQQ session pool ratio remap (2026-05-13 Day 2)

NQ futures(30,000pt scale)에서 가져온 session high/low를 QQQ 차트(700pt scale) sweep candidate에 그대로 prepend하면 `is_sweep_bar`의 close-back-inside 조건에서 자동 reject. `_handle_pre_market`에서 ratio 변환 후 저장:

```python
ratio = qqq_close / nq_last      # ≈ 0.024 (지수/현물 비율)
pools_qqq = {key: (hi * ratio, lo * ratio) for key, (hi, lo) in nq_pools.items()}
self._session_pools = pools_qqq
```

결정 로그(`session_pools_computed`)에 ratio·nq_last·qqq_close 포함.

## Sweep 후보 풀 우선순위 (2026-05-12 M3/M4)

`require_sweep_choch=true` 상태에서 `levels_up` / `levels_down` 구성 순서 (앞쪽일수록 sweep 검출 우선):

```
levels_down  =  [session_pools.lows...]   ← M4 (Asia/London/Premkt low from NQ futures)
            +   [EQL pool means...]       ← M3 (clustered swing lows < 0.05%)
            +   [orb.low]                 ← 기본 ORB low
            +   [recent swing lows ×5]    ← Phase 2 base
```

- 같은 식으로 `levels_up`에 session highs / EQH means / orb.high / recent swing highs.
- `is_sweep_bar`는 levels 리스트를 순회하며 첫 매치를 사용 → 강한 풀(NQ 세션 + EQH/EQL)이 자연스럽게 우선.
- 결정 로그에 `eqh_eql_pools`, `session_pools_computed`, `session_pools` 이벤트 적재.

## 1m yfinance backfill (2026-05-12 M2)

`_cold_start_backfill`은 두 단계 backfill 수행:

| 데이터 | 윈도우 | 소스 | 조건 |
|---|---|---|---|
| 5m bars | 60일 | yfinance 5m | `DATA_COLLECTION=on`일 때만 |
| 1m bars (NEW) | 8일 | yfinance 1m | 항상 (`DATA_COLLECTION` 무관) |
| daily bars | 100~120일 | KIS/yfinance | 항상 |
| NQ=F 5m | 5~60일 | yfinance | use_power_of_3 또는 use_session_pools 일 때 |

1m partition (`data/marketdata/<sym>/1m/<year>/<date>.parquet`)은 5m partition과 완전 격리 — 한쪽이 비어도 다른 쪽 동작 영향 없음.

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
