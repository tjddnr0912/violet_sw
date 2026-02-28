import SwiftUI

struct WeeklyComparisonSection: View {
    let messageChange: Double
    let sessionChange: Double
    let toolCallChange: Double

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("vs Last Week")
                .font(.system(size: 13, weight: .medium))

            HStack(spacing: 0) {
                changeColumn(label: "Messages", change: messageChange)
                Spacer()
                changeColumn(label: "Sessions", change: sessionChange)
                Spacer()
                changeColumn(label: "Tools", change: toolCallChange)
            }
        }
    }

    private func changeColumn(label: String, change: Double) -> some View {
        VStack(spacing: 2) {
            Text(label)
                .font(.system(size: 10))
                .foregroundStyle(.secondary)

            HStack(spacing: 2) {
                if abs(change) < 0.5 {
                    Text("—")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(.secondary)
                } else {
                    Image(systemName: change > 0 ? "arrow.up" : "arrow.down")
                        .font(.system(size: 9, weight: .bold))
                    Text("\(Int(abs(change)))%")
                        .font(.system(size: 12, weight: .medium))
                }
            }
            .foregroundStyle(changeColor(change))
        }
        .frame(maxWidth: .infinity)
    }

    private func changeColor(_ change: Double) -> Color {
        if abs(change) < 0.5 { return .secondary }
        return change > 0 ? .green : .red
    }
}
