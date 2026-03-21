import Foundation

@MainActor
final class BlockRegistry {
    static let shared = BlockRegistry()

    private(set) var definitions: [BlockDefinition] = []
    private var definitionMap: [String: BlockDefinition] = [:]

    private init() {
        registerAllBlocks()
    }

    func definition(for id: String) -> BlockDefinition? {
        definitionMap[id]
    }

    func definitions(for category: BlockCategory) -> [BlockDefinition] {
        definitions.filter { $0.category == category }
    }

    func search(query: String) -> [BlockDefinition] {
        guard !query.isEmpty else { return definitions }
        let lower = query.lowercased()
        return definitions.filter {
            $0.name.lowercased().contains(lower) ||
            $0.summary.lowercased().contains(lower) ||
            $0.category.rawValue.lowercased().contains(lower)
        }
    }

    private func register(_ definition: BlockDefinition) {
        definitions.append(definition)
        definitionMap[definition.id] = definition
    }

    private func registerAllBlocks() {
        registerBasicBlocks()
        registerScriptingBlocks()
        registerMediaBlocks()
        registerWebBlocks()
        registerAppBlocks()
        registerDeviceBlocks()
        registerSharingBlocks()
    }

    // MARK: - 기본 (8개)

    private func registerBasicBlocks() {
        register(BlockDefinition(
            id: "text", name: "텍스트", category: .basic, iconName: "doc.text", color: "blue",
            inputType: .none, outputType: .text,
            parameters: [
                ParameterDefinition(id: "WFTextActionText", label: "텍스트", type: .text,
                    defaultValue: .text(""), placeholder: "텍스트를 입력하세요")
            ],
            wfActionIdentifier: "is.workflow.actions.gettext", summary: "텍스트 값을 생성합니다"
        ))

        register(BlockDefinition(
            id: "number", name: "숫자", category: .basic, iconName: "number", color: "blue",
            inputType: .none, outputType: .number,
            parameters: [
                ParameterDefinition(id: "WFNumberActionNumber", label: "숫자", type: .number,
                    defaultValue: .number(0), placeholder: "숫자를 입력하세요")
            ],
            wfActionIdentifier: "is.workflow.actions.number", summary: "숫자 값을 생성합니다"
        ))

        register(BlockDefinition(
            id: "comment", name: "코멘트", category: .basic, iconName: "text.bubble", color: "gray",
            inputType: .any, outputType: .any,
            parameters: [
                ParameterDefinition(id: "WFCommentActionText", label: "코멘트", type: .text,
                    defaultValue: .text(""), placeholder: "메모를 입력하세요")
            ],
            wfActionIdentifier: "is.workflow.actions.comment", summary: "워크플로우에 메모를 추가합니다"
        ))

        register(BlockDefinition(
            id: "dictionary", name: "사전", category: .basic, iconName: "list.bullet.rectangle", color: "blue",
            inputType: .none, outputType: .dictionary,
            parameters: [
                ParameterDefinition(id: "WFItems", label: "내용", type: .text,
                    defaultValue: .text(""), placeholder: "키: 값 형태로 입력")
            ],
            wfActionIdentifier: "is.workflow.actions.dictionary", summary: "사전(키-값) 데이터를 생성합니다"
        ))

        register(BlockDefinition(
            id: "list", name: "목록", category: .basic, iconName: "list.bullet", color: "blue",
            inputType: .none, outputType: .list,
            parameters: [
                ParameterDefinition(id: "WFItems", label: "항목들", type: .text,
                    defaultValue: .text(""), placeholder: "각 줄에 하나씩 입력")
            ],
            wfActionIdentifier: "is.workflow.actions.list", summary: "목록 데이터를 생성합니다"
        ))

        register(BlockDefinition(
            id: "getVariable", name: "변수 가져오기", category: .basic, iconName: "tray.and.arrow.up", color: "blue",
            inputType: .none, outputType: .any,
            parameters: [
                ParameterDefinition(id: "WFVariable", label: "변수 이름", type: .text,
                    defaultValue: .text(""), placeholder: "변수 이름")
            ],
            wfActionIdentifier: "is.workflow.actions.getvariable", summary: "저장된 변수를 가져옵니다"
        ))

        register(BlockDefinition(
            id: "setVariable", name: "변수 설정", category: .basic, iconName: "tray.and.arrow.down", color: "blue",
            inputType: .any, outputType: .any,
            parameters: [
                ParameterDefinition(id: "WFVariableName", label: "변수 이름", type: .text,
                    defaultValue: .text(""), placeholder: "변수 이름")
            ],
            wfActionIdentifier: "is.workflow.actions.setvariable", summary: "입력을 변수에 저장합니다"
        ))

        register(BlockDefinition(
            id: "nothing", name: "없음", category: .basic, iconName: "circle.slash", color: "gray",
            inputType: .none, outputType: .any,
            parameters: [],
            wfActionIdentifier: "is.workflow.actions.nothing", summary: "빈 값(없음)을 전달합니다"
        ))
    }

