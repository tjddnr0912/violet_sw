import SwiftUI

@MainActor
struct WorkflowExporter {
    let registry = BlockRegistry.shared

    enum ExportError: Error, LocalizedError {
        case emptyWorkflow
        case conversionFailed
        case plistGenerationFailed
        case signingFailed(String)

        var errorDescription: String? {
            switch self {
            case .emptyWorkflow: return "워크플로우에 블록이 없습니다"
            case .conversionFailed: return "블록 변환에 실패했습니다"
            case .plistGenerationFailed: return "plist 생성에 실패했습니다"
            case .signingFailed(let msg): return "서명 실패: \(msg)"
            }
        }
    }

    struct ExportResult {
        let fileURL: URL
        let isSigned: Bool
        let blockCount: Int
    }

    func export(document: WorkflowDocument) throws -> ExportResult {
        guard !document.blocks.isEmpty else {
            throw ExportError.emptyWorkflow
        }

        let converter = BlockToWFConverter(registry: registry)
        let actions = converter.convert(blocks: document.blocks)

        let plist = WFWorkflowPlist(
            workflowIcon: WFWorkflowPlist.WFWorkflowIcon(
                startColor: colorToInt(document.colorName),
                glyphNumber: iconToGlyph(document.icon)
            ),
            workflowActions: actions,
            workflowInputContentItemClasses: [
                "WFAppStoreAppContentItem",
                "WFArticleContentItem",
                "WFContactContentItem",
                "WFDateContentItem",
                "WFEmailAddressContentItem",
                "WFGenericFileContentItem",
                "WFImageContentItem",
                "WFiTunesProductContentItem",
                "WFLocationContentItem",
                "WFDCMapsLinkContentItem",
                "WFAVAssetContentItem",
                "WFPDFContentItem",
                "WFPhoneNumberContentItem",
                "WFRichTextContentItem",
                "WFSafariWebPageContentItem",
                "WFStringContentItem",
                "WFURLContentItem"
            ],
            workflowTypes: ["NCWidget", "WatchKit"]
        )

        let generator = PlistGenerator()
        let data = try generator.generate(from: plist)

        let tempDir = FileManager.default.temporaryDirectory
        let safeName = document.name.replacingOccurrences(of: "/", with: "_")
        let unsignedURL = tempDir.appendingPathComponent("\(safeName)_unsigned.shortcut")
        try data.write(to: unsignedURL)

        #if os(macOS)
        let signedURL = tempDir.appendingPathComponent("\(safeName).shortcut")
        let signer = ShortcutSigner()
        do {
            try signer.signSync(inputURL: unsignedURL, outputURL: signedURL)
            try? FileManager.default.removeItem(at: unsignedURL)
            return ExportResult(fileURL: signedURL, isSigned: true, blockCount: actions.count)
        } catch {
            // Signing failed, fall back to unsigned
            let fallbackURL = tempDir.appendingPathComponent("\(safeName).shortcut")
            try? FileManager.default.moveItem(at: unsignedURL, to: fallbackURL)
            return ExportResult(fileURL: fallbackURL, isSigned: false, blockCount: actions.count)
        }
        #else
        let finalURL = tempDir.appendingPathComponent("\(safeName).shortcut")
        if FileManager.default.fileExists(atPath: finalURL.path) {
            try? FileManager.default.removeItem(at: finalURL)
        }
        try FileManager.default.moveItem(at: unsignedURL, to: finalURL)
        return ExportResult(fileURL: finalURL, isSigned: false, blockCount: actions.count)
        #endif
    }

    private func colorToInt(_ colorName: String) -> Int {
        // ARGB color values used by Apple Shortcuts
        switch colorName {
        case "red":    return 4_282_601_983  // FF4C3E3F
        case "orange": return 4_294_218_495  // FFED8B1F
        case "green":  return 4_292_093_695  // FFD1E95F
        case "blue":   return 463_140_863    // 1B9AF0FF
        case "purple": return 4_251_333_119  // FD6EC4FF
        case "pink":   return 4_290_774_271  // FFB04EDF
        case "teal":   return 431_817_727    // 19B8EDFF
        default:       return 431_817_727
        }
    }

    private func iconToGlyph(_ iconName: String) -> Int {
        // Map SF Symbol names to Shortcuts glyph numbers
        switch iconName {
        case "star":                    return 0xE032
        case "sun.max":                 return 0xE034
        case "moon.fill":              return 0xE036
        case "safari":                  return 0xE044
        case "doc.on.clipboard":       return 0xE050
        case "bell":                    return 0xE054
        case "camera.viewfinder":      return 0xE056
        case "message":                return 0xE058
        case "calendar.badge.plus":    return 0xE05A
        case "keyboard":               return 0xE05C
        case "battery.75percent":      return 0xE062
        case "arrow.down.doc":         return 0xE064
        case "link":                    return 0xE066
        default:                        return 0xE032
        }
    }
}
