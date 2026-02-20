import Foundation

struct APIResponse<T: Codable>: Codable {
    let status: String
    let data: T
    let timestamp: String
}
