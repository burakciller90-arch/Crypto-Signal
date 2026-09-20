from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.confluence.models import ScoreSemantic
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.signals.models import (
    ProbabilityStatus,
    SignalDirection,
    SignalState,
)

ALERT_SCHEMA_VERSION = "alert-v1/1"


class AlertSourceKind(StrEnum):
    INITIAL_SIGNAL = "initial_signal"
    LIFECYCLE_TRANSITION = "lifecycle_transition"


class DeliveryAttemptStatus(StrEnum):
    DELIVERED = "delivered"
    RETRYABLE_FAILURE = "retryable_failure"
    PERMANENT_FAILURE = "permanent_failure"


@dataclass(frozen=True, slots=True)
class AlertPolicy:
    version: str
    initial_states: tuple[SignalState, ...]
    transition_states: tuple[SignalState, ...]

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("alert policy version must be non-empty")
        if len(set(self.initial_states)) != len(self.initial_states):
            raise ValueError("alert policy initial states must be unique")
        if len(set(self.transition_states)) != len(self.transition_states):
            raise ValueError("alert policy transition states must be unique")
        if SignalState.INVALIDATED in self.initial_states:
            raise ValueError(
                "initial alert policy cannot contain INVALIDATED"
            )
        if any(
            state is not SignalState.INVALIDATED
            for state in self.transition_states
        ):
            raise ValueError(
                "V1 transition alert policy only supports INVALIDATED"
            )

    @classmethod
    def default_v1(cls) -> AlertPolicy:
        return cls(
            version="alerts-v1-default/1",
            initial_states=(SignalState.ACTIVE,),
            transition_states=(SignalState.INVALIDATED,),
        )


@dataclass(frozen=True, slots=True)
class AlertEvent:
    event_identity: str
    schema_version: str
    policy_version: str
    source_kind: AlertSourceKind
    signal_freeze_identity: str
    lifecycle_evaluation_identity: str | None
    transition_identity: str | None
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    signal_state: SignalState
    direction: SignalDirection
    setup_type: str
    decision_as_of_ms: int
    source_evaluated_as_of_ms: int
    confluence_score: Decimal
    confluence_score_semantic: ScoreSemantic
    probability_status: ProbabilityStatus
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.event_identity, "alert event identity")
        _require_sha256(
            self.signal_freeze_identity,
            "alert signal freeze identity",
        )
        if self.schema_version != ALERT_SCHEMA_VERSION:
            raise ValueError("unsupported alert schema version")
        if not self.policy_version.strip():
            raise ValueError("alert policy version must be non-empty")
        if not self.symbol.strip() or not self.timeframe.strip():
            raise ValueError("alert market identity must be non-empty")
        if not self.setup_type.strip():
            raise ValueError("alert setup type must be non-empty")
        if self.decision_as_of_ms < 0 or self.source_evaluated_as_of_ms < 0:
            raise ValueError("alert timestamps must be non-negative")
        if self.source_evaluated_as_of_ms < self.decision_as_of_ms:
            raise ValueError(
                "alert source evaluation cannot precede signal decision"
            )
        if not Decimal(0) <= self.confluence_score <= Decimal(100):
            raise ValueError("alert confluence score must be 0..100")
        if len(set(self.uncertainty_flags)) != len(self.uncertainty_flags):
            raise ValueError("alert uncertainty flags must be unique")

        if self.source_kind is AlertSourceKind.INITIAL_SIGNAL:
            if self.lifecycle_evaluation_identity is not None:
                raise ValueError(
                    "initial alert cannot reference lifecycle evaluation"
                )
            if self.transition_identity is not None:
                raise ValueError(
                    "initial alert cannot reference lifecycle transition"
                )
            if self.signal_state is SignalState.INVALIDATED:
                raise ValueError(
                    "initial alert cannot start as INVALIDATED"
                )
        else:
            if self.lifecycle_evaluation_identity is None:
                raise ValueError(
                    "lifecycle alert requires evaluation identity"
                )
            _require_sha256(
                self.lifecycle_evaluation_identity,
                "lifecycle evaluation identity",
            )
            if self.transition_identity is None:
                raise ValueError(
                    "lifecycle alert requires transition identity"
                )
            _require_sha256(
                self.transition_identity,
                "lifecycle transition identity",
            )
            if self.signal_state is not SignalState.INVALIDATED:
                raise ValueError(
                    "V1 lifecycle alert must represent INVALIDATED"
                )


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    status: DeliveryAttemptStatus
    receipt: str | None = None
    error_code: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        if self.status is DeliveryAttemptStatus.DELIVERED:
            if self.receipt is None or not self.receipt.strip():
                raise ValueError(
                    "delivered alert result requires receipt"
                )
            if self.error_code is not None or self.error_message is not None:
                raise ValueError(
                    "delivered alert result cannot carry error"
                )
        else:
            if self.receipt is not None:
                raise ValueError(
                    "failed alert result cannot carry receipt"
                )
            if self.error_code is None or not self.error_code.strip():
                raise ValueError(
                    "failed alert result requires error code"
                )
            if self.error_message is None or not self.error_message.strip():
                raise ValueError(
                    "failed alert result requires error message"
                )


@dataclass(frozen=True, slots=True)
class AlertDeliveryAttempt:
    attempt_identity: str
    event_identity: str
    sink_id: str
    attempt_number: int
    attempted_at_ms: int
    status: DeliveryAttemptStatus
    receipt: str | None
    error_code: str | None
    error_message: str | None

    def __post_init__(self) -> None:
        _require_sha256(self.attempt_identity, "alert attempt identity")
        _require_sha256(self.event_identity, "alert event identity")
        if not self.sink_id.strip():
            raise ValueError("alert sink id must be non-empty")
        if self.attempt_number <= 0:
            raise ValueError("alert attempt number must be positive")
        if self.attempted_at_ms < 0:
            raise ValueError("alert attempt time must be non-negative")
        DeliveryResult(
            status=self.status,
            receipt=self.receipt,
            error_code=self.error_code,
            error_message=self.error_message,
        )


@dataclass(frozen=True, slots=True)
class AlertDeliveryState:
    event_identity: str
    sink_id: str
    attempts: int
    terminal: bool
    delivered: bool
    latest_status: DeliveryAttemptStatus | None
    latest_receipt: str | None

    def __post_init__(self) -> None:
        _require_sha256(self.event_identity, "alert event identity")
        if not self.sink_id.strip():
            raise ValueError("alert sink id must be non-empty")
        if self.attempts < 0:
            raise ValueError("alert attempt count must be non-negative")
        if self.delivered and not self.terminal:
            raise ValueError("delivered alert state must be terminal")
        if self.attempts == 0:
            if self.latest_status is not None or self.latest_receipt is not None:
                raise ValueError(
                    "undelivered alert with zero attempts has no latest result"
                )
        elif self.latest_status is None:
            raise ValueError(
                "alert state with attempts requires latest status"
            )


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64:
        raise ValueError(f"{label} must be SHA256")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be hexadecimal") from exc
