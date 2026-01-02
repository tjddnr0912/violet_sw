//
//  DeadlineIndicator.swift
//  project
//
//  Visual indicator for task deadlines
//

import SwiftUI

struct DeadlineIndicator: View {
    let date: Date
    var showIcon: Bool = true

    private var daysRemaining: Int {
        Calendar.current.dateComponents([.day], from: Calendar.current.startOfDay(for: Date()), to: Calendar.current.startOfDay(for: date)).day ?? 0
    }

    private var indicatorColor: Color {
        switch daysRemaining {
        case ..<0: return .red // Overdue
        case 0: return .orange // Due today
        case 1: return .orange // Due tomorrow
        case 2...3: return .yellow // Due soon
        case 4...7: return .green // This week
        default: return .blue // Plenty of time
        }
    }

    private var statusText: String {
        switch daysRemaining {
        case ..<(-7): return "\(-daysRemaining)d overdue"
        case -7..<0: return "\(-daysRemaining)d overdue"
        case 0: return "Due today"
        case 1: return "Due tomorrow"
        case 2...7: return "\(daysRemaining)d left"
        default: return date.formatted(.dateTime.month(.abbreviated).day())
        }
    }

    private var icon: String {
        switch daysRemaining {
        case ..<0: return "exclamationmark.circle.fill"
        case 0...1: return "clock.badge.exclamationmark"
        default: return "calendar"
        }
    }

    var body: some View {
        HStack(spacing: 4) {
            if showIcon {
                Image(systemName: icon)
                    .font(.caption)
            }

            Text(statusText)
                .font(.caption)
        }
        .foregroundStyle(indicatorColor)
        .padding(.horizontal, 6)
        .padding(.vertical, 2)
        .background(indicatorColor.opacity(0.15))
        .clipShape(RoundedRectangle(cornerRadius: 4))
    }
}

// MARK: - Compact Version

struct CompactDeadlineIndicator: View {
    let date: Date

    private var daysRemaining: Int {
        Calendar.current.dateComponents([.day], from: Date(), to: date).day ?? 0
    }

    private var indicatorColor: Color {
        switch daysRemaining {
        case ..<0: return .red
        case 0...2: return .orange
        case 3...7: return .yellow
        default: return .green
        }
    }

    var body: some View {
        Circle()
            .fill(indicatorColor)
            .frame(width: 8, height: 8)
            .help(date.formatted(.dateTime.month().day().year()))
    }
}

// MARK: - Preview

#Preview {
    VStack(spacing: 16) {
        DeadlineIndicator(date: Calendar.current.date(byAdding: .day, value: -3, to: Date())!)
        DeadlineIndicator(date: Date())
        DeadlineIndicator(date: Calendar.current.date(byAdding: .day, value: 1, to: Date())!)
        DeadlineIndicator(date: Calendar.current.date(byAdding: .day, value: 5, to: Date())!)
        DeadlineIndicator(date: Calendar.current.date(byAdding: .day, value: 14, to: Date())!)
    }
    .padding()
}
