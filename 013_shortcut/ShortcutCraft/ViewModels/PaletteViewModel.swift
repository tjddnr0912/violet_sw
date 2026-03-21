import SwiftUI

@MainActor
final class PaletteViewModel: ObservableObject {
    @Published var searchText: String = ""
    @Published var selectedCategory: BlockCategory?

    private let registry = BlockRegistry.shared

    var categories: [BlockCategory] {
        BlockCategory.allCases
    }

    var filteredBlocks: [BlockDefinition] {
        var results: [BlockDefinition]

        if let category = selectedCategory {
            results = registry.definitions(for: category)
        } else {
            results = registry.definitions
        }

        if !searchText.isEmpty {
            results = registry.search(query: searchText)
            if let category = selectedCategory {
                results = results.filter { $0.category == category }
            }
        }

        // Hide control flow marker blocks from palette
        results = results.filter { !$0.isControlFlowMarker }

        return results
    }

    func selectCategory(_ category: BlockCategory?) {
        if selectedCategory == category {
            selectedCategory = nil
        } else {
            selectedCategory = category
        }
    }

    func clearSearch() {
        searchText = ""
    }
}
