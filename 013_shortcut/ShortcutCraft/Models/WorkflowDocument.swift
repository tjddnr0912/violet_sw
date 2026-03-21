import SwiftUI

struct WorkflowDocument: Identifiable, Codable {
    var id: UUID
    var name: String
    var icon: String
    var colorName: String
    var blocks: [BlockInstance]
    var variables: [VariableRef]
    var createdAt: Date
    var updatedAt: Date

    var color: Color {
        switch colorName {
        case "blue": return .blue
        case "red": return .red
        case "green": return .green
        case "orange": return .orange
        case "purple": return .purple
        case "pink": return .pink
        case "teal": return .teal
        default: return .blue
        }
    }

    init(
        id: UUID = UUID(),
        name: String = "새 워크플로우",
        icon: String = "star",
        colorName: String = "blue",
        blocks: [BlockInstance] = [],
        variables: [VariableRef] = [],
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.name = name
        self.icon = icon
        self.colorName = colorName
        self.blocks = blocks
        self.variables = variables
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }
}
