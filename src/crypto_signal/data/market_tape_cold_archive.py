from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from crypto_signal.data.derivatives import DerivativesInstrumentType
from crypto_signal.data.liquidations import (
    LiquidatedPositionSide,
    LiquidationFeedCoverage,
    LiquidationObservation,
)
from crypto_signal.data.market_tape import (
    MarketTapeConflictError,
    MarketTapeLiquidationReplay,
)
from crypto_signal.data.market_tape_hotcold import (
    DEFAULT_MARKET_TAPE_HOTCOLD_POLICY,
    MarketTapeHotColdPolicy,
    archive_before_ms,
    directory_file_bytes,
)
from crypto_signal.data.models import DataSource, Exchange

COLD_ARCHIVE_SCHEMA_VERSION = "market-tape-cold-parquet-v1/2"
LEGACY_COLD_ARCHIVE_SCHEMA_VERSIONS = frozenset({"market-tape-cold-parquet-v1/1"})

_RAW_COLUMNS = (
    "event_identity",
    "exchange",
    "channel",
    "symbol",
    "event_kind",
    "source_timestamp_ms",
    "event_at_ms",
    "ingested_at_ms",
    "sequence",
    "update_id",
    "payload_json",
)
_ORDERBOOK_COLUMNS = (
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
)
_TRADE_COLUMNS = (
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
)
_DERIVATIVES_COLUMNS = (
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
)

_LIQUIDATION_COLUMNS = (
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
)
_LIQUIDATION_COVERAGE_COLUMNS = (
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
)


@dataclass(frozen=True, slots=True)
class _TableSpec:
    key: str
    table: str
    filename: str
    identity_column: str
    time_column: str
    columns: tuple[str, ...]
    raw_database: bool


_TABLE_SPECS = (
    _TableSpec(
        key="raw",
        table="raw_market_events",
        filename="raw.parquet",
        identity_column="event_identity",
        time_column="event_at_ms",
        columns=_RAW_COLUMNS,
        raw_database=True,
    ),
    _TableSpec(
        key="orderbooks",
        table="market_tape_orderbooks",
        filename="orderbooks.parquet",
        identity_column="snapshot_identity",
        time_column="event_at_ms",
        columns=_ORDERBOOK_COLUMNS,
        raw_database=False,
    ),
    _TableSpec(
        key="trades",
        table="market_tape_trades",
        filename="trades.parquet",
        identity_column="trade_identity",
        time_column="event_at_ms",
        columns=_TRADE_COLUMNS,
        raw_database=False,
    ),
    _TableSpec(
        key="derivatives",
        table="market_tape_derivatives",
        filename="derivatives.parquet",
        identity_column="observation_identity",
        time_column="event_at_ms",
        columns=_DERIVATIVES_COLUMNS,
        raw_database=False,
    ),
    _TableSpec(
        key="liquidations",
        table="market_tape_liquidations",
        filename="liquidations.parquet",
        identity_column="liquidation_identity",
        time_column="event_at_ms",
        columns=_LIQUIDATION_COLUMNS,
        raw_database=False,
    ),
    _TableSpec(
        key="liquidation_coverage",
        table="market_tape_liquidation_coverage",
        filename="liquidation_coverage.parquet",
        identity_column="coverage_identity",
        time_column="coverage_end_ms",
        columns=_LIQUIDATION_COVERAGE_COLUMNS,
        raw_database=False,
    ),
)

_LEGACY_TABLE_KEYS = frozenset({"raw", "orderbooks", "trades", "derivatives"})


@dataclass(frozen=True, slots=True)
class ColdArchivePartitionResult:
    partition_id: str
    window_start_ms: int
    window_end_ms: int
    archived_rows: int
    pruned_rows: int
    cold_bytes: int
    reused_existing_partition: bool


@dataclass(frozen=True, slots=True)
class ColdArchiveCycleResult:
    archive_before_ms: int
    partitions: tuple[ColdArchivePartitionResult, ...]
    cold_bytes: int

    @property
    def archived_rows(self) -> int:
        return sum(item.archived_rows for item in self.partitions)

    @property
    def pruned_rows(self) -> int:
        return sum(item.pruned_rows for item in self.partitions)


