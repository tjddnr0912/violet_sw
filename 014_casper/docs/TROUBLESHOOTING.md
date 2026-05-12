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

---

## 전략 문서의 핵심 조건이 구현에서 누락 (ORB-FVG intersect)

- **증상**: 백테스트는 잘 돌아가고 시그널은 잡히지만, 60일 trend baseline에서 PF 0.61, 승률 16.7%로 적자(-$16.28). 봇은 정상 작동하는데 결과가 전략 의도와 동떨어짐.
- **원인**: 전략 명세서(`docs/strategy/STRATEGY_REVIEW.md`)에는 "기준선 없이 형성된 FVG는 무의미", "FVG 위치: ORB 레벨과 밀접하게 겹침"이 명확히 적혀 있는데, 실제 구현(`src/core/fvg.py::check_breakout_with_fvg`)은 `Close > orb_high` 조건만 검증. 즉 (S1) displacement 캔들 몸통이 ORB 가로지르기, (S2) FVG zone이 ORB 라인 포함 — 두 조건 모두 코드에 누락. 이미 ORB 위에서 횡보 중에 큰 양봉만 나와도 시그널 발생.
- **해결**: `check_breakout_with_fvg(..., strict=False)` 파라미터 추가. strict=True일 때 (S1)+(S2) 검증. config에서 `entry.strict_fvg=true`로 default ON.
- **복구 절차**:
  1. fvg.py에 strict 파라미터 추가
  2. strategy.py에서 strict 패스스루
  3. config에 `entry.strict_fvg=true` 추가
  4. 백테스트로 가짜 시그널 제거율 측정 (~70%) + 수익 전환 확인
  5. 봇 재기동
- **관련 사고**: 2026-05-06 (사용자가 캐스퍼 유튜브 원본 영상의 의도와 실제 코드 동작 사이 괴리를 지적)
- **재발 감지**: `docs/strategy/*.md`의 핵심 트리거 조건과 `src/core/*.py` 검증 로직을 줄 단위로 매핑하는 회귀 테스트. 또는 백테스트 PF가 0.5~1.5 사이에서 헤매면 "조건 누락" 의심.

### Claude 진단 미스 (이번 사고)
- **Claude 처음 가정 (이전 세션, 코드 작성 시점)**: STRATEGY_REVIEW.md의 "기준선 돌파 + FVG 동시 형성"을 `Close > orb_high && bullish candle && FVG exists`로만 해석. "ORB 라인을 가로지른다"는 기하학적 조건을 코드로 옮기지 않음. FVG 검출 윈도우만 잘 잡으면 자연스럽게 만족할 것이라고 암묵적 가정 — 실제로는 자주 어긋남.
- **실제 원인**: 영상의 의도는 displacement 캔들이 ORB 라인 자체를 몸통으로 가로지르고, 그 결과 형성되는 FVG zone이 ORB 라인을 포함하는 기하학적 패턴. STRATEGY_REVIEW.md L19/L33/L174/L284에 사실상 동일 표현이 4번 등장 — 단순 문구가 아니라 명세였음.
- **방향 전환 지점**: 사용자 메시지 "캐스퍼의 유투브를 잘 살펴보면 orb 기준선을 돌파하는 fvg를 의미 있는 것을 보는 것 같아. orb를 돌파한 이후에 발생하는 fvg가 아닌것 같아. 원본 영상을 다시 검토해봐" — 사용자가 영상과 코드 사이 괴리를 지적. 이후 FMZ Quant 공식 정의(`open[1] <= orb_high AND close[1] >= orb_high`)로 외부 검증.
- **교훈 (다음에 같은 패턴이 보이면)**:
  - 첫 의심 영역: **전략 명세 문서의 핵심 조건들이 실제로 코드의 검증 분기에 1:1 매핑돼 있는가**. 명세 문구를 grep으로 추적해서 코드의 if/assert로 환원되는지 확인
  - 빨리 배제할 가설: "구현이 명세보다 보수적이다" — 백테스트가 적자면 보통 반대(누락이 많아 가짜 시그널이 통과). PF<1.0이면 명세 누락 의심
  - 명세-구현 일관성 룰: `docs/strategy/*.md`의 "필수 조건" / "핵심 트리거" / "무효" 키워드 인근 문장은 모두 코드의 early-return 또는 assertion에 대응돼야 한다
  - 외부 검증 자원: 한국어 인플루언서 전략은 보통 영어 원본 출처(ICT, Casper SMC, FMZ Quant 등)가 있고, 그쪽이 더 명시적. 명세가 모호하면 영어 1차 출처(논문/공식 전략)를 검색해 정의를 못박는다
  - 핵심 진단 명령: 백테스트로 baseline vs strict 동시 비교 — 시그널 수가 70% 줄면서 PF가 2배 이상 뛰면 누락된 조건이 있었던 것

