# jvpn — WireGuard VPN

## Structure

```
WPC (Windows PC)          Internet / LAN          WL (Windows Laptop)
─────────────────                                 ─────────────────────
  cli.py                                          orchestrator.py
  WireGuard client   ←── encrypted UDP ──→        WireGuard (native Windows)
  10.0.0.2/24                                     10.0.0.1/24
                                                  (keys managed by WSL2/NixOS)
```

> **Important:** WireGuard runs natively on Windows on WL — NOT inside WSL2.
> WSL2/NixOS is used for key management and orchestration only.
> Running WireGuard inside WSL2 makes it unreachable from outside due to
> Hyper-V double-NAT — UDP packets cannot pass through regardless of firewall
> or port forwarding settings. See [Why Not WSL2?](#why-not-wsl2) for the full explanation.

---

## Prerequisites

### On WL (Windows Laptop — the server)

1. **Install WSL2:**
   ```powershell
   # In PowerShell as Administrator
   wsl --install
   ```
   Restart after.

2. **Install NixOS in WSL2:**
   - Download the `.wsl` file from https://github.com/nix-community/NixOS-WSL/releases
   - Import it (use `.wsl` extension, not `.tar.gz`):
     ```powershell
     wsl --import NixOS C:\NixOS .\nixos.wsl --version 2
     ```
   - Launch:
     ```powershell
     wsl -d NixOS
     # If that fails:
     wsl -d NixOS --user nixos
     ```

3. **Install WireGuard for Windows on WL:**
   - https://www.wireguard.com/install/
   - This is where the server tunnel actually runs

### On WPC (Windows PC — the client)

1. **Install Python 3:** https://python.org/downloads
   - Check "Add Python to PATH" during install

2. **Install WireGuard for Windows:** https://www.wireguard.com/install/

3. **Always run PowerShell as Administrator** for VPN commands

---

## NixOS Setup (WSL2 on WL)

### Step 1 — Write the configuration

Do NOT replace the existing `configuration.nix` wholesale — it will break
the WSL module import. Instead run this to write the correct config:

```bash
sudo tee /etc/nixos/configuration.nix << 'EOF'
{ config, pkgs, lib, ... }:
{
  imports = [
    <nixos-wsl/modules>
  ];

  wsl = {
    enable      = true;
    defaultUser = "nixos";
  };

  networking = {
    hostName = "wl-vpn-server";
    firewall = {
      enable          = true;
      allowedUDPPorts = [ 51820 ];
    };
  };

  boot.kernel.sysctl = {
    "net.ipv4.ip_forward" = 1;
  };

  boot.kernelModules = [ "wireguard" ];

  environment.systemPackages = with pkgs; [
    wireguard-tools
    iproute2
    iptables
    tcpdump
    curl
    git
    python3
    vim
    nano
    socat
  ];

  services.openssh = {
    enable = true;
    settings = {
      PermitRootLogin        = "no";
      PasswordAuthentication = true;
    };
  };

  security.sudo.wheelNeedsPassword = false;

  nix.settings.experimental-features = [ "nix-command" "flakes" ];

  nix.gc = {
    automatic = true;
    dates     = "weekly";
    options   = "--delete-older-than 30d";
  };

  system.stateVersion = "25.05";
}
EOF
```

### Step 2 — Add the correct NixOS channel

NixOS-WSL releases track nixos-unstable. Using an older channel (e.g. 24.05)
causes `hardware.graphics option does not exist` errors because the WSL module
is newer than the channel.

```bash
sudo nix-channel --add https://nixos.org/channels/nixos-unstable nixos
sudo nix-channel --update
```

### Step 3 — Rebuild

```bash
sudo nixos-rebuild switch
```

### Step 4 — Verify

```bash
wg --version
python3 --version
cat /proc/sys/net/ipv4/ip_forward   # should print 1
git --version
```

---

## Setup Walkthrough

### Step 1: Generate server keys (on WL in WSL2)

```bash
python3 orchestrator.py start
```

Output:
```
══ VPN Server Startup ══

[1/4] Generating server keys...
      Server public key: abc123XYZsomeLongBase64String=
...
```

> The orchestrator will warn that Windows port forwarding failed — that is
> expected and fine. WireGuard runs natively on Windows now, not in WSL2.
> The key generation and config writing steps are what matter here.

**Copy the server public key.**

Find WL's Windows IP:
```powershell
ipconfig
# Look for IPv4 Address under WiFi or Ethernet — e.g. 192.168.1.40
# Ignore the 172.x.x.x address — that is the WSL2 internal IP, WPC cannot reach it
```

---

### Step 2: Initialize the client on WPC

Open PowerShell **as Administrator** on WPC:

```powershell
python cli.py init
```

Output:
```
Your WPC public key:

    XYZabc789anotherLongBase64String=
```

**Copy WPC's public key.**

---

### Step 3: Register WPC as a peer (on WL in WSL2)

```bash
python3 orchestrator.py add-peer
```

- **Peer name:** e.g. `WPC-desktop`
- **Peer's public key:** paste WPC's key from Step 2

Output:
```
  ✓ Peer added! VPN IP: 10.0.0.2

  Give these details to the peer:
    Server public key:  abc123XYZsomeLongBase64String=
    Server endpoint:    192.168.1.40:51820
    Client VPN IP:      10.0.0.2/24
```

---

### Step 4: Set up the Windows WireGuard server on WL

Get the generated server config from WSL2:
```bash
cat ~/.wg-vpn/wg0.conf
```

Copy the contents. On Windows on WL:
- Open the WireGuard app
- Click **Add Tunnel** → **Add empty tunnel**
- Paste the config → Save → **Activate**

The tunnel is now listening directly on `192.168.1.40:51820` with no WSL2
involved and no port forwarding needed.

---

### Step 5: Configure cli.py on WPC

Open `cli.py` and fill in the three lines at the top:

```python
SERVER_ENDPOINT   = "192.168.1.40"                        # WL's Windows IP
SERVER_PUBLIC_KEY = "abc123XYZsomeLongBase64String="       # from Step 1
CLIENT_VPN_IP     = "10.0.0.2"                            # from Step 3
```

> Set `SERVER_ENDPOINT` to just the IP — no port, no trailing characters.
> The port is appended automatically. Writing `192.168.1.40:51820` here
> will produce a broken endpoint like `192.168.1.40:51820:51820`.

---

### Step 6: Connect

```powershell
python cli.py connect
```

Expected output:
```
══ Connecting to VPN ══

[1/3] Preparing client configuration...
  ✓ Client config written to C:\Users\You\.wg-vpn\wg0-client.conf

[2/3] Bringing WireGuard tunnel up...
  ✓ WireGuard tunnel is UP

[3/3] Verifying connection...
  ✓ Connected! VPN server (10.0.0.1) is reachable.
  ✓ Your VPN IP: 10.0.0.2
```

---

## Daily Usage

On WPC:
```powershell
python cli.py connect
python cli.py disconnect
python cli.py status
python cli.py ping
```

On WL (WSL2):
```bash
python3 orchestrator.py status
python3 orchestrator.py add-peer
python3 orchestrator.py stop
```

---

## Troubleshooting

### NixOS rebuild: `option does not exist` errors

**`networking.enableIPv4Forwarding does not exist`**
This option was removed in newer NixOS. Use:
```nix
boot.kernel.sysctl = { "net.ipv4.ip_forward" = 1; };
```

**`wsl option does not exist`**
You replaced `configuration.nix` without keeping the WSL module import.
The `wsl { }` block only works if `<nixos-wsl/modules>` is in your imports.
Make sure your config starts with:
```nix
imports = [ <nixos-wsl/modules> ];
```
Never use `imports = [ ];` on NixOS-WSL.

**`hardware.graphics option does not exist`**
Your nixpkgs channel is too old for the NixOS-WSL version you installed.
NixOS-WSL 25.x requires nixos-unstable:
```bash
sudo nix-channel --add https://nixos.org/channels/nixos-unstable nixos
sudo nix-channel --update
sudo nixos-rebuild switch
```

**`[Errno 13] Permission denied: 'git'`**
The nixpkgs channel is missing entirely. Run:
```bash
sudo nix-channel --list
sudo nix-channel --update
sudo nixos-rebuild switch
```

---

### WireGuard / cli.py errors

**`wg-quick is not recognized`**
`wg-quick` is Linux-only and does not exist on Windows. The updated `cli.py`
uses `wireguard.exe /installtunnel` instead, which is the correct Windows
equivalent. If `wg` itself is missing, reinstall WireGuard for Windows and
restart your terminal.

**Endpoint has double port: `192.168.1.40:51820:51820`**
You included `:51820` in the `SERVER_ENDPOINT` string in `cli.py`.
Set it to just the IP:
```python
SERVER_ENDPOINT = "192.168.1.40"   # correct
SERVER_ENDPOINT = "192.168.1.40:51820"  # wrong — produces double port
```

**`Access denied` / permission errors**
Run PowerShell as Administrator. WireGuard needs admin rights to create
network interfaces on Windows.

---

### Tunnel up but ping fails / handshake never completes

**Symptoms:**
- `wg show` shows no `latest handshake`
- `tcpdump -i eth0 udp port 51820` shows no packets arriving in WSL2
- WPC sends packets but WSL2 never receives them

**This is the WSL2 inbound UDP problem.** The fix is running WireGuard
natively on Windows (Setup Step 4). Do not try to run WireGuard inside WSL2
as a server — it cannot receive inbound connections from outside.

**Why turning off Windows Firewall does not help:**
The Hyper-V firewall on `vEthernet (WSL)` is separate from Windows Firewall.
`netsh advfirewall set allprofiles state off` does not touch it.

**Why `netsh portproxy` does not help:**
`netsh interface portproxy` is TCP-only. It accepts the command and reports
`Ok.` but silently drops all UDP packets. WireGuard is pure UDP so portproxy
never forwards a single byte.

---

### Can connect but cannot browse the internet

The NAT masquerade rule is missing. Check on WL in WSL2:
```bash
sudo iptables -t nat -L POSTROUTING
# Should show a MASQUERADE rule for 10.0.0.0/24
```
If missing:
```bash
python3 orchestrator.py stop
python3 orchestrator.py start
```

---

### WSL2 IP changed after reboot

Normal — WSL2 gets a new `172.x.x.x` IP from Hyper-V on every restart.
Since WireGuard now runs natively on Windows this does not affect the VPN.
If the orchestrator needs updating:
```bash
python3 orchestrator.py stop
python3 orchestrator.py start
```

---

## Why Not WSL2?

We originally planned to run WireGuard inside WSL2. Here is exactly why
that does not work:

```
WPC sends UDP to 192.168.1.40:51820
         ↓
Windows receives it  ✓
         ↓
netsh portproxy tries to forward  ✗  TCP only — drops UDP silently
         ↓
Hyper-V firewall on vEthernet (WSL)  ✗  separate from Windows Firewall
         ↓
WSL2 double-NAT  ✗  inbound UDP does not survive two NAT layers
         ↓
WireGuard in WSL2 never sees the packet
```

Confirmed with a raw UDP test — WPC sent 5 bytes to `192.168.1.40:51820`,
WSL2 received nothing, even with Windows Firewall completely disabled.

WSL2 is excellent for dev tools, key management, and running orchestrator.py.
It is not suitable as a server for inbound UDP connections.

---

## File Structure

```
~/.wg-vpn/               (created automatically by orchestrator.py)
├── server.private       # server private key — NEVER share or commit
├── server.public        # server public key — safe to share
├── client.private       # client private key — NEVER share or commit
├── client.public        # client public key — share with server
├── wg0.conf             # server WireGuard config
├── wg0-client.conf      # client WireGuard config
└── peers.json           # registered peer list
```

`.gitignore` must contain:
```
.wg-vpn/
*.conf
*.private
peers.json
```

