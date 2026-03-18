#!/usr/bin/env python3
import subprocess
import os
import json
from pathlib import Path

class WireGuardServer:
    def __init__(self, interface='wg0', port=51820, subnet='10.0.0'):
        self.interface = interface
        self.port = port
        self.subnet = subnet
        self.config_dir = Path('/etc/wireguard')
        self.keys_dir = Path.home() / '.wg_keys'
        self.clients_file = self.keys_dir / 'clients.json'
        self.next_client_ip = 2
        
        self.keys_dir.mkdir(exist_ok=True)

    def run_cmd(self, cmd):
        """Run shell command"""
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return result.stdout.strip(), result.returncode
        except Exception as e:
            print(f"[-] Error: {e}")
            return "", 1

    def generate_keys(self):
        """Generate WireGuard keys"""
        print("[*] Generating WireGuard keys...")
        
        # Server keys
        self.run_cmd(f"wg genkey | tee {self.keys_dir}/server_private.key | wg pubkey > {self.keys_dir}/server_public.key")
        
        with open(f"{self.keys_dir}/server_private.key") as f:
            self.server_private = f.read().strip()
        with open(f"{self.keys_dir}/server_public.key") as f:
            self.server_public = f.read().strip()
        
        print(f"[+] Server public key: {self.server_public}")

    def generate_client_keys(self, client_name):
        """Generate client keys"""
        print(f"[*] Generating keys for {client_name}...")
        
        self.run_cmd(f"wg genkey | tee {self.keys_dir}/{client_name}_private.key | wg pubkey > {self.keys_dir}/{client_name}_public.key")
        
        with open(f"{self.keys_dir}/{client_name}_private.key") as f:
            client_private = f.read().strip()
        with open(f"{self.keys_dir}/{client_name}_public.key") as f:
            client_public = f.read().strip()
        
        return client_private, client_public

    def assign_client_ip(self):
        """Assign unique IP to client"""
        ip = f"{self.subnet}.{self.next_client_ip}"
        self.next_client_ip += 1
        return ip

    def add_client(self, client_name):
        """Add new client and return config"""
        client_ip = self.assign_client_ip()
        client_private, client_public = self.generate_client_keys(client_name)
        
        # Save to clients.json
        clients = {}
        if self.clients_file.exists():
            with open(self.clients_file) as f:
                clients = json.load(f)
        
        clients[client_name] = {
            'ip': client_ip,
            'public_key': client_public
        }
        
        with open(self.clients_file, 'w') as f:
            json.dump(clients, f, indent=2)
        
        print(f"[+] Client {client_name} added with IP {client_ip}")
        
        return {
            'client_name': client_name,
            'client_ip': client_ip,
            'client_private_key': client_private,
            'server_public_key': self.server_public,
            'server_ip': f"{self.subnet}.1"
        }

    def create_server_config(self):
        """Create WireGuard server config"""
        print("[*] Creating WireGuard server config...")
        
        # Load existing clients
        peers = ""
        if self.clients_file.exists():
            with open(self.clients_file) as f:
                clients = json.load(f)
            
            for client_name, client_data in clients.items():
                peers += f"""
[Peer]
PublicKey = {client_data['public_key']}
AllowedIPs = {client_data['ip']}/32
"""
        
        config = f"""[Interface]
Address = {self.subnet}.1/24
ListenPort = {self.port}
PrivateKey = {self.server_private}
SaveCounter = true
{peers}"""
        
        return config

    def setup_server(self):
        """Setup WireGuard server"""
        print("[*] Setting up WireGuard server...")
        
        # Generate keys if not exist
        if not (self.keys_dir / 'server_private.key').exists():
            self.generate_keys()
        else:
            with open(f"{self.keys_dir}/server_private.key") as f:
                self.server_private = f.read().strip()
            with open(f"{self.keys_dir}/server_public.key") as f:
                self.server_public = f.read().strip()
        
        # Create config
        config = self.create_server_config()
        
        # Write config
        config_path = self.config_dir / f'{self.interface}.conf'
        self.run_cmd(f"sudo tee {config_path} > /dev/null << 'EOF'\n{config}\nEOF")
        self.run_cmd(f"sudo chmod 600 {config_path}")
        
        print(f"[+] Config written to {config_path}")
        
        # Start interface
        self.run_cmd(f"sudo wg-quick up {self.interface}")
        
        # Check status
        output, _ = self.run_cmd(f"sudo wg show")
        print(f"\n[+] WireGuard Status:\n{output}")

    def start(self):
        """Start server"""
        self.setup_server()
        
        print(f"\n[+] WireGuard server running on port {self.port}")
        print(f"[+] Server public key: {self.server_public}")
        print("[*] Waiting for clients...")
        
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[*] Shutting down...")
            self.run_cmd(f"sudo wg-quick down {self.interface}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='WireGuard VPN Server')
    parser.add_argument('--interface', default='wg0', help='Interface name')
    parser.add_argument('--port', type=int, default=51820, help='Listen port')
    parser.add_argument('--subnet', default='10.0.0', help='Subnet (10.0.0)')
    parser.add_argument('--add-client', help='Add client by name')
    
    args = parser.parse_args()
    
    server = WireGuardServer(interface=args.interface, port=args.port, subnet=args.subnet)
    
    if args.add_client:
        config = server.add_client(args.add_client)
        print(json.dumps(config, indent=2))
    else:
        server.start()