//
//  Project+Extensions.swift
//  project
//
//  Extensions for Project Core Data entity
//

import Foundation
import SwiftUI
import CoreData

extension Project {
    // MARK: - Computed Properties

    var taskArray: [ProjectTask] {
        let set = tasks as? Set<ProjectTask> ?? []
        return set.sorted { ($0.createdAt ?? Date()) > ($1.createdAt ?? Date()) }
    }

    var sprintArray: [Sprint] {
        let set = sprints as? Set<Sprint> ?? []
        return set.sorted { ($0.startDate ?? Date()) > ($1.startDate ?? Date()) }
    }

    var memberArray: [User] {
        let set = members as? Set<User> ?? []
        return set.sorted { ($0.name ?? "") < ($1.name ?? "") }
    }

    var projectColor: Color {
        Color(color ?? "blue")
    }

    var activeSprint: Sprint? {
        sprintArray.first { SprintStatus(rawValue: $0.status) == .active }
    }

    var totalTasks: Int {
        taskArray.count
    }

    var completedTasks: Int {
        taskArray.filter { TaskStatus(rawValue: $0.status) == .done }.count
    }

    var inProgressTasks: Int {
        taskArray.filter { TaskStatus(rawValue: $0.status) == .inProgress }.count
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

    // MARK: - Task Filtering

    func tasks(with status: TaskStatus) -> [ProjectTask] {
        taskArray.filter { $0.statusEnum == status }
    }

    func tasks(in sprint: Sprint?) -> [ProjectTask] {
        guard let sprint = sprint else {
            return taskArray.filter { $0.sprint == nil }
        }
        return taskArray.filter { $0.sprint == sprint }
    }

    func backlogTasks() -> [ProjectTask] {
        taskArray.filter { $0.sprint == nil }
    }

    // MARK: - Status Counts for Charts

    var statusCounts: [TaskStatus: Int] {
        var counts: [TaskStatus: Int] = [:]
        for status in TaskStatus.allCases {
            counts[status] = tasks(with: status).count
        }
        return counts
    }

    var priorityCounts: [TaskPriority: Int] {
        var counts: [TaskPriority: Int] = [:]
        for priority in TaskPriority.allCases {
            counts[priority] = taskArray.filter { $0.priorityEnum == priority }.count
        }
        return counts
    }

    var typeCounts: [TaskType: Int] {
        var counts: [TaskType: Int] = [:]
        for type in TaskType.allCases {
            counts[type] = taskArray.filter { $0.typeEnum == type }.count
        }
        return counts
    }

    // MARK: - Factory Method

    static func create(
        in context: NSManagedObjectContext,
        name: String,
        description: String? = nil,
        color: String = "blue",
        owner: User
    ) -> Project {
        let project = Project(context: context)
        project.id = UUID()
        project.name = name
        project.projectDescription = description
        project.color = color
        project.createdAt = Date()
        project.updatedAt = Date()
        project.isArchived = false
        project.owner = owner
        return project
    }

    // MARK: - Actions

    func archive() {
        isArchived = true
        updatedAt = Date()
    }

    func unarchive() {
        isArchived = false
        updatedAt = Date()
    }

    func addMember(_ user: User) {
        addToMembers(user)
        updatedAt = Date()
    }

    func removeMember(_ user: User) {
        removeFromMembers(user)
        updatedAt = Date()
    }
}

// MARK: - Color Extension
extension Color {
    init(_ name: String) {
        switch name.lowercased() {
        case "blue": self = .blue
        case "red": self = .red
        case "green": self = .green
        case "orange": self = .orange
        case "purple": self = .purple
        case "pink": self = .pink
        case "yellow": self = .yellow
        case "cyan": self = .cyan
        case "mint": self = .mint
        case "indigo": self = .indigo
        case "teal": self = .teal
        default: self = .blue
        }
    }
}
