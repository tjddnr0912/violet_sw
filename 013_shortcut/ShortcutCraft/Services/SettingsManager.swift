import SwiftUI

@MainActor
final class SettingsManager: ObservableObject {
    static let shared = SettingsManager()

    @AppStorage("showBlockLabels") var showBlockLabels: Bool = true
    @AppStorage("compactMode") var compactMode: Bool = false
    @AppStorage("autoSave") var autoSave: Bool = true
    @AppStorage("hapticFeedback") var hapticFeedback: Bool = true
    @AppStorage("defaultWorkflowColor") var defaultWorkflowColor: String = "blue"

    private init() {}
}
