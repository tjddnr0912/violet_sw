# Casper 트러블슈팅

각 항목은 6필드(증상/원인/해결/복구절차/관련 사고/재발 감지) + Claude 진단 미스 기록 구조를 따른다. "Claude 진단 미스"는 과거 세션에서 진단 방향이 한 번 빗나갔던 경우만 기록 — 미래의 같은 패턴이 나오면 처음부터 올바른 영역을 보도록 가이드하기 위함.

---

## trend·GEM 월말 리밸런스가 봇을 계속 켜두면 영영 실행 안 됨 (RTH 재시도 누락)

- **증상**: `sleeve_engine=trend` + `TREND_MODE=auto`(또는 `GEM_MODE=auto`)인데 월말이 지나도 trend 버킷이 `$0`(`data/portfolio_state.json` trend `current_value_usd: 0.0`, `current_symbol: null`)이고 `data/trend_state.json`의 `last_signal_date`가 `null`. 텔레그램으로 "trend signal" 알림은 왔는데 실제 매수 주문이 안 나감. GEM도 정규 월말 로테이션이 한 번도 자동 실행 안 됨(`gem_state`가 seed일에 멈춤).
- **원인**: 일일 멀티버킷 틱(`_daily_portfolio_tick`)은 **신규일 감지(`_reset_day`)에서만** 호출되고, 신규일은 ET 00:00 = **KST 13:00에 바뀌는데 그 시각 미국장은 마감**. `_maybe_run_gem`/`_maybe_run_trend`는 auto 모드라도 `is_market_open()`이 False면 실행을 보류(defer)한다. 그런데 seed(`_seed_pending`)와 달리 **GEM/trend엔 RTH 재시도 경로가 없었고**, 틱 끝의 `save_evaluation`이 `last_eval_date=today`로 그날을 잠가(`_portfolio_tick_done_for` 가드) 장이 열려도 틱이 다시 안 돈다. 결과적으로 봇이 계속 켜져 있으면 월말 주문이 영영 안 나가고, RTH(KST 22:30~05:00) 중 봇이 새로 시작될 때만 우연히 실행됨(초기 seed가 5/15에 성공한 이유 — seed는 `_seed_pending` RTH 재시도가 있었음).
- **해결**: `_gem_pending`/`_trend_pending` 플래그 추가(`_seed_pending` 미러). ① `__init__`에서 `should_run_*`로 arming(재시작·유예창 대응), ② 장 마감 defer 시 arming. `_tick`이 `is_market_open()` True가 되는 즉시 `_retry_deferred_rebalance()`로 보류분 실행. `gem_state`/`trend_state`로 멱등, 부분 실패 시 플래그 유지 → 다음 틱 재시도. (commit e7fd22c, 2026-06-01)
- **복구 절차**: (a) fix 이전 상태라면 — 봇을 정지하고 **RTH(KST 22:30~05:00) 중에** 새로 시작하면, 그날 KST 13:00 틱이 안 돈 상태라 `_reset_day`가 장중에 틱을 돌려 즉시 실행됨. (b) fix 적용 후엔 재시작만 하면 `__init__` arming + `_tick` 재시도가 자동 처리 (유예창=월말 마지막 거래일+3거래일 내, 그 외엔 다음 월말). (c) 확인: `cat data/trend_state.json` → `last_signal_date`가 해당 월말 날짜, `current_holding`/`last_exposure` 채워짐.
- **관련 사고**: 2026-06-01 (5/29 월말 trend 리밸런스가 KST 13:00 틱에서 보류된 채 미실행 → 사용자가 "장 열렸는데 trend 매매 안 한다" 지적 → RTH 재시도 갭 발견·수정. trend 첫 실행 결과: exposure 0.8331 → TQQQ 83.3% + BIL 16.7% vol-target 분할)
- **재발 감지**: 월말 다음 거래일 RTH에 `trend_state.json`/`gem_state.json`의 `last_signal_date`가 해당 월말로 갱신됐는지 점검. 안 됐는데 trend 버킷이 $0면 재발. **신규 sleeve를 auto 스케줄러로 붙일 때 반드시 RTH 재시도 경로(`_*_pending` + `_tick` 재시도)를 함께 달 것** — daily 틱은 항상 미국장 마감 시각(KST 13:00)에 발화하므로 "다음 틱에 재시도"는 RTH 재진입이 없으면 거짓이다. (참고: `_retry_deferred_rebalance`는 `save_evaluation`을 다시 부르지 않아 `portfolio_state.json` 버킷 값은 다음 데일리 틱까지 stale — 실보유는 broker 기준, cosmetic)

---

## Casper 프로세스 찾기 — 진입점이 `python -m src.bot`이 아니라 `run_bot.py`

- **증상**: `ps aux | grep "python -m src.bot"` 또는 `pgrep -f "src.bot"` 같은 패턴 검색이 빈 결과를 반환 → "봇이 죽었다"라고 잘못 판단.
- **원인**: Casper의 실행 entry는 프로젝트 루트의 `run_bot.py` 한 줄짜리 wrapper. `run_casper.sh`의 `start`/`daemon` 경로 둘 다 `python3 run_bot.py`를 호출하지 `python -m src.bot`을 호출하지 않음. 005/006/008 등 다른 봇은 모듈 실행 스타일을 쓰기도 해서 패턴이 다름.
- **해결**: 봇 alive 확인은 다음 중 하나로:
  - `pgrep -af "run_bot.py"`
  - `lsof -p $(pgrep -f run_bot.py) | grep casper_$(date +%F).log` (로그 파일 핸들 검증)
  - `ps -ef | grep -E "src\.bot|run_casper|run_bot\.py" | grep 014_casper` (cwd 확인 곁들이기)
  - **가장 확실**: 최신 로그 파일 mtime + lsof 핸들 보유 확인
