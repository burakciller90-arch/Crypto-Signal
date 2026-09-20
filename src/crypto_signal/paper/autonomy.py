"""Pure, versioned autonomy eligibility policy for the virtual paper fund.

This module can emit a BUY or EXIT *candidate* from frozen signal decisions.
It never creates an order, fill, ledger mutation, network request, or execution
price. A separate frozen execution-input gate remains mandatory before a
candidate may become a simulated trade plan. REAL_CAPITAL remains 0.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from enum import StrEnum

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction, PaperSymbol
from crypto_signal.paper.state import PaperFundState
from crypto_signal.signals.models import (
    SignalDecision,
    SignalDirection,
    SignalState,
)

__all__ = [
    "DEFAULT_ALLOWED_UNCERTAINTY_FLAGS",
    "DEFAULT_AUTONOMY_COOLDOWN_MS",
    "DEFAULT_AUTONOMY_DECISION_TIMEFRAME",
    "DEFAULT_AUTONOMY_MAX_SIGNAL_AGE_MS",
    "DEFAULT_AUTONOMY_MAX_POSITION_RISK_FRACTION",
    "DEFAULT_AUTONOMY_REQUIRED_EXCHANGES",
    "PAPER_AUTONOMY_POLICY_VERSION",
    "REAL_CAPITAL",
    "PaperAutonomyDecision",
    "PaperAutonomyPolicy",
    "PaperAutonomyReason",
    "default_conservative_autonomy_policy",
    "evaluate_autonomy_policy",
]

PAPER_AUTONOMY_POLICY_VERSION = "paper_autonomy_policy.v1"
DEFAULT_AUTONOMY_DECISION_TIMEFRAME = "4h"
DEFAULT_AUTONOMY_COOLDOWN_MS = 4 * 60 * 60 * 1000
DEFAULT_AUTONOMY_MAX_SIGNAL_AGE_MS = 4 * 60 * 60 * 1000
DEFAULT_AUTONOMY_MAX_POSITION_RISK_FRACTION = Decimal("0.01")
DEFAULT_AUTONOMY_REQUIRED_EXCHANGES = (
    Exchange.BINANCE,
    Exchange.BYBIT,
)
DEFAULT_ALLOWED_UNCERTAINTY_FLAGS = ("partial_methodology_coverage",)
_RISK_BUDGET_QUANTUM = Decimal("0.01")


class PaperAutonomyReason(StrEnum):
    """Deterministic reason code for one autonomy-policy evaluation."""

    BUY_ELIGIBLE = "buy_eligible"
    EXIT_ELIGIBLE = "exit_eligible"
    NO_SIGNALS = "no_signals"
    PROVIDER_SET_MISMATCH = "provider_set_mismatch"
    MIXED_SIGNAL_CONTEXT = "mixed_signal_context"
    UNSUPPORTED_SYMBOL = "unsupported_symbol"
    TIMEFRAME_NOT_ELIGIBLE = "timeframe_not_eligible"
    PRE_ACTIVATION_SIGNAL = "pre_activation_signal"
    FUTURE_SIGNAL = "future_signal"
    STALE_SIGNAL = "stale_signal"
    SIGNAL_NOT_ACTIVE = "signal_not_active"
    DIRECTION_DISAGREEMENT = "direction_disagreement"
    ACTIVE_CONTRACT_MISMATCH = "active_contract_mismatch"
    UNSAFE_UNCERTAINTY = "unsafe_uncertainty"
    COOLDOWN_ACTIVE = "cooldown_active"
    MISSING_MARK_PRICE = "missing_mark_price"
    RISK_BUDGET_TOO_SMALL = "risk_budget_too_small"
    PYRAMIDING_FORBIDDEN = "pyramiding_forbidden"
    SHORTING_FORBIDDEN = "shorting_forbidden"


@dataclass(frozen=True, slots=True)
class PaperAutonomyPolicy:
    """Conservative V1 eligibility/risk policy above the immutable planner."""

    version: str
    decision_timeframe: str
    required_exchanges: tuple[Exchange, ...]
    max_position_risk_fraction: Decimal
    cooldown_ms: int
    max_signal_age_ms: int
    allowed_uncertainty_flags: tuple[str, ...]
    allow_pyramiding: bool = False
    allow_shorting: bool = False
    allow_automatic_reduce: bool = False

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("autonomy policy version must be non-empty")
        if not self.decision_timeframe.strip():
            raise ValueError("autonomy decision timeframe must be non-empty")
        if not self.required_exchanges:
            raise ValueError("autonomy policy requires at least one exchange")
        if len(set(self.required_exchanges)) != len(self.required_exchanges):
            raise ValueError("autonomy required exchanges must be unique")
        if not isinstance(self.max_position_risk_fraction, Decimal):
            raise TypeError("max_position_risk_fraction must be Decimal")
        if (
            self.max_position_risk_fraction.is_nan()
            or self.max_position_risk_fraction.is_infinite()
        ):
            raise ValueError("max_position_risk_fraction must be finite")
        if not Decimal(0) < self.max_position_risk_fraction <= Decimal(1):
            raise ValueError(
                "max_position_risk_fraction must be greater than 0 and at most 1"
            )
        if self.cooldown_ms <= 0:
            raise ValueError("autonomy cooldown_ms must be positive")
        if self.max_signal_age_ms <= 0:
            raise ValueError("autonomy max_signal_age_ms must be positive")
        if len(set(self.allowed_uncertainty_flags)) != len(
            self.allowed_uncertainty_flags
        ):
            raise ValueError("allowed uncertainty flags must be unique")
        if self.allow_pyramiding or self.allow_shorting or self.allow_automatic_reduce:
            raise ValueError(
                "paper_autonomy_policy.v1 forbids pyramiding, shorting, "
                "and automatic REDUCE"
            )


@dataclass(frozen=True, slots=True)
class PaperAutonomyDecision:
    """Pure candidate output; never an executable or persisted trade."""

    policy_version: str
    evaluated_at_ms: int
    activation_cutoff_ms: int
    candidate_action: PaperAction
    symbol: PaperSymbol | None
    source_freeze_identities: tuple[str, ...]
    source_as_of_ms: int | None
    reason_code: PaperAutonomyReason
    reason: str
    max_position_risk_usdt: Decimal
    execution_input_required: bool
    cooldown_remaining_ms: int = 0
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if not self.policy_version.strip():
            raise ValueError("policy_version must be non-empty")
        if self.evaluated_at_ms < 0 or self.activation_cutoff_ms < 0:
            raise ValueError("autonomy timestamps must be non-negative")
        if self.activation_cutoff_ms > self.evaluated_at_ms:
            raise ValueError("activation cutoff cannot be after evaluation time")
        if self.max_position_risk_usdt < Decimal(0):
            raise ValueError("max_position_risk_usdt cannot be negative")
        if self.cooldown_remaining_ms < 0:
            raise ValueError("cooldown_remaining_ms cannot be negative")
        if self.candidate_action is PaperAction.REDUCE:
            raise ValueError("automatic REDUCE is not allowed in autonomy policy v1")
        if self.candidate_action in {PaperAction.BUY, PaperAction.EXIT}:
            if self.symbol is None:
                raise ValueError("trade candidate requires symbol")
            if not self.execution_input_required:
                raise ValueError("trade candidate requires frozen execution input")
            if not self.source_freeze_identities:
                raise ValueError("trade candidate requires source signal identities")
        else:
            if self.candidate_action is not PaperAction.HOLD_CASH:
                raise ValueError("unsupported autonomy candidate action")
            if self.execution_input_required:
                raise ValueError("HOLD_CASH cannot require execution input")
        if self.candidate_action is PaperAction.BUY:
            if self.max_position_risk_usdt <= Decimal(0):
                raise ValueError("BUY candidate requires positive risk budget")
        elif self.max_position_risk_usdt != Decimal(0):
            raise ValueError("only BUY candidate may carry position risk budget")


def default_conservative_autonomy_policy() -> PaperAutonomyPolicy:
    """Return the explicit conservative paper autonomy policy v1."""
    return PaperAutonomyPolicy(
        version=PAPER_AUTONOMY_POLICY_VERSION,
        decision_timeframe=DEFAULT_AUTONOMY_DECISION_TIMEFRAME,
        required_exchanges=DEFAULT_AUTONOMY_REQUIRED_EXCHANGES,
        max_position_risk_fraction=DEFAULT_AUTONOMY_MAX_POSITION_RISK_FRACTION,
        cooldown_ms=DEFAULT_AUTONOMY_COOLDOWN_MS,
        max_signal_age_ms=DEFAULT_AUTONOMY_MAX_SIGNAL_AGE_MS,
        allowed_uncertainty_flags=DEFAULT_ALLOWED_UNCERTAINTY_FLAGS,
        allow_pyramiding=False,
        allow_shorting=False,
        allow_automatic_reduce=False,
    )


def evaluate_autonomy_policy(
    *,
    state: PaperFundState,
    signals: tuple[SignalDecision, ...],
    evaluated_at_ms: int,
    activation_cutoff_ms: int,
    mark_prices: Mapping[PaperSymbol, Decimal] | None = None,
    last_action_at_ms: Mapping[PaperSymbol, int] | None = None,
    policy: PaperAutonomyPolicy | None = None,
) -> PaperAutonomyDecision:
    """Evaluate frozen signal consensus into a non-executable paper candidate."""
    selected_policy = policy or default_conservative_autonomy_policy()
    if state.real_capital != REAL_CAPITAL:
        raise ValueError("REAL_CAPITAL must remain 0")
    if evaluated_at_ms < 0 or activation_cutoff_ms < 0:
        raise ValueError("autonomy timestamps must be non-negative")
    if activation_cutoff_ms > evaluated_at_ms:
        raise ValueError("activation cutoff cannot be after evaluation time")

    if not signals:
        return _hold(
            policy=selected_policy,
            evaluated_at_ms=evaluated_at_ms,
            activation_cutoff_ms=activation_cutoff_ms,
            reason_code=PaperAutonomyReason.NO_SIGNALS,
            reason="no frozen signal set available",
        )

    provider_map = {signal.exchange: signal for signal in signals}
    if (
        len(provider_map) != len(signals)
        or tuple(sorted(provider_map, key=lambda value: value.value))
        != tuple(sorted(selected_policy.required_exchanges, key=lambda value: value.value))
    ):
        return _hold_from_signals(
            policy=selected_policy,
            signals=signals,
            evaluated_at_ms=evaluated_at_ms,
            activation_cutoff_ms=activation_cutoff_ms,
            reason_code=PaperAutonomyReason.PROVIDER_SET_MISMATCH,
            reason="required Bybit/Binance provider set is not exact",
        )

    ordered = tuple(provider_map[exchange] for exchange in selected_policy.required_exchanges)
    symbols = {signal.symbol for signal in ordered}
    timeframes = {signal.timeframe for signal in ordered}
    as_of_values = {signal.as_of_ms for signal in ordered}
    market_types = {signal.market_type for signal in ordered}
    if (
        len(symbols) != 1
        or len(timeframes) != 1
        or len(as_of_values) != 1
        or market_types != {MarketType.SPOT}
    ):
        return _hold_from_signals(
            policy=selected_policy,
            signals=ordered,
            evaluated_at_ms=evaluated_at_ms,
            activation_cutoff_ms=activation_cutoff_ms,
            reason_code=PaperAutonomyReason.MIXED_SIGNAL_CONTEXT,
            reason="provider signals do not share one exact spot context",
        )

    raw_symbol = ordered[0].symbol
    try:
        symbol = PaperSymbol(raw_symbol)
    except ValueError:
        return _hold_from_signals(
            policy=selected_policy,
            signals=ordered,
            evaluated_at_ms=evaluated_at_ms,
            activation_cutoff_ms=activation_cutoff_ms,
            reason_code=PaperAutonomyReason.UNSUPPORTED_SYMBOL,
            reason="signal symbol is outside the permitted paper universe",
        )

    source_as_of_ms = ordered[0].as_of_ms
    if ordered[0].timeframe != selected_policy.decision_timeframe:
        return _hold_from_signals(
            policy=selected_policy,
            signals=ordered,
            evaluated_at_ms=evaluated_at_ms,
            activation_cutoff_ms=activation_cutoff_ms,
            symbol=symbol,
            reason_code=PaperAutonomyReason.TIMEFRAME_NOT_ELIGIBLE,
            reason="signal timeframe is outside the autonomy decision cadence",
        )
    if source_as_of_ms < activation_cutoff_ms:
        return _hold_from_signals(
            policy=selected_policy,
            signals=ordered,
            evaluated_at_ms=evaluated_at_ms,
            activation_cutoff_ms=activation_cutoff_ms,
            symbol=symbol,
            reason_code=PaperAutonomyReason.PRE_ACTIVATION_SIGNAL,
            reason="frozen signal predates the explicit paper activation watermark",
        )
    if source_as_of_ms > evaluated_at_ms:
        return _hold_from_signals(
            policy=selected_policy,
            signals=ordered,
            evaluated_at_ms=evaluated_at_ms,
            activation_cutoff_ms=activation_cutoff_ms,
            symbol=symbol,
            reason_code=PaperAutonomyReason.FUTURE_SIGNAL,
            reason="frozen signal as-of is after evaluation time",
        )
    if evaluated_at_ms - source_as_of_ms > selected_policy.max_signal_age_ms:
        return _hold_from_signals(
            policy=selected_policy,
            signals=ordered,
            evaluated_at_ms=evaluated_at_ms,
            activation_cutoff_ms=activation_cutoff_ms,
            symbol=symbol,
            reason_code=PaperAutonomyReason.STALE_SIGNAL,
            reason="frozen signal exceeded the policy freshness window",
        )

    if any(signal.state is not SignalState.ACTIVE for signal in ordered):
        return _hold_from_signals(
            policy=selected_policy,
            signals=ordered,
            evaluated_at_ms=evaluated_at_ms,
            activation_cutoff_ms=activation_cutoff_ms,
            symbol=symbol,
            reason_code=PaperAutonomyReason.SIGNAL_NOT_ACTIVE,
            reason="all required providers must be ACTIVE",
        )

    directions = {signal.direction for signal in ordered}
    if len(directions) != 1:
        return _hold_from_signals(
            policy=selected_policy,
            signals=ordered,
            evaluated_at_ms=evaluated_at_ms,
            activation_cutoff_ms=activation_cutoff_ms,
            symbol=symbol,
            reason_code=PaperAutonomyReason.DIRECTION_DISAGREEMENT,
            reason="required providers disagree on signal direction",
        )

    if any(
        signal.geometry is None
        or signal.agreement.support_method_count < 2
        or signal.agreement.opposing_method_count != 0
        for signal in ordered
    ):
        return _hold_from_signals(
            policy=selected_policy,
            signals=ordered,
            evaluated_at_ms=evaluated_at_ms,
            activation_cutoff_ms=activation_cutoff_ms,
            symbol=symbol,
            reason_code=PaperAutonomyReason.ACTIVE_CONTRACT_MISMATCH,
            reason="ACTIVE signal does not satisfy the independent-support contract",
        )

    allowed_flags = set(selected_policy.allowed_uncertainty_flags)
    if any(
        any(flag not in allowed_flags for flag in signal.uncertainty_flags)
        for signal in ordered
    ):
        return _hold_from_signals(
            policy=selected_policy,
            signals=ordered,
            evaluated_at_ms=evaluated_at_ms,
            activation_cutoff_ms=activation_cutoff_ms,
            symbol=symbol,
            reason_code=PaperAutonomyReason.UNSAFE_UNCERTAINTY,
            reason="signal carries an uncertainty flag not allowed by autonomy v1",
        )

    last_action = (last_action_at_ms or {}).get(symbol)
    if last_action is not None:
        if last_action > evaluated_at_ms:
            return _hold_from_signals(
                policy=selected_policy,
                signals=ordered,
                evaluated_at_ms=evaluated_at_ms,
                activation_cutoff_ms=activation_cutoff_ms,
                symbol=symbol,
                reason_code=PaperAutonomyReason.COOLDOWN_ACTIVE,
                reason="last action timestamp is after evaluation time",
                cooldown_remaining_ms=selected_policy.cooldown_ms,
            )
        elapsed = evaluated_at_ms - last_action
        if elapsed < selected_policy.cooldown_ms:
            return _hold_from_signals(
                policy=selected_policy,
                signals=ordered,
                evaluated_at_ms=evaluated_at_ms,
                activation_cutoff_ms=activation_cutoff_ms,
                symbol=symbol,
                reason_code=PaperAutonomyReason.COOLDOWN_ACTIVE,
                reason="symbol remains inside the post-action cooldown",
                cooldown_remaining_ms=selected_policy.cooldown_ms - elapsed,
            )

    held_quantity = _held_quantity(state=state, symbol=symbol)
    direction = next(iter(directions))
    if direction is SignalDirection.BULLISH:
        if held_quantity > Decimal(0):
            return _hold_from_signals(
                policy=selected_policy,
                signals=ordered,
                evaluated_at_ms=evaluated_at_ms,
                activation_cutoff_ms=activation_cutoff_ms,
                symbol=symbol,
                reason_code=PaperAutonomyReason.PYRAMIDING_FORBIDDEN,
                reason="autonomy v1 does not add to an existing long position",
            )

        nav = _marked_nav(state=state, mark_prices=mark_prices or {})
        if nav is None:
            return _hold_from_signals(
                policy=selected_policy,
                signals=ordered,
                evaluated_at_ms=evaluated_at_ms,
                activation_cutoff_ms=activation_cutoff_ms,
                symbol=symbol,
                reason_code=PaperAutonomyReason.MISSING_MARK_PRICE,
                reason="NAV cannot be reconstructed from current paper positions",
            )
        risk_budget = (
            nav * selected_policy.max_position_risk_fraction
        ).quantize(_RISK_BUDGET_QUANTUM, rounding=ROUND_DOWN)
        if risk_budget <= Decimal(0):
            return _hold_from_signals(
                policy=selected_policy,
                signals=ordered,
                evaluated_at_ms=evaluated_at_ms,
                activation_cutoff_ms=activation_cutoff_ms,
                symbol=symbol,
                reason_code=PaperAutonomyReason.RISK_BUDGET_TOO_SMALL,
                reason="conservative per-position risk budget rounded to zero",
            )
        return PaperAutonomyDecision(
            policy_version=selected_policy.version,
            evaluated_at_ms=evaluated_at_ms,
            activation_cutoff_ms=activation_cutoff_ms,
            candidate_action=PaperAction.BUY,
            symbol=symbol,
            source_freeze_identities=tuple(
                signal.freeze_identity for signal in ordered
            ),
            source_as_of_ms=source_as_of_ms,
            reason_code=PaperAutonomyReason.BUY_ELIGIBLE,
            reason=(
                "fresh ACTIVE bullish Bybit/Binance consensus passed the "
                "autonomy eligibility and cooldown gates"
            ),
            max_position_risk_usdt=risk_budget,
            execution_input_required=True,
            real_capital=REAL_CAPITAL,
        )

    if direction is SignalDirection.BEARISH:
        if held_quantity <= Decimal(0):
            return _hold_from_signals(
                policy=selected_policy,
                signals=ordered,
                evaluated_at_ms=evaluated_at_ms,
                activation_cutoff_ms=activation_cutoff_ms,
                symbol=symbol,
                reason_code=PaperAutonomyReason.SHORTING_FORBIDDEN,
                reason="bearish consensus cannot open a short position in autonomy v1",
            )
        return PaperAutonomyDecision(
            policy_version=selected_policy.version,
            evaluated_at_ms=evaluated_at_ms,
            activation_cutoff_ms=activation_cutoff_ms,
            candidate_action=PaperAction.EXIT,
            symbol=symbol,
            source_freeze_identities=tuple(
                signal.freeze_identity for signal in ordered
            ),
            source_as_of_ms=source_as_of_ms,
            reason_code=PaperAutonomyReason.EXIT_ELIGIBLE,
            reason=(
                "fresh ACTIVE bearish Bybit/Binance consensus may close the "
                "existing long position"
            ),
            max_position_risk_usdt=Decimal(0),
            execution_input_required=True,
            real_capital=REAL_CAPITAL,
        )

    return _hold_from_signals(
        policy=selected_policy,
        signals=ordered,
        evaluated_at_ms=evaluated_at_ms,
        activation_cutoff_ms=activation_cutoff_ms,
        symbol=symbol,
        reason_code=PaperAutonomyReason.DIRECTION_DISAGREEMENT,
        reason="ACTIVE provider consensus did not resolve to bullish or bearish",
    )


def _hold(
    *,
    policy: PaperAutonomyPolicy,
    evaluated_at_ms: int,
    activation_cutoff_ms: int,
    reason_code: PaperAutonomyReason,
    reason: str,
    symbol: PaperSymbol | None = None,
    source_freeze_identities: tuple[str, ...] = (),
    source_as_of_ms: int | None = None,
    cooldown_remaining_ms: int = 0,
) -> PaperAutonomyDecision:
    return PaperAutonomyDecision(
        policy_version=policy.version,
        evaluated_at_ms=evaluated_at_ms,
        activation_cutoff_ms=activation_cutoff_ms,
        candidate_action=PaperAction.HOLD_CASH,
        symbol=symbol,
        source_freeze_identities=source_freeze_identities,
        source_as_of_ms=source_as_of_ms,
        reason_code=reason_code,
        reason=reason,
        max_position_risk_usdt=Decimal(0),
        execution_input_required=False,
        cooldown_remaining_ms=cooldown_remaining_ms,
        real_capital=REAL_CAPITAL,
    )


def _hold_from_signals(
    *,
    policy: PaperAutonomyPolicy,
    signals: tuple[SignalDecision, ...],
    evaluated_at_ms: int,
    activation_cutoff_ms: int,
    reason_code: PaperAutonomyReason,
    reason: str,
    symbol: PaperSymbol | None = None,
    cooldown_remaining_ms: int = 0,
) -> PaperAutonomyDecision:
    as_of_values = {signal.as_of_ms for signal in signals}
    source_as_of_ms = next(iter(as_of_values)) if len(as_of_values) == 1 else None
    return _hold(
        policy=policy,
        evaluated_at_ms=evaluated_at_ms,
        activation_cutoff_ms=activation_cutoff_ms,
        reason_code=reason_code,
        reason=reason,
        symbol=symbol,
        source_freeze_identities=tuple(
            signal.freeze_identity for signal in signals
        ),
        source_as_of_ms=source_as_of_ms,
        cooldown_remaining_ms=cooldown_remaining_ms,
    )


def _held_quantity(*, state: PaperFundState, symbol: PaperSymbol) -> Decimal:
    for position in state.positions:
        if position.symbol is symbol:
            return position.quantity
    return Decimal(0)


def _marked_nav(
    *,
    state: PaperFundState,
    mark_prices: Mapping[PaperSymbol, Decimal],
) -> Decimal | None:
    nav = state.cash_usdt
    for position in state.positions:
        price = mark_prices.get(position.symbol)
        if price is None or price <= Decimal(0):
            return None
        nav += position.quantity * price
    return nav
