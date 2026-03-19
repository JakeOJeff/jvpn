## Structure




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

