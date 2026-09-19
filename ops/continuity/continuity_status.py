#!/usr/bin/env python3
import os
from pathlib import Path

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
STATE = BASE / "runtime" / "continuity"


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def count(path: Path, pattern: str) -> int:
    return len(list(path.glob(pattern))) if path.exists() else 0


pause = STATE / "user_pause"
target = STATE / "wake" / "current_chat_url"
pidfile = STATE / "bridge.pid"
worker = STATE / "workers" / "active_task"
pid = 0
if pidfile.exists():
    try:
        pid = int(pidfile.read_text().strip())
    except ValueError:
        pid = 0

print(f"PAUSED={'YES' if pause.exists() else 'NO'}")
print(f"CHAT_BOUND={'YES' if target.exists() else 'NO'}")
print(f"BRIDGE_PID={pid if pid else 'NONE'}")
print(f"BRIDGE_ALIVE={'YES' if pid and alive(pid) else 'NO'}")
print(f"ACTIVE_WORKER={'YES' if worker.exists() else 'NO'}")
print(f"WAKE_QUEUE={count(STATE / 'wake' / 'queue', '*.wake')}")
print(f"ACTIVE_LEASES={count(STATE / 'leases' / 'active', '*.lease')}")
print(f"DELIVERED_LEASES={count(STATE / 'leases' / 'delivered', '*.lease')}")
print(f"WAKE_RECEIPTS={count(STATE / 'wake' / 'receipts', '*.state')}")
