import Foundation

@MainActor
final class DocumentManager: ObservableObject {
    static let shared = DocumentManager()

    @Published var savedDocuments: [WorkflowDocument] = []

    private let fileManager = FileManager.default
    private var documentsDirectory: URL {
        fileManager.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("ShortcutCraft", isDirectory: true)
    }

    private init() {
        ensureDirectory()
        loadAll()
    }

    private func ensureDirectory() {
        try? fileManager.createDirectory(at: documentsDirectory, withIntermediateDirectories: true)
    }

    func save(_ document: WorkflowDocument) {
        var doc = document
        doc.updatedAt = Date()

        let fileURL = documentsDirectory.appendingPathComponent("\(doc.id.uuidString).json")
        do {
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .iso8601
            encoder.outputFormatting = .prettyPrinted
            let data = try encoder.encode(doc)
            try data.write(to: fileURL)

            if let index = savedDocuments.firstIndex(where: { $0.id == doc.id }) {
                savedDocuments[index] = doc
            } else {
                savedDocuments.append(doc)
            }
        } catch {
            print("Save error: \(error)")
        }
    }

    func delete(_ document: WorkflowDocument) {
        let fileURL = documentsDirectory.appendingPathComponent("\(document.id.uuidString).json")
        try? fileManager.removeItem(at: fileURL)
        savedDocuments.removeAll { $0.id == document.id }
    }

    func loadAll() {
        guard let files = try? fileManager.contentsOfDirectory(at: documentsDirectory, includingPropertiesForKeys: nil) else {
            return
        }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601

        savedDocuments = files
            .filter { $0.pathExtension == "json" }
            .compactMap { url in
                guard let data = try? Data(contentsOf: url),
                      let doc = try? decoder.decode(WorkflowDocument.self, from: data) else {
                    return nil
                }
                return doc
            }
            .sorted { $0.updatedAt > $1.updatedAt }
    }
}
