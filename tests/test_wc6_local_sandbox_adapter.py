"""WC6 local deterministic sandbox adapter acceptance."""

from __future__ import annotations

import inspect
import sqlite3
from decimal import Decimal

import pytest

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.paper import local_sandbox_adapter
from crypto_signal.paper.activation import (
    activate_paper_policy,
    commit_planned_pretrade_event,
)
from crypto_signal.paper.execution_input import (
    PAPER_EXECUTION_INPUT_POLICY_VERSION,
    FrozenPaperExecutionInput,
    compute_execution_input_identity,
)
from crypto_signal.paper.execution_lab_lifecycle import (
    WC6PartialFillSupport,
    build_wc6_partial_fill_scenario,
    simulate_wc6_shadow_order_lifecycle,
)
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.local_sandbox_adapter import (
    WC6ExternalTestnetStatus,
    WC6LocalSandboxAdapterStatus,
    WC6LocalSandboxJournal,
    WC6SandboxJournalConflict,
    WC6SandboxJournalDisposition,
    WC6SandboxRejectReason,
    build_local_sandbox_accepted_order,
    build_local_sandbox_rejection,
    build_wc6_local_sandbox_dossier,
)
from crypto_signal.paper.models import (
    REAL_CAPITAL,
    PaperAction,
    PaperSymbol,
    build_fund_creation,
)
from crypto_signal.paper.pretrade import PaperPretradeReason, PaperPretradeStatus
from crypto_signal.paper.sizing import (
    PAPER_POSITION_SIZING_POLICY_VERSION,
    PaperPositionSizingDecision,
    PaperPositionSizingReason,
    PaperPositionSizingStatus,
    compute_position_sizing_identity,
)
from crypto_signal.paper.state import reconstruct_paper_fund_state
from crypto_signal.paper.venue_rules import (
    FrozenBinanceSpotVenueRules,
    parse_binance_spot_venue_rules,
    prepare_authoritative_paper_trade_plan,
)
from crypto_signal.paper.write_authority import append_paper_write_authority_event


SOURCE_IDS = ("a" * 64, "b" * 64)


def _venue_payload(*, max_quantity: str = "9000") -> dict[str, object]:
    return {
        "timezone": "UTC",
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "status": "TRADING",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "isSpotTradingAllowed": True,
                "orderTypes": ["LIMIT", "MARKET"],
                "filters": [
                    {
                        "filterType": "PRICE_FILTER",
                        "minPrice": "0.01",
                        "maxPrice": "1000000",
                        "tickSize": "0.01",
                    },
                    {
                        "filterType": "LOT_SIZE",
                        "minQty": "0.00001",
                        "maxQty": max_quantity,
                        "stepSize": "0.00001",
                    },
                    {
                        "filterType": "NOTIONAL",
                        "minNotional": "5",
                        "applyMinToMarket": True,
                        "maxNotional": "100000000",
                    },
                ],
            }
        ],
    }


def _execution_input() -> FrozenPaperExecutionInput:
    kwargs = {
        "policy_version": PAPER_EXECUTION_INPUT_POLICY_VERSION,
        "candidate_action": PaperAction.BUY,
        "symbol": PaperSymbol.BTCUSDT,
        "source_freeze_identities": SOURCE_IDS,
        "signal_as_of_ms": 10_000,
        "source_exchange": Exchange.BINANCE,
        "source_market_type": MarketType.SPOT,
        "source_timeframe": "15m",
        "source_candle_open_time_ms": 11_000,
        "source_candle_close_time_ms": 19_000,
        "source_candle_ingested_at_ms": 19_100,
        "source_adapter_version": "wc6-local-sandbox-fixture/1",
        "reference_price": Decimal(100),
        "price_field": "open",
    }
    return FrozenPaperExecutionInput(
        input_identity=compute_execution_input_identity(**kwargs),
        observed_at_ms=20_000,
        real_capital=REAL_CAPITAL,
        **kwargs,
    )


