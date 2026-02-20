import Foundation

struct BotStatus: Codable {
    let running: Bool
    let lastUpdate: String?
    let ageMinutes: Double?

    enum CodingKeys: String, CodingKey {
        case running
        case lastUpdate = "last_update"
        case ageMinutes = "age_minutes"
    }

    var statusText: String {
        guard running else { return "중지됨" }
        guard let age = ageMinutes else { return "실행 중" }
        if age < 1 { return "방금 업데이트" }
        if age < 60 { return "\(Int(age))분 전" }
        return "\(Int(age / 60))시간 전"
    }
}