def archive_due_hot_partitions(
    *,
    hot_dir: Path,
    cold_dir: Path,
    now_ms: int,
    policy: MarketTapeHotColdPolicy = DEFAULT_MARKET_TAPE_HOTCOLD_POLICY,
) -> ColdArchiveCycleResult:
    if now_ms < 0:
        raise ValueError("now_ms cannot be negative")
    cutoff = archive_before_ms(now_ms=now_ms, policy=policy)
    if cutoff <= 0:
        return ColdArchiveCycleResult(
            archive_before_ms=cutoff,
            partitions=(),
            cold_bytes=directory_file_bytes(cold_dir),
        )

    normalized_db = hot_dir / "market_tape.sqlite3"
    raw_db = hot_dir / "raw_market_tape.sqlite3"
    starts = _eligible_partition_starts(
        normalized_db=normalized_db,
        raw_db=raw_db,
        before_ms=cutoff,
        partition_ms=policy.partition_ms,
        limit=policy.max_archive_partitions_per_cycle,
    )
    results: list[ColdArchivePartitionResult] = []
    for start_ms in starts:
        results.append(
            _archive_partition(
                normalized_db=normalized_db,
                raw_db=raw_db,
                cold_dir=cold_dir,
                start_ms=start_ms,
                end_ms=start_ms + policy.partition_ms,
            )
        )

    return ColdArchiveCycleResult(
        archive_before_ms=cutoff,
        partitions=tuple(results),
        cold_bytes=directory_file_bytes(cold_dir),
    )


def verify_cold_partition(path: Path) -> dict[str, Any]:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"cold archive manifest missing: {path}")
    payload = json.loads(manifest_path.read_text())
    if not isinstance(payload, dict):
        raise TypeError("cold archive manifest must be an object")
    schema_version = str(payload.get("schema_version", ""))
    specs = _specs_for_schema(schema_version)
    tables = payload.get("tables")
    if not isinstance(tables, dict):
        raise TypeError("cold archive tables manifest must be an object")

    for spec in specs:
        table_meta = tables.get(spec.key)
        if not isinstance(table_meta, dict):
            raise TypeError(f"cold archive table metadata missing: {spec.key}")
        rows = int(table_meta.get("rows", -1))
        expected_digest = str(table_meta.get("canonical_sha256", ""))
        if rows < 0 or not _is_sha256(expected_digest):
            raise ValueError(f"invalid cold archive table metadata: {spec.key}")
        filename = table_meta.get("filename")
        if rows == 0:
            if filename is not None:
                raise ValueError(f"empty cold archive table has file: {spec.key}")
            continue
        if filename != spec.filename:
            raise ValueError(f"cold archive filename mismatch: {spec.key}")
        parquet_path = path / spec.filename
        if not parquet_path.is_file():
            raise ValueError(f"cold archive parquet missing: {spec.key}")
        expected_file_hash = str(table_meta.get("file_sha256", ""))
        if not _is_sha256(expected_file_hash):
            raise ValueError(f"invalid cold archive file hash: {spec.key}")
        if _sha256_file(parquet_path) != expected_file_hash:
            raise ValueError(f"cold archive file hash mismatch: {spec.key}")
        restored = _read_parquet(parquet_path)
        if len(restored) != rows:
            raise ValueError(f"cold archive row count mismatch: {spec.key}")
        if _canonical_rows_sha256(restored) != expected_digest:
            raise ValueError(f"cold archive canonical digest mismatch: {spec.key}")
    return payload


