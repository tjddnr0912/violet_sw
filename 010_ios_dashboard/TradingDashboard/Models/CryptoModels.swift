import Foundation

struct CryptoRegime: Codable {
    let marketRegime: String
    let volatilityLevel: String
    let entryMode: String
    let entryThresholdModifier: Double
    let stopLossModifier: Double
    let currentAtrPct: Double?
    let takeProfitTarget: String?
    let lastUpdate: String?

    enum CodingKeys: String, CodingKey {
        case marketRegime = "market_regime"
        case volatilityLevel = "volatility_level"
        case entryMode = "entry_mode"
        case entryThresholdModifier = "entry_threshold_modifier"
        case stopLossModifier = "stop_loss_modifier"
        case currentAtrPct = "current_atr_pct"
        case takeProfitTarget = "take_profit_target"
        case lastUpdate = "last_update"
    }

    var regimeDisplayName: String {
        switch marketRegime {
        case "strong_bullish": return "강세 상승"
        case "bullish": return "상승"
        case "neutral": return "중립"
        case "bearish": return "하락"
        case "strong_bearish": return "강세 하락"
        default: return marketRegime
        }
    }
}

struct CryptoTrade: Codable, Identifiable {
    var id: String { tradeId }
    let coin: String
    let entryTime: String
    let exitTime: String?
    let entryPrice: Double
    let exitPrice: Double?
    let entryConditions: [String]
    let profitKrw: Double
    let profitPct: Double
    let regime: String
    let tradeId: String
    let status: String

    enum CodingKeys: String, CodingKey {
        case coin
        case entryTime = "entry_time"
        case exitTime = "exit_time"
        case entryPrice = "entry_price"
        case exitPrice = "exit_price"
        case entryConditions = "entry_conditions"
        case profitKrw = "profit_krw"
        case profitPct = "profit_pct"
        case regime
        case tradeId = "trade_id"
        case status
    }
}

struct CryptoPerformance: Codable {
    let totalTrades: Int
    let winRate: Double
    let totalProfitPct: Double
    let avgProfitPct: Double

    enum CodingKeys: String, CodingKey {
        case totalTrades = "total_trades"
        case winRate = "win_rate"
        case totalProfitPct = "total_profit_pct"
        case avgProfitPct = "avg_profit_pct"
    }
}

struct CoinSummary: Codable, Identifiable {
    var id: String { coin }
    let coin: String
    let trades: Int
    let wins: Int
    let winRate: Double
    let totalProfitPct: Double
    let totalProfitKrw: Double
    let avgProfitPct: Double
    let lastTrade: String

    enum CodingKeys: String, CodingKey {
        case coin, trades, wins
        case winRate = "win_rate"
        case totalProfitPct = "total_profit_pct"
        case totalProfitKrw = "total_profit_krw"
        case avgProfitPct = "avg_profit_pct"
        case lastTrade = "last_trade"
    }
}

struct CoinPrice: Codable {
    let coin: String
    let closingPrice: Double?
    let openingPrice: Double?
    let highPrice: Double?
    let lowPrice: Double?
    let volume: Double?
    let changePct: Double?
    let timestamp: String?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case coin
        case closingPrice = "closing_price"
        case openingPrice = "opening_price"
        case highPrice = "high_price"
        case lowPrice = "low_price"
        case volume
        case changePct = "change_pct"
        case timestamp, error
    }

    var hasData: Bool { closingPrice != nil && error == nil }
}

struct Candlestick: Codable, Identifiable {
    var id: Int { timestamp }
    let timestamp: Int
    let open: Double
    let close: Double
    let high: Double
    let low: Double
    let volume: Double
}
