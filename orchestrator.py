#!/usr/bin/env python3
import socket
import threading
import json

class VPNServer:
    def __init__(self, host='0.0.0.0', port=5555):
        self.host = host
        self.port = port
        self.clients = {}
        self.next_ip = 2
        self.lock = threading.Lock()

    def assign_ip(self):
        with self.lock:
            ip = f"10.8.0.{self.next_ip}"
            self.next_ip += 1
            return ip

    def handle_client(self, sock, addr):
        client_ip = self.assign_ip()
        print(f"[+] Client {addr} connected -> {client_ip}")
        
        config = {"client_ip": client_ip, "server_ip": "10.8.0.1"}
        sock.send(json.dumps(config).encode() + b'\n')
        
        try:
            while True:
                data = sock.recv(1024)
                if not data:
                    break
                sock.send(data)  # Echo back
        finally:
            sock.close()
            print(f"[-] Client {addr} disconnected")

    def start(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen(5)
        print(f"[*] VPN Server listening on {self.host}:{self.port}")
        
        try:
            while True:
                sock, addr = server.accept()
                thread = threading.Thread(target=self.handle_client, args=(sock, addr), daemon=True)
                thread.start()
        except KeyboardInterrupt:
            print("\n[*] Shutting down...")
        finally:
            server.close()

if __name__ == '__main__':
    vpn = VPNServer()
    vpn.start()