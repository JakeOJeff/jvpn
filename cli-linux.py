#!/usr/bin/env python3
"""
cli.py — The client-side VPN tool. Runs on WPC (Windows PC).

What this file does:
  - Generates a WireGuard keypair for WPC (if it doesn't exist)
  - Writes a WireGuard client config (wg0-client.conf)
  - Calls wg-quick to connect/disconnect
  - Shows connection status with helpful messages

HOW TO RUN (on WPC, in a terminal with admin rights):
  python cli.py init          — first-time setup: generate keys, show your public key
  python cli.py connect       — connect to the VPN
  python cli.py disconnect    — disconnect
  python cli.py status        — show connection status
  python cli.py ping          — ping the server through the VPN tunnel

PREREQUISITES ON WPC:
  1. Install Python 3: https://python.org
  2. Install WireGuard for Windows: https://www.wireguard.com/install/
     (This gives you `wg` and `wg-quick` commands in PowerShell)
  3. Run your terminal as Administrator (WireGuard needs admin rights)
"""

import subprocess
import os
import sys
import time
import platform
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# Fill these in after running `python3 orchestrator.py add-peer` on the server.
# The orchestrator prints the values you need.
# ─────────────────────────────────────────────────────────────────────────────

# The Windows IP address of WL — the machine running the VPN server.
# Find it by running `ipconfig` in a Windows terminal on WL and looking for
# the IP of your main ethernet or WiFi adapter.
# Example: "192.168.1.42"
SERVER_ENDPOINT = "YOUR_WL_WINDOWS_IP_HERE"

# The server's WireGuard public key.
# Printed when you run `python3 orchestrator.py start` on the server.
SERVER_PUBLIC_KEY = "PASTE_SERVER_PUBLIC_KEY_HERE"

# The VPN IP address assigned to THIS client (WPC).
# Printed when you run `python3 orchestrator.py add-peer` on the server.
CLIENT_VPN_IP = "10.0.0.2"

# WireGuard port on the server
SERVER_PORT = 51820

# Where to store WPC's keys and config
# On Windows, Path.home() gives C:\Users\YourName
CONFIG_DIR = Path.home() / ".wg-vpn"

# ─────────────────────────────────────────────────────────────────────────────
# DETECT OPERATING SYSTEM
#
# `platform.system()` returns "Windows", "Linux", or "Darwin" (macOS).
# We need this because:
#   - wg-quick on Windows is called differently than on Linux
#   - File paths use backslashes on Windows, forward slashes on Linux
#   - We use different ping commands on Windows vs Linux
# ─────────────────────────────────────────────────────────────────────────────

IS_WINDOWS = platform.system() == "Windows"

# ─────────────────────────────────────────────────────────────────────────────
# PRETTY PRINTING HELPERS
#
# These just make the terminal output look nice.
# ANSI escape codes are special character sequences that terminals interpret
# as formatting instructions (color, bold, etc.).
# ─────────────────────────────────────────────────────────────────────────────

# On Windows, ANSI codes only work in newer terminals (Windows Terminal, VS Code).
# We check if we can use them.
USE_COLOR = not IS_WINDOWS or os.environ.get("WT_SESSION")  # WT_SESSION = Windows Terminal

GREEN  = "\033[92m" if USE_COLOR else ""
YELLOW = "\033[93m" if USE_COLOR else ""
RED    = "\033[91m" if USE_COLOR else ""
BLUE   = "\033[94m" if USE_COLOR else ""
BOLD   = "\033[1m"  if USE_COLOR else ""
RESET  = "\033[0m"  if USE_COLOR else ""

def ok(msg):    print(f"{GREEN}  ✓{RESET} {msg}")
def info(msg):  print(f"{BLUE}  ℹ{RESET} {msg}")
def warn(msg):  print(f"{YELLOW}  ⚠{RESET} {msg}")
def err(msg):   print(f"{RED}  ✗{RESET} {msg}")
def step(n, total, msg): print(f"\n{BOLD}[{n}/{total}]{RESET} {msg}")
def header(msg): print(f"\n{BOLD}══ {msg} ══{RESET}\n")

# ─────────────────────────────────────────────────────────────────────────────
# RUN SHELL COMMANDS
# ─────────────────────────────────────────────────────────────────────────────

def run(cmd: str, check=True, capture=True, verbose=False) -> subprocess.CompletedProcess:
    """Run a shell command. On Windows, use PowerShell."""
    if verbose:
        info(f"running: {cmd}")

    if IS_WINDOWS:
        # On Windows, wrap the command in powershell.exe so we get access
        # to wg-quick and other tools installed on Windows PATH.
        full_cmd = ["powershell.exe", "-Command", cmd]
        result = subprocess.run(full_cmd, capture_output=capture, text=True)
    else:
        result = subprocess.run(cmd, shell=True, capture_output=capture, text=True)

    if check and result.returncode != 0:
        err(f"Command failed: {cmd}")
        if result.stderr:
            print(f"      {result.stderr.strip()}")
        sys.exit(1)

    return result

