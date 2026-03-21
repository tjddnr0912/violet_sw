import Foundation

@MainActor
struct BlockToWFConverter {
    let registry: BlockRegistry

    func convert(blocks: [BlockInstance]) -> [WFWorkflowPlist.WFAction] {
        blocks.compactMap { convert(block: $0) }
    }

    func convert(block: BlockInstance) -> WFWorkflowPlist.WFAction? {
        guard let definition = registry.definition(for: block.definitionId) else {
            return nil
        }

        var params: [String: Any] = [:]

        for (key, value) in block.parameterValues {
            switch value {
            case .text(let s):
                params[key] = s
            case .number(let n):
                params[key] = n
            case .boolean(let b):
                params[key] = b
            case .enumValue(let s):
                params[key] = convertEnumValue(key: key, value: s, definition: definition)
            case .variable:
                break
            case .date:
                break
            }
        }

        // Fill defaults for missing required params
        for paramDef in definition.parameters where paramDef.isRequired {
            if params[paramDef.id] == nil, let defaultVal = paramDef.defaultValue {
                switch defaultVal {
                case .text(let s): params[paramDef.id] = s
                case .number(let n): params[paramDef.id] = n
                case .boolean(let b): params[paramDef.id] = b
                case .enumValue(let s): params[paramDef.id] = s
                default: break
                }
            }
        }

        // Control flow: GroupingIdentifier + WFControlFlowMode
        if let groupId = block.groupingIdentifier {
            params["GroupingIdentifier"] = groupId.uuidString
        }
        if let mode = block.controlFlowMode {
            params["WFControlFlowMode"] = mode
        }

        return WFWorkflowPlist.WFAction(
            identifier: definition.wfActionIdentifier,
            parameters: params
        )
    }

    private func convertEnumValue(key: String, value: String, definition: BlockDefinition) -> Any {
        if key == "WFCondition" {
            switch value {
            case "같음": return 4
            case "같지 않음": return 5
            case "포함": return 99
            case "포함하지 않음": return 999
            case "보다 큼": return 2
            case "보다 작음": return 3
            default: return 4
            }
        }
        return value
    }
}
