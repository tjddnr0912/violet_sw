# Casper × Freqtrade Gap Review

> Date: 2026-04-23
> Status: Draft — **리뷰 대기 (수정 전 논의용)**
> Scope: 시스템/운영 완성도. **트레이딩 로직(ORB/FVG/RR) 변경 금지.**
> Reference baseline: freqtrade (github.com/freqtrade/freqtrade)

---

## 0. 이 문서의 목적과 원칙

Casper는 2026년 3월 이후 프로덕션 운영 중이고, 실제 거래·토큰 lockout·cold-start·`.env` IFS 버그 같은 실전 이슈를 여러 차례 겪으며 패치가 누적됐다. 이제 "전략 다듬기"보다 **"운영 시스템으로서 완성도를 올리는 일"**이 한계수익을 주는 단계다. 본 문서는 freqtrade(업계 사실상 표준 open-source 크립토 봇)가 수년간 쌓아 온 시스템 패턴을 **거울**로 삼아, Casper에 도입 가치가 있는 항목만 취사선택한다.

**원칙**
- (P1) **수정은 하지 않는다.** 이 문서는 리뷰·토론을 위한 설계 제안서.
- (P2) **전략 로직 동등성 유지.** ORB/FVG/Pullback/RR 1:2는 건드리지 않는다.
- (P3) **소형 단일 계정 봇 맥락.** freqtrade가 지원하는 "100 페어 동시 거래", "CCXT 200+ 거래소" 같은 범용 기능은 **의도적으로 제외**한다.
- (P4) **각 항목은 도입 비용 대비 실전 이슈 빈도로 평가한다.** 이론적 이상론이 아니라 Casper가 실제로 겪은 사고/로그를 기준으로 가중치를 준다.

---

## 1. 실전 사고 이력에서 출발하는 우선순위

문서 아래의 모든 제안은 이 4건의 실전 사고와 얼마나 직접 맞닿아 있는지로 순위를 매긴다.

| # | 사건 | 근본 원인 | 재발 방지 장치 | 현재 커버리지 |
|---|------|----------|----------------|----------------|
| E1 | 2026-04-13 KIS 토큰 하루 lockout, 거래 0건 | retry 루프가 rate limit 때림 | exponential backoff + 토큰 상태 가시화 | **부분** (backoff는 있음, 가시화 없음) |
| E2 | 2026-04-14 `IFS='=' read` base64 padding 유실 → KIS 500 | bash dotenv 파서 버그 | config 무결성 검증 + 로드 직후 self-test | **부분** (fix 됨, 재발 감지 없음) |
| E3 | 2026-04-13 cold-start HTTP 500 17초 retry 뚫지 못함 | KIS 세션 priming 지연 | warm-up polling | **해결됨** (단, 가시화·알림 없음) |
| E4 | 2026-04-22 장중 루프 정지 → Late join → 거래 0건 | 프로세스 생존/스케줄 정확성 확증 없음 | 헬스체크 + 외부 watchdog + 이상 감지 알림 | **미해결** ← **최대 격차** |

E4가 현재 가장 큰 격차이며, 본 문서에서 가장 많은 분량을 차지한다.

---

## 2. Freqtrade에서 가져올 만한 아이디어 (전체 카탈로그)

각 항목은 다음 5필드로 정리한다:

- **무엇을**: freqtrade가 하는 일 (사실)
- **Casper 현황**: 현재 가진 수준 (Explore 감사 결과)
- **도입 가치**: Casper 맥락에서의 의미
- **비용/위험**: 구현·운영 복잡도
- **판정**: `[도입]` / `[부분도입]` / `[보류]` / `[버림]`

### 2.1 Configuration 레이어

**무엇을 (freqtrade)**
- JSON-Schema로 config 검증. `config.json`에 `$schema` 필드로 에디터 자동완성 + 기동 시 검증.
- 계층 병합: CLI > ENV(`FREQTRADE__` 접두사) > 파일 > strategy 기본값. `show-config`로 병합 결과 확인.
- `/reload_config`로 무재시작 갱신.

**Casper 현황**
- `.env` + `config/strategy_params.json` 2원화. `_validate_params()` (src/utils/config.py:45-60)가 rr_ratio·vix 범위 등 몇 항목만 검증.
- `.env` 로드가 직접 bash 파싱이라 E2 사고를 일으킴 (fix는 `IFS=` + parameter expansion).
- show-config·reload 없음.

