"""Read-only Product Truth for Hot Market Tape and Cold Archive runtime evidence.

This module deliberately does not use MarketTapeStore read helpers because those
helpers call initialize(). Product GETs must never create or migrate runtime
databases. Runtime process liveness is not inferred from persisted evidence.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ACCEPTED_MARKET_TAPE_SCHEMAS = frozenset(
    {"market-tape-schema-v1/1", "market-tape-schema-v1/2"}
)
_ACCEPTED_COLD_SCHEMAS = frozenset(
    {"market-tape-cold-parquet-v1/1", "market-tape-cold-parquet-v1/2"}
)
_COLD_TABLE_FILENAMES = {
    "raw": "raw.parquet",
    "orderbooks": "orderbooks.parquet",
    "trades": "trades.parquet",
    "derivatives": "derivatives.parquet",
    "liquidations": "liquidations.parquet",
    "liquidation_coverage": "liquidation_coverage.parquet",
}
_COLD_SCHEMA_KEYS = {
    "market-tape-cold-parquet-v1/1": frozenset(
        {"raw", "orderbooks", "trades", "derivatives"}
    ),
    "market-tape-cold-parquet-v1/2": frozenset(_COLD_TABLE_FILENAMES),
}
_CORE_TABLES = (
    ("orderbooks", "market_tape_orderbooks", "event_at_ms"),
    ("trades", "market_tape_trades", "event_at_ms"),
    ("derivatives", "market_tape_derivatives", "event_at_ms"),
)
_V12_TABLES = (
    ("liquidations", "market_tape_liquidations", "event_at_ms"),
    (
        "liquidation_coverage",
        "market_tape_liquidation_coverage",
        "coverage_end_ms",
    ),
)

_TABLE_REQUIRED_COLUMNS = {
    "market_tape_meta": frozenset({"key", "value"}),
    "market_tape_orderbooks": frozenset(
        {
            "snapshot_identity",
            "exchange",
            "market_type",
            "symbol",
            "event_at_ms",
            "source_timestamp_ms",
            "ingested_at_ms",
            "update_id",
            "sequence",
            "source",
            "adapter_version",
            "payload_json",
        }
    ),
    "market_tape_trades": frozenset(
        {
            "trade_identity",
            "exchange",
            "market_type",
            "symbol",
            "event_at_ms",
            "source_timestamp_ms",
            "ingested_at_ms",
            "exec_id",
            "sequence",
            "aggressor_side",
            "source",
            "adapter_version",
            "payload_json",
        }
    ),
    "market_tape_derivatives": frozenset(
        {
            "observation_identity",
            "semantic_identity",
            "exchange",
            "instrument_type",
            "symbol",
            "event_at_ms",
            "source_timestamp_ms",
            "ingested_at_ms",
            "source",
            "adapter_version",
            "payload_json",
        }
    ),
    "market_tape_liquidations": frozenset(
        {
            "liquidation_identity",
            "provider_identity",
            "exchange",
            "instrument_type",
            "symbol",
            "event_at_ms",
            "source_timestamp_ms",
            "ingested_at_ms",
            "source_row_index",
            "liquidated_position_side",
            "source",
            "adapter_version",
            "payload_json",
        }
    ),
    "market_tape_liquidation_coverage": frozenset(
        {
            "coverage_identity",
            "exchange",
            "instrument_type",
            "symbol",
            "coverage_start_ms",
            "coverage_end_ms",
            "observed_at_ms",
            "source",
            "adapter_version",
            "payload_json",
        }
    ),
}


@dataclass(frozen=True, slots=True)
class MarketTapeRuntimeTruth:
    schema_version: str
    total_rows: int
    counts: tuple[tuple[str, int], ...]
    latest_event_at_ms: int | None
    latest_event_age_ms: int | None
    quick_check_ok: bool
    read_only_verified: bool
    collection_process_status: str = "NOT_MEASURED"
    production_authority: bool = False
    real_capital: int = 0

    def __post_init__(self) -> None:
        if self.schema_version not in _ACCEPTED_MARKET_TAPE_SCHEMAS:
            raise ValueError("unsupported Market Tape schema")
        if self.total_rows < 0:
            raise ValueError("Market Tape total rows cannot be negative")
        if self.counts != tuple(sorted(self.counts)):
            raise ValueError("Market Tape counts must be canonical")
        if any(value < 0 for _, value in self.counts):
            raise ValueError("Market Tape table count cannot be negative")
        if sum(value for _, value in self.counts) != self.total_rows:
            raise ValueError("Market Tape total row count mismatch")
        if self.latest_event_at_ms is not None and self.latest_event_at_ms < 0:
            raise ValueError("Market Tape latest event time cannot be negative")
        if self.latest_event_age_ms is not None and self.latest_event_age_ms < 0:
            raise ValueError("Market Tape latest event age cannot be negative")
        if not self.quick_check_ok or not self.read_only_verified:
            raise ValueError("Market Tape Product Truth requires verified read-only state")
        if self.collection_process_status != "NOT_MEASURED":
            raise ValueError("Market Tape persistence cannot assert process liveness")
        if self.production_authority or self.real_capital != 0:
            raise ValueError("Market Tape Product Truth cannot grant authority")


@dataclass(frozen=True, slots=True)
class ColdArchiveRuntimeTruth:
    partition_count: int
    verified_partition_count: int
    latest_partition_end_ms: int | None
    verified_rows: int
    verified_file_bytes: int
    integrity_scope: str
    canonical_row_digest_replay: str = "NOT_MEASURED"
    archive_process_status: str = "NOT_MEASURED"
    read_only_verified: bool = True
    production_authority: bool = False
    real_capital: int = 0

    def __post_init__(self) -> None:
        if self.partition_count < 0 or self.verified_partition_count < 0:
            raise ValueError("Cold Archive partition counts cannot be negative")
        if self.verified_partition_count > self.partition_count:
            raise ValueError("Cold Archive verified count exceeds total partitions")
        if self.latest_partition_end_ms is not None and self.latest_partition_end_ms < 0:
            raise ValueError("Cold Archive latest partition time cannot be negative")
        if self.verified_rows < 0 or self.verified_file_bytes < 0:
            raise ValueError("Cold Archive verified metrics cannot be negative")
        if not self.integrity_scope:
            raise ValueError("Cold Archive integrity scope cannot be empty")
        if self.canonical_row_digest_replay != "NOT_MEASURED":
            raise ValueError("Product adapter does not replay Parquet canonical rows")
        if self.archive_process_status != "NOT_MEASURED":
            raise ValueError("Cold Archive evidence cannot assert process liveness")
        if not self.read_only_verified:
            raise ValueError("Cold Archive Product Truth must be read-only verified")
        if self.production_authority or self.real_capital != 0:
            raise ValueError("Cold Archive Product Truth cannot grant authority")


@dataclass(frozen=True, slots=True)
class _ColdManifest:
    path: Path
    window_end_ms: int
    rows: int
    file_bytes: int


def read_market_tape_runtime_truth(
    path: Path,
    *,
    observed_at_ms: int,
) -> MarketTapeRuntimeTruth:
    if observed_at_ms < 0:
        raise ValueError("Market Tape observation time cannot be negative")
    if not path.is_file():
        raise ValueError("Market Tape runtime database missing")

    uri = f"{path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        quick = connection.execute("PRAGMA quick_check").fetchone()
        if quick is None or str(quick[0]).lower() != "ok":
            raise ValueError("Market Tape SQLite quick_check failed")

        tables = {
            str(row[0])
            for row in connection.execute(
                """SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'"""
            ).fetchall()
        }
        if "market_tape_meta" not in tables:
            raise ValueError("Market Tape metadata table missing")
        schema_row = connection.execute(
            """SELECT value FROM market_tape_meta
            WHERE key='schema_version'"""
        ).fetchone()
        if schema_row is None:
            raise ValueError("Market Tape schema version missing")
        schema_version = str(schema_row[0])
        if schema_version not in _ACCEPTED_MARKET_TAPE_SCHEMAS:
            raise ValueError("Market Tape schema version mismatch")

        required = list(_CORE_TABLES)
        if schema_version == "market-tape-schema-v1/2":
            required.extend(_V12_TABLES)

        _verify_required_columns(connection, "market_tape_meta")
        for _label, table, _time_column in required:
            if table not in tables:
                raise ValueError(f"Market Tape required table missing: {table}")
            _verify_required_columns(connection, table)

        counts: list[tuple[str, int]] = []
        latest_values: list[int] = []
        for label, table, time_column in required:
            row_count = int(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            )
            counts.append((label, row_count))
            latest = connection.execute(
                f"SELECT MAX({time_column}) FROM {table}"
            ).fetchone()[0]
            if latest is not None:
                latest_values.append(int(latest))

    latest_event_at_ms = max(latest_values) if latest_values else None
    if latest_event_at_ms is not None and latest_event_at_ms > observed_at_ms:
        raise ValueError("Market Tape contains future evidence at observation time")
    latest_age_ms = (
        None
        if latest_event_at_ms is None
        else observed_at_ms - latest_event_at_ms
    )
    canonical_counts = tuple(sorted(counts))
    return MarketTapeRuntimeTruth(
        schema_version=schema_version,
        total_rows=sum(value for _, value in canonical_counts),
        counts=canonical_counts,
        latest_event_at_ms=latest_event_at_ms,
        latest_event_age_ms=latest_age_ms,
        quick_check_ok=True,
        read_only_verified=True,
    )


