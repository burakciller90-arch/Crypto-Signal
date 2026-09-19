#!/usr/bin/env python3
from pathlib import Path

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
PAUSE = BASE / "runtime" / "continuity" / "user_pause"

if PAUSE.exists():
    PAUSE.unlink()
    print("CONTINUITY_RESUMED state_first_rearm_required=YES")
else:
    print("CONTINUITY_ALREADY_RESUMED state_first_rearm_required=YES")
