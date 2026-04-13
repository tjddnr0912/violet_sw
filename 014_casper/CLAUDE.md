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
| R:R | 1:2 고정 |
| 매매시간 | 09:45~10:55 ET (스캔), 15:50 강제청산 |
| 필터 | VIX(12~30), ORB 폭, 서킷브레이커(3연패/주간3%손실), 공휴일 |
| 안전장치 | 크래시 복구, SIGTERM, 포지션 상한, 오버나잇 방지, 잔고 동기화, 부분체결 감지 |
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

## 환경변수 (.env)

```bash
KIS_APP_KEY=         # 실전투자 앱키
KIS_APP_SECRET=      # 실전투자 시크릿
KIS_ACCOUNT_NO=      # 계좌번호 (8자리)
TRADING_MODE=live    # paper | live
TEST_MODE=on         # on | off (1주 고정)
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

## 테스트 격리 원칙

테스트가 production 데이터 파일(`data/trades/trades_YYYY.json`, `data/position_state.json`)에 쓰면 **누적 통계·서킷브레이커 기준이 오염**되어 실거래 판단에 영향. `tests/conftest.py`의 격리 fixture는 **반드시 `autouse=True`**여야 함. opt-in fixture는 Bot lifecycle 테스트가 내부적으로 `save_trade`를 호출하는 경로에서 조용히 누수됨. 검증 루프: 테스트 실행 전후 `md5 data/trades/trades_2026.json` 비교 → 동일하지 않으면 격리 실패.

## 상세 문서

- [코드 리뷰](docs/CODE_REVIEW.md)
- [설계 스펙](docs/superpowers/specs/2026-04-02-casper-bot-design.md)
- [전략 리뷰](docs/strategy/STRATEGY_REVIEW.md)
- [실행 계획](docs/strategy/EXECUTION_PLAN.md)
- [코드 감사](docs/CODE_AUDIT_2026-04-11.md)
