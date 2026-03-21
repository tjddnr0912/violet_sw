import SwiftUI

struct LibraryView: View {
    @StateObject private var viewModel = LibraryViewModel()
    @Environment(\.dismiss) private var dismiss
    let onSelect: (WorkflowDocument) -> Void

    var body: some View {
        NavigationStack {
            Group {
                if viewModel.documents.isEmpty {
                    VStack(spacing: 12) {
                        Image(systemName: "folder.badge.questionmark")
                            .font(.system(size: 48))
                            .foregroundStyle(.tertiary)
                        Text("저장된 워크플로우가 없습니다")
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    List {
                        ForEach(viewModel.documents) { doc in
                            Button {
                                onSelect(doc)
                            } label: {
                                HStack(spacing: 12) {
                                    Image(systemName: doc.icon)
                                        .font(.title3)
                                        .foregroundStyle(doc.color)
                                        .frame(width: 36, height: 36)
                                        .background(doc.color.opacity(0.15))
                                        .clipShape(RoundedRectangle(cornerRadius: 8))

                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(doc.name)
                                            .font(.headline)
                                        Text("\(doc.blocks.count)개 블록 \u{00B7} \(doc.updatedAt.formatted(.relative(presentation: .named)))")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }

                                    Spacer()
                                }
                            }
                            .buttonStyle(.plain)
                        }
                        .onDelete { indexSet in
                            for index in indexSet {
                                viewModel.delete(viewModel.documents[index])
                            }
                        }
                    }
                }
            }
            .navigationTitle("라이브러리")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("닫기") { dismiss() }
                }
            }
            .searchable(text: $viewModel.searchText, prompt: "워크플로우 검색")
        }
    }
}
