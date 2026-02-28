import Foundation

// MARK: - Live Stats Result

struct LiveStats {
    struct DayStats {
        var sessionIds: Set<String> = []
        var messageCount: Int = 0
        var toolCallCount: Int = 0
    }

    var dailyStats: [String: DayStats] = [:]
    var modelUsage: [String: ModelUsageDetail] = [:]
    var hourCounts: [String: Int] = [:]

    var totalSessions: Int {
        var all = Set<String>()
        for day in dailyStats.values {
            all.formUnion(day.sessionIds)
        }
        return all.count
    }

    var totalMessages: Int {
        dailyStats.values.map(\.messageCount).reduce(0, +)
    }
}

// MARK: - JSONL Live Parser

struct JSONLLiveParser {

    static let projectsPath: String = {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        return "\(home)/.claude/projects"
    }()

    /// Parse all JSONL files with activity after the cutoff date.
    /// Runs on a background thread — caller is responsible for dispatching.
    static func parseLiveStats(afterDate cutoffDate: String) -> LiveStats {
        let fm = FileManager.default
        guard let projectDirs = try? fm.contentsOfDirectory(atPath: projectsPath) else {
            print("[JSONLLiveParser] ERROR: cannot read projectsPath: \(projectsPath)")
            return LiveStats()
        }

        // Convert cutoff date string to Date for mtime comparison
        let dateFmt = DateFormatter()
        dateFmt.dateFormat = "yyyy-MM-dd"
        let cutoffTime = dateFmt.date(from: cutoffDate) ?? Date.distantPast

        var result = LiveStats()
        for dir in projectDirs {
            let dirPath = "\(projectsPath)/\(dir)"
            guard let files = try? fm.contentsOfDirectory(atPath: dirPath) else { continue }

            for file in files where file.hasSuffix(".jsonl") {
                let filePath = "\(dirPath)/\(file)"

                // Skip files not modified after cutoff (70% skip expected)
                guard let attrs = try? fm.attributesOfItem(atPath: filePath),
                      let modDate = attrs[.modificationDate] as? Date,
                      modDate > cutoffTime else { continue }

                parseFile(at: filePath, cutoffDate: cutoffDate, into: &result)
            }
        }

        return result
    }

    // MARK: - Per-file parsing

    private static func parseFile(at path: String, cutoffDate: String, into result: inout LiveStats) {
        guard let data = FileManager.default.contents(atPath: path),
              let content = String(data: data, encoding: .utf8) else { return }

        let lines = content.components(separatedBy: .newlines)

        var sessionId = ""
        var currentDate = ""
        var currentHour = ""

        // Reusable formatters
        let isoFrac = ISO8601DateFormatter()
        isoFrac.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let isoPlain = ISO8601DateFormatter()
        isoPlain.formatOptions = [.withInternetDateTime]
        let calendar = Calendar.current
        let dateFmt = DateFormatter()
        dateFmt.dateFormat = "yyyy-MM-dd"

        // Assistant message dedup: message.id -> last seen entry
        struct AssistantEntry {
            let model: String
            let inputTokens: Int
            let outputTokens: Int
            let cacheReadTokens: Int
            let cacheWriteTokens: Int
            let toolCallCount: Int
            let date: String
        }
        var assistantMap: [String: AssistantEntry] = [:]

        for line in lines {
            guard !line.isEmpty,
                  let lineData = line.data(using: .utf8),
                  let obj = try? JSONSerialization.jsonObject(with: lineData) as? [String: Any] else {
                continue
            }

            // Extract sessionId from first line that has it
            if sessionId.isEmpty, let sid = obj["sessionId"] as? String {
                sessionId = sid
            }

            // Parse timestamp -> local date & hour
            if let ts = obj["timestamp"] as? String {
                if let date = isoFrac.date(from: ts) ?? isoPlain.date(from: ts) {
                    let comps = calendar.dateComponents([.year, .month, .day, .hour], from: date)
                    currentDate = String(format: "%04d-%02d-%02d", comps.year!, comps.month!, comps.day!)
                    currentHour = String(comps.hour!)
                }
            }

            // Skip entries on or before cutoff date
            guard currentDate > cutoffDate else { continue }

            let type = obj["type"] as? String

            // User messages: count + hour tracking
            if type == "user" {
                result.dailyStats[currentDate, default: .init()].messageCount += 1
                result.dailyStats[currentDate, default: .init()].sessionIds.insert(sessionId)
                if !currentHour.isEmpty {
                    result.hourCounts[currentHour, default: 0] += 1
                }
            }

            // Assistant messages: dedup by message.id (last wins)
            if type == "assistant", let message = obj["message"] as? [String: Any] {
                guard let messageId = message["id"] as? String else { continue }
                let model = message["model"] as? String ?? ""
                let usage = message["usage"] as? [String: Any] ?? [:]

                var toolCalls = 0
                if let content = message["content"] as? [[String: Any]] {
                    for item in content where item["type"] as? String == "tool_use" {
                        toolCalls += 1
                    }
                }

                // Overwrite = keep last occurrence (final streaming value)
                assistantMap[messageId] = AssistantEntry(
                    model: model,
                    inputTokens: usage["input_tokens"] as? Int ?? 0,
                    outputTokens: usage["output_tokens"] as? Int ?? 0,
                    cacheReadTokens: usage["cache_read_input_tokens"] as? Int ?? 0,
                    cacheWriteTokens: usage["cache_creation_input_tokens"] as? Int ?? 0,
                    toolCallCount: toolCalls,
                    date: currentDate
                )
            }
        }

        // Aggregate deduplicated assistant messages into result
        for (_, entry) in assistantMap {
            // Model usage
            if !entry.model.isEmpty {
                let prev = result.modelUsage[entry.model]
                result.modelUsage[entry.model] = ModelUsageDetail(
                    inputTokens: (prev?.inputTokens ?? 0) + entry.inputTokens,
                    outputTokens: (prev?.outputTokens ?? 0) + entry.outputTokens,
                    cacheReadInputTokens: (prev?.cacheReadInputTokens ?? 0) + entry.cacheReadTokens,
                    cacheCreationInputTokens: (prev?.cacheCreationInputTokens ?? 0) + entry.cacheWriteTokens,
                    webSearchRequests: nil,
                    costUSD: nil,
                    contextWindow: nil,
                    maxOutputTokens: nil
                )
            }

            // Tool calls per day
            if entry.toolCallCount > 0 {
                result.dailyStats[entry.date, default: .init()].toolCallCount += entry.toolCallCount
                result.dailyStats[entry.date, default: .init()].sessionIds.insert(sessionId)
            }
        }
    }
}
