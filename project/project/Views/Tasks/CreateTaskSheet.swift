//
//  CreateTaskSheet.swift
//  project
//
//  Sheet for creating new tasks
//

import SwiftUI
import CoreData

struct CreateTaskSheet: View {
    @Environment(\.managedObjectContext) private var viewContext
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var appState: AppState

    // Task Fields
    @State private var title = ""
    @State private var description = ""
    @State private var taskType: TaskType = .task
    @State private var priority: TaskPriority = .medium
    @State private var storyPoints: Int16 = 3
    @State private var selectedProject: Project?
    @State private var selectedSprint: Sprint?
    @State private var selectedAssignee: User?
    @State private var hasDueDate = false
    @State private var dueDate = Calendar.current.date(byAdding: .day, value: 7, to: Date())!

    // Fetch projects and users
    @FetchRequest(
        sortDescriptors: [NSSortDescriptor(keyPath: \Project.name, ascending: true)],
        predicate: NSPredicate(format: "isArchived == NO"),
        animation: .default
    )
    private var projects: FetchedResults<Project>

    @FetchRequest(
        sortDescriptors: [NSSortDescriptor(keyPath: \User.name, ascending: true)],
        animation: .default
    )
    private var users: FetchedResults<User>

    private var availableSprints: [Sprint] {
        selectedProject?.sprintArray.filter { $0.statusEnum != .completed } ?? []
    }

    var body: some View {
        NavigationStack {
            Form {
                // Title Section
                Section("Task Title") {
                    TextField("Enter task title", text: $title)
                        .textFieldStyle(.plain)
                        .font(.title3)
                }

                // Type and Priority
                Section("Classification") {
                    Picker("Type", selection: $taskType) {
                        ForEach(TaskType.allCases) { type in
                            Label(type.displayName, systemImage: type.icon)
                                .tag(type)
                        }
                    }

                    Picker("Priority", selection: $priority) {
                        ForEach(TaskPriority.allCases) { p in
                            Label(p.displayName, systemImage: p.icon)
                                .foregroundStyle(p.color)
                                .tag(p)
                        }
                    }

                    Stepper("Story Points: \(storyPoints)", value: $storyPoints, in: 1...21)
                }

                // Assignment
                Section("Assignment") {
                    Picker("Project", selection: $selectedProject) {
                        Text("Select Project").tag(nil as Project?)
                        ForEach(projects) { project in
                            HStack {
                                Circle()
                                    .fill(project.projectColor)
                                    .frame(width: 10, height: 10)
                                Text(project.name ?? "")
                            }
                            .tag(project as Project?)
                        }
                    }

                    if selectedProject != nil {
                        Picker("Sprint", selection: $selectedSprint) {
                            Text("Backlog").tag(nil as Sprint?)
                            ForEach(availableSprints) { sprint in
                                Text(sprint.name ?? "").tag(sprint as Sprint?)
                            }
                        }
                    }

                    Picker("Assignee", selection: $selectedAssignee) {
                        Text("Unassigned").tag(nil as User?)
                        ForEach(users) { user in
                            HStack {
                                AvatarView(user: user, size: 20)
                                Text(user.name ?? "")
                            }
                            .tag(user as User?)
                        }
                    }
                }

                // Due Date
                Section("Due Date") {
                    Toggle("Set Due Date", isOn: $hasDueDate)

                    if hasDueDate {
                        DatePicker("Due Date", selection: $dueDate, displayedComponents: .date)

                        // Quick date buttons
                        HStack {
                            ForEach([1, 3, 7, 14], id: \.self) { days in
                                Button(days == 1 ? "Tomorrow" : "\(days) days") {
                                    dueDate = Calendar.current.date(byAdding: .day, value: days, to: Date())!
                                }
                                .buttonStyle(.bordered)
                                .controlSize(.small)
                            }
                        }
                    }
                }

                // Description
                Section("Description") {
                    TextEditor(text: $description)
                        .frame(minHeight: 80)
                }
            }
            .formStyle(.grouped)
            .frame(minWidth: 500, minHeight: 550)
            .navigationTitle("New Task")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        dismiss()
                    }
                }

                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") {
                        createTask()
                    }
                    .disabled(title.isEmpty || selectedProject == nil)
                    .buttonStyle(.borderedProminent)
                }
            }
            .onAppear {
                // Pre-select current project if available
                if selectedProject == nil {
                    selectedProject = appState.selectedProject ?? projects.first
                }
            }
            .onChange(of: selectedProject) { _, _ in
                // Reset sprint when project changes
                selectedSprint = nil
            }
            .onChange(of: taskType) { _, newType in
                // Update default story points based on type
                storyPoints = newType.defaultStoryPoints
            }
        }
    }

    private func createTask() {
        guard let project = selectedProject else { return }

        let task = ProjectTask.create(
            in: viewContext,
            title: title,
            project: project,
            type: taskType,
            priority: priority,
            sprint: selectedSprint,
            assignee: selectedAssignee,
            dueDate: hasDueDate ? dueDate : nil,
            description: description.isEmpty ? nil : description,
            storyPoints: storyPoints
        )

        viewContext.saveIfNeeded()
        dismiss()
    }
}

// MARK: - Preview

#Preview {
    CreateTaskSheet()
        .environment(\.managedObjectContext, PersistenceController.preview.container.viewContext)
        .environmentObject(AppState())
}
