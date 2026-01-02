//
//  SprintStatus.swift
//  project
//
//  Sprint lifecycle status
//

import SwiftUI

enum SprintStatus: Int16, CaseIterable, Identifiable, Codable {
    case planning = 0
    case active = 1
    case completed = 2

    var id: Int16 { rawValue }

    var displayName: String {
        switch self {
        case .planning: return "Planning"
        case .active: return "Active"
        case .completed: return "Completed"
        }
    }

    var color: Color {
        switch self {
        case .planning: return .gray
        case .active: return .blue
        case .completed: return .green
        }
    }

    var icon: String {
        switch self {
        case .planning: return "pencil.and.list.clipboard"
        case .active: return "play.circle.fill"
        case .completed: return "checkmark.seal.fill"
        }
    }
}
