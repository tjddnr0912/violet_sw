# CLAUDE.md - violet_sw

멀티 프로젝트 개발 및 운영 저장소. 코딩 학습부터 실전 자동매매 시스템까지 포함.

## Repository Overview

```
violet_sw/
├── Production Systems (상시 운영)
│   ├── 005_money/          # 암호화폐 트레이딩 봇 (Bithumb)
│   ├── 006_auto_bot/       # 뉴스 자동화 봇 (RSS→AI→Blogger)
│   ├── 007_stock_trade/    # 주식 퀀트 자동매매 (한국, KIS API)
│   └── 008_stock_trade_us/ # 주식 퀀트 자동매매 (미국, KIS API)
│
├── Lab & Study
│   ├── 000_personal_lib_code/     # Python 유틸리티
│   ├── 001_coding_test_question/  # 코딩 테스트 풀이
│   ├── 002_study_swift/           # Swift/iOS 학습
│   ├── 003_script/                # 유틸리티 스크립트
│   └── 004_hacker_rank/           # HackerRank 풀이
│
├── start_all_bots.sh       # 전체 봇 일괄 실행
└── CLAUDE.md               # 이 파일
```

## Production Systems

### Quick Start (전체 봇 실행)

```bash
./start_all_bots.sh    # iTerm2에서 4개 탭으로 모든 봇 실행
```

| Tab | Project | Script | Description |
|-----|---------|--------|-------------|
| 1 | 005_money | `run_v3_watchdog.sh` | 암호화폐 트레이딩 (Watchdog 모드) |
| 2 | 006_auto_bot | `run_scheduled.sh` | 뉴스봇 (일간/주간/월간 스케줄) |
| 3 | 006_auto_bot | `run_telegram_bot.sh` | Telegram Gemini Q&A 봇 |
| 4 | 007_stock_trade | `run_quant.sh daemon` | 주식 퀀트 데몬 |

---

### 005_money - Bithumb Trading Bot

| Item | Value |
|------|-------|
| Exchange | Bithumb |
| Language | Python 3.13+ |
| Strategy | Portfolio Multi-Coin (Ver3) |
| Interval | 15분 |

**실행:**
```bash
cd 005_money
./scripts/run_v3_watchdog.sh   # 권장 (자동 재시작 + hang 감지)
./scripts/run_v3_cli.sh        # 단순 CLI
./scripts/run_v3_gui.sh        # GUI 모드
```

**Telegram 명령어:** `/status`, `/positions`, `/factors`, `/close <COIN>`, `/stop`

**상세 문서:** `005_money/CLAUDE.md`

---

### 006_auto_bot - News Automation Bot

| Item | Value |
|------|-------|
| AI | Gemini (gemini-2.5-flash) |
| Output | Blogger |
| Schedule | Daily 07:00, Weekly 일요일, Monthly 1일 |

**실행:**
```bash
cd 006_auto_bot
./run_scheduled.sh           # 스케줄 모드
./run_telegram_bot.sh        # Telegram Gemini Q&A
```

**Data Flow:** RSS Feed → Gemini 요약 → Markdown → Blogger → Telegram 알림

**상세 문서:** `006_auto_bot/CLAUDE.md`

---

### 007_stock_trade - KIS Quant Trading (Korea)

| Item | Value |
|------|-------|
| Broker | 한국투자증권 (KIS API) |
| Universe | KOSPI200 |
| Strategy | Multi-Factor (모멘텀 20% + 단기모멘텀 10% + 저변동성 50%) |
| Target | 15 종목 |

**실행:**
```bash
cd 007_stock_trade
./run_quant.sh daemon        # 통합 데몬 (권장)
./run_quant.sh screen        # 스크리닝만
./run_quant.sh backtest      # 백테스트
```

**Telegram 명령어:** `/start_trading`, `/stop_trading`, `/status`, `/positions`, `/run_screening`, `/set_target N`

**Daily Schedule:**
- 08:30 장 전 스크리닝
- 09:00 주문 실행
- 5분마다 포지션 모니터링
- 15:20 일일 리포트

**상세 문서:** `007_stock_trade/CLAUDE.md`

---

### 008_stock_trade_us - KIS Quant Trading (US)

007_stock_trade와 동일한 아키텍처의 미국 주식 버전.

**상세 문서:** `008_stock_trade_us/CLAUDE.md`

---

## Lab & Study Projects

