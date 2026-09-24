"""Read-only Product Truth for Hot Market Tape and Cold Archive runtime evidence.

This module deliberately does not use MarketTapeStore read helpers because those
helpers call initialize(). Product GETs must never create or migrate runtime
databases. Runtime process liveness is not inferred from persisted evidence.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crypto_signal.data.market_tape_cold_archive import verify_cold_partition

_ACCEPTED_MARKET_TAPE_SCHEMAS = frozenset(
    {"market-tape-schema-v1/1", "market-tape-schema-v1/2"}
)
_COLLECTOR_RUNTIME_SCHEMA = "market-tape-collector-runtime-v1/2"
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


def _pin_live_read_snapshot(
    connection: sqlite3.Connection,
    observed_at_ms: int | None,
    *,
    label: str,
) -> int:
    if observed_at_ms is not None and observed_at_ms < 0:
        raise ValueError(f"{label} observation time cannot be negative")
    connection.execute("BEGIN")
    connection.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
    if observed_at_ms is not None:
        return observed_at_ms
    return time.time_ns() // 1_000_000


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
class MarketTapeCollectorRuntimeTruth:
    schema_version: str
    provider: str
    source: str
    symbols: tuple[str, ...]
    instance_identity: str
    start_kind: str
    previous_instance_identity: str | None
    process_id: int
    started_at_ms: int
    heartbeat_identity: str | None
    heartbeat_sequence_no: int | None
    heartbeat_observed_at_ms: int | None
    heartbeat_age_ms: int | None
    last_successful_ingestion_ms: int | None
    ingestion_age_ms: int | None
    observed_messages_total: int
    normalized_rows_total: int
    raw_rows_total: int
    process_evidence_status: str
    quick_check_ok: bool = True
    read_only_verified: bool = True
    production_authority: bool = False
    real_capital: int = 0

    def __post_init__(self) -> None:
        if self.schema_version != _COLLECTOR_RUNTIME_SCHEMA:
            raise ValueError("unsupported collector runtime Product schema")
        if not self.provider or not self.source:
            raise ValueError("collector runtime provider/source missing")
        if not self.symbols or tuple(sorted(set(self.symbols))) != self.symbols:
            raise ValueError("collector runtime symbols are not canonical")
        if self.process_id <= 0 or self.started_at_ms < 0:
            raise ValueError("collector runtime process/start values invalid")
        if self.start_kind not in {"start", "restart"}:
            raise ValueError("collector runtime start kind invalid")
        _require_sha256(self.instance_identity, "collector instance identity")
        if self.start_kind == "start" and self.previous_instance_identity is not None:
            raise ValueError("collector initial instance cannot have predecessor")
        if self.start_kind == "restart":
            if self.previous_instance_identity is None:
                raise ValueError("collector restart predecessor missing")
            _require_sha256(
                self.previous_instance_identity,
                "collector previous instance identity",
            )
        if self.heartbeat_identity is None:
            if any(
                value is not None
                for value in (
                    self.heartbeat_sequence_no,
                    self.heartbeat_observed_at_ms,
                    self.heartbeat_age_ms,
                )
            ):
                raise ValueError("collector heartbeat fields are inconsistent")
            if self.process_evidence_status != "NO_HEARTBEAT":
                raise ValueError("collector missing heartbeat status mismatch")
        else:
            _require_sha256(self.heartbeat_identity, "collector heartbeat identity")
            if (
                self.heartbeat_sequence_no is None
                or self.heartbeat_sequence_no <= 0
                or self.heartbeat_observed_at_ms is None
                or self.heartbeat_age_ms is None
            ):
                raise ValueError("collector heartbeat evidence is incomplete")
            if self.heartbeat_age_ms < 0:
                raise ValueError("collector heartbeat age cannot be negative")
            if self.process_evidence_status not in {
                "HEARTBEAT_FRESH",
                "HEARTBEAT_STALE",
            }:
                raise ValueError("collector heartbeat status invalid")
        if self.last_successful_ingestion_ms is None:
            if self.ingestion_age_ms is not None:
                raise ValueError("collector ingestion age without ingestion")
        elif self.ingestion_age_ms is None or self.ingestion_age_ms < 0:
            raise ValueError("collector ingestion age invalid")
        if min(
            self.observed_messages_total,
            self.normalized_rows_total,
            self.raw_rows_total,
        ) < 0:
            raise ValueError("collector runtime counters cannot be negative")
        if not self.quick_check_ok or not self.read_only_verified:
            raise ValueError("collector runtime Product Truth must be read-only")
        if self.production_authority or self.real_capital != 0:
            raise ValueError("collector runtime Product Truth cannot grant authority")


def read_market_tape_collector_runtime_truth(
    path: Path,
    *,
    observed_at_ms: int | None,
    heartbeat_freshness_ms: int = 30_000,
) -> MarketTapeCollectorRuntimeTruth | None:
    if not 1 <= heartbeat_freshness_ms <= 300_000:
        raise ValueError("collector heartbeat freshness must be inside 1..300000 ms")
    if not path.is_file():
        raise ValueError("collector runtime database missing")

    uri = f"{path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        observation = _pin_live_read_snapshot(
            connection,
            observed_at_ms,
            label="collector runtime",
        )
        quick = connection.execute("PRAGMA quick_check").fetchone()
        if quick is None or str(quick[0]).lower() != "ok":
            raise ValueError("collector runtime SQLite quick_check failed")

        tables = {
            str(row[0])
            for row in connection.execute(
                """SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'"""
            ).fetchall()
        }
        required_tables = {
            "collector_runtime_meta",
            "collector_instances",
            "collector_heartbeats",
        }
        if not required_tables.issubset(tables):
            raise ValueError("collector runtime required table missing")
        _verify_collector_runtime_columns(connection)

        schema_row = connection.execute(
            """SELECT value FROM collector_runtime_meta
            WHERE key='schema_version'"""
        ).fetchone()
        if schema_row is None or str(schema_row[0]) != _COLLECTOR_RUNTIME_SCHEMA:
            raise ValueError("collector runtime schema version mismatch")

        instance_row = connection.execute(
            """SELECT instance_identity, payload_json
            FROM collector_instances
            ORDER BY started_at_ms DESC, instance_identity DESC
            LIMIT 1"""
        ).fetchone()
        if instance_row is None:
            return None

        instance_identity = str(instance_row["instance_identity"])
        instance_payload_json = str(instance_row["payload_json"])
        _verify_payload_identity(
            instance_identity,
            instance_payload_json,
            "collector instance",
        )
        instance_payload = json.loads(instance_payload_json)
        if not isinstance(instance_payload, dict):
            raise TypeError("collector instance payload must be object")
        if str(instance_payload.get("schema_version")) != _COLLECTOR_RUNTIME_SCHEMA:
            raise ValueError("collector instance payload schema mismatch")

        heartbeat_row = connection.execute(
            """SELECT heartbeat_identity, payload_json
            FROM collector_heartbeats
            WHERE instance_identity=?
            ORDER BY sequence_no DESC
            LIMIT 1""",
            (instance_identity,),
        ).fetchone()

    heartbeat_identity: str | None = None
    heartbeat_sequence_no: int | None = None
    heartbeat_observation: int | None = None
    heartbeat_age_ms: int | None = None
    last_successful_ingestion_ms: int | None = None
    ingestion_age_ms: int | None = None
    observed_messages_total = 0
    normalized_rows_total = 0
    raw_rows_total = 0
    process_evidence_status = "NO_HEARTBEAT"

    if heartbeat_row is not None:
        heartbeat_identity = str(heartbeat_row["heartbeat_identity"])
        heartbeat_payload_json = str(heartbeat_row["payload_json"])
        _verify_payload_identity(
            heartbeat_identity,
            heartbeat_payload_json,
            "collector heartbeat",
        )
        heartbeat_payload = json.loads(heartbeat_payload_json)
        if not isinstance(heartbeat_payload, dict):
            raise TypeError("collector heartbeat payload must be object")
        if str(heartbeat_payload.get("schema_version")) != _COLLECTOR_RUNTIME_SCHEMA:
            raise ValueError("collector heartbeat payload schema mismatch")
        if str(heartbeat_payload.get("instance_identity")) != instance_identity:
            raise ValueError("collector heartbeat/instance lineage mismatch")

        heartbeat_sequence_no = int(heartbeat_payload["sequence_no"])
        heartbeat_observation = int(heartbeat_payload["observation"])
        if heartbeat_observation > observation:
            raise ValueError("collector heartbeat is future evidence")
        heartbeat_age_ms = observation - heartbeat_observation
        process_evidence_status = (
            "HEARTBEAT_FRESH"
            if heartbeat_age_ms <= heartbeat_freshness_ms
            else "HEARTBEAT_STALE"
        )
        ingestion_raw = heartbeat_payload.get("last_successful_ingestion_ms")
        if ingestion_raw is not None:
            last_successful_ingestion_ms = int(ingestion_raw)
            if last_successful_ingestion_ms > observation:
                raise ValueError("collector ingestion is future evidence")
            ingestion_age_ms = observation - last_successful_ingestion_ms
        observed_messages_total = int(
            heartbeat_payload["observed_messages_total"]
        )
        normalized_rows_total = int(heartbeat_payload["normalized_rows_total"])
        raw_rows_total = int(heartbeat_payload["raw_rows_total"])

    symbols_raw = instance_payload.get("symbols")
    if not isinstance(symbols_raw, list):
        raise TypeError("collector instance symbols must be array")
    symbols = tuple(str(value) for value in symbols_raw)
    previous_raw = instance_payload.get("previous_instance_identity")
    previous = None if previous_raw is None else str(previous_raw)

    return MarketTapeCollectorRuntimeTruth(
        schema_version=str(instance_payload["schema_version"]),
        provider=str(instance_payload["provider"]),
        source=str(instance_payload["source"]),
        symbols=symbols,
        instance_identity=instance_identity,
        start_kind=str(instance_payload["start_kind"]),
        previous_instance_identity=previous,
        process_id=int(instance_payload["process_id"]),
        started_at_ms=int(instance_payload["started_at_ms"]),
        heartbeat_identity=heartbeat_identity,
        heartbeat_sequence_no=heartbeat_sequence_no,
        heartbeat_observation=heartbeat_observation,
        heartbeat_age_ms=heartbeat_age_ms,
        last_successful_ingestion_ms=last_successful_ingestion_ms,
        ingestion_age_ms=ingestion_age_ms,
        observed_messages_total=observed_messages_total,
        normalized_rows_total=normalized_rows_total,
        raw_rows_total=raw_rows_total,
        process_evidence_status=process_evidence_status,
    )


