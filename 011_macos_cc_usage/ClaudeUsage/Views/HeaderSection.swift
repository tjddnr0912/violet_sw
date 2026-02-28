import SwiftUI

struct HeaderSection: View {
    let planType: String

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text("Plan Usage Limits")
                .font(.system(size: 15, weight: .semibold))
            Spacer()
            Text(planType)
                .font(.system(size: 11, weight: .medium))
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(Color.claudeOrange.opacity(0.12))
                .foregroundStyle(Color.claudeOrange)
                .clipShape(Capsule())
        }
    }
}
