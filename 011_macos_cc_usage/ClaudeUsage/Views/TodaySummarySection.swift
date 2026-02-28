import SwiftUI

struct TodaySummarySection: View {
    let sessions: Int
    let messages: Int
    let toolCalls: Int
    let totalSessions: Int
    let totalMessages: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Today's Activity")
                .font(.system(size: 13, weight: .medium))

            HStack(spacing: 0) {
                statItem(value: "\(sessions)", label: "sessions")
                Spacer()
                statItem(value: messages.formattedCompact, label: "messages")
                Spacer()
                statItem(value: toolCalls.formattedCompact, label: "tool calls")
            }

            Text("All time: \(totalSessions) sessions, \(totalMessages.formattedCompact) messages")
                .font(.system(size: 11))
                .foregroundStyle(.tertiary)
        }
    }

    private func statItem(value: String, label: String) -> some View {
        VStack(spacing: 1) {
            Text(value)
                .font(.system(size: 20, weight: .semibold, design: .rounded))
            Text(label)
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
}
