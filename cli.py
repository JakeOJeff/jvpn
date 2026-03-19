#!/usr/bin/env python3
"""
cli.py
------
Runs on the VPN CLIENT (your PC WSL2).
Manages your WireGuard tunnel by talking to the orchestrator.

Commands:
  python3 cli.py init                → generate keypair, create config
  python3 cli.py register <name>     → register with server, get VPN IP
  python3 cli.py up                  → connect to VPN
  python3 cli.py down                → disconnect
  python3 cli.py status              → show tunnel state + public IP

Config: ~/.config/vpn/config.json
Run up/down with: sudo -E python3 cli.py up

Requires:
  pip install requests
  sudo apt install wireguard-tools
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# ── Config paths ──────────────────────────────────────────────────────────────

CONFIG_DIR  = Path.home() / ".config" / "vpn"
CONFIG_FILE = CONFIG_DIR / "config.json"
KEY_FILE    = CONFIG_DIR / "private.key"

# VPN client interface name
# wg1 so it doesn't clash with wg0 if testing on same machine
CLIENT_IFACE = "wg1"

# ── Config helpers ────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        die(f"No config found. Run: python3 cli.py init")
    return json.loads(CONFIG_FILE.read_text())


def save_config(cfg: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    CONFIG_FILE.chmod(0o600)


# ── Key helpers ───────────────────────────────────────────────────────────────

def generate_private_key() -> str:
    return subprocess.run(
        ["wg", "genkey"], capture_output=True, text=True, check=True
    ).stdout.strip()


def derive_public_key(private_key: str) -> str:
    return subprocess.run(
        ["wg", "pubkey"], input=private_key,
        capture_output=True, text=True, check=True
    ).stdout.strip()


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_init(args):
    """Generate keypair and write initial config file."""
    if CONFIG_FILE.exists():
        print(f"Config already exists: {CONFIG_FILE}")
        print("Delete it manually to reinitialise.")
        return

    print("Generating WireGuard keypair...")
    private_key = generate_private_key()
    public_key  = derive_public_key(private_key)

    cfg = {
        "private_key":        private_key,
        "public_key":         public_key,
        "orchestrator_url":   "http://YOUR_SERVER_IP:8080",
        "dns":                "1.1.1.1",
        # filled in after register:
        "client_ip":          None,
        "server_public_key":  None,
        "server_endpoint":    None,
    }
    save_config(cfg)

    print(f"\nConfig saved: {CONFIG_FILE}")
    print(f"\nYour public key (server needs this):")
    print(f"  {public_key}")
    print(f"\nNext:")
    print(f"  1. Edit {CONFIG_FILE}")
    print(f"     Set orchestrator_url to http://LAPTOP_LOCAL_IP:8080")
    print(f"  2. python3 cli.py register yourname")
    print(f"  3. sudo -E python3 cli.py up")


def cmd_register(args):
    """Register with the server. Gets assigned a VPN IP."""
    import requests

    cfg = load_config()
    url = cfg.get("orchestrator_url", "")

    if "YOUR_SERVER_IP" in url or not url:
        die(f"Set orchestrator_url in {CONFIG_FILE} to http://LAPTOP_IP:8080")

    print(f"Registering '{args.name}' with {url}...")

    try:
        resp = requests.post(
            f"{url}/peers",
            json={"name": args.name, "public_key": cfg["public_key"]},
            timeout=10
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        die(
            f"Cannot reach orchestrator at {url}\n"
            f"Is it running? Is the laptop IP correct?\n"
            f"Try: curl {url}/health"
        )
    except requests.exceptions.HTTPError as e:
        die(f"Server error: {e}\n{resp.text}")

    data = resp.json()

    cfg["client_ip"]        = data["ip"]
    cfg["server_public_key"] = data["server_public_key"]
    cfg["server_endpoint"]  = data["endpoint"]
    save_config(cfg)

    print(f"\nRegistered.")
    print(f"  Your VPN IP    : {data['ip']}")
    print(f"  Server endpoint: {data['endpoint']}")
    print(f"\nRun: sudo -E python3 cli.py up")


def cmd_up(args):
    """Connect to the VPN."""
    cfg = load_config()

    missing = [k for k in ["client_ip", "server_public_key", "server_endpoint"]
               if not cfg.get(k)]
    if missing:
        die(f"Missing config: {missing}\nRun: python3 cli.py register <name>")

    print("Connecting...")

    # write private key to temp file (wg needs a file path, not stdin)
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(cfg["private_key"])
    KEY_FILE.chmod(0o600)

    # clean up any leftover interface silently
    subprocess.run(["ip", "link", "delete", CLIENT_IFACE],
                   capture_output=True)

    # create WireGuard interface
    run(["ip", "link", "add", CLIENT_IFACE, "type", "wireguard"])

    # assign VPN IP
    run(["ip", "addr", "add", f"{cfg['client_ip']}/24", "dev", CLIENT_IFACE])

    # configure WireGuard — keys, peer, endpoint
    run(["wg", "set", CLIENT_IFACE,
         "private-key", str(KEY_FILE),
         "peer",         cfg["server_public_key"],
         "endpoint",     cfg["server_endpoint"],
         # route ALL traffic through VPN
         # split into two halves to avoid WSL2 routing bug with 0.0.0.0/0
         "allowed-ips",  "0.0.0.0/1,128.0.0.0/1",
         "persistent-keepalive", "25"])

    # bring interface up
    run(["ip", "link", "set", CLIENT_IFACE, "up"])

    # add routes — send all traffic through wg1
    run(["ip", "route", "add", "0.0.0.0/1",   "dev", CLIENT_IFACE], ok_if_exists=True)
    run(["ip", "route", "add", "128.0.0.0/1", "dev", CLIENT_IFACE], ok_if_exists=True)

    # set DNS
    try:
        dns = cfg.get("dns", "1.1.1.1")
        Path("/etc/resolv.conf").write_text(f"nameserver {dns}\n")
    except PermissionError:
        print("  (could not set DNS — run with sudo -E)")

    print(f"Connected.")
    print(f"  VPN IP : {cfg['client_ip']}")
    print(f"  Server : {cfg['server_endpoint']}")
    print(f"\nVerify: python3 cli.py status")


def cmd_down(args):
    """Disconnect from VPN."""
    result = subprocess.run(
        ["ip", "link", "delete", CLIENT_IFACE],
        capture_output=True
    )
    if result.returncode != 0:
        print("Not connected (interface not found).")
    else:
        print("Disconnected.")


def cmd_status(args):
    """Show current connection state and public IP."""
    result = subprocess.run(["wg", "show"], capture_output=True, text=True)

    if result.returncode != 0 or not result.stdout.strip():
        print("Status: disconnected")
        return

    print("Status: connected\n")
    print(result.stdout)

    print("Public IP: ", end="", flush=True)
    for url in ["https://ifconfig.me", "https://api.ipify.org"]:
        try:
            r = subprocess.run(
                ["curl", "-s", "--max-time", "4", url],
                capture_output=True, text=True
            )
            if r.returncode == 0 and r.stdout.strip():
                print(r.stdout.strip())
                return
        except Exception:
            continue
    print("(could not fetch)")


# ── Utils ─────────────────────────────────────────────────────────────────────

def run(cmd: list, ok_if_exists: bool = False):
    """Run a command. Die on failure unless ok_if_exists and error is EEXIST."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if ok_if_exists and "File exists" in stderr:
            return   # route already there — fine
        die(f"Command failed: {' '.join(cmd)}\n{stderr}")


def die(msg: str):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


# ── Entry ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="vpn",
        description="Minimal WireGuard VPN client"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init",   help="Generate keypair and create config")
    sub.add_parser("up",     help="Connect to VPN (run with sudo -E)")
    sub.add_parser("down",   help="Disconnect (run with sudo -E)")
    sub.add_parser("status", help="Show connection status")

    reg = sub.add_parser("register", help="Register with server, get VPN IP")
    reg.add_argument("name", help="Your name e.g. jake")

    args = parser.parse_args()

    {
        "init":     cmd_init,
        "up":       cmd_up,
        "down":     cmd_down,
        "status":   cmd_status,
        "register": cmd_register,
    }[args.command](args)


if __name__ == "__main__":
    main()