# Production Systems 상세

## 005_money - Bithumb Trading Bot

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

**Telegram:** `/status`, `/positions`, `/factors`, `/close <COIN>`, `/stop`

---

## 006_auto_bot - News Automation Bot

| Item | Value |
|------|-------|
| AI | Gemini + Claude (HTML 변환) |
| Output | Blogger (7개 블로그 지원) |
| Schedule | Daily 07:00, Weekly 일요일, Monthly 1일 |

**실행:**
```bash
cd 006_auto_bot
./run_scheduled.sh           # 뉴스봇 스케줄 모드
./run_telegram_bot.sh        # Telegram Gemini Q&A (블로그 선택)
./run_weekly_sector.sh       # 주간 섹터 투자정보 (일요일 13:00~18:00)
```

**Telegram Gemini Bot:**
- Inline Keyboard로 블로그 선택 → Dual 업로드 (Default + 선택 블로그)
- 최소 글자 수: Gemini 1500자+, Claude HTML 1000자+

**Weekly Sector Bot:**
- 일요일 11개 섹터별 자동 수집/분석 → OgusInvest 블로그
- `--resume`로 중단 지점부터 재개

---

## 007_stock_trade - KIS Quant Trading (Korea)

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

**Telegram:** `/start_trading`, `/stop_trading`, `/status`, `/positions`, `/run_screening`, `/set_target N`

**Daily Schedule:** 08:30 스크리닝 → 09:00 주문 → 5분 모니터링 → 15:20 리포트

---

## 008_stock_trade_us - KIS Quant Trading (US)

007_stock_trade 기반 미국 주식 버전. 동일 아키텍처, S&P500 유니버스.

**미국 전용:** `us_quant_engine.py`, `us_screener.py`, `us_universe.py`, `kis_us_client.py`

---

## 009_dashboard - Trading Dashboard (Flask)

005_money + 007_stock_trade 데이터 통합 조회. Port 5001.

v1 API (인증 없음) + v2 API (API Key, 12개 엔드포인트).

---

## 010_ios_dashboard - Trading Dashboard (iOS)

SwiftUI MVVM. 009의 v2 API 소비. xcodegen 빌드.

URL Scheme: `tradingdashboard://tab/{dashboard,crypto,stock}`

---

## Lab & Study

| Directory | Description | Language |
|-----------|-------------|----------|
| 000_personal_lib_code | Python 유틸리티 | Python |
| 001_coding_test_question | 코딩 테스트 풀이 | Python |
| 002_study_swift | Swift/iOS 학습 | Swift |
| 003_script | 유틸리티 스크립트 | Bash/Verilog |
| 004_hacker_rank | HackerRank 풀이 | Python |

## Tech Stack

| Project | Language | API | Notification | Data |
|---------|----------|-----|--------------|------|
| 005_money | Python 3.13+ | Bithumb REST | Telegram | JSON |
| 006_auto_bot | Python 3.11+ | Gemini, Blogger | Telegram | Markdown |
| 007_stock_trade | Python 3.11+ | KIS REST/WS | Telegram | JSON |
| 008_stock_trade_us | Python 3.11+ | KIS REST/WS | Telegram | JSON |
| 009_dashboard | Python 3.11+ | Flask REST | - | 005/007 JSON 참조 |
| 010_ios_dashboard | Swift | 009 v2 API | - | UserDefaults |

## Documentation Index

| Project | Main Doc | Detail Docs |
|---------|----------|-------------|
| 005_money | `CLAUDE.md` | `docs/ARCHITECTURE.md`, `docs/TROUBLESHOOTING.md`, `docs/CHANGELOG.md` |
| 006_auto_bot | `CLAUDE.md` | `docs/ARCHITECTURE.md`, `docs/SECTOR_BOT.md`, `docs/TELEGRAM_BOT.md`, `docs/TROUBLESHOOTING.md` |
| 007_stock_trade | `CLAUDE.md` | `docs/ARCHITECTURE.md`, `docs/TROUBLESHOOTING.md`, `docs/CHANGELOG.md` |
| 008_stock_trade_us | `CLAUDE.md` | `docs/ARCHITECTURE.md`, `docs/COMMANDS.md` |
| 009_dashboard | `CLAUDE.md` | `docs/API_REFERENCE.md`, `docs/ARCHITECTURE.md`, `docs/STATUS.md` |
| 010_ios_dashboard | `CLAUDE.md` | `docs/ARCHITECTURE.md`, `docs/VIEWS.md` |
