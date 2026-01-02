//
//  UserRole.swift
//  project
//
//  User role for access control
//

import SwiftUI

enum UserRole: Int16, CaseIterable, Identifiable, Codable {
    case member = 0
    case admin = 1
    case owner = 2

    var id: Int16 { rawValue }

    var displayName: String {
        switch self {
        case .member: return "Member"
        case .admin: return "Admin"
        case .owner: return "Owner"
        }
    }

    var color: Color {
        switch self {
        case .member: return .blue
        case .admin: return .orange
        case .owner: return .purple
        }
    }

    var icon: String {
        switch self {
        case .member: return "person"
        case .admin: return "person.badge.key"
        case .owner: return "crown"
        }
    }

    var canManageProject: Bool {
        self == .admin || self == .owner
    }

    var canManageTeam: Bool {
        self == .owner
    }

    var canDeleteProject: Bool {
        self == .owner
    }
}
