import SwiftUI

struct IconPickerView: View {
    @Binding var selectedIcon: String
    @Binding var selectedColor: String
    @Environment(\.dismiss) private var dismiss

    private let icons = [
        "star", "heart", "bolt", "flame", "leaf",
        "sun.max", "moon.fill", "cloud", "snowflake", "drop",
        "bell", "tag", "bookmark", "flag", "pin",
        "doc.text", "folder", "tray", "archivebox", "externaldrive",
        "calendar", "clock", "timer", "alarm", "stopwatch",
        "message", "envelope", "phone", "video", "mic",
        "camera", "photo", "film", "music.note", "headphones",
        "globe", "map", "location", "safari", "link",
        "magnifyingglass", "gearshape", "wrench", "hammer", "paintbrush",
        "pencil", "scissors", "paperclip", "ruler", "level",
        "person", "person.2", "figure.walk", "house", "building",
        "car", "airplane", "tram", "bus", "bicycle",
        "cart", "bag", "creditcard", "banknote", "gift",
        "gamecontroller", "puzzlepiece", "die.face.5", "trophy", "medal",
        "lightbulb", "battery.100percent", "wifi", "antenna.radiowaves.left.and.right", "bolt.shield"
    ]

    private let colors = [
        ("파랑", "blue"), ("빨강", "red"), ("초록", "green"),
        ("주황", "orange"), ("보라", "purple"), ("분홍", "pink"), ("청록", "teal")
    ]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    // Preview
                    HStack {
                        Spacer()
                        Image(systemName: selectedIcon)
                            .font(.system(size: 36))
                            .foregroundStyle(.white)
                            .frame(width: 72, height: 72)
                            .background(colorValue(selectedColor))
                            .clipShape(RoundedRectangle(cornerRadius: 18))
                        Spacer()
                    }
                    .padding(.vertical)

                    // Color picker
                    VStack(alignment: .leading, spacing: 8) {
                        Text("색상")
                            .font(.headline)

                        HStack(spacing: 10) {
                            ForEach(colors, id: \.1) { name, value in
                                Button {
                                    selectedColor = value
                                } label: {
                                    Circle()
                                        .fill(colorValue(value))
                                        .frame(width: 36, height: 36)
                                        .overlay(
                                            Circle()
                                                .stroke(Color.primary, lineWidth: selectedColor == value ? 3 : 0)
                                                .padding(2)
                                        )
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }

                    // Icon grid
                    VStack(alignment: .leading, spacing: 8) {
                        Text("아이콘")
                            .font(.headline)

                        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 7), spacing: 8) {
                            ForEach(icons, id: \.self) { icon in
                                Button {
                                    selectedIcon = icon
                                } label: {
                                    Image(systemName: icon)
                                        .font(.system(size: 18))
                                        .foregroundStyle(selectedIcon == icon ? .white : .primary)
                                        .frame(width: 40, height: 40)
                                        .background(
                                            RoundedRectangle(cornerRadius: 8)
                                                .fill(selectedIcon == icon ? colorValue(selectedColor) : Color.clear)
                                        )
                                        .overlay(
                                            RoundedRectangle(cornerRadius: 8)
                                                .stroke(Color.secondary.opacity(0.2), lineWidth: 1)
                                        )
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("아이콘 선택")
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

    private func colorValue(_ name: String) -> Color {
        switch name {
        case "red": return .red
        case "orange": return .orange
        case "green": return .green
        case "blue": return .blue
        case "purple": return .purple
        case "pink": return .pink
        case "teal": return .teal
        default: return .blue
        }
    }
}
