//
//  AvatarView.swift
//  project
//
//  User avatar view with initials
//

import SwiftUI

struct AvatarView: View {
    let user: User?
    var size: CGFloat = 32

    private var initials: String {
        user?.initials ?? "?"
    }

    private var color: Color {
        user?.userColor ?? .gray
    }

    var body: some View {
        ZStack {
            Circle()
                .fill(color.gradient)

            Text(initials)
                .font(.system(size: size * 0.4, weight: .semibold))
                .foregroundStyle(.white)
        }
        .frame(width: size, height: size)
    }
}

// MARK: - Avatar Stack (for multiple assignees)

struct AvatarStackView: View {
    let users: [User]
    var maxDisplay: Int = 3
    var size: CGFloat = 24

    var body: some View {
        HStack(spacing: -size * 0.3) {
            ForEach(users.prefix(maxDisplay), id: \.self) { user in
                AvatarView(user: user, size: size)
                    .overlay(
                        Circle()
                            .stroke(.background, lineWidth: 2)
                    )
            }

            if users.count > maxDisplay {
                ZStack {
                    Circle()
                        .fill(.secondary)

                    Text("+\(users.count - maxDisplay)")
                        .font(.system(size: size * 0.35, weight: .semibold))
                        .foregroundStyle(.white)
                }
                .frame(width: size, height: size)
                .overlay(
                    Circle()
                        .stroke(.background, lineWidth: 2)
                )
            }
        }
    }
}

// MARK: - Preview

#Preview {
    VStack(spacing: 20) {
        HStack(spacing: 20) {
            AvatarView(user: nil, size: 24)
            AvatarView(user: nil, size: 32)
            AvatarView(user: nil, size: 48)
        }

        Text("Avatar Stack")
        // Preview would need sample users
    }
    .padding()
}
