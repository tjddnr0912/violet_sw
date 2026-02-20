# CLAUDE.md - 009_dashboard + 010_ios_dashboard

Trading Dashboard 웹 서버 + iOS 앱 프로젝트.
005_money(암호화폐)와 007_stock_trade(한국주식)의 실시간 데이터를 통합 조회.

## 현재 상태 (2026-02-20)

### 완료된 작업

| Phase | 상태 | 내용 |
|-------|------|------|
| Phase 1: Flask 백엔드 강화 | **완료** | v2 API 8개, API Key 인증, 신규 메서드 3개 |
| Phase 3: iOS 앱 소스코드 | **완료** | 24개 Swift 파일, xcodegen 빌드 성공 |
| xcode-select 전환 | **완료** | Xcode.app Developer 경로로 전환 완료 |
| 시뮬레이터 빌드/실행 검증 | **완료** | iPhone 16 Pro (iOS 18.2) 시뮬레이터 빌드/실행/데이터 연동 확인 |
| URL Scheme 딥링크 | **완료** | `tradingdashboard://tab/{dashboard,crypto,stock}` 탭 전환 지원 |

### 미완료 작업

| Phase | 상태 | 내용 | 필요 조건 |
|-------|------|------|-----------|
| Phase 2: Cloudflare Tunnel | **미진행** | 터널 설정 + launchd 등록 | `setup_tunnel.sh` 실행, 도메인 결정 |
| .env API Key 설정 | **미진행** | DASHBOARD_API_KEY 생성 후 .env 반영 | 수동 작업 |
| Xcode 실기기 테스트 | **미진행** | 실기기 빌드 검증 | Apple Developer 계정 + 기기 연결 |
| iOS WidgetKit | **미진행** | 홈 화면 위젯 | App Groups 설정 필요 |

---

## 프로젝트 구조

### 009_dashboard (Flask 백엔드)

```
009_dashboard/
├── app.py              # Flask 앱 (v1 + v2 API, 188줄)
├── data_loader.py      # JSON 데이터 로더 (233줄)
├── .env.example        # 환경변수 템플릿
├── requirements.txt    # Flask, gunicorn, dotenv, cors
├── render.yaml         # Render.com 배포 설정 (미사용)
├── setup_tunnel.sh     # Cloudflare Tunnel 설정 스크립트
├── com.violet.dashboard.plist  # launchd 자동 시작 설정
├── templates/          # Jinja2 HTML (기존 웹 대시보드)
├── static/             # CSS, JS
└── logs/               # 서버 로그
```

### 010_ios_dashboard (Swift iOS 앱)

```
010_ios_dashboard/
├── project.yml                    # xcodegen 프로젝트 설정
├── TradingDashboard.xcodeproj/    # 생성된 Xcode 프로젝트
└── TradingDashboard/
    ├── App/           # 앱 진입점, 탭 구조 (URL Scheme 딥링크 포함)
    ├── Models/        # API 응답 Codable 모델 (5개)
    ├── Services/      # APIClient, SettingsManager
    ├── ViewModels/    # MVVM ViewModel (3개)
    ├── Views/         # SwiftUI 화면 (9개 + 컴포넌트 3개)
    ├── Extensions/    # Double 포맷, Color 테마
    ├── Info.plist     # URL Scheme 등록 (tradingdashboard://)
    └── Assets.xcassets/
```

---

## API 엔드포인트

### v1 (인증 없음, 기존 호환)
- `GET /api/summary`
- `GET /api/stock/positions`
- `GET /api/crypto/regime`
- `GET /api/crypto/trades`
- `GET /api/crypto/performance`

### v2 (API Key 인증, iOS 앱용)
- `GET /api/v2/summary` → 통합 요약 (stock + crypto + system_status)
- `GET /api/v2/crypto/regime` → 레짐 상세 (ATR% 포함)
- `GET /api/v2/crypto/trades?limit=N`
- `GET /api/v2/crypto/performance`
- `GET /api/v2/stock/positions`
- `GET /api/v2/stock/daily?days=N` → 일일 자산 히스토리
- `GET /api/v2/stock/transactions?limit=N` → 거래 내역
- `GET /api/v2/system/status` → 봇 상태

### 인증 방식
- 헤더: `X-API-Key: <key>`
- 쿼리: `?api_key=<key>`
- `DASHBOARD_API_KEY` 환경변수 비어있으면 인증 비활성화

---

## 참조 데이터 파일 (읽기 전용)

| 키 | 파일 경로 | 데이터 |
|----|-----------|--------|
| stock_engine | `007_stock_trade/data/quant/engine_state.json` | 포지션, 리밸런스 |
| stock_daily | `007_stock_trade/data/quant/daily_history.json` | 일일 스냅샷 배열 |
| stock_transactions | `007_stock_trade/data/quant/transaction_journal.json` | 거래 내역 배열 |
| crypto_factors | `005_money/logs/dynamic_factors_v3.json` | 시장 레짐, ATR% |
| crypto_history | `005_money/logs/performance_history_v3.json` | 거래 히스토리 배열 |

---

## 개발 가이드

### Flask 서버 실행
```bash
cd 009_dashboard
source venv/bin/activate
python app.py              # localhost:5001
```

### API 테스트
```bash
curl localhost:5001/health
curl localhost:5001/api/v2/summary   # API Key 없으면 인증 비활성화
```

### iOS 앱
```bash
cd 010_ios_dashboard
xcodegen generate          # project.yml → .xcodeproj 재생성
open TradingDashboard.xcodeproj   # Xcode에서 열기
```

### 포트
- Flask: **5001** (macOS ControlCenter가 5000 사용)
