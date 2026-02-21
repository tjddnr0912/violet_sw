# CLAUDE.md - 010_ios_dashboard

009_dashboard Flask 서버의 v2 API를 소비하는 SwiftUI iOS 앱.
암호화폐 + 한국주식 포트폴리오를 모바일에서 조회.

## 빌드

```bash
cd 010_ios_dashboard
xcodegen generate                      # project.yml → .xcodeproj
open TradingDashboard.xcodeproj        # Xcode에서 열기
```

- **최소 iOS**: 17.0
- **Bundle ID**: com.violet.tradingdashboard
- **URL Scheme**: `tradingdashboard://tab/{dashboard,crypto,stock}`

## 구조 요약

| 레이어 | 파일 | 역할 |
|--------|------|------|
| App | `TradingDashboardApp.swift`, `ContentView.swift` | 진입점, 탭 구조, 딥링크 |
| Models (5개) | `APIResponse`, `PortfolioSummary`, `CryptoModels`, `StockModels`, `SystemStatus` | Codable 모델 |
| Services (2개) | `APIClient`, `SettingsManager` | v2 API 호출, UserDefaults 설정 |
| ViewModels (3개) | `DashboardViewModel`, `CryptoViewModel`, `StockViewModel` | MVVM, 자동 새로고침 |
| Views (12개) | Dashboard/Crypto/Stock/Settings/Components | SwiftUI 화면 |

## 핵심 참조

- **백엔드**: 009_dashboard Flask 서버 (v2 API)
- **설정 저장**: UserDefaults (serverURL, apiKey, refreshInterval)
- **기본 새로고침**: 30초 간격
- **서버 미설정 시**: 설정 화면(SettingsView) 자동 표시

## 상세 문서

- [아키텍처](docs/ARCHITECTURE.md) - MVVM 구조, 데이터 흐름, 모델 매핑
- [화면 구성](docs/VIEWS.md) - 탭별 화면 설명, 컴포넌트
