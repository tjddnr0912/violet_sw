# 014_casper - 프로젝트 폴더 구조

> 007_stock_trade / 008_stock_trade_us 패턴 기반, 캐스퍼 전략 특성에 맞게 확장

---

## 전체 구조

```
014_casper/
│
├── .env                          # API 키, 시크릿 (git 제외)
├── .env.example                  # .env 템플릿 (git 포함)
├── .gitignore
├── .venv/                        # Python 가상환경 (git 제외)
├── main.py                       # 엔트리포인트 (모드 선택: backtest / scan / paper / live)
├── run_casper.sh                 # 실행 쉘 스크립트
├── requirements.txt              # Python 의존성
├── CLAUDE.md                     # Claude Code 프로젝트 컨텍스트
│
│
│ ── docs/                         # 문서 (전략, 이론, 결과, 운영)
│   │
│   ├── strategy/                  # 전략 문서
│   │   ├── STRATEGY_REVIEW.md     # 전략 검토 및 분석 (현재 최상위에서 이동)
│   │   ├── EXECUTION_PLAN.md      # 실행 계획서 (현재 최상위에서 이동)
│   │   ├── THEORY.md              # ORB + FVG 이론 정립
│   │   ├── STOCK_SELECTION.md     # 종목 선택 기준
│   │   └── TRADING_RULES.md       # 최종 매매 규칙서 (전략 완성 후)
│   │
│   ├── research/                  # 리서치 자료
│   │   ├── orb_literature.md      # ORB 관련 논문/서적 요약
│   │   ├── fvg_analysis.md        # FVG 실증 자료 정리
│   │   ├── market_microstructure.md # 시장 미시구조 (유동성, 스프레드)
│   │   └── references.md          # 참고 자료 링크 모음
│   │
│   ├── results/                   # 분석 결과
│   │   ├── BACKTEST_RESULTS.md    # 백테스트 종합 결과
│   │   ├── PARAMETER_SENSITIVITY.md # 파라미터 민감도 분석
│   │   ├── REGIME_ANALYSIS.md     # 시장 국면별 분석
│   │   └── PAPER_TRADING_LOG.md   # 페이퍼 트레이딩 기록
│   │
│   ├── ops/                       # 운영 문서
│   │   ├── DAILY_ROUTINE.md       # 매일 실행 루틴
│   │   ├── TROUBLESHOOTING.md     # 에러 대응
│   │   └── CHANGELOG.md           # 변경 이력
│   │
│   └── images/                    # 문서용 이미지, 차트 캡처
│       └── .gitkeep
│
│
│ ── config/                       # 설정 파일 (코드가 읽는 정적 설정)
│   │
│   ├── strategy_params.json       # 전략 파라미터 (ORB 시간, R:R, 필터 임계값)
│   ├── scanner_filters.json       # 종목 스캐너 필터 기준
│   ├── risk_params.json           # 리스크 관리 (포지션 사이징, 최대 손실)
│   ├── symbols.json               # 관심 종목 리스트 (ETF + 개별주)
│   └── market_calendar.json       # FOMC/CPI 등 매크로 이벤트 일정
│
│
│ ── src/                          # 메인 소스 코드 (트레이딩 시스템)
│   │
│   ├── __init__.py
│   │
│   ├── core/                      # 핵심 트레이딩 로직
│   │   ├── __init__.py
│   │   ├── strategy.py            # 전략 엔진 (진입/청산 판단)
│   │   ├── indicators.py          # 지표 계산 (ORB, FVG, Market Bias)
│   │   ├── position.py            # 포지션 관리 (사이징, 손절/익절 추적)
│   │   └── risk.py                # 리스크 관리 (Circuit Breaker, 일일 한도)
│   │
│   ├── scanner/                   # 종목 스캐너
│   │   ├── __init__.py
│   │   ├── premarket.py           # Pre-market 스캐너 (갭, 볼륨, RVOL)
│   │   ├── filters.py             # 필터 체인 (유동성, 변동성, 카탈리스트)
│   │   └── watchlist.py           # 당일 워치리스트 생성
│   │
│   ├── data/                      # 데이터 수집/처리
│   │   ├── __init__.py
│   │   ├── loader.py              # 데이터 다운로드 (Alpaca, yfinance)
│   │   ├── preprocessor.py        # 전처리 (정규화, 갭 보정, 분할 조정)
│   │   └── cache.py               # 로컬 캐시 관리
│   │
│   ├── api/                       # 외부 API 연동
│   │   ├── __init__.py
│   │   ├── alpaca_client.py       # Alpaca API (데이터 + 주문)
│   │   └── market_data.py         # 시장 데이터 통합 인터페이스
│   │
│   ├── telegram/                  # 텔레그램 알림
│   │   ├── __init__.py
│   │   └── notifier.py            # 시그널/결과 알림
│   │
│   └── utils/                     # 공통 유틸리티
│       ├── __init__.py
│       ├── logger.py              # 로깅 설정 (파일 + 콘솔 + 텔레그램)
│       ├── time_utils.py          # 시간대 변환 (ET, KST), 장 시간 판별
│       └── config_loader.py       # config/ JSON 로더
│
│
│ ── backtest/                     # 검증 코드 (백테스팅 전용)
│   │
│   ├── __init__.py
│   │
│   ├── engine/                    # 백테스팅 엔진
│   │   ├── __init__.py
│   │   ├── backtester.py          # VectorBT 기반 메인 엔진
│   │   ├── cost_model.py          # 수수료 + 슬리피지 모델
│   │   └── simulator.py           # Monte Carlo 시뮬레이션
│   │
│   ├── analysis/                  # 성과 분석
│   │   ├── __init__.py
│   │   ├── metrics.py             # 성과 지표 (승률, PF, Sharpe, MDD 등)
│   │   ├── regime.py              # 시장 국면별 분석 (VIX, 추세, 요일)
│   │   ├── comparison.py          # 벤치마크 비교 (B&H, Random, ORB-only)
│   │   └── walk_forward.py        # Walk-Forward Analysis
│   │
│   ├── optimization/              # 파라미터 최적화
│   │   ├── __init__.py
│   │   ├── param_search.py        # 그리드/랜덤 서치
│   │   └── sensitivity.py         # 파라미터 민감도 분석
│   │
│   ├── visualization/             # 시각화
│   │   ├── __init__.py
│   │   ├── charts.py              # 수익 곡선, 드로다운, 히트맵
│   │   └── trade_plots.py         # 개별 거래 차트 (진입/청산 마킹)
│   │
│   └── run_backtest.py            # 백테스트 실행 스크립트
│
│
│ ── data/                         # 데이터 저장소 (git 제외, 용량 큼)
│   │
│   ├── raw/                       # 원시 데이터 (API에서 다운로드한 그대로)
│   │   ├── ohlcv/                 # OHLCV 봉 데이터
│   │   │   ├── 1min/             # 1분봉 (spy_1min_2021.parquet ...)
│   │   │   └── 5min/             # 5분봉
│   │   ├── fundamentals/          # 기본적 데이터 (시가총액, float 등)
│   │   └── market/                # 시장 데이터 (VIX, SPY daily 등)
│   │
│   ├── processed/                 # 전처리 완료 데이터
│   │   ├── features/              # 피처 엔지니어링 결과
│   │   └── splits/                # Train/Test 분리 데이터
│   │
│   └── paper_trades/              # 페이퍼 트레이딩 거래 기록
│       └── .gitkeep
│
│
│ ── logs/                         # 로그 (실행 기록, 디버깅)
│   │
│   ├── app/                       # 애플리케이션 로그 (일별 로테이션)
│   │   ├── casper_2026-03-27.log  # 메인 실행 로그
│   │   └── ...
│   │
│   ├── trades/                    # 거래 기록 로그
│   │   ├── signals/               # 시그널 발생 기록 (진입 판단 근거)
│   │   │   └── signals_2026-03-27.jsonl
│   │   ├── executions/            # 체결 기록
│   │   │   └── exec_2026-03-27.jsonl
│   │   └── daily_summary/         # 일별 요약 (P&L, 승률, 종목별)
│   │       └── summary_2026-03-27.json
│   │
│   ├── scanner/                   # 스캐너 로그
│   │   └── scan_2026-03-27.json   # 당일 스캔 결과 + 필터링 과정
│   │
│   ├── backtest/                  # 백테스트 실행 로그
│   │   ├── bt_20260327_143022/    # 실행별 디렉토리 (타임스탬프)
│   │   │   ├── params.json        # 사용된 파라미터
│   │   │   ├── results.json       # 성과 지표
│   │   │   ├── trades.csv         # 거래 내역
│   │   │   └── equity_curve.png   # 수익 곡선 이미지
│   │   └── ...
│   │
│   └── debug/                     # 디버깅 전용
│       └── .gitkeep               # 임시 디버그 출력, 수동 삭제
│
│
│ ── notebooks/                    # Jupyter 노트북 (탐색/시각화)
│   │
│   ├── 01_data_exploration.ipynb  # 데이터 탐색 (분포, 패턴)
│   ├── 02_orb_analysis.ipynb      # ORB 레벨 통계 분석
│   ├── 03_fvg_analysis.ipynb      # FVG 발생/충족 통계
│   ├── 04_backtest_review.ipynb   # 백테스트 결과 상세 리뷰
│   └── 05_paper_review.ipynb      # 페이퍼 트레이딩 리뷰
│
│
│ ── scripts/                      # 유틸리티 스크립트 (일회성/배치)
│   │
│   ├── download_data.py           # 전체 데이터 일괄 다운로드
│   ├── update_calendar.py         # 매크로 이벤트 캘린더 업데이트
│   ├── export_trades.py           # 거래 기록 CSV/Excel 내보내기
│   └── cleanup_logs.sh            # 오래된 로그 정리
│
│
│ ── tests/                        # 테스트 코드
│   │
│   ├── __init__.py
│   ├── test_indicators.py         # ORB, FVG 계산 정확성
│   ├── test_strategy.py           # 진입/청산 로직 단위 테스트
│   ├── test_risk.py               # 포지션 사이징, Circuit Breaker
│   ├── test_scanner.py            # 스캐너 필터 테스트
│   └── fixtures/                  # 테스트용 샘플 데이터
│       ├── sample_ohlcv.csv
│       └── sample_fvg_cases.json
│
│
└── output/                        # 산출물 (보고서, 차트 이미지)
    │
    ├── reports/                   # 생성된 보고서 (PDF, HTML)
    │   └── .gitkeep
    │
    └── charts/                    # 생성된 차트 이미지
        └── .gitkeep
```

