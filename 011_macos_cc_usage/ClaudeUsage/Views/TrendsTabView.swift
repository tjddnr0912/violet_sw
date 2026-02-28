import SwiftUI

struct TrendsTabView: View {
    @ObservedObject var viewModel: UsageViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Daily Activity Chart
            DailyActivityChart(
                activities: viewModel.recentDailyActivity
            )
            .padding(.bottom, 12)

            Divider().padding(.bottom, 10)

            // Hourly Pattern
            HourlyPatternChart(
                hourCounts: viewModel.hourlyPattern,
                developerType: viewModel.developerType
            )
            .padding(.bottom, 12)

            Divider().padding(.bottom, 10)

            // Milestones
            MilestonesSection(
                firstSessionDate: viewModel.firstSessionDate,
                longestSession: viewModel.stats?.longestSession,
                totalSessions: viewModel.stats?.totalSessions ?? 0,
                totalMessages: viewModel.stats?.totalMessages ?? 0,
                currentStreak: viewModel.currentStreak,
                maxStreak: viewModel.maxStreak
            )
        }
    }
}
