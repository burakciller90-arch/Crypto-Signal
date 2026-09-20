"""Pure conservative paper position sizing.

Consumes an autonomy trade candidate, frozen execution reference, current paper
state and exact frozen SignalDecision lineage. Produces only a pre-venue,
pre-cost quantity. No ledger mutation, exchange/network access or fill.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.autonomy import PaperAutonomyDecision
from crypto_signal.paper.execution_input import FrozenPaperExecutionInput
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction, PaperSymbol
from crypto_signal.paper.state import PaperFundState
from crypto_signal.signals.models import SignalDecision, SignalDirection, SignalState

__all__ = [
    "PAPER_POSITION_SIZING_POLICY_VERSION",
    "REAL_CAPITAL",
    "PaperPositionSizingDecision",
    "PaperPositionSizingError",
    "PaperPositionSizingReason",
    "PaperPositionSizingStatus",
    "size_paper_candidate",
]

PAPER_POSITION_SIZING_POLICY_VERSION = "paper_position_sizing_policy.v1"
_CALCULATION_PRECISION = 50


class PaperPositionSizingError(ValueError):
    """Raised when sizing inputs do not share exact immutable lineage."""


class PaperPositionSizingStatus(StrEnum):
    SIZED = "sized"
    REJECTED = "rejected"


class PaperPositionSizingReason(StrEnum):
    BUY_RISK_SIZED = "buy_risk_sized"
    EXIT_FULL_POSITION = "exit_full_position"
    REFERENCE_OUTSIDE_ENTRY_ZONE = "reference_outside_entry_zone"
    REFERENCE_NOT_ABOVE_INVALIDATION = "reference_not_above_invalidation"
    NO_POSITION_TO_EXIT = "no_position_to_exit"


@dataclass(frozen=True, slots=True)
class PaperPositionSizingDecision:
    sizing_identity: str
    policy_version: str
    status: PaperPositionSizingStatus
    reason_code: PaperPositionSizingReason
    action: PaperAction
    symbol: PaperSymbol
    execution_input_identity: str
    source_freeze_identities: tuple[str, ...]
    reference_price: Decimal
    conservative_invalidation_price: Decimal | None
    risk_per_unit_usdt: Decimal
    max_position_risk_usdt: Decimal
    raw_quantity: Decimal | None
    venue_rule_check_required: bool
    cost_adjustment_required: bool
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.action not in {PaperAction.BUY, PaperAction.EXIT}:
            raise ValueError("sizing requires BUY or EXIT")
        if not self.policy_version.strip():
            raise ValueError("sizing policy version must be non-empty")
        if len(self.execution_input_identity) != 64:
            raise ValueError("execution_input_identity must be SHA256")
        if not self.source_freeze_identities:
            raise ValueError("sizing requires source signal identities")
        for label, value in (
            ("reference_price", self.reference_price),
            ("risk_per_unit_usdt", self.risk_per_unit_usdt),
            ("max_position_risk_usdt", self.max_position_risk_usdt),
        ):
            if not isinstance(value, Decimal):
                raise TypeError(f"{label} must be Decimal")
            if value.is_nan() or value.is_infinite() or value < Decimal(0):
                raise ValueError(f"{label} must be finite and non-negative")
        if self.reference_price <= Decimal(0):
            raise ValueError("reference_price must be positive")
        if (
            self.conservative_invalidation_price is not None
            and self.conservative_invalidation_price <= Decimal(0)
        ):
            raise ValueError("invalidation price must be positive")
        if self.status is PaperPositionSizingStatus.SIZED:
            if self.raw_quantity is None or self.raw_quantity <= Decimal(0):
                raise ValueError("SIZED result requires positive raw_quantity")
        elif self.raw_quantity is not None:
            raise ValueError("REJECTED result cannot carry raw_quantity")
        if self.action is PaperAction.BUY:
            if self.status is PaperPositionSizingStatus.SIZED:
                if self.conservative_invalidation_price is None:
                    raise ValueError("BUY sizing requires invalidation price")
                if self.risk_per_unit_usdt <= Decimal(0):
                    raise ValueError("BUY sizing requires positive risk per unit")
                if self.max_position_risk_usdt <= Decimal(0):
                    raise ValueError("BUY sizing requires positive max risk")
        else:
            if self.conservative_invalidation_price is not None:
                raise ValueError("EXIT sizing must not carry invalidation price")
            if self.risk_per_unit_usdt != Decimal(0):
                raise ValueError("EXIT sizing risk_per_unit must be zero")
            if self.max_position_risk_usdt != Decimal(0):
                raise ValueError("EXIT sizing max risk must be zero")
        expected = compute_position_sizing_identity(
            policy_version=self.policy_version,
            status=self.status,
            reason_code=self.reason_code,
            action=self.action,
            symbol=self.symbol,
            execution_input_identity=self.execution_input_identity,
            source_freeze_identities=self.source_freeze_identities,
            reference_price=self.reference_price,
            conservative_invalidation_price=self.conservative_invalidation_price,
            risk_per_unit_usdt=self.risk_per_unit_usdt,
            max_position_risk_usdt=self.max_position_risk_usdt,
            raw_quantity=self.raw_quantity,
            venue_rule_check_required=self.venue_rule_check_required,
            cost_adjustment_required=self.cost_adjustment_required,
        )
        if self.sizing_identity != expected:
            raise ValueError("position sizing identity mismatch")


def compute_position_sizing_identity(
    *,
    policy_version: str,
    status: PaperPositionSizingStatus,
    reason_code: PaperPositionSizingReason,
    action: PaperAction,
    symbol: PaperSymbol,
    execution_input_identity: str,
    source_freeze_identities: tuple[str, ...],
    reference_price: Decimal,
    conservative_invalidation_price: Decimal | None,
    risk_per_unit_usdt: Decimal,
    max_position_risk_usdt: Decimal,
    raw_quantity: Decimal | None,
    venue_rule_check_required: bool,
    cost_adjustment_required: bool,
) -> str:
    return canonical_sha256(
        {
            "action": action.value,
            "conservative_invalidation_price": conservative_invalidation_price,
            "cost_adjustment_required": cost_adjustment_required,
            "execution_input_identity": execution_input_identity,
            "max_position_risk_usdt": max_position_risk_usdt,
            "policy_version": policy_version,
            "raw_quantity": raw_quantity,
            "reason_code": reason_code.value,
            "reference_price": reference_price,
            "risk_per_unit_usdt": risk_per_unit_usdt,
            "source_freeze_identities": list(source_freeze_identities),
            "status": status.value,
            "symbol": symbol.value,
            "venue_rule_check_required": venue_rule_check_required,
        }
    )


def size_paper_candidate(
    *,
    state: PaperFundState,
    autonomy_decision: PaperAutonomyDecision,
    execution_input: FrozenPaperExecutionInput,
    signals: tuple[SignalDecision, ...],
) -> PaperPositionSizingDecision:
    _validate_lineage(
        state=state,
        autonomy_decision=autonomy_decision,
        execution_input=execution_input,
        signals=signals,
    )
    symbol = autonomy_decision.symbol
    if symbol is None:
        raise PaperPositionSizingError("autonomy trade candidate lacks symbol")

    if autonomy_decision.candidate_action is PaperAction.EXIT:
        held = _held_quantity(state=state, symbol=symbol)
        if held <= Decimal(0):
            return _decision(
                status=PaperPositionSizingStatus.REJECTED,
                reason_code=PaperPositionSizingReason.NO_POSITION_TO_EXIT,
                action=PaperAction.EXIT,
                symbol=symbol,
                execution_input=execution_input,
                source_freeze_identities=autonomy_decision.source_freeze_identities,
                reference_price=execution_input.reference_price,
                invalidation=None,
                risk_per_unit=Decimal(0),
                max_risk=Decimal(0),
                raw_quantity=None,
                venue_rule_check_required=False,
                cost_adjustment_required=False,
            )
        return _decision(
            status=PaperPositionSizingStatus.SIZED,
            reason_code=PaperPositionSizingReason.EXIT_FULL_POSITION,
            action=PaperAction.EXIT,
            symbol=symbol,
            execution_input=execution_input,
            source_freeze_identities=autonomy_decision.source_freeze_identities,
            reference_price=execution_input.reference_price,
            invalidation=None,
            risk_per_unit=Decimal(0),
            max_risk=Decimal(0),
            raw_quantity=held,
            venue_rule_check_required=True,
            cost_adjustment_required=True,
        )

    reference = execution_input.reference_price
    geometries = tuple(signal.geometry for signal in signals)
    if any(geometry is None for geometry in geometries):
        raise PaperPositionSizingError("BUY source signal lost required geometry")
    concrete = tuple(geometry for geometry in geometries if geometry is not None)

    if any(
        not (geometry.entry_zone.low <= reference <= geometry.entry_zone.high)
        for geometry in concrete
    ):
        return _decision(
            status=PaperPositionSizingStatus.REJECTED,
            reason_code=PaperPositionSizingReason.REFERENCE_OUTSIDE_ENTRY_ZONE,
            action=PaperAction.BUY,
            symbol=symbol,
            execution_input=execution_input,
            source_freeze_identities=autonomy_decision.source_freeze_identities,
            reference_price=reference,
            invalidation=None,
            risk_per_unit=Decimal(0),
            max_risk=autonomy_decision.max_position_risk_usdt,
            raw_quantity=None,
            venue_rule_check_required=False,
            cost_adjustment_required=False,
        )

    invalidations = tuple(geometry.invalidation_price for geometry in concrete)
    if any(invalidation >= reference for invalidation in invalidations):
        return _decision(
            status=PaperPositionSizingStatus.REJECTED,
            reason_code=PaperPositionSizingReason.REFERENCE_NOT_ABOVE_INVALIDATION,
            action=PaperAction.BUY,
            symbol=symbol,
            execution_input=execution_input,
            source_freeze_identities=autonomy_decision.source_freeze_identities,
            reference_price=reference,
            invalidation=None,
            risk_per_unit=Decimal(0),
            max_risk=autonomy_decision.max_position_risk_usdt,
            raw_quantity=None,
            venue_rule_check_required=False,
            cost_adjustment_required=False,
        )

    conservative_invalidation = min(invalidations)
    risk_per_unit = reference - conservative_invalidation
    with localcontext() as context:
        context.prec = _CALCULATION_PRECISION
        raw_quantity = autonomy_decision.max_position_risk_usdt / risk_per_unit

    return _decision(
        status=PaperPositionSizingStatus.SIZED,
        reason_code=PaperPositionSizingReason.BUY_RISK_SIZED,
        action=PaperAction.BUY,
        symbol=symbol,
        execution_input=execution_input,
        source_freeze_identities=autonomy_decision.source_freeze_identities,
        reference_price=reference,
        invalidation=conservative_invalidation,
        risk_per_unit=risk_per_unit,
        max_risk=autonomy_decision.max_position_risk_usdt,
        raw_quantity=raw_quantity,
        venue_rule_check_required=True,
        cost_adjustment_required=True,
    )


def _validate_lineage(
    *,
    state: PaperFundState,
    autonomy_decision: PaperAutonomyDecision,
    execution_input: FrozenPaperExecutionInput,
    signals: tuple[SignalDecision, ...],
) -> None:
    if (
        state.real_capital != REAL_CAPITAL
        or autonomy_decision.real_capital != REAL_CAPITAL
        or execution_input.real_capital != REAL_CAPITAL
    ):
        raise PaperPositionSizingError("REAL_CAPITAL must remain 0")
    if autonomy_decision.candidate_action not in {PaperAction.BUY, PaperAction.EXIT}:
        raise PaperPositionSizingError("sizing requires BUY or EXIT candidate")
    if not autonomy_decision.execution_input_required:
        raise PaperPositionSizingError("candidate does not require execution input")
    if autonomy_decision.symbol is None:
        raise PaperPositionSizingError("candidate symbol is missing")
    if execution_input.candidate_action is not autonomy_decision.candidate_action:
        raise PaperPositionSizingError("execution input action lineage mismatch")
    if execution_input.symbol is not autonomy_decision.symbol:
        raise PaperPositionSizingError("execution input symbol lineage mismatch")
    if (
        execution_input.source_freeze_identities
        != autonomy_decision.source_freeze_identities
    ):
        raise PaperPositionSizingError("execution input signal lineage mismatch")
    signal_ids = tuple(signal.freeze_identity for signal in signals)
    if set(signal_ids) != set(autonomy_decision.source_freeze_identities):
        raise PaperPositionSizingError("source SignalDecision lineage mismatch")
    if len(signal_ids) != len(set(signal_ids)):
        raise PaperPositionSizingError("duplicate source SignalDecision identity")
    expected_direction = (
        SignalDirection.BULLISH
        if autonomy_decision.candidate_action is PaperAction.BUY
        else SignalDirection.BEARISH
    )
    for signal in signals:
        if signal.state is not SignalState.ACTIVE:
            raise PaperPositionSizingError("source signal is not ACTIVE")
        if signal.direction is not expected_direction:
            raise PaperPositionSizingError("source signal direction lineage mismatch")
        if signal.symbol != autonomy_decision.symbol.value:
            raise PaperPositionSizingError("source signal symbol lineage mismatch")


def _held_quantity(*, state: PaperFundState, symbol: PaperSymbol) -> Decimal:
    for position in state.positions:
        if position.symbol is symbol:
            return position.quantity
    return Decimal(0)


def _decision(
    *,
    status: PaperPositionSizingStatus,
    reason_code: PaperPositionSizingReason,
    action: PaperAction,
    symbol: PaperSymbol,
    execution_input: FrozenPaperExecutionInput,
    source_freeze_identities: tuple[str, ...],
    reference_price: Decimal,
    invalidation: Decimal | None,
    risk_per_unit: Decimal,
    max_risk: Decimal,
    raw_quantity: Decimal | None,
    venue_rule_check_required: bool,
    cost_adjustment_required: bool,
) -> PaperPositionSizingDecision:
    identity = compute_position_sizing_identity(
        policy_version=PAPER_POSITION_SIZING_POLICY_VERSION,
        status=status,
        reason_code=reason_code,
        action=action,
        symbol=symbol,
        execution_input_identity=execution_input.input_identity,
        source_freeze_identities=source_freeze_identities,
        reference_price=reference_price,
        conservative_invalidation_price=invalidation,
        risk_per_unit_usdt=risk_per_unit,
        max_position_risk_usdt=max_risk,
        raw_quantity=raw_quantity,
        venue_rule_check_required=venue_rule_check_required,
        cost_adjustment_required=cost_adjustment_required,
    )
    return PaperPositionSizingDecision(
        sizing_identity=identity,
        policy_version=PAPER_POSITION_SIZING_POLICY_VERSION,
        status=status,
        reason_code=reason_code,
        action=action,
        symbol=symbol,
        execution_input_identity=execution_input.input_identity,
        source_freeze_identities=source_freeze_identities,
        reference_price=reference_price,
        conservative_invalidation_price=invalidation,
        risk_per_unit_usdt=risk_per_unit,
        max_position_risk_usdt=max_risk,
        raw_quantity=raw_quantity,
        venue_rule_check_required=venue_rule_check_required,
        cost_adjustment_required=cost_adjustment_required,
        real_capital=REAL_CAPITAL,
    )
