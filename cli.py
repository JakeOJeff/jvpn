#!/usr/bin/env python3
import socket
import json
import sys
import argparse

class VPNClient:
    def __init__(self, server, port):
        self.server = server
        self.port = port
        self.sock = None
        self.connected = False

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.server, self.port))
            
            # Get config
            config = json.loads(self.sock.recv(1024).decode().strip())
            self.client_ip = config['client_ip']
            self.server_ip = config['server_ip']
            self.connected = True
            
            print(f"[+] Connected!")
            print(f"    Client IP: {self.client_ip}")
            print(f"    Server IP: {self.server_ip}")
            return True
        except Exception as e:
            print(f"[-] Connection failed: {e}")
            return False

    def send(self, data):
        if self.connected:
            self.sock.send(data.encode())
            response = self.sock.recv(1024)
            print(f"[*] Response: {response.decode()}")

    def disconnect(self):
        if self.sock:
            self.sock.close()
        self.connected = False
        print("[*] Disconnected")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--server', required=True, help='Server address')
    parser.add_argument('--port', type=int, default=5555, help='Server port')
    args = parser.parse_args()
    
    client = VPNClient(args.server, args.port)
    if client.connect():
        try:
            while True:
                cmd = input("vpn> ").strip()
                if cmd == 'quit':
                    break
                elif cmd == 'status':
                    print(f"Connected: {client.connected}")
                    print(f"IP: {client.client_ip}")
                elif cmd:
                    client.send(cmd)
        except KeyboardInterrupt:
            print()
        finally:
            client.disconnect()