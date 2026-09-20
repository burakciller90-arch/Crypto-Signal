from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from crypto_signal.ledger.bundle import (
    DecisionFreezeBundle,
    bundle_json,
    verify_bundle_identity,
)
from crypto_signal.ledger.serialization import canonical_json, sha256_text
from crypto_signal.outcomes.evaluator import verify_outcome_identity
from crypto_signal.outcomes.models import OutcomeEvaluation
from crypto_signal.signals.models import SignalLifecycleEvaluation


class LedgerConflictError(ValueError):
    """Raised when immutable ledger identity is rebound to different content."""


class LedgerWriteDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class FreezeRecord:
    bundle_identity: str
    signal_freeze_identity: str
    exchange: str
    market_type: str
    symbol: str
    timeframe: str
    as_of_ms: int
    source_cutoff_open_time_ms: int
    signal_state: str
    direction: str
    frozen_at_ms: int
    bundle_json: str


@dataclass(frozen=True, slots=True)
class LifecycleRecord:
    evaluation_identity: str
    signal_freeze_identity: str
    evaluated_as_of_ms: int
    current_state: str
    status: str
    appended_at_ms: int
    evaluation_json: str


@dataclass(frozen=True, slots=True)
class OutcomeRecord:
    outcome_identity: str
    signal_freeze_identity: str
    evidence_class: str
    evaluated_as_of_ms: int
    resolution_status: str
    outcome_state: str | None
    max_holding_bars: int
    appended_at_ms: int
    outcome_json: str


def lifecycle_evaluation_json(
    evaluation: SignalLifecycleEvaluation,
) -> str:
    return canonical_json(evaluation)


def lifecycle_evaluation_identity(
    evaluation: SignalLifecycleEvaluation,
) -> str:
    return sha256_text(lifecycle_evaluation_json(evaluation))


def outcome_evaluation_json(evaluation: OutcomeEvaluation) -> str:
    return canonical_json(evaluation)


