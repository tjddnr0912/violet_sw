import SwiftUI

@MainActor
final class HapticManager {
    static let shared = HapticManager()
    private let settings = SettingsManager.shared

    private init() {}

    func impact(_ style: HapticStyle = .medium) {
        guard settings.hapticFeedback else { return }
        #if os(iOS)
        switch style {
        case .light:
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
        case .medium:
            UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        case .heavy:
            UIImpactFeedbackGenerator(style: .heavy).impactOccurred()
        }
        #endif
    }

    func notification(_ type: NotificationType) {
        guard settings.hapticFeedback else { return }
        #if os(iOS)
        let generator = UINotificationFeedbackGenerator()
        switch type {
        case .success:
            generator.notificationOccurred(.success)
        case .warning:
            generator.notificationOccurred(.warning)
        case .error:
            generator.notificationOccurred(.error)
        }
        #endif
    }

    func selection() {
        guard settings.hapticFeedback else { return }
        #if os(iOS)
        UISelectionFeedbackGenerator().selectionChanged()
        #endif
    }

    enum HapticStyle {
        case light, medium, heavy
    }

    enum NotificationType {
        case success, warning, error
    }
}
