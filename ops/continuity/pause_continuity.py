#!/usr/bin/env python3
import shutil
import time
from pathlib import Path

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
STATE = BASE / "runtime" / "continuity"
PAUSE = STATE / "user_pause"
LEASE_ACTIVE = STATE / "leases" / "active"
LEASE_PAUSED = STATE / "leases" / "paused"
QUEUE = STATE / "wake" / "queue"
QUEUE_PAUSED = STATE / "wake" / "paused"

for path in (LEASE_PAUSED, QUEUE_PAUSED):
    path.mkdir(parents=True, exist_ok=True)

stamp = int(time.time())
PAUSE.write_text(f"user_pause_epoch={stamp}\n")
PAUSE.chmod(0o600)
lease_count = 0
for item in LEASE_ACTIVE.glob("*.lease"):
    shutil.move(item, LEASE_PAUSED / f"{item.name}.user-pause.{stamp}")
    lease_count += 1

queue_count = 0
for item in QUEUE.glob("*.wake"):
    shutil.move(item, QUEUE_PAUSED / f"{item.name}.user-pause.{stamp}")
    queue_count += 1

print(
    f"CONTINUITY_PAUSED leases_archived={lease_count} "
    f"queued_wakes_archived={queue_count} worker_untouched=YES"
)
