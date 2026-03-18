#!/usr/bin/env python3
import json
import subprocess
import argparse
from pathlib import Path

class WireGuardClient:
    def __init__(self, server_ip, server_port=51820):
        self.server_ip = server_ip
        self.server_port = server_port
        self.config_dir = Path.home() / '.wg_client'
        self.config_dir.mkdir(exist_ok=True)

    def create_config(self, config_data):
        """Create WireGuard client config"""
        config = f"""[Interface]
Address = {config_data['client_ip']}/24
PrivateKey = {config_data['client_private_key']}
DNS = 8.8.8.8, 8.8.4.4

[Peer]
PublicKey = {config_data['server_public_key']}
Endpoint = {self.server_ip}:{self.server_port}
AllowedIPs = 10.0.0.0/24
PersistentKeepalive = 25
"""
        return config

    def save_config(self, config_data):
        """Save config to file"""
        client_name = config_data['client_name']
        config = self.create_config(config_data)
        
        config_file = self.config_dir / f'{client_name}.conf'
        with open(config_file, 'w') as f:
            f.write(config)
        
        # Set permissions
        config_file.chmod(0o600)
        
        print(f"[+] Config saved to {config_file}")
        print(f"\n[*] WireGuard Configuration:\n{config}")
        
        return str(config_file)

    def import_config(self, config_json):
        """Import config from JSON"""
        try:
            config_data = json.loads(config_json)
            config_file = self.save_config(config_data)
            
            print(f"\n[+] To connect on Windows:")
            print(f"    1. Open WireGuard")
            print(f"    2. Click 'Add Tunnel' > 'Import tunnel(s) from file'")
            print(f"    3. Select: {config_file}")
            print(f"    4. Click 'Activate'")
            
            print(f"\n[+] To connect on Linux:")
            print(f"    sudo wg-quick up {config_data['client_name']}")
            
            return True
        except json.JSONDecodeError as e:
            print(f"[-] Invalid JSON: {e}")
            return False

    def display_instructions(self, server_ip):
        """Display connection instructions"""
        print(f"""
╔═════════════════════════════════════════╗
║  WireGuard Client Setup Instructions    ║
╚═════════════════════════════════════════╝

1. On the SERVER (laptop), add a client:
   python3 orchestrator.py --add-client mypc

2. Copy the JSON output from the server

3. On this PC, run:
   python cli.py --server {server_ip} --import <paste-json-here>

4. Or save JSON to file and run:
   python cli.py --server {server_ip} --import-file config.json

5. Open WireGuard app on Windows and import the generated config

6. Click "Activate" to connect!
""")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='WireGuard Client')
    parser.add_argument('--server', required=True, help='Server IP address')
    parser.add_argument('--port', type=int, default=51820, help='Server port')
    parser.add_argument('--import', dest='import_json', help='Import config from JSON string')
    parser.add_argument('--import-file', help='Import config from JSON file')
    parser.add_argument('--instructions', action='store_true', help='Show setup instructions')
    
    args = parser.parse_args()
    
    client = WireGuardClient(args.server, args.port)
    
    if args.instructions:
        client.display_instructions(args.server)
    elif args.import_file:
        with open(args.import_file) as f:
            config_json = f.read()
        client.import_config(config_json)
    elif args.import_json:
        client.import_config(args.import_json)
    else:
        client.display_instructions(args.server)