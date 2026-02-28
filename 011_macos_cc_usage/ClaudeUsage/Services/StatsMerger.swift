import Foundation

struct StatsMerger {

    /// Merge stats-cache baseline (up to cutoff) with JSONL live data (after cutoff).
    /// Returns a unified StatsCache so all existing views work unchanged.
    static func merge(baseline: StatsCache?, live: LiveStats) -> StatsCache {
        // 1. Daily Activity: baseline dates + live dates (no overlap expected)
        var dailyMap: [String: DailyActivity] = [:]

        for day in baseline?.dailyActivity ?? [] {
            dailyMap[day.date] = day
        }

        for (date, dayStats) in live.dailyStats {
            let existing = dailyMap[date]
            dailyMap[date] = DailyActivity(
                date: date,
                messageCount: (existing?.messageCount ?? 0) + dayStats.messageCount,
                sessionCount: (existing?.sessionCount ?? 0) + dayStats.sessionIds.count,
                toolCallCount: (existing?.toolCallCount ?? 0) + dayStats.toolCallCount
            )
        }

        let sortedActivity = dailyMap.values.sorted { $0.date < $1.date }

        // 2. Model Usage: sum tokens per model
        var modelMap = baseline?.modelUsage ?? [:]
        for (model, detail) in live.modelUsage {
            if let existing = modelMap[model] {
                modelMap[model] = ModelUsageDetail(
                    inputTokens: existing.inputTokens + detail.inputTokens,
                    outputTokens: existing.outputTokens + detail.outputTokens,
                    cacheReadInputTokens: existing.cacheReadInputTokens + detail.cacheReadInputTokens,
                    cacheCreationInputTokens: existing.cacheCreationInputTokens + detail.cacheCreationInputTokens,
                    webSearchRequests: existing.webSearchRequests,
                    costUSD: existing.costUSD,
                    contextWindow: existing.contextWindow,
                    maxOutputTokens: existing.maxOutputTokens
                )
            } else {
                modelMap[model] = detail
            }
        }

        // 3. Hour Counts: sum per hour
        var hourMap = baseline?.hourCounts ?? [:]
        for (hour, count) in live.hourCounts {
            hourMap[hour, default: 0] += count
        }

        // 4. Totals: sum baseline + live
        let totalSessions = (baseline?.totalSessions ?? 0) + live.totalSessions
        let totalMessages = (baseline?.totalMessages ?? 0) + live.totalMessages

        // 5. Assemble — longestSession and firstSessionDate kept from baseline
        return StatsCache(
            version: baseline?.version ?? 2,
            lastComputedDate: todayString(),
            dailyActivity: sortedActivity,
            dailyModelTokens: baseline?.dailyModelTokens ?? [],
            modelUsage: modelMap,
            totalSessions: totalSessions,
            totalMessages: totalMessages,
            longestSession: baseline?.longestSession,
            firstSessionDate: baseline?.firstSessionDate,
            hourCounts: hourMap,
            totalSpeculationTimeSavedMs: baseline?.totalSpeculationTimeSavedMs
        )
    }

    private static func todayString() -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: Date())
    }
}
