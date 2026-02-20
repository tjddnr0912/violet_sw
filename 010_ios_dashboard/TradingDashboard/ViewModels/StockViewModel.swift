import Foundation

@MainActor
class StockViewModel: ObservableObject {
    @Published var positions: [StockPosition] = []
    @Published var dailyData: StockDailyData?
    @Published var transactions: [StockTransaction] = []
    @Published var isLoading = false
    @Published var error: String?

    private let apiClient: APIClient
    private var refreshTimer: Timer?

    init(apiClient: APIClient = APIClient()) {
        self.apiClient = apiClient
    }

    func loadData() async {
        isLoading = dailyData == nil
        error = nil

        do {
            async let posResult: [StockPosition] = apiClient.fetch("/api/v2/stock/positions")
            async let dailyResult: StockDailyData = apiClient.fetch("/api/v2/stock/daily?days=30")
            async let txnResult: [StockTransaction] = apiClient.fetch("/api/v2/stock/transactions?limit=20")

            self.positions = try await posResult
            self.dailyData = try await dailyResult
            self.transactions = try await txnResult
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    var latestSnapshot: DailySnapshot? {
        dailyData?.snapshots.last
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
