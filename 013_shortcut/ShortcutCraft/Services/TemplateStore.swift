import Foundation

@MainActor
final class TemplateStore: ObservableObject {
    static let shared = TemplateStore()

    @Published private(set) var templates: [Template] = []

    private init() {
        loadBuiltInTemplates()
    }

    var categories: [String] {
        Array(Set(templates.map { $0.category })).sorted()
    }

    private func loadBuiltInTemplates() {
        templates = [
            // 일상
            Template(
                id: "morning_greeting", name: "아침 인사 알림",
                summary: "매일 아침 알림으로 인사 메시지를 보냅니다",
                iconName: "sun.max", colorName: "orange", category: "일상",
                document: WorkflowDocument(name: "아침 인사 알림", icon: "sun.max", colorName: "orange", blocks: [
                    BlockInstance(definitionId: "text", parameterValues: ["WFTextActionText": .text("좋은 아침이에요! 오늘도 화이팅!")], position: 0),
                    BlockInstance(definitionId: "notification", parameterValues: ["WFNotificationActionTitle": .text("아침 인사"), "WFNotificationActionBody": .text("좋은 아침이에요!")], position: 1)
                ])
            ),
            Template(
                id: "battery_check", name: "배터리 확인 알림",
                summary: "배터리 잔량을 확인하고 알림으로 보여줍니다",
                iconName: "battery.75percent", colorName: "green", category: "일상",
                document: WorkflowDocument(name: "배터리 확인", icon: "battery.75percent", colorName: "green", blocks: [
                    BlockInstance(definitionId: "getBatteryLevel", parameterValues: [:], position: 0),
                    BlockInstance(definitionId: "notification", parameterValues: ["WFNotificationActionTitle": .text("배터리 잔량"), "WFNotificationActionBody": .text("")], position: 1)
                ])
            ),
            Template(
                id: "dnd_toggle", name: "방해금지 토글",
                summary: "방해금지 모드를 켜거나 끕니다",
                iconName: "moon.fill", colorName: "purple", category: "일상",
                document: WorkflowDocument(name: "방해금지 토글", icon: "moon.fill", colorName: "purple", blocks: [
                    BlockInstance(definitionId: "dnd", parameterValues: ["WFDNDSetting": .enumValue("토글")], position: 0),
                    BlockInstance(definitionId: "notification", parameterValues: ["WFNotificationActionTitle": .text("방해금지"), "WFNotificationActionBody": .text("방해금지 모드가 전환되었습니다")], position: 1)
                ])
            ),

            // 웹
            Template(
                id: "open_website", name: "즐겨찾기 열기",
                summary: "자주 방문하는 웹사이트를 빠르게 엽니다",
                iconName: "safari", colorName: "green", category: "웹",
                document: WorkflowDocument(name: "즐겨찾기 열기", icon: "safari", colorName: "green", blocks: [
                    BlockInstance(definitionId: "url", parameterValues: ["WFURLActionURL": .text("https://apple.com")], position: 0),
                    BlockInstance(definitionId: "openurl", parameterValues: [:], position: 1)
                ])
            ),
            Template(
                id: "api_call", name: "API 호출",
                summary: "웹 API를 호출하고 결과를 표시합니다",
                iconName: "arrow.down.doc", colorName: "green", category: "웹",
                document: WorkflowDocument(name: "API 호출", icon: "arrow.down.doc", colorName: "green", blocks: [
                    BlockInstance(definitionId: "url", parameterValues: ["WFURLActionURL": .text("https://api.example.com/data")], position: 0),
                    BlockInstance(definitionId: "getURLContents", parameterValues: ["WFHTTPMethod": .enumValue("GET")], position: 1),
                    BlockInstance(definitionId: "showAlert", parameterValues: ["WFAlertActionTitle": .text("API 결과"), "WFAlertActionMessage": .text("")], position: 2)
                ])
            ),

            // 유틸리티
            Template(
                id: "copy_text", name: "텍스트 복사",
                summary: "자주 사용하는 텍스트를 클립보드에 복사합니다",
                iconName: "doc.on.clipboard", colorName: "teal", category: "유틸리티",
                document: WorkflowDocument(name: "텍스트 복사", icon: "doc.on.clipboard", colorName: "teal", blocks: [
                    BlockInstance(definitionId: "text", parameterValues: ["WFTextActionText": .text("여기에 텍스트 입력")], position: 0),
                    BlockInstance(definitionId: "clipboard", parameterValues: [:], position: 1)
                ])
            ),
            Template(
                id: "user_input", name: "사용자 입력 받기",
                summary: "사용자에게 입력을 받아 알림으로 표시합니다",
                iconName: "keyboard", colorName: "orange", category: "유틸리티",
                document: WorkflowDocument(name: "사용자 입력", icon: "keyboard", colorName: "orange", blocks: [
                    BlockInstance(definitionId: "askInput", parameterValues: ["WFAskActionPrompt": .text("이름을 입력하세요"), "WFAskActionDefaultAnswer": .text("")], position: 0),
                    BlockInstance(definitionId: "setVariable", parameterValues: ["WFVariableName": .text("사용자이름")], position: 1),
                    BlockInstance(definitionId: "notification", parameterValues: ["WFNotificationActionTitle": .text("환영합니다!"), "WFNotificationActionBody": .text("")], position: 2)
                ])
            ),
            Template(
                id: "screenshot_share", name: "스크린샷 공유",
                summary: "스크린샷을 찍고 공유 시트를 표시합니다",
                iconName: "camera.viewfinder", colorName: "pink", category: "유틸리티",
                document: WorkflowDocument(name: "스크린샷 공유", icon: "camera.viewfinder", colorName: "pink", blocks: [
                    BlockInstance(definitionId: "takeScreenshot", parameterValues: [:], position: 0),
                    BlockInstance(definitionId: "share", parameterValues: [:], position: 1)
                ])
            ),

            // 커뮤니케이션
            Template(
                id: "quick_message", name: "빠른 메시지",
                summary: "자주 보내는 메시지를 빠르게 전송합니다",
                iconName: "message", colorName: "blue", category: "커뮤니케이션",
                document: WorkflowDocument(name: "빠른 메시지", icon: "message", colorName: "blue", blocks: [
                    BlockInstance(definitionId: "text", parameterValues: ["WFTextActionText": .text("곧 도착합니다!")], position: 0),
                    BlockInstance(definitionId: "sendMessage", parameterValues: ["WFSendMessageActionRecipients": .text(""), "WFSendMessageContent": .text("")], position: 1)
                ])
            ),
            Template(
                id: "meeting_reminder", name: "회의 미리알림",
                summary: "캘린더에 회의를 추가하고 미리알림도 생성합니다",
                iconName: "calendar.badge.plus", colorName: "red", category: "커뮤니케이션",
                document: WorkflowDocument(name: "회의 미리알림", icon: "calendar.badge.plus", colorName: "red", blocks: [
                    BlockInstance(definitionId: "askInput", parameterValues: ["WFAskActionPrompt": .text("회의 제목을 입력하세요")], position: 0),
                    BlockInstance(definitionId: "addCalendarEvent", parameterValues: ["WFCalendarItemTitle": .text(""), "WFCalendarItemAllDay": .boolean(false)], position: 1),
                    BlockInstance(definitionId: "addReminder", parameterValues: ["WFReminderTitle": .text("회의 준비"), "WFReminderNotes": .text("")], position: 2)
                ])
            )
        ]
    }
}