    // MARK: - 스크립팅 (12개 + 제어 흐름 마커)

    // Control flow block IDs that auto-insert markers
    static let controlFlowStartBlocks: Set<String> = ["conditional", "repeat", "repeatEach"]
    static let controlFlowWithElse: Set<String> = ["conditional"]

    private func registerScriptingBlocks() {
        register(BlockDefinition(
            id: "conditional", name: "조건 (If)", category: .scripting, iconName: "arrow.triangle.branch", color: "orange",
            inputType: .any, outputType: .any,
            parameters: [
                ParameterDefinition(id: "WFCondition", label: "조건", type: .enumeration,
                    defaultValue: .enumValue("같음"),
                    enumOptions: ["같음", "같지 않음", "포함", "포함하지 않음", "보다 큼", "보다 작음"]),
                ParameterDefinition(id: "WFConditionalActionString", label: "비교 값", type: .text,
                    placeholder: "비교할 값")
            ],
            wfActionIdentifier: "is.workflow.actions.conditional", summary: "조건에 따라 분기합니다"
        ))

        register(BlockDefinition(
            id: "conditional_otherwise", name: "그렇지 않으면 (Otherwise)", category: .scripting,
            iconName: "arrow.triangle.branch", color: "orange",
            inputType: .any, outputType: .any, parameters: [],
            wfActionIdentifier: "is.workflow.actions.conditional", summary: "If 조건이 거짓일 때 실행됩니다"
        ))

        register(BlockDefinition(
            id: "conditional_end", name: "조건 끝 (End If)", category: .scripting,
            iconName: "arrow.triangle.branch", color: "orange",
            inputType: .any, outputType: .any, parameters: [],
            wfActionIdentifier: "is.workflow.actions.conditional", summary: "If 블록의 끝입니다"
        ))

        register(BlockDefinition(
            id: "repeat", name: "반복", category: .scripting, iconName: "repeat", color: "orange",
            inputType: .any, outputType: .any,
            parameters: [
                ParameterDefinition(id: "WFRepeatCount", label: "반복 횟수", type: .stepper,
                    defaultValue: .number(3), minValue: 1, maxValue: 100)
            ],
            wfActionIdentifier: "is.workflow.actions.repeat.count", summary: "지정한 횟수만큼 반복합니다"
        ))

        register(BlockDefinition(
            id: "repeat_end", name: "반복 끝 (End Repeat)", category: .scripting,
            iconName: "repeat", color: "orange",
            inputType: .any, outputType: .any, parameters: [],
            wfActionIdentifier: "is.workflow.actions.repeat.count", summary: "반복 블록의 끝입니다"
        ))

        register(BlockDefinition(
            id: "repeatEach", name: "각 항목 반복", category: .scripting, iconName: "repeat.circle", color: "orange",
            inputType: .list, outputType: .any,
            parameters: [],
            wfActionIdentifier: "is.workflow.actions.repeat.each", summary: "목록의 각 항목에 대해 반복합니다"
        ))

        register(BlockDefinition(
            id: "repeatEach_end", name: "각 항목 반복 끝", category: .scripting,
            iconName: "repeat.circle", color: "orange",
            inputType: .any, outputType: .any, parameters: [],
            wfActionIdentifier: "is.workflow.actions.repeat.each", summary: "각 항목 반복 블록의 끝입니다"
        ))

        register(BlockDefinition(
            id: "wait", name: "대기", category: .scripting, iconName: "clock", color: "orange",
            inputType: .any, outputType: .any,
            parameters: [
                ParameterDefinition(id: "WFWaitActionTime", label: "대기 시간(초)", type: .stepper,
                    defaultValue: .number(1), minValue: 0.5, maxValue: 60)
            ],
            wfActionIdentifier: "is.workflow.actions.delay", summary: "지정된 시간 동안 대기합니다"
        ))

        register(BlockDefinition(
            id: "exit", name: "단축어 종료", category: .scripting, iconName: "xmark.circle", color: "orange",
            inputType: .any, outputType: .none,
            parameters: [],
            wfActionIdentifier: "is.workflow.actions.exit", summary: "단축어 실행을 중지합니다"
        ))

        register(BlockDefinition(
            id: "chooseFromMenu", name: "메뉴에서 선택", category: .scripting, iconName: "list.bullet.indent", color: "orange",
            inputType: .any, outputType: .any,
            parameters: [
                ParameterDefinition(id: "WFMenuPrompt", label: "프롬프트", type: .text,
                    defaultValue: .text("선택하세요"), placeholder: "메뉴 제목")
            ],
            wfActionIdentifier: "is.workflow.actions.choosefrommenu", summary: "메뉴 옵션을 표시하고 선택받습니다"
        ))

        register(BlockDefinition(
            id: "showAlert", name: "알림 대화상자", category: .scripting, iconName: "exclamationmark.triangle", color: "orange",
            inputType: .any, outputType: .any,
            parameters: [
                ParameterDefinition(id: "WFAlertActionTitle", label: "제목", type: .text,
                    defaultValue: .text("알림"), placeholder: "대화상자 제목"),
                ParameterDefinition(id: "WFAlertActionMessage", label: "메시지", type: .text,
                    defaultValue: .text(""), placeholder: "메시지 내용"),
                ParameterDefinition(id: "WFAlertActionCancelButtonShown", label: "취소 버튼 표시", type: .boolean,
                    defaultValue: .boolean(true), isRequired: false)
            ],
            wfActionIdentifier: "is.workflow.actions.alert", summary: "알림 대화상자를 표시합니다"
        ))

        register(BlockDefinition(
            id: "askInput", name: "입력 요청", category: .scripting, iconName: "keyboard", color: "orange",
            inputType: .any, outputType: .text,
            parameters: [
                ParameterDefinition(id: "WFAskActionPrompt", label: "프롬프트", type: .text,
                    defaultValue: .text(""), placeholder: "질문 내용"),
                ParameterDefinition(id: "WFInputType", label: "입력 유형", type: .enumeration,
                    defaultValue: .enumValue("Text"),
                    enumOptions: ["Text", "Number", "URL", "Date", "Time", "Date and Time"]),
                ParameterDefinition(id: "WFAskActionDefaultAnswer", label: "기본값", type: .text,
                    defaultValue: .text(""), placeholder: "기본 답변", isRequired: false)
            ],
            wfActionIdentifier: "is.workflow.actions.ask", summary: "사용자에게 입력을 요청합니다"
        ))

        register(BlockDefinition(
            id: "chooseFromList", name: "목록에서 선택", category: .scripting, iconName: "hand.tap", color: "orange",
            inputType: .list, outputType: .any,
            parameters: [
                ParameterDefinition(id: "WFChooseFromListActionPrompt", label: "프롬프트", type: .text,
                    defaultValue: .text("선택하세요"), placeholder: "안내 문구"),
                ParameterDefinition(id: "WFChooseFromListActionSelectMultiple", label: "복수 선택", type: .boolean,
                    defaultValue: .boolean(false), isRequired: false)
            ],
            wfActionIdentifier: "is.workflow.actions.choosefromlist", summary: "목록에서 항목을 선택합니다"
        ))
    }

