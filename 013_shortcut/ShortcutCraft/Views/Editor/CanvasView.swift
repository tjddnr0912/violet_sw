import SwiftUI

struct CanvasView: View {
    @ObservedObject var viewModel: EditorViewModel
    @ObservedObject private var settings = SettingsManager.shared

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                workflowHeader

                if viewModel.document.blocks.isEmpty {
                    emptyState
                } else {
                    let levels = viewModel.nestingLevels

                    ForEach(Array(viewModel.document.blocks.enumerated()), id: \.element.id) { index, block in
                        let nestingLevel = levels[block.id] ?? 0

                        VStack(spacing: 0) {
                            if index > 0 {
                                ConnectionLineView(
                                    hasError: viewModel.validationErrors[block.id] != nil
                                )
                                .padding(.leading, CGFloat(nestingLevel) * 24)
                            }

                            DropZoneView(index: index, viewModel: viewModel)
                                .padding(.leading, CGFloat(nestingLevel) * 24)

                            BlockView(
                                block: block,
                                definition: BlockRegistry.shared.definition(for: block.definitionId),
                                isSelected: viewModel.selectedBlockId == block.id,
                                validationError: viewModel.validationErrors[block.id],
                                compact: settings.compactMode,
                                showLabel: settings.showBlockLabels,
                                onTap: {
                                    viewModel.selectBlock(block.id)
                                    HapticManager.shared.selection()
                                },
                                onDelete: {
                                    withAnimation(.spring(response: 0.3)) {
                                        viewModel.removeBlock(id: block.id)
                                    }
                                    HapticManager.shared.impact(.medium)
                                },
                                onDuplicate: {
                                    withAnimation(.spring(response: 0.3)) {
                                        viewModel.duplicateBlock(id: block.id)
                                    }
                                    HapticManager.shared.impact(.light)
                                },
                                onToggleCollapse: {
                                    withAnimation(.spring(response: 0.3)) {
                                        viewModel.toggleCollapse(id: block.id)
                                    }
                                    HapticManager.shared.selection()
                                }
                            )
                            .padding(.leading, CGFloat(nestingLevel) * 24)
                            .draggable(block.id.uuidString) {
                                BlockDragPreview(
                                    name: BlockRegistry.shared.definition(for: block.definitionId)?.name ?? "블록",
                                    color: BlockRegistry.shared.definition(for: block.definitionId)?.categoryColor ?? .gray
                                )
                            }
                        }
                        .transition(.asymmetric(
                            insertion: .scale(scale: 0.8).combined(with: .opacity),
                            removal: .scale(scale: 0.8).combined(with: .opacity)
                        ))
                    }

                    DropZoneView(index: viewModel.document.blocks.count, viewModel: viewModel)
                }

                if !viewModel.availableVariables.isEmpty {
                    variableBar
                }
            }
            .padding()
            .animation(.spring(response: 0.35), value: viewModel.document.blocks.count)
        }
        .background(Color.canvasBackground)
        .onTapGesture {
            viewModel.selectBlock(nil)
        }
    }

    private var workflowHeader: some View {
        HStack(spacing: 12) {
            Image(systemName: viewModel.document.icon)
                .font(.title2)
                .foregroundStyle(viewModel.document.color)
                .frame(width: 40, height: 40)
                .background(viewModel.document.color.opacity(0.15))
                .clipShape(RoundedRectangle(cornerRadius: 10))

            VStack(alignment: .leading, spacing: 2) {
                TextField("워크플로우 이름", text: Binding(
                    get: { viewModel.document.name },
                    set: { viewModel.updateName($0) }
                ))
                .font(.headline)

                Text("\(viewModel.document.blocks.count)개 블록")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Menu {
                Button { viewModel.collapseAll() } label: { Label("모두 접기", systemImage: "chevron.up.2") }
                Button { viewModel.expandAll() } label: { Label("모두 펼치기", systemImage: "chevron.down.2") }
            } label: {
                Image(systemName: "ellipsis.circle")
                    .font(.title3)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .padding(.bottom, 8)
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "plus.square.dashed")
                .font(.system(size: 56))
                .foregroundStyle(.tertiary)

            Text("블록을 추가하여 워크플로우를 만드세요")
                .font(.headline)
                .foregroundStyle(.secondary)

            Text("왼쪽 팔레트에서 블록을 선택하거나\n템플릿으로 시작하세요")
                .font(.subheadline)
                .foregroundStyle(.tertiary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 80)
    }

    private var variableBar: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("사용 가능한 변수")
                .font(.caption)
                .foregroundStyle(.secondary)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(viewModel.availableVariables) { variable in
                        HStack(spacing: 4) {
                            Circle()
                                .fill(variable.color)
                                .frame(width: 8, height: 8)
                            Text(variable.displayName)
                                .font(.system(size: 11, weight: .medium))
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(variable.color.opacity(0.12))
                        .clipShape(Capsule())
                    }
                }
            }
        }
        .padding()
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .padding(.top, 12)
    }
}

// MARK: - Drag Preview

struct BlockDragPreview: View {
    let name: String
    let color: Color

    var body: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(color)
                .frame(width: 12, height: 12)
            Text(name)
                .font(.system(size: 13, weight: .medium))
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}