---

## 각 디렉토리 역할 요약

```
디렉토리          읽기/쓰기    git 추적    역할
─────────────────────────────────────────────────────────────────
docs/             사람이 읽기   O          전략/이론/결과 문서
config/           코드가 읽기   O          정적 설정 파라미터
src/              코드 실행     O          트레이딩 시스템 (런타임)
backtest/         코드 실행     O          검증 시스템 (오프라인)
data/             코드가 쓰기   X          대용량 데이터 저장소
logs/             코드가 쓰기   X          실행 로그, 거래 기록
notebooks/        사람이 실행   O          탐색적 분석, 시각화
scripts/          사람이 실행   O          일회성 유틸리티
tests/            코드 실행     O          자동화 테스트
output/           코드가 쓰기   X          보고서, 차트 산출물
```

---

## .env 구조

```bash
# === Alpaca API ===
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ALPACA_BASE_URL=https://paper-api.alpaca.markets   # paper 또는 live

# === Polygon.io (선택) ===
POLYGON_API_KEY=

# === Telegram 알림 ===
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# === 운영 모드 ===
TRADING_MODE=paper          # paper | live | backtest
LOG_LEVEL=INFO              # DEBUG | INFO | WARNING | ERROR
TIMEZONE=US/Eastern
```

---

## .gitignore 핵심 항목

