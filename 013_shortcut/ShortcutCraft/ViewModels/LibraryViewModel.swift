import SwiftUI

@MainActor
final class LibraryViewModel: ObservableObject {
    @Published var searchText: String = ""

    private let documentManager = DocumentManager.shared

    var documents: [WorkflowDocument] {
        if searchText.isEmpty {
            return documentManager.savedDocuments
        }
        let lower = searchText.lowercased()
        return documentManager.savedDocuments.filter {
            $0.name.lowercased().contains(lower)
        }
    }

    func delete(_ document: WorkflowDocument) {
        documentManager.delete(document)
    }

    func refresh() {
        documentManager.loadAll()
    }
}