def _archive_partition(
    *,
    normalized_db: Path,
    raw_db: Path,
    cold_dir: Path,
    start_ms: int,
    end_ms: int,
) -> ColdArchivePartitionResult:
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError("invalid cold archive window")

    rows_by_key = _read_partition_rows(
        normalized_db=normalized_db,
        raw_db=raw_db,
        start_ms=start_ms,
        end_ms=end_ms,
    )
    archived_rows = sum(len(rows) for rows in rows_by_key.values())
    if archived_rows <= 0:
        raise ValueError("cold archive partition cannot be empty")

    final_dir = _partition_path(cold_dir, start_ms)
    reused = final_dir.exists()
    if reused:
        manifest = verify_cold_partition(final_dir)
        _assert_hot_rows_are_archive_subset(
            path=final_dir,
            rows_by_key=rows_by_key,
        )
    else:
        manifest = _write_partition_atomic(
            final_dir=final_dir,
            rows_by_key=rows_by_key,
            start_ms=start_ms,
            end_ms=end_ms,
        )
        verify_cold_partition(final_dir)

    if int(manifest["window_start_ms"]) != start_ms:
        raise ValueError("cold archive start mismatch")
    if int(manifest["window_end_ms"]) != end_ms:
        raise ValueError("cold archive end mismatch")

    pruned_rows = _prune_hot_partition(
        normalized_db=normalized_db,
        raw_db=raw_db,
        start_ms=start_ms,
        end_ms=end_ms,
    )
    return ColdArchivePartitionResult(
        partition_id=str(manifest["partition_id"]),
        window_start_ms=start_ms,
        window_end_ms=end_ms,
        archived_rows=archived_rows,
        pruned_rows=pruned_rows,
        cold_bytes=directory_file_bytes(final_dir),
        reused_existing_partition=reused,
    )


def _write_partition_atomic(
    *,
    final_dir: Path,
    rows_by_key: dict[str, list[dict[str, object]]],
    start_ms: int,
    end_ms: int,
) -> dict[str, Any]:
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = final_dir.parent / (
        f".{final_dir.name}.partial-{os.getpid()}-{time.time_ns()}"
    )
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()

    tables_manifest: dict[str, dict[str, object]] = {}
    try:
        for spec in _TABLE_SPECS:
            rows = rows_by_key[spec.key]
            digest = _canonical_rows_sha256(rows)
            if not rows:
                tables_manifest[spec.key] = {
                    "rows": 0,
                    "filename": None,
                    "bytes": 0,
                    "file_sha256": None,
                    "canonical_sha256": digest,
                    "identity_column": spec.identity_column,
                }
                continue

            parquet_path = temporary / spec.filename
            _write_parquet(parquet_path, rows)
            restored = _read_parquet(parquet_path)
            if len(restored) != len(rows):
                raise ValueError(
                    f"cold archive write row mismatch: {spec.key}"
                )
            if _canonical_rows_sha256(restored) != digest:
                raise ValueError(
                    f"cold archive write digest mismatch: {spec.key}"
                )
            tables_manifest[spec.key] = {
                "rows": len(rows),
                "filename": spec.filename,
                "bytes": parquet_path.stat().st_size,
                "file_sha256": _sha256_file(parquet_path),
                "canonical_sha256": digest,
                "identity_column": spec.identity_column,
                "time_column": spec.time_column,
            }

        partition_id = _partition_id(start_ms)
        manifest: dict[str, Any] = {
            "schema_version": COLD_ARCHIVE_SCHEMA_VERSION,
            "partition_id": partition_id,
            "window_start_ms": start_ms,
            "window_end_ms": end_ms,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "format": "parquet",
            "compression": "zstd",
            "compression_level": 8,
            "tables": tables_manifest,
        }
        _write_json_atomic(temporary / "manifest.json", manifest)
        verify_cold_partition(temporary)
        os.replace(temporary, final_dir)
        return manifest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _assert_hot_rows_are_archive_subset(
    *,
    path: Path,
    rows_by_key: dict[str, list[dict[str, object]]],
) -> None:
    manifest = verify_cold_partition(path)
    tables = manifest["tables"]
    if not isinstance(tables, dict):
        raise TypeError("cold archive tables manifest must be an object")

    for spec in _TABLE_SPECS:
        hot_rows = rows_by_key[spec.key]
        if not hot_rows:
            continue
        meta = tables.get(spec.key)
        if meta is None:
            raise ValueError(
                f"late hot rows absent from legacy cold archive: {spec.key}"
            )
        if not isinstance(meta, dict):
            raise TypeError(
                f"cold archive table metadata must be an object: {spec.key}"
            )
        if int(meta["rows"]) == 0:
            raise ValueError(
                f"late hot rows conflict with empty cold partition: {spec.key}"
            )
        cold_rows = _read_parquet(path / spec.filename)
        cold_by_identity = {
            str(row[spec.identity_column]): _canonical_row_bytes(row)
            for row in cold_rows
        }
        for row in hot_rows:
            identity = str(row[spec.identity_column])
            archived = cold_by_identity.get(identity)
            if archived is None:
                raise ValueError(
                    f"late hot row absent from immutable cold archive: "
                    f"{spec.key}:{identity}"
                )
            if archived != _canonical_row_bytes(row):
                raise ValueError(
                    f"hot/cold identity conflict: {spec.key}:{identity}"
                )


