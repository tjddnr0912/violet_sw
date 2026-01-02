//
//  ReportsView.swift
//  project
//
//  Reports and analytics hub
//

import SwiftUI
import CoreData
import Charts

struct ReportsView: View {
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
        animation: .default
    )
    private var sprints: FetchedResults<Sprint>

    @State private var selectedReportType: ReportType = .overview

    var body: some View {
        HSplitView {
            // Report Type Selection
            reportTypeList
                .frame(minWidth: 200, maxWidth: 250)

            // Report Content
            reportContent
        }
    }

    // MARK: - Report Type List

    @ViewBuilder
    private var reportTypeList: some View {
        List(selection: $selectedReportType) {
            Section("Reports") {
                ForEach(ReportType.allCases) { type in
                    Label(type.displayName, systemImage: type.icon)
                        .tag(type)
                }
            }
        }
        .listStyle(.sidebar)
    }

    // MARK: - Report Content

    @ViewBuilder
    private var reportContent: some View {
        ScrollView {
            VStack(spacing: 24) {
                switch selectedReportType {
                case .overview:
                    OverviewReport(projects: Array(projects), tasks: Array(allTasks))
                case .taskAnalysis:
                    TaskAnalysisReport(tasks: Array(allTasks))
                case .sprintReport:
                    SprintAnalysisReport(sprints: Array(sprints))
                case .teamPerformance:
                    TeamPerformanceReport()
                case .burndown:
                    BurndownReport(sprints: Array(sprints.filter { $0.statusEnum == .active }))
                }
            }
            .padding()
        }
    }
}

// MARK: - Report Type Enum

enum ReportType: String, CaseIterable, Identifiable {
    case overview = "Overview"
    case taskAnalysis = "Task Analysis"
    case sprintReport = "Sprint Report"
    case teamPerformance = "Team Performance"
    case burndown = "Burndown Charts"

    var id: String { rawValue }

    var displayName: String { rawValue }

    var icon: String {
        switch self {
        case .overview: return "chart.pie"
        case .taskAnalysis: return "checklist"
        case .sprintReport: return "arrow.triangle.2.circlepath"
        case .teamPerformance: return "person.3"
        case .burndown: return "chart.line.downtrend.xyaxis"
        }
    }
}

// MARK: - Overview Report

struct OverviewReport: View {
    let projects: [Project]
    let tasks: [ProjectTask]

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            Text("Overview Report")
                .font(.title)
                .fontWeight(.bold)

            // Summary Stats
            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 16) {
                StatCard(title: "Total Projects", value: "\(projects.count)", icon: "folder.fill", color: .blue)
                StatCard(title: "Total Tasks", value: "\(tasks.count)", icon: "checkmark.square.fill", color: .green)
                StatCard(title: "Completed", value: "\(completedTasks)", icon: "checkmark.circle.fill", color: .purple)
                StatCard(title: "Completion Rate", value: "\(completionRate)%", icon: "percent", color: .orange)
            }

            // Charts
            HStack(spacing: 16) {
                ReportCard(title: "Task Distribution by Status") {
                    TaskStatusPieChart(tasks: tasks)
                }

                ReportCard(title: "Tasks by Priority") {
                    PriorityBarChart(tasks: tasks)
                }
            }
            .frame(height: 250)

            // Task Type Distribution
            ReportCard(title: "Task Types") {
                TaskTypeChart(tasks: tasks)
            }
            .frame(height: 200)
        }
    }

    private var completedTasks: Int {
        tasks.filter { $0.statusEnum == .done }.count
    }

    private var completionRate: Int {
        guard !tasks.isEmpty else { return 0 }
        return Int(Double(completedTasks) / Double(tasks.count) * 100)
    }
}

// MARK: - Task Analysis Report

struct TaskAnalysisReport: View {
    let tasks: [ProjectTask]

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            Text("Task Analysis")
                .font(.title)
                .fontWeight(.bold)

            // Overdue tasks
            overdueTasks

            // Task age distribution
            ReportCard(title: "Task Age Distribution") {
                TaskAgeChart(tasks: tasks)
            }
            .frame(height: 200)

            // Story points summary
            storyPointsSummary
        }
    }

    @ViewBuilder
    private var overdueTasks: some View {
        let overdueList = tasks.filter { $0.isOverdue }

        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Overdue Tasks")
                    .font(.headline)

                Spacer()

                Text("\(overdueList.count) tasks")
                    .foregroundStyle(overdueList.isEmpty ? .green : .red)
            }

            if overdueList.isEmpty {
                Text("No overdue tasks")
                    .foregroundStyle(.secondary)
                    .padding()
            } else {
                ForEach(overdueList.prefix(5)) { task in
                    HStack {
                        TaskTypeBadge(type: task.typeEnum, showText: false)
                        Text(task.title ?? "Untitled")
                            .lineLimit(1)
                        Spacer()
                        if let dueDate = task.dueDate {
                            DeadlineIndicator(date: dueDate)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .padding()
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.05), radius: 5)
    }

    @ViewBuilder
    private var storyPointsSummary: some View {
        let totalPoints = tasks.reduce(0) { $0 + Int($1.storyPoints) }
        let completedPoints = tasks.filter { $0.isCompleted }.reduce(0) { $0 + Int($1.storyPoints) }

        VStack(alignment: .leading, spacing: 12) {
            Text("Story Points")
                .font(.headline)

            HStack(spacing: 24) {
                VStack {
                    Text("\(totalPoints)")
                        .font(.system(size: 32, weight: .bold))
                    Text("Total")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                VStack {
                    Text("\(completedPoints)")
                        .font(.system(size: 32, weight: .bold))
                        .foregroundStyle(.green)
                    Text("Completed")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                VStack {
                    Text("\(totalPoints - completedPoints)")
                        .font(.system(size: 32, weight: .bold))
                        .foregroundStyle(.orange)
                    Text("Remaining")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                GradientProgressRing(
                    progress: totalPoints > 0 ? Double(completedPoints) / Double(totalPoints) : 0,
                    lineWidth: 10,
                    size: 80
                )
            }
        }
        .padding()
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.05), radius: 5)
    }
}

// MARK: - Sprint Analysis Report

struct SprintAnalysisReport: View {
    let sprints: [Sprint]

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            Text("Sprint Analysis")
                .font(.title)
                .fontWeight(.bold)

            if sprints.isEmpty {
                Text("No sprints available")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding()
            } else {
                // Velocity chart
                ReportCard(title: "Team Velocity") {
                    VelocityChartView(sprints: sprints)
                }
                .frame(height: 250)

                // Sprint list
                VStack(alignment: .leading, spacing: 12) {
                    Text("Sprint Summary")
                        .font(.headline)

                    ForEach(sprints.prefix(5)) { sprint in
                        SprintSummaryRow(sprint: sprint)
                    }
                }
            }
        }
    }
}

