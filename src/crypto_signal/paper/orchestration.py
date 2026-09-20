"""Pure paper-fund plan -> immutable record orchestration.

No ledger writes, network calls, exchange endpoints, credentials, or real capital.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from crypto_signal.paper.execution import (
    FrozenExecutionSnapshot,
    PaperExecutionRejectedError,
    SimulatedExecutionResult,
    simulate_paper_fill,
    total_simulated_cost_usdt,
)
from crypto_signal.paper.models import (
    PAPER_EXECUTION_POLICY_VERSION,
    PAPER_RISK_POLICY_VERSION,
    REAL_CAPITAL,
    DecisionIntentRecord,
    PaperAction,
    PaperPosition,
    PaperSymbol,
    PositionCashMutationRecord,
    SimulatedFillRecord,
    build_decision_intent,
    build_position_cash_mutation,
    normalize_positions,
)
from crypto_signal.paper.planning import PaperTradePlan
from crypto_signal.paper.state import PaperFundState

__all__ = [
    "REAL_CAPITAL",
    "PaperOrchestrationBundle",
    "PaperOrchestrationRejectedError",
    "orchestrate_paper_plan",
]


class PaperOrchestrationRejectedError(ValueError):
    """Raised when state, plan and execution snapshot cannot reconcile."""


@dataclass(frozen=True, slots=True)
class PaperOrchestrationBundle:
    """Immutable in-memory record bundle. It never writes to a ledger."""

    decision: DecisionIntentRecord
    fill: SimulatedFillRecord | None
    mutation: PositionCashMutationRecord | None
    execution: SimulatedExecutionResult
    execution_snapshot_identity: str | None
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.decision.action is PaperAction.HOLD_CASH:
            if self.fill is not None or self.mutation is not None:
                raise ValueError("HOLD_CASH bundle cannot invent fill or mutation")
            if self.execution_snapshot_identity is not None:
                raise ValueError("HOLD_CASH bundle cannot bind execution snapshot")
            return
        if self.fill is None or self.mutation is None:
            raise ValueError("trade bundle requires fill and mutation")
        if self.execution_snapshot_identity is None:
            raise ValueError("trade bundle requires execution snapshot identity")
        if self.fill.decision_identity != self.decision.record_identity:
            raise ValueError("fill must reference decision identity")
        if self.mutation.source_identity != self.fill.record_identity:
            raise ValueError("mutation must reference fill identity")
        if self.execution.snapshot_identity != self.execution_snapshot_identity:
            raise ValueError("execution snapshot identity mismatch in bundle")


def orchestrate_paper_plan(
    *,
    state: PaperFundState,
    plan: PaperTradePlan,
    snapshot: FrozenExecutionSnapshot | None,
) -> PaperOrchestrationBundle:
    """Materialize deterministic virtual records from accepted state + plan."""
    _validate_policy_lineage(state=state, plan=plan, snapshot=snapshot)
    _validate_state_plan_identity(state=state, plan=plan)

    decision = build_decision_intent(
        fund_identity=plan.fund_identity,
        decided_at_ms=plan.planned_at_ms,
        action=plan.action,
        reason=plan.reason,
        invalidation_context=plan.invalidation_context,
        symbol=plan.symbol,
        quantity=plan.quantity,
        reference_price=plan.reference_price,
    )
    if decision.risk_policy_version != plan.risk_policy_version:
        raise PaperOrchestrationRejectedError(
            "decision risk policy version must equal plan risk policy version"
        )

    if plan.action is PaperAction.HOLD_CASH:
        _validate_hold_projection(state=state, plan=plan)
        try:
            execution = simulate_paper_fill(
                plan=plan,
                snapshot=None,
                decision_identity=decision.record_identity,
                filled_at_ms=plan.planned_at_ms,
            )
        except PaperExecutionRejectedError as exc:
            raise PaperOrchestrationRejectedError(str(exc)) from exc
        return PaperOrchestrationBundle(
            decision=decision,
            fill=None,
            mutation=None,
            execution=execution,
            execution_snapshot_identity=None,
            real_capital=REAL_CAPITAL,
        )

    if snapshot is None:
        raise PaperOrchestrationRejectedError(
            "trade action requires frozen execution snapshot"
        )
    if plan.symbol is None or plan.symbol is not snapshot.symbol:
        raise PaperOrchestrationRejectedError(
            "plan symbol must match execution snapshot symbol"
        )

    try:
        execution = simulate_paper_fill(
            plan=plan,
            snapshot=snapshot,
            decision_identity=decision.record_identity,
            filled_at_ms=plan.planned_at_ms,
        )
    except PaperExecutionRejectedError as exc:
        raise PaperOrchestrationRejectedError(str(exc)) from exc

    fill = execution.fill
    if fill is None or execution.costs is None:
        raise PaperOrchestrationRejectedError("trade execution did not produce fill")
    if fill.venue_reference != snapshot.execution_reference:
        raise PaperOrchestrationRejectedError(
            "fill provenance is not bound to frozen execution snapshot"
        )
    if fill.costs.execution_policy_version != snapshot.policy_version:
        raise PaperOrchestrationRejectedError(
            "fill execution policy version mismatch"
        )

    mutation = _build_mutation_from_fill(
        state=state,
        fill=fill,
        execution=execution,
        mutated_at_ms=plan.planned_at_ms,
    )
    _reconcile_plan_and_mutation(
        state=state,
        plan=plan,
        execution=execution,
        mutation=mutation,
    )
    return PaperOrchestrationBundle(
        decision=decision,
        fill=fill,
        mutation=mutation,
        execution=execution,
        execution_snapshot_identity=snapshot.snapshot_identity,
        real_capital=REAL_CAPITAL,
    )


def _validate_policy_lineage(
    *,
    state: PaperFundState,
    plan: PaperTradePlan,
    snapshot: FrozenExecutionSnapshot | None,
) -> None:
    if state.real_capital != REAL_CAPITAL or plan.real_capital != REAL_CAPITAL:
        raise PaperOrchestrationRejectedError("REAL_CAPITAL must remain 0")
    if state.risk_policy_version != PAPER_RISK_POLICY_VERSION:
        raise PaperOrchestrationRejectedError(
            "unsupported paper fund risk policy version"
        )
    if state.execution_policy_version != PAPER_EXECUTION_POLICY_VERSION:
        raise PaperOrchestrationRejectedError(
            "unsupported paper fund execution policy version"
        )
    if plan.risk_policy_version != state.risk_policy_version:
        raise PaperOrchestrationRejectedError(
            "plan risk policy version does not match paper fund"
        )
    if plan.action is PaperAction.HOLD_CASH:
        if snapshot is not None:
            raise PaperOrchestrationRejectedError(
                "HOLD_CASH must not supply execution snapshot"
            )
        return
    if snapshot is None:
        raise PaperOrchestrationRejectedError(
            "trade action requires frozen execution snapshot"
        )
    if snapshot.real_capital != REAL_CAPITAL:
        raise PaperOrchestrationRejectedError("REAL_CAPITAL must remain 0")
    if snapshot.policy_version != state.execution_policy_version:
        raise PaperOrchestrationRejectedError(
            "execution snapshot policy version does not match paper fund"
        )


def _validate_state_plan_identity(
    *,
    state: PaperFundState,
    plan: PaperTradePlan,
) -> None:
    if plan.fund_identity != state.fund_identity:
        raise PaperOrchestrationRejectedError(
            "plan fund identity must equal state fund identity"
        )
    if normalize_positions(state.positions) != state.positions:
        raise PaperOrchestrationRejectedError("state positions must be normalized")


def _validate_hold_projection(
    *,
    state: PaperFundState,
    plan: PaperTradePlan,
) -> None:
    if plan.symbol is not None or plan.quantity is not None or plan.reference_price is not None:
        raise PaperOrchestrationRejectedError("HOLD_CASH cannot specify trade fields")
    if plan.virtual_notional_usdt != Decimal(0) or plan.cost_budget_usdt != Decimal(0):
        raise PaperOrchestrationRejectedError("HOLD_CASH must have zero notional/cost")
    if plan.projected_cash_usdt != state.cash_usdt:
        raise PaperOrchestrationRejectedError(
            "HOLD_CASH projected cash must equal current cash"
        )
    if plan.projected_positions != state.positions:
        raise PaperOrchestrationRejectedError(
            "HOLD_CASH projected positions must equal current positions"
        )


def _build_mutation_from_fill(
    *,
    state: PaperFundState,
    fill: SimulatedFillRecord,
    execution: SimulatedExecutionResult,
    mutated_at_ms: int,
) -> PositionCashMutationRecord:
    holdings = _quantity_held(state.positions, fill.symbol)
    fee = fill.costs.fee_usdt

    if fill.action is PaperAction.BUY:
        cash_after = state.cash_usdt - execution.fill_notional_usdt - fee
        if cash_after < Decimal(0):
            raise PaperOrchestrationRejectedError("BUY cannot produce negative cash")
        quantity_after = holdings + fill.quantity
    elif fill.action in {PaperAction.REDUCE, PaperAction.EXIT}:
        if fill.quantity > holdings:
            raise PaperOrchestrationRejectedError(
                "REDUCE/EXIT cannot exceed virtual holdings"
            )
        cash_after = state.cash_usdt + execution.fill_notional_usdt - fee
        if cash_after < Decimal(0):
            raise PaperOrchestrationRejectedError(
                "sell-side mutation cannot produce negative cash"
            )
        quantity_after = holdings - fill.quantity
        if quantity_after < Decimal(0):
            raise PaperOrchestrationRejectedError(
                "REDUCE/EXIT cannot produce negative holdings"
            )
        if fill.action is PaperAction.EXIT and quantity_after != Decimal(0):
            raise PaperOrchestrationRejectedError(
                "EXIT must leave zero quantity for symbol"
            )
    else:
        raise PaperOrchestrationRejectedError(
            f"unsupported fill action: {fill.action}"
        )

    return build_position_cash_mutation(
        fund_identity=state.fund_identity,
        source_identity=fill.record_identity,
        mutated_at_ms=mutated_at_ms,
        cash_before_usdt=state.cash_usdt,
        cash_after_usdt=cash_after,
        positions_before=state.positions,
        positions_after=_replace_quantity(
            state.positions,
            fill.symbol,
            quantity_after,
        ),
    )


def _reconcile_plan_and_mutation(
    *,
    state: PaperFundState,
    plan: PaperTradePlan,
    execution: SimulatedExecutionResult,
    mutation: PositionCashMutationRecord,
) -> None:
    fill = execution.fill
    if fill is None:
        raise PaperOrchestrationRejectedError("trade reconciliation requires fill")
    if mutation.cash_before_usdt != state.cash_usdt:
        raise PaperOrchestrationRejectedError(
            "mutation before cash must equal supplied state"
        )
    if mutation.positions_before != state.positions:
        raise PaperOrchestrationRejectedError(
            "mutation before positions must equal supplied state"
        )
    if mutation.positions_after != plan.projected_positions:
        raise PaperOrchestrationRejectedError(
            "plan projected positions do not reconcile with execution"
        )
    if plan.virtual_notional_usdt != execution.reference_notional_usdt:
        raise PaperOrchestrationRejectedError(
            "plan virtual notional does not match reference notional"
        )
    if execution.total_cost_usdt != total_simulated_cost_usdt(fill.costs):
        raise PaperOrchestrationRejectedError(
            "simulated total cost is not reconstructable"
        )
    if execution.total_cost_usdt > plan.cost_budget_usdt:
        raise PaperOrchestrationRejectedError(
            "simulated costs exceed accepted plan cost budget"
        )

    if fill.action is PaperAction.BUY:
        budgeted_cash = (
            state.cash_usdt
            - execution.reference_notional_usdt
            - plan.cost_budget_usdt
        )
    else:
        budgeted_cash = (
            state.cash_usdt
            + execution.reference_notional_usdt
            - plan.cost_budget_usdt
        )
    if plan.projected_cash_usdt != budgeted_cash:
        raise PaperOrchestrationRejectedError(
            "plan projected cash is inconsistent with accepted budget"
        )
    if mutation.cash_after_usdt < plan.projected_cash_usdt:
        raise PaperOrchestrationRejectedError(
            "execution cash outcome is worse than accepted plan projection"
        )


def _quantity_held(
    positions: tuple[PaperPosition, ...],
    symbol: PaperSymbol,
) -> Decimal:
    for item in positions:
        if item.symbol is symbol:
            return item.quantity
    return Decimal(0)


def _replace_quantity(
    positions: tuple[PaperPosition, ...],
    symbol: PaperSymbol,
    quantity: Decimal,
) -> tuple[PaperPosition, ...]:
    mapping = {item.symbol: item.quantity for item in positions}
    mapping[symbol] = quantity
    return normalize_positions(mapping)
