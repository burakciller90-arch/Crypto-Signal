"""FP4-B deterministic timing and queue-uncertainty contract.

This module classifies when a paper order becomes execution-ready using only
caller-supplied immutable Market Tape order-book snapshots. Passive limit-order
touch/cross is never promoted to a fill without queue/trade proof.
REAL_CAPITAL remains 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.microstructure import OrderBookSnapshot
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction, PaperSymbol

FP4_TIMING_POLICY_VERSION = "paper_execution_timing.v2"


class TimedExecutionRejectedError(ValueError):
    """Raised when a timing/queue decision cannot be established safely."""


class PaperOrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class TimedExecutionStatus(StrEnum):
    EXECUTION_READY = "execution_ready"
    PENDING = "pending"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    FILL_NOT_PROVEN = "fill_not_proven"


@dataclass(frozen=True, slots=True)
class FrozenExecutionTimingRequest:
    request_identity: str
    policy_version: str
    action: PaperAction
    symbol: PaperSymbol
    exchange: Exchange
    market_type: MarketType
    order_type: PaperOrderType
    submitted_at_ms: int
    latency_ms: int
    deadline_at_ms: int
    cancel_at_ms: int | None
    limit_price: Decimal | None
    partial_fills_enabled: bool
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        _require_sha256(self.request_identity, "request_identity")
        if not self.policy_version.strip():
            raise ValueError("policy_version must be non-empty")
        if self.action not in {PaperAction.BUY, PaperAction.REDUCE, PaperAction.EXIT}:
            raise ValueError("timing request requires BUY/REDUCE/EXIT")
        if self.submitted_at_ms < 0 or self.latency_ms < 0:
            raise ValueError("submission and latency must be non-negative")
        if self.deadline_at_ms < self.submitted_at_ms:
            raise ValueError("deadline cannot precede submission")
        if self.cancel_at_ms is not None:
            if self.cancel_at_ms < self.submitted_at_ms:
                raise ValueError("cancellation cannot precede submission")
            if self.cancel_at_ms > self.deadline_at_ms:
                raise ValueError("cancellation cannot postdate deadline")
        if self.order_type is PaperOrderType.MARKET:
            if self.limit_price is not None:
                raise ValueError("market request cannot carry limit_price")
        else:
            if self.limit_price is None:
                raise ValueError("limit request requires limit_price")
            _require_positive_decimal(self.limit_price, "limit_price")
        if self.request_identity != compute_timing_request_identity(
            policy_version=self.policy_version,
            action=self.action,
            symbol=self.symbol,
            exchange=self.exchange,
            market_type=self.market_type,
            order_type=self.order_type,
            submitted_at_ms=self.submitted_at_ms,
            latency_ms=self.latency_ms,
            deadline_at_ms=self.deadline_at_ms,
            cancel_at_ms=self.cancel_at_ms,
            limit_price=self.limit_price,
            partial_fills_enabled=self.partial_fills_enabled,
        ):
            raise ValueError("timing request identity mismatch")

    @property
    def eligible_at_ms(self) -> int:
        return self.submitted_at_ms + self.latency_ms


@dataclass(frozen=True, slots=True)
class TimedExecutionDecision:
    decision_identity: str
    policy_version: str
    request_identity: str
    status: TimedExecutionStatus
    evaluated_at_ms: int
    eligible_at_ms: int
    observed_orderbook_identities: tuple[str, ...]
    terminal_orderbook_identity: str | None
    reason_code: str
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        _require_sha256(self.decision_identity, "decision_identity")
        _require_sha256(self.request_identity, "request_identity")
        if not self.policy_version.strip():
            raise ValueError("policy_version must be non-empty")
        if self.evaluated_at_ms < 0 or self.eligible_at_ms < 0:
            raise ValueError("decision times must be non-negative")
        if not self.reason_code.strip():
            raise ValueError("reason_code must be non-empty")
        for identity in self.observed_orderbook_identities:
            _require_sha256(identity, "observed orderbook identity")
        if self.terminal_orderbook_identity is not None:
            _require_sha256(
                self.terminal_orderbook_identity,
                "terminal_orderbook_identity",
            )
            if self.terminal_orderbook_identity not in self.observed_orderbook_identities:
                raise ValueError("terminal orderbook must be part of observed lineage")
        if self.status in {
            TimedExecutionStatus.EXECUTION_READY,
            TimedExecutionStatus.FILL_NOT_PROVEN,
        } and self.terminal_orderbook_identity is None:
            raise ValueError("terminal execution state requires orderbook evidence")
        if self.decision_identity != compute_timing_decision_identity(
            policy_version=self.policy_version,
            request_identity=self.request_identity,
            status=self.status,
            evaluated_at_ms=self.evaluated_at_ms,
            eligible_at_ms=self.eligible_at_ms,
            observed_orderbook_identities=self.observed_orderbook_identities,
            terminal_orderbook_identity=self.terminal_orderbook_identity,
            reason_code=self.reason_code,
        ):
            raise ValueError("timing decision identity mismatch")


def compute_timing_request_identity(
    *,
    policy_version: str,
    action: PaperAction,
    symbol: PaperSymbol,
    exchange: Exchange,
    market_type: MarketType,
    order_type: PaperOrderType,
    submitted_at_ms: int,
    latency_ms: int,
    deadline_at_ms: int,
    cancel_at_ms: int | None,
    limit_price: Decimal | None,
    partial_fills_enabled: bool,
) -> str:
    return canonical_sha256(
        {
            "action": action.value,
            "cancel_at_ms": cancel_at_ms,
            "deadline_at_ms": deadline_at_ms,
            "exchange": exchange.value,
            "latency_ms": latency_ms,
            "limit_price": limit_price,
            "market_type": market_type.value,
            "order_type": order_type.value,
            "partial_fills_enabled": partial_fills_enabled,
            "policy_version": policy_version,
            "submitted_at_ms": submitted_at_ms,
            "symbol": symbol.value,
        }
    )


def build_timing_request(
    *,
    action: PaperAction,
    symbol: PaperSymbol,
    exchange: Exchange,
    market_type: MarketType,
    order_type: PaperOrderType,
    submitted_at_ms: int,
    latency_ms: int,
    deadline_at_ms: int,
    cancel_at_ms: int | None = None,
    limit_price: Decimal | None = None,
    partial_fills_enabled: bool = False,
    policy_version: str = FP4_TIMING_POLICY_VERSION,
) -> FrozenExecutionTimingRequest:
    identity = compute_timing_request_identity(
        policy_version=policy_version,
        action=action,
        symbol=symbol,
        exchange=exchange,
        market_type=market_type,
        order_type=order_type,
        submitted_at_ms=submitted_at_ms,
        latency_ms=latency_ms,
        deadline_at_ms=deadline_at_ms,
        cancel_at_ms=cancel_at_ms,
        limit_price=limit_price,
        partial_fills_enabled=partial_fills_enabled,
    )
    return FrozenExecutionTimingRequest(
        request_identity=identity,
        policy_version=policy_version,
        action=action,
        symbol=symbol,
        exchange=exchange,
        market_type=market_type,
        order_type=order_type,
        submitted_at_ms=submitted_at_ms,
        latency_ms=latency_ms,
        deadline_at_ms=deadline_at_ms,
        cancel_at_ms=cancel_at_ms,
        limit_price=limit_price,
        partial_fills_enabled=partial_fills_enabled,
        real_capital=REAL_CAPITAL,
    )


def compute_timing_decision_identity(
    *,
    policy_version: str,
    request_identity: str,
    status: TimedExecutionStatus,
    evaluated_at_ms: int,
    eligible_at_ms: int,
    observed_orderbook_identities: tuple[str, ...],
    terminal_orderbook_identity: str | None,
    reason_code: str,
) -> str:
    return canonical_sha256(
        {
            "eligible_at_ms": eligible_at_ms,
            "evaluated_at_ms": evaluated_at_ms,
            "observed_orderbook_identities": list(observed_orderbook_identities),
            "policy_version": policy_version,
            "reason_code": reason_code,
            "request_identity": request_identity,
            "status": status.value,
            "terminal_orderbook_identity": terminal_orderbook_identity,
        }
    )


def evaluate_timed_execution(
    *,
    request: FrozenExecutionTimingRequest,
    orderbooks: tuple[OrderBookSnapshot, ...],
    evaluation_cutoff_ms: int,
) -> TimedExecutionDecision:
    """Classify execution readiness without inventing queue or future evidence."""
    if request.real_capital != REAL_CAPITAL:
        raise TimedExecutionRejectedError("REAL_CAPITAL must remain 0")
    if evaluation_cutoff_ms < request.submitted_at_ms:
        raise TimedExecutionRejectedError(
            "evaluation cutoff cannot precede submission"
        )

    evidence_cutoff_ms = min(evaluation_cutoff_ms, request.deadline_at_ms)
    if (
        request.cancel_at_ms is not None
        and request.cancel_at_ms <= evaluation_cutoff_ms
    ):
        evidence_cutoff_ms = min(evidence_cutoff_ms, request.cancel_at_ms)

    eligible_books = tuple(
        sorted(
            (
                book
                for book in orderbooks
                if _matches_request(book, request)
                and book.ingested_at_ms <= evidence_cutoff_ms
                and request.eligible_at_ms
                <= book.source_timestamp_ms
                <= evidence_cutoff_ms
            ),
            key=lambda book: (
                book.source_timestamp_ms,
                book.sequence,
                book.snapshot_identity,
            ),
        )
    )

    if not eligible_books:
        if _cancel_is_effective(request, evaluation_cutoff_ms):
            return _decision(
                request=request,
                status=TimedExecutionStatus.CANCELLED,
                evaluated_at_ms=evaluation_cutoff_ms,
                observed=(),
                terminal=None,
                reason_code="cancelled_before_execution_evidence",
            )
        if evaluation_cutoff_ms < request.deadline_at_ms:
            return _decision(
                request=request,
                status=TimedExecutionStatus.PENDING,
                evaluated_at_ms=evaluation_cutoff_ms,
                observed=(),
                terminal=None,
                reason_code="awaiting_causally_eligible_orderbook",
            )
        return _decision(
            request=request,
            status=TimedExecutionStatus.TIMED_OUT,
            evaluated_at_ms=evaluation_cutoff_ms,
            observed=(),
            terminal=None,
            reason_code="deadline_elapsed_without_eligible_orderbook",
        )

    first = eligible_books[0]
    if (
        request.cancel_at_ms is not None
        and request.cancel_at_ms <= evaluation_cutoff_ms
        and request.cancel_at_ms <= first.source_timestamp_ms
    ):
        return _decision(
            request=request,
            status=TimedExecutionStatus.CANCELLED,
            evaluated_at_ms=evaluation_cutoff_ms,
            observed=(),
            terminal=None,
            reason_code="cancellation_precedes_first_eligible_book",
        )

    if request.order_type is PaperOrderType.MARKET:
        return _decision(
            request=request,
            status=TimedExecutionStatus.EXECUTION_READY,
            evaluated_at_ms=evaluation_cutoff_ms,
            observed=(first,),
            terminal=first,
            reason_code="first_post_latency_book_ready_for_depth_execution",
        )

    limit_price = request.limit_price
    assert limit_price is not None
    if _limit_is_marketable(
        action=request.action,
        limit_price=limit_price,
        orderbook=first,
    ):
        return _decision(
            request=request,
            status=TimedExecutionStatus.EXECUTION_READY,
            evaluated_at_ms=evaluation_cutoff_ms,
            observed=(first,),
            terminal=first,
            reason_code="limit_marketable_on_first_eligible_book",
        )

    observed: list[OrderBookSnapshot] = [first]
    for book in eligible_books[1:]:
        if (
            request.cancel_at_ms is not None
            and request.cancel_at_ms <= evaluation_cutoff_ms
            and request.cancel_at_ms <= book.source_timestamp_ms
        ):
            return _decision(
                request=request,
                status=TimedExecutionStatus.CANCELLED,
                evaluated_at_ms=evaluation_cutoff_ms,
                observed=tuple(observed),
                terminal=None,
                reason_code="passive_limit_cancelled_before_later_book",
            )
        observed.append(book)
        if _limit_is_marketable(
            action=request.action,
            limit_price=limit_price,
            orderbook=book,
        ):
            return _decision(
                request=request,
                status=TimedExecutionStatus.FILL_NOT_PROVEN,
                evaluated_at_ms=evaluation_cutoff_ms,
                observed=tuple(observed),
                terminal=book,
                reason_code="passive_limit_touch_or_cross_lacks_queue_proof",
            )

    if _cancel_is_effective(request, evaluation_cutoff_ms):
        return _decision(
            request=request,
            status=TimedExecutionStatus.CANCELLED,
            evaluated_at_ms=evaluation_cutoff_ms,
            observed=tuple(observed),
            terminal=None,
            reason_code="passive_limit_cancelled",
        )
    if evaluation_cutoff_ms < request.deadline_at_ms:
        return _decision(
            request=request,
            status=TimedExecutionStatus.PENDING,
            evaluated_at_ms=evaluation_cutoff_ms,
            observed=tuple(observed),
            terminal=None,
            reason_code="passive_limit_waiting_without_fill_proof",
        )
    return _decision(
        request=request,
        status=TimedExecutionStatus.TIMED_OUT,
        evaluated_at_ms=evaluation_cutoff_ms,
        observed=tuple(observed),
        terminal=None,
        reason_code="passive_limit_deadline_elapsed_without_fill_proof",
    )


def _decision(
    *,
    request: FrozenExecutionTimingRequest,
    status: TimedExecutionStatus,
    evaluated_at_ms: int,
    observed: tuple[OrderBookSnapshot, ...],
    terminal: OrderBookSnapshot | None,
    reason_code: str,
) -> TimedExecutionDecision:
    observed_ids = tuple(book.snapshot_identity for book in observed)
    terminal_id = None if terminal is None else terminal.snapshot_identity
    identity = compute_timing_decision_identity(
        policy_version=request.policy_version,
        request_identity=request.request_identity,
        status=status,
        evaluated_at_ms=evaluated_at_ms,
        eligible_at_ms=request.eligible_at_ms,
        observed_orderbook_identities=observed_ids,
        terminal_orderbook_identity=terminal_id,
        reason_code=reason_code,
    )
    return TimedExecutionDecision(
        decision_identity=identity,
        policy_version=request.policy_version,
        request_identity=request.request_identity,
        status=status,
        evaluated_at_ms=evaluated_at_ms,
        eligible_at_ms=request.eligible_at_ms,
        observed_orderbook_identities=observed_ids,
        terminal_orderbook_identity=terminal_id,
        reason_code=reason_code,
        real_capital=REAL_CAPITAL,
    )


def _matches_request(
    orderbook: OrderBookSnapshot,
    request: FrozenExecutionTimingRequest,
) -> bool:
    return (
        orderbook.symbol == request.symbol.value
        and orderbook.exchange is request.exchange
        and orderbook.market_type is request.market_type
    )


def _cancel_is_effective(
    request: FrozenExecutionTimingRequest,
    evaluation_cutoff_ms: int,
) -> bool:
    return (
        request.cancel_at_ms is not None
        and request.cancel_at_ms <= evaluation_cutoff_ms
        and request.cancel_at_ms <= request.deadline_at_ms
    )


def _limit_is_marketable(
    *,
    action: PaperAction,
    limit_price: Decimal,
    orderbook: OrderBookSnapshot,
) -> bool:
    if action is PaperAction.BUY:
        return orderbook.asks[0].price <= limit_price
    return orderbook.bids[0].price >= limit_price


def _require_positive_decimal(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if value.is_nan() or value.is_infinite() or value <= Decimal(0):
        raise ValueError(f"{label} must be finite and positive")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")


__all__ = [
    "FP4_TIMING_POLICY_VERSION",
    "FrozenExecutionTimingRequest",
    "PaperOrderType",
    "TimedExecutionDecision",
    "TimedExecutionRejectedError",
    "TimedExecutionStatus",
    "build_timing_request",
    "compute_timing_decision_identity",
    "compute_timing_request_identity",
    "evaluate_timed_execution",
]
