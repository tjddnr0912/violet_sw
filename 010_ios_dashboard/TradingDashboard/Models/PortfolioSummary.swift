import Foundation

struct PortfolioSummary: Codable {
    let stock: StockSummary
    let crypto: CryptoSummary
    let systemStatus: [String: BotStatus]
    let generatedAt: String

    enum CodingKeys: String, CodingKey {
        case stock, crypto
        case systemStatus = "system_status"
        case generatedAt = "generated_at"
    }
}

struct StockSummary: Codable {
    let positionCount: Int
    let totalValue: Double
    let totalProfit: Double
    let totalAssets: Double
    let dailyPnl: Double
    let dailyPnlPct: Double
    let totalPnlPct: Double
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case positionCount = "position_count"
        case totalValue = "total_value"
        case totalProfit = "total_profit"
        case totalAssets = "total_assets"
        case dailyPnl = "daily_pnl"
        case dailyPnlPct = "daily_pnl_pct"
        case totalPnlPct = "total_pnl_pct"
        case updatedAt = "updated_at"
    }
}

struct CryptoSummary: Codable {
    let marketRegime: String?
    let volatilityLevel: String?
    let totalTrades: Int?
    let winRate: Double?
    let totalProfitPct: Double?
    let avgProfitPct: Double?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case marketRegime = "market_regime"
        case volatilityLevel = "volatility_level"
        case totalTrades = "total_trades"
        case winRate = "win_rate"
        case totalProfitPct = "total_profit_pct"
        case avgProfitPct = "avg_profit_pct"
        case updatedAt = "updated_at"
    }
}
