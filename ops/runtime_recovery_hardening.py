"""Bounded SSD/runtime recovery verification helpers.

The live verifier is deliberately conservative:
- canonical SSD paths only, never a home-directory project fallback;
- source SQLite databases are opened read-only;
- backup/restore proof is performed on bounded copies;
- no live WAL checkpoint or mutation is performed;
- REAL_CAPITAL remains 0.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

REAL_CAPITAL = 0
DEFAULT_ROOT = Path("/Volumes/Crypto-504/Crypto-Signal")
LEGACY_PROJECT_ROOTS = (
    Path("/Users/crypto-signal-agent/Crypto-Signal"),
    Path("/Users/crypto-signal-agent/Crypto-Signal-Live"),
    Path("/Users/crypto-signal-agent/Crypto-Signal-Product"),
    Path("/Users/crypto-signal-agent/Crypto-Signal-Alerts"),
    Path("/Users/crypto-signal-agent/Crypto-Signal-Paper"),
)
CRITICAL_DATABASES = (
    ("signal_ledger", Path("Development/runtime/ledger/live_signal_ledger.sqlite3")),
    ("alert_outbox", Path("Development/runtime/alerts/alert_outbox.sqlite3")),
    ("paper_fund", Path("Development/runtime/paper/paper_fund.sqlite3")),
    ("candle_cache", Path("Development/runtime/data/live_base_15m_cache.sqlite3")),
)
SERVICE_LOG_NAMES = (
    "supervisor.log",
    "dashboard.out.log",
    "dashboard.err.log",
    "live.out.log",
    "live.err.log",
    "alert.out.log",
    "alert.err.log",
    "paper.out.log",
    "paper.err.log",
    "dry.out.log",
    "dry.err.log",
)


class RuntimeRecoveryError(RuntimeError):
    """Fail-closed runtime recovery verification error."""


@dataclass(frozen=True, slots=True)
class SqliteBackupReport:
    name: str
    source_path: str
    source_size_bytes: int
    source_wal_present: bool
    source_shm_present: bool
    source_quick_check: str
    source_table_counts: tuple[tuple[str, int], ...]
    backup_path: str
    backup_size_bytes: int
    backup_sha256: str
    backup_quick_check: str
    backup_table_counts: tuple[tuple[str, int], ...]
    restore_quick_check: str
    restore_table_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class RuntimeRecoveryReport:
    root: str
    evidence_dir: str
    databases: tuple[SqliteBackupReport, ...]
    service_log_sizes: tuple[tuple[str, int], ...]
    oversized_logs: tuple[str, ...]
    legacy_payloads_present: tuple[str, ...]
    real_capital: int = REAL_CAPITAL


def require_canonical_root(root: Path) -> Path:
    resolved = root.expanduser()
    if resolved != DEFAULT_ROOT:
        raise RuntimeRecoveryError(
            f"runtime root must be canonical SSD path: {DEFAULT_ROOT}"
        )
    if not resolved.is_dir():
        raise RuntimeRecoveryError("canonical SSD runtime root is unavailable")
    development = resolved / "Development"
    product = resolved / "Product"
    if not development.is_dir() or not product.is_dir():
        raise RuntimeRecoveryError("canonical SSD runtime layout is incomplete")
    return resolved


def live_database_paths(root: Path) -> tuple[tuple[str, Path], ...]:
    canonical = require_canonical_root(root)
    paths = tuple((name, canonical / relative) for name, relative in CRITICAL_DATABASES)
    missing = tuple(str(path) for _, path in paths if not path.is_file())
    if missing:
        raise RuntimeRecoveryError(
            "critical runtime database missing: " + ", ".join(missing)
        )
    return paths


def verify_sqlite_read_only(path: Path) -> tuple[str, tuple[tuple[str, int], ...]]:
    if not path.is_file():
        raise RuntimeRecoveryError(f"SQLite source missing: {path}")
    uri = f"file:{quote(str(path.resolve()), safe='/')}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
            if quick != "ok":
                raise RuntimeRecoveryError(f"SQLite quick_check failed: {path}: {quick}")
            tables = tuple(
                str(row[0])
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                    ORDER BY name
                    """
                ).fetchall()
            )
            counts = tuple(
                (table, int(connection.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0]))
                for table in tables
            )
    except sqlite3.Error as exc:
        raise RuntimeRecoveryError(f"SQLite read-only verification failed: {path}") from exc
    return quick, counts