def _sizing(execution_input: FrozenPaperExecutionInput) -> PaperPositionSizingDecision:
    raw_quantity = Decimal("0.10")
    kwargs = {
        "policy_version": PAPER_POSITION_SIZING_POLICY_VERSION,
        "status": PaperPositionSizingStatus.SIZED,
        "reason_code": PaperPositionSizingReason.BUY_RISK_SIZED,
        "action": PaperAction.BUY,
        "symbol": PaperSymbol.BTCUSDT,
        "execution_input_identity": execution_input.input_identity,
        "source_freeze_identities": SOURCE_IDS,
        "reference_price": execution_input.reference_price,
        "conservative_invalidation_price": Decimal(90),
        "risk_per_unit_usdt": Decimal(10),
        "max_position_risk_usdt": raw_quantity * Decimal(10),
        "raw_quantity": raw_quantity,
        "venue_rule_check_required": True,
        "cost_adjustment_required": True,
    }
    return PaperPositionSizingDecision(
        sizing_identity=compute_position_sizing_identity(**kwargs),
        real_capital=REAL_CAPITAL,
        **kwargs,
    )


def _rules(*, max_quantity: str = "9000") -> FrozenBinanceSpotVenueRules:
    return parse_binance_spot_venue_rules(
        _venue_payload(max_quantity=max_quantity),
        symbol=PaperSymbol.BTCUSDT,
        observed_at_ms=19_500,
    )


def _prepared(tmp_path):
    ledger = PaperFundLedger(tmp_path / "wc6_local_sandbox_paper.sqlite3")
    ledger.append_fund_creation(build_fund_creation(created_at_ms=1))
    state = reconstruct_paper_fund_state(ledger)
    execution_input = _execution_input()
    sizing = _sizing(execution_input)

    accepted_rules = _rules()
    accepted_bound = prepare_authoritative_paper_trade_plan(
        state=state,
        sizing=sizing,
        execution_input=execution_input,
        venue_rules=accepted_rules,
        planned_at_ms=21_000,
    )
    assert accepted_bound.pretrade.status is PaperPretradeStatus.PLANNED

    rejected_rules = _rules(max_quantity="0.05")
    rejected_bound = prepare_authoritative_paper_trade_plan(
        state=state,
        sizing=sizing,
        execution_input=execution_input,
        venue_rules=rejected_rules,
        planned_at_ms=21_000,
    )
    assert rejected_bound.pretrade.status is PaperPretradeStatus.REJECTED
    assert (
        rejected_bound.pretrade.reason_code
        is PaperPretradeReason.ABOVE_MAXIMUM_QUANTITY
    )

    activation = activate_paper_policy(
        ledger=ledger,
        state=state,
        activated_at_ms=9_999,
        baseline_signal_freeze_count=1,
        baseline_latest_signal_freeze_identity="f" * 64,
        baseline_latest_frozen_at_ms=9_998,
    )[1]
    enabled = append_paper_write_authority_event(
        ledger=ledger,
        activation=activation,
        enabled=True,
        created_at_ms=20_001,
        reason="WC6 local sandbox reviewed enable",
        reviewed_event_identities=("c" * 64,),
        reviewed_trace_identities=("d" * 64,),
    )[1]
    commit = commit_planned_pretrade_event(
        ledger=ledger,
        state=state,
        activation=activation,
        pretrade=accepted_bound.pretrade,
        execution_input=execution_input,
        execution_snapshot=accepted_bound.execution_snapshot,
        required_authority_event_identity=enabled.authority_event_identity,
    )
    canonical_fill = commit.pipeline.bundle.fill
    assert canonical_fill is not None
    first_quantity = accepted_bound.execution_snapshot.quantity_step
    second_quantity = canonical_fill.quantity - first_quantity
    assert second_quantity > Decimal(0)

    scenario = build_wc6_partial_fill_scenario(
        commit=commit,
        execution_snapshot=accepted_bound.execution_snapshot,
        ack_latency_ms=25,
        fill_latency_ms=(50, 125),
        partial_quantities=(first_quantity, second_quantity),
    )
    lifecycle = simulate_wc6_shadow_order_lifecycle(
        commit=commit,
        execution_snapshot=accepted_bound.execution_snapshot,
        scenario=scenario,
    )
    alternate_scenario = build_wc6_partial_fill_scenario(
        commit=commit,
        execution_snapshot=accepted_bound.execution_snapshot,
        ack_latency_ms=30,
        fill_latency_ms=(60, 140),
        partial_quantities=(first_quantity, second_quantity),
    )
    alternate_lifecycle = simulate_wc6_shadow_order_lifecycle(
        commit=commit,
        execution_snapshot=accepted_bound.execution_snapshot,
        scenario=alternate_scenario,
    )
    return (
        ledger,
        activation,
        enabled,
        accepted_rules,
        accepted_bound,
        rejected_rules,
        rejected_bound,
        lifecycle,
        alternate_lifecycle,
    )


