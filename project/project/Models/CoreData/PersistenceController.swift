//
//  PersistenceController.swift
//  project
//
//  Core Data + CloudKit persistence stack
//

import CoreData
import CloudKit
import SwiftUI

class PersistenceController: ObservableObject {
    static let shared = PersistenceController()

    // Preview instance for SwiftUI previews
    static var preview: PersistenceController = {
        let controller = PersistenceController(inMemory: true)
        let viewContext = controller.container.viewContext

        // Create sample data for previews
        createPreviewData(in: viewContext)

        return controller
    }()

    let container: NSPersistentCloudKitContainer

    @Published var syncStatus: SyncStatus = .idle
    @Published var lastSyncDate: Date?

    private var historyToken: NSPersistentHistoryToken?

    init(inMemory: Bool = false) {
        container = NSPersistentCloudKitContainer(name: "ProjectManagement")

        guard let description = container.persistentStoreDescriptions.first else {
            fatalError("No persistent store description found")
        }

        if inMemory {
            description.url = URL(fileURLWithPath: "/dev/null")
        } else {
            // Configure for CloudKit sync
            description.cloudKitContainerOptions = NSPersistentCloudKitContainerOptions(
                containerIdentifier: "iCloud.com.projectmanagement.app"
            )

            // Enable persistent history tracking
            description.setOption(true as NSNumber,
                                 forKey: NSPersistentHistoryTrackingKey)
            description.setOption(true as NSNumber,
                                 forKey: NSPersistentStoreRemoteChangeNotificationPostOptionKey)
        }

        container.loadPersistentStores { description, error in
            if let error = error {
                // In production, handle this more gracefully
                print("Core Data failed to load: \(error.localizedDescription)")
            }
        }

        // Configure view context
        container.viewContext.automaticallyMergesChangesFromParent = true
        container.viewContext.mergePolicy = NSMergeByPropertyObjectTrumpMergePolicy
        container.viewContext.undoManager = UndoManager()

        // Listen for remote changes
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleRemoteChange),
            name: .NSPersistentStoreRemoteChange,
            object: container.persistentStoreCoordinator
        )
    }

    // MARK: - Remote Change Handling
    @objc private func handleRemoteChange(_ notification: Notification) {
        DispatchQueue.main.async {
            self.syncStatus = .syncing
        }

        // Process remote changes
        processRemoteChanges()
    }

    private func processRemoteChanges() {
        let context = container.newBackgroundContext()

        context.perform {
            let fetchHistoryRequest = NSPersistentHistoryChangeRequest.fetchHistory(
                after: self.historyToken
            )

            do {
                let historyResult = try context.execute(fetchHistoryRequest) as? NSPersistentHistoryResult
                guard let history = historyResult?.result as? [NSPersistentHistoryTransaction] else {
                    return
                }

                // Update token
                self.historyToken = history.last?.token

                DispatchQueue.main.async {
                    self.syncStatus = .synced
                    self.lastSyncDate = Date()
                }
            } catch {
                DispatchQueue.main.async {
                    self.syncStatus = .error(error.localizedDescription)
                }
            }
        }
    }

    // MARK: - Save Context
    func save() {
        let context = container.viewContext

        if context.hasChanges {
            do {
                try context.save()
            } catch {
                print("Failed to save context: \(error.localizedDescription)")
            }
        }
    }

    // MARK: - Background Operations
    func performBackgroundTask(_ block: @escaping (NSManagedObjectContext) -> Void) {
        container.performBackgroundTask(block)
    }

    // MARK: - Preview Data
    static func createPreviewData(in context: NSManagedObjectContext) {
        // Create sample user
        let user = User(context: context)
        user.id = UUID()
        user.name = "John Doe"
        user.email = "john@example.com"
        user.avatarColor = "blue"
        user.role = UserRole.owner.rawValue
        user.isCurrentUser = true
        user.createdAt = Date()

        // Create sample project
        let project = Project(context: context)
        project.id = UUID()
        project.name = "Sample Project"
        project.projectDescription = "A sample project for testing"
        project.color = "blue"
        project.createdAt = Date()
        project.updatedAt = Date()
        project.isArchived = false
        project.owner = user

        // Create sample sprint
        let sprint = Sprint(context: context)
        sprint.id = UUID()
        sprint.name = "Sprint 1"
        sprint.goal = "Complete initial setup"
        sprint.startDate = Date()
        sprint.endDate = Calendar.current.date(byAdding: .day, value: 14, to: Date())!
        sprint.status = SprintStatus.active.rawValue
        sprint.createdAt = Date()
        sprint.project = project

        // Create sample tasks
        let taskTitles = [
            ("Setup project structure", TaskStatus.done, TaskPriority.high, TaskType.task),
            ("Design database schema", TaskStatus.done, TaskPriority.high, TaskType.task),
            ("Implement user authentication", TaskStatus.inProgress, TaskPriority.critical, TaskType.story),
            ("Create dashboard UI", TaskStatus.inProgress, TaskPriority.medium, TaskType.task),
            ("Write unit tests", TaskStatus.todo, TaskPriority.medium, TaskType.task),
            ("Fix login bug", TaskStatus.inReview, TaskPriority.high, TaskType.bug),
            ("Add dark mode support", TaskStatus.todo, TaskPriority.low, TaskType.story),
        ]

        for (index, (title, status, priority, type)) in taskTitles.enumerated() {
            let task = ProjectTask(context: context)
            task.id = UUID()
            task.title = title
            task.taskDescription = "Description for \(title)"
            task.status = status.rawValue
            task.priority = priority.rawValue
            task.type = type.rawValue
            task.storyPoints = Int16.random(in: 1...8)
            task.createdAt = Date()
            task.updatedAt = Date()
            task.orderIndex = Int32(index)
            task.project = project

            if status != .todo {
                task.sprint = sprint
            }

            if status == .inProgress || status == .inReview {
                task.assignee = user
            }

            // Add due date for some tasks
            if Bool.random() {
                task.dueDate = Calendar.current.date(byAdding: .day, value: Int.random(in: -2...10), to: Date())
            }
        }

        // Create sample personal todos
        let todoTitles = ["Review code changes", "Update documentation", "Team meeting", "Read technical blog"]
        for title in todoTitles {
            let todo = PersonalTodo(context: context)
            todo.id = UUID()
            todo.title = title
            todo.isCompleted = Bool.random()
            todo.priority = TaskPriority.allCases.randomElement()!.rawValue
            todo.createdAt = Date()
            todo.user = user

            if Bool.random() {
                todo.dueDate = Calendar.current.date(byAdding: .day, value: Int.random(in: 1...7), to: Date())
            }
        }

        do {
            try context.save()
        } catch {
            print("Failed to save preview data: \(error)")
        }
    }
}

// MARK: - Convenience Extensions
extension NSManagedObjectContext {
    func saveIfNeeded() {
        if hasChanges {
            do {
                try save()
            } catch {
                print("Context save error: \(error)")
            }
        }
    }
}
