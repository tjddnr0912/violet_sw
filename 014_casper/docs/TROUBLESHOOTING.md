# Casper 트러블슈팅

각 항목은 6필드(증상/원인/해결/복구절차/관련 사고/재발 감지) + Claude 진단 미스 기록 구조를 따른다. "Claude 진단 미스"는 과거 세션에서 진단 방향이 한 번 빗나갔던 경우만 기록 — 미래의 같은 패턴이 나오면 처음부터 올바른 영역을 보도록 가이드하기 위함.

---

## EGW00103 "유효하지 않은 AppKey" — 사실은 토큰 발급 rate limit lockout

- **증상**: KIS API 호출이 `EGW00103 "유효하지 않은 AppKey"`로 거부. 키를 재발급해도 동일 증상.
- **원인**: 토큰 발급 rate limit(분당 1회) 위반 누적 lockout. 키 자체는 정상.
- **해결**: `kis_auth.py`의 exponential backoff (60s→5m→15m→30m→1h) — 토큰 실패 시 단계적 cooldown, 성공 시 카운트/백오프 리셋.
- **복구 절차**:
  1. 봇 정지 (재시도 루프 차단)
  2. 60~120초 쿨다운 대기
  3. 수동 토큰 발급 → `config/token.json` 저장
  4. 봇 재시작
- **관련 사고**: 2026-04-11 (KIS 서버 일시 장애 → 30s 재시도 루프가 rate limit 누적 → 4/12 403 → 4/13 하루 lockout)
- **재발 감지**: `_BACKOFF_SCHEDULE` 활성 횟수, "New token acquired" 로그 0건 + token.json 만료 시각, 일일 거래 건수 0

### Claude 진단 미스 (이전 세션에서 있었음)
- **Claude 처음 가설**: AppKey/Secret 자체에 문제가 있다고 판단 — KIS Open API 콘솔에서 키 재발급, .env 갱신 시도
- **실제 원인**: 토큰 발급 호출 자체는 정상이지만 봇의 retry 루프가 분당 1회 제한을 초과해 IP/앱 단위로 lockout
- **방향 전환 지점**: 수동 `curl tokenP`가 200 반환 → "키는 정상이니 봇 루프가 문제" 인식 후
- **교훈 (다음에 같은 패턴이 보이면)**:
  - 첫 의심 영역: **봇의 토큰 retry 빈도** (코드 path), 키 자체 X
  - 빨리 배제할 가설: "키가 만료됐다", "재발급 필요"
  - 핵심 진단 명령: `curl -s -X POST https://openapi.koreainvestment.com:9443/oauth2/tokenP -H "Content-Type: application/json" -d '{"grant_type":"client_credentials","appkey":"'$KEY'","appsecret":"'$SEC'"}'` — 200이면 키 정상

---

## KIS 해외주식 잔고/주문가능금액 API 분기 실패

- **증상**: HTTP 500 또는 `rt_cd=7 APBN0746 "상품이 없습니다"`. 같은 함수가 어떤 호출에서는 정상, 어떤 호출에서는 변덕스럽게 실패.
- **원인**: 두 API가 겉보기엔 비슷하지만 **용도와 필수 파라미터가 다름**:

  | 용도 | API | tr_id | 필수 파라미터 |
  |------|-----|-------|------------|
  | USD 예수금·출금가능 | `inquire-present-balance` | `CTRP6504R` | `WCRC_FRCR_DVSN_CD=02`, `NATN_CD=840` (ITEM_CD 불필요) |
  | 특정 종목 주문가능수량 | `inquire-psamount` | `TTTS3007R` | `ITEM_CD` + `OVRS_ORD_UNPR` (둘 다 non-empty) |
  | 보유 포지션·평가손익 | `inquire-balance` | `TTTS3012R` | — (현금 정보 없음) |

  `get_us_balance(symbol="")` → `ITEM_CD=""` → `inquire-psamount` 에러.

- **해결**: `kis_client.py::get_us_balance` 분기 — `symbol` 없으면 present-balance, 있으면 psamount.
- **복구 절차**: 호출부에서 symbol 인자 명시 여부 점검. KIS 500 에러 로깅은 반드시 **엔드포인트 + tr_id + 응답 body(`msg_cd`/`msg1`)**를 함께 기록.
- **관련 사고**: 2026-04-05 (us-exchange-code-normalization 함께 발생)
- **재발 감지**: `KIS HTTP 500` 로그 발생 시 인접 라인에 endpoint/tr_id/msg_cd 셋이 모두 나오는지 확인. 하나라도 없으면 로깅 누락.

