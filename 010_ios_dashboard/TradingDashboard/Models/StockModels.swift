import Foundation

struct StockPosition: Codable, Identifiable {
    var id: String { code }
    let code: String
    let name: String
    let quantity: Int
    let entryPrice: Double
    let currentPrice: Double
    let profitPct: Double?
    let profitKrw: Double?
    let stopLoss: Double?
    let takeProfit1: Double?
    let stopLossPct: Double?
    let takeProfit1Pct: Double?
    let entryDate: String?

    enum CodingKeys: String, CodingKey {
        case code, name, quantity
        case entryPrice = "entry_price"
        case currentPrice = "current_price"
        case profitPct = "profit_pct"
        case profitKrw = "profit_krw"
        case stopLoss = "stop_loss"
        case takeProfit1 = "take_profit_1"
        case stopLossPct = "stop_loss_pct"
        case takeProfit1Pct = "take_profit_1_pct"
        case entryDate = "entry_date"
    }
}

struct StockDailyData: Codable {
    let initialCapital: Int
    let snapshots: [DailySnapshot]

    enum CodingKeys: String, CodingKey {
        case initialCapital = "initial_capital"
        case snapshots
    }
}

struct DailySnapshot: Codable, Identifiable {
    var id: String { date }
    let date: String
    let totalAssets: Int
    let cash: Int
    let invested: Int
    let totalPnl: Int
    let totalPnlPct: Double
    let dailyPnl: Int
    let dailyPnlPct: Double
    let tradesToday: Int
    let positionCount: Int

    enum CodingKeys: String, CodingKey {
        case date
        case totalAssets = "total_assets"
        case cash, invested
        case totalPnl = "total_pnl"
        case totalPnlPct = "total_pnl_pct"
        case dailyPnl = "daily_pnl"
        case dailyPnlPct = "daily_pnl_pct"
        case tradesToday = "trades_today"
        case positionCount = "position_count"
    }
}

struct StockTransaction: Codable, Identifiable {
    var id: String { "\(timestamp)_\(code)" }
    let timestamp: String
    let date: String
    let type: String
    let code: String
    let name: String
    let quantity: Int
    let price: Double
    let amount: Double
    let orderNo: String?
    let reason: String?
    let pnl: Double?
    let pnlPct: Double?

    enum CodingKeys: String, CodingKey {
        case timestamp, date, type, code, name, quantity, price, amount
        case orderNo = "order_no"
        case reason, pnl
        case pnlPct = "pnl_pct"
    }
}
