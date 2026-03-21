import Foundation

struct WFWorkflowPlist {
    var workflowMinimumClientVersion: Int = 900
    var workflowMinimumClientVersionString: String = "900"
    var workflowIcon: WFWorkflowIcon
    var workflowActions: [WFAction]
    var workflowInputContentItemClasses: [String]
    var workflowTypes: [String]

    struct WFWorkflowIcon: Codable {
        var startColor: Int
        var glyphNumber: Int

        func toDictionary() -> [String: Any] {
            [
                "WFWorkflowIconStartColor": startColor,
                "WFWorkflowIconGlyphNumber": glyphNumber
            ]
        }
    }

    struct WFAction {
        var identifier: String
        var parameters: [String: Any]

        func toDictionary() -> [String: Any] {
            [
                "WFWorkflowActionIdentifier": identifier,
                "WFWorkflowActionParameters": parameters
            ]
        }
    }

    func toDictionary() -> [String: Any] {
        [
            "WFWorkflowMinimumClientVersion": workflowMinimumClientVersion,
            "WFWorkflowMinimumClientVersionString": workflowMinimumClientVersionString,
            "WFWorkflowIcon": workflowIcon.toDictionary(),
            "WFWorkflowActions": workflowActions.map { $0.toDictionary() },
            "WFWorkflowInputContentItemClasses": workflowInputContentItemClasses,
            "WFWorkflowTypes": workflowTypes
        ]
    }
}
