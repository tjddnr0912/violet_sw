//
//  BacklogView.swift
//  project
//
//  Backlog view showing tasks not assigned to sprints
//

import SwiftUI
import CoreData

struct BacklogView: View {
    @Environment(\.managedObjectContext) private var viewContext
    @EnvironmentObject var appState: AppState

    @State private var selectedTask: ProjectTask?
    @State private var sortOption: SortOption = .priority
    @State private var filterPriority: TaskPriority?
    @State private var filterType: TaskType?

    var project: Project? {
        appState.selectedProject
    }

    private var backlogTasks: [ProjectTask] {
        guard let project = project else { return [] }
        var tasks = project.backlogTasks()

        // Apply filters
        if let priority = filterPriority {
            tasks = tasks.filter { $0.priorityEnum == priority }
        }
        if let type = filterType {
            tasks = tasks.filter { $0.typeEnum == type }
        }

        // Apply sorting
        return sortTasks(tasks)
    }

    var body: some View {
        VStack(spacing: 0) {
            // Toolbar
            backlogToolbar

            Divider()

            // Content
            if backlogTasks.isEmpty {
                emptyState
            } else {
                List(selection: $selectedTask) {
                    ForEach(backlogTasks) { task in
                        BacklogTaskRow(task: task)
                            .tag(task)
                    }
                    .onDelete(perform: deleteTasks)
                }
                .listStyle(.inset)
            }
        }
        .sheet(item: $selectedTask) { task in
            TaskDetailSheet(task: task)
        }
    }

    // MARK: - Toolbar

    @ViewBuilder
    private var backlogToolbar: some View {
        HStack {
            Text("Backlog")
                .font(.headline)

            Text("\(backlogTasks.count) items")
                .font(.caption)
                .foregroundStyle(.secondary)

            Spacer()

            // Filters
            Menu {
                Button("All Priorities") {
                    filterPriority = nil
                }

                Divider()

                ForEach(TaskPriority.allCases) { priority in
                    Button {
                        filterPriority = priority
                    } label: {
                        Label(priority.displayName, systemImage: priority.icon)
                    }
                }
            } label: {
                Label(filterPriority?.displayName ?? "Priority", systemImage: "line.3.horizontal.decrease.circle")
            }

            Menu {
                Button("All Types") {
                    filterType = nil
                }

                Divider()

                ForEach(TaskType.allCases) { type in
                    Button {
                        filterType = type
                    } label: {
                        Label(type.displayName, systemImage: type.icon)
                    }
                }
            } label: {
                Label(filterType?.displayName ?? "Type", systemImage: "tag")
            }

            // Sort
            Picker("Sort", selection: $sortOption) {
                ForEach(SortOption.allCases) { option in
                    Text(option.rawValue).tag(option)
                }
            }
            .pickerStyle(.menu)

            Button {
                appState.isShowingNewTaskSheet = true
            } label: {
                Label("Add Task", systemImage: "plus")
            }
        }
        .padding()
    }

    // MARK: - Empty State

    @ViewBuilder
    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "tray")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)

            Text("Backlog is Empty")
                .font(.headline)

            Text("All tasks are assigned to sprints, or you haven't created any tasks yet")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Button {
                appState.isShowingNewTaskSheet = true
            } label: {
                Label("Create Task", systemImage: "plus")
            }
            .buttonStyle(.borderedProminent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    // MARK: - Helpers

    private func sortTasks(_ tasks: [ProjectTask]) -> [ProjectTask] {
        switch sortOption {
        case .priority:
            return tasks.sorted { $0.priorityEnum > $1.priorityEnum }
        case .created:
            return tasks.sorted { ($0.createdAt ?? Date()) > ($1.createdAt ?? Date()) }
        case .dueDate:
            return tasks.sorted {
                ($0.dueDate ?? Date.distantFuture) < ($1.dueDate ?? Date.distantFuture)
            }
        case .storyPoints:
            return tasks.sorted { $0.storyPoints > $1.storyPoints }
        }
    }

    private func deleteTasks(at offsets: IndexSet) {
        for index in offsets {
            let task = backlogTasks[index]
            viewContext.delete(task)
        }
        viewContext.saveIfNeeded()
    }

    enum SortOption: String, CaseIterable, Identifiable {
        case priority = "Priority"
        case created = "Created"
        case dueDate = "Due Date"
        case storyPoints = "Story Points"

        var id: String { rawValue }
    }
}

// MARK: - Backlog Task Row

struct BacklogTaskRow: View {
    @ObservedObject var task: ProjectTask
    @Environment(\.managedObjectContext) private var viewContext
    @EnvironmentObject var appState: AppState

    var body: some View {
        HStack(spacing: 12) {
            // Task Type Icon
            TaskTypeBadge(type: task.typeEnum, showText: false)

            // Task Info
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(task.title ?? "Untitled")
                        .fontWeight(.medium)

                    Text(task.shortId)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if let description = task.taskDescription, !description.isEmpty {
                    Text(description)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }

            Spacer()

            // Story Points
            if task.storyPoints > 0 {
                HStack(spacing: 2) {
                    Image(systemName: "star.fill")
                        .font(.caption2)
                    Text("\(task.storyPoints)")
                        .font(.caption)
                }
                .foregroundStyle(.secondary)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(.secondary.opacity(0.1))
                .clipShape(Capsule())
            }

            // Priority Badge
            PriorityBadge(priority: task.priorityEnum, showText: false, size: .small)

            // Due Date
            if let dueDate = task.dueDate {
                DeadlineIndicator(date: dueDate)
            }

            // Assignee
            if let assignee = task.assignee {
                AvatarView(user: assignee, size: 24)
            }
        }
        .padding(.vertical, 4)
        .contextMenu {
            // Move to Sprint submenu
            if let sprints = appState.selectedProject?.sprintArray.filter({ $0.statusEnum != .completed }), !sprints.isEmpty {
                Menu("Move to Sprint") {
                    ForEach(sprints) { sprint in
                        Button(sprint.name ?? "Sprint") {
                            task.moveTo(sprint: sprint)
                            viewContext.saveIfNeeded()
                        }
                    }
                }
            }

            // Change Priority submenu
            Menu("Set Priority") {
                ForEach(TaskPriority.allCases) { priority in
                    Button {
                        task.priorityEnum = priority
                        viewContext.saveIfNeeded()
                    } label: {
                        Label(priority.displayName, systemImage: priority.icon)
                    }
                }
            }

            Divider()

            Button(role: .destructive) {
                viewContext.delete(task)
                viewContext.saveIfNeeded()
            } label: {
                Label("Delete", systemImage: "trash")
            }
        }
    }
}

// MARK: - Preview

#Preview {
    BacklogView()
        .environment(\.managedObjectContext, PersistenceController.preview.container.viewContext)
        .environmentObject(AppState())
}
