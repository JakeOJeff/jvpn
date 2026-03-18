# server.nix
# ──────────────────────────────────────────────────────────────────────────────
# NixOS configuration for the VPN server.
# This is for when you move to a REAL Linux server (Hetzner, VPS, Mac Mini).
# Not used for the Windows/WSL2 setup — that uses setup-server.sh instead.
#
# Deploy to a NixOS machine:
#   scp server.nix root@SERVER_IP:/etc/nixos/configuration.nix
#   ssh root@SERVER_IP "nixos-rebuild switch"
#
# First time on a fresh server:
#   ssh root@SERVER_IP
#   mkdir -p /etc/wireguard && chmod 700 /etc/wireguard
#   wg genkey > /etc/wireguard/private.key && chmod 600 /etc/wireguard/private.key
#   echo '{}' > /etc/wireguard/peers.json
#   mkdir -p /opt/vpn && cp orchestrator.py /opt/vpn/
# ──────────────────────────────────────────────────────────────────────────────

{ config, pkgs, ... }:

{
  system.stateVersion = "24.05";

  # ── IP forwarding ────────────────────────────────────────────────────────────
  # Without this the kernel drops forwarded packets — VPN won't work
  boot.kernel.sysctl = {
    "net.ipv4.ip_forward"          = 1;
    "net.ipv6.conf.all.forwarding" = 1;
  };

  # ── NAT ──────────────────────────────────────────────────────────────────────
  # Rewrites VPN client IPs to server's public IP when forwarding to internet
  # Client traffic appears to come from the server — that's the VPN effect
  networking.nat = {
    enable             = true;
    externalInterface  = "eth0";     # ← change to your server's main interface
                                     #   check with: ip link show
    internalInterfaces = [ "wg0" ];
  };

  # ── Firewall ─────────────────────────────────────────────────────────────────
  networking.firewall = {
    enable          = true;
    allowedTCPPorts = [ 22 8080 ];   # SSH + orchestrator API
    allowedUDPPorts = [ 51820 ];     # WireGuard tunnel
  };

  # ── WireGuard server interface ───────────────────────────────────────────────
  networking.wireguard.interfaces.wg0 = {
    ips        = [ "10.0.0.1/24" ];  # server is always .1
    listenPort = 51820;

    # private key lives outside nix store so it's not world-readable
    privateKeyFile = "/etc/wireguard/private.key";

    # peers are managed dynamically by orchestrator.py at runtime
    # no need to hardcode them here
    peers = [];
  };

  # ── Packages ─────────────────────────────────────────────────────────────────
  environment.systemPackages = with pkgs; [
    wireguard-tools
    python3
    python3Packages.pip
    curl
    htop
  ];

  # ── SSH ───────────────────────────────────────────────────────────────────────
  services.openssh = {
    enable   = true;
    settings = {
      PasswordAuthentication = false;  # keys only
      PermitRootLogin        = "prohibit-password";
    };
  };

  # ── Orchestrator service ──────────────────────────────────────────────────────
  # Runs orchestrator.py as a background service
  # Starts automatically on boot, restarts on crash
  systemd.services.vpn-orchestrator = {
    description = "VPN peer orchestrator";
    after       = [ "network.target" "wireguard-wg0.service" ];
    wantedBy    = [ "multi-user.target" ];

    serviceConfig = {
      ExecStart        = "${pkgs.python3}/bin/python3 /opt/vpn/orchestrator.py";
      Restart          = "always";
      RestartSec       = "3s";
      User             = "root";          # needs wg set access
      WorkingDirectory = "/opt/vpn";
    };
  };
}
