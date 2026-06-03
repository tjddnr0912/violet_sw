# 006_auto_bot 명령 카탈로그

## 통합 실행

```bash
cd 006_auto_bot/001_code
source .venv/bin/activate
```

| 명령 | 동작 |
|------|------|
| `python investment_bot.py` | 통합 스케줄러 (뉴스+버핏+섹터+부동산 자동) — **권장** |
| `python telegram_gemini_bot.py` | Telegram Gemini Q&A 봇 (별도 프로세스) |

## 개별 봇 즉시 실행

| 명령 | 동작 |
|------|------|
| `python main.py --mode once` | 뉴스봇 일간 즉시 1회 |
| `python main.py --mode weekly` | 뉴스봇 주간 1회 |
| `python main.py --mode monthly` | 뉴스봇 월간 1회 |
| `python buffett_bot.py --once` | 버핏봇 즉시 1회 |
| `python weekly_sector_bot.py --once` | 섹터봇 11개 섹터 즉시 |
| `python weekly_sector_bot.py --comprehensive` | 섹터 종합 투자 평가 보고서 |
| `python weekly_sector_bot.py --reset` | 섹터봇 state 초기화 (resume 실패 복구용) |
| `python weekly_realestate_bot.py --once [--test]` | 부동산봇 전국 디제스트 즉시 (test=Blogger/HTML 스킵) |
| `python weekly_realestate_bot.py --backfill-all 36` | 4종(아파트·오피스텔 × 매매·전월세) 119시군구 백필 |

## 자동 스케줄

| 봇 | 일정 |
|----|------|
| 뉴스봇 일간 | 매일 06:00 |
| 뉴스봇 주간 | 일요일 07:00 |
| 뉴스봇 월간 | 1일 07:30 |
| 버핏봇 | 월~금 06:30 |
| 섹터봇 | 일요일 13:00~18:00 (11개 섹터) |
| 섹터 종합 | 일요일 19:00 |
| 부동산봇 | 토 01:00 (전국 119시군구 주간 디제스트) |

## Telegram Gemini Q&A 봇

| 입력 | 동작 |
|------|------|
| 평문 메시지 | **Deep research** (default) — multi-round Gemini × Claude 5차원 검증 |
| `/quick <질문>` | 단발 모드 (Gemini 1회 호출, 빠른 응답) |
| `/help` | 도움말 |
| `/status` | 봇 상태 |

`/quick` opt-out 패턴: 평문이 default deep research, 빠른 답이 필요하면 `/quick`.

## 디버깅 명령

```bash
# Gemini API 키 확인
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(bool(os.getenv('GEMINI_API_KEY')))"

# Claude CLI 확인
echo "test" | claude -p "echo back"

# Blogger 인증 재발급
rm credentials/blogger_token.pkl
python news_bot/blogger_uploader.py --auth
```

## 통합 스모크 테스트

```bash
# Live integration test (env-gated)
RUN_LIVE_RESEARCH_TEST=1 pytest tests/integration/test_run_research_live.py
```

## 로그 명령

```bash
tail -f logs/investment_bot_$(date +%Y%m%d).log    # 통합 오케스트레이터
tail -f logs/sector_bot_$(date +%Y%m%d).log        # 섹터봇
grep -i "error\|429\|503" logs/*_$(date +%Y%m%d).log    # API 에러
```

## 시그널 처리

| 시그널 | 동작 |
|--------|------|
| `SIGTERM` | graceful shutdown (진행 중 업로드 finalize) |
| `SIGINT` (Ctrl+C) | 동일 |
| `SIGKILL` | 즉시 종료 — 진행 중 sector 분석은 다음 실행에서 resume |
