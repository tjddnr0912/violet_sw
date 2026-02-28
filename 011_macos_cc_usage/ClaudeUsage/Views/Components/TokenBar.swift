import SwiftUI

struct TokenBar: View {
    let outputTokens: Int
    let cacheTokens: Int
    let maxTokens: Int
    let color: Color

    private var outputRatio: Double {
        guard maxTokens > 0 else { return 0 }
        return min(Double(outputTokens) / Double(maxTokens), 1.0)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    // Background
                    RoundedRectangle(cornerRadius: 3)
                        .fill(.quaternary)

                    // Output bar
                    RoundedRectangle(cornerRadius: 3)
                        .fill(color)
                        .frame(width: max(geo.size.width * outputRatio, 2))
                }
            }
            .frame(height: 6)

            HStack {
                Text("\(outputTokens.formattedCompact) output")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Spacer()
                Text("\(cacheTokens.formattedCompact) cache")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
    }
}
