"""Explicit, append-only authority for virtual paper-ledger writes.

This authority can only enable/disable simulated paper mutations inside the
local paper SQLite ledger. It never grants real-capital, credential, network,
or exchange-order authority. REAL_CAPITAL remains 0.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.paper.activation import (
    PaperActivationState,
    load_paper_activation,
)
from crypto_signal.paper.ledger import (
    PaperFundLedger,
    PaperLedgerConflictError,
    PaperLedgerWriteDisposition,
)
from crypto_signal.paper.models import REAL_CAPITAL

__all__ = [
    "PAPER_WRITE_AUTHORITY_VERSION",
    "REAL_CAPITAL",
    "PaperWriteAuthorityError",
    "PaperWriteAuthorityEvent",
    "append_paper_write_authority_event",
    "list_paper_write_authority_events",
    "load_current_paper_write_authority",
]

PAPER_WRITE_AUTHORITY_VERSION = "paper_write_authority.v1"


class PaperWriteAuthorityError(ValueError):
    """Raised when virtual-paper write authority truth cannot be reconciled."""


@dataclass(frozen=True, slots=True)
class PaperWriteAuthorityEvent:
    authority_event_identity: str
    version: str
    activation_identity: str
    enabled: bool
    created_at_ms: int
    previous_event_identity: str | None
    reason: str
    reviewed_event_identities: tuple[str, ...]
    reviewed_trace_identities: tuple[str, ...]
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.version != PAPER_WRITE_AUTHORITY_VERSION:
            raise ValueError("unsupported paper write authority version")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        _require_sha256(
            self.authority_event_identity,
            "authority_event_identity",
        )
        _require_sha256(self.activation_identity, "activation_identity")
        if self.created_at_ms < 0:
            raise ValueError("authority created_at_ms must be non-negative")
        if self.previous_event_identity is not None:
            _require_sha256(
                self.previous_event_identity,
                "previous_event_identity",
            )
        if not self.reason.strip():
            raise ValueError("authority reason must be non-empty")
        if (
            len(set(self.reviewed_event_identities))
            != len(self.reviewed_event_identities)
        ):
            raise ValueError("reviewed event identities must be unique")
        if (
            len(set(self.reviewed_trace_identities))
            != len(self.reviewed_trace_identities)
        ):
            raise ValueError("reviewed trace identities must be unique")
        for identity in self.reviewed_event_identities:
            _require_sha256(identity, "reviewed event identity")
        for identity in self.reviewed_trace_identities:
            _require_sha256(identity, "reviewed trace identity")
        if self.enabled:
            if not self.reviewed_event_identities:
                raise ValueError(
                    "enabling virtual writes requires reviewed production events"
                )
            if len(self.reviewed_event_identities) != len(
                self.reviewed_trace_identities
            ):
                raise ValueError(
                    "reviewed event/trace evidence must have equal cardinality"
                )
        elif self.reviewed_event_identities or self.reviewed_trace_identities:
            raise ValueError(
                "disable event cannot carry reviewed activation evidence"
            )

        expected = compute_paper_write_authority_identity(
            version=self.version,
            activation_identity=self.activation_identity,
            enabled=self.enabled,
            created_at_ms=self.created_at_ms,
            previous_event_identity=self.previous_event_identity,
            reason=self.reason,
            reviewed_event_identities=self.reviewed_event_identities,
            reviewed_trace_identities=self.reviewed_trace_identities,
        )
        if self.authority_event_identity != expected:
            raise ValueError("paper write authority identity mismatch")


def compute_paper_write_authority_identity(
    *,
    version: str,
    activation_identity: str,
    enabled: bool,
    created_at_ms: int,
    previous_event_identity: str | None,
    reason: str,
    reviewed_event_identities: tuple[str, ...],
    reviewed_trace_identities: tuple[str, ...],
) -> str:
    return canonical_sha256(
        {
            "activation_identity": activation_identity,
            "created_at_ms": created_at_ms,
            "enabled": enabled,
            "previous_event_identity": previous_event_identity,
            "reason": reason,
            "reviewed_event_identities": list(reviewed_event_identities),
            "reviewed_trace_identities": list(reviewed_trace_identities),
            "version": version,
        }
    )


def append_paper_write_authority_event(
    *,
    ledger: PaperFundLedger,
    activation: PaperActivationState,
    enabled: bool,
    created_at_ms: int,
    reason: str,
    reviewed_event_identities: tuple[str, ...] = (),
    reviewed_trace_identities: tuple[str, ...] = (),
) -> tuple[PaperLedgerWriteDisposition, PaperWriteAuthorityEvent]:
    """Append one revocable virtual-write authority state transition."""
    if activation.real_capital != REAL_CAPITAL:
        raise PaperWriteAuthorityError("REAL_CAPITAL must remain 0")
    stored_activation = load_paper_activation(ledger)
    if stored_activation != activation:
        raise PaperWriteAuthorityError(
            "write authority requires exact persistent activation"
        )
    previous = load_current_paper_write_authority(ledger)
    previous_identity = (
        None if previous is None else previous.authority_event_identity
    )
    event_identity = compute_paper_write_authority_identity(
        version=PAPER_WRITE_AUTHORITY_VERSION,
        activation_identity=activation.activation_identity,
        enabled=enabled,
        created_at_ms=created_at_ms,
        previous_event_identity=previous_identity,
        reason=reason,
        reviewed_event_identities=reviewed_event_identities,
        reviewed_trace_identities=reviewed_trace_identities,
    )
    event = PaperWriteAuthorityEvent(
        authority_event_identity=event_identity,
        version=PAPER_WRITE_AUTHORITY_VERSION,
        activation_identity=activation.activation_identity,
        enabled=enabled,
        created_at_ms=created_at_ms,
        previous_event_identity=previous_identity,
        reason=reason,
        reviewed_event_identities=reviewed_event_identities,
        reviewed_trace_identities=reviewed_trace_identities,
        real_capital=REAL_CAPITAL,
    )
    try:
        disposition = ledger._append_write_authority_event(
            authority_event_identity=event.authority_event_identity,
            activation_identity=event.activation_identity,
            enabled=event.enabled,
            previous_event_identity=event.previous_event_identity,
            payload_json=canonical_json(event),
            created_at_ms=event.created_at_ms,
        )
    except PaperLedgerConflictError as exc:
        raise PaperWriteAuthorityError(str(exc)) from exc
    return disposition, event


def load_current_paper_write_authority(
    ledger: PaperFundLedger,
) -> PaperWriteAuthorityEvent | None:
    events = list_paper_write_authority_events(ledger)
    if not events:
        return None
    return events[-1]


def list_paper_write_authority_events(
    ledger: PaperFundLedger,
) -> tuple[PaperWriteAuthorityEvent, ...]:
    result: list[PaperWriteAuthorityEvent] = []
    previous: str | None = None
    for (
        sequence_id,
        event_identity,
        activation_identity,
        enabled,
        previous_event_identity,
        payload_json,
        created_at_ms,
    ) in ledger._list_write_authority_rows():
        if sequence_id <= 0:
            raise PaperWriteAuthorityError(
                "write-authority sequence must be positive"
            )
        event = _deserialize_authority_event(payload_json)
        if (
            event.authority_event_identity != event_identity
            or event.activation_identity != activation_identity
            or event.enabled is not enabled
            or event.previous_event_identity != previous_event_identity
            or event.created_at_ms != created_at_ms
        ):
            raise PaperWriteAuthorityError(
                "stored write-authority metadata/payload mismatch"
            )
        if event.previous_event_identity != previous:
            raise PaperWriteAuthorityError(
                "write-authority event chain is discontinuous"
            )
        result.append(event)
        previous = event.authority_event_identity
    return tuple(result)


def _deserialize_authority_event(payload_json: str) -> PaperWriteAuthorityEvent:
    try:
        raw = json.loads(payload_json)
        if not isinstance(raw, dict):
            raise TypeError("authority payload must be an object")
        return PaperWriteAuthorityEvent(
            authority_event_identity=str(raw["authority_event_identity"]),
            version=str(raw["version"]),
            activation_identity=str(raw["activation_identity"]),
            enabled=bool(raw["enabled"]),
            created_at_ms=int(raw["created_at_ms"]),
            previous_event_identity=(
                None
                if raw["previous_event_identity"] is None
                else str(raw["previous_event_identity"])
            ),
            reason=str(raw["reason"]),
            reviewed_event_identities=tuple(
                str(item) for item in raw["reviewed_event_identities"]
            ),
            reviewed_trace_identities=tuple(
                str(item) for item in raw["reviewed_trace_identities"]
            ),
            real_capital=int(raw["real_capital"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PaperWriteAuthorityError(
            "persistent write-authority payload is invalid"
        ) from exc


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
