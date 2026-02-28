import Foundation
import SwiftUI

@MainActor
final class UsageViewModel: ObservableObject {
    @Published var stats: StatsCache?
    @Published var recentSessions: [SessionEntry] = []
    @Published var activeSession: SessionTokenUsage?
    @Published var lastUpdated: Date?
    @Published var isLoading = false

    private var fileWatcher: FileWatcher?
    private var sessionWatcher: FileWatcher?
    private var fallbackTimer: Timer?
    private var currentSessionPath: String?

    var planType: String { "Max" }

    // MARK: - Computed: Today's stats

    var todayActivity: DailyActivity? {
        let today = todayString()
        return stats?.dailyActivity.first(where: { $0.date == today })
    }

    var todaySessions: Int { todayActivity?.sessionCount ?? 0 }
    var todayMessages: Int { todayActivity?.messageCount ?? 0 }
    var todayToolCalls: Int { todayActivity?.toolCallCount ?? 0 }

    // Peak messages in a single day (for progress bar scale)
    var todayPeakMessages: Int {
        stats?.dailyActivity.map(\.messageCount).max() ?? 1
    }

    var todaySubtitle: String {
        "\(todaySessions) sessions, \(todayToolCalls.formattedCompact) tool calls"
    }

    // MARK: - Computed: Weekly stats (last 7 days)

    var weeklyMessages: Int {
        recentNDaysActivity(7).map(\.messageCount).reduce(0, +)
    }

    var weeklyPeakMessages: Int {
        let activity = stats?.dailyActivity ?? []
        guard activity.count >= 7 else {
            return max(weeklyMessages, 1)
        }
        var maxWeekly = 0
        for i in 0...(activity.count - 7) {
            let weekTotal = activity[i..<(i+7)].map(\.messageCount).reduce(0, +)
            maxWeekly = max(maxWeekly, weekTotal)
        }
        return max(maxWeekly, 1)
    }

    var weeklySubtitle: String {
        let sessions = recentNDaysActivity(7).map(\.sessionCount).reduce(0, +)
        return "Last 7 days: \(sessions) sessions, \(weeklyMessages.formattedCompact) messages"
    }

    // MARK: - Computed: Model usage sorted

    var sortedModelUsage: [(model: String, detail: ModelUsageDetail)] {
        guard let usage = stats?.modelUsage else { return [] }
        return usage
            .map { (model: $0.key, detail: $0.value) }
            .sorted { $0.detail.outputTokens > $1.detail.outputTokens }
    }

    // MARK: - Computed: Daily activity (last 14 days)

    var recentDailyActivity: [DailyActivity] {
        guard let activity = stats?.dailyActivity else { return [] }
        return Array(activity.suffix(14))
    }

    // MARK: - Computed: Weekly comparison (this week vs last week)

    var lastWeekMessages: Int {
        recentNDaysActivity(from: 8, to: 14).map(\.messageCount).reduce(0, +)
    }

    var lastWeekSessions: Int {
        recentNDaysActivity(from: 8, to: 14).map(\.sessionCount).reduce(0, +)
    }

    var lastWeekToolCalls: Int {
        recentNDaysActivity(from: 8, to: 14).map(\.toolCallCount).reduce(0, +)
    }

    var thisWeekMessages: Int {
        recentNDaysActivity(7).map(\.messageCount).reduce(0, +)
    }

    var thisWeekSessions: Int {
        recentNDaysActivity(7).map(\.sessionCount).reduce(0, +)
    }

    var thisWeekToolCalls: Int {
        recentNDaysActivity(7).map(\.toolCallCount).reduce(0, +)
    }

    var weeklyMessageChange: Double {
        percentChange(current: thisWeekMessages, previous: lastWeekMessages)
    }

    var weeklySessionChange: Double {
        percentChange(current: thisWeekSessions, previous: lastWeekSessions)
    }

    var weeklyToolCallChange: Double {
        percentChange(current: thisWeekToolCalls, previous: lastWeekToolCalls)
    }

    // MARK: - Computed: Streak

    var currentStreak: Int {
        guard let activity = stats?.dailyActivity, !activity.isEmpty else { return 0 }
        let dates = Set(activity.map(\.date))
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        var streak = 0
        var day = Date()
        while true {
            let dayStr = formatter.string(from: day)
            if dates.contains(dayStr) {
                streak += 1
            } else {
                break
            }
            day = Calendar.current.date(byAdding: .day, value: -1, to: day) ?? day
        }
        return streak
    }

    var maxStreak: Int {
        guard let activity = stats?.dailyActivity, !activity.isEmpty else { return 0 }
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        let sortedDates = activity.map(\.date).sorted()
        var best = 0
        var current = 1
        for i in 1..<sortedDates.count {
            if let prev = formatter.date(from: sortedDates[i-1]),
               let curr = formatter.date(from: sortedDates[i]),
               Calendar.current.dateComponents([.day], from: prev, to: curr).day == 1 {
                current += 1
            } else {
                best = max(best, current)
                current = 1
            }
        }
        return max(best, current)
    }

    // MARK: - Computed: Developer Type (peak time badge)

    var developerType: (title: String, icon: String, description: String) {
        guard let hourCounts = stats?.hourCounts, !hourCounts.isEmpty else {
            return ("", "", "")
        }
        // Weighted average hour
        var totalWeight = 0
        var weightedSum = 0.0
        for (hourStr, count) in hourCounts {
            guard let hour = Int(hourStr) else { continue }
            totalWeight += count
            // Use angle for circular mean
            weightedSum += Double(count) * Double(hour)
        }
        guard totalWeight > 0 else {
            return ("", "", "")
        }
        let avgHour = Int(weightedSum / Double(totalWeight)) % 24

        switch avgHour {
        case 0...5:
            return ("올빼미 개발자", "moon.stars", "Night Owl")
        case 6...9:
            return ("얼리버드", "sunrise", "Early Bird")
        case 10...14:
            return ("데이 빌더", "sun.max", "Day Builder")
        case 15...18:
            return ("에프터눈 코더", "cloud.sun", "Afternoon Coder")
        case 19...22:
            return ("나이트 코더", "moon.haze", "Night Coder")
        default:
            return ("미드나잇 해커", "moon.zzz", "Midnight Hacker")
        }
    }

