from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256

LIQUIDATION_CONNECTION_RUNTIME_SCHEMA_VERSION = (
    "liquidation-connection-runtime-v1/1"
)
REAL_CAPITAL = 0


class LiquidationConnectionState(StrEnum):
    CONNECTED = "connected"
    STALE = "stale"
    DISCONNECTED = "disconnected"


class LiquidationRuntimeConflictError(ValueError):
    """Raised when immutable connection-runtime identity conflicts."""


@dataclass(frozen=True, slots=True)
class LiquidationConnectionCoverage:
    coverage_identity: str
    instance_identity: str
    sequence_no: int
    state: LiquidationConnectionState
    observed_at_ms: int
    connected_since_ms: int | None
    last_transport_activity_ms: int | None
    last_liquidation_ingestion_ms: int | None
    symbols: tuple[str, ...]
    reason_codes: tuple[str, ...]
    schema_version: str = LIQUIDATION_CONNECTION_RUNTIME_SCHEMA_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.schema_version != LIQUIDATION_CONNECTION_RUNTIME_SCHEMA_VERSION:
            raise ValueError("unsupported liquidation connection runtime schema")
        _require_sha256(self.coverage_identity, "liquidation connection coverage")
        _require_sha256(self.instance_identity, "liquidation collector instance")
        if self.sequence_no <= 0:
            raise ValueError("liquidation connection sequence must be positive")
        if self.observed_at_ms < 0:
            raise ValueError(
                "liquidation connection observation cannot be negative"
            )
        if not self.symbols or tuple(sorted(set(self.symbols))) != self.symbols:
            raise ValueError(
                "liquidation connection symbols must be unique and sorted"
            )
        if any(
            not symbol or symbol != symbol.upper() for symbol in self.symbols
        ):
            raise ValueError(
                "liquidation connection symbols must be uppercase"
            )
        if not self.reason_codes:
            raise ValueError(
                "liquidation connection coverage requires reason codes"
            )
        for label, value in (
            ("connected_since_ms", self.connected_since_ms),
            ("last_transport_activity_ms", self.last_transport_activity_ms),
            (
                "last_liquidation_ingestion_ms",
                self.last_liquidation_ingestion_ms,
            ),
        ):
            if value is not None:
                if value < 0:
                    raise ValueError(f"{label} cannot be negative")
                if value > self.observed_at_ms:
                    raise ValueError(
                        f"{label} cannot exceed connection observation"
                    )
        if self.state in {
            LiquidationConnectionState.CONNECTED,
            LiquidationConnectionState.STALE,
        }:
            if (
                self.connected_since_ms is None
                or self.last_transport_activity_ms is None
            ):
                raise ValueError(
                    "connected/stale liquidation state requires transport proof"
                )
            if self.connected_since_ms > self.last_transport_activity_ms:
                raise ValueError(
                    "liquidation connection start exceeds transport activity"
                )
        elif self.connected_since_ms is not None:
            raise ValueError(
                "disconnected liquidation state cannot claim active session"
            )
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError(
                "liquidation connection runtime cannot grant authority"
            )
        if self.coverage_identity != canonical_sha256(
            _coverage_payload(self)
        ):
            raise ValueError("liquidation connection coverage identity mismatch")


def build_liquidation_connection_coverage(
    *,
    instance_identity: str,
    sequence_no: int,
    state: LiquidationConnectionState,
    observed_at_ms: int,
    connected_since_ms: int | None,
    last_transport_activity_ms: int | None,
    last_liquidation_ingestion_ms: int | None,
    symbols: tuple[str, ...],
    reason_codes: tuple[str, ...],
) -> LiquidationConnectionCoverage:
    canonical_symbols = tuple(sorted(set(symbols)))
    canonical_reasons = tuple(sorted(set(reason_codes)))
    values = _coverage_payload_values(
        instance_identity=instance_identity,
        sequence_no=sequence_no,
        state=state,
        observed_at_ms=observed_at_ms,
        connected_since_ms=connected_since_ms,
        last_transport_activity_ms=last_transport_activity_ms,
        last_liquidation_ingestion_ms=last_liquidation_ingestion_ms,
        symbols=canonical_symbols,
        reason_codes=canonical_reasons,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )
    return LiquidationConnectionCoverage(
        coverage_identity=canonical_sha256(values),
        instance_identity=instance_identity,
        sequence_no=sequence_no,
        state=state,
        observed_at_ms=observed_at_ms,
        connected_since_ms=connected_since_ms,
        last_transport_activity_ms=last_transport_activity_ms,
        last_liquidation_ingestion_ms=last_liquidation_ingestion_ms,
        symbols=canonical_symbols,
        reason_codes=canonical_reasons,
    )


class LiquidationConnectionRuntimeStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10.0)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=10000")
        return db

    def initialize(self) -> None:
        if self._initialized:
            return
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        with self._connect() as db:
            parent = db.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='collector_instances'
                """
            ).fetchone()
            if parent is None:
                raise ValueError(
                    "liquidation connection runtime requires collector instances"
                )
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS liquidation_connection_coverage (
                    coverage_identity TEXT PRIMARY KEY,
                    instance_identity TEXT NOT NULL,
                    sequence_no INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE(instance_identity, sequence_no),
                    FOREIGN KEY(instance_identity)
                        REFERENCES collector_instances(instance_identity)
                );
                CREATE INDEX IF NOT EXISTS
                    liquidation_connection_coverage_instance_time
                ON liquidation_connection_coverage(
                    instance_identity,
                    observed_at_ms
                );
                CREATE TRIGGER IF NOT EXISTS
                    liquidation_connection_coverage_no_update
                BEFORE UPDATE ON liquidation_connection_coverage
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'liquidation connection coverage is immutable'
                    );
                END;
                CREATE TRIGGER IF NOT EXISTS
                    liquidation_connection_coverage_no_delete
                BEFORE DELETE ON liquidation_connection_coverage
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'liquidation connection coverage is immutable'
                    );
                END;
                """
            )
        self._initialized = True

    def append(self, coverage: LiquidationConnectionCoverage) -> None:
        self.initialize()
        payload = canonical_json(_coverage_payload(coverage))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            parent = db.execute(
                """
                SELECT 1 FROM collector_instances
                WHERE instance_identity=?
                """,
                (coverage.instance_identity,),
            ).fetchone()
            if parent is None:
                raise ValueError(
                    "liquidation connection coverage references unknown instance"
                )
            previous = db.execute(
                """
                SELECT sequence_no, observed_at_ms, payload_json
                FROM liquidation_connection_coverage
                WHERE instance_identity=?
                ORDER BY sequence_no DESC
                LIMIT 1
                """,
                (coverage.instance_identity,),
            ).fetchone()
            if previous is not None:
                previous_sequence = int(previous["sequence_no"])
                if coverage.sequence_no < previous_sequence:
                    raise ValueError(
                        "liquidation connection sequence regressed"
                    )
                if coverage.sequence_no == previous_sequence:
                    if str(previous["payload_json"]) != payload:
                        raise LiquidationRuntimeConflictError(
                            "liquidation connection sequence conflict"
                        )
                    return
                if coverage.observed_at_ms < int(previous["observed_at_ms"]):
                    raise ValueError(
                        "liquidation connection observation time regressed"
                    )
                previous_payload = _coverage_from_payload(
                    str(previous["payload_json"])
                )
                if (
                    previous_payload.last_liquidation_ingestion_ms is not None
                    and coverage.last_liquidation_ingestion_ms is None
                ):
                    raise ValueError(
                        "liquidation ingestion evidence cannot disappear"
                    )
                if (
                    previous_payload.last_liquidation_ingestion_ms is not None
                    and coverage.last_liquidation_ingestion_ms is not None
                    and coverage.last_liquidation_ingestion_ms
                    < previous_payload.last_liquidation_ingestion_ms
                ):
                    raise ValueError(
                        "liquidation ingestion time regressed"
                    )
            db.execute(
                """
                INSERT INTO liquidation_connection_coverage(
                    coverage_identity,
                    instance_identity,
                    sequence_no,
                    state,
                    observed_at_ms,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    coverage.coverage_identity,
                    coverage.instance_identity,
                    coverage.sequence_no,
                    coverage.state.value,
                    coverage.observed_at_ms,
                    payload,
                ),
            )

    def latest(
        self,
        instance_identity: str,
    ) -> LiquidationConnectionCoverage | None:
        if not self.path.is_file():
            return None
        with self._connect() as db:
            row = db.execute(
                """
                SELECT payload_json
                FROM liquidation_connection_coverage
                WHERE instance_identity=?
                ORDER BY sequence_no DESC
                LIMIT 1
                """,
                (instance_identity,),
            ).fetchone()
        return (
            None
            if row is None
            else _coverage_from_payload(str(row["payload_json"]))
        )

    def quick_check(self) -> bool:
        if not self.path.is_file():
            return False
        with self._connect() as db:
            row = db.execute("PRAGMA quick_check").fetchone()
        return row is not None and str(row[0]).lower() == "ok"


def _coverage_payload(
    coverage: LiquidationConnectionCoverage,
) -> dict[str, object]:
    return _coverage_payload_values(
        instance_identity=coverage.instance_identity,
        sequence_no=coverage.sequence_no,
        state=coverage.state,
        observed_at_ms=coverage.observed_at_ms,
        connected_since_ms=coverage.connected_since_ms,
        last_transport_activity_ms=coverage.last_transport_activity_ms,
        last_liquidation_ingestion_ms=(
            coverage.last_liquidation_ingestion_ms
        ),
        symbols=coverage.symbols,
        reason_codes=coverage.reason_codes,
        production_authority=coverage.production_authority,
        real_capital=coverage.real_capital,
    )


def _coverage_payload_values(
    *,
    instance_identity: str,
    sequence_no: int,
    state: LiquidationConnectionState,
    observed_at_ms: int,
    connected_since_ms: int | None,
    last_transport_activity_ms: int | None,
    last_liquidation_ingestion_ms: int | None,
    symbols: tuple[str, ...],
    reason_codes: tuple[str, ...],
    production_authority: bool,
    real_capital: int,
) -> dict[str, object]:
    return {
        "schema_version": LIQUIDATION_CONNECTION_RUNTIME_SCHEMA_VERSION,
        "instance_identity": instance_identity,
        "sequence_no": sequence_no,
        "state": state.value,
        "observed_at_ms": observed_at_ms,
        "connected_since_ms": connected_since_ms,
        "last_transport_activity_ms": last_transport_activity_ms,
        "last_liquidation_ingestion_ms": last_liquidation_ingestion_ms,
        "symbols": symbols,
        "reason_codes": reason_codes,
        "production_authority": production_authority,
        "real_capital": real_capital,
    }


def _coverage_from_payload(payload_json: str) -> LiquidationConnectionCoverage:
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise TypeError(
            "liquidation connection coverage payload must be object"
        )
    return LiquidationConnectionCoverage(
        coverage_identity=canonical_sha256(payload),
        instance_identity=str(payload["instance_identity"]),
        sequence_no=int(payload["sequence_no"]),
        state=LiquidationConnectionState(str(payload["state"])),
        observed_at_ms=int(payload["observed_at_ms"]),
        connected_since_ms=(
            None
            if payload["connected_since_ms"] is None
            else int(payload["connected_since_ms"])
        ),
        last_transport_activity_ms=(
            None
            if payload["last_transport_activity_ms"] is None
            else int(payload["last_transport_activity_ms"])
        ),
        last_liquidation_ingestion_ms=(
            None
            if payload["last_liquidation_ingestion_ms"] is None
            else int(payload["last_liquidation_ingestion_ms"])
        ),
        symbols=tuple(str(value) for value in payload["symbols"]),
        reason_codes=tuple(
            str(value) for value in payload["reason_codes"]
        ),
        production_authority=bool(payload["production_authority"]),
        real_capital=int(payload["real_capital"]),
    )


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise ValueError(f"{label} must be SHA256")
