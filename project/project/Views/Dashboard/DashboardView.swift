//
//  DashboardView.swift
//  project
//
//  Main dashboard with overview cards and charts
//

import SwiftUI
import CoreData
import Charts

struct DashboardView: View {
    @Environment(\.managedObjectContext) private var viewContext
    @EnvironmentObject var appState: AppState

    @FetchRequest(
        sortDescriptors: [NSSortDescriptor(keyPath: \Project.name, ascending: true)],
        predicate: NSPredicate(format: "isArchived == NO"),
        animation: .default
    )
    private var projects: FetchedResults<Project>

    @FetchRequest(
        sortDescriptors: [NSSortDescriptor(keyPath: \ProjectTask.createdAt, ascending: false)],
        animation: .default
    )
    private var allTasks: FetchedResults<ProjectTask>

    @FetchRequest(
        sortDescriptors: [NSSortDescriptor(keyPath: \Sprint.startDate, ascending: false)],
        predicate: NSPredicate(format: "status == %d", SprintStatus.active.rawValue),
        animation: .default
    )
    private var activeSprints: FetchedResults<Sprint>

    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                // Summary Cards Row
                summaryCardsSection

                // Charts Row
                chartsSection

                // Active Sprints
                if !activeSprints.isEmpty {
                    activeSprintsSection
                }

                // Recent Activity
                recentActivitySection

                // Quick Actions
                quickActionsSection
            }
            .padding()
        }
        .background(Color(nsColor: .windowBackgroundColor))
    }

    // MARK: - Summary Cards

    @ViewBuilder
    private var summaryCardsSection: some View {
        LazyVGrid(columns: [
            GridItem(.flexible()),
            GridItem(.flexible()),
            GridItem(.flexible()),
            GridItem(.flexible())
        ], spacing: 16) {
            SummaryCard(
                title: "Projects",
                value: "\(projects.count)",
                icon: "folder.fill",
                color: .blue
            )

            SummaryCard(
                title: "Total Tasks",
                value: "\(allTasks.count)",
                icon: "checkmark.square.fill",
                color: .green
            )

            SummaryCard(
                title: "In Progress",
                value: "\(inProgressCount)",
                icon: "clock.fill",
                color: .orange
            )

            SummaryCard(
                title: "Completed",
                value: "\(completedCount)",
                icon: "checkmark.circle.fill",
                color: .purple
            )
        }
    }

    private var inProgressCount: Int {
        allTasks.filter { TaskStatus(rawValue: $0.status) == .inProgress }.count
    }

    private var completedCount: Int {
        allTasks.filter { TaskStatus(rawValue: $0.status) == .done }.count
    }

    // MARK: - Charts Section

    @ViewBuilder
    private var chartsSection: some View {
        HStack(spacing: 16) {
            // Task Status Distribution
            DashboardCard(title: "Task Distribution") {
                TaskStatusPieChart(tasks: Array(allTasks))
            }

            // Priority Distribution
            DashboardCard(title: "Priority Overview") {
                PriorityBarChart(tasks: Array(allTasks))
            }

            // Project Progress
            DashboardCard(title: "Project Progress") {
                ProjectProgressList(projects: Array(projects))
            }
        }
        .frame(height: 280)
    }

    // MARK: - Active Sprints

    @ViewBuilder
    private var activeSprintsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Active Sprints")
                .font(.headline)

            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 12) {
                ForEach(activeSprints) { sprint in
                    ActiveSprintCard(sprint: sprint)
                }
            }
        }
    }

    // MARK: - Recent Activity

    @ViewBuilder
    private var recentActivitySection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Recent Tasks")
                .font(.headline)

            DashboardCard(title: "") {
                VStack(spacing: 8) {
                    ForEach(Array(allTasks.prefix(5))) { task in
                        RecentTaskRow(task: task)
                    }

                    if allTasks.isEmpty {
                        Text("No tasks yet")
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity)
                            .padding()
                    }
                }
            }
        }
    }

    // MARK: - Quick Actions

    @ViewBuilder
    private var quickActionsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Quick Actions")
                .font(.headline)

            HStack(spacing: 12) {
                QuickActionButton(
                    title: "New Task",
                    icon: "plus.square.fill",
                    color: .blue
                ) {
                    appState.isShowingNewTaskSheet = true
                }

                QuickActionButton(
                    title: "New Project",
                    icon: "folder.badge.plus",
                    color: .green
                ) {
                    appState.isShowingNewProjectSheet = true
                }

                QuickActionButton(
                    title: "View Reports",
                    icon: "chart.bar.fill",
                    color: .purple
                ) {
                    appState.selectedSection = .reports
                }

                QuickActionButton(
                    title: "Team",
                    icon: "person.3.fill",
                    color: .orange
                ) {
                    appState.selectedSection = .team
                }
            }
        }
    }
}

// MARK: - Summary Card

struct SummaryCard: View {
    let title: String
    let value: String
    let icon: String
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: icon)
                    .font(.title2)
                    .foregroundStyle(color)
                Spacer()
            }

            Text(value)
                .font(.system(size: 32, weight: .bold))

            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.05), radius: 5)
    }
}

// MARK: - Dashboard Card

struct DashboardCard<Content: View>: View {
    let title: String
    @ViewBuilder let content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if !title.isEmpty {
                Text(title)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundStyle(.secondary)
            }

            content()
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.05), radius: 5)
    }
}

// MARK: - Task Status Pie Chart

