#!/bin/bash
# ==============================================
# Start All Bots - iTerm2 Multi-Tab Launcher
# ==============================================
# Opens a new iTerm2 window with 4 tabs:
#   Tab 1: Trading Bot (Ver3 Watchdog - Auto-restart + Hang Detection)
#   Tab 2: News Bot (Scheduled)
#   Tab 3: Telegram Gemini Bot
#   Tab 4: Quant Trading Daemon (주식 자동매매)
#
# Watchdog Features:
#   - Auto-restart on crash
#   - Hang detection: kills bot if no log activity for 10 min
#   - Grace period: 2 min after start before hang check
# ==============================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Script paths
TRADING_BOT="$SCRIPT_DIR/005_money/scripts/run_v3_watchdog.sh"
NEWS_BOT="$SCRIPT_DIR/006_auto_bot/run_scheduled.sh"
TELEGRAM_BOT="$SCRIPT_DIR/006_auto_bot/run_telegram_bot.sh"
QUANT_DAEMON="$SCRIPT_DIR/007_stock_trade/run_quant.sh"

# Check if scripts exist
for script in "$TRADING_BOT" "$NEWS_BOT" "$TELEGRAM_BOT" "$QUANT_DAEMON"; do
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

    -- Create fourth tab (Quant Trading Daemon)
    tell current window
        create tab with default profile
        tell current session
            set name to "Quant Daemon"
            write text "cd '$SCRIPT_DIR/007_stock_trade' && '$QUANT_DAEMON' daemon --no-dry-run"
        end tell
    end tell

    -- Select first tab
    tell current window
        select first tab
    end tell
end tell
EOF

echo "All bots started in iTerm2 tabs!"
