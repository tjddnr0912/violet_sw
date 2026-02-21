import SwiftUI

struct DashboardView: View {
    @StateObject private var viewModel = DashboardViewModel()
    @EnvironmentObject var settings: SettingsManager

    var body: some View {
        NavigationStack {
            ScrollView {
                if viewModel.isLoading {
                    LoadingView()
                } else if let summary = viewModel.summary {
                    VStack(spacing: 16) {
                        BotStatusSection(status: summary.systemStatus)

                        PortfolioCardView(
                            title: "한국주식",
                            icon: "chart.line.uptrend.xyaxis",
                            items: [
                                ("총 자산", summary.stock.totalAssets.formattedKRW),
                                ("일일 P&L", summary.stock.dailyPnl.formattedKRW),
                                ("일일 수익률", summary.stock.dailyPnlPct.formattedPercent),
                                ("누적 수익률", summary.stock.totalPnlPct.formattedPercent),
                                ("포지션", "\(summary.stock.positionCount)개"),
                            ],
                            accentColor: summary.stock.dailyPnl >= 0 ? .green : .red
                        )

                        PortfolioCardView(
                            title: "암호화폐",
                            icon: "bitcoinsign.circle",
                            items: [
                                ("시장 레짐", summary.crypto.marketRegime ?? "-"),
                                ("변동성", summary.crypto.volatilityLevel ?? "-"),
                                ("총 거래", "\(summary.crypto.totalTrades ?? 0)회"),
                                ("승률", (summary.crypto.winRate ?? 0).formattedPercent),
                                ("평균 수익", (summary.crypto.avgProfitPct ?? 0).formattedPercent),
                            ],
                            accentColor: .orange
                        )
                    }
                    .padding()
                } else if let error = viewModel.error {
                    ErrorView(message: error) {
                        Task { await viewModel.loadData() }
                    }
                }
            }
            .refreshable {
                await viewModel.loadData()
            }
            .navigationTitle("Trading Dashboard")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    NavigationLink(destination: SettingsView()) {
                        Image(systemName: "gearshape")
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    ConnectionIndicator(isConnected: viewModel.isConnected)
                }
            }
            .onAppear {
                Task { await viewModel.loadData() }
                viewModel.startAutoRefresh(interval: settings.refreshInterval)
            }
            .onDisappear {
                viewModel.stopAutoRefresh()
            }
        }
    }
}

struct BotStatusSection: View {
    let status: [String: BotStatus]

    var body: some View {
        HStack(spacing: 20) {
            ForEach(Array(status.sorted(by: { $0.key < $1.key })), id: \.key) { name, bot in
                BotStatusRow(name: name == "crypto_bot" ? "암호화폐 봇" : "주식 봇", status: bot)
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
}

struct BotStatusRow: View {
    let name: String
    let status: BotStatus

    var body: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(status.indicatorColor)
                .frame(width: 10, height: 10)
            VStack(alignment: .leading, spacing: 2) {
                Text(name)
                    .font(.caption)
                    .fontWeight(.medium)
                Text(status.statusText)
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
        }
    }
}

struct ConnectionIndicator: View {
    let isConnected: Bool

    var body: some View {
        Circle()
            .fill(isConnected ? .green : .red)
            .frame(width: 8, height: 8)
    }
}
