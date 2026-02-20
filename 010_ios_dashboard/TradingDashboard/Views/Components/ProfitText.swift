import SwiftUI

struct ProfitText: View {
    let value: Double
    var suffix: String = ""

    var body: some View {
        Text("\(value >= 0 ? "+" : "")\(String(format: "%.2f", value))\(suffix)")
            .font(.subheadline)
            .fontWeight(.semibold)
            .foregroundColor(value >= 0 ? .green : .red)
    }
}