```
.env
.venv/
data/
logs/
output/
__pycache__/
*.pyc
.DS_Store
*.parquet
notebooks/.ipynb_checkpoints/
```

---

## config/ 예시: strategy_params.json

```json
{
  "orb": {
    "timeframe_minutes": 15,
    "chart_timeframe": "5min",
    "breakout_type": "body_close"
  },
  "fvg": {
    "min_gap_pct": 0.05,
    "max_distance_from_orb_pct": 0.5,
    "require_overlap_with_orb": true
  },
  "entry": {
    "type": "pullback_to_fvg",
    "confirmation_candles": 1
  },
  "exit": {
    "risk_reward_ratio": 2.0,
    "time_limit_minutes": 90,
    "trailing_stop": false
  },
  "filters": {
    "vix_min": 12,
    "vix_max": 30,
    "spy_ma_period": 20,
    "require_market_bias_alignment": true
  },
  "risk": {
    "max_risk_per_trade_pct": 1.0,
    "max_daily_loss_pct": 3.0,
    "max_consecutive_losses": 3,
    "max_concurrent_positions": 2
  }
}
```

---

## logs/ 상세 구조 설명

### trades/signals/ (시그널 로그) — 왜 진입했는지 추적

```jsonl
{"ts":"2026-03-27T09:52:00-04:00","symbol":"SPY","type":"long","orb_high":562.30,"orb_low":560.85,"breakout_candle":"09:50","fvg_zone":[561.90,562.10],"market_bias":"bullish","vix":18.3,"entry_price":562.05,"stop":561.45,"target":563.25,"rr":2.0}
```

### trades/executions/ (체결 로그) — 실제 무슨 일이 일어났는지

```jsonl
{"ts":"2026-03-27T09:52:15-04:00","symbol":"SPY","side":"buy","qty":166,"price":562.07,"slippage":0.02,"commission":0.83}
{"ts":"2026-03-27T10:15:30-04:00","symbol":"SPY","side":"sell","qty":166,"price":563.18,"reason":"take_profit","pnl":184.26}
```

### trades/daily_summary/ — 하루를 한눈에

```json
{
  "date": "2026-03-27",
  "trades": 2,
  "wins": 1,
  "losses": 1,
  "pnl": 87.50,
  "win_rate": 0.50,
  "max_drawdown": -96.76,
  "circuit_breaker_triggered": false
}
```
