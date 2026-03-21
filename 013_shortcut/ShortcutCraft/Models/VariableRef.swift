import SwiftUI

struct VariableRef: Identifiable, Codable, Equatable, Hashable {
    let id: UUID
    let sourceBlockId: UUID
    let displayName: String
    let colorName: String

    var color: Color {
        switch colorName {
        case "blue": return .blue
        case "green": return .green
        case "orange": return .orange
        case "purple": return .purple
        case "pink": return .pink
        case "teal": return .teal
        case "red": return .red
        default: return .gray
        }
    }

    init(
        id: UUID = UUID(),
        sourceBlockId: UUID,
        displayName: String,
        colorName: String = "blue"
    ) {
        self.id = id
        self.sourceBlockId = sourceBlockId
        self.displayName = displayName
        self.colorName = colorName
    }
}
