#!/bin/bash
# ==============================================
# Start All Bots - iTerm2 Multi-Tab Launcher
# ==============================================
# Opens a new iTerm2 window with 5 tabs:
#   Tab 1: Trading Bot (Ver3 Watchdog - Auto-restart + Hang Detection)
#   Tab 2: Telegram Gemini Bot
#   Tab 3: Quant Trading Daemon (주식 자동매매)
#   Tab 4: Investment Bot (뉴스봇 + 버핏봇 + 섹터봇 통합)
#   Tab 5: Casper Bot (TQQQ/SQQQ ORB+FVG, R:R 1:3, Telegram alerts via .env)
#   (Disabled) Tab 6: Dashboard Server (Flask, port 5001)
#   (Disabled) Tab 7: Stock Dashboard (FastAPI, port 5002)
#
# Watchdog Features:
#   - Auto-restart on crash
#   - Hang detection: kills bot if no log activity for 10 min
#   - Grace period: 2 min after start before hang check
#
# Telegram alerts:
#   - Each bot reads its own TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID from
#     <project>/.env. Casper shares 008's keys (set in 014_casper/.env).
# ==============================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Script paths
TRADING_BOT="$SCRIPT_DIR/005_money/scripts/run_v3_watchdog.sh"
TELEGRAM_BOT="$SCRIPT_DIR/006_auto_bot/run_telegram_bot.sh"
QUANT_DAEMON="$SCRIPT_DIR/007_stock_trade/run_quant.sh"
INVESTMENT_BOT="$SCRIPT_DIR/006_auto_bot/run_investment_bot.sh"
CASPER_BOT="$SCRIPT_DIR/014_casper/run_casper.sh"
DASHBOARD="$SCRIPT_DIR/009_dashboard"
STOCK_DASHBOARD="$SCRIPT_DIR/012_stock_dashboard"

# Check if scripts exist
for script in "$TRADING_BOT" "$TELEGRAM_BOT" "$QUANT_DAEMON" "$INVESTMENT_BOT" "$CASPER_BOT"; do
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
        write text "echo -ne '\\\\e]0;Trading Bot\\\\a' && cd '$SCRIPT_DIR' && '$TRADING_BOT'"
    end tell

    -- Create second tab (Telegram Bot)
    tell current window
        create tab with default profile
        tell current session
            write text "echo -ne '\\\\e]0;Telegram Bot\\\\a' && cd '$SCRIPT_DIR' && '$TELEGRAM_BOT'"
        end tell
    end tell

    -- Create third tab (Quant Trading Daemon)
    tell current window
        create tab with default profile
        tell current session
            write text "echo -ne '\\\\e]0;Quant Daemon\\\\a' && cd '$SCRIPT_DIR/007_stock_trade' && '$QUANT_DAEMON' daemon --no-dry-run"
        end tell
    end tell

    -- Create fourth tab (Investment Bot: News + Buffett + Sector)
    tell current window
        create tab with default profile
        tell current session
            write text "echo -ne '\\\\e]0;Investment Bot\\\\a' && cd '$SCRIPT_DIR' && '$INVESTMENT_BOT'"
        end tell
    end tell

    -- Create fifth tab (Casper Bot: TQQQ/SQQQ ORB+FVG, --yes skips live confirmation)
    tell current window
        create tab with default profile
        tell current session
            write text "echo -ne '\\\\e]0;Casper Bot\\\\a' && cd '$SCRIPT_DIR/014_casper' && '$CASPER_BOT' start --yes"
        end tell
    end tell

    -- (Disabled) Create sixth tab (Dashboard Server)
    -- Uncomment to re-enable:
    -- tell current window
    --     create tab with default profile
    --     tell current session
    --         write text "echo -ne '\\\\e]0;Dashboard\\\\a' && cd '$DASHBOARD' && source venv/bin/activate && python app.py"
    --     end tell
    -- end tell

    -- (Disabled) Create seventh tab (Stock Dashboard)
    -- Uncomment to re-enable:
    -- tell current window
    --     create tab with default profile
    --     tell current session
    --         write text "echo -ne '\\\\e]0;Stock Dashboard\\\\a' && cd '$STOCK_DASHBOARD' && './run_watchdog.sh'"
    --     end tell
    -- end tell

    -- Select first tab
    tell current window
        select first tab
    end tell
end tell
EOF

echo "All bots started in iTerm2 tabs! (5 tabs)"
echo "  Tab 1: Trading Bot (005_money)"
echo "  Tab 2: Telegram Bot (006_auto_bot)"
echo "  Tab 3: Quant Daemon (007_stock_trade)"
echo "  Tab 4: Investment Bot (006_auto_bot — News+Buffett+Sector)"
echo "  Tab 5: Casper Bot (014_casper — TQQQ/SQQQ, Telegram via .env)"
