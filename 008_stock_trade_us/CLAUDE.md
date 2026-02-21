# CLAUDE.md - 미국 주식 퀀트 자동매매

007_stock_trade 기반의 미국 주식 버전. KIS Open API로 S&P500 멀티팩터 자동매매.

## 실행

```bash
./run_quant.sh daemon          # 통합 데몬 (권장)
./run_quant.sh screen          # 스크리닝
./run_quant.sh backtest        # 백테스트
```

## 핵심 정보

| 항목 | 값 |
|------|-----|
| 전략 | 모멘텀(20%) + 단기모멘텀(10%) + 저변동성(50%) |
| 유니버스 | S&P500 |
| 목표 종목 | 15개 |
| 기반 | 007_stock_trade와 동일 아키텍처 |

## 미국 전용 모듈

| 파일 | 역할 |
|------|------|
| `src/us_quant_engine.py` | 미국 주식 전용 퀀트 엔진 |
| `src/strategy/us_screener.py` | 미국 주식 스크리너 |
| `src/strategy/us_universe.py` | S&P500 유니버스 |
| `src/api/kis_us_client.py` | 미국 주식 전용 KIS 클라이언트 |

## 텔레그램 명령어

007_stock_trade와 동일. `/start_trading`, `/stop_trading`, `/status`, `/positions`, `/run_screening`, `/set_target N` 등.

## 환경변수 (.env)

```bash
KIS_APP_KEY=
KIS_APP_SECRET=
KIS_ACCOUNT_NO=12345678-01
TRADING_MODE=VIRTUAL
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

## 상세 문서

- [아키텍처](docs/ARCHITECTURE.md) - 프로젝트 구조, 핵심 모듈, 데이터 흐름, 설정
- [텔레그램 명령어](docs/COMMANDS.md) - 전체 명령어 목록 및 사용법
- [KIS API 정보](docs/get_api_information.md) - KIS Open API 레퍼런스
- [멀티팩터 전략](docs/strategy/multi_factor_strategy.md) - 팩터 설계 상세
- [퀀트 트레이딩 가이드](docs/strategy/quant_trading_guide.md) - 전략 운영 가이드
