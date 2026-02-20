# Trading Dashboard + iOS 앱 - 코드 리뷰 문서

> 이 문서는 009_dashboard(Flask 백엔드)와 010_ios_dashboard(Swift iOS 앱) 전체 구현을 해설합니다.
> 리뷰 후 질문사항을 자유롭게 물어보세요.

---

## 1. 전체 아키텍처

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  005_money  │     │  009_dashboard   │     │ 010_ios_dashboard│
│ (암호화폐봇) │────▶│  Flask (:5001)   │◀────│   Swift iOS App  │
│  JSON files │     │                  │     │                  │
└─────────────┘     │  v1 API (웹용)   │     │  3개 탭 + 설정    │
                    │  v2 API (앱용)   │     │  30초 자동갱신    │
┌─────────────┐     │  웹 대시보드      │     └────────┬─────────┘
│007_stock_trade│───▶│                  │              │
│ (한국주식봇)  │     └────────┬─────────┘              │
│  JSON files │              │                        │
└─────────────┘              │  Cloudflare Tunnel     │
                    ┌────────▼─────────┐              │
                    │  HTTPS (외부접근) │◀─────────────┘
                    │  dashboard.xxx.com│   iPhone에서 접속
                    └──────────────────┘
```

**핵심 원리**: 005/007 봇들이 실시간으로 JSON 파일을 갱신하고, Flask가 이 파일들을 읽어서 API로 제공하며, iOS 앱이 이 API를 주기적으로 호출합니다. Cloudflare Tunnel은 Mac의 포트를 열지 않고도 HTTPS로 외부 접근을 가능하게 합니다.

---

## 2. Phase 1: Flask 백엔드 (009_dashboard)

### 2-1. data_loader.py - 데이터 로더

**역할**: 005/007 프로젝트의 JSON 파일을 읽어서 Python dict로 변환

#### 데이터 경로 매핑 (21~29줄)

```python
self.data_paths = {
    # 기존 4개
    'stock_engine':       '007_stock_trade/data/quant/engine_state.json',
    'stock_metrics':      '007_stock_trade/data/strategy_monitor.json',
    'crypto_factors':     '005_money/logs/dynamic_factors_v3.json',
    'crypto_history':     '005_money/logs/performance_history_v3.json',
    # 신규 3개
    'stock_system':       '007_stock_trade/data/quant/system_state.json',
    'stock_daily':        '007_stock_trade/data/quant/daily_history.json',
    'stock_transactions': '007_stock_trade/data/quant/transaction_journal.json',
}
```

**해설**: `_load_json(key)` 메서드가 이 딕셔너리의 키를 받아 해당 파일을 로드합니다. 파일이 없거나 JSON 파싱 실패 시 `None`을 반환하므로 봇이 꺼져있어도 서버가 죽지 않습니다.

**리뷰 포인트**: `stock_metrics`와 `stock_system`은 현재 직접 사용하는 API가 없습니다. `stock_metrics`는 기존에 있던 것이고, `stock_system`은 추후 봇 상태 확인에 활용할 수 있습니다.

#### 신규 메서드 1: get_stock_daily_history() (79~88줄)

```python
def get_stock_daily_history(self, days: int = 30) -> Dict[str, Any]:
    data = self._load_json('stock_daily')
    if not data:
        return {'initial_capital': 0, 'snapshots': []}
    snapshots = data.get('snapshots', [])
    return {
        'initial_capital': data.get('initial_capital', 0),
        'snapshots': snapshots[-days:],  # 리스트 슬라이싱으로 최근 N일만
    }
```

**해설**: `daily_history.json`에는 매일 15:20에 기록된 스냅샷이 배열로 저장됩니다. `snapshots[-30:]`으로 최근 30일 데이터만 잘라서 반환합니다. API 호출 시 `?days=7`처럼 원하는 기간을 지정할 수 있습니다.

**실제 데이터 예시** (007_stock_trade가 매일 기록):
```json
{
  "initial_capital": 4970786,
  "snapshots": [
    {"date": "2026-02-13", "total_assets": 17095836, "daily_pnl": 60470, ...}
  ]
}
```

#### 신규 메서드 2: get_stock_transactions() (90~97줄)

```python
def get_stock_transactions(self, limit: int = 20) -> List[Dict[str, Any]]:
    data = self._load_json('stock_transactions')
    if not data:
        return []
    txns = data.get('transactions', [])
    sorted_txns = sorted(txns, key=lambda x: x.get('timestamp', ''), reverse=True)
    return sorted_txns[:limit]
