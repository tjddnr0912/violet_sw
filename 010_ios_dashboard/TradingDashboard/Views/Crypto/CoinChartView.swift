import SwiftUI
import Charts

struct CoinChartView: View {
    let chartData: [Candlestick]
    let selectedInterval: String
    let onIntervalChange: (String) -> Void

    private let intervals = ["5m", "30m", "1h", "6h", "1d"]
    private let intervalLabels = ["5분", "30분", "1시간", "6시간", "1일"]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("가격 차트")
                .font(.headline)

            // 인터벌 선택
            HStack(spacing: 4) {
                ForEach(Array(zip(intervals, intervalLabels)), id: \.0) { interval, label in
                    Button(label) {
                        onIntervalChange(interval)
                    }
                    .font(.caption)
                    .fontWeight(selectedInterval == interval ? .bold : .regular)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(selectedInterval == interval ? Color.accentColor : Color(.systemGray5))
                    .foregroundColor(selectedInterval == interval ? .white : .primary)
                    .cornerRadius(8)
                }
            }

            if chartData.isEmpty {
                Text("차트 데이터 없음")
                    .foregroundColor(.secondary)
                    .frame(height: 200)
                    .frame(maxWidth: .infinity)
            } else {
                Chart(chartData) { candle in
                    LineMark(
                        x: .value("시간", Date(timeIntervalSince1970: Double(candle.timestamp) / 1000)),
                        y: .value("가격", candle.close)
                    )
                    .foregroundStyle(.blue)
                    .lineStyle(StrokeStyle(lineWidth: 1.5))

                    AreaMark(
                        x: .value("시간", Date(timeIntervalSince1970: Double(candle.timestamp) / 1000)),
                        y: .value("가격", candle.close)
                    )
                    .foregroundStyle(
                        .linearGradient(
                            colors: [.blue.opacity(0.15), .clear],
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
                                if v >= 1_000_000 {
                                    Text("\(v / 1_000_000, specifier: "%.1f")M")
                                } else if v >= 1_000 {
                                    Text("\(v / 1_000, specifier: "%.0f")K")
                                } else {
                                    Text("\(v, specifier: "%.0f")")
                                }
                            }
                        }
                    }
                }
                .chartXAxis {
                    AxisMarks { value in
                        AxisGridLine()
                        AxisValueLabel(format: .dateTime.hour().minute())
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
