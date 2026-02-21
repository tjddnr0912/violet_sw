# Environment Variables

각 프로젝트별 `.env` 파일 필요. **절대 Git에 커밋하지 말 것.**

## 005_money/.env

```bash
BITHUMB_API_KEY=
BITHUMB_SECRET_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

## 006_auto_bot/001_code/.env

```bash
GEMINI_API_KEY=
BLOGGER_BLOG_ID=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Blog Selection (Telegram Gemini Bot)
BLOG_LIST='[{"key":"...","id":"...","name":"..."}, ...]'
DEFAULT_BLOG=brave_ogu
BLOG_SELECTION_TIMEOUT=180

# Weekly Sector Bot
SECTOR_BLOGGER_BLOG_ID=9115231004981625966  # OgusInvest
SECTOR_GEMINI_MODEL=gemini-3-flash-preview
```

## 007_stock_trade/.env & 008_stock_trade_us/.env

```bash
KIS_APP_KEY=
KIS_APP_SECRET=
KIS_ACCOUNT_NO=
TRADING_MODE=VIRTUAL  # or REAL
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

## 009_dashboard/.env

```bash
DASHBOARD_API_KEY=    # 비어있으면 인증 비활성화
FLASK_DEBUG=false
```

## Telegram Bot Tokens

각 프로젝트는 **독립적인 Telegram Bot Token** 사용. 충돌 없음.

| Project | Bot Purpose |
|---------|-------------|
| 005_money | 암호화폐 트레이딩 알림/제어 |
| 006_auto_bot | 뉴스 알림 + Gemini Q&A |
| 007_stock_trade | 주식 트레이딩 알림/제어 |
| 008_stock_trade_us | 미국주식 트레이딩 알림/제어 |
