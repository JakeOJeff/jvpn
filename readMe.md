## Structure

### On Server (WSL Debian/Linux Dis):
~/jvpn/
├── orchestrator.py    (server)
└── server.nix         (NixOS config)
### On Client:
jvpn\
└── cli.py             (client)


## Server Setup

### Start Server

```bash
cd ~/jvpn
python3 orchestrator.py
```

### Get Server IP

```bash
hostname -I
```

### Client Connection

```bash
cd Path/To/Vpn
python cli.py --server [server-ip]
```


