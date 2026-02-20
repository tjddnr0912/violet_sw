import SwiftUI
import Charts

struct DailyPnLChartView: View {
    let snapshots: [DailySnapshot]

    var body: some View {
        VStack(alignment: .leading) {
            Text("일일 손익")
                .font(.headline)

            Chart(snapshots) { snapshot in
                BarMark(
                    x: .value("날짜", String(snapshot.date.suffix(5))),
                    y: .value("P&L", snapshot.dailyPnl)
                )
                .foregroundStyle(snapshot.dailyPnl >= 0 ? .green : .red)
            }
            .frame(height: 200)
            .chartYAxis {
                AxisMarks(position: .leading) { value in
                    AxisGridLine()
                    AxisValueLabel {
                        if let v = value.as(Int.self) {
                            Text(Double(v).formattedCompactKRW)
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
