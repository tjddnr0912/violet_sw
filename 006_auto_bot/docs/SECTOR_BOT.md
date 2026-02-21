# Weekly Sector Bot

매주 일요일 11개 섹터별 투자정보를 자동 수집/분석하여 OgusInvest 블로그에 업로드.

## 실행

```bash
python weekly_sector_bot.py           # 스케줄 모드 (일요일 자동)
python weekly_sector_bot.py --once    # 즉시 전체 실행
python weekly_sector_bot.py --resume  # 중단 후 재개
python weekly_sector_bot.py --sector 1  # 특정 섹터만 (1-11)
python weekly_sector_bot.py --test    # 테스트 (업로드 스킵)
python weekly_sector_bot.py --status  # 상태 확인
python weekly_sector_bot.py --reset   # 상태 초기화
```

## 11개 섹터

| ID | 섹터 | 영문명 | 시간 |
|----|------|--------|------|
| 1 | AI/양자컴퓨터 | ai_quantum | 13:00 |
| 2 | 금융 | finance | 13:30 |
| 3 | 조선/항공/우주 | shipbuilding_aerospace | 14:00 |
| 4 | 에너지 | energy | 14:30 |
| 5 | 바이오 | bio | 15:00 |
| 6 | IT/통신/Cloud/DC | it_cloud | 15:30 |
| 7 | 주식시장 | stock_market | 16:00 |
| 8 | 반도체 | semiconductor | 16:30 |
| 9 | 자동차/배터리/로봇 | auto_battery_robot | 17:00 |
| 10 | 리츠(REITs) | reits | 17:30 |
| 11 | 필수 소비재 | consumer_staples | 18:00 |

## 섹터별 분석 초점

| ID | 분석 초점 |
|----|-----------|
| 1 | AI 기술발표/벤치마크, MCP/Skills 에이전트, 양자컴퓨팅, AI 반도체 |
| 2 | 기준금리/통화정책, 월가 전망, CPI/인플레이션, 고용지표, 귀금속 |
| 3 | 조선 수주, Boeing/Airbus, SpaceX/위성, 방산 수출 |
| 4 | 신재생에너지, 원유 WTI/Brent, 천연가스, 원자력/SMR, ESS |
| 5 | FDA 승인, 임상시험, 유전자치료/CRISPR, 바이오텍 M&A/IPO |
| 6 | AWS/Azure/GCP, 데이터센터, 5G/통신, 사이버보안, SaaS |
| 7 | S&P500/Nasdaq 전망, 지정학 리스크, 무역분쟁, VIX |
| 8 | 파운드리 (TSMC, 삼성), 장비 (ASML), Fabless (NVIDIA, AMD), 메모리 |
| 9 | EV (Tesla, BYD), 배터리 (LG, 삼성SDI, CATL), 자율주행, 휴머노이드 |
| 10 | 리츠 ETF 수급, FTSE NAREIT, 배당/자산매매, 경기 사이클 |
| 11 | 종목/ETF 추천 (P&G, Coca-Cola, XLP), 경기 사이클, 주가 전망 |

## 파일 저장 구조

```
004_Sector_Weekly/YYYYMMDD/
├── sector_01_ai_quantum.md
├── sector_02_finance.md
├── ...
└── sector_11_consumer_staples.md
```

## 블로그 업로드

- **블로그**: OgusInvest (Blog ID: `9115231004981625966`)
- **제목**: `{날짜} {N}주차 {섹터명} 투자정보`
- **라벨**: `[섹터명, 주간, 투자정보]`

## State Management

- **상태 파일**: `sector_bot/state.json`
- **주차 키**: YYYY-WW 형식 (같은 주 내에서만 재개 가능)
- **저장 정보**: 완료 섹터, 실패 섹터, 블로그 URL

## 설정 (sector_bot/config.py)

| Setting | Value | Description |
|---------|-------|-------------|
| `GEMINI_MODEL` | gemini-3-flash-preview | Gemini 모델 |
| `MAX_RETRIES` | 3 | API 호출 최대 재시도 |
| `RETRY_DELAY` | 60초 | 재시도 대기 (지수 백오프) |
| `CLAUDE_TIMEOUT` | 900초 (15분) | Claude CLI 타임아웃 |
| `SCHEDULE_DAY` | 6 (Sunday) | 스케줄 실행 요일 |

## 에러 처리

| 에러 | 처리 |
|------|------|
| Gemini Search 실패 | 3회 재시도 (60초→120초→240초 지수 백오프) |
| Gemini Safety Filter | BLOCK_NONE 설정으로 비활성화 |
| Claude CLI 타임아웃 | 15분 후 마크다운 폴백 |
| 네트워크 에러 | 지수 백오프 재시도 |
