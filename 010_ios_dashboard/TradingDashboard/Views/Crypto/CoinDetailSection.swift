import SwiftUI

struct CoinDetailSection: View {
    @ObservedObject var viewModel: CryptoViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("코인별 성과")
                .font(.headline)

            if viewModel.coinSummaries.isEmpty {
                Text("코인 데이터 없음")
                    .foregroundColor(.secondary)
            } else {
                // 전체 코인 요약 테이블
                AllCoinsSummaryCard(summaries: viewModel.coinSummaries)

                // 코인 선택 + 상세 뷰
                Text("코인 상세")
                    .font(.headline)

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(viewModel.coinSummaries) { summary in
                            Button {
                                Task { await viewModel.loadCoinDetail(coin: summary.coin) }
                            } label: {
                                Text(summary.coin)
                                    .font(.subheadline)
                                    .fontWeight(.bold)
                                    .padding(.horizontal, 16)
                                    .padding(.vertical, 8)
                                    .background(viewModel.selectedCoin == summary.coin ? Color.accentColor : Color(.systemGray5))
                                    .foregroundColor(viewModel.selectedCoin == summary.coin ? .white : .primary)
                                    .cornerRadius(10)
                            }
                        }
                    }
                }

                if viewModel.isCoinLoading {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                        .padding()
                } else {
                    // 가격 카드
                    if let price = viewModel.coinPrice, price.hasData {
                        CoinPriceCard(price: price)
                    }

                    // 차트
                    CoinChartView(
                        chartData: viewModel.chartData,
                        selectedInterval: viewModel.chartInterval,
                        onIntervalChange: { interval in
                            Task { await viewModel.changeChartInterval(interval) }
                        }
                    )

                    // 코인별 거래 내역
                    if !viewModel.coinTrades.isEmpty {
                        CoinTradeListSection(trades: viewModel.coinTrades)
                    }
                }
            }
        }
    }
}

struct AllCoinsSummaryCard: View {
    let summaries: [CoinSummary]

    var body: some View {
        VStack(spacing: 0) {
            // 헤더
            HStack {
                Text("코인")
                    .frame(width: 50, alignment: .leading)
                Spacer()
                Text("거래")
                    .frame(width: 40, alignment: .trailing)
                Text("승률")
                    .frame(width: 60, alignment: .trailing)
                Text("수익률")
                    .frame(width: 65, alignment: .trailing)
                Text("수익금")
                    .frame(width: 65, alignment: .trailing)
            }
            .font(.caption)
            .foregroundColor(.secondary)
            .padding(.horizontal)
            .padding(.vertical, 6)

            Divider()

            // 코인별 행
            ForEach(summaries) { s in
                HStack {
                    Text(s.coin)
                        .font(.subheadline)
                        .fontWeight(.bold)
                        .frame(width: 50, alignment: .leading)
                    Spacer()
                    Text("\(s.trades)")
                        .font(.subheadline)
                        .frame(width: 40, alignment: .trailing)
                    Text(String(format: "%.0f%%", s.winRate))
                        .font(.subheadline)
                        .foregroundColor(s.winRate >= 50 ? .green : .red)
                        .frame(width: 60, alignment: .trailing)
                    Text(String(format: "%+.1f%%", s.totalProfitPct))
                        .font(.subheadline)
                        .foregroundColor(s.totalProfitPct >= 0 ? .green : .red)
                        .frame(width: 65, alignment: .trailing)
                    Text(s.totalProfitKrw.formattedCompactKRW)
                        .font(.subheadline)
                        .foregroundColor(s.totalProfitKrw >= 0 ? .green : .red)
                        .frame(width: 65, alignment: .trailing)
                }
                .padding(.horizontal)
                .padding(.vertical, 8)

                if s.id != summaries.last?.id {
                    Divider().padding(.horizontal)
                }
            }
        }
        .padding(.vertical, 4)
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.05), radius: 5, y: 2)
    }
}

struct CoinPriceCard: View {
    let price: CoinPrice

    var body: some View {
        let closing = price.closingPrice ?? 0
        let change = price.changePct ?? 0
        let opening = price.openingPrice ?? 0
        let high = price.highPrice ?? 0
        let low = price.lowPrice ?? 0

        VStack(spacing: 8) {
            HStack {
                Text(price.coin)
                    .font(.headline)
                    .fontWeight(.bold)
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text(closing.formattedKRW)
                        .font(.title3)
                        .fontWeight(.bold)
                    Text("\(change >= 0 ? "+" : "")\(String(format: "%.2f", change))%")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundColor(change >= 0 ? .green : .red)
                }
            }

            Divider()

            HStack {
                StatItem(label: "시가", value: opening.formattedCompactKRW, color: .secondary)
                Spacer()
                StatItem(label: "고가", value: high.formattedCompactKRW, color: .green)
                Spacer()
                StatItem(label: "저가", value: low.formattedCompactKRW, color: .red)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.05), radius: 5, y: 2)
    }
}

struct CoinPerformanceCard: View {
    let summary: CoinSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("\(summary.coin) 성과")
                .font(.subheadline)
                .fontWeight(.semibold)

            HStack {
                StatItem(label: "거래", value: "\(summary.trades)회", color: .primary)
                Spacer()
                StatItem(label: "승률", value: summary.winRate.formattedPercent,
                        color: summary.winRate >= 50 ? .green : .red)
                Spacer()
                StatItem(label: "총 수익률", value: summary.totalProfitPct.formattedPercent,
                        color: summary.totalProfitPct >= 0 ? .green : .red)
                Spacer()
                StatItem(label: "수익금", value: summary.totalProfitKrw.formattedCompactKRW,
                        color: summary.totalProfitKrw >= 0 ? .green : .red)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.05), radius: 5, y: 2)
    }
}

struct CoinTradeListSection: View {
    let trades: [CryptoTrade]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("최근 거래")
                .font(.subheadline)
                .fontWeight(.semibold)

            ForEach(trades) { trade in
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(String(trade.entryTime.prefix(10)))
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                    ProfitText(value: trade.profitPct, suffix: "%")
                }
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