**도입 가치**
- **E2 재발 방지 핵심**: config 로드 직후 "정규화된 config 전체를 로그에 덤프 + 민감정보는 길이/해시로만" 출력하면 base64 padding 유실 같은 사건을 **첫 기동 로그**에서 바로 감지 가능.
- Pydantic(이미 파이썬에 있는 표준)으로 전체 스키마를 명시하면 strategy_params.json 편집 실수도 기동 시점에 잡힘.

**비용/위험**
- Pydantic 모델 1~2개 (~80 LOC). 기존 `_validate_params`를 대체.
- 민감정보 출력 로직 실수 시 secret 유출 리스크 → 길이·앞 4자·마지막 2자만 출력하는 규칙 필요.

**판정**: `[도입]` — E2 비용 대비 구현 가벼움.

---

### 2.2 Strategy Interface & 파라미터 분리

**무엇을 (freqtrade)**
- `IStrategy` 추상 클래스. `populate_indicators`/`populate_entry_trend`/`populate_exit_trend` + `INTERFACE_VERSION`.
- `IntParameter`/`DecimalParameter` 선언이 **live 기본값 + hyperopt 탐색공간**을 겸함.
- 벡터화 규칙(`.iloc[-1]` 금지 등)으로 백테스트-라이브 패리티 강제.

**Casper 현황**
- `src/core/strategy.py::scan_for_signal()` 단일 함수, Bot에서 직접 호출. 파라미터는 config에서 주입.
- Long-only 단일 전략. A/B 없음. 백테스트 미구현 (TRADING_MODE=backtest는 선언만).

**도입 가치**
- **소형 봇에는 `IStrategy` 풀스택은 과도.** 그러나 다음 두 개는 값어치 있음:
  - (a) **`Strategy` Protocol** 1개 — `scan(bars, orb, context) -> Optional[TradeSignal]` 시그니처 고정. Bot은 Protocol만 알게 함. 교체·이중검증 여지 확보.
  - (b) **파라미터 = 단일 출처**: 현재 `config/strategy_params.json` + `src/core/strategy.py`의 기본 인자(rr_ratio=2.0 등) 이중화. freqtrade 방식으로 strategy 클래스가 `StrategyParams` dataclass를 소유하고, config 로더가 그걸 채움.

**비용/위험**
- Protocol 도입은 코드 3~5곳 refactor. 테스트 깨질 위험 있음.

**판정**: `[부분도입]` — (a) Protocol은 하되, 하위호환 래퍼 둘 것. (b) 파라미터 이중화 제거는 별도 PR.

---

### 2.3 Data Pipeline & OHLCV 저장소

**무엇을 (freqtrade)**
- Feather/Parquet으로 OHLCV 로컬 저장. `convert-data`, `download-data` CLI.
- SQLAlchemy로 trades·orders·pairlocks·wallet_history 영속화. 마이그레이션(`migrations.py`).

**Casper 현황**
- OHLCV 영속화 없음. 매 틱 실시간 fetch (KIS → yfinance 폴백).
- trades는 JSON 파일. 스키마 버저닝 없음.

**도입 가치**
- Casper 거래량 = 일 1건 수준. OHLCV 저장은 **백테스트를 붙일 때** 의미 생김. 지금 당장은 근거 부족.
- 다만 **"당일 분봉 스냅샷"**을 거래 성사 시 함께 저장하면 포스트모템(왜 시그널이 거기서 났나)에 결정적. freqtrade보다 훨씬 가벼운 버전(거래 1건당 `data/snapshots/YYYY-MM-DD_TQQQ.parquet`)으로 가능.

**비용/위험**
- parquet 쓰기 가벼움, pandas만 추가.

**판정**: `[부분도입]` — 일 1건짜리 "거래 스냅샷 보존"만 채택. 상시 OHLCV 저장은 `[보류]`.

---

### 2.4 Order Lifecycle 상태머신

**무엇을 (freqtrade)**
- orders 테이블에 명시적 상태: `open → filled / canceled / partial`. 파셜 필 누적.
- `stoploss_on_exchange`, `position_adjustment_enable` (DCA) 등 훅.
- 거래소별 quirks는 `_ft_has_params` dict로 격리.