---

## ICT phase 라벨에 `*` 잘못 표기 (Bias 통합 완료인데 미통합처럼 표시)

- **증상**: `./run_casper.sh start` stdout에 `ICT : KZ Disp Sweep Bear* Bias*  (* = config 로딩만, bot 통합 보류)` 표시. 사용자가 "ICT 통합 전이라고 나오는데?"라고 지적.
- **원인**: 라벨 코드(`run_casper.sh`의 ICT label 블록)가 Phase 3 작업 시작 시점의 상태(bias/bear 모두 모듈만 있고 bot 미통합)를 그대로 두고 있었음. Phase 3 `daily_bias` hook을 `bot.py:_handle_pre_market`에 추가한 뒤에도 라벨 코드는 업데이트 안 함.
- **해결**: 라벨을 두 부류로 분리 — Bias는 통합 완료(`Bias`, 별표 없음), Bear는 QQQ-mapping plan 미구현(`Bear*` 별표). 추후 Bear까지 통합한 뒤엔 `QQQ→SQQQ` 라벨로 변경.
- **복구 절차**:
  1. `run_casper.sh` start_bot의 ICT 라벨 블록 수정 (Bias `*` 제거)
  2. `run_bot.py --status`의 `_ict_status_line()` 동기화
  3. 텔레그램 `notify_bot_started`의 ICT flags 동기화
  4. 봇 재기동해 stdout/log/telegram 3채널 모두 일치 확인
- **관련 사고**: 2026-05-12 (Phase 3 통합 후 라벨 미동기)
- **재발 감지**: 새 ICT 옵션 도입 시 *동시에* 4채널(bash stdout / app log banner / `run_bot.py --status` / telegram `notify_bot_started`) 라벨 grep으로 일관성 확인. 누락 시 사용자 인지 즉시.

### Claude 진단 미스 (이번 사고)
- **Claude 처음 가정**: ICT 라벨에서 별표 의미를 "config 로딩만, bot 통합 보류"로 통일 처리. Phase 3 작업 단계별로 *어떤 옵션이 실제로 bot에 hook됐는지*를 라벨에 따로 반영해야 한다는 인식이 없었음.
- **실제 원인**: Phase 3 안에서도 `daily_bias`는 bot 통합 완료, `bear_fvg`는 미통합 — 라벨이 두 상태를 *섞어서* 표시하면 사용자에게 잘못된 정보. 라벨이 **"현재 실제 효과를 주는 옵션이 무엇인가"** 를 정확히 반영해야 한다는 핵심 원칙 누락.
- **방향 전환 지점**: 사용자 메시지 "지금 캐스퍼봇 재시행하니까 터미널 출력에 ict 통합전이라고 나오는데?" — Claude가 즉시 라벨 코드 위치 파악 후 `Bias*` → `Bias` 분리. 같은 세션에서 사용자 명령 "통합 진행해"로 Bear도 통합 후 라벨을 `QQQ→SQQQ`로 변경.
- **교훈 (다음에 같은 패턴이 보이면)**:
  - 첫 의심 영역: **UI 라벨의 의미(`*`, 색상, 약어)는 실제 bot 동작과 1:1 매핑이어야 한다**. 라벨 변경은 코드 hook 변경과 *동시* 작업
  - 라벨 동기화 4채널 점검: bash stdout / app log banner / status CLI / telegram bot_started — grep으로 한 번에 일관성 확인
  - 빨리 배제할 가설: "사용자가 이전 버전 캐시를 보고 있다" — 사용자는 재시작 직후 신뢰 가능. 라벨 코드 자체 점검 우선
  - 핵심 진단 명령: `grep -n "ICT\|Bias\|Bear\|Sweep" run_casper.sh run_bot.py src/telegram/notifier.py src/bot.py`

---

## ICT 매매 윈도우 ET만 표기 (한국 운용자 혼란)

