import Foundation

struct ShortcutSigner {
    enum SigningError: Error, LocalizedError {
        case notMacOS
        case signingFailed(String)
        case fileNotFound
        case commandNotFound

        var errorDescription: String? {
            switch self {
            case .notMacOS: return "서명은 macOS에서만 가능합니다"
            case .signingFailed(let msg): return "서명 실패: \(msg)"
            case .fileNotFound: return "파일을 찾을 수 없습니다"
            case .commandNotFound: return "shortcuts 명령을 찾을 수 없습니다"
            }
        }
    }

    #if os(macOS)
    func signSync(inputURL: URL, outputURL: URL) throws {
        guard FileManager.default.fileExists(atPath: inputURL.path) else {
            throw SigningError.fileNotFound
        }

        let shortcutsPath = "/usr/bin/shortcuts"
        guard FileManager.default.fileExists(atPath: shortcutsPath) else {
            throw SigningError.commandNotFound
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: shortcutsPath)
        process.arguments = ["sign", "-i", inputURL.path, "-o", outputURL.path]

        let pipe = Pipe()
        process.standardError = pipe

        try process.run()
        process.waitUntilExit()

        if process.terminationStatus != 0 {
            let errorData = pipe.fileHandleForReading.readDataToEndOfFile()
            let errorMsg = String(data: errorData, encoding: .utf8) ?? "알 수 없는 오류"
            throw SigningError.signingFailed(errorMsg)
        }
    }
    #endif
}
