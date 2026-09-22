#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from continuity_contracts import require_exact_binding

BASE = Path("/Volumes/Crypto-504/Crypto-Signal/Development")
STATE = BASE / "runtime" / "continuity"
LOCAL_CHAT = STATE / "wake" / "current_chat_url"
LOCAL_EXPECTED = STATE / "wake" / "expected_chat_url"
LOCAL_PAUSE = STATE / "user_pause"
SHARED = Path("/Users/Shared/.crypto-signal-wake-relay")
SHARED_CHAT = SHARED / "current_chat_url"
SHARED_EXPECTED = SHARED / "expected_chat_url"
SHARED_PAUSE = SHARED / "user_pause"
RELAY_SUBMIT = Path(__file__).with_name("relay_submit.py")

WAKE_MESSAGE = "Kullanıcı aktif değil ve projeyi tamamlaman için sana bıraktı; HAFIZANA GÜVENME. READ_FIRST, CURRENT_STATUS, Chronicle ve docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md dosyasını oku; gerçek Git/worker/wake/lease state’ini kontrol et, gerçek frontier’ı bul. Tamamlanmış/stale/duplicate işi tekrarlama. Kullanıcı REAL MONEY hariç roadmap’in bitmesini istiyor; güvenli aşamalar arasında onay bekleme ve devam et. REAL_CAPITAL=0."


def read_text(path: Path) -> str:
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return ""


def scheduled_slot_event_id() -> str:
    now = datetime.now().astimezone()
    slot_minute = (now.minute // 20) * 20
    slot = now.replace(minute=slot_minute, second=0, microsecond=0)
    return f"crypto-20m-locked-roadmap:{slot:%Y%m%dT%H%M%z}"


def main() -> int:
    trigger_event_id = sys.argv[1] if len(sys.argv) >= 2 else scheduled_slot_event_id()
    print(f"WAKE_TRIGGER_EVENT_ID={trigger_event_id}")

    marker = STATE / "recurring_wake_last_local_attempt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        f"epoch={int(time.time())}\n"
        f"trigger_event_id={trigger_event_id}\n"
    )

    if LOCAL_PAUSE.exists() or SHARED_PAUSE.exists():
        print("WAKE_SKIPPED_USER_PAUSE=YES")
        return 0

    try:
        target = require_exact_binding(
            expected=read_text(LOCAL_EXPECTED),
            local_current=read_text(LOCAL_CHAT),
            shared_current=read_text(SHARED_CHAT),
            shared_expected=read_text(SHARED_EXPECTED),
        )
    except ValueError as exc:
        print(f"WAKE_TARGET_BINDING_INVALID={exc}", file=sys.stderr)
        return 66
    print(f"EXACT_CHAT_BOUND={target}")

    proc = subprocess.run(
        ["/usr/bin/python3", str(RELAY_SUBMIT), trigger_event_id, WAKE_MESSAGE, "45"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip(), file=sys.stderr)
    print(f"RELAY_SUBMIT_RC={proc.returncode}")
    if proc.returncode in {0, 2}:
        print("CRYPTO_LOCKED_20M_WAKE_PASS=YES")
        return 0
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
