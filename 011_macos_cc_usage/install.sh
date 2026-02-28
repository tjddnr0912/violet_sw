#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="ClaudeUsage"
APP_BUNDLE="${APP_NAME}.app"
INSTALL_DIR="/Applications"
BUILD_DIR="${SCRIPT_DIR}/build"
PLIST_LABEL="com.violet.claudeusage"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

echo "=== ${APP_NAME} Install ==="

# 1. xcodegen
echo "[1/4] Generating Xcode project..."
xcodegen generate

# 2. Release build
echo "[2/4] Building Release..."
xcodebuild \
    -scheme "$APP_NAME" \
    -configuration Release \
    -derivedDataPath "$BUILD_DIR" \
    CODE_SIGN_IDENTITY="-" \
    build | tail -5

BUILT_APP="${BUILD_DIR}/Build/Products/Release/${APP_BUNDLE}"
if [ ! -d "$BUILT_APP" ]; then
    echo "Error: Build failed. ${BUILT_APP} not found."
    exit 1
fi

# 3. Copy to /Applications
echo "[3/4] Installing to ${INSTALL_DIR}..."
if [ -d "${INSTALL_DIR}/${APP_BUNDLE}" ]; then
    echo "  Removing existing ${APP_BUNDLE}..."
    rm -rf "${INSTALL_DIR}/${APP_BUNDLE}"
fi
cp -R "$BUILT_APP" "$INSTALL_DIR/"
echo "  Installed: ${INSTALL_DIR}/${APP_BUNDLE}"

# 4. LaunchAgent
echo "[4/4] Registering LaunchAgent..."
mkdir -p "$HOME/Library/LaunchAgents"

# Unload existing if present
if launchctl list 2>/dev/null | grep -q "$PLIST_LABEL"; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>
    <key>Program</key>
    <string>${INSTALL_DIR}/${APP_BUNDLE}/Contents/MacOS/${APP_NAME}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
EOF

launchctl load "$PLIST_PATH"
echo "  LaunchAgent registered: ${PLIST_PATH}"

echo ""
echo "=== Done ==="
echo "  App: ${INSTALL_DIR}/${APP_BUNDLE}"
echo "  Auto-start: enabled (login)"
echo "  To launch now: open ${INSTALL_DIR}/${APP_BUNDLE}"
