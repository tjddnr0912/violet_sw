# CLAUDE.md - Casper Trading Bot

TQQQ/SQQQ Long-Only 자동매매 봇. ORB + FVG + Pullback 전략, R:R 1:2.

## 실행

```bash
./run_casper.sh start         # 포그라운드 (live 모드 확인 프롬프트)
./run_casper.sh start --yes   # 확인 없이 시작
./run_casper.sh daemon --yes  # 백그라운드 데몬
./run_casper.sh stop          # 종료
./run_casper.sh status        # 누적 매매 통계
./run_casper.sh test          # 유닛 테스트 (270개)
```

## 핵심 정보

| 항목 | 값 |
|------|-----|
| 전략 | ORB(15분) + FVG + Pullback |
| 종목 | TQQQ (강세) / SQQQ (약세), QQQ MA20 기준 |
| R:R | 1:3 고정 (commission 0.25% 환경에서 1:2의 PF 2.64 → 1:3 PF 3.19, 수익률 +34%) |
| 매매시간 | 09:45~10:55 ET (스캔), 15:50 강제청산 |
| 필터 | VIX(12~30), ORB 폭, 서킷브레이커(3연패/주간3%손실), 공휴일 |
| 안전장치 | 크래시 복구, SIGTERM, 포지션 상한, 오버나잇 방지, 잔고 동기화, 부분체결 감지 |
| 알림 | 텔레그램 (env-driven, 큐 기반 critical 지연 재전송, 네트워크 에러 silent drop) |
| 테스트모드 | `TEST_MODE=on` → live지만 1주 고정 |

## 상태머신

```
WAITING → PRE_MARKET → ORB_FORMING → SCANNING → POSITION_OPEN → DONE_TODAY
```

## 주요 모듈

| 파일 | 역할 |
|------|------|
| `src/bot.py` | 상태머신 + 메인 루프 |
| `src/core/orb.py` | ORB 계산 |
| `src/core/fvg.py` | FVG 감지 |
| `src/core/strategy.py` | 시그널 엔진 |
| `src/core/position.py` | 포지션 관리 (SL/TP/BE) |
| `src/core/risk.py` | VIX 필터, 트렌드, 서킷브레이커 |
| `src/api/kis_order.py` | KIS 주문 실행 |
| `src/api/kis_client.py` | KIS 시세 (현재가, 분봉, 일봉, 체결내역) |
| `src/data/market_data.py` | 시세 통합 (KIS 우선 → yfinance 폴백, VIX는 yf 전용) |
| `src/telegram/notifier.py` | 텔레그램 알림 (큐+필터, send-only) |
| `scripts/test_telegram_messages.py` | 텔레그램 알림 스모크 테스트 (14건, `[test i/N]` 태그) |

## 환경변수 (.env)

```bash
KIS_APP_KEY=         # 실전투자 앱키
KIS_APP_SECRET=      # 실전투자 시크릿
KIS_ACCOUNT_NO=      # 계좌번호 (8자리)
TRADING_MODE=live    # paper | live
TEST_MODE=on         # on | off (1주 고정)
TELEGRAM_BOT_TOKEN=  # 008과 동일 키 사용 (한 봇으로 모든 프로젝트 알림 통합)
TELEGRAM_CHAT_ID=    # 008과 동일 chat_id
```

## KIS 토큰/AppKey 디버깅 (함정 주의)

**EGW00103 "유효하지 않은 AppKey"는 대부분 키 문제가 아니다.** 실제 원인은 토큰 발급 rate limit(분당 1회) 위반 누적 lockout. 수동 `curl`로 tokenP 호출 시 200이 나오면 키는 정상.

**진단 순서** (시간 낭비 금지):

1. `config/token.json` 만료 시각 확인 — 만료됐는데 "New token acquired" 로그가 0건이면 갱신 실패 루프
2. 수동 호출 테스트:
   ```bash
   curl -s -X POST https://openapi.koreainvestment.com:9443/oauth2/tokenP \
     -H "Content-Type: application/json" \
     -d '{"grant_type":"client_credentials","appkey":"'$KEY'","appsecret":"'$SEC'"}'
   ```
   200 → 키 정상, 봇 루프 문제 / 403 → IP/키/앱 자체 문제
3. 403인 경우 본문 `error_code` 확인. IP 문제면 네트워크 레벨에서 reject (connection refused). `EGW00103`이면 키 관련.

**복구 절차**: (a) 봇 정지 → (b) 60~120초 쿨다운 대기 → (c) 수동 토큰 발급 → `config/token.json` 저장 → (d) 봇 재시작. 재시도 루프가 남아있으면 재시작해도 또 막힘.

