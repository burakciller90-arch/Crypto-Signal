"""Focused tests for paper_autonomy_policy.v1."""

from __future__ import annotations

import inspect
from dataclasses import replace
from decimal import Decimal

from crypto_signal.confluence.models import (
    InvalidationTrigger,
    MethodologyKind,
    PriceZone,
    ScoreSemantic,
)
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.paper import autonomy as paper_autonomy
from crypto_signal.paper.autonomy import (
    DEFAULT_AUTONOMY_COOLDOWN_MS,
    PAPER_AUTONOMY_POLICY_VERSION,
    PaperAutonomyReason,
    default_conservative_autonomy_policy,
    evaluate_autonomy_policy,
)
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.models import (
    REAL_CAPITAL,
    PaperAction,
    PaperPosition,
    PaperSymbol,
    build_fund_creation,
)
from crypto_signal.paper.state import reconstruct_paper_fund_state
from crypto_signal.signals.models import (
    EntryReferenceModel,
    HistoricalStatsStatus,
    MethodologyVersionRef,
    ProbabilityStatus,
    RiskRewardTarget,
    SignalAgreementSummary,
    SignalDecision,
    SignalDirection,
    SignalGeometry,
    SignalState,
)

AS_OF = 40_000_000
EVALUATED = AS_OF + 60_000
ACTIVATION = AS_OF - 1


def _state(tmp_path):
    ledger = PaperFundLedger(tmp_path / "paper.sqlite3")
    ledger.append_fund_creation(build_fund_creation(created_at_ms=1))
    return reconstruct_paper_fund_state(ledger)


def _signal(
    exchange: Exchange,
    *,
    direction: SignalDirection = SignalDirection.BULLISH,
    state: SignalState = SignalState.ACTIVE,
    as_of_ms: int = AS_OF,
    timeframe: str = "4h",
    symbol: str = "BTCUSDT",
    flags: tuple[str, ...] = ("partial_methodology_coverage",),
) -> SignalDecision:
    if direction is SignalDirection.BULLISH:
        invalidation = Decimal(90)
        targets = (RiskRewardTarget("t1", Decimal(110), Decimal(1)),)
    else:
        invalidation = Decimal(110)
        targets = (RiskRewardTarget("t1", Decimal(90), Decimal(1)),)
    geometry = None
    if state is SignalState.ACTIVE:
        geometry = SignalGeometry(
            source_evidence_id=f"{exchange.value}-geometry",
            source_methodology=MethodologyKind.HARMONIC,
            entry_zone=PriceZone(Decimal(99), Decimal(101)),
            entry_reference_price=Decimal(100),
            entry_reference_model=(
                EntryReferenceModel.ZONE_MIDPOINT_REFERENCE_NOT_EXECUTION
            ),
            invalidation_price=invalidation,
            invalidation_trigger=InvalidationTrigger.TOUCH_OR_CROSS,
            targets=targets,
        )

    return SignalDecision(
        freeze_identity=(
            "a" * 64 if exchange is Exchange.BINANCE else "b" * 64
        ),
        signal_version="signal.test.v1",
        state=state,
        exchange=exchange,
        market_type=MarketType.SPOT,
        symbol=symbol,
        timeframe=timeframe,
        as_of_ms=as_of_ms,
        direction=(
            SignalDirection.NONE
            if state in {SignalState.NO_SIGNAL, SignalState.NEUTRAL}
            else direction
        ),
        setup_type="test_setup",
        geometry=geometry,
        agreement=SignalAgreementSummary(
            confluence_score=Decimal("66.67"),
            score_semantic=ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY,
            support_method_count=2,
            opposing_method_count=0,
            resolved_method_count=2,
            total_methodology_slots=3,
            pairwise_relations=(),
        ),
        selected_evidence_ids=(f"{exchange.value}-pa", f"{exchange.value}-harmonic"),
        methodology_versions=(
            MethodologyVersionRef(MethodologyKind.PRICE_ACTION, "pa.test.v1"),
            MethodologyVersionRef(MethodologyKind.HARMONIC, "harmonic.test.v1"),
        ),
        probability_status=ProbabilityStatus.NOT_CALIBRATED,
        historical_stats_status=HistoricalStatsStatus.NOT_EVALUATED,
        uncertainty_flags=flags,
        evidence_summary=(),
    )


def _consensus(
    *,
    direction: SignalDirection = SignalDirection.BULLISH,
    state: SignalState = SignalState.ACTIVE,
    as_of_ms: int = AS_OF,
    timeframe: str = "4h",
    flags: tuple[str, ...] = ("partial_methodology_coverage",),
):
    return (
        _signal(
            Exchange.BINANCE,
            direction=direction,
            state=state,
            as_of_ms=as_of_ms,
            timeframe=timeframe,
            flags=flags,
        ),
        _signal(
            Exchange.BYBIT,
            direction=direction,
            state=state,
            as_of_ms=as_of_ms,
            timeframe=timeframe,
            flags=flags,
        ),
    )


