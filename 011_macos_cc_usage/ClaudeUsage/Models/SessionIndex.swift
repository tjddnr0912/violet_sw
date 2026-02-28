import Foundation

struct SessionIndex: Codable {
    let version: Int
    let entries: [SessionEntry]
    let originalPath: String?
}

struct SessionEntry: Codable, Identifiable {
    let sessionId: String
    let fullPath: String?
    let fileMtime: Int?
    let firstPrompt: String?
    let summary: String?
    let messageCount: Int
    let created: String
    let modified: String
    let gitBranch: String?
    let projectPath: String?
    let isSidechain: Bool?

    var id: String { sessionId }

    var createdDate: Date? {
        ISO8601DateFormatter().date(from: created)
    }

    var modifiedDate: Date? {
        ISO8601DateFormatter().date(from: modified)
    }

    var projectName: String? {
        guard let path = projectPath else { return nil }
        return URL(fileURLWithPath: path).lastPathComponent
    }

    var timeAgo: String {
        guard let date = modifiedDate else { return "" }
        let interval = Date().timeIntervalSince(date)
        if interval < 60 { return "just now" }
        if interval < 3600 { return "\(Int(interval / 60))m ago" }
        if interval < 86400 { return "\(Int(interval / 3600))h ago" }
        return "\(Int(interval / 86400))d ago"
    }
}
