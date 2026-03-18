{ config, pkgs, ... }:

{
  system.stateVersion = "23.11";

  # Enable IP forwarding for WireGuard
  networking = {
    firewall.allowedUDPPorts = [ 51820 ];
    nat = {
      enable = true;
      internalInterfaces = [ "wg0" ];
      externalInterface = "eth0";
    };
  };

  boot.kernel.sysctl = {
    "net.ipv4.ip_forward" = 1;
  };

  environment.systemPackages = with pkgs; [
    python3
    python3Packages.pip
    wireguard-tools
  ];

  # Enable WireGuard
  networking.wireguard.interfaces.wg0 = {
    ips = [ "10.0.0.1/24" ];
    listenPort = 51820;
    privateKeyFile = "/etc/wireguard/private.key";
  };

  systemd.services.vpn-server = {
    description = "WireGuard VPN Server";
    after = [ "network.target" ];
    wantedBy = [ "multi-user.target" ];
    
    serviceConfig = {
      Type = "simple";
      ExecStart = "${pkgs.python3}/bin/python3 /opt/vpn/orchestrator.py";
      Restart = "on-failure";
    };
  };
}
