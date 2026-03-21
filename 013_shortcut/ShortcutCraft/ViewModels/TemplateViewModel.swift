import SwiftUI

@MainActor
final class TemplateViewModel: ObservableObject {
    @Published var searchText: String = ""

    private let store = TemplateStore.shared

    var templates: [Template] {
        if searchText.isEmpty {
            return store.templates
        }
        let lower = searchText.lowercased()
        return store.templates.filter {
            $0.name.lowercased().contains(lower) ||
            $0.summary.lowercased().contains(lower)
        }
    }

    var categories: [String] {
        Array(Set(store.templates.map { $0.category })).sorted()
    }

    func templates(for category: String) -> [Template] {
        templates.filter { $0.category == category }
    }
}
