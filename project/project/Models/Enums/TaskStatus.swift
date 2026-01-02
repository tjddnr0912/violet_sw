//
//  TaskStatus.swift
//  project
//
//  Task status enum for Kanban workflow
//

import SwiftUI

enum TaskStatus: Int16, CaseIterable, Identifiable, Codable {
    case todo = 0
    case inProgress = 1
    case inReview = 2
    case done = 3

    var id: Int16 { rawValue }

    var displayName: String {
        switch self {
        case .todo: return "To Do"
        case .inProgress: return "In Progress"
        case .inReview: return "In Review"
        case .done: return "Done"
        }
    }

    var shortName: String {
        switch self {
        case .todo: return "TODO"
        case .inProgress: return "PROG"
        case .inReview: return "REVIEW"
        case .done: return "DONE"
        }
    }

    var color: Color {
        switch self {
        case .todo: return .gray
        case .inProgress: return .blue
        case .inReview: return .purple
        case .done: return .green
        }
    }

    var icon: String {
        switch self {
        case .todo: return "circle"
        case .inProgress: return "circle.lefthalf.filled"
        case .inReview: return "eye.circle"
        case .done: return "checkmark.circle.fill"
        }
    }

    var sortOrder: Int {
        return Int(rawValue)
    }
}

// MARK: - Status Transitions
extension TaskStatus {
    var canTransitionTo: [TaskStatus] {
        switch self {
        case .todo:
            return [.inProgress]
        case .inProgress:
            return [.todo, .inReview, .done]
        case .inReview:
            return [.inProgress, .done]
        case .done:
            return [.inProgress, .todo]
        }
    }

    func canTransition(to status: TaskStatus) -> Bool {
        return canTransitionTo.contains(status)
    }
}

// MARK: - Transferable for Drag and Drop
extension TaskStatus: Transferable {
    static var transferRepresentation: some TransferRepresentation {
        CodableRepresentation(contentType: .plainText)
    }
}
