# CLAUDE.md - 011_macos_cc_usage

macOS 메뉴바 상주 앱. Claude Code 사용량을 실시간 모니터링.

## Quick Start

```bash
cd 011_macos_cc_usage
./install.sh       # Release 빌드 → /Applications 설치 → 로그인 시 자동실행
./uninstall.sh     # LaunchAgent 해제 → 앱 삭제
```

개발 시: `xcodegen generate && open ClaudeUsage.xcodeproj` → Cmd+R

## 핵심 정보

- **타겟**: macOS 14.0+, LSUIElement (Dock 아이콘 없음)
- **데이터 소스**: `~/.claude/stats-cache.json` (로컬 파일, 인증 불필요)
- **세션 소스**: `~/.claude/projects/*/sessions-index.json`
- **Sandbox**: OFF (홈 디렉토리 파일 접근 필요)
- **아키텍처**: MVVM (SwiftUI + MenuBarExtra)
- **API 제약**: `api.anthropic.com/api/oauth/usage`는 현재 외부 앱에서 호출 불가. 로컬 파일만 사용.

## 주요 모듈

| 파일 | 역할 |
|------|------|
| `App/ClaudeUsageApp.swift` | @main, MenuBarExtra(.window) 진입점 |
| `Models/StatsCache.swift` | stats-cache.json Codable 모델 |
| `Models/SessionIndex.swift` | sessions-index.json Codable 모델 |
| `Services/StatsFileReader.swift` | 파일 읽기 + JSON 디코딩 |
| `Services/SessionScanner.swift` | 프로젝트별 세션 스캔 |
| `Services/FileWatcher.swift` | DispatchSource 파일 변경 감지 |
| `ViewModels/UsageViewModel.swift` | 데이터 집계 + 모델명 매핑 |
| `Views/PopoverContentView.swift` | 루트 팝업 뷰 (340x560) |
| `Views/UsageMeterView.swift` | 프로그레스 바 + % (웹 스타일) |
| `Views/HeaderSection.swift` | "Plan Usage Limits" + Max 배지 |
| `Views/ModelBreakdownSection.swift` | 모델별 토큰 비율 바 |
| `Views/DailyActivityChart.swift` | Swift Charts 14일 막대 차트 |

## 파일 모니터링

- **Primary**: DispatchSource (kqueue) - 파일 변경 즉시 감지 (CPU 0%)
- **Fallback**: 60초 타이머
- **Manual**: Refresh 버튼

## 제약사항

- Anthropic Usage API (`/api/oauth/usage`)에 OAuth 토큰으로 직접 호출 불가 ("OAuth authentication is currently not supported")
- 따라서 실시간 사용률(%), 리셋 시간은 표시 불가. 로컬 stats-cache.json 기반 활동량만 표시.
- 키체인 접근 제거됨 (macOS 비밀번호 프롬프트 발생 → UX 문제). planType "Max" 하드코딩.
