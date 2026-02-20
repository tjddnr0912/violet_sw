import SwiftUI

struct PortfolioCardView: View {
    let title: String
    let icon: String
    let items: [(String, String)]
    let accentColor: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: icon)
                    .foregroundColor(accentColor)
                Text(title)
                    .font(.headline)
            }

            Divider()

            ForEach(items, id: \.0) { label, value in
                HStack {
                    Text(label)
                        .foregroundColor(.secondary)
                        .font(.subheadline)
                    Spacer()
                    Text(value)
                        .font(.subheadline)
                        .fontWeight(.medium)
                }
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.05), radius: 5, y: 2)
    }
}
