import Foundation

struct PlistGenerator {
    func generate(from plist: WFWorkflowPlist) throws -> Data {
        let dict = plist.toDictionary() as NSDictionary
        return try PropertyListSerialization.data(fromPropertyList: dict, format: .binary, options: 0)
    }

    func generateXML(from plist: WFWorkflowPlist) throws -> Data {
        let dict = plist.toDictionary() as NSDictionary
        return try PropertyListSerialization.data(fromPropertyList: dict, format: .xml, options: 0)
    }
}
