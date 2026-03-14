# 012_stock_dashboard - Global Market Dashboard

Bloomberg-style 실시간 글로벌 시장 대시보드. 6x4 타일 그리드에 지수, 원자재, 환율, 뉴스를 표시.

## Quick Start

```bash
cd 012_stock_dashboard
source venv/bin/activate
./run_watchdog.sh           # 권장: 헬스체크 + 자동 재시작 (http://localhost:5002)
./run_dashboard.sh          # 단순 실행 (디버깅용)
```

## 환경변수 (.env)

| Key | 용도 | 필수 |
|-----|------|------|
| `GEMINI_API_KEY` | 뉴스 AI 한국어 번역/요약 | Yes |
| `FINNHUB_API_KEY` | 실시간 뉴스 + 시세 보강 | No |
| `DASHBOARD_PORT` | 서버 포트 (기본 5002) | No |

## 구조

```
012_stock_dashboard/
├── app.py                    # FastAPI 메인 (라우트, WebSocket, 워커, 로그 설정)
├── config.py                 # 타일 정의, 티커, RSS URL, 업데이트 주기
├── run_watchdog.sh           # 헬스체크(/health) + 자동 재시작 (30s 간격, 3회 실패 시 재시작)
├── logs/                     # dashboard.log (7일 로테이션) + uvicorn.log
├── workers/
│   ├── base.py               # BaseWorker (async loop, 에러 백오프)
│   ├── market_worker.py      # 지수/원자재/환율/스파크라인 (yfinance)
│   ├── news_worker.py        # RSS + Finnhub 수집 → AI 요약 (2단계)
│   ├── sentiment_worker.py   # Fear & Greed, Market Breadth
│   ├── sector_worker.py      # S&P 500 섹터 히트맵
│   └── alert_worker.py       # 급등/급락 감지 (US+KR, 1h ±3%)
├── data_sources/
│   ├── yfinance_adapter.py   # yfinance 비동기 래퍼 + 캐싱
│   ├── rss_adapter.py        # 다국어 RSS 파서 (EN/KR/JP/CN)
│   ├── ai_summarizer.py      # Gemini 뉴스 한국어 번역 (google-genai SDK)
│   ├── finnhub_adapter.py    # Finnhub REST (뉴스/시세)
│   ├── fear_greed.py         # CNN Fear & Greed 스크래퍼
│   └── market_calendar.py    # 시장 시간대 + US 공휴일 (US/EU/JP/CN/KR)
├── tiles/
│   ├── tile_manager.py       # DataStore + WebSocket broadcast
│   └── dynamic_rotator.py    # 뉴스 타일 FIFO 로테이션
└── templates/
    └── dashboard.html        # 단일 HTML (CSS Grid + TradingView + WS)
```

## 타일 레이아웃 (6x4 Grid)

| Row | Col 1 | Col 2 | Col 3 | Col 4 | Col 5 | Col 6 |
|-----|-------|-------|-------|-------|-------|-------|
| 1   | S&P 500 (2col) | | NASDAQ (2col) | | Dow Jones (2col) | |
| 2   | VIX | 10Y Yield | DXY | Gold | WTI Oil | Bitcoin |
| 3   | Sectors (2col) | | Top Movers | Fear & Greed | Europe | Asia |
| 4   | FX Rates | Mkt Breadth | Yield Curve | Watchlist | Commodities | News Feed |

## 핵심 아키텍처

- **데이터 흐름**: Workers → DataStore → WebSocket → Browser
- **공유 어댑터**: 모든 Worker가 단일 YFinanceAdapter 인스턴스 공유 (SQLite 캐시 충돌 방지)
- **업데이트 주기**: T1(30s) 주요지수, T2(60s) VIX/환율/Yield/Watchlist/Commodities, T3(120s) 섹터, T4(600s) 뉴스, T5(600s) 센티먼트
- **뉴스 2단계**: Phase A = 원문 즉시 표시 → Phase B = Gemini AI 한국어 번역 비동기 교체
- **뉴스 Compact**: 4개 뉴스를 1타일 2x2 그리드에 통합 표시 (FIFO 로테이션)
- **Gemini 절약**: 한국어(KR) 기사는 Gemini 스킵 (원문 유지), EN/JP/CN만 번역 호출
- **yfinance**: v1.2.0+ MultiIndex `("Close", ticker)` 형식. 크립토/주식 별도 fetch 필요. 개별 티커 fallback + LKG 캐시
- **Market Tape**: Header 하단 상시 스크롤 (12종목: 지수/VIX/환율/원자재/BTC/FX), 기존 타일 데이터 재활용, 호버 시 일시정지
- **장외 선물 전환**: Row 1 지수(^GSPC/^IXIC/^DJI)는 장외 시간에 선물(ES=F/NQ=F/YM=F)로 자동 전환, "FUTURES" 배지 표시
- **차트**: TradingView Lightweight Charts v4 (Row 1), Canvas 스파크라인 (Row 2), Canvas Yield Curve (Row 4)
- **Alert 스캔**: 120s 주기, Phase1 일간 |±2%| 필터 → Phase2 후보만 인트라데이 5m 캔들 → |1h ±3%| 감지 → Ticker Tape + Movers 배지
- **Alert 대상**: US S&P 500 (45종목) + KR KOSPI 대형주 (15종목), 장 개장 시간에만 스캔
- **Watchlist**: 고정 5종목 (O, SCHD, QQQ, GOOGL, SPY) + 동적 3종목 (일간 변동률 상위, 5분 로테이션)

## 주의사항

- 장외 시간: 전체 5분 간격으로 통합 (OFF_HOURS_INTERVAL)
- CNN Fear & Greed: `User-Agent` + `Referer` 헤더 필수 (없으면 HTTP 418)
- Gemini SDK: `google-genai` 패키지 사용 (구 `google-generativeai`는 deprecated)
- Gemini Free Tier: gemini-2.5-flash-lite 사용, 10분 주기 + KR 스킵으로 쿼타 절약
- VIX(^VIX): 인트라데이 스파크라인 미지원 (yfinance 비호환), 가격/변동률만 표시
- Port 5002 사용 (009_dashboard 5001과 충돌 회피)
