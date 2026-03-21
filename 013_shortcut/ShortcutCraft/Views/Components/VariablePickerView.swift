import SwiftUI

struct VariablePickerView: View {
    let variables: [VariableRef]
    let onSelect: (VariableRef) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Group {
                if variables.isEmpty {
                    VStack(spacing: 12) {
                        Image(systemName: "tray")
                            .font(.system(size: 40))
                            .foregroundStyle(.tertiary)
                        Text("사용 가능한 변수가 없습니다")
                            .foregroundStyle(.secondary)
                        Text("출력이 있는 블록을 추가하면\n변수로 사용할 수 있습니다")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                            .multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    List(variables) { variable in
                        Button {
                            onSelect(variable)
                            dismiss()
                        } label: {
                            HStack(spacing: 10) {
                                Circle()
                                    .fill(variable.color)
                                    .frame(width: 12, height: 12)

                                Text(variable.displayName)
                                    .font(.system(size: 14, weight: .medium))
                                    .foregroundStyle(.primary)

                                Spacer()

                                Image(systemName: "chevron.right")
                                    .font(.system(size: 12))
                                    .foregroundStyle(.tertiary)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .navigationTitle("변수 선택")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("닫기") { dismiss() }
                }
            }
        }
    }
}
