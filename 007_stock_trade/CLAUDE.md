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
├── quant_engine.py           # 자동매매 엔진
├── api/kis_client.py         # KIS API 클라이언트
├── core/system_controller.py # 원격 제어 (싱글톤)
├── scheduler/auto_manager.py # 월간 모니터링, 반기 최적화
├── telegram/bot.py           # 텔레그램 봇 (20+ 명령어)
└── strategy/quant/           # 팩터, 스크리너, 리스크
scripts/run_daemon.py         # 통합 데몬
config/
├── optimal_weights.json      # 팩터 가중치
└── system_config.json        # 시스템 설정
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
- 해결: 자동 150~200ms 딜레이 적용됨 (2026-01)

### 텔레그램 네트워크 에러 (httpx.ConnectError)
- 원인: 네트워크 연결 문제 (토큰 충돌 아님)
- 해결: 자동 복구됨 - 최대 10회 재시도 + 스레드 자동 재시작 (2026-01)

### 목표 종목 미달
- 스크리닝 결과 < 목표: 필터 조건 미충족
- 매수 실패: 다음 장 09:00 재시도 (최대 3회)
- 텔레그램으로 미달 알림 발송 (2026-01)

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

### 콜백 등록
```python
controller = get_controller()
controller.register_callback('on_screening', engine.run_screening)
```

## 봇 운영 구조

| 봇 | 실행 방식 | 토큰 |
|----|----------|------|
| 주식봇 (007_stock_trade) | 수동 터미널 | 별도 .env |
| 암호화폐봇 (005_money) | start_all_bots.sh | 별도 .env |

각 봇은 독립 터미널/토큰 사용 → 토큰 충돌 없음.
