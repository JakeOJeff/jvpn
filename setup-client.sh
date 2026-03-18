#!/usr/bin/env bash
# setup-client.sh
# ──────────────────────────────────────────────────────────────────────────────
# Run this ONCE on the client PC WSL2.
# Sets up dependencies and initialises your VPN config.
#
# Usage:
#   chmod +x setup-client.sh
#   ./setup-client.sh
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[+]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[x]${NC} $1"; exit 1; }

# ── Step 1: install dependencies ──────────────────────────────────────────────

info "Installing dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq wireguard-tools python3 python3-venv python3-full curl
info "Dependencies installed."

# ── Step 2: load WireGuard module ─────────────────────────────────────────────

info "Loading WireGuard kernel module..."
sudo modprobe wireguard || error "WireGuard not available in your WSL2 kernel."
info "WireGuard module loaded."

# ── Step 3: set up Python venv ────────────────────────────────────────────────

info "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install -q requests
info "Python deps installed."

# ── Step 4: init VPN config ───────────────────────────────────────────────────

info "Initialising VPN config..."
python3 cli.py init

# ── Step 5: print summary ─────────────────────────────────────────────────────

echo ""
echo "══════════════════════════════════════════════"
echo "  VPN Client Setup Complete"
echo "══════════════════════════════════════════════"
echo ""
echo "  Next steps:"
echo ""
echo "  1. Edit your config:"
echo "     nano ~/.config/vpn/config.json"
echo "     Set orchestrator_url to http://LAPTOP_LAN_IP:8080"
echo ""
echo "  2. Register with the server:"
echo "     source venv/bin/activate"
echo "     python3 cli.py register yourname"
echo ""
echo "  3. Connect:"
echo "     sudo -E python3 cli.py up"
echo ""
echo "  4. Verify:"
echo "     python3 cli.py status"
echo "     (public IP should show the laptop's IP)"
echo ""
echo "  To disconnect:"
echo "     sudo -E python3 cli.py down"
echo ""
echo "══════════════════════════════════════════════"