import SwiftUI

struct ContentView: View {
    @StateObject private var editorVM = EditorViewModel()
    @StateObject private var paletteVM = PaletteViewModel()
    @State private var showTemplates = false
    @State private var showLibrary = false
    @State private var showSettings = false
    @State private var showPreview = false
    @State private var showIconPicker = false
    @State private var showAlert = false
    @State private var alertTitle = ""
    @State private var alertMessage = ""
    @State private var exportedFileURL: URL?
    @State private var showShareSheet = false
    @State private var columnVisibility: NavigationSplitViewVisibility = .all

    var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            BlockPaletteView(viewModel: paletteVM) { definitionId in
                withAnimation(.spring(response: 0.3)) {
                    editorVM.addBlock(definitionId: definitionId)
                }
                HapticManager.shared.impact(.medium)
            }
            .navigationTitle("블록")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
        } content: {
            CanvasView(viewModel: editorVM)
                .navigationTitle(editorVM.document.name)
                #if os(iOS)
                .navigationBarTitleDisplayMode(.inline)
                #endif
                .toolbar {
                    toolbarContent
                }
        } detail: {
            if let block = editorVM.selectedBlock,
               let definition = editorVM.selectedBlockDefinition {
                BlockConfigView(
                    block: block,
                    definition: definition,
                    availableVariables: editorVM.availableVariables
                ) { key, value in
                    editorVM.updateParameter(blockId: block.id, key: key, value: value)
                }
            } else {
                VStack(spacing: 12) {
                    Image(systemName: "square.dashed")
                        .font(.system(size: 48))
                        .foregroundStyle(.tertiary)
                    Text("블록을 선택하세요")
                        .foregroundStyle(.secondary)
                    Text("블록의 매개변수를 편집할 수 있습니다")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
            }
        }
        .sheet(isPresented: $showTemplates) {
            TemplateGalleryView { document in
                editorVM.loadDocument(document)
                showTemplates = false
            }
        }
        .sheet(isPresented: $showLibrary) {
            LibraryView { document in
                editorVM.loadDocument(document)
                showLibrary = false
            }
        }
        .sheet(isPresented: $showSettings) {
            SettingsView()
        }
        .sheet(isPresented: $showPreview) {
            WorkflowPreviewView(
                document: editorVM.document,
                onExport: { performExport() },
                onDismiss: { showPreview = false }
            )
        }
        .sheet(isPresented: $showIconPicker) {
            IconPickerView(
                selectedIcon: Binding(
                    get: { editorVM.document.icon },
                    set: { editorVM.updateIcon($0) }
                ),
                selectedColor: Binding(
                    get: { editorVM.document.colorName },
                    set: { editorVM.updateColor($0) }
                )
            )
        }
        #if os(iOS)
        .sheet(isPresented: $showShareSheet) {
            if let url = exportedFileURL {
                ShareSheet(items: [url])
            }
        }
        #endif
        .alert(alertTitle, isPresented: $showAlert) {
            Button("확인") {}
            if exportedFileURL != nil {
                #if os(macOS)
                Button("Finder에서 보기") {
                    if let url = exportedFileURL {
                        NSWorkspace.shared.activateFileViewerSelecting([url])
                    }
                }
                #endif
            }
        } message: {
            Text(alertMessage)
        }
        .overlay { keyboardShortcutButtons }
    }

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItemGroup(placement: .primaryAction) {
            Button { showIconPicker = true } label: {
                Label("아이콘", systemImage: "paintpalette")
            }

            Button { showTemplates = true } label: {
                Label("템플릿", systemImage: "square.grid.2x2")
            }

            Button { showLibrary = true } label: {
                Label("라이브러리", systemImage: "folder")
            }

            Button { saveDocument() } label: {
                Label("저장", systemImage: "square.and.arrow.down")
            }

            Button { showPreview = true } label: {
                Label("내보내기", systemImage: "square.and.arrow.up")
            }
            .disabled(editorVM.document.blocks.isEmpty)

            Button { showSettings = true } label: {
                Label("설정", systemImage: "gearshape")
            }
        }

        ToolbarItemGroup(placement: .secondaryAction) {
            Button { editorVM.undo() } label: {
                Label("실행 취소", systemImage: "arrow.uturn.backward")
            }
            .disabled(!editorVM.canUndo)

            Button { editorVM.redo() } label: {
                Label("다시 실행", systemImage: "arrow.uturn.forward")
            }
            .disabled(!editorVM.canRedo)

            Divider()

            Button { editorVM.newDocument() } label: {
                Label("새 워크플로우", systemImage: "doc.badge.plus")
            }
        }
    }

    private func saveDocument() {
        DocumentManager.shared.save(editorVM.document)
        HapticManager.shared.notification(.success)
        alertTitle = "저장 완료"
        alertMessage = "'\(editorVM.document.name)' 워크플로우가 저장되었습니다"
        showAlert = true
    }

    private func deleteSelected() {
        guard let id = editorVM.selectedBlockId else { return }
        withAnimation(.spring(response: 0.3)) {
            editorVM.removeBlock(id: id)
        }
        HapticManager.shared.impact(.medium)
    }

    // MARK: - Keyboard Shortcuts

    @ViewBuilder
    private var keyboardShortcutButtons: some View {
        VStack {
            Button("") { saveDocument() }
                .keyboardShortcut("s", modifiers: .command)
            Button("") { editorVM.undo() }
                .keyboardShortcut("z", modifiers: .command)
            Button("") { editorVM.redo() }
                .keyboardShortcut("z", modifiers: [.command, .shift])
            Button("") { showPreview = true }
                .keyboardShortcut("e", modifiers: .command)
            Button("") { editorVM.newDocument() }
                .keyboardShortcut("n", modifiers: .command)
            Button("") { deleteSelected() }
                .keyboardShortcut(.delete, modifiers: .command)
        }
        .frame(width: 0, height: 0)
        .hidden()
    }

    private func performExport() {
        showPreview = false
        do {
            let exporter = WorkflowExporter()
            let result = try exporter.export(document: editorVM.document)
            exportedFileURL = result.fileURL

            HapticManager.shared.notification(.success)
            let signedText = result.isSigned ? "(서명됨)" : "(미서명)"
            alertTitle = "내보내기 완료"
            alertMessage = "\(result.blockCount)개 블록이 포함된 '\(editorVM.document.name).shortcut' 파일이 생성되었습니다 \(signedText)"

            #if os(iOS)
            showShareSheet = true
            #else
            showAlert = true
            #endif
        } catch {
            HapticManager.shared.notification(.error)
            alertTitle = "내보내기 실패"
            alertMessage = error.localizedDescription
            showAlert = true
        }
    }
}

// MARK: - iOS Share Sheet

#if os(iOS)
struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}
#endif

#Preview {
    ContentView()
}
