//
//  KanbanBoardView.swift
//  project
//
//  Kanban board with drag-and-drop task management
//

import SwiftUI
import CoreData

struct KanbanBoardView: View {
    @Environment(\.managedObjectContext) private var viewContext
    @EnvironmentObject var appState: AppState

    @State private var draggedTask: ProjectTask?
    @State private var selectedTask: ProjectTask?
    @State private var showingTaskDetail = false

    var project: Project? {
        appState.selectedProject
    }

    private var tasks: [ProjectTask] {
        project?.taskArray ?? []
    }

    var body: some View {
        ScrollView(.horizontal, showsIndicators: true) {
            HStack(alignment: .top, spacing: 16) {
                ForEach(TaskStatus.allCases) { status in
                    KanbanColumnView(
                        status: status,
                        tasks: tasks(for: status),
                        draggedTask: $draggedTask,
                        onTaskTap: { task in
                            selectedTask = task
                            showingTaskDetail = true
                        },
                        onTaskDrop: { task, newStatus in
                            moveTask(task, to: newStatus)
                        }
                    )
                }
            }
            .padding()
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .sheet(item: $selectedTask) { task in
            TaskDetailSheet(task: task)
        }
    }

    private func tasks(for status: TaskStatus) -> [ProjectTask] {
        tasks.filter { $0.statusEnum == status }
            .sorted { $0.orderIndex < $1.orderIndex }
    }

    private func moveTask(_ task: ProjectTask, to newStatus: TaskStatus) {
        withAnimation(.spring(response: 0.3)) {
            task.updateStatus(to: newStatus)
            viewContext.saveIfNeeded()
        }
    }
}

// MARK: - Kanban Column

struct KanbanColumnView: View {
    let status: TaskStatus
    let tasks: [ProjectTask]
    @Binding var draggedTask: ProjectTask?
    let onTaskTap: (ProjectTask) -> Void
    let onTaskDrop: (ProjectTask, TaskStatus) -> Void

    @State private var isTargeted = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Column Header
            HStack {
                Circle()
                    .fill(status.color)
                    .frame(width: 12, height: 12)

                Text(status.displayName)
                    .font(.headline)
                    .fontWeight(.semibold)

                Spacer()

                Text("\(tasks.count)")
                    .font(.caption)
                    .fontWeight(.medium)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(.secondary.opacity(0.15))
                    .clipShape(Capsule())
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)

            // Task List
            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(tasks) { task in
                        KanbanCardView(task: task)
                            .onTapGesture {
                                onTaskTap(task)
                            }
                            .draggable(task.id?.uuidString ?? "") {
                                KanbanCardView(task: task)
                                    .frame(width: 260)
                                    .opacity(0.8)
                                    .onAppear {
                                        draggedTask = task
                                    }
                            }
                    }

                    // Empty state
                    if tasks.isEmpty {
                        Text("No tasks")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 32)
                    }
                }
                .padding(.horizontal, 8)
                .padding(.bottom, 8)
            }
        }
        .frame(width: 280)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(isTargeted ? status.color.opacity(0.1) : Color.secondary.opacity(0.05))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(isTargeted ? status.color : Color.clear, lineWidth: 2)
        )
        .dropDestination(for: String.self) { items, _ in
            guard let taskIdString = items.first,
                  let draggedTask = draggedTask else {
                return false
            }
            onTaskDrop(draggedTask, status)
            self.draggedTask = nil
            return true
        } isTargeted: { targeted in
            withAnimation(.easeInOut(duration: 0.2)) {
                isTargeted = targeted
            }
        }
    }
}

// MARK: - Kanban Card

struct KanbanCardView: View {
    @ObservedObject var task: ProjectTask

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Header: Type and Priority
            HStack {
                TaskTypeBadge(type: task.typeEnum, showText: false, size: 14)

                Text(task.shortId)
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                Spacer()

                PriorityBadge(priority: task.priorityEnum, showText: false, size: .small)
            }

            // Title
            Text(task.title ?? "Untitled")
                .font(.subheadline)
                .fontWeight(.medium)
                .lineLimit(2)
                .multilineTextAlignment(.leading)

            // Story Points
            if task.storyPoints > 0 {
                HStack(spacing: 4) {
                    Image(systemName: "star.fill")
                        .font(.caption2)
                    Text("\(task.storyPoints) points")
                        .font(.caption2)
                }
                .foregroundStyle(.secondary)
            }

            // Footer: Assignee and Due Date
            HStack {
                if let assignee = task.assignee {
                    AvatarView(user: assignee, size: 22)
                }

                Spacer()

                if let dueDate = task.dueDate {
                    DeadlineIndicator(date: dueDate, showIcon: true)
                }
            }

            // Subtask progress
            if !task.subtaskArray.isEmpty {
                let completedSubtasks = task.subtaskArray.filter { $0.isCompleted }.count
                HStack(spacing: 4) {
                    Image(systemName: "checklist")
                        .font(.caption2)
                    Text("\(completedSubtasks)/\(task.subtaskArray.count)")
                        .font(.caption2)

                    GeometryReader { geometry in
                        ZStack(alignment: .leading) {
                            RoundedRectangle(cornerRadius: 2)
                                .fill(.secondary.opacity(0.2))

                            RoundedRectangle(cornerRadius: 2)
                                .fill(.green)
                                .frame(width: geometry.size.width * (task.completionPercentage / 100))
                        }
                    }
                    .frame(height: 4)
                }
                .foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .shadow(color: .black.opacity(0.08), radius: 3, y: 2)
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(task.isOverdue ? Color.red.opacity(0.5) : Color.clear, lineWidth: 2)
        )
    }
}

// MARK: - Task Detail Sheet