def test_default_policy_is_explicit_and_conservative() -> None:
    policy = default_conservative_autonomy_policy()

    assert policy.version == PAPER_AUTONOMY_POLICY_VERSION
    assert policy.decision_timeframe == "4h"
    assert policy.required_exchanges == (Exchange.BINANCE, Exchange.BYBIT)
    assert policy.max_position_risk_fraction == Decimal("0.01")
    assert policy.cooldown_ms == 4 * 60 * 60 * 1000
    assert policy.max_signal_age_ms == 4 * 60 * 60 * 1000
    assert policy.allow_pyramiding is False
    assert policy.allow_shorting is False
    assert policy.allow_automatic_reduce is False


def test_fresh_bullish_provider_consensus_emits_buy_candidate(tmp_path) -> None:
    decision = evaluate_autonomy_policy(
        state=_state(tmp_path),
        signals=_consensus(),
        evaluated_at_ms=EVALUATED,
        activation_cutoff_ms=ACTIVATION,
    )

    assert decision.candidate_action is PaperAction.BUY
    assert decision.symbol is PaperSymbol.BTCUSDT
    assert decision.reason_code is PaperAutonomyReason.BUY_ELIGIBLE
    assert decision.max_position_risk_usdt == Decimal("1.00")
    assert decision.execution_input_required is True
    assert decision.real_capital == REAL_CAPITAL == 0


def test_watch_signal_holds_cash(tmp_path) -> None:
    decision = evaluate_autonomy_policy(
        state=_state(tmp_path),
        signals=_consensus(state=SignalState.WATCH),
        evaluated_at_ms=EVALUATED,
        activation_cutoff_ms=ACTIVATION,
    )

    assert decision.candidate_action is PaperAction.HOLD_CASH
    assert decision.reason_code is PaperAutonomyReason.SIGNAL_NOT_ACTIVE


def test_provider_direction_disagreement_holds_cash(tmp_path) -> None:
    signals = (
        _signal(Exchange.BINANCE, direction=SignalDirection.BULLISH),
        _signal(Exchange.BYBIT, direction=SignalDirection.BEARISH),
    )
    decision = evaluate_autonomy_policy(
        state=_state(tmp_path),
        signals=signals,
        evaluated_at_ms=EVALUATED,
        activation_cutoff_ms=ACTIVATION,
    )

    assert decision.candidate_action is PaperAction.HOLD_CASH
    assert decision.reason_code is PaperAutonomyReason.DIRECTION_DISAGREEMENT


def test_missing_provider_holds_cash(tmp_path) -> None:
    decision = evaluate_autonomy_policy(
        state=_state(tmp_path),
        signals=(_signal(Exchange.BINANCE),),
        evaluated_at_ms=EVALUATED,
        activation_cutoff_ms=ACTIVATION,
    )

    assert decision.reason_code is PaperAutonomyReason.PROVIDER_SET_MISMATCH


def test_pre_activation_signal_cannot_backfill_trade(tmp_path) -> None:
    decision = evaluate_autonomy_policy(
        state=_state(tmp_path),
        signals=_consensus(as_of_ms=AS_OF - 10),
        evaluated_at_ms=EVALUATED,
        activation_cutoff_ms=AS_OF,
    )

    assert decision.candidate_action is PaperAction.HOLD_CASH
    assert decision.reason_code is PaperAutonomyReason.PRE_ACTIVATION_SIGNAL


def test_stale_signal_holds_cash(tmp_path) -> None:
    old = EVALUATED - (4 * 60 * 60 * 1000) - 1
    decision = evaluate_autonomy_policy(
        state=_state(tmp_path),
        signals=_consensus(as_of_ms=old),
        evaluated_at_ms=EVALUATED,
        activation_cutoff_ms=old - 1,
    )

    assert decision.reason_code is PaperAutonomyReason.STALE_SIGNAL


def test_wrong_timeframe_holds_cash(tmp_path) -> None:
    decision = evaluate_autonomy_policy(
        state=_state(tmp_path),
        signals=_consensus(timeframe="15m"),
        evaluated_at_ms=EVALUATED,
        activation_cutoff_ms=ACTIVATION,
    )

    assert decision.reason_code is PaperAutonomyReason.TIMEFRAME_NOT_ELIGIBLE


def test_cooldown_blocks_repeat_action(tmp_path) -> None:
    decision = evaluate_autonomy_policy(
        state=_state(tmp_path),
        signals=_consensus(),
        evaluated_at_ms=EVALUATED,
        activation_cutoff_ms=ACTIVATION,
        last_action_at_ms={
            PaperSymbol.BTCUSDT: EVALUATED - 60_000,
        },
    )

    assert decision.reason_code is PaperAutonomyReason.COOLDOWN_ACTIVE
    assert decision.cooldown_remaining_ms == DEFAULT_AUTONOMY_COOLDOWN_MS - 60_000


def test_existing_long_forbids_pyramiding(tmp_path) -> None:
    state = replace(
        _state(tmp_path),
        cash_usdt=Decimal(80),
        positions=(PaperPosition(PaperSymbol.BTCUSDT, Decimal("0.2")),),
    )
    decision = evaluate_autonomy_policy(
        state=state,
        signals=_consensus(),
        evaluated_at_ms=EVALUATED,
        activation_cutoff_ms=ACTIVATION,
        mark_prices={PaperSymbol.BTCUSDT: Decimal(100)},
    )

    assert decision.reason_code is PaperAutonomyReason.PYRAMIDING_FORBIDDEN
    assert decision.candidate_action is PaperAction.HOLD_CASH


