"""Focused tests for paper_position_sizing_policy.v1."""

from __future__ import annotations

import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.confluence.models import (
    InvalidationTrigger,
    MethodologyKind,
    PriceZone,
    ScoreSemantic,
)
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.paper import sizing as paper_sizing
from crypto_signal.paper.autonomy import (
    PAPER_AUTONOMY_POLICY_VERSION,
    PaperAutonomyDecision,
    PaperAutonomyReason,
)
from crypto_signal.paper.execution_input import (
    PAPER_EXECUTION_INPUT_POLICY_VERSION,
    FrozenPaperExecutionInput,
    compute_execution_input_identity,
)
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.models import (
    REAL_CAPITAL,
    PaperAction,
    PaperPosition,
    PaperSymbol,
    build_fund_creation,
)
from crypto_signal.paper.sizing import (
    PAPER_POSITION_SIZING_POLICY_VERSION,
    PaperPositionSizingError,
    PaperPositionSizingReason,
    PaperPositionSizingStatus,
    size_paper_candidate,
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


def _state(tmp_path):
    ledger = PaperFundLedger(tmp_path / "paper.sqlite3")
    ledger.append_fund_creation(build_fund_creation(created_at_ms=1))
    return reconstruct_paper_fund_state(ledger)


def _signal(
    exchange: Exchange,
    *,
    direction: SignalDirection,
    invalidation: Decimal,
    zone_low: Decimal = Decimal(95),
    zone_high: Decimal = Decimal(105),
) -> SignalDecision:
    freeze = "a" * 64 if exchange is Exchange.BINANCE else "b" * 64
    target = Decimal(110) if direction is SignalDirection.BULLISH else Decimal(90)
    return SignalDecision(
        freeze_identity=freeze,
        signal_version="signal.test.v1",
        state=SignalState.ACTIVE,
        exchange=exchange,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="4h",
        as_of_ms=1_000,
        direction=direction,
        setup_type="test",
        geometry=SignalGeometry(
            source_evidence_id=f"{exchange.value}-g",
            source_methodology=MethodologyKind.HARMONIC,
            entry_zone=PriceZone(zone_low, zone_high),
            entry_reference_price=Decimal(100),
            entry_reference_model=(
                EntryReferenceModel.ZONE_MIDPOINT_REFERENCE_NOT_EXECUTION
            ),
            invalidation_price=invalidation,
            invalidation_trigger=InvalidationTrigger.TOUCH_OR_CROSS,
            targets=(RiskRewardTarget("t1", target, Decimal(1)),),
        ),
        agreement=SignalAgreementSummary(
            confluence_score=Decimal("66.67"),
            score_semantic=ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY,
            support_method_count=2,
            opposing_method_count=0,
            resolved_method_count=2,
            total_methodology_slots=3,
            pairwise_relations=(),
        ),
        selected_evidence_ids=(f"{exchange.value}-1", f"{exchange.value}-2"),
        methodology_versions=(
            MethodologyVersionRef(MethodologyKind.PRICE_ACTION, "pa.v1"),
            MethodologyVersionRef(MethodologyKind.HARMONIC, "h.v1"),
        ),
        probability_status=ProbabilityStatus.NOT_CALIBRATED,
        historical_stats_status=HistoricalStatsStatus.NOT_EVALUATED,
        uncertainty_flags=("partial_methodology_coverage",),
        evidence_summary=(),
    )


def _autonomy(action: PaperAction) -> PaperAutonomyDecision:
    return PaperAutonomyDecision(
        policy_version=PAPER_AUTONOMY_POLICY_VERSION,
        evaluated_at_ms=1_050,
        activation_cutoff_ms=900,
        candidate_action=action,
        symbol=PaperSymbol.BTCUSDT,
        source_freeze_identities=("a" * 64, "b" * 64),
        source_as_of_ms=1_000,
        reason_code=(
            PaperAutonomyReason.BUY_ELIGIBLE
            if action is PaperAction.BUY
            else PaperAutonomyReason.EXIT_ELIGIBLE
        ),
        reason="test",
        max_position_risk_usdt=(
            Decimal("1.00") if action is PaperAction.BUY else Decimal(0)
        ),
        execution_input_required=True,
        real_capital=REAL_CAPITAL,
    )


def _execution_input(
    action: PaperAction,
    *,
    reference_price: Decimal = Decimal(100),
) -> FrozenPaperExecutionInput:
    kwargs = {
        "policy_version": PAPER_EXECUTION_INPUT_POLICY_VERSION,
        "candidate_action": action,
        "symbol": PaperSymbol.BTCUSDT,
        "source_freeze_identities": ("a" * 64, "b" * 64),
        "signal_as_of_ms": 1_000,
        "source_exchange": Exchange.BINANCE,
        "source_market_type": MarketType.SPOT,
        "source_timeframe": "15m",
        "source_candle_open_time_ms": 1_100,
        "source_candle_close_time_ms": 2_000,
        "source_candle_ingested_at_ms": 2_001,
        "source_adapter_version": "adapter.test.v1",
        "reference_price": reference_price,
        "price_field": "open",
    }
    identity = compute_execution_input_identity(**kwargs)
    return FrozenPaperExecutionInput(
        input_identity=identity,
        observed_at_ms=2_100,
        real_capital=REAL_CAPITAL,
        **kwargs,
    )


def _bullish():
    return (
        _signal(
            Exchange.BINANCE,
            direction=SignalDirection.BULLISH,
            invalidation=Decimal(95),
        ),
        _signal(
            Exchange.BYBIT,
            direction=SignalDirection.BULLISH,
            invalidation=Decimal(90),
        ),
    )


def _bearish():
    return (
        _signal(
            Exchange.BINANCE,
            direction=SignalDirection.BEARISH,
            invalidation=Decimal(110),
        ),
        _signal(
            Exchange.BYBIT,
            direction=SignalDirection.BEARISH,
            invalidation=Decimal(111),
        ),
    )


def test_buy_uses_widest_provider_risk_distance(tmp_path) -> None:
    decision = size_paper_candidate(
        state=_state(tmp_path),
        autonomy_decision=_autonomy(PaperAction.BUY),
        execution_input=_execution_input(PaperAction.BUY),
        signals=_bullish(),
    )
    assert decision.status is PaperPositionSizingStatus.SIZED
    assert decision.reason_code is PaperPositionSizingReason.BUY_RISK_SIZED
    assert decision.policy_version == PAPER_POSITION_SIZING_POLICY_VERSION
    assert decision.conservative_invalidation_price == Decimal(90)
    assert decision.risk_per_unit_usdt == Decimal(10)
    assert decision.max_position_risk_usdt == Decimal("1.00")
    assert decision.raw_quantity == Decimal("0.1")
    assert decision.raw_quantity * decision.risk_per_unit_usdt == Decimal("1.00")
    assert decision.venue_rule_check_required is True
    assert decision.cost_adjustment_required is True


def test_buy_rejects_reference_outside_any_entry_zone(tmp_path) -> None:
    decision = size_paper_candidate(
        state=_state(tmp_path),
        autonomy_decision=_autonomy(PaperAction.BUY),
        execution_input=_execution_input(PaperAction.BUY, reference_price=Decimal(106)),
        signals=_bullish(),
    )
    assert decision.status is PaperPositionSizingStatus.REJECTED
    assert decision.reason_code is PaperPositionSizingReason.REFERENCE_OUTSIDE_ENTRY_ZONE
    assert decision.raw_quantity is None


def test_buy_rejects_reference_at_or_below_invalidation(tmp_path) -> None:
    signals = (
        _signal(
            Exchange.BINANCE,
            direction=SignalDirection.BULLISH,
            invalidation=Decimal(90),
            zone_low=Decimal(80),
            zone_high=Decimal(110),
        ),
        _signal(
            Exchange.BYBIT,
            direction=SignalDirection.BULLISH,
            invalidation=Decimal(95),
            zone_low=Decimal(80),
            zone_high=Decimal(110),
        ),
    )
    decision = size_paper_candidate(
        state=_state(tmp_path),
        autonomy_decision=_autonomy(PaperAction.BUY),
        execution_input=_execution_input(PaperAction.BUY, reference_price=Decimal(92)),
        signals=signals,
    )
    assert decision.status is PaperPositionSizingStatus.REJECTED
    assert decision.reason_code is PaperPositionSizingReason.REFERENCE_NOT_ABOVE_INVALIDATION


def test_exit_sizes_exact_full_existing_position(tmp_path) -> None:
    state = replace(
        _state(tmp_path),
        cash_usdt=Decimal(80),
        positions=(PaperPosition(PaperSymbol.BTCUSDT, Decimal("0.1234")),),
    )
    decision = size_paper_candidate(
        state=state,
        autonomy_decision=_autonomy(PaperAction.EXIT),
        execution_input=_execution_input(PaperAction.EXIT, reference_price=Decimal(98)),
        signals=_bearish(),
    )
    assert decision.status is PaperPositionSizingStatus.SIZED
    assert decision.reason_code is PaperPositionSizingReason.EXIT_FULL_POSITION
    assert decision.raw_quantity == Decimal("0.1234")
    assert decision.max_position_risk_usdt == Decimal(0)
    assert decision.conservative_invalidation_price is None


def test_exit_without_position_is_rejected(tmp_path) -> None:
    decision = size_paper_candidate(
        state=_state(tmp_path),
        autonomy_decision=_autonomy(PaperAction.EXIT),
        execution_input=_execution_input(PaperAction.EXIT),
        signals=_bearish(),
    )
    assert decision.status is PaperPositionSizingStatus.REJECTED
    assert decision.reason_code is PaperPositionSizingReason.NO_POSITION_TO_EXIT


def test_execution_input_lineage_mismatch_fails_closed(tmp_path) -> None:
    source = _execution_input(PaperAction.BUY)
    kwargs = {
        "policy_version": source.policy_version,
        "candidate_action": source.candidate_action,
        "symbol": source.symbol,
        "source_freeze_identities": ("c" * 64, "d" * 64),
        "signal_as_of_ms": source.signal_as_of_ms,
        "source_exchange": source.source_exchange,
        "source_market_type": source.source_market_type,
        "source_timeframe": source.source_timeframe,
        "source_candle_open_time_ms": source.source_candle_open_time_ms,
        "source_candle_close_time_ms": source.source_candle_close_time_ms,
        "source_candle_ingested_at_ms": source.source_candle_ingested_at_ms,
        "source_adapter_version": source.source_adapter_version,
        "reference_price": source.reference_price,
        "price_field": source.price_field,
    }
    bad = FrozenPaperExecutionInput(
        input_identity=compute_execution_input_identity(**kwargs),
        observed_at_ms=source.observed_at_ms,
        real_capital=REAL_CAPITAL,
        **kwargs,
    )
    with pytest.raises(PaperPositionSizingError, match="signal lineage"):
        size_paper_candidate(
            state=_state(tmp_path),
            autonomy_decision=_autonomy(PaperAction.BUY),
            execution_input=bad,
            signals=_bullish(),
        )


def test_sizing_identity_is_deterministic(tmp_path) -> None:
    state = _state(tmp_path)
    autonomy = _autonomy(PaperAction.BUY)
    execution_input = _execution_input(PaperAction.BUY)
    signals = _bullish()
    first = size_paper_candidate(
        state=state,
        autonomy_decision=autonomy,
        execution_input=execution_input,
        signals=signals,
    )
    second = size_paper_candidate(
        state=state,
        autonomy_decision=autonomy,
        execution_input=execution_input,
        signals=signals,
    )
    assert first == second
    assert len(first.sizing_identity) == 64


def test_sizing_surface_has_no_network_order_or_ledger_authority() -> None:
    source = inspect.getsource(paper_sizing).lower()
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
        "paperfundledger",
        "append_",
    )
    assert all(token not in source for token in forbidden)
    assert paper_sizing.REAL_CAPITAL == REAL_CAPITAL == 0
