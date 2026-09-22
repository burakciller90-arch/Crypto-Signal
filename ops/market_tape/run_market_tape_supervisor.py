from __future__ import annotations

import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import FrameType
from typing import IO

ROOT = Path("/Volumes/Crypto-504/Crypto-Signal")
STABLE = ROOT / "MarketTape"
PYTHON = ROOT / "Development/.venv/bin/python"
RUNTIME = STABLE / "ops/run_market_tape_runtime.py"
COLD_PYTHON = ROOT / "RuntimeEnvs/market-tape-cold/bin/python"
COLD_ARCHIVER = STABLE / "ops/market_tape/archive_hot_to_parquet.py"
TAPE_DIR = ROOT / "Development/runtime/market_tape"
STATUS = TAPE_DIR / "supervisor_status.json"
RUNTIME_OUT = ROOT / "ServiceLogs/market-tape-supervisor-runtime.out.log"
RUNTIME_ERR = ROOT / "ServiceLogs/market-tape-supervisor-runtime.err.log"

CONTROL_DIR = Path("/Users/crypto-signal-agent/.crypto-signal-runtime")
LOCK = CONTROL_DIR / "market-tape-supervisor.lock"
PID_FILE = CONTROL_DIR / "market-tape-supervisor.pid"
STOP_FILE = CONTROL_DIR / "market-tape-supervisor.stop"
DAEMON_LOG = (
    Path("/Users/crypto-signal-agent/Library/Logs/CryptoSignal")
    / "market-tape-supervisor.log"
)

RESTART_DELAY_SECONDS = 30

_stop_requested = False
_child: subprocess.Popen[bytes] | None = None


def _signal_stop(_signum: int, _frame: FrameType | None) -> None:
    global _stop_requested
    _stop_requested = True
    child = _child
    if child is not None and child.poll() is None:
        try:
            child.terminate()
        except ProcessLookupError:
            pass


