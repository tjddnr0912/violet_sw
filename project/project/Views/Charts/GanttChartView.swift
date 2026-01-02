//
//  GanttChartView.swift
//  project
//
//  Timeline/Gantt chart view for task scheduling
//

import SwiftUI
import CoreData

struct GanttChartView: View {
    @Environment(\.managedObjectContext) private var viewContext
    @EnvironmentObject var appState: AppState

    @State private var dateRange: ClosedRange<Date> = Date()...Date()
    @State private var selectedTask: ProjectTask?
    @State private var zoomLevel: Double = 1.0

    private let dayWidth: CGFloat = 40
    private let rowHeight: CGFloat = 36

    var project: Project? {
        appState.selectedProject
    }

    private var tasks: [ProjectTask] {
        guard let project = project else { return [] }
        return project.taskArray.filter { $0.parent == nil } // Only top-level tasks
            .sorted { ($0.dueDate ?? Date.distantFuture) < ($1.dueDate ?? Date.distantFuture) }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Toolbar
            ganttToolbar

            Divider()

            if tasks.isEmpty {
                emptyState
            } else {
                // Main content
                HSplitView {
                    // Task list (left panel)
                    taskListPanel
                        .frame(minWidth: 250, maxWidth: 350)

                    // Timeline (right panel)
                    timelinePanel
                }
            }
        }
        .onAppear {
            calculateDateRange()
        }
        .onChange(of: project) { _, _ in
            calculateDateRange()
        }
    }

    // MARK: - Toolbar

    @ViewBuilder
    private var ganttToolbar: some View {
        HStack {
            Text("Timeline")
                .font(.headline)

            Spacer()

            // Zoom controls
            HStack(spacing: 8) {
                Button {
                    zoomLevel = max(0.5, zoomLevel - 0.25)
                } label: {
                    Image(systemName: "minus.magnifyingglass")
                }

                Text("\(Int(zoomLevel * 100))%")
                    .font(.caption)
                    .frame(width: 40)

                Button {
                    zoomLevel = min(2.0, zoomLevel + 0.25)
                } label: {
                    Image(systemName: "plus.magnifyingglass")
                }
            }

            Divider()
                .frame(height: 20)

            Button {
                // Jump to today
            } label: {
                Label("Today", systemImage: "calendar")
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
    }

    // MARK: - Empty State

    @ViewBuilder
    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "calendar.day.timeline.left")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)

            Text("No Tasks with Dates")
                .font(.headline)

            Text("Add due dates to your tasks to see them on the timeline")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Task List Panel

    @ViewBuilder
    private var taskListPanel: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Task")
                    .font(.caption)
                    .fontWeight(.semibold)
                    .foregroundStyle(.secondary)
                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(.secondary.opacity(0.1))

            // Task rows
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(tasks) { task in
                        GanttTaskRowLabel(
                            task: task,
                            isSelected: selectedTask == task
                        )
                        .frame(height: rowHeight)
                        .onTapGesture {
                            selectedTask = task
                        }
                    }
                }
            }
        }
    }

    // MARK: - Timeline Panel

    @ViewBuilder
    private var timelinePanel: some View {
        GeometryReader { geometry in
            ScrollView([.horizontal, .vertical]) {
                VStack(spacing: 0) {
                    // Date header
                    dateHeader

                    // Task bars
                    ZStack(alignment: .topLeading) {
                        // Grid lines
                        gridLines

                        // Today marker
                        todayMarker

                        // Task bars
                        LazyVStack(spacing: 0) {
                            ForEach(Array(tasks.enumerated()), id: \.element.id) { index, task in
                                GanttTaskBar(
                                    task: task,
                                    dateRange: dateRange,
                                    dayWidth: dayWidth * zoomLevel,
                                    isSelected: selectedTask == task
                                )
                                .frame(height: rowHeight)
                            }
                        }
                    }
                }
                .frame(width: timelineWidth)
            }
        }
    }

    // MARK: - Date Header

    @ViewBuilder
    private var dateHeader: some View {
        HStack(spacing: 0) {
            ForEach(datesInRange, id: \.self) { date in
                VStack(spacing: 2) {
                    Text(date, format: .dateTime.weekday(.abbreviated))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(date, format: .dateTime.day())
                        .font(.caption)
                        .fontWeight(Calendar.current.isDateInToday(date) ? .bold : .regular)
                        .foregroundStyle(Calendar.current.isDateInToday(date) ? .blue : .primary)
                }
                .frame(width: dayWidth * zoomLevel)
                .padding(.vertical, 4)
                .background(Calendar.current.isDateInWeekend(date) ? Color.secondary.opacity(0.05) : Color.clear)
            }
        }
        .background(.secondary.opacity(0.1))
    }

    // MARK: - Grid Lines

    @ViewBuilder
    private var gridLines: some View {
        HStack(spacing: 0) {
            ForEach(datesInRange, id: \.self) { date in
                Rectangle()
                    .fill(Calendar.current.isDateInWeekend(date) ? Color.secondary.opacity(0.1) : Color.clear)
                    .frame(width: dayWidth * zoomLevel)
                    .overlay(alignment: .leading) {
                        Rectangle()
                            .fill(.secondary.opacity(0.2))
                            .frame(width: 1)
                    }
            }
        }
        .frame(height: CGFloat(tasks.count) * rowHeight)
    }

    // MARK: - Today Marker

    @ViewBuilder
    private var todayMarker: some View {
        if dateRange.contains(Date()) {
            let offset = daysFromStart(Date()) * dayWidth * zoomLevel
            Rectangle()
                .fill(.red.opacity(0.5))
                .frame(width: 2)
                .frame(height: CGFloat(tasks.count) * rowHeight)
                .offset(x: offset)
        }
    }

    // MARK: - Helpers

    private var timelineWidth: CGFloat {
        CGFloat(datesInRange.count) * dayWidth * zoomLevel
    }

    private var datesInRange: [Date] {
        var dates: [Date] = []
        var current = dateRange.lowerBound
        let calendar = Calendar.current

        while current <= dateRange.upperBound {
            dates.append(current)
            current = calendar.date(byAdding: .day, value: 1, to: current)!
        }

        return dates
    }

    private func daysFromStart(_ date: Date) -> CGFloat {
        let calendar = Calendar.current
        let days = calendar.dateComponents([.day], from: dateRange.lowerBound, to: date).day ?? 0
        return CGFloat(days)
    }

    private func calculateDateRange() {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: Date())

        // Start 7 days before today
        let start = calendar.date(byAdding: .day, value: -7, to: today)!

        // Find the latest due date among tasks, or 30 days from now
        let latestDueDate = tasks.compactMap { $0.dueDate }.max() ?? today
        let end = max(
            calendar.date(byAdding: .day, value: 30, to: today)!,
            calendar.date(byAdding: .day, value: 7, to: latestDueDate)!
        )

        dateRange = start...end
    }
}

