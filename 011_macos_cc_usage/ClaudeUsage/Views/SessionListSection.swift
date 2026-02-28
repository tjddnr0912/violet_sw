import SwiftUI

struct SessionListSection: View {
    let sessions: [SessionEntry]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Recent Sessions")
                .font(.subheadline)
                .fontWeight(.medium)

            if sessions.isEmpty {
                Text("No sessions found")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 8)
            } else {
                ForEach(sessions) { session in
                    HStack(alignment: .top, spacing: 8) {
                        Circle()
                            .fill(Color.claudeOrange.opacity(0.3))
                            .frame(width: 6, height: 6)
                            .padding(.top, 5)

                        VStack(alignment: .leading, spacing: 2) {
                            Text(session.summary ?? session.firstPrompt?.prefix(50).description ?? "Session")
                                .font(.caption)
                                .lineLimit(1)

                            HStack(spacing: 4) {
                                if let project = session.projectName {
                                    Text(project)
                                        .font(.caption2)
                                        .foregroundStyle(Color.claudeOrange)
                                }
                                Text("\(session.messageCount) msgs")
                                    .font(.caption2)
                                    .foregroundStyle(.tertiary)
                                Text(session.timeAgo)
                                    .font(.caption2)
                                    .foregroundStyle(.tertiary)
                            }
                        }

                        Spacer()
                    }
                }
            }
        }
    }
}
