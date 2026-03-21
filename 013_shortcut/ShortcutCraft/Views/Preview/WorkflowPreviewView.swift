import SwiftUI

struct WorkflowPreviewView: View {
    let document: WorkflowDocument
    let onExport: () -> Void
    let onDismiss: () -> Void

    @State private var isExporting = false
    @State private var exportResult: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    // Workflow info
                    VStack(spacing: 12) {
                        Image(systemName: document.icon)
                            .font(.system(size: 40))
                            .foregroundStyle(.white)
                            .frame(width: 72, height: 72)
                            .background(document.color)
                            .clipShape(RoundedRectangle(cornerRadius: 18))

                        Text(document.name)
                            .font(.title2.bold())

                        Text("\(document.blocks.count)개 블록")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 20)

                    Divider()

                    // Block summary
                    VStack(alignment: .leading, spacing: 8) {
                        Text("워크플로우 흐름")
                            .font(.headline)

                        ForEach(Array(document.blocks.enumerated()), id: \.element.id) { index, block in
                            HStack(spacing: 10) {
                                Text("\(index + 1)")
                                    .font(.system(size: 12, weight: .bold, design: .rounded))
                                    .foregroundStyle(.white)
                                    .frame(width: 24, height: 24)
                                    .background(blockColor(for: block))
                                    .clipShape(Circle())

                                VStack(alignment: .leading, spacing: 1) {
                                    Text(blockName(for: block))
                                        .font(.system(size: 14, weight: .medium))
                                    Text(blockSummary(for: block))
                                        .font(.system(size: 12))
                                        .foregroundStyle(.secondary)
                                        .lineLimit(1)
                                }

                                Spacer()
                            }
                            .padding(.vertical, 4)
                        }
                    }

                    if let result = exportResult {
                        Text(result)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .padding()
                            .background(.regularMaterial)
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                    }
                }
                .padding()
            }
            .navigationTitle("미리보기")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("닫기") { onDismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button {
                        onExport()
                    } label: {
                        Label("내보내기", systemImage: "square.and.arrow.up")
                    }
                    .disabled(document.blocks.isEmpty)
                }
            }
        }
    }

    @MainActor
    private func blockName(for block: BlockInstance) -> String {
        BlockRegistry.shared.definition(for: block.definitionId)?.name ?? "알 수 없는 블록"
    }

    @MainActor
    private func blockSummary(for block: BlockInstance) -> String {
        let params = block.parameterValues.values.map { $0.displayText }.filter { !$0.isEmpty }
        if params.isEmpty {
            return BlockRegistry.shared.definition(for: block.definitionId)?.summary ?? ""
        }
        return params.joined(separator: ", ")
    }

    @MainActor
    private func blockColor(for block: BlockInstance) -> Color {
        BlockRegistry.shared.definition(for: block.definitionId)?.categoryColor ?? .gray
    }
}
