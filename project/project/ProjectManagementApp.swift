//
//  ProjectManagementApp.swift
//  project
//
//  macOS Project Management Application
//  SwiftUI + Core Data + CloudKit
//

import SwiftUI

@main
struct ProjectManagementApp: App {
    @StateObject private var persistenceController = PersistenceController.shared
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(\.managedObjectContext, persistenceController.container.viewContext)
                .environmentObject(persistenceController)
                .environmentObject(appState)
                .frame(minWidth: 1200, minHeight: 700)
        }
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unified(showsTitle: true))
        .commands {
            ProjectCommands()
            SidebarCommands()
        }

        Settings {
            SettingsView()
                .environmentObject(appState)
        }
    }
}

// MARK: - App State
class AppState: ObservableObject {
    @Published var selectedProject: Project?
    @Published var selectedSection: NavigationSection = .dashboard
    @Published var isShowingNewProjectSheet = false
    @Published var isShowingNewTaskSheet = false
    @Published var searchText = ""

    // Sync status
    @Published var syncStatus: SyncStatus = .idle
}

// MARK: - Navigation Section
enum NavigationSection: String, CaseIterable, Identifiable {
    case dashboard = "Dashboard"
    case myTodo = "My Todo"
    case kanban = "Kanban Board"
    case backlog = "Backlog"
    case sprints = "Sprints"
    case reports = "Reports"
    case gantt = "Timeline"
    case team = "Team"
    case settings = "Settings"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .dashboard: return "square.grid.2x2"
        case .myTodo: return "checklist"
        case .kanban: return "rectangle.split.3x1"
        case .backlog: return "tray.full"
        case .sprints: return "arrow.triangle.2.circlepath"
        case .reports: return "chart.bar.xaxis"
        case .gantt: return "calendar.day.timeline.left"
        case .team: return "person.3"
        case .settings: return "gearshape"
        }
    }
}

// MARK: - Sync Status
enum SyncStatus: Equatable {
    case idle
    case syncing
    case synced
    case error(String)

    var icon: String {
        switch self {
        case .idle: return "cloud"
        case .syncing: return "arrow.triangle.2.circlepath"
        case .synced: return "checkmark.icloud"
        case .error: return "exclamationmark.icloud"
        }
    }

    var color: Color {
        switch self {
        case .idle: return .secondary
        case .syncing: return .blue
        case .synced: return .green
        case .error: return .red
        }
    }
}

// MARK: - Custom Commands
struct ProjectCommands: Commands {
    var body: some Commands {
        CommandGroup(after: .newItem) {
            Button("New Project...") {
                NotificationCenter.default.post(name: .newProject, object: nil)
            }
            .keyboardShortcut("n", modifiers: [.command, .shift])

            Button("New Task...") {
                NotificationCenter.default.post(name: .newTask, object: nil)
            }
            .keyboardShortcut("t", modifiers: [.command])

            Button("New Sprint...") {
                NotificationCenter.default.post(name: .newSprint, object: nil)
            }
            .keyboardShortcut("s", modifiers: [.command, .shift])
        }
    }
}

// MARK: - Notification Names
extension Notification.Name {
    static let newProject = Notification.Name("newProject")
    static let newTask = Notification.Name("newTask")
    static let newSprint = Notification.Name("newSprint")
}

// MARK: - Settings View
struct SettingsView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        TabView {
            GeneralSettingsView()
                .tabItem {
                    Label("General", systemImage: "gear")
                }

            AppearanceSettingsView()
                .tabItem {
                    Label("Appearance", systemImage: "paintbrush")
                }

            SyncSettingsView()
                .tabItem {
                    Label("Sync", systemImage: "arrow.triangle.2.circlepath")
                }
        }
        .frame(width: 450, height: 300)
    }
}

struct GeneralSettingsView: View {
    @AppStorage("defaultSprintDuration") private var defaultSprintDuration = 14
    @AppStorage("showCompletedTasks") private var showCompletedTasks = true

    var body: some View {
        Form {
            Picker("Default Sprint Duration", selection: $defaultSprintDuration) {
                Text("1 Week").tag(7)
                Text("2 Weeks").tag(14)
                Text("3 Weeks").tag(21)
                Text("4 Weeks").tag(28)
            }

            Toggle("Show Completed Tasks", isOn: $showCompletedTasks)
        }
        .padding()
    }
}

struct AppearanceSettingsView: View {
    @AppStorage("accentColorName") private var accentColorName = "blue"

    var body: some View {
        Form {
            Picker("Accent Color", selection: $accentColorName) {
                Text("Blue").tag("blue")
                Text("Purple").tag("purple")
                Text("Green").tag("green")
                Text("Orange").tag("orange")
            }
        }
        .padding()
    }
}

struct SyncSettingsView: View {
    @AppStorage("enableCloudSync") private var enableCloudSync = true

    var body: some View {
        Form {
            Toggle("Enable iCloud Sync", isOn: $enableCloudSync)

            Text("Sync your projects and tasks across all your devices using iCloud.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
    }
}
