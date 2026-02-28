import SwiftUI

struct MilestonesSection: View {
    let firstSessionDate: Date?
    let longestSession: LongestSession?
    let totalSessions: Int
    let totalMessages: Int
    let currentStreak: Int
    let maxStreak: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Milestones")
                .font(.system(size: 13, weight: .medium))

            VStack(alignment: .leading, spacing: 6) {
                // Streak
                if currentStreak > 0 || maxStreak > 0 {
                    streakRow()
                }

                // First use
                if let date = firstSessionDate {
                    milestoneRow(
                        icon: "calendar",
                        text: "First use: \(formattedDate(date))",
                        detail: daysAgo(from: date)
                    )
                }

                // Longest session (duration is in milliseconds)
                if let longest = longestSession {
                    milestoneRow(
                        icon: "trophy",
                        text: "Longest: \(longest.messageCount.formattedCompact) msgs",
                        detail: formattedDuration(longest.duration / 1000)
                    )
                }

                // Total stats
                milestoneRow(
                    icon: "chart.bar",
                    text: "Total: \(totalSessions) sessions",
                    detail: "\(totalMessages.formattedCompact) messages"
                )
            }
        }
    }

    private func streakRow() -> some View {
        HStack(spacing: 8) {
            Image(systemName: "flame")
                .font(.system(size: 11))
                .foregroundStyle(.orange)
                .frame(width: 16)

            Text("Current streak: \(currentStreak) days")
                .font(.system(size: 12))

            Spacer()

            Text("Best: \(maxStreak)")
                .font(.system(size: 11))
                .foregroundStyle(.tertiary)
        }
    }

    private func milestoneRow(icon: String, text: String, detail: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
                .frame(width: 16)

            Text(text)
                .font(.system(size: 12))

            Spacer()

            Text(detail)
                .font(.system(size: 11))
                .foregroundStyle(.tertiary)
        }
    }

    private func formattedDate(_ date: Date) -> String {
        let fmt = DateFormatter()
        fmt.dateFormat = "MMM d, yyyy"
        return fmt.string(from: date)
    }

    private func daysAgo(from date: Date) -> String {
        let days = Calendar.current.dateComponents([.day], from: date, to: Date()).day ?? 0
        return "\(days)d ago"
    }

    private func formattedDuration(_ seconds: Int) -> String {
        if seconds >= 86400 {
            let days = Double(seconds) / 86400
            return String(format: "%.1f days", days)
        } else if seconds >= 3600 {
            let hours = Double(seconds) / 3600
            return String(format: "%.1f hrs", hours)
        } else {
            let mins = seconds / 60
            return "\(mins) min"
        }
    }
}
