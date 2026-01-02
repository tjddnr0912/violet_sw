//
//  ProjectTask+Extensions.swift
//  project
//
//  Extensions for ProjectTask Core Data entity
//

import Foundation
import SwiftUI
import CoreData
import UniformTypeIdentifiers

extension ProjectTask {
    // MARK: - Computed Properties

    var statusEnum: TaskStatus {
        get { TaskStatus(rawValue: status) ?? .todo }
        set { status = newValue.rawValue }
    }

    var priorityEnum: TaskPriority {
        get { TaskPriority(rawValue: priority) ?? .medium }
        set { priority = newValue.rawValue }
    }

    var typeEnum: TaskType {
        get { TaskType(rawValue: type) ?? .task }
        set { type = newValue.rawValue }
    }

    var shortId: String {
        guard let id = id else { return "???" }
        return String(id.uuidString.prefix(8)).uppercased()
    }

    var isOverdue: Bool {
        guard let dueDate = dueDate else { return false }
        return dueDate < Date() && statusEnum != .done
    }

    var daysUntilDue: Int? {
        guard let dueDate = dueDate else { return nil }
        return Calendar.current.dateComponents([.day], from: Date(), to: dueDate).day
    }

    var priorityColor: Color {
        priorityEnum.color
    }

    var statusColor: Color {
        statusEnum.color
    }

    var typeColor: Color {
        typeEnum.color
    }

    var isCompleted: Bool {
        statusEnum == .done
    }

    var subtaskArray: [ProjectTask] {
        let set = subtasks as? Set<ProjectTask> ?? []
        return set.sorted { ($0.orderIndex) < ($1.orderIndex) }
    }

    var commentArray: [Comment] {
        let set = comments as? Set<Comment> ?? []
        return set.sorted { ($0.createdAt ?? Date()) > ($1.createdAt ?? Date()) }
    }

    var completionPercentage: Double {
        let subtaskList = subtaskArray
        guard !subtaskList.isEmpty else { return isCompleted ? 100 : 0 }

        let completed = subtaskList.filter { $0.isCompleted }.count
        return Double(completed) / Double(subtaskList.count) * 100
    }

    // MARK: - Factory Methods

    static func create(
        in context: NSManagedObjectContext,
        title: String,
        project: Project,
        type: TaskType = .task,
        priority: TaskPriority = .medium,
        sprint: Sprint? = nil,
        assignee: User? = nil,
        dueDate: Date? = nil,
        description: String? = nil,
        storyPoints: Int16? = nil
    ) -> ProjectTask {
        let task = ProjectTask(context: context)
        task.id = UUID()
        task.title = title
        task.taskDescription = description
        task.status = TaskStatus.todo.rawValue
        task.priority = priority.rawValue
        task.type = type.rawValue
        task.storyPoints = storyPoints ?? type.defaultStoryPoints
        task.dueDate = dueDate
        task.createdAt = Date()
        task.updatedAt = Date()
        task.orderIndex = 0
        task.project = project
        task.sprint = sprint
        task.assignee = assignee
        return task
    }

    // MARK: - Actions

    func updateStatus(to newStatus: TaskStatus) {
        status = newStatus.rawValue
        updatedAt = Date()

        if newStatus == .done {
            completedAt = Date()
        } else {
            completedAt = nil
        }
    }

    func assignTo(_ user: User?) {
        assignee = user
        updatedAt = Date()
    }

    func moveTo(sprint: Sprint?) {
        self.sprint = sprint
        updatedAt = Date()
    }
}

// MARK: - Transferable for Drag and Drop
extension ProjectTask: Transferable {
    public static var transferRepresentation: some TransferRepresentation {
        CodableRepresentation(contentType: .projectTask)
    }
}

extension UTType {
    static var projectTask: UTType {
        UTType(exportedAs: "com.projectmanagement.task")
    }
}

// MARK: - Codable wrapper for drag and drop
extension ProjectTask {
    struct TransferData: Codable {
        let id: UUID
    }

    var transferData: TransferData {
        TransferData(id: id ?? UUID())
    }
}
