"""Focused tests for paper_pretrade_bridge_policy.v1."""

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
from crypto_signal.paper import pretrade as paper_pretrade
from crypto_signal.paper.autonomy import (
    PAPER_AUTONOMY_POLICY_VERSION,
    PaperAutonomyDecision,
    PaperAutonomyReason,
)
from crypto_signal.paper.execution import (
    build_frozen_execution_snapshot,
    simulate_paper_fill,
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
from crypto_signal.paper.pretrade import (
    PAPER_PRETRADE_BRIDGE_POLICY_VERSION,
    PaperPretradeError,
    PaperPretradeReason,
    PaperPretradeStatus,
    prepare_paper_trade_plan,
)
from crypto_signal.paper.sizing import size_paper_candidate
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

AS_OF = 1_000
EVALUATED_AT = 1_050


def _state(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
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
):
    return SignalDecision(
        freeze_identity=("a" * 64 if exchange is Exchange.BINANCE else "b" * 64),
        signal_version="signal.test.v1",
        state=SignalState.ACTIVE,
        exchange=exchange,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="4h",
        as_of_ms=AS_OF,
        direction=direction,
        setup_type="test",
        geometry=SignalGeometry(
            source_evidence_id=f"{exchange.value}-g",
            source_methodology=MethodologyKind.HARMONIC,
            entry_zone=PriceZone(zone_low, zone_high),
            entry_reference_price=Decimal(100),
            entry_reference_model=EntryReferenceModel.ZONE_MIDPOINT_REFERENCE_NOT_EXECUTION,
            invalidation_price=invalidation,
            invalidation_trigger=InvalidationTrigger.TOUCH_OR_CROSS,
            targets=(
                RiskRewardTarget(
                    "t1",
                    Decimal(110) if direction is SignalDirection.BULLISH else Decimal(90),
                    Decimal(1),
                ),
            ),
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


def _signals(
    direction: SignalDirection,
    *,
    invalidation: Decimal,
):
    return (
        _signal(Exchange.BINANCE, direction=direction, invalidation=invalidation),
        _signal(Exchange.BYBIT, direction=direction, invalidation=invalidation),
    )


def _autonomy(action: PaperAction):
    return PaperAutonomyDecision(
        policy_version=PAPER_AUTONOMY_POLICY_VERSION,
        evaluated_at_ms=EVALUATED_AT,
        activation_cutoff_ms=900,
        candidate_action=action,
        symbol=PaperSymbol.BTCUSDT,
        source_freeze_identities=("a" * 64, "b" * 64),
        source_as_of_ms=AS_OF,
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


def _execution_input(action: PaperAction, *, reference: Decimal = Decimal(100)):
    kwargs = {
        "policy_version": PAPER_EXECUTION_INPUT_POLICY_VERSION,
        "candidate_action": action,
        "symbol": PaperSymbol.BTCUSDT,
        "source_freeze_identities": ("a" * 64, "b" * 64),
        "signal_as_of_ms": AS_OF,
        "source_exchange": Exchange.BINANCE,
        "source_market_type": MarketType.SPOT,
        "source_timeframe": "15m",
        "source_candle_open_time_ms": 1_100,
        "source_candle_close_time_ms": 2_000,
        "source_candle_ingested_at_ms": 2_001,
        "source_adapter_version": "adapter.test.v1",
        "reference_price": reference,
        "price_field": "open",
    }
    return FrozenPaperExecutionInput(
        input_identity=compute_execution_input_identity(**kwargs),
        observed_at_ms=2_100,
        real_capital=REAL_CAPITAL,
        **kwargs,
    )


def _snapshot(
    execution_input: FrozenPaperExecutionInput,
    *,
    step: Decimal = Decimal("0.01"),
    minimum: Decimal = Decimal("0.01"),
    min_notional: Decimal = Decimal(5),
):
    return build_frozen_execution_snapshot(
        venue_reference=execution_input.venue_reference,
        symbol=PaperSymbol.BTCUSDT,
        quantity_step=step,
        min_quantity=minimum,
        min_notional_usdt=min_notional,
        fee_rate=Decimal("0.001"),
        spread_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"),
    )


def _buy_sizing(tmp_path, *, invalidation: Decimal):
    state = _state(tmp_path)
    autonomy = _autonomy(PaperAction.BUY)
    execution_input = _execution_input(PaperAction.BUY)
    sizing = size_paper_candidate(
        state=state,
        autonomy_decision=autonomy,
        execution_input=execution_input,
        signals=_signals(SignalDirection.BULLISH, invalidation=invalidation),
    )
    return state, execution_input, sizing


def test_buy_rounds_only_down_and_builds_planner_approved_plan(tmp_path) -> None:
    state, execution_input, sizing = _buy_sizing(
        tmp_path,
        invalidation=Decimal(92),
    )
    snapshot = _snapshot(execution_input, step=Decimal("0.03"))

    decision = prepare_paper_trade_plan(
        state=state,
        sizing=sizing,
        execution_input=execution_input,
        execution_snapshot=snapshot,
        planned_at_ms=3_000,
    )

    assert decision.status is PaperPretradeStatus.PLANNED
    assert decision.reason_code is PaperPretradeReason.PLANNED
    assert decision.policy_version == PAPER_PRETRADE_BRIDGE_POLICY_VERSION
    assert decision.raw_quantity is not None
    assert decision.planned_quantity == Decimal("0.12")
    assert decision.planned_quantity <= decision.raw_quantity
    assert decision.plan is not None
    assert decision.plan.quantity == Decimal("0.12")
    assert decision.plan.reference_price == Decimal(100)
    assert len(decision.pretrade_identity) == 64


def test_cost_budget_exactly_covers_same_snapshot_simulator(tmp_path) -> None:
    state, execution_input, sizing = _buy_sizing(
        tmp_path,
        invalidation=Decimal(90),
    )
    snapshot = _snapshot(execution_input)

    decision = prepare_paper_trade_plan(
        state=state,
        sizing=sizing,
        execution_input=execution_input,
        execution_snapshot=snapshot,
        planned_at_ms=3_000,
    )
    assert decision.plan is not None
    simulated = simulate_paper_fill(
        plan=decision.plan,
        snapshot=snapshot,
        decision_identity="c" * 64,
        filled_at_ms=3_000,
    )
    assert simulated.total_cost_usdt == decision.cost_budget_usdt
    assert simulated.total_cost_usdt == decision.plan.cost_budget_usdt


def test_buy_below_minimum_notional_is_rejected(tmp_path) -> None:
    state, execution_input, sizing = _buy_sizing(
        tmp_path,
        invalidation=Decimal(90),
    )
    snapshot = _snapshot(execution_input, min_notional=Decimal(20))

    decision = prepare_paper_trade_plan(
        state=state,
        sizing=sizing,
        execution_input=execution_input,
        execution_snapshot=snapshot,
        planned_at_ms=3_000,
    )
    assert decision.status is PaperPretradeStatus.REJECTED
    assert decision.reason_code is PaperPretradeReason.BELOW_MINIMUM_NOTIONAL
    assert decision.plan is None


def test_planner_independently_rejects_concentration_breach(tmp_path) -> None:
    state, execution_input, sizing = _buy_sizing(
        tmp_path,
        invalidation=Decimal("97.5"),
    )
    snapshot = _snapshot(execution_input)

    decision = prepare_paper_trade_plan(
        state=state,
        sizing=sizing,
        execution_input=execution_input,
        execution_snapshot=snapshot,
        planned_at_ms=3_000,
    )
    assert decision.status is PaperPretradeStatus.REJECTED
    assert decision.reason_code is PaperPretradeReason.PLANNER_REJECTED
    assert decision.rejection_detail is not None
    assert "concentration" in decision.rejection_detail


def test_exit_requires_exact_full_position_step(tmp_path) -> None:
    state = replace(
        _state(tmp_path),
        cash_usdt=Decimal(80),
        positions=(PaperPosition(PaperSymbol.BTCUSDT, Decimal("0.1234")),),
    )
    autonomy = _autonomy(PaperAction.EXIT)
    execution_input = _execution_input(PaperAction.EXIT, reference=Decimal(98))
    sizing = size_paper_candidate(
        state=state,
        autonomy_decision=autonomy,
        execution_input=execution_input,
        signals=_signals(SignalDirection.BEARISH, invalidation=Decimal(110)),
    )
    snapshot = _snapshot(execution_input, step=Decimal("0.001"))

    decision = prepare_paper_trade_plan(
        state=state,
        sizing=sizing,
        execution_input=execution_input,
        execution_snapshot=snapshot,
        planned_at_ms=3_000,
    )
    assert decision.status is PaperPretradeStatus.REJECTED
    assert decision.reason_code is PaperPretradeReason.EXIT_STEP_MISMATCH


def test_exit_exact_step_builds_full_exit_plan(tmp_path) -> None:
    state = replace(
        _state(tmp_path),
        cash_usdt=Decimal(80),
        positions=(PaperPosition(PaperSymbol.BTCUSDT, Decimal("0.1234")),),
    )
    autonomy = _autonomy(PaperAction.EXIT)
    execution_input = _execution_input(PaperAction.EXIT, reference=Decimal(98))
    sizing = size_paper_candidate(
        state=state,
        autonomy_decision=autonomy,
        execution_input=execution_input,
        signals=_signals(SignalDirection.BEARISH, invalidation=Decimal(110)),
    )
    snapshot = _snapshot(execution_input, step=Decimal("0.0001"))

    decision = prepare_paper_trade_plan(
        state=state,
        sizing=sizing,
        execution_input=execution_input,
        execution_snapshot=snapshot,
        planned_at_ms=3_000,
    )
    assert decision.status is PaperPretradeStatus.PLANNED
    assert decision.plan is not None
    assert decision.plan.action is PaperAction.EXIT
    assert decision.plan.quantity == Decimal("0.1234")


def test_snapshot_must_bind_exact_frozen_execution_input(tmp_path) -> None:
    state, execution_input, sizing = _buy_sizing(
        tmp_path,
        invalidation=Decimal(90),
    )
    bad = build_frozen_execution_snapshot(
        venue_reference="unbound:test",
        symbol=PaperSymbol.BTCUSDT,
        quantity_step=Decimal("0.01"),
        min_quantity=Decimal("0.01"),
        min_notional_usdt=Decimal(5),
        fee_rate=Decimal("0.001"),
        spread_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"),
    )
    with pytest.raises(PaperPretradeError, match="not bound"):
        prepare_paper_trade_plan(
            state=state,
            sizing=sizing,
            execution_input=execution_input,
            execution_snapshot=bad,
            planned_at_ms=3_000,
        )


def test_plan_time_cannot_predate_frozen_execution_input(tmp_path) -> None:
    state, execution_input, sizing = _buy_sizing(
        tmp_path,
        invalidation=Decimal(90),
    )
    snapshot = _snapshot(execution_input)

    with pytest.raises(PaperPretradeError, match="cannot predate"):
        prepare_paper_trade_plan(
            state=state,
            sizing=sizing,
            execution_input=execution_input,
            execution_snapshot=snapshot,
            planned_at_ms=2_000,
        )


def test_planned_decision_rechecks_embedded_plan_lineage(tmp_path) -> None:
    state, execution_input, sizing = _buy_sizing(
        tmp_path,
        invalidation=Decimal(90),
    )
    snapshot = _snapshot(execution_input)
    decision = prepare_paper_trade_plan(
        state=state,
        sizing=sizing,
        execution_input=execution_input,
        execution_snapshot=snapshot,
        planned_at_ms=3_000,
    )
    assert decision.status is PaperPretradeStatus.PLANNED
    with pytest.raises(ValueError, match="plan action mismatch"):
        replace(decision, action=PaperAction.EXIT)


def test_pretrade_surface_has_no_network_fill_or_ledger_authority() -> None:
    source = inspect.getsource(paper_pretrade).lower()
    forbidden = (
        "import requests",
        "import httpx",
        "import urllib",
        "import socket",
        "sqlite3",
        "place_order",
        "submit_order",
        "cancel_order",
        "api_key",
        "api_secret",
        "ccxt",
        "subprocess",
        "launchctl",
        "simulate_paper_fill",
        "paperfundledger",
        "commit_orchestration_bundle",
    )
    assert all(token not in source for token in forbidden)
    assert paper_pretrade.REAL_CAPITAL == REAL_CAPITAL == 0
