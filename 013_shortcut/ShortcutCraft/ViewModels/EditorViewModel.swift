import SwiftUI

@MainActor
final class EditorViewModel: ObservableObject {
    @Published var document: WorkflowDocument
    @Published var selectedBlockId: UUID?
    @Published var isDragging: Bool = false
    @Published var dragTargetIndex: Int?
    @Published var validationErrors: [UUID: String] = [:]

    private let registry = BlockRegistry.shared
    private let validator = ConnectionValidator.shared
    private var undoStack: [WorkflowDocument] = []
    private var redoStack: [WorkflowDocument] = []

    var selectedBlock: BlockInstance? {
        guard let id = selectedBlockId else { return nil }
        return document.blocks.first { $0.id == id }
    }

    var selectedBlockDefinition: BlockDefinition? {
        guard let block = selectedBlock else { return nil }
        return registry.definition(for: block.definitionId)
    }

    var canUndo: Bool { !undoStack.isEmpty }
    var canRedo: Bool { !redoStack.isEmpty }
    var blockCount: Int { document.blocks.count }

    var availableVariables: [VariableRef] {
        document.blocks.compactMap { block -> VariableRef? in
            guard let def = registry.definition(for: block.definitionId),
                  def.outputType != .none,
                  !def.isControlFlowMarker else { return nil }
            return VariableRef(
                sourceBlockId: block.id,
                displayName: "\(def.name) 결과",
                colorName: def.color
            )
        }
    }

    /// Computed nesting level for each block (for indentation)
    var nestingLevels: [UUID: Int] {
        var levels: [UUID: Int] = [:]
        var depth = 0
        for block in document.blocks {
            // Otherwise/End reduce depth before rendering
            if block.isControlFlowMiddle || block.isControlFlowEnd {
                depth = max(0, depth - 1)
            }
            levels[block.id] = depth
            // Start/Otherwise increase depth after rendering
            if block.isControlFlowStart || block.isControlFlowMiddle {
                depth += 1
            }
        }
        return levels
    }

    init(document: WorkflowDocument = WorkflowDocument()) {
        self.document = document
    }

    // MARK: - Block Operations

    func addBlock(definitionId: String, at index: Int? = nil) {
        saveUndo()

        // Check if this is a control flow block that needs markers
        if BlockRegistry.controlFlowStartBlocks.contains(definitionId) {
            addControlFlowBlock(definitionId: definitionId, at: index)
            return
        }

        var paramDefaults: [String: ParameterValue] = [:]
        if let definition = registry.definition(for: definitionId) {
            for param in definition.parameters {
                if let defaultValue = param.defaultValue {
                    paramDefaults[param.id] = defaultValue
                }
            }
        }
        let block = BlockInstance(
            definitionId: definitionId,
            parameterValues: paramDefaults,
            position: index ?? document.blocks.count
        )
        if let index = index, index < document.blocks.count {
            document.blocks.insert(block, at: index)
        } else {
            document.blocks.append(block)
        }
        reindex()
        selectedBlockId = block.id
        validateConnections()
    }

    private func addControlFlowBlock(definitionId: String, at index: Int?) {
        let groupId = UUID()
        let insertAt = index ?? document.blocks.count

        var paramDefaults: [String: ParameterValue] = [:]
        if let definition = registry.definition(for: definitionId) {
            for param in definition.parameters {
                if let defaultValue = param.defaultValue {
                    paramDefaults[param.id] = defaultValue
                }
            }
        }

        // Start block
        let startBlock = BlockInstance(
            definitionId: definitionId,
            parameterValues: paramDefaults,
            groupingIdentifier: groupId,
            controlFlowMode: 0
        )

        var blocksToInsert: [BlockInstance] = [startBlock]

        // Otherwise block (for If)
        if BlockRegistry.controlFlowWithElse.contains(definitionId) {
            let otherwiseId = definitionId + "_otherwise"
            let otherwiseBlock = BlockInstance(
                definitionId: otherwiseId,
                groupingIdentifier: groupId,
                controlFlowMode: 1
            )
            blocksToInsert.append(otherwiseBlock)
        }

        // End block
        let endId: String
        if definitionId == "repeatEach" {
            endId = "repeatEach_end"
        } else {
            endId = definitionId + "_end"
        }
        let endBlock = BlockInstance(
            definitionId: endId,
            groupingIdentifier: groupId,
            controlFlowMode: 2
        )
        blocksToInsert.append(endBlock)

        // Insert all blocks
        for (offset, block) in blocksToInsert.enumerated() {
            let targetIndex = min(insertAt + offset, document.blocks.count)
            document.blocks.insert(block, at: targetIndex)
        }

        reindex()
        selectedBlockId = startBlock.id
        validateConnections()
    }

