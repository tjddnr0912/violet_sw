import SwiftUI

struct UsageMeterView: View {
    let title: String
    let subtitle: String
    let value: Int
    let maxValue: Int
    let color: Color

    private var ratio: Double {
        guard maxValue > 0 else { return 0 }
        return min(Double(value) / Double(maxValue), 1.0)
    }

    private var percentText: String {
        guard maxValue > 0 else { return "0%" }
        let pct = Int(ratio * 100)
        return "\(pct)%"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.system(size: 13, weight: .medium))
            Text(subtitle)
                .font(.system(size: 11))
                .foregroundStyle(.secondary)

            HStack(spacing: 10) {
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 3)
                            .fill(Color.primary.opacity(0.08))
                        RoundedRectangle(cornerRadius: 3)
                            .fill(color)
                            .frame(width: max(geo.size.width * ratio, ratio > 0 ? 4 : 0))
                    }
                }
                .frame(height: 8)

                Text(percentText)
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .frame(width: 40, alignment: .trailing)
            }
        }
    }
}
