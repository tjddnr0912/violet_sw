import Foundation

extension Int {
    var formattedCompact: String {
        if self >= 1_000_000_000 {
            return String(format: "%.1fB", Double(self) / 1_000_000_000)
        } else if self >= 1_000_000 {
            return String(format: "%.1fM", Double(self) / 1_000_000)
        } else if self >= 1_000 {
            return String(format: "%.1fK", Double(self) / 1_000)
        }
        return "\(self)"
    }
}