// MARK: - Gantt Task Row Label

struct GanttTaskRowLabel: View {
    @ObservedObject var task: ProjectTask
    var isSelected: Bool

    var body: some View {
        HStack(spacing: 8) {
            TaskTypeBadge(type: task.typeEnum, showText: false, size: 12)

            Text(task.title ?? "Untitled")
                .font(.caption)
                .lineLimit(1)

            Spacer()

            if let assignee = task.assignee {
                AvatarView(user: assignee, size: 18)
            }
        }
        .padding(.horizontal, 12)
        .background(isSelected ? Color.accentColor.opacity(0.1) : Color.clear)
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(.secondary.opacity(0.1))
                .frame(height: 1)
        }
    }
}

// MARK: - Gantt Task Bar

struct GanttTaskBar: View {
    @ObservedObject var task: ProjectTask
    let dateRange: ClosedRange<Date>
    let dayWidth: CGFloat
    var isSelected: Bool

    private var barOffset: CGFloat {
        guard let startDate = task.createdAt else { return 0 }
        let calendar = Calendar.current
        let days = calendar.dateComponents([.day], from: dateRange.lowerBound, to: startDate).day ?? 0
        return CGFloat(max(0, days)) * dayWidth
    }

    private var barWidth: CGFloat {
        let startDate = task.createdAt ?? Date()
        let endDate = task.dueDate ?? Calendar.current.date(byAdding: .day, value: 3, to: startDate)!
        let calendar = Calendar.current
        let days = calendar.dateComponents([.day], from: startDate, to: endDate).day ?? 1
        return CGFloat(max(1, days)) * dayWidth
    }

    var body: some View {
        GeometryReader { geometry in
            HStack(spacing: 0) {
                RoundedRectangle(cornerRadius: 4)
                    .fill(barColor)
                    .frame(width: max(dayWidth, barWidth), height: 20)
                    .overlay(alignment: .leading) {
                        Text(task.title ?? "")
                            .font(.caption2)
                            .foregroundStyle(.white)
                            .lineLimit(1)
                            .padding(.horizontal, 6)
                    }
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(isSelected ? Color.white : Color.clear, lineWidth: 2)
                    )
                    .shadow(color: barColor.opacity(0.3), radius: 2, y: 1)

                Spacer(minLength: 0)
            }
            .offset(x: barOffset)
        }
    }

    private var barColor: Color {
        switch task.statusEnum {
        case .done: return .green
        case .inProgress: return .blue
        case .inReview: return .purple
        case .todo: return .gray
        }
    }
}

// MARK: - Preview

#Preview {
    GanttChartView()
        .environment(\.managedObjectContext, PersistenceController.preview.container.viewContext)
        .environmentObject(AppState())
        .frame(width: 1000, height: 600)
}
