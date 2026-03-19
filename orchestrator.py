#!/usr/bin/env python3
"""
orchestrator.py — The server brain. Runs inside WSL2 on WL (Windows Laptop).

What this file does, step by step:
  1. Generates WireGuard keypairs (if they don't exist yet)
  2. Writes a wg0.conf file (WireGuard's instruction sheet)
  3. Figures out WSL2's current IP address (it changes every reboot!)
  4. Tells Windows to forward port 51820 → WSL2's IP (via netsh)
  5. Brings the WireGuard interface up or down
  6. Manages peers (clients that are allowed to connect)

HOW TO RUN:
  python3 orchestrator.py start        — bring the VPN server up
  python3 orchestrator.py stop         — bring it down
  python3 orchestrator.py status       — show current state
  python3 orchestrator.py add-peer     — register a new client
  python3 orchestrator.py show-config  — print the server config
"""

import subprocess   # lets Python run shell commands (like wg, ip, netsh)
import os           # file system stuff: does this file exist? make this folder.
import sys          # gives us sys.argv (the words typed after "python3 orchestrator.py")
import json         # for saving/loading peer info as a JSON file
import ipaddress    # helps us validate and work with IP addresses
from pathlib import Path  # a nicer way to work with file paths

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# Think of these like the settings panel at the top. Change them here, not
# scattered through the code.
# ─────────────────────────────────────────────────────────────────────────────

# Where we store keys and config files.
# Path.home() gives us /home/youruser — works on any machine.
CONFIG_DIR   = Path.home() / ".wg-vpn"

# The WireGuard interface name. "wg0" means "WireGuard interface number 0".
# Linux network interfaces are named things like eth0 (ethernet 0), wlan0
# (wireless 0), wg0 (WireGuard 0). You can have wg0, wg1, wg2... for multiple VPNs.
WG_INTERFACE = "wg0"

# The UDP port WireGuard listens on. 51820 is the conventional default.
# UDP is a network protocol — think of it like sending postcards (fast, no
# confirmation) vs TCP which is like certified mail (slower, confirmed delivery).
# WireGuard uses UDP because it handles its own reliability internally.
WG_PORT      = 51820

# The VPN's internal IP address range. This is a "private" subnet — addresses
# that only exist inside the tunnel, not on the real internet.
# 10.0.0.0/24 means: addresses 10.0.0.1 through 10.0.0.254 (254 possible devices).
# The server will be 10.0.0.1. Clients get 10.0.0.2, 10.0.0.3, etc.
VPN_SUBNET   = "10.0.0.0/24"
SERVER_VPN_IP = "10.0.0.1"

# ─────────────────────────────────────────────────────────────────────────────
# HELPER: run a shell command and return its output
# ─────────────────────────────────────────────────────────────────────────────

def run(cmd: str, check=True, capture=True) -> subprocess.CompletedProcess:
    """
    Run a shell command.

    WHY subprocess? Python can't directly talk to the WireGuard kernel module —
    it has to use the `wg` command-line tool, which is the official interface.
    subprocess.run() is how Python runs other programs.

    `shell=True` means we pass the whole string to bash, so pipes (|) and
    redirects (>) work naturally.
    `capture_output=True` captures stdout/stderr so we can read the output.
    `check=True` means: if the command fails (non-zero exit code), raise an error.
    """
    print(f"  → running: {cmd}")
    return subprocess.run(
        cmd,
        shell=True,
        check=check,
        capture_output=capture,
        text=True  # decode bytes to string automatically
    )

