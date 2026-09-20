"""Persistent paper-account runtime foundation.

This layer creates/reopens exactly one virtual 100 USDT fund and observes the
accepted immutable signal ledger in read-only mode. It does not create a
decision-to-trade policy, execution venue truth, network calls, or real orders.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from crypto_signal.paper.ledger import (
    PaperFundLedger,
    PaperLedgerConflictError,
    PaperLedgerWriteDisposition,
)
from crypto_signal.paper.models import REAL_CAPITAL, build_fund_creation
from crypto_signal.paper.state import (
    PaperFundState,
    reconstruct_paper_fund_state_from_entries,
)

__all__ = [
    "REAL_CAPITAL",
    "PaperFundBootstrapStatus",
    "PaperRuntimeError",
    "PaperRuntimeSnapshot",
    "PaperSignalLedgerObservation",
    "ensure_persistent_paper_fund",
    "observe_signal_ledger",
    "run_paper_runtime_tick",
]


class PaperRuntimeError(RuntimeError):
    """Raised when persistent paper runtime truth cannot be established safely."""


class PaperFundBootstrapStatus(StrEnum):
    CREATED = "created"
    EXISTING = "existing"


@dataclass(frozen=True, slots=True)
class PaperSignalLedgerObservation:
    freeze_count: int
    lifecycle_count: int
    outcome_count: int
    latest_signal_freeze_identity: str | None
    latest_frozen_at_ms: int | None
    latest_symbol: str | None
    latest_timeframe: str | None
    latest_signal_state: str | None
    latest_direction: str | None

    def __post_init__(self) -> None:
        if min(self.freeze_count, self.lifecycle_count, self.outcome_count) < 0:
            raise ValueError("signal-ledger observation counts cannot be negative")
        latest_values = (
            self.latest_signal_freeze_identity,
            self.latest_frozen_at_ms,
            self.latest_symbol,
            self.latest_timeframe,
            self.latest_signal_state,
            self.latest_direction,
        )
        if self.freeze_count == 0 and any(value is not None for value in latest_values):
            raise ValueError("empty signal ledger cannot expose latest signal metadata")
        if self.freeze_count > 0 and any(value is None for value in latest_values):
            raise ValueError("non-empty signal ledger requires latest signal metadata")


@dataclass(frozen=True, slots=True)
class PaperRuntimeSnapshot:
    bootstrap_status: PaperFundBootstrapStatus
    fund_state: PaperFundState
    signal_observation: PaperSignalLedgerObservation
    trade_policy_activated: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.trade_policy_activated:
            raise ValueError(
                "Stage 6C runtime foundation must not activate a trade policy"
            )


def ensure_persistent_paper_fund(
    ledger: PaperFundLedger,
    *,
    created_at_ms: int,
) -> tuple[PaperFundBootstrapStatus, PaperFundState]:
    """Create the single fund once, or deterministically reopen the existing fund."""
    if created_at_ms < 0:
        raise ValueError("created_at_ms must be non-negative")

    replay = ledger.replay()
    if replay:
        return (
            PaperFundBootstrapStatus.EXISTING,
            reconstruct_paper_fund_state_from_entries(replay),
        )

    creation = build_fund_creation(created_at_ms=created_at_ms)
    try:
        disposition, replay = ledger._append_records_atomic(
            (creation,),
            expected_replayed_record_count=0,
        )
    except PaperLedgerConflictError:
        replay = ledger.replay()
        if not replay:
            raise
        return (
            PaperFundBootstrapStatus.EXISTING,
            reconstruct_paper_fund_state_from_entries(replay),
        )

    status = (
        PaperFundBootstrapStatus.CREATED
        if disposition is PaperLedgerWriteDisposition.INSERTED
        else PaperFundBootstrapStatus.EXISTING
    )
    return status, reconstruct_paper_fund_state_from_entries(replay)


def observe_signal_ledger(path: Path) -> PaperSignalLedgerObservation:
    """Read accepted live signal-ledger metadata without initializing or mutating it."""
    if not path.exists():
        raise PaperRuntimeError("immutable signal ledger does not exist")

    uri = f"file:{path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        required = (
            "signal_freezes",
            "lifecycle_evaluations",
            "outcome_evaluations",
        )
        for table in required:
            row = connection.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table' AND name = ?
                """,
                (table,),
            ).fetchone()
            if row is None:
                raise PaperRuntimeError(
                    f"immutable signal ledger missing required table: {table}"
                )

        freeze_count = _table_count(connection, "signal_freezes")
        lifecycle_count = _table_count(connection, "lifecycle_evaluations")
        outcome_count = _table_count(connection, "outcome_evaluations")
        latest = connection.execute(
            """
            SELECT
                signal_freeze_identity,
                frozen_at_ms,
                symbol,
                timeframe,
                signal_state,
                direction
            FROM signal_freezes
            ORDER BY frozen_at_ms DESC, signal_freeze_identity DESC
            LIMIT 1
            """
        ).fetchone()

    if latest is None:
        return PaperSignalLedgerObservation(
            freeze_count=freeze_count,
            lifecycle_count=lifecycle_count,
            outcome_count=outcome_count,
            latest_signal_freeze_identity=None,
            latest_frozen_at_ms=None,
            latest_symbol=None,
            latest_timeframe=None,
            latest_signal_state=None,
            latest_direction=None,
        )
    return PaperSignalLedgerObservation(
        freeze_count=freeze_count,
        lifecycle_count=lifecycle_count,
        outcome_count=outcome_count,
        latest_signal_freeze_identity=str(latest["signal_freeze_identity"]),
        latest_frozen_at_ms=int(latest["frozen_at_ms"]),
        latest_symbol=str(latest["symbol"]),
        latest_timeframe=str(latest["timeframe"]),
        latest_signal_state=str(latest["signal_state"]),
        latest_direction=str(latest["direction"]),
    )


def run_paper_runtime_tick(
    *,
    paper_ledger_path: Path,
    signal_ledger_path: Path,
    created_at_ms: int,
) -> PaperRuntimeSnapshot:
    """Run one restart-safe, no-trade paper-account observation tick."""
    observation = observe_signal_ledger(signal_ledger_path)
    ledger = PaperFundLedger(paper_ledger_path)
    bootstrap_status, fund_state = ensure_persistent_paper_fund(
        ledger,
        created_at_ms=created_at_ms,
    )
    return PaperRuntimeSnapshot(
        bootstrap_status=bootstrap_status,
        fund_state=fund_state,
        signal_observation=observation,
        trade_policy_activated=False,
        real_capital=REAL_CAPITAL,
    )


def _table_count(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    if row is None:
        raise PaperRuntimeError(f"failed to count table: {table}")
    return int(row["count"])
