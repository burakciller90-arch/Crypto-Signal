from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256

MARKET_TAPE_COLLECTOR_RUNTIME_SCHEMA_VERSION = (
    "market-tape-collector-runtime-v1/2"
)
REAL_CAPITAL = 0


class CollectorStartKind(StrEnum):
    START = "start"
    RESTART = "restart"


class CollectorRuntimeConflictError(ValueError):
    """Raised when immutable runtime identity maps to conflicting content."""


@dataclass(frozen=True, slots=True)
class MarketTapeCollectorInstance:
    instance_identity: str
    provider: str
    source: str
    symbols: tuple[str, ...]
    started_at_ms: int
    process_id: int
    runtime_nonce: str
    start_kind: CollectorStartKind
    previous_instance_identity: str | None
    schema_version: str = MARKET_TAPE_COLLECTOR_RUNTIME_SCHEMA_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.schema_version != MARKET_TAPE_COLLECTOR_RUNTIME_SCHEMA_VERSION:
            raise ValueError("unsupported collector runtime schema")
        if not self.provider.strip() or not self.source.strip():
            raise ValueError("collector provider/source must be non-empty")
        if not self.symbols or tuple(sorted(set(self.symbols))) != self.symbols:
            raise ValueError("collector symbols must be unique and sorted")
        if any(not symbol or symbol != symbol.upper() for symbol in self.symbols):
            raise ValueError("collector symbols must be uppercase")
        if self.started_at_ms < 0 or self.process_id <= 0:
            raise ValueError("collector start/process values are invalid")
        if not self.runtime_nonce.strip():
            raise ValueError("collector runtime nonce must be non-empty")
        if self.start_kind is CollectorStartKind.START:
            if self.previous_instance_identity is not None:
                raise ValueError("initial collector start cannot have predecessor")
        else:
            if self.previous_instance_identity is None:
                raise ValueError("collector restart requires predecessor")
            _require_sha256(
                self.previous_instance_identity,
                "collector previous instance identity",
            )
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("collector runtime evidence cannot grant authority")
        _require_sha256(self.instance_identity, "collector instance identity")
        if self.instance_identity != canonical_sha256(_instance_payload(self)):
            raise ValueError("collector instance identity mismatch")


@dataclass(frozen=True, slots=True)
class MarketTapeCollectorHeartbeat:
    heartbeat_identity: str
    instance_identity: str
    sequence_no: int
    observed_at_ms: int
    last_successful_ingestion_ms: int | None
    observed_messages_total: int
    normalized_rows_total: int
    raw_rows_total: int
    schema_version: str = MARKET_TAPE_COLLECTOR_RUNTIME_SCHEMA_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.schema_version != MARKET_TAPE_COLLECTOR_RUNTIME_SCHEMA_VERSION:
            raise ValueError("unsupported collector runtime schema")
        _require_sha256(self.heartbeat_identity, "collector heartbeat identity")
        _require_sha256(self.instance_identity, "collector instance identity")
        if self.sequence_no <= 0:
            raise ValueError("collector heartbeat sequence must be positive")
        if self.observed_at_ms < 0:
            raise ValueError("collector heartbeat timestamp must be non-negative")
        if self.last_successful_ingestion_ms is not None:
            if self.last_successful_ingestion_ms < 0:
                raise ValueError("collector ingestion timestamp must be non-negative")
            if self.last_successful_ingestion_ms > self.observed_at_ms:
                raise ValueError("collector ingestion cannot be in the future")
        if min(
            self.observed_messages_total,
            self.normalized_rows_total,
            self.raw_rows_total,
        ) < 0:
            raise ValueError("collector heartbeat counters cannot be negative")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("collector heartbeat cannot grant authority")
        if self.heartbeat_identity != canonical_sha256(_heartbeat_payload(self)):
            raise ValueError("collector heartbeat identity mismatch")


def build_collector_instance(
    *,
    provider: str,
    source: str,
    symbols: tuple[str, ...],
    started_at_ms: int,
    process_id: int,
    runtime_nonce: str,
    previous_instance_identity: str | None = None,
) -> MarketTapeCollectorInstance:
    canonical_symbols = tuple(sorted(set(symbols)))
    start_kind = (
        CollectorStartKind.START
        if previous_instance_identity is None
        else CollectorStartKind.RESTART
    )
    payload = _instance_payload_values(
        provider=provider,
        source=source,
        symbols=canonical_symbols,
        started_at_ms=started_at_ms,
        process_id=process_id,
        runtime_nonce=runtime_nonce,
        start_kind=start_kind,
        previous_instance_identity=previous_instance_identity,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )
    return MarketTapeCollectorInstance(
        instance_identity=canonical_sha256(payload),
        provider=provider,
        source=source,
        symbols=canonical_symbols,
        started_at_ms=started_at_ms,
        process_id=process_id,
        runtime_nonce=runtime_nonce,
        start_kind=start_kind,
        previous_instance_identity=previous_instance_identity,
    )


