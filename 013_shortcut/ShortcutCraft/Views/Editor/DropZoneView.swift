import SwiftUI

struct DropZoneView: View {
    let index: Int
    @ObservedObject var viewModel: EditorViewModel
    @State private var isTargeted = false

    var body: some View {
        RoundedRectangle(cornerRadius: 8)
            .strokeBorder(
                isTargeted ? Color.accentColor : Color.clear,
                style: StrokeStyle(lineWidth: 2, dash: [6, 3])
            )
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(isTargeted ? Color.dropZoneHighlight : Color.clear)
            )
            .frame(height: isTargeted ? 44 : 8)
            .overlay {
                if isTargeted {
                    Text("여기에 놓기")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(.secondary)
                }
            }
            .animation(.spring(response: 0.25), value: isTargeted)
            .dropDestination(for: String.self) { items, _ in
                guard let item = items.first else { return false }

                // Check if it's a block UUID (reorder) or definition ID (new block)
                if let _ = UUID(uuidString: item) {
                    // Reorder existing block
                    withAnimation(.spring(response: 0.3)) {
                        viewModel.moveBlockByDrag(fromId: UUID(uuidString: item)!, toIndex: index)
                    }
                } else {
                    // Add new block from palette
                    withAnimation(.spring(response: 0.3)) {
                        viewModel.addBlock(definitionId: item, at: index)
                    }
                }
                return true
            } isTargeted: { targeted in
                isTargeted = targeted
            }
    }
}
