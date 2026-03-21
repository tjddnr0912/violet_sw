import Foundation

struct BlockInstance: Identifiable, Codable, Equatable {
    let id: UUID
    let definitionId: String
    var parameterValues: [String: ParameterValue]
    var position: Int
    var isCollapsed: Bool
    var groupingIdentifier: UUID?
    var controlFlowMode: Int?  // 0=start, 1=else/otherwise, 2=end

    var isControlFlowStart: Bool { controlFlowMode == 0 }
    var isControlFlowMiddle: Bool { controlFlowMode == 1 }
    var isControlFlowEnd: Bool { controlFlowMode == 2 }
    var isControlFlowMarker: Bool { controlFlowMode != nil }

    init(
        id: UUID = UUID(),
        definitionId: String,
        parameterValues: [String: ParameterValue] = [:],
        position: Int = 0,
        isCollapsed: Bool = false,
        groupingIdentifier: UUID? = nil,
        controlFlowMode: Int? = nil
    ) {
        self.id = id
        self.definitionId = definitionId
        self.parameterValues = parameterValues
        self.position = position
        self.isCollapsed = isCollapsed
        self.groupingIdentifier = groupingIdentifier
        self.controlFlowMode = controlFlowMode
    }

    static func == (lhs: BlockInstance, rhs: BlockInstance) -> Bool {
        lhs.id == rhs.id
    }
}
