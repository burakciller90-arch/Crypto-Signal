"""End-to-end bounded tests for accepted paper pre-trade commit integration."""

from __future__ import annotations

import inspect
from decimal import Decimal

import pytest

from crypto_signal.confluence.models import (
    InvalidationTrigger,
    MethodologyKind,
    PriceZone,
    ScoreSemantic,
)
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.paper import pipeline as paper_pipeline
from crypto_signal.paper.autonomy import evaluate_autonomy_policy
from crypto_signal.paper.execution import build_frozen_execution_snapshot
from crypto_signal.paper.execution_input import (
    PAPER_EXECUTION_INPUT_POLICY_VERSION,
    FrozenPaperExecutionInput,
    compute_execution_input_identity,
)
from crypto_signal.paper.ledger import (
    PaperFundLedger,
    PaperLedgerWriteDisposition,
)
from crypto_signal.paper.models import (
    REAL_CAPITAL,
    PaperAction,
    PaperSymbol,
    build_decision_intent,
    build_fund_creation,
)
from crypto_signal.paper.pipeline import (
    PaperTradePipelineError,
    commit_planned_pretrade,
)
from crypto_signal.paper.planning import plan_hold_cash
from crypto_signal.paper.pretrade import (
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

AS_OF = 10_000
EVALUATED_AT = 10_100
OBSERVED_AT = 20_000
PLANNED_AT = 21_000


def _ledger_and_state(tmp_path):
    ledger = PaperFundLedger(tmp_path / "paper_pipeline.sqlite3")
    ledger.append_fund_creation(build_fund_creation(created_at_ms=1))
    return ledger, reconstruct_paper_fund_state(ledger)


def _signal(exchange: Exchange) -> SignalDecision:
    return SignalDecision(
        freeze_identity=("a" * 64 if exchange is Exchange.BINANCE else "b" * 64),
        signal_version="signal.test.v1",
        state=SignalState.ACTIVE,
        exchange=exchange,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="4h",
        as_of_ms=AS_OF,
        direction=SignalDirection.BULLISH,
        setup_type="test",
        geometry=SignalGeometry(
            source_evidence_id=f"{exchange.value}-geometry",
            source_methodology=MethodologyKind.HARMONIC,
            entry_zone=PriceZone(Decimal(95), Decimal(105)),
            entry_reference_price=Decimal(100),
            entry_reference_model=(
                EntryReferenceModel.ZONE_MIDPOINT_REFERENCE_NOT_EXECUTION
            ),
            invalidation_price=Decimal(90),
            invalidation_trigger=InvalidationTrigger.TOUCH_OR_CROSS,
            targets=(RiskRewardTarget("t1", Decimal(110), Decimal(1)),),
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
            MethodologyVersionRef(MethodologyKind.HARMONIC, "harmonic.v1"),
        ),
        probability_status=ProbabilityStatus.NOT_CALIBRATED,
        historical_stats_status=HistoricalStatsStatus.NOT_EVALUATED,
        uncertainty_flags=("partial_methodology_coverage",),
        evidence_summary=(),
    )


def _prepared_buy(tmp_path, *, min_notional: Decimal = Decimal(5)):
    ledger, state = _ledger_and_state(tmp_path)
    signals = (_signal(Exchange.BINANCE), _signal(Exchange.BYBIT))
    autonomy = evaluate_autonomy_policy(
        state=state,
        signals=signals,
        evaluated_at_ms=EVALUATED_AT,
        activation_cutoff_ms=AS_OF - 1,
    )
    assert autonomy.candidate_action is PaperAction.BUY

    kwargs = {
        "policy_version": PAPER_EXECUTION_INPUT_POLICY_VERSION,
        "candidate_action": PaperAction.BUY,
        "symbol": PaperSymbol.BTCUSDT,
        "source_freeze_identities": autonomy.source_freeze_identities,
        "signal_as_of_ms": AS_OF,
        "source_exchange": Exchange.BINANCE,
        "source_market_type": MarketType.SPOT,
        "source_timeframe": "15m",
        "source_candle_open_time_ms": 11_000,
        "source_candle_close_time_ms": 19_000,
        "source_candle_ingested_at_ms": 19_100,
        "source_adapter_version": "adapter.test.v1",
        "reference_price": Decimal(100),
        "price_field": "open",
    }
    execution_input = FrozenPaperExecutionInput(
        input_identity=compute_execution_input_identity(**kwargs),
        observed_at_ms=OBSERVED_AT,
        real_capital=REAL_CAPITAL,
        **kwargs,
    )
    sizing = size_paper_candidate(
        state=state,
        autonomy_decision=autonomy,
        execution_input=execution_input,
        signals=signals,
    )
    snapshot = build_frozen_execution_snapshot(
        venue_reference=execution_input.venue_reference,
        symbol=PaperSymbol.BTCUSDT,
        quantity_step=Decimal("0.01"),
        min_quantity=Decimal("0.01"),
        min_notional_usdt=min_notional,
        fee_rate=Decimal("0.001"),
        spread_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"),
    )
    pretrade = prepare_paper_trade_plan(
        state=state,
        sizing=sizing,
        execution_input=execution_input,
        execution_snapshot=snapshot,
        planned_at_ms=PLANNED_AT,
    )
    return ledger, state, execution_input, snapshot, pretrade


def test_planned_buy_orchestrates_and_commits_atomically(tmp_path) -> None:
    ledger, state, _, snapshot, pretrade = _prepared_buy(tmp_path)
    assert pretrade.status is PaperPretradeStatus.PLANNED

    result = commit_planned_pretrade(
        ledger=ledger,
        state=state,
        pretrade=pretrade,
        execution_snapshot=snapshot,
    )

    assert result.commit.disposition is PaperLedgerWriteDisposition.INSERTED
    assert len(result.commit.record_identities) == 3
    assert result.bundle.fill is not None
    assert result.bundle.mutation is not None
    assert result.bundle.fill.venue_reference == snapshot.execution_reference
    assert result.commit.state_after.cash_usdt < state.cash_usdt
    assert result.commit.state_after.positions[0].symbol is PaperSymbol.BTCUSDT
    assert result.commit.state_after.positions[0].quantity == pretrade.planned_quantity
    assert reconstruct_paper_fund_state(ledger) == result.commit.state_after
    assert result.real_capital == REAL_CAPITAL == 0


def test_exact_retry_is_idempotent_from_original_state(tmp_path) -> None:
    ledger, state, _, snapshot, pretrade = _prepared_buy(tmp_path)

    first = commit_planned_pretrade(
        ledger=ledger,
        state=state,
        pretrade=pretrade,
        execution_snapshot=snapshot,
    )
    replay_after_first = ledger.replay()
    second = commit_planned_pretrade(
        ledger=ledger,
        state=state,
        pretrade=pretrade,
        execution_snapshot=snapshot,
    )

    assert first.commit.disposition is PaperLedgerWriteDisposition.INSERTED
    assert second.commit.disposition is PaperLedgerWriteDisposition.UNCHANGED
    assert second.commit.state_after == first.commit.state_after
    assert ledger.replay() == replay_after_first


def test_stale_state_is_rejected_without_pipeline_write(tmp_path) -> None:
    ledger, state, _, snapshot, pretrade = _prepared_buy(tmp_path)
    hold = plan_hold_cash(
        state=state,
        planned_at_ms=20_500,
        reason="intervening decision",
        invalidation_context="test",
    )
    unrelated = build_decision_intent(
        fund_identity=hold.fund_identity,
        decided_at_ms=hold.planned_at_ms,
        action=PaperAction.HOLD_CASH,
        reason=hold.reason,
        invalidation_context=hold.invalidation_context,
    )
    ledger.append_decision_intent(unrelated)
    before = ledger.replay()

    with pytest.raises(ValueError, match="stale"):
        commit_planned_pretrade(
            ledger=ledger,
            state=state,
            pretrade=pretrade,
            execution_snapshot=snapshot,
        )

    assert ledger.replay() == before


def test_snapshot_identity_mismatch_fails_before_ledger_write(tmp_path) -> None:
    ledger, state, execution_input, snapshot, pretrade = _prepared_buy(tmp_path)
    different = build_frozen_execution_snapshot(
        venue_reference=execution_input.venue_reference,
        symbol=PaperSymbol.BTCUSDT,
        quantity_step=snapshot.quantity_step,
        min_quantity=snapshot.min_quantity,
        min_notional_usdt=snapshot.min_notional_usdt,
        fee_rate=Decimal("0.002"),
        spread_rate=snapshot.spread_rate,
        slippage_rate=snapshot.slippage_rate,
    )
    before = ledger.replay()

    with pytest.raises(PaperTradePipelineError, match="snapshot identity mismatch"):
        commit_planned_pretrade(
            ledger=ledger,
            state=state,
            pretrade=pretrade,
            execution_snapshot=different,
        )

    assert ledger.replay() == before


def test_rejected_pretrade_never_reaches_ledger(tmp_path) -> None:
    ledger, state, _, snapshot, pretrade = _prepared_buy(
        tmp_path,
        min_notional=Decimal(1000),
    )
    assert pretrade.status is PaperPretradeStatus.REJECTED
    before = ledger.replay()

    with pytest.raises(PaperTradePipelineError, match="PLANNED"):
        commit_planned_pretrade(
            ledger=ledger,
            state=state,
            pretrade=pretrade,
            execution_snapshot=snapshot,
        )

    assert ledger.replay() == before


def test_pipeline_surface_has_no_network_order_or_runtime_activation_authority() -> None:
    source = inspect.getsource(paper_pipeline).lower()
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
        "run_paper_runtime_tick",
        "freeze_execution_input_from_cache",
        "evaluate_autonomy_policy",
    )
    assert all(token not in source for token in forbidden)
    assert paper_pipeline.REAL_CAPITAL == REAL_CAPITAL == 0
