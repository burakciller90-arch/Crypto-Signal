from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from crypto_signal.forecast.builders import (
    conditional_forecast_payload,
    decision_proof_payload,
    forecast_resolution_payload,
    verify_decision_proof_identity,
    verify_forecast_identity,
    verify_forecast_resolution_identity,
)
from crypto_signal.forecast.models import (
    ConditionalForecast,
    DecisionProof,
    ForecastResolution,
)
from crypto_signal.ledger.serialization import canonical_json
from crypto_signal.ledger.store import ImmutableSignalLedger


class ForecastLedgerConflictError(ValueError):
    """Raised when immutable forecast/proof lineage conflicts."""


class ForecastLedgerWriteDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class ForecastLedgerCounts:
    forecasts: int
    proofs: int
    resolutions: int


class ImmutableForecastLedger:
    """Append-only Decision Proof extension over the canonical signal ledger."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        ImmutableSignalLedger(self.path).initialize()
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conditional_forecasts (
                    forecast_identity TEXT PRIMARY KEY,
                    forecast_version TEXT NOT NULL,
                    signal_freeze_identity TEXT NOT NULL,
                    bundle_identity TEXT NOT NULL,
                    issued_at_ms INTEGER NOT NULL,
                    target_label TEXT NOT NULL,
                    horizon_bars INTEGER NOT NULL,
                    forecast_json TEXT NOT NULL,
                    appended_at_ms INTEGER NOT NULL,
                    UNIQUE (
                        signal_freeze_identity,
                        forecast_version,
                        target_label,
                        horizon_bars
                    ),
                    FOREIGN KEY (signal_freeze_identity)
                        REFERENCES signal_freezes(signal_freeze_identity),
                    FOREIGN KEY (bundle_identity)
                        REFERENCES signal_freezes(bundle_identity)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS decision_proofs (
                    proof_identity TEXT PRIMARY KEY,
                    proof_version TEXT NOT NULL,
                    forecast_identity TEXT NOT NULL UNIQUE,
                    signal_freeze_identity TEXT NOT NULL,
                    bundle_identity TEXT NOT NULL,
                    authority TEXT NOT NULL,
                    proof_json TEXT NOT NULL,
                    appended_at_ms INTEGER NOT NULL,
                    FOREIGN KEY (forecast_identity)
                        REFERENCES conditional_forecasts(forecast_identity),
                    FOREIGN KEY (signal_freeze_identity)
                        REFERENCES signal_freezes(signal_freeze_identity),
                    FOREIGN KEY (bundle_identity)
                        REFERENCES signal_freezes(bundle_identity)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS forecast_resolutions (
                    resolution_identity TEXT PRIMARY KEY,
                    resolution_version TEXT NOT NULL,
                    forecast_identity TEXT NOT NULL,
                    signal_freeze_identity TEXT NOT NULL,
                    outcome_identity TEXT NOT NULL,
                    evidence_class TEXT NOT NULL,
                    evaluated_as_of_ms INTEGER NOT NULL,
                    resolution_status TEXT NOT NULL,
                    outcome_state TEXT,
                    resolution_json TEXT NOT NULL,
                    appended_at_ms INTEGER NOT NULL,
                    UNIQUE (forecast_identity, outcome_identity),
                    FOREIGN KEY (forecast_identity)
                        REFERENCES conditional_forecasts(forecast_identity),
                    FOREIGN KEY (signal_freeze_identity)
                        REFERENCES signal_freezes(signal_freeze_identity),
                    FOREIGN KEY (outcome_identity)
                        REFERENCES outcome_evaluations(outcome_identity)
                )
                """
            )
            self._install_immutability_triggers(connection)

    def append_forecast(
        self,
        forecast: ConditionalForecast,
        *,
        appended_at_ms: int | None = None,
    ) -> ForecastLedgerWriteDisposition:
        verify_forecast_identity(forecast)
        canonical = canonical_json(conditional_forecast_payload(forecast))
        inserted_at = _inserted_at(
            appended_at_ms,
            minimum=forecast.issued_at_ms,
            label="forecast",
        )
        self.initialize()
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            parent = connection.execute(
                """
                SELECT bundle_identity
                FROM signal_freezes
                WHERE signal_freeze_identity = ?
                """,
                (forecast.signal_freeze_identity,),
            ).fetchone()
            if parent is None:
                raise ForecastLedgerConflictError(
                    "forecast references unknown signal freeze"
                )
            if str(parent["bundle_identity"]) != forecast.bundle_identity:
                raise ForecastLedgerConflictError(
                    "forecast bundle does not match frozen signal parent"
                )

            existing = connection.execute(
                """
                SELECT forecast_identity, forecast_json
                FROM conditional_forecasts
                WHERE forecast_identity = ?
                   OR (
                        signal_freeze_identity = ?
                        AND forecast_version = ?
                        AND target_label = ?
                        AND horizon_bars = ?
                   )
                LIMIT 1
                """,
                (
                    forecast.forecast_identity,
                    forecast.signal_freeze_identity,
                    forecast.forecast_version,
                    forecast.target_label,
                    forecast.horizon_bars,
                ),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["forecast_identity"]) == forecast.forecast_identity
                    and str(existing["forecast_json"]) == canonical
                ):
                    return ForecastLedgerWriteDisposition.UNCHANGED
                raise ForecastLedgerConflictError(
                    "immutable conditional forecast conflict"
                )

            connection.execute(
                """
                INSERT INTO conditional_forecasts (
                    forecast_identity,
                    forecast_version,
                    signal_freeze_identity,
                    bundle_identity,
                    issued_at_ms,
                    target_label,
                    horizon_bars,
                    forecast_json,
                    appended_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    forecast.forecast_identity,
                    forecast.forecast_version,
                    forecast.signal_freeze_identity,
                    forecast.bundle_identity,
                    forecast.issued_at_ms,
                    forecast.target_label,
                    forecast.horizon_bars,
                    canonical,
                    inserted_at,
                ),
            )
        return ForecastLedgerWriteDisposition.INSERTED

    def append_proof(
        self,
        proof: DecisionProof,
        *,
        appended_at_ms: int | None = None,
    ) -> ForecastLedgerWriteDisposition:
        verify_decision_proof_identity(proof)
        canonical = canonical_json(decision_proof_payload(proof))
        inserted_at = _inserted_at(
            appended_at_ms,
            minimum=proof.created_at_ms,
            label="Decision Proof",
        )
        self.initialize()
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            forecast = connection.execute(
                """
                SELECT signal_freeze_identity, bundle_identity
                FROM conditional_forecasts
                WHERE forecast_identity = ?
                """,
                (proof.forecast_identity,),
            ).fetchone()
            if forecast is None:
                raise ForecastLedgerConflictError(
                    "Decision Proof references unknown forecast"
                )
            if (
                str(forecast["signal_freeze_identity"])
                != proof.signal_freeze_identity
                or str(forecast["bundle_identity"]) != proof.bundle_identity
            ):
                raise ForecastLedgerConflictError(
                    "Decision Proof lineage does not match forecast"
                )

            existing = connection.execute(
                """
                SELECT proof_identity, proof_json
                FROM decision_proofs
                WHERE proof_identity = ?
                   OR forecast_identity = ?
                LIMIT 1
                """,
                (proof.proof_identity, proof.forecast_identity),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["proof_identity"]) == proof.proof_identity
                    and str(existing["proof_json"]) == canonical
                ):
                    return ForecastLedgerWriteDisposition.UNCHANGED
                raise ForecastLedgerConflictError(
                    "immutable Decision Proof conflict"
                )

            connection.execute(
                """
                INSERT INTO decision_proofs (
                    proof_identity,
                    proof_version,
                    forecast_identity,
                    signal_freeze_identity,
                    bundle_identity,
                    authority,
                    proof_json,
                    appended_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proof.proof_identity,
                    proof.proof_version,
                    proof.forecast_identity,
                    proof.signal_freeze_identity,
                    proof.bundle_identity,
                    proof.authority.value,
                    canonical,
                    inserted_at,
                ),
            )
        return ForecastLedgerWriteDisposition.INSERTED

    def append_resolution(
        self,
        resolution: ForecastResolution,
        *,
        appended_at_ms: int | None = None,
    ) -> ForecastLedgerWriteDisposition:
        verify_forecast_resolution_identity(resolution)
        canonical = canonical_json(forecast_resolution_payload(resolution))
        inserted_at = _inserted_at(
            appended_at_ms,
            minimum=resolution.evaluated_as_of_ms,
            label="forecast resolution",
        )
        self.initialize()
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            forecast = connection.execute(
                """
                SELECT signal_freeze_identity, horizon_bars
                FROM conditional_forecasts
                WHERE forecast_identity = ?
                """,
                (resolution.forecast_identity,),
            ).fetchone()
            if forecast is None:
                raise ForecastLedgerConflictError(
                    "resolution references unknown forecast"
                )
            outcome = connection.execute(
                """
                SELECT signal_freeze_identity, max_holding_bars
                FROM outcome_evaluations
                WHERE outcome_identity = ?
                """,
                (resolution.outcome_identity,),
            ).fetchone()
            if outcome is None:
                raise ForecastLedgerConflictError(
                    "resolution references unknown outcome"
                )
            if (
                str(forecast["signal_freeze_identity"])
                != resolution.signal_freeze_identity
                or str(outcome["signal_freeze_identity"])
                != resolution.signal_freeze_identity
            ):
                raise ForecastLedgerConflictError(
                    "forecast resolution signal lineage mismatch"
                )
            if (
                int(forecast["horizon_bars"]) != resolution.horizon_bars
                or int(outcome["max_holding_bars"]) != resolution.horizon_bars
            ):
                raise ForecastLedgerConflictError(
                    "forecast resolution horizon lineage mismatch"
                )

            existing = connection.execute(
                """
                SELECT resolution_identity, resolution_json
                FROM forecast_resolutions
                WHERE resolution_identity = ?
                   OR (
                        forecast_identity = ?
                        AND outcome_identity = ?
                   )
                LIMIT 1
                """,
                (
                    resolution.resolution_identity,
                    resolution.forecast_identity,
                    resolution.outcome_identity,
                ),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["resolution_identity"])
                    == resolution.resolution_identity
                    and str(existing["resolution_json"]) == canonical
                ):
                    return ForecastLedgerWriteDisposition.UNCHANGED
                raise ForecastLedgerConflictError(
                    "immutable forecast resolution conflict"
                )

            connection.execute(
                """
                INSERT INTO forecast_resolutions (
                    resolution_identity,
                    resolution_version,
                    forecast_identity,
                    signal_freeze_identity,
                    outcome_identity,
                    evidence_class,
                    evaluated_as_of_ms,
                    resolution_status,
                    outcome_state,
                    resolution_json,
                    appended_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolution.resolution_identity,
                    resolution.resolution_version,
                    resolution.forecast_identity,
                    resolution.signal_freeze_identity,
                    resolution.outcome_identity,
                    resolution.evidence_class.value,
                    resolution.evaluated_as_of_ms,
                    resolution.resolution_status.value,
                    (
                        None
                        if resolution.outcome_state is None
                        else resolution.outcome_state.value
                    ),
                    canonical,
                    inserted_at,
                ),
            )
        return ForecastLedgerWriteDisposition.INSERTED

    def counts(self) -> ForecastLedgerCounts:
        self.initialize()
        with self._connect() as connection:
            return ForecastLedgerCounts(
                forecasts=_count(connection, "conditional_forecasts"),
                proofs=_count(connection, "decision_proofs"),
                resolutions=_count(connection, "forecast_resolutions"),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _install_immutability_triggers(
        connection: sqlite3.Connection,
    ) -> None:
        for table in (
            "conditional_forecasts",
            "decision_proofs",
            "forecast_resolutions",
        ):
            connection.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS {table}_reject_update
                BEFORE UPDATE ON {table}
                BEGIN
                    SELECT RAISE(ABORT, 'immutable forecast ledger rejects UPDATE');
                END
                """
            )
            connection.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS {table}_reject_delete
                BEFORE DELETE ON {table}
                BEGIN
                    SELECT RAISE(ABORT, 'immutable forecast ledger rejects DELETE');
                END
                """
            )


def _inserted_at(
    value: int | None,
    *,
    minimum: int,
    label: str,
) -> int:
    inserted_at = int(time.time() * 1000) if value is None else value
    if inserted_at < minimum:
        raise ValueError(f"{label} append time cannot precede event time")
    return inserted_at


def _count(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(
        f"SELECT COUNT(*) AS count FROM {table}"
    ).fetchone()
    return 0 if row is None else int(row["count"])
