//
//  SidebarView.swift
//  project
//
//  Sidebar navigation view
//

import SwiftUI
import CoreData

struct SidebarView: View {
    @EnvironmentObject var appState: AppState
    @Environment(\.managedObjectContext) private var viewContext

    let projects: [Project]

    @State private var isProjectsExpanded = true

    var body: some View {
        List(selection: Binding(
            get: { appState.selectedSection },
            set: { appState.selectedSection = $0 ?? .dashboard }
        )) {
            // Navigation Sections
            Section("Navigation") {
                ForEach([NavigationSection.dashboard, .myTodo]) { section in
                    NavigationLink(value: section) {
                        Label(section.rawValue, systemImage: section.icon)
                    }
                }
            }

            // Projects Section
            Section {
                DisclosureGroup(isExpanded: $isProjectsExpanded) {
                    ForEach(projects, id: \.self) { project in
                        ProjectRowView(project: project)
                            .tag(project)
                    }
                } label: {
                    HStack {
                        Label("Projects", systemImage: "folder")
                        Spacer()
                        Text("\(projects.count)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 2)
                            .background(.secondary.opacity(0.2))
                            .clipShape(Capsule())
                    }
                }
            }

            // Project Views (when project is selected)
            if appState.selectedProject != nil {
                Section("Project Views") {
                    ForEach([NavigationSection.kanban, .backlog, .sprints, .gantt]) { section in
                        NavigationLink(value: section) {
                            Label(section.rawValue, systemImage: section.icon)
                        }
                    }
                }
            }

            // Analytics & Team
            Section("Analytics") {
                NavigationLink(value: NavigationSection.reports) {
                    Label("Reports", systemImage: NavigationSection.reports.icon)
                }
            }

            Section("Team") {
                NavigationLink(value: NavigationSection.team) {
                    Label("Team Members", systemImage: NavigationSection.team.icon)
                }
            }
        }
        .listStyle(.sidebar)
        .navigationTitle("Project Manager")
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Button {
                    appState.isShowingNewProjectSheet = true
                } label: {
                    Image(systemName: "folder.badge.plus")
                }
                .help("New Project")
            }
        }
        .searchable(text: $appState.searchText, placement: .sidebar, prompt: "Search...")
    }
}

// MARK: - Project Row View

struct ProjectRowView: View {
    @EnvironmentObject var appState: AppState
    @ObservedObject var project: Project

    var body: some View {
        Button {
            appState.selectedProject = project
            appState.selectedSection = .kanban
        } label: {
            HStack(spacing: 8) {
                Circle()
                    .fill(project.projectColor)
                    .frame(width: 10, height: 10)

                Text(project.name ?? "Untitled")
                    .lineLimit(1)

                Spacer()

                if project == appState.selectedProject {
                    Image(systemName: "checkmark")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .buttonStyle(.plain)
        .contextMenu {
            Button {
                appState.selectedProject = project
                appState.selectedSection = .kanban
            } label: {
                Label("Open Kanban", systemImage: "rectangle.split.3x1")
            }

            Button {
                appState.selectedProject = project
                appState.selectedSection = .backlog
            } label: {
                Label("Open Backlog", systemImage: "tray.full")
            }

            Divider()

            Button(role: .destructive) {
                deleteProject()
            } label: {
                Label("Delete", systemImage: "trash")
            }
        }
    }

    private func deleteProject() {
        withAnimation {
            if appState.selectedProject == project {
                appState.selectedProject = nil
            }
            project.managedObjectContext?.delete(project)
            try? project.managedObjectContext?.save()
        }
    }
}

// MARK: - Preview

#Preview {
    SidebarView(projects: [])
        .environmentObject(AppState())
        .environment(\.managedObjectContext, PersistenceController.preview.container.viewContext)
}
