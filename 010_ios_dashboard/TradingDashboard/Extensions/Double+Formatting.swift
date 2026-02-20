import Foundation

extension Double {
    /// "1,234,567원" 형태
    var formattedKRW: String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.maximumFractionDigits = 0
        let number = formatter.string(from: NSNumber(value: self)) ?? "0"
        return "\(number)원"
    }

    /// "1.2만원" 같은 축약 형태
    var formattedCompactKRW: String {
        if abs(self) >= 100_000_000 {
            return String(format: "%.1f억", self / 100_000_000)
        } else if abs(self) >= 10_000 {
            return String(format: "%.0f만", self / 10_000)
        }
        return formattedKRW
    }

    /// "+2.35%" 또는 "-1.20%" 형태
    var formattedPercent: String {
        let sign = self >= 0 ? "+" : ""
        return "\(sign)\(String(format: "%.2f", self))%"
    }
}
