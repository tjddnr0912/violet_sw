import SwiftUI

struct SettingsView: View {
    @ObservedObject private var settings = SettingsManager.shared
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("에디터") {
                    Toggle("블록 라벨 표시", isOn: $settings.showBlockLabels)
                    Toggle("컴팩트 모드", isOn: $settings.compactMode)
                }

                Section("저장") {
                    Toggle("자동 저장", isOn: $settings.autoSave)
                }

                #if os(iOS)
                Section("피드백") {
                    Toggle("햅틱 피드백", isOn: $settings.hapticFeedback)
                }
                #endif

                Section("기본값") {
                    Picker("워크플로우 색상", selection: $settings.defaultWorkflowColor) {
                        Text("파랑").tag("blue")
                        Text("빨강").tag("red")
                        Text("초록").tag("green")
                        Text("주황").tag("orange")
                        Text("보라").tag("purple")
                        Text("분홍").tag("pink")
                        Text("청록").tag("teal")
                    }
                }

                Section("정보") {
                    HStack {
                        Text("버전")
                        Spacer()
                        Text("1.0.0")
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("설정")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("완료") { dismiss() }
                }
            }
        }
    }
}

#Preview {
    SettingsView()
}
