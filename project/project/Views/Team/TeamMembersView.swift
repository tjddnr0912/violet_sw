//
//  TeamMembersView.swift
//  project
//
//  Team members management view
//

import SwiftUI
import CoreData

struct TeamMembersView: View {
    @Environment(\.managedObjectContext) private var viewContext

    @FetchRequest(
        sortDescriptors: [NSSortDescriptor(keyPath: \User.name, ascending: true)],
        animation: .default
    )
    private var users: FetchedResults<User>

    @State private var selectedUser: User?
    @State private var isShowingAddMember = false
    @State private var searchText = ""

    var body: some View {
        VStack(spacing: 0) {
            // Header
            teamHeader

            Divider()

            // Member Grid
            ScrollView {
                LazyVGrid(columns: [
                    GridItem(.adaptive(minimum: 280, maximum: 350), spacing: 16)
                ], spacing: 16) {
                    ForEach(filteredUsers) { user in
                        TeamMemberCardView(user: user)
                            .onTapGesture {
                                selectedUser = user
                            }
                    }
                }
                .padding()
            }
        }
        .searchable(text: $searchText, prompt: "Search members...")
        .sheet(item: $selectedUser) { user in
            MemberDetailSheet(user: user)
        }
        .sheet(isPresented: $isShowingAddMember) {
            AddMemberSheet()
        }
    }

    // MARK: - Header

    @ViewBuilder
    private var teamHeader: some View {
        HStack {
            Text("Team Members")
                .font(.headline)

            Text("\(users.count) members")
                .font(.caption)
                .foregroundStyle(.secondary)

            Spacer()

            Button {
                isShowingAddMember = true
            } label: {
                Label("Add Member", systemImage: "person.badge.plus")
            }
        }
        .padding()
    }

    private var filteredUsers: [User] {
        if searchText.isEmpty {
            return Array(users)
        }
        return users.filter {
            ($0.name ?? "").localizedCaseInsensitiveContains(searchText) ||
            ($0.email ?? "").localizedCaseInsensitiveContains(searchText)
        }
    }
}

// MARK: - Team Member Card

struct TeamMemberCardView: View {
    @ObservedObject var user: User

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Header
            HStack(spacing: 12) {
                AvatarView(user: user, size: 48)

                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(user.name ?? "Unknown")
                            .font(.headline)

                        if user.isCurrentUser {
                            Text("You")
                                .font(.caption2)
                                .foregroundStyle(.blue)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(.blue.opacity(0.15))
                                .clipShape(Capsule())
                        }
                    }

                    Text(user.email ?? "")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                // Role badge
                Text(user.roleEnum.displayName)
                    .font(.caption)
                    .fontWeight(.medium)
                    .foregroundStyle(user.roleEnum.color)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(user.roleEnum.color.opacity(0.15))
                    .clipShape(Capsule())
            }

            Divider()

            // Stats
            HStack(spacing: 24) {
                VStack(alignment: .center) {
                    Text("\(user.totalAssignedTasks)")
                        .font(.title2)
                        .fontWeight(.bold)
                    Text("Assigned")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                VStack(alignment: .center) {
                    Text("\(user.completedAssignedTasks)")
                        .font(.title2)
                        .fontWeight(.bold)
                        .foregroundStyle(.green)
                    Text("Completed")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                VStack(alignment: .center) {
                    Text("\(user.inProgressAssignedTasks)")
                        .font(.title2)
                        .fontWeight(.bold)
                        .foregroundStyle(.blue)
                    Text("In Progress")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                // Completion rate ring
                if user.totalAssignedTasks > 0 {
                    let rate = Double(user.completedAssignedTasks) / Double(user.totalAssignedTasks)
                    ProgressRing(
                        progress: rate,
                        lineWidth: 4,
                        size: 40,
                        color: .green
                    )
                }
            }
        }
        .padding()
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.05), radius: 5)
    }
}

// MARK: - Member Detail Sheet

struct MemberDetailSheet: View {
    @ObservedObject var user: User
    @Environment(\.dismiss) private var dismiss
    @Environment(\.managedObjectContext) private var viewContext

    @State private var editedName: String = ""
    @State private var editedEmail: String = ""
    @State private var editedRole: UserRole = .member
    @State private var selectedColor: String = "blue"

    private let colorOptions = ["blue", "red", "green", "orange", "purple", "pink", "cyan", "indigo"]

