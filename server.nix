# server.nix — NixOS configuration for the WireGuard VPN server
#
# ─────────────────────────────────────────────────────────────────────────────
# WHAT IS NIX / NIXOS?
# ─────────────────────────────────────────────────────────────────────────────
#
# Normally, to set up a Linux server you would:
#   1. Type `apt install wireguard` (install the software)
#   2. Edit /etc/wireguard/wg0.conf (configure it)
#   3. Run `systemctl enable wg-quick@wg0` (make it start on boot)
#   4. Edit /etc/sysctl.conf (enable IP forwarding)
#   ... and hope you remember all of this when you need to rebuild the server.
#
# With NixOS, you write ONE file (this file) that DECLARES the entire desired
# state of the system. NixOS reads it and makes reality match the declaration.
# If you delete a line, NixOS removes that thing. If you add a line, NixOS
# installs that thing. It's like version-controlling your entire server setup.
#
# The Nix language itself looks a bit like JSON but with functions and imports.
# `{ config, pkgs, ... }:` — this is a function. NixOS calls it with the
# current system config and package set. We return an "attribute set" (like
# a dictionary) describing what we want.
#
# ─────────────────────────────────────────────────────────────────────────────
# HOW TO USE THIS FILE
# ─────────────────────────────────────────────────────────────────────────────
#
# 1. Install NixOS in WSL2:
#    - Download the NixOS WSL tarball from https://github.com/nix-community/NixOS-WSL
#    - Import it: wsl --import NixOS C:\NixOS nixos-wsl.tar.gz
#    - Launch: wsl -d NixOS
#
# 2. Copy this file to /etc/nixos/configuration.nix
#    (or import it from your main configuration.nix)
#
# 3. Run: sudo nixos-rebuild switch
#    NixOS will install WireGuard, configure the service, and apply all settings.
#
# 4. Then run orchestrator.py to manage keys and peers.
#
# ─────────────────────────────────────────────────────────────────────────────

{ config, pkgs, lib, ... }:

