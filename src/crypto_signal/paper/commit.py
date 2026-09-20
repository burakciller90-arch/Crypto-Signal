"""Atomic persistence boundary for accepted paper orchestration bundles.

Simulation only. REAL_CAPITAL remains 0. This module has no exchange, network,
credential, or real-order authority.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from crypto_signal.paper.ledger import (
    PaperFundLedger,
    PaperLedgerEntry,
    PaperLedgerWriteDisposition,
    PaperProcessedEventWrite,
    PaperRecord,
)
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction
from crypto_signal.paper.orchestration import PaperOrchestrationBundle
from crypto_signal.paper.state import (
    PaperFundState,
    reconstruct_paper_fund_state,
    reconstruct_paper_fund_state_from_entries,
)

__all__ = [
    "REAL_CAPITAL",
    "PaperBundleCommitError",
    "PaperBundleCommitResult",
    "commit_orchestration_bundle",
]


class PaperBundleCommitError(ValueError):
    """Raised when an orchestration bundle cannot be safely persisted."""


@dataclass(frozen=True, slots=True)
class PaperBundleCommitResult:
    """Result of one atomic/idempotent paper-bundle commit attempt."""

    disposition: PaperLedgerWriteDisposition
    record_identities: tuple[str, ...]
    state_after: PaperFundState
    processed_event_identity: str | None = None
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.processed_event_identity is not None:
            if len(self.processed_event_identity) != 64 or any(
                ch not in "0123456789abcdef"
                for ch in self.processed_event_identity
            ):
                raise ValueError("processed_event_identity must be SHA256")


def commit_orchestration_bundle(
    *,
    ledger: PaperFundLedger,
    state: PaperFundState,
    bundle: PaperOrchestrationBundle,
    processed_event: PaperProcessedEventWrite | None = None,
) -> PaperBundleCommitResult:
    """Persist one accepted orchestration bundle atomically, then re-read state."""
    records = _bundle_records(state=state, bundle=bundle)
    identities = tuple(record.record_identity for record in records)

    existing = tuple(ledger.get_by_identity(identity) for identity in identities)
    if not any(item is not None for item in existing):
        current = reconstruct_paper_fund_state(ledger)
        if current != state:
            raise PaperBundleCommitError(
                "supplied paper fund state is stale or does not match ledger replay"
            )

    if processed_event is None:
        disposition, replay = ledger._append_records_atomic(
            records,
            expected_replayed_record_count=state.replayed_record_count,
        )
    else:
        if bundle.decision.action is PaperAction.HOLD_CASH:
            raise PaperBundleCommitError(
                "processed trade event cannot bind a HOLD_CASH bundle"
            )
        if processed_event.outcome != "committed_trade":
            raise PaperBundleCommitError(
                "trade bundle processed event outcome must be committed_trade"
            )
        latest_bundle_time = bundle.decision.decided_at_ms
        if bundle.fill is not None:
            latest_bundle_time = max(latest_bundle_time, bundle.fill.filled_at_ms)
        if bundle.mutation is not None:
            latest_bundle_time = max(
                latest_bundle_time,
                bundle.mutation.mutated_at_ms,
            )
        if processed_event.processed_at_ms < latest_bundle_time:
            raise PaperBundleCommitError(
                "processed trade event cannot predate committed bundle"
            )
        disposition, replay = ledger._append_records_and_processed_event_atomic(
            records,
            expected_replayed_record_count=state.replayed_record_count,
            event_identity=processed_event.event_identity,
            activation_identity=processed_event.activation_identity,
            outcome=processed_event.outcome,
            event_payload_json=processed_event.payload_json,
            processed_at_ms=processed_event.processed_at_ms,
        )
    _validate_bundle_replay_order(replay=replay, identities=identities)

    state_after = reconstruct_paper_fund_state_from_entries(replay)
    if disposition is PaperLedgerWriteDisposition.INSERTED:
        _validate_inserted_state(
            state=state,
            bundle=bundle,
            record_count=len(records),
            state_after=state_after,
        )

    return PaperBundleCommitResult(
        disposition=disposition,
        record_identities=identities,
        state_after=state_after,
        processed_event_identity=(
            None if processed_event is None else processed_event.event_identity
        ),
        real_capital=REAL_CAPITAL,
    )


def _bundle_records(
    *,
    state: PaperFundState,
    bundle: PaperOrchestrationBundle,
) -> tuple[PaperRecord, ...]:
    if state.real_capital != REAL_CAPITAL or bundle.real_capital != REAL_CAPITAL:
        raise PaperBundleCommitError("REAL_CAPITAL must remain 0")
    if bundle.decision.fund_identity != state.fund_identity:
        raise PaperBundleCommitError("bundle decision fund identity mismatch")
    if bundle.decision.risk_policy_version != state.risk_policy_version:
        raise PaperBundleCommitError("bundle decision risk policy mismatch")

    if bundle.decision.action is PaperAction.HOLD_CASH:
        if bundle.fill is not None or bundle.mutation is not None:
            raise PaperBundleCommitError(
                "HOLD_CASH commit cannot contain fill or mutation"
            )
        return (bundle.decision,)

    if bundle.fill is None or bundle.mutation is None:
        raise PaperBundleCommitError("trade commit requires fill and mutation")
    if bundle.fill.fund_identity != state.fund_identity:
        raise PaperBundleCommitError("bundle fill fund identity mismatch")
    if bundle.mutation.fund_identity != state.fund_identity:
        raise PaperBundleCommitError("bundle mutation fund identity mismatch")
    if bundle.fill.costs.execution_policy_version != state.execution_policy_version:
        raise PaperBundleCommitError("bundle execution policy mismatch")
    if bundle.mutation.cash_before_usdt != state.cash_usdt:
        raise PaperBundleCommitError("bundle mutation cash_before is stale")
    if bundle.mutation.positions_before != state.positions:
        raise PaperBundleCommitError("bundle mutation positions_before are stale")
    return (bundle.decision, bundle.fill, bundle.mutation)


def _validate_bundle_replay_order(
    *,
    replay: tuple[PaperLedgerEntry, ...],
    identities: tuple[str, ...],
) -> None:
    index_by_identity = {
        entry.record_identity: index for index, entry in enumerate(replay)
    }
    try:
        positions = tuple(index_by_identity[identity] for identity in identities)
    except KeyError as exc:
        raise PaperBundleCommitError(
            "committed bundle identity missing from replay"
        ) from exc
    expected = tuple(range(positions[0], positions[0] + len(positions)))
    if positions != expected:
        raise PaperBundleCommitError(
            "committed bundle records are not contiguous in replay order"
        )


def _validate_inserted_state(
    *,
    state: PaperFundState,
    bundle: PaperOrchestrationBundle,
    record_count: int,
    state_after: PaperFundState,
) -> None:
    if bundle.decision.action is PaperAction.HOLD_CASH:
        expected = replace(
            state,
            replayed_record_count=state.replayed_record_count + record_count,
        )
    else:
        mutation = bundle.mutation
        if mutation is None:
            raise PaperBundleCommitError("trade commit lost mutation")
        expected = replace(
            state,
            cash_usdt=mutation.cash_after_usdt,
            positions=mutation.positions_after,
            last_mutation_identity=mutation.record_identity,
            last_mutation_at_ms=mutation.mutated_at_ms,
            replayed_record_count=state.replayed_record_count + record_count,
        )
    if state_after != expected:
        raise PaperBundleCommitError(
            "post-commit replay state does not match accepted bundle"
        )