class ImmutableSignalLedger:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS signal_freezes (
                    bundle_identity TEXT PRIMARY KEY,
                    signal_freeze_identity TEXT NOT NULL UNIQUE,
                    exchange TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    as_of_ms INTEGER NOT NULL,
                    source_cutoff_open_time_ms INTEGER NOT NULL,
                    signal_state TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    bundle_json TEXT NOT NULL,
                    frozen_at_ms INTEGER NOT NULL,
                    UNIQUE (
                        exchange,
                        market_type,
                        symbol,
                        timeframe,
                        source_cutoff_open_time_ms
                    )
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS lifecycle_evaluations (
                    evaluation_identity TEXT PRIMARY KEY,
                    signal_freeze_identity TEXT NOT NULL,
                    evaluated_as_of_ms INTEGER NOT NULL,
                    current_state TEXT NOT NULL,
                    status TEXT NOT NULL,
                    evaluation_json TEXT NOT NULL,
                    appended_at_ms INTEGER NOT NULL,
                    UNIQUE (signal_freeze_identity, evaluated_as_of_ms),
                    FOREIGN KEY (signal_freeze_identity)
                        REFERENCES signal_freezes(signal_freeze_identity)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS outcome_evaluations (
                    outcome_identity TEXT PRIMARY KEY,
                    signal_freeze_identity TEXT NOT NULL,
                    evidence_class TEXT NOT NULL,
                    evaluated_as_of_ms INTEGER NOT NULL,
                    resolution_status TEXT NOT NULL,
                    outcome_state TEXT,
                    max_holding_bars INTEGER NOT NULL,
                    outcome_json TEXT NOT NULL,
                    appended_at_ms INTEGER NOT NULL,
                    UNIQUE (
                        signal_freeze_identity,
                        evidence_class,
                        evaluated_as_of_ms,
                        max_holding_bars
                    ),
                    FOREIGN KEY (signal_freeze_identity)
                        REFERENCES signal_freezes(signal_freeze_identity)
                )
                """
            )
            self._install_immutability_triggers(connection)

    def freeze(
        self,
        bundle: DecisionFreezeBundle,
        *,
        frozen_at_ms: int | None = None,
    ) -> LedgerWriteDisposition:
        verify_bundle_identity(bundle)
        canonical_bundle = bundle_json(bundle)
        decision = bundle.signal_decision
        inserted_at = (
            int(time.time() * 1000)
            if frozen_at_ms is None
            else frozen_at_ms
        )
        if inserted_at < decision.as_of_ms:
            raise ValueError("ledger freeze time cannot precede decision as-of")

        self.initialize()
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")

            existing = self._find_existing_freeze(
                connection,
                bundle=bundle,
            )
            if existing is not None:
                if (
                    existing.bundle_identity == bundle.bundle_identity
                    and existing.signal_freeze_identity
                    == decision.freeze_identity
                    and existing.bundle_json == canonical_bundle
                ):
                    return LedgerWriteDisposition.UNCHANGED
                raise LedgerConflictError(
                    "immutable freeze conflict for signal identity or source cutoff"
                )

            connection.execute(
                """
                INSERT INTO signal_freezes (
                    bundle_identity,
                    signal_freeze_identity,
                    exchange,
                    market_type,
                    symbol,
                    timeframe,
                    as_of_ms,
                    source_cutoff_open_time_ms,
                    signal_state,
                    direction,
                    bundle_json,
                    frozen_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bundle.bundle_identity,
                    decision.freeze_identity,
                    decision.exchange.value,
                    decision.market_type.value,
                    decision.symbol,
                    decision.timeframe,
                    decision.as_of_ms,
                    bundle.source_cutoff_open_time_ms,
                    decision.state.value,
                    decision.direction.value,
                    canonical_bundle,
                    inserted_at,
                ),
            )
        return LedgerWriteDisposition.INSERTED

    def append_lifecycle_evaluation(
        self,
        evaluation: SignalLifecycleEvaluation,
        *,
        appended_at_ms: int | None = None,
    ) -> LedgerWriteDisposition:
        canonical_evaluation = lifecycle_evaluation_json(evaluation)
        identity = lifecycle_evaluation_identity(evaluation)
        inserted_at = (
            int(time.time() * 1000)
            if appended_at_ms is None
            else appended_at_ms
        )
        if inserted_at < evaluation.evaluated_as_of_ms:
            raise ValueError(
                "lifecycle append time cannot precede evaluation as-of"
            )

        self.initialize()
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            parent = connection.execute(
                """
                SELECT signal_freeze_identity
                FROM signal_freezes
                WHERE signal_freeze_identity = ?
                """,
                (evaluation.signal_freeze_identity,),
            ).fetchone()
            if parent is None:
                raise LedgerConflictError(
                    "lifecycle evaluation references unknown signal freeze"
                )

            existing = connection.execute(
                """
                SELECT * FROM lifecycle_evaluations
                WHERE evaluation_identity = ?
                   OR (
                        signal_freeze_identity = ?
                        AND evaluated_as_of_ms = ?
                   )
                LIMIT 1
                """,
                (
                    identity,
                    evaluation.signal_freeze_identity,
                    evaluation.evaluated_as_of_ms,
                ),
            ).fetchone()
            if existing is not None:
                record = self._row_to_lifecycle(existing)
                if (
                    record.evaluation_identity == identity
                    and record.evaluation_json == canonical_evaluation
                ):
                    return LedgerWriteDisposition.UNCHANGED
                raise LedgerConflictError(
                    "immutable lifecycle evaluation conflict"
                )

            connection.execute(
                """
                INSERT INTO lifecycle_evaluations (
                    evaluation_identity,
                    signal_freeze_identity,
                    evaluated_as_of_ms,
                    current_state,
                    status,
                    evaluation_json,
                    appended_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identity,
                    evaluation.signal_freeze_identity,
                    evaluation.evaluated_as_of_ms,
                    evaluation.current_state.value,
                    evaluation.status.value,
                    canonical_evaluation,
                    inserted_at,
                ),
            )
        return LedgerWriteDisposition.INSERTED

    def append_outcome_evaluation(
        self,
        evaluation: OutcomeEvaluation,
        *,
        appended_at_ms: int | None = None,
    ) -> LedgerWriteDisposition:
        verify_outcome_identity(evaluation)
        canonical_outcome = outcome_evaluation_json(evaluation)
        inserted_at = (
            int(time.time() * 1000)
            if appended_at_ms is None
            else appended_at_ms
        )
        if inserted_at < evaluation.evaluated_as_of_ms:
            raise ValueError(
                "outcome append time cannot precede evaluation as-of"
            )

        self.initialize()
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            parent = connection.execute(
                """
                SELECT signal_freeze_identity
                FROM signal_freezes
                WHERE signal_freeze_identity = ?
                """,
                (evaluation.signal_freeze_identity,),
            ).fetchone()
            if parent is None:
                raise LedgerConflictError(
                    "outcome evaluation references unknown signal freeze"
                )

            existing = connection.execute(
                """
                SELECT * FROM outcome_evaluations
                WHERE outcome_identity = ?
                   OR (
                        signal_freeze_identity = ?
                        AND evidence_class = ?
                        AND evaluated_as_of_ms = ?
                        AND max_holding_bars = ?
                   )
                LIMIT 1
                """,
                (
                    evaluation.outcome_identity,
                    evaluation.signal_freeze_identity,
                    evaluation.evidence_class.value,
                    evaluation.evaluated_as_of_ms,
                    evaluation.max_holding_bars,
                ),
            ).fetchone()
            if existing is not None:
                record = self._row_to_outcome(existing)
                if (
                    record.outcome_identity == evaluation.outcome_identity
                    and record.outcome_json == canonical_outcome
                ):
                    return LedgerWriteDisposition.UNCHANGED
                raise LedgerConflictError(
                    "immutable outcome evaluation conflict"
                )

            connection.execute(
                """
                INSERT INTO outcome_evaluations (
                    outcome_identity,
                    signal_freeze_identity,
                    evidence_class,
                    evaluated_as_of_ms,
                    resolution_status,
                    outcome_state,
                    max_holding_bars,
                    outcome_json,
                    appended_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation.outcome_identity,
                    evaluation.signal_freeze_identity,
                    evaluation.evidence_class.value,
                    evaluation.evaluated_as_of_ms,
                    evaluation.resolution_status.value,
                    (
                        None
                        if evaluation.outcome_state is None
                        else evaluation.outcome_state.value
                    ),
                    evaluation.max_holding_bars,
                    canonical_outcome,
                    inserted_at,
                ),
            )
        return LedgerWriteDisposition.INSERTED

    def has_source_cutoff(
        self,
        *,
        exchange: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        source_cutoff_open_time_ms: int,
    ) -> bool:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM signal_freezes
                WHERE exchange = ?
                  AND market_type = ?
                  AND symbol = ?
                  AND timeframe = ?
                  AND source_cutoff_open_time_ms = ?
                LIMIT 1
                """,
                (
                    exchange,
                    market_type,
                    symbol,
                    timeframe,
                    source_cutoff_open_time_ms,
                ),
            ).fetchone()
        return row is not None

    def get_freeze_by_signal(
        self,
        signal_freeze_identity: str,
    ) -> FreezeRecord | None:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM signal_freezes
                WHERE signal_freeze_identity = ?
                """,
                (signal_freeze_identity,),
            ).fetchone()
        return None if row is None else self._row_to_freeze(row)

    def list_freezes(self) -> tuple[FreezeRecord, ...]:
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM signal_freezes
                ORDER BY frozen_at_ms ASC, bundle_identity ASC
                """
            ).fetchall()
        return tuple(self._row_to_freeze(row) for row in rows)

    def list_lifecycle_evaluations(
        self,
        signal_freeze_identity: str | None = None,
    ) -> tuple[LifecycleRecord, ...]:
        self.initialize()
        with self._connect() as connection:
            if signal_freeze_identity is None:
                rows = connection.execute(
                    """
                    SELECT * FROM lifecycle_evaluations
                    ORDER BY appended_at_ms ASC, evaluation_identity ASC
                    """
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM lifecycle_evaluations
                    WHERE signal_freeze_identity = ?
                    ORDER BY appended_at_ms ASC, evaluation_identity ASC
                    """,
                    (signal_freeze_identity,),
                ).fetchall()
        return tuple(self._row_to_lifecycle(row) for row in rows)

    def list_outcome_evaluations(
        self,
        signal_freeze_identity: str | None = None,
    ) -> tuple[OutcomeRecord, ...]:
        self.initialize()
        with self._connect() as connection:
            if signal_freeze_identity is None:
                rows = connection.execute(
                    """
                    SELECT * FROM outcome_evaluations
                    ORDER BY appended_at_ms ASC, outcome_identity ASC
                    """
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM outcome_evaluations
                    WHERE signal_freeze_identity = ?
                    ORDER BY appended_at_ms ASC, outcome_identity ASC
                    """,
                    (signal_freeze_identity,),
                ).fetchall()
        return tuple(self._row_to_outcome(row) for row in rows)

    def count_freezes(self) -> int:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM signal_freezes"
            ).fetchone()
        return 0 if row is None else int(row["count"])

    def count_lifecycle_evaluations(self) -> int:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM lifecycle_evaluations"
            ).fetchone()
        return 0 if row is None else int(row["count"])

    def count_outcome_evaluations(self) -> int:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM outcome_evaluations"
            ).fetchone()
        return 0 if row is None else int(row["count"])

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _install_immutability_triggers(
        connection: sqlite3.Connection,
    ) -> None:
        for table in (
            "signal_freezes",
            "lifecycle_evaluations",
            "outcome_evaluations",
        ):
            connection.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS {table}_reject_update
                BEFORE UPDATE ON {table}
                BEGIN
                    SELECT RAISE(ABORT, 'immutable ledger rejects UPDATE');
                END
                """
            )
            connection.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS {table}_reject_delete
                BEFORE DELETE ON {table}
                BEGIN
                    SELECT RAISE(ABORT, 'immutable ledger rejects DELETE');
                END
                """
            )

    def _find_existing_freeze(
        self,
        connection: sqlite3.Connection,
        *,
        bundle: DecisionFreezeBundle,
    ) -> FreezeRecord | None:
        decision = bundle.signal_decision
        row = connection.execute(
            """
            SELECT * FROM signal_freezes
            WHERE bundle_identity = ?
               OR signal_freeze_identity = ?
               OR (
                    exchange = ?
                    AND market_type = ?
                    AND symbol = ?
                    AND timeframe = ?
                    AND source_cutoff_open_time_ms = ?
               )
            LIMIT 1
            """,
            (
                bundle.bundle_identity,
                decision.freeze_identity,
                decision.exchange.value,
                decision.market_type.value,
                decision.symbol,
                decision.timeframe,
                bundle.source_cutoff_open_time_ms,
            ),
        ).fetchone()
        return None if row is None else self._row_to_freeze(row)

    @staticmethod
    def _row_to_freeze(row: sqlite3.Row) -> FreezeRecord:
        return FreezeRecord(
            bundle_identity=str(row["bundle_identity"]),
            signal_freeze_identity=str(row["signal_freeze_identity"]),
            exchange=str(row["exchange"]),
            market_type=str(row["market_type"]),
            symbol=str(row["symbol"]),
            timeframe=str(row["timeframe"]),
            as_of_ms=int(row["as_of_ms"]),
            source_cutoff_open_time_ms=int(row["source_cutoff_open_time_ms"]),
            signal_state=str(row["signal_state"]),
            direction=str(row["direction"]),
            frozen_at_ms=int(row["frozen_at_ms"]),
            bundle_json=str(row["bundle_json"]),
        )

    @staticmethod
    def _row_to_lifecycle(row: sqlite3.Row) -> LifecycleRecord:
        return LifecycleRecord(
            evaluation_identity=str(row["evaluation_identity"]),
            signal_freeze_identity=str(row["signal_freeze_identity"]),
            evaluated_as_of_ms=int(row["evaluated_as_of_ms"]),
            current_state=str(row["current_state"]),
            status=str(row["status"]),
            appended_at_ms=int(row["appended_at_ms"]),
            evaluation_json=str(row["evaluation_json"]),
        )

    @staticmethod
    def _row_to_outcome(row: sqlite3.Row) -> OutcomeRecord:
        return OutcomeRecord(
            outcome_identity=str(row["outcome_identity"]),
            signal_freeze_identity=str(row["signal_freeze_identity"]),
            evidence_class=str(row["evidence_class"]),
            evaluated_as_of_ms=int(row["evaluated_as_of_ms"]),
            resolution_status=str(row["resolution_status"]),
            outcome_state=(
                None
                if row["outcome_state"] is None
                else str(row["outcome_state"])
            ),
            max_holding_bars=int(row["max_holding_bars"]),
            appended_at_ms=int(row["appended_at_ms"]),
            outcome_json=str(row["outcome_json"]),
        )
