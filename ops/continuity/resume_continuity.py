#!/usr/bin/env python3
from pathlib import Path

BASE = Path("/Volumes/Crypto-504/Crypto-Signal/Development")
LOCAL_PAUSE = BASE / "runtime" / "continuity" / "user_pause"
SHARED_PAUSE = Path("/Users/Shared/.crypto-signal-wake-relay/user_pause")

removed = 0
for path in (LOCAL_PAUSE, SHARED_PAUSE):
    if path.exists():
        path.unlink()
        removed += 1

if removed:
    print("CONTINUITY_RESUMED state_first_rearm_required=YES stale_relay_replay=NO")
else:
    print("CONTINUITY_ALREADY_RESUMED state_first_rearm_required=YES")