**Casper 현황**
- `src/api/kis_order.py`: market 주문 후 `get_us_holdings()` 폴링으로 fill 감지. partial fill 로직 없음.
- `_reconcile_fill` 관련 코드는 있지만 (로그에 `RECONCILE: No executions found from broker` 있음) 브로커가 체결 내역을 주지 않는 케이스 방어 미흡.

**도입 가치**
- Casper는 하루 1건, market 주문 한 번이라 **상태머신 풀구현은 과도**. 다만 아래 3개는 누락:
  - (a) **명시적 order 객체**: `Order(id, side, qty, submit_ts, fill_ts, fill_price, status)` dataclass로 메모리에 쥐고, 매 틱 상태 업데이트. 현재 bot.py에 산재한 주문 관련 변수가 정리됨.
  - (b) **Fill 타임아웃 정책**: market이 X초 내 체결 확인 안 되면 `get_us_orders()`로 broker 상태 조회 → 대기/재조회/수동취소. 지금은 "pending → POSITION_OPEN으로 일단 전이"해서 혼란 여지.
  - (c) **주문 id ↔ 체결 id 매핑 로그**: 추후 세무·감사용.

**비용/위험**
- (a) refactor 3~4시간. 테스트 추가 필요. (b) 민감 — 잘못 구현하면 주문 이중 전송 가능.

**판정**: `[부분도입]` — (a)(c) 우선. (b)는 별도 리뷰 필요 (market 주문이라 KIS에서 몇 초 내 거의 다 잡힘, 실제 사례 증거 먼저 수집).

---

### 2.5 Risk & Protections 플러그인화

**무엇을 (freqtrade)**
- `StoplossGuard` (최근 N회 손절 시 락), `MaxDrawdown`, `LowProfitPairs`, `CooldownPeriod` — 체인처럼 붙이고 뗀다.
- 각 protection은 hyperopt 가능.

**Casper 현황**
- `src/core/risk.py`에 VIX 필터·트렌드 필터·3연패/주간3%DD 서킷브레이커·ORB width 필터·휴일 필터 모두 **하드코딩**. 개별 on/off 토글 없음. 파라미터는 config에 있음.

**도입 가치**
- 단일 전략에 플러그인 체인까지는 과함. 그러나 **"개별 protection을 log 한 줄로 명시"**는 큰 차이를 만든다:
  - 현재: "signal 없음" 한 줄 → 왜인지 모름.
  - 제안: `[FILTER] VIX=19.4 PASS`, `[FILTER] ORB_WIDTH=0.59 / ADR 1.1=0.53 → WIDE, SKIP` 식의 per-filter verdict.
- 이건 구조를 바꾸지 않고도 가능 — 각 check 함수가 `(bool, reason: str)` 반환하도록 시그니처만 통일.

**비용/위험**
- 코드 5~7곳 시그니처 통일. 기존 호출자 업데이트. 테스트 영향 중간.

**판정**: `[도입]` — E4 포스트모템 시간 절약, 운영 가시성 급상승.

---

### 2.6 Observability — **Casper의 최대 격차**

**무엇을 (freqtrade)**
- **Telegram 명령**: `/status`, `/count`, `/profit`, `/daily`, `/weekly`, `/monthly`, `/performance`, `/balance`, `/forceexit`, `/stop`, `/reload_config`, `/locks` 등.
- **REST API + JWT**: `/api/v1/*`, WebSocket 스트림. FreqUI Vue SPA가 이걸 소비.
- **Webhook 이벤트**: entry/entry_fill/entry_cancel/exit/exit_fill/exit_cancel/status, retry 내장.

**Casper 현황**
- Telegram은 단방향 알림만: `notify_entry/exit/skip/daily_summary/error/status`. **명령 수신 없음.**
- REST API 없음. `run_casper.sh status`가 유일한 외부 인터페이스.
- 로그는 `logs/app/casper_YYYY-MM-DD.log` 일자 파일, 로테이션 없음 (파일명만 날짜).