```

**해설**: `transaction_journal.json`의 거래 내역을 최신순 정렬 후 limit개만 반환합니다. 현재 데이터에는 GS 손절 매도 1건만 있습니다.

#### 신규 메서드 3: get_system_status() (148~171줄)

```python
def get_system_status(self) -> Dict[str, Any]:
    checks = {
        'crypto_bot': 'crypto_factors',   # dynamic_factors_v3.json
        'stock_bot': 'stock_engine',       # engine_state.json
    }
    for bot_name, data_key in checks.items():
        path = self.data_paths.get(data_key)
        mtime = path.stat().st_mtime
        age_minutes = (time.time() - mtime) / 60
        statuses[bot_name] = {
            'running': age_minutes < 30,  # 30분 이내 갱신이면 running
            ...
        }
```

**해설**: 봇이 살아있는지 직접 프로세스를 확인하는 대신, 봇이 주기적으로 갱신하는 JSON 파일의 수정 시각(mtime)을 확인합니다. 30분 이내에 갱신되었으면 `running: true`.

**판단 기준 30분의 근거**:
- 005_money: 15분마다 트레이딩 사이클 → 최대 15분 간격으로 파일 갱신
- 007_stock_trade: 5분마다 모니터링 → 최대 5분 간격으로 파일 갱신
- 30분 임계값이면 2번 연속 갱신 실패 시 "중지됨"으로 판단 (넉넉한 마진)

**리뷰 포인트**: 주식 봇은 장 마감(15:20) 이후 파일 갱신을 하지 않으므로, 밤/주말에는 항상 `running: false`로 표시됩니다. 이것이 의도된 동작인지, 아니면 "장중에만 running 체크"로 바꿔야 할지 검토가 필요합니다.

#### 수정된 get_portfolio_summary() (175~218줄)

기존 대비 변경점:
1. `system_status` 추가 (봇 상태)
2. `daily_pnl`, `daily_pnl_pct`, `total_pnl_pct`, `total_assets` 추가 (daily_history에서)
3. `total_profit_pct`, `avg_profit_pct` 추가 (crypto 성과)

**해설**: 이 메서드가 `/api/v2/summary`의 데이터 소스이며, iOS 앱 대시보드 탭의 메인 데이터입니다. 한 번의 API 호출로 주식+암호화폐+봇상태를 모두 가져올 수 있도록 설계했습니다.

#### 수정된 get_crypto_regime() (101~115줄)

```python
# 추가된 필드
'current_atr_pct': data.get('current_atr_pct'),      # ATR 변동성 %
'take_profit_target': data.get('take_profit_target'),  # 익절 전략
```

**해설**: 기존에 5개 필드만 반환하던 것에 2개를 추가. ATR%(Average True Range)는 현재 시장 변동성을 %로 표시하며, take_profit_target은 익절 전략(bb_middle = 볼린저밴드 중간선)을 나타냅니다.

---

### 2-2. app.py - Flask 라우트

#### API Key 인증 미들웨어 (23~33줄)

```python
@app.before_request
def check_api_key():
    if request.path == '/health':
        return None                    # health check는 항상 통과
    if request.path.startswith('/api/v2/'):
        if not API_KEY:
            return None                # API Key 미설정 시 인증 비활성화
        key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if not key or key != API_KEY:
            return jsonify({...}), 401
