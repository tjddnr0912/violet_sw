import SwiftUI

struct SessionTabView: View {
    @ObservedObject var viewModel: UsageViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Active Session
            if let session = viewModel.activeSession {
                activeSessionCard(session)
            } else {
                Text("No active session")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 16)
            }

            Divider().padding(.vertical, 10)

            // Recent Sessions
            SessionListSection(sessions: viewModel.recentSessions)
        }
    }

    private func activeSessionCard(_ session: SessionTokenUsage) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Active Session")
                .font(.system(size: 13, weight: .medium))

            // Project + Model + Time
            HStack(spacing: 6) {
                Text(session.projectName)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(Color.claudeOrange)

                Text("•")
                    .font(.system(size: 10))
                    .foregroundStyle(.tertiary)

                Text(UsageViewModel.displayName(for: session.model))
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }

            if !session.startTimeAgo.isEmpty {
                Text("Started \(session.startTimeAgo)")
                    .font(.system(size: 11))
                    .foregroundStyle(.tertiary)
            }

            // Token stats grid
            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 8) {
                tokenStat(value: session.outputTokens, label: "Output")
                tokenStat(value: session.inputTokens, label: "Input")
                tokenStat(value: session.cacheReadTokens, label: "Cache Read")
                tokenStat(value: session.cacheWriteTokens, label: "Cache Write")
                tokenStat(value: session.messageCount, label: "Messages", isCount: true)
            }
            .padding(.top, 2)
        }
        .padding(10)
        .background(.quaternary.opacity(0.5))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func tokenStat(value: Int, label: String, isCount: Bool = false) -> some View {
        VStack(spacing: 2) {
            Text(isCount ? "\(value)" : value.formattedCompact)
                .font(.system(size: 16, weight: .semibold, design: .rounded))
            Text(label)
                .font(.system(size: 9))
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
}
