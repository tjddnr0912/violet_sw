import SwiftUI

@main
struct TradingDashboardApp: App {
    @StateObject private var settings = SettingsManager.shared

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(settings)
        }
    }
}
