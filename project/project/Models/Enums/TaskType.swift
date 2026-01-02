//
//  TaskType.swift
//  project
//
//  Task type classification (Agile issue types)
//

import SwiftUI

enum TaskType: Int16, CaseIterable, Identifiable, Codable {
    case task = 0
    case bug = 1
    case story = 2
    case epic = 3
    case subtask = 4

    var id: Int16 { rawValue }

    var displayName: String {
        switch self {
        case .task: return "Task"
        case .bug: return "Bug"
        case .story: return "Story"
        case .epic: return "Epic"
        case .subtask: return "Subtask"
        }
    }

    var color: Color {
        switch self {
        case .task: return .blue
        case .bug: return .red
        case .story: return .green
        case .epic: return .purple
        case .subtask: return .cyan
        }
    }

    var icon: String {
        switch self {
        case .task: return "checkmark.square"
        case .bug: return "ladybug"
        case .story: return "book"
        case .epic: return "bolt.fill"
        case .subtask: return "arrow.turn.down.right"
        }
    }

    var canHaveSubtasks: Bool {
        switch self {
        case .task, .story, .epic:
            return true
        case .bug, .subtask:
            return false
        }
    }

    var defaultStoryPoints: Int16 {
        switch self {
        case .epic: return 13
        case .story: return 5
        case .task: return 3
        case .bug: return 2
        case .subtask: return 1
        }
    }
}
