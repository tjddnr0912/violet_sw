import Foundation

class SettingsManager: ObservableObject {
    static let shared = SettingsManager()

    @Published var serverURL: String {
        didSet { UserDefaults.standard.set(serverURL, forKey: "serverURL") }
    }

    @Published var apiKey: String {
        didSet { UserDefaults.standard.set(apiKey, forKey: "apiKey") }
    }

    @Published var refreshInterval: TimeInterval {
        didSet { UserDefaults.standard.set(refreshInterval, forKey: "refreshInterval") }
    }

    var isConfigured: Bool {
        !serverURL.isEmpty
    }

    private init() {
        self.serverURL = UserDefaults.standard.string(forKey: "serverURL") ?? ""
        self.apiKey = UserDefaults.standard.string(forKey: "apiKey") ?? ""
        self.refreshInterval = UserDefaults.standard.double(forKey: "refreshInterval")
        if self.refreshInterval == 0 { self.refreshInterval = 30 }
    }
}