    // MARK: - Computed: Hourly pattern

    var hourlyPattern: [(hour: Int, count: Int)] {
        guard let hourCounts = stats?.hourCounts else { return [] }
        return (0..<24).map { hour in
            let count = hourCounts[String(hour)] ?? 0
            return (hour: hour, count: count)
        }
    }

    // MARK: - Computed: First session date

    var firstSessionDate: Date? {
        guard let dateStr = stats?.firstSessionDate else { return nil }
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"
        if let date = fmt.date(from: dateStr) { return date }
        return ISO8601DateFormatter().date(from: dateStr)
    }

    // MARK: - Model name formatting

    static func displayName(for modelId: String) -> String {
        let patterns: [(prefix: String, name: String)] = [
            ("claude-opus-4-6", "Opus 4.6"),
            ("claude-opus-4-5", "Opus 4.5"),
            ("claude-sonnet-4-6", "Sonnet 4.6"),
            ("claude-sonnet-4-5", "Sonnet 4.5"),
            ("claude-haiku-4-5", "Haiku 4.5"),
        ]

        for pattern in patterns {
            if modelId.hasPrefix(pattern.prefix) {
                return pattern.name
            }
        }

        let parts = modelId.replacingOccurrences(of: "claude-", with: "").split(separator: "-")
        if parts.count >= 3 {
            let family = parts[0].capitalized
            let major = parts[1]
            let minor = parts[2]
            return "\(family) \(major).\(minor)"
        }

        return modelId
    }

    // MARK: - Data Loading

    func load() {
        isLoading = true
        recentSessions = SessionScanner.recentSessions(limit: 5)
        activeSession = SessionTokenReader.readActiveSession()

        // Hybrid: stats-cache baseline + JSONL live data (background)
        let baseline = StatsFileReader.read()
        let cutoff = baseline?.lastComputedDate ?? "1970-01-01"

        // Show baseline immediately while JSONL parses in background
        if stats == nil, let baseline {
            stats = baseline
        }

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let live = JSONLLiveParser.parseLiveStats(afterDate: cutoff)
            let merged = StatsMerger.merge(baseline: baseline, live: live)
            DispatchQueue.main.async {
                self?.stats = merged
                self?.lastUpdated = Date()
                self?.isLoading = false
            }
        }
    }

    func startWatching() {
        load()

        // Watch stats-cache.json
        fileWatcher = FileWatcher(path: StatsFileReader.statsPath) { [weak self] in
            Task { @MainActor in
                self?.load()
            }
        }
        fileWatcher?.start()

        // Watch active session JSONL
        startSessionWatcher()

        // Fallback timer
        fallbackTimer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.load()
                self?.startSessionWatcher()
            }
        }
    }

    func stopWatching() {
        fileWatcher?.stop()
        fileWatcher = nil
        sessionWatcher?.stop()
        sessionWatcher = nil
        fallbackTimer?.invalidate()
        fallbackTimer = nil
        currentSessionPath = nil
    }

    // MARK: - Session Watcher

    private func startSessionWatcher() {
        let newPath = SessionTokenReader.activeSessionPath
        // Only restart if path changed
        guard newPath != currentSessionPath else { return }

        sessionWatcher?.stop()
        sessionWatcher = nil
        currentSessionPath = newPath

        guard let path = newPath else { return }

        sessionWatcher = FileWatcher(path: path) { [weak self] in
            Task { @MainActor in
                self?.load()
            }
        }
        sessionWatcher?.start()
    }

    // MARK: - Helpers

    var lastUpdatedText: String {
        guard let date = lastUpdated else { return "No data" }
        let interval = Date().timeIntervalSince(date)

        if interval < 60 { return "Just now" }
        if interval < 3600 { return "\(Int(interval / 60))m ago" }
        if interval < 86400 { return "\(Int(interval / 3600))h ago" }

        let fmt = DateFormatter()
        fmt.dateFormat = "MMM d, h:mm a"
        return fmt.string(from: date)
    }

    private func todayString() -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: Date())
    }

    private func recentNDaysActivity(_ n: Int) -> [DailyActivity] {
        guard let activity = stats?.dailyActivity else { return [] }
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        let cutoff = Calendar.current.date(byAdding: .day, value: -n, to: Date()) ?? Date()
        let cutoffString = formatter.string(from: cutoff)
        return activity.filter { $0.date >= cutoffString }
    }

    /// Activity from `from` days ago to `to` days ago (inclusive)
    private func recentNDaysActivity(from: Int, to: Int) -> [DailyActivity] {
        guard let activity = stats?.dailyActivity else { return [] }
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        let startDate = Calendar.current.date(byAdding: .day, value: -to, to: Date()) ?? Date()
        let endDate = Calendar.current.date(byAdding: .day, value: -from, to: Date()) ?? Date()
        let startStr = formatter.string(from: startDate)
        let endStr = formatter.string(from: endDate)
        return activity.filter { $0.date >= startStr && $0.date <= endStr }
    }

    private func percentChange(current: Int, previous: Int) -> Double {
        guard previous > 0 else { return current > 0 ? 100.0 : 0.0 }
        return Double(current - previous) / Double(previous) * 100.0
    }
}