def _complete(tmp_path):
    (
        ledger,
        activation,
        enabled,
        accepted_rules,
        accepted_bound,
        rejected_rules,
        rejected_bound,
        lifecycle,
        alternate_lifecycle,
    ) = _prepared(tmp_path)

    accepted = build_local_sandbox_accepted_order(
        paper_ledger=ledger,
        lifecycle=lifecycle,
        bound_pretrade=accepted_bound,
        venue_rules=accepted_rules,
        authority=enabled,
    )
    conflicting = build_local_sandbox_accepted_order(
        paper_ledger=ledger,
        lifecycle=alternate_lifecycle,
        bound_pretrade=accepted_bound,
        venue_rules=accepted_rules,
        authority=enabled,
    )
    venue_rejection = build_local_sandbox_rejection(
        paper_ledger=ledger,
        bound_pretrade=rejected_bound,
        venue_rules=rejected_rules,
        authority=enabled,
        submitted_at_ms=30_000,
        acknowledgement_latency_ms=12,
    )

    journal_path = tmp_path / "wc6_local_sandbox_journal.sqlite3"
    first_journal = WC6LocalSandboxJournal(journal_path)
    first_disposition = first_journal.append(accepted)
    restarted_journal = WC6LocalSandboxJournal(journal_path)
    retry_disposition = restarted_journal.append(accepted)

    disabled = append_paper_write_authority_event(
        ledger=ledger,
        activation=activation,
        enabled=False,
        created_at_ms=30_100,
        reason="WC6 local sandbox kill switch",
    )[1]
    kill_switch_rejection = build_local_sandbox_rejection(
        paper_ledger=ledger,
        bound_pretrade=accepted_bound,
        venue_rules=accepted_rules,
        authority=disabled,
        submitted_at_ms=30_200,
        acknowledgement_latency_ms=8,
    )
    dossier = build_wc6_local_sandbox_dossier(
        accepted_order=accepted,
        lifecycle=lifecycle,
        venue_rejection=venue_rejection,
        kill_switch_rejection=kill_switch_rejection,
        first_journal_disposition=first_disposition,
        restart_retry_disposition=retry_disposition,
    )
    return (
        ledger,
        accepted,
        conflicting,
        lifecycle,
        venue_rejection,
        kill_switch_rejection,
        journal_path,
        dossier,
    )


