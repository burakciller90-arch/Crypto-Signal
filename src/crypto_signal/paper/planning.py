"""Conservative virtual trade planning for the paper fund.

A plan is intent only: it never appends to the ledger and never contacts an
exchange. REAL_CAPITAL remains 0. No leverage, borrowing, shorting,
derivatives, or martingale.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.models import (
    PAPER_RISK_POLICY_VERSION,
    PERMITTED_ACTIONS,
    PERMITTED_SYMBOLS,
    REAL_CAPITAL,
    PaperAction,
    PaperPosition,
    PaperSymbol,
    normalize_positions,
)
from crypto_signal.paper.state import PaperFundState

__all__ = [
    "DEFAULT_MAX_GROSS_EXPOSURE_FRACTION",
    "DEFAULT_MAX_POSITION_CONCENTRATION",
    "DEFAULT_MIN_CASH_RESERVE_USDT",
    "REAL_CAPITAL",
    "PaperPlanRejectedError",
    "PaperRiskPolicy",
    "PaperTradePlan",
    "compute_trade_plan_identity",
    "default_conservative_risk_policy",
    "plan_hold_cash",
    "plan_or_hold_on_missing_evidence",
    "plan_paper_trade",
]

# Explicit conservative v1 defaults (Decimal, versioned via policy.version).
DEFAULT_MAX_POSITION_CONCENTRATION = Decimal("0.25")
DEFAULT_MIN_CASH_RESERVE_USDT = Decimal("20.00")
DEFAULT_MAX_GROSS_EXPOSURE_FRACTION = Decimal("0.50")


class PaperPlanRejectedError(ValueError):
    """Raised when a virtual plan violates cash, holdings, or risk policy."""


@dataclass(frozen=True, slots=True)
class PaperRiskPolicy:
    """Versioned conservative risk limits for virtual paper planning."""

    version: str
    max_position_concentration: Decimal
    min_cash_reserve_usdt: Decimal
    max_gross_exposure_fraction: Decimal
    allow_leverage: bool = False
    allow_borrowing: bool = False
    allow_shorting: bool = False
    allow_derivatives: bool = False
    allow_martingale: bool = False

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("risk policy version must be non-empty")
        for label, value in (
            ("max_position_concentration", self.max_position_concentration),
            ("min_cash_reserve_usdt", self.min_cash_reserve_usdt),
            ("max_gross_exposure_fraction", self.max_gross_exposure_fraction),
        ):
            if not isinstance(value, Decimal):
                raise TypeError(f"{label} must be Decimal")
            if value.is_nan() or value.is_infinite():
                raise ValueError(f"{label} must be a finite Decimal")
            if value < Decimal(0):
                raise ValueError(f"{label} cannot be negative")
        if self.max_position_concentration > Decimal(1):
            raise ValueError("max_position_concentration cannot exceed 1")
        if self.max_gross_exposure_fraction > Decimal(1):
            raise ValueError("max_gross_exposure_fraction cannot exceed 1")
        if self.allow_leverage or self.allow_borrowing or self.allow_shorting:
            raise ValueError("v1 risk policy forbids leverage, borrowing, and shorting")
        if self.allow_derivatives or self.allow_martingale:
            raise ValueError("v1 risk policy forbids derivatives and martingale")


@dataclass(frozen=True, slots=True)
class PaperTradePlan:
    """Virtual trade intent — not a ledger mutation and not an exchange order."""

    plan_identity: str
    fund_identity: str
    planned_at_ms: int
    action: PaperAction
    symbol: PaperSymbol | None
    quantity: Decimal | None
    reference_price: Decimal | None
    reason: str
    invalidation_context: str
    virtual_notional_usdt: Decimal
    cost_budget_usdt: Decimal
    projected_cash_usdt: Decimal
    projected_quantity: Decimal | None
    projected_positions: tuple[PaperPosition, ...]
    risk_policy_version: str
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.action not in PERMITTED_ACTIONS:
            raise ValueError(f"action not permitted: {self.action}")
        if self.projected_cash_usdt < Decimal(0):
            raise ValueError("projected_cash_usdt cannot be negative")
        if self.cost_budget_usdt < Decimal(0):
            raise ValueError("cost_budget_usdt cannot be negative")
        if self.virtual_notional_usdt < Decimal(0):
            raise ValueError("virtual_notional_usdt cannot be negative")
        if normalize_positions(self.projected_positions) != self.projected_positions:
            raise ValueError("projected_positions must be normalized")
        if self.plan_identity != compute_trade_plan_identity(
            fund_identity=self.fund_identity,
            planned_at_ms=self.planned_at_ms,
            action=self.action,
            symbol=self.symbol,
            quantity=self.quantity,
            reference_price=self.reference_price,
            reason=self.reason,
            invalidation_context=self.invalidation_context,
            virtual_notional_usdt=self.virtual_notional_usdt,
            cost_budget_usdt=self.cost_budget_usdt,
            projected_cash_usdt=self.projected_cash_usdt,
            projected_quantity=self.projected_quantity,
            projected_positions=self.projected_positions,
            risk_policy_version=self.risk_policy_version,
        ):
            raise ValueError("trade plan identity mismatch")


def default_conservative_risk_policy() -> PaperRiskPolicy:
    """Return the deliberately conservative, versioned v1 risk policy."""
    return PaperRiskPolicy(
        version=PAPER_RISK_POLICY_VERSION,
        max_position_concentration=DEFAULT_MAX_POSITION_CONCENTRATION,
        min_cash_reserve_usdt=DEFAULT_MIN_CASH_RESERVE_USDT,
        max_gross_exposure_fraction=DEFAULT_MAX_GROSS_EXPOSURE_FRACTION,
        allow_leverage=False,
        allow_borrowing=False,
        allow_shorting=False,
        allow_derivatives=False,
        allow_martingale=False,
    )


def compute_trade_plan_identity(
    *,
    fund_identity: str,
    planned_at_ms: int,
    action: PaperAction,
    symbol: PaperSymbol | None,
    quantity: Decimal | None,
    reference_price: Decimal | None,
    reason: str,
    invalidation_context: str,
    virtual_notional_usdt: Decimal,
    cost_budget_usdt: Decimal,
    projected_cash_usdt: Decimal,
    projected_quantity: Decimal | None,
    projected_positions: tuple[PaperPosition, ...],
    risk_policy_version: str,
) -> str:
    return canonical_sha256(
        {
            "action": action.value,
            "cost_budget_usdt": cost_budget_usdt,
            "fund_identity": fund_identity,
            "invalidation_context": invalidation_context,
            "planned_at_ms": planned_at_ms,
            "projected_cash_usdt": projected_cash_usdt,
            "projected_positions": [
                {"quantity": item.quantity, "symbol": item.symbol.value}
                for item in projected_positions
            ],
            "projected_quantity": projected_quantity,
            "quantity": quantity,
            "reason": reason,
            "reference_price": reference_price,
            "risk_policy_version": risk_policy_version,
            "symbol": None if symbol is None else symbol.value,
            "virtual_notional_usdt": virtual_notional_usdt,
        }
    )


def plan_hold_cash(
    *,
    state: PaperFundState,
    planned_at_ms: int,
    reason: str,
    invalidation_context: str,
    risk_policy: PaperRiskPolicy | None = None,
) -> PaperTradePlan:
    """HOLD_CASH remains a valid professional allocation and requires no trade."""
    policy = risk_policy or default_conservative_risk_policy()
    if not reason.strip():
        raise PaperPlanRejectedError("reason must be non-empty")
    if not invalidation_context.strip():
        raise PaperPlanRejectedError("invalidation_context must be non-empty")
    if planned_at_ms < 0:
        raise PaperPlanRejectedError("planned_at_ms must be non-negative")
    return _build_plan(
        state=state,
        planned_at_ms=planned_at_ms,
        action=PaperAction.HOLD_CASH,
        symbol=None,
        quantity=None,
        reference_price=None,
        reason=reason,
        invalidation_context=invalidation_context,
        virtual_notional_usdt=Decimal(0),
        cost_budget_usdt=Decimal(0),
        projected_cash_usdt=state.cash_usdt,
        projected_quantity=None,
        projected_positions=state.positions,
        risk_policy_version=policy.version,
    )


def plan_paper_trade(
    *,
    state: PaperFundState,
    planned_at_ms: int,
    action: PaperAction,
    reason: str,
    invalidation_context: str,
    symbol: PaperSymbol | None = None,
    quantity: Decimal | None = None,
    reference_price: Decimal | None = None,
    cost_budget_usdt: Decimal = Decimal(0),
    mark_prices: Mapping[PaperSymbol, Decimal] | None = None,
    risk_policy: PaperRiskPolicy | None = None,
) -> PaperTradePlan:
    """Build a conservative virtual plan or reject explicitly.

    Missing prices/marks needed for a trade yield rejection (never fabricated
    certainty). Callers that prefer cash when evidence is absent should use
    ``plan_or_hold_on_missing_evidence``.
    """
    policy = risk_policy or default_conservative_risk_policy()
    if state.real_capital != REAL_CAPITAL:
        raise PaperPlanRejectedError("REAL_CAPITAL must remain 0")
    if not reason.strip():
        raise PaperPlanRejectedError("reason must be non-empty")
    if not invalidation_context.strip():
        raise PaperPlanRejectedError("invalidation_context must be non-empty")
    if planned_at_ms < 0:
        raise PaperPlanRejectedError("planned_at_ms must be non-negative")
    if not isinstance(cost_budget_usdt, Decimal):
        raise TypeError("cost_budget_usdt must be Decimal")
    if cost_budget_usdt < Decimal(0):
        raise PaperPlanRejectedError("cost_budget_usdt cannot be negative")
    if action not in PERMITTED_ACTIONS:
        raise PaperPlanRejectedError(f"action not permitted: {action}")

    if action is PaperAction.HOLD_CASH:
        if symbol is not None or quantity is not None or reference_price is not None:
            raise PaperPlanRejectedError(
                "HOLD_CASH must not specify symbol, quantity, or reference_price"
            )
        if cost_budget_usdt != Decimal(0):
            raise PaperPlanRejectedError("HOLD_CASH requires zero cost budget")
        return plan_hold_cash(
            state=state,
            planned_at_ms=planned_at_ms,
            reason=reason,
            invalidation_context=invalidation_context,
            risk_policy=policy,
        )

    if symbol is None or symbol not in PERMITTED_SYMBOLS:
        raise PaperPlanRejectedError("trade action requires a permitted symbol")
    if quantity is None or quantity <= Decimal(0):
        raise PaperPlanRejectedError("trade quantity must be positive")
    if reference_price is None or reference_price <= Decimal(0):
        raise PaperPlanRejectedError(
            "missing or non-positive reference_price — refusing fabricated certainty"
        )

    holdings = _quantity_held(state.positions, symbol)
    notional = quantity * reference_price

    if action is PaperAction.BUY:
        return _plan_buy(
            state=state,
            planned_at_ms=planned_at_ms,
            symbol=symbol,
            quantity=quantity,
            reference_price=reference_price,
            notional=notional,
            cost_budget_usdt=cost_budget_usdt,
            reason=reason,
            invalidation_context=invalidation_context,
            mark_prices=mark_prices or {},
            policy=policy,
            holdings=holdings,
        )

    if action in {PaperAction.REDUCE, PaperAction.EXIT}:
        return _plan_reduce_or_exit(
            state=state,
            planned_at_ms=planned_at_ms,
            action=action,
            symbol=symbol,
            quantity=quantity,
            reference_price=reference_price,
            notional=notional,
            cost_budget_usdt=cost_budget_usdt,
            reason=reason,
            invalidation_context=invalidation_context,
            policy=policy,
            holdings=holdings,
        )

    raise PaperPlanRejectedError(f"unsupported paper action: {action}")


def plan_or_hold_on_missing_evidence(
    *,
    state: PaperFundState,
    planned_at_ms: int,
    action: PaperAction | None,
    reason: str,
    invalidation_context: str,
    symbol: PaperSymbol | None = None,
    quantity: Decimal | None = None,
    reference_price: Decimal | None = None,
    cost_budget_usdt: Decimal = Decimal(0),
    mark_prices: Mapping[PaperSymbol, Decimal] | None = None,
    risk_policy: PaperRiskPolicy | None = None,
) -> PaperTradePlan:
    """Unknown/missing trade evidence yields HOLD_CASH rather than invented certainty."""
    policy = risk_policy or default_conservative_risk_policy()
    if action is None:
        return plan_hold_cash(
            state=state,
            planned_at_ms=planned_at_ms,
            reason=reason or "missing action evidence — holding cash",
            invalidation_context=invalidation_context
            or "no actionable evidence",
            risk_policy=policy,
        )
    if action is not PaperAction.HOLD_CASH and (
        reference_price is None or reference_price <= Decimal(0)
    ):
        return plan_hold_cash(
            state=state,
            planned_at_ms=planned_at_ms,
            reason="missing reference price evidence — holding cash",
            invalidation_context=invalidation_context
            or "reference price unavailable",
            risk_policy=policy,
        )
    if action is PaperAction.BUY and not _marks_sufficient_for_buy(
        state=state,
        symbol=symbol,
        mark_prices=mark_prices or {},
        reference_price=reference_price,
    ):
        return plan_hold_cash(
            state=state,
            planned_at_ms=planned_at_ms,
            reason="missing mark-price evidence for risk checks — holding cash",
            invalidation_context=invalidation_context
            or "mark prices unavailable",
            risk_policy=policy,
        )
    return plan_paper_trade(
        state=state,
        planned_at_ms=planned_at_ms,
        action=action,
        reason=reason,
        invalidation_context=invalidation_context,
        symbol=symbol,
        quantity=quantity,
        reference_price=reference_price,
        cost_budget_usdt=cost_budget_usdt,
        mark_prices=mark_prices,
        risk_policy=policy,
    )


def _plan_buy(
    *,
    state: PaperFundState,
    planned_at_ms: int,
    symbol: PaperSymbol,
    quantity: Decimal,
    reference_price: Decimal,
    notional: Decimal,
    cost_budget_usdt: Decimal,
    reason: str,
    invalidation_context: str,
    mark_prices: Mapping[PaperSymbol, Decimal],
    policy: PaperRiskPolicy,
    holdings: Decimal,
) -> PaperTradePlan:
    total_debit = notional + cost_budget_usdt
    if total_debit > state.cash_usdt:
        raise PaperPlanRejectedError(
            "BUY exceeds available cash including explicit cost budget"
        )
    projected_cash = state.cash_usdt - total_debit
    if projected_cash < policy.min_cash_reserve_usdt:
        raise PaperPlanRejectedError(
            "BUY would breach minimum cash reserve"
        )

    nav_before_costs = _estimate_nav(
        state=state,
        mark_prices=mark_prices,
        buy_symbol=symbol,
        buy_price=reference_price,
    )
    projected_nav = nav_before_costs - cost_budget_usdt
    projected_qty = holdings + quantity
    projected_positions = _replace_quantity(state.positions, symbol, projected_qty)
    position_notional = projected_qty * reference_price
    if projected_nav <= Decimal(0):
        raise PaperPlanRejectedError("projected NAV must be positive for risk checks")
    if position_notional / projected_nav > policy.max_position_concentration:
        raise PaperPlanRejectedError(
            "BUY would breach position concentration ceiling"
        )
    invested_after = _gross_exposure(
        positions=projected_positions,
        mark_prices=_marks_with_reference(mark_prices, symbol, reference_price),
    )
    if invested_after / projected_nav > policy.max_gross_exposure_fraction:
        raise PaperPlanRejectedError(
            "BUY would breach maximum gross exposure fraction"
        )

    return _build_plan(
        state=state,
        planned_at_ms=planned_at_ms,
        action=PaperAction.BUY,
        symbol=symbol,
        quantity=quantity,
        reference_price=reference_price,
        reason=reason,
        invalidation_context=invalidation_context,
        virtual_notional_usdt=notional,
        cost_budget_usdt=cost_budget_usdt,
        projected_cash_usdt=projected_cash,
        projected_quantity=projected_qty,
        projected_positions=projected_positions,
        risk_policy_version=policy.version,
    )


def _plan_reduce_or_exit(
    *,
    state: PaperFundState,
    planned_at_ms: int,
    action: PaperAction,
    symbol: PaperSymbol,
    quantity: Decimal,
    reference_price: Decimal,
    notional: Decimal,
    cost_budget_usdt: Decimal,
    reason: str,
    invalidation_context: str,
    policy: PaperRiskPolicy,
    holdings: Decimal,
) -> PaperTradePlan:
    if quantity > holdings:
        raise PaperPlanRejectedError(
            f"{action.value} quantity exceeds virtual holdings"
        )
    if notional < cost_budget_usdt:
        raise PaperPlanRejectedError(
            f"{action.value} cost budget exceeds virtual notional proceeds"
        )
    if action is PaperAction.EXIT and quantity != holdings:
        raise PaperPlanRejectedError(
            "EXIT must close the entire virtual holding for the symbol"
        )
    projected_cash = state.cash_usdt + notional - cost_budget_usdt
    projected_qty = holdings - quantity
    projected_positions = _replace_quantity(state.positions, symbol, projected_qty)
    return _build_plan(
        state=state,
        planned_at_ms=planned_at_ms,
        action=action,
        symbol=symbol,
        quantity=quantity,
        reference_price=reference_price,
        reason=reason,
        invalidation_context=invalidation_context,
        virtual_notional_usdt=notional,
        cost_budget_usdt=cost_budget_usdt,
        projected_cash_usdt=projected_cash,
        projected_quantity=projected_qty if projected_qty > Decimal(0) else None,
        projected_positions=projected_positions,
        risk_policy_version=policy.version,
    )


def _build_plan(
    *,
    state: PaperFundState,
    planned_at_ms: int,
    action: PaperAction,
    symbol: PaperSymbol | None,
    quantity: Decimal | None,
    reference_price: Decimal | None,
    reason: str,
    invalidation_context: str,
    virtual_notional_usdt: Decimal,
    cost_budget_usdt: Decimal,
    projected_cash_usdt: Decimal,
    projected_quantity: Decimal | None,
    projected_positions: tuple[PaperPosition, ...],
    risk_policy_version: str,
) -> PaperTradePlan:
    identity = compute_trade_plan_identity(
        fund_identity=state.fund_identity,
        planned_at_ms=planned_at_ms,
        action=action,
        symbol=symbol,
        quantity=quantity,
        reference_price=reference_price,
        reason=reason,
        invalidation_context=invalidation_context,
        virtual_notional_usdt=virtual_notional_usdt,
        cost_budget_usdt=cost_budget_usdt,
        projected_cash_usdt=projected_cash_usdt,
        projected_quantity=projected_quantity,
        projected_positions=projected_positions,
        risk_policy_version=risk_policy_version,
    )
    return PaperTradePlan(
        plan_identity=identity,
        fund_identity=state.fund_identity,
        planned_at_ms=planned_at_ms,
        action=action,
        symbol=symbol,
        quantity=quantity,
        reference_price=reference_price,
        reason=reason,
        invalidation_context=invalidation_context,
        virtual_notional_usdt=virtual_notional_usdt,
        cost_budget_usdt=cost_budget_usdt,
        projected_cash_usdt=projected_cash_usdt,
        projected_quantity=projected_quantity,
        projected_positions=projected_positions,
        risk_policy_version=risk_policy_version,
        real_capital=REAL_CAPITAL,
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


def _marks_with_reference(
    mark_prices: Mapping[PaperSymbol, Decimal],
    symbol: PaperSymbol,
    reference_price: Decimal,
) -> dict[PaperSymbol, Decimal]:
    merged = dict(mark_prices)
    merged[symbol] = reference_price
    return merged


def _estimate_nav(
    *,
    state: PaperFundState,
    mark_prices: Mapping[PaperSymbol, Decimal],
    buy_symbol: PaperSymbol,
    buy_price: Decimal,
) -> Decimal:
    marks = _marks_with_reference(mark_prices, buy_symbol, buy_price)
    for position in state.positions:
        if position.symbol not in marks or marks[position.symbol] <= Decimal(0):
            raise PaperPlanRejectedError(
                "missing mark-price evidence for concentration/NAV checks"
            )
    return state.cash_usdt + _gross_exposure(state.positions, marks)


def _gross_exposure(
    positions: tuple[PaperPosition, ...],
    mark_prices: Mapping[PaperSymbol, Decimal],
) -> Decimal:
    total = Decimal(0)
    for position in positions:
        price = mark_prices.get(position.symbol)
        if price is None or price <= Decimal(0):
            raise PaperPlanRejectedError(
                "missing mark-price evidence for exposure checks"
            )
        total += position.quantity * price
    return total


def _marks_sufficient_for_buy(
    *,
    state: PaperFundState,
    symbol: PaperSymbol | None,
    mark_prices: Mapping[PaperSymbol, Decimal],
    reference_price: Decimal | None,
) -> bool:
    if symbol is None or reference_price is None or reference_price <= Decimal(0):
        return False
    marks = _marks_with_reference(mark_prices, symbol, reference_price)
    return all(
        position.symbol in marks and marks[position.symbol] > Decimal(0)
        for position in state.positions
    )