struct TaskDetailSheet: View {
    @Environment(\.managedObjectContext) private var viewContext
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var task: ProjectTask

    @State private var editedTitle: String = ""
    @State private var editedDescription: String = ""
    @State private var editedPriority: TaskPriority = .medium
    @State private var editedStatus: TaskStatus = .todo
    @State private var editedDueDate: Date?
    @State private var hasDueDate = false
    @State private var newCommentText = ""

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    // Header
                    taskHeader

                    Divider()

                    // Details
                    detailsSection

                    Divider()

                    // Description
                    descriptionSection

                    Divider()

                    // Comments
                    commentsSection
                }
                .padding()
            }
            .frame(minWidth: 500, minHeight: 600)
            .navigationTitle("Task Details")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        dismiss()
                    }
                }

                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        saveChanges()
                        dismiss()
                    }
                }
            }
        }
        .onAppear {
            loadTaskData()
        }
    }

    private func loadTaskData() {
        editedTitle = task.title ?? ""
        editedDescription = task.taskDescription ?? ""
        editedPriority = task.priorityEnum
        editedStatus = task.statusEnum
        editedDueDate = task.dueDate
        hasDueDate = task.dueDate != nil
    }

    private func saveChanges() {
        task.title = editedTitle
        task.taskDescription = editedDescription
        task.priorityEnum = editedPriority
        task.statusEnum = editedStatus
        task.dueDate = hasDueDate ? editedDueDate : nil
        task.updatedAt = Date()
        viewContext.saveIfNeeded()
    }

    @ViewBuilder
    private var taskHeader: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                TaskTypeBadge(type: task.typeEnum, showText: true)
                Text(task.shortId)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            TextField("Task title", text: $editedTitle)
                .font(.title2)
                .fontWeight(.bold)
                .textFieldStyle(.plain)
        }
    }

    @ViewBuilder
    private var detailsSection: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Details")
                .font(.headline)

            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 16) {
                // Status
                VStack(alignment: .leading, spacing: 4) {
                    Text("Status")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Picker("Status", selection: $editedStatus) {
                        ForEach(TaskStatus.allCases) { status in
                            Text(status.displayName).tag(status)
                        }
                    }
                    .labelsHidden()
                }

                // Priority
                VStack(alignment: .leading, spacing: 4) {
                    Text("Priority")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Picker("Priority", selection: $editedPriority) {
                        ForEach(TaskPriority.allCases) { priority in
                            Label(priority.displayName, systemImage: priority.icon)
                                .tag(priority)
                        }
                    }
                    .labelsHidden()
                }

                // Assignee
                VStack(alignment: .leading, spacing: 4) {
                    Text("Assignee")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let assignee = task.assignee {
                        HStack {
                            AvatarView(user: assignee, size: 24)
                            Text(assignee.name ?? "")
                        }
                    } else {
                        Text("Unassigned")
                            .foregroundStyle(.secondary)
                    }
                }

                // Story Points
                VStack(alignment: .leading, spacing: 4) {
                    Text("Story Points")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("\(task.storyPoints)")
                        .fontWeight(.semibold)
                }

                // Due Date
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text("Due Date")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Toggle("", isOn: $hasDueDate)
                            .labelsHidden()
                            .scaleEffect(0.8)
                    }
                    if hasDueDate {
                        DatePicker("", selection: Binding(
                            get: { editedDueDate ?? Date() },
                            set: { editedDueDate = $0 }
                        ), displayedComponents: .date)
                        .labelsHidden()
                    }
                }

                // Sprint
                VStack(alignment: .leading, spacing: 4) {
                    Text("Sprint")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(task.sprint?.name ?? "Backlog")
                        .fontWeight(task.sprint != nil ? .semibold : .regular)
                        .foregroundStyle(task.sprint != nil ? .primary : .secondary)
                }
            }
        }
    }

    @ViewBuilder
    private var descriptionSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Description")
                .font(.headline)

            TextEditor(text: $editedDescription)
                .font(.body)
                .frame(minHeight: 100)
                .padding(8)
                .background(.secondary.opacity(0.1))
                .clipShape(RoundedRectangle(cornerRadius: 8))
        }
    }

    @ViewBuilder
    private var commentsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Comments (\(task.commentArray.count))")
                .font(.headline)

            // Comment input
            HStack(alignment: .top) {
                TextField("Add a comment...", text: $newCommentText, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                    .lineLimit(3)

                Button {
                    addComment()
                } label: {
                    Image(systemName: "paperplane.fill")
                }
                .disabled(newCommentText.isEmpty)
            }

            // Comment list
            ForEach(task.commentArray) { comment in
                CommentRowView(comment: comment)
            }
        }
    }

    private func addComment() {
        guard !newCommentText.isEmpty else { return }

        let comment = Comment(context: viewContext)
        comment.id = UUID()
        comment.content = newCommentText
        comment.createdAt = Date()
        comment.task = task
        comment.author = User.currentUser(in: viewContext)

        newCommentText = ""
        viewContext.saveIfNeeded()
    }
}

// MARK: - Comment Row

struct CommentRowView: View {
    @ObservedObject var comment: Comment

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            AvatarView(user: comment.author, size: 28)

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(comment.author?.name ?? "Unknown")
                        .font(.caption)
                        .fontWeight(.semibold)

                    Text(comment.createdAt?.formatted(.relative(presentation: .named)) ?? "")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                Text(comment.content ?? "")
                    .font(.subheadline)
            }

            Spacer()
        }
        .padding(8)
        .background(.secondary.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

// MARK: - Preview

#Preview {
    KanbanBoardView()
        .environment(\.managedObjectContext, PersistenceController.preview.container.viewContext)
        .environmentObject(AppState())
        .frame(width: 1200, height: 700)
}
