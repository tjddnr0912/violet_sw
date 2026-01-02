//
//  CreateProjectSheet.swift
//  project
//
//  Sheet for creating new projects
//

import SwiftUI
import CoreData

struct CreateProjectSheet: View {
    @Environment(\.managedObjectContext) private var viewContext
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var appState: AppState

    @State private var name = ""
    @State private var description = ""
    @State private var selectedColor = "blue"

    private let colorOptions = [
        ("blue", Color.blue),
        ("red", Color.red),
        ("green", Color.green),
        ("orange", Color.orange),
        ("purple", Color.purple),
        ("pink", Color.pink),
        ("cyan", Color.cyan),
        ("indigo", Color.indigo),
        ("mint", Color.mint),
        ("teal", Color.teal)
    ]

    var body: some View {
        NavigationStack {
            Form {
                // Project Name
                Section("Project Name") {
                    TextField("Enter project name", text: $name)
                        .textFieldStyle(.plain)
                        .font(.title3)
                }

                // Description
                Section("Description") {
                    TextEditor(text: $description)
                        .frame(minHeight: 80)
                }

                // Color Selection
                Section("Project Color") {
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 5), spacing: 12) {
                        ForEach(colorOptions, id: \.0) { colorName, color in
                            Circle()
                                .fill(color.gradient)
                                .frame(width: 40, height: 40)
                                .overlay(
                                    Circle()
                                        .stroke(selectedColor == colorName ? Color.white : Color.clear, lineWidth: 3)
                                )
                                .shadow(color: selectedColor == colorName ? color.opacity(0.5) : .clear, radius: 4)
                                .onTapGesture {
                                    withAnimation(.spring(response: 0.3)) {
                                        selectedColor = colorName
                                    }
                                }
                        }
                    }
                    .padding(.vertical, 8)
                }

                // Preview
                Section("Preview") {
                    HStack(spacing: 12) {
                        RoundedRectangle(cornerRadius: 8)
                            .fill(Color(selectedColor).gradient)
                            .frame(width: 50, height: 50)

                        VStack(alignment: .leading, spacing: 4) {
                            Text(name.isEmpty ? "Project Name" : name)
                                .font(.headline)
                                .foregroundStyle(name.isEmpty ? .secondary : .primary)

                            Text(description.isEmpty ? "Project description" : description)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(2)
                        }

                        Spacer()
                    }
                    .padding(.vertical, 4)
                }
            }
            .formStyle(.grouped)
            .frame(minWidth: 450, minHeight: 400)
            .navigationTitle("New Project")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        dismiss()
                    }
                }

                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") {
                        createProject()
                    }
                    .disabled(name.isEmpty)
                    .buttonStyle(.borderedProminent)
                }
            }
        }
    }

    private func createProject() {
        let currentUser = User.getOrCreateCurrentUser(in: viewContext)

        let project = Project.create(
            in: viewContext,
            name: name,
            description: description.isEmpty ? nil : description,
            color: selectedColor,
            owner: currentUser
        )

        viewContext.saveIfNeeded()

        // Select the new project
        appState.selectedProject = project
        appState.selectedSection = .kanban

        dismiss()
    }
}

// MARK: - Preview

#Preview {
    CreateProjectSheet()
        .environment(\.managedObjectContext, PersistenceController.preview.container.viewContext)
        .environmentObject(AppState())
}
