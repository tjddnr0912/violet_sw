import SwiftUI
import Charts

struct CryptoDetailView: View {
    @StateObject private var viewModel = CryptoViewModel()
    @EnvironmentObject var settings: SettingsManager

    var body: some View {
        NavigationStack {
            ScrollView {
                if viewModel.isLoading {
                    LoadingView()
                } else {
                    VStack(spacing: 16) {
                        if let regime = viewModel.regime {
                            RegimeCardView(regime: regime)
                        }

                        if let perf = viewModel.performance {
                            CryptoPerformanceCard(performance: perf)
                        }

                        if !viewModel.trades.isEmpty {
                            CryptoPnLChart(trades: viewModel.trades)
                        }

                        CoinDetailSection(viewModel: viewModel)

                        if !viewModel.trades.isEmpty {
                            TradeListSection(trades: viewModel.trades)
                        }
                    }
                    .padding()
                }
            }
            .refreshable { await viewModel.loadData() }
            .navigationTitle("암호화폐")
            .onAppear {
                Task {
                    await viewModel.loadData()
                    await viewModel.loadCoinDetail(coin: viewModel.selectedCoin)
                }
                viewModel.startAutoRefresh(interval: settings.refreshInterval)
            }
            .onDisappear { viewModel.stopAutoRefresh() }
        }
    }
}

struct CryptoPerformanceCard: View {
    let performance: CryptoPerformance

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("성과 요약")
                .font(.headline)

            Divider()

            HStack {
                StatItem(label: "총 거래", value: "\(performance.totalTrades)회", color: .primary)
                Spacer()
                StatItem(label: "승률", value: performance.winRate.formattedPercent,
                        color: performance.winRate >= 50 ? .green : .red)
                Spacer()
                StatItem(label: "총 수익률", value: performance.totalProfitPct.formattedPercent,
                        color: performance.totalProfitPct >= 0 ? .green : .red)
                Spacer()
                StatItem(label: "평균 수익", value: performance.avgProfitPct.formattedPercent,
                        color: performance.avgProfitPct >= 0 ? .green : .red)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.05), radius: 5, y: 2)
    }
}

struct CryptoPnLChart: View {
    let trades: [CryptoTrade]

    var cumulativeData: [(index: Int, pnl: Double)] {
        var cumulative = 0.0
        return trades.reversed().enumerated().map { i, trade in
            cumulative += trade.profitPct
            return (index: i, pnl: cumulative)
        }
    }

    var body: some View {
        VStack(alignment: .leading) {
            Text("누적 수익률")
                .font(.headline)

            Chart(cumulativeData, id: \.index) { point in
                LineMark(
                    x: .value("거래", point.index),
                    y: .value("수익률", point.pnl)
                )
                .foregroundStyle(point.pnl >= 0 ? .green : .red)

                AreaMark(
                    x: .value("거래", point.index),
                    y: .value("수익률", point.pnl)
                )
                .foregroundStyle(
                    .linearGradient(
                        colors: [.green.opacity(0.2), .clear],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
            }
            .frame(height: 200)
            .chartYAxis {
                AxisMarks(position: .leading) { value in
                    AxisGridLine()
                    AxisValueLabel {
                        if let v = value.as(Double.self) {
                            Text("\(v, specifier: "%.1f")%")
                        }
                    }
                }
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.05), radius: 5, y: 2)
    }
}

struct TradeListSection: View {
    let trades: [CryptoTrade]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("거래 내역")
                .font(.headline)

            ForEach(trades) { trade in
                CryptoTradeRow(trade: trade)
                if trade.id != trades.last?.id {
                    Divider()
                }
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.05), radius: 5, y: 2)
    }
}

struct CryptoTradeRow: View {
    let trade: CryptoTrade

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(trade.coin)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Text(String(trade.entryTime.prefix(10)))
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Spacer()

            ProfitText(value: trade.profitPct, suffix: "%")
        }
    }
}
