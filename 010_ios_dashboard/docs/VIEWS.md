# Views

## 탭 구조

3개 탭 + 설정 (NavigationStack 내부).
URL Scheme `tradingdashboard://tab/{dashboard,crypto,stock}`으로 탭 전환 가능.

## Dashboard 탭

| 파일 | 설명 |
|------|------|
| `DashboardView.swift` | 메인 화면 - 주식/암호화폐 요약 카드, 봇 상태, Pull-to-refresh |
| `PortfolioCardView.swift` | 포트폴리오 요약 카드 (총자산, 일일 P&L, 수익률) |

## Crypto 탭

| 파일 | 설명 |
|------|------|
| `CryptoDetailView.swift` | 시장 레짐 + 코인 목록 + 최근 거래 |
| `RegimeCardView.swift` | 시장 레짐 카드 (상태명, ATR%, 진입 모드) |
| `CoinDetailSection.swift` | 코인별 상세 (시세, 성과 통계) |
| `CoinChartView.swift` | 캔들스틱 차트 (5m/30m/1h/6h/1d 간격 선택) |

## Stock 탭

| 파일 | 설명 |
|------|------|
| `StockDetailView.swift` | 포지션 목록 + 일일 자산 차트 + 거래 내역 |
| `DailyPnLChartView.swift` | 일일 P&L 차트 (Swift Charts) |

## Settings

| 파일 | 설명 |
|------|------|
| `SettingsView.swift` | 서버 URL, API Key, 새로고침 간격 설정. 초기 설정 모드 지원 |

## 공통 컴포넌트

| 파일 | 설명 |
|------|------|
| `ProfitText.swift` | 손익 텍스트 (양수 초록, 음수 빨강) |
| `StatusBadge.swift` | 봇 상태 배지 (색상 인디케이터 + 텍스트) |
| `LoadingView.swift` | 로딩 스피너 |

## BotStatus 인디케이터 색상

| 상태 | 주식 봇 | 암호화폐 봇 |
|------|---------|------------|
| 실행 중 | 초록 (장중) | 초록 |
| 대기 중 | 노랑 (장 전/후) | - |
| 휴장 | 회색 (주말/공휴일) | - |
| 중지됨 | 빨강 | 빨강 |