```

**해설**: `@app.before_request`는 모든 요청 전에 실행됩니다. 동작 방식:

| 경로 | API_KEY 설정됨 | 키 제공 | 결과 |
|------|---------------|---------|------|
| `/health` | 무관 | 무관 | 통과 |
| `/api/summary` (v1) | 무관 | 무관 | 통과 |
| `/api/v2/summary` | 아니오 | 무관 | 통과 (인증 비활성화) |
| `/api/v2/summary` | 예 | 올바른 키 | 통과 |
| `/api/v2/summary` | 예 | 없음/틀림 | 401 |

**설계 의도**:
- v1 API는 기존 웹 대시보드 호환성을 위해 인증 없이 유지
- v2 API는 외부 접근(Cloudflare Tunnel)을 전제로 인증 필요
- 로컬 개발 시 `.env`에 키를 설정하지 않으면 자동으로 인증 비활성화

**리뷰 포인트**: 현재는 단순 문자열 비교입니다. timing attack에 취약할 수 있으나, Cloudflare Tunnel의 네트워크 지터가 이를 충분히 상쇄합니다. 보안을 강화하려면 `hmac.compare_digest()`로 변경할 수 있습니다.

#### v2 응답 형식 (36~42줄)

```python
def api_response(data):
    return jsonify({
        'status': 'ok',
        'data': data,           # 실제 데이터
        'timestamp': '...',     # 응답 생성 시각
    })
```

**해설**: 모든 v2 API가 동일한 래퍼 구조를 사용합니다. iOS 앱의 `APIResponse<T>` 제네릭 타입이 이 구조를 파싱하여 `data` 필드의 타입을 자동으로 디코딩합니다.

#### v2 API 엔드포인트 (125~175줄)

8개 엔드포인트 모두 동일한 패턴:
1. `request.args.get()`으로 쿼리 파라미터 파싱 (선택적)
2. `data_loader`의 해당 메서드 호출
3. `api_response()`로 래핑하여 반환

**특이사항**: `/api/v2/crypto/trades`는 `get_recent_trades()`를 호출하는데, 이는 내부적으로 `get_crypto_history()`의 wrapper입니다. v1과 v2가 같은 데이터 소스를 사용합니다.

#### 포트 변경: 5000 → 5001

```python
app.run(host='0.0.0.0', port=5001, debug=debug_mode)
```

**이유**: macOS Monterey 이후 AirPlay Receiver(ControlCenter)가 포트 5000을 점유합니다. 시스템 설정 → 일반 → AirDrop 및 Handoff → AirPlay 수신모드를 끄면 5000을 사용할 수 있지만, 충돌을 피하기 위해 5001로 변경했습니다.

---

### 2-3. 기타 파일

#### setup_tunnel.sh

Cloudflare Tunnel 초기 설정 자동화 스크립트:
1. cloudflared 설치 (brew)
2. Cloudflare 계정 인증 (브라우저 열림)
3. 터널 생성
4. config.yml 자동 생성

**실행 전 확인**: Cloudflare에 도메인이 등록되어 있어야 합니다. 없으면 `cloudflared tunnel --url http://localhost:5001` 명령으로 임시 URL을 사용할 수 있습니다(매번 URL이 변경됨).

#### com.violet.dashboard.plist

macOS launchd 서비스 설정. `~/Library/LaunchAgents/`에 복사 후 `launchctl load`하면 부팅 시 자동으로 Flask 서버가 시작됩니다.

**주의**: `ProgramArguments`에 `/usr/bin/python3`을 사용하는데, venv의 패키지를 사용하려면 경로를 venv의 python으로 변경해야 할 수 있습니다:
```xml
<string>/Users/seongwookjang/project/git/violet_sw/009_dashboard/venv/bin/python</string>
```

---

## 3. Phase 3: iOS 앱 (010_ios_dashboard)

### 3-1. 아키텍처: MVVM + SwiftUI

```
┌────────────┐     ┌──────────────┐     ┌──────────┐
│   Views    │────▶│  ViewModels  │────▶│ APIClient │──▶ Flask API
│  (SwiftUI) │◀────│ (@Published) │◀────│  (async)  │◀── JSON
└────────────┘     └──────────────┘     └──────────┘
                          │                    │
                   ┌──────▼──────┐     ┌──────▼──────┐
                   │   Models    │     │  Settings   │
                   │  (Codable)  │     │ (UserDefaults)│
                   └─────────────┘     └─────────────┘
```

- **View**: UI만 담당. 데이터 표시와 사용자 입력 처리
- **ViewModel**: 비즈니스 로직. API 호출, 자동 갱신 타이머, 상태 관리
- **Model**: 데이터 구조 정의. JSON ↔ Swift 타입 매핑
- **Service**: 네트워크 통신, 설정 저장

