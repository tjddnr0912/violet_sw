import SwiftUI

// MARK: - Block Category

enum BlockCategory: String, CaseIterable, Identifiable, Codable {
    case basic = "기본"
    case scripting = "스크립팅"
    case media = "미디어"
    case web = "웹"
    case apps = "앱"
    case device = "기기"
    case sharing = "공유"

    var id: String { rawValue }

    var iconName: String {
        switch self {
        case .basic: return "doc.text"
        case .scripting: return "gearshape"
        case .media: return "photo"
        case .web: return "globe"
        case .apps: return "square.grid.2x2"
        case .device: return "wrench"
        case .sharing: return "square.and.arrow.up"
        }
    }

    var color: Color {
        switch self {
        case .basic: return .blue
        case .scripting: return .orange
        case .media: return .pink
        case .web: return .green
        case .apps: return .purple
        case .device: return .gray
        case .sharing: return .teal
        }
    }
}

// MARK: - IO Type

enum IOType: String, Codable, Equatable {
    case any
    case text
    case number
    case boolean
    case url
    case image
    case date
    case dictionary
    case list
    case none
}

// MARK: - Parameter Type

enum ParameterType: String, Codable {
    case text
    case number
    case boolean
    case enumeration
    case variable
    case date
    case stepper
}

// MARK: - Parameter Definition

struct ParameterDefinition: Identifiable, Codable {
    let id: String
    let label: String
    let type: ParameterType
    let defaultValue: ParameterValue?
    let placeholder: String?
    let enumOptions: [String]?
    let minValue: Double?
    let maxValue: Double?
    let isRequired: Bool

    init(
        id: String,
        label: String,
        type: ParameterType,
        defaultValue: ParameterValue? = nil,
        placeholder: String? = nil,
        enumOptions: [String]? = nil,
        minValue: Double? = nil,
        maxValue: Double? = nil,
        isRequired: Bool = true
    ) {
        self.id = id
        self.label = label
        self.type = type
        self.defaultValue = defaultValue
        self.placeholder = placeholder
        self.enumOptions = enumOptions
        self.minValue = minValue
        self.maxValue = maxValue
        self.isRequired = isRequired
    }
}

// MARK: - Parameter Value

enum ParameterValue: Codable, Equatable {
    case text(String)
    case number(Double)
    case boolean(Bool)
    case enumValue(String)
    case variable(VariableRef)
    case date(Date)

    var displayText: String {
        switch self {
        case .text(let s): return s
        case .number(let n): return n.truncatingRemainder(dividingBy: 1) == 0 ? String(Int(n)) : String(n)
        case .boolean(let b): return b ? "참" : "거짓"
        case .enumValue(let s): return s
        case .variable(let v): return v.displayName
        case .date(let d):
            let formatter = DateFormatter()
            formatter.dateStyle = .short
            formatter.timeStyle = .short
            return formatter.string(from: d)
        }
    }
}
