//
//  Sprint+Extensions.swift
//  project
//
//  Extensions for Sprint Core Data entity
//

import Foundation
import SwiftUI
import CoreData

extension Sprint {
    // MARK: - Computed Properties

    var statusEnum: SprintStatus {
        get { SprintStatus(rawValue: status) ?? .planning }
        set { status = newValue.rawValue }
    }

    var taskArray: [ProjectTask] {
        let set = tasks as? Set<ProjectTask> ?? []
        return set.sorted { ($0.orderIndex) < ($1.orderIndex) }
    }

    var totalDays: Int {
        guard let start = startDate, let end = endDate else { return 0 }
        return Calendar.current.dateComponents([.day], from: start, to: end).day ?? 0
    }

    var daysRemaining: Int {
        guard let end = endDate else { return 0 }
        let days = Calendar.current.dateComponents([.day], from: Date(), to: end).day ?? 0
        return max(0, days)
    }

    var daysElapsed: Int {
        guard let start = startDate else { return 0 }
        let days = Calendar.current.dateComponents([.day], from: start, to: Date()).day ?? 0
        return max(0, days)
    }

    var progress: Double {
        guard totalDays > 0 else { return 0 }
        return min(Double(daysElapsed) / Double(totalDays), 1.0)
    }

    var isActive: Bool {
        statusEnum == .active
    }

    var isOverdue: Bool {
        guard let end = endDate else { return false }
        return end < Date() && statusEnum == .active
    }

    // MARK: - Task Statistics

    var totalTasks: Int {
        taskArray.count
    }

    var completedTasks: Int {
        taskArray.filter { $0.isCompleted }.count
    }

    var completionPercentage: Double {
        guard totalTasks > 0 else { return 0 }
        return Double(completedTasks) / Double(totalTasks) * 100
    }

    var totalStoryPoints: Int {
        taskArray.reduce(0) { $0 + Int($1.storyPoints) }
    }

    var completedStoryPoints: Int {
        taskArray.filter { $0.isCompleted }.reduce(0) { $0 + Int($1.storyPoints) }
    }

    var remainingStoryPoints: Int {
        totalStoryPoints - completedStoryPoints
    }

    // MARK: - Burndown Data

    func burndownData() -> [BurndownDataPoint] {
        guard let start = startDate, let end = endDate else { return [] }

        var data: [BurndownDataPoint] = []
        let calendar = Calendar.current
        var currentDate = start
        let totalPoints = Double(totalStoryPoints)

        while currentDate <= end {
            let daysSinceStart = calendar.dateComponents([.day], from: start, to: currentDate).day ?? 0
            let idealRemaining = totalPoints - (totalPoints * Double(daysSinceStart) / Double(totalDays))

            // Calculate actual remaining (simplified - in real app, track daily)
            let actualRemaining: Double
            if currentDate <= Date() {
                let progressRatio = Double(daysSinceStart) / Double(max(daysElapsed, 1))
                actualRemaining = Double(remainingStoryPoints) + (Double(completedStoryPoints) * (1 - progressRatio))
            } else {
                actualRemaining = Double(remainingStoryPoints)
            }

            data.append(BurndownDataPoint(
                date: currentDate,
                idealRemaining: max(0, idealRemaining),
                actualRemaining: max(0, actualRemaining)
            ))

            currentDate = calendar.date(byAdding: .day, value: 1, to: currentDate)!
        }

        return data
    }

    // MARK: - Task Filtering

    func tasks(with status: TaskStatus) -> [ProjectTask] {
        taskArray.filter { $0.statusEnum == status }
    }

    // MARK: - Factory Method

    static func create(
        in context: NSManagedObjectContext,
        name: String,
        project: Project,
        goal: String? = nil,
        startDate: Date,
        endDate: Date
    ) -> Sprint {
        let sprint = Sprint(context: context)
        sprint.id = UUID()
        sprint.name = name
        sprint.goal = goal
        sprint.startDate = startDate
        sprint.endDate = endDate
        sprint.status = SprintStatus.planning.rawValue
        sprint.createdAt = Date()
        sprint.project = project
        return sprint
    }

    // MARK: - Actions

    func start() {
        guard statusEnum == .planning else { return }
        status = SprintStatus.active.rawValue
        startDate = Date()
    }

    func complete() {
        guard statusEnum == .active else { return }
        status = SprintStatus.completed.rawValue
    }
}

// MARK: - Burndown Data Point
struct BurndownDataPoint: Identifiable {
    let id = UUID()
    let date: Date
    let idealRemaining: Double
    let actualRemaining: Double
}
