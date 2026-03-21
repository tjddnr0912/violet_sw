import SwiftUI

struct BlockDefinition: Identifiable, Codable {
    let id: String
    let name: String
    let category: BlockCategory
    let iconName: String
    let color: String
    let inputType: IOType
    let outputType: IOType
    let parameters: [ParameterDefinition]
    let wfActionIdentifier: String
    let summary: String

    var categoryColor: Color {
        category.color
    }

    var icon: String {
        iconName
    }

    /// Control flow marker blocks (otherwise, end) are not shown in palette
    var isControlFlowMarker: Bool {
        id.hasSuffix("_otherwise") || id.hasSuffix("_end")
    }
}
