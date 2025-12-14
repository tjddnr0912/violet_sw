#!/bin/bash
# ==============================================
# Start All Bots - iTerm2 Multi-Tab Launcher
# ==============================================
# Opens a new iTerm2 window with 3 tabs:
#   Tab 1: Trading Bot (Ver3 CLI)
#   Tab 2: News Bot (Scheduled)
#   Tab 3: Telegram Gemini Bot
# ==============================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Script paths
TRADING_BOT="$SCRIPT_DIR/005_money/scripts/run_v3_cli.sh"
NEWS_BOT="$SCRIPT_DIR/006_auto_bot/run_scheduled.sh"
TELEGRAM_BOT="$SCRIPT_DIR/006_auto_bot/run_telegram_bot.sh"

# Check if scripts exist
for script in "$TRADING_BOT" "$NEWS_BOT" "$TELEGRAM_BOT"; do
    if [[ ! -f "$script" ]]; then
        echo "Error: Script not found: $script"
        exit 1
    fi
done

# Launch iTerm2 with tabs
osascript <<EOF
tell application "iTerm2"
    activate

    -- Create new window with first tab (Trading Bot)
    create window with default profile
    tell current session of current window
        set name to "Trading Bot"
        write text "cd '$SCRIPT_DIR' && '$TRADING_BOT'"
    end tell

    -- Create second tab (News Bot)
    tell current window
        create tab with default profile
        tell current session
            set name to "News Bot"
            write text "cd '$SCRIPT_DIR' && '$NEWS_BOT'"
        end tell
    end tell

    -- Create third tab (Telegram Bot)
    tell current window
        create tab with default profile
        tell current session
            set name to "Telegram Bot"
            write text "cd '$SCRIPT_DIR' && '$TELEGRAM_BOT'"
        end tell
    end tell

    -- Select first tab
    tell current window
        select first tab
    end tell
end tell
EOF

echo "All bots started in iTerm2 tabs!"
