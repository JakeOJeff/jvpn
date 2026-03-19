## Structure




## Setup

### NixOS Setup


Copy the Configuration to Nix
```bash
cp configuration.nix /etc/nixos/configuration.nix
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