{
  # ───────────────────────────────────────────────────────────────────────────
  # IMPORTS
  # You can split your config into multiple files and import them here.
  # For now everything is in one place.
  # ───────────────────────────────────────────────────────────────────────────
  imports = [ ];

  # ───────────────────────────────────────────────────────────────────────────
  # BOOT LOADER
  # WSL2 doesn't use a traditional bootloader (Windows boots it), but NixOS
  # still needs this declared. `systemd-boot` is a simple EFI bootloader.
  # ───────────────────────────────────────────────────────────────────────────
  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = true;

  # ───────────────────────────────────────────────────────────────────────────
  # WSL2 INTEGRATION
  # This enables NixOS-specific WSL2 compatibility shims.
  # ───────────────────────────────────────────────────────────────────────────
  wsl = {
    enable        = true;
    defaultUser   = "nixos";
    startMenuLaunchers = true;
  };

  # ───────────────────────────────────────────────────────────────────────────
  # NETWORKING
  # ───────────────────────────────────────────────────────────────────────────

  networking = {
    # The hostname is the "name" your machine announces on the network.
    hostName = "wl-vpn-server";

    # Enable the firewall. NixOS's firewall is a wrapper around iptables/nftables.
    # iptables is the Linux kernel's built-in packet filtering system.
    # Think of it as a bouncer at the door: each network packet gets checked
    # against a list of rules before being let in or out.
    firewall = {
      enable = true;

      # Open UDP port 51820 for WireGuard.
      # By default, NixOS's firewall drops all incoming traffic.
      # We explicitly allow port 51820 UDP here.
      allowedUDPPorts = [ 51820 ];

      # If you also need SSH access from the VPN, allow port 22 TCP.
      # allowedTCPPorts = [ 22 ];
    };

    # Enable IP forwarding at the kernel level.
    # WHY: When a VPN client (WPC at 10.0.0.2) sends a packet to the internet,
    # it arrives at the server addressed to some external IP. Without IP
    # forwarding, Linux says "that's not for me" and drops it. With forwarding
    # enabled, Linux routes it onward — acting as a router.
    # This is the same setting as `sysctl net.ipv4.ip_forward=1`.
    enableIPv4Forwarding = true;
    enableIPv6Forwarding = false; # Keep simple for now
  };

  # ───────────────────────────────────────────────────────────────────────────
  # PACKAGES
  # `pkgs` is the NixOS package set — a massive collection of software
  # (80,000+ packages) all expressed as Nix derivations (build recipes).
  #
  # Installing software in NixOS means adding it to this list.
  # NixOS will download, verify, and install each package.
  # Removing from the list uninstalls it on the next `nixos-rebuild switch`.
  # ───────────────────────────────────────────────────────────────────────────
  environment.systemPackages = with pkgs; [
    # WireGuard tools: the `wg` and `wg-quick` commands
    # `wg` manages interfaces; `wg-quick` is a helper that reads .conf files
    wireguard-tools

    # General networking utilities (useful for debugging)
    iproute2     # ip addr, ip route — the modern Linux networking toolkit
    iptables     # packet filtering rules (used for NAT masquerade)
    tcpdump      # packet sniffer — see actual network traffic in real time
    nmap         # network scanner — check if ports are open
    curl         # HTTP client — test connectivity
    jq           # JSON processor — handy for parsing API responses

    # Python 3 with the packages orchestrator.py needs
    # `python3.withPackages` creates a Python environment with specified libraries
    (python3.withPackages (ps: with ps; [
      # No external deps needed for orchestrator.py!
      # All imports (subprocess, os, sys, json, ipaddress, pathlib) are stdlib.
    ]))

    # Text editors for editing configs
    vim
    nano

    # Git — version control. Good to have for managing your config files.
    git
  ];

  # ───────────────────────────────────────────────────────────────────────────
  # WIREGUARD SERVICE
  #
  # NixOS has built-in WireGuard support via `networking.wireguard.interfaces`.
  # However, we're using orchestrator.py to manage the wg-quick config file
  # dynamically (because peers change, keys are generated at runtime).
  #
  # So here we do the ENVIRONMENT setup (kernel module, IP forwarding, firewall)
  # and let orchestrator.py handle the actual wg-quick up/down.
  #
  # If you wanted fully declarative WireGuard (keys hardcoded in Nix), it
  # would look like this (shown for education — we don't use this approach):
  #
  #   networking.wireguard.interfaces.wg0 = {
  #     ips = [ "10.0.0.1/24" ];
  #     listenPort = 51820;
  #     privateKeyFile = "/etc/wireguard/server.private";
  #     peers = [
  #       {
  #         publicKey = "CLIENT_PUBLIC_KEY_HERE";
  #         allowedIPs = [ "10.0.0.2/32" ];
  #       }
  #     ];
  #   };
  #
  # We skip this because hardcoding keys in a config file is awkward when
  # peers change dynamically. orchestrator.py manages this better.
  # ───────────────────────────────────────────────────────────────────────────

  # Load the WireGuard kernel module at boot.
  # A kernel module is a piece of code that extends what the kernel can do.
  # WireGuard is built into modern Linux kernels (5.6+), but loading it
  # explicitly here ensures it's available immediately.
  boot.kernelModules = [ "wireguard" ];

  # ───────────────────────────────────────────────────────────────────────────
  # SYSTEMD SERVICE: orchestrator auto-start
  #
  # systemd is Linux's init system and service manager.
  # "init system" means: it's the first process that starts when Linux boots,
  # and it's responsible for starting everything else.
  # A "service" is a background process that systemd manages (start, stop,
  # restart on failure, etc.)
  #
  # We define a custom service that runs orchestrator.py on boot.
  # ───────────────────────────────────────────────────────────────────────────
  systemd.services.vpn-orchestrator = {
    description = "WireGuard VPN Orchestrator";

    # Start this service after the network is up.
    # `network-online.target` is a systemd "target" — a milestone that
    # represents "the network is fully configured and ready."
    after    = [ "network-online.target" ];
    wants    = [ "network-online.target" ];

    # `wantedBy = multi-user.target` means: start this service in normal
    # multi-user mode (i.e., after a normal boot, not just recovery mode).
    wantedBy = [ "multi-user.target" ];

    serviceConfig = {
      Type       = "oneshot";        # run once, don't keep running in background
      RemainAfterExit = true;        # systemd considers it "active" after it exits
      User       = "root";           # needs root to configure network interfaces
      WorkingDirectory = "/root";

      # The actual command to run.
      # ${pkgs.python3} gives the Nix store path to Python 3.
      ExecStart  = "${pkgs.python3}/bin/python3 /etc/vpn/orchestrator.py start";
      ExecStop   = "${pkgs.python3}/bin/python3 /etc/vpn/orchestrator.py stop";

      # Restart policy: if it fails, wait 10 seconds and try again, up to 3 times.
      Restart    = "on-failure";
      RestartSec = "10s";
    };
  };

  # ───────────────────────────────────────────────────────────────────────────
  # USER ACCOUNTS
  # ───────────────────────────────────────────────────────────────────────────

  users.users.nixos = {
    isNormalUser = true;
    home         = "/home/nixos";
    # `wheel` group = sudo access
    # `networkmanager` = manage network connections
    extraGroups  = [ "wheel" "networkmanager" ];
    # In production, use SSH keys instead of passwords:
    # openssh.authorizedKeys.keys = [ "ssh-ed25519 AAAA..." ];
  };

  # Allow wheel group members to use sudo without a password.
  # In production you'd want a password, but for development this is convenient.
  security.sudo.wheelNeedsPassword = false;

  # ───────────────────────────────────────────────────────────────────────────
  # SSH SERVER (optional but highly recommended)
  # Lets you connect to WL from WPC via terminal once the VPN is up.
  # ───────────────────────────────────────────────────────────────────────────
  services.openssh = {
    enable       = true;
    ports        = [ 22 ];
    settings = {
      PermitRootLogin    = "no";   # never allow direct root SSH login
      PasswordAuthentication = true; # set to false once you have SSH keys set up
    };
  };

  # ───────────────────────────────────────────────────────────────────────────
  # NIX SETTINGS
  # ───────────────────────────────────────────────────────────────────────────

  # Nix flakes are an experimental but widely-used feature that provides
  # reproducible builds with locked dependency versions (like package-lock.json
  # for Nix). We'll use this when we add the Rust component.
  nix.settings.experimental-features = [ "nix-command" "flakes" ];

  # Automatically remove old package generations to save disk space.
  # Each `nixos-rebuild switch` creates a new "generation" — a snapshot of
  # the system. Old generations are kept for rollback. This removes ones
  # older than 30 days.
  nix.gc = {
    automatic  = true;
    dates      = "weekly";
    options    = "--delete-older-than 30d";
  };

  # NixOS version. Don't change this without reading the upgrade notes.
  system.stateVersion = "24.05";
}