**핵심 설계 원칙**: `kis_auth.py`는 토큰 실패 시 exponential backoff (60s→5m→15m→30m→1h) 필수. 없으면 KIS 일시 장애(Connection refused) 만나면 재시도가 rate limit을 때려서 며칠간 lockout됨. 성공 시 카운트/백오프 리셋.

**사례**: 2026-04-11 KIS 서버 일시 장애 → 30초 재시도 루프가 rate limit 누적 → 4/12 403 전환 → 4/13 하루종일 lockout, 거래 0건. 백오프 패치(`_BACKOFF_SCHEDULE`, `_note_failure`)로 해결.

## KIS 해외주식 잔고/주문가능금액 API 함정

두 API가 겉보기엔 비슷하지만 **용도와 필수 파라미터가 전혀 다름**. 잘못 쓰면 HTTP 500 또는 `rt_cd=7 APBN0746 "상품이 없습니다"` 반환.

| 용도 | API | tr_id | 필수 파라미터 |
|------|-----|-------|------------|
| 순수 USD 예수금·출금가능 | `inquire-present-balance` | `CTRP6504R` | `WCRC_FRCR_DVSN_CD=02`, `NATN_CD=840` (ITEM_CD 불필요) |
| 특정 종목 주문가능수량 | `inquire-psamount` | `TTTS3007R` | `ITEM_CD` + `OVRS_ORD_UNPR` (둘 다 non-empty 필수) |
| 보유 포지션·평가손익 | `inquire-balance` | `TTTS3012R` | — (현금 정보 없음) |

**실수**: `get_us_balance(symbol="")` → `ITEM_CD=""` → `inquire-psamount` 에러. KIS는 이를 HTTP 200/rt_cd=7 또는 HTTP 500으로 변덕스럽게 반환해서 `KIS HTTP 500` 로그만 보고 진단 시간 허비. `kis_client.py`의 `get_us_balance`는 symbol 없으면 present-balance, 있으면 psamount로 분기하는 구조가 필수. KIS 500 에러 로깅은 반드시 **엔드포인트 + tr_id + 응답 body**(`msg_cd`/`msg1`)를 함께 포함할 것 — 세 요소가 없으면 여러 KIS 호출 중 어느 것이 터졌는지 특정 불가.

## KIS cold-start lockout 대응

**증상**: 봇 프로세스 새로 시작 후 **첫 15~60초** 동안 KIS 대부분의 GET API가 HTTP 500 + `{"rt_cd":"1","msg_cd":"","msg1":""}` 반환. `price`(HHDFS00000300), `inquire-present-balance`(CTRP6504R) 모두 해당. 동일 토큰·파라미터로 warm 프로세스에서 호출하면 200. 즉 **코드 문제 아니라 KIS 서버의 세션 priming 지연**.

**영향**: `self.capital` 초기값은 `0.0`. `_sync_capital`이 cold 구간에 걸려 실패하면 그날 `shares = int(self.capital/price) = 0` → **매매 전면 차단**. 내장 retry(1→2→4s)는 총 7초로 lockout 구간을 못 뚫음.

**해결**: `KISClient.warm_up(max_secs=90, poll_interval=10)` — 가벼운 quote 엔드포인트를 `retry=False`로 10초 간격 polling, 200 받으면 즉시 종료. Bot `_init_kis`가 KIS 초기화 직후 호출. warm-up 실패해도 봇 진행은 계속되며 다음 `_sync_capital`(새날/장마감)에서 자동 교정.

**사례**: 2026-04-13 세션 — 내장 retry 3회(17초)로 뚫지 못함. 90s polling 우회책 도입 후 해결. `client.get_us_price()` 자체도 cold에 걸리므로 warm-up 호출은 반드시 `retry=False`로 할 것(내부 retry가 polling budget 소모).

## .env 로드 버그 (bash IFS='=' read 함정)

**진짜 범인**: `run_casper.sh`의 기존 `while IFS='=' read -r key value; do ...` 패턴은 **value가 IFS 문자(`=`)로 끝나면 trailing `=`를 제거**한다. base64 padding으로 끝나는 `KIS_APP_SECRET`이 1 byte 잘림 → 잘못된 secret → KIS가 토큰 검증 실패하여 **HTTP 500 + 빈 body** (`rt_cd:"1", msg_cd:"", msg1:""`) 반환. 파라미터/헤더/토큰이 모두 정상으로 보이므로 진단 시간 대량 소모.

**해결 원칙**: `IFS='='` 대신 `IFS=` + bash parameter expansion 사용:
```bash
while IFS= read -r line || [ -n "$line" ]; do
    key="${line%%=*}"
    value="${line#*=}"
    # ... trim/unquote ...
done < .env
```

