import SwiftUI
import Charts

struct StockDetailView: View {
    @StateObject private var viewModel = StockViewModel()
    @EnvironmentObject var settings: SettingsManager

    var body: some View {
        NavigationStack {
            ScrollView {
                if viewModel.isLoading {
                    LoadingView()
                } else {
                    VStack(spacing: 16) {
                        if let snapshot = viewModel.latestSnapshot {
                            StockSummaryCard(snapshot: snapshot,
                                           initialCapital: viewModel.dailyData?.initialCapital ?? 0)
                        }

                        if let data = viewModel.dailyData, !data.snapshots.isEmpty {
                            DailyPnLChartView(snapshots: data.snapshots)
                        }

                        if !viewModel.positions.isEmpty {
                            PositionListSection(positions: viewModel.positions)
                        } else {
                            EmptyCard(message: "현재 보유 포지션이 없습니다")
                        }

                        if !viewModel.transactions.isEmpty {
                            TransactionListSection(transactions: viewModel.transactions)
                        }
                    }
                    .padding()
                }
            }
            .refreshable { await viewModel.loadData() }
            .navigationTitle("한국주식")
            .onAppear {
                Task { await viewModel.loadData() }
                viewModel.startAutoRefresh(interval: settings.refreshInterval)
            }
            .onDisappear { viewModel.stopAutoRefresh() }
        }
    }
}

struct StockSummaryCard: View {
    let snapshot: DailySnapshot
    let initialCapital: Int

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Text("총 자산")
                    .foregroundColor(.secondary)
                Spacer()
                Text(Double(snapshot.totalAssets).formattedKRW)
                    .font(.title2)
                    .fontWeight(.bold)
            }

            Divider()

            HStack {
                StatItem(label: "일일 P&L", value: Double(snapshot.dailyPnl).formattedKRW,
                        color: snapshot.dailyPnl >= 0 ? .green : .red)
                Spacer()
                StatItem(label: "일일 수익률", value: snapshot.dailyPnlPct.formattedPercent,
                        color: snapshot.dailyPnlPct >= 0 ? .green : .red)
                Spacer()
                StatItem(label: "누적 수익률", value: snapshot.totalPnlPct.formattedPercent,
                        color: snapshot.totalPnlPct >= 0 ? .green : .red)
            }

            HStack {
                StatItem(label: "초기 자본", value: Double(initialCapital).formattedKRW, color: .secondary)
                Spacer()
                StatItem(label: "포지션", value: "\(snapshot.positionCount)개", color: .secondary)
                Spacer()
                StatItem(label: "오늘 거래", value: "\(snapshot.tradesToday)건", color: .secondary)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.05), radius: 5, y: 2)
    }
}

struct StatItem: View {
    let label: String
    let value: String
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption)
                .foregroundColor(.secondary)
            Text(value)
                .font(.subheadline)
                .fontWeight(.medium)
                .foregroundColor(color)
        }
    }
}

struct PositionListSection: View {
    let positions: [StockPosition]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("보유 포지션")
                .font(.headline)

            ForEach(positions) { position in
                StockPositionRow(position: position)
                if position.id != positions.last?.id {
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

struct StockPositionRow: View {
    let position: StockPosition

    var body: some View {
        VStack(spacing: 6) {
            // 상단: 종목명+코드|수량 | 수익률
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(position.name)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                    Text("\(position.code) | \(position.quantity)주")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                Spacer()
                if let pct = position.profitPct {
                    ProfitText(value: pct, suffix: "%")
                }
            }

            // 하단: 평균단가 | 현재가격 | 수익금액
            HStack {
                VStack(alignment: .leading, spacing: 1) {
                    Text("평균단가")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                    Text(position.entryPrice.formattedKRW)
                        .font(.caption)
                        .fontWeight(.medium)
                }
                Spacer()
                VStack(spacing: 1) {
                    Text("현재가")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                    Text(position.currentPrice.formattedKRW)
                        .font(.caption)
                        .fontWeight(.medium)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 1) {
                    Text("수익금")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                    if let krw = position.profitKrw {
                        Text("\(krw >= 0 ? "+" : "")\(krw.formattedKRW)")
                            .font(.caption)
                            .fontWeight(.medium)
                            .foregroundColor(krw >= 0 ? .green : .red)
                    } else {
                        Text("-")
                            .font(.caption)
                    }
                }
            }
            .padding(.top, 2)
        }
    }
}

struct TransactionListSection: View {
    let transactions: [StockTransaction]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("최근 거래")
                .font(.headline)

            ForEach(transactions) { txn in
                StockTransactionRow(transaction: txn)
                if txn.id != transactions.last?.id {
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

struct StockTransactionRow: View {
    let transaction: StockTransaction

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(transaction.type)
                        .font(.caption)
                        .fontWeight(.bold)
                        .foregroundColor(transaction.type == "BUY" ? .green : .red)
                    Text(transaction.name)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                }
                Text("\(transaction.date) | \(transaction.quantity)주")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 4) {
                Text(transaction.amount.formattedKRW)
                    .font(.subheadline)
                if let pnl = transaction.pnl {
                    ProfitText(value: pnl, suffix: "원")
                }
            }
        }
    }
}