### Claude 진단 미스 (이전 세션에서 있었음)
- **Claude 처음 가설**: KIS 서버 일시 장애로 추정 (`HTTP 500`은 보통 서버 문제)
- **실제 원인**: 빈 `ITEM_CD`로 `inquire-psamount` 호출 — 클라이언트 측 파라미터 미스
- **방향 전환 지점**: 다른 시간대에 동일 endpoint로 호출했더니 정상 → "서버 문제 아님" 인식
- **교훈**:
  - 첫 의심 영역: **호출 직전의 실제 request body 덤프** (어떤 tr_id로 어떤 파라미터로 갔는지)
  - 빨리 배제할 가설: "KIS 서버 장애"는 일시적이지만 분기 실패는 결정적
  - 핵심 진단 명령: KIS 500 발생 시 `grep "tr_id\|msg_cd\|msg1"` 같이 봐야 — 셋이 없으면 로깅 부족

---

## KIS cold-start: 새 프로세스 첫 15~60초 HTTP 500

- **증상**: 봇 프로세스 새로 시작 후 첫 15~60초 동안 KIS 대부분의 GET API가 HTTP 500 + `{"rt_cd":"1","msg_cd":"","msg1":""}` 반환. `price`(HHDFS00000300), `inquire-present-balance`(CTRP6504R) 모두 해당. warm 프로세스에서는 동일 토큰·파라미터로 200.
- **원인**: KIS 서버의 세션 priming 지연 (코드 문제 아님).
- **영향**: `self.capital` 초기값 `0.0`. `_sync_capital`이 cold 구간에 걸려 실패하면 그날 `shares = int(self.capital/price) = 0` → 매매 전면 차단. 내장 retry(1→2→4s, 총 7초)는 lockout 구간을 못 뚫음.
- **해결**: `KISClient.warm_up(max_secs=90, poll_interval=10)` — 가벼운 quote 엔드포인트를 `retry=False`로 10초 간격 polling, 200 받으면 즉시 종료. Bot `_init_kis`가 KIS 초기화 직후 호출.
- **복구 절차**: warm-up 실패해도 봇 진행은 계속. 다음 `_sync_capital`(새날/장마감)에서 자동 교정.
- **관련 사고**: 2026-04-13 (내장 retry 3회로 뚫지 못함 → 90s polling 우회책 도입)
- **재발 감지**: 시작 로그에서 `KIS warm-up succeeded in Ns (attempt M)`. M ≥ 3이거나 N ≥ 30s면 KIS 측 priming 지연 심화.

### Claude 진단 미스 (이전 세션에서 있었음)
- **Claude 처음 가설**: 토큰이 만료됐거나 인증 실패. retry 횟수만 늘리면 해결.
- **실제 원인**: KIS 서버 측 세션 priming. retry 7초로는 부족, 90s polling 필요.
- **방향 전환 지점**: 동일 토큰으로 warm 프로세스에서 200 → "토큰 정상" 인식
- **교훈**:
  - 첫 의심 영역: **프로세스 lifetime** (cold vs warm)
  - 빨리 배제할 가설: "토큰 문제", "코드 버그" — 동일 토큰 warm 호출이 200이면 둘 다 X
  - 핵심 진단 명령: warm-up 호출은 반드시 `retry=False`로 — 내부 retry가 polling budget 소모

---

## .env 로드: bash `IFS='=' read` trailing-byte 누락

- **증상**: 모든 KIS 호출이 HTTP 500 + 빈 body (`rt_cd:"1", msg_cd:"", msg1:""`). 파라미터·헤더·토큰 모두 정상으로 보임. 수동 python-dotenv 경로로 호출하면 200.
- **원인**: `run_casper.sh`의 기존 `while IFS='=' read -r key value` 패턴은 **value가 IFS 문자(`=`)로 끝나면 trailing `=`를 제거**. base64 padding으로 끝나는 `KIS_APP_SECRET`이 1 byte 잘림 → 잘못된 secret → KIS가 토큰 검증 실패.
- **해결**:

  ```bash
  while IFS= read -r line || [ -n "$line" ]; do
      key="${line%%=*}"
      value="${line#*=}"
      # ... trim/unquote ...
  done < .env
  ```

  + 이중 방어: `src/utils/config.py::load_env`도 `load_dotenv(env_path, override=True)`. bash가 잘못 export해도 Python이 파일에서 재읽어 덮어쓴다. `.env` 파일이 단일 source of truth.

