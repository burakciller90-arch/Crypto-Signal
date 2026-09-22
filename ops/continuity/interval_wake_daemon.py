from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import TypedDict, cast

from continuity_contracts import event_key

BASE = Path("/Volumes/Crypto-504/Crypto-Signal/Development")
STATE = BASE / "runtime" / "continuity"
SHARED = Path("/Users/Shared/.crypto-signal-wake-relay")
SHARED_RECEIPTS = SHARED / "receipts"
LOCAL_PAUSE = STATE / "user_pause"
SHARED_PAUSE = SHARED / "user_pause"
RECURRING_WAKE = Path(__file__).with_name("recurring_wake.py")

RUNTIME = Path(__file__).resolve().parent / "runtime"
PIDFILE = RUNTIME / "rolling_wake.pid"
STATE_FILE = RUNTIME / "rolling_wake_state.json"
STATUS_FILE = RUNTIME / "rolling_wake_status"
HEARTBEAT_FILE = RUNTIME / "rolling_wake_heartbeat"
LOG_FILE = RUNTIME / "rolling_wake.log"

INTERVAL_SECONDS = 20 * 60
RETRY_SECONDS = 5
LOOP_SECONDS = 2
FINAL_RECEIPT_STATES = {"OBSERVED"}


class RollingWakeState(TypedDict):
    generation: str
    sequence: int
    next_due_epoch: float
    pending_event_id: str
    last_event_id: str
    last_attempt_epoch: float
    last_receipt_epoch: float
    failure_count: int


def _coerce_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _coerce_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(content)
    os.chmod(tmp, mode)
    tmp.replace(path)


