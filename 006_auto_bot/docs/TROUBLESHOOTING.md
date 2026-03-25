# Troubleshooting

| Error | Solution |
|-------|----------|
| ModuleNotFoundError | `pip install -r requirements.txt` |
| Gemini API error | Check `GEMINI_API_KEY` |
| Blogger OAuth | Delete `credentials/blogger_token.pkl` |
| Telegram HTML parse error | Plain text fallback 자동 적용 |
| Claude CLI not found | `pip install claude-cli` 또는 PATH 확인 |
| Claude CLI empty response | API 일시 장애 — 자동 재시도 (3회, 30초 간격) |
| Blog selection timeout | `BLOG_SELECTION_TIMEOUT` 값 조정 (기본 180초) |
| Sector bot resume 실패 | 다른 주에 시작 - `--reset` 후 `--once` 실행 |
| Gemini Search 실패 | API 키 확인, 재시도 자동 (3회, 지수 백오프) |
| Sector state 손상 | `python weekly_sector_bot.py --reset` |

## 로그 파일

```
logs/
├── investment_bot_YYYYMMDD.log  # 통합 오케스트레이터
├── news_bot_YYYYMMDD.log        # 뉴스봇
├── buffett_bot_YYYYMMDD.log     # 버핏봇
└── sector_bot_YYYYMMDD.log      # 섹터봇
```
