#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import os
import sys
import time
from pathlib import Path

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
STATE = BASE / "runtime" / "continuity"
SHARED = Path("/Users/Shared/.crypto-signal-wake-relay")
QUEUE = SHARED / "queue"
RECEIPTS = SHARED / "receipts"
PAUSE = SHARED / "user_pause"
LOCAL_PAUSE = STATE / "user_pause"
SECRET_FILE = STATE / "relay_secret"


def event_key(event_id: str) -> str:
    return hashlib.sha256(event_id.encode()).hexdigest()


def marker_for(event_id: str) -> str:
    return f"[#cryptowake:{event_key(event_id)[:16]}]"


def expected_wire_sha(event_id: str, message: str) -> str:
    wire = f"{message} {marker_for(event_id)}"
    return hashlib.sha256(wire.encode()).hexdigest()


def signature(secret: bytes, event_id: str, message: str) -> str:
    payload = f"{event_id}\n{message}".encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()
def receipt_sha(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        if line.startswith("message_sha256="):
            return line.split("=", 1)[1]
    return ""


def queue_matches(path: Path, event_id: str, message: str) -> bool:
    try:
        lines = path.read_text().splitlines()
    except (OSError, UnicodeError):
        return False
    return len(lines) >= 8 and lines[0] == event_id and lines[7] == message


def main() -> int:
    if len(sys.argv) not in {3, 4}:
        print("USAGE: relay_submit.py event_id message [wait_seconds]", file=sys.stderr)
        return 64

    event_id = sys.argv[1]
    message = " ".join(sys.argv[2].splitlines()).strip()
    wait_seconds = float(sys.argv[3]) if len(sys.argv) == 4 else 25.0
    if not event_id or not message:
        print("EMPTY_EVENT_OR_MESSAGE", file=sys.stderr)
        return 64
    if LOCAL_PAUSE.exists() or PAUSE.exists():
        print("RELAY_SUBMIT_PAUSED")
        return 2

    secret = SECRET_FILE.read_text().strip().encode()
    if len(secret) < 32:
        print("RELAY_SECRET_INVALID", file=sys.stderr)
        return 78
    key = event_key(event_id)
    queue_path = QUEUE / f"{key}.wake"
    receipt_path = RECEIPTS / f"{key}.state"
    expected_sha = expected_wire_sha(event_id, message)

    bound_sha = receipt_sha(receipt_path)
    if bound_sha is not None:
        if bound_sha and bound_sha != expected_sha:
            print("EVENT_ID_MESSAGE_CONFLICT")
            return 65
        print("ALREADY_RECEIPTED")
        return 0

    QUEUE.mkdir(parents=True, exist_ok=True)
    if queue_path.exists():
        if not queue_matches(queue_path, event_id, message):
            print("EVENT_ID_MESSAGE_CONFLICT")
            return 65
    else:
        sig = signature(secret, event_id, message)
        tmp = QUEUE / f".{key}.{os.getpid()}.tmp"
        content = "\n".join(
            (
                event_id,
                "",
                "",
                "",
                "",
                time.strftime("%Y-%m-%d %H:%M:%S %z"),
                sig,
                message,
            )
        ) + "\n"
        tmp.write_text(content)
        os.chmod(tmp, 0o660)
        tmp.replace(queue_path)

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        bound_sha = receipt_sha(receipt_path)
        if bound_sha is not None:
            if bound_sha and bound_sha != expected_sha:
                print("EVENT_ID_MESSAGE_CONFLICT")
                return 65
            print("RELAY_RECEIPTED")
            return 0
        time.sleep(0.25)

    print("RELAY_RECEIPT_TIMEOUT")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
