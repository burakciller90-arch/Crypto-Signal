"""Persistent activation watermark and terminal event receipts.

Activation state and processed-event receipts live in the same SQLite database
as the virtual paper ledger. They are immutable and insert-only. This module
does not activate PAPER/STABLE by itself and contains no signal selection,
network, exchange, credential, fill, or real-order authority.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.paper.ledger import (
    PaperFundLedger,
    PaperLedgerConflictError,
    PaperLedgerWriteDisposition,
)
from crypto_signal.paper.models import REAL_CAPITAL, PaperSymbol
from crypto_signal.paper.state import PaperFundState, reconstruct_paper_fund_state

__all__ = [
    "PAPER_ACTIVATION_SCHEMA_VERSION",
    "REAL_CAPITAL",
    "PaperActivationError",
    "PaperActivationState",
    "PaperProcessedEventOutcome",
    "PaperProcessedEventReceipt",
    "activate_paper_policy",
    "build_processed_event_receipt",
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


def record_terminal_no_action(
    *,
    ledger: PaperFundLedger,
    state: PaperFundState,
    activation: PaperActivationState,
    receipt: PaperProcessedEventReceipt,
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
        )
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