**도입 가치 — E4 관점에서 최우선**
- (a) **Heartbeat**: 매 루프 말미에 `/tmp/casper.heartbeat` 파일 mtime 업데이트. 외부 cron/launchd가 60초 이상 안 바뀌면 알림. **E4가 이거 하나만 있었어도 22:45에 이상 감지됐음.**
- (b) **`/status` 등 Telegram 명령 수신**: python-telegram-bot의 `CommandHandler`로 `/status`, `/today`, `/halt` 3개만 구현해도 운영 부담 급감. 전체 채택 아니라 **미니멀 세트**.
- (c) **구조화 로그(JSON Lines)**: 병렬로 띄우되 기존 텍스트 로그 유지. 후일 grep·검색·Obsidian 연동 쉬움.
- (d) **상태 스냅샷 JSON**: 현재 상태(`bot_state.json`)를 5초마다 덮어쓰고, `run_casper.sh status`가 그걸 읽도록. 지금은 상태 조회 시 trades 누적만 보여줌.

**비용/위험**
- (a) 3줄. (b) ~60 LOC. (c) 로거 핸들러 1개 추가. (d) ~20 LOC.
- 위험은 (b)뿐 — 명령 핸들러가 잘못 동작하면 운영 중 예외. 읽기 전용 명령만으로 시작.

**판정**: `[도입]` — 전부. 가장 ROI 높은 묶음.

---

### 2.7 Persistence 레이어

**무엇을 (freqtrade)**
- SQLite 기본, Postgres 옵션. 스키마 마이그레이션, 백업은 파일 복사.
- `custom_data` 테이블로 전략이 자유롭게 key-value 쓰기.

**Casper 현황**
- JSON 3종: `trades/trades_YYYY.json` (append-only, atomic write), `position_state.json` (5초마다 덮어쓰기, 크래시 복구용), `config/token.json`.
- `backup_YYYYMMDD_HHMMSS.json` 수동 백업 흔적 있음. 자동화 없음.
- 두 봇 인스턴스 동시 실행 시 lock 없음 (현재 `.casper.pid`로 막음).

**도입 가치**
- **DB 마이그레이션은 보류**. 연 1건 수준에서 JSON 5KB 파일이 SQLite를 이길 이유 없음. 다만:
  - (a) **schema_version 필드** 추가: 2026년 중반 이후 스키마가 이미 한 번 확장됨(broker settlement fields). 다음 변경 시 legacy 파일 자동 마이그레이션 훅이 없어 위험.
  - (b) **자동 백업**: 매일 새 날짜 진입 시 `trades_YYYY.json → trades_YYYY.backup_{today}.json` 1회 복사. 7일 retention.

**비용/위험**
- (a)(b) 합쳐서 ~30 LOC. 위험 매우 낮음.

**판정**: `[도입]`. DB 전환은 `[보류]` (백테스트 붙일 때 재평가).

---

### 2.8 Testing / Backtest

**무엇을 (freqtrade)**
- 백테스트 엔진이 코어. `backtesting --timeframe-detail`로 캔들 내부 움직임 replay.
- Hyperopt 프레임워크, walk-forward.
- `tests/`가 소스 트리 미러. online-gated 테스트는 `exchange_online/`으로 분리.

**Casper 현황**
- 301개 테스트. `conftest.py`의 `_isolate_trades_and_state`가 autouse로 프로덕션 파일 오염 차단 — 이미 매우 견고.
- **백테스트 엔진 없음**. TRADING_MODE=backtest는 선언만.

**도입 가치**
- **백테스트는 전략 변경 시에만 가치 생김**. 원칙 P2(전략 불변)로 지금은 우선순위 낮음. 대신:
  - (a) **"어제 하루 재생" 미니 백테스터**: 저장된 5분봉만 있으면 `scan_for_signal`을 오프라인에서 돌려 결과 재현 가능. E4 같은 포스트모템·디버깅용. 완전한 백테스트 아님.
  - (b) **Regression pack**: 과거 체결된 6건을 고정 fixture로 두고 "동일 입력 → 동일 시그널" 회귀 테스트. 전략 파라미터 실수 방지.

**비용/위험**
- (a) 2.3의 "거래 스냅샷 보존"과 짝. ~100 LOC. (b) fixture 6개 + 테스트 1개.

**판정**: `[부분도입]` — (a)(b)만. 풀 백테스트는 `[보류]`.

