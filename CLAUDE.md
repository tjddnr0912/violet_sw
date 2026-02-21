# CLAUDE.md - violet_sw

멀티 프로젝트 개발 및 운영 저장소.

## Repository Overview

```
violet_sw/
├── 005_money/          # 암호화폐 트레이딩 봇 (Bithumb)
├── 006_auto_bot/       # 뉴스 자동화 봇 (RSS→AI→Blogger)
├── 007_stock_trade/    # 주식 퀀트 자동매매 (한국, KIS API)
├── 008_stock_trade_us/ # 주식 퀀트 자동매매 (미국, KIS API)
├── 009_dashboard/      # 트레이딩 대시보드 Flask 백엔드
├── 010_ios_dashboard/  # 트레이딩 대시보드 iOS 앱 (SwiftUI)
├── 000~004_*/          # Lab & Study (Archive)
└── start_all_bots.sh   # 전체 봇 일괄 실행 (iTerm2 5탭)
```

## Quick Start

```bash
./start_all_bots.sh    # iTerm2에서 모든 봇 일괄 실행
```

## Production Systems

| Project | 설명 | 실행 | 상세 |
|---------|------|------|------|
| 005_money | Bithumb 암호화폐 봇 (Ver3, 15분 주기) | `./scripts/run_v3_watchdog.sh` | [CLAUDE.md](005_money/CLAUDE.md) |
| 006_auto_bot | 뉴스/섹터 봇 (Gemini→Blogger) | `./run_scheduled.sh` | [CLAUDE.md](006_auto_bot/CLAUDE.md) |
| 007_stock_trade | 한국주식 퀀트 (KOSPI200, 15종목) | `./run_quant.sh daemon` | [CLAUDE.md](007_stock_trade/CLAUDE.md) |
| 008_stock_trade_us | 미국주식 퀀트 (S&P500, 15종목) | `./run_quant.sh daemon` | [CLAUDE.md](008_stock_trade_us/CLAUDE.md) |
| 009_dashboard | Flask 대시보드 (port 5001) | `python app.py` | [CLAUDE.md](009_dashboard/CLAUDE.md) |
| 010_ios_dashboard | SwiftUI iOS 앱 (MVVM) | `xcodegen generate` | [CLAUDE.md](010_ios_dashboard/CLAUDE.md) |

## Development Guidelines

1. **프로젝트 경계 존중**: 각 프로젝트는 독립적. 다른 프로젝트 코드 참조 금지.
2. **파일 생성 최소화**: 기존 파일 수정 우선. `.md`는 명시적 요청 시에만 생성.
3. **환경변수**: 각 프로젝트별 `.env` 파일 필요. **절대 Git에 커밋하지 말 것.**
4. **Telegram**: 각 프로젝트는 독립 Bot Token 사용. 충돌 없음.

### Git Commit Convention

```
Add <feature> / Fix <bug> / Update <component> / Refactor <module>
```

## 상세 문서

- [프로젝트 상세](docs/PROJECTS.md) - 각 프로젝트 실행 방법, 기능 설명
- [환경변수](docs/ENVIRONMENT.md) - 프로젝트별 .env 설정
- [트러블슈팅](docs/TROUBLESHOOTING.md) - 봇 중복 실행, Telegram 에러, API Rate Limit