    func removeBlock(id: UUID) {
        guard let block = document.blocks.first(where: { $0.id == id }) else { return }
        saveUndo()

        // If removing a control flow block, remove all related blocks
        if let groupId = block.groupingIdentifier {
            document.blocks.removeAll { $0.groupingIdentifier == groupId }
        } else {
            document.blocks.removeAll { $0.id == id }
        }

        if selectedBlockId == id {
            selectedBlockId = nil
        }
        reindex()
        validateConnections()
    }

    func moveBlock(from source: IndexSet, to destination: Int) {
        saveUndo()
        document.blocks.move(fromOffsets: source, toOffset: destination)
        reindex()
        validateConnections()
    }

    func moveBlockByDrag(fromId: UUID, toIndex: Int) {
        guard let block = document.blocks.first(where: { $0.id == fromId }) else { return }

        // Don't allow dragging control flow markers individually
        if block.isControlFlowMarker { return }

        guard let fromIndex = document.blocks.firstIndex(where: { $0.id == fromId }) else { return }
        saveUndo()
        let removed = document.blocks.remove(at: fromIndex)
        let adjustedIndex = toIndex > fromIndex ? toIndex - 1 : toIndex
        let safeIndex = min(adjustedIndex, document.blocks.count)
        document.blocks.insert(removed, at: safeIndex)
        reindex()
        validateConnections()
    }

    func duplicateBlock(id: UUID) {
        guard let block = document.blocks.first(where: { $0.id == id }),
              let index = document.blocks.firstIndex(where: { $0.id == id }) else { return }

        // If it's a control flow start, duplicate the whole group
        if let groupId = block.groupingIdentifier, block.isControlFlowStart {
            duplicateControlFlowGroup(groupId: groupId, afterIndex: index)
            return
        }

        // Don't allow duplicating control flow markers individually
        if block.isControlFlowMarker { return }

        saveUndo()
        let copy = BlockInstance(
            definitionId: block.definitionId,
            parameterValues: block.parameterValues,
            position: index + 1
        )
        document.blocks.insert(copy, at: index + 1)
        reindex()
        selectedBlockId = copy.id
        validateConnections()
    }

    private func duplicateControlFlowGroup(groupId: UUID, afterIndex: Int) {
        let groupBlocks = document.blocks.filter { $0.groupingIdentifier == groupId }
        guard let lastIndex = document.blocks.lastIndex(where: { $0.groupingIdentifier == groupId }) else { return }

        saveUndo()
        let newGroupId = UUID()
        for (offset, original) in groupBlocks.enumerated() {
            let copy = BlockInstance(
                definitionId: original.definitionId,
                parameterValues: original.parameterValues,
                groupingIdentifier: newGroupId,
                controlFlowMode: original.controlFlowMode
            )
            document.blocks.insert(copy, at: lastIndex + 1 + offset)
        }
        reindex()
        validateConnections()
    }

    func toggleCollapse(id: UUID) {
        guard let index = document.blocks.firstIndex(where: { $0.id == id }) else { return }
        document.blocks[index].isCollapsed.toggle()
    }

    func selectBlock(_ id: UUID?) {
        selectedBlockId = id
    }

    func collapseAll() {
        for i in document.blocks.indices {
            document.blocks[i].isCollapsed = true
        }
    }

    func expandAll() {
        for i in document.blocks.indices {
            document.blocks[i].isCollapsed = false
        }
    }

    // MARK: - Parameter Updates

    func updateParameter(blockId: UUID, key: String, value: ParameterValue) {
        guard let index = document.blocks.firstIndex(where: { $0.id == blockId }) else { return }
        saveUndo()
        document.blocks[index].parameterValues[key] = value
    }

    // MARK: - Document

    func updateName(_ name: String) {
        document.name = name
    }

    func updateIcon(_ icon: String) {
        document.icon = icon
    }

    func updateColor(_ color: String) {
        document.colorName = color
    }

    func newDocument() {
        saveUndo()
        document = WorkflowDocument()
        selectedBlockId = nil
        validationErrors.removeAll()
    }

    func loadDocument(_ doc: WorkflowDocument) {
        saveUndo()
        document = doc
        selectedBlockId = nil
        validateConnections()
    }

    // MARK: - Undo/Redo

    func undo() {
        guard let previous = undoStack.popLast() else { return }
        redoStack.append(document)
        document = previous
        selectedBlockId = nil
        validateConnections()
    }

    func redo() {
        guard let next = redoStack.popLast() else { return }
        undoStack.append(document)
        document = next
        selectedBlockId = nil
        validateConnections()
    }

    private func saveUndo() {
        undoStack.append(document)
        redoStack.removeAll()
        if undoStack.count > 50 {
            undoStack.removeFirst()
        }
    }

    // MARK: - Validation

    func validateConnections() {
        validationErrors.removeAll()
        let results = validator.validate(blocks: document.blocks)
        for (index, result) in results.enumerated() where !result.isValid {
            if index + 1 < document.blocks.count {
                validationErrors[document.blocks[index + 1].id] = result.message
            }
        }
    }

    // MARK: - Helpers

    private func reindex() {
        for i in document.blocks.indices {
            document.blocks[i].position = i
        }
    }
}
