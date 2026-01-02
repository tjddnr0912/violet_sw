//
//  BurndownChartView.swift
//  project
//
//  Sprint burndown chart showing ideal vs actual progress
//

import SwiftUI
import Charts

struct BurndownChartView: View {
    let sprint: Sprint

    private var burndownData: [BurndownDataPoint] {
        sprint.burndownData()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Header
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Burndown Chart")
                        .font(.headline)
                    Text(sprint.name ?? "Sprint")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 4) {
                    Text("\(sprint.remainingStoryPoints) points remaining")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                    Text("\(sprint.daysRemaining) days left")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            // Chart
            if burndownData.isEmpty {
                Text("No data available")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                Chart {
                    // Ideal burndown line (dashed)
                    ForEach(burndownData) { point in
                        LineMark(
                            x: .value("Date", point.date),
                            y: .value("Ideal", point.idealRemaining),
                            series: .value("Type", "Ideal")
                        )
                        .foregroundStyle(.gray.opacity(0.6))
                        .lineStyle(StrokeStyle(lineWidth: 2, dash: [5, 5]))
                    }

                    // Actual burndown line
                    ForEach(burndownData.filter { $0.date <= Date() }) { point in
                        LineMark(
                            x: .value("Date", point.date),
                            y: .value("Actual", point.actualRemaining),
                            series: .value("Type", "Actual")
                        )
                        .foregroundStyle(.blue)
                        .lineStyle(StrokeStyle(lineWidth: 3))
                    }

                    // Points on actual line
                    ForEach(burndownData.filter { $0.date <= Date() }) { point in
                        PointMark(
                            x: .value("Date", point.date),
                            y: .value("Actual", point.actualRemaining)
                        )
                        .foregroundStyle(.blue)
                        .symbolSize(40)
                    }

                    // Today line
                    RuleMark(x: .value("Today", Date()))
                        .foregroundStyle(.orange.opacity(0.5))
                        .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
                        .annotation(position: .top, alignment: .leading) {
                            Text("Today")
                                .font(.caption2)
                                .foregroundStyle(.orange)
                        }
                }
                .chartYAxis {
                    AxisMarks(position: .leading) { value in
                        AxisGridLine()
                        AxisValueLabel {
                            if let intValue = value.as(Double.self) {
                                Text("\(Int(intValue))")
                            }
                        }
                    }
                }
                .chartXAxis {
                    AxisMarks(values: .stride(by: .day, count: 2)) { value in
                        AxisGridLine()
                        AxisValueLabel(format: .dateTime.day().month(.abbreviated))
                    }
                }
                .chartLegend(position: .bottom) {
                    HStack(spacing: 20) {
                        LegendItem(color: .gray, label: "Ideal", isDashed: true)
                        LegendItem(color: .blue, label: "Actual", isDashed: false)
                    }
                }
            }
        }
        .padding()
    }
}

// MARK: - Legend Item

struct LegendItem: View {
    let color: Color
    let label: String
    var isDashed: Bool = false

    var body: some View {
        HStack(spacing: 6) {
            if isDashed {
                HStack(spacing: 2) {
                    ForEach(0..<3) { _ in
                        Rectangle()
                            .fill(color)
                            .frame(width: 6, height: 2)
                    }
                }
                .frame(width: 24)
            } else {
                Rectangle()
                    .fill(color)
                    .frame(width: 24, height: 3)
            }

            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }
}

// MARK: - Velocity Chart

struct VelocityChartView: View {
    let sprints: [Sprint]

    private var velocityData: [VelocityDataPoint] {
        sprints.prefix(6).enumerated().map { index, sprint in
            VelocityDataPoint(
                sprintName: sprint.name ?? "Sprint \(index + 1)",
                planned: Double(sprint.totalStoryPoints),
                completed: Double(sprint.completedStoryPoints)
            )
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Team Velocity")
                .font(.headline)

            if velocityData.isEmpty {
                Text("No sprint data available")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                Chart(velocityData) { data in
                    BarMark(
                        x: .value("Sprint", data.sprintName),
                        y: .value("Points", data.planned)
                    )
                    .foregroundStyle(.gray.opacity(0.3))
                    .position(by: .value("Type", "Planned"))

                    BarMark(
                        x: .value("Sprint", data.sprintName),
                        y: .value("Points", data.completed)
                    )
                    .foregroundStyle(.blue)
                    .position(by: .value("Type", "Completed"))
                }
                .chartYAxis {
                    AxisMarks(position: .leading)
                }
            }
        }
        .padding()
    }
}

struct VelocityDataPoint: Identifiable {
    let id = UUID()
    let sprintName: String
    let planned: Double
    let completed: Double
}

// MARK: - Preview

#Preview {
    VStack {
        Text("Preview requires Sprint data")
            .foregroundStyle(.secondary)
    }
    .frame(width: 600, height: 400)
    .padding()
}