- **복구 절차**: (a) `run_bot.py`로 재검색 (b) 안 보이면 `data/casper.pid` 확인 (daemon 모드만 생성) (c) 그래도 부재면 진짜 죽은 것 — `./run_casper.sh start --yes` 또는 cmux `restart` 스킬 사용
- **관련 사고**: 2026-05-14 라이브 봇 점검 세션
- **재발 감지**: 점검 스크립트에 `python -m src.bot` 단일 패턴 grep이 있으면 false negative 위험. `run_bot.py`도 함께 매치하도록 union 패턴 사용.

### Claude 진단 미스 (2026-05-14)

- **Claude 처음 가설**: `ps aux | grep -E "python.*src.bot|run_casper"`가 빈 결과 → "**Issue found**: There's NO 미장봇 process running. The process list shows ... but no `python -m src.bot` for Casper. The screen scrollback ended at 07:20:58 with 'New Day' but the process is not running anymore. ... It may have crashed silently or exited cleanly."
- **실제 원인**: 봇은 정상 동작 중. PID 96955 (`python3 run_bot.py`), cwd=014_casper, 로그 파일 핸들 보유. silent polling이 정상 (off-hours WAITING 상태에서 60초 sleep). grep 패턴이 너무 좁았던 것뿐.
- **방향 전환 지점**: `lsof | grep casper_2026-05-14.log` 로 로그 파일을 잡고 있는 프로세스를 역추적했더니 PID 96955 → `ps -p 96955 -o args` 결과가 `python3 run_bot.py` 였고, `head run_bot.py`로 "미장봇 - Entry Point" 헤더 확인.
- **교훈 (다음에 봇 alive 점검할 때)**:
  - 첫 의심 영역: **각 봇의 실제 entry script 이름** (014_casper=`run_bot.py`, 005=`auto_v3.py`, 007=각자 다름). `python -m <pkg>`를 가정하지 말 것
  - 빨리 배제할 가설: "프로세스 없음 = 봇 죽음" (먼저 lsof로 로그 핸들 확인)
  - 핵심 진단 명령: `lsof | grep casper_$(date +%F).log` → 핸들 보유 PID 확보 → `ps -p $PID -o args` → entry 정체 확인
  - 화면 무출력 ≠ 봇 죽음. WAITING/DONE_TODAY 상태는 60~300초 sleep 폴링이라 long quiet가 정상

---

## Claude의 옵션 분석 — "선택" vs "보완" 관계 혼동 (NQ vs QQQ premkt)

- **증상**: 사용자에게 두 데이터 보강 옵션(A: NQ futures session pools, B: yfinance prepost로 QQQ premkt fetch)을 제시할 때 *"하나를 선택"*하라는 식으로 제시. 그러나 권장 워크플로에는 "프리마켓 fetch를 추가"한다고 적어 일관성 결여.
- **원인**: Claude가 두 옵션의 *목적*을 분리해서 보지 않음. 둘 다 같은 목적(sweep pool 보강)으로 비교했으나 실제로는:
  - 목적 A — *sweep candidate 풀에 가격값 추가*: NQ도 OK, QQQ premkt도 OK (NQ가 풍부)
  - 목적 B — *swing fractal 시계열 확장 → CHoCH 정상화*: **QQQ 자체 premkt만 가능**. NQ는 다른 종목 차트라 fractal 의미 없음
- **해결**: 결정 → 두 옵션 동시 도입.
  - QQQ premkt fetch (`use_premkt_history=true`) → swing fractal 확장 + premkt 1쌍 sweep pool 부산물
  - NQ session pools (이미 ON) + NQ→QQQ ratio 단위 fix → Asia/London 시간대 풀 보존
  - PDH/PDL 추가 보강 (`use_pdh_pdl_pool=true`)
- **복구 절차**: (a) 두 옵션의 *목적 분리* 명시적 비교 (b) "선택 vs 보완" 결정 (c) 단위 일치/불일치 확인
- **관련 사고**: 2026-05-13 워크플로 설계 시점
- **재발 감지**: 사용자가 "이전 설명에 따르면 X가 더 나은 것처럼 ... 그런데 워크플로에는 Y" 같은 일관성 지적

### Claude 진단/설계 미스 (이번 세션 = 2026-05-13)

- **Claude 처음 가설**: "옵션 C (NQ + QQQ premkt 혼합)이 우월, *하지만 우선순위는 NQ가 ICT 정통 흐름 보존*" — 두 옵션을 sweep pool 보강 한 가지 목적으로 비교
- **실제 원인 (사용자 지적)**: "프리마켓 fetch랑 NQ future 중 하나를 선택하는 게 좋아? ... 워크플로우에는 프리마켓 fetch를 추가하는 것처럼 보여서 동작을 어떻게 구현하려는지 자세히 설명해" → Claude가 두 옵션의 진짜 목적(sweep pool 가격 vs swing fractal 시계열)을 분리하지 않은 채 비교한 게 드러남
- **방향 전환 지점**: 사용자의 정정 요청 후 — "둘 다 가져갑니다. 역할이 다릅니다" 명시. swing fractal 시계열 (CHoCH 정상화)이 어제 09:55 reject의 *진짜 병목*이라는 점도 동시 노출됨
- **교훈 (다음에 비슷한 옵션 분석할 때)**:
  - 옵션 비교 전에 *각 옵션이 해결하는 진짜 목적*을 분리해서 정의
  - "선택 vs 보완"을 명시적으로 결정 (목적이 다르면 보완, 같으면 선택)
  - 워크플로/구현 계획이 옵션 비교 결론과 *일관*되는지 self-check
  - 우선순위 만들 때 "어느 게 더 좋은가"보다 "어느 게 진짜 병목을 해결하는가"

