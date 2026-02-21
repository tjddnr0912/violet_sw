# Architecture

## 프로젝트 구조

```
TradingDashboard/
├── App/
│   ├── TradingDashboardApp.swift      # @main, SettingsManager 주입
│   └── ContentView.swift              # TabView + URL Scheme 딥링크 처리
├── Models/
│   ├── APIResponse.swift              # Generic API 응답 래퍼 (status, data, timestamp)
│   ├── PortfolioSummary.swift         # 통합 요약 (StockSummary + CryptoSummary + BotStatus)
│   ├── CryptoModels.swift             # CryptoRegime, CryptoTrade, CoinSummary, CoinPrice, Candlestick
│   ├── StockModels.swift              # StockPosition, StockDailyData, DailySnapshot, StockTransaction
│   └── SystemStatus.swift             # BotStatus (장시간 인식, 4색 인디케이터)
├── Services/
│   ├── APIClient.swift                # Generic fetch<T>, X-API-Key 헤더, testConnection
│   └── SettingsManager.swift          # Singleton, UserDefaults 저장 (URL, Key, Interval)
├── ViewModels/
│   ├── DashboardViewModel.swift       # /api/v2/summary 호출
│   ├── CryptoViewModel.swift          # regime + performance + trades + coins + 코인별 상세
│   └── StockViewModel.swift           # positions + daily + transactions
├── Views/ (아래 VIEWS.md 참조)
├── Extensions/
│   ├── Double+Formatting.swift        # 숫자 포맷 (원화, %, 소수점)
│   └── Color+Theme.swift              # 앱 컬러 테마
├── Info.plist                         # URL Scheme 등록
└── Assets.xcassets/
```

## MVVM 데이터 흐름

```
009_dashboard (Flask)
    ↓ v2 API (JSON)
APIClient.fetch<T>()
    ↓ Codable 디코딩
ViewModel (@Published)
    ↓ SwiftUI 바인딩
View (자동 갱신)
```

### ViewModel → API 매핑

| ViewModel | API 엔드포인트 |
|-----------|---------------|
| DashboardViewModel | `/api/v2/summary` |
| CryptoViewModel | `/api/v2/crypto/regime`, `/performance`, `/trades`, `/coins`, `/price/<coin>`, `/chart/<coin>` |
| StockViewModel | `/api/v2/stock/positions`, `/daily`, `/transactions` |

### 자동 새로고침

모든 ViewModel이 `startAutoRefresh(interval:)` / `stopAutoRefresh()` 패턴 사용.
기본 30초 간격, `SettingsManager.refreshInterval`로 변경 가능.

## Model ↔ API JSON 매핑

모든 모델은 `CodingKeys`로 snake_case(API) ↔ camelCase(Swift) 변환.

### 주요 모델

| Swift Model | API 응답 | 용도 |
|-------------|---------|------|
| `PortfolioSummary` | `/api/v2/summary` | 대시보드 통합 요약 |
| `CryptoRegime` | `/api/v2/crypto/regime` | 시장 레짐 (강세~약세, ATR%) |
| `CryptoTrade` | `/api/v2/crypto/trades` | 거래 내역 (Identifiable, tradeId) |
| `CoinSummary` | `/api/v2/crypto/coins` | 코인별 성과 집계 |
| `CoinPrice` | `/api/v2/crypto/price/<coin>` | Bithumb 실시간 시세 |
| `Candlestick` | `/api/v2/crypto/chart/<coin>` | 캔들스틱 차트 데이터 |
| `StockPosition` | `/api/v2/stock/positions` | 주식 포지션 (손익 포함) |
| `StockDailyData` | `/api/v2/stock/daily` | 일일 자산 스냅샷 배열 |
| `StockTransaction` | `/api/v2/stock/transactions` | 주식 거래 내역 |
| `BotStatus` | `/api/v2/system/status` | 봇 상태 (장시간 인식 4색) |

## APIClient 에러 처리

| 에러 | 조건 |
|------|------|
| `notConfigured` | serverURL 미설정 |
| `invalidURL` | URL 파싱 실패 |
| `unauthorized` | HTTP 401 |
| `networkError` | 네트워크 연결 실패 |
| `decodingError` | JSON 파싱 실패 |
| `serverError` | HTTP 4xx/5xx |

## xcodegen

`project.yml`로 `.xcodeproj` 생성. Xcode 프로젝트 파일 직접 수정 대신 `project.yml` 수정 후 재생성.

```bash
xcodegen generate
```