def test_bearish_consensus_exits_existing_long_but_never_shorts(tmp_path) -> None:
    flat = _state(tmp_path)
    no_short = evaluate_autonomy_policy(
        state=flat,
        signals=_consensus(direction=SignalDirection.BEARISH),
        evaluated_at_ms=EVALUATED,
        activation_cutoff_ms=ACTIVATION,
    )
    assert no_short.reason_code is PaperAutonomyReason.SHORTING_FORBIDDEN
    assert no_short.candidate_action is PaperAction.HOLD_CASH

    held = replace(
        flat,
        cash_usdt=Decimal(80),
        positions=(PaperPosition(PaperSymbol.BTCUSDT, Decimal("0.2")),),
    )
    exit_candidate = evaluate_autonomy_policy(
        state=held,
        signals=_consensus(direction=SignalDirection.BEARISH),
        evaluated_at_ms=EVALUATED,
        activation_cutoff_ms=ACTIVATION,
    )
    assert exit_candidate.reason_code is PaperAutonomyReason.EXIT_ELIGIBLE
    assert exit_candidate.candidate_action is PaperAction.EXIT
    assert exit_candidate.max_position_risk_usdt == Decimal(0)
    assert exit_candidate.execution_input_required is True


def test_missing_marks_for_other_positions_blocks_buy_risk_budget(tmp_path) -> None:
    state = replace(
        _state(tmp_path),
        cash_usdt=Decimal(90),
        positions=(PaperPosition(PaperSymbol.ETHUSDT, Decimal("0.01")),),
    )
    decision = evaluate_autonomy_policy(
        state=state,
        signals=_consensus(),
        evaluated_at_ms=EVALUATED,
        activation_cutoff_ms=ACTIVATION,
        mark_prices={},
    )

    assert decision.reason_code is PaperAutonomyReason.MISSING_MARK_PRICE
    assert decision.candidate_action is PaperAction.HOLD_CASH


def test_marked_nav_sets_one_percent_risk_budget(tmp_path) -> None:
    state = replace(
        _state(tmp_path),
        cash_usdt=Decimal(80),
        positions=(PaperPosition(PaperSymbol.ETHUSDT, Decimal("0.01")),),
    )
    decision = evaluate_autonomy_policy(
        state=state,
        signals=_consensus(),
        evaluated_at_ms=EVALUATED,
        activation_cutoff_ms=ACTIVATION,
        mark_prices={PaperSymbol.ETHUSDT: Decimal(2000)},
    )

    assert decision.candidate_action is PaperAction.BUY
    assert decision.max_position_risk_usdt == Decimal("1.00")


def test_partial_methodology_coverage_is_allowed_but_other_uncertainty_is_not(
    tmp_path,
) -> None:
    allowed = evaluate_autonomy_policy(
        state=_state(tmp_path),
        signals=_consensus(flags=("partial_methodology_coverage",)),
        evaluated_at_ms=EVALUATED,
        activation_cutoff_ms=ACTIVATION,
    )
    assert allowed.candidate_action is PaperAction.BUY

    blocked = evaluate_autonomy_policy(
        state=_state(tmp_path / "second"),
        signals=_consensus(flags=("internal_direction_conflict:elliott",)),
        evaluated_at_ms=EVALUATED,
        activation_cutoff_ms=ACTIVATION,
    )
    assert blocked.reason_code is PaperAutonomyReason.UNSAFE_UNCERTAINTY


def test_automatic_reduce_is_never_emitted(tmp_path) -> None:
    bullish = evaluate_autonomy_policy(
        state=_state(tmp_path),
        signals=_consensus(),
        evaluated_at_ms=EVALUATED,
        activation_cutoff_ms=ACTIVATION,
    )
    held = replace(
        _state(tmp_path / "held"),
        cash_usdt=Decimal(80),
        positions=(PaperPosition(PaperSymbol.BTCUSDT, Decimal("0.2")),),
    )
    bearish = evaluate_autonomy_policy(
        state=held,
        signals=_consensus(direction=SignalDirection.BEARISH),
        evaluated_at_ms=EVALUATED,
        activation_cutoff_ms=ACTIVATION,
    )

    assert bullish.candidate_action is not PaperAction.REDUCE
    assert bearish.candidate_action is not PaperAction.REDUCE


def test_policy_surface_has_no_execution_network_or_order_authority() -> None:
    source = inspect.getsource(paper_autonomy).lower()
    forbidden = (
        "import requests",
        "import httpx",
        "import urllib",
        "import socket",
        "place_order",
        "submit_order",
        "cancel_order",
        "api_key",
        "api_secret",
        "ccxt",
        "subprocess",
        "launchctl",
    )
    assert all(token not in source for token in forbidden)
    assert paper_autonomy.REAL_CAPITAL == REAL_CAPITAL == 0
