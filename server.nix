{ config, pkgs, ... }:

{
  system.stateVersion = "23.11";

  networking = {
    firewall.allowedTCPPorts = [ 5555 ];
    firewall.allowedUDPPorts = [ 5555 ];
  };

  boot.kernel.sysctl = {
    "net.ipv4.ip_forward" = 1;
  };

  environment.systemPackages = with pkgs; [
    python3
    python3Packages.pip
  ];

  systemd.services.vpn-server = {
    description = "VPN Server";
    after = [ "network.target" ];
    wantedBy = [ "multi-user.target" ];
    
    serviceConfig = {
      Type = "simple";
      ExecStart = "${pkgs.python3}/bin/python3 /opt/vpn/orchestrator.py";
      Restart = "on-failure";
    };
  };
}
