//
//  StatusBadge.swift
//  project
//
//  Visual badge for task status
//

import SwiftUI

struct StatusBadge: View {
    let status: TaskStatus
    var showIcon: Bool = true
    var size: BadgeSize = .medium

    var body: some View {
        HStack(spacing: size.spacing) {
            if showIcon {
                Image(systemName: status.icon)
                    .font(size.iconFont)
            }

            Text(status.displayName)
                .font(size.textFont)
        }
        .foregroundStyle(status.color)
        .padding(.horizontal, size.horizontalPadding)
        .padding(.vertical, size.verticalPadding)
        .background(status.color.opacity(0.15))
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
        ForEach(TaskStatus.allCases) { status in
            HStack {
                StatusBadge(status: status, size: .small)
                StatusBadge(status: status, size: .medium)
                StatusBadge(status: status, size: .large)
            }
        }
    }
    .padding()
}
