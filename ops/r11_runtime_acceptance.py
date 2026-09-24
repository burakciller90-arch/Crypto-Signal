from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

from crypto_signal.runtime_recovery import backup_and_restore_sqlite

DEFAULT_ROOT = Path("/Volumes/Crypto-504/Crypto-Signal")
LEGACY_HOME = Path("/Users/crypto-signal-agent")


def _ps_text() -> str:
    result = subprocess.run(
        ["/bin/ps", "-axo", "pid=,ppid=,user=,comm=,args="],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _health() -> dict[str, Any]:
    with urllib.request.urlopen(
        "http://127.0.0.1:48700/api/health",
        timeout=5,
    ) as response:
        decoded: object = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, dict):
        raise TypeError("dashboard health payload must be a JSON object")
    payload: dict[str, Any] = {
        str(key): value for key, value in decoded.items()
    }
    if payload.get("status") != "ok":
        raise RuntimeError("dashboard health status is not ok")
    if payload.get("real_capital") != 0:
        raise RuntimeError("REAL_CAPITAL boundary violated")
    if payload.get("read_only") is not True:
        raise RuntimeError("dashboard must remain read-only")
    if payload.get("ledger_present") is not True:
        raise RuntimeError("signal ledger missing")
    if payload.get("alert_outbox_present") is not True:
        raise RuntimeError("alert outbox missing")
    return payload


def _parsed_process(
    line: str,
) -> tuple[int, str, str] | None:
    parts = line.strip().split(maxsplit=4)
    if len(parts) < 5:
        return None
    pid_text, _ppid, _user, command_name, args = parts
    if not pid_text.isdigit():
        return None
    return int(pid_text), Path(command_name).name, args


def _matching_supervisor_pids(ps: str, supervisor_needle: str) -> list[int]:
    result: list[int] = []
    for line in ps.splitlines():
        parsed = _parsed_process(line)
        if parsed is None:
            continue
        pid, command_name, args = parsed
        if command_name != "bash":
            continue
        if supervisor_needle not in args.split():
            continue
        result.append(pid)
    return result


def _matching_dashboard_pids(ps: str, dashboard_needle: str) -> list[int]:
    result: list[int] = []
    for line in ps.splitlines():
        parsed = _parsed_process(line)
        if parsed is None:
            continue
        pid, _command_name, args = parsed
        argv = args.split()
        if not argv:
            continue
        if not Path(argv[0]).name.lower().startswith("python"):
            continue
        if dashboard_needle not in argv:
            continue
        try:
            port_index = argv.index("--port")
        except ValueError:
            continue
        if port_index + 1 >= len(argv) or argv[port_index + 1] != "48700":
            continue
        result.append(pid)
    return result


def _matching_runner_pids(ps: str, runner_needle: str) -> list[int]:
    result: list[int] = []
    for line in ps.splitlines():
        parsed = _parsed_process(line)
        if parsed is None:
            continue
        pid, _command_name, args = parsed
        if args.strip() == runner_needle:
            result.append(pid)
    return result


def _assert_no_legacy_runtime_payload() -> tuple[str, ...]:
    forbidden = (
        LEGACY_HOME / "Crypto-Signal/runtime/ledger/live_signal_ledger.sqlite3",
        LEGACY_HOME / "Crypto-Signal/runtime/data/live_base_15m_cache.sqlite3",
        LEGACY_HOME / "Crypto-Signal/runtime/alerts/alert_outbox.sqlite3",
        LEGACY_HOME / "Crypto-Signal/runtime/paper/paper_fund.sqlite3",
        LEGACY_HOME / "Crypto-Signal-Live",
        LEGACY_HOME / "Crypto-Signal-Product",
        LEGACY_HOME / "Crypto-Signal-Alerts",
        LEGACY_HOME / "Crypto-Signal-Paper",
    )
    present = tuple(str(path) for path in forbidden if path.exists())
    if present:
        raise RuntimeError(f"legacy runtime payload remains: {present}")
    return tuple(str(path) for path in forbidden)


