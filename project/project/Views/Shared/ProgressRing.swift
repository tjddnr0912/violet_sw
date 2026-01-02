//
//  ProgressRing.swift
//  project
//
//  Circular progress indicator
//

import SwiftUI

struct ProgressRing: View {
    let progress: Double // 0.0 to 1.0
    var lineWidth: CGFloat = 8
    var size: CGFloat = 60
    var color: Color = .blue
    var backgroundColor: Color = .secondary.opacity(0.2)
    var showPercentage: Bool = true

    var body: some View {
        ZStack {
            // Background circle
            Circle()
                .stroke(backgroundColor, lineWidth: lineWidth)

            // Progress arc
            Circle()
                .trim(from: 0, to: min(progress, 1.0))
                .stroke(
                    color,
                    style: StrokeStyle(lineWidth: lineWidth, lineCap: .round)
                )
                .rotationEffect(.degrees(-90))
                .animation(.easeOut(duration: 0.5), value: progress)

            // Percentage text
            if showPercentage {
                Text("\(Int(progress * 100))%")
                    .font(.system(size: size * 0.25, weight: .semibold))
                    .foregroundStyle(.primary)
            }
        }
        .frame(width: size, height: size)
    }
}

// MARK: - Gradient Progress Ring

struct GradientProgressRing: View {
    let progress: Double
    var lineWidth: CGFloat = 8
    var size: CGFloat = 60
    var showPercentage: Bool = true

    private var gradientColors: [Color] {
        switch progress {
        case 0..<0.25: return [.red, .orange]
        case 0.25..<0.5: return [.orange, .yellow]
        case 0.5..<0.75: return [.yellow, .green]
        default: return [.green, .mint]
        }
    }

    var body: some View {
        ZStack {
            Circle()
                .stroke(.secondary.opacity(0.2), lineWidth: lineWidth)

            Circle()
                .trim(from: 0, to: min(progress, 1.0))
                .stroke(
                    AngularGradient(
                        colors: gradientColors,
                        center: .center,
                        startAngle: .degrees(0),
                        endAngle: .degrees(360 * progress)
                    ),
                    style: StrokeStyle(lineWidth: lineWidth, lineCap: .round)
                )
                .rotationEffect(.degrees(-90))
                .animation(.easeOut(duration: 0.5), value: progress)

            if showPercentage {
                Text("\(Int(progress * 100))%")
                    .font(.system(size: size * 0.25, weight: .semibold))
                    .foregroundStyle(.primary)
            }
        }
        .frame(width: size, height: size)
    }
}

// MARK: - Preview

#Preview {
    HStack(spacing: 20) {
        ProgressRing(progress: 0.25, color: .red)
        ProgressRing(progress: 0.5, color: .orange)
        ProgressRing(progress: 0.75, color: .blue)
        ProgressRing(progress: 1.0, color: .green)
    }
    .padding()
}