def _read_partition_rows(
    *,
    normalized_db: Path,
    raw_db: Path,
    start_ms: int,
    end_ms: int,
) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    for spec in _TABLE_SPECS:
        db = raw_db if spec.raw_database else normalized_db
        result[spec.key] = _read_rows(
            db=db,
            table=spec.table,
            columns=spec.columns,
            start_ms=start_ms,
            end_ms=end_ms,
            identity_column=spec.identity_column,
            time_column=spec.time_column,
        )
    return result


def _read_rows(
    *,
    db: Path,
    table: str,
    columns: tuple[str, ...],
    start_ms: int,
    end_ms: int,
    identity_column: str,
    time_column: str,
) -> list[dict[str, object]]:
    if not db.is_file():
        return []
    connection = sqlite3.connect(
        f"file:{db}?mode=ro",
        uri=True,
        timeout=10.0,
    )
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        check = connection.execute("PRAGMA quick_check").fetchone()
        if check is None or str(check[0]) != "ok":
            raise ValueError(f"hot SQLite quick_check failed: {db}")
        if not _table_exists(connection, table):
            return []
        sql = (
            f"SELECT {','.join(columns)} FROM {table} "
            f"WHERE {time_column} >= ? AND {time_column} < ? "
            f"ORDER BY {time_column}, {identity_column}"
        )
        return [
            dict(row)
            for row in connection.execute(
                sql,
                (start_ms, end_ms),
            ).fetchall()
        ]
    finally:
        connection.close()


def _eligible_partition_starts(
    *,
    normalized_db: Path,
    raw_db: Path,
    before_ms: int,
    partition_ms: int,
    limit: int,
) -> tuple[int, ...]:
    if before_ms <= 0:
        return ()
    starts: set[int] = set()
    for spec in _TABLE_SPECS:
        db = raw_db if spec.raw_database else normalized_db
        if not db.is_file():
            continue
        connection = sqlite3.connect(
            f"file:{db}?mode=ro",
            uri=True,
            timeout=10.0,
        )
        try:
            connection.execute("PRAGMA query_only=ON")
            if not _table_exists(connection, spec.table):
                continue
            rows = connection.execute(
                f"""
                SELECT
                    CAST({spec.time_column} / ? AS INTEGER) * ? AS partition_start
                FROM {spec.table}
                WHERE {spec.time_column} < ?
                GROUP BY partition_start
                ORDER BY partition_start
                LIMIT ?
                """,
                (partition_ms, partition_ms, before_ms, limit),
            ).fetchall()
            starts.update(int(row[0]) for row in rows)
        finally:
            connection.close()
    return tuple(sorted(starts)[:limit])


def _prune_hot_partition(
    *,
    normalized_db: Path,
    raw_db: Path,
    start_ms: int,
    end_ms: int,
) -> int:
    total = 0
    raw_specs = tuple(spec for spec in _TABLE_SPECS if spec.raw_database)
    normalized_specs = tuple(spec for spec in _TABLE_SPECS if not spec.raw_database)
    if raw_db.is_file():
        total += _delete_specs(
            db=raw_db,
            specs=raw_specs,
            start_ms=start_ms,
            end_ms=end_ms,
        )
    if normalized_db.is_file():
        total += _delete_specs(
            db=normalized_db,
            specs=normalized_specs,
            start_ms=start_ms,
            end_ms=end_ms,
        )
    return total