@dataclass(frozen=True, slots=True)
class ColdArchiveRuntimeTruth:
    partition_count: int
    verified_partition_count: int
    latest_partition_end_ms: int | None
    verified_rows: int
    verified_file_bytes: int
    integrity_scope: str
    canonical_row_digest_replay: str = "NOT_MEASURED"
    canonical_replay_verified_partition_count: int = 0
    canonical_replay_scope: str = "NOT_MEASURED"
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
        if self.canonical_row_digest_replay not in {
            "NOT_MEASURED",
            "VERIFIED",
        }:
            raise ValueError("unsupported Cold Archive canonical replay status")
        if (
            self.canonical_replay_verified_partition_count < 0
            or self.canonical_replay_verified_partition_count
            > self.verified_partition_count
        ):
            raise ValueError("Cold Archive canonical replay count is invalid")
        if self.canonical_row_digest_replay == "NOT_MEASURED":
            if self.canonical_replay_verified_partition_count != 0:
                raise ValueError(
                    "unmeasured Cold Archive replay cannot claim verified partitions"
                )
            if self.canonical_replay_scope != "NOT_MEASURED":
                raise ValueError(
                    "unmeasured Cold Archive replay scope must remain explicit"
                )
        else:
            if self.canonical_replay_verified_partition_count <= 0:
                raise ValueError(
                    "verified Cold Archive replay requires verified partition"
                )
            if not self.canonical_replay_scope:
                raise ValueError("verified Cold Archive replay scope missing")
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
    observed_at_ms: int | None,
) -> MarketTapeRuntimeTruth:
    if not path.is_file():
        raise ValueError("Market Tape runtime database missing")

    uri = f"{path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        observation = _pin_live_read_snapshot(
            connection,
            observed_at_ms,
            label="Market Tape",
        )
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
    if latest_event_at_ms is not None and latest_event_at_ms > observation:
        raise ValueError("Market Tape contains future evidence at observation time")
    latest_age_ms = (
        None
        if latest_event_at_ms is None
        else observation - latest_event_at_ms
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
    canonical_replay_limit: int = 3,
) -> ColdArchiveRuntimeTruth:
    if verify_limit <= 0 or verify_limit > 500:
        raise ValueError("Cold Archive verify_limit must be inside 1..500")
    if canonical_replay_limit <= 0 or canonical_replay_limit > 500:
        raise ValueError(
            "Cold Archive canonical_replay_limit must be inside 1..500"
        )
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

    replay_status = "NOT_MEASURED"
    replay_count = 0
    replay_scope = "NOT_MEASURED"
    if importlib.util.find_spec("pyarrow") is not None:
        effective_replay_limit = min(
            canonical_replay_limit,
            len(selected),
        )
        replay_selected = selected[-effective_replay_limit:]
        for item in replay_selected:
            verify_cold_partition(item.path)
        replay_count = len(replay_selected)
        if replay_count:
            replay_status = "VERIFIED"
            replay_scope = (
                "ALL_FILE_VERIFIED_PARTITIONS_CANONICAL_ROW_SHA256"
                if replay_count == len(selected)
                else (
                    f"LATEST_{replay_count}_OF_{len(selected)}_"
                    "FILE_VERIFIED_PARTITIONS_CANONICAL_ROW_SHA256"
                )
            )

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
        canonical_row_digest_replay=replay_status,
        canonical_replay_verified_partition_count=replay_count,
        canonical_replay_scope=replay_scope,
    )

def _verify_collector_runtime_columns(
    connection: sqlite3.Connection,
) -> None:
    expected = {
        "collector_runtime_meta": {"key", "value"},
        "collector_instances": {
            "instance_identity",
            "provider",
            "source",
            "started_at_ms",
            "process_id",
            "payload_json",
        },
        "collector_heartbeats": {
            "heartbeat_identity",
            "instance_identity",
            "sequence_no",
            "observed_at_ms",
            "last_successful_ingestion_ms",
            "payload_json",
        },
    }
    for table, required in expected.items():
        observed = {
            str(row[1])
            for row in connection.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()
        }
        missing = required - observed
        if missing:
            raise ValueError(
                f"collector runtime columns missing from {table}: "
                + ",".join(sorted(missing))
            )


def _verify_payload_identity(
    identity: str,
    payload_json: str,
    label: str,
) -> None:
    _require_sha256(identity, f"{label} identity")
    canonical = json.dumps(
        json.loads(payload_json),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    observed = hashlib.sha256(canonical.encode()).hexdigest()
    if observed != identity:
        raise ValueError(f"{label} payload identity mismatch")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")


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