    // MARK: - 미디어 (5개)

    private func registerMediaBlocks() {
        register(BlockDefinition(
            id: "selectPhotos", name: "사진 선택", category: .media, iconName: "photo.on.rectangle", color: "pink",
            inputType: .none, outputType: .image,
            parameters: [
                ParameterDefinition(id: "WFSelectMultiplePhotos", label: "여러 장 선택", type: .boolean,
                    defaultValue: .boolean(false), isRequired: false)
            ],
            wfActionIdentifier: "is.workflow.actions.selectphoto", summary: "사진 라이브러리에서 사진을 선택합니다"
        ))

        register(BlockDefinition(
            id: "takePhoto", name: "사진 찍기", category: .media, iconName: "camera", color: "pink",
            inputType: .none, outputType: .image,
            parameters: [
                ParameterDefinition(id: "WFCameraCaptureShowPreview", label: "미리보기 표시", type: .boolean,
                    defaultValue: .boolean(true), isRequired: false)
            ],
            wfActionIdentifier: "is.workflow.actions.takephoto", summary: "카메라로 사진을 촬영합니다"
        ))

        register(BlockDefinition(
            id: "takeScreenshot", name: "스크린샷", category: .media, iconName: "camera.viewfinder", color: "pink",
            inputType: .none, outputType: .image,
            parameters: [],
            wfActionIdentifier: "is.workflow.actions.takescreenshot", summary: "현재 화면의 스크린샷을 찍습니다"
        ))

        register(BlockDefinition(
            id: "resizeImage", name: "이미지 크기 조정", category: .media, iconName: "arrow.up.left.and.arrow.down.right", color: "pink",
            inputType: .image, outputType: .image,
            parameters: [
                ParameterDefinition(id: "WFImageResizeWidth", label: "너비", type: .number,
                    defaultValue: .number(800), placeholder: "픽셀"),
                ParameterDefinition(id: "WFImageResizeHeight", label: "높이", type: .number,
                    defaultValue: .number(600), placeholder: "픽셀", isRequired: false)
            ],
            wfActionIdentifier: "is.workflow.actions.image.resize", summary: "이미지 크기를 변경합니다"
        ))

        register(BlockDefinition(
            id: "overlayText", name: "텍스트 오버레이", category: .media, iconName: "textformat.abc", color: "pink",
            inputType: .image, outputType: .image,
            parameters: [
                ParameterDefinition(id: "WFText", label: "텍스트", type: .text,
                    defaultValue: .text(""), placeholder: "이미지 위에 표시할 텍스트")
            ],
            wfActionIdentifier: "is.workflow.actions.overlayimageonimage", summary: "이미지 위에 텍스트를 오버레이합니다"
        ))
    }

