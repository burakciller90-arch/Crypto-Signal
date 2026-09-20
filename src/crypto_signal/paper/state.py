"""Deterministic paper-fund state reconstruction from immutable ledger replay.

Simulation only. REAL_CAPITAL remains 0. Read-only over the ledger — never
appends, updates, or deletes records.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from crypto_signal.paper.ledger import (
    PaperFundLedger,
    PaperLedgerEntry,
    PaperRecordKind,
)
from crypto_signal.paper.models import (
    INITIAL_CASH_USDT,
    REAL_CAPITAL,
    DecisionIntentRecord,
    FundCreationRecord,
    NavSnapshotRecord,
    PaperPosition,
    PositionCashMutationRecord,
    SimulatedFillRecord,
    normalize_positions,
)

__all__ = [
    "REAL_CAPITAL",
    "PaperFundState",
    "PaperStateReconstructionError",
    "reconstruct_paper_fund_state",
    "reconstruct_paper_fund_state_from_entries",
]


class PaperStateReconstructionError(ValueError):
    """Raised when ledger lineage cannot reconstruct a coherent fund state."""


@dataclass(frozen=True, slots=True)
class PaperFundState:
    """Accounting state rebuilt from append-only paper-fund records."""

    fund_identity: str
    cash_usdt: Decimal
    positions: tuple[PaperPosition, ...]
    real_capital: int
    created_at_ms: int
    schema_version: str
    execution_policy_version: str
    risk_policy_version: str
    last_mutation_identity: str | None
    last_mutation_at_ms: int | None
    latest_nav_snapshot: NavSnapshotRecord | None
    replayed_record_count: int

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.cash_usdt < Decimal(0):
            raise ValueError("cash_usdt cannot be negative")
        if normalize_positions(self.positions) != self.positions:
            raise ValueError("positions must be normalized")
        for position in self.positions:
            if position.quantity < Decimal(0):
                raise ValueError("position quantity cannot be negative")


def reconstruct_paper_fund_state(ledger: PaperFundLedger) -> PaperFundState:
    """Rebuild current PaperFundState from ledger replay without mutating it."""
    return reconstruct_paper_fund_state_from_entries(ledger.replay())


def reconstruct_paper_fund_state_from_entries(
    entries: tuple[PaperLedgerEntry, ...],
) -> PaperFundState:
    """Rebuild state from an ordered replay tuple (read-only)."""
    if not entries:
        raise PaperStateReconstructionError(
            "empty ledger cannot reconstruct a paper fund"
        )

    first = entries[0]
    if first.record_kind is not PaperRecordKind.FUND_CREATION:
        raise PaperStateReconstructionError(
            "ledger must begin with exactly one fund creation record"
        )
    if not isinstance(first.record, FundCreationRecord):
        raise PaperStateReconstructionError("malformed fund creation record")

    creation = first.record
    if creation.initial_cash_usdt != INITIAL_CASH_USDT:
        raise PaperStateReconstructionError(
            "fund creation must start at exactly 100.00 USDT"
        )
    if creation.positions != ():
        raise PaperStateReconstructionError(
            "fund creation must start with zero positions"
        )
    if creation.real_capital != REAL_CAPITAL:
        raise PaperStateReconstructionError("REAL_CAPITAL must remain 0")

    fund_identity = creation.record_identity
    cash_usdt = INITIAL_CASH_USDT
    positions: tuple[PaperPosition, ...] = ()
    last_mutation_identity: str | None = None
    last_mutation_at_ms: int | None = None
    latest_nav_snapshot: NavSnapshotRecord | None = None

    decision_by_identity: dict[str, DecisionIntentRecord] = {}
    fill_identities: set[str] = set()
    seen_identities: set[str] = {fund_identity}
    previous_sequence_id = first.sequence_id

    for entry in entries[1:]:
        record = entry.record
        if entry.sequence_id <= previous_sequence_id:
            raise PaperStateReconstructionError(
                "replay sequence_id must be strictly increasing"
            )
        previous_sequence_id = entry.sequence_id
        if entry.record_identity != record.record_identity:
            raise PaperStateReconstructionError(
                "replay entry identity does not match typed record identity"
            )
        expected_kind = {
            FundCreationRecord: PaperRecordKind.FUND_CREATION,
            DecisionIntentRecord: PaperRecordKind.DECISION_INTENT,
            SimulatedFillRecord: PaperRecordKind.SIMULATED_FILL,
            PositionCashMutationRecord: PaperRecordKind.POSITION_CASH_MUTATION,
            NavSnapshotRecord: PaperRecordKind.NAV_SNAPSHOT,
        }.get(type(record))
        if expected_kind is None or entry.record_kind is not expected_kind:
            raise PaperStateReconstructionError(
                "replay record kind does not match typed record"
            )

        if entry.record_identity in seen_identities:
            raise PaperStateReconstructionError(
                f"duplicate record identity in replay: {entry.record_identity}"
            )
        seen_identities.add(entry.record_identity)

        if isinstance(record, FundCreationRecord):
            raise PaperStateReconstructionError(
                "exactly one fund creation identity is permitted per reconstructed fund"
            )

        if isinstance(record, DecisionIntentRecord):
            if record.fund_identity != fund_identity:
                raise PaperStateReconstructionError(
                    "cross-fund decision lineage rejected"
                )
            decision_by_identity[record.record_identity] = record
            continue

        if isinstance(record, SimulatedFillRecord):
            if record.fund_identity != fund_identity:
                raise PaperStateReconstructionError(
                    "cross-fund fill lineage rejected"
                )
            source_decision = decision_by_identity.get(record.decision_identity)
            if source_decision is None:
                raise PaperStateReconstructionError(
                    "fill source decision is missing, wrong type, or out of order"
                )
            if (
                source_decision.action is not record.action
                or source_decision.symbol is not record.symbol
                or source_decision.quantity != record.quantity
                or source_decision.reference_price != record.reference_price
            ):
                raise PaperStateReconstructionError(
                    "fill does not match its source decision intent"
                )
            fill_identities.add(record.record_identity)
            continue

        if isinstance(record, PositionCashMutationRecord):
            cash_usdt, positions, last_mutation_identity, last_mutation_at_ms = (
                _apply_mutation(
                    record=record,
                    fund_identity=fund_identity,
                    cash_usdt=cash_usdt,
                    positions=positions,
                    known_source_identities=set(decision_by_identity) | fill_identities,
                )
            )
            continue

        if isinstance(record, NavSnapshotRecord):
            if record.fund_identity != fund_identity:
                raise PaperStateReconstructionError(
                    "cross-fund NAV snapshot lineage rejected"
                )
            if record.cash_usdt != cash_usdt:
                raise PaperStateReconstructionError(
                    "NAV snapshot cash does not match reconstructed accounting state"
                )
            if record.positions != positions:
                raise PaperStateReconstructionError(
                    "NAV snapshot positions do not match reconstructed accounting state"
                )
            latest_nav_snapshot = record
            continue

        raise PaperStateReconstructionError(
            f"unsupported or malformed paper record kind: {entry.record_kind}"
        )

    return PaperFundState(
        fund_identity=fund_identity,
        cash_usdt=cash_usdt,
        positions=positions,
        real_capital=REAL_CAPITAL,
        created_at_ms=creation.created_at_ms,
        schema_version=creation.schema_version,
        execution_policy_version=creation.execution_policy_version,
        risk_policy_version=creation.risk_policy_version,
        last_mutation_identity=last_mutation_identity,
        last_mutation_at_ms=last_mutation_at_ms,
        latest_nav_snapshot=latest_nav_snapshot,
        replayed_record_count=len(entries),
    )


def _apply_mutation(
    *,
    record: PositionCashMutationRecord,
    fund_identity: str,
    cash_usdt: Decimal,
    positions: tuple[PaperPosition, ...],
    known_source_identities: set[str],
) -> tuple[Decimal, tuple[PaperPosition, ...], str, int]:
    if record.fund_identity != fund_identity:
        raise PaperStateReconstructionError(
            "cross-fund mutation lineage rejected"
        )
    if record.source_identity not in known_source_identities:
        raise PaperStateReconstructionError(
            "mutation source identity is missing, out of order, or cross-fund"
        )
    if record.cash_before_usdt != cash_usdt:
        raise PaperStateReconstructionError(
            "discontinuous cash lineage: cash_before does not equal prior state"
        )
    if record.positions_before != positions:
        raise PaperStateReconstructionError(
            "discontinuous position lineage: positions_before do not equal prior state"
        )
    if record.cash_after_usdt < Decimal(0):
        raise PaperStateReconstructionError(
            "mutation would produce negative cash state"
        )
    for position in record.positions_after:
        if position.quantity < Decimal(0):
            raise PaperStateReconstructionError(
                "mutation would produce negative position state"
            )
    if normalize_positions(record.positions_after) != record.positions_after:
        raise PaperStateReconstructionError(
            "mutation positions_after must be normalized"
        )
    return (
        record.cash_after_usdt,
        record.positions_after,
        record.record_identity,
        record.mutated_at_ms,
    )
