import Foundation

@MainActor
class CryptoViewModel: ObservableObject {
    @Published var regime: CryptoRegime?
    @Published var performance: CryptoPerformance?
    @Published var trades: [CryptoTrade] = []
    @Published var isLoading = false
    @Published var error: String?

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

            self.regime = try await regimeResult
            self.performance = try await perfResult
            self.trades = try await tradesResult
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
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
