#!/bin/bash
# Cloudflare Tunnel Setup Script for Trading Dashboard
# Run this script once to set up the tunnel.

set -e

echo "=== Cloudflare Tunnel Setup ==="

# Step 1: Install cloudflared
if ! command -v cloudflared &> /dev/null; then
    echo "Installing cloudflared..."
    brew install cloudflare/cloudflare/cloudflared
else
    echo "cloudflared is already installed: $(cloudflared --version)"
fi

# Step 2: Login to Cloudflare
echo ""
echo "Step 2: Logging in to Cloudflare..."
echo "A browser window will open. Log in and select your domain."
cloudflared tunnel login

# Step 3: Create tunnel
echo ""
echo "Step 3: Creating tunnel 'trading-dashboard'..."
cloudflared tunnel create trading-dashboard

# Step 4: Get tunnel ID
TUNNEL_ID=$(cloudflared tunnel list | grep "trading-dashboard" | awk '{print $1}')
echo "Tunnel ID: $TUNNEL_ID"

# Step 5: Create config file
echo ""
echo "Step 4: Creating config file..."
mkdir -p ~/.cloudflared

cat > ~/.cloudflared/config.yml << EOF
tunnel: $TUNNEL_ID
credentials-file: /Users/$(whoami)/.cloudflared/${TUNNEL_ID}.json

ingress:
  - hostname: dashboard.yourdomain.com
    service: http://localhost:5001
    originRequest:
      noTLSVerify: true
  - service: http_status:404
EOF

echo "Config written to ~/.cloudflared/config.yml"
echo ""
echo "=== IMPORTANT ==="
echo "1. Edit ~/.cloudflared/config.yml and replace 'dashboard.yourdomain.com' with your actual domain"
echo "2. Run: cloudflared tunnel route dns trading-dashboard dashboard.yourdomain.com"
echo "3. Test: cloudflared tunnel run trading-dashboard"
echo ""
echo "For quick test without a domain:"
echo "  cloudflared tunnel --url http://localhost:5001"
echo ""
echo "To install as system service (auto-start on boot):"
echo "  sudo cloudflared service install"
