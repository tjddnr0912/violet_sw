import SwiftUI
import Charts

struct HourlyPatternChart: View {
    let hourCounts: [(hour: Int, count: Int)]
    var developerType: (title: String, icon: String, description: String) = ("", "", "")

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Peak Hours")
                    .font(.system(size: 13, weight: .medium))

                Spacer()

                if !developerType.title.isEmpty {
                    HStack(spacing: 4) {
                        Image(systemName: developerType.icon)
                            .font(.system(size: 10))
                        Text(developerType.title)
                            .font(.system(size: 11))
                    }
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.secondary.opacity(0.1))
                    .clipShape(Capsule())
                }
            }

            if hourCounts.isEmpty {
                Text("No data yet")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 8)
            } else {
                Chart(hourCounts, id: \.hour) { item in
                    BarMark(
                        x: .value("Hour", item.hour),
                        y: .value("Sessions", item.count)
                    )
                    .foregroundStyle(barColor(for: item.hour).gradient)
                    .cornerRadius(2)
                }
                .chartXAxis {
                    AxisMarks(values: [0, 3, 6, 9, 12, 15, 18, 21]) { value in
                        AxisValueLabel {
                            if let h = value.as(Int.self) {
                                Text("\(h)")
                                    .font(.caption2)
                            }
                        }
                    }
                }
                .chartYAxis {
                    AxisMarks(position: .leading, values: .automatic(desiredCount: 3)) { _ in
                        AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5, dash: [2]))
                        AxisValueLabel()
                            .font(.caption2)
                    }
                }
                .frame(height: 80)
            }
        }
    }

    private func barColor(for hour: Int) -> Color {
        // Dawn/morning = blue, day = orange, evening = purple, night = blue
        switch hour {
        case 6..<12: return Color.claudeOrange
        case 12..<18: return Color.claudeOrange
        case 18..<22: return Color.claudePurple
        default: return Color.claudeBlue
        }
    }
}
