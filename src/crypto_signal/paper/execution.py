"""Deterministic simulated execution for the virtual paper fund.

Caller-supplied frozen venue/cost snapshots only. No network, exchange,
credential, broker, or real-order surface. REAL_CAPITAL remains 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.models import (
    PAPER_EXECUTION_POLICY_VERSION,
    PARTIAL_FILLS_SUPPORTED,
    PERMITTED_ACTIONS,
    PERMITTED_SYMBOLS,
    REAL_CAPITAL,
    ExecutionCostAssumptions,
    PaperAction,
    PaperSymbol,
    SimulatedFillRecord,
    build_simulated_fill,
)
from crypto_signal.paper.planning import PaperTradePlan

__all__ = [
    "REAL_CAPITAL",
    "FrozenExecutionSnapshot",
    "PaperExecutionRejectedError",
    "SimulatedExecutionResult",
    "build_frozen_execution_snapshot",
    "compute_frozen_execution_snapshot_identity",
    "simulate_paper_fill",
    "total_simulated_cost_usdt",
]


class PaperExecutionRejectedError(ValueError):
    """Raised when a virtual execution cannot satisfy frozen rules safely."""


@dataclass(frozen=True, slots=True)
class FrozenExecutionSnapshot:
    """Immutable caller-supplied venue-rule and execution-cost assumptions."""

    snapshot_identity: str
    policy_version: str
    venue_reference: str
    symbol: PaperSymbol
    quantity_step: Decimal
    min_quantity: Decimal
    min_notional_usdt: Decimal
    fee_rate: Decimal
    spread_rate: Decimal
    slippage_rate: Decimal
    partial_fills_supported: bool = PARTIAL_FILLS_SUPPORTED
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if len(self.snapshot_identity) != 64 or any(
            ch not in "0123456789abcdef" for ch in self.snapshot_identity
        ):
            raise ValueError("snapshot_identity must be a SHA256 hex digest")
        if not self.policy_version.strip():
            raise ValueError("policy_version must be non-empty")
        if not self.venue_reference.strip():
            raise ValueError("venue_reference must be non-empty")
        if "|snapshot:" in self.venue_reference:
            raise ValueError("venue_reference must not contain reserved snapshot marker")
        if self.symbol not in PERMITTED_SYMBOLS:
            raise ValueError("snapshot symbol is not permitted")
        for label, value in (
            ("quantity_step", self.quantity_step),
            ("min_quantity", self.min_quantity),
            ("min_notional_usdt", self.min_notional_usdt),
            ("fee_rate", self.fee_rate),
            ("spread_rate", self.spread_rate),
            ("slippage_rate", self.slippage_rate),
        ):
            if not isinstance(value, Decimal):
                raise TypeError(f"{label} must be Decimal")
            if value.is_nan() or value.is_infinite():
                raise ValueError(f"{label} must be a finite Decimal")
            if value < Decimal(0):
                raise ValueError(f"{label} cannot be negative")
        if self.quantity_step <= Decimal(0):
            raise ValueError("quantity_step must be positive")
        if self.min_quantity <= Decimal(0):
            raise ValueError("min_quantity must be positive")
        if self.min_notional_usdt <= Decimal(0):
            raise ValueError("min_notional_usdt must be positive")
        if self.fee_rate > Decimal(1):
            raise ValueError("fee_rate cannot exceed 1")
        if self.spread_rate > Decimal(1):
            raise ValueError("spread_rate cannot exceed 1")
        if self.slippage_rate > Decimal(1):
            raise ValueError("slippage_rate cannot exceed 1")
        if self.spread_rate + self.slippage_rate >= Decimal(1):
            raise ValueError("combined spread/slippage must remain below 1")
        if self.partial_fills_supported is not False:
            raise ValueError("v1 partial fills are unsupported and must remain False")
        expected = compute_frozen_execution_snapshot_identity(
            policy_version=self.policy_version,
            venue_reference=self.venue_reference,
            symbol=self.symbol,
            quantity_step=self.quantity_step,
            min_quantity=self.min_quantity,
            min_notional_usdt=self.min_notional_usdt,
            fee_rate=self.fee_rate,
            spread_rate=self.spread_rate,
            slippage_rate=self.slippage_rate,
            partial_fills_supported=self.partial_fills_supported,
        )
        if self.snapshot_identity != expected:
            raise ValueError("frozen execution snapshot identity mismatch")

    @property
    def execution_reference(self) -> str:
        """Audit reference that cryptographically binds a fill to this snapshot."""
        return f"{self.venue_reference}|snapshot:{self.snapshot_identity}"


@dataclass(frozen=True, slots=True)
class SimulatedExecutionResult:
    """Deterministic virtual fill outcome; never an exchange execution."""

    action: PaperAction
    snapshot_identity: str | None
    fill: SimulatedFillRecord | None
    costs: ExecutionCostAssumptions | None
    total_cost_usdt: Decimal
    reference_notional_usdt: Decimal
    fill_notional_usdt: Decimal
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        for label, value in (
            ("total_cost_usdt", self.total_cost_usdt),
            ("reference_notional_usdt", self.reference_notional_usdt),
            ("fill_notional_usdt", self.fill_notional_usdt),
        ):
            if not isinstance(value, Decimal):
                raise TypeError(f"{label} must be Decimal")
            if value < Decimal(0):
                raise ValueError(f"{label} cannot be negative")
        if self.action is PaperAction.HOLD_CASH:
            if self.snapshot_identity is not None:
                raise ValueError("HOLD_CASH must not bind an execution snapshot")
            if self.fill is not None or self.costs is not None:
                raise ValueError("HOLD_CASH must not produce fill or costs")
            if any(
                value != Decimal(0)
                for value in (
                    self.total_cost_usdt,
                    self.reference_notional_usdt,
                    self.fill_notional_usdt,
                )
            ):
                raise ValueError("HOLD_CASH execution values must be zero")
            return
        if self.snapshot_identity is None or len(self.snapshot_identity) != 64:
            raise ValueError("trade execution requires snapshot identity")
        if self.fill is None or self.costs is None:
            raise ValueError("trade execution requires fill and explicit costs")
        if self.total_cost_usdt != total_simulated_cost_usdt(self.costs):
            raise ValueError("total_cost_usdt must equal fee+spread+slippage")
        impact = abs(self.fill_notional_usdt - self.reference_notional_usdt)
        if impact != self.costs.spread_usdt + self.costs.slippage_usdt:
            raise ValueError("fill-price impact must equal explicit spread+slippage")
        if self.action is PaperAction.BUY:
            if self.fill_notional_usdt < self.reference_notional_usdt:
                raise ValueError("BUY cannot receive beneficial simulated execution")
        elif self.action in {PaperAction.REDUCE, PaperAction.EXIT}:
            if self.fill_notional_usdt > self.reference_notional_usdt:
                raise ValueError("sell-side action cannot receive beneficial execution")


def compute_frozen_execution_snapshot_identity(
    *,
    policy_version: str,
    venue_reference: str,
    symbol: PaperSymbol,
    quantity_step: Decimal,
    min_quantity: Decimal,
    min_notional_usdt: Decimal,
    fee_rate: Decimal,
    spread_rate: Decimal,
    slippage_rate: Decimal,
    partial_fills_supported: bool,
) -> str:
    return canonical_sha256(
        {
            "fee_rate": fee_rate,
            "min_notional_usdt": min_notional_usdt,
            "min_quantity": min_quantity,
            "partial_fills_supported": partial_fills_supported,
            "policy_version": policy_version,
            "quantity_step": quantity_step,
            "slippage_rate": slippage_rate,
            "spread_rate": spread_rate,
            "symbol": symbol.value,
            "venue_reference": venue_reference,
        }
    )


def build_frozen_execution_snapshot(
    *,
    venue_reference: str,
    symbol: PaperSymbol,
    quantity_step: Decimal,
    min_quantity: Decimal,
    min_notional_usdt: Decimal,
    fee_rate: Decimal,
    spread_rate: Decimal,
    slippage_rate: Decimal,
    policy_version: str = PAPER_EXECUTION_POLICY_VERSION,
    partial_fills_supported: bool = PARTIAL_FILLS_SUPPORTED,
) -> FrozenExecutionSnapshot:
    identity = compute_frozen_execution_snapshot_identity(
        policy_version=policy_version,
        venue_reference=venue_reference,
        symbol=symbol,
        quantity_step=quantity_step,
        min_quantity=min_quantity,
        min_notional_usdt=min_notional_usdt,
        fee_rate=fee_rate,
        spread_rate=spread_rate,
        slippage_rate=slippage_rate,
        partial_fills_supported=partial_fills_supported,
    )
    return FrozenExecutionSnapshot(
        snapshot_identity=identity,
        policy_version=policy_version,
        venue_reference=venue_reference,
        symbol=symbol,
        quantity_step=quantity_step,
        min_quantity=min_quantity,
        min_notional_usdt=min_notional_usdt,
        fee_rate=fee_rate,
        spread_rate=spread_rate,
        slippage_rate=slippage_rate,
        partial_fills_supported=partial_fills_supported,
        real_capital=REAL_CAPITAL,
    )


def total_simulated_cost_usdt(costs: ExecutionCostAssumptions) -> Decimal:
    return costs.fee_usdt + costs.spread_usdt + costs.slippage_usdt


def simulate_paper_fill(
    *,
    plan: PaperTradePlan,
    snapshot: FrozenExecutionSnapshot | None,
    decision_identity: str,
    filled_at_ms: int,
) -> SimulatedExecutionResult:
    """Produce a deterministic full virtual fill from explicit frozen inputs."""
    if plan.real_capital != REAL_CAPITAL:
        raise PaperExecutionRejectedError("REAL_CAPITAL must remain 0")
    if filled_at_ms < 0:
        raise PaperExecutionRejectedError("filled_at_ms must be non-negative")
    if plan.action is PaperAction.HOLD_CASH:
        if snapshot is not None:
            raise PaperExecutionRejectedError(
                "HOLD_CASH must not supply an execution snapshot"
            )
        return SimulatedExecutionResult(
            action=PaperAction.HOLD_CASH,
            snapshot_identity=None,
            fill=None,
            costs=None,
            total_cost_usdt=Decimal(0),
            reference_notional_usdt=Decimal(0),
            fill_notional_usdt=Decimal(0),
            real_capital=REAL_CAPITAL,
        )
    if snapshot is None:
        raise PaperExecutionRejectedError("trade action requires execution snapshot")
    if snapshot.real_capital != REAL_CAPITAL:
        raise PaperExecutionRejectedError("REAL_CAPITAL must remain 0")
    if snapshot.partial_fills_supported is not False:
        raise PaperExecutionRejectedError("partial fills are unsupported in v1")
    if plan.action not in PERMITTED_ACTIONS:
        raise PaperExecutionRejectedError(f"action not permitted: {plan.action}")
    if plan.symbol is None or plan.quantity is None or plan.reference_price is None:
        raise PaperExecutionRejectedError(
            "trade action requires symbol, quantity, and reference_price"
        )
    if plan.symbol is not snapshot.symbol:
        raise PaperExecutionRejectedError(
            "plan symbol does not match execution snapshot symbol"
        )
    if plan.quantity <= Decimal(0) or plan.reference_price <= Decimal(0):
        raise PaperExecutionRejectedError("trade quantity and price must be positive")

    _validate_quantity_and_notional(
        quantity=plan.quantity,
        reference_price=plan.reference_price,
        snapshot=snapshot,
    )
    fill_price = _adverse_fill_price(
        action=plan.action,
        reference_price=plan.reference_price,
        spread_rate=snapshot.spread_rate,
        slippage_rate=snapshot.slippage_rate,
    )
    reference_notional = plan.quantity * plan.reference_price
    fill_notional = plan.quantity * fill_price
    costs = _explicit_costs(
        reference_notional=reference_notional,
        fill_notional=fill_notional,
        snapshot=snapshot,
    )
    total_cost = total_simulated_cost_usdt(costs)
    if total_cost > plan.cost_budget_usdt:
        raise PaperExecutionRejectedError(
            "plan cost budget is insufficient for simulated execution"
        )
    fill = build_simulated_fill(
        fund_identity=plan.fund_identity,
        decision_identity=decision_identity,
        filled_at_ms=filled_at_ms,
        action=plan.action,
        symbol=plan.symbol,
        quantity=plan.quantity,
        reference_price=plan.reference_price,
        simulated_fill_price=fill_price,
        costs=costs,
        venue_reference=snapshot.execution_reference,
    )
    return SimulatedExecutionResult(
        action=plan.action,
        snapshot_identity=snapshot.snapshot_identity,
        fill=fill,
        costs=costs,
        total_cost_usdt=total_cost,
        reference_notional_usdt=reference_notional,
        fill_notional_usdt=fill_notional,
        real_capital=REAL_CAPITAL,
    )


def _validate_quantity_and_notional(
    *,
    quantity: Decimal,
    reference_price: Decimal,
    snapshot: FrozenExecutionSnapshot,
) -> None:
    if quantity < snapshot.min_quantity:
        raise PaperExecutionRejectedError(
            "quantity below frozen snapshot minimum quantity"
        )
    steps = quantity / snapshot.quantity_step
    if steps != steps.to_integral_value(rounding=ROUND_DOWN):
        raise PaperExecutionRejectedError(
            "quantity is not an exact multiple of frozen quantity_step"
        )
    if quantity * reference_price < snapshot.min_notional_usdt:
        raise PaperExecutionRejectedError(
            "notional below frozen snapshot minimum notional"
        )


def _adverse_fill_price(
    *,
    action: PaperAction,
    reference_price: Decimal,
    spread_rate: Decimal,
    slippage_rate: Decimal,
) -> Decimal:
    adverse = spread_rate + slippage_rate
    if action is PaperAction.BUY:
        return reference_price * (Decimal(1) + adverse)
    if action in {PaperAction.REDUCE, PaperAction.EXIT}:
        price = reference_price * (Decimal(1) - adverse)
        if price <= Decimal(0):
            raise PaperExecutionRejectedError(
                "spread/slippage assumptions produce non-positive sell price"
            )
        return price
    raise PaperExecutionRejectedError(f"unsupported paper action: {action}")


def _explicit_costs(
    *,
    reference_notional: Decimal,
    fill_notional: Decimal,
    snapshot: FrozenExecutionSnapshot,
) -> ExecutionCostAssumptions:
    return ExecutionCostAssumptions(
        fee_usdt=fill_notional * snapshot.fee_rate,
        spread_usdt=reference_notional * snapshot.spread_rate,
        slippage_usdt=reference_notional * snapshot.slippage_rate,
        execution_policy_version=snapshot.policy_version,
        partial_fills_supported=False,
    )
