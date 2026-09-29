"""FP4-A deterministic depth-aware paper execution.

Consumes only caller-supplied immutable Market Tape order-book truth. The module
does not read the network, mutate R21/R22, or place real orders. REAL_CAPITAL=0.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.microstructure import OrderBookSnapshot
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction

FP4_DEPTH_EXECUTION_POLICY_VERSION = "paper_execution_depth.v2"


class DepthExecutionRejectedError(ValueError):
    """Raised when depth-aware paper execution cannot be proven safely."""


class DepthExecutionStatus(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    NOT_FILLED = "not_filled"
    FILL_NOT_PROVEN = "fill_not_proven"


@dataclass(frozen=True, slots=True)
class ConsumedDepthLevel:
    price: Decimal
    available_quantity: Decimal
    consumed_quantity: Decimal

    def __post_init__(self) -> None:
        for label, value in (
            ("price", self.price),
            ("available_quantity", self.available_quantity),
            ("consumed_quantity", self.consumed_quantity),
        ):
            _require_positive_decimal(value, label)
        if self.consumed_quantity > self.available_quantity:
            raise ValueError("consumed quantity cannot exceed available quantity")

    @property
    def notional(self) -> Decimal:
        return self.price * self.consumed_quantity


@dataclass(frozen=True, slots=True)
class DepthExecutionOutcome:
    outcome_identity: str
    policy_version: str
    status: DepthExecutionStatus
    action: PaperAction
    orderbook_snapshot_identity: str
    execution_cutoff_ms: int
    requested_quantity: Decimal
    filled_quantity: Decimal
    unfilled_quantity: Decimal
    fill_notional: Decimal
    average_fill_price: Decimal | None
    consumed_levels: tuple[ConsumedDepthLevel, ...]
    partial_fills_enabled: bool
    execution_provable: bool
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if not self.policy_version.strip():
            raise ValueError("policy_version must be non-empty")
        _require_sha256(self.outcome_identity, "outcome_identity")
        _require_sha256(self.orderbook_snapshot_identity, "orderbook_snapshot_identity")
        if self.execution_cutoff_ms < 0:
            raise ValueError("execution_cutoff_ms must be non-negative")
        _require_positive_decimal(self.requested_quantity, "requested_quantity")
        _require_non_negative_decimal(self.filled_quantity, "filled_quantity")
        _require_non_negative_decimal(self.unfilled_quantity, "unfilled_quantity")
        _require_non_negative_decimal(self.fill_notional, "fill_notional")
        if self.filled_quantity + self.unfilled_quantity != self.requested_quantity:
            raise ValueError("filled + unfilled must equal requested quantity")
        consumed_quantity = sum(
            (level.consumed_quantity for level in self.consumed_levels),
            Decimal(0),
        )
        consumed_notional = sum(
            (level.notional for level in self.consumed_levels),
            Decimal(0),
        )
        if consumed_quantity != self.filled_quantity:
            raise ValueError("consumed depth must equal filled quantity")
        if consumed_notional != self.fill_notional:
            raise ValueError("consumed depth notional must equal fill_notional")
        if self.filled_quantity == Decimal(0):
            if self.average_fill_price is not None:
                raise ValueError("zero fill cannot expose average_fill_price")
            if self.fill_notional != Decimal(0) or self.consumed_levels:
                raise ValueError("zero fill cannot consume depth")
        else:
            if self.average_fill_price is None:
                raise ValueError("positive fill requires average_fill_price")
            _require_positive_decimal(self.average_fill_price, "average_fill_price")
            if self.average_fill_price != self.fill_notional / self.filled_quantity:
                raise ValueError("average fill must reconcile to consumed depth")
        if self.status is DepthExecutionStatus.FULL:
            if self.filled_quantity != self.requested_quantity:
                raise ValueError("FULL outcome must fill the requested quantity")
        elif self.status is DepthExecutionStatus.PARTIAL:
            if not self.partial_fills_enabled:
                raise ValueError("PARTIAL outcome requires partial-fill policy")
            if not (Decimal(0) < self.filled_quantity < self.requested_quantity):
                raise ValueError("PARTIAL outcome requires a strict partial fill")
        elif (
            self.status
            in {
                DepthExecutionStatus.NOT_FILLED,
                DepthExecutionStatus.FILL_NOT_PROVEN,
            }
            and self.filled_quantity != Decimal(0)
        ):
            raise ValueError("unfilled/not-proven outcome cannot contain a fill")
        if self.status is DepthExecutionStatus.FILL_NOT_PROVEN and self.execution_provable:
            raise ValueError("FILL_NOT_PROVEN requires execution_provable=False")
        if self.status is not DepthExecutionStatus.FILL_NOT_PROVEN and not self.execution_provable:
            raise ValueError("unprovable execution must fail as FILL_NOT_PROVEN")
        if self.outcome_identity != compute_depth_execution_outcome_identity(
            policy_version=self.policy_version,
            status=self.status,
            action=self.action,
            orderbook_snapshot_identity=self.orderbook_snapshot_identity,
            execution_cutoff_ms=self.execution_cutoff_ms,
            requested_quantity=self.requested_quantity,
            filled_quantity=self.filled_quantity,
            unfilled_quantity=self.unfilled_quantity,
            fill_notional=self.fill_notional,
            average_fill_price=self.average_fill_price,
            consumed_levels=self.consumed_levels,
            partial_fills_enabled=self.partial_fills_enabled,
            execution_provable=self.execution_provable,
        ):
            raise ValueError("depth execution outcome identity mismatch")


def compute_depth_execution_outcome_identity(
    *,
    policy_version: str,
    status: DepthExecutionStatus,
    action: PaperAction,
    orderbook_snapshot_identity: str,
    execution_cutoff_ms: int,
    requested_quantity: Decimal,
    filled_quantity: Decimal,
    unfilled_quantity: Decimal,
    fill_notional: Decimal,
    average_fill_price: Decimal | None,
    consumed_levels: tuple[ConsumedDepthLevel, ...],
    partial_fills_enabled: bool,
    execution_provable: bool,
) -> str:
    return canonical_sha256(
        {
            "action": action.value,
            "average_fill_price": average_fill_price,
            "consumed_levels": [
                {
                    "available_quantity": level.available_quantity,
                    "consumed_quantity": level.consumed_quantity,
                    "price": level.price,
                }
                for level in consumed_levels
            ],
            "execution_cutoff_ms": execution_cutoff_ms,
            "execution_provable": execution_provable,
            "fill_notional": fill_notional,
            "filled_quantity": filled_quantity,
            "orderbook_snapshot_identity": orderbook_snapshot_identity,
            "partial_fills_enabled": partial_fills_enabled,
            "policy_version": policy_version,
            "requested_quantity": requested_quantity,
            "status": status.value,
            "unfilled_quantity": unfilled_quantity,
        }
    )


def simulate_depth_execution(
    *,
    action: PaperAction,
    requested_quantity: Decimal,
    orderbook: OrderBookSnapshot,
    execution_cutoff_ms: int,
    partial_fills_enabled: bool,
    execution_provable: bool = True,
    policy_version: str = FP4_DEPTH_EXECUTION_POLICY_VERSION,
) -> DepthExecutionOutcome:
    """Consume immutable visible depth conservatively and deterministically."""
    if action not in {PaperAction.BUY, PaperAction.REDUCE, PaperAction.EXIT}:
        raise DepthExecutionRejectedError(f"unsupported depth execution action: {action}")
    _require_positive_decimal(requested_quantity, "requested_quantity")
    if execution_cutoff_ms < 0:
        raise DepthExecutionRejectedError("execution_cutoff_ms must be non-negative")
    if orderbook.ingested_at_ms > execution_cutoff_ms:
        raise DepthExecutionRejectedError(
            "future order-book state cannot enter historical execution"
        )
    if not policy_version.strip():
        raise DepthExecutionRejectedError("policy_version must be non-empty")

    if not execution_provable:
        return _build_outcome(
            policy_version=policy_version,
            status=DepthExecutionStatus.FILL_NOT_PROVEN,
            action=action,
            orderbook=orderbook,
            execution_cutoff_ms=execution_cutoff_ms,
            requested_quantity=requested_quantity,
            consumed_levels=(),
            partial_fills_enabled=partial_fills_enabled,
            execution_provable=False,
        )

    levels = orderbook.asks if action is PaperAction.BUY else orderbook.bids
    available_quantity = sum((level.size for level in levels), Decimal(0))

    if requested_quantity > available_quantity and not partial_fills_enabled:
        return _build_outcome(
            policy_version=policy_version,
            status=DepthExecutionStatus.NOT_FILLED,
            action=action,
            orderbook=orderbook,
            execution_cutoff_ms=execution_cutoff_ms,
            requested_quantity=requested_quantity,
            consumed_levels=(),
            partial_fills_enabled=False,
            execution_provable=True,
        )

    remaining = min(requested_quantity, available_quantity)
    consumed: list[ConsumedDepthLevel] = []
    for level in levels:
        if remaining == Decimal(0):
            break
        take = min(level.size, remaining)
        if take > Decimal(0):
            consumed.append(
                ConsumedDepthLevel(
                    price=level.price,
                    available_quantity=level.size,
                    consumed_quantity=take,
                )
            )
            remaining -= take

    filled_quantity = sum(
        (level.consumed_quantity for level in consumed),
        Decimal(0),
    )
    if filled_quantity == requested_quantity:
        status = DepthExecutionStatus.FULL
    elif filled_quantity > Decimal(0) and partial_fills_enabled:
        status = DepthExecutionStatus.PARTIAL
    else:
        status = DepthExecutionStatus.NOT_FILLED
        consumed = []

    return _build_outcome(
        policy_version=policy_version,
        status=status,
        action=action,
        orderbook=orderbook,
        execution_cutoff_ms=execution_cutoff_ms,
        requested_quantity=requested_quantity,
        consumed_levels=tuple(consumed),
        partial_fills_enabled=partial_fills_enabled,
        execution_provable=True,
    )


def _build_outcome(
    *,
    policy_version: str,
    status: DepthExecutionStatus,
    action: PaperAction,
    orderbook: OrderBookSnapshot,
    execution_cutoff_ms: int,
    requested_quantity: Decimal,
    consumed_levels: tuple[ConsumedDepthLevel, ...],
    partial_fills_enabled: bool,
    execution_provable: bool,
) -> DepthExecutionOutcome:
    filled_quantity = sum(
        (level.consumed_quantity for level in consumed_levels),
        Decimal(0),
    )
    fill_notional = sum((level.notional for level in consumed_levels), Decimal(0))
    unfilled_quantity = requested_quantity - filled_quantity
    average_fill_price = (
        None
        if filled_quantity == Decimal(0)
        else fill_notional / filled_quantity
    )
    identity = compute_depth_execution_outcome_identity(
        policy_version=policy_version,
        status=status,
        action=action,
        orderbook_snapshot_identity=orderbook.snapshot_identity,
        execution_cutoff_ms=execution_cutoff_ms,
        requested_quantity=requested_quantity,
        filled_quantity=filled_quantity,
        unfilled_quantity=unfilled_quantity,
        fill_notional=fill_notional,
        average_fill_price=average_fill_price,
        consumed_levels=consumed_levels,
        partial_fills_enabled=partial_fills_enabled,
        execution_provable=execution_provable,
    )
    return DepthExecutionOutcome(
        outcome_identity=identity,
        policy_version=policy_version,
        status=status,
        action=action,
        orderbook_snapshot_identity=orderbook.snapshot_identity,
        execution_cutoff_ms=execution_cutoff_ms,
        requested_quantity=requested_quantity,
        filled_quantity=filled_quantity,
        unfilled_quantity=unfilled_quantity,
        fill_notional=fill_notional,
        average_fill_price=average_fill_price,
        consumed_levels=consumed_levels,
        partial_fills_enabled=partial_fills_enabled,
        execution_provable=execution_provable,
        real_capital=REAL_CAPITAL,
    )


def _require_positive_decimal(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if value.is_nan() or value.is_infinite() or value <= Decimal(0):
        raise ValueError(f"{label} must be finite and positive")


def _require_non_negative_decimal(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if value.is_nan() or value.is_infinite() or value < Decimal(0):
        raise ValueError(f"{label} must be finite and non-negative")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")


__all__ = [
    "FP4_DEPTH_EXECUTION_POLICY_VERSION",
    "ConsumedDepthLevel",
    "DepthExecutionOutcome",
    "DepthExecutionRejectedError",
    "DepthExecutionStatus",
    "compute_depth_execution_outcome_identity",
    "simulate_depth_execution",
]
