#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import time
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
LOCKED_SUCCESS_STATE = SHARED / "locked_wake_success"
RELAY_SUBMIT = Path(__file__).with_name("relay_submit.py")

LOCKED_WAKE_INTERVAL_SECONDS = 20 * 60
WAKE_MESSAGE = "Kullanıcı aktif değil ve projeyi tamamlaman için sana bıraktı; HAFIZANA GÜVENME! READ_FIRST, CURRENT_STATUS, Chronicle ve docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md dosyasını oku; gerçek Git/worker/wake/lease state’ini kontrol et, gerçek frontier’ı bul. Tamamlanmış/stale/duplicate işi tekrarlama. Kullanıcı REAL MONEY hariç roadmap’in bitmesini istiyor; güvenli aşamalar arasında onay bekleme ve devam et. Ve bir sonraki ajan için yaptığın her işi her güncellemeyi GitHub üzerine kayıt et. Bu mesaj döngüsünü bozamazsın."


def read_text(path: Path) -> str:
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return ""


def read_last_observed_epoch() -> float | None:
    try:
        lines = LOCKED_SUCCESS_STATE.read_text().splitlines()
    except FileNotFoundError:
        return None
    for line in lines:
        if line.startswith("last_observed_epoch="):
            try:
                return float(line.split("=", 1)[1])
            except ValueError:
                return None
    return None


def recurring_event_id(last_observed_epoch: float | None) -> str:
    if last_observed_epoch is None:
        return "crypto-20m-locked-roadmap:bootstrap"
    return f"crypto-20m-locked-roadmap:after:{int(last_observed_epoch)}"


def main() -> int:
    explicit_event_id = sys.argv[1] if len(sys.argv) >= 2 else None
    now = time.time()

    marker = STATE / "recurring_wake_last_local_attempt"
    marker.parent.mkdir(parents=True, exist_ok=True)

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

    last_observed_epoch = read_last_observed_epoch()
    if explicit_event_id is None and last_observed_epoch is not None:
        age = now - last_observed_epoch
        print(f"LOCKED_WAKE_LAST_OBSERVED_AGE_SECONDS={int(max(0, age))}")
        if 0 <= age < LOCKED_WAKE_INTERVAL_SECONDS:
            remaining = int(LOCKED_WAKE_INTERVAL_SECONDS - age)
            print(f"LOCKED_WAKE_NOT_DUE=YES remaining_seconds={remaining}")
            return 0

    trigger_event_id = explicit_event_id or recurring_event_id(last_observed_epoch)
    marker.write_text(
        f"epoch={int(now)}\n"
        f"trigger_event_id={trigger_event_id}\n"
        f"last_observed_epoch={'' if last_observed_epoch is None else last_observed_epoch}\n"
    )
    print(f"WAKE_TRIGGER_EVENT_ID={trigger_event_id}")
    print(f"EXACT_CHAT_BOUND={target}")

    proc = subprocess.run(
        ["/usr/bin/python3", str(RELAY_SUBMIT), trigger_event_id, WAKE_MESSAGE, "90"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip(), file=sys.stderr)
    print(f"RELAY_SUBMIT_RC={proc.returncode}")

    if proc.returncode == 0:
        print("CRYPTO_LOCKED_20M_WAKE_PASS=YES")
        return 0
    if proc.returncode == 2:
        print("WAKE_SKIPPED_USER_PAUSE_RACE=YES")
        return 0

    print("CRYPTO_LOCKED_20M_WAKE_PASS=NO", file=sys.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
