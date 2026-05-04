#!/usr/bin/env python3
"""
HA Cluster Heartbeat Service
Writes a heartbeat record to /data/heartbeat.json every second.
Exposes /status endpoint returning recent heartbeat history.
Managed by Pacemaker — runs on whichever node is Primary.
"""

import json
import os
import socket
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ── Config ────────────────────────────────────────────────────────────────────
DATA_DIR = Path("/data")
HEARTBEAT_FILE = DATA_DIR / "heartbeat.json"
HISTORY_FILE = DATA_DIR / "heartbeat_history.jsonl"
MAX_HISTORY = 60          # keep last 60 entries in history
HEARTBEAT_INTERVAL = 1.0  # seconds

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="HA Heartbeat", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Heartbeat writer ──────────────────────────────────────────────────────────
def get_node_name() -> str:
    return socket.gethostname()

def read_counter() -> int:
    try:
        if HEARTBEAT_FILE.exists():
            data = json.loads(HEARTBEAT_FILE.read_text())
            return data.get("counter", 0)
    except Exception:
        pass
    return 0

def write_heartbeat():
    counter = read_counter() + 1
    node = get_node_name()
    ts = datetime.now(timezone.utc).isoformat()

    record = {
        "counter": counter,
        "node": node,
        "timestamp": ts,
    }

    # Write current heartbeat
    HEARTBEAT_FILE.write_text(json.dumps(record))

    # Append to history
    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")

    # Trim history to last MAX_HISTORY lines
    try:
        lines = HISTORY_FILE.read_text().splitlines()
        if len(lines) > MAX_HISTORY:
            HISTORY_FILE.write_text("\n".join(lines[-MAX_HISTORY:]) + "\n")
    except Exception:
        pass

    return record

def heartbeat_loop():
    """Background thread — writes heartbeat every second."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            write_heartbeat()
        except Exception as e:
            print(f"Heartbeat write error: {e}")
        time.sleep(HEARTBEAT_INTERVAL)

# Start heartbeat thread on startup
@app.on_event("startup")
def start_heartbeat():
    t = threading.Thread(target=heartbeat_loop, daemon=True)
    t.start()

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/status")
def status():
    """Return current heartbeat and last 30 history entries."""
    current = {}
    history = []

    try:
        if HEARTBEAT_FILE.exists():
            current = json.loads(HEARTBEAT_FILE.read_text())
    except Exception:
        pass

    try:
        if HISTORY_FILE.exists():
            lines = HISTORY_FILE.read_text().splitlines()
            history = [json.loads(l) for l in lines[-30:] if l.strip()]
    except Exception:
        pass

    return {
        "current": current,
        "history": history,
        "service_node": get_node_name(),
    }

@app.get("/health")
def health():
    return {"status": "ok", "node": get_node_name()}

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
