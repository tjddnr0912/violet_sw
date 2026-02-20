import Foundation

enum APIError: Error, LocalizedError {
    case notConfigured
    case invalidURL
    case unauthorized
    case networkError(Error)
    case decodingError(Error)
    case serverError(Int, String?)

    var errorDescription: String? {
        switch self {
        case .notConfigured: return "서버가 설정되지 않았습니다. 설정에서 서버 URL을 입력하세요."
        case .invalidURL: return "잘못된 서버 URL입니다."
        case .unauthorized: return "API Key가 올바르지 않습니다."
        case .networkError(let e): return "네트워크 오류: \(e.localizedDescription)"
        case .decodingError: return "데이터 파싱 오류"
        case .serverError(let code, _): return "서버 오류 (\(code))"
        }
    }
}

class APIClient {
    private let settings: SettingsManager
    private let session: URLSession
    private let decoder: JSONDecoder

    init(settings: SettingsManager = .shared) {
        self.settings = settings

        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        self.session = URLSession(configuration: config)

        self.decoder = JSONDecoder()
    }

    func fetch<T: Codable>(_ endpoint: String) async throws -> T {
        guard settings.isConfigured else {
            throw APIError.notConfigured
        }

        let baseURL = settings.serverURL.hasSuffix("/")
            ? String(settings.serverURL.dropLast())
            : settings.serverURL

        guard let url = URL(string: "\(baseURL)\(endpoint)") else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        if !settings.apiKey.isEmpty {
            request.setValue(settings.apiKey, forHTTPHeaderField: "X-API-Key")
        }

        let data: Data
        let response: URLResponse

        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.networkError(error)
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(URLError(.badServerResponse))
        }

        switch httpResponse.statusCode {
        case 200...299:
            do {
                let apiResponse = try decoder.decode(APIResponse<T>.self, from: data)
                return apiResponse.data
            } catch {
                throw APIError.decodingError(error)
            }
        case 401:
            throw APIError.unauthorized
        default:
            let body = String(data: data, encoding: .utf8)
            throw APIError.serverError(httpResponse.statusCode, body)
        }
    }

    func testConnection() async -> Bool {
        guard settings.isConfigured else { return false }

        let baseURL = settings.serverURL.hasSuffix("/")
            ? String(settings.serverURL.dropLast())
            : settings.serverURL

        guard let url = URL(string: "\(baseURL)/health") else { return false }

        do {
            let (_, response) = try await session.data(from: url)
            return (response as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }
}
