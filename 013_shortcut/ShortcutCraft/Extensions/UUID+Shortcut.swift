import Foundation

extension UUID {
    var shortId: String {
        String(uuidString.prefix(8))
    }
}
