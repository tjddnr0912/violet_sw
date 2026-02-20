import SwiftUI

struct RegimeCardView: View {
    let regime: CryptoRegime

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("시장 레짐")
                .font(.headline)

            HStack {
                StatusBadge(text: regime.regimeDisplayName, color: regimeColor)
                StatusBadge(text: regime.volatilityLevel, color: .blue)
                StatusBadge(text: regime.entryMode, color: .purple)
            }

            Divider()

            HStack {
                VStack(alignment: .leading) {
                    Text("ATR%").font(.caption).foregroundColor(.secondary)
                    Text(regime.currentAtrPct?.formattedPercent ?? "-").font(.subheadline)
                }
                Spacer()
                VStack(alignment: .leading) {
                    Text("진입 임계값").font(.caption).foregroundColor(.secondary)
                    Text("x\(regime.entryThresholdModifier, specifier: "%.1f")").font(.subheadline)
                }
                Spacer()
                VStack(alignment: .leading) {
                    Text("손절 배수").font(.caption).foregroundColor(.secondary)
                    Text("x\(regime.stopLossModifier, specifier: "%.1f")").font(.subheadline)
                }
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.05), radius: 5, y: 2)
    }

    var regimeColor: Color {
        switch regime.marketRegime {
        case "strong_bullish", "bullish": return .green
        case "neutral": return .gray
        case "bearish", "strong_bearish": return .red
        default: return .gray
        }
    }
}
