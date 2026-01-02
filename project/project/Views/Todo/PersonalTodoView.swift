//
//  PersonalTodoView.swift
//  project
//
//  Personal todo list (separate from project tasks)
//

import SwiftUI
import CoreData

struct PersonalTodoView: View {
    @Environment(\.managedObjectContext) private var viewContext

    @FetchRequest(
        sortDescriptors: [
            NSSortDescriptor(keyPath: \PersonalTodo.isCompleted, ascending: true),
            NSSortDescriptor(keyPath: \PersonalTodo.priority, ascending: false),
            NSSortDescriptor(keyPath: \PersonalTodo.createdAt, ascending: false)
        ],
        animation: .default
    )
    private var todos: FetchedResults<PersonalTodo>

    @State private var newTodoTitle = ""
    @State private var showCompleted = true

    var body: some View {
        VStack(spacing: 0) {
            // Header
            todoHeader

            Divider()

            // Quick Add
            quickAddSection

            Divider()

            // Todo List
            if filteredTodos.isEmpty {
                emptyState
            } else {
                List {
                    // Pending Todos
                    if !pendingTodos.isEmpty {
                        Section("To Do") {
                            ForEach(pendingTodos) { todo in
                                TodoRowView(todo: todo)
                            }
                            .onDelete { offsets in
                                deleteTodos(from: pendingTodos, at: offsets)
                            }
                        }
                    }

                    // Completed Todos
                    if showCompleted && !completedTodos.isEmpty {
                        Section("Completed") {
                            ForEach(completedTodos) { todo in
                                TodoRowView(todo: todo)
                            }
                            .onDelete { offsets in
                                deleteTodos(from: completedTodos, at: offsets)
                            }
                        }
                    }
                }
                .listStyle(.inset)
            }
        }
    }

    // MARK: - Header

    @ViewBuilder
    private var todoHeader: some View {
        HStack {
            Text("My Todo")
                .font(.headline)

            Text("\(pendingTodos.count) pending")
                .font(.caption)
                .foregroundStyle(.secondary)

            Spacer()

            Toggle("Show Completed", isOn: $showCompleted)
                .toggleStyle(.switch)
                .controlSize(.small)

            Button {
                clearCompleted()
            } label: {
                Label("Clear Completed", systemImage: "trash")
            }
            .disabled(completedTodos.isEmpty)
        }
        .padding()
    }

    // MARK: - Quick Add Section

    @ViewBuilder
    private var quickAddSection: some View {
        HStack(spacing: 12) {
            Image(systemName: "plus.circle.fill")
                .foregroundStyle(.blue)
                .font(.title2)

            TextField("Add a new todo...", text: $newTodoTitle)
                .textFieldStyle(.plain)
                .onSubmit {
                    addTodo()
                }

            if !newTodoTitle.isEmpty {
                Button("Add") {
                    addTodo()
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
            }
        }
        .padding()
        .background(.secondary.opacity(0.05))
    }

    // MARK: - Empty State

    @ViewBuilder
    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "checklist")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)

            Text("All Done!")
                .font(.headline)

            Text("You have no pending todos")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Computed Properties

    private var filteredTodos: [PersonalTodo] {
        showCompleted ? Array(todos) : pendingTodos
    }

    private var pendingTodos: [PersonalTodo] {
        todos.filter { !$0.isCompleted }
    }

    private var completedTodos: [PersonalTodo] {
        todos.filter { $0.isCompleted }
    }

    // MARK: - Actions

    private func addTodo() {
        guard !newTodoTitle.isEmpty else { return }

        withAnimation {
            let todo = PersonalTodo(context: viewContext)
            todo.id = UUID()
            todo.title = newTodoTitle
            todo.isCompleted = false
            todo.priority = TaskPriority.medium.rawValue
            todo.createdAt = Date()
            todo.user = User.currentUser(in: viewContext)

            newTodoTitle = ""
            viewContext.saveIfNeeded()
        }
    }

    private func deleteTodos(from source: [PersonalTodo], at offsets: IndexSet) {
        withAnimation {
            for index in offsets {
                viewContext.delete(source[index])
            }
            viewContext.saveIfNeeded()
        }
    }

    private func clearCompleted() {
        withAnimation {
            for todo in completedTodos {
                viewContext.delete(todo)
            }
            viewContext.saveIfNeeded()
        }
    }
}

// MARK: - Todo Row View

struct TodoRowView: View {
    @ObservedObject var todo: PersonalTodo
    @Environment(\.managedObjectContext) private var viewContext

    @State private var isEditing = false
    @State private var editedTitle = ""

    var body: some View {
        HStack(spacing: 12) {
            // Checkbox
            Button {
                toggleComplete()
            } label: {
                Image(systemName: todo.isCompleted ? "checkmark.circle.fill" : "circle")
                    .font(.title2)
                    .foregroundStyle(todo.isCompleted ? .green : .secondary)
            }
            .buttonStyle(.plain)

            // Title
            if isEditing {
                TextField("Todo", text: $editedTitle)
                    .textFieldStyle(.plain)
                    .onSubmit {
                        saveEdit()
                    }
            } else {
                Text(todo.title ?? "Untitled")
                    .strikethrough(todo.isCompleted)
                    .foregroundStyle(todo.isCompleted ? .secondary : .primary)
                    .onTapGesture(count: 2) {
                        startEditing()
                    }
            }

            Spacer()

            // Priority
            Menu {
                ForEach(TaskPriority.allCases) { priority in
                    Button {
                        todo.priority = priority.rawValue
                        viewContext.saveIfNeeded()
                    } label: {
                        Label(priority.displayName, systemImage: priority.icon)
                    }
                }
            } label: {
                Image(systemName: TodoPriority(rawValue: todo.priority)?.icon ?? "minus")
                    .foregroundStyle(TodoPriority(rawValue: todo.priority)?.color ?? .gray)
            }
            .menuStyle(.borderlessButton)

            // Due Date
            if let dueDate = todo.dueDate {
                DeadlineIndicator(date: dueDate, showIcon: false)
            }
        }
        .padding(.vertical, 4)
        .contextMenu {
            // Priority
            Menu("Set Priority") {
                ForEach(TaskPriority.allCases) { priority in
                    Button {
                        todo.priority = priority.rawValue
                        viewContext.saveIfNeeded()
                    } label: {
                        Label(priority.displayName, systemImage: priority.icon)
                    }
                }
            }

            // Due Date
            Button {
                todo.dueDate = Calendar.current.date(byAdding: .day, value: 1, to: Date())
                viewContext.saveIfNeeded()
            } label: {
                Label("Due Tomorrow", systemImage: "calendar")
            }

            Divider()

            Button(role: .destructive) {
                viewContext.delete(todo)
                viewContext.saveIfNeeded()
            } label: {
                Label("Delete", systemImage: "trash")
            }
        }
    }

    private func toggleComplete() {
        withAnimation(.spring(response: 0.3)) {
            todo.isCompleted.toggle()
            todo.completedAt = todo.isCompleted ? Date() : nil
            viewContext.saveIfNeeded()
        }
    }

    private func startEditing() {
        editedTitle = todo.title ?? ""
        isEditing = true
    }

    private func saveEdit() {
        todo.title = editedTitle
        isEditing = false
        viewContext.saveIfNeeded()
    }
}

// MARK: - Todo Priority (wrapper for TaskPriority)

typealias TodoPriority = TaskPriority

// MARK: - Preview

#Preview {
    PersonalTodoView()
        .environment(\.managedObjectContext, PersistenceController.preview.container.viewContext)
}
