import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var settings: SettingsManager
    @State private var isTestingConnection = false
    @State private var connectionResult: Bool?
    var isInitialSetup = false

    var body: some View {
        Form {
            Section("서버 설정") {
                TextField("서버 URL", text: $settings.serverURL)
                    .keyboardType(.URL)
                    .autocapitalization(.none)
                    .textContentType(.URL)

                SecureField("API Key", text: $settings.apiKey)
                    .textContentType(.password)
            }

            Section("새로고침 간격") {
                Picker("간격", selection: $settings.refreshInterval) {
                    Text("15초").tag(15.0)
                    Text("30초").tag(30.0)
                    Text("60초").tag(60.0)
                }
                .pickerStyle(.segmented)
            }

            Section {
                Button(action: testConnection) {
                    HStack {
                        if isTestingConnection {
                            ProgressView()
                                .scaleEffect(0.8)
                        }
                        Text("연결 테스트")
                        Spacer()
                        if let result = connectionResult {
                            Image(systemName: result ? "checkmark.circle.fill" : "xmark.circle.fill")
                                .foregroundColor(result ? .green : .red)
                        }
                    }
                }
                .disabled(!settings.isConfigured || isTestingConnection)
            }
        }
        .navigationTitle(isInitialSetup ? "초기 설정" : "설정")
    }

    func testConnection() {
        isTestingConnection = true
        connectionResult = nil

        Task {
            let client = APIClient(settings: settings)
            let result = await client.testConnection()

            await MainActor.run {
                connectionResult = result
                isTestingConnection = false
            }
        }
    }
}
