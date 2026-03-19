## Structure

```
WPC (Windows PC)          Internet / LAN          WL (Windows Laptop)
─────────────────                                 ─────────────────────
  cli.py                                          orchestrator.py
  WireGuard client   ←── encrypted UDP ──→        WireGuard server
  10.0.0.2/24                                     10.0.0.1/24
                                                  (running in WSL2/NixOS)
```



## Setup

### NixOS Setup


Copy the Configuration to Nix
```bash
cp configuration.nix /etc/nixos/configuration.nix
```

Or 

```bash
sudo tee /etc/nixos/configuration.nix << 'EOF'
{ config, pkgs, lib, ... }:

{
  imports = [
    <nixos-wsl/modules>
  ];

  # WSL2 integration — works because nixos-wsl/modules defines this option
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

  system.stateVersion = "24.05";
}
EOF
```


Add Latest NixOS Channel
```bash
sudo nix-channel --add https://nixos.org/channels/nixos-unstable nixos
```

Check/Add Latest Updates
```bash
sudo nix-channel --update
```

Rebuild NixOS with Latest Configuration
```bash
sudo nixos-rebuild switch
```

For Stable version, use 25.05 ( Unverified )
```bash
sudo nix-channel --add https://nixos.org/channels/nixos-25.05 nixos
sudo nix-channel --update
sudo nixos-rebuild switch
```

### Routine Check/Verification

```bash
# WireGuard tools are installed
wg --version

# Python is there
python3 --version

# IP forwarding is enabled (should print 1)
cat /proc/sys/net/ipv4/ip_forward

# Git is there
git --version
```

## Setup Walkthrough

### Step 1: Start the server on WL

Open WSL2 (NixOS) and run:
```bash
python3 orchestrator.py start
```

You'll see output like:
```
══ VPN Server Startup ══

[1/4] Generating server keys...
      Server public key: abc123XYZsomeLongBase64String=

[2/4] Writing WireGuard config...
[3/4] Configuring Windows port forwarding...
[4/4] Bringing WireGuard interface up...

══ VPN Server is RUNNING ══
```

**Copy the server public key — you'll need it on WPC.**

Also find WL's Windows IP address:
```powershell
# In a Windows PowerShell on WL:
ipconfig
# Look for "IPv4 Address" under your WiFi or Ethernet adapter
# Example: 192.168.1.42
```

---

### Step 2: Initialize the client on WPC

Open PowerShell **as Administrator** on WPC and run:
```powershell
python cli.py init
```

You'll see:
```
══ First-Time Setup ══

  ✓ Client keypair saved to C:\Users\You\.wg-vpn

Your WPC public key:

    XYZabc789anotherLongBase64String=
```

**Copy WPC's public key.**

---

### Step 3: Register WPC as a peer on the server

Back on WL (in WSL2), run:
```bash
python3 orchestrator.py add-peer
```

When asked:
- **Peer name**: type something like `WPC-desktop`
- **Peer's public key**: paste WPC's public key from Step 2

Output:
```
  ✓ Peer 'WPC-desktop' added! VPN IP: 10.0.0.2

  Give these details to the peer:
    Server public key:  abc123XYZsomeLongBase64String=
    Server endpoint:    192.168.1.42:51820
    Client VPN IP:      10.0.0.2/24
```

---

### Step 4: Configure cli.py on WPC

Open `cli.py` in a text editor and fill in the three lines near the top:

```python
SERVER_ENDPOINT  = "192.168.1.42"              # ← WL's Windows IP
SERVER_PUBLIC_KEY = "abc123XYZsomeLongBase64String="  # ← from Step 1
CLIENT_VPN_IP    = "10.0.0.2"                  # ← from Step 3
```

---

### Step 5: Connect!

On WPC (PowerShell as Administrator):
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

  ℹ All your internet traffic is now routed through WL.
```

---

## Daily Usage

```powershell
# Connect
python cli.py connect

# Check status
python cli.py status

# Disconnect
python cli.py disconnect

# Test latency through the tunnel
python cli.py ping
```

On the server:
```bash
# Check who's connected
python3 orchestrator.py status

# Add another device
python3 orchestrator.py add-peer

# Stop the server
python3 orchestrator.py stop
```

---

## Troubleshooting

### "wg-quick is not recognized"
WireGuard for Windows isn't installed or not in PATH.
Install from https://www.wireguard.com/install/ and restart your terminal.

### "Access denied" / permission errors
Run PowerShell as Administrator.

### Can connect but can't browse the internet
The server's NAT/iptables rule isn't working.
On WL in WSL2:
```bash
sudo iptables -t nat -L POSTROUTING
# Should show a MASQUERADE rule for 10.0.0.0/24
```

### Handshake never completes (0 bytes received)
Port forwarding isn't set up. Run:
```bash
python3 orchestrator.py start  # re-runs the netsh setup
```
Also check Windows Firewall on WL isn't blocking UDP 51820.

### WSL2 IP changed after reboot
Normal! Just restart the orchestrator:
```bash
python3 orchestrator.py stop
python3 orchestrator.py start
```
It detects the new WSL2 IP and updates the Windows port forwarding.

---

## File Structure

```
~/.wg-vpn/          (created automatically)
├── server.private  # server's private key (NEVER share)
├── server.public   # server's public key (safe to share)
├── client.private  # client's private key (NEVER share)
├── client.public   # client's public key (share with server)
├── wg0.conf        # server WireGuard config
├── wg0-client.conf # client WireGuard config
└── peers.json      # list of registered peers
```