def backup_sqlite_read_only(
    name: str,
    source: Path,
    evidence_dir: Path,
) -> SqliteBackupReport:
    source_quick, source_counts = verify_sqlite_read_only(source)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    backup = evidence_dir / f"{name}.backup.sqlite3"
    restore = evidence_dir / f"{name}.restore-proof.sqlite3"
    backup.unlink(missing_ok=True)
    restore.unlink(missing_ok=True)

    source_uri = f"file:{quote(str(source.resolve()), safe='/')}?mode=ro"
    try:
        with sqlite3.connect(source_uri, uri=True) as source_connection:
            with sqlite3.connect(backup) as backup_connection:
                source_connection.backup(backup_connection)
        backup_quick, backup_counts = verify_sqlite_read_only(backup)
        if backup_counts != source_counts:
            raise RuntimeRecoveryError(
                f"SQLite backup table counts diverged for {name}"
            )

        shutil.copy2(backup, restore)
        restore_quick, restore_counts = verify_sqlite_read_only(restore)
        if restore_counts != backup_counts:
            raise RuntimeRecoveryError(
                f"SQLite restore proof table counts diverged for {name}"
            )
    except (OSError, sqlite3.Error) as exc:
        raise RuntimeRecoveryError(f"SQLite backup/restore proof failed for {name}") from exc
    finally:
        restore.unlink(missing_ok=True)

    return SqliteBackupReport(
        name=name,
        source_path=str(source),
        source_size_bytes=source.stat().st_size,
        source_wal_present=Path(f"{source}-wal").exists(),
        source_shm_present=Path(f"{source}-shm").exists(),
        source_quick_check=source_quick,
        source_table_counts=source_counts,
        backup_path=str(backup),
        backup_size_bytes=backup.stat().st_size,
        backup_sha256=_sha256_file(backup),
        backup_quick_check=backup_quick,
        backup_table_counts=backup_counts,
        restore_quick_check=restore_quick,
        restore_table_counts=restore_counts,
    )


def inspect_service_logs(
    root: Path,
    *,
    max_bytes: int,
) -> tuple[tuple[tuple[str, int], ...], tuple[str, ...]]:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    log_dir = require_canonical_root(root) / "ServiceLogs"
    sizes: list[tuple[str, int]] = []
    oversized: list[str] = []
    for name in SERVICE_LOG_NAMES:
        path = log_dir / name
        size = path.stat().st_size if path.is_file() else 0
        sizes.append((name, size))
        if size > max_bytes:
            oversized.append(name)
    return tuple(sizes), tuple(oversized)


def legacy_payloads_present() -> tuple[str, ...]:
    present: list[str] = []
    for path in LEGACY_PROJECT_ROOTS:
        if path.exists():
            if path.is_dir() and not any(path.iterdir()):
                continue
            present.append(str(path))
        elif path.is_symlink():
            present.append(str(path))
    return tuple(present)


def build_runtime_recovery_report(
    root: Path,
    evidence_dir: Path,
    *,
    max_log_bytes: int = 16 * 1024 * 1024,
) -> RuntimeRecoveryReport:
    canonical = require_canonical_root(root)
    evidence = evidence_dir.expanduser()
    if canonical not in evidence.parents:
        raise RuntimeRecoveryError("recovery evidence must remain on canonical SSD")
    reports = tuple(
        backup_sqlite_read_only(name, path, evidence)
        for name, path in live_database_paths(canonical)
    )
    log_sizes, oversized = inspect_service_logs(
        canonical,
        max_bytes=max_log_bytes,
    )
    legacy = legacy_payloads_present()
    report = RuntimeRecoveryReport(
        root=str(canonical),
        evidence_dir=str(evidence),
        databases=reports,
        service_log_sizes=log_sizes,
        oversized_logs=oversized,
        legacy_payloads_present=legacy,
    )
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "manifest.json").write_text(
        json.dumps(_jsonable(asdict(report)), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def _jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument(
        "--max-log-bytes",
        type=int,
        default=16 * 1024 * 1024,
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        report = build_runtime_recovery_report(
            args.root,
            args.evidence_dir,
            max_log_bytes=args.max_log_bytes,
        )
    except RuntimeRecoveryError as exc:
        print(f"R11_RUNTIME_RECOVERY_FAIL={exc}")
        return 2

    print(json.dumps(_jsonable(asdict(report)), indent=2, sort_keys=True))
    if report.legacy_payloads_present:
        print("R11_LEGACY_PAYLOAD_PRESENT=YES")
        return 3
    if report.oversized_logs:
        print("R11_LOG_POLICY_FAIL=YES")
        return 4
    print("R11_SQLITE_BACKUP_RESTORE_PASS=YES")
    print("R11_LOG_POLICY_PASS=YES")
    print("R11_NO_LEGACY_PROJECT_FALLBACK_PASS=YES")
    print("R11_RUNTIME_RECOVERY_REPORT_PASS=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
