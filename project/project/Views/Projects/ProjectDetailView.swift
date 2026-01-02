//
//  ProjectDetailView.swift
//  project
//
//  Detailed view for a selected project
//

import SwiftUI
import CoreData
import Charts

struct ProjectDetailView: View {
    @ObservedObject var project: Project
    @Environment(\.managedObjectContext) private var viewContext
    @EnvironmentObject var appState: AppState

    @State private var selectedTab: ProjectTab = .overview

    var body: some View {
        VStack(spacing: 0) {
            // Project Header
            projectHeader

            Divider()

            // Tab Selection
            Picker("View", selection: $selectedTab) {
                ForEach(ProjectTab.allCases) { tab in
                    Text(tab.rawValue).tag(tab)
                }
            }
            .pickerStyle(.segmented)
            .padding()

            // Tab Content
            ScrollView {
                switch selectedTab {
                case .overview:
                    overviewContent
                case .tasks:
                    tasksContent
                case .sprints:
                    sprintsContent
                case .settings:
                    settingsContent
                }
            }
        }
    }

    // MARK: - Project Header

    @ViewBuilder
    private var projectHeader: some View {
        HStack(spacing: 16) {
            // Project Icon
            RoundedRectangle(cornerRadius: 12)
                .fill(project.projectColor.gradient)
                .frame(width: 64, height: 64)
                .overlay(
                    Text(String((project.name ?? "P").prefix(1)).uppercased())
                        .font(.title)
                        .fontWeight(.bold)
                        .foregroundStyle(.white)
                )

            // Project Info
            VStack(alignment: .leading, spacing: 4) {
                Text(project.name ?? "Untitled Project")
                    .font(.title2)
                    .fontWeight(.bold)

                if let description = project.projectDescription, !description.isEmpty {
                    Text(description)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }

                HStack(spacing: 12) {
                    Label("\(project.totalTasks) tasks", systemImage: "checkmark.square")
                    Label("\(project.memberArray.count + 1) members", systemImage: "person.2")

                    if let activeSprint = project.activeSprint {
                        Label(activeSprint.name ?? "Active Sprint", systemImage: "arrow.triangle.2.circlepath")
                            .foregroundStyle(.blue)
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }

            Spacer()

            // Progress Ring
            GradientProgressRing(
                progress: project.completionPercentage / 100,
                lineWidth: 8,
                size: 64
            )
        }
        .padding()
    }

    // MARK: - Overview Tab

    @ViewBuilder
    private var overviewContent: some View {
        VStack(spacing: 24) {
            // Stats Cards
            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 16) {
                StatCard(title: "Total Tasks", value: "\(project.totalTasks)", icon: "checkmark.square.fill", color: .blue)
                StatCard(title: "Completed", value: "\(project.completedTasks)", icon: "checkmark.circle.fill", color: .green)
                StatCard(title: "In Progress", value: "\(project.inProgressTasks)", icon: "clock.fill", color: .orange)
                StatCard(title: "Story Points", value: "\(project.totalStoryPoints)", icon: "star.fill", color: .purple)
            }

            // Charts Row
            HStack(spacing: 16) {
                // Status Distribution
                DashboardCard(title: "Task Status") {
                    TaskStatusPieChart(tasks: project.taskArray)
                }

                // Priority Distribution
                DashboardCard(title: "Priority Breakdown") {
                    PriorityBarChart(tasks: project.taskArray)
                }
            }
            .frame(height: 250)

            // Active Sprint (if any)
            if let sprint = project.activeSprint {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Active Sprint")
                        .font(.headline)

                    ActiveSprintCard(sprint: sprint)
                }
            }

            // Recent Activity
            VStack(alignment: .leading, spacing: 12) {
                Text("Recent Tasks")
                    .font(.headline)

                ForEach(project.taskArray.prefix(5)) { task in
                    RecentTaskRow(task: task)
                }
            }
            .padding()
            .background(.background)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .shadow(color: .black.opacity(0.05), radius: 5)
        }
        .padding()
    }

    // MARK: - Tasks Tab

