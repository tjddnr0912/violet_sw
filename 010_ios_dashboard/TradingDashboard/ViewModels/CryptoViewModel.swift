import Foundation

@MainActor
class CryptoViewModel: ObservableObject {
    @Published var regime: CryptoRegime?
    @Published var performance: CryptoPerformance?
    @Published var trades: [CryptoTrade] = []
    @Published var isLoading = false
    @Published var error: String?

    // 코인별 상세
    @Published var coinSummaries: [CoinSummary] = []
    @Published var selectedCoin: String = "BTC"
    @Published var coinPrice: CoinPrice?
    @Published var chartData: [Candlestick] = []
    @Published var coinTrades: [CryptoTrade] = []
    @Published var chartInterval: String = "1h"
    @Published var isCoinLoading = false

    private let apiClient: APIClient
    private var refreshTimer: Timer?

    init(apiClient: APIClient = APIClient()) {
        self.apiClient = apiClient
    }

    func loadData() async {
        isLoading = regime == nil
        error = nil

        do {
            async let regimeResult: CryptoRegime = apiClient.fetch("/api/v2/crypto/regime")
            async let perfResult: CryptoPerformance = apiClient.fetch("/api/v2/crypto/performance")
            async let tradesResult: [CryptoTrade] = apiClient.fetch("/api/v2/crypto/trades?limit=50")
            async let coinsResult: [CoinSummary] = apiClient.fetch("/api/v2/crypto/coins")

            self.regime = try await regimeResult
            self.performance = try await perfResult
            self.trades = try await tradesResult
            self.coinSummaries = try await coinsResult

            if !self.coinSummaries.isEmpty && !self.coinSummaries.contains(where: { $0.coin == self.selectedCoin }) {
                self.selectedCoin = self.coinSummaries[0].coin
            }
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func loadCoinDetail(coin: String) async {
        selectedCoin = coin
        isCoinLoading = true

        // 코인 전환 시 이전 데이터 초기화
        coinPrice = nil
        chartData = []
        coinTrades = []

        // 각 API를 독립적으로 호출 (하나 실패해도 나머지는 표시)
        do {
            self.coinPrice = try await apiClient.fetch("/api/v2/crypto/price/\(coin)")
        } catch { }

        do {
            self.chartData = try await apiClient.fetch("/api/v2/crypto/chart/\(coin)?interval=\(chartInterval)")
        } catch { }

        do {
            self.coinTrades = try await apiClient.fetch("/api/v2/crypto/coins/\(coin)/trades?limit=20")
        } catch { }

        isCoinLoading = false
    }

    func changeChartInterval(_ interval: String) async {
        chartInterval = interval
        do {
            let result: [Candlestick] = try await apiClient.fetch("/api/v2/crypto/chart/\(selectedCoin)?interval=\(interval)")
            self.chartData = result
        } catch {
            // 차트 로딩 실패 무시
        }
    }

    func startAutoRefresh(interval: TimeInterval = 30) {
        stopAutoRefresh()
        refreshTimer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in
                await self?.loadData()
            }
        }
    }

    func stopAutoRefresh() {
        refreshTimer?.invalidate()
        refreshTimer = nil
    }
}