    var body: some View {
        NavigationStack {
            Form {
                // Avatar Section
                Section {
                    HStack {
                        Spacer()
                        VStack(spacing: 12) {
                            AvatarView(user: user, size: 80)

                            // Color picker
                            HStack(spacing: 8) {
                                ForEach(colorOptions, id: \.self) { color in
                                    Circle()
                                        .fill(Color(color))
                                        .frame(width: 24, height: 24)
                                        .overlay(
                                            Circle()
                                                .stroke(selectedColor == color ? Color.white : Color.clear, lineWidth: 2)
                                        )
                                        .shadow(color: selectedColor == color ? Color(color).opacity(0.5) : .clear, radius: 3)
                                        .onTapGesture {
                                            selectedColor = color
                                        }
                                }
                            }
                        }
                        Spacer()
                    }
                }

                // Details Section
                Section("Details") {
                    TextField("Name", text: $editedName)
                    TextField("Email", text: $editedEmail)
                        .textContentType(.emailAddress)

                    Picker("Role", selection: $editedRole) {
                        ForEach(UserRole.allCases) { role in
                            Label(role.displayName, systemImage: role.icon)
                                .tag(role)
                        }
                    }
                }

                // Statistics Section
                Section("Statistics") {
                    LabeledContent("Assigned Tasks", value: "\(user.totalAssignedTasks)")
                    LabeledContent("Completed Tasks", value: "\(user.completedAssignedTasks)")
                    LabeledContent("In Progress", value: "\(user.inProgressAssignedTasks)")
                    LabeledContent("Personal Todos", value: "\(user.todoArray.count)")
                }

                // Projects Section
                if !user.memberProjectArray.isEmpty {
                    Section("Projects") {
                        ForEach(user.memberProjectArray) { project in
                            HStack {
                                Circle()
                                    .fill(project.projectColor)
                                    .frame(width: 10, height: 10)
                                Text(project.name ?? "")
                            }
                        }
                    }
                }
            }
            .formStyle(.grouped)
            .frame(minWidth: 400, minHeight: 500)
            .navigationTitle("Member Details")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        dismiss()
                    }
                }

                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        saveChanges()
                        dismiss()
                    }
                }
            }
            .onAppear {
                loadUserData()
            }
        }
    }

    private func loadUserData() {
        editedName = user.name ?? ""
        editedEmail = user.email ?? ""
        editedRole = user.roleEnum
        selectedColor = user.avatarColor ?? "blue"
    }

    private func saveChanges() {
        user.name = editedName
        user.email = editedEmail
        user.role = editedRole.rawValue
        user.avatarColor = selectedColor
        viewContext.saveIfNeeded()
    }
}

// MARK: - Add Member Sheet

struct AddMemberSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.managedObjectContext) private var viewContext

    @State private var name = ""
    @State private var email = ""
    @State private var role: UserRole = .member
    @State private var avatarColor = "blue"

    private let colorOptions = ["blue", "red", "green", "orange", "purple", "pink", "cyan", "indigo"]

    var body: some View {
        NavigationStack {
            Form {
                Section("Member Info") {
                    TextField("Name", text: $name)
                    TextField("Email", text: $email)
                        .textContentType(.emailAddress)

                    Picker("Role", selection: $role) {
                        ForEach(UserRole.allCases) { role in
                            Text(role.displayName).tag(role)
                        }
                    }
                }

                Section("Avatar Color") {
                    HStack(spacing: 12) {
                        ForEach(colorOptions, id: \.self) { color in
                            Circle()
                                .fill(Color(color))
                                .frame(width: 32, height: 32)
                                .overlay(
                                    Circle()
                                        .stroke(avatarColor == color ? Color.white : Color.clear, lineWidth: 3)
                                )
                                .shadow(color: avatarColor == color ? Color(color).opacity(0.5) : .clear, radius: 4)
                                .onTapGesture {
                                    avatarColor = color
                                }
                        }
                    }
                }
            }
            .formStyle(.grouped)
            .frame(minWidth: 350, minHeight: 300)
            .navigationTitle("Add Member")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        dismiss()
                    }
                }

                ToolbarItem(placement: .confirmationAction) {
                    Button("Add") {
                        addMember()
                    }
                    .disabled(name.isEmpty || email.isEmpty)
                }
            }
        }
    }

    private func addMember() {
        let user = User.create(
            in: viewContext,
            name: name,
            email: email,
            role: role,
            avatarColor: avatarColor
        )

        viewContext.saveIfNeeded()
        dismiss()
    }
}

// MARK: - Preview

#Preview {
    TeamMembersView()
        .environment(\.managedObjectContext, PersistenceController.preview.container.viewContext)
}