**이중 방어**: `src/utils/config.py::load_env`도 `load_dotenv(env_path, override=True)` 사용. bash가 잘못 export해도 Python이 파일에서 재읽어 덮어쓴다. `.env` 파일이 단일 source of truth.

**사례**: 2026-04-14 세션 — 모든 KIS 호출(HHDFS00000300, CTRP6504R 등)이 500 반환. 수동 python-dotenv 경로는 200. 차이의 유일한 원인이 `IFS='=' read`의 trailing-byte 누락이었다. 같은 증상 보이면 제일 먼저 `echo "SEC_LEN=${#KIS_APP_SECRET}"`로 bash export된 secret 길이와 `.env` 파일의 원본 길이 비교할 것.

## 포지션 사이징 vs limit price 함정

`bot.py` 사이징과 `kis_order.py` 매수 limit price가 같은 가격을 써야 한다. 사이징이 `int(capital/price)`인데 주문은 `price * (1 + buy_slippage_pct)`로 나가면 **자본을 buy_slippage만큼(현 설정 1%) 초과**해서 KIS가 `주문가능금액 초과`로 거부한다. signal은 정상 발사돼도 **그날 거래 0**.

**해결**: 사이징도 KIS가 검증하는 all-in cost-per-share 기준으로 (slippage + entry-side commission):
```python
buy_slip = self.params["order"]["buy_slippage_pct"]
comm_rate = self.params["commission"]["rate_per_side"]
eff_price = price * (1 + buy_slip + comm_rate)
shares = int(self.capital / eff_price)
```
+ `risk.max_position_pct: 1.0 → 0.99` (FX/정산 lag 흡수용 안전 floor 1%).

백테스트 영향: 25거래 중 2거래에서 1주 감소, 60일 누적 자본 차이 0.04%. 실거래 거부 제거.

**사례**: 2026-04-29 TQQQ signal $61.01 → 사이징 51주 → 주문 51 × $61.66 = $3144 > 자본 $3128.22 → 거부 → DONE_TODAY. 같은 패턴은 자본이 1주 단위로 빡빡한 모든 날 재발한다.

## 수수료 0.25% + R:R 1:3 (2026-05-01 업데이트)

`commission.rate_per_side`를 **0.0009 → 0.0025** (사용자 실계좌 기준), `entry.rr_ratio`를 **2.0 → 3.0**으로 동시 갱신. 두 변경의 동기는 같은 분석에서 나왔다:

**문제**: 0.25% 왕복 수수료 환경에서 R:R 1:2의 1R win net이 commission 차감 후 거의 사라짐. 60일 백테스트에서 trend 모드 PF 2.64 / 수익률 6.25% — 마지노선.

**수학**: 1R win net = 2R - round-trip commission. 평균 trade에서 1R ≈ $17, comm ≈ $30 → 1:2에서 1 win net = +$4 (commission이 win의 88% 잠식). 1:3에선 1 win net = +$21 (5배 cushion).

**검증** (60일, $500 시작, comm 0.25%/0.25%):
| | trend 1:2 | trend 1:3 | dual 1:2 | dual 1:3 |
|---|---:|---:|---:|---:|
| 거래 수 | 24 | 24 | 44 | 44 |
| 승률 | 45.83% | 25.00% | 38.64% | 20.45% |
| PF | 2.64 | **3.19** | 1.58 | 1.80 |
| 순손익 | $31.26 | **$41.91** | $32.95 | $46.31 |
| MDD | -1.57% | -2.18% | -4.18% | -5.18% |

**1:3 효과**:
- 승률은 절반으로 떨어지지만 (TP가 더 멀어짐), BE 분류가 4건 → 11건으로 흡수 — 작은 손실/0손익으로 끝남
- 1 win이 cover 가능한 loss 수 0.08 → 0.45 (5배)
- PF·MDD 비율은 거의 동일 (-1.57/6.25=0.25 vs -2.18/8.38=0.26)
- **dual은 1:3에서도 marginal** — 추가 거래 PF 1.11. dual은 도입 보류 유지.

**BE move 자동 영향**: `Position.breakeven_price = entry × (1+r)/(1-r)`. r=0.0009 → r=0.0025로 갱신 → BE target이 entry × 1.00501로 상승 (이전 1.00180). 11:00 BE move 후 더 높은 곳에서 stop 발동 — 실 commission을 제대로 cover. r과 실수수료 mismatch 시 BE 거래가 마이너스로 흘렀던 잠재 버그 동시 수정.

**상세 분석**: 본 세션의 4 라운드 백테스트(0.18% / 0.50% / 0.65% × R:R 1:2/1:3) 비교는 `scripts/backtest_compare_dual_scan.py`에서 재현 가능. env var `BT_BUY_RATE` `BT_SELL_RATE` `BT_RR_RATIO`로 토글.