---

## Claude의 백그라운드 폴링 셸이 영원히 sleep — 종료 조건 미스

- **증상**: `Bash run_in_background`로 띄운 `until grep -q ... do sleep N done` 폴링 셸이 시스템 통보 후에도 계속 살아있음. `ps -ef`에 sleep 프로세스가 누적.
- **원인**: 폴링 종료 조건이 실제 출력과 매치하지 않음. 케이스 (a) 파일 경로 오타 (`/tmp/foo.log`인데 실제는 `/private/tmp/claude-501/.../tasks/<id>.output`), (b) grep 키워드가 출력에 등장하지 않는 형태(`=== ` 공백 포함, 대소문자 차이 등).
- **해결**: 폴링 자체를 지양. `run_in_background:true`로 명령을 띄우면 시스템이 자동 task-notification을 전달하므로 폴링이 불필요. 굳이 폴링한다면:
  1. 항상 실제 출력 파일 경로(`<task-notification>`의 `<output-file>`) 사용
  2. grep 패턴은 pytest 종료 표시(`passed\|failed\|error\b`)나 명시 echo(`echo DONE`) 등 출력에 *반드시* 나오는 토큰
  3. `timeout_ms` 한정 적용 또는 `Monitor` 도구 사용
- **복구 절차**:
  1. `ps -ef | grep "until grep\|sleep"` 으로 dangling 셸 PID 식별
  2. `TaskStop --task_id <bg-id>` 로 graceful 종료 (가능하면)
  3. 안 되면 `kill -TERM <PID>` (사용자 워크스페이스 ttys에 attach된 셸은 건드리지 말 것)
- **관련 사고**: 2026-05-12 (P1 회귀 폴링 21분, backtest 폴링 23분 무한 sleep)
- **재발 감지**: 한 세션에서 `until` 또는 `while true` 루프를 2개 이상 띄우면 plausible warning. ps -ef 주기 점검.

### Claude 운영 실수 (이번 세션 = 2026-05-12)
- **Claude 실수 패턴**: `Bash run_in_background:true`로 띄운 명령은 시스템이 자동 노티 보내는데, 별도 `until grep ... sleep` 폴링 셸을 추가로 띄움. 종료 조건 grep 패턴/경로를 실수해도 self-detect 불가 → 영원히 sleep.
- **올바른 패턴**: `run_in_background:true` → 알림 기다림 → 도착 시 `cat`/`tail`로 결과 읽기. 폴링 셸은 생성 자체를 피한다.
- **교훈 (다음에 같은 작업 시작 시)**:
  - 백그라운드 명령은 `run_in_background:true` 하나만 띄움
  - 결과 대기는 사용자에게 짧게 보고 + 시스템 task-notification 신호로 자동 깨어남
  - 폴링이 정말 필요하면 `Monitor` 도구 (until-loop 내장 지원)

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
- **방향 전환 지점**: 사용자 메시지 "지금 미장봇 재시행하니까 터미널 출력에 ict 통합전이라고 나오는데?" — Claude가 즉시 라벨 코드 위치 파악 후 `Bias*` → `Bias` 분리. 같은 세션에서 사용자 명령 "통합 진행해"로 Bear도 통합 후 라벨을 `QQQ→SQQQ`로 변경.
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
  - 4-channel sync 표 (미장봇):
    1. bash `run_casper.sh` start_bot/start_daemon stdout
    2. `bot.py:run()` logger.info startup banner
    3. `run_bot.py:_ict_status_line()` (status CLI)
    4. `notifier.py:notify_bot_started()` (telegram)
  - 빨리 배제할 가설: "한 곳을 고치면 다른 곳도 자동" — UI 라벨은 보통 그렇지 않음.
  - 핵심 진단 명령: 봇 시작 후 직접 시뮬레이션: `python3 -c "from src.telegram.notifier import TelegramNotifier; ..."`로 텔레그램 메시지 형태를 코드로 캡처. 또는 4채널 grep 동시 확인.

---

## Multi-bucket 봇 초기 자본 시드를 ‘수동 매수 권고’로 잘못 설계

