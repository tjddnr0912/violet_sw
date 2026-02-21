# Troubleshooting

## 봇 중복 실행 확인

```bash
ps aux | grep "ver3/run_cli.py"      # 005_money
ps aux | grep "main.py"              # 006_auto_bot (뉴스봇)
ps aux | grep "weekly_sector_bot.py" # 006_auto_bot (섹터봇)
ps aux | grep "run_daemon.py"        # 007_stock_trade
```

## Telegram Conflict 에러

같은 Bot Token을 여러 프로세스가 사용할 때 발생.

```bash
pkill -f "run_cli.py"
./scripts/run_v3_watchdog.sh
```

## API Rate Limit

| Project | API | Limit |
|---------|-----|-------|
| 005_money | Bithumb | 제한 없음 (적정 사용) |
| 007_stock_trade | KIS 모의투자 | 5건/초 |
| 007_stock_trade | KIS 실전투자 | 20건/초 |

## 프로젝트별 트러블슈팅

각 프로젝트의 `docs/TROUBLESHOOTING.md` 참조:
- [005_money](../005_money/docs/TROUBLESHOOTING.md) - Hang 방지 시스템, Timeout 레이어
- [006_auto_bot](../006_auto_bot/docs/TROUBLESHOOTING.md) - Gemini/Blogger/Claude 에러
- [007_stock_trade](../007_stock_trade/docs/TROUBLESHOOTING.md) - T+2 결제, pykrx, 리밸런싱