def read_cold_archive_runtime_truth(
    cold_dir: Path,
    *,
    verify_limit: int = 24,
) -> ColdArchiveRuntimeTruth:
    if verify_limit <= 0 or verify_limit > 500:
        raise ValueError("Cold Archive verify_limit must be inside 1..500")
    if not cold_dir.is_dir():
        raise ValueError("Cold Archive runtime directory missing")

    manifest_paths = tuple(sorted(cold_dir.rglob("manifest.json")))
    if not manifest_paths:
        return ColdArchiveRuntimeTruth(
            partition_count=0,
            verified_partition_count=0,
            latest_partition_end_ms=None,
            verified_rows=0,
            verified_file_bytes=0,
            integrity_scope="NO_PARTITIONS",
        )

    parsed = tuple(_parse_cold_manifest(path) for path in manifest_paths)
    ordered = tuple(
        sorted(parsed, key=lambda item: (item.window_end_ms, str(item.path)))
    )
    selected = ordered[-verify_limit:]
    for item in selected:
        _verify_cold_manifest_files(item.path)

    all_verified = len(selected) == len(ordered)
    scope = (
        "ALL_PARTITIONS_FILE_SHA256"
        if all_verified
        else f"LATEST_{len(selected)}_OF_{len(ordered)}_PARTITIONS_FILE_SHA256"
    )
    return ColdArchiveRuntimeTruth(
        partition_count=len(ordered),
        verified_partition_count=len(selected),
        latest_partition_end_ms=ordered[-1].window_end_ms,
        verified_rows=sum(item.rows for item in selected),
        verified_file_bytes=sum(item.file_bytes for item in selected),
        integrity_scope=scope,
    )