    // MARK: - 웹 (7개)

    private func registerWebBlocks() {
        register(BlockDefinition(
            id: "url", name: "URL", category: .web, iconName: "link", color: "green",
            inputType: .none, outputType: .url,
            parameters: [
                ParameterDefinition(id: "WFURLActionURL", label: "URL", type: .text,
                    defaultValue: .text("https://"), placeholder: "URL을 입력하세요")
            ],
            wfActionIdentifier: "is.workflow.actions.url", summary: "URL 값을 생성합니다"
        ))

        register(BlockDefinition(
            id: "openurl", name: "URL 열기", category: .web, iconName: "safari", color: "green",
            inputType: .url, outputType: .none,
            parameters: [],
            wfActionIdentifier: "is.workflow.actions.openurl", summary: "Safari에서 URL을 엽니다"
        ))

        register(BlockDefinition(
            id: "getURLContents", name: "URL 내용 가져오기", category: .web, iconName: "arrow.down.doc", color: "green",
            inputType: .url, outputType: .any,
            parameters: [
                ParameterDefinition(id: "WFHTTPMethod", label: "HTTP 메서드", type: .enumeration,
                    defaultValue: .enumValue("GET"),
                    enumOptions: ["GET", "POST", "PUT", "PATCH", "DELETE"]),
                ParameterDefinition(id: "WFHTTPHeaders", label: "헤더", type: .text,
                    defaultValue: .text(""), placeholder: "JSON 형태의 헤더", isRequired: false),
                ParameterDefinition(id: "WFHTTPBodyType", label: "본문", type: .text,
                    defaultValue: .text(""), placeholder: "요청 본문", isRequired: false)
            ],
            wfActionIdentifier: "is.workflow.actions.downloadurl", summary: "URL의 내용을 가져옵니다 (API 호출)"
        ))

        register(BlockDefinition(
            id: "getWebPageContents", name: "웹 페이지 내용", category: .web, iconName: "doc.richtext", color: "green",
            inputType: .url, outputType: .text,
            parameters: [],
            wfActionIdentifier: "is.workflow.actions.getarticle", summary: "웹 페이지의 본문 텍스트를 추출합니다"
        ))

        register(BlockDefinition(
            id: "searchWeb", name: "웹 검색", category: .web, iconName: "magnifyingglass.circle", color: "green",
            inputType: .text, outputType: .url,
            parameters: [],
            wfActionIdentifier: "is.workflow.actions.searchweb", summary: "기본 검색 엔진으로 웹을 검색합니다"
        ))

        register(BlockDefinition(
            id: "getRSS", name: "RSS 피드", category: .web, iconName: "dot.radiowaves.up.forward", color: "green",
            inputType: .url, outputType: .list,
            parameters: [
                ParameterDefinition(id: "WFRSSItemQuantity", label: "항목 수", type: .stepper,
                    defaultValue: .number(10), minValue: 1, maxValue: 50)
            ],
            wfActionIdentifier: "is.workflow.actions.rss", summary: "RSS 피드의 항목들을 가져옵니다"
        ))

        register(BlockDefinition(
            id: "expandURL", name: "URL 확장", category: .web, iconName: "link.badge.plus", color: "green",
            inputType: .url, outputType: .url,
            parameters: [],
            wfActionIdentifier: "is.workflow.actions.url.expand", summary: "단축 URL을 원래 URL로 확장합니다"
        ))
    }

