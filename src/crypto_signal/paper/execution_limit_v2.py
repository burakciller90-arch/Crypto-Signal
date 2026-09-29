"""FP4-B passive-limit timing and queue-proof simulation.

This module models a passive paper limit order from immutable caller-supplied
Market Tape order-book and public-trade truth. It has no network or order
authority and never mutates R21/R22. REAL_CAPITAL remains 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.microstructure import (
    AggressorSide,
    OrderBookSnapshot,
    PublicTradeObservation,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction

FP4_PASSIVE_LIMIT_POLICY_VERSION = "paper_execution_passive_limit.v2"


class PassiveLimitExecutionRejectedError(ValueError):
    """Raised when passive-limit evidence violates the frozen contract."""


class PassiveLimitExecutionStatus(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    NOT_FILLED = "not_filled"
    FILL_NOT_PROVEN = "fill_not_proven"


class PassiveLimitTerminalState(StrEnum):
    FILLED = "filled"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    UNPROVEN = "unproven"


@dataclass(frozen=True, slots=True)
class PassiveLimitExecutionOutcome:
    outcome_identity: str
    policy_version: str
    status: PassiveLimitExecutionStatus
    terminal_state: PassiveLimitTerminalState
    action: PaperAction
    orderbook_snapshot_identity: str
    evidence_trade_identities: tuple[str, ...]
    supporting_trade_identities: tuple[str, ...]
    submitted_at_ms: int
    latency_ms: int
    effective_arrival_ms: int
    timeout_ms: int
    cancel_at_ms: int | None
    terminal_at_ms: int
    completed_at_ms: int
    max_book_age_ms: int
    limit_price: Decimal
    requested_quantity: Decimal
    visible_queue_ahead_quantity: Decimal
    queue_consumed_quantity: Decimal
    filled_quantity: Decimal
    unfilled_quantity: Decimal
    fill_notional: Decimal
    average_fill_price: Decimal | None
    partial_fills_enabled: bool
    queue_position_proven: bool
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        _require_sha256(self.outcome_identity, "outcome_identity")
        _require_sha256(self.orderbook_snapshot_identity, "orderbook_snapshot_identity")
        if not self.policy_version.strip():
            raise ValueError("policy_version must be non-empty")
        if self.action not in {PaperAction.BUY, PaperAction.REDUCE, PaperAction.EXIT}:
            raise ValueError("passive-limit outcome requires BUY/REDUCE/EXIT")
        for label, timestamp_value in (
            ("submitted_at_ms", self.submitted_at_ms),
            ("latency_ms", self.latency_ms),
            ("effective_arrival_ms", self.effective_arrival_ms),
            ("timeout_ms", self.timeout_ms),
            ("terminal_at_ms", self.terminal_at_ms),
            ("completed_at_ms", self.completed_at_ms),
            ("max_book_age_ms", self.max_book_age_ms),
        ):
            if timestamp_value < 0:
                raise ValueError(f"{label} must be non-negative")
        if self.timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        if self.effective_arrival_ms != self.submitted_at_ms + self.latency_ms:
            raise ValueError("effective arrival must equal submitted time plus latency")
        expected_terminal_at = self.effective_arrival_ms + self.timeout_ms
        if self.cancel_at_ms is not None:
            if self.cancel_at_ms < self.effective_arrival_ms:
                raise ValueError("cancel_at_ms cannot precede effective arrival")
            expected_terminal_at = min(expected_terminal_at, self.cancel_at_ms)
        if self.terminal_at_ms != expected_terminal_at:
            raise ValueError("terminal_at_ms does not match timeout/cancel policy")
        if not self.effective_arrival_ms <= self.completed_at_ms <= self.terminal_at_ms:
            raise ValueError("completed_at_ms must be inside the active order window")
        _require_positive_decimal(self.limit_price, "limit_price")
        _require_positive_decimal(self.requested_quantity, "requested_quantity")
        for label, decimal_value in (
            ("visible_queue_ahead_quantity", self.visible_queue_ahead_quantity),
            ("queue_consumed_quantity", self.queue_consumed_quantity),
            ("filled_quantity", self.filled_quantity),
            ("unfilled_quantity", self.unfilled_quantity),
            ("fill_notional", self.fill_notional),
        ):
            _require_non_negative_decimal(decimal_value, label)
        if self.queue_consumed_quantity > self.visible_queue_ahead_quantity:
            raise ValueError("queue consumed cannot exceed visible queue ahead")
        if self.filled_quantity + self.unfilled_quantity != self.requested_quantity:
            raise ValueError("filled + unfilled must equal requested quantity")
        if self.filled_quantity == Decimal(0):
            if self.average_fill_price is not None:
                raise ValueError("zero fill cannot expose average_fill_price")
            if self.fill_notional != Decimal(0):
                raise ValueError("zero fill must have zero fill_notional")
        else:
            if self.average_fill_price != self.limit_price:
                raise ValueError("passive V2 fill must use the frozen limit price")
            if self.fill_notional != self.filled_quantity * self.limit_price:
                raise ValueError("passive fill notional must reconcile to limit price")
        evidence = set(self.evidence_trade_identities)
        if len(evidence) != len(self.evidence_trade_identities):
            raise ValueError("evidence trade identities must be unique")
        if not set(self.supporting_trade_identities).issubset(evidence):
            raise ValueError("supporting trades must be part of evidence trades")
        if self.status is PassiveLimitExecutionStatus.FULL:
            if self.filled_quantity != self.requested_quantity:
                raise ValueError("FULL outcome must fill requested quantity")
            if self.terminal_state is not PassiveLimitTerminalState.FILLED:
                raise ValueError("FULL outcome must terminate as FILLED")
        elif self.status is PassiveLimitExecutionStatus.PARTIAL:
            if not self.partial_fills_enabled:
                raise ValueError("PARTIAL requires partial-fill support")
            if not (Decimal(0) < self.filled_quantity < self.requested_quantity):
                raise ValueError("PARTIAL requires a strict partial quantity")
            if self.terminal_state not in {
                PassiveLimitTerminalState.TIMED_OUT,
                PassiveLimitTerminalState.CANCELLED,
            }:
                raise ValueError("PARTIAL must end by timeout or cancellation")
        elif self.status is PassiveLimitExecutionStatus.NOT_FILLED:
            if self.filled_quantity != Decimal(0):
                raise ValueError("NOT_FILLED cannot contain filled quantity")
            if self.terminal_state not in {
                PassiveLimitTerminalState.TIMED_OUT,
                PassiveLimitTerminalState.CANCELLED,
            }:
                raise ValueError("NOT_FILLED must end by timeout or cancellation")
        elif self.status is PassiveLimitExecutionStatus.FILL_NOT_PROVEN:
            if self.filled_quantity != Decimal(0):
                raise ValueError("FILL_NOT_PROVEN cannot promote a fill")
            if self.terminal_state is not PassiveLimitTerminalState.UNPROVEN:
                raise ValueError("FILL_NOT_PROVEN must terminate as UNPROVEN")
        if (
            self.status is not PassiveLimitExecutionStatus.FILL_NOT_PROVEN
            and not self.queue_position_proven
        ):
            raise ValueError("promoted passive outcome requires queue proof")
        if self.outcome_identity != compute_passive_limit_outcome_identity(
            policy_version=self.policy_version,
            status=self.status,
            terminal_state=self.terminal_state,
            action=self.action,
            orderbook_snapshot_identity=self.orderbook_snapshot_identity,
            evidence_trade_identities=self.evidence_trade_identities,
            supporting_trade_identities=self.supporting_trade_identities,
            submitted_at_ms=self.submitted_at_ms,
            latency_ms=self.latency_ms,
            effective_arrival_ms=self.effective_arrival_ms,
            timeout_ms=self.timeout_ms,
            cancel_at_ms=self.cancel_at_ms,
            terminal_at_ms=self.terminal_at_ms,
            completed_at_ms=self.completed_at_ms,
            max_book_age_ms=self.max_book_age_ms,
            limit_price=self.limit_price,
            requested_quantity=self.requested_quantity,
            visible_queue_ahead_quantity=self.visible_queue_ahead_quantity,
            queue_consumed_quantity=self.queue_consumed_quantity,
            filled_quantity=self.filled_quantity,
            unfilled_quantity=self.unfilled_quantity,
            fill_notional=self.fill_notional,
            average_fill_price=self.average_fill_price,
            partial_fills_enabled=self.partial_fills_enabled,
            queue_position_proven=self.queue_position_proven,
        ):
            raise ValueError("passive-limit outcome identity mismatch")


def compute_passive_limit_outcome_identity(
    *,
    policy_version: str,
    status: PassiveLimitExecutionStatus,
    terminal_state: PassiveLimitTerminalState,
    action: PaperAction,
    orderbook_snapshot_identity: str,
    evidence_trade_identities: tuple[str, ...],
    supporting_trade_identities: tuple[str, ...],
    submitted_at_ms: int,
    latency_ms: int,
    effective_arrival_ms: int,
    timeout_ms: int,
    cancel_at_ms: int | None,
    terminal_at_ms: int,
    completed_at_ms: int,
    max_book_age_ms: int,
    limit_price: Decimal,
    requested_quantity: Decimal,
    visible_queue_ahead_quantity: Decimal,
    queue_consumed_quantity: Decimal,
    filled_quantity: Decimal,
    unfilled_quantity: Decimal,
    fill_notional: Decimal,
    average_fill_price: Decimal | None,
    partial_fills_enabled: bool,
    queue_position_proven: bool,
) -> str:
    return canonical_sha256(
        {
            "action": action.value,
            "average_fill_price": average_fill_price,
            "cancel_at_ms": cancel_at_ms,
            "completed_at_ms": completed_at_ms,
            "effective_arrival_ms": effective_arrival_ms,
            "evidence_trade_identities": list(evidence_trade_identities),
            "fill_notional": fill_notional,
            "filled_quantity": filled_quantity,
            "latency_ms": latency_ms,
            "limit_price": limit_price,
            "max_book_age_ms": max_book_age_ms,
            "orderbook_snapshot_identity": orderbook_snapshot_identity,
            "partial_fills_enabled": partial_fills_enabled,
            "policy_version": policy_version,
            "queue_consumed_quantity": queue_consumed_quantity,
            "queue_position_proven": queue_position_proven,
            "requested_quantity": requested_quantity,
            "status": status.value,
            "submitted_at_ms": submitted_at_ms,
            "supporting_trade_identities": list(supporting_trade_identities),
            "terminal_at_ms": terminal_at_ms,
            "terminal_state": terminal_state.value,
            "timeout_ms": timeout_ms,
            "unfilled_quantity": unfilled_quantity,
            "visible_queue_ahead_quantity": visible_queue_ahead_quantity,
        }
    )


def simulate_passive_limit_execution(
    *,
    action: PaperAction,
    requested_quantity: Decimal,
    limit_price: Decimal,
    arrival_book: OrderBookSnapshot,
    public_trades: tuple[PublicTradeObservation, ...],
    submitted_at_ms: int,
    latency_ms: int,
    timeout_ms: int,
    max_book_age_ms: int,
    partial_fills_enabled: bool,
    queue_position_proven: bool,
    cancel_at_ms: int | None = None,
    policy_version: str = FP4_PASSIVE_LIMIT_POLICY_VERSION,
) -> PassiveLimitExecutionOutcome:
    """Simulate one passive limit order with explicit queue evidence."""
    if action not in {PaperAction.BUY, PaperAction.REDUCE, PaperAction.EXIT}:
        raise PassiveLimitExecutionRejectedError(
            f"unsupported passive-limit action: {action}"
        )
    _require_positive_decimal(requested_quantity, "requested_quantity")
    _require_positive_decimal(limit_price, "limit_price")
    if min(submitted_at_ms, latency_ms, max_book_age_ms) < 0:
        raise PassiveLimitExecutionRejectedError(
            "submitted_at_ms, latency_ms and max_book_age_ms must be non-negative"
        )
    if timeout_ms <= 0:
        raise PassiveLimitExecutionRejectedError("timeout_ms must be positive")
    if not policy_version.strip():
        raise PassiveLimitExecutionRejectedError("policy_version must be non-empty")

    effective_arrival_ms = submitted_at_ms + latency_ms
    timeout_at_ms = effective_arrival_ms + timeout_ms
    if cancel_at_ms is not None and cancel_at_ms < effective_arrival_ms:
        raise PassiveLimitExecutionRejectedError(
            "cancel_at_ms cannot precede effective arrival"
        )
    terminal_at_ms = (
        timeout_at_ms
        if cancel_at_ms is None
        else min(timeout_at_ms, cancel_at_ms)
    )
    terminal_state = (
        PassiveLimitTerminalState.CANCELLED
        if cancel_at_ms is not None and cancel_at_ms <= timeout_at_ms
        else PassiveLimitTerminalState.TIMED_OUT
    )

    if arrival_book.event_at_ms > effective_arrival_ms:
        raise PassiveLimitExecutionRejectedError(
            "future order-book event cannot define arrival queue"
        )
    if arrival_book.ingested_at_ms > effective_arrival_ms:
        raise PassiveLimitExecutionRejectedError(
            "future-ingested order-book state cannot define arrival queue"
        )
    ordered_trades = _validate_and_order_trades(
        arrival_book=arrival_book,
        public_trades=public_trades,
    )
    evidence_trade_identities = tuple(
        trade.trade_identity for trade in ordered_trades
    )
    visible_queue = _visible_queue_ahead(
        action=action,
        limit_price=limit_price,
        arrival_book=arrival_book,
    )
    if effective_arrival_ms - arrival_book.event_at_ms > max_book_age_ms:
        return _unproven_outcome(
            policy_version=policy_version,
            action=action,
            arrival_book=arrival_book,
            evidence_trade_identities=evidence_trade_identities,
            submitted_at_ms=submitted_at_ms,
            latency_ms=latency_ms,
            effective_arrival_ms=effective_arrival_ms,
            timeout_ms=timeout_ms,
            cancel_at_ms=cancel_at_ms,
            terminal_at_ms=terminal_at_ms,
            max_book_age_ms=max_book_age_ms,
            limit_price=limit_price,
            requested_quantity=requested_quantity,
            visible_queue=visible_queue,
            partial_fills_enabled=partial_fills_enabled,
            queue_position_proven=queue_position_proven,
        )

    _reject_marketable_limit(
        action=action,
        limit_price=limit_price,
        arrival_book=arrival_book,
    )
    if not queue_position_proven:
        return _unproven_outcome(
            policy_version=policy_version,
            action=action,
            arrival_book=arrival_book,
            evidence_trade_identities=evidence_trade_identities,
            submitted_at_ms=submitted_at_ms,
            latency_ms=latency_ms,
            effective_arrival_ms=effective_arrival_ms,
            timeout_ms=timeout_ms,
            cancel_at_ms=cancel_at_ms,
            terminal_at_ms=terminal_at_ms,
            max_book_age_ms=max_book_age_ms,
            limit_price=limit_price,
            requested_quantity=requested_quantity,
            visible_queue=visible_queue,
            partial_fills_enabled=partial_fills_enabled,
            queue_position_proven=False,
        )

    late_qualifying = tuple(
        trade.trade_identity
        for trade in ordered_trades
        if effective_arrival_ms <= trade.event_at_ms <= terminal_at_ms
        and _trade_executes_at_limit(action=action, limit_price=limit_price, trade=trade)
        and trade.ingested_at_ms > terminal_at_ms
    )
    if late_qualifying:
        return _unproven_outcome(
            policy_version=policy_version,
            action=action,
            arrival_book=arrival_book,
            evidence_trade_identities=evidence_trade_identities,
            submitted_at_ms=submitted_at_ms,
            latency_ms=latency_ms,
            effective_arrival_ms=effective_arrival_ms,
            timeout_ms=timeout_ms,
            cancel_at_ms=cancel_at_ms,
            terminal_at_ms=terminal_at_ms,
            max_book_age_ms=max_book_age_ms,
            limit_price=limit_price,
            requested_quantity=requested_quantity,
            visible_queue=visible_queue,
            partial_fills_enabled=partial_fills_enabled,
            queue_position_proven=True,
        )

    queue_remaining = visible_queue
    queue_consumed = Decimal(0)
    filled_quantity = Decimal(0)
    supporting: list[str] = []
    fill_completed_at_ms: int | None = None

    for trade in ordered_trades:
        if trade.event_at_ms < effective_arrival_ms or trade.event_at_ms > terminal_at_ms:
            continue
        if trade.ingested_at_ms > terminal_at_ms:
            continue
        if not _trade_executes_at_limit(
            action=action,
            limit_price=limit_price,
            trade=trade,
        ):
            continue
        available = trade.size
        supporting.append(trade.trade_identity)
        if queue_remaining > Decimal(0):
            consumed = min(queue_remaining, available)
            queue_remaining -= consumed
            queue_consumed += consumed
            available -= consumed
        if available <= Decimal(0):
            continue
        own_remaining = requested_quantity - filled_quantity
        own_fill = min(own_remaining, available)
        filled_quantity += own_fill
        if filled_quantity == requested_quantity:
            fill_completed_at_ms = trade.event_at_ms
            break

    if filled_quantity == requested_quantity:
        return _build_outcome(
            policy_version=policy_version,
            status=PassiveLimitExecutionStatus.FULL,
            terminal_state=PassiveLimitTerminalState.FILLED,
            action=action,
            arrival_book=arrival_book,
            evidence_trade_identities=evidence_trade_identities,
            supporting_trade_identities=tuple(supporting),
            submitted_at_ms=submitted_at_ms,
            latency_ms=latency_ms,
            effective_arrival_ms=effective_arrival_ms,
            timeout_ms=timeout_ms,
            cancel_at_ms=cancel_at_ms,
            terminal_at_ms=terminal_at_ms,
            completed_at_ms=(
                terminal_at_ms
                if fill_completed_at_ms is None
                else fill_completed_at_ms
            ),
            max_book_age_ms=max_book_age_ms,
            limit_price=limit_price,
            requested_quantity=requested_quantity,
            visible_queue=visible_queue,
            queue_consumed=queue_consumed,
            filled_quantity=filled_quantity,
            partial_fills_enabled=partial_fills_enabled,
            queue_position_proven=True,
        )

    if filled_quantity > Decimal(0) and not partial_fills_enabled:
        return _unproven_outcome(
            policy_version=policy_version,
            action=action,
            arrival_book=arrival_book,
            evidence_trade_identities=evidence_trade_identities,
            submitted_at_ms=submitted_at_ms,
            latency_ms=latency_ms,
            effective_arrival_ms=effective_arrival_ms,
            timeout_ms=timeout_ms,
            cancel_at_ms=cancel_at_ms,
            terminal_at_ms=terminal_at_ms,
            max_book_age_ms=max_book_age_ms,
            limit_price=limit_price,
            requested_quantity=requested_quantity,
            visible_queue=visible_queue,
            partial_fills_enabled=False,
            queue_position_proven=True,
        )

    status = (
        PassiveLimitExecutionStatus.PARTIAL
        if filled_quantity > Decimal(0)
        else PassiveLimitExecutionStatus.NOT_FILLED
    )
    return _build_outcome(
        policy_version=policy_version,
        status=status,
        terminal_state=terminal_state,
        action=action,
        arrival_book=arrival_book,
        evidence_trade_identities=evidence_trade_identities,
        supporting_trade_identities=tuple(supporting),
        submitted_at_ms=submitted_at_ms,
        latency_ms=latency_ms,
        effective_arrival_ms=effective_arrival_ms,
        timeout_ms=timeout_ms,
        cancel_at_ms=cancel_at_ms,
        terminal_at_ms=terminal_at_ms,
        completed_at_ms=terminal_at_ms,
        max_book_age_ms=max_book_age_ms,
        limit_price=limit_price,
        requested_quantity=requested_quantity,
        visible_queue=visible_queue,
        queue_consumed=queue_consumed,
        filled_quantity=filled_quantity,
        partial_fills_enabled=partial_fills_enabled,
        queue_position_proven=True,
    )


def _validate_and_order_trades(
    *,
    arrival_book: OrderBookSnapshot,
    public_trades: tuple[PublicTradeObservation, ...],
) -> tuple[PublicTradeObservation, ...]:
    seen: set[str] = set()
    for trade in public_trades:
        if trade.trade_identity in seen:
            raise PassiveLimitExecutionRejectedError(
                "duplicate public-trade identity in execution evidence"
            )
        seen.add(trade.trade_identity)
        if (
            trade.exchange is not arrival_book.exchange
            or trade.market_type is not arrival_book.market_type
            or trade.symbol != arrival_book.symbol
        ):
            raise PassiveLimitExecutionRejectedError(
                "public trade context does not match arrival order book"
            )
    return tuple(
        sorted(
            public_trades,
            key=lambda trade: (
                trade.event_at_ms,
                trade.sequence,
                trade.trade_identity,
            ),
        )
    )


def _visible_queue_ahead(
    *,
    action: PaperAction,
    limit_price: Decimal,
    arrival_book: OrderBookSnapshot,
) -> Decimal:
    levels = arrival_book.bids if action is PaperAction.BUY else arrival_book.asks
    return next(
        (level.size for level in levels if level.price == limit_price),
        Decimal(0),
    )


def _reject_marketable_limit(
    *,
    action: PaperAction,
    limit_price: Decimal,
    arrival_book: OrderBookSnapshot,
) -> None:
    if action is PaperAction.BUY and limit_price >= arrival_book.asks[0].price:
        raise PassiveLimitExecutionRejectedError(
            "marketable BUY limit must use FP4-A depth execution"
        )
    if (
        action in {PaperAction.REDUCE, PaperAction.EXIT}
        and limit_price <= arrival_book.bids[0].price
    ):
        raise PassiveLimitExecutionRejectedError(
            "marketable sell limit must use FP4-A depth execution"
        )


def _trade_executes_at_limit(
    *,
    action: PaperAction,
    limit_price: Decimal,
    trade: PublicTradeObservation,
) -> bool:
    if not trade.book_eligible:
        return False
    if action is PaperAction.BUY:
        return (
            trade.aggressor_side is AggressorSide.SELL
            and trade.price <= limit_price
        )
    return (
        trade.aggressor_side is AggressorSide.BUY
        and trade.price >= limit_price
    )


def _unproven_outcome(
    *,
    policy_version: str,
    action: PaperAction,
    arrival_book: OrderBookSnapshot,
    evidence_trade_identities: tuple[str, ...],
    submitted_at_ms: int,
    latency_ms: int,
    effective_arrival_ms: int,
    timeout_ms: int,
    cancel_at_ms: int | None,
    terminal_at_ms: int,
    max_book_age_ms: int,
    limit_price: Decimal,
    requested_quantity: Decimal,
    visible_queue: Decimal,
    partial_fills_enabled: bool,
    queue_position_proven: bool,
) -> PassiveLimitExecutionOutcome:
    return _build_outcome(
        policy_version=policy_version,
        status=PassiveLimitExecutionStatus.FILL_NOT_PROVEN,
        terminal_state=PassiveLimitTerminalState.UNPROVEN,
        action=action,
        arrival_book=arrival_book,
        evidence_trade_identities=evidence_trade_identities,
        supporting_trade_identities=(),
        submitted_at_ms=submitted_at_ms,
        latency_ms=latency_ms,
        effective_arrival_ms=effective_arrival_ms,
        timeout_ms=timeout_ms,
        cancel_at_ms=cancel_at_ms,
        terminal_at_ms=terminal_at_ms,
        completed_at_ms=terminal_at_ms,
        max_book_age_ms=max_book_age_ms,
        limit_price=limit_price,
        requested_quantity=requested_quantity,
        visible_queue=visible_queue,
        queue_consumed=Decimal(0),
        filled_quantity=Decimal(0),
        partial_fills_enabled=partial_fills_enabled,
        queue_position_proven=queue_position_proven,
    )


def _build_outcome(
    *,
    policy_version: str,
    status: PassiveLimitExecutionStatus,
    terminal_state: PassiveLimitTerminalState,
    action: PaperAction,
    arrival_book: OrderBookSnapshot,
    evidence_trade_identities: tuple[str, ...],
    supporting_trade_identities: tuple[str, ...],
    submitted_at_ms: int,
    latency_ms: int,
    effective_arrival_ms: int,
    timeout_ms: int,
    cancel_at_ms: int | None,
    terminal_at_ms: int,
    completed_at_ms: int,
    max_book_age_ms: int,
    limit_price: Decimal,
    requested_quantity: Decimal,
    visible_queue: Decimal,
    queue_consumed: Decimal,
    filled_quantity: Decimal,
    partial_fills_enabled: bool,
    queue_position_proven: bool,
) -> PassiveLimitExecutionOutcome:
    unfilled_quantity = requested_quantity - filled_quantity
    fill_notional = filled_quantity * limit_price
    average_fill_price = None if filled_quantity == Decimal(0) else limit_price
    identity = compute_passive_limit_outcome_identity(
        policy_version=policy_version,
        status=status,
        terminal_state=terminal_state,
        action=action,
        orderbook_snapshot_identity=arrival_book.snapshot_identity,
        evidence_trade_identities=evidence_trade_identities,
        supporting_trade_identities=supporting_trade_identities,
        submitted_at_ms=submitted_at_ms,
        latency_ms=latency_ms,
        effective_arrival_ms=effective_arrival_ms,
        timeout_ms=timeout_ms,
        cancel_at_ms=cancel_at_ms,
        terminal_at_ms=terminal_at_ms,
        completed_at_ms=completed_at_ms,
        max_book_age_ms=max_book_age_ms,
        limit_price=limit_price,
        requested_quantity=requested_quantity,
        visible_queue_ahead_quantity=visible_queue,
        queue_consumed_quantity=queue_consumed,
        filled_quantity=filled_quantity,
        unfilled_quantity=unfilled_quantity,
        fill_notional=fill_notional,
        average_fill_price=average_fill_price,
        partial_fills_enabled=partial_fills_enabled,
        queue_position_proven=queue_position_proven,
    )
    return PassiveLimitExecutionOutcome(
        outcome_identity=identity,
        policy_version=policy_version,
        status=status,
        terminal_state=terminal_state,
        action=action,
        orderbook_snapshot_identity=arrival_book.snapshot_identity,
        evidence_trade_identities=evidence_trade_identities,
        supporting_trade_identities=supporting_trade_identities,
        submitted_at_ms=submitted_at_ms,
        latency_ms=latency_ms,
        effective_arrival_ms=effective_arrival_ms,
        timeout_ms=timeout_ms,
        cancel_at_ms=cancel_at_ms,
        terminal_at_ms=terminal_at_ms,
        completed_at_ms=completed_at_ms,
        max_book_age_ms=max_book_age_ms,
        limit_price=limit_price,
        requested_quantity=requested_quantity,
        visible_queue_ahead_quantity=visible_queue,
        queue_consumed_quantity=queue_consumed,
        filled_quantity=filled_quantity,
        unfilled_quantity=unfilled_quantity,
        fill_notional=fill_notional,
        average_fill_price=average_fill_price,
        partial_fills_enabled=partial_fills_enabled,
        queue_position_proven=queue_position_proven,
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
    "FP4_PASSIVE_LIMIT_POLICY_VERSION",
    "PassiveLimitExecutionOutcome",
    "PassiveLimitExecutionRejectedError",
    "PassiveLimitExecutionStatus",
    "PassiveLimitTerminalState",
    "compute_passive_limit_outcome_identity",
    "simulate_passive_limit_execution",
]
