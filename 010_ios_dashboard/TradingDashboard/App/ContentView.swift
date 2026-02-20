import SwiftUI

enum AppTab: String {
    case dashboard
    case crypto
    case stock
}

struct ContentView: View {
    @EnvironmentObject var settings: SettingsManager
    @State var selectedTab: AppTab = .dashboard

    var body: some View {
        if settings.isConfigured {
            TabView(selection: $selectedTab) {
                DashboardView()
                    .tabItem {
                        Label("대시보드", systemImage: "chart.pie")
                    }
                    .tag(AppTab.dashboard)

                CryptoDetailView()
                    .tabItem {
                        Label("암호화폐", systemImage: "bitcoinsign.circle")
                    }
                    .tag(AppTab.crypto)

                StockDetailView()
                    .tabItem {
                        Label("한국주식", systemImage: "chart.line.uptrend.xyaxis")
                    }
                    .tag(AppTab.stock)
            }
            .onOpenURL { url in
                guard url.scheme == "tradingdashboard",
                      url.host == "tab",
                      let tab = AppTab(rawValue: url.lastPathComponent) else { return }
                selectedTab = tab
            }
        } else {
            NavigationStack {
                SettingsView(isInitialSetup: true)
            }
        }
    }
}
