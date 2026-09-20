"""Persistent activation watermark and terminal event receipts.

Activation state and processed-event receipts live in the same SQLite database
as the virtual paper ledger. They are immutable and insert-only. This module
does not activate PAPER/STABLE by itself and contains no signal selection,
network, exchange, credential, or real-order authority. It may compose only
already-accepted virtual simulation/atomic-ledger boundaries so a processed
trade receipt and its simulated paper mutation share one transaction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.paper.commit import (
    PaperBundleCommitError,
    commit_orchestration_bundle,
)
from crypto_signal.paper.execution import FrozenExecutionSnapshot
from crypto_signal.paper.execution_input import FrozenPaperExecutionInput
from crypto_signal.paper.ledger import (
    PaperFundLedger,
    PaperLedgerConflictError,
    PaperLedgerWriteAuthorityError,
    PaperLedgerWriteDisposition,
    PaperProcessedEventWrite,
)
from crypto_signal.paper.models import REAL_CAPITAL, PaperSymbol
from crypto_signal.paper.pipeline import (
    PaperTradePipelineResult,
    materialize_planned_pretrade,
)
from crypto_signal.paper.pretrade import PaperPretradeDecision
from crypto_signal.paper.state import PaperFundState, reconstruct_paper_fund_state

__all__ = [
    "PAPER_ACTIVATION_SCHEMA_VERSION",
    "REAL_CAPITAL",
    "PaperActivationError",
    "PaperActivationState",
    "PaperProcessedEventOutcome",
    "PaperProcessedEventReceipt",
    "PaperProcessedTradeCommit",
    "activate_paper_policy",
    "build_processed_event_receipt",
    "commit_planned_pretrade_event",
    "compute_activation_identity",
    "compute_processed_event_identity",
    "is_paper_event_processed",
    "list_processed_paper_events",
    "load_paper_activation",
    "record_terminal_no_action",
]

PAPER_ACTIVATION_SCHEMA_VERSION = "paper_activation_state.v1"


class PaperActivationError(ValueError):
    """Raised when persistent activation/event truth cannot be established safely."""


class PaperProcessedEventOutcome(StrEnum):
    TERMINAL_NO_ACTION = "terminal_no_action"
    COMMITTED_TRADE = "committed_trade"


@dataclass(frozen=True, slots=True)
class PaperActivationState:
    activation_identity: str
    schema_version: str
    fund_identity: str
    activated_at_ms: int
    activation_cutoff_ms: int
    baseline_signal_freeze_count: int
    baseline_latest_signal_freeze_identity: str | None
    baseline_latest_frozen_at_ms: int | None
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.schema_version != PAPER_ACTIVATION_SCHEMA_VERSION:
            raise ValueError("unsupported paper activation schema version")
        _require_sha256(self.activation_identity, "activation_identity")
        _require_sha256(self.fund_identity, "fund_identity")
        if self.activated_at_ms < 0:
            raise ValueError("activated_at_ms must be non-negative")
        if self.activation_cutoff_ms != self.activated_at_ms:
            raise ValueError("activation cutoff must equal activation timestamp in v1")
        if self.baseline_signal_freeze_count < 0:
            raise ValueError("baseline signal freeze count cannot be negative")
        if self.baseline_signal_freeze_count == 0:
            if (
                self.baseline_latest_signal_freeze_identity is not None
                or self.baseline_latest_frozen_at_ms is not None
            ):
                raise ValueError("empty baseline cannot expose latest freeze metadata")
        else:
            if (
                self.baseline_latest_signal_freeze_identity is None
                or self.baseline_latest_frozen_at_ms is None
            ):
                raise ValueError("non-empty baseline requires latest freeze metadata")
            _require_sha256(
                self.baseline_latest_signal_freeze_identity,
                "baseline latest signal freeze identity",
            )
            if self.baseline_latest_frozen_at_ms < 0:
                raise ValueError("baseline latest frozen_at_ms must be non-negative")
            if self.baseline_latest_frozen_at_ms > self.activated_at_ms:
                raise ValueError("baseline latest freeze cannot postdate activation")
        expected = compute_activation_identity(
            schema_version=self.schema_version,
            fund_identity=self.fund_identity,
            activated_at_ms=self.activated_at_ms,
            activation_cutoff_ms=self.activation_cutoff_ms,
            baseline_signal_freeze_count=self.baseline_signal_freeze_count,
            baseline_latest_signal_freeze_identity=(
                self.baseline_latest_signal_freeze_identity
            ),
            baseline_latest_frozen_at_ms=self.baseline_latest_frozen_at_ms,
        )
        if self.activation_identity != expected:
            raise ValueError("paper activation identity mismatch")


@dataclass(frozen=True, slots=True)
class PaperProcessedTradeCommit:
    receipt: PaperProcessedEventReceipt
    pipeline: PaperTradePipelineResult
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.receipt.outcome is not PaperProcessedEventOutcome.COMMITTED_TRADE:
            raise ValueError("processed trade result requires COMMITTED_TRADE receipt")
        if self.receipt.pretrade_identity != self.pipeline.pretrade_identity:
            raise ValueError("processed trade pretrade identity mismatch")
        if self.receipt.record_identities != self.pipeline.commit.record_identities:
            raise ValueError("processed trade record identity mismatch")
        if (
            self.pipeline.commit.processed_event_identity
            != self.receipt.event_identity
        ):
            raise ValueError("processed trade event identity mismatch")


@dataclass(frozen=True, slots=True)
class PaperProcessedEventReceipt:
    event_identity: str
    activation_identity: str
    source_freeze_identities: tuple[str, str]
    symbol: PaperSymbol
    timeframe: str
    signal_as_of_ms: int
    outcome: PaperProcessedEventOutcome
    processed_at_ms: int
    terminal_reason: str
    pretrade_identity: str | None = None
    record_identities: tuple[str, ...] = ()
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        _require_sha256(self.event_identity, "event_identity")
        _require_sha256(self.activation_identity, "activation_identity")
        if len(self.source_freeze_identities) != 2:
            raise ValueError("paper event requires exactly two source freeze identities")
        if len(set(self.source_freeze_identities)) != 2:
            raise ValueError("paper event source freeze identities must be unique")
        for identity in self.source_freeze_identities:
            _require_sha256(identity, "source freeze identity")
        if self.timeframe != "4h":
            raise ValueError("paper processed event v1 requires 4h timeframe")
        if self.signal_as_of_ms < 0 or self.processed_at_ms < 0:
            raise ValueError("paper event timestamps must be non-negative")
        if self.processed_at_ms < self.signal_as_of_ms:
            raise ValueError("processed event cannot predate signal as-of")
        if not self.terminal_reason.strip():
            raise ValueError("terminal_reason must be non-empty")
        if self.outcome is PaperProcessedEventOutcome.COMMITTED_TRADE:
            if self.pretrade_identity is None:
                raise ValueError("committed trade receipt requires pretrade identity")
            _require_sha256(self.pretrade_identity, "pretrade_identity")
            if len(self.record_identities) != 3:
                raise ValueError("committed trade receipt requires three record identities")
            for identity in self.record_identities:
                _require_sha256(identity, "committed record identity")
        else:
            if self.pretrade_identity is not None or self.record_identities:
                raise ValueError(
                    "terminal no-action receipt cannot carry trade record lineage"
                )
        expected = compute_processed_event_identity(
            activation_identity=self.activation_identity,
            source_freeze_identities=self.source_freeze_identities,
            symbol=self.symbol,
            timeframe=self.timeframe,
            signal_as_of_ms=self.signal_as_of_ms,
        )
        if self.event_identity != expected:
            raise ValueError("paper processed event identity mismatch")


def compute_activation_identity(
    *,
    schema_version: str,
    fund_identity: str,
    activated_at_ms: int,
    activation_cutoff_ms: int,
    baseline_signal_freeze_count: int,
    baseline_latest_signal_freeze_identity: str | None,
    baseline_latest_frozen_at_ms: int | None,
) -> str:
    return canonical_sha256(
        {
            "activated_at_ms": activated_at_ms,
            "activation_cutoff_ms": activation_cutoff_ms,
            "baseline_latest_frozen_at_ms": baseline_latest_frozen_at_ms,
            "baseline_latest_signal_freeze_identity": (
                baseline_latest_signal_freeze_identity
            ),
            "baseline_signal_freeze_count": baseline_signal_freeze_count,
            "fund_identity": fund_identity,
            "schema_version": schema_version,
        }
    )


def compute_processed_event_identity(
    *,
    activation_identity: str,
    source_freeze_identities: tuple[str, str],
    symbol: PaperSymbol,
    timeframe: str,
    signal_as_of_ms: int,
) -> str:
    canonical_sources = tuple(sorted(source_freeze_identities))
    return canonical_sha256(
        {
            "activation_identity": activation_identity,
            "signal_as_of_ms": signal_as_of_ms,
            "source_freeze_identities": list(canonical_sources),
            "symbol": symbol.value,
            "timeframe": timeframe,
        }
    )


def activate_paper_policy(
    *,
    ledger: PaperFundLedger,
    state: PaperFundState,
    activated_at_ms: int,
    baseline_signal_freeze_count: int,
    baseline_latest_signal_freeze_identity: str | None,
    baseline_latest_frozen_at_ms: int | None,
) -> tuple[PaperLedgerWriteDisposition, PaperActivationState]:
    if state.real_capital != REAL_CAPITAL:
        raise PaperActivationError("REAL_CAPITAL must remain 0")
    current = reconstruct_paper_fund_state(ledger)
    if current != state:
        raise PaperActivationError("paper activation requires current replay state")
    identity = compute_activation_identity(
        schema_version=PAPER_ACTIVATION_SCHEMA_VERSION,
        fund_identity=state.fund_identity,
        activated_at_ms=activated_at_ms,
        activation_cutoff_ms=activated_at_ms,
        baseline_signal_freeze_count=baseline_signal_freeze_count,
        baseline_latest_signal_freeze_identity=baseline_latest_signal_freeze_identity,
        baseline_latest_frozen_at_ms=baseline_latest_frozen_at_ms,
    )
    activation = PaperActivationState(
        activation_identity=identity,
        schema_version=PAPER_ACTIVATION_SCHEMA_VERSION,
        fund_identity=state.fund_identity,
        activated_at_ms=activated_at_ms,
        activation_cutoff_ms=activated_at_ms,
        baseline_signal_freeze_count=baseline_signal_freeze_count,
        baseline_latest_signal_freeze_identity=baseline_latest_signal_freeze_identity,
        baseline_latest_frozen_at_ms=baseline_latest_frozen_at_ms,
        real_capital=REAL_CAPITAL,
    )
    try:
        disposition = ledger._put_activation_state(
            activation_identity=activation.activation_identity,
            payload_json=canonical_json(activation),
            activated_at_ms=activation.activated_at_ms,
        )
    except PaperLedgerConflictError as exc:
        raise PaperActivationError(str(exc)) from exc
    return disposition, activation


def load_paper_activation(ledger: PaperFundLedger) -> PaperActivationState | None:
    row = ledger._get_activation_state_row()
    if row is None:
        return None
    identity, payload_json, activated_at_ms = row
    raw = json.loads(payload_json)
    activation = PaperActivationState(
        activation_identity=str(raw["activation_identity"]),
        schema_version=str(raw["schema_version"]),
        fund_identity=str(raw["fund_identity"]),
        activated_at_ms=int(raw["activated_at_ms"]),
        activation_cutoff_ms=int(raw["activation_cutoff_ms"]),
        baseline_signal_freeze_count=int(raw["baseline_signal_freeze_count"]),
        baseline_latest_signal_freeze_identity=(
            None
            if raw["baseline_latest_signal_freeze_identity"] is None
            else str(raw["baseline_latest_signal_freeze_identity"])
        ),
        baseline_latest_frozen_at_ms=(
            None
            if raw["baseline_latest_frozen_at_ms"] is None
            else int(raw["baseline_latest_frozen_at_ms"])
        ),
        real_capital=int(raw["real_capital"]),
    )
    if activation.activation_identity != identity:
        raise PaperActivationError("stored activation identity/payload mismatch")
    if activation.activated_at_ms != activated_at_ms:
        raise PaperActivationError("stored activation timestamp/payload mismatch")
    return activation


def build_processed_event_receipt(
    *,
    activation: PaperActivationState,
    source_freeze_identities: tuple[str, str],
    symbol: PaperSymbol,
    timeframe: str,
    signal_as_of_ms: int,
    outcome: PaperProcessedEventOutcome,
    processed_at_ms: int,
    terminal_reason: str,
    pretrade_identity: str | None = None,
    record_identities: tuple[str, ...] = (),
) -> PaperProcessedEventReceipt:
    if signal_as_of_ms < activation.activation_cutoff_ms:
        raise PaperActivationError(
            "paper event predates activation watermark and cannot be processed"
        )
    canonical_sources = tuple(sorted(source_freeze_identities))
    if len(canonical_sources) != 2:
        raise PaperActivationError("paper event requires exactly two source freezes")
    identity = compute_processed_event_identity(
        activation_identity=activation.activation_identity,
        source_freeze_identities=canonical_sources,
        symbol=symbol,
        timeframe=timeframe,
        signal_as_of_ms=signal_as_of_ms,
    )
    return PaperProcessedEventReceipt(
        event_identity=identity,
        activation_identity=activation.activation_identity,
        source_freeze_identities=(canonical_sources[0], canonical_sources[1]),
        symbol=symbol,
        timeframe=timeframe,
        signal_as_of_ms=signal_as_of_ms,
        outcome=outcome,
        processed_at_ms=processed_at_ms,
        terminal_reason=terminal_reason,
        pretrade_identity=pretrade_identity,
        record_identities=record_identities,
        real_capital=REAL_CAPITAL,
    )


def commit_planned_pretrade_event(
    *,
    ledger: PaperFundLedger,
    state: PaperFundState,
    activation: PaperActivationState,
    pretrade: PaperPretradeDecision,
    execution_input: FrozenPaperExecutionInput,
    execution_snapshot: FrozenExecutionSnapshot,
    required_authority_event_identity: str | None = None,
) -> PaperProcessedTradeCommit:
    """Atomically commit trade bundle and COMMITTED_TRADE receipt in one DB tx."""
    stored = load_paper_activation(ledger)
    if stored != activation:
        raise PaperActivationError("supplied activation does not match persistent state")
    if activation.fund_identity != state.fund_identity:
        raise PaperActivationError("activation fund identity mismatch")
    if pretrade.execution_input_identity != execution_input.input_identity:
        raise PaperActivationError("pretrade execution-input identity mismatch")
    if pretrade.symbol is not execution_input.symbol:
        raise PaperActivationError("pretrade execution-input symbol mismatch")
    if execution_input.signal_as_of_ms < activation.activation_cutoff_ms:
        raise PaperActivationError(
            "trade event predates activation watermark and cannot be committed"
        )

    bundle = materialize_planned_pretrade(
        state=state,
        pretrade=pretrade,
        execution_snapshot=execution_snapshot,
    )
    if bundle.fill is None or bundle.mutation is None:
        raise PaperActivationError("trade event materialization lost fill or mutation")
    record_identities = (
        bundle.decision.record_identity,
        bundle.fill.record_identity,
        bundle.mutation.record_identity,
    )
    plan = pretrade.plan
    if plan is None:
        raise PaperActivationError("PLANNED pretrade lost plan")
    source_freeze_identities = execution_input.source_freeze_identities
    if len(source_freeze_identities) != 2:
        raise PaperActivationError(
            "trade event requires exactly two source freeze identities"
        )
    source_pair = (source_freeze_identities[0], source_freeze_identities[1])
    receipt = build_processed_event_receipt(
        activation=activation,
        source_freeze_identities=source_pair,
        symbol=execution_input.symbol,
        timeframe="4h",
        signal_as_of_ms=execution_input.signal_as_of_ms,
        outcome=PaperProcessedEventOutcome.COMMITTED_TRADE,
        processed_at_ms=plan.planned_at_ms,
        terminal_reason="atomic paper trade committed",
        pretrade_identity=pretrade.pretrade_identity,
        record_identities=record_identities,
    )
    event_write = PaperProcessedEventWrite(
        event_identity=receipt.event_identity,
        activation_identity=receipt.activation_identity,
        outcome=receipt.outcome.value,
        payload_json=canonical_json(receipt),
        processed_at_ms=receipt.processed_at_ms,
    )
    try:
        committed = commit_orchestration_bundle(
            ledger=ledger,
            state=state,
            bundle=bundle,
            processed_event=event_write,
            required_authority_event_identity=required_authority_event_identity,
        )
    except PaperLedgerWriteAuthorityError:
        raise
    except (PaperBundleCommitError, PaperLedgerConflictError) as exc:
        raise PaperActivationError(str(exc)) from exc

    pipeline = PaperTradePipelineResult(
        pretrade_identity=pretrade.pretrade_identity,
        execution_snapshot_identity=execution_snapshot.snapshot_identity,
        bundle=bundle,
        commit=committed,
        real_capital=REAL_CAPITAL,
    )
    return PaperProcessedTradeCommit(
        receipt=receipt,
        pipeline=pipeline,
        real_capital=REAL_CAPITAL,
    )


def record_terminal_no_action(
    *,
    ledger: PaperFundLedger,
    state: PaperFundState,
    activation: PaperActivationState,
    receipt: PaperProcessedEventReceipt,
    required_authority_event_identity: str | None = None,
) -> PaperLedgerWriteDisposition:
    if receipt.outcome is not PaperProcessedEventOutcome.TERMINAL_NO_ACTION:
        raise PaperActivationError("no-action recorder requires TERMINAL_NO_ACTION")
    if receipt.activation_identity != activation.activation_identity:
        raise PaperActivationError("event receipt activation lineage mismatch")
    stored = load_paper_activation(ledger)
    if stored != activation:
        raise PaperActivationError("supplied activation does not match persistent state")
    try:
        disposition, _ = ledger._append_records_and_processed_event_atomic(
            (),
            expected_replayed_record_count=state.replayed_record_count,
            event_identity=receipt.event_identity,
            activation_identity=receipt.activation_identity,
            outcome=receipt.outcome.value,
            event_payload_json=canonical_json(receipt),
            processed_at_ms=receipt.processed_at_ms,
            required_authority_event_identity=required_authority_event_identity,
        )
    except PaperLedgerWriteAuthorityError:
        raise
    except PaperLedgerConflictError as exc:
        raise PaperActivationError(str(exc)) from exc
    return disposition


def is_paper_event_processed(
    ledger: PaperFundLedger,
    event_identity: str,
) -> bool:
    return ledger._get_processed_event_row(event_identity) is not None


def list_processed_paper_events(
    ledger: PaperFundLedger,
) -> tuple[PaperProcessedEventReceipt, ...]:
    receipts: list[PaperProcessedEventReceipt] = []
    for event_identity, activation_identity, outcome, payload_json, processed_at_ms in (
        ledger._list_processed_event_rows()
    ):
        raw = json.loads(payload_json)
        receipt = PaperProcessedEventReceipt(
            event_identity=str(raw["event_identity"]),
            activation_identity=str(raw["activation_identity"]),
            source_freeze_identities=(
                str(raw["source_freeze_identities"][0]),
                str(raw["source_freeze_identities"][1]),
            ),
            symbol=PaperSymbol(str(raw["symbol"])),
            timeframe=str(raw["timeframe"]),
            signal_as_of_ms=int(raw["signal_as_of_ms"]),
            outcome=PaperProcessedEventOutcome(str(raw["outcome"])),
            processed_at_ms=int(raw["processed_at_ms"]),
            terminal_reason=str(raw["terminal_reason"]),
            pretrade_identity=(
                None
                if raw["pretrade_identity"] is None
                else str(raw["pretrade_identity"])
            ),
            record_identities=tuple(str(item) for item in raw["record_identities"]),
            real_capital=int(raw["real_capital"]),
        )
        if (
            receipt.event_identity != event_identity
            or receipt.activation_identity != activation_identity
            or receipt.outcome.value != outcome
            or receipt.processed_at_ms != processed_at_ms
        ):
            raise PaperActivationError("stored processed event metadata mismatch")
        receipts.append(receipt)
    return tuple(receipts)


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