- **증상**: `[NOTE] 위는 필터 상태일 뿐. 실제 매매는 09:30~10:55 ET 시점에 결정.` — ET 시간만 출력. 사용자가 "KZ의 의미 설명에 섬머타임을 감안해서 메세지가 나와야 할것 같아. 현재는 한국시간으로 22:30분부터 시작이야"로 지적.
- **원인**: NOTE 라벨에 KST 변환 누락. 한국 운용자가 매번 머릿속에서 ET+13(서머타임)/+14(표준시) 계산해야 함. 운용 윈도우 시작 시각을 잘못 인지하면 KST 미국장 직전인데 봇이 멈춰있다고 오해.
- **해결**: pytz로 ET→KST 변환 + DST 자동 인식. 출력 형식 `매매 윈도우: ET 09:30~10:55  (KST 22:30~23:55, 서머타임)`. 4채널 모두 적용.
- **복구 절차**:
  1. `pytz` 의존성 확인 (이미 `requirements.txt`에 있음)
  2. `bot.py:run()` startup banner에 ET→KST 변환 라인 추가
  3. `run_casper.sh` start_bot / start_daemon 모두에 같은 라인
  4. `run_bot.py --status`에 추가
  5. `src/telegram/notifier.py:notify_bot_started`에 추가
  6. 봇 재기동
- **관련 사고**: 2026-05-12 (ICT 통합 후 KST 미표기 지적)
- **재발 감지**: 새 시간 윈도우 옵션 추가 시 항상 KST 변환 함께. `grep -n "09:30\|10:55\|ET" run_casper.sh run_bot.py src/bot.py src/telegram/notifier.py` 으로 ET-only 라인 식별.

### Claude 진단 미스 (이번 사고)
- **Claude 처음 가정**: ICT 영상이 ET 기준이라 봇 메시지도 ET로 충분할 것이라 추정. 운용자 입장(한국)에 대한 시간대 변환을 *암묵적 지식*으로 처리.
- **실제 원인**: 한국 운용자는 KST 기준으로 일과 관리. ICT 영상은 미국 트레이더 대상이라 ET 기본이지만, **운용 환경이 한국**이면 KST가 1차 시간대. 봇 메시지를 사용자가 *즉시 행동*으로 옮기려면 운용자 시간대 기준이어야 함.
- **방향 전환 지점**: 사용자 메시지 "현재는 한국시간으로 22:30분부터 시작이야" — Claude가 즉시 pytz DST 변환으로 동적 KST 라인 추가. 봇 재시작으로 확인.
- **교훈 (다음에 같은 패턴이 보이면)**:
  - 첫 의심 영역: **사용자 운용 시간대에 맞춰 표시되는가**. ET / UTC / KST 등 표시 시간대는 *문서 출처*가 아니라 *운용자 위치* 기준
  - 빨리 배제할 가설: "사용자가 시간대 변환을 직접 할 것이다" — 매번 변환은 인지 부하. 봇이 변환해서 보여줘야 함
  - DST 처리: 정적 offset(+13/+14) 하드코딩 금지. pytz/zoneinfo로 동적 변환 (서머타임 전환 자동)
  - 핵심 진단 명령: `grep -n "ET\|UTC\|GMT" src/ run_*.sh` 으로 시간대만 표기된 라인 검출

---

## ICT 신규 모듈 cold-start backfill이 DATA_COLLECTION 토글에 silent-skip

- **증상**: 봇 재시작 후 `data/marketdata/NQ=F/` 디렉토리가 생성되지 않음. 일봉 store 워밍업과 1분봉 warm-up도 누락. 사용자 "적용 확인" 요청에서 발견.
- **원인**: `_cold_start_backfill()` 함수 시작부의 `if self.collector is None: return` 가드가 *5m 백필*만이 아니라 *daily/NQ/1m warm-up까지 통째로* 차단. DataCollector(5m 실시간 스트리밍)는 별도 토글 `DATA_COLLECTION=on`이 필요하지만, 일봉/NQ/1m은 ICT 모듈이 *항상* 필요로 함.
- **해결**: `_cold_start_backfill()`을 2-tier 구조로 분리. 5m 백필은 `if self.collector is not None:` 안에 두고, 일봉/NQ=F/1m warm-up은 `DATA_COLLECTION_BACKFILL=on`만으로 *항상* 실행되게 함.
- **복구 절차**:
  1. `bot.py:_cold_start_backfill` 의 가드 분리
  2. 봇 재시작
  3. `logs/app/casper_*.log` 에서 `Backfill: NQ=F N 5m bars persisted` 확인
  4. `ls data/marketdata/NQ=F/` 로 디스크 확인
