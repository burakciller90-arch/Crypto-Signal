#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
STATE = BASE / "runtime" / "continuity"
LOCAL_CHAT = STATE / "wake" / "current_chat_url"
LOCAL_PAUSE = STATE / "user_pause"
SHARED = Path("/Users/Shared/.crypto-signal-wake-relay")
SHARED_CHAT = SHARED / "current_chat_url"
SHARED_PAUSE = SHARED / "user_pause"
EXPECTED_CHAT = "https://chatgpt.com/c/6ab0debd-49a8-83eb-8b33-a7ce2ef826d0"
RELAY_SUBMIT = Path(__file__).with_name("relay_submit.py")

MESSAGE = (
    "CRYPTO_SIGNAL_AUTONOMOUS_CONTINUE_V1 — Kullanıcı aktif değil ve projeyi "
    "tamamlaman için sana bıraktı; bu yüzden sana mesaj gönderemez. Hafızana "
    "güvenme: READ_FIRST_CRYPTO_SIGNAL.md, CURRENT_STATUS.md, PROJECT_CHRONICLE.md "
    "ve mevcut Git/worker/wake/lease state'ini mekanik olarak kontrol et; kaldığın "
    "gerçek frontier'ı bul ve oradan devam et. Tamamlanmış, stale, duplicate veya "
    "superseded işi tekrarlama. Kullanıcı REAL MONEY hariç roadmap'i bitirmeni "
    "istiyor; güvenli aşamalar arasında onay bekleme, sürekli ilerle. REAL_CAPITAL=0."
)


def read_text(path: Path) -> str:
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return ""


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(BASE), *args],
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()


def scheduled_slot_event_id() -> str:
    now = datetime.now().astimezone()
    slot_minute = 0 if now.minute < 30 else 30
    slot = now.replace(minute=slot_minute, second=0, microsecond=0)
    return f"crypto-30m-continuity:{slot:%Y%m%dT%H%M%z}"


def main() -> int:
    local_slot_invocation = len(sys.argv) < 2
    event_id = sys.argv[1] if not local_slot_invocation else scheduled_slot_event_id()
    print(f"WAKE_EVENT_ID={event_id}")
    if local_slot_invocation:
        marker = STATE / "recurring_wake_last_local_attempt"
        marker.write_text(
            f"epoch={int(time.time())}\n"
            f"event_id={event_id}\n"
        )

    if LOCAL_PAUSE.exists() or SHARED_PAUSE.exists():
        print("WAKE_SKIPPED_USER_PAUSE=YES")
        return 0

    local_target = read_text(LOCAL_CHAT)
    shared_target = read_text(SHARED_CHAT)
    print(f"EXPECTED_CHAT={EXPECTED_CHAT}")
    print(f"LOCAL_CHAT={local_target or 'MISSING'}")
    print(f"SHARED_CHAT={shared_target or 'MISSING'}")
    if local_target != EXPECTED_CHAT or shared_target != EXPECTED_CHAT:
        print("WAKE_TARGET_MISMATCH=YES", file=sys.stderr)
        return 66

    try:
        print(f"CANONICAL_HEAD={git('rev-parse', 'HEAD')}")
        print(f"CANONICAL_BRANCH={git('branch', '--show-current') or 'DETACHED'}")
        dirty = git("status", "--porcelain")
        print(f"CANONICAL_DIRTY={'YES' if dirty else 'NO'}")
    except subprocess.CalledProcessError as exc:
        print(f"CANONICAL_GIT_CHECK_FAILED={exc.output}", file=sys.stderr)
        return 67

    active_leases = list((STATE / "leases" / "active").glob("*.lease"))
    active_task = read_text(STATE / "workers" / "active_task")
    print(f"ACTIVE_LEASES={len(active_leases)}")
    print(f"ACTIVE_WORKER={'YES' if active_task else 'NO'}")

    proc = subprocess.run(
        ["/usr/bin/python3", str(RELAY_SUBMIT), event_id, MESSAGE, "25"],
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
        print("CRYPTO_30M_CONTINUITY_WAKE_PASS=YES")
        return 0
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
