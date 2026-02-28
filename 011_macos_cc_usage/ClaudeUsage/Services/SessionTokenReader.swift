import Foundation

struct SessionTokenReader {
    static let projectsPath: String = {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        return "\(home)/.claude/projects"
    }()

    /// Find the most recently modified .jsonl file across all projects
    static func findActiveSessionFile() -> (path: String, projectDir: String)? {
        let fm = FileManager.default
        guard let projectDirs = try? fm.contentsOfDirectory(atPath: projectsPath) else {
            return nil
        }

        var newest: (path: String, projectDir: String, date: Date)?

        for dir in projectDirs {
            let dirPath = "\(projectsPath)/\(dir)"
            guard let files = try? fm.contentsOfDirectory(atPath: dirPath) else { continue }

            for file in files where file.hasSuffix(".jsonl") {
                let filePath = "\(dirPath)/\(file)"
                guard let attrs = try? fm.attributesOfItem(atPath: filePath),
                      let modDate = attrs[.modificationDate] as? Date else { continue }

                if newest == nil || modDate > newest!.date {
                    newest = (path: filePath, projectDir: dir, date: modDate)
                }
            }
        }

        guard let result = newest else { return nil }
        return (path: result.path, projectDir: result.projectDir)
    }

    /// Parse a JSONL session file and aggregate token usage
    static func readSession(at path: String, projectDir: String) -> SessionTokenUsage? {
        guard let data = FileManager.default.contents(atPath: path) else { return nil }
        guard let content = String(data: data, encoding: .utf8) else { return nil }

        var model = ""
        var sessionId = ""
        var cwd = ""
        var firstTimestamp: Date?
        var userMessageCount = 0

        // message.id dedup: keep last occurrence per message (streaming writes multiple lines)
        struct UsageEntry {
            var input: Int
            var output: Int
            var cacheRead: Int
            var cacheWrite: Int
        }
        var messageUsage: [String: UsageEntry] = [:]

        let lines = content.components(separatedBy: .newlines)

        for line in lines {
            guard !line.isEmpty,
                  let lineData = line.data(using: .utf8),
                  let obj = try? JSONSerialization.jsonObject(with: lineData) as? [String: Any] else {
                continue
            }

            // Extract sessionId from any line
            if sessionId.isEmpty, let sid = obj["sessionId"] as? String {
                sessionId = sid
            }

            // Extract cwd
            if cwd.isEmpty, let c = obj["cwd"] as? String {
                cwd = c
            }

            let type = obj["type"] as? String

            // Count user messages and capture first timestamp
            if type == "user" {
                userMessageCount += 1
                if firstTimestamp == nil, let ts = obj["timestamp"] as? String {
                    firstTimestamp = ISO8601DateFormatter().date(from: ts)
                }
            }

            // Extract usage from assistant messages — dedup by message.id
            guard let message = obj["message"] as? [String: Any],
                  let usage = message["usage"] as? [String: Any],
                  let messageId = message["id"] as? String else {
                continue
            }

            // Get model from first assistant message
            if model.isEmpty, let m = message["model"] as? String {
                model = m
            }

            // Overwrite = last occurrence has final token counts
            messageUsage[messageId] = UsageEntry(
                input: usage["input_tokens"] as? Int ?? 0,
                output: usage["output_tokens"] as? Int ?? 0,
                cacheRead: usage["cache_read_input_tokens"] as? Int ?? 0,
                cacheWrite: usage["cache_creation_input_tokens"] as? Int ?? 0
            )
        }

        // Sum deduplicated usage
        var totalInput = 0
        var totalOutput = 0
        var totalCacheRead = 0
        var totalCacheWrite = 0
        for entry in messageUsage.values {
            totalInput += entry.input
            totalOutput += entry.output
            totalCacheRead += entry.cacheRead
            totalCacheWrite += entry.cacheWrite
        }

        // If no usage data found, skip
        guard totalOutput > 0 || totalInput > 0 else { return nil }

        // Extract project name from cwd or projectDir
        let projectName = extractProjectName(cwd: cwd, projectDir: projectDir)

        // If no explicit timestamp, use file creation date
        if firstTimestamp == nil {
            let attrs = try? FileManager.default.attributesOfItem(atPath: path)
            firstTimestamp = attrs?[.creationDate] as? Date
        }

        return SessionTokenUsage(
            sessionId: sessionId,
            projectName: projectName,
            model: model,
            startTime: firstTimestamp,
            messageCount: userMessageCount,
            inputTokens: totalInput,
            outputTokens: totalOutput,
            cacheReadTokens: totalCacheRead,
            cacheWriteTokens: totalCacheWrite
        )
    }

    /// Read the currently active session
    static func readActiveSession() -> SessionTokenUsage? {
        guard let file = findActiveSessionFile() else { return nil }
        return readSession(at: file.path, projectDir: file.projectDir)
    }

    /// Get the path of the active session file (for FileWatcher)
    static var activeSessionPath: String? {
        findActiveSessionFile()?.path
    }

    // MARK: - Helpers

    private static func extractProjectName(cwd: String, projectDir: String) -> String {
        // Try to get a meaningful name from cwd
        if !cwd.isEmpty {
            let url = URL(fileURLWithPath: cwd)
            return url.lastPathComponent
        }
        // Fallback: decode projectDir (e.g. "-Users-foo-project-bar" -> "bar")
        let parts = projectDir.split(separator: "-")
        if let last = parts.last {
            return String(last)
        }
        return projectDir
    }
}