    // MARK: - 앱 (5개)

    private func registerAppBlocks() {
        register(BlockDefinition(
            id: "addCalendarEvent", name: "캘린더 이벤트 추가", category: .apps, iconName: "calendar.badge.plus", color: "purple",
            inputType: .any, outputType: .any,
            parameters: [
                ParameterDefinition(id: "WFCalendarItemTitle", label: "제목", type: .text,
                    defaultValue: .text(""), placeholder: "이벤트 제목"),
                ParameterDefinition(id: "WFCalendarItemLocation", label: "위치", type: .text,
                    defaultValue: .text(""), placeholder: "위치", isRequired: false),
                ParameterDefinition(id: "WFCalendarItemAllDay", label: "종일 이벤트", type: .boolean,
                    defaultValue: .boolean(false), isRequired: false)
            ],
            wfActionIdentifier: "is.workflow.actions.addnewcalendar", summary: "캘린더에 새 이벤트를 추가합니다"
        ))

        register(BlockDefinition(
            id: "addReminder", name: "미리알림 추가", category: .apps, iconName: "checklist", color: "purple",
            inputType: .any, outputType: .any,
            parameters: [
                ParameterDefinition(id: "WFReminderTitle", label: "제목", type: .text,
                    defaultValue: .text(""), placeholder: "미리알림 제목"),
                ParameterDefinition(id: "WFReminderNotes", label: "메모", type: .text,
                    defaultValue: .text(""), placeholder: "메모", isRequired: false)
            ],
            wfActionIdentifier: "is.workflow.actions.addnewreminder", summary: "미리알림에 새 항목을 추가합니다"
        ))

        register(BlockDefinition(
            id: "sendEmail", name: "메일 보내기", category: .apps, iconName: "envelope", color: "purple",
            inputType: .any, outputType: .none,
            parameters: [
                ParameterDefinition(id: "WFSendEmailActionTo", label: "받는 사람", type: .text,
                    defaultValue: .text(""), placeholder: "이메일 주소"),
                ParameterDefinition(id: "WFSendEmailActionSubject", label: "제목", type: .text,
                    defaultValue: .text(""), placeholder: "메일 제목"),
                ParameterDefinition(id: "WFSendEmailActionBody", label: "본문", type: .text,
                    defaultValue: .text(""), placeholder: "메일 내용", isRequired: false)
            ],
            wfActionIdentifier: "is.workflow.actions.sendemail", summary: "이메일을 전송합니다"
        ))

        register(BlockDefinition(
            id: "sendMessage", name: "메시지 보내기", category: .apps, iconName: "message", color: "purple",
            inputType: .any, outputType: .none,
            parameters: [
                ParameterDefinition(id: "WFSendMessageActionRecipients", label: "받는 사람", type: .text,
                    defaultValue: .text(""), placeholder: "전화번호 또는 이메일"),
                ParameterDefinition(id: "WFSendMessageContent", label: "내용", type: .text,
                    defaultValue: .text(""), placeholder: "메시지 내용")
            ],
            wfActionIdentifier: "is.workflow.actions.sendmessage", summary: "iMessage/SMS를 전송합니다"
        ))

        register(BlockDefinition(
            id: "openApp", name: "앱 열기", category: .apps, iconName: "app.badge", color: "purple",
            inputType: .none, outputType: .none,
            parameters: [
                ParameterDefinition(id: "WFAppIdentifier", label: "앱 이름", type: .text,
                    defaultValue: .text(""), placeholder: "앱 이름 또는 번들 ID")
            ],
            wfActionIdentifier: "is.workflow.actions.openapp", summary: "지정한 앱을 엽니다"
        ))
    }