struct SprintSummaryRow: View {
    @ObservedObject var sprint: Sprint

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(sprint.name ?? "Untitled")
                        .fontWeight(.semibold)

                    SprintStatusBadge(status: sprint.statusEnum)
                }

                Text(sprint.project?.name ?? "")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 4) {
                Text("\(sprint.completedTasks)/\(sprint.totalTasks) tasks")
                    .font(.subheadline)

                Text("\(sprint.completedStoryPoints)/\(sprint.totalStoryPoints) points")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            ProgressRing(
                progress: sprint.completionPercentage / 100,
                lineWidth: 4,
                size: 40,
                showPercentage: false
            )
        }
        .padding()
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

// MARK: - Team Performance Report

struct TeamPerformanceReport: View {
    @Environment(\.managedObjectContext) private var viewContext

    @FetchRequest(
        sortDescriptors: [NSSortDescriptor(keyPath: \User.name, ascending: true)],
        animation: .default
    )
    private var users: FetchedResults<User>

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            Text("Team Performance")
                .font(.title)
                .fontWeight(.bold)

            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 16) {
                ForEach(users) { user in
                    TeamMemberCard(user: user)
                }
            }
        }
    }
}

struct TeamMemberCard: View {
    @ObservedObject var user: User

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                AvatarView(user: user, size: 40)

                VStack(alignment: .leading) {
                    Text(user.name ?? "Unknown")
                        .fontWeight(.semibold)
                    Text(user.roleEnum.displayName)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()
            }

            Divider()

            HStack {
                VStack {
                    Text("\(user.totalAssignedTasks)")
                        .font(.title3)
                        .fontWeight(.bold)
                    Text("Assigned")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                VStack {
                    Text("\(user.completedAssignedTasks)")
                        .font(.title3)
                        .fontWeight(.bold)
                        .foregroundStyle(.green)
                    Text("Completed")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                VStack {
                    Text("\(user.inProgressAssignedTasks)")
                        .font(.title3)
                        .fontWeight(.bold)
                        .foregroundStyle(.blue)
                    Text("In Progress")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding()
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.05), radius: 5)
    }
}

// MARK: - Burndown Report

struct BurndownReport: View {
    let sprints: [Sprint]

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            Text("Burndown Charts")
                .font(.title)
                .fontWeight(.bold)

            if sprints.isEmpty {
                Text("No active sprints")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding()
            } else {
                ForEach(sprints) { sprint in
                    ReportCard(title: sprint.name ?? "Sprint") {
                        BurndownChartView(sprint: sprint)
                    }
                    .frame(height: 300)
                }
            }
        }
    }
}

// MARK: - Supporting Views

struct StatCard: View {
    let title: String
    let value: String
    let icon: String
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: icon)
                    .foregroundStyle(color)
                Spacer()
            }

            Text(value)
                .font(.title)
                .fontWeight(.bold)

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

struct ReportCard<Content: View>: View {
    let title: String
    @ViewBuilder let content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if !title.isEmpty {
                Text(title)
                    .font(.headline)
            }

            content()
        }
        .padding()
        .frame(maxWidth: .infinity)
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.05), radius: 5)
    }
}

struct TaskTypeChart: View {
    let tasks: [ProjectTask]

    private var typeData: [TypeChartData] {
        TaskType.allCases.map { type in
            TypeChartData(type: type, count: tasks.filter { $0.typeEnum == type }.count)
        }.filter { $0.count > 0 }
    }

    var body: some View {
        Chart(typeData) { data in
            BarMark(
                x: .value("Count", data.count),
                y: .value("Type", data.type.displayName)
            )
            .foregroundStyle(data.type.color)
        }
    }
}

struct TypeChartData: Identifiable {
    let id = UUID()
    let type: TaskType
    let count: Int
}

struct TaskAgeChart: View {
    let tasks: [ProjectTask]

    var body: some View {
        Text("Task age distribution chart")
            .foregroundStyle(.secondary)
    }
}

// MARK: - Sprint Status Badge

struct SprintStatusBadge: View {
    let status: SprintStatus

    var body: some View {
        Text(status.displayName)
            .font(.caption2)
            .fontWeight(.medium)
            .foregroundStyle(status.color)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(status.color.opacity(0.15))
            .clipShape(Capsule())
    }
}

// MARK: - Preview

#Preview {
    ReportsView()
        .environment(\.managedObjectContext, PersistenceController.preview.container.viewContext)
        .environmentObject(AppState())
}
