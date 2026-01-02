//
//  SprintListView.swift
//  project
//
//  Sprint list and management view
//

import SwiftUI
import CoreData

struct SprintListView: View {
    @Environment(\.managedObjectContext) private var viewContext
    @EnvironmentObject var appState: AppState

    @State private var selectedSprint: Sprint?
    @State private var isShowingNewSprintSheet = false

    var project: Project? {
        appState.selectedProject
    }

    private var sprints: [Sprint] {
        project?.sprintArray ?? []
    }

    var body: some View {
        VStack(spacing: 0) {
            // Toolbar
            HStack {
                Text("Sprints")
                    .font(.headline)

                Spacer()

                Button {
                    isShowingNewSprintSheet = true
                } label: {
                    Label("New Sprint", systemImage: "plus")
                }
            }
            .padding()

            Divider()

            // Sprint List
            if sprints.isEmpty {
                emptyState
            } else {
                List(selection: $selectedSprint) {
                    // Active Sprints
                    if !activeSprints.isEmpty {
                        Section("Active") {
                            ForEach(activeSprints) { sprint in
                                SprintRowView(sprint: sprint)
                                    .tag(sprint)
                            }
                        }
                    }

                    // Planning Sprints
                    if !planningSprints.isEmpty {
                        Section("Planning") {
                            ForEach(planningSprints) { sprint in
                                SprintRowView(sprint: sprint)
                                    .tag(sprint)
                            }
                        }
                    }

                    // Completed Sprints
                    if !completedSprints.isEmpty {
                        Section("Completed") {
                            ForEach(completedSprints) { sprint in
                                SprintRowView(sprint: sprint)
                                    .tag(sprint)
                            }
                        }
                    }
                }
                .listStyle(.inset)
            }
        }
        .sheet(isPresented: $isShowingNewSprintSheet) {
            CreateSprintSheet()
        }
    }

    private var activeSprints: [Sprint] {
        sprints.filter { $0.statusEnum == .active }
    }

    private var planningSprints: [Sprint] {
        sprints.filter { $0.statusEnum == .planning }
    }

    private var completedSprints: [Sprint] {
        sprints.filter { $0.statusEnum == .completed }
    }

    @ViewBuilder
    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "arrow.triangle.2.circlepath")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)

            Text("No Sprints Yet")
                .font(.headline)

            Text("Create your first sprint to start organizing your work")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Button {
                isShowingNewSprintSheet = true
            } label: {
                Label("Create Sprint", systemImage: "plus")
            }
            .buttonStyle(.borderedProminent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }
}

// MARK: - Sprint Row View

struct SprintRowView: View {
    @ObservedObject var sprint: Sprint
    @Environment(\.managedObjectContext) private var viewContext

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(sprint.name ?? "Untitled Sprint")
                            .font(.headline)

