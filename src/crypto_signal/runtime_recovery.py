from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


@dataclass(frozen=True, slots=True)
class SQLiteRecoveryReport:
    source: str
    source_bytes: int
    wal_bytes: int
    table_names: tuple[str, ...]
    page_count: int
    backup_page_count: int
    restore_page_count: int


def _readonly_connection(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    uri = "file:" + quote(str(path.resolve()), safe="/") + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _quick_check(connection: sqlite3.Connection) -> None:
    row = connection.execute("PRAGMA quick_check").fetchone()
    if row != ("ok",):
        raise RuntimeError(f"sqlite quick_check failed: {row!r}")


def _table_names(connection: sqlite3.Connection) -> tuple[str, ...]:
    return tuple(
        row[0]
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
    )


def backup_and_restore_sqlite(
    source_path: Path,
    *,
    work_dir: Path,
    label: str,
) -> SQLiteRecoveryReport:
    """Create a consistent SQLite backup and restore it into a second DB.

    The source is opened read-only. SQLite's backup API includes committed WAL
    state without checkpointing, truncating, or otherwise mutating the source.
    """

    work_dir.mkdir(parents=True, exist_ok=True)
    backup_path = work_dir / f"{label}.backup.sqlite3"
    restore_path = work_dir / f"{label}.restore.sqlite3"
    backup_path.unlink(missing_ok=True)
    restore_path.unlink(missing_ok=True)

    with _readonly_connection(source_path) as source:
        _quick_check(source)
        source_tables = _table_names(source)
        source_page_count = int(source.execute("PRAGMA page_count").fetchone()[0])
        with sqlite3.connect(backup_path) as backup:
            source.backup(backup)
            _quick_check(backup)

    with _readonly_connection(backup_path) as backup_ro:
        _quick_check(backup_ro)
        backup_tables = _table_names(backup_ro)
        backup_page_count = int(backup_ro.execute("PRAGMA page_count").fetchone()[0])
        with sqlite3.connect(restore_path) as restore:
            backup_ro.backup(restore)
            _quick_check(restore)

    with _readonly_connection(restore_path) as restored:
        _quick_check(restored)
        restore_tables = _table_names(restored)
        restore_page_count = int(restored.execute("PRAGMA page_count").fetchone()[0])

    if backup_tables != source_tables or restore_tables != source_tables:
        raise RuntimeError("sqlite backup/restore schema mismatch")
    if source_page_count <= 0 or backup_page_count <= 0 or restore_page_count <= 0:
        raise RuntimeError("sqlite backup/restore page count invalid")

    wal_path = Path(f"{source_path}-wal")
    return SQLiteRecoveryReport(
        source=str(source_path),
        source_bytes=source_path.stat().st_size,
        wal_bytes=wal_path.stat().st_size if wal_path.is_file() else 0,
        table_names=source_tables,
        page_count=source_page_count,
        backup_page_count=backup_page_count,
        restore_page_count=restore_page_count,
    )


def bound_log_file(
    path: Path,
    *,
    max_bytes: int,
    keep_bytes: int,
) -> tuple[int, int, bool]:
    """Bound a regular log file in place while preserving its newest bytes."""

    if max_bytes <= 0 or keep_bytes <= 0 or keep_bytes > max_bytes:
        raise ValueError("invalid log bounds")
    if path.is_symlink() or not path.is_file():
        return (0, 0, False)

    before = path.stat().st_size
    if before <= max_bytes:
        return (before, before, False)

    with path.open("rb") as source:
        source.seek(max(0, before - keep_bytes))
        tail = source.read()

    with path.open("r+b") as target:
        target.seek(0)
        target.truncate(0)
        target.write(tail)
        target.flush()
        os.fsync(target.fileno())

    after = path.stat().st_size
    if after > keep_bytes:
        raise RuntimeError("bounded log remains larger than keep_bytes")
    return (before, after, True)


def bound_log_directory(
    log_dir: Path,
    *,
    max_bytes: int,
    keep_bytes: int,
) -> tuple[tuple[str, int, int], ...]:
    if not log_dir.is_dir():
        return ()
    bounded: list[tuple[str, int, int]] = []
    for path in sorted(log_dir.iterdir()):
        if path.suffix not in {".log", ".out", ".err"}:
            continue
        before, after, changed = bound_log_file(
            path,
            max_bytes=max_bytes,
            keep_bytes=keep_bytes,
        )
        if changed:
            bounded.append((path.name, before, after))
    return tuple(bounded)
