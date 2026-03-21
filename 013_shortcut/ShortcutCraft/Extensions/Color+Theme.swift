import SwiftUI

extension Color {
    #if os(iOS)
    static let blockBackground = Color(uiColor: .systemBackground)
    static let canvasBackground = Color(uiColor: .secondarySystemBackground)
    #else
    static let blockBackground = Color(nsColor: .windowBackgroundColor)
    static let canvasBackground = Color(nsColor: .controlBackgroundColor)
    #endif

    static let dropZoneHighlight = Color.accentColor.opacity(0.2)
    static let connectionLine = Color.secondary.opacity(0.4)
}

extension ShapeStyle where Self == Color {
    static var blockShadow: Color {
        Color.black.opacity(0.08)
    }
}