- **관련 사고**: 2026-05-12 (ICT Phase 4 통합 직후)
- **재발 감지**: 새 ICT 의존 데이터 소스를 추가할 때 즉시 *어떤 토글 분기 아래*에 들어가는지 점검. `grep -n "if self.collector is None" src/bot.py` 로 silent-skip 영역 한눈에 확인.

### Claude 진단 미스 (이번 사고)
- **Claude 처음 가설**: NQ=F 백필 코드를 `_cold_start_backfill` 안에 추가한 뒤, 함수 시작부의 collector 가드가 그것까지 stop시킨다는 인식을 못 함. "코드 추가 완료" 시점에 "통합 완료" 보고했지만 실제로는 DATA_COLLECTION=off 환경에서 *전혀 실행되지 않는 코드*였음.
- **실제 원인**: 가드의 의미(5m 스트리밍 의존성)와 새 코드 라인의 의미(일봉/NQ/1m은 의존성 X)가 **다름**. 한 함수 내에서 두 종류의 backfill이 같은 가드를 공유하면 안 됨.
- **방향 전환 지점**: 사용자 메시지 "적용 확인하고 텔레그램 메시지도 점검해" → Claude가 `ls data/marketdata/`로 NQ=F 부재 확인 후 가드 분리 수정.
- **교훈 (다음에 같은 패턴이 보이면)**:
  - 첫 의심 영역: **함수 시작부의 early-return / 가드가 새로 추가된 코드 라인까지 의도 외로 stop시키지 않는가**. 가드는 *원래 의도된 영역*과 *그것에 의존하지 않는 새 코드*를 명확히 구분.
  - 빨리 배제할 가설: "코드를 추가하면 자동으로 실행될 것" — 함수 흐름(가드/예외/조건분기) 안에서 *반드시 도달하는 라인인지* 확인 필수.
  - 점검 패턴: 새 기능 추가 후 사용자에게 "적용 확인" 요청을 받기 *전에*, 직접 disk/log/process를 점검해 `data/`나 `logs/`에 흔적이 남았는지 확인. 보고 전에 *실제 실행 흔적*을 검증.
  - 핵심 진단 명령: `ls -la data/marketdata/<new_dir>/` + `grep "<new_log_line>" logs/app/*.log`

---

## venv 환경에 새 dependencies 미설치 (시스템 python에만 설치)

- **증상**: 봇 재시작 후 로그에 `Backfill: cold start failed silently: No module named 'pandas_market_calendars'` 경고. 단위 테스트는 모두 통과하는데 봇에서만 실패.
- **원인**: 새 의존성을 `pip install --break-system-packages`로 *시스템 python*에 설치했지만, 봇 runtime은 `.venv/bin/python3` (venv) 사용. `requirements.txt`만 갱신하고 venv에 실제 `pip install`을 안 함.
- **해결**: `.venv/bin/python3 -m pip install -r requirements.txt` (또는 명시 패키지).
- **복구 절차**:
  1. venv 위치 확인: `which python3` (봇 환경에서)
  2. `.venv/bin/python3 -m pip install 'pyarrow>=14.0.0' 'pandas_market_calendars>=4.0.0'`
  3. 봇 재시작
  4. `logs/app/casper_*.log` 에서 `No module named` 사라졌는지 확인
- **관련 사고**: 2026-05-12 (ICT Phase 4 통합 후)
- **재발 감지**: `requirements.txt` 변경 후 *항상* `.venv/bin/python3 -m pip install -r requirements.txt` 실행. pytest는 시스템 python으로 돌리면 통과해도 봇은 venv라 실패.

