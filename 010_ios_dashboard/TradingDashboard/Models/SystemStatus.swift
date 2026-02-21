import Foundation
import SwiftUI

struct BotStatus: Codable {
    let running: Bool
    let lastUpdate: String?
    let ageMinutes: Double?
    let daemonRunning: Bool?
    let marketStatus: String?
    let marketStatusText: String?

    enum CodingKeys: String, CodingKey {
        case running
        case lastUpdate = "last_update"
        case ageMinutes = "age_minutes"
        case daemonRunning = "daemon_running"
        case marketStatus = "market_status"
        case marketStatusText = "market_status_text"
    }

    var statusText: String {
        // 주식 봇: 장 시간 인식 상태 텍스트
        if let ms = marketStatus {
            switch ms {
            case "trading":
                return running ? "장중 실행 중" : "장중 중지됨"
            case "pre_market":
                return daemonRunning == true ? "장 시작 대기" : "중지됨"
            case "after_hours":
                return daemonRunning == true ? "장 마감 대기" : "중지됨"
            case "weekend":
                return daemonRunning == true ? "주말 대기" : "중지됨"
            case "holiday":
                return daemonRunning == true ? "휴장일 대기" : "중지됨"
            default:
                break
            }
        }
        // 암호화폐 봇: 기존 로직
        guard running else { return "중지됨" }
        guard let age = ageMinutes else { return "실행 중" }
        if age < 1 { return "방금 업데이트" }
        if age < 60 { return "\(Int(age))분 전" }
        return "\(Int(age / 60))시간 전"
    }

    var indicatorColor: Color {
        // 주식 봇: 4색 인디케이터
        if let ms = marketStatus {
            switch ms {
            case "trading":
                return running ? .green : .red
            case "pre_market", "after_hours":
                return daemonRunning == true ? .yellow : .red
            case "weekend", "holiday":
                return daemonRunning == true ? .gray : .red
            default:
                break
            }
        }
        // 암호화폐 봇: 기존 2색
        return running ? .green : .red
    }
}