---

### 2.9 Deployment / Ops

**무엇을 (freqtrade)**
- Docker + compose가 정석. `restart: unless-stopped`로 auto-restart. `/api/v1/ping` healthcheck. DB 마이그레이션은 컨테이너 기동 시 자동.

**Casper 현황**
- `run_casper.sh start|daemon|stop`. nohup daemon. `.casper.pid`로 중복 실행 방지.
- launchd/systemd 없음. watchdog 없음 — **E4의 직접 원인**.
- cold-start warm-up (`KISClient.warm_up`) 90s polling은 이미 잘 구현됨.
- 토큰 backoff schedule (`_BACKOFF_SCHEDULE`)도 이미 구현 — E1 대응 완료.

**도입 가치**
- **Docker화는 현 프로젝트에 과도**. macOS에서 launchd로 운영 중이므로 방향 일치시키는 편이 낫다.
- (a) **launchd plist**: `com.casper.bot.plist` with `KeepAlive={SuccessfulExit=false}` + `StartInterval` 체크. `stderr/stdout`을 별도 파일로. 22:30 이전 자동 기동 가능.
- (b) **Heartbeat watchdog**: `com.casper.watchdog.plist`를 StartInterval=60으로 돌려 heartbeat 파일 mtime 확인, 2분 이상 stale이면 bot 재시작 + Telegram 알림. **E4 직접 해결.**
- (c) **Pre-flight check subcommand**: `run_casper.sh doctor` — KIS 토큰 유효성, `.env` 필드 길이, yfinance 응답, 시스템 타임존, 디스크 공간을 한 번에 검사. 기동 전 수동 호출 or launchd 내 RunAtLoad.

**비용/위험**
- (a)(b) 각 plist 1개, ~40줄. 테스트는 macOS 실기기 필요.
- (c) shell 스크립트 1개, ~80줄.

**판정**: `[도입]` — (a)(b)(c) 전부. E4 재발 방지의 핵심.

---

### 2.10 기타 엣지 기능 (freqtrade가 갖지만 Casper에 불필요한 것들)

명시적으로 **버린다**: 나중에 "왜 안 했냐"가 되지 않기 위함.

- **FreqAI (ML 파이프라인)**: `[버림]`. 원칙 P2.
- **CCXT 멀티 거래소**: `[버림]`. KIS 단일 브로커.
- **Pairlist 플러그인**: `[버림]`. TQQQ/SQQQ 2종 고정.
- **External Message Consumer (producer/follower)**: `[버림]`. 단일 계정.
- **FreqUI 웹 대시보드**: `[보류]`. 009_dashboard가 별도 존재 — 연동으로 대체 가능할 때 재평가.
- **Leverage / can_short**: `[버림]`. Long only.
- **Webhook retries**: `[보류]`. Telegram 명령 먼저.

---

## 3. 통합 제안 — Phase 구분

각 phase는 **독립적으로 릴리스 가능**하게 자른다. 우선순위는 **실전 사고 ROI** 순.

### Phase A — 운영 가시성 & watchdog (E4 대응, **최우선**)
1. Heartbeat 파일 업데이트 (bot.py 메인 루프 끝) ← 2.6(a)
2. launchd plist 2개 (bot + watchdog) ← 2.9(a)(b)
3. `run_casper.sh doctor` ← 2.9(c)
4. Telegram `/status` `/today` `/halt` 3개 ← 2.6(b)
5. 상태 스냅샷 `data/bot_state.json` + `run_casper.sh status` 개선 ← 2.6(d)
6. Filter verdict 구조화 로그 ← 2.5

→ 예상 총량: ~300 LOC + plist 2개. 1~2일.

### Phase B — Config 견고화 (E2 재발 방지)
1. Pydantic 기반 config 스키마 ← 2.1
2. 기동 로그에 정규화된 config 덤프(민감정보 마스킹) ← 2.1
3. `schema_version` 필드 도입 + 자동 백업 ← 2.7

→ 예상 총량: ~150 LOC. 0.5일.

### Phase C — 포스트모템 인프라
1. 거래 스냅샷 parquet 저장 ← 2.3
2. "하루 재생" 미니 백테스터 ← 2.8(a)
3. 6건 fixture 회귀 테스트 ← 2.8(b)
4. JSON Lines 구조화 로그 ← 2.6(c)

