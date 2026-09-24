"""WC6 paper execution-lab recovery/reconciliation acceptance."""

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
from crypto_signal.paper import execution_lab, execution_lab_lifecycle
from crypto_signal.paper.activation import (
    activate_paper_policy,
    commit_planned_pretrade_event,
)
from crypto_signal.paper.autonomy import evaluate_autonomy_policy
from crypto_signal.paper.execution import build_frozen_execution_snapshot
from crypto_signal.paper.execution_input import (
    PAPER_EXECUTION_INPUT_POLICY_VERSION,
    FrozenPaperExecutionInput,
    compute_execution_input_identity,
)
from crypto_signal.paper.execution_lab import (
    WC6ExecutionLabError,
    WC6ExecutionLabSemantic,
    WC6PartialFillStatus,
    WC6SandboxAdapterStatus,
    build_wc6_execution_lab_dossier,
    probe_disabled_paper_write_authority,
)
from crypto_signal.paper.execution_lab_lifecycle import (
    WC6PartialFillSupport,
    WC6ShadowLifecycleError,
    WC6ShadowOrderStatus,
    build_wc6_partial_fill_scenario,
    simulate_wc6_shadow_order_lifecycle,
)
from crypto_signal.paper.ledger import (
    PaperFundLedger,
    PaperLedgerWriteDisposition,
)
from crypto_signal.paper.models import (
    REAL_CAPITAL,
    PaperAction,
    PaperSymbol,
    build_fund_creation,
)
from crypto_signal.paper.pretrade import prepare_paper_trade_plan
from crypto_signal.paper.sizing import size_paper_candidate
from crypto_signal.paper.state import reconstruct_paper_fund_state
from crypto_signal.paper.write_authority import append_paper_write_authority_event
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
        setup_type="wc6-test",
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


def _prepared_cycle(tmp_path):
    ledger = PaperFundLedger(tmp_path / "wc6_execution_lab.sqlite3")
    ledger.append_fund_creation(build_fund_creation(created_at_ms=1))
    state = reconstruct_paper_fund_state(ledger)

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
        "source_adapter_version": "adapter.wc6.test.v1",
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
        min_notional_usdt=Decimal(5),
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
    activation = activate_paper_policy(
        ledger=ledger,
        state=state,
        activated_at_ms=AS_OF - 1,
        baseline_signal_freeze_count=1,
        baseline_latest_signal_freeze_identity="f" * 64,
        baseline_latest_frozen_at_ms=AS_OF - 2,
    )[1]
    enabled = append_paper_write_authority_event(
        ledger=ledger,
        activation=activation,
        enabled=True,
        created_at_ms=OBSERVED_AT + 1,
        reason="WC6 paper execution lab reviewed enable",
        reviewed_event_identities=("c" * 64,),
        reviewed_trace_identities=("d" * 64,),
    )[1]
    return (
        ledger,
        state,
        execution_input,
        snapshot,
        pretrade,
        activation,
        enabled,
    )


def _complete_cycle(tmp_path):
    (
        ledger,
        state,
        execution_input,
        snapshot,
        pretrade,
        activation,
        enabled,
    ) = _prepared_cycle(tmp_path)

    first = commit_planned_pretrade_event(
        ledger=ledger,
        state=state,
        activation=activation,
        pretrade=pretrade,
        execution_input=execution_input,
        execution_snapshot=snapshot,
        required_authority_event_identity=enabled.authority_event_identity,
    )
    retry = commit_planned_pretrade_event(
        ledger=ledger,
        state=state,
        activation=activation,
        pretrade=pretrade,
        execution_input=execution_input,
        execution_snapshot=snapshot,
        required_authority_event_identity=enabled.authority_event_identity,
    )
    disabled = append_paper_write_authority_event(
        ledger=ledger,
        activation=activation,
        enabled=False,
        created_at_ms=PLANNED_AT + 1,
        reason="WC6 paper execution lab kill switch",
    )[1]
    probe = probe_disabled_paper_write_authority(
        ledger=ledger,
        state=state,
        activation=activation,
        pretrade=pretrade,
        execution_input=execution_input,
        execution_snapshot=snapshot,
        disabled_authority=disabled,
    )
    dossier = build_wc6_execution_lab_dossier(
        state_before=state,
        first_commit=first,
        retry_commit=retry,
        enabled_authority=enabled,
        disabled_authority=disabled,
        kill_switch_probe=probe,
    )
    return (
        ledger,
        state,
        first,
        retry,
        enabled,
        disabled,
        probe,
        dossier,
    )