### 3-2. Models 레이어 (5개 파일)

#### APIResponse.swift - 공통 래퍼

```swift
struct APIResponse<T: Codable>: Codable {
    let status: String
    let data: T           // 제네릭: 엔드포인트마다 다른 타입
    let timestamp: String
}
```

**해설**: Flask의 `api_response()` 구조와 1:1 매핑. `APIClient.fetch<T>()`에서 `APIResponse<T>`로 디코딩 후 `.data`만 추출하여 반환합니다.

#### PortfolioSummary.swift - 대시보드 메인 데이터

```swift
struct PortfolioSummary: Codable {
    let stock: StockSummary          // 주식 요약
    let crypto: CryptoSummary        // 암호화폐 요약
    let systemStatus: [String: BotStatus]  // 봇 상태 딕셔너리
    let generatedAt: String

    enum CodingKeys: String, CodingKey {
        case systemStatus = "system_status"   // snake_case → camelCase
        case generatedAt = "generated_at"
        ...
    }
}
```

**CodingKeys 해설**: Python(Flask)은 `snake_case`, Swift는 `camelCase` 관례입니다. `CodingKeys` enum으로 JSON 키와 Swift 프로퍼티를 매핑합니다. 모든 모델 파일에서 이 패턴을 사용합니다.

**`[String: BotStatus]` 해설**: `system_status` JSON은 `{"crypto_bot": {...}, "stock_bot": {...}}` 형태이므로 Dictionary로 디코딩합니다. 키가 동적이기 때문에 struct가 아닌 Dictionary를 사용합니다.

#### CryptoModels.swift - 암호화폐 모델

주목할 패턴:

```swift
struct CryptoTrade: Codable, Identifiable {
    var id: String { tradeId }  // Identifiable 프로토콜 충족 (ForEach에서 필요)
    ...
}
```

**Identifiable 해설**: SwiftUI의 `ForEach`에서 리스트를 렌더링할 때 각 항목을 고유하게 식별해야 합니다. `Identifiable` 프로토콜을 채택하고 `id` 프로퍼티를 제공하면 `ForEach(trades) { trade in ... }` 처럼 간결하게 사용할 수 있습니다.

```swift
var regimeDisplayName: String {
    switch marketRegime {
    case "strong_bullish": return "강세 상승"
    ...
    }
}
```

**computed property 해설**: API에서는 `"strong_bearish"` 같은 영문 키가 오지만, UI에서는 한글로 표시해야 합니다. Model에 변환 로직을 넣어서 View가 단순해집니다.

#### StockModels.swift - 주식 모델

```swift
struct DailySnapshot: Codable, Identifiable {
    var id: String { date }  // 날짜가 고유 키
    let totalAssets: Int     // Int (원 단위, 소수점 없음)
    let dailyPnlPct: Double  // Double (% 단위)
    ...
}
```

**Int vs Double 해설**: JSON의 `total_assets`는 정수(17095836), `daily_pnl_pct`는 실수(0.35)입니다. Swift는 타입 엄격하므로 JSON 구조에 맞춰 정확한 타입을 지정해야 합니다.

**리뷰 포인트**: `StockTransaction`의 `id`가 `"\(timestamp)_\(code)"`인데, 같은 시각에 같은 종목을 2번 거래하면 충돌합니다. 실제로는 거의 불가능하지만, `order_no`를 id로 사용하는 것이 더 안전할 수 있습니다(다만 optional이라 nil일 수 있음).

#### SystemStatus.swift - 봇 상태

```swift
struct BotStatus: Codable {
    var statusText: String {
        guard running else { return "중지됨" }
        guard let age = ageMinutes else { return "실행 중" }
        if age < 1 { return "방금 업데이트" }
        if age < 60 { return "\(Int(age))분 전" }
        return "\(Int(age / 60))시간 전"
    }
}
```

**guard let 해설**: `ageMinutes`가 nil이면(파일이 없는 경우) "실행 중"을 반환합니다. nil이 아니면 시간 경과에 따라 사람이 읽기 쉬운 문자열을 반환합니다.

---

### 3-3. Services 레이어 (2개 파일)

#### SettingsManager.swift - 설정 관리