## 추가 KIS 거부·orphan 시나리오 (2026-04-30 다중 관점 감사)

같은 "우리 view ≠ KIS view" 패턴으로 재발 가능한 케이스들. 모두 패치 완료. 코드 수정 시 동일 패턴 도입 금지.

- **매도 limit 너무 타이트(`sell_slippage_pct=0.01`) → SL/TP 미체결**: market × 0.99 limit이 급락장에서 bid 아래로 떨어져 미체결. 16:00 KIS day-order 만료 → 다음날 강제청산. **3%로 확대** (`0.01 → 0.03`). 매수와 달리 매도는 fill 보장이 우선이라 buffer 넓게.
- **매수 성공 직후 fill polling 중 크래시 → orphan 포지션**: `buy_market`은 성공했는데 `get_us_filled_price`가 5회 × 2s polling 도중 SIGKILL/OOM 시 `position_state.json` 미작성. KIS는 51주 보유, 봇은 재기동 후 포지션 인지 못함 → SL 모니터링 부재. **해결**: 주문 성공 즉시 `_save_position_state()` 호출 (fill price 갱신은 사후 처리, `_apply_fill_price`가 다시 저장).
- **부분체결 재매도 시 holdings 폴링 lag → 더블 매도**: 첫 매도 후 `time.sleep(2)` + `get_us_holdings`는 KIS 정산 lag로 pre-fill quantity 그대로 리포트 → 잔량 또 매도. **해결**: `get_us_today_executions(order_no)`로 그 주문의 실제 체결량(`fill_qty`) 합산 후 `remaining = ordered - filled`만 재매도. 체결 0이면 retry skip하고 reconcile에 위임.
- **Token backoff 중 stale/empty 토큰 silent 사용**: `auth.token` property가 만료 토큰을 그대로 반환 → KIS 401 cascade를 매번 다른 endpoint에서 재현 → 진단 시간 허비. **해결**: backoff 활성 + 유효 토큰 없을 시 빈 문자열 반환 + `logger.critical`로 backoff 잔여시간 명시.

## 텔레그램 알림 (env-driven, send-only)

봇 lifecycle의 핵심 지점에서 텔레그램으로 알림 송출. 수신/명령 처리 없음.

**송출 시점**: bot started/stopped, pre-market 결과, ORB 형성, signal 발사, **entry (critical)**, BE move, **exit (critical)**, **order failed (critical)**, daily summary (DONE_TODAY 시 오늘 거래 + 누적).

**핵심 규칙**:
- **네트워크 오류는 텔레그램으로 안 보냄**: `notify_error`가 timeout/connection/SSL 등 네트워크-class 메시지 자동 필터(`_is_network_error_text`).
- **거래 중 실패한 critical 메시지는 큐에 쌓고 거래 종료 후 순차 flush**: `begin_trade()`/`end_trade()`로 lifecycle 토글. entry/exit/order_failed 메시지가 텔레그램 네트워크 오류로 실패하면 즉시 retry 안 하고 `_close_and_record` 끝에서 0.5s 간격으로 flush.
- **dedup**: pre-market/ORB/signal은 하루 1회만 알림 (`_notified_*` 플래그, `_reset_day`에서 리셋).

**검증**: `python scripts/test_telegram_messages.py` — 14단계 스모크 테스트. 각 메시지에 `[test i/14]` 태그 → 텔레그램 클라이언트에서 도착 확인 가능. 13/14, 14/14는 의도적 silent drop (필터·큐 unit-style 검증)이라 도착하면 안 됨.

**환경변수**: 008과 동일한 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` 사용 — 한 텔레그램 봇으로 005/006/007/008/014 모든 프로젝트 알림이 같은 채팅으로 들어옴.

## 테스트 격리 원칙

테스트가 production 데이터 파일(`data/trades/trades_YYYY.json`, `data/position_state.json`)에 쓰면 **누적 통계·서킷브레이커 기준이 오염**되어 실거래 판단에 영향. `tests/conftest.py`의 격리 fixture는 **반드시 `autouse=True`**여야 함. opt-in fixture는 Bot lifecycle 테스트가 내부적으로 `save_trade`를 호출하는 경로에서 조용히 누수됨. 검증 루프: 테스트 실행 전후 `md5 data/trades/trades_2026.json` 비교 → 동일하지 않으면 격리 실패.

## 상세 문서

- [코드 리뷰](docs/CODE_REVIEW.md)
- [설계 스펙](docs/superpowers/specs/2026-04-02-casper-bot-design.md)
- [전략 리뷰](docs/strategy/STRATEGY_REVIEW.md)
- [실행 계획](docs/strategy/EXECUTION_PLAN.md)
- [코드 감사](docs/CODE_AUDIT_2026-04-11.md)