def build_collector_heartbeat(
    *,
    instance_identity: str,
    sequence_no: int,
    observed_at_ms: int,
    last_successful_ingestion_ms: int | None,
    observed_messages_total: int,
    normalized_rows_total: int,
    raw_rows_total: int,
) -> MarketTapeCollectorHeartbeat:
    payload = _heartbeat_payload_values(
        instance_identity=instance_identity,
        sequence_no=sequence_no,
        observed_at_ms=observed_at_ms,
        last_successful_ingestion_ms=last_successful_ingestion_ms,
        observed_messages_total=observed_messages_total,
        normalized_rows_total=normalized_rows_total,
        raw_rows_total=raw_rows_total,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )
    return MarketTapeCollectorHeartbeat(
        heartbeat_identity=canonical_sha256(payload),
        instance_identity=instance_identity,
        sequence_no=sequence_no,
        observed_at_ms=observed_at_ms,
        last_successful_ingestion_ms=last_successful_ingestion_ms,
        observed_messages_total=observed_messages_total,
        normalized_rows_total=normalized_rows_total,
        raw_rows_total=raw_rows_total,
    )


class MarketTapeCollectorRuntimeStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10.0)
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def initialize(self) -> None:
        if self._initialized:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS collector_runtime_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS collector_instances (
                    instance_identity TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    source TEXT NOT NULL,
                    started_at_ms INTEGER NOT NULL,
                    process_id INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS collector_instances_source_time
                    ON collector_instances(provider, source, started_at_ms);
                CREATE TABLE IF NOT EXISTS collector_heartbeats (
                    heartbeat_identity TEXT PRIMARY KEY,
                    instance_identity TEXT NOT NULL,
                    sequence_no INTEGER NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    last_successful_ingestion_ms INTEGER,
                    payload_json TEXT NOT NULL,
                    UNIQUE(instance_identity, sequence_no),
                    FOREIGN KEY(instance_identity)
                        REFERENCES collector_instances(instance_identity)
                );
                CREATE INDEX IF NOT EXISTS collector_heartbeats_instance_time
                    ON collector_heartbeats(instance_identity, observed_at_ms);
                """
            )
            row = db.execute(
                "SELECT value FROM collector_runtime_meta WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO collector_runtime_meta(key, value) VALUES (?, ?)",
                    (
                        "schema_version",
                        MARKET_TAPE_COLLECTOR_RUNTIME_SCHEMA_VERSION,
                    ),
                )
            elif str(row[0]) != MARKET_TAPE_COLLECTOR_RUNTIME_SCHEMA_VERSION:
                raise ValueError("collector runtime schema mismatch")
        self._initialized = True

    def append_instance(self, instance: MarketTapeCollectorInstance) -> None:
        self.initialize()
        payload = canonical_json(_instance_payload(instance))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT payload_json FROM collector_instances "
                "WHERE instance_identity=?",
                (instance.instance_identity,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != payload:
                    raise CollectorRuntimeConflictError(
                        "collector instance identity conflict"
                    )
                return
            db.execute(
                """
                INSERT INTO collector_instances(
                    instance_identity, provider, source, started_at_ms,
                    process_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    instance.instance_identity,
                    instance.provider,
                    instance.source,
                    instance.started_at_ms,
                    instance.process_id,
                    payload,
                ),
            )

    def append_heartbeat(self, heartbeat: MarketTapeCollectorHeartbeat) -> None:
        self.initialize()
        payload = canonical_json(_heartbeat_payload(heartbeat))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            parent = db.execute(
                "SELECT 1 FROM collector_instances WHERE instance_identity=?",
                (heartbeat.instance_identity,),
            ).fetchone()
            if parent is None:
                raise ValueError("collector heartbeat references unknown instance")
            previous = db.execute(
                """
                SELECT sequence_no, observed_at_ms, last_successful_ingestion_ms,
                       payload_json
                FROM collector_heartbeats
                WHERE instance_identity=?
                ORDER BY sequence_no DESC
                LIMIT 1
                """,
                (heartbeat.instance_identity,),
            ).fetchone()
            if previous is not None:
                previous_sequence = int(previous[0])
                if heartbeat.sequence_no < previous_sequence:
                    raise ValueError("collector heartbeat sequence regressed")
                if heartbeat.sequence_no == previous_sequence:
                    if str(previous[3]) != payload:
                        raise CollectorRuntimeConflictError(
                            "collector heartbeat sequence conflict"
                        )
                    return
                if heartbeat.observed_at_ms < int(previous[1]):
                    raise ValueError("collector heartbeat observation time regressed")
                previous_ingestion = (
                    None if previous[2] is None else int(previous[2])
                )
                if (
                    previous_ingestion is not None
                    and heartbeat.last_successful_ingestion_ms is None
                ):
                    raise ValueError("collector ingestion evidence cannot disappear")
                if (
                    previous_ingestion is not None
                    and heartbeat.last_successful_ingestion_ms is not None
                    and heartbeat.last_successful_ingestion_ms
                    < previous_ingestion
                ):
                    raise ValueError("collector ingestion time regressed")
            db.execute(
                """
                INSERT INTO collector_heartbeats(
                    heartbeat_identity, instance_identity, sequence_no,
                    observed_at_ms, last_successful_ingestion_ms, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    heartbeat.heartbeat_identity,
                    heartbeat.instance_identity,
                    heartbeat.sequence_no,
                    heartbeat.observed_at_ms,
                    heartbeat.last_successful_ingestion_ms,
                    payload,
                ),
            )

    def latest_instance(
        self,
        *,
        provider: str,
        source: str,
    ) -> MarketTapeCollectorInstance | None:
        if not self.path.is_file():
            return None
        with self._connect() as db:
            row = db.execute(
                """
                SELECT payload_json
                FROM collector_instances
                WHERE provider=? AND source=?
                ORDER BY started_at_ms DESC, instance_identity DESC
                LIMIT 1
                """,
                (provider, source),
            ).fetchone()
        return None if row is None else _instance_from_payload(str(row[0]))

    def latest_heartbeat(
        self,
        instance_identity: str,
    ) -> MarketTapeCollectorHeartbeat | None:
        if not self.path.is_file():
            return None
        with self._connect() as db:
            row = db.execute(
                """
                SELECT payload_json
                FROM collector_heartbeats
                WHERE instance_identity=?
                ORDER BY sequence_no DESC
                LIMIT 1
                """,
                (instance_identity,),
            ).fetchone()
        return None if row is None else _heartbeat_from_payload(str(row[0]))

    def quick_check(self) -> bool:
        if not self.path.is_file():
            return False
        with self._connect() as db:
            row = db.execute("PRAGMA quick_check").fetchone()
        return row is not None and str(row[0]).lower() == "ok"


def _instance_payload(instance: MarketTapeCollectorInstance) -> dict[str, object]:
    return _instance_payload_values(
        provider=instance.provider,
        source=instance.source,
        symbols=instance.symbols,
        started_at_ms=instance.started_at_ms,
        process_id=instance.process_id,
        runtime_nonce=instance.runtime_nonce,
        start_kind=instance.start_kind,
        previous_instance_identity=instance.previous_instance_identity,
        production_authority=instance.production_authority,
        real_capital=instance.real_capital,
    )


def _instance_payload_values(
    *,
    provider: str,
    source: str,
    symbols: tuple[str, ...],
    started_at_ms: int,
    process_id: int,
    runtime_nonce: str,
    start_kind: CollectorStartKind,
    previous_instance_identity: str | None,
    production_authority: bool,
    real_capital: int,
) -> dict[str, object]:
    return {
        "schema_version": MARKET_TAPE_COLLECTOR_RUNTIME_SCHEMA_VERSION,
        "provider": provider,
        "source": source,
        "symbols": symbols,
        "started_at_ms": started_at_ms,
        "process_id": process_id,
        "runtime_nonce": runtime_nonce,
        "start_kind": start_kind.value,
        "previous_instance_identity": previous_instance_identity,
        "production_authority": production_authority,
        "real_capital": real_capital,
    }


def _heartbeat_payload(
    heartbeat: MarketTapeCollectorHeartbeat,
) -> dict[str, object]:
    return _heartbeat_payload_values(
        instance_identity=heartbeat.instance_identity,
        sequence_no=heartbeat.sequence_no,
        observed_at_ms=heartbeat.observed_at_ms,
        last_successful_ingestion_ms=heartbeat.last_successful_ingestion_ms,
        observed_messages_total=heartbeat.observed_messages_total,
        normalized_rows_total=heartbeat.normalized_rows_total,
        raw_rows_total=heartbeat.raw_rows_total,
        production_authority=heartbeat.production_authority,
        real_capital=heartbeat.real_capital,
    )


def _heartbeat_payload_values(
    *,
    instance_identity: str,
    sequence_no: int,
    observed_at_ms: int,
    last_successful_ingestion_ms: int | None,
    observed_messages_total: int,
    normalized_rows_total: int,
    raw_rows_total: int,
    production_authority: bool,
    real_capital: int,
) -> dict[str, object]:
    return {
        "schema_version": MARKET_TAPE_COLLECTOR_RUNTIME_SCHEMA_VERSION,
        "instance_identity": instance_identity,
        "sequence_no": sequence_no,
        "observed_at_ms": observed_at_ms,
        "last_successful_ingestion_ms": last_successful_ingestion_ms,
        "observed_messages_total": observed_messages_total,
        "normalized_rows_total": normalized_rows_total,
        "raw_rows_total": raw_rows_total,
        "production_authority": production_authority,
        "real_capital": real_capital,
    }


def _instance_from_payload(payload_json: str) -> MarketTapeCollectorInstance:
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise TypeError("collector instance payload must be object")
    symbols = tuple(str(value) for value in payload["symbols"])
    start_kind = CollectorStartKind(str(payload["start_kind"]))
    previous = (
        None
        if payload["previous_instance_identity"] is None
        else str(payload["previous_instance_identity"])
    )
    values = _instance_payload_values(
        provider=str(payload["provider"]),
        source=str(payload["source"]),
        symbols=symbols,
        started_at_ms=int(payload["started_at_ms"]),
        process_id=int(payload["process_id"]),
        runtime_nonce=str(payload["runtime_nonce"]),
        start_kind=start_kind,
        previous_instance_identity=previous,
        production_authority=bool(payload["production_authority"]),
        real_capital=int(payload["real_capital"]),
    )
    return MarketTapeCollectorInstance(
        instance_identity=canonical_sha256(values),
        provider=str(payload["provider"]),
        source=str(payload["source"]),
        symbols=symbols,
        started_at_ms=int(payload["started_at_ms"]),
        process_id=int(payload["process_id"]),
        runtime_nonce=str(payload["runtime_nonce"]),
        start_kind=start_kind,
        previous_instance_identity=previous,
        schema_version=str(payload["schema_version"]),
        production_authority=bool(payload["production_authority"]),
        real_capital=int(payload["real_capital"]),
    )


def _heartbeat_from_payload(payload_json: str) -> MarketTapeCollectorHeartbeat:
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise TypeError("collector heartbeat payload must be object")
    values = _heartbeat_payload_values(
        instance_identity=str(payload["instance_identity"]),
        sequence_no=int(payload["sequence_no"]),
        observed_at_ms=int(payload["observed_at_ms"]),
        last_successful_ingestion_ms=(
            None
            if payload["last_successful_ingestion_ms"] is None
            else int(payload["last_successful_ingestion_ms"])
        ),
        observed_messages_total=int(payload["observed_messages_total"]),
        normalized_rows_total=int(payload["normalized_rows_total"]),
        raw_rows_total=int(payload["raw_rows_total"]),
        production_authority=bool(payload["production_authority"]),
        real_capital=int(payload["real_capital"]),
    )
    return MarketTapeCollectorHeartbeat(
        heartbeat_identity=canonical_sha256(values),
        instance_identity=str(payload["instance_identity"]),
        sequence_no=int(payload["sequence_no"]),
        observed_at_ms=int(payload["observed_at_ms"]),
        last_successful_ingestion_ms=(
            None
            if payload["last_successful_ingestion_ms"] is None
            else int(payload["last_successful_ingestion_ms"])
        ),
        observed_messages_total=int(payload["observed_messages_total"]),
        normalized_rows_total=int(payload["normalized_rows_total"]),
        raw_rows_total=int(payload["raw_rows_total"]),
        schema_version=str(payload["schema_version"]),
        production_authority=bool(payload["production_authority"]),
        real_capital=int(payload["real_capital"]),
    )


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