def log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S %z")
    with LOG_FILE.open("a") as handle:
        handle.write(f"{stamp} {message}\n")


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def load_state(*, reset: bool) -> RollingWakeState:
    if reset:
        STATE_FILE.unlink(missing_ok=True)
    try:
        raw: object = json.loads(STATE_FILE.read_text())
    except FileNotFoundError:
        raw = {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        bad = STATE_FILE.with_name(f"{STATE_FILE.name}.bad.{int(time.time())}")
        try:
            STATE_FILE.replace(bad)
        except OSError:
            pass
        raw = {}

    value = cast(dict[str, object], raw) if isinstance(raw, dict) else {}
    generation = str(value.get("generation") or uuid.uuid4().hex[:16])
    sequence = max(0, _coerce_int(value.get("sequence"), 0))
    next_due_epoch = _coerce_float(value.get("next_due_epoch"), 0.0)
    if next_due_epoch <= 0:
        next_due_epoch = time.time()

    return {
        "generation": generation,
        "sequence": sequence,
        "next_due_epoch": next_due_epoch,
        "pending_event_id": str(value.get("pending_event_id") or ""),
        "last_event_id": str(value.get("last_event_id") or ""),
        "last_attempt_epoch": _coerce_float(value.get("last_attempt_epoch"), 0.0),
        "last_receipt_epoch": _coerce_float(value.get("last_receipt_epoch"), 0.0),
        "failure_count": max(0, _coerce_int(value.get("failure_count"), 0)),
    }


def save_state(state: RollingWakeState) -> None:
    atomic_write(
        STATE_FILE,
        json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n",
    )


def receipt_status(event_id: str) -> str | None:
    path = SHARED_RECEIPTS / f"{event_key(event_id)}.state"
    try:
        lines = path.read_text().splitlines()
    except (FileNotFoundError, OSError, UnicodeError):
        return None
    for line in lines:
        if line.startswith("status="):
            return line.split("=", 1)[1].strip()
    return None


def final_receipt(event_id: str) -> bool:
    status = receipt_status(event_id)
    return status in FINAL_RECEIPT_STATES


def paused() -> bool:
    return LOCAL_PAUSE.exists() or SHARED_PAUSE.exists()


def prerequisites_ready() -> bool:
    return BASE.is_dir() and RECURRING_WAKE.is_file()


def write_runtime_status(
    state: RollingWakeState,
    *,
    runtime_state: str,
    detail: str,
) -> None:
    now = time.time()
    next_due = state["next_due_epoch"]
    pending = str(state["pending_event_id"])
    countdown = max(0, round(next_due - now)) if not pending else 0
    content = (
        f"state={runtime_state}\n"
        f"pid={os.getpid()}\n"
        f"interval_seconds={INTERVAL_SECONDS}\n"
        f"heartbeat_epoch={int(now)}\n"
        f"generation={state['generation']}\n"
        f"sequence={state['sequence']}\n"
        f"pending_event_id={pending}\n"
        f"last_event_id={state['last_event_id']}\n"
        f"last_attempt_epoch={int(state['last_attempt_epoch'])}\n"
        f"last_receipt_epoch={int(state['last_receipt_epoch'])}\n"
        f"next_due_epoch={int(next_due)}\n"
        f"next_due_in_seconds={countdown}\n"
        f"failure_count={state['failure_count']}\n"
        f"detail={detail}\n"
    )
    atomic_write(STATUS_FILE, content)
    atomic_write(HEARTBEAT_FILE, f"{int(now)}\n")


def run_wake(event_id: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["/usr/bin/python3", str(RECURRING_WAKE), event_id],
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, "RECURRING_WAKE_TIMEOUT"
    output = (proc.stdout + proc.stderr).strip().replace("\n", " | ")
    return proc.returncode, output


def next_event(state: RollingWakeState) -> str:
    sequence = state["sequence"] + 1
    state["sequence"] = sequence
    event_id = f"crypto-20m-rolling:{state['generation']}:{sequence}"
    state["pending_event_id"] = event_id
    save_state(state)
    return event_id


def main() -> int:
    reset = "--reset" in sys.argv[1:]
    RUNTIME.mkdir(parents=True, exist_ok=True)

    if PIDFILE.exists():
        try:
            old_pid = int(PIDFILE.read_text().strip())
        except (OSError, ValueError):
            old_pid = 0
        if old_pid and old_pid != os.getpid() and pid_alive(old_pid):
            print(f"ROLLING_WAKE_ALREADY_RUNNING:{old_pid}")
            return 0

    atomic_write(PIDFILE, f"{os.getpid()}\n")
    state = load_state(reset=reset)
    if reset:
        state["next_due_epoch"] = time.time()
        state["pending_event_id"] = ""
        state["failure_count"] = 0
        save_state(state)
    log(
        "rolling_timer=START "
        f"pid={os.getpid()} reset={'YES' if reset else 'NO'} "
        f"generation={state['generation']}"
    )

    try:
        while True:
            try:
                if paused():
                    write_runtime_status(
                        state,
                        runtime_state="PAUSED",
                        detail="user_pause_present",
                    )
                    time.sleep(LOOP_SECONDS)
                    continue

                if not prerequisites_ready():
                    write_runtime_status(
                        state,
                        runtime_state="WAITING_FOR_RUNTIME",
                        detail="ssd_or_recurring_wake_unavailable",
                    )
                    time.sleep(LOOP_SECONDS)
                    continue

                pending = str(state["pending_event_id"])
                now = time.time()
                if not pending and now >= state["next_due_epoch"]:
                    pending = next_event(state)
                    log(f"event_due={pending}")

                if pending:
                    if final_receipt(pending):
                        receipt_epoch = time.time()
                        state["last_event_id"] = pending
                        state["last_receipt_epoch"] = receipt_epoch
                        state["next_due_epoch"] = receipt_epoch + INTERVAL_SECONDS
                        state["pending_event_id"] = ""
                        state["failure_count"] = 0
                        save_state(state)
                        log(
                            f"event_receipted={pending} "
                            f"next_due_epoch={int(state['next_due_epoch'])}"
                        )
                        write_runtime_status(
                            state,
                            runtime_state="RUNNING",
                            detail="receipt_confirmed_countdown_reset",
                        )
                        time.sleep(LOOP_SECONDS)
                        continue

                    attempt_epoch = time.time()
                    state["last_attempt_epoch"] = attempt_epoch
                    save_state(state)
                    rc, output = run_wake(pending)
                    if final_receipt(pending):
                        receipt_epoch = time.time()
                        state["last_event_id"] = pending
                        state["last_receipt_epoch"] = receipt_epoch
                        state["next_due_epoch"] = receipt_epoch + INTERVAL_SECONDS
                        state["pending_event_id"] = ""
                        state["failure_count"] = 0
                        save_state(state)
                        log(
                            f"event_receipted={pending} rc={rc} "
                            f"next_due_epoch={int(state['next_due_epoch'])} "
                            f"result={output}"
                        )
                        write_runtime_status(
                            state,
                            runtime_state="RUNNING",
                            detail="receipt_confirmed_countdown_reset",
                        )
                        time.sleep(LOOP_SECONDS)
                        continue

                    state["failure_count"] += 1
                    save_state(state)
                    log(
                        f"event_retry={pending} rc={rc} "
                        f"failure_count={state['failure_count']} result={output}"
                    )
                    write_runtime_status(
                        state,
                        runtime_state="RETRYING",
                        detail=f"waiting_for_final_receipt_rc_{rc}",
                    )
                    time.sleep(RETRY_SECONDS)
                    continue

                write_runtime_status(
                    state,
                    runtime_state="RUNNING",
                    detail="countdown_active",
                )
                sleep_for = min(
                    LOOP_SECONDS,
                    max(0.2, state["next_due_epoch"] - time.time()),
                )
                time.sleep(sleep_for)
            except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as exc:
                log(f"loop_error={type(exc).__name__}:{exc}")
                write_runtime_status(
                    state,
                    runtime_state="RETRYING",
                    detail=f"loop_error_{type(exc).__name__}",
                )
                time.sleep(RETRY_SECONDS)
    finally:
        try:
            if PIDFILE.read_text().strip() == str(os.getpid()):
                PIDFILE.unlink(missing_ok=True)
        except (FileNotFoundError, OSError):
            pass
        log(f"rolling_timer=STOP pid={os.getpid()}")


if __name__ == "__main__":
    raise SystemExit(main())
