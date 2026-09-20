"""Bounded virtual-paper writer over the accepted dry-run decision chain.

The writer is local simulation only. It requires explicit append-only write
authority, never sends exchange/network orders, and keeps REAL_CAPITAL=0.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from crypto_signal.paper.activation import (
    PaperProcessedEventOutcome,
    build_processed_event_receipt,
    commit_planned_pretrade_event,
    record_terminal_no_action,
)
from crypto_signal.paper.autonomy import PaperAutonomyReason
from crypto_signal.paper.dry_run import (
    PaperActivationDryRunResult,
    PaperActivationDryRunStatus,
    evaluate_paper_activation_dry_run,
    read_paper_activation_read_only,
)
from crypto_signal.paper.event_scanner import scan_post_activation_signal_events
from crypto_signal.paper.ledger import (
    PaperFundLedger,
    PaperLedgerWriteDisposition,
)
from crypto_signal.paper.models import REAL_CAPITAL
from crypto_signal.paper.state import reconstruct_paper_fund_state
from crypto_signal.paper.write_authority import (
    PaperWriteAuthorityError,
    load_current_paper_write_authority,
)

__all__ = [
    "PAPER_WRITE_TICK_VERSION",
    "REAL_CAPITAL",
    "PaperWriteEventDisposition",
    "PaperWriteEventResult",
    "PaperWriteTickError",
    "PaperWriteTickResult",
    "run_paper_write_tick",
]

PAPER_WRITE_TICK_VERSION = "paper_write_tick.v1"


class PaperWriteTickError(RuntimeError):
    """Raised when an authorized virtual-paper write tick cannot reconcile truth."""


class PaperWriteEventDisposition(StrEnum):
    TERMINAL_NO_ACTION = "terminal_no_action"
    COMMITTED_TRADE = "committed_trade"
    RETRYABLE = "retryable"


@dataclass(frozen=True, slots=True)
class PaperWriteEventResult:
    event_identity: str
    status: PaperActivationDryRunStatus
    disposition: PaperWriteEventDisposition
    reason_code: str
    record_identities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_sha256(self.event_identity, "event identity")
        if not self.reason_code.strip():
            raise ValueError("write event reason_code must be non-empty")
        if self.disposition is PaperWriteEventDisposition.COMMITTED_TRADE:
            if len(self.record_identities) != 3:
                raise ValueError("committed trade must expose three record identities")
            for identity in self.record_identities:
                _require_sha256(identity, "committed record identity")
        elif self.record_identities:
            raise ValueError("non-trade writer result cannot carry trade records")


@dataclass(frozen=True, slots=True)
class PaperWriteTickResult:
    version: str
    authority_event_identity: str | None
    authority_enabled: bool
    evaluated_at_ms: int
    scanned_candidate_count: int
    event_results: tuple[PaperWriteEventResult, ...]
    processed_skip_count: int
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.version != PAPER_WRITE_TICK_VERSION:
            raise ValueError("unsupported paper write tick version")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.evaluated_at_ms < 0:
            raise ValueError("write tick evaluation time must be non-negative")
        if self.scanned_candidate_count < 0 or self.processed_skip_count < 0:
            raise ValueError("write tick counts cannot be negative")
        if self.authority_enabled:
            if self.authority_event_identity is None:
                raise ValueError("enabled write tick requires authority identity")
            _require_sha256(
                self.authority_event_identity,
                "authority event identity",
            )
        elif self.event_results:
            raise ValueError("disabled write tick cannot process events")
        if len(self.event_results) > self.scanned_candidate_count:
            raise ValueError("write tick results cannot exceed scanned candidates")

    @property
    def terminal_no_action_count(self) -> int:
        return sum(
            1
            for item in self.event_results
            if item.disposition is PaperWriteEventDisposition.TERMINAL_NO_ACTION
        )

    @property
    def committed_trade_count(self) -> int:
        return sum(
            1
            for item in self.event_results
            if item.disposition is PaperWriteEventDisposition.COMMITTED_TRADE
        )

    @property
    def retryable_count(self) -> int:
        return sum(
            1
            for item in self.event_results
            if item.disposition is PaperWriteEventDisposition.RETRYABLE
        )


_RETRYABLE_HOLD_REASONS = frozenset(
    {
        PaperAutonomyReason.FUTURE_SIGNAL,
        PaperAutonomyReason.COOLDOWN_ACTIVE,
        PaperAutonomyReason.MISSING_MARK_PRICE,
    }
)


def run_paper_write_tick(
    *,
    paper_ledger_path: Path,
    signal_ledger_path: Path,
    candle_cache_path: Path,
    evaluated_at_ms: int,
    max_events: int = 10,
) -> PaperWriteTickResult:
    """Evaluate and atomically persist bounded virtual-paper event outcomes."""
    if REAL_CAPITAL != 0:
        raise PaperWriteTickError("REAL_CAPITAL must remain 0")
    if evaluated_at_ms < 0:
        raise ValueError("evaluated_at_ms must be non-negative")
    if max_events <= 0:
        raise ValueError("max_events must be positive")

    ledger = PaperFundLedger(paper_ledger_path)
    authority = load_current_paper_write_authority(ledger)
    if authority is None or not authority.enabled:
        return PaperWriteTickResult(
            version=PAPER_WRITE_TICK_VERSION,
            authority_event_identity=(
                None if authority is None else authority.authority_event_identity
            ),
            authority_enabled=False,
            evaluated_at_ms=evaluated_at_ms,
            scanned_candidate_count=0,
            event_results=(),
            processed_skip_count=0,
            real_capital=REAL_CAPITAL,
        )

    activation = read_paper_activation_read_only(paper_ledger_path)
    if authority.activation_identity != activation.activation_identity:
        raise PaperWriteAuthorityError(
            "write authority does not match current paper activation"
        )
    scan = scan_post_activation_signal_events(
        signal_ledger_path=signal_ledger_path,
        paper_ledger_path=paper_ledger_path,
        activation=activation,
        observed_at_ms=evaluated_at_ms,
    )
    if len(scan.candidates) > max_events:
        raise PaperWriteTickError(
            "write tick candidate count exceeds bounded max_events"
        )

    results: list[PaperWriteEventResult] = []
    for event in scan.candidates:
        evaluated = evaluate_paper_activation_dry_run(
            event=event,
            activation=activation,
            paper_ledger_path=paper_ledger_path,
            candle_cache_path=candle_cache_path,
            evaluated_at_ms=evaluated_at_ms,
        )
        disposition = _write_evaluated_event(
            ledger=ledger,
            activation=activation,
            event=event,
            evaluated=evaluated,
            processed_at_ms=evaluated_at_ms,
        )
        results.append(disposition)

    return PaperWriteTickResult(
        version=PAPER_WRITE_TICK_VERSION,
        authority_event_identity=authority.authority_event_identity,
        authority_enabled=True,
        evaluated_at_ms=evaluated_at_ms,
        scanned_candidate_count=len(scan.candidates),
        event_results=tuple(results),
        processed_skip_count=scan.processed_skip_count,
        real_capital=REAL_CAPITAL,
    )


def _write_evaluated_event(
    *,
    ledger: PaperFundLedger,
    activation,
    event,
    evaluated: PaperActivationDryRunResult,
    processed_at_ms: int,
) -> PaperWriteEventResult:
    if evaluated.event_identity != event.event_identity:
        raise PaperWriteTickError("dry-run/event identity mismatch")

    if evaluated.status is PaperActivationDryRunStatus.PRETRADE_READY:
        if evaluated.execution_input is None or evaluated.venue_bound_pretrade is None:
            raise PaperWriteTickError("PRETRADE_READY lost execution lineage")
        state = reconstruct_paper_fund_state(ledger)
        committed = commit_planned_pretrade_event(
            ledger=ledger,
            state=state,
            activation=activation,
            pretrade=evaluated.venue_bound_pretrade.pretrade,
            execution_input=evaluated.execution_input,
            execution_snapshot=evaluated.venue_bound_pretrade.execution_snapshot,
        )
        return PaperWriteEventResult(
            event_identity=event.event_identity,
            status=evaluated.status,
            disposition=PaperWriteEventDisposition.COMMITTED_TRADE,
            reason_code=evaluated.autonomy.reason_code.value,
            record_identities=committed.receipt.record_identities,
        )

    if _is_retryable(evaluated):
        return PaperWriteEventResult(
            event_identity=event.event_identity,
            status=evaluated.status,
            disposition=PaperWriteEventDisposition.RETRYABLE,
            reason_code=_result_reason_code(evaluated),
        )

    state = reconstruct_paper_fund_state(ledger)
    receipt = build_processed_event_receipt(
        activation=activation,
        source_freeze_identities=event.source_freeze_identities,
        symbol=event.symbol,
        timeframe=event.timeframe,
        signal_as_of_ms=event.signal_as_of_ms,
        outcome=PaperProcessedEventOutcome.TERMINAL_NO_ACTION,
        processed_at_ms=processed_at_ms,
        terminal_reason=(
            f"paper_write_tick:{evaluated.status.value}:"
            f"{_result_reason_code(evaluated)}"
        ),
    )
    write = record_terminal_no_action(
        ledger=ledger,
        state=state,
        activation=activation,
        receipt=receipt,
    )
    if write not in {
        PaperLedgerWriteDisposition.INSERTED,
        PaperLedgerWriteDisposition.UNCHANGED,
    }:
        raise PaperWriteTickError("unexpected terminal no-action disposition")
    return PaperWriteEventResult(
        event_identity=event.event_identity,
        status=evaluated.status,
        disposition=PaperWriteEventDisposition.TERMINAL_NO_ACTION,
        reason_code=_result_reason_code(evaluated),
    )


def _is_retryable(result: PaperActivationDryRunResult) -> bool:
    if result.status in {
        PaperActivationDryRunStatus.WAITING_EXECUTION_INPUT,
        PaperActivationDryRunStatus.WAITING_VENUE_RULES,
    }:
        return True
    if result.status is PaperActivationDryRunStatus.HOLD_CASH:
        return result.autonomy.reason_code in _RETRYABLE_HOLD_REASONS
    return False


def _result_reason_code(result: PaperActivationDryRunResult) -> str:
    if result.status is PaperActivationDryRunStatus.SIZING_REJECTED:
        if result.sizing is None:
            raise PaperWriteTickError("sizing rejection lost sizing decision")
        return result.sizing.reason_code.value
    if result.status is PaperActivationDryRunStatus.PRETRADE_REJECTED:
        if result.venue_bound_pretrade is None:
            raise PaperWriteTickError("pretrade rejection lost pretrade decision")
        return result.venue_bound_pretrade.pretrade.reason_code.value
    return result.autonomy.reason_code.value


def summarize_write_tick_statuses(
    result: PaperWriteTickResult,
) -> tuple[tuple[str, int], ...]:
    counter = Counter(item.disposition.value for item in result.event_results)
    return tuple(sorted(counter.items()))


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
