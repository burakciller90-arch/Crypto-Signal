#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

BASE = Path("/Volumes/Crypto-504/Crypto-Signal/Development")
STATE = BASE / "runtime" / "continuity"
LOCAL_PAUSE = STATE / "user_pause"
SHARED = Path("/Users/Shared/.crypto-signal-wake-relay")
SHARED_PAUSE = SHARED / "user_pause"
ACTIVE_LEASES = STATE / "leases" / "active"
LOCAL_QUEUE = STATE / "wake" / "queue"
SHARED_QUEUE = SHARED / "queue"


def count(path: Path, pattern: str) -> int:
    return len(list(path.glob(pattern))) if path.exists() else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="verify resume preconditions without removing pause latches",
    )
    args = parser.parse_args()

    leases = count(ACTIVE_LEASES, "*.lease")
    local_queue = count(LOCAL_QUEUE, "*.wake")
    shared_queue = count(SHARED_QUEUE, "*.wake")
    local_paused = LOCAL_PAUSE.exists()
    shared_paused = SHARED_PAUSE.exists()

    print(f"LOCAL_PAUSED={'YES' if local_paused else 'NO'}")
    print(f"SHARED_PAUSED={'YES' if shared_paused else 'NO'}")
    print(f"ACTIVE_LEASES={leases}")
    print(f"LOCAL_WAKE_QUEUE={local_queue}")
    print(f"RELAY_WAKE_QUEUE={shared_queue}")

    if leases or local_queue or shared_queue:
        print("CONTINUITY_RESUME_PRECONDITION_FAILED=YES")
        return 78

    if args.dry_run:
        print("CONTINUITY_RESUME_DRY_RUN_PASS=YES")
        print("STATE_FIRST_REARM_REQUIRED=YES")
        print("ARCHIVED_STALE_REPLAY=NO")
        return 0

    removed = 0
    for path in (LOCAL_PAUSE, SHARED_PAUSE):
        if path.exists():
            path.unlink()
            removed += 1

    if removed:
        print("CONTINUITY_RESUMED state_first_rearm_required=YES stale_relay_replay=NO")
    else:
        print("CONTINUITY_ALREADY_RESUMED state_first_rearm_required=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