                        sprintStatusBadge
                    }

                    if let goal = sprint.goal, !goal.isEmpty {
                        Text(goal)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }

                Spacer()

                ProgressRing(
                    progress: sprint.completionPercentage / 100,
                    lineWidth: 4,
                    size: 40,
                    color: sprint.statusEnum == .completed ? .green : .blue
                )
            }

            // Date range
            HStack {
                Label(dateRangeText, systemImage: "calendar")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Spacer()

                if sprint.statusEnum == .active {
                    Text("\(sprint.daysRemaining) days remaining")
                        .font(.caption)
                        .foregroundStyle(sprint.daysRemaining <= 2 ? .orange : .secondary)
                }
            }

            // Stats
            HStack(spacing: 16) {
                Label("\(sprint.completedTasks)/\(sprint.totalTasks) tasks", systemImage: "checkmark.square")
                Label("\(sprint.completedStoryPoints)/\(sprint.totalStoryPoints) points", systemImage: "star")
            }
            .font(.caption)
            .foregroundStyle(.secondary)

            // Actions
            if sprint.statusEnum == .planning {
                Button("Start Sprint") {
                    startSprint()
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
            } else if sprint.statusEnum == .active {
                Button("Complete Sprint") {
                    completeSprint()
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
        }
        .padding(.vertical, 8)
        .contextMenu {
            if sprint.statusEnum == .planning {
                Button {
                    startSprint()
                } label: {
                    Label("Start Sprint", systemImage: "play")
                }
            }

            if sprint.statusEnum == .active {
                Button {
                    completeSprint()
                } label: {
                    Label("Complete Sprint", systemImage: "checkmark")
                }
            }

            Divider()

            Button(role: .destructive) {
                deleteSprint()
            } label: {
                Label("Delete Sprint", systemImage: "trash")
            }
        }
    }

    @ViewBuilder
    private var sprintStatusBadge: some View {
        Text(sprint.statusEnum.displayName)
            .font(.caption2)
            .fontWeight(.medium)
            .foregroundStyle(sprint.statusEnum.color)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(sprint.statusEnum.color.opacity(0.15))
            .clipShape(Capsule())
    }

    private var dateRangeText: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d"

        let start = sprint.startDate.map { formatter.string(from: $0) } ?? "TBD"
        let end = sprint.endDate.map { formatter.string(from: $0) } ?? "TBD"

        return "\(start) - \(end)"
    }

    private func startSprint() {
        withAnimation {
            sprint.start()
            viewContext.saveIfNeeded()
        }
    }

    private func completeSprint() {
        withAnimation {
            sprint.complete()
            viewContext.saveIfNeeded()
        }
    }

    private func deleteSprint() {
        withAnimation {
            viewContext.delete(sprint)
            viewContext.saveIfNeeded()
        }
    }
}

// MARK: - Create Sprint Sheet

struct CreateSprintSheet: View {
    @Environment(\.managedObjectContext) private var viewContext
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var appState: AppState

    @State private var name = ""
    @State private var goal = ""
    @State private var startDate = Date()
    @State private var endDate = Calendar.current.date(byAdding: .day, value: 14, to: Date())!

    var body: some View {
        NavigationStack {
            Form {
                Section("Sprint Details") {
                    TextField("Sprint Name", text: $name)
                    TextField("Goal (optional)", text: $goal, axis: .vertical)
                        .lineLimit(3)
                }

                Section("Duration") {
                    DatePicker("Start Date", selection: $startDate, displayedComponents: .date)
                    DatePicker("End Date", selection: $endDate, displayedComponents: .date)

                    HStack {
                        Text("Duration")
                        Spacer()
                        Text("\(sprintDuration) days")
                            .foregroundStyle(.secondary)
                    }
                }

                Section {
                    // Quick duration buttons
                    HStack {
                        ForEach([7, 14, 21], id: \.self) { days in
                            Button("\(days) days") {
                                endDate = Calendar.current.date(byAdding: .day, value: days, to: startDate)!
                            }
                            .buttonStyle(.bordered)
                        }
                    }
                }
            }
            .formStyle(.grouped)
            .frame(minWidth: 400, minHeight: 350)
            .navigationTitle("New Sprint")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        dismiss()
                    }
                }

                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") {
                        createSprint()
                    }
                    .disabled(name.isEmpty)
                }
            }
        }
    }

    private var sprintDuration: Int {
        Calendar.current.dateComponents([.day], from: startDate, to: endDate).day ?? 0
    }

    private func createSprint() {
        guard let project = appState.selectedProject else { return }

        let sprint = Sprint.create(
            in: viewContext,
            name: name,
            project: project,
            goal: goal.isEmpty ? nil : goal,
            startDate: startDate,
            endDate: endDate
        )

        viewContext.saveIfNeeded()
        dismiss()
    }
}

// MARK: - Preview

#Preview {
    SprintListView()
        .environment(\.managedObjectContext, PersistenceController.preview.container.viewContext)
        .environmentObject(AppState())
}