    // MARK: - 기기 (7개)

    private func registerDeviceBlocks() {
        register(BlockDefinition(
            id: "notification", name: "알림 표시", category: .device, iconName: "bell", color: "gray",
            inputType: .any, outputType: .none,
            parameters: [
                ParameterDefinition(id: "WFNotificationActionTitle", label: "제목", type: .text,
                    defaultValue: .text("알림"), placeholder: "알림 제목"),
                ParameterDefinition(id: "WFNotificationActionBody", label: "본문", type: .text,
                    defaultValue: .text(""), placeholder: "알림 내용")
            ],
            wfActionIdentifier: "is.workflow.actions.notification", summary: "푸시 알림을 표시합니다"
        ))

        register(BlockDefinition(
            id: "setBrightness", name: "밝기 설정", category: .device, iconName: "sun.max", color: "gray",
            inputType: .any, outputType: .any,
            parameters: [
                ParameterDefinition(id: "WFBrightness", label: "밝기 (%)", type: .stepper,
                    defaultValue: .number(50), minValue: 0, maxValue: 100)
            ],
            wfActionIdentifier: "is.workflow.actions.setbrightness", summary: "화면 밝기를 설정합니다"
        ))

        register(BlockDefinition(
            id: "setVolume", name: "볼륨 설정", category: .device, iconName: "speaker.wave.2", color: "gray",
            inputType: .any, outputType: .any,
            parameters: [
                ParameterDefinition(id: "WFVolume", label: "볼륨 (%)", type: .stepper,
                    defaultValue: .number(50), minValue: 0, maxValue: 100)
            ],
            wfActionIdentifier: "is.workflow.actions.setvolume", summary: "기기 볼륨을 설정합니다"
        ))

        register(BlockDefinition(
            id: "vibrate", name: "진동", category: .device, iconName: "iphone.radiowaves.left.and.right", color: "gray",
            inputType: .any, outputType: .any,
            parameters: [],
            wfActionIdentifier: "is.workflow.actions.vibrate", summary: "기기를 진동시킵니다"
        ))

        register(BlockDefinition(
            id: "flashlight", name: "손전등", category: .device, iconName: "flashlight.on.fill", color: "gray",
            inputType: .any, outputType: .any,
            parameters: [
                ParameterDefinition(id: "WFFlashlightSetting", label: "동작", type: .enumeration,
                    defaultValue: .enumValue("켜기"), enumOptions: ["켜기", "끄기", "토글"])
            ],
            wfActionIdentifier: "is.workflow.actions.flashlight", summary: "손전등을 켜거나 끕니다"
        ))

        register(BlockDefinition(
            id: "dnd", name: "방해금지 모드", category: .device, iconName: "moon.fill", color: "gray",
            inputType: .any, outputType: .any,
            parameters: [
                ParameterDefinition(id: "WFDNDSetting", label: "동작", type: .enumeration,
                    defaultValue: .enumValue("켜기"), enumOptions: ["켜기", "끄기", "토글"])
            ],
            wfActionIdentifier: "is.workflow.actions.dnd", summary: "방해금지 모드를 전환합니다"
        ))

        register(BlockDefinition(
            id: "getBatteryLevel", name: "배터리 잔량", category: .device, iconName: "battery.75percent", color: "gray",
            inputType: .none, outputType: .number,
            parameters: [],
            wfActionIdentifier: "is.workflow.actions.getbatterylevel", summary: "현재 배터리 잔량을 가져옵니다"
        ))
    }

