from __future__ import annotations

import hashlib
import sqlite3
import subprocess
from pathlib import Path

import pytest

from ops import runtime_recovery_hardening as recovery


def _layout(tmp_path: Path) -> Path:
    root = tmp_path / "Crypto-Signal"
    for path in (
        root / "Development/runtime/ledger",
        root / "Development/runtime/alerts",
        root / "Development/runtime/paper",
        root / "Development/runtime/data",
        root / "Product",
        root / "ServiceLogs",
    ):
        path.mkdir(parents=True, exist_ok=True)
    return root


def _db(path: Path, *, rows: int = 3, wal: bool = False) -> None:
    with sqlite3.connect(path) as connection:
        if wal:
            assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        connection.execute(
            "CREATE TABLE evidence (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO evidence(value) VALUES(?)",
            [(f"row-{index}",) for index in range(rows)],
        )
        connection.commit()


def _seed_critical(root: Path) -> None:
    for index, (_name, relative) in enumerate(recovery.CRITICAL_DATABASES):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _db(path, rows=index + 1, wal=index == 0)


def test_read_only_sqlite_backup_restore_handles_wal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _layout(tmp_path)
    monkeypatch.setattr(recovery, "DEFAULT_ROOT", root)
    _seed_critical(root)
    source = root / recovery.CRITICAL_DATABASES[0][1]
    before = source.stat()

    report = recovery.backup_sqlite_read_only(
        "signal_ledger",
        source,
        root / "RecoveryEvidence/test",
    )
    after = source.stat()

    assert report.source_quick_check == "ok"
    assert report.backup_quick_check == "ok"
    assert report.restore_quick_check == "ok"
    assert report.source_table_counts == (("evidence", 1),)
    assert report.backup_table_counts == report.source_table_counts
    assert report.restore_table_counts == report.source_table_counts
    assert len(report.backup_sha256) == 64
    assert hashlib.sha256(
        Path(report.backup_path).read_bytes()
    ).hexdigest() == report.backup_sha256
    assert before.st_size == after.st_size
    assert before.st_mtime_ns == after.st_mtime_ns


def test_runtime_report_is_bounded_and_stays_on_ssd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _layout(tmp_path)
    monkeypatch.setattr(recovery, "DEFAULT_ROOT", root)
    monkeypatch.setattr(recovery, "LEGACY_PROJECT_ROOTS", ())
    _seed_critical(root)
    (root / "ServiceLogs/supervisor.log").write_text("ok\n")

    report = recovery.build_runtime_recovery_report(
        root,
        root / "RecoveryEvidence/r11",
        max_log_bytes=1024,
    )

    assert len(report.databases) == 4
    assert report.oversized_logs == ()
    assert report.legacy_payloads_present == ()
    assert report.real_capital == 0
    assert (root / "RecoveryEvidence/r11/manifest.json").is_file()
    assert all(
        Path(item.backup_path).is_file()
        for item in report.databases
    )


def test_missing_or_noncanonical_root_fails_closed_without_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = tmp_path / "expected"
    monkeypatch.setattr(recovery, "DEFAULT_ROOT", canonical)

    with pytest.raises(
        recovery.RuntimeRecoveryError,
        match="canonical SSD path",
    ):
        recovery.require_canonical_root(tmp_path / "other")

    with pytest.raises(
        recovery.RuntimeRecoveryError,
        match="unavailable",
    ):
        recovery.require_canonical_root(canonical)

    assert not canonical.exists()


def test_log_policy_reports_oversized_without_mutating(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _layout(tmp_path)
    monkeypatch.setattr(recovery, "DEFAULT_ROOT", root)
    log = root / "ServiceLogs/dashboard.out.log"
    log.write_bytes(b"x" * 33)
    before = log.read_bytes()

    sizes, oversized = recovery.inspect_service_logs(root, max_bytes=32)

    assert ("dashboard.out.log", 33) in sizes
    assert oversized == ("dashboard.out.log",)
    assert log.read_bytes() == before


def test_empty_legacy_directory_is_not_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty = tmp_path / "Crypto-Signal"
    payload = tmp_path / "Crypto-Signal-Product"
    empty.mkdir()
    payload.mkdir()
    (payload / "unexpected.txt").write_text("payload")
    monkeypatch.setattr(
        recovery,
        "LEGACY_PROJECT_ROOTS",
        (empty, payload),
    )

    assert recovery.legacy_payloads_present() == (str(payload),)


@pytest.mark.parametrize(
    "path",
    (
        "ops/ssd_service_supervisor.sh",
        "ops/start_ssd_supervisor.command",
        "ops/ssd_supervisor_terminal_watchdog.sh",
    ),
)
def test_runtime_shell_scripts_are_valid_and_ssd_only(path: str) -> None:
    repo = Path(__file__).resolve().parents[1]
    script = repo / path
    subprocess.run(["bash", "-n", str(script)], check=True)
    source = script.read_text().lower()

    assert "/volumes/crypto-504/crypto-signal" in source
    assert "/users/crypto-signal-agent/crypto-signal" not in source
    assert "real_capital" not in source
    assert "place_order" not in source
    assert "submit_order" not in source
    assert "api_key" not in source
    assert "api_secret" not in source


def test_supervisor_contains_stale_pid_and_bounded_log_recovery() -> None:
    repo = Path(__file__).resolve().parents[1]
    source = (repo / "ops/ssd_service_supervisor.sh").read_text()

    assert "DASHBOARD_STALE_PID_REMOVED=YES" in source
    assert "DASHBOARD_PID_RECONCILED=YES" in source
    assert "DASHBOARD_DUPLICATE_FAIL_CLOSED=YES" in source
    assert "DASHBOARD_LOG_ROTATION_RESTART=YES" in source
    assert "SSD_RUNTIME_BECAME_UNAVAILABLE_FAIL_CLOSED=YES" in source
    assert "MAX_LOG_BYTES" in source
    assert "--alert-outbox" in source
    assert "--paper-ledger" in source
    assert "--candle-cache" in source


def test_supervisor_watchdog_is_terminal_mediated_and_duplicate_safe() -> None:
    repo = Path(__file__).resolve().parents[1]
    start = (repo / "ops/start_ssd_supervisor.command").read_text()
    watch = (repo / "ops/ssd_supervisor_terminal_watchdog.sh").read_text()

    assert "SUPERVISOR_ALREADY_ALIVE=YES" in start
    assert "SSD_SUPERVISOR_NOT_READY=YES" in start
    assert "SSD_RUNTIME_LAYOUT_NOT_READY=YES" in start
    assert "REQUESTING_TERMINAL_SUPERVISOR_START=YES" in watch
    assert "/usr/bin/open -gj -a Terminal" in watch
    assert "watchdog.lock" in watch
