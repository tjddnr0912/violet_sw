//
//  TaskTypeBadge.swift
//  project
//
//  Visual badge for task type (task, bug, story, epic)
//

import SwiftUI

struct TaskTypeBadge: View {
    let type: TaskType
    var showText: Bool = false
    var size: CGFloat = 16

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: type.icon)
                .font(.system(size: size * 0.8))

            if showText {
                Text(type.displayName)
                    .font(.caption)
            }
        }
        .foregroundStyle(type.color)
        .padding(.horizontal, showText ? 8 : 4)
        .padding(.vertical, 4)
        .background(type.color.opacity(0.15))
        .clipShape(RoundedRectangle(cornerRadius: 4))
    }
}

// MARK: - Preview

#Preview {
    VStack(spacing: 16) {
        ForEach(TaskType.allCases) { type in
            HStack {
                TaskTypeBadge(type: type, showText: false)
                TaskTypeBadge(type: type, showText: true)
            }
        }
    }
    .padding()
}