| Directory | Description | Language | Status |
|-----------|-------------|----------|--------|
| 000_personal_lib_code | 재사용 가능한 유틸리티 | Python | Archive |
| 001_coding_test_question | 코딩 테스트 문제 풀이 | Python | Archive |
| 002_study_swift | Swift/iOS 학습 자료 | Swift | Lab |
| 003_script | 유틸리티 스크립트 | Bash/Verilog | Archive |
| 004_hacker_rank | HackerRank 문제 풀이 | Python | Archive |

---

## Architecture Summary

### Tech Stack by Project

| Project | Language | API | Notification | Data Storage |
|---------|----------|-----|--------------|--------------|
| 005_money | Python 3.13+ | Bithumb REST | Telegram | JSON files |
| 006_auto_bot | Python 3.11+ | Gemini, Blogger | Telegram | Markdown files |
| 007_stock_trade | Python 3.11+ | KIS REST/WebSocket | Telegram | JSON files |
| 008_stock_trade_us | Python 3.11+ | KIS REST/WebSocket | Telegram | JSON files |

### Telegram Bot Tokens

각 프로젝트는 **독립적인 Telegram Bot Token** 사용. 충돌 없음.

| Project | Bot Purpose |
|---------|-------------|
| 005_money | 암호화폐 트레이딩 알림/제어 |
| 006_auto_bot | 뉴스 알림 + Gemini Q&A |
| 007_stock_trade | 주식 트레이딩 알림/제어 |
| 008_stock_trade_us | 미국주식 트레이딩 알림/제어 |

---

## Environment Variables

각 프로젝트별 `.env` 파일 필요. **절대 Git에 커밋하지 말 것.**

### 005_money/.env
```bash
BITHUMB_API_KEY=
BITHUMB_SECRET_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

### 006_auto_bot/001_code/.env
```bash
GEMINI_API_KEY=
BLOGGER_BLOG_ID=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

### 007_stock_trade/.env & 008_stock_trade_us/.env
```bash
KIS_APP_KEY=
KIS_APP_SECRET=
KIS_ACCOUNT_NO=
TRADING_MODE=VIRTUAL  # or REAL
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## Development Guidelines

### Code Modification Rules

1. **프로젝트 경계 존중**: 각 프로젝트는 독립적. 다른 프로젝트 코드 참조 금지.
2. **005_money**: ver3가 유일한 프로덕션 버전. ver3/ 디렉토리에서 작업.
3. **Shared Lib 수정 시**: 005_money의 `lib/` 수정 시 ver3 호환성 테스트.
4. **설정 파일 동기화**: 007/008의 `system_config.json`은 Telegram 명령으로 변경됨.

### File Creation Policy

- 새 파일 생성 최소화. 기존 파일 수정 우선.
- `.md` 문서 파일은 명시적 요청 시에만 생성.
- 테스트 파일은 `tests/` 디렉토리에만 생성.

### Git Commit Convention

```bash
git commit -m "Add <feature>"      # 새 기능
git commit -m "Fix <bug>"          # 버그 수정
git commit -m "Update <component>" # 기존 기능 개선
git commit -m "Refactor <module>"  # 리팩토링
```

---

## Troubleshooting

### 봇 중복 실행 확인

```bash
# 각 프로젝트별 프로세스 확인
ps aux | grep "ver3/run_cli.py"      # 005_money
ps aux | grep "main.py"              # 006_auto_bot
ps aux | grep "run_daemon.py"        # 007_stock_trade
```

### Telegram Conflict 에러

같은 Bot Token을 여러 프로세스가 사용할 때 발생.

```bash
# 해당 프로젝트 프로세스 모두 종료 후 재시작
pkill -f "run_cli.py"
./scripts/run_v3_watchdog.sh
```

### API Rate Limit

| Project | API | Limit |
|---------|-----|-------|
| 005_money | Bithumb | 제한 없음 (적정 사용) |
| 007_stock_trade | KIS 모의투자 | 5건/초 |
| 007_stock_trade | KIS 실전투자 | 20건/초 |

---

## Project Documentation Index

| Project | Main Doc | Detail Docs |
|---------|----------|-------------|
| 005_money | `CLAUDE.md` | `.claude/rules/*.md` |
| 006_auto_bot | `CLAUDE.md` | - |
| 007_stock_trade | `CLAUDE.md` | `.claude/rules/*.md` |
| 008_stock_trade_us | `CLAUDE.md` | `.claude/rules/*.md` |

각 프로젝트 작업 시 해당 프로젝트의 CLAUDE.md를 먼저 참조할 것.
