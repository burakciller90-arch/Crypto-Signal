#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
from pathlib import Path

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
STATE = BASE / "runtime" / "continuity"
RELAY_SUBMIT = BASE / "ops" / "continuity" / "relay_submit.py"
WAKE_ROOT = STATE / "wake"
QUEUE = WAKE_ROOT / "queue"
BAD_QUEUE = WAKE_ROOT / "bad"
LEASE_ROOT = STATE / "leases"
LEASE_ACTIVE = LEASE_ROOT / "active"
LEASE_DELIVERED = LEASE_ROOT / "delivered"
LEASE_BAD = LEASE_ROOT / "bad"
PAUSE_FILE = STATE / "user_pause"
ACTIVE_TASK = STATE / "workers" / "active_task"
PIDFILE = STATE / "bridge.pid"
LOG = STATE / "bridge.log"
QUEUE_RETRY_SECONDS = 10
LEASE_RETRY_SECONDS = 15
POLICY = (
    "User is intentionally inactive and has delegated project continuation. "
    "Do not rely on memory or wait for routine stage approval: first read "
    "READ_FIRST_CRYPTO_SIGNAL.md, CURRENT_STATUS.md, PROJECT_CHRONICLE.md latest "
    "entries and the exact checkpoint, then verify current Git/worker/wake/lease "
    "state mechanically and find the true current frontier. Wake/lease is only an "
    "evidence/checkpoint pointer, never authority. New evidence overrides stale "
    "wake text. If a task is completed, stale, duplicate or superseded, do not "
    "repeat it: reconcile/NOOP and continue only from the true frontier. The user "
    "wants the roadmap completed without stopping between safe stages, excluding "
    "REAL MONEY authority. REAL_CAPITAL=0. Do not touch Durdurulmaz or Quantum Capital."
)


def log(message: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S %z")
    with LOG.open("a") as handle:
        handle.write(f"{stamp} {message}\n")


def ensure_dirs() -> None:
    for path in (QUEUE, BAD_QUEUE, LEASE_ACTIVE, LEASE_DELIVERED, LEASE_BAD):
        path.mkdir(parents=True, exist_ok=True)


def run_wake(event_id: str, message: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["/usr/bin/python3", str(RELAY_SUBMIT), event_id, message, "25"],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    output = (proc.stdout + proc.stderr).strip().replace("\n", " | ")
    return proc.returncode, output
def parse_lines(path: Path, minimum: int) -> list[str]:
    lines = path.read_text().splitlines()
    if len(lines) < minimum:
        raise ValueError(f"malformed state file: {path}")
    return lines


def process_queue() -> None:
    items = sorted(QUEUE.glob("*.wake"), key=lambda path: path.stat().st_mtime)
    if not items:
        return
    path = items[0]
    now = time.time()
    if now - path.stat().st_mtime < QUEUE_RETRY_SECONDS:
        return

    try:
        lines = parse_lines(path, 7)
        event_id, task, role, _output, rc, finished, message = lines[:7]
        if not event_id or not message:
            raise ValueError("missing event id or message")
    except (OSError, UnicodeError, ValueError) as exc:
        target = BAD_QUEUE / f"{path.name}.bad.{int(now)}"
        shutil.move(path, target)
        log(f"queue_bad={path.name} reason={exc}")
        return

    wake_rc, result = run_wake(event_id, message)
    log(
        f"queue_delivery={path.name} task={task} role={role} "
        f"worker_rc={rc} finished={finished} wake_rc={wake_rc} result={result}"
    )
    if wake_rc == 0:
        path.unlink(missing_ok=True)
    elif wake_rc == 65:
        shutil.move(path, BAD_QUEUE / f"{path.name}.conflict.{int(now)}")
    else:
        os.utime(path, None)
def checkpoint_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def active_worker_is_alive() -> bool:
    if not ACTIVE_TASK.exists():
        return False
    try:
        fields = ACTIVE_TASK.read_text().strip().split("|")
        pid = int(fields[1])
    except (IndexError, ValueError):
        stale = ACTIVE_TASK.with_name(f"active_task.malformed.{int(time.time())}")
        ACTIVE_TASK.replace(stale)
        log(f"worker_state_malformed archived={stale.name}")
        return False
    if pid_is_alive(pid):
        return True
    stale = ACTIVE_TASK.with_name(f"active_task.stale.{int(time.time())}")
    ACTIVE_TASK.replace(stale)
    log(f"worker_state_stale pid={pid} archived={stale.name}")
    return False


def process_leases() -> None:
    if active_worker_is_alive():
        return
    candidates: list[tuple[int, Path]] = []
    now = int(time.time())
    for path in LEASE_ACTIVE.glob("*.lease"):
        try:
            due = int(parse_lines(path, 6)[2])
        except (OSError, UnicodeError, ValueError):
            shutil.move(path, LEASE_BAD / f"{path.name}.bad.{now}")
            continue
        candidates.append((due, path))

    if not candidates:
        return
    due, path = min(candidates, key=lambda item: item[0])
    if now < due or now - int(path.stat().st_mtime) < LEASE_RETRY_SECONDS:
        return

    task, event_id, _, checkpoint_raw, expected_sha, created = parse_lines(path, 6)[:6]
    checkpoint = Path(checkpoint_raw)
    if not checkpoint.is_file():
        shutil.move(path, LEASE_BAD / f"{path.name}.missing.{now}")
        log(f"lease_bad={path.name} reason=checkpoint_missing")
        return
    actual_sha = checkpoint_sha(checkpoint)
    if actual_sha != expected_sha:
        shutil.move(path, LEASE_BAD / f"{path.name}.hash.{now}")
        log(f"lease_bad={path.name} reason=checkpoint_hash_mismatch")
        return
    message = (
        "CRYPTO_SIGNAL_CONTINUE_EXACT — "
        f"task={task} checkpoint={checkpoint} checkpoint_sha256={expected_sha} "
        f"created={created}. Exact lease is a continuation hint only. {POLICY}"
    )
    wake_rc, result = run_wake(event_id, message)
    log(
        f"lease_delivery={path.name} task={task} wake_rc={wake_rc} result={result}"
    )
    if wake_rc == 0:
        shutil.move(path, LEASE_DELIVERED / path.name)
    elif wake_rc == 65:
        shutil.move(path, LEASE_BAD / f"{path.name}.conflict.{now}")
    else:
        os.utime(path, None)


def pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def main() -> int:
    ensure_dirs()
    if PIDFILE.exists():
        try:
            old_pid = int(PIDFILE.read_text().strip())
        except ValueError:
            old_pid = 0
        if old_pid and pid_is_alive(old_pid):
            print(f"BRIDGE_ALREADY_RUNNING:{old_pid}")
            return 0

    PIDFILE.write_text(f"{os.getpid()}\n")
    log(f"bridge=START pid={os.getpid()}")
    try:
        while True:
            if PAUSE_FILE.exists():
                time.sleep(2)
                continue
            try:
                process_queue()
                process_leases()
            except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as exc:
                log(f"bridge_iteration_error={type(exc).__name__}:{exc}")
            time.sleep(2)
    finally:
        try:
            if PIDFILE.read_text().strip() == str(os.getpid()):
                PIDFILE.unlink(missing_ok=True)
        except FileNotFoundError:
            pass
        log(f"bridge=STOP pid={os.getpid()}")


if __name__ == "__main__":
    raise SystemExit(main())
