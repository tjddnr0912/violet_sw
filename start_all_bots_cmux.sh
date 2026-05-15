#!/bin/bash
# ==============================================
# Start All Bots - cmux Single Workspace Launcher
# ==============================================
# Creates 1 cmux workspace "running_machine" with 5 panes (2+2+1):
#
#   +-------------------+-------------------+
#   | Trading Bot       | Telegram Bot      |
#   +-------------------+-------------------+
#   | Quant Daemon      | Investment Bot    |
#   +-------------------+-------------------+
#   |     미장봇 (TQQQ/SQQQ + TG)       |
#   +---------------------------------------+
#
# (Disabled) Dashboard (5001), Stock Dashboard (5002)
#
# Telegram alerts:
#   Each bot reads its own TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID from
#   <project>/.env. Casper shares 008's keys (set in 014_casper/.env).
#   No CLI flag — purely env-driven; absent keys disable alerts silently.
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
# (Disabled) 005_money Trading Bot - commented out by user
# TRADING_BOT="$SCRIPT_DIR/005_money/scripts/run_v3_watchdog.sh"
TELEGRAM_BOT="$SCRIPT_DIR/006_auto_bot/run_telegram_bot.sh"
QUANT_DAEMON="$SCRIPT_DIR/007_stock_trade/run_quant.sh"
INVESTMENT_BOT="$SCRIPT_DIR/006_auto_bot/run_investment_bot.sh"
CASPER_BOT="$SCRIPT_DIR/014_casper/run_casper.sh"
# (Disabled) Uncomment to re-enable dashboards:
# DASHBOARD="$SCRIPT_DIR/009_dashboard"
# STOCK_DASHBOARD="$SCRIPT_DIR/012_stock_dashboard"

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
for script in "$TELEGRAM_BOT" "$QUANT_DAEMON" "$INVESTMENT_BOT" "$CASPER_BOT"; do
    if [[ ! -f "$script" ]]; then
        echo "Error: Script not found: $script"
        exit 1
    fi
done

# Helper: parse surface ref from cmux output (format: "OK surface:N ...")
parse_surface() {
    echo "$1" | grep -oE 'surface:[0-9]+' | head -1
}

echo "Starting all bots in cmux workspace 'running_machine'..."

# --- Step 1: Create single workspace ---
echo "  [1/3] Creating workspace..."
ws_output=$(cmux new-workspace --cwd "$SCRIPT_DIR" 2>&1)
ws_ref=$(echo "$ws_output" | grep -oE 'workspace:[0-9]+' | head -1)
if [[ -z "$ws_ref" ]]; then
    echo "Error: Could not create workspace (output: $ws_output)"
    exit 1
fi
sleep 0.5

# Rename workspace to "running_machine"
cmux rename-workspace --workspace "$ws_ref" "running_machine" &>/dev/null

# Get initial surface from tree output
S_TL=$(cmux tree --workspace "$ws_ref" 2>&1 | grep -oE 'surface:[0-9]+' | head -1)
if [[ -z "$S_TL" ]]; then
    echo "Error: Could not find initial surface"
    exit 1
fi

# --- Step 2: Build 2+2+1 grid layout ---
echo "  [2/3] Building 2+2+1 grid..."

# Split 1: top → top + middle (row 1 / row 2)
split_out=$(cmux new-split down --workspace "$ws_ref" --surface "$S_TL" 2>&1)
S_BL=$(parse_surface "$split_out")
sleep 0.3

# Split 2: top-left → top-left + top-right
split_out=$(cmux new-split right --workspace "$ws_ref" --surface "$S_TL" 2>&1)
S_TR=$(parse_surface "$split_out")
sleep 0.3

# Split 3: bottom-left → bottom-left + bottom-right
split_out=$(cmux new-split right --workspace "$ws_ref" --surface "$S_BL" 2>&1)
S_BR=$(parse_surface "$split_out")
sleep 0.3

# Split 4: bottom-left → bottom-left + casper row
split_out=$(cmux new-split down --workspace "$ws_ref" --surface "$S_BL" 2>&1)
S_BOTTOM=$(parse_surface "$split_out")
sleep 0.3

echo "    Top:    $S_TL | $S_TR"
echo "    Mid:    $S_BL | $S_BR"
echo "    Bottom: $S_BOTTOM"

# Verify all 5 surfaces
for s in "$S_TL" "$S_TR" "$S_BL" "$S_BR" "$S_BOTTOM"; do
    if [[ -z "$s" ]]; then
        echo "Error: Failed to create all 5 panes. Check cmux status."
        exit 1
    fi
done

# --- Step 3: Launch bots in each pane ---
echo "  [3/3] Starting bots..."

# Helper: send command to a specific surface in our workspace
run_in_pane() {
    local surface="$1"
    local name="$2"
    local cmd="$3"
    echo "    $name → $surface"
    cmux send --workspace "$ws_ref" --surface "$surface" "printf '\\e]0;${name}\\a' && ${cmd}\n"
}

# Top row
# (Disabled) Trading Bot (005_money) - commented out by user
# run_in_pane "$S_TL" "Trading Bot"     "cd '$SCRIPT_DIR' && '$TRADING_BOT'"
run_in_pane "$S_TL" "(disabled) Trading Bot" "echo 'Trading Bot (005_money) disabled'"
run_in_pane "$S_TR" "Telegram Bot"    "cd '$SCRIPT_DIR' && '$TELEGRAM_BOT'"

# Bottom row
run_in_pane "$S_BL" "Quant Daemon"    "cd '$SCRIPT_DIR/007_stock_trade' && '$QUANT_DAEMON' daemon --no-dry-run"
run_in_pane "$S_BR" "Investment Bot"  "cd '$SCRIPT_DIR' && '$INVESTMENT_BOT'"

# Bottom row
run_in_pane "$S_BOTTOM" "미장봇"  "cd '$SCRIPT_DIR/014_casper' && '$CASPER_BOT' start --yes"

# (Disabled) Dashboard panes - Uncomment to re-enable:
# run_in_pane "$S_??" "Dashboard"       "cd '$DASHBOARD' && source venv/bin/activate && python app.py"
# run_in_pane "$S_??" "Stock Dashboard" "cd '$STOCK_DASHBOARD' && './run_watchdog.sh'"

echo ""
echo "4 bots running in workspace 'running_machine' (2+2+1 grid)"
echo "  Top:    (disabled) | Telegram Bot"
echo "  Mid:    Quant Daemon | Investment Bot"
echo "  Bottom: 미장봇"
echo ""
echo ""
echo "  (미장봇 uses --yes flag to skip live mode confirmation)"
echo ""
echo "Use 'cmux tree --workspace $ws_ref' to see the pane layout."
