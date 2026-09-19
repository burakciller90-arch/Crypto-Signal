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
SHARED = Path("/Users/Shared/.crypto-signal-wake-relay")
SHARED_PAUSE = SHARED / "user_pause"
SHARED_QUEUE = SHARED / "queue"
SHARED_PAUSED = SHARED / "paused"

for path in (LEASE_PAUSED, QUEUE_PAUSED, SHARED_PAUSED):
    path.mkdir(parents=True, exist_ok=True)

stamp = int(time.time())
payload = f"user_pause_epoch={stamp}\n"
PAUSE.write_text(payload)
PAUSE.chmod(0o600)
SHARED_PAUSE.write_text(payload)
SHARED_PAUSE.chmod(0o660)

lease_count = 0
for item in LEASE_ACTIVE.glob("*.lease"):
    shutil.move(item, LEASE_PAUSED / f"{item.name}.user-pause.{stamp}")
    lease_count += 1

queue_count = 0
for item in QUEUE.glob("*.wake"):
    shutil.move(item, QUEUE_PAUSED / f"{item.name}.user-pause.{stamp}")
    queue_count += 1

relay_count = 0
for item in SHARED_QUEUE.glob("*.wake"):
    shutil.move(item, SHARED_PAUSED / f"{item.name}.user-pause.{stamp}")
    relay_count += 1

print(
    f"CONTINUITY_PAUSED leases_archived={lease_count} "
    f"queued_wakes_archived={queue_count} relay_wakes_archived={relay_count} "
    "worker_untouched=YES"
)
