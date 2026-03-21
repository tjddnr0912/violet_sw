import Foundation

@MainActor
final class ConnectionValidator {
    static let shared = ConnectionValidator()
    private let registry = BlockRegistry.shared

    private init() {}

    struct ValidationResult {
        let isValid: Bool
        let message: String?

        static let valid = ValidationResult(isValid: true, message: nil)
        static func invalid(_ message: String) -> ValidationResult {
            ValidationResult(isValid: false, message: message)
        }
    }

    func validate(blocks: [BlockInstance]) -> [ValidationResult] {
        guard blocks.count > 1 else { return [] }

        var results: [ValidationResult] = []
        for i in 0..<(blocks.count - 1) {
            let current = blocks[i]
            let next = blocks[i + 1]

            guard let currentDef = registry.definition(for: current.definitionId),
                  let nextDef = registry.definition(for: next.definitionId) else {
                results.append(.invalid("알 수 없는 블록"))
                continue
            }

            if ConnectionRule.canConnect(from: currentDef.outputType, to: nextDef.inputType) {
                results.append(.valid)
            } else {
                results.append(.invalid(
                    "'\(currentDef.name)'의 출력(\(currentDef.outputType.rawValue))과 '\(nextDef.name)'의 입력(\(nextDef.inputType.rawValue))이 호환되지 않습니다"
                ))
            }
        }
        return results
    }
}