def test_wc6_execution_lab_dossier_binds_recovery_reconciliation_and_kill_switch(
    tmp_path,
) -> None:
    (
        ledger,
        state,
        first,
        retry,
        enabled,
        disabled,
        probe,
        dossier,
    ) = _complete_cycle(tmp_path)

    assert first.pipeline.commit.disposition is PaperLedgerWriteDisposition.INSERTED
    assert retry.pipeline.commit.disposition is PaperLedgerWriteDisposition.UNCHANGED
    assert first.receipt == retry.receipt
    assert first.pipeline.commit.state_after == retry.pipeline.commit.state_after
    assert reconstruct_paper_fund_state(ledger) == first.pipeline.commit.state_after

    assert enabled.enabled is True
    assert disabled.enabled is False
    assert disabled.previous_event_identity == enabled.authority_event_identity
    assert probe.rejected_by_disabled_authority is True
    assert probe.ledger_unchanged is True

    assert dossier.semantic is (
        WC6ExecutionLabSemantic.PAPER_RECOVERY_RECONCILIATION_NO_LIVE_ORDER_AUTHORITY
    )
    assert dossier.first_commit_disposition is PaperLedgerWriteDisposition.INSERTED
    assert dossier.retry_commit_disposition is PaperLedgerWriteDisposition.UNCHANGED
    assert dossier.exact_retry_idempotence_proven is True
    assert dossier.duplicate_prevention_proven is True
    assert dossier.reconciliation_proven is True
    assert dossier.kill_switch_proven is True
    assert dossier.state_before_identity != dossier.state_after_identity
    assert dossier.sandbox_adapter_status is WC6SandboxAdapterStatus.NOT_IMPLEMENTED
    assert dossier.partial_fill_status is WC6PartialFillStatus.UNSUPPORTED_V1
    assert dossier.network_authority is False
    assert dossier.credential_authority is False
    assert dossier.live_order_authority is False
    assert dossier.production_authority is False
    assert dossier.real_capital == state.real_capital == REAL_CAPITAL == 0


def test_wc6_execution_lab_cycle_is_deterministic(tmp_path) -> None:
    first = _complete_cycle(tmp_path / "first")[-1]
    second = _complete_cycle(tmp_path / "second")[-1]
    assert first == second


def test_wc6_kill_switch_probe_rejects_enabled_authority(tmp_path) -> None:
    (
        ledger,
        state,
        execution_input,
        snapshot,
        pretrade,
        activation,
        enabled,
    ) = _prepared_cycle(tmp_path)

    with pytest.raises(WC6ExecutionLabError, match="disabled authority"):
        probe_disabled_paper_write_authority(
            ledger=ledger,
            state=state,
            activation=activation,
            pretrade=pretrade,
            execution_input=execution_input,
            execution_snapshot=snapshot,
            disabled_authority=enabled,
        )


def test_wc6_execution_lab_source_has_no_external_order_surface() -> None:
    source = inspect.getsource(execution_lab).lower()
    forbidden = (
        "import requests",
        "import httpx",
        "import urllib",
        "import socket",
        "api_key",
        "api_secret",
        "ccxt",
        "place_order",
        "submit_order",
        "cancel_order",
        "launchctl",
        "subprocess",
        "api.binance.com",
        "testnet.binance",
        "sandbox_url",
        "sandbox_client",
    )
    assert all(token not in source for token in forbidden)
    assert "not_implemented" in source
    assert "unsupported_v1" in source
    assert execution_lab.REAL_CAPITAL == 0



def _committed_trade_for_shadow_lifecycle(tmp_path):
    (
        ledger,
        state,
        execution_input,
        snapshot,
        pretrade,
        activation,
        enabled,
    ) = _prepared_cycle(tmp_path)
    commit = commit_planned_pretrade_event(
        ledger=ledger,
        state=state,
        activation=activation,
        pretrade=pretrade,
        execution_input=execution_input,
        execution_snapshot=snapshot,
        required_authority_event_identity=enabled.authority_event_identity,
    )
    return ledger, commit, snapshot


