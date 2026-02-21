# Architecture

## 프로젝트 구조

```
008_stock_trade_us/
├── src/
│   ├── quant_engine.py          # 퀀트 자동매매 엔진 (기본)
│   ├── us_quant_engine.py       # 미국 주식 전용 퀀트 엔진
│   ├── engine.py                # 엔진 기본 클래스
│   ├── api/
│   │   ├── kis_client.py        # KIS API 기본 클라이언트
│   │   ├── kis_us_client.py     # 미국 주식 전용 클라이언트
│   │   ├── kis_auth.py          # 인증 모듈
│   │   ├── kis_quant.py         # 퀀트용 확장
│   │   └── kis_websocket.py     # WebSocket 실시간 시세
│   ├── core/
│   │   └── system_controller.py # 시스템 원격 제어 (싱글톤)
│   ├── scheduler/
│   │   └── auto_manager.py      # 월간 모니터링, 반기 최적화
│   ├── strategy/
│   │   ├── us_screener.py       # 미국 주식 스크리너
│   │   ├── us_universe.py       # S&P500 유니버스
│   │   └── quant/               # 팩터, 스크리너, 리스크, 백테스트
│   ├── telegram/
│   │   └── bot.py               # 텔레그램 봇 (알림 + 명령어)
│   └── utils/
├── scripts/
│   ├── run_daemon.py            # 통합 데몬
│   └── run_backtest.py          # 백테스트
├── config/
│   ├── optimal_weights.json     # 팩터 가중치
│   ├── system_config.json       # 시스템 설정
│   └── token.json               # KIS API 토큰
├── data/quant/                  # 상태/포지션 데이터
├── logs/                        # 로그 파일
└── run_quant.sh                 # 메인 실행 스크립트
```

## 핵심 모듈

### SystemController (`src/core/system_controller.py`)

텔레그램 원격 제어 싱글톤.

```python
from src.core import get_controller
controller = get_controller()
controller.start_trading()
controller.set_target_count(15)
controller.register_callback('on_screening', engine.run_screening)
```

시스템 상태: `STOPPED`, `RUNNING`, `PAUSED`, `EMERGENCY_STOP`

### AutoStrategyManager (`src/scheduler/auto_manager.py`)

- 월간 모니터링: 매월 1일 09:00
- 반기 최적화: 1월, 7월 첫째주
- 가중치 자동 업데이트

## 데이터 흐름

```
1. 유니버스 구성 (S&P500)
2. 가격/재무 데이터 수집 (KIS API)
3. 팩터 점수 계산 (모멘텀 + 저변동성)
4. 종합 점수 순위화
5. 섹터 분산 적용
6. 상위 15개 선정
7. 리밸런싱 계산
8. 주문 실행 (Dry-run 해제 시)
9. 텔레그램 알림
```

## 팩터 가중치 (config/optimal_weights.json)

```json
{
  "momentum_weight": 0.20,
  "short_mom_weight": 0.10,
  "volatility_weight": 0.50,
  "volume_weight": 0.00,
  "target_count": 15,
  "auto_update": true
}
```

## 설정 동기화

```
Telegram → SystemController → system_config.json → QuantEngine
```

데몬 재시작 후에도 설정 유지.

## 일일 스케줄

| 시간 | 동작 |
|------|------|
| 08:30 | 장 전 스크리닝 |
| 09:00 | 주문 실행 |
| 5분마다 | 포지션 모니터링 (손절 -7% / 익절 +10%) |
| 15:20 | 일일 리포트 |