# ─────────────────────────────────────────────────────────────────────────────
# KEY GENERATION (client side)
# ─────────────────────────────────────────────────────────────────────────────

def generate_client_keypair() -> tuple[str, str]:
    """
    Generate WPC's WireGuard keypair.

    Same as the server side — we get a private key and a public key.
    The public key is what you paste into the server's `add-peer` command.
    The private key NEVER leaves WPC.

    On Windows: WireGuard for Windows installs `wg.exe` and adds it to PATH.
    `wg genkey` and `wg pubkey` work the same as on Linux.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    priv_path = CONFIG_DIR / "client.private"
    pub_path  = CONFIG_DIR / "client.public"

    if priv_path.exists() and pub_path.exists():
        info("Client keys already exist, reusing them.")
        return priv_path.read_text().strip(), pub_path.read_text().strip()

    info("Generating new client keypair...")

    # `wg genkey` outputs a random base64-encoded 32-byte private key
    priv_result = run("wg genkey")
    private_key = priv_result.stdout.strip()

    # Pipe the private key into `wg pubkey` to derive the public key
    if IS_WINDOWS:
        # On Windows, piping works differently in PowerShell
        pub_result = subprocess.run(
            ["powershell.exe", "-Command", f'echo "{private_key}" | wg pubkey'],
            capture_output=True, text=True
        )
    else:
        pub_result = subprocess.run(
            "wg pubkey",
            input=private_key,
            shell=True, capture_output=True, text=True, check=True
        )
    public_key = pub_result.stdout.strip()

    priv_path.write_text(private_key)
    pub_path.write_text(public_key)

    # On Windows, we can't chmod, but the file is in the user's home dir
    # which is already protected by Windows ACLs (access control lists).
    if not IS_WINDOWS:
        run(f"chmod 600 {priv_path}")

    ok(f"Client keypair saved to {CONFIG_DIR}")
    return private_key, public_key

# ─────────────────────────────────────────────────────────────────────────────
# WRITE CLIENT CONFIG
# ─────────────────────────────────────────────────────────────────────────────

def write_client_config(client_private_key: str) -> Path:
    """
    Write the WireGuard client config file (wg0-client.conf).

    CLIENT CONFIG STRUCTURE:

    [Interface]
      PrivateKey — WPC's secret key (never shared)
      Address    — WPC's IP inside the VPN (10.0.0.2/24)
      DNS        — which DNS server to use for name lookups inside the VPN
                   DNS = Domain Name System. It's like a phone book:
                   you give it a name (google.com) and it returns an IP (142.250.x.x).
                   We point to the server (10.0.0.1) so DNS queries go through the tunnel.

    [Peer]  (the server)
      PublicKey  — the server's public key (we verify this is really our server)
      Endpoint   — server's real-world IP:port (WL's Windows IP, port 51820)
      AllowedIPs — which traffic goes through the tunnel
                   0.0.0.0/0 means ALL traffic — full tunnel mode.
                   You could also use just 10.0.0.0/24 to only route VPN traffic
                   (split tunnel mode) — useful to keep local traffic fast.
      PersistentKeepalive — send a packet every 25 seconds to keep the tunnel alive.
                   WHY: NAT devices (routers) forget UDP connections after ~30s of
                   silence. Without keepalive, the tunnel goes silent and the
                   connection breaks. Keepalive prevents that.
    """
    config_path = CONFIG_DIR / "wg0-client.conf"

    config = f"""# WireGuard Client Config for WPC
# Generated by cli.py — do not share this file (it contains your private key)

[Interface]
PrivateKey = {client_private_key}
Address = {CLIENT_VPN_IP}/24
DNS = {SERVER_VPN_IP_FOR_DNS}

[Peer]
# This is the VPN server (WL)
PublicKey = {SERVER_PUBLIC_KEY}

# Endpoint = real-world address of the server
# Format: IP:Port or hostname:Port
Endpoint = {SERVER_ENDPOINT}:{SERVER_PORT}

# AllowedIPs = which destination IPs get sent through the tunnel
# 0.0.0.0/0 = everything (all traffic goes through VPN — "full tunnel")
# 10.0.0.0/24 = only VPN subnet traffic ("split tunnel" — faster for browsing)
AllowedIPs = 0.0.0.0/0

