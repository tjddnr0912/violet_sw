# violet_sw

여러 개인 프로젝트를 한 저장소에서 개발·운영하는 **멀티 프로젝트 모노레포**입니다.
암호화폐·주식 자동매매 봇, 뉴스 자동화, 대시보드(웹·iOS·macOS), RTL 시뮬레이터, 학습용 코드까지
번호가 매겨진 폴더(`0NN_*`)로 분리되어 있습니다.

> 각 프로젝트는 독립적으로 동작하며 서로의 코드를 직접 참조하지 않습니다.

## 한눈에 보기

폴더는 세 부류로 나뉩니다.

- **프로덕션 시스템** (`005`–`016`) — 실제로 돌리는 봇·앱·도구
- **랩 & 스터디** (`000`–`004`, `999`) — 학습·실험·아카이브
- **지원 폴더** (`docs/`, `obsidian/`) — 공통 문서와 지식 베이스

## Quick Start

```bash
./start_all_bots.sh         # iTerm2 탭으로 전체 봇 일괄 실행
./start_all_bots_cmux.sh    # cmux 단일 워크스페이스(그리드)로 전체 봇 실행
```

개별 프로젝트는 각 폴더로 들어가 해당 `CLAUDE.md` / `docs/`의 실행 방법을 따릅니다.

## 프로덕션 시스템

| 폴더 | 프로젝트 | 한 줄 설명 | 스택 |
|------|----------|-----------|------|
| `005_money` | 암호화폐 봇 | Bithumb 멀티코인 자동매매 (15분 주기) | Python |
| `006_auto_bot` | 뉴스 자동화 봇 | RSS → AI 요약 → Blogger 발행 (뉴스/버핏/섹터/부동산/텔레그램) | Python |
| `007_stock_trade` | 한국주식 퀀트 | KOSPI200 자동매매 | Python · KIS API |
| `008_stock_trade_us` | 미국주식 퀀트 | S&P500 자동매매 (007 기반) | Python · KIS API |
| `009_dashboard` | 트레이딩 대시보드 | 봇 상태 웹 대시보드 (port 5001) | Flask |
| `010_ios_dashboard` | iOS 대시보드 | 대시보드 iOS 앱 (MVVM) | SwiftUI |
| `011_macos_cc_usage` | 사용량 모니터 | Claude Code 사용량 macOS 메뉴바 앱 | Swift |
| `012_stock_dashboard` | 글로벌 시장 대시보드 | Bloomberg 스타일 실시간 대시보드 (port 5002) | FastAPI |
| `013_shortcut` | Shortcuts 빌더 | 비주얼 블록 Apple Shortcuts 빌더 | SwiftUI |
| `014_casper` | 미장봇 | SPMO/GEM/Casper 멀티버킷 미국주식 봇 | Python · KIS API |
| `015_little_lion` | 개인 비서 | Obsidian 연동 개인 어시스턴트 (설계/계획 단계) | Python · FastAPI |
| `016_claude_rtl` | vitamin | 오픈소스 Rust RTL 시뮬레이터 (SystemVerilog/Verilog) | Rust |

각 프로젝트 폴더의 `CLAUDE.md`에 실행법·아키텍처·주의사항이 정리되어 있습니다.

## 랩 & 스터디 (아카이브)

| 폴더 | 내용 |
|------|------|
| `000_personal_lib_code` | 재사용 가능한 Python 유틸 코드 모음 |
| `001_coding_test_question` | 코딩테스트 문제 풀이 |
| `002_study_swift` | Swift 언어 학습 |
| `003_script` | 잡다한 스크립트 (Verilog 등) |
| `004_hacker_rank` | HackerRank 풀이 |
| `999_test` | 실험·테스트용 (real-estate MCP 등) |

## 지원 폴더

| 폴더 | 용도 |
|------|------|
| `docs/` | 저장소 공통 문서 — [PROJECTS](docs/PROJECTS.md)(프로젝트 상세), [ENVIRONMENT](docs/ENVIRONMENT.md)(환경변수), [TROUBLESHOOTING](docs/TROUBLESHOOTING.md)(트러블슈팅) |
| `obsidian/` | 크로스 프로젝트 지식 베이스(Obsidian vault) — 주제별 원자 노트 |

## 개발 규칙

1. **프로젝트 경계 존중** — 각 프로젝트는 독립. 다른 프로젝트 코드를 직접 참조하지 않습니다.
2. **파일 생성 최소화** — 기존 파일 수정 우선, `.md`는 명시적 요청 시에만 생성.
3. **환경변수 분리** — 프로젝트별 `.env` 사용.
4. **독립 Telegram Bot** — 봇마다 별도 토큰을 사용해 충돌이 없습니다.

커밋 메시지 접두사: `Add` / `Fix` / `Update` / `Refactor`

## 민감정보 / 보안

API 키·토큰·계정 정보는 **절대 저장소에 커밋하지 않습니다.** 루트 `.gitignore`가 다음을 차단합니다.

- `.env`, `.env.*` (단 `.env.example`은 허용)
- `*_token.pkl`, `token.json`, `credentials*.json`, `*_secret*.json`
- `*.pem`, `*.key`, `api_key*`, `auth_token*`
- 로컬 머신 전용 `.mcp.json`, 계좌·포트폴리오 설정 JSON

새 프로젝트를 추가하거나 키를 다룰 때는 위 패턴을 따르고, 설정 예시는 `.env.example`로만 공유합니다.

## AI 에이전트 가이드

- `CLAUDE.md` — Claude Code용 저장소·프로젝트 작업 지침
- `GEMINI.md` — Gemini용 지침
- 각 프로젝트 폴더의 `CLAUDE.md` — 프로젝트별 상세 지침