```swift
class SettingsManager: ObservableObject {
    static let shared = SettingsManager()  // 싱글톤

    @Published var serverURL: String {
        didSet { UserDefaults.standard.set(serverURL, forKey: "serverURL") }
    }
    ...
}
```

**@Published + didSet 해설**:
- `@Published`: 값이 변경되면 이 객체를 구독하는 SwiftUI View가 자동으로 다시 렌더링됩니다
- `didSet`: 값이 변경되면 `UserDefaults`에 저장하여 앱 재시작 후에도 유지됩니다

**싱글톤 패턴 해설**: `static let shared`로 앱 전체에서 하나의 인스턴스만 사용합니다. `TradingDashboardApp.swift`에서 `@StateObject`로 생성하고 `.environmentObject()`로 모든 View에 전달합니다.

#### APIClient.swift - 네트워크 통신

```swift
func fetch<T: Codable>(_ endpoint: String) async throws -> T {
    // 1. URL 조합
    guard let url = URL(string: "\(baseURL)\(endpoint)") else { ... }

    // 2. 요청 생성 + API Key 헤더 추가
    var request = URLRequest(url: url)
    request.setValue(settings.apiKey, forHTTPHeaderField: "X-API-Key")

    // 3. 비동기 네트워크 호출
    (data, response) = try await session.data(for: request)

    // 4. 응답 디코딩
    let apiResponse = try decoder.decode(APIResponse<T>.self, from: data)
    return apiResponse.data  // 래퍼에서 data만 추출
}
```

**제네릭 `<T: Codable>` 해설**: 호출하는 쪽에서 반환 타입을 지정합니다:
```swift
let summary: PortfolioSummary = try await apiClient.fetch("/api/v2/summary")
let positions: [StockPosition] = try await apiClient.fetch("/api/v2/stock/positions")
```
컴파일러가 `T`를 추론하여 `APIResponse<PortfolioSummary>` 또는 `APIResponse<[StockPosition]>`으로 디코딩합니다.

**에러 처리 해설**: `APIError` enum으로 에러 종류를 구분합니다:
- `notConfigured`: 서버 URL 미설정 → 설정 화면으로 유도
- `unauthorized`: API Key 틀림 → 401 응답
- `networkError`: 네트워크 끊김, 타임아웃
- `decodingError`: JSON 구조 불일치 → API 변경 시 발생 가능

**리뷰 포인트**: `session.data(for:)`의 타임아웃이 15초인데, Cloudflare Tunnel 경유 시 지연이 있을 수 있습니다. 느린 네트워크에서는 30초로 늘릴 수 있습니다.

---

### 3-4. ViewModels 레이어 (3개 파일)

#### DashboardViewModel.swift - 대시보드

```swift
@MainActor
class DashboardViewModel: ObservableObject {
    @Published var summary: PortfolioSummary?
    @Published var isLoading = false

    func loadData() async {
        isLoading = summary == nil  // 최초만 로딩 표시
        ...
    }

    func startAutoRefresh(interval: TimeInterval = 30) {
        refreshTimer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { ... }
    }
}
```

**@MainActor 해설**: Swift의 동시성 모델에서 UI 업데이트는 반드시 메인 스레드에서 해야 합니다. `@MainActor`를 클래스에 붙이면 모든 프로퍼티 접근과 메서드 호출이 자동으로 메인 스레드에서 실행됩니다.

**isLoading 로직 해설**: `isLoading = summary == nil`은 최초 로딩(summary가 아직 없을 때)에만 `true`가 됩니다. 자동 갱신 시에는 이미 summary가 있으므로 `false`가 유지되어, 사용자에게 로딩 스피너가 매번 표시되지 않습니다.

**자동 갱신 해설**: `Timer.scheduledTimer`로 30초마다 `loadData()`를 호출합니다. View의 `onAppear`에서 시작하고 `onDisappear`에서 중지하여 화면을 떠나면 불필요한 API 호출을 방지합니다.

#### CryptoViewModel.swift - 암호화폐

