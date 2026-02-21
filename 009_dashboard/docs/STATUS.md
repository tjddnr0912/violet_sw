# 프로젝트 진행 상태

최종 업데이트: 2026-02-21

## 완료

| 항목 | 내용 |
|------|------|
| Flask 백엔드 | v1 API 5개 + v2 API 12개, API Key 인증 |
| 웹 대시보드 | Jinja2 HTML 페이지 4개 (메인, 주식, 암호화폐, 임베드) |
| iOS 앱 소스코드 | 26개 Swift 파일, MVVM, xcodegen 빌드 |
| 시뮬레이터 검증 | iPhone 16 Pro (iOS 18.2) 빌드/실행/데이터 연동 확인 |
| URL Scheme 딥링크 | `tradingdashboard://tab/{dashboard,crypto,stock}` |
| UX 개선 | 주식 포지션 상세화, 장시간 인식 봇 상태, 코인별 차트/성과 |
| xcode-select 전환 | Xcode.app Developer 경로로 전환 완료 |

## 미완료

| 항목 | 내용 | 필요 조건 |
|------|------|-----------|
| Cloudflare Tunnel | 외부 접근을 위한 터널 설정 + launchd 등록 | `setup_tunnel.sh` 실행, 도메인 결정 |
| .env API Key | DASHBOARD_API_KEY 생성 후 .env 반영 | 수동 작업 |
| 실기기 테스트 | iPhone 실기기 빌드 검증 | Apple Developer 계정 + 기기 연결 |
| iOS WidgetKit | 홈 화면 위젯 | App Groups 설정 필요 |
