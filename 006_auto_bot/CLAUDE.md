# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated news aggregation, AI summarization, and blog posting bot. Collects news from RSS feeds, summarizes using Google Gemini AI, and posts to Google Blogger.

## Development Commands

```bash
# Setup
cd 006_auto_bot/001_code
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Configure API keys

# Run news bot (one-time)
python main.py --version v3 --mode once

# Run news bot (scheduled daily at configured time)
python main.py --version v3 --mode scheduled

# Test mode (no saving/uploading)
python main.py --version v3 --test

# Run Telegram Gemini chatbot
python telegram_gemini_bot.py           # Production mode
python telegram_gemini_bot.py --test    # Skip blog upload

# Version selection
python main.py --version v1   # Global news (CNN, BBC, etc.)
python main.py --version v2   # Korean news by category
python main.py --version v3   # All categories (politics, economy, crypto, stocks, etc.)
```

## Architecture

### Version System (`v1/`, `v2/`, `v3/`)
Each version contains its own modules that are dynamically imported by `main.py`:
- `config.py` - Version-specific configuration and RSS sources
- `news_aggregator.py` - RSS feed parsing and news selection
- `ai_summarizer.py` - Gemini AI summarization
- `markdown_writer.py` - Output file generation

**Version Differences:**
- **v1**: Global English news sources (CNN, BBC, Reuters, etc.)
- **v2**: Korean news sources with category selection
- **v3**: All Korean categories including stocks/crypto + Gemini blog summary generation

### Core Modules (root level)
- `main.py` - Entry point, orchestrates workflow: fetch → summarize → save → upload → notify
- `telegram_gemini_bot.py` - Telegram bot that accepts questions, runs Gemini CLI, and posts answers to Blogger
- `telegram_notifier.py` - Send notifications via Telegram Bot API
- `blogger_uploader.py` - Google Blogger API v3 integration (OAuth2-based)

### Data Flow (v3)
1. `NewsAggregator` fetches RSS feeds from 8 categories
2. `MarkdownWriter.save_raw_news_by_category()` saves organized raw news
3. `AISummarizer.create_blog_summary()` generates AI summary via Gemini
4. `BloggerUploader` posts to blog
5. `TelegramNotifier` sends summary notification

## Configuration

### Environment Variables (`.env`)
```
GEMINI_API_KEY=your_key          # Required
GEMINI_MODEL=gemini-2.5-flash-lite
NEWS_HOURS_LIMIT=24              # Hours to look back for news

# Google Blogger (API-based)
BLOGGER_ENABLED=false
BLOGGER_BLOG_ID=your_blog_id
BLOGGER_CREDENTIALS_PATH=./credentials/blogger_credentials.json
BLOGGER_TOKEN_PATH=./credentials/blogger_token.pkl
BLOGGER_LABELS=뉴스,AI요약,자동화
BLOGGER_IS_DRAFT=false

# Telegram notifications
TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### Key Config Settings (`v3/config.py`)
- `NEWS_SOURCES_BY_CATEGORY` - RSS feeds organized by category
- `MAX_NEWS_COUNT` - Number of articles to fetch (default: 50 for v3)
- `POSTING_TIME` - Daily scheduled time (HH:MM)
- `OUTPUT_DIR` - Where markdown files are saved (`../004_News_paper`)

## Directory Structure

```
001_code/
├── main.py                      # Entry point
├── telegram_gemini_bot.py       # Telegram chatbot
├── telegram_notifier.py         # Telegram notifications
├── blogger_uploader.py          # Google Blogger API
├── config.py                    # Legacy config (use v*/config.py)
├── v1/, v2/, v3/               # Version-specific modules
├── credentials/                 # Google OAuth tokens
└── logs/                        # Daily log files
```

## Key Patterns

- **Dynamic version loading**: `importlib.import_module(f'{version}.config')` allows switching between v1/v2/v3
- **Context manager pattern**: Uploaders use `with` statement for cleanup
- **Category mapping**: RSS URLs mapped to categories via `CATEGORY_MAP` dict
- **Graceful degradation**: Blogger/Telegram features toggle independently

## Debugging

**ModuleNotFoundError**: Activate venv and `pip install -r requirements.txt`

**Gemini API errors**: Check `GEMINI_API_KEY` in `.env`, verify model name exists

**Blogger OAuth**: Delete `credentials/blogger_token.pkl` to trigger re-authentication

**Telegram bot not responding**: Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`, test with `python telegram_notifier.py`
