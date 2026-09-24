from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from crypto_signal.forecast_stream import ForecastResolution, ImmutableForecast
from crypto_signal.ledger.serialization import canonical_json, sha256_text
from crypto_signal.product.decision_proof import (
    DecisionProofSnapshot,
    LiveFeedEventKind,
    LiveIntelligenceFeedEvent,
)

DECISION_LEDGER_SCHEMA_VERSION = "r25-decision-evidence-ledger-v1/1"
REAL_CAPITAL = 0


class DecisionLedgerConflictError(ValueError):
    """Raised when immutable decision evidence would be rebound or forked."""


class DecisionLedgerWriteDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class DecisionEvidenceLedgerStatus:
    forecast_count: int
    proof_count: int
    resolution_count: int
    feed_event_count: int
    latest_event_at_ms: int | None
    schema_version: str = DECISION_LEDGER_SCHEMA_VERSION
    read_only: bool = True
    real_capital: int = REAL_CAPITAL


class ImmutableDecisionEvidenceLedger:
    """Append-only persistence for accepted R20/R20.5 decision evidence.

    This ledger grants no production, exchange, credential or real-capital authority.
    Product reads are query-only and never initialize a missing database.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect_rw() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS r20_forecasts (
                    forecast_identity TEXT PRIMARY KEY,
                    signal_freeze_identity TEXT NOT NULL,
                    asset TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    issued_at_ms INTEGER NOT NULL,
                    source_as_of_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS r20_resolutions (
                    resolution_identity TEXT PRIMARY KEY,
                    forecast_identity TEXT NOT NULL UNIQUE,
                    signal_freeze_identity TEXT NOT NULL,
                    evaluated_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    FOREIGN KEY (forecast_identity)
                        REFERENCES r20_forecasts(forecast_identity)
                );

                CREATE TABLE IF NOT EXISTS r20_5_decision_proofs (
                    proof_identity TEXT PRIMARY KEY,
                    forecast_identity TEXT NOT NULL UNIQUE,
                    signal_freeze_identity TEXT NOT NULL,
                    asset TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    issued_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    FOREIGN KEY (forecast_identity)
                        REFERENCES r20_forecasts(forecast_identity)
                );

                CREATE TABLE IF NOT EXISTS r20_5_live_feed_events (
                    event_identity TEXT PRIMARY KEY,
                    forecast_identity TEXT NOT NULL,
                    proof_identity TEXT NOT NULL,
                    resolution_identity TEXT,
                    kind TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    UNIQUE (forecast_identity, kind),
                    FOREIGN KEY (forecast_identity)
                        REFERENCES r20_forecasts(forecast_identity),
                    FOREIGN KEY (proof_identity)
                        REFERENCES r20_5_decision_proofs(proof_identity),
                    FOREIGN KEY (resolution_identity)
                        REFERENCES r20_resolutions(resolution_identity)
                );
                """
            )
            for table in (
                "r20_forecasts",
                "r20_resolutions",
                "r20_5_decision_proofs",
                "r20_5_live_feed_events",
            ):
                for action in ("UPDATE", "DELETE"):
                    connection.execute(
                        f"""
                        CREATE TRIGGER IF NOT EXISTS {table}_immutable_{action.lower()}
                        BEFORE {action} ON {table}
                        BEGIN
                            SELECT RAISE(
                                ABORT,
                                'immutable decision evidence cannot be mutated'
                            );
                        END
                        """
                    )

    def append_forecast(
        self,
        forecast: ImmutableForecast,
    ) -> DecisionLedgerWriteDisposition:
        if forecast.production_authority or forecast.real_capital != REAL_CAPITAL:
            raise DecisionLedgerConflictError(
                "R20 forecast violates decision-ledger authority boundary"
            )
        payload, digest = _serialized(forecast)
        self.initialize()
        with self._connect_rw() as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM r20_forecasts
                WHERE forecast_identity = ?
                """,
                (forecast.forecast_identity,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) == payload and str(existing[1]) == digest:
                    return DecisionLedgerWriteDisposition.UNCHANGED
                raise DecisionLedgerConflictError(
                    "immutable R20 forecast identity conflict"
                )
            last = connection.execute(
                """
                SELECT forecast_identity, issued_at_ms
                FROM r20_forecasts
                ORDER BY issued_at_ms DESC, forecast_identity DESC
                LIMIT 1
                """
            ).fetchone()
            if last is not None and (
                forecast.issued_at_ms,
                forecast.forecast_identity,
            ) <= (int(last[1]), str(last[0])):
                raise DecisionLedgerConflictError(
                    "R20 forecast append would backfill or fork chronology"
                )
            connection.execute(
                """
                INSERT INTO r20_forecasts (
                    forecast_identity,
                    signal_freeze_identity,
                    asset,
                    symbol,
                    timeframe,
                    issued_at_ms,
                    source_as_of_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    forecast.forecast_identity,
                    forecast.signal_freeze_identity,
                    forecast.asset,
                    forecast.symbol,
                    forecast.timeframe,
                    forecast.issued_at_ms,
                    forecast.source_as_of_ms,
                    payload,
                    digest,
                ),
            )
        return DecisionLedgerWriteDisposition.INSERTED

    def append_proof(
        self,
        proof: DecisionProofSnapshot,
    ) -> DecisionLedgerWriteDisposition:
        if (
            proof.production_authority
            or not proof.read_only
            or proof.real_capital != REAL_CAPITAL
        ):
            raise DecisionLedgerConflictError(
                "Decision Proof violates decision-ledger authority boundary"
            )
        payload, digest = _serialized(proof)
        self.initialize()
        with self._connect_rw() as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            forecast = connection.execute(
                """
                SELECT signal_freeze_identity, asset, symbol, timeframe, issued_at_ms
                FROM r20_forecasts
                WHERE forecast_identity = ?
                """,
                (proof.forecast_identity,),
            ).fetchone()
            if forecast is None:
                raise DecisionLedgerConflictError(
                    "Decision Proof references unknown R20 forecast"
                )
            expected = (
                str(forecast[0]),
                str(forecast[1]),
                str(forecast[2]),
                str(forecast[3]),
                int(forecast[4]),
            )
            actual = (
                proof.signal_freeze_identity,
                proof.asset,
                proof.symbol,
                proof.timeframe,
                proof.issued_at_ms,
            )
            if actual != expected:
                raise DecisionLedgerConflictError(
                    "Decision Proof lineage does not match persisted R20 forecast"
                )
            existing = connection.execute(
                """
                SELECT proof_identity, payload_json, payload_sha256
                FROM r20_5_decision_proofs
                WHERE forecast_identity = ? OR proof_identity = ?
                LIMIT 1
                """,
                (proof.forecast_identity, proof.proof_identity),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == proof.proof_identity
                    and str(existing[1]) == payload
                    and str(existing[2]) == digest
                ):
                    return DecisionLedgerWriteDisposition.UNCHANGED
                raise DecisionLedgerConflictError(
                    "immutable Decision Proof forecast binding conflict"
                )
            connection.execute(
                """
                INSERT INTO r20_5_decision_proofs (
                    proof_identity,
                    forecast_identity,
                    signal_freeze_identity,
                    asset,
                    symbol,
                    timeframe,
                    issued_at_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proof.proof_identity,
                    proof.forecast_identity,
                    proof.signal_freeze_identity,
                    proof.asset,
                    proof.symbol,
                    proof.timeframe,
                    proof.issued_at_ms,
                    payload,
                    digest,
                ),
            )
        return DecisionLedgerWriteDisposition.INSERTED

    def append_issuance_bundle(
        self,
        forecast: ImmutableForecast,
        proof: DecisionProofSnapshot,
        event: LiveIntelligenceFeedEvent,
    ) -> DecisionLedgerWriteDisposition:
        """Atomically persist one R20 -> R20.5 issuance lineage."""
        if forecast.production_authority or forecast.real_capital != REAL_CAPITAL:
            raise DecisionLedgerConflictError(
                "R20 forecast violates decision-ledger authority boundary"
            )
        if (
            proof.production_authority
            or not proof.read_only
            or proof.real_capital != REAL_CAPITAL
        ):
            raise DecisionLedgerConflictError(
                "Decision Proof violates decision-ledger authority boundary"
            )
        if (
            event.production_authority
            or not event.read_only
            or event.real_capital != REAL_CAPITAL
        ):
            raise DecisionLedgerConflictError(
                "Live Intelligence Feed event violates authority boundary"
            )
        if event.kind is not LiveFeedEventKind.FORECAST_ISSUED:
            raise DecisionLedgerConflictError(
                "issuance bundle requires FORECAST_ISSUED event"
            )
        if event.resolution_identity is not None:
            raise DecisionLedgerConflictError(
                "issuance bundle cannot carry resolution identity"
            )
        if (
            proof.forecast_identity != forecast.forecast_identity
            or event.forecast_identity != forecast.forecast_identity
            or event.proof_identity != proof.proof_identity
        ):
            raise DecisionLedgerConflictError(
                "issuance bundle forecast/proof/event lineage mismatch"
            )
        if (
            proof.signal_freeze_identity != forecast.signal_freeze_identity
            or proof.asset != forecast.asset
            or proof.symbol != forecast.symbol
            or proof.timeframe != forecast.timeframe
            or proof.issued_at_ms != forecast.issued_at_ms
            or event.event_at_ms != forecast.issued_at_ms
        ):
            raise DecisionLedgerConflictError(
                "issuance bundle market/timestamp lineage mismatch"
            )

        forecast_payload, forecast_digest = _serialized(forecast)
        proof_payload, proof_digest = _serialized(proof)
        event_payload, event_digest = _serialized(event)

        self.initialize()
        with self._connect_rw() as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")

            existing_forecast = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM r20_forecasts
                WHERE forecast_identity = ?
                """,
                (forecast.forecast_identity,),
            ).fetchone()
            existing_proof = connection.execute(
                """
                SELECT proof_identity, payload_json, payload_sha256
                FROM r20_5_decision_proofs
                WHERE forecast_identity = ? OR proof_identity = ?
                LIMIT 1
                """,
                (forecast.forecast_identity, proof.proof_identity),
            ).fetchone()
            existing_event = connection.execute(
                """
                SELECT event_identity, payload_json, payload_sha256
                FROM r20_5_live_feed_events
                WHERE event_identity = ?
                   OR (forecast_identity = ? AND kind = ?)
                LIMIT 1
                """,
                (
                    event.event_identity,
                    forecast.forecast_identity,
                    LiveFeedEventKind.FORECAST_ISSUED.value,
                ),
            ).fetchone()

            present = (
                existing_forecast is not None,
                existing_proof is not None,
                existing_event is not None,
            )
            if any(present):
                if not all(present):
                    raise DecisionLedgerConflictError(
                        "partial immutable issuance bundle already exists"
                    )
                assert existing_forecast is not None
                assert existing_proof is not None
                assert existing_event is not None
                exact = (
                    str(existing_forecast[0]) == forecast_payload
                    and str(existing_forecast[1]) == forecast_digest
                    and str(existing_proof[0]) == proof.proof_identity
                    and str(existing_proof[1]) == proof_payload
                    and str(existing_proof[2]) == proof_digest
                    and str(existing_event[0]) == event.event_identity
                    and str(existing_event[1]) == event_payload
                    and str(existing_event[2]) == event_digest
                )
                if exact:
                    return DecisionLedgerWriteDisposition.UNCHANGED
                raise DecisionLedgerConflictError(
                    "immutable issuance bundle identity conflict"
                )

            last_forecast = connection.execute(
                """
                SELECT forecast_identity, issued_at_ms
                FROM r20_forecasts
                ORDER BY issued_at_ms DESC, forecast_identity DESC
                LIMIT 1
                """
            ).fetchone()
            if last_forecast is not None and (
                forecast.issued_at_ms,
                forecast.forecast_identity,
            ) <= (int(last_forecast[1]), str(last_forecast[0])):
                raise DecisionLedgerConflictError(
                    "R20 forecast append would backfill or fork chronology"
                )

            last_event = connection.execute(
                """
                SELECT event_identity, event_at_ms
                FROM r20_5_live_feed_events
                ORDER BY event_at_ms DESC, event_identity DESC
                LIMIT 1
                """
            ).fetchone()
            if last_event is not None and (
                event.event_at_ms,
                event.event_identity,
            ) <= (int(last_event[1]), str(last_event[0])):
                raise DecisionLedgerConflictError(
                    "live feed append would backfill or fork chronology"
                )

            connection.execute(
                """
                INSERT INTO r20_forecasts (
                    forecast_identity,
                    signal_freeze_identity,
                    asset,
                    symbol,
                    timeframe,
                    issued_at_ms,
                    source_as_of_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    forecast.forecast_identity,
                    forecast.signal_freeze_identity,
                    forecast.asset,
                    forecast.symbol,
                    forecast.timeframe,
                    forecast.issued_at_ms,
                    forecast.source_as_of_ms,
                    forecast_payload,
                    forecast_digest,
                ),
            )
            connection.execute(
                """
                INSERT INTO r20_5_decision_proofs (
                    proof_identity,
                    forecast_identity,
                    signal_freeze_identity,
                    asset,
                    symbol,
                    timeframe,
                    issued_at_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proof.proof_identity,
                    proof.forecast_identity,
                    proof.signal_freeze_identity,
                    proof.asset,
                    proof.symbol,
                    proof.timeframe,
                    proof.issued_at_ms,
                    proof_payload,
                    proof_digest,
                ),
            )
            connection.execute(
                """
                INSERT INTO r20_5_live_feed_events (
                    event_identity,
                    forecast_identity,
                    proof_identity,
                    resolution_identity,
                    kind,
                    event_at_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_identity,
                    event.forecast_identity,
                    event.proof_identity,
                    None,
                    event.kind.value,
                    event.event_at_ms,
                    event_payload,
                    event_digest,
                ),
            )
        return DecisionLedgerWriteDisposition.INSERTED

    def append_resolution(
        self,
        resolution: ForecastResolution,
    ) -> DecisionLedgerWriteDisposition:
        if resolution.production_authority or resolution.real_capital != REAL_CAPITAL:
            raise DecisionLedgerConflictError(
                "R20 resolution violates decision-ledger authority boundary"
            )
        payload, digest = _serialized(resolution)
        self.initialize()
        with self._connect_rw() as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            forecast = connection.execute(
                """
                SELECT signal_freeze_identity, issued_at_ms
                FROM r20_forecasts
                WHERE forecast_identity = ?
                """,
                (resolution.forecast_identity,),
            ).fetchone()
            if forecast is None:
                raise DecisionLedgerConflictError(
                    "R20 resolution references unknown forecast"
                )
            if str(forecast[0]) != resolution.signal_freeze_identity:
                raise DecisionLedgerConflictError(
                    "R20 resolution signal lineage mismatch"
                )
            if resolution.evaluated_at_ms < int(forecast[1]):
                raise DecisionLedgerConflictError(
                    "R20 resolution cannot predate forecast issuance"
                )
            existing = connection.execute(
                """
                SELECT resolution_identity, payload_json, payload_sha256
                FROM r20_resolutions
                WHERE forecast_identity = ? OR resolution_identity = ?
                LIMIT 1
                """,
                (resolution.forecast_identity, resolution.resolution_identity),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == resolution.resolution_identity
                    and str(existing[1]) == payload
                    and str(existing[2]) == digest
                ):
                    return DecisionLedgerWriteDisposition.UNCHANGED
                raise DecisionLedgerConflictError(
                    "immutable R20 forecast resolution conflict"
                )
            last = connection.execute(
                """
                SELECT resolution_identity, evaluated_at_ms
                FROM r20_resolutions
                ORDER BY evaluated_at_ms DESC, resolution_identity DESC
                LIMIT 1
                """
            ).fetchone()
            if last is not None and (
                resolution.evaluated_at_ms,
                resolution.resolution_identity,
            ) <= (int(last[1]), str(last[0])):
                raise DecisionLedgerConflictError(
                    "R20 resolution append would backfill or fork chronology"
                )
            connection.execute(
                """
                INSERT INTO r20_resolutions (
                    resolution_identity,
                    forecast_identity,
                    signal_freeze_identity,
                    evaluated_at_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    resolution.resolution_identity,
                    resolution.forecast_identity,
                    resolution.signal_freeze_identity,
                    resolution.evaluated_at_ms,
                    payload,
                    digest,
                ),
            )
        return DecisionLedgerWriteDisposition.INSERTED

    def append_feed_event(
        self,
        event: LiveIntelligenceFeedEvent,
    ) -> DecisionLedgerWriteDisposition:
        if (
            event.production_authority
            or not event.read_only
            or event.real_capital != REAL_CAPITAL
        ):
            raise DecisionLedgerConflictError(
                "Live Intelligence Feed event violates authority boundary"
            )
        payload, digest = _serialized(event)
        self.initialize()
        with self._connect_rw() as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            proof = connection.execute(
                """
                SELECT forecast_identity
                FROM r20_5_decision_proofs
                WHERE proof_identity = ?
                """,
                (event.proof_identity,),
            ).fetchone()
            if proof is None or str(proof[0]) != event.forecast_identity:
                raise DecisionLedgerConflictError(
                    "Live feed event proof/forecast lineage mismatch"
                )
            if event.kind is LiveFeedEventKind.FORECAST_RESOLVED:
                if event.resolution_identity is None:
                    raise DecisionLedgerConflictError(
                        "resolved live feed event requires resolution identity"
                    )
                resolution = connection.execute(
                    """
                    SELECT forecast_identity, evaluated_at_ms
                    FROM r20_resolutions
                    WHERE resolution_identity = ?
                    """,
                    (event.resolution_identity,),
                ).fetchone()
                if (
                    resolution is None
                    or str(resolution[0]) != event.forecast_identity
                    or int(resolution[1]) != event.event_at_ms
                ):
                    raise DecisionLedgerConflictError(
                        "Live feed resolution lineage mismatch"
                    )
            elif event.resolution_identity is not None:
                raise DecisionLedgerConflictError(
                    "issuance live feed event cannot carry resolution identity"
                )

            existing = connection.execute(
                """
                SELECT event_identity, payload_json, payload_sha256
                FROM r20_5_live_feed_events
                WHERE event_identity = ?
                   OR (forecast_identity = ? AND kind = ?)
                LIMIT 1
                """,
                (
                    event.event_identity,
                    event.forecast_identity,
                    event.kind.value,
                ),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == event.event_identity
                    and str(existing[1]) == payload
                    and str(existing[2]) == digest
                ):
                    return DecisionLedgerWriteDisposition.UNCHANGED
                raise DecisionLedgerConflictError(
                    "immutable Live Intelligence Feed event conflict"
                )

            last = connection.execute(
                """
                SELECT event_identity, event_at_ms
                FROM r20_5_live_feed_events
                ORDER BY event_at_ms DESC, event_identity DESC
                LIMIT 1
                """
            ).fetchone()
            if last is not None and (
                event.event_at_ms,
                event.event_identity,
            ) <= (int(last[1]), str(last[0])):
                raise DecisionLedgerConflictError(
                    "live feed append would backfill or fork chronology"
                )
            connection.execute(
                """
                INSERT INTO r20_5_live_feed_events (
                    event_identity,
                    forecast_identity,
                    proof_identity,
                    resolution_identity,
                    kind,
                    event_at_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_identity,
                    event.forecast_identity,
                    event.proof_identity,
                    event.resolution_identity,
                    event.kind.value,
                    event.event_at_ms,
                    payload,
                    digest,
                ),
            )
        return DecisionLedgerWriteDisposition.INSERTED

    def read_status(self) -> DecisionEvidenceLedgerStatus:
        with self._connect_ro() as connection:
            self._require_schema(connection)
            counts = {
                table: _table_count(connection, table)
                for table in (
                    "r20_forecasts",
                    "r20_5_decision_proofs",
                    "r20_resolutions",
                    "r20_5_live_feed_events",
                )
            }
            latest = connection.execute(
                """
                SELECT event_at_ms
                FROM r20_5_live_feed_events
                ORDER BY event_at_ms DESC, event_identity DESC
                LIMIT 1
                """
            ).fetchone()
        return DecisionEvidenceLedgerStatus(
            forecast_count=counts["r20_forecasts"],
            proof_count=counts["r20_5_decision_proofs"],
            resolution_count=counts["r20_resolutions"],
            feed_event_count=counts["r20_5_live_feed_events"],
            latest_event_at_ms=None if latest is None else int(latest[0]),
        )

    def read_issuance_for_signal(
        self,
        signal_freeze_identity: str,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Read one exact persisted R20/R20.5 issuance for recovery only."""
        _require_sha256(signal_freeze_identity, "signal freeze identity")
        with self._connect_ro() as connection:
            self._require_schema(connection)
            rows = connection.execute(
                """
                SELECT
                    f.payload_json,
                    f.payload_sha256,
                    p.payload_json,
                    p.payload_sha256
                FROM r20_forecasts AS f
                JOIN r20_5_decision_proofs AS p
                  ON p.forecast_identity = f.forecast_identity
                WHERE f.signal_freeze_identity = ?
                ORDER BY f.issued_at_ms, f.forecast_identity
                LIMIT 2
                """,
                (signal_freeze_identity,),
            ).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise DecisionLedgerConflictError(
                "signal freeze maps to multiple immutable R20 issuances"
            )
        row = rows[0]
        forecast = _verified_payload(str(row[0]), str(row[1]))
        proof = _verified_payload(str(row[2]), str(row[3]))
        if forecast.get("signal_freeze_identity") != signal_freeze_identity:
            raise DecisionLedgerConflictError(
                "persisted R20 signal identity mismatch"
            )
        if proof.get("signal_freeze_identity") != signal_freeze_identity:
            raise DecisionLedgerConflictError(
                "persisted Decision Proof signal identity mismatch"
            )
        if proof.get("forecast_identity") != forecast.get("forecast_identity"):
            raise DecisionLedgerConflictError(
                "persisted R20/Decision Proof identity mismatch"
            )
        return forecast, proof

    def read_resolution_for_forecast(
        self,
        forecast_identity: str,
    ) -> dict[str, Any] | None:
        """Read one immutable R20 resolution without mutating the ledger."""
        _require_sha256(forecast_identity, "forecast identity")
        with self._connect_ro() as connection:
            self._require_schema(connection)
            row = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM r20_resolutions
                WHERE forecast_identity = ?
                LIMIT 1
                """,
                (forecast_identity,),
            ).fetchone()
            if row is None:
                return None
            return _verified_payload(str(row[0]), str(row[1]))

    def read_proof_for_signal(
        self,
        signal_freeze_identity: str,
    ) -> dict[str, Any] | None:
        _require_sha256(signal_freeze_identity, "signal freeze identity")
        with self._connect_ro() as connection:
            self._require_schema(connection)
            row = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM r20_5_decision_proofs
                WHERE signal_freeze_identity = ?
                ORDER BY issued_at_ms DESC, proof_identity DESC
                LIMIT 1
                """,
                (signal_freeze_identity,),
            ).fetchone()
            if row is None:
                return None
            return _verified_payload(str(row[0]), str(row[1]))

    def read_feed(
        self,
        *,
        limit: int = 100,
    ) -> tuple[dict[str, Any], ...]:
        if limit <= 0 or limit > 1000:
            raise ValueError("decision feed limit must be inside [1,1000]")
        with self._connect_ro() as connection:
            self._require_schema(connection)
            rows = tuple(
                connection.execute(
                    """
                    SELECT payload_json, payload_sha256
                    FROM r20_5_live_feed_events
                    ORDER BY event_at_ms DESC, event_identity DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            )
        return tuple(
            _verified_payload(str(row[0]), str(row[1]))
            for row in rows
        )

    @contextmanager
    def _connect_rw(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @contextmanager
    def _connect_ro(self) -> Iterator[sqlite3.Connection]:
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _require_schema(connection: sqlite3.Connection) -> None:
        for table in (
            "r20_forecasts",
            "r20_resolutions",
            "r20_5_decision_proofs",
            "r20_5_live_feed_events",
        ):
            row = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = ?
                """,
                (table,),
            ).fetchone()
            if row is None:
                raise DecisionLedgerConflictError(
                    f"decision evidence ledger missing table: {table}"
                )


def _serialized(value: object) -> tuple[str, str]:
    payload = canonical_json(value)
    return payload, sha256_text(payload)


def _verified_payload(payload_json: str, expected_sha256: str) -> dict[str, Any]:
    if sha256_text(payload_json) != expected_sha256:
        raise DecisionLedgerConflictError(
            "decision evidence persisted payload digest mismatch"
        )
    raw = json.loads(payload_json)
    if not isinstance(raw, dict):
        raise DecisionLedgerConflictError(
            "decision evidence payload must decode to object"
        )
    if raw.get("real_capital") != REAL_CAPITAL:
        raise DecisionLedgerConflictError(
            "decision evidence persisted REAL_CAPITAL boundary mismatch"
        )
    if raw.get("production_authority") is True:
        raise DecisionLedgerConflictError(
            "decision evidence persisted production authority mismatch"
        )
    return raw


def _table_count(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    if row is None:
        raise DecisionLedgerConflictError(
            f"decision evidence count failed for {table}"
        )
    return int(row[0])


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be exact SHA256")
