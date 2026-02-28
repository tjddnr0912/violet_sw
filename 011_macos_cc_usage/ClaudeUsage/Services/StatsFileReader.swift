import Foundation

struct StatsFileReader {
    static let statsPath: String = {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        return "\(home)/.claude/stats-cache.json"
    }()

    static func read() -> StatsCache? {
        guard let data = FileManager.default.contents(atPath: statsPath) else {
            return nil
        }
        do {
            return try JSONDecoder().decode(StatsCache.self, from: data)
        } catch {
            print("StatsFileReader decode error: \(error)")
            return nil
        }
    }

    static func fileModificationDate() -> Date? {
        try? FileManager.default.attributesOfItem(atPath: statsPath)[.modificationDate] as? Date
    }
}
