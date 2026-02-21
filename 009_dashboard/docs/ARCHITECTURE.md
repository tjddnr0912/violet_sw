# Architecture

## 009_dashboard (Flask 백엔드)

```
009_dashboard/
├── app.py                          # Flask 앱 (v1 + v2 API, 214줄)
├── data_loader.py                  # JSON 데이터 로더 (408줄)
├── requirements.txt                # flask, gunicorn, python-dotenv, flask-cors, requests
├── .env.example                    # 환경변수 템플릿
├── setup_tunnel.sh                 # Cloudflare Tunnel 설정 스크립트
├── com.violet.dashboard.plist      # launchd 자동 시작 설정
├── render.yaml                     # Render.com 배포 설정 (미사용)
├── templates/                      # Jinja2 HTML (5개: base, index, stock, crypto, embed)
├── static/                         # CSS, JS
├── docs/                           # 상세 문서
└── logs/                           # 서버 로그
```

### 핵심 모듈

| 파일 | 역할 |
|------|------|
| `app.py` | Flask 라우트 정의 (페이지 4개 + v1 API 5개 + v2 API 12개 + health) |
| `data_loader.py` | `TradingDataLoader` 클래스 - JSON 파일 로드, 가공, Bithumb API 호출 |

### 데이터 흐름

```
007_stock_trade/data/quant/*.json  ─┐
                                    ├→ data_loader.py → app.py → JSON/HTML 응답
005_money/logs/*.json              ─┘
                                         ↑
                                    Bithumb Public API (실시간 시세/차트)
```

## 010_ios_dashboard (SwiftUI iOS 앱)

```
010_ios_dashboard/
├── project.yml                        # xcodegen 프로젝트 설정
├── TradingDashboard.xcodeproj/        # 생성된 Xcode 프로젝트
└── TradingDashboard/
    ├── App/                           # 진입점 + 탭 구조 (URL Scheme 딥링크)
    │   ├── TradingDashboardApp.swift
    │   └── ContentView.swift
    ├── Models/ (5개)                  # Codable 모델
    │   ├── APIResponse.swift
    │   ├── PortfolioSummary.swift
    │   ├── CryptoModels.swift
    │   ├── StockModels.swift
    │   └── SystemStatus.swift
    ├── Services/ (2개)
    │   ├── APIClient.swift            # v2 API 호출
    │   └── SettingsManager.swift      # 서버 URL/API Key 저장
    ├── ViewModels/ (3개)              # MVVM
    │   ├── DashboardViewModel.swift
    │   ├── CryptoViewModel.swift
    │   └── StockViewModel.swift
    ├── Views/
    │   ├── Dashboard/
    │   │   ├── DashboardView.swift
    │   │   └── PortfolioCardView.swift
    │   ├── Crypto/
    │   │   ├── CryptoDetailView.swift
    │   │   ├── CoinDetailSection.swift
    │   │   ├── CoinChartView.swift
    │   │   └── RegimeCardView.swift
    │   ├── Stock/
    │   │   ├── StockDetailView.swift
    │   │   └── DailyPnLChartView.swift
    │   ├── Settings/
    │   │   └── SettingsView.swift
    │   └── Components/
    │       ├── ProfitText.swift
    │       ├── StatusBadge.swift
    │       └── LoadingView.swift
    ├── Extensions/
    │   ├── Double+Formatting.swift
    │   └── Color+Theme.swift
    ├── Info.plist                      # URL Scheme: tradingdashboard://
    └── Assets.xcassets/
```

### iOS 앱 빌드

```bash
cd 010_ios_dashboard
xcodegen generate                      # project.yml → .xcodeproj
open TradingDashboard.xcodeproj        # Xcode에서 열기
```

### URL Scheme 딥링크

`tradingdashboard://tab/{dashboard,crypto,stock}` → 해당 탭으로 전환

## 기술 스택

| 구분 | 기술 |
|------|------|
| 백엔드 | Python 3.11+, Flask 3.0, Gunicorn |
| iOS | Swift, SwiftUI, MVVM, xcodegen |
| 데이터 | JSON 파일 (읽기 전용), Bithumb Public API |
| 인증 | API Key (X-API-Key 헤더 / api_key 쿼리) |

## 환경변수

```bash
# 009_dashboard/.env
DASHBOARD_API_KEY=    # 비어있으면 인증 비활성화
FLASK_DEBUG=false     # 디버그 모드
```