- **증상**: `$3,000` 100% 현금 상태에서 봇이 시작해도 SPMO·GEM 자산을 자동 매수하지 않음. 첫 분기말까지 자본 80%가 cash로 놀음. 사용자가 KIS 앱에서 수동으로 SPMO 12주 + GEM 자산을 매수해야 작동.
- **원인**: P3 (portfolio bucket) 초기 설계에서 ‘리밸런스는 분기말 drift 5%+ 시에만’ 규칙만 두고, **첫 1회 ‘seed 매수’ 트리거가 없음**. 봇이 cash 상태를 drift로 인식해도 분기말까지 기다림.
- **해결**: `portfolio.py`에 `needs_initial_seed(total, holdings, state)` + `PortfolioState.seeded_at` 필드 추가. cash 비율 ≥ 90% AND seeded_at=None 이면 ‘일회성 자동 매수’ fire. 매수 후 `seeded_at`=today 영속화 → 재시작 후에도 중복 매수 0.
- **복구 절차**:
  1. `src/core/portfolio.py::needs_initial_seed` 추가 (cash ratio 90% threshold)
  2. `PortfolioState.seeded_at` 필드 + JSON 직렬화 추가
  3. `src/bot.py::_execute_initial_seed` 메서드 + `_daily_portfolio_tick`에서 호출
  4. 봇 재시작 후 다음 RTH에 자동 fire 확인
- **관련 사고**: 2026-05-15 (P3 첫 운영 직전)
- **재발 감지**: 새 bucket 추가 시 ‘처음 0%에서 어떻게 채워지나’ 시나리오 unit-test 1건 필수.

### Claude 진단 미스
- **Claude 처음 가설**: "$3,000 자본 분배 권고 = (a) SPMO 12주 수동 매수 (b) GEM 자산 수동 매수 (c) 그 후 봇이 분기/월 리밸런스만 자동 처리". ‘초기 시드’를 사용자 수동 작업으로 떠넘김.
- **실제 원인**: KIS API의 ETF 매수는 이미 미장봇이 매일 사용하는 **동일 인프라**. 초기 시드도 `kis_order.buy_market(symbol, qty)` 한 줄로 자동화 가능. ‘일회성 트리거 + state flag 1개’로 해결되는 것을 ‘사용자 노력’으로 잘못 위임.
- **방향 전환 지점**: 사용자 "처음 수동매수를 해야해? 왜 이것조차 자동으로 하게 할 수 없나? 현재 전액 현금 보유중이야" → Claude가 즉시 `_execute_initial_seed` + `needs_initial_seed` + `seeded_at` 구현.
- **교훈**:
  - 첫 의심 영역: **‘무엇이 자동인가’ 설계 시 기존 인프라의 재사용 가능성**부터 점검. ‘봇이 매매 인프라를 이미 갖고 있는데 일회성 트리거만 빠졌는가?’를 묻는다.
  - 빨리 배제할 가설: "사용자가 일회성 작업은 직접 하는 게 편리하다" — 자동화 봇 사용자는 정확히 그 반대를 원함.
  - 핵심 진단 명령: 새 기능 권고할 때 “이 단계는 자동 가능한가”를 매 단계마다 명시. 예: "Phase A (수동) → Phase B (자동)"이면 "Phase A를 자동으로 만들 수 있는 트리거가 있는가?"부터 점검.

---

## 코드/.env 변경 후 ‘적용 완료’ 보고 직전에 실행 중인 프로세스 재시작을 빠뜨림

- **증상**: 사용자가 “env랑 shell 재시작에 해당 옵션들 적용은 다 됐나?”라고 물음. Claude는 직전에 `.env`에 새 옵션을 추가하고 “적용 완료”라고 보고했지만, **봇은 이미 옛 코드로 실행 중이라 새 코드·새 env가 메모리에 반영 안 됨**. 사용자가 알아채지 못했다면 봇은 그 채로 계속 옛 동작.
- **원인**: Python `load_dotenv()`는 import 시점에 한 번만 실행됨. 봇이 이미 실행 중이면 `.env` 수정해도 그 프로세스는 옛 값 사용. 코드도 마찬가지 — `import` 시점에 모듈이 메모리에 박힘. **‘파일 수정 = 적용’이 아니라 ‘프로세스 재시작 = 적용’**.
- **해결**: 코드/.env 변경 후 ‘적용 완료’ 보고 *전에* 반드시:
  1. `ps aux | grep <bot>` 또는 cmux read-screen으로 실행 중인 프로세스 확인
  2. 실행 중이면 Ctrl+C(또는 SIGTERM) 후 동일 명령 재실행
  3. 새 코드의 startup banner / 새 옵션 활성화 로그(예: `GEM scheduler active`) 를 cmux read-screen으로 확인
  4. 그제야 “적용 완료” 보고
- **복구 절차**:
  1. 사용자에게 “봇 재시작 필요” 알림
  2. cmux send `\x03` (Ctrl+C) → 1~2초 대기 → cmux read-screen으로 shell prompt 확인
  3. cmux send `./run_casper.sh start --yes\n` → 8~10초 대기 → 새 startup banner 확인
  4. 새 코드 시그널 (예: `GEM scheduler active`, `Initial seed needed but US market is closed — deferring to RTH`) 출력 검증
- **관련 사고**: 2026-05-15 (Multi-bucket P0~P3 통합 후 봇 재시작 누락)
- **재발 감지**: 코드 변경 + ‘적용 완료’ 보고 사이에 반드시 `ps aux` 또는 cmux read-screen 점검 단계를 끼워 넣음.

