"""Pure pre-trade bridge for the virtual paper fund.

Consumes accepted sizing plus an externally frozen venue/cost snapshot, rounds
quantity only downward, derives the exact simulator cost budget and invokes the
existing conservative paper planner. It never fetches venue metadata, simulates
a fill, writes a ledger, or contacts an exchange. REAL_CAPITAL remains 0.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.execution import FrozenExecutionSnapshot
from crypto_signal.paper.execution_input import FrozenPaperExecutionInput
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction, PaperSymbol
from crypto_signal.paper.planning import (
    PaperPlanRejectedError,
    PaperTradePlan,
    plan_paper_trade,
)
from crypto_signal.paper.sizing import (
    PaperPositionSizingDecision,
    PaperPositionSizingStatus,
)
from crypto_signal.paper.state import PaperFundState

__all__ = [
    "PAPER_PRETRADE_BRIDGE_POLICY_VERSION",
    "REAL_CAPITAL",
    "PaperPretradeDecision",
    "PaperPretradeError",
    "PaperPretradeReason",
    "PaperPretradeStatus",
    "prepare_paper_trade_plan",
]

PAPER_PRETRADE_BRIDGE_POLICY_VERSION = "paper_pretrade_bridge_policy.v1"


class PaperPretradeError(ValueError):
    """Raised when immutable pre-trade inputs do not reconcile exactly."""


class PaperPretradeStatus(StrEnum):
    PLANNED = "planned"
    REJECTED = "rejected"


class PaperPretradeReason(StrEnum):
    PLANNED = "planned"
    UPSTREAM_SIZING_REJECTED = "upstream_sizing_rejected"
    ROUNDED_TO_ZERO = "rounded_to_zero"
    BELOW_MINIMUM_QUANTITY = "below_minimum_quantity"
    BELOW_MINIMUM_NOTIONAL = "below_minimum_notional"
    EXIT_STEP_MISMATCH = "exit_step_mismatch"
    PLANNER_REJECTED = "planner_rejected"


@dataclass(frozen=True, slots=True)
class PaperPretradeDecision:
    """Auditable result before simulated execution."""

    pretrade_identity: str
    policy_version: str
    status: PaperPretradeStatus
    reason_code: PaperPretradeReason
    action: PaperAction
    symbol: PaperSymbol
    sizing_identity: str
    execution_input_identity: str
    execution_snapshot_identity: str
    raw_quantity: Decimal | None
    planned_quantity: Decimal | None
    reference_price: Decimal
    cost_budget_usdt: Decimal
    plan: PaperTradePlan | None
    rejection_detail: str | None
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if not self.policy_version.strip():
            raise ValueError("pretrade policy version must be non-empty")
        if self.action not in {PaperAction.BUY, PaperAction.EXIT}:
            raise ValueError("pretrade supports BUY or EXIT only")
        if self.reference_price <= Decimal(0):
            raise ValueError("reference_price must be positive")
        if self.cost_budget_usdt < Decimal(0):
            raise ValueError("cost_budget_usdt cannot be negative")
        for label, value in (
            ("sizing_identity", self.sizing_identity),
            ("execution_input_identity", self.execution_input_identity),
            ("execution_snapshot_identity", self.execution_snapshot_identity),
            ("pretrade_identity", self.pretrade_identity),
        ):
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise ValueError(f"{label} must be SHA256")
        if self.status is PaperPretradeStatus.PLANNED:
            if self.reason_code is not PaperPretradeReason.PLANNED:
                raise ValueError("PLANNED status requires PLANNED reason")
            if self.plan is None:
                raise ValueError("PLANNED status requires a paper plan")
            if self.planned_quantity is None or self.planned_quantity <= Decimal(0):
                raise ValueError("PLANNED status requires positive quantity")
            if self.rejection_detail is not None:
                raise ValueError("PLANNED status cannot carry rejection detail")
            if self.plan.quantity != self.planned_quantity:
                raise ValueError("paper plan quantity mismatch")
            if self.plan.cost_budget_usdt != self.cost_budget_usdt:
                raise ValueError("paper plan cost budget mismatch")
        else:
            if self.plan is not None:
                raise ValueError("REJECTED status cannot carry a paper plan")
            if self.planned_quantity is not None:
                raise ValueError("REJECTED status cannot carry planned quantity")
            if self.reason_code is PaperPretradeReason.PLANNED:
                raise ValueError("REJECTED status cannot use PLANNED reason")
            if not self.rejection_detail:
                raise ValueError("REJECTED status requires rejection detail")
        expected = compute_pretrade_identity(
            policy_version=self.policy_version,
            status=self.status,
            reason_code=self.reason_code,
            action=self.action,
            symbol=self.symbol,
            sizing_identity=self.sizing_identity,
            execution_input_identity=self.execution_input_identity,
            execution_snapshot_identity=self.execution_snapshot_identity,
            raw_quantity=self.raw_quantity,
            planned_quantity=self.planned_quantity,
            reference_price=self.reference_price,
            cost_budget_usdt=self.cost_budget_usdt,
            plan_identity=None if self.plan is None else self.plan.plan_identity,
            rejection_detail=self.rejection_detail,
        )
        if self.pretrade_identity != expected:
            raise ValueError("pretrade identity mismatch")


def compute_pretrade_identity(
    *,
    policy_version: str,
    status: PaperPretradeStatus,
    reason_code: PaperPretradeReason,
    action: PaperAction,
    symbol: PaperSymbol,
    sizing_identity: str,
    execution_input_identity: str,
    execution_snapshot_identity: str,
    raw_quantity: Decimal | None,
    planned_quantity: Decimal | None,
    reference_price: Decimal,
    cost_budget_usdt: Decimal,
    plan_identity: str | None,
    rejection_detail: str | None,
) -> str:
    return canonical_sha256(
        {
            "action": action.value,
            "cost_budget_usdt": cost_budget_usdt,
            "execution_input_identity": execution_input_identity,
            "execution_snapshot_identity": execution_snapshot_identity,
            "plan_identity": plan_identity,
            "planned_quantity": planned_quantity,
            "policy_version": policy_version,
            "pretrade_reason": reason_code.value,
            "pretrade_status": status.value,
            "raw_quantity": raw_quantity,
            "reference_price": reference_price,
            "rejection_detail": rejection_detail,
            "sizing_identity": sizing_identity,
            "symbol": symbol.value,
        }
    )


def prepare_paper_trade_plan(
    *,
    state: PaperFundState,
    sizing: PaperPositionSizingDecision,
    execution_input: FrozenPaperExecutionInput,
    execution_snapshot: FrozenExecutionSnapshot,
    planned_at_ms: int,
    mark_prices: Mapping[PaperSymbol, Decimal] | None = None,
) -> PaperPretradeDecision:
    """Round conservatively, budget explicit costs and invoke paper planner."""
    _validate_lineage(
        state=state,
        sizing=sizing,
        execution_input=execution_input,
        execution_snapshot=execution_snapshot,
    )
    if planned_at_ms < 0:
        raise PaperPretradeError("planned_at_ms must be non-negative")

    if sizing.status is PaperPositionSizingStatus.REJECTED:
        return _rejected(
            sizing=sizing,
            execution_input=execution_input,
            execution_snapshot=execution_snapshot,
            reason_code=PaperPretradeReason.UPSTREAM_SIZING_REJECTED,
            detail=f"sizing rejected: {sizing.reason_code.value}",
        )

    raw_quantity = sizing.raw_quantity
    if raw_quantity is None or raw_quantity <= Decimal(0):
        raise PaperPretradeError("SIZED input lacks positive raw quantity")

    if sizing.action is PaperAction.EXIT:
        steps = raw_quantity / execution_snapshot.quantity_step
        if steps != steps.to_integral_value(rounding=ROUND_DOWN):
            return _rejected(
                sizing=sizing,
                execution_input=execution_input,
                execution_snapshot=execution_snapshot,
                reason_code=PaperPretradeReason.EXIT_STEP_MISMATCH,
                detail="full EXIT quantity is not an exact frozen venue step",
            )
        quantity = raw_quantity
    else:
        steps = (raw_quantity / execution_snapshot.quantity_step).to_integral_value(
            rounding=ROUND_DOWN
        )
        quantity = steps * execution_snapshot.quantity_step
        if quantity <= Decimal(0):
            return _rejected(
                sizing=sizing,
                execution_input=execution_input,
                execution_snapshot=execution_snapshot,
                reason_code=PaperPretradeReason.ROUNDED_TO_ZERO,
                detail="BUY quantity rounds to zero under frozen venue step",
            )

    if quantity > raw_quantity:
        raise PaperPretradeError("venue rounding must never increase quantity")
    if quantity < execution_snapshot.min_quantity:
        return _rejected(
            sizing=sizing,
            execution_input=execution_input,
            execution_snapshot=execution_snapshot,
            reason_code=PaperPretradeReason.BELOW_MINIMUM_QUANTITY,
            detail="rounded quantity is below frozen minimum quantity",
        )

    reference_price = execution_input.reference_price
    reference_notional = quantity * reference_price
    if reference_notional < execution_snapshot.min_notional_usdt:
        return _rejected(
            sizing=sizing,
            execution_input=execution_input,
            execution_snapshot=execution_snapshot,
            reason_code=PaperPretradeReason.BELOW_MINIMUM_NOTIONAL,
            detail="rounded reference notional is below frozen minimum notional",
        )

    cost_budget = _exact_simulator_cost_budget(
        action=sizing.action,
        quantity=quantity,
        reference_price=reference_price,
        snapshot=execution_snapshot,
    )
    reason = (
        f"autonomy-pretrade:{sizing.reason_code.value}"
        f"|sizing:{sizing.sizing_identity}"
        f"|execution_input:{execution_input.input_identity}"
        f"|execution_snapshot:{execution_snapshot.snapshot_identity}"
    )
    invalidation_context = (
        f"conservative_invalidation={sizing.conservative_invalidation_price}"
        if sizing.action is PaperAction.BUY
        else "full_exit_on_accepted_bearish_consensus"
    )

    try:
        plan = plan_paper_trade(
            state=state,
            planned_at_ms=planned_at_ms,
            action=sizing.action,
            symbol=sizing.symbol,
            quantity=quantity,
            reference_price=reference_price,
            cost_budget_usdt=cost_budget,
            reason=reason,
            invalidation_context=invalidation_context,
            mark_prices=mark_prices,
        )
    except PaperPlanRejectedError as exc:
        return _rejected(
            sizing=sizing,
            execution_input=execution_input,
            execution_snapshot=execution_snapshot,
            reason_code=PaperPretradeReason.PLANNER_REJECTED,
            detail=str(exc),
            cost_budget_usdt=cost_budget,
        )

    return _decision(
        status=PaperPretradeStatus.PLANNED,
        reason_code=PaperPretradeReason.PLANNED,
        sizing=sizing,
        execution_input=execution_input,
        execution_snapshot=execution_snapshot,
        raw_quantity=raw_quantity,
        planned_quantity=quantity,
        cost_budget_usdt=cost_budget,
        plan=plan,
        rejection_detail=None,
    )


def _validate_lineage(
    *,
    state: PaperFundState,
    sizing: PaperPositionSizingDecision,
    execution_input: FrozenPaperExecutionInput,
    execution_snapshot: FrozenExecutionSnapshot,
) -> None:
    if (
        state.real_capital != REAL_CAPITAL
        or sizing.real_capital != REAL_CAPITAL
        or execution_input.real_capital != REAL_CAPITAL
        or execution_snapshot.real_capital != REAL_CAPITAL
    ):
        raise PaperPretradeError("REAL_CAPITAL must remain 0")
    if sizing.action is not execution_input.candidate_action:
        raise PaperPretradeError("sizing/execution-input action mismatch")
    if sizing.symbol is not execution_input.symbol:
        raise PaperPretradeError("sizing/execution-input symbol mismatch")
    if sizing.execution_input_identity != execution_input.input_identity:
        raise PaperPretradeError("sizing execution-input identity mismatch")
    if sizing.reference_price != execution_input.reference_price:
        raise PaperPretradeError("sizing reference price mismatch")
    if execution_snapshot.symbol is not sizing.symbol:
        raise PaperPretradeError("execution snapshot symbol mismatch")
    if execution_snapshot.policy_version != state.execution_policy_version:
        raise PaperPretradeError("execution snapshot policy mismatch")
    if execution_snapshot.venue_reference != execution_input.venue_reference:
        raise PaperPretradeError(
            "execution snapshot is not bound to frozen execution input"
        )


def _exact_simulator_cost_budget(
    *,
    action: PaperAction,
    quantity: Decimal,
    reference_price: Decimal,
    snapshot: FrozenExecutionSnapshot,
) -> Decimal:
    adverse = snapshot.spread_rate + snapshot.slippage_rate
    if action is PaperAction.BUY:
        fill_price = reference_price * (Decimal(1) + adverse)
    elif action is PaperAction.EXIT:
        fill_price = reference_price * (Decimal(1) - adverse)
        if fill_price <= Decimal(0):
            raise PaperPretradeError("frozen costs produce non-positive EXIT fill")
    else:
        raise PaperPretradeError("pretrade supports BUY or EXIT only")
    reference_notional = quantity * reference_price
    fill_notional = quantity * fill_price
    fee_usdt = fill_notional * snapshot.fee_rate
    spread_usdt = reference_notional * snapshot.spread_rate
    slippage_usdt = reference_notional * snapshot.slippage_rate
    return fee_usdt + spread_usdt + slippage_usdt


def _rejected(
    *,
    sizing: PaperPositionSizingDecision,
    execution_input: FrozenPaperExecutionInput,
    execution_snapshot: FrozenExecutionSnapshot,
    reason_code: PaperPretradeReason,
    detail: str,
    cost_budget_usdt: Decimal = Decimal(0),
) -> PaperPretradeDecision:
    return _decision(
        status=PaperPretradeStatus.REJECTED,
        reason_code=reason_code,
        sizing=sizing,
        execution_input=execution_input,
        execution_snapshot=execution_snapshot,
        raw_quantity=sizing.raw_quantity,
        planned_quantity=None,
        cost_budget_usdt=cost_budget_usdt,
        plan=None,
        rejection_detail=detail,
    )


def _decision(
    *,
    status: PaperPretradeStatus,
    reason_code: PaperPretradeReason,
    sizing: PaperPositionSizingDecision,
    execution_input: FrozenPaperExecutionInput,
    execution_snapshot: FrozenExecutionSnapshot,
    raw_quantity: Decimal | None,
    planned_quantity: Decimal | None,
    cost_budget_usdt: Decimal,
    plan: PaperTradePlan | None,
    rejection_detail: str | None,
) -> PaperPretradeDecision:
    identity = compute_pretrade_identity(
        policy_version=PAPER_PRETRADE_BRIDGE_POLICY_VERSION,
        status=status,
        reason_code=reason_code,
        action=sizing.action,
        symbol=sizing.symbol,
        sizing_identity=sizing.sizing_identity,
        execution_input_identity=execution_input.input_identity,
        execution_snapshot_identity=execution_snapshot.snapshot_identity,
        raw_quantity=raw_quantity,
        planned_quantity=planned_quantity,
        reference_price=execution_input.reference_price,
        cost_budget_usdt=cost_budget_usdt,
        plan_identity=None if plan is None else plan.plan_identity,
        rejection_detail=rejection_detail,
    )
    return PaperPretradeDecision(
        pretrade_identity=identity,
        policy_version=PAPER_PRETRADE_BRIDGE_POLICY_VERSION,
        status=status,
        reason_code=reason_code,
        action=sizing.action,
        symbol=sizing.symbol,
        sizing_identity=sizing.sizing_identity,
        execution_input_identity=execution_input.input_identity,
        execution_snapshot_identity=execution_snapshot.snapshot_identity,
        raw_quantity=raw_quantity,
        planned_quantity=planned_quantity,
        reference_price=execution_input.reference_price,
        cost_budget_usdt=cost_budget_usdt,
        plan=plan,
        rejection_detail=rejection_detail,
        real_capital=REAL_CAPITAL,
    )
