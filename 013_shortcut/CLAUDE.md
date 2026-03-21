# CLAUDE.md - ShortcutCraft (013_shortcut)

비주얼 블록 기반 Apple Shortcuts 빌더. 블록을 끌어다 이어붙이는 방식으로 .shortcut 파일 생성.

## Quick Start

```bash
cd 013_shortcut
xcodegen generate          # .xcodeproj 생성
open ShortcutCraft.xcodeproj  # Xcode에서 열기
# iOS Simulator 또는 macOS 타겟으로 빌드 & 실행
```

## 아키텍처

```
ShortcutCraft/
├── App/          # @main, ContentView (3-column NavigationSplitView)
├── Models/       # BlockDefinition, BlockInstance, WorkflowDocument, WFWorkflowPlist 등
├── Services/     # BlockRegistry(45블록), Exporter, PlistGenerator, Signer 등
├── ViewModels/   # EditorVM, PaletteVM, TemplateVM, LibraryVM
├── Views/        # Editor/, Palette/, Config/, Templates/, Library/, Preview/, Settings/, Components/
└── Extensions/   # Color+Theme, View+AdaptiveLayout, UUID+Shortcut
```

**패턴**: MVVM + @MainActor, SwiftUI 네이티브, 외부 의존성 없음
**플랫폼**: iOS 16+ / macOS 14+ 유니버설 (단일 타겟, supportedDestinations)
**빌드**: xcodegen (project.yml)

## 핵심 모듈

| 모듈 | 역할 |
|------|------|
| `BlockRegistry` | 45개 블록 정의 (7 카테고리). `definition(for:)`, `search(query:)` |
| `EditorViewModel` | 캔버스 상태 관리. 추가/삭제/이동/복제/Undo/Redo/검증 |
| `BlockToWFConverter` | BlockInstance → WFAction 변환 (GroupingIdentifier, WFControlFlowMode 포함) |
| `PlistGenerator` | WFWorkflowPlist → 바이너리 plist (PropertyListSerialization) |
| `WorkflowExporter` | 내보내기 오케스트레이터. macOS 자동 서명, iOS ShareSheet |
| `DocumentManager` | ~/Documents/ShortcutCraft/ JSON 저장/불러오기 |
| `HapticManager` | iOS 햅틱 피드백 (설정 연동) |

## 중첩 블록 (제어 흐름)

If/Else, Repeat 블록은 자동으로 시작/종료 마커를 삽입:
```
If (GroupingIdentifier: UUID, WFControlFlowMode: 0)
  → 본문 블록들 (들여쓰기)
Otherwise (같은 GroupingIdentifier, WFControlFlowMode: 1)
  → else 본문
End If (같은 GroupingIdentifier, WFControlFlowMode: 2)
```

## 내보내기 파이프라인

```
WorkflowDocument → BlockToWFConverter → PlistGenerator → .shortcut 파일
                                                        ↓ (macOS만)
                                                   ShortcutSigner (/usr/bin/shortcuts sign)
```

## 키보드 단축키

| 단축키 | 동작 |
|--------|------|
| Cmd+S | 저장 |
| Cmd+Z | 실행 취소 |
| Cmd+Shift+Z | 다시 실행 |
| Cmd+E | 내보내기 |
| Cmd+N | 새 워크플로우 |
| Cmd+Delete | 선택 블록 삭제 |

## 주의사항

- WFWorkflow plist 형식은 비공식. 실제 .shortcut 파일과 `plutil -convert xml1`로 비교 검증 필요
- iOS에서는 서명 불가 → 미서명 파일을 공유 시트로 Shortcuts 앱에 전달
- BlockRegistry 수정 시 BlockToWFConverter의 매개변수 키 매핑도 확인
- `#if os(macOS)` / `#if os(iOS)` 조건부 코드 주의
- 일부 액션은 추가 필수 매개변수 필요 (예: `askInput`에 `WFInputType`)