```swift
func loadData() async {
    async let regimeResult: CryptoRegime = apiClient.fetch("/api/v2/crypto/regime")
    async let perfResult: CryptoPerformance = apiClient.fetch("/api/v2/crypto/performance")
    async let tradesResult: [CryptoTrade] = apiClient.fetch("/api/v2/crypto/trades?limit=50")

    self.regime = try await regimeResult
    self.performance = try await perfResult
    self.trades = try await tradesResult
}
```

**async let 해설**: 3개 API를 **동시에** 호출합니다. 순차 호출이면 각각 0.5초씩 1.5초가 걸리지만, 병렬 호출이면 가장 느린 하나의 시간(~0.5초)만 소요됩니다. `try await`으로 모든 결과를 기다립니다.

**리뷰 포인트**: 3개 중 하나라도 실패하면 전체가 실패합니다. 개별 에러 처리가 필요하면 `async let` 대신 `TaskGroup`을 사용하거나 각각을 별도 do-catch로 감싸야 합니다.

#### StockViewModel.swift - 한국주식

DashboardViewModel, CryptoViewModel과 동일한 패턴.

```swift
var latestSnapshot: DailySnapshot? {
    dailyData?.snapshots.last
}
```

**computed property 해설**: `dailyData`의 마지막 스냅샷(가장 최근 날짜)을 View에서 쉽게 접근할 수 있게 합니다. View에서 `viewModel.latestSnapshot?.totalAssets`처럼 사용합니다.

---

### 3-5. Views 레이어 (12개 파일)

#### TradingDashboardApp.swift - 앱 진입점

```swift
@main
struct TradingDashboardApp: App {
    @StateObject private var settings = SettingsManager.shared

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(settings)  // 모든 하위 View에 전달
        }
    }
}
```

**@StateObject vs @ObservedObject 해설**:
- `@StateObject`: 이 View가 객체의 **소유자**. View가 재생성되어도 객체 유지
- `@ObservedObject`: 외부에서 주입받은 객체. View 재생성 시 객체도 재생성될 수 있음
- 앱 진입점에서는 `@StateObject`로 생성하고, 하위에서는 `@EnvironmentObject`로 받습니다

#### ContentView.swift - 조건부 화면 분기

```swift
if settings.isConfigured {
    TabView { ... }   // 서버 설정됨 → 3개 탭
} else {
    SettingsView(isInitialSetup: true)  // 미설정 → 설정 화면
}
```

**해설**: 앱 최초 실행 시 서버 URL이 비어있으면 설정 화면을 먼저 표시합니다. 설정 완료 후 `settings.serverURL`이 변경되면 `@Published`에 의해 자동으로 View가 재렌더링되어 TabView로 전환됩니다.

#### DashboardView.swift - 종합 대시보드

주요 구성:
1. **BotStatusSection**: 봇 상태 표시 (초록/빨간 원)
2. **PortfolioCardView** x2: 주식/암호화폐 요약 카드
3. **ErrorView**: 에러 시 재시도 버튼

```swift
.refreshable {
    await viewModel.loadData()  // Pull-to-refresh
}
```

**refreshable 해설**: iOS의 스크롤 당겨서 새로고침 기능. `async` 함수를 직접 호출할 수 있으며, 완료될 때까지 새로고침 인디케이터가 표시됩니다.

```swift
.toolbar {
    ToolbarItem(placement: .topBarTrailing) {
        ConnectionIndicator(isConnected: viewModel.isConnected)
    }
}
```

**해설**: 네비게이션 바 오른쪽에 작은 초록/빨간 원으로 서버 연결 상태를 표시합니다.

#### CryptoDetailView.swift - 암호화폐 상세

주요 컴포넌트:
1. **RegimeCardView**: 시장 레짐, 변동성, 진입 모드를 StatusBadge로 표시
2. **CryptoPerformanceCard**: 총 거래, 승률, 수익률 4개 StatItem
3. **CryptoPnLChart**: Swift Charts로 누적 수익률 선 그래프
4. **TradeListSection**: 거래 내역 리스트

```swift
// 누적 수익 계산
var cumulativeData: [(index: Int, pnl: Double)] {
    var cumulative = 0.0
    return trades.reversed().enumerated().map { i, trade in
        cumulative += trade.profitPct
        return (index: i, pnl: cumulative)
    }
}
```