    @ViewBuilder
    private var tasksContent: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Task counts by status
            HStack(spacing: 12) {
                ForEach(TaskStatus.allCases) { status in
                    let count = project.tasks(with: status).count
                    VStack(spacing: 4) {
                        Text("\(count)")
                            .font(.title2)
                            .fontWeight(.bold)
                            .foregroundStyle(status.color)
                        Text(status.displayName)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(status.color.opacity(0.1))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
            }

            // Task List by Type
            ForEach(TaskType.allCases) { type in
                let typeTasks = project.taskArray.filter { $0.typeEnum == type }
                if !typeTasks.isEmpty {
                    DisclosureGroup {
                        ForEach(typeTasks) { task in
                            HStack(spacing: 12) {
                                StatusBadge(status: task.statusEnum, showIcon: true, size: .small)
                                Text(task.title ?? "")
                                Spacer()
                                if let assignee = task.assignee {
                                    AvatarView(user: assignee, size: 20)
                                }
                                PriorityBadge(priority: task.priorityEnum, showText: false, size: .small)
                            }
                            .padding(.vertical, 4)
                        }
                    } label: {
                        HStack {
                            TaskTypeBadge(type: type, showText: true)
                            Spacer()
                            Text("\(typeTasks.count)")
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .padding()
    }

    // MARK: - Sprints Tab

    @ViewBuilder
    private var sprintsContent: some View {
        VStack(alignment: .leading, spacing: 16) {
            if project.sprintArray.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "arrow.triangle.2.circlepath")
                        .font(.system(size: 40))
                        .foregroundStyle(.secondary)
                    Text("No sprints yet")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 40)
            } else {
                ForEach(project.sprintArray) { sprint in
                    SprintRowView(sprint: sprint)
                }
            }
        }
        .padding()
    }

    // MARK: - Settings Tab

    @ViewBuilder
    private var settingsContent: some View {
        VStack(alignment: .leading, spacing: 24) {
            // Project Details Section
            GroupBox("Project Details") {
                VStack(alignment: .leading, spacing: 12) {
                    LabeledContent("Name", value: project.name ?? "")
                    LabeledContent("Created", value: project.createdAt?.formatted(.dateTime) ?? "")
                    LabeledContent("Owner", value: project.owner?.name ?? "Unknown")

                    Divider()

                    // Color picker
                    HStack {
                        Text("Color")
                        Spacer()
                        Circle()
                            .fill(project.projectColor)
                            .frame(width: 24, height: 24)
                    }
                }
                .padding()
            }

            // Team Members
            GroupBox("Team Members (\(project.memberArray.count + 1))") {
                VStack(alignment: .leading, spacing: 8) {
                    // Owner
                    if let owner = project.owner {
                        HStack {
                            AvatarView(user: owner, size: 32)
                            VStack(alignment: .leading) {
                                Text(owner.name ?? "")
                                    .fontWeight(.medium)
                                Text("Owner")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                        }
                    }

                    // Members
                    ForEach(project.memberArray) { member in
                        HStack {
                            AvatarView(user: member, size: 32)
                            VStack(alignment: .leading) {
                                Text(member.name ?? "")
                                Text(member.roleEnum.displayName)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                        }
                    }
                }
                .padding()
            }

            // Danger Zone
            GroupBox("Danger Zone") {
                VStack(alignment: .leading, spacing: 12) {
                    Button(role: .destructive) {
                        archiveProject()
                    } label: {
                        Label("Archive Project", systemImage: "archivebox")
                    }

                    Button(role: .destructive) {
                        deleteProject()
                    } label: {
                        Label("Delete Project", systemImage: "trash")
                    }
                }
                .padding()
            }
        }
        .padding()
    }

    // MARK: - Actions

    private func archiveProject() {
        project.archive()
        appState.selectedProject = nil
        viewContext.saveIfNeeded()
    }

    private func deleteProject() {
        appState.selectedProject = nil
        viewContext.delete(project)
        viewContext.saveIfNeeded()
    }
}

// MARK: - Project Tab

enum ProjectTab: String, CaseIterable, Identifiable {
    case overview = "Overview"
    case tasks = "Tasks"
    case sprints = "Sprints"
    case settings = "Settings"

    var id: String { rawValue }
}

// MARK: - Preview

#Preview {
    let context = PersistenceController.preview.container.viewContext
    let project = Project(context: context)
    project.id = UUID()
    project.name = "Preview Project"
    project.projectDescription = "A sample project for preview"
    project.color = "blue"
    project.createdAt = Date()
    project.updatedAt = Date()

    return ProjectDetailView(project: project)
        .environment(\.managedObjectContext, context)
        .environmentObject(AppState())
}
