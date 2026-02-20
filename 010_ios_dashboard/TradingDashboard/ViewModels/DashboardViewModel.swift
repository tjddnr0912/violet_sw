import Foundation
import Combine

@MainActor
class DashboardViewModel: ObservableObject {
    @Published var summary: PortfolioSummary?
    @Published var isLoading = false
    @Published var error: String?
    @Published var lastRefresh: Date?
    @Published var isConnected = false

    private let apiClient: APIClient
    private var refreshTimer: Timer?

    init(apiClient: APIClient = APIClient()) {
        self.apiClient = apiClient
    }

    func loadData() async {
        isLoading = summary == nil
        error = nil

        do {
            summary = try await apiClient.fetch("/api/v2/summary")
            lastRefresh = Date()
            isConnected = true
        } catch {
            self.error = error.localizedDescription
            isConnected = false
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