→ 예상 총량: ~300 LOC. 1일.

### Phase D — Order Lifecycle 정리
1. `Order` dataclass + 상태 전이 ← 2.4(a)
2. 주문-체결 id 매핑 persist ← 2.4(c)

→ 예상 총량: ~200 LOC + 기존 코드 refactor. 1일. **Phase A/B 검증 후** 진행.

### Phase E (미확정, 별도 리뷰 필요)
- Strategy Protocol ← 2.2(a)
- Fill 타임아웃 정책 ← 2.4(b) — 실제 문제 증거 수집 후
- DB 전환 ← 2.7 최종형 — 백테스트 도입 시 재평가

---

## 4. 리뷰 질문 (토론용)

문서를 읽고 다음에 대해 의사결정해 주세요:

1. **Phase A의 launchd watchdog**은 실기기에서 검증이 필요하다. 개발 환경에서 "bot이 헬스체크 실패 → watchdog이 살리는" 시나리오를 어떻게 안전하게 시뮬레이션할지?
2. **Telegram `/halt` 명령**은 거래 중단을 의미. 현재 상태머신(`DONE_TODAY`)에 외부 강제 전이 path를 넣어야 한다. 이게 기존 상태머신 불변식을 깨지 않는지 한 번 더 보고 싶음.
3. **Pydantic 도입**은 파이썬 의존성 1개 추가. 현재 의존성(`requests`, `pandas`, `yfinance`, `python-dotenv`, `python-telegram-bot`) 외에 Pydantic v2를 추가하는 것이 허용 범위인지?
4. **거래 스냅샷 parquet**은 pyarrow 의존성을 부른다. 대안은 DataFrame.to_json(lines=True) — 용량은 약 3~5배. 선택?
5. **Filter verdict 로그**를 INFO 레벨로 전부 낼 것인지, DEBUG로 숨길 것인지? Post-mortem에 필요하나 평상시 로그가 장황해짐. 제안: INFO지만 한 줄에 모든 필터 verdict를 묶어 출력.
6. **보류 항목** 중 우선순위 올릴 것이 있는지? (특히 2.4(b) fill 타임아웃)

---

## 5. 부록 — 조사 근거

### Casper 현황 감사 (파일 인용)
- Config: `src/utils/config.py:17-42`, `src/utils/config.py:45-60`, `run_casper.sh:28-62`
- 전략: `src/core/strategy.py:34-100`, `src/core/strategy.py:19-31`
- 데이터: `src/data/market_data.py:99-116`, `src/data/market_data.py:119`, `src/data/market_data.py:53-84`
- 주문: `src/api/kis_order.py:32-81`, `src/api/kis_order.py:104-150`
- Risk: `src/core/risk.py:32-53`, `src/core/risk.py:56-90`, `src/core/risk.py:93-170`, `src/core/orb.py:64-85`, `src/utils/time_utils.py:59-66`
- 상태·영속화: `src/bot.py:151-177`, `src/bot.py:268-286`, `src/data/trade_store.py:54-107`
- 테스트: `tests/conftest.py:8-60`

### 실전 사고 근거
- E1: `CLAUDE.md` "KIS 토큰/AppKey 디버깅", `_BACKOFF_SCHEDULE`
- E2: `CLAUDE.md` ".env 로드 버그"
- E3: `CLAUDE.md` "KIS cold-start lockout 대응"
- E4: `logs/app/casper_2026-04-19.log:63-76` (`Late join` 기록)

### Freqtrade 참조
- https://www.freqtrade.io/en/stable/configuration/
- https://www.freqtrade.io/en/stable/strategy-customization/
- https://www.freqtrade.io/en/stable/plugins/ (protections)
- https://www.freqtrade.io/en/stable/telegram-usage/
- https://www.freqtrade.io/en/stable/rest-api/
- https://www.freqtrade.io/en/stable/webhook-config/
- Source: `freqtrade/persistence/trade_model.py`, `freqtrade/rpc/telegram.py`, `freqtrade/plugins/protections/`, `freqtrade/configuration/`

---

## 6. 변경 이력

- 2026-04-23: 초안 작성 (리뷰 대기)
