#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

from continuity_contracts import (
    PROJECT_NAMESPACE,
    RELAY_PROTOCOL,
    decode_relay_event,
    encode_relay_event,
    event_key,
    expected_wire_sha,
    require_exact_binding,
)

BASE = Path("/Volumes/Crypto-504/Crypto-Signal/Development")
STATE = BASE / "runtime" / "continuity"
SHARED = Path("/Users/Shared/.crypto-signal-wake-relay")
QUEUE = SHARED / "queue"
RECEIPTS = SHARED / "receipts"
PAUSE = SHARED / "user_pause"
LOCAL_PAUSE = STATE / "user_pause"
LOCAL_CURRENT = STATE / "wake" / "current_chat_url"
LOCAL_EXPECTED = STATE / "wake" / "expected_chat_url"
SHARED_CURRENT = SHARED / "current_chat_url"
SHARED_EXPECTED = SHARED / "expected_chat_url"
SECRET_FILE = STATE / "relay_secret"
AUTONOMOUS_PREFIX = "CRYPTO_SIGNAL_AUTONOMOUS_CONTINUE_V1"
LOCKED_WAKE_MESSAGE = "Kullanıcı aktif değil ve projeyi tamamlaman için sana bıraktı; HAFIZANA GÜVENME! READ_FIRST, CURRENT_STATUS, Chronicle ve docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md dosyasını oku; gerçek Git/worker/wake/lease state’ini kontrol et, gerçek frontier’ı bul. Tamamlanmış/stale/duplicate işi tekrarlama. Kullanıcı REAL MONEY hariç roadmap’in bitmesini istiyor; güvenli aşamalar arasında onay bekleme ve devam et. REAL_CAPITAL=0. Bir sonraki ajan için yaptığın her işi ve her güncellemeyi GitHub üzerine kaydet. Bu 20 dakikalık mesaj döngüsünü bozamazsın."

TERMINAL_RECEIPT_STATUSES = {
    "OBSERVED",
    "RECENT_LOCKED_DUPLICATE_DROPPED",
    "STALE_AUTONOMOUS_DROPPED",
    "SEMANTIC_DUPLICATE_DROPPED",
}


def receipt_fields(path: Path) -> tuple[str, str] | None:
    if not path.exists():
        return None
    status = ""
    message_sha = ""
    for line in path.read_text().splitlines():
        if line.startswith("status="):
            status = line.split("=", 1)[1]
        elif line.startswith("message_sha256="):
            message_sha = line.split("=", 1)[1]
    return status, message_sha


def queue_matches(
    path: Path,
    event_id: str,
    message: str,
    *,
    secret: bytes,
) -> bool:
    try:
        event = decode_relay_event(path.read_text(), secret=secret)
    except (OSError, UnicodeError, ValueError):
        return False
    return event.event_id == event_id and event.message == message


def main() -> int:
    if len(sys.argv) not in {3, 4}:
        print("USAGE: relay_submit.py event_id message [wait_seconds]", file=sys.stderr)
        return 64

    event_id = sys.argv[1].strip()
    message = " ".join(sys.argv[2].splitlines()).strip()
    wait_seconds = float(sys.argv[3]) if len(sys.argv) == 4 else 25.0
    if not event_id or not message:
        print("EMPTY_EVENT_OR_MESSAGE", file=sys.stderr)
        return 64
    if LOCAL_PAUSE.exists() or PAUSE.exists():
        print("RELAY_SUBMIT_PAUSED")
        return 2

    def read(path: Path) -> str:
        try:
            return path.read_text().strip()
        except FileNotFoundError:
            return ""

    try:
        bound_target = require_exact_binding(
            expected=read(LOCAL_EXPECTED),
            local_current=read(LOCAL_CURRENT),
            shared_current=read(SHARED_CURRENT),
            shared_expected=read(SHARED_EXPECTED),
        )
    except ValueError as exc:
        print(f"RELAY_BINDING_INVALID:{exc}", file=sys.stderr)
        return 66
    print(f"RELAY_PROTOCOL={RELAY_PROTOCOL}")
    print(f"PROJECT_NAMESPACE={PROJECT_NAMESPACE}")
    print(f"BOUND_TARGET={bound_target}")

    secret = SECRET_FILE.read_text().strip().encode()
    if len(secret) < 32:
        print("RELAY_SECRET_INVALID", file=sys.stderr)
        return 78

    key = event_key(event_id)
    queue_path = QUEUE / f"{key}.wake"
    receipt_path = RECEIPTS / f"{key}.state"
    expected_sha = (
        hashlib.sha256(message.encode()).hexdigest()
        if message == LOCKED_WAKE_MESSAGE
        else expected_wire_sha(event_id, message)
    )

    existing = receipt_fields(receipt_path)
    if existing is not None:
        status, bound_sha = existing
        if bound_sha and bound_sha != expected_sha:
            print("EVENT_ID_MESSAGE_CONFLICT")
            return 65
        if status in TERMINAL_RECEIPT_STATUSES:
            print(f"ALREADY_RECEIPTED status={status}")
            return 0
        print(f"NONTERMINAL_RECEIPT_IGNORED status={status or 'UNKNOWN'}")

    QUEUE.mkdir(parents=True, exist_ok=True)
    if queue_path.exists():
        if not queue_matches(
            queue_path,
            event_id,
            message,
            secret=secret,
        ):
            print("EVENT_ID_MESSAGE_CONFLICT")
            return 65
    else:
        tmp = QUEUE / f".{key}.{os.getpid()}.tmp"
        content = encode_relay_event(
            secret=secret,
            event_id=event_id,
            message=message,
            created=time.strftime("%Y-%m-%d %H:%M:%S %z"),
        )
        tmp.write_text(content)
        os.chmod(tmp, 0o660)
        tmp.replace(queue_path)

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        existing = receipt_fields(receipt_path)
        if existing is not None:
            status, bound_sha = existing
            if bound_sha and bound_sha != expected_sha:
                print("EVENT_ID_MESSAGE_CONFLICT")
                return 65
            if status in TERMINAL_RECEIPT_STATUSES:
                print(f"RELAY_RECEIPTED status={status}")
                return 0
        if LOCAL_PAUSE.exists() or PAUSE.exists():
            print("RELAY_SUBMIT_PAUSED_DURING_WAIT")
            return 2
        time.sleep(0.25)

    print("RELAY_RECEIPT_TIMEOUT", file=sys.stderr)
    return 75


if __name__ == "__main__":
    raise SystemExit(main())