def _verify_required_columns(
    connection: sqlite3.Connection,
    table: str,
) -> None:
    expected = _TABLE_REQUIRED_COLUMNS[table]
    observed = {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    missing = expected - observed
    if missing:
        raise ValueError(
            f"Market Tape required columns missing from {table}: "
            + ",".join(sorted(missing))
        )


def _parse_cold_manifest(path: Path) -> _ColdManifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("Cold Archive manifest must be an object")
    schema_version = str(raw.get("schema_version", ""))
    if schema_version not in _ACCEPTED_COLD_SCHEMAS:
        raise ValueError("Cold Archive schema version mismatch")
    start = _required_non_negative_int(raw, "window_start_ms")
    end = _required_non_negative_int(raw, "window_end_ms")
    if end <= start:
        raise ValueError("Cold Archive partition window is invalid")
    tables = raw.get("tables")
    if not isinstance(tables, dict) or not tables:
        raise TypeError("Cold Archive table manifest missing")
    expected_keys = _COLD_SCHEMA_KEYS[schema_version]
    if frozenset(tables) != expected_keys:
        raise ValueError("Cold Archive table keys do not match schema")

    rows = 0
    file_bytes = 0
    for key, value in tables.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            raise TypeError("Cold Archive table metadata invalid")
        table_rows = _required_non_negative_int(value, "rows")
        rows += table_rows
        filename = value.get("filename")
        if table_rows == 0:
            if filename is not None:
                raise ValueError("empty Cold Archive table cannot reference file")
            continue
        if not isinstance(filename, str) or not filename:
            raise TypeError("Cold Archive filename missing")
        expected_filename = _COLD_TABLE_FILENAMES[key]
        if filename != expected_filename:
            raise ValueError(f"Cold Archive filename mismatch: {key}")
        expected_hash = value.get("file_sha256")
        if not isinstance(expected_hash, str) or not _is_sha256(expected_hash):
            raise ValueError("Cold Archive file SHA256 missing")
        expected_bytes = _required_non_negative_int(value, "bytes")
        file_bytes += expected_bytes
        canonical_hash = value.get("canonical_sha256")
        if not isinstance(canonical_hash, str) or not _is_sha256(canonical_hash):
            raise ValueError("Cold Archive canonical SHA256 missing")
    return _ColdManifest(
        path=path.parent,
        window_end_ms=end,
        rows=rows,
        file_bytes=file_bytes,
    )


def _verify_cold_manifest_files(partition_dir: Path) -> None:
    raw = json.loads((partition_dir / "manifest.json").read_text(encoding="utf-8"))
    tables = raw.get("tables")
    if not isinstance(tables, dict):
        raise TypeError("Cold Archive table manifest missing")
    for key, value in tables.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            raise TypeError("Cold Archive table metadata invalid")
        rows = _required_non_negative_int(value, "rows")
        if rows == 0:
            continue
        filename = value.get("filename")
        expected_hash = value.get("file_sha256")
        expected_bytes = _required_non_negative_int(value, "bytes")
        if not isinstance(filename, str):
            raise TypeError("Cold Archive filename invalid")
        if filename != _COLD_TABLE_FILENAMES[key]:
            raise ValueError(f"Cold Archive filename mismatch: {key}")
        if not isinstance(expected_hash, str) or not _is_sha256(expected_hash):
            raise ValueError("Cold Archive file SHA256 invalid")
        file_path = partition_dir / filename
        if not file_path.is_file():
            raise ValueError(f"Cold Archive partition file missing: {filename}")
        if file_path.stat().st_size != expected_bytes:
            raise ValueError(f"Cold Archive partition file size mismatch: {filename}")
        if _sha256_file(file_path) != expected_hash:
            raise ValueError(f"Cold Archive partition file hash mismatch: {filename}")


def _required_non_negative_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool):
        raise TypeError(f"{key} must be integer")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.isdigit():
        parsed = int(value)
    else:
        raise TypeError(f"{key} must be integer")
    if parsed < 0:
        raise ValueError(f"{key} cannot be negative")
    return parsed


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)
