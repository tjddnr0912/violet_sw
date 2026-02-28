#!/bin/bash
set -e

APP_NAME="ClaudeUsage"
APP_BUNDLE="${APP_NAME}.app"
PLIST_LABEL="com.violet.claudeusage"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

echo "=== ${APP_NAME} Uninstall ==="

# 1. Stop running app
if pgrep -x "$APP_NAME" > /dev/null 2>&1; then
    echo "[1/3] Stopping ${APP_NAME}..."
    killall "$APP_NAME" 2>/dev/null || true
else
    echo "[1/3] ${APP_NAME} not running."
fi

# 2. Unload LaunchAgent
if [ -f "$PLIST_PATH" ]; then
    echo "[2/3] Removing LaunchAgent..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
    echo "  Removed: ${PLIST_PATH}"
else
    echo "[2/3] LaunchAgent not found. Skipping."
fi

# 3. Remove app
if [ -d "/Applications/${APP_BUNDLE}" ]; then
    echo "[3/3] Removing /Applications/${APP_BUNDLE}..."
    rm -rf "/Applications/${APP_BUNDLE}"
    echo "  Removed."
else
    echo "[3/3] App not found in /Applications. Skipping."
fi

echo ""
echo "=== Uninstall complete ==="