### Claude 진단 미스
- **Claude 처음 가설**: "`.env`에 옵션 추가 = 다음 봇 시작 시 자동 적용". 봇 재시작 여부 확인 없이 ‘적용 완료’ 보고.
- **실제 원인**: 봇이 이미 cmux surface:54에서 옛 코드로 실행 중. `_daily_portfolio_tick`도, `needs_initial_seed`도, 새 `.env` 옵션도 메모리에 없음.
- **방향 전환 지점**: 사용자 "env랑 shell 재시작에 해당 옵션들 적용은 다 됐나?" → Claude가 `ps aux` + cmux read-screen으로 봇 상태 점검 → 옛 코드 실행 중 확인 → 재시작 자동화.
- **교훈**:
  - 첫 의심 영역: **“코드 변경 → 자동 적용” 가정 금지**. Python·daemon·서비스는 명시적 재시작이 필수.
  - 빨리 배제할 가설: "다음 tick에서 자동 reload되겠지" — `load_dotenv()`, `import`는 startup 시점에만 호출됨.
  - 핵심 진단 명령: 변경 후 보고 직전에 `ps aux | grep <bot_proc>` + cmux/iTerm 화면에서 새 startup banner 확인. cmux 환경: `cmux read-screen --surface surface:N --lines 30`.

---

## 멀티버킷 ETF가 KIS에서 매수/가격조회 silently 실패 (NASD/AMEX 거래소 코드 미스매치)

- **증상**: 시드 실행 시 SPMO·VEU·MTUM·QUAL·SPY·AGG·BIL 등 NYSE Arca-listed ETF에 대해 `Initial seed: cannot fetch price for <SYM>` 또는 `BUY: Cannot get price for <SYM>` 에러. TQQQ/SQQQ/QQQ는 정상.
- **원인**: KIS overseas API는 거래소 코드를 정확히 받아야 한다. `get_us_price`/`buy_market`/`sell_market`의 default가 `exchange="NASD"`인데 NYSE Arca 종목은 `"AMEX"` 코드로 조회해야 한다. 원래 봇은 TQQQ/SQQQ만 다뤄서 NASD default가 정확했지만 멀티버킷 도입 후 Arca-listed 종목에선 silent fail.
- **해결**: `src/core/portfolio.py`에 `TICKER_EXCHANGE` 매핑 + `exchange_for(symbol)` 헬퍼. 모든 multi-bucket KIS 호출 사이트(시드 / 잔고 snapshot / GEM rotation / drift rebalance — 총 9곳)에 `exchange=exchange_for(symbol)` 명시. `src/api/kis_order.py::_get_market_price` 내부 호출도 exchange 인자 전파.
- **복구 절차**: (a) `./run_casper.sh stop` (b) `data/portfolio_state.json` 백업 후 `seeded_at`·`last_eval_date`를 `null`로 (c) `./run_casper.sh daemon --yes` (d) 다음 RTH 안에서 `Initial seed complete: N buckets funded` + `ORDER OK` 로그 확인.
- **관련 사고**: 2026-05-15 (멀티버킷 시드 첫 가동, KIS exchange mismatch로 2회 연속 0건 매수)
- **재발 감지**: 신규 ETF는 `TICKER_EXCHANGE`에 등록해야 함. 누락 시 default NASD로 fallback → 첫 시드/rotation에서 즉시 fail. 등록 검증: `python -c "from src.core.portfolio import exchange_for; print(exchange_for('NEW_SYM'))"`.

### Claude 진단 미스 (2026-05-15)

- **Claude 처음 가설**: `_execute_initial_seed`의 `get_us_price(symbol)`만 NASD default라 매수 실패. 그 한 호출에 `exchange=ex` 추가하면 해결될 거라 판단.
- **실제 원인**: `kis_order.buy_market`이 내부에서 `_get_market_price(symbol)`을 또 호출하는데 그 helper가 다시 `client.get_us_price(symbol)`을 exchange 없이 호출. 즉 같은 default 함정이 한 layer 더 안쪽에 있었음.
- **방향 전환 지점**: 1차 fix 후 봇 재기동 → 시드 재시도 → 동일 에러 `BUY: Cannot get price for SPMO`. grep로 발생 위치 추적해서 `kis_order.py:49` 발견.
- **교훈 (다음에 횡단 default 인자 fix할 때)**:
  - 첫 의심 영역: **공통 인자(exchange/region/account)는 모든 layer를 한 번에 grep**. `grep -rn "get_us_price\|buy_market\|sell_market" src/`로 전수 조사 후 fix 범위 결정.
  - 빨리 배제할 가설: "한 호출 사이트만 고치면 끝난다" — 같은 default가 내부 helper에도 있을 확률 높음.
  - 핵심 진단 명령: `grep -nE "def _get_market_price|def get_us_price|def buy_market|def sell_market" src/api/` + 각 함수의 default 인자 점검.

---

## 시작/상태 배너가 sleeve_engine=trend인데 레거시 인트라데이 전략을 설명 (배너 3곳 분산)