- **복구 절차**:
  1. `echo "SEC_LEN=${#KIS_APP_SECRET}"` 로 bash export 길이 확인
  2. `wc -c .env` 또는 grep `KIS_APP_SECRET` 행 길이로 원본 비교
  3. 차이 1 byte → IFS 문제

- **관련 사고**: 2026-04-14 (모든 KIS 호출 500 → 일일 진단 시간 대량 소모)
- **재발 감지**: 기동 시 `bash export`된 secret 길이 vs `.env` 파일 원본 길이 비교 로그.

### Claude 진단 미스 (이전 세션에서 있었음)
- **Claude 처음 가설**: KIS 서버 장애 또는 token 만료 (HTTP 500 + 빈 body는 보통 서버 측 신호로 보임)
- **실제 원인**: bash dotenv 파서가 secret 1 byte 잘라먹음 — 헤더·파라미터·토큰 모두 정상으로 보이지만 secret 검증 실패
- **방향 전환 지점**: python-dotenv로 직접 secret 읽어 호출했더니 200 → "환경변수 export 경로의 문제" 인식
- **교훈**:
  - 첫 의심 영역: **bash와 python의 환경변수 값 길이 비교**
  - 빨리 배제할 가설: "KIS 서버 문제"는 빈 body 500이면 오히려 **클라이언트의 인증 실패** 가능성 우선
  - 핵심 진단 명령: `echo "SEC_LEN=${#KIS_APP_SECRET}"` + `grep KIS_APP_SECRET .env | wc -c` — 두 길이가 다르면 즉시 IFS 의심

---

## 포지션 사이징 vs 매수 limit price mismatch

- **증상**: signal 정상 발사되는데 KIS가 `주문가능금액 초과`로 거부 → DONE_TODAY. 자본이 1주 단위로 빡빡한 날 재발.
- **원인**: 사이징은 `int(capital/price)`인데 매수 limit은 `price × (1 + buy_slippage)`. shares × limit > capital 가능. 매도 limit, commission도 미반영.
- **해결**:

  ```python
  buy_slip = self.params["order"]["buy_slippage_pct"]
  comm_rate = self.params["commission"]["rate_per_side"]
  eff_price = price * (1 + buy_slip + comm_rate)
  shares = int(self.capital / eff_price)
  ```

  + `risk.max_position_pct: 1.0 → 0.99` (FX/정산 lag 흡수용 안전 floor 1%).

- **복구 절차**: 코드 패치 후 `scripts/backtest_compare_dual_scan.py`로 영향 측정 — 25거래 중 2거래 1주 감소, 60일 자본 차이 0.04%.
- **관련 사고**: 2026-04-29 (TQQQ signal $61.01, 사이징 51주 × $61.66 limit = $3144 > 자본 $3128.22)
- **재발 감지**: 일일 로그에서 `signal` 발사 + `주문가능금액 초과` 동시 출현 패턴.

### Claude 진단 미스 (해당 없음 — 사용자가 즉시 root cause 지목)

이 사고는 사용자가 백테스트 차이 분석 후 직접 limit price와 사이징 가격 mismatch로 짚어냄. Claude의 헛발질 없음.

### 패턴화 — "우리 view ≠ broker view"

같은 패턴이 다른 곳에도 적용 가능:

| 변환 | 누가 추가 | 사이징이 알아야 하는 이유 |
|------|--------|-------------------|
| 매수 slippage | order layer | 매수가 ≠ 시세, 자본 부족 |
| 매도 slippage | order layer | 익절가가 더 낮아져 실현 R 변화 |
| 거래 수수료 | broker | 자본 계산에서 빠지면 미세 부족 |
| FX 변환 | KIS 환율 | 원화 계좌 USD 매매 시 환율 갭 |

→ 단일 진실 함수 `effective_buy_price(symbol, price)`로 사이징·주문·익절이 같은 값을 쓰는 구조 권장.

---

## 매도 limit 너무 타이트 (sell_slippage_pct=0.01) → SL/TP 미체결

- **증상**: SL/TP 주문이 KIS에 들어갔는데 체결 안 됨. 16:00 KIS day-order 만료 → 다음날 강제청산.
- **원인**: market × 0.99 limit이 급락장에서 bid 아래로 떨어져 미체결. 매수와 달리 매도는 fill 보장이 우선이라 buffer 좁으면 위험.
- **해결**: `sell_slippage_pct: 0.01 → 0.03`. (3%로 확대)
- **복구 절차**: 미체결 만기 주문 발견 시 → `kis_order.cancel_us_order` → 새 limit으로 재제출 또는 market.
- **관련 사고**: 2026-04-30 (multi-lens 감사에서 잠재 이슈로 발견, 패치 적용)
- **재발 감지**: SL/TP 주문 후 N분 내 체결 없음 → alert. 16:00 만료 직전 미체결 알림.