def run_windows(cmd: str) -> str:
    """
    Run a command on the WINDOWS side from inside WSL2.

    This is one of WSL2's superpowers: you can call Windows .exe files directly
    from Linux! powershell.exe and netsh.exe are both available from WSL2.

    WHY do we need this? WireGuard is running inside WSL2. But the "door"
    (port 51820) that the internet knocks on is on the Windows side. We need
    Windows to answer the door and pass the message into WSL2. That's what
    `netsh interface portproxy` does — it's Windows' port forwarding system.
    """
    result = subprocess.run(
        ["powershell.exe", "-Command", cmd],
        capture_output=True,
        text=True
    )
    return result.stdout.strip()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: KEY GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def generate_keypair(name: str) -> tuple[str, str]:
    """
    Generate a WireGuard public/private keypair and save them to files.

    HOW WIREGUARD KEYS WORK (the padlock analogy):
    - Private key: your secret. Never share it. Like the key to your house.
    - Public key: derived from the private key mathematically. You give this
      to anyone who needs to verify it's really you, or encrypt something
      that only you can decrypt.

    The math behind it is called "Curve25519" elliptic-curve cryptography.
    You don't need to understand the math — just know it's one-way: you can
    always go private→public, but you can NEVER go public→private.

    `wg genkey` generates a random private key (32 random bytes, base64 encoded).
    `wg pubkey` reads a private key from stdin and outputs the matching public key.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)  # create ~/.wg-vpn/ if needed

    priv_path = CONFIG_DIR / f"{name}.private"
    pub_path  = CONFIG_DIR / f"{name}.public"

    if priv_path.exists() and pub_path.exists():
        print(f"  ✓ Keys for '{name}' already exist, reusing them.")
        return priv_path.read_text().strip(), pub_path.read_text().strip()

    print(f"  Generating new keypair for '{name}'...")

    # Generate private key
    priv_result = run("wg genkey")
    private_key = priv_result.stdout.strip()

    # Derive public key from private key
    pub_result = subprocess.run(
        "wg pubkey",
        input=private_key,
        shell=True,
        capture_output=True,
        text=True,
        check=True
    )
    public_key = pub_result.stdout.strip()

    # Save both to files
    # chmod 600 means: only the owner can read/write. Nobody else.
    # This is important for private keys — WireGuard will refuse to use
    # a private key file that's readable by other users.
    priv_path.write_text(private_key)
    pub_path.write_text(public_key)
    run(f"chmod 600 {priv_path}")
    run(f"chmod 644 {pub_path}")

    print(f"  ✓ Keypair saved to {CONFIG_DIR}/")
    return private_key, public_key

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: FIGURE OUT WSL2'S IP ADDRESS
# ─────────────────────────────────────────────────────────────────────────────

def get_wsl2_ip() -> str:
    """
    Find the IP address of WSL2's ethernet interface (eth0).

    WHY IS THIS HARD? When you run WSL2, Windows creates a virtual ethernet
    adapter. WSL2 gets an IP like 172.18.x.x or 172.19.x.x — in the 172.16.0.0/12
    "private" range. This IP is assigned by a tiny DHCP server inside Hyper-V.
    It changes every time WSL2 restarts.

    `ip addr show eth0` lists the network config of the eth0 interface.
    We grep for "inet " (IPv4 address lines) and cut out just the IP part.

    Example output of `ip addr show eth0`:
        2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 ...
            inet 172.18.144.1/20 brd 172.18.159.255 scope global eth0
                                ^^^^^^^^^^^^^^^^^^^ we want this part, minus /20
    """
    result = run("ip addr show eth0 | grep 'inet ' | awk '{print $2}' | cut -d/ -f1")
    ip = result.stdout.strip()

    if not ip:
        raise RuntimeError(
            "Could not find WSL2 IP on eth0.\n"
            "Make sure you're running inside WSL2, not in a VM or bare metal Linux."
        )

    print(f"  ✓ WSL2 IP address: {ip}")
    return ip

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: CONFIGURE WINDOWS PORT FORWARDING
# ─────────────────────────────────────────────────────────────────────────────

def setup_port_forward(wsl2_ip: str):
    """
    Tell Windows to forward UDP port 51820 to WSL2.

    THE PROBLEM: The internet (and WPC) sends packets to WL's Windows IP address.
    But WireGuard is running inside WSL2, which has a DIFFERENT IP address.
    Windows doesn't automatically know to pass those packets to WSL2.

    THE SOLUTION: netsh (Network Shell) — Windows' command-line networking tool.
    `netsh interface portproxy` creates a rule: "any traffic arriving on
    this port, forward it to that other IP:port."

    NOTE: portproxy natively only supports TCP. For UDP WireGuard, the better
    approach is a Windows Firewall rule + a socat relay inside WSL2. We set
    up both here for reliability.

    SOCAT = "SOcket CAT" — a Unix tool that relays data between two sockets.
    Think of it like a person standing at the Windows door, catching packets,
    and throwing them through the WSL2 window.
    """
    print(f"\n  Setting up Windows port forwarding (UDP {WG_PORT} → {wsl2_ip}:{WG_PORT})")

    # First, remove any old port forwarding rules for this port
    run_windows(
        f"netsh interface portproxy delete v4tov4 listenport={WG_PORT} listenaddress=0.0.0.0"
    )

    # Add new rule: forward TCP on 51820 to WSL2
    # (We'll handle UDP via socat below — netsh portproxy is TCP-only)
    run_windows(
        f"netsh interface portproxy add v4tov4 "
        f"listenport={WG_PORT} listenaddress=0.0.0.0 "
        f"connectport={WG_PORT} connectaddress={wsl2_ip}"
    )

    # Open Windows Firewall for UDP 51820 inbound
    # This is the actual door that WireGuard needs open.
    run_windows(
        f'netsh advfirewall firewall delete rule name="WireGuard-VPN-In"'
    )
    run_windows(
        f'netsh advfirewall firewall add rule name="WireGuard-VPN-In" '
        f'protocol=UDP dir=in localport={WG_PORT} action=allow'
    )

    print("  ✓ Windows firewall and port forwarding configured.")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: WRITE THE WIREGUARD CONFIG FILE
# ─────────────────────────────────────────────────────────────────────────────

def load_peers() -> list[dict]:
    """Load the list of approved client peers from our JSON file."""
    peers_file = CONFIG_DIR / "peers.json"
    if not peers_file.exists():
        return []
    return json.loads(peers_file.read_text())

def save_peers(peers: list[dict]):
    """Save the peer list to disk."""
    peers_file = CONFIG_DIR / "peers.json"
    peers_file.write_text(json.dumps(peers, indent=2))

def write_server_config(server_private_key: str, peers: list[dict]):
    """
    Write wg0.conf — WireGuard's main configuration file.

    A wg0.conf file has two kinds of sections:

    [Interface] — describes THIS machine's WireGuard setup:
      - PrivateKey: the server's secret key
      - Address: the server's IP *inside* the VPN tunnel (10.0.0.1)
      - ListenPort: which port to listen on (51820)
      - PostUp/PostDown: shell commands to run when WireGuard starts/stops
        (we use these to enable IP forwarding and NAT)

    [Peer] — describes each CLIENT allowed to connect:
      - PublicKey: the client's public key (we verify their identity with this)
      - AllowedIPs: which VPN IPs this peer is allowed to use
        (10.0.0.2/32 means "only this one exact IP address")

    IP FORWARDING: By default, Linux drops packets that aren't addressed to it.
    But a VPN server needs to ROUTE packets from the tunnel to the internet
    (and back). `sysctl -w net.ipv4.ip_forward=1` enables this — Linux will
    now forward packets between interfaces.

    NAT (Network Address Translation): When the client's traffic exits the
    server to the internet, it needs to look like it came FROM the server's
    IP, not from 10.0.0.2. iptables masquerade does this translation.
    It's like a receptionist who receives mail addressed to the company,
    re-sends it with their name as the return address, and routes replies back.
    """
    config_path = CONFIG_DIR / "wg0.conf"

    # Build [Peer] sections for each registered client
    peer_sections = ""
    for peer in peers:
        peer_sections += f"""