def _delete_specs(
    *,
    db: Path,
    specs: tuple[_TableSpec, ...],
    start_ms: int,
    end_ms: int,
) -> int:
    connection = sqlite3.connect(db, timeout=30.0)
    deleted = 0
    try:
        connection.execute("BEGIN IMMEDIATE")
        for spec in specs:
            if not _table_exists(connection, spec.table):
                continue
            cursor = connection.execute(
                f"DELETE FROM {spec.table} "
                f"WHERE {spec.time_column} >= ? AND {spec.time_column} < ?",
                (start_ms, end_ms),
            )
            deleted += max(0, int(cursor.rowcount))
        connection.commit()
        checkpoint = connection.execute(
            "PRAGMA wal_checkpoint(TRUNCATE)"
        ).fetchone()
        if checkpoint is None or int(checkpoint[0]) != 0:
            raise ValueError(f"hot SQLite checkpoint busy after prune: {db}")
        check = connection.execute("PRAGMA quick_check").fetchone()
        if check is None or str(check[0]) != "ok":
            raise ValueError(f"hot SQLite quick_check failed after prune: {db}")
        return deleted
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def cold_liquidation_replay(
    *,
    cold_dir: Path,
    coverage_identity: str,
    as_of_ms: int,
) -> MarketTapeLiquidationReplay:
    if as_of_ms < 0:
        raise ValueError("cold liquidation replay as_of_ms must be non-negative")

    coverage: LiquidationFeedCoverage | None = None
    event_by_identity: dict[str, LiquidationObservation] = {}

    for partition in _cold_partition_paths(cold_dir):
        manifest = verify_cold_partition(partition)
        if str(manifest["schema_version"]) != COLD_ARCHIVE_SCHEMA_VERSION:
            continue
        tables = manifest["tables"]
        if not isinstance(tables, dict):
            raise TypeError("cold archive tables manifest must be an object")

        coverage_meta = tables.get("liquidation_coverage")
        if isinstance(coverage_meta, dict) and int(coverage_meta["rows"]) > 0:
            for row in _read_parquet(partition / "liquidation_coverage.parquet"):
                if str(row["coverage_identity"]) != coverage_identity:
                    continue
                candidate = _coverage_from_payload_json(str(row["payload_json"]))
                if coverage is not None and coverage != candidate:
                    raise MarketTapeConflictError(
                        "cold liquidation coverage identity conflicts"
                    )
                coverage = candidate

    if coverage is None:
        raise MarketTapeConflictError(
            "cold liquidation replay coverage is not persisted"
        )
    if coverage.observed_at_ms > as_of_ms:
        raise MarketTapeConflictError(
            "cold liquidation replay coverage is future evidence"
        )

    for partition in _cold_partition_paths(cold_dir):
        manifest = verify_cold_partition(partition)
        if str(manifest["schema_version"]) != COLD_ARCHIVE_SCHEMA_VERSION:
            continue
        tables = manifest["tables"]
        if not isinstance(tables, dict):
            raise TypeError("cold archive tables manifest must be an object")
        meta = tables.get("liquidations")
        if not isinstance(meta, dict) or int(meta["rows"]) <= 0:
            continue
        for row in _read_parquet(partition / "liquidations.parquet"):
            event = _liquidation_from_payload_json(str(row["payload_json"]))
            if (
                event.exchange is not coverage.exchange
                or event.instrument_type is not coverage.instrument_type
                or event.symbol != coverage.symbol
            ):
                continue
            if not (
                coverage.coverage_start_ms
                <= event.event_at_ms
                <= coverage.coverage_end_ms
            ):
                continue
            if max(
                event.event_at_ms,
                event.source_timestamp_ms,
                event.ingested_at_ms,
            ) > as_of_ms:
                continue
            existing = event_by_identity.get(event.liquidation_identity)
            if existing is not None and existing != event:
                raise MarketTapeConflictError(
                    "cold liquidation identity conflicts across partitions"
                )
            event_by_identity[event.liquidation_identity] = event

    events = tuple(
        sorted(
            event_by_identity.values(),
            key=lambda item: (
                item.event_at_ms,
                item.source_timestamp_ms,
                item.source_row_index,
                item.liquidation_identity,
            ),
        )
    )
    return MarketTapeLiquidationReplay(
        coverage=coverage,
        events=events,
        as_of_ms=as_of_ms,
    )


