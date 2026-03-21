import SwiftUI

struct ConnectionLineView: View {
    var hasError: Bool = false

    private var lineColor: Color {
        hasError ? .orange.opacity(0.6) : Color.connectionLine
    }

    var body: some View {
        VStack(spacing: 0) {
            Rectangle()
                .fill(lineColor)
                .frame(width: 2, height: 16)

            Circle()
                .fill(lineColor)
                .frame(width: 6, height: 6)

            Rectangle()
                .fill(lineColor)
                .frame(width: 2, height: 8)
        }
    }
}
