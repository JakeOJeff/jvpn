#!/usr/bin/env python3
"""
orchestrator.py
---------------
Runs on the VPN SERVER (laptop WSL2).
Manages WireGuard peers via a simple HTTP API.

Endpoints:
  GET    /health            → server status + public key
  GET    /peers             → list all registered peers
  POST   /peers             → register new peer, returns assigned VPN IP
  DELETE /peers/{pubkey}    → remove a peer

Start:
  sudo venv/bin/python3 orchestrator.py
"""

import json
import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

app = FastAPI()

# ── Constants ─────────────────────────────────────────────────────────────────

WG_INTERFACE  = "wg0"
VPN_SUBNET    = "10.0.0"
SERVER_VPN_IP = "10.0.0.1"
PRIVATE_KEY   = Path("/etc/wireguard/private.key")
PEERS_FILE    = Path("/etc/wireguard/peers.json")

# ── Peer storage ──────────────────────────────────────────────────────────────

def load_peers() -> dict:
    if not PEERS_FILE.exists():
        return {}
    text = PEERS_FILE.read_text().strip()
    if not text:
        return {}
    return json.loads(text)


def save_peers(peers: dict):
    PEERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PEERS_FILE.write_text(json.dumps(peers, indent=2))


def next_available_ip(peers: dict) -> str:
    used = {p["ip"] for p in peers.values()}
    for i in range(2, 255):
        candidate = f"{VPN_SUBNET}.{i}"
        if candidate not in used:
            return candidate
    raise RuntimeError("IP pool exhausted")


# ── WireGuard helpers ─────────────────────────────────────────────────────────

def wg_add_peer(public_key: str, ip: str):
    subprocess.run(
        ["wg", "set", WG_INTERFACE,
         "peer", public_key,
         "allowed-ips", f"{ip}/32"],
        check=True, capture_output=True
    )


def wg_remove_peer(public_key: str):
    subprocess.run(
        ["wg", "set", WG_INTERFACE, "peer", public_key, "remove"],
        check=True, capture_output=True
    )


def get_server_public_key() -> str:
    private = PRIVATE_KEY.read_text().strip()
    result = subprocess.run(
        ["wg", "pubkey"], input=private,
        capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def get_server_public_ip() -> str:
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "4", "https://ifconfig.me"],
            capture_output=True, text=True
        )
        return r.stdout.strip() or "YOUR_SERVER_IP"
    except Exception:
        return "YOUR_SERVER_IP"


# ── Models ────────────────────────────────────────────────────────────────────

class AddPeerRequest(BaseModel):
    name:       str
    public_key: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status":     "ok",
        "server_ip":  SERVER_VPN_IP,
        "public_key": get_server_public_key(),
        "interface":  WG_INTERFACE,
    }


@app.get("/peers")
def list_peers():
    return load_peers()


@app.post("/peers")
def add_peer(req: AddPeerRequest):
    peers = load_peers()

    # idempotent — already registered, return existing
    if req.public_key in peers:
        existing = peers[req.public_key]
        return {
            "name":              existing["name"],
            "ip":                existing["ip"],
            "server_public_key": get_server_public_key(),
            "endpoint":          f"{get_server_public_ip()}:51820",
        }

    ip = next_available_ip(peers)

    try:
        wg_add_peer(req.public_key, ip)
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500,
            detail=f"wg set failed: {e.stderr.decode() if e.stderr else str(e)}"
        )

    peers[req.public_key] = {"name": req.name, "ip": ip}
    save_peers(peers)
    print(f"[+] {req.name} registered → {ip}")

    return {
        "name":              req.name,
        "ip":                ip,
        "server_public_key": get_server_public_key(),
        "endpoint":          f"{get_server_public_ip()}:51820",
    }


@app.delete("/peers/{public_key}")
def remove_peer(public_key: str):
    peers = load_peers()
    if public_key not in peers:
        raise HTTPException(status_code=404, detail="Peer not found")

    name = peers[public_key]["name"]
    try:
        wg_remove_peer(public_key)
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500,
            detail=f"wg remove failed: {e.stderr.decode() if e.stderr else str(e)}"
        )

    del peers[public_key]
    save_peers(peers)
    print(f"[-] {name} removed")
    return {"removed": name}


# ── Startup: restore peers ────────────────────────────────────────────────────

@app.on_event("startup")
def restore_peers():
    """Re-add all persisted peers to WireGuard on orchestrator start.
    Needed because WSL2 resets network interfaces on restart."""
    peers = load_peers()
    if not peers:
        return
    print(f"[*] Restoring {len(peers)} peer(s)...")
    for pubkey, info in peers.items():
        try:
            wg_add_peer(pubkey, info["ip"])
            print(f"    restored: {info['name']} → {info['ip']}")
        except subprocess.CalledProcessError:
            print(f"    skipped (already exists): {info['name']}")


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[*] Starting orchestrator on 0.0.0.0:8080")
    print(f"[*] WireGuard interface : {WG_INTERFACE}")
    print(f"[*] Peers file          : {PEERS_FILE}")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")