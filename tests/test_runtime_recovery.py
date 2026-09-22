from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest

from crypto_signal.runtime_recovery import (
    backup_and_restore_sqlite,
    bound_log_directory,
    bound_log_file,
)


def test_sqlite_backup_restore_includes_committed_wal_state(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    work = tmp_path / "work"

    connection = sqlite3.connect(source)
    try:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("CREATE TABLE evidence(id INTEGER PRIMARY KEY, value TEXT)")
        connection.commit()
        connection.executemany(
            "INSERT INTO evidence(value) VALUES(?)",
            [("alpha",), ("beta",), ("gamma",)],
        )
        connection.commit()

        wal_path = Path(f"{source}-wal")
        assert wal_path.is_file()
        assert wal_path.stat().st_size > 0

        report = backup_and_restore_sqlite(
            source,
            work_dir=work,
            label="evidence",
        )
    finally:
        connection.close()

    assert report.wal_bytes > 0
    assert report.table_names == ("evidence",)
    assert report.page_count > 0
    assert report.backup_page_count > 0
    assert report.restore_page_count > 0

    with sqlite3.connect(work / "evidence.backup.sqlite3") as backup:
        assert backup.execute("SELECT value FROM evidence ORDER BY id").fetchall() == [
            ("alpha",),
            ("beta",),
            ("gamma",),
        ]
        assert backup.execute("PRAGMA quick_check").fetchone() == ("ok",)

    with sqlite3.connect(work / "evidence.restore.sqlite3") as restored:
        assert restored.execute("SELECT count(*) FROM evidence").fetchone() == (3,)
        assert restored.execute("PRAGMA quick_check").fetchone() == ("ok",)


def test_bound_log_file_preserves_newest_bytes(tmp_path: Path) -> None:
    path = tmp_path / "service.log"
    payload = (b"old-" * 50) + (b"new-" * 50)
    path.write_bytes(payload)

    before, after, changed = bound_log_file(
        path,
        max_bytes=200,
        keep_bytes=80,
    )

    assert changed is True
    assert before == len(payload)
    assert after == 80
    assert path.read_bytes() == payload[-80:]


def test_bound_log_directory_ignores_small_files_and_symlinks(tmp_path: Path) -> None:
    large = tmp_path / "large.err"
    small = tmp_path / "small.out"
    other = tmp_path / "notes.txt"
    target = tmp_path / "target.log"
    link = tmp_path / "linked.log"

    large.write_bytes(b"x" * 300)
    small.write_bytes(b"y" * 20)
    other.write_bytes(b"z" * 300)
    target.write_bytes(b"t" * 300)
    link.symlink_to(target)

    changed = bound_log_directory(
        tmp_path,
        max_bytes=100,
        keep_bytes=40,
    )

    assert changed == (("large.err", 300, 40), ("target.log", 300, 40))
    assert large.stat().st_size == 40
    assert small.stat().st_size == 20
    assert other.stat().st_size == 300
    assert link.is_symlink()
    assert target.stat().st_size == 40


@pytest.mark.parametrize(
    ("max_bytes", "keep_bytes"),
    [(0, 1), (10, 0), (10, 11)],
)
def test_bound_log_file_rejects_invalid_bounds(
    tmp_path: Path,
    max_bytes: int,
    keep_bytes: int,
) -> None:
    path = tmp_path / "service.log"
    path.write_text("hello")

    with pytest.raises(ValueError, match="invalid log bounds"):
        bound_log_file(
            path,
            max_bytes=max_bytes,
            keep_bytes=keep_bytes,
        )


def test_r11_shell_scripts_are_syntax_valid() -> None:
    root = Path(__file__).resolve().parents[1]
    scripts = (
        root / "ops/ssd_runtime_supervisor.sh",
        root / "ops/r11/start_ssd_runtime.command",
        root / "ops/r11/runtime_terminal_watchdog.sh",
        root / "ops/r11/install_runtime_watchdog.sh",
    )
    for script in scripts:
        subprocess.run(
            ["/bin/bash", "-n", str(script)],
            check=True,
            capture_output=True,
            text=True,
        )


def test_ssd_supervisor_recovers_market_tape_through_terminal_tcc_tree() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "ops/ssd_runtime_supervisor.sh").read_text()

    assert 'MARKET_TAPE="$ROOT/MarketTape"' in source
    assert 'MARKET_TAPE_START="$MARKET_TAPE/ops/market_tape/start_market_tape_supervisor.sh"' in source
    assert 'MARKET_TAPE_PIDFILE="$MARKET_TAPE_CONTROL/market-tape-supervisor.pid"' in source
    assert 'MARKET_TAPE_ENABLE_FILE="$MARKET_TAPE_CONTROL/market-tape.enabled"' in source
    assert '[ ! -f "$MARKET_TAPE_ENABLE_FILE" ]' in source
    assert "market_tape_supervisor_pid_is_expected" in source
    assert "ensure_market_tape_supervisor" in source
    assert "[ $((now-last_market_tape)) -ge 30 ]" in source
    assert '/bin/bash "$MARKET_TAPE_START"' in source
    assert "market_tape_supervisor_start_failed" in source
