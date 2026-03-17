#!/bin/bash
# ==============================================
# Start All Bots - cmux Workspace Launcher
# ==============================================
# Creates 6 cmux workspaces (one per bot):
#   1: Trading Bot (Ver3 Watchdog - Auto-restart + Hang Detection)
#   2: Telegram Gemini Bot
#   3: Quant Trading Daemon (주식 자동매매)
#   4: Investment Bot (뉴스봇 + 버핏봇 + 섹터봇 통합)
#   5: Dashboard Server (Flask, port 5001)
#   6: Stock Dashboard (FastAPI, port 5002)
#
# Usage:
#   ./start_all_bots_cmux.sh
#
# Prerequisites:
#   - cmux must be installed and running
#   - CLI symlink: sudo ln -sf "/Applications/cmux.app/Contents/Resources/bin/cmux" /usr/local/bin/cmux
# ==============================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Script paths
TRADING_BOT="$SCRIPT_DIR/005_money/scripts/run_v3_watchdog.sh"
TELEGRAM_BOT="$SCRIPT_DIR/006_auto_bot/run_telegram_bot.sh"
QUANT_DAEMON="$SCRIPT_DIR/007_stock_trade/run_quant.sh"
INVESTMENT_BOT="$SCRIPT_DIR/006_auto_bot/run_investment_bot.sh"
DASHBOARD="$SCRIPT_DIR/009_dashboard"
STOCK_DASHBOARD="$SCRIPT_DIR/012_stock_dashboard"

# Check if cmux is available
if ! command -v cmux &>/dev/null; then
    echo "Error: cmux CLI not found."
    echo "Install symlink: sudo ln -sf \"/Applications/cmux.app/Contents/Resources/bin/cmux\" /usr/local/bin/cmux"
    exit 1
fi

# Check if cmux is running
if ! cmux ping &>/dev/null; then
    echo "Error: cmux is not running. Please start cmux first."
    exit 1
fi

# Check if scripts exist
for script in "$TRADING_BOT" "$TELEGRAM_BOT" "$QUANT_DAEMON" "$INVESTMENT_BOT"; do
    if [[ ! -f "$script" ]]; then
        echo "Error: Script not found: $script"
        exit 1
    fi
done

# Helper: create a new workspace, capture its workspace ID, and send a command
# cmux new-workspace returns: "OK workspace:N"
create_workspace_and_run() {
    local name="$1"
    local cmd="$2"

    # Create new workspace and capture output
    local output
    output=$(cmux new-workspace 2>&1)

    # Parse workspace reference from output (format: "OK workspace:N")
    local ws_ref
    ws_ref=$(echo "$output" | grep -oE 'workspace:[0-9]+' | head -1)

    # Small delay to let workspace initialize
    sleep 0.5

    # Set tab title via terminal escape sequence + run command
    if [[ -n "$ws_ref" ]]; then
        cmux send --workspace "$ws_ref" "printf '\\e]0;${name}\\a' && ${cmd}\n"
    else
        echo "    Error: Could not create workspace for '$name' (output: $output)"
    fi

    sleep 0.3
}

echo "Starting all bots in cmux..."

# --- Workspace 1: Trading Bot ---
echo "  [1/6] Trading Bot..."
create_workspace_and_run "Trading Bot" "cd '$SCRIPT_DIR' && '$TRADING_BOT'"

# --- Workspace 2: Telegram Bot ---
echo "  [2/6] Telegram Bot..."
create_workspace_and_run "Telegram Bot" "cd '$SCRIPT_DIR' && '$TELEGRAM_BOT'"

# --- Workspace 3: Quant Trading Daemon ---
echo "  [3/6] Quant Daemon..."
create_workspace_and_run "Quant Daemon" "cd '$SCRIPT_DIR/007_stock_trade' && '$QUANT_DAEMON' daemon --no-dry-run"

# --- Workspace 4: Investment Bot ---
echo "  [4/6] Investment Bot..."
create_workspace_and_run "Investment Bot" "cd '$SCRIPT_DIR' && '$INVESTMENT_BOT'"

# --- Workspace 5: Dashboard Server ---
echo "  [5/6] Dashboard..."
create_workspace_and_run "Dashboard" "cd '$DASHBOARD' && source venv/bin/activate && python app.py"

# --- Workspace 6: Stock Dashboard ---
echo "  [6/6] Stock Dashboard..."
create_workspace_and_run "Stock Dashboard" "cd '$STOCK_DASHBOARD' && './run_watchdog.sh'"

echo ""
echo "All bots started in cmux! (6 workspaces including Dashboards on ports 5001/5002)"
echo "Use 'cmux list-workspaces' to see all running workspaces."