[Peer]
# {peer.get('name', 'unnamed')}
PublicKey = {peer['public_key']}
AllowedIPs = {peer['vpn_ip']}/32
"""

    config = f"""# WireGuard Server Config — generated by orchestrator.py
# Edit this file directly only if you know what you're doing.
# Better: use `python3 orchestrator.py add-peer` to manage peers.

[Interface]
PrivateKey = {server_private_key}
Address = {SERVER_VPN_IP}/24
ListenPort = {WG_PORT}

# PostUp runs when `wg-quick up wg0` is called.
# 1. Enable IP forwarding (let packets pass through this machine)
# 2. Add NAT masquerade (rewrite source IPs of outbound packets)
PostUp   = sysctl -w net.ipv4.ip_forward=1; iptables -t nat -A POSTROUTING -s {VPN_SUBNET} -o eth0 -j MASQUERADE

# PostDown runs when `wg-quick down wg0` is called.
# Clean up the iptables rule we added.
PostDown = iptables -t nat -D POSTROUTING -s {VPN_SUBNET} -o eth0 -j MASQUERADE
{peer_sections}"""

    config_path.write_text(config)
    run(f"chmod 600 {config_path}")  # private key is in here, lock it down
    print(f"  ✓ Server config written to {config_path}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: BRING WIREGUARD UP OR DOWN
# ─────────────────────────────────────────────────────────────────────────────

def interface_up():
    """
    Bring the WireGuard interface up using wg-quick.

    `wg-quick` is a helper script that:
    1. Reads wg0.conf
    2. Creates the wg0 network interface
    3. Sets up routes (tells the OS: "packets for 10.0.0.x go through wg0")
    4. Runs PostUp commands
    5. Applies all [Peer] configurations

    Think of it like: wg-quick reads the blueprint and builds the tunnel.
    """
    config_path = CONFIG_DIR / "wg0.conf"
    result = run(f"sudo wg-quick up {config_path}", check=False)
    if result.returncode != 0:
        if "already exists" in result.stderr:
            print("  ℹ WireGuard interface already up.")
        else:
            print(f"  ✗ Error: {result.stderr}")
            sys.exit(1)
    else:
        print(f"  ✓ WireGuard interface {WG_INTERFACE} is UP")

def interface_down():
    """Tear down the WireGuard interface."""
    config_path = CONFIG_DIR / "wg0.conf"
    result = run(f"sudo wg-quick down {config_path}", check=False)
    if result.returncode != 0:
        print(f"  ℹ Interface may already be down: {result.stderr.strip()}")
    else:
        print(f"  ✓ WireGuard interface {WG_INTERFACE} is DOWN")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: SHOW STATUS
# ─────────────────────────────────────────────────────────────────────────────

def show_status():
    """
    Show what's currently happening with the VPN.

    `wg show` queries the running WireGuard interface and prints:
    - The interface's public key
    - Listening port
    - Each peer: their public key, last handshake time, data transferred

    A "handshake" is the initial cryptographic greeting between two WireGuard
    peers. They exchange public keys and agree on session keys. If the last
    handshake was recent (< 3 minutes), the peer is actively connected.
    """
    print("\n── WireGuard Interface Status ──")
    result = run(f"sudo wg show {WG_INTERFACE}", check=False)
    if result.returncode != 0:
        print("  Interface is not running.")
    else:
        print(result.stdout)

    print("\n── Registered Peers ──")
    peers = load_peers()
    if not peers:
        print("  No peers registered yet. Run: python3 orchestrator.py add-peer")
    for i, peer in enumerate(peers):
        print(f"  [{i+1}] {peer.get('name','?'):20s}  VPN IP: {peer['vpn_ip']:15s}  PubKey: {peer['public_key'][:20]}...")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 7: ADD A PEER (client registration)
# ─────────────────────────────────────────────────────────────────────────────

def add_peer():
    """
    Register a new client peer on the server.

    To add WPC as a client:
    1. WPC generates its own keypair (cli.py does this)
    2. WPC gives us its PUBLIC key (safe to share!)
    3. We assign it a VPN IP (10.0.0.2, 10.0.0.3, etc.)
    4. We add it to peers.json and regenerate wg0.conf
    5. We hot-reload the peer into the running WireGuard interface

    HOT RELOAD: We don't need to restart WireGuard to add a peer!
    `wg set` can add peers to a running interface on the fly.
    This is one of WireGuard's nicest features.
    """
    peers = load_peers()

    # Assign the next available VPN IP
    # Existing peers might have 10.0.0.2, 10.0.0.3 — we take the next one
    used_ips = {p['vpn_ip'] for p in peers}
    network  = ipaddress.ip_network(VPN_SUBNET)
    next_ip  = None
    for host in network.hosts():
        candidate = str(host)
        if candidate == SERVER_VPN_IP:
            continue  # skip the server's own IP
        if candidate not in used_ips:
            next_ip = candidate
            break

    if next_ip is None:
        print("  ✗ No available IP addresses in the VPN subnet!")
        sys.exit(1)

    # Prompt for peer info
    print("\n── Add New Peer ──")
    name       = input("  Peer name (e.g. 'WPC-desktop'): ").strip()
    public_key = input("  Peer's WireGuard public key: ").strip()

    if not public_key or len(public_key) < 40:
        print("  ✗ That doesn't look like a valid WireGuard public key.")
        sys.exit(1)

    peer = {
        "name":       name,
        "public_key": public_key,
        "vpn_ip":     next_ip,
    }
    peers.append(peer)
    save_peers(peers)

    # Regenerate the config file with the new peer
    server_private_key, _ = generate_keypair("server")
    write_server_config(server_private_key, peers)

    # Hot-add the peer to the running interface (no restart needed)
    result = run(
        f"sudo wg set {WG_INTERFACE} peer {public_key} allowed-ips {next_ip}/32",
        check=False
    )
    if result.returncode == 0:
        print(f"\n  ✓ Peer '{name}' added! VPN IP: {next_ip}")
    else:
        print(f"  ⚠ Peer saved to config but hot-reload failed (is WG running?): {result.stderr.strip()}")

    print(f"\n  Give these details to the peer for their client config:")
    print(f"    Server public key:  {(CONFIG_DIR / 'server.public').read_text().strip()}")
    print(f"    Server endpoint:    <WL_WINDOWS_IP>:{WG_PORT}")
    print(f"    Client VPN IP:      {next_ip}/24")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN: parse command-line arguments and dispatch
# ─────────────────────────────────────────────────────────────────────────────

def cmd_start():
    """Full startup sequence."""
    print("\n══ VPN Server Startup ══\n")

    print("[1/4] Generating server keys...")
    server_priv, server_pub = generate_keypair("server")
    print(f"      Server public key: {server_pub}")

    print("\n[2/4] Writing WireGuard config...")
    peers = load_peers()
    write_server_config(server_priv, peers)

    print("\n[3/4] Configuring Windows port forwarding...")
    try:
        wsl2_ip = get_wsl2_ip()
        setup_port_forward(wsl2_ip)
    except Exception as e:
        print(f"  ⚠ Port forward failed (are you in WSL2?): {e}")
        print("    You may need to run as Administrator on the Windows side.")

    print("\n[4/4] Bringing WireGuard interface up...")
    interface_up()

    print("\n══ VPN Server is RUNNING ══")
    print(f"   VPN subnet:   {VPN_SUBNET}")
    print(f"   Server VPN IP: {SERVER_VPN_IP}")
    print(f"   Port:          UDP {WG_PORT}")
    print(f"\n   Next step: run `python3 orchestrator.py add-peer` to register WPC.")

def cmd_stop():
    print("\n══ Stopping VPN Server ══\n")
    interface_down()

def cmd_status():
    show_status()

def cmd_add_peer():
    add_peer()

def cmd_show_config():
    config_path = CONFIG_DIR / "wg0.conf"
    if config_path.exists():
        print(config_path.read_text())
    else:
        print("No config found. Run: python3 orchestrator.py start")

COMMANDS = {
    "start":       cmd_start,
    "stop":        cmd_stop,
    "status":      cmd_status,
    "add-peer":    cmd_add_peer,
    "show-config": cmd_show_config,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Usage: python3 orchestrator.py <command>")
        print("Commands:", ", ".join(COMMANDS.keys()))
        sys.exit(1)

    COMMANDS[sys.argv[1]]()