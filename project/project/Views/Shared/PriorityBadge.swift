//
//  PriorityBadge.swift
//  project
//
//  Visual badge for task priority
//

import SwiftUI

struct PriorityBadge: View {
    let priority: TaskPriority
    var showText: Bool = true
    var size: BadgeSize = .medium

    var body: some View {
        HStack(spacing: size.spacing) {
            Image(systemName: priority.icon)
                .font(size.iconFont)

            if showText {
                Text(priority.displayName)
                    .font(size.textFont)
            }
        }
        .foregroundStyle(priority.color)
        .padding(.horizontal, size.horizontalPadding)
        .padding(.vertical, size.verticalPadding)
        .background(priority.backgroundColor)
        .clipShape(Capsule())
    }

    enum BadgeSize {
        case small, medium, large

        var iconFont: Font {
            switch self {
            case .small: return .caption2
            case .medium: return .caption
            case .large: return .subheadline
            }
        }

        var textFont: Font {
            switch self {
            case .small: return .caption2
            case .medium: return .caption
            case .large: return .subheadline
            }
        }

        var spacing: CGFloat {
            switch self {
            case .small: return 2
            case .medium: return 4
            case .large: return 6
            }
        }

        var horizontalPadding: CGFloat {
            switch self {
            case .small: return 4
            case .medium: return 8
            case .large: return 12
            }
        }

        var verticalPadding: CGFloat {
            switch self {
            case .small: return 2
            case .medium: return 4
            case .large: return 6
            }
        }
    }
}

// MARK: - Preview

#Preview {
    VStack(spacing: 16) {
        ForEach(TaskPriority.allCases) { priority in
            HStack {
                PriorityBadge(priority: priority, size: .small)
                PriorityBadge(priority: priority, size: .medium)
                PriorityBadge(priority: priority, size: .large)
            }
        }
    }
    .padding()
}