- **증상**: 20% sleeve를 인트라데이 ORB+FVG → 저빈도 TQQQ Vol-Target(`sleeve_engine=trend`)로 교체했는데도, 봇 시작 로그와 `./run_casper.sh status` 출력에 여전히 `전략: ORB + FVG + Pullback (R:R 1:3)`, `스캔: DUAL SCAN (TQQQ+SQQQ)`, `FVG: STRICT`, `ICT: KZ(AM_MACRO,AM_LATE) + Disp + ...`, `📌 Fine-tune: ICT 매매 N건 누적`이 표시됨. 비활성 엔진을 설명하므로 운용자에게 거짓 정보.
- **원인**: 봇의 "전략 설명" 배너가 **3개 파일에 독립적으로** 존재하고, 전부 `sleeve_engine` 분기 없이 인트라데이 텍스트를 무조건 출력했음.
  1. `src/bot.py` `run()` — Python 로거 배너(`INFO casper |` 접두사, 봇 실행 중). "Intraday engine GATED OFF"라고 선언만 하고 그 아래 상세 블록(Scan/FVG/R:R/ICT/매매 윈도우/Fine-tune)을 무조건 print.
  2. `run_casper.sh` `start_bot()` / `start_daemon()` — 셸이 봇 실행 *전* 출력(`[INFO]`/`[OK]` 접두사). `전략: ORB+FVG+Pullback` 등 하드코딩.
  3. `run_bot.py` `show_status()` — `./run_casper.sh status` → `python3 run_bot.py --status` 경로(`=== Cumulative Stats ===` 블록). R:R/Strict FVG/ICT/Fine-tune 무조건 print.
  `ICT 매매 N건 누적`은 과거 인트라데이 시절 거래가 `trades_*.json`에 남아 카운트된 것 — 데이터는 정상, 표시 분기가 빠진 게 root cause.
- **해결**:
  - ① `_log_intraday_startup_detail()` / `_log_trend_startup_detail()` 메서드로 추출, `run()`에서 `sleeve_engine`으로 분기 (커밋 7535979, c0aeb58).
  - ② `run_casper.sh`에 `show_trend_banner()` 헬퍼 추가, `start_bot`·`start_daemon` 둘 다 `sleeve_engine!=intraday`면 호출·레거시는 else 브랜치 (커밋 e4a7bc2, 실행권한 복구 25af01f).
  - ③ `run_bot.py`에 `_print_trend_status()` 추가, `show_status()`에서 분기 (커밋 ba38900).
  - 세 배너 모두 동일 문구(슬리브/전략/노출/리밸런스/상태/비활성)로 통일. 전략 무관 라인(Cumulative Stats/Win Rate/History)은 유지. 전부 `sleeve_engine=intraday`로 되돌리면 레거시 배너 복원(가역).
- **복구 절차**: 코드 수정 후 봇 재시작해야 반영(실행 중 프로세스는 옛 코드). (a) `./run_casper.sh stop` (b) `./run_casper.sh daemon --yes` (c) 시작 배너에 `슬리브: TREND` / `전략: QQQ>200d SMA ...` 확인, `./run_casper.sh status`도 동일 확인.
- **관련 사고**: 2026-05-31 (sleeve_engine 교체 후 배너 3곳 잔존)
- **재발 감지**: 전략 표시 문구를 새로 추가할 땐 3곳(`src/bot.py` run, `run_casper.sh`, `run_bot.py` show_status)을 모두 점검. `grep -rn "ORB + FVG + Pullback\|DUAL SCAN\|전략: ORB" src/ run_bot.py run_casper.sh`로 ungated 라인 전수 조사. 테스트: `tests/test_bot_banner_sleeve.py` (trend=인트라데이 상세 없음+Trend 설명 있음 / intraday=레거시 복원).

### Claude 진단 미스 (2026-05-31)

- **Claude 처음 가설**: 시작 로그의 "ICT 거래 누적" 설명은 `src/bot.py`의 Python 로거 배너 한 곳 문제. 그 한 파일만 `sleeve_engine` 분기 처리하면 끝이라고 보고 "수정 완료, 재시작하면 반영"이라 보고.
- **실제 원인**: 같은 "전략 설명" 배너가 **3개 파일에 분산**(Python 로거 / 셸 스크립트 / `--status` CLI). `src/bot.py`만 고치자 사용자가 셸 배너(`[INFO] 전략: ORB + FVG + Pullback ...`)를 보고 "이 부분은 하나도 안 고쳐졌잖아"라고 지적. 그걸 고친 뒤 `status` 검증 중 3번째(run_bot.py)까지 발견.
- **방향 전환 지점**: 사용자가 봇 터미널 출력 raw 텍스트(`[OK] KIS API 키 확인됨 / [INFO] 전략: ORB + FVG + Pullback ...`)를 붙여넣고 "이 부분은 하나도 안 고쳐졌잖아" → 로그 접두사(`[INFO]` = 셸, `INFO casper |` = Python)로 출처가 다름을 인지하고 셸 스크립트 발견. 이후 `./run_casper.sh status` 렌더 확인 중 3번째 발견.
- **교훈 (다음에 "배너/시작 로그에 옛 설명이 남아있다" 신고를 받으면)**:
  - 첫 의심 영역: **같은 문구가 여러 출력 경로에 중복 존재한다고 가정하고 전수 grep**. 봇 류는 보통 (a) Python 로거 시작 배너 (b) 셸 런처(`run_*.sh`) 배너 (c) `--status`/`--help` CLI 출력에 같은 설명이 따로 하드코딩됨. 한 곳 고치고 "완료" 보고 금지.
  - 빨리 배제할 가설: "로거에서 한 번만 print하니 한 곳일 것"이다 — 셸 런처가 봇 실행 *전에* 자체 배너를 찍는 경우가 흔함. **로그 접두사로 출처 판별**: `INFO casper |`=Python 로거, `[INFO]`/`[OK]`(타임스탬프 없음)=셸 echo, `=== ... Stats ===` 박스=`run_bot.py --status`.
  - 핵심 진단 명령: `grep -rn "ORB + FVG + Pullback\|DUAL SCAN\|전략:\|R:R:\|ICT :" src/ run_bot.py run_casper.sh` — 전략 설명 문자열의 모든 출처를 한 번에 나열한 뒤 각각 `sleeve_engine` 게이트 여부 확인.

