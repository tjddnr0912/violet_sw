import SwiftUI
import Charts

struct DailyActivityChart: View {
    let activities: [DailyActivity]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Daily Activity (\(activities.count) days)")
                .font(.subheadline)
                .fontWeight(.medium)

            Chart(activities) { activity in
                BarMark(
                    x: .value("Date", activity.shortDate),
                    y: .value("Messages", activity.messageCount)
                )
                .foregroundStyle(Color.claudeOrange.gradient)
                .cornerRadius(2)
            }
            .chartXAxis {
                AxisMarks(values: .automatic(desiredCount: 5)) { value in
                    AxisValueLabel()
                        .font(.caption2)
                }
            }
            .chartYAxis {
                AxisMarks(position: .leading, values: .automatic(desiredCount: 3)) { value in
                    AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5, dash: [2]))
                    AxisValueLabel()
                        .font(.caption2)
                }
            }
            .frame(height: 100)
        }
    }
}

private extension DailyActivity {
    var shortDate: String {
        // "2026-02-14" -> "2/14"
        let parts = date.split(separator: "-")
        guard parts.count == 3,
              let month = Int(parts[1]),
              let day = Int(parts[2]) else { return date }
        return "\(month)/\(day)"
    }
}
