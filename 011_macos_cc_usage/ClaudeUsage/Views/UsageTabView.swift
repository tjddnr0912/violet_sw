import SwiftUI

struct UsageTabView: View {
    @ObservedObject var viewModel: UsageViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Today meter
            UsageMeterView(
                title: "Today",
                subtitle: viewModel.todaySubtitle,
                value: viewModel.todayMessages,
                maxValue: viewModel.todayPeakMessages,
                color: Color.claudeOrange
            )
            .padding(.bottom, 12)

            Divider().padding(.bottom, 10)

            // Weekly meter
            UsageMeterView(
                title: "Last 7 Days",
                subtitle: viewModel.weeklySubtitle,
                value: viewModel.weeklyMessages,
                maxValue: viewModel.weeklyPeakMessages,
                color: .blue
            )
            .padding(.bottom, 8)

            // Weekly comparison
            WeeklyComparisonSection(
                messageChange: viewModel.weeklyMessageChange,
                sessionChange: viewModel.weeklySessionChange,
                toolCallChange: viewModel.weeklyToolCallChange
            )
            .padding(.bottom, 12)

            Divider().padding(.bottom, 10)

            // Today's Activity
            TodaySummarySection(
                sessions: viewModel.todaySessions,
                messages: viewModel.todayMessages,
                toolCalls: viewModel.todayToolCalls,
                totalSessions: viewModel.stats?.totalSessions ?? 0,
                totalMessages: viewModel.stats?.totalMessages ?? 0
            )
            .padding(.bottom, 12)

            Divider().padding(.bottom, 10)

            // Model breakdown
            ModelBreakdownSection(
                models: viewModel.sortedModelUsage
            )
        }
    }
}