**해설**: trades는 최신순 정렬이므로 `reversed()`로 시간순으로 뒤집은 뒤, 수익률을 누적 합산합니다. `[(0, 1.2), (1, 0.8), (2, -0.3)]` 형태의 배열이 되어 Charts에서 X=거래번호, Y=누적수익률로 표시됩니다.

#### StockDetailView.swift - 한국주식 상세

주요 컴포넌트:
1. **StockSummaryCard**: 총자산, 일일P&L, 누적수익률
2. **DailyPnLChartView**: 일일 손익 막대 그래프 (초록=양수, 빨강=음수)
3. **PositionListSection**: 보유 포지션 (현재가, 수익률)
4. **TransactionListSection**: 최근 거래 (매수/매도, 손익)

```swift
// 포지션이 없을 때
if !viewModel.positions.isEmpty {
    PositionListSection(positions: viewModel.positions)
} else {
    EmptyCard(message: "현재 보유 포지션이 없습니다")
}
```

#### SettingsView.swift - 설정

```swift
TextField("서버 URL", text: $settings.serverURL)
    .keyboardType(.URL)
    .autocapitalization(.none)

SecureField("API Key", text: $settings.apiKey)
```

**$binding 해설**: `$settings.serverURL`은 양방향 바인딩입니다. TextField에 입력하면 `settings.serverURL`이 업데이트되고, `SettingsManager`의 `didSet`에 의해 `UserDefaults`에도 자동 저장됩니다.

**연결 테스트 해설**: "연결 테스트" 버튼은 `/health` 엔드포인트를 호출하여 서버 접근 가능 여부를 확인합니다. API Key 인증이 필요 없는 health check를 사용하므로, 서버 URL만 올바르면 성공합니다.

---

### 3-6. Extensions & Components

#### Double+Formatting.swift

```swift
17095836.0.formattedKRW        // "17,095,836원"
17095836.0.formattedCompactKRW // "1710만"
2.35.formattedPercent           // "+2.35%"
-1.20.formattedPercent          // "-1.20%"
```

**해설**: 원화 금액과 퍼센트를 일관된 형식으로 표시합니다. `formattedCompactKRW`는 차트 Y축에 사용하여 긴 숫자가 잘리지 않게 합니다.

#### ProfitText, StatusBadge, LoadingView

재사용 컴포넌트로, 색상 규칙을 통일합니다:
- 양수: 초록색 / 음수: 빨간색
- 봇 실행중: 초록 원 / 중지: 빨간 원

---

### 3-7. 프로젝트 설정 (project.yml → xcodegen)

```yaml
name: TradingDashboard
options:
  deploymentTarget:
    iOS: "17.0"           # iOS 17 이상 (Swift Charts 지원)
targets:
  TradingDashboard:
    type: application
    platform: iOS
    sources:
      - TradingDashboard  # 이 디렉토리의 모든 .swift 파일을 포함
    settings:
      base:
        GENERATE_INFOPLIST_FILE: YES  # Info.plist 자동 생성
```

**xcodegen 해설**: `.xcodeproj` 파일은 바이너리 형태라 직접 편집이 어렵습니다. `project.yml`에 설정을 텍스트로 작성하고 `xcodegen generate` 명령으로 `.xcodeproj`를 생성합니다. 새 파일을 추가하면 `xcodegen generate`만 다시 실행하면 됩니다.

**iOS 17.0 최소 버전 이유**: Swift Charts 프레임워크가 iOS 16부터 사용 가능하지만, iOS 17에서 `#Preview` 매크로와 여러 SwiftUI 개선이 있어 17.0을 선택했습니다.

---

## 4. 데이터 흐름 상세

### 대시보드 탭 데이터 흐름

