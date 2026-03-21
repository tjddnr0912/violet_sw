import SwiftUI

struct BlockView: View {
    let block: BlockInstance
    let definition: BlockDefinition?
    let isSelected: Bool
    let validationError: String?
    let compact: Bool
    let showLabel: Bool
    let onTap: () -> Void
    let onDelete: () -> Void
    let onDuplicate: () -> Void
    let onToggleCollapse: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            HStack(spacing: 10) {
                Image(systemName: definition?.iconName ?? "questionmark.square")
                    .font(.system(size: compact ? 14 : 16, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(width: compact ? 28 : 32, height: compact ? 28 : 32)
                    .background(definition?.categoryColor ?? .gray)
                    .clipShape(RoundedRectangle(cornerRadius: compact ? 6 : 8))

                VStack(alignment: .leading, spacing: 1) {
                    Text(definition?.name ?? "알 수 없는 블록")
                        .font(.system(size: compact ? 13 : 14, weight: .semibold))
                    if showLabel && !block.isCollapsed {
                        Text(definition?.summary ?? "")
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }

                Spacer()

                Text("#\(block.position + 1)")
                    .font(.system(size: 10, weight: .medium, design: .rounded))
                    .foregroundStyle(.tertiary)

                Button(action: onToggleCollapse) {
                    Image(systemName: block.isCollapsed ? "chevron.right" : "chevron.down")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, compact ? 10 : 14)
            .padding(.vertical, compact ? 7 : 10)

            // Parameters preview
            if !block.isCollapsed && !compact, let definition = definition, !definition.parameters.isEmpty {
                Divider()
                    .padding(.horizontal, 14)

                VStack(alignment: .leading, spacing: 6) {
                    ForEach(definition.parameters) { param in
                        HStack(spacing: 8) {
                            Text(param.label)
                                .font(.system(size: 12))
                                .foregroundStyle(.secondary)
                                .frame(width: 80, alignment: .trailing)

                            if let value = block.parameterValues[param.id] {
                                parameterPill(value: value)
                            } else if let defaultValue = param.defaultValue {
                                parameterPill(value: defaultValue)
                                    .opacity(0.5)
                            } else {
                                Text(param.placeholder ?? "미설정")
                                    .font(.system(size: 12))
                                    .foregroundStyle(.tertiary)
                                    .italic()
                            }

                            Spacer()
                        }
                    }
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
            }

            // Validation error
            if let error = validationError {
                Divider()
                    .padding(.horizontal, 14)
                HStack(spacing: 4) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 10))
                    Text(error)
                        .font(.system(size: 11))
                        .lineLimit(2)
                }
                .foregroundStyle(.orange)
                .padding(.horizontal, 14)
                .padding(.vertical, 6)
            }
        }
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(
                    validationError != nil ? Color.orange :
                    (isSelected ? (definition?.categoryColor ?? .blue) : .clear),
                    lineWidth: 2
                )
        )
        .shadow(color: .blockShadow, radius: isSelected ? 6 : 2, y: isSelected ? 3 : 1)
        .onTapGesture(perform: onTap)
        .contextMenu {
            Button(action: onDuplicate) {
                Label("복제", systemImage: "doc.on.doc")
            }
            Button(action: onToggleCollapse) {
                Label(block.isCollapsed ? "펼치기" : "접기", systemImage: block.isCollapsed ? "chevron.down" : "chevron.up")
            }
            Divider()
            Button(role: .destructive, action: onDelete) {
                Label("삭제", systemImage: "trash")
            }
        }
        .padding(.horizontal, 4)
    }

    private func parameterPill(value: ParameterValue) -> some View {
        Group {
            if case .variable(let ref) = value {
                HStack(spacing: 4) {
                    Circle()
                        .fill(ref.color)
                        .frame(width: 8, height: 8)
                    Text(ref.displayName)
                        .font(.system(size: 12, weight: .medium))
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(
                    RoundedRectangle(cornerRadius: 6)
                        .fill(ref.color.opacity(0.15))
                )
            } else {
                Text(value.displayText.isEmpty ? "빈 값" : value.displayText)
                    .font(.system(size: 12, weight: .medium))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(
                        RoundedRectangle(cornerRadius: 6)
                            .fill((definition?.categoryColor ?? .blue).opacity(0.12))
                    )
                    .lineLimit(1)
            }
        }
    }
}
