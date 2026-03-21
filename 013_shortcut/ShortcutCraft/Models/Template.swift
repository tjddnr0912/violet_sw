import Foundation

struct Template: Identifiable, Codable {
    let id: String
    let name: String
    let summary: String
    let iconName: String
    let colorName: String
    let category: String
    let document: WorkflowDocument

    init(
        id: String,
        name: String,
        summary: String,
        iconName: String = "star",
        colorName: String = "blue",
        category: String = "일반",
        document: WorkflowDocument
    ) {
        self.id = id
        self.name = name
        self.summary = summary
        self.iconName = iconName
        self.colorName = colorName
        self.category = category
        self.document = document
    }
}