def _assert_process_topology(root: Path) -> dict[str, int]:
    ps = _ps_text()
    supervisor_needle = str(root / "ssd-service-supervisor.sh")
    dashboard_needle = str(root / "Product/ops/run_dashboard.py")
    runner_needle = str(root / "Runner/bin/Runner.Listener run --startuptype service")

    supervisors = _matching_supervisor_pids(ps, supervisor_needle)
    dashboards = _matching_dashboard_pids(ps, dashboard_needle)
    runners = _matching_runner_pids(ps, runner_needle)
    if len(supervisors) != 1:
        raise RuntimeError(f"expected exactly one SSD supervisor, got {supervisors}")
    if len(dashboards) != 1:
        raise RuntimeError(f"expected exactly one SSD dashboard, got {dashboards}")
    if len(runners) != 1:
        raise RuntimeError(f"expected exactly one SSD runner listener, got {runners}")

    legacy_process_needles = (
        "/Users/crypto-signal-agent/actions-runner-crypto/",
        "/Users/crypto-signal-agent/Crypto-Signal-Product/",
        "/Users/crypto-signal-agent/Crypto-Signal-Live/",
        "/Users/crypto-signal-agent/Crypto-Signal-Alerts/",
        "/Users/crypto-signal-agent/Crypto-Signal-Paper/",
    )
    active_legacy = tuple(
        needle for needle in legacy_process_needles if needle in ps
    )
    if active_legacy:
        raise RuntimeError(f"legacy runtime process path active: {active_legacy}")

    return {
        "supervisor_pid": supervisors[0],
        "dashboard_pid": dashboards[0],
        "runner_listener_pid": runners[0],
    }


def _assert_root(root: Path) -> None:
    expected = DEFAULT_ROOT
    if root.resolve() != expected.resolve():
        raise RuntimeError(f"acceptance root must be canonical SSD root: {expected}")
    required_dirs = (
        root / "Development",
        root / "Live",
        root / "Product",
        root / "Alerts",
        root / "Paper",
        root / "Runner",
        root / "ServiceLogs",
    )
    missing = [str(path) for path in required_dirs if not path.is_dir()]
    if missing:
        raise RuntimeError(f"required SSD runtime dirs missing: {missing}")
    supervisor = root / "ssd-service-supervisor.sh"
    if not supervisor.is_file():
        raise RuntimeError("SSD supervisor script missing")


def _database_paths(root: Path) -> tuple[tuple[str, Path], ...]:
    dev = root / "Development"
    return (
        ("signal_ledger", dev / "runtime/ledger/live_signal_ledger.sqlite3"),
        ("alert_outbox", dev / "runtime/alerts/alert_outbox.sqlite3"),
        ("paper_ledger", dev / "runtime/paper/paper_fund.sqlite3"),
        ("candle_cache", dev / "runtime/data/live_base_15m_cache.sqlite3"),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--min-free-bytes", type=int, default=1024 * 1024 * 1024)
    args = parser.parse_args()

    root = args.root
    _assert_root(root)
    legacy_absent = _assert_no_legacy_runtime_payload()
    topology = _assert_process_topology(root)
    health = _health()

    disk = shutil.disk_usage(root)
    if disk.free < args.min_free_bytes:
        raise RuntimeError(
            f"SSD free space below recovery floor: {disk.free} < {args.min_free_bytes}"
        )

    with tempfile.TemporaryDirectory(prefix="crypto-r11-backup-") as raw:
        work_dir = Path(raw)
        db_reports = []
        for label, path in _database_paths(root):
            report = backup_and_restore_sqlite(
                path,
                work_dir=work_dir,
                label=label,
            )
            db_reports.append(
                {
                    "label": label,
                    "source": report.source,
                    "source_bytes": report.source_bytes,
                    "wal_bytes": report.wal_bytes,
                    "table_names": report.table_names,
                    "page_count": report.page_count,
                    "backup_page_count": report.backup_page_count,
                    "restore_page_count": report.restore_page_count,
                }
            )

    result = {
        "status": "ok",
        "root": str(root),
        "real_capital": 0,
        "read_only": True,
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "min_free_bytes": args.min_free_bytes,
        },
        "topology": topology,
        "health": health,
        "databases": db_reports,
        "legacy_runtime_absent": legacy_absent,
    }
    print(json.dumps(result, sort_keys=True))
    print("R11_RUNTIME_AUDIT_PASS=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
