import SwiftUI

struct ModelBreakdownSection: View {
    let models: [(model: String, detail: ModelUsageDetail)]

    private var totalOutput: Int {
        models.map(\.detail.outputTokens).reduce(0, +)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Model Usage")
                .font(.system(size: 13, weight: .medium))

            ForEach(models, id: \.model) { item in
                modelRow(item: item)
            }
        }
    }

    private func modelRow(item: (model: String, detail: ModelUsageDetail)) -> some View {
        let ratio = totalOutput > 0
            ? CGFloat(item.detail.outputTokens) / CGFloat(totalOutput)
            : 0

        return VStack(alignment: .leading, spacing: 4) {
            HStack {
                Circle()
                    .fill(Color.colorForModel(item.model))
                    .frame(width: 7, height: 7)
                Text(UsageViewModel.displayName(for: item.model))
                    .font(.system(size: 12, weight: .medium))
                Spacer()
                Text(item.detail.outputTokens.formattedCompact)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                Text("output")
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
            }

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 2.5)
                        .fill(Color.primary.opacity(0.06))
                    RoundedRectangle(cornerRadius: 2.5)
                        .fill(Color.colorForModel(item.model))
                        .frame(width: max(geo.size.width * ratio, ratio > 0 ? 4 : 0))
                }
            }
            .frame(height: 5)

            HStack(spacing: 8) {
                tokenLabel(item.detail.inputTokens.formattedCompact, "input")
                tokenLabel(item.detail.cacheReadInputTokens.formattedCompact, "cache read")
                tokenLabel(item.detail.cacheCreationInputTokens.formattedCompact, "cache write")
            }
        }
    }

    private func tokenLabel(_ value: String, _ label: String) -> some View {
        HStack(spacing: 2) {
            Text(value)
                .font(.system(size: 10, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
            Text(label)
                .font(.system(size: 10))
                .foregroundStyle(.tertiary)
        }
    }
}
