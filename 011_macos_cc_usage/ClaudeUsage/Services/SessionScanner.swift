import Foundation

struct SessionScanner {
    static let projectsPath: String = {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        return "\(home)/.claude/projects"
    }()

    static func scanAllSessions() -> [SessionEntry] {
        let fm = FileManager.default
        guard let projectDirs = try? fm.contentsOfDirectory(atPath: projectsPath) else {
            return []
        }

        var allEntries: [SessionEntry] = []

        for dir in projectDirs {
            let indexPath = "\(projectsPath)/\(dir)/sessions-index.json"
            guard let data = fm.contents(atPath: indexPath) else { continue }
            guard let index = try? JSONDecoder().decode(SessionIndex.self, from: data) else { continue }
            allEntries.append(contentsOf: index.entries)
        }

        // Sort by modified date descending
        allEntries.sort { a, b in
            guard let dateA = a.modifiedDate, let dateB = b.modifiedDate else { return false }
            return dateA > dateB
        }

        return allEntries
    }

    static func recentSessions(limit: Int = 5) -> [SessionEntry] {
        Array(scanAllSessions().prefix(limit))
    }
}