def test_wc6_shadow_partial_fill_lifecycle_reconciles_to_canonical_accounting(
    tmp_path,
) -> None:
    ledger, commit, snapshot = _committed_trade_for_shadow_lifecycle(tmp_path)
    canonical_fill = commit.pipeline.bundle.fill
    assert canonical_fill is not None
    assert canonical_fill.quantity > snapshot.quantity_step

    first_quantity = snapshot.quantity_step
    second_quantity = canonical_fill.quantity - first_quantity
    scenario = build_wc6_partial_fill_scenario(
        commit=commit,
        execution_snapshot=snapshot,
        ack_latency_ms=25,
        fill_latency_ms=(50, 125),
        partial_quantities=(first_quantity, second_quantity),
    )
    lifecycle = simulate_wc6_shadow_order_lifecycle(
        commit=commit,
        execution_snapshot=snapshot,
        scenario=scenario,
    )

    assert lifecycle.final_status is WC6ShadowOrderStatus.FILLED
    assert lifecycle.partial_fill_support is (
        WC6PartialFillSupport.LAB_ONLY_CANONICAL_UNSUPPORTED
    )
    assert lifecycle.acknowledgement.acknowledged_at_ms == (
        commit.pipeline.bundle.decision.decided_at_ms + 25
    )
    assert len(lifecycle.partial_fills) == 2
    assert lifecycle.partial_fills[0].filled_at_ms == (
        commit.pipeline.bundle.decision.decided_at_ms + 50
    )
    assert lifecycle.partial_fills[1].filled_at_ms == (
        commit.pipeline.bundle.decision.decided_at_ms + 125
    )
    assert lifecycle.partial_fills[-1].cumulative_quantity == canonical_fill.quantity
    assert lifecycle.filled_quantity == canonical_fill.quantity
    assert lifecycle.canonical_fill_price == canonical_fill.simulated_fill_price
    assert lifecycle.shadow_notional_usdt == lifecycle.canonical_notional_usdt
    assert lifecycle.quantity_reconciled is True
    assert lifecycle.notional_reconciled is True
    assert lifecycle.accounting_shadow_reconciled is True
    assert lifecycle.canonical_partial_fills_supported is False
    assert lifecycle.sandbox_adapter_implemented is False
    assert lifecycle.network_authority is False
    assert lifecycle.credential_authority is False
    assert lifecycle.live_order_authority is False
    assert lifecycle.production_authority is False
    assert lifecycle.real_capital == REAL_CAPITAL == 0

    replay_before = ledger.replay()
    second = simulate_wc6_shadow_order_lifecycle(
        commit=commit,
        execution_snapshot=snapshot,
        scenario=scenario,
    )
    assert second == lifecycle
    assert ledger.replay() == replay_before


def test_wc6_partial_fill_scenario_rejects_quantity_mismatch(tmp_path) -> None:
    _, commit, snapshot = _committed_trade_for_shadow_lifecycle(tmp_path)
    canonical_fill = commit.pipeline.bundle.fill
    assert canonical_fill is not None

    with pytest.raises(
        WC6ShadowLifecycleError,
        match="sum to canonical fill quantity",
    ):
        build_wc6_partial_fill_scenario(
            commit=commit,
            execution_snapshot=snapshot,
            ack_latency_ms=10,
            fill_latency_ms=(20, 30),
            partial_quantities=(
                snapshot.quantity_step,
                snapshot.quantity_step,
            ),
        )


def test_wc6_partial_fill_scenario_rejects_fill_before_ack(tmp_path) -> None:
    _, commit, snapshot = _committed_trade_for_shadow_lifecycle(tmp_path)
    canonical_fill = commit.pipeline.bundle.fill
    assert canonical_fill is not None
    first_quantity = snapshot.quantity_step
    second_quantity = canonical_fill.quantity - first_quantity

    with pytest.raises(ValueError, match="predate acknowledgement"):
        build_wc6_partial_fill_scenario(
            commit=commit,
            execution_snapshot=snapshot,
            ack_latency_ms=50,
            fill_latency_ms=(40, 75),
            partial_quantities=(first_quantity, second_quantity),
        )


def test_wc6_shadow_lifecycle_source_has_no_canonical_write_or_order_surface() -> None:
    source = inspect.getsource(execution_lab_lifecycle).lower()
    forbidden = (
        "paperfundledger",
        "commit_planned_pretrade_event",
        "append_paper_write_authority_event",
        "import requests",
        "import httpx",
        "import urllib",
        "import socket",
        "api_key",
        "api_secret",
        "ccxt",
        "place_order",
        "submit_order",
        "cancel_order",
        "launchctl",
        "subprocess",
    )
    assert all(token not in source for token in forbidden)
    assert "canonical_partial_fills_supported: bool = false" in source
    assert "sandbox_adapter_implemented: bool = false" in source
    assert execution_lab_lifecycle.REAL_CAPITAL == 0
