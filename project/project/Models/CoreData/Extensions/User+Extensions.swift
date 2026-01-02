//
//  User+Extensions.swift
//  project
//
//  Extensions for User Core Data entity
//

import Foundation
import SwiftUI
import CoreData

extension User {
    // MARK: - Computed Properties

    var roleEnum: UserRole {
        get { UserRole(rawValue: role) ?? .member }
        set { role = newValue.rawValue }
    }

    var userColor: Color {
        Color(avatarColor ?? "blue")
    }

    var initials: String {
        guard let name = name else { return "?" }
        let components = name.split(separator: " ")
        if components.count >= 2 {
            return String(components[0].prefix(1) + components[1].prefix(1)).uppercased()
        }
        return String(name.prefix(2)).uppercased()
    }

    var assignedTaskArray: [ProjectTask] {
        let set = assignedTasks as? Set<ProjectTask> ?? []
        return set.sorted { ($0.createdAt ?? Date()) > ($1.createdAt ?? Date()) }
    }

    var todoArray: [PersonalTodo] {
        let set = todos as? Set<PersonalTodo> ?? []
        return set.sorted { ($0.createdAt ?? Date()) > ($1.createdAt ?? Date()) }
    }

    var ownedProjectArray: [Project] {
        let set = ownedProjects as? Set<Project> ?? []
        return set.sorted { ($0.name ?? "") < ($1.name ?? "") }
    }

    var memberProjectArray: [Project] {
        let set = memberOfProjects as? Set<Project> ?? []
        return set.sorted { ($0.name ?? "") < ($1.name ?? "") }
    }

    // MARK: - Statistics

    var totalAssignedTasks: Int {
        assignedTaskArray.count
    }

    var completedAssignedTasks: Int {
        assignedTaskArray.filter { $0.isCompleted }.count
    }

    var inProgressAssignedTasks: Int {
        assignedTaskArray.filter { $0.statusEnum == .inProgress }.count
    }

    var incompleteTodos: Int {
        todoArray.filter { !$0.isCompleted }.count
    }

    // MARK: - Factory Method

    static func create(
        in context: NSManagedObjectContext,
        name: String,
        email: String,
        role: UserRole = .member,
        avatarColor: String = "blue",
        isCurrentUser: Bool = false
    ) -> User {
        let user = User(context: context)
        user.id = UUID()
        user.name = name
        user.email = email
        user.role = role.rawValue
        user.avatarColor = avatarColor
        user.isCurrentUser = isCurrentUser
        user.createdAt = Date()
        return user
    }

    // MARK: - Current User

    static func currentUser(in context: NSManagedObjectContext) -> User? {
        let request: NSFetchRequest<User> = User.fetchRequest()
        request.predicate = NSPredicate(format: "isCurrentUser == YES")
        request.fetchLimit = 1
        return try? context.fetch(request).first
    }

    static func getOrCreateCurrentUser(in context: NSManagedObjectContext) -> User {
        if let existing = currentUser(in: context) {
            return existing
        }

        return create(
            in: context,
            name: NSFullUserName(),
            email: "user@example.com",
            role: .owner,
            avatarColor: "blue",
            isCurrentUser: true
        )
    }
}