# Send a keepalive ping every 25 seconds so NAT mappings don't expire
PersistentKeepalive = 25
"""

    config_path.write_text(config)
    ok(f"Client config written to {config_path}")
    return config_path

# Server's VPN IP (used as DNS)
SERVER_VPN_IP_FOR_DNS = "10.0.0.1"

# ─────────────────────────────────────────────────────────────────────────────
# CONNECT / DISCONNECT
# ─────────────────────────────────────────────────────────────────────────────

def cmd_connect():
    """
    Connect WPC to the VPN server on WL.

    Sequence:
    1. Load (or generate) the client config
    2. Call wg-quick up — this:
       a. Creates a virtual network interface (utun0 on macOS, a TUN adapter on Windows)
       b. Configures it with our IP address (10.0.0.2)
       c. Adds routes: 0.0.0.0/0 → wg0 (all traffic through VPN)
       d. Performs the WireGuard handshake with the server

    TUN ADAPTER: A TUN (network TUNnel) interface is a virtual network card
    that exists only in software. Packets you send to it are handed to
    WireGuard instead of going out a real ethernet port. WireGuard encrypts
    them and sends them via UDP to the real server. Incoming encrypted UDP
    packets from the server get decrypted and injected back through the TUN
    interface as if they arrived on a normal network card.

    ROUTING: Your OS keeps a routing table — a map of "if the destination is
    X, send the packet out interface Y." wg-quick adds an entry saying "send
    everything out the wg0 interface." Your normal internet traffic goes through
    the VPN server instead of directly to the internet.
    """
    header("Connecting to VPN")

    # Check that the user has filled in the configuration
    if SERVER_ENDPOINT == "YOUR_WL_WINDOWS_IP_HERE":
        err("You haven't set SERVER_ENDPOINT in cli.py!")
        err("Open cli.py in a text editor and fill in your server's IP address.")
        err("You can find it by running `ipconfig` on WL and looking for the IPv4 address.")
        sys.exit(1)

    if SERVER_PUBLIC_KEY == "PASTE_SERVER_PUBLIC_KEY_HERE":
        err("You haven't set SERVER_PUBLIC_KEY in cli.py!")
        err("Run `python3 orchestrator.py start` on WL and copy the public key it prints.")
        sys.exit(1)

    step(1, 3, "Preparing client configuration...")
    priv_key, pub_key = generate_client_keypair()
    config_path = write_client_config(priv_key)

    step(2, 3, "Bringing WireGuard tunnel up...")
    if IS_WINDOWS:
        # On Windows, wg-quick is installed by the WireGuard for Windows app.
        # It's accessible as a PowerShell command.
        result = run(f'wg-quick up "{config_path}"', check=False)
    else:
        result = run(f"sudo wg-quick up {config_path}", check=False)

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "already exists" in stderr or "already active" in stderr.lower():
            warn("Tunnel already active. Run `python cli.py disconnect` first if needed.")
        else:
            err(f"wg-quick failed:\n    {stderr}")
            print()
            info("Common fixes:")
            info("  1. Run this terminal as Administrator")
            info("  2. Make sure WireGuard for Windows is installed: https://www.wireguard.com/install/")
            info("  3. Check that the server is running: python3 orchestrator.py status (on WL)")
            sys.exit(1)
    else:
        ok("WireGuard tunnel is UP")

    step(3, 3, "Verifying connection...")
    time.sleep(2)  # give the tunnel a moment to establish
    _verify_connection()

def _verify_connection():
    """Ping the VPN server to verify the tunnel is working."""
    server_vpn_ip = "10.0.0.1"
    info(f"Pinging VPN server at {server_vpn_ip}...")

    if IS_WINDOWS:
        result = run(f"ping -n 3 {server_vpn_ip}", check=False)
    else:
        result = run(f"ping -c 3 {server_vpn_ip}", check=False)

    if result.returncode == 0:
        ok(f"Connected! VPN server ({server_vpn_ip}) is reachable.")
        ok(f"Your VPN IP: {CLIENT_VPN_IP}")
        print()
        info("All your internet traffic is now routed through WL.")
        info("To disconnect: python cli.py disconnect")
    else:
        warn("Tunnel is up but server ping failed.")
        warn("Possible reasons:")
        warn("  - Server might not be running (check: python3 orchestrator.py status on WL)")
        warn("  - Firewall on WL is blocking ICMP (ping) packets")
        warn("  - Windows port forwarding isn't set up correctly")
        print()
        info("Try: python cli.py status — to see WireGuard handshake details")

def cmd_disconnect():
    """
    Tear down the VPN tunnel.

    `wg-quick down` reverses everything `wg-quick up` did:
    - Removes the VPN routes from the routing table
    - Destroys the TUN interface
    - Runs any PostDown commands from the config
    """
    header("Disconnecting from VPN")

    config_path = CONFIG_DIR / "wg0-client.conf"

    if not config_path.exists():
        warn("No client config found. Maybe you haven't connected yet?")
        return

    if IS_WINDOWS:
        result = run(f'wg-quick down "{config_path}"', check=False)
    else:
        result = run(f"sudo wg-quick down {config_path}", check=False)

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not found" in stderr or "does not exist" in stderr.lower():
            info("Tunnel was already down.")
        else:
            warn(f"wg-quick down returned an error: {stderr}")
    else:
        ok("VPN tunnel disconnected.")
        info("Your traffic now goes directly to the internet (not through VPN).")

# ─────────────────────────────────────────────────────────────────────────────
# STATUS
# ─────────────────────────────────────────────────────────────────────────────

def cmd_status():
    """
    Show the current VPN status.

    We check several things:
    1. Is the wg0 interface up? (does `wg show` work?)
    2. When was the last handshake? (recent = connected)
    3. How much data has been transferred?
    4. What's our public IP? (should be WL's IP when VPN is active)
    """
    header("VPN Status")

    # Check WireGuard interface
    result = run("wg show all", check=False)
    if result.returncode != 0 or not result.stdout.strip():
        warn("WireGuard tunnel is NOT active.")
        info("To connect: python cli.py connect")
        return

    print(result.stdout)

    # Check public IP — if VPN is working, this should be WL's IP
    print()
    info("Checking your public IP address (should be WL's IP when VPN is on)...")
    try:
        if IS_WINDOWS:
            ip_result = run(
                "(Invoke-WebRequest -Uri 'https://api.ipify.org' -UseBasicParsing).Content",
                check=False
            )
        else:
            ip_result = run("curl -s https://api.ipify.org", check=False)

        if ip_result.returncode == 0:
            public_ip = ip_result.stdout.strip()
            info(f"Your public IP: {public_ip}")
            if SERVER_ENDPOINT != "YOUR_WL_WINDOWS_IP_HERE":
                if SERVER_ENDPOINT in public_ip or public_ip == SERVER_ENDPOINT:
                    ok("Public IP matches server — VPN routing is working!")
                else:
                    warn(f"Public IP ({public_ip}) doesn't match server ({SERVER_ENDPOINT})")
                    warn("VPN tunnel may be up but routing may be incomplete.")
    except Exception:
        warn("Could not check public IP (network may be offline).")

def cmd_init():
    """
    First-time setup: generate keys and print the public key for the server.

    WORKFLOW:
    1. Run `python cli.py init` on WPC → get your public key
    2. Run `python3 orchestrator.py add-peer` on WL → paste the public key
    3. Fill in SERVER_ENDPOINT and SERVER_PUBLIC_KEY in cli.py
    4. Run `python cli.py connect` on WPC
    """
    header("First-Time Setup")

    info("Generating client keypair for WPC...")
    priv_key, pub_key = generate_client_keypair()

    print()
    print(f"{BOLD}Your WPC public key:{RESET}")
    print(f"\n    {GREEN}{pub_key}{RESET}\n")
    print("Next steps:")
    print("  1. Copy the public key above.")
    print("  2. On WL (in WSL2), run:")
    print("       python3 orchestrator.py add-peer")
    print("     Paste your public key when asked.")
    print("  3. The server will print your assigned VPN IP and its own public key.")
    print("  4. Open cli.py in a text editor and fill in:")
    print("       SERVER_ENDPOINT  = WL's Windows IP address")
    print("       SERVER_PUBLIC_KEY = the key the server printed")
    print("       CLIENT_VPN_IP    = the VPN IP the server assigned you")
    print("  5. Run: python cli.py connect")

def cmd_ping():
    """Ping the VPN server to test latency."""
    header("Ping VPN Server")
    server_ip = "10.0.0.1"

    if IS_WINDOWS:
        result = run(f"ping -n 5 {server_ip}", check=False, capture=False)
    else:
        result = run(f"ping -c 5 {server_ip}", check=False, capture=False)

    if result.returncode != 0:
        err(f"Could not reach {server_ip}. Is the VPN connected?")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

COMMANDS = {
    "init":       (cmd_init,       "First-time setup: generate keys"),
    "connect":    (cmd_connect,    "Connect to the VPN"),
    "disconnect": (cmd_disconnect, "Disconnect from the VPN"),
    "status":     (cmd_status,     "Show connection status"),
    "ping":       (cmd_ping,       "Ping the VPN server"),
}

def usage():
    print(f"\n{BOLD}cli.py — WireGuard VPN Client{RESET}")
    print(f"\nUsage: python cli.py <command>\n")
    print("Commands:")
    for cmd, (fn, desc) in COMMANDS.items():
        print(f"  {cmd:15s}  {desc}")
    print()
    print("First time? Run:  python cli.py init")

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        usage()
        sys.exit(0 if len(sys.argv) < 2 else 1)

    COMMANDS[sys.argv[1]][0]()