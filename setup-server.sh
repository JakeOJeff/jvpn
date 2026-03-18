#!/usr/bin/env bash
# setup-server.sh
# ──────────────────────────────────────────────────────────────────────────────
# Run this ONCE on the laptop WSL2 to set up the VPN server side.
# After this, start the orchestrator with: sudo venv/bin/python3 orchestrator.py
#
# Usage:
#   chmod +x setup-server.sh
#   ./setup-server.sh
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[+]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[x]${NC} $1"; exit 1; }

# ── Step 1: check dependencies ────────────────────────────────────────────────

info "Checking dependencies..."

sudo apt-get update -qq
sudo apt-get install -y -qq wireguard-tools python3 python3-venv python3-full curl

info "Dependencies installed."

# ── Step 2: load WireGuard kernel module ──────────────────────────────────────

info "Loading WireGuard kernel module..."
sudo modprobe wireguard || error "WireGuard kernel module not available in your WSL2 kernel."
info "WireGuard module loaded."

# ── Step 3: generate server keypair ───────────────────────────────────────────

info "Setting up WireGuard keys..."

sudo mkdir -p /etc/wireguard
sudo chmod 755 /etc/wireguard

if [ ! -f /etc/wireguard/private.key ]; then
    wg genkey | sudo tee /etc/wireguard/private.key > /dev/null
    sudo chmod 600 /etc/wireguard/private.key
    info "Server keypair generated."
else
    warn "Private key already exists — skipping keygen."
fi

# create peers file if missing
if [ ! -f /etc/wireguard/peers.json ]; then
    echo '{}' | sudo tee /etc/wireguard/peers.json > /dev/null
fi
sudo chmod 644 /etc/wireguard/peers.json

SERVER_PUBLIC_KEY=$(cat /etc/wireguard/private.key | wg pubkey)
info "Server public key: ${SERVER_PUBLIC_KEY}"

# ── Step 4: create WireGuard interface ────────────────────────────────────────

info "Creating wg0 interface..."

# remove if exists from previous run
sudo ip link delete wg0 2>/dev/null || true

sudo ip link add wg0 type wireguard
sudo ip addr add 10.0.0.1/24 dev wg0
sudo wg set wg0 listen-port 51820 private-key /etc/wireguard/private.key
sudo ip link set wg0 up

info "wg0 is up at 10.0.0.1"

# ── Step 5: IP forwarding + NAT ───────────────────────────────────────────────

info "Enabling IP forwarding and NAT..."

# IP forwarding — allows kernel to route packets between interfaces
sudo sysctl -w net.ipv4.ip_forward=1 > /dev/null

# NAT — rewrite client source IPs to server IP when going to internet
# find the main network interface automatically
MAIN_IFACE=$(ip route | grep default | awk '{print $5}' | head -1)
info "Main interface: ${MAIN_IFACE}"

sudo iptables -t nat -A POSTROUTING -s 10.0.0.0/24 -o "${MAIN_IFACE}" -j MASQUERADE 2>/dev/null || true
sudo iptables -A FORWARD -i wg0 -j ACCEPT 2>/dev/null || true
sudo iptables -A FORWARD -o wg0 -j ACCEPT 2>/dev/null || true

info "NAT configured."

# ── Step 6: set up Python venv ────────────────────────────────────────────────

info "Setting up Python virtual environment..."

python3 -m venv venv
source venv/bin/activate
pip install -q fastapi uvicorn requests

info "Python deps installed."

# ── Step 7: print summary ─────────────────────────────────────────────────────

WSL_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "══════════════════════════════════════════════"
echo "  VPN Server Setup Complete"
echo "══════════════════════════════════════════════"
echo ""
echo "  Server public key:"
echo "  ${SERVER_PUBLIC_KEY}"
echo ""
echo "  WSL2 IP (for portproxy): ${WSL_IP}"
echo ""
echo "  Next steps:"
echo ""
echo "  1. On Windows laptop — run in PowerShell (Admin):"
echo ""
echo "     netsh interface portproxy add v4tov4 \\"
echo "       listenport=8080 listenaddress=0.0.0.0 \\"
echo "       connectport=8080 connectaddress=${WSL_IP}"
echo ""
echo "     New-NetFirewallRule -DisplayName 'WireGuard' \\"
echo "       -Direction Inbound -Protocol UDP -LocalPort 51820 -Action Allow"
echo ""
echo "     New-NetFirewallRule -DisplayName 'VPN Orchestrator' \\"
echo "       -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow"
echo ""
echo "  2. Start orchestrator:"
echo "     sudo venv/bin/python3 orchestrator.py"
echo ""
echo "  3. On PC — edit ~/.config/vpn/config.json"
echo "     Set orchestrator_url to your laptop's LAN IP:"
echo "     http://LAPTOP_LAN_IP:8080"
echo ""
echo "══════════════════════════════════════════════"