    // MARK: - 공유 (4개)

    private func registerSharingBlocks() {
        register(BlockDefinition(
            id: "clipboard", name: "클립보드에 복사", category: .sharing, iconName: "doc.on.clipboard", color: "teal",
            inputType: .any, outputType: .none,
            parameters: [
                ParameterDefinition(id: "WFLocalOnly", label: "기기 내에서만", type: .boolean,
                    defaultValue: .boolean(false), isRequired: false)
            ],
            wfActionIdentifier: "is.workflow.actions.setclipboard", summary: "입력을 클립보드에 복사합니다"
        ))

        register(BlockDefinition(
            id: "getClipboard", name: "클립보드 가져오기", category: .sharing, iconName: "doc.on.clipboard.fill", color: "teal",
            inputType: .none, outputType: .any,
            parameters: [],
            wfActionIdentifier: "is.workflow.actions.getclipboard", summary: "클립보드 내용을 가져옵니다"
        ))

        register(BlockDefinition(
            id: "share", name: "공유", category: .sharing, iconName: "square.and.arrow.up", color: "teal",
            inputType: .any, outputType: .none,
            parameters: [],
            wfActionIdentifier: "is.workflow.actions.share", summary: "공유 시트를 표시합니다"
        ))

        register(BlockDefinition(
            id: "airdrop", name: "AirDrop", category: .sharing, iconName: "airplayaudio", color: "teal",
            inputType: .any, outputType: .none,
            parameters: [],
            wfActionIdentifier: "is.workflow.actions.airdrop", summary: "AirDrop으로 콘텐츠를 공유합니다"
        ))
    }
}
