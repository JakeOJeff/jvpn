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

  system.stateVersion = "24.05";
}