---

## 매수 성공 직후 fill polling 중 크래시 → orphan 포지션

- **증상**: KIS는 51주 보유, 봇 재기동 후 포지션 인지 못함 → SL/TP 모니터링 부재.
- **원인**: `buy_market`은 성공했는데 `get_us_filled_price`가 5회 × 2s polling 도중 SIGKILL/OOM 시 `position_state.json` 미작성.
- **해결**: 주문 성공 즉시 `_save_position_state()` 호출. fill price 갱신은 사후 `_apply_fill_price`가 다시 저장.
- **복구 절차**: 봇 재기동 시 KIS holdings vs `position_state.json` reconcile. 불일치 시 holdings 기준으로 state 재구성.
- **관련 사고**: 2026-04-30 (multi-lens 감사에서 잠재 이슈로 발견, 패치 적용)
- **재발 감지**: 봇 시작 시 KIS holdings != state 파일 → CRITICAL log + Telegram critical 알림.

---

## 부분체결 재매도 시 holdings 폴링 lag → 더블 매도

- **증상**: 첫 매도 후 잔량 재매도 호출했는데 KIS가 같은 quantity 재매도 처리 → 포지션 음수.
- **원인**: 첫 매도 후 `time.sleep(2)` + `get_us_holdings`는 KIS 정산 lag로 pre-fill quantity 그대로 리포트.
- **해결**: `get_us_today_executions(order_no)`로 그 주문의 실제 체결량(`fill_qty`) 합산 후 `remaining = ordered - filled`만 재매도. 체결 0이면 retry skip하고 reconcile에 위임.
- **복구 절차**: 재매도 전 항상 `today_executions`로 confirmed fill 합산.
- **관련 사고**: 2026-04-30 (multi-lens 감사 — 패치 적용)
- **재발 감지**: 단일 거래일에 같은 symbol에 대한 sell 주문이 N+1회 발사되면 alert.

---

## Token backoff 중 stale/empty 토큰 silent 사용

- **증상**: KIS 401 cascade를 매번 다른 endpoint에서 재현. 어디서 인증 실패하는지 추적 어려움.
- **원인**: `auth.token` property가 만료 토큰을 그대로 반환. backoff 활성이어도 호출자가 모름.
- **해결**: backoff 활성 + 유효 토큰 없을 시 빈 문자열 반환 + `logger.critical`로 backoff 잔여시간 명시.
- **복구 절차**: CRITICAL 로그 보고 backoff 만료까지 대기 → 자동 토큰 갱신 → 정상화.
- **관련 사고**: 2026-04-30 (multi-lens 감사)
- **재발 감지**: `auth.token == ""` 호출 발생 시 CRITICAL 로그 + 모든 KIS API call 자동 abort (이미 구현).

---

## 테스트가 production 데이터 파일 오염

- **증상**: 누적 통계·서킷브레이커 기준이 변경되어 실거래 판단에 영향. 봇 재시작 시 history 카운트가 비정상.
- **원인**: 테스트가 `data/trades/trades_YYYY.json`, `data/position_state.json`에 직접 쓰기. `tests/conftest.py`의 격리 fixture가 `autouse=True`가 아니면 Bot lifecycle 테스트의 내부 `save_trade` 경로에서 누수.
- **해결**: 격리 fixture는 **반드시 `autouse=True`**.
- **복구 절차**: 오염된 trades 파일 백업본 복원 + 테스트 격리 fixture 재검증.
- **관련 사고**: 2026-04-08 (position-state-test-isolation), 2026-04-14 (test-fixture-prod-data-leak)
- **재발 감지**: 테스트 실행 전후 `md5 data/trades/trades_2026.json` 비교 → 동일하지 않으면 격리 실패.

### Claude 진단 미스 (이전 세션에서 있었음)
- **Claude 처음 가설**: 테스트 격리 fixture가 이미 존재하므로 다른 원인일 것
- **실제 원인**: fixture는 있었지만 `autouse=True`가 아니어서 일부 경로에서 silent leak
- **방향 전환 지점**: 사용자가 "fixture 어노테이션 다시 봐" 지적
- **교훈**:
  - 첫 의심 영역: **모든 `pytest.fixture`의 `autouse` 여부**
  - 빨리 배제할 가설: "fixture 자체가 없다" — 있어도 적용 범위가 좁으면 똑같이 누수
  - 핵심 진단 명령: 테스트 전후 prod 데이터 파일 md5 비교
