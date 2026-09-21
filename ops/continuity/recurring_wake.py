#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
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
ACTIVE_TASK = STATE / "workers" / "active_task"
LEASE_ACTIVE = STATE / "leases" / "active"
SHARED = Path("/Users/Shared/.crypto-signal-wake-relay")
SHARED_CHAT = SHARED / "current_chat_url"
SHARED_EXPECTED = SHARED / "expected_chat_url"
SHARED_PAUSE = SHARED / "user_pause"
RELAY_SUBMIT = Path(__file__).with_name("relay_submit.py")

POLICY = (
    "User is intentionally inactive and delegated safe project continuation. "
    "Read READ_FIRST_CRYPTO_SIGNAL.md, CURRENT_STATUS.md, latest "
    "PROJECT_CHRONICLE.md, the exact checkpoint and current Git/worker/wake/lease "
    "state first. This lease is only a state pointer, never authority. "
    "Completed, stale, duplicate or superseded work must NOOP/reconcile. "
    "Continue only from the true current frontier. REAL_CAPITAL=0."
)


def read_text(path: Path) -> str:
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return ""


def scheduled_slot_event_id() -> str:
    now = datetime.now().astimezone()
    slot_minute = (now.minute // 20) * 20
    slot = now.replace(minute=slot_minute, second=0, microsecond=0)
    return f"crypto-20m-continuity:{slot:%Y%m%dT%H%M%z}"


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def active_worker_alive() -> bool:
    try:
        fields = ACTIVE_TASK.read_text().strip().split("|")
        pid = int(fields[1])
    except (FileNotFoundError, IndexError, ValueError):
        return False
    return pid_alive(pid)


def checkpoint_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_lease(path: Path) -> tuple[str, str, int, Path, str, str]:
    lines = path.read_text().splitlines()
    if len(lines) < 6:
        raise ValueError("malformed exact lease")
    task, event_id, due_raw, checkpoint_raw, expected_sha, created = lines[:6]
    if not task or not event_id or not checkpoint_raw or not expected_sha:
        raise ValueError("exact lease has empty required field")
    due = int(due_raw)
    checkpoint = Path(checkpoint_raw)
    return task, event_id, due, checkpoint, expected_sha, created


def main() -> int:
    trigger_event_id = (
        sys.argv[1] if len(sys.argv) >= 2 else scheduled_slot_event_id()
    )
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

    if active_worker_alive():
        print("WAKE_SKIPPED_ACTIVE_WORKER_OWNER=YES")
        return 0

    leases = sorted(LEASE_ACTIVE.glob("*.lease"))
    print(f"ACTIVE_LEASES={len(leases)}")
    if not leases:
        print("WAKE_SKIPPED_NO_EXACT_CONTINUATION_OWNER=YES")
        return 0
    if len(leases) != 1:
        print("WAKE_FAIL_MULTIPLE_CONTINUATION_OWNERS=YES", file=sys.stderr)
        return 68

    try:
        task, event_id, due, checkpoint, expected_sha, created = parse_lease(
            leases[0]
        )
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"WAKE_FAIL_INVALID_EXACT_LEASE={exc}", file=sys.stderr)
        return 69

    now = int(time.time())
    if now < due:
        print(f"WAKE_SKIPPED_EXACT_LEASE_NOT_DUE=YES due_epoch={due}")
        return 0
    if not checkpoint.is_file():
        print("WAKE_FAIL_CHECKPOINT_MISSING=YES", file=sys.stderr)
        return 69
    if checkpoint_sha(checkpoint) != expected_sha:
        print("WAKE_FAIL_CHECKPOINT_HASH_MISMATCH=YES", file=sys.stderr)
        return 69

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

    message = (
        "CRYPTO_SIGNAL_CONTINUE_EXACT — "
        f"task={task} checkpoint={checkpoint} checkpoint_sha256={expected_sha} "
        f"created={created}. Exact lease is a continuation hint only. {POLICY}"
    )
    proc = subprocess.run(
        ["/usr/bin/python3", str(RELAY_SUBMIT), event_id, message, "25"],
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
        print("CRYPTO_EXACT_CONTINUITY_FALLBACK_PASS=YES")
        return 0
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