---

## Initial seed full-fail 시 영구 lock-out — `seeded_at`이 0건에도 박힘

- **증상**: 시드 매수가 0건이어도 `data/portfolio_state.json::seeded_at = "<today>"`이 박혀 다음 봇 재시작에서 `needs_initial_seed=False`로 시드 진입 영구 차단.
- **원인**: `_execute_initial_seed`는 본래 "ALWAYS mark seeded" 정책 (재시도 폭주 방지 의도). 하지만 매수 0건은 부분 실패가 아니라 **완전 실패** — 그 정책이 retry를 영구로 차단하는 사이드이펙트가 있다. 추가로 `_daily_portfolio_tick`이 `save_evaluation`으로 `last_eval_date=today`까지 박아 `_portfolio_tick_done_for` guard도 활성화.
- **해결**: `_execute_initial_seed` → `bool` 반환 (매수 ≥ 1건이면 True + `seeded_at` 박음, 0건이면 False + 박지 않음). `_daily_portfolio_tick`이 False 받으면 `save_evaluation`/`_portfolio_tick_done_for=today` 둘 다 건너뛰고 일찍 return → 다음 `_tick`/`_reset_day`에서 자연 재시도.
- **복구 절차**: (a) `./run_casper.sh stop` (b) `data/portfolio_state.json::seeded_at` + `last_eval_date`를 `null` (c) 재기동 → 자동 재시도.
- **관련 사고**: 2026-05-15 (KIS exchange mismatch 사고와 동시 발생 — 시드 0건이 두 번 누적)
- **재발 감지**: `Initial seed: 0 positions opened — seeded_at NOT marked; next tick will retry` warning 로그가 뜨면 자동 재시도 중. 같은 warning이 5회 이상 반복되면 KIS API/거래소 문제 의심.

---

## Scan window 시간에 봇 시작/재시작 시 SCANNING 합류 불가 — Late entry 분기 부재

- **증상**: ET 09:45~10:55 (KST 22:45~23:55) 매수 윈도우 진행 중에 봇을 새로 시작하거나 재시작하면, `STATE: ... → SCANNING` 로그가 끝까지 안 나오고 그 날 캐스퍼 거래 0건. WAITING 상태로 `sleep 60`만 반복.
- **원인**: `_handle_waiting`이 `is_pre_market` / `is_orb_forming` 두 시간대만 분기 처리. `is_scan_window` 시간대 분기 부재. 추가로 ORB는 메모리(`self.orbs`)에만 있어 같은 거래일 재시작 시 lost되어, 우연히 SCANNING으로 도달해도 시그널 평가 불가.
- **해결**:
  - `_handle_waiting`에 `is_scan_window` 분기 추가 → PRE_MARKET 으로 전이. 거기서 trend 계산 후 `_handle_pre_market`의 "Late join" 경로로 ORB_FORMING. 그 안에서 5분봉 backfill로 ORB 재계산 → SCANNING.
  - `data/intraday_state.json`에 trend + ORBs 영구 저장 (`_save_intraday_state` in PRE_MARKET 끝 + ORB_FORMING → SCANNING 전이 직전). `_reset_day` 끝에서 `_load_intraday_state`로 today 매칭 시 복원.
  - `_handle_orb_forming` 시작에 "이미 `self.orbs` 있으면 SCANNING 직행" 분기 → 재계산 회피 + 즉시 시그널 탐색 재개.
- **복구 절차**: 자가 복구. 봇 재기동 시 자동 합류.
- **관련 사고**: 2026-05-15 (23:27 KST 시드 직후 봇이 SCANNING으로 못 들어가 23:55까지 침묵, 그날 캐스퍼 매매 0건)
- **재발 감지**: 봇 시작 후 5분 안에 `STATE: WAITING → PRE_MARKET` 또는 `Late entry — scan window` 로그가 안 보이면 의심. SCANNING 시간에 startup banner만 찍히고 state 전이 없으면 즉시 lookup.

### Claude 진단 미스 (2026-05-16)

- **Claude 처음 가설**: 시드 매수 성공 = 미장봇 정상 동작 완료. 사용자에게 "캐스퍼는 시그널 발생 시 자동 매수, 미발생이면 23:55 종료"라고 보고하고 봇 종료 안내.
- **실제 원인**: 시드 후 SCANNING 윈도우 안에 있었는데 `_handle_waiting`이 그 시간을 처리 못해 sleep만 반복. "시그널 미발생"이 아니라 "시그널 평가 자체를 시작 못함" 상태.
- **방향 전환 지점**: 사용자 "11시 37분 이후 특별한 로그가 없는데 제대로 된 거 맞아? 정밀하게 검토" → Claude가 `_handle_waiting` 코드를 다시 읽고 scan_window 분기 부재 발견.
- **교훈 (다음에 멀티스테이지 봇 fix를 보고할 때)**:
  - 첫 의심 영역: **"임무 성공" 보고 전에 후속 상태머신이 의도대로 흐르는지 검증**. 한 단계 성공만 보고 "다음 상태에서 머무는가"는 별도 확인 필요.
  - 빨리 배제할 가설: "로그가 조용 = 정상 idle". 정상 idle은 폴링 로그가 한 번이라도 나옴 (예: `STATE: ... → SCANNING`). 봇 시작 후 N분 동안 STATE 전이 로그 0회면 abnormal.
  - 핵심 진단 명령: `grep -E "STATE:|=== New Day" logs/app/casper_$(date +%F).log | tail -20` — 상태 전이 시퀀스가 시작~ORB_FORMING~SCANNING 라인을 그리는지.

