//
//  TaskPriority.swift
//  project
//
//  Task priority levels with visual indicators
//

import SwiftUI

enum TaskPriority: Int16, CaseIterable, Identifiable, Codable {
    case low = 0
    case medium = 1
    case high = 2
    case critical = 3

    var id: Int16 { rawValue }

    var displayName: String {
        switch self {
        case .low: return "Low"
        case .medium: return "Medium"
        case .high: return "High"
        case .critical: return "Critical"
        }
    }

    var color: Color {
        switch self {
        case .low: return .gray
        case .medium: return .blue
        case .high: return .orange
        case .critical: return .red
        }
    }

    var backgroundColor: Color {
        color.opacity(0.15)
    }

    var icon: String {
        switch self {
        case .low: return "arrow.down"
        case .medium: return "minus"
        case .high: return "arrow.up"
        case .critical: return "exclamationmark.triangle.fill"
        }
    }

    var sortOrder: Int {
        // Higher priority = lower sort order (appears first)
        return Int(3 - rawValue)
    }
}

// MARK: - Comparable
extension TaskPriority: Comparable {
    static func < (lhs: TaskPriority, rhs: TaskPriority) -> Bool {
        return lhs.rawValue < rhs.rawValue
    }
}