def _write_status(payload: dict[str, object]) -> None:
    try:
        TAPE_DIR.mkdir(parents=True, exist_ok=True)
        complete = {
            **payload,
            "supervisor_pid": os.getpid(),
            "updated_at_epoch": int(time.time()),
            "real_capital": 0,
        }
        temporary = STATUS.with_suffix(".tmp")
        encoded = (
            json.dumps(
                complete,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
        with temporary.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, STATUS)
    except OSError as exc:
        print(
            "MARKET_TAPE_SUPERVISOR_STATUS_WRITE_ERROR "
            f"error={type(exc).__name__}:{exc}",
            file=sys.stderr,
            flush=True,
        )


def _runtime_dependencies_ready() -> tuple[bool, str]:
    if not ROOT.is_dir():
        return False, "ssd_root_unavailable"
    for path in (STABLE, PYTHON, RUNTIME, COLD_PYTHON, COLD_ARCHIVER):
        if not path.exists():
            return False, f"dependency_missing:{path}"
    if not os.access(PYTHON, os.X_OK):
        return False, "main_python_not_executable"
    if not os.access(COLD_PYTHON, os.X_OK):
        return False, "cold_python_not_executable"
    return True, "ready"


def _build_commit() -> str | None:
    path = STABLE / "BUILD_COMMIT"
    try:
        value = path.read_text().strip()
    except OSError:
        return None
    return value if value else None


def _open_runtime_logs() -> tuple[IO[bytes], IO[bytes]]:
    RUNTIME_OUT.parent.mkdir(parents=True, exist_ok=True)
    return RUNTIME_OUT.open("ab", buffering=0), RUNTIME_ERR.open(
        "ab",
        buffering=0,
    )


def _wait_or_stop(seconds: int) -> None:
    deadline = time.monotonic() + seconds
    while not _stop_requested and time.monotonic() < deadline:
        time.sleep(1)


def _daemonize() -> bool:
    os.environ.pop("RUNNER_TRACKING_ID", None)

    first_pid = os.fork()
    if first_pid > 0:
        return True

    os.setsid()

    second_pid = os.fork()
    if second_pid > 0:
        os._exit(0)

    os.chdir("/")
    os.umask(0o077)

    DAEMON_LOG.parent.mkdir(parents=True, exist_ok=True)
    stdin_fd = os.open("/dev/null", os.O_RDONLY)
    log_fd = os.open(
        DAEMON_LOG,
        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
        0o600,
    )
    try:
        os.dup2(stdin_fd, 0)
        os.dup2(log_fd, 1)
        os.dup2(log_fd, 2)
    finally:
        if stdin_fd > 2:
            os.close(stdin_fd)
        if log_fd > 2:
            os.close(log_fd)

    return False


def _entrypoint() -> int:
    arguments = sys.argv[1:]
    if arguments:
        if arguments != ["--daemonize"]:
            print(
                "MARKET_TAPE_SUPERVISOR_ERROR=UNSUPPORTED_ARGUMENTS",
                file=sys.stderr,
                flush=True,
            )
            return 64
        if _daemonize():
            return 0
    return main()


def main() -> int:
    global _child, _stop_requested

    if os.getuid() != 504:
        print(
            "MARKET_TAPE_SUPERVISOR_ERROR=UID_MISMATCH "
            f"expected=504 actual={os.getuid()}",
            file=sys.stderr,
            flush=True,
        )
        return 75

    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    STOP_FILE.unlink(missing_ok=True)

    with LOCK.open("a+") as lock_handle:
        try:
            fcntl.flock(
                lock_handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            print(
                "MARKET_TAPE_SUPERVISOR_ALREADY_RUNNING",
                flush=True,
            )
            return 0

        PID_FILE.write_text(f"{os.getpid()}\n")
        signal.signal(signal.SIGTERM, _signal_stop)
        signal.signal(signal.SIGINT, _signal_stop)

        restart_count = 0
        last_exit_code: int | None = None

        print(
            "MARKET_TAPE_SUPERVISOR_STARTED "
            f"pid={os.getpid()} REAL_CAPITAL=0",
            flush=True,
        )

        try:
            while not _stop_requested:
                if STOP_FILE.exists():
                    _stop_requested = True
                    break

                ready, reason = _runtime_dependencies_ready()
                if not ready:
                    _write_status(
                        {
                            "state": "waiting_for_runtime",
                            "reason": reason,
                            "restart_count": restart_count,
                            "last_child_exit_code": last_exit_code,
                            "build_commit": _build_commit(),
                        }
                    )
                    _wait_or_stop(RESTART_DELAY_SECONDS)
                    continue

                environment = os.environ.copy()
                environment.pop("RUNNER_TRACKING_ID", None)
                environment.update(
                    {
                        "HOME": "/Users/crypto-signal-agent",
                        "PYTHONPATH": str(STABLE / "src"),
                        "PYTHONUNBUFFERED": "1",
                    }
                )

                stdout_handle, stderr_handle = _open_runtime_logs()
                try:
                    child = subprocess.Popen(
                        [str(PYTHON), str(RUNTIME)],
                        stdin=subprocess.DEVNULL,
                        stdout=stdout_handle,
                        stderr=stderr_handle,
                        env=environment,
                        cwd=STABLE,
                        close_fds=True,
                    )
                    _child = child
                    _write_status(
                        {
                            "state": "running",
                            "child_pid": child.pid,
                            "restart_count": restart_count,
                            "last_child_exit_code": last_exit_code,
                            "build_commit": _build_commit(),
                        }
                    )
                    print(
                        "MARKET_TAPE_SUPERVISOR_CHILD_STARTED "
                        f"child_pid={child.pid} restart_count={restart_count}",
                        flush=True,
                    )

                    while (
                        child.poll() is None
                        and not _stop_requested
                        and not STOP_FILE.exists()
                    ):
                        time.sleep(1)

                    if _stop_requested or STOP_FILE.exists():
                        _stop_requested = True
                        if child.poll() is None:
                            child.terminate()
                            try:
                                child.wait(timeout=20)
                            except subprocess.TimeoutExpired:
                                child.kill()
                                child.wait(timeout=10)
                    else:
                        child.wait()

                    last_exit_code = child.returncode
                finally:
                    _child = None
                    stdout_handle.close()
                    stderr_handle.close()

                if _stop_requested:
                    break

                restart_count += 1
                _write_status(
                    {
                        "state": "restart_wait",
                        "restart_count": restart_count,
                        "last_child_exit_code": last_exit_code,
                        "build_commit": _build_commit(),
                    }
                )
                print(
                    "MARKET_TAPE_SUPERVISOR_CHILD_EXIT "
                    f"rc={last_exit_code} restart_count={restart_count}",
                    flush=True,
                )
                _wait_or_stop(RESTART_DELAY_SECONDS)

            _write_status(
                {
                    "state": "stopped",
                    "restart_count": restart_count,
                    "last_child_exit_code": last_exit_code,
                    "build_commit": _build_commit(),
                }
            )
            print(
                "MARKET_TAPE_SUPERVISOR_STOPPED REAL_CAPITAL=0",
                flush=True,
            )
            return 0
        finally:
            PID_FILE.unlink(missing_ok=True)
            STOP_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
