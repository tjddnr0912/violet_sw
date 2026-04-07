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
| 안전장치 | 크래시 복구, SIGTERM, 포지션 상한, 오버나잇 방지, 잔고 동기화 |
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

## 상세 문서

- [코드 리뷰](docs/CODE_REVIEW.md)
- [설계 스펙](docs/superpowers/specs/2026-04-02-casper-bot-design.md)
- [전략 리뷰](docs/strategy/STRATEGY_REVIEW.md)
- [실행 계획](docs/strategy/EXECUTION_PLAN.md)