### Claude 진단 미스 (이번 사고)
- **Claude 처음 가설**: `pip install --break-system-packages` 명령으로 시스템 python에 모듈이 들어갔으니 봇도 인식할 것이라 추정. venv 분리를 잊음. 단위 테스트는 시스템 python으로 실행해 통과 → 봇도 통과할 것이라 가정.
- **실제 원인**: pytest와 봇 runtime이 **다른 python**. pytest는 `python -m pytest`(시스템), 봇은 `run_casper.sh`의 `activate_venv()`로 `.venv/bin/python3`. 두 환경의 site-packages가 분리.
- **방향 전환 지점**: 사용자 "적용 확인" → 로그에 `ModuleNotFoundError` 발견 → venv 점검 후 설치.
- **교훈**:
  - 첫 의심 영역: **테스트 환경과 봇 runtime이 같은 python인지**. Python 프로젝트는 venv 분리가 보통.
  - 빨리 배제할 가설: "pip install 성공이면 모든 곳에서 import 가능" — Python에서 가장 자주 깨지는 직관.
  - 점검 패턴: `requirements.txt` 수정 → *반드시* venv에서도 install. `which python3` 와 `head -1 .venv/bin/python3.14`로 어느 python인지 확인.
  - 핵심 진단 명령: `.venv/bin/python3 -c "import <module>"` — 봇이 사용할 python으로 직접 import 테스트.

---

## 텔레그램 시작 메시지가 새 ICT 옵션을 표시하지 않음 (UI 동기화 누락)

- **증상**: `notify_bot_started`에서 KZ/Disp/Sweep/Bias/QQQ→SQQQ 5개만 표시. Phase 4 신규 5개(QQQ→TQQQ, OTE, Unicorn, MTF-SL, P3)는 모두 누락. bash stdout / app log / status CLI 에서는 정상 표시.
- **원인**: 새 옵션을 추가할 때 4-channel 라벨 sync 중 *Telegram notifier* 만 누락. `strategy_info` dict에 새 키 5개를 추가하지 않았고, `notify_bot_started`의 ict_flags 빌더도 5개만 인식.
- **해결**: `bot.py:strategy_info` dict에 ict_bull_for_tqqq/ict_ote/ict_unicorn/ict_mtf_sl/ict_power_of_3 키 추가. `notifier.py:notify_bot_started`의 ict_flags 빌더에 5개 처리 분기 추가.
- **복구 절차**:
  1. `src/bot.py`의 `strategy_info` dict 갱신
  2. `src/telegram/notifier.py`의 `notify_bot_started` ict_flags 갱신
  3. 봇 재시작
  4. Telegram 시작 알림에 10개 옵션 모두 표시되는지 확인
- **관련 사고**: 2026-05-12 (ICT Phase 4 N1~N6 통합 직후)
- **재발 감지**: 새 ICT 옵션 추가 시 *동시에* 4개 채널 모두 grep으로 점검. 추가 헬퍼: `grep -n "ict_killzone\|ict_displacement\|ict_sweep\|ict_bias\|ict_bear\|ict_bull\|ict_ote\|ict_unicorn\|ict_mtf\|ict_power" src/`

### Claude 진단 미스 (이번 사고)
- **Claude 처음 가설**: bash stdout과 status CLI에 옵션을 추가했으니 telegram도 같은 데이터를 표시할 것이라 추정. 4-channel sync 점검을 생략.
- **실제 원인**: 4채널은 *독립적* 코드 경로 (bash python inline / logger.info / `run_bot.py` _ict_status_line / telegram notifier). 한 곳을 고치면 다른 곳도 자동 동기화되지 않음.
- **방향 전환 지점**: 사용자 "텔레그램 메시지도 점검해" → unit-test로 시뮬레이션 → 5개 누락 확인 → notifier + bot.py 동시 수정.
- **교훈**:
  - 첫 의심 영역: **UI 라벨이 N개의 코드 경로에서 따로 생성되는가**. 라벨 변경은 *모든* 경로에 동시 적용 필요.
  - 4-channel sync 표 (캐스퍼봇):
    1. bash `run_casper.sh` start_bot/start_daemon stdout
    2. `bot.py:run()` logger.info startup banner
    3. `run_bot.py:_ict_status_line()` (status CLI)
    4. `notifier.py:notify_bot_started()` (telegram)
  - 빨리 배제할 가설: "한 곳을 고치면 다른 곳도 자동" — UI 라벨은 보통 그렇지 않음.
  - 핵심 진단 명령: 봇 시작 후 직접 시뮬레이션: `python3 -c "from src.telegram.notifier import TelegramNotifier; ..."`로 텔레그램 메시지 형태를 코드로 캡처. 또는 4채널 grep 동시 확인.