def _cold_partition_paths(cold_dir: Path) -> tuple[Path, ...]:
    if not cold_dir.is_dir():
        return ()
    return tuple(
        sorted(
            path.parent
            for path in cold_dir.glob(
                "year=*/month=*/day=*/hour=*/manifest.json"
            )
        )
    )


def _coverage_from_payload_json(payload_json: str) -> LiquidationFeedCoverage:
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise TypeError("cold liquidation coverage payload must be an object")
    return LiquidationFeedCoverage(
        coverage_identity=str(payload["coverage_identity"]),
        exchange=Exchange(str(payload["exchange"])),
        instrument_type=DerivativesInstrumentType(str(payload["instrument_type"])),
        symbol=str(payload["symbol"]),
        coverage_start_ms=int(payload["coverage_start_ms"]),
        coverage_end_ms=int(payload["coverage_end_ms"]),
        observed_at_ms=int(payload["observed_at_ms"]),
        source=DataSource(str(payload["source"])),
        adapter_version=str(payload["adapter_version"]),
    )


def _liquidation_from_payload_json(payload_json: str) -> LiquidationObservation:
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise TypeError("cold liquidation payload must be an object")
    return LiquidationObservation(
        liquidation_identity=str(payload["liquidation_identity"]),
        exchange=Exchange(str(payload["exchange"])),
        instrument_type=DerivativesInstrumentType(str(payload["instrument_type"])),
        symbol=str(payload["symbol"]),
        liquidated_position_side=LiquidatedPositionSide(
            str(payload["liquidated_position_side"])
        ),
        size=Decimal(str(payload["size"])),
        bankruptcy_price=Decimal(str(payload["bankruptcy_price"])),
        event_at_ms=int(payload["event_at_ms"]),
        source_timestamp_ms=int(payload["source_timestamp_ms"]),
        ingested_at_ms=int(payload["ingested_at_ms"]),
        source_row_index=int(payload["source_row_index"]),
        source=DataSource(str(payload["source"])),
        adapter_version=str(payload["adapter_version"]),
    )


def _specs_for_schema(schema_version: str) -> tuple[_TableSpec, ...]:
    if schema_version == COLD_ARCHIVE_SCHEMA_VERSION:
        return _TABLE_SPECS
    if schema_version in LEGACY_COLD_ARCHIVE_SCHEMA_VERSIONS:
        return tuple(
            spec for spec in _TABLE_SPECS if spec.key in _LEGACY_TABLE_KEYS
        )
    raise ValueError("unsupported cold archive schema")


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _partition_path(cold_dir: Path, start_ms: int) -> Path:
    dt = datetime.fromtimestamp(start_ms / 1000, tz=UTC)
    return (
        cold_dir
        / f"year={dt:%Y}"
        / f"month={dt:%m}"
        / f"day={dt:%d}"
        / f"hour={dt:%H}"
    )


def _partition_id(start_ms: int) -> str:
    return datetime.fromtimestamp(start_ms / 1000, tz=UTC).strftime(
        "%Y%m%dT%H0000Z"
    )


def _write_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError("cannot write empty Parquet table")
    pa, pq = _pyarrow_modules()
    table = pa.Table.from_pylist(rows)
    pq.write_table(
        table,
        path,
        compression="zstd",
        compression_level=8,
        use_dictionary=True,
        write_statistics=True,
    )
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _read_parquet(path: Path) -> list[dict[str, object]]:
    _pa, pq = _pyarrow_modules()
    rows = pq.ParquetFile(path).read().to_pylist()
    if not isinstance(rows, list):
        raise TypeError("Parquet reader returned non-list rows")
    return [
        {str(key): value for key, value in row.items()}
        for row in rows
    ]


def _pyarrow_modules() -> tuple[Any, Any]:
    try:
        pa = importlib.import_module("pyarrow")
        pq = importlib.import_module("pyarrow.parquet")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PyArrow is required for Market Tape cold archive"
        ) from exc
    return pa, pq


def _canonical_rows_sha256(rows: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(_canonical_row_bytes(row))
    return digest.hexdigest()


def _canonical_row_bytes(row: dict[str, object]) -> bytes:
    return (
        json.dumps(
            row,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    encoded = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )
