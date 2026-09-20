"""Append-only SQLite ledger for the virtual 100 USDT paper fund.

Insert-only public API. No update/delete surface. No real order execution.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from crypto_signal.ledger.serialization import canonical_json
from crypto_signal.paper.models import (
    BenchmarkId,
    DecisionIntentRecord,
    ExecutionCostAssumptions,
    FundCreationRecord,
    NavSnapshotRecord,
    PaperAction,
    PaperPosition,
    PaperSymbol,
    PositionCashMutationRecord,
    SimulatedFillRecord,
)


class PaperLedgerConflictError(ValueError):
    """Raised when a deterministic identity is rebound to different content."""


class PaperLedgerWriteDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


class PaperRecordKind(StrEnum):
    FUND_CREATION = "fund_creation"
    DECISION_INTENT = "decision_intent"
    SIMULATED_FILL = "simulated_fill"
    POSITION_CASH_MUTATION = "position_cash_mutation"
    NAV_SNAPSHOT = "nav_snapshot"


PaperRecord = (
    FundCreationRecord
    | DecisionIntentRecord
    | SimulatedFillRecord
    | PositionCashMutationRecord
    | NavSnapshotRecord
)


@dataclass(frozen=True, slots=True)
class PaperLedgerEntry:
    sequence_id: int
    record_kind: PaperRecordKind
    record_identity: str
    appended_at_ms: int
    payload_json: str
    record: PaperRecord


_TABLE_BY_KIND: dict[PaperRecordKind, str] = {
    PaperRecordKind.FUND_CREATION: "paper_fund_creations",
    PaperRecordKind.DECISION_INTENT: "paper_decision_intents",
    PaperRecordKind.SIMULATED_FILL: "paper_simulated_fills",
    PaperRecordKind.POSITION_CASH_MUTATION: "paper_position_cash_mutations",
    PaperRecordKind.NAV_SNAPSHOT: "paper_nav_snapshots",
}


class PaperFundLedger:
    """Caller-supplied-path append-only paper fund ledger."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            for table in _TABLE_BY_KIND.values():
                connection.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        record_identity TEXT PRIMARY KEY,
                        payload_json TEXT NOT NULL,
                        appended_at_ms INTEGER NOT NULL
                    )
                    """
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_replay_index (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_kind TEXT NOT NULL,
                    record_identity TEXT NOT NULL UNIQUE,
                    appended_at_ms INTEGER NOT NULL
                )
                """
            )
            self._install_immutability_triggers(connection)

    def append_fund_creation(
        self,
        record: FundCreationRecord,
        *,
        appended_at_ms: int | None = None,
    ) -> PaperLedgerWriteDisposition:
        return self._append(
            kind=PaperRecordKind.FUND_CREATION,
            record_identity=record.record_identity,
            payload_json=canonical_json(record),
            appended_at_ms=(
                record.created_at_ms if appended_at_ms is None else appended_at_ms
            ),
        )

    def append_decision_intent(
        self,
        record: DecisionIntentRecord,
        *,
        appended_at_ms: int | None = None,
    ) -> PaperLedgerWriteDisposition:
        return self._append(
            kind=PaperRecordKind.DECISION_INTENT,
            record_identity=record.record_identity,
            payload_json=canonical_json(record),
            appended_at_ms=(
                record.decided_at_ms if appended_at_ms is None else appended_at_ms
            ),
        )

    def append_simulated_fill(
        self,
        record: SimulatedFillRecord,
        *,
        appended_at_ms: int | None = None,
    ) -> PaperLedgerWriteDisposition:
        return self._append(
            kind=PaperRecordKind.SIMULATED_FILL,
            record_identity=record.record_identity,
            payload_json=canonical_json(record),
            appended_at_ms=(
                record.filled_at_ms if appended_at_ms is None else appended_at_ms
            ),
        )

    def append_position_cash_mutation(
        self,
        record: PositionCashMutationRecord,
        *,
        appended_at_ms: int | None = None,
    ) -> PaperLedgerWriteDisposition:
        return self._append(
            kind=PaperRecordKind.POSITION_CASH_MUTATION,
            record_identity=record.record_identity,
            payload_json=canonical_json(record),
            appended_at_ms=(
                record.mutated_at_ms if appended_at_ms is None else appended_at_ms
            ),
        )

    def append_nav_snapshot(
        self,
        record: NavSnapshotRecord,
        *,
        appended_at_ms: int | None = None,
    ) -> PaperLedgerWriteDisposition:
        return self._append(
            kind=PaperRecordKind.NAV_SNAPSHOT,
            record_identity=record.record_identity,
            payload_json=canonical_json(record),
            appended_at_ms=(
                record.snapshot_at_ms if appended_at_ms is None else appended_at_ms
            ),
        )

    def replay(self) -> tuple[PaperLedgerEntry, ...]:
        """Return all paper-fund records in append order."""
        self.initialize()
        with self._connect() as connection:
            index_rows = connection.execute(
                """
                SELECT sequence_id, record_kind, record_identity, appended_at_ms
                FROM paper_replay_index
                ORDER BY sequence_id ASC
                """
            ).fetchall()
            entries: list[PaperLedgerEntry] = []
            for row in index_rows:
                kind = PaperRecordKind(str(row["record_kind"]))
                table = _TABLE_BY_KIND[kind]
                payload_row = connection.execute(
                    f"""
                    SELECT payload_json
                    FROM {table}
                    WHERE record_identity = ?
                    """,
                    (str(row["record_identity"]),),
                ).fetchone()
                if payload_row is None:
                    raise RuntimeError(
                        f"missing payload for paper record {row['record_identity']}"
                    )
                payload_json = str(payload_row["payload_json"])
                entries.append(
                    PaperLedgerEntry(
                        sequence_id=int(row["sequence_id"]),
                        record_kind=kind,
                        record_identity=str(row["record_identity"]),
                        appended_at_ms=int(row["appended_at_ms"]),
                        payload_json=payload_json,
                        record=deserialize_paper_record(kind, payload_json),
                    )
                )
        return tuple(entries)

    def list_fund_creations(self) -> tuple[FundCreationRecord, ...]:
        return tuple(
            entry.record
            for entry in self.replay()
            if isinstance(entry.record, FundCreationRecord)
        )

    def get_by_identity(self, record_identity: str) -> PaperLedgerEntry | None:
        for entry in self.replay():
            if entry.record_identity == record_identity:
                return entry
        return None

    def _append(
        self,
        *,
        kind: PaperRecordKind,
        record_identity: str,
        payload_json: str,
        appended_at_ms: int,
    ) -> PaperLedgerWriteDisposition:
        if appended_at_ms < 0:
            raise ValueError("appended_at_ms must be non-negative")
        table = _TABLE_BY_KIND[kind]
        self.initialize()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                f"""
                SELECT payload_json
                FROM {table}
                WHERE record_identity = ?
                """,
                (record_identity,),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_json"]) == payload_json:
                    return PaperLedgerWriteDisposition.UNCHANGED
                raise PaperLedgerConflictError(
                    f"immutable paper ledger conflict for {kind.value} identity"
                )

            index_existing = connection.execute(
                """
                SELECT record_kind
                FROM paper_replay_index
                WHERE record_identity = ?
                """,
                (record_identity,),
            ).fetchone()
            if index_existing is not None:
                raise PaperLedgerConflictError(
                    "immutable paper ledger identity already indexed under another kind"
                )

            connection.execute(
                f"""
                INSERT INTO {table} (
                    record_identity,
                    payload_json,
                    appended_at_ms
                ) VALUES (?, ?, ?)
                """,
                (record_identity, payload_json, appended_at_ms),
            )
            connection.execute(
                """
                INSERT INTO paper_replay_index (
                    record_kind,
                    record_identity,
                    appended_at_ms
                ) VALUES (?, ?, ?)
                """,
                (kind.value, record_identity, appended_at_ms),
            )
        return PaperLedgerWriteDisposition.INSERTED

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _install_immutability_triggers(connection: sqlite3.Connection) -> None:
        tables = [*_TABLE_BY_KIND.values(), "paper_replay_index"]
        for table in tables:
            connection.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS {table}_reject_update
                BEFORE UPDATE ON {table}
                BEGIN
                    SELECT RAISE(ABORT, 'immutable paper ledger rejects UPDATE');
                END
                """
            )
            connection.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS {table}_reject_delete
                BEFORE DELETE ON {table}
                BEGIN
                    SELECT RAISE(ABORT, 'immutable paper ledger rejects DELETE');
                END
                """
            )

def deserialize_paper_record(
    kind: PaperRecordKind,
    payload_json: str,
) -> PaperRecord:
    """Rebuild a typed paper record from canonical ledger JSON."""
    raw: dict[str, Any] = json.loads(payload_json)

    def decimal_or_none(value: Any) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value))

    def positions(value: Any) -> tuple[PaperPosition, ...]:
        return tuple(
            PaperPosition(
                symbol=PaperSymbol(str(item["symbol"])),
                quantity=Decimal(str(item["quantity"])),
            )
            for item in value
        )

    if kind is PaperRecordKind.FUND_CREATION:
        return FundCreationRecord(
            record_identity=str(raw["record_identity"]),
            created_at_ms=int(raw["created_at_ms"]),
            initial_cash_usdt=Decimal(str(raw["initial_cash_usdt"])),
            real_capital=int(raw["real_capital"]),
            positions=positions(raw["positions"]),
            schema_version=str(raw["schema_version"]),
            execution_policy_version=str(raw["execution_policy_version"]),
            risk_policy_version=str(raw["risk_policy_version"]),
            permitted_symbols=tuple(
                PaperSymbol(str(item)) for item in raw["permitted_symbols"]
            ),
            benchmark_ids=tuple(
                BenchmarkId(str(item)) for item in raw["benchmark_ids"]
            ),
        )
    if kind is PaperRecordKind.DECISION_INTENT:
        return DecisionIntentRecord(
            record_identity=str(raw["record_identity"]),
            fund_identity=str(raw["fund_identity"]),
            decided_at_ms=int(raw["decided_at_ms"]),
            action=PaperAction(str(raw["action"])),
            symbol=(
                None
                if raw["symbol"] is None
                else PaperSymbol(str(raw["symbol"]))
            ),
            quantity=decimal_or_none(raw["quantity"]),
            reference_price=decimal_or_none(raw["reference_price"]),
            reason=str(raw["reason"]),
            invalidation_context=str(raw["invalidation_context"]),
            schema_version=str(raw["schema_version"]),
            risk_policy_version=str(raw["risk_policy_version"]),
        )
    if kind is PaperRecordKind.SIMULATED_FILL:
        costs_raw = raw["costs"]
        return SimulatedFillRecord(
            record_identity=str(raw["record_identity"]),
            fund_identity=str(raw["fund_identity"]),
            decision_identity=str(raw["decision_identity"]),
            filled_at_ms=int(raw["filled_at_ms"]),
            action=PaperAction(str(raw["action"])),
            symbol=PaperSymbol(str(raw["symbol"])),
            quantity=Decimal(str(raw["quantity"])),
            reference_price=Decimal(str(raw["reference_price"])),
            simulated_fill_price=Decimal(str(raw["simulated_fill_price"])),
            costs=ExecutionCostAssumptions(
                fee_usdt=Decimal(str(costs_raw["fee_usdt"])),
                spread_usdt=Decimal(str(costs_raw["spread_usdt"])),
                slippage_usdt=Decimal(str(costs_raw["slippage_usdt"])),
                execution_policy_version=str(
                    costs_raw["execution_policy_version"]
                ),
                partial_fills_supported=bool(
                    costs_raw["partial_fills_supported"]
                ),
            ),
            venue_reference=str(raw["venue_reference"]),
            schema_version=str(raw["schema_version"]),
        )
    if kind is PaperRecordKind.POSITION_CASH_MUTATION:
        return PositionCashMutationRecord(
            record_identity=str(raw["record_identity"]),
            fund_identity=str(raw["fund_identity"]),
            source_identity=str(raw["source_identity"]),
            mutated_at_ms=int(raw["mutated_at_ms"]),
            cash_before_usdt=Decimal(str(raw["cash_before_usdt"])),
            cash_after_usdt=Decimal(str(raw["cash_after_usdt"])),
            positions_before=positions(raw["positions_before"]),
            positions_after=positions(raw["positions_after"]),
            schema_version=str(raw["schema_version"]),
        )
    if kind is PaperRecordKind.NAV_SNAPSHOT:
        return NavSnapshotRecord(
            record_identity=str(raw["record_identity"]),
            fund_identity=str(raw["fund_identity"]),
            snapshot_at_ms=int(raw["snapshot_at_ms"]),
            cash_usdt=Decimal(str(raw["cash_usdt"])),
            positions=positions(raw["positions"]),
            mark_prices=tuple(
                (
                    PaperSymbol(str(item[0])),
                    Decimal(str(item[1])),
                )
                for item in raw["mark_prices"]
            ),
            nav_usdt=Decimal(str(raw["nav_usdt"])),
            benchmark_ids=tuple(
                BenchmarkId(str(item)) for item in raw["benchmark_ids"]
            ),
            schema_version=str(raw["schema_version"]),
        )
    raise ValueError(f"unsupported paper record kind: {kind}")