struct TaskStatusPieChart: View {
    let tasks: [ProjectTask]

    private var statusData: [StatusChartData] {
        TaskStatus.allCases.map { status in
            let count = tasks.filter { $0.statusEnum == status }.count
            return StatusChartData(status: status, count: count)
        }.filter { $0.count > 0 }
    }

    var body: some View {
        if statusData.isEmpty {
            Text("No tasks")
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            Chart(statusData) { data in
                SectorMark(
                    angle: .value("Count", data.count),
                    innerRadius: .ratio(0.5),
                    angularInset: 1.5
                )
                .cornerRadius(4)
                .foregroundStyle(by: .value("Status", data.status.displayName))
            }
            .chartForegroundStyleScale([
                TaskStatus.todo.displayName: TaskStatus.todo.color,
                TaskStatus.inProgress.displayName: TaskStatus.inProgress.color,
                TaskStatus.inReview.displayName: TaskStatus.inReview.color,
                TaskStatus.done.displayName: TaskStatus.done.color
            ])
            .chartLegend(position: .bottom, spacing: 8)
        }
    }
}

struct StatusChartData: Identifiable {
    let id = UUID()
    let status: TaskStatus
    let count: Int
}

// MARK: - Priority Bar Chart

struct PriorityBarChart: View {
    let tasks: [ProjectTask]

    private var priorityData: [PriorityChartData] {
        TaskPriority.allCases.map { priority in
            let count = tasks.filter { $0.priorityEnum == priority }.count
            return PriorityChartData(priority: priority, count: count)
        }
    }

    var body: some View {
        Chart(priorityData) { data in
            BarMark(
                x: .value("Priority", data.priority.displayName),
                y: .value("Count", data.count)
            )
            .foregroundStyle(data.priority.color)
            .cornerRadius(4)
        }
        .chartYAxis {
            AxisMarks(position: .leading)
        }
    }
}

struct PriorityChartData: Identifiable {
    let id = UUID()
    let priority: TaskPriority
    let count: Int
}

// MARK: - Project Progress List

struct ProjectProgressList: View {
    let projects: [Project]

    var body: some View {
        VStack(spacing: 12) {
            ForEach(projects.prefix(4)) { project in
                HStack {
                    Circle()
                        .fill(project.projectColor)
                        .frame(width: 8, height: 8)

                    Text(project.name ?? "Untitled")
                        .font(.subheadline)
                        .lineLimit(1)

                    Spacer()

                    ProgressRing(
                        progress: project.completionPercentage / 100,
                        lineWidth: 4,
                        size: 32,
                        color: project.projectColor,
                        showPercentage: false
                    )

                    Text("\(Int(project.completionPercentage))%")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .frame(width: 35, alignment: .trailing)
                }
            }

            if projects.isEmpty {
                Text("No projects")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
            }
        }
    }
}

// MARK: - Active Sprint Card

struct ActiveSprintCard: View {
    @ObservedObject var sprint: Sprint

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(sprint.name ?? "Untitled Sprint")
                        .font(.headline)

                    Text(sprint.project?.name ?? "")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                ProgressRing(
                    progress: sprint.completionPercentage / 100,
                    lineWidth: 6,
                    size: 50,
                    color: .blue
                )
            }

            // Sprint progress bar
            VStack(alignment: .leading, spacing: 4) {
                GeometryReader { geometry in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 4)
                            .fill(.secondary.opacity(0.2))

                        RoundedRectangle(cornerRadius: 4)
                            .fill(.blue)
                            .frame(width: geometry.size.width * sprint.progress)
                    }
                }
                .frame(height: 6)

                HStack {
                    Text("\(sprint.daysElapsed) days elapsed")
                        .font(.caption2)
                        .foregroundStyle(.secondary)

                    Spacer()

                    Text("\(sprint.daysRemaining) days remaining")
                        .font(.caption2)
                        .foregroundStyle(sprint.daysRemaining <= 2 ? .orange : .secondary)
                }
            }

            // Task stats
            HStack(spacing: 16) {
                Label("\(sprint.completedTasks)/\(sprint.totalTasks) tasks", systemImage: "checkmark.square")
                Label("\(sprint.completedStoryPoints)/\(sprint.totalStoryPoints) points", systemImage: "star")
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding()
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.05), radius: 5)
    }
}

// MARK: - Recent Task Row

struct RecentTaskRow: View {
    @ObservedObject var task: ProjectTask

    var body: some View {
        HStack(spacing: 12) {
            TaskTypeBadge(type: task.typeEnum, showText: false)

            VStack(alignment: .leading, spacing: 2) {
                Text(task.title ?? "Untitled")
                    .font(.subheadline)
                    .lineLimit(1)

                Text(task.project?.name ?? "")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            StatusBadge(status: task.statusEnum, showIcon: false, size: .small)

            if let assignee = task.assignee {
                AvatarView(user: assignee, size: 24)
            }
        }
        .padding(.vertical, 4)
    }
}

// MARK: - Quick Action Button

struct QuickActionButton: View {
    let title: String
    let icon: String
    let color: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.title2)
                    .foregroundStyle(color)

                Text(title)
                    .font(.caption)
                    .foregroundStyle(.primary)
            }
            .frame(maxWidth: .infinity)
            .padding()
            .background(.background)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .shadow(color: .black.opacity(0.05), radius: 5)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Preview

#Preview {
    DashboardView()
        .environment(\.managedObjectContext, PersistenceController.preview.container.viewContext)
        .environmentObject(AppState())
}
