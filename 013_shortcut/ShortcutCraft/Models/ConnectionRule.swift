import Foundation

struct ConnectionRule {
    let fromOutputType: IOType
    let toInputType: IOType
    let isAllowed: Bool
    let message: String?

    static func canConnect(from: IOType, to: IOType) -> Bool {
        if from == .any || to == .any { return true }
        if from == .none || to == .none { return false }
        return from == to
    }
}