def test_wc6_local_sandbox_adapter_builds_complete_no_network_dossier(
    tmp_path,
) -> None:
    (
        ledger,
        accepted,
        _,
        lifecycle,
        venue_rejection,
        kill_switch_rejection,
        _,
        dossier,
    ) = _complete(tmp_path)

    assert accepted.lifecycle_identity == lifecycle.lifecycle_identity
    assert accepted.acknowledgement_latency_ms == 25
    assert accepted.final_fill_latency_ms == 125
    assert len(accepted.partial_fill_identities) == 2
    assert accepted.adapter_status is (
        WC6LocalSandboxAdapterStatus.IMPLEMENTED_NO_NETWORK
    )
    assert accepted.external_testnet_status is WC6ExternalTestnetStatus.NOT_CONNECTED

    assert venue_rejection.reason is WC6SandboxRejectReason.VENUE_POLICY_REJECTED
    assert venue_rejection.detail == "above_maximum_quantity"
    assert venue_rejection.fill_count == 0
    assert kill_switch_rejection.reason is (
        WC6SandboxRejectReason.KILL_SWITCH_DISABLED
    )
    assert kill_switch_rejection.fill_count == 0
    assert kill_switch_rejection.client_order_key == accepted.client_order_key

    assert dossier.first_journal_disposition is WC6SandboxJournalDisposition.INSERTED
    assert dossier.restart_retry_disposition is WC6SandboxJournalDisposition.UNCHANGED
    assert dossier.partial_fill_count == 2
    assert dossier.acknowledgement_latency_ms == 25
    assert dossier.final_fill_latency_ms == 125
    assert dossier.quantity_reconciled is True
    assert dossier.notional_reconciled is True
    assert dossier.accounting_shadow_reconciled is True
    assert dossier.venue_rejection_proven is True
    assert dossier.kill_switch_proven is True
    assert dossier.duplicate_prevention_proven is True
    assert dossier.restart_idempotence_proven is True
    assert dossier.partial_fill_support is (
        WC6PartialFillSupport.LAB_ONLY_CANONICAL_UNSUPPORTED
    )
    assert dossier.adapter_status is (
        WC6LocalSandboxAdapterStatus.IMPLEMENTED_NO_NETWORK
    )
    assert dossier.external_testnet_status is WC6ExternalTestnetStatus.NOT_CONNECTED
    assert dossier.network_authority is False
    assert dossier.credential_authority is False
    assert dossier.live_order_authority is False
    assert dossier.production_authority is False
    assert dossier.real_capital == REAL_CAPITAL == 0

    state_after = reconstruct_paper_fund_state(ledger)
    assert state_after.last_mutation_identity == lifecycle.canonical_mutation_identity


def test_wc6_local_sandbox_journal_is_restart_idempotent_and_duplicate_closed(
    tmp_path,
) -> None:
    _, accepted, conflicting, _, _, _, journal_path, _ = _complete(tmp_path)

    restarted = WC6LocalSandboxJournal(journal_path)
    assert restarted.append(accepted) is WC6SandboxJournalDisposition.UNCHANGED
    assert conflicting.client_order_key == accepted.client_order_key
    assert conflicting.adapter_order_identity != accepted.adapter_order_identity
    with pytest.raises(WC6SandboxJournalConflict, match="client-order key"):
        restarted.append(conflicting)


def test_wc6_local_sandbox_journal_rejects_update_delete(tmp_path) -> None:
    _, accepted, _, _, _, _, journal_path, _ = _complete(tmp_path)

    with sqlite3.connect(journal_path) as connection:
        for statement in (
            "UPDATE wc6_local_sandbox_orders "
            "SET payload_json = payload_json WHERE client_order_key = ?",
            "DELETE FROM wc6_local_sandbox_orders WHERE client_order_key = ?",
        ):
            with pytest.raises(
                sqlite3.IntegrityError,
                match="immutable WC6 local sandbox journal",
            ):
                connection.execute(statement, (accepted.client_order_key,))


def test_wc6_local_sandbox_dossier_is_deterministic(tmp_path) -> None:
    first = _complete(tmp_path / "first")[-1]
    second = _complete(tmp_path / "second")[-1]
    assert first == second


def test_wc6_local_sandbox_source_has_no_external_order_surface() -> None:
    source = inspect.getsource(local_sandbox_adapter).lower()
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
        "api.binance.com",
        "testnet.binance",
        "sandbox_url",
        "subprocess",
        "launchctl",
    )
    assert all(token not in source for token in forbidden)
    assert "implemented_no_network" in source
    assert "not_connected" in source
    assert local_sandbox_adapter.REAL_CAPITAL == 0
