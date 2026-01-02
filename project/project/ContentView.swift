//
//  ContentView.swift
//  project
//
//  Main content view with three-column NavigationSplitView
//

import SwiftUI
import CoreData

struct ContentView: View {
    @Environment(\.managedObjectContext) private var viewContext
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var persistenceController: PersistenceController

    @State private var columnVisibility: NavigationSplitViewVisibility = .all

    // Fetch projects
    @FetchRequest(
        sortDescriptors: [NSSortDescriptor(keyPath: \Project.name, ascending: true)],
        predicate: NSPredicate(format: "isArchived == NO"),
        animation: .default
    )
    private var projects: FetchedResults<Project>

    var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            // SIDEBAR
            SidebarView(projects: Array(projects))
                .navigationSplitViewColumnWidth(min: 220, ideal: 250, max: 300)
        } content: {
            // CONTENT COLUMN
            ContentColumnView()
                .navigationSplitViewColumnWidth(min: 300, ideal: 350, max: 450)
        } detail: {
            // DETAIL COLUMN
            DetailColumnView()
        }
        .navigationSplitViewStyle(.balanced)
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                toolbarItems
            }

            ToolbarItemGroup(placement: .status) {
                syncStatusView
            }
        }
        .sheet(isPresented: $appState.isShowingNewProjectSheet) {
            CreateProjectSheet()
        }
        .sheet(isPresented: $appState.isShowingNewTaskSheet) {
            CreateTaskSheet()
        }
        .onReceive(NotificationCenter.default.publisher(for: .newProject)) { _ in
            appState.isShowingNewProjectSheet = true
        }
        .onReceive(NotificationCenter.default.publisher(for: .newTask)) { _ in
            appState.isShowingNewTaskSheet = true
        }
        .onAppear {
            initializeIfNeeded()
        }
    }

    // MARK: - Toolbar Items

    @ViewBuilder
    private var toolbarItems: some View {
        Button {
            appState.isShowingNewTaskSheet = true
        } label: {
            Label("New Task", systemImage: "plus")
        }
        .keyboardShortcut("t", modifiers: .command)

        Menu {
            Button {
                appState.isShowingNewProjectSheet = true
            } label: {
                Label("New Project", systemImage: "folder.badge.plus")
            }

            Button {
                // New sprint action
            } label: {
                Label("New Sprint", systemImage: "arrow.triangle.2.circlepath")
            }
        } label: {
            Label("Add", systemImage: "plus.circle")
        }
    }

    @ViewBuilder
    private var syncStatusView: some View {
        HStack(spacing: 4) {
            Image(systemName: persistenceController.syncStatus.icon)
                .foregroundStyle(persistenceController.syncStatus.color)
                .symbolEffect(.pulse, isActive: persistenceController.syncStatus == .syncing)

            if case .synced = persistenceController.syncStatus,
               let lastSync = persistenceController.lastSyncDate {
                Text(lastSync, style: .relative)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - Initialization

    private func initializeIfNeeded() {
        // Create current user if doesn't exist
        let _ = User.getOrCreateCurrentUser(in: viewContext)

        // Create sample project if no projects exist
        if projects.isEmpty {
            createSampleProject()
        }

        viewContext.saveIfNeeded()
    }

    private func createSampleProject() {
        let currentUser = User.getOrCreateCurrentUser(in: viewContext)

        let project = Project.create(
            in: viewContext,
            name: "My First Project",
            description: "A sample project to get you started",
            color: "blue",
            owner: currentUser
        )

        // Create a sample sprint
        let sprint = Sprint.create(
            in: viewContext,
            name: "Sprint 1",
            project: project,
            goal: "Initial setup and planning",
            startDate: Date(),
            endDate: Calendar.current.date(byAdding: .day, value: 14, to: Date())!
        )
        sprint.statusEnum = .active

        // Create sample tasks
        let taskData: [(String, TaskStatus, TaskPriority, TaskType)] = [
            ("Set up development environment", .done, .high, .task),
            ("Create project structure", .done, .high, .task),
            ("Design database schema", .inProgress, .critical, .story),
            ("Implement user authentication", .inProgress, .high, .story),
            ("Write unit tests", .todo, .medium, .task),
            ("Fix navigation bug", .inReview, .high, .bug),
            ("Add dark mode support", .todo, .low, .story),
        ]

        for (index, (title, status, priority, type)) in taskData.enumerated() {
            let task = ProjectTask.create(
                in: viewContext,
                title: title,
                project: project,
                type: type,
                priority: priority,
                sprint: status == .todo ? nil : sprint,
                assignee: status == .inProgress ? currentUser : nil
            )
            task.statusEnum = status
            task.orderIndex = Int32(index)
            task.storyPoints = Int16([1, 2, 3, 5, 8].randomElement()!)

            if Bool.random() {
                task.dueDate = Calendar.current.date(byAdding: .day, value: Int.random(in: -2...10), to: Date())
            }
        }

        appState.selectedProject = project
    }
}

// MARK: - Content Column View

struct ContentColumnView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        Group {
            switch appState.selectedSection {
            case .dashboard:
                DashboardContentView()
            case .myTodo:
                PersonalTodoView()
            case .kanban:
                if appState.selectedProject != nil {
                    KanbanBoardView()
                } else {
                    NoProjectSelectedView()
                }
            case .backlog:
                if appState.selectedProject != nil {
                    BacklogView()
                } else {
                    NoProjectSelectedView()
                }
            case .sprints:
                if appState.selectedProject != nil {
                    SprintListView()
                } else {
                    NoProjectSelectedView()
                }
            case .reports:
                ReportsView()
            case .gantt:
                if appState.selectedProject != nil {
                    GanttChartView()
                } else {
                    NoProjectSelectedView()
                }
            case .team:
                TeamMembersView()
            case .settings:
                SettingsContentView()
            }
        }
        .navigationTitle(appState.selectedSection.rawValue)
    }
}

// MARK: - Detail Column View

struct DetailColumnView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        Group {
            switch appState.selectedSection {
            case .dashboard:
                if let project = appState.selectedProject {
                    ProjectDetailView(project: project)
                } else {
                    WelcomeView()
                }
            case .kanban, .backlog, .sprints:
                TaskDetailPlaceholderView()
            default:
                EmptyDetailView()
            }
        }
    }
}

// MARK: - Placeholder Views

struct NoProjectSelectedView: View {
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "folder.badge.questionmark")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            Text("No Project Selected")
                .font(.headline)
            Text("Select a project from the sidebar to view its content")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct WelcomeView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "square.grid.2x2")
                .font(.system(size: 64))
                .foregroundStyle(.blue)

            Text("Welcome to Project Manager")
                .font(.largeTitle)
                .fontWeight(.bold)

            Text("Organize your work with agile project management")
                .font(.title3)
                .foregroundStyle(.secondary)

            Button {
                appState.isShowingNewProjectSheet = true
            } label: {
                Label("Create New Project", systemImage: "plus")
                    .font(.headline)
                    .padding()
            }
            .buttonStyle(.borderedProminent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct EmptyDetailView: View {
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            Text("Select an item to view details")
                .font(.headline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct TaskDetailPlaceholderView: View {
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "checkmark.square")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            Text("Select a task to view details")
                .font(.headline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct SettingsContentView: View {
    var body: some View {
        Text("Settings")
            .font(.largeTitle)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct DashboardContentView: View {
    var body: some View {
        DashboardView()
    }
}

// MARK: - Preview

#Preview {
    ContentView()
        .environment(\.managedObjectContext, PersistenceController.preview.container.viewContext)
        .environmentObject(PersistenceController.preview)
        .environmentObject(AppState())
}