```
[iPhone 앱 시작]
    │
    ▼
ContentView: settings.isConfigured? → No → SettingsView
    │ Yes
    ▼
DashboardView.onAppear
    │
    ├─ DashboardViewModel.loadData()
    │      │
    │      ▼
    │  APIClient.fetch<PortfolioSummary>("/api/v2/summary")
    │      │
    │      ▼  HTTP GET (X-API-Key 헤더)
    │  Flask: api_v2_summary()
    │      │
    │      ▼
    │  data_loader.get_portfolio_summary()
    │      │
    │      ├─ get_stock_positions()     ← engine_state.json
    │      ├─ get_stock_state()         ← engine_state.json
    │      ├─ get_crypto_regime()       ← dynamic_factors_v3.json
    │      ├─ get_crypto_performance()  ← performance_history_v3.json
    │      ├─ get_system_status()       ← 파일 mtime 확인
    │      └─ get_stock_daily_history() ← daily_history.json
    │      │
    │      ▼
    │  JSON 응답 → APIResponse<PortfolioSummary> 디코딩
    │      │
    │      ▼
    │  viewModel.summary = 결과 → @Published → View 자동 업데이트
    │
    └─ DashboardViewModel.startAutoRefresh(30초)
           │
           ▼ (30초 후)
       loadData() 반복...
```

---

## 5. 보안 구조

```
[iPhone] ──HTTPS──▶ [Cloudflare Edge] ──encrypted──▶ [cloudflared] ──HTTP──▶ [Flask :5001]
                     │                                  │
                     │ DDoS 방어                         │ 내부 연결 (포트 미개방)
                     │ WAF                              │ 공유기 설정 불필요
                     │ SSL 자동 관리                      │ IP 노출 없음
```

| 계층 | 보호 | 현재 상태 |
|------|------|----------|
| 전송 | HTTPS (Cloudflare 자동) | Phase 2에서 적용 예정 |
| 인증 | X-API-Key 헤더 | 구현 완료, .env 설정 필요 |
| DDoS | Cloudflare 기본 방어 | Phase 2에서 적용 예정 |
| 접근 제어 | Cloudflare Access (이메일 OTP) | 미구현 (추후 선택) |

---

## 6. 알려진 제한사항 & 개선 가능 사항

### 현재 제한

1. **주식 봇 야간/주말 상태**: `get_system_status()`의 30분 임계값 때문에 장 마감 후 항상 "중지됨"으로 표시됩니다. 실제로는 정상이지만 봇이 장중에만 파일을 갱신하기 때문입니다.

2. **API Key 단순 비교**: `key != API_KEY` 문자열 비교. timing attack 이론적 취약점이 있으나 Cloudflare Tunnel 네트워크 지연으로 실질적 위험은 낮습니다.

3. **에러 처리 세분화 없음**: CryptoViewModel의 `async let` 3개 중 하나라도 실패하면 전체 에러. 부분 성공/실패 처리가 없습니다.

4. **launchd plist의 Python 경로**: 시스템 python3 사용. venv 패키지(flask 등)를 찾지 못할 수 있어 venv python 경로로 변경이 필요할 수 있습니다.

5. **StockTransaction id 충돌 가능성**: `"\(timestamp)_\(code)"`가 중복될 수 있음 (같은 시각 같은 종목).

6. **WidgetKit 미구현**: 계획에는 있지만 아직 코드가 없습니다. App Groups 설정이 선행되어야 합니다.

### 개선 아이디어

1. **장중 여부 판단**: 주식 봇 상태를 "장중이면 30분, 비장중이면 무시"로 변경
2. **hmac.compare_digest()**: API Key 비교를 타이밍 안전하게 변경
3. **개별 에러 처리**: 각 API 호출을 독립적으로 try-catch
4. **캐싱**: `data_loader`에 파일별 캐시 (mtime 변경 시에만 재로드)
5. **Push 알림**: 봇 상태 변경 시 iOS 푸시 알림 (APNs)
6. **다크모드**: 현재 시스템 설정을 따르지만, 수익/손실 색상이 다크모드에서 잘 보이는지 확인 필요

---

## 7. 즉시 해야 할 작업 (체크리스트)

- [ ] `.env`에 `DASHBOARD_API_KEY` 추가 (생성: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`)
- [ ] `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer` 실행
- [ ] Xcode에서 `010_ios_dashboard/TradingDashboard.xcodeproj` 열고 시뮬레이터 빌드
- [ ] Flask 서버 실행 후 시뮬레이터에서 서버 URL(`http://localhost:5001`) + API Key 입력
- [ ] 3개 탭 데이터 표시 확인
- [ ] Cloudflare Tunnel 설정 여부 결정 (도메인 보유 확인)
