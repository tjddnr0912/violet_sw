import SwiftUI

extension Color {
    // Claude brand colors
    static let claudeOrange = Color(red: 0.87, green: 0.55, blue: 0.30)
    static let claudeBlue = Color(red: 0.30, green: 0.55, blue: 0.87)
    static let claudeGreen = Color(red: 0.30, green: 0.75, blue: 0.50)
    static let claudePurple = Color(red: 0.60, green: 0.40, blue: 0.80)

    static func colorForModel(_ modelId: String) -> Color {
        if modelId.contains("opus") {
            return .claudeOrange
        } else if modelId.contains("sonnet") {
            return .claudeBlue
        } else if modelId.contains("haiku") {
            return .claudeGreen
        }
        return .claudePurple
    }
}