---

## Portfolio 메시지 'Target/Drift'를 사용자가 매도 트리거로 오해

- **증상**: 텔레그램 일일 포트폴리오 메시지에서 모든 bucket의 Drift가 음수(SPMO -4.4%, GEM -1.6%, CASPER -100%)로 표시됨. 사용자가 "내 계좌는 실제로 수익 + 상태인데 왜 봇은 마이너스?"로 오해. CASPER -100%는 "전손"처럼 보임.
- **원인**: 두 가지가 결합한 표시(meaning) 문제 — (a) `Bucket.drift_pct = (current_value_usd - target_usd) / target_usd`는 "목표 배분 대비 부족"이지 P&L이 아닌데, 메시지에 그 정의가 적혀있지 않음. 컬럼명 'Target'을 사용자는 "매도 트리거 가격" 또는 "익절 목표"로 해석. (b) CASPER bucket은 intraday 전용이라 일과 종료 시 항상 cash holding이 정상인데, 같은 공식으로 계산하면 `(0 - 626.94)/626.94 = -100%`로 떠 "거대한 손실"로 오인. 산수 자체는 모두 정확 — 총액 $3,134.69 = cash $711.70 + SPMO $1,498 + VEU $924.99, 그리고 모든 bucket diff 합계 = -cash. **계산 버그 아님, 용어 정의 부재.**
- **해결**: `src/telegram/notifier.py::notify_portfolio_summary`의 footer에 legend 1줄 추가 — `Current=평가금액(현재가×수량) · Target=목표배분(자본×weight, 매도가 아님) · Drift=배분편차(분기말 ±10%↑ 리밸런스)`. 컬럼 폭/구조는 그대로 유지(정렬 보존). KIS API/계산 로직은 손대지 않음.
- **복구 절차**: 봇 재기동 불필요. 다음 일일 portfolio tick (KST 13:00 또는 ET RTH 진입 시점)부터 새 메시지에 legend가 함께 발송.
- **관련 사고**: 2026-05-27 (사용자가 분기 리밸런스용 'Target' 컬럼을 매도 트리거로 오해, 모든 bucket drift 음수를 손실로 인식)
- **재발 감지**: 신규 알림 도입 시 도메인 용어(P&L, drift, allocation, exposure 등)를 컬럼 헤더로 쓰면 반드시 footer에 1줄 정의 추가. 사용자가 "메시지의 X가 이상하다"고 신고하면 먼저 X의 도메인 의미 ↔ 사용자 해석 차이부터 점검.

### Claude 진단 미스 (2026-05-27)

- **Claude 처음 가설**: KIS 잔고 API의 `frcr_drwg_psbl_amt_1`(외화 출금가능금액)이 미체결 매수/T+3 미결제 매도 자금을 제외하기 때문에 cash가 underestimate, 결과적으로 total/target이 어긋난다 — 또는 `_fetch_full_portfolio_snapshot`이 `get_us_price` 호출 실패 시 `avg_price`로 fallback해 cost basis로 표시될 가능성. 즉 **데이터 소스 mismatch가 root cause**라고 가정.
- **실제 원인**: 계산은 모두 정확 (산수: 총액 - 보유합 = cash, drift sum = -cash로 정합). 사용자가 'Target' 단어를 "매도 트리거"로 오해. 메시지 자체에 의미 설명이 없는 게 root cause — 데이터 흐름 / API 필드는 무관.
- **방향 전환 지점**: 사용자가 두 번째 메시지에서 "총자산은 비슷해. SPMO 1442→1502, VEU 893→927 평가금액이 더 높아 마이너스 상황 아니야. **아니면 target이란 목표를 말하는건가? 내 순 수익 상관없이 목표수치에 도달하면 매도되는 기준을 이야기하는거야?**" 라고 직접 용어 정의를 물어본 시점. 그 전까지 Claude는 KIS API 필드/가격 소스만 의심.
- **교훈 (다음에 사용자가 "텔레그램 메시지의 X가 이상하다"고 신고하면)**:
  - 첫 의심 영역: **메시지 컬럼 헤더의 도메인 용어 ↔ 사용자 직관 차이**. 'Target', 'Drift', 'Exposure', 'Allocation' 등은 트레이딩 용어로는 명확하지만 일반 사용자에게 다른 의미로 읽힐 수 있음. 사용자에게 "이 컬럼을 어떻게 해석했는지" 먼저 물어보면 30초 만에 root cause 확인 가능.
  - 빨리 배제할 가설: 사용자가 "KIS HTS 값과 봇 메시지가 비슷하다"고 했으면 → API 필드 mismatch는 거의 원인 아님. 산수 검증으로 "총액 - 보유합 = cash, drift합 = -cash" 정합이 확인되면 → 계산 버그 아님 100% 확정.
  - 핵심 진단 명령:
    ```bash
    # 메시지 시뮬레이션 — 사용자가 실제 본 화면 재구성
    python3 -c "import json; print(json.dumps(json.load(open('data/portfolio_state.json')), indent=2))"
    # 산수 정합 1줄: 총액 - 보유합 = cash, sum(diff) = -cash 여야 정상
    ```
