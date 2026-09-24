"""WC6 deterministic local-sandbox lifecycle acceptance."""

from __future__ import annotations

import inspect
import sqlite3
from decimal import Decimal

import pytest

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.paper import local_sandbox
from crypto_signal.paper.activation import activate_paper_policy
from crypto_signal.paper.execution_input import (
    PAPER_EXECUTION_INPUT_POLICY_VERSION,
    FrozenPaperExecutionInput,
    compute_execution_input_identity,
)
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.local_sandbox import (
    WC6ExternalTestnetStatus,
    WC6LocalSandboxJournal,
    WC6SandboxAdapterStatus,
    WC6SandboxJournalConflict,
    WC6SandboxJournalDisposition,
    WC6SandboxOrderStatus,
    WC6SandboxPartialFillStatus,
    WC6SandboxRejectReason,
    build_local_sandbox_trace,
    build_wc6_sandbox_execution_dossier,
)
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction, PaperSymbol, build_fund_creation
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
        "source_adapter_version": "sandbox-fixture/1",
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
    ledger = PaperFundLedger(tmp_path / "wc6_sandbox_paper.sqlite3")
    ledger.append_fund_creation(build_fund_creation(created_at_ms=1))
    state = reconstruct_paper_fund_state(ledger)
    execution_input = _execution_input()
    sizing = _sizing(execution_input)

    accepted_rules = _rules()
    accepted = prepare_authoritative_paper_trade_plan(
        state=state,
        sizing=sizing,
        execution_input=execution_input,
        venue_rules=accepted_rules,
        planned_at_ms=21_000,
    )
    assert accepted.pretrade.status is PaperPretradeStatus.PLANNED

    rejected_rules = _rules(max_quantity="0.05")
    rejected = prepare_authoritative_paper_trade_plan(
        state=state,
        sizing=sizing,
        execution_input=execution_input,
        venue_rules=rejected_rules,
        planned_at_ms=21_000,
    )
    assert rejected.pretrade.status is PaperPretradeStatus.REJECTED
    assert (
        rejected.pretrade.reason_code
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
    return (
        ledger,
        state,
        activation,
        enabled,
        accepted_rules,
        accepted,
        rejected_rules,
        rejected,
    )


def _complete(tmp_path):
    (
        ledger,
        state,
        activation,
        enabled,
        accepted_rules,
        accepted,
        rejected_rules,
        rejected,
    ) = _prepared(tmp_path)

    accepted_trace = build_local_sandbox_trace(
        paper_ledger=ledger,
        state=state,
        bound_pretrade=accepted,
        venue_rules=accepted_rules,
        authority=enabled,
        submitted_at_ms=30_000,
        acknowledgement_latency_ms=10,
        partial_fill_quantities=(Decimal("0.04"), Decimal("0.06")),
        partial_fill_latency_ms=(25, 55),
    )
    conflicting_trace = build_local_sandbox_trace(
        paper_ledger=ledger,
        state=state,
        bound_pretrade=accepted,
        venue_rules=accepted_rules,
        authority=enabled,
        submitted_at_ms=30_000,
        acknowledgement_latency_ms=10,
        partial_fill_quantities=(Decimal("0.04"), Decimal("0.06")),
        partial_fill_latency_ms=(30, 60),
    )
    venue_rejection = build_local_sandbox_trace(
        paper_ledger=ledger,
        state=state,
        bound_pretrade=rejected,
        venue_rules=rejected_rules,
        authority=enabled,
        submitted_at_ms=30_100,
        acknowledgement_latency_ms=12,
    )

    journal_path = tmp_path / "wc6_local_sandbox.sqlite3"
    first_journal = WC6LocalSandboxJournal(journal_path)
    first_disposition = first_journal.append(accepted_trace)
    restarted_journal = WC6LocalSandboxJournal(journal_path)
    retry_disposition = restarted_journal.append(accepted_trace)

    disabled = append_paper_write_authority_event(
        ledger=ledger,
        activation=activation,
        enabled=False,
        created_at_ms=30_200,
        reason="WC6 local sandbox kill switch",
    )[1]
    kill_switch = build_local_sandbox_trace(
        paper_ledger=ledger,
        state=state,
        bound_pretrade=accepted,
        venue_rules=accepted_rules,
        authority=disabled,
        submitted_at_ms=30_300,
        acknowledgement_latency_ms=8,
    )
    dossier = build_wc6_sandbox_execution_dossier(
        accepted_trace=accepted_trace,
        venue_rejection_trace=venue_rejection,
        kill_switch_trace=kill_switch,
        first_journal_disposition=first_disposition,
        retry_journal_disposition=retry_disposition,
    )
    return (
        ledger,
        accepted_trace,
        conflicting_trace,
        venue_rejection,
        kill_switch,
        journal_path,
        dossier,
    )


def test_wc6_local_sandbox_dossier_closes_order_lifecycle_and_reconciliation(
    tmp_path,
) -> None:
    (
        ledger,
        accepted,
        _,
        rejected,
        kill_switch,
        _,
        dossier,
    ) = _complete(tmp_path)

    assert accepted.status is WC6SandboxOrderStatus.FILLED
    assert accepted.acknowledgement.accepted is True
    assert accepted.acknowledgement_latency_ms == 10
    assert accepted.final_fill_latency_ms == 55
    assert len(accepted.fill_fragments) == 2
    assert accepted.fill_fragments[0].remaining_quantity == Decimal("0.06")
    assert accepted.fill_fragments[1].remaining_quantity == Decimal(0)
    assert accepted.weighted_fill_price == accepted.canonical_fill_price
    assert accepted.canonical_fill_price != accepted.reference_price
    assert accepted.simulated_slippage_usdt is not None
    assert accepted.simulated_slippage_usdt > Decimal(0)

    assert rejected.status is WC6SandboxOrderStatus.REJECTED
    assert (
        rejected.acknowledgement.reject_reason
        is WC6SandboxRejectReason.PRETRADE_REJECTED
    )
    assert rejected.fill_fragments == ()

    assert kill_switch.status is WC6SandboxOrderStatus.REJECTED
    assert (
        kill_switch.acknowledgement.reject_reason
        is WC6SandboxRejectReason.KILL_SWITCH_DISABLED
    )
    assert kill_switch.client_order_key == accepted.client_order_key

    assert dossier.first_journal_disposition is WC6SandboxJournalDisposition.INSERTED
    assert dossier.retry_journal_disposition is WC6SandboxJournalDisposition.UNCHANGED
    assert dossier.partial_fill_count == 2
    assert dossier.intended_quantity == Decimal("0.10")
    assert dossier.reconciled_filled_quantity == Decimal("0.10")
    assert dossier.weighted_fill_price == dossier.canonical_fill_price
    assert dossier.latency_simulation_proven is True
    assert dossier.slippage_simulation_proven is True
    assert dossier.partial_fill_simulation_proven is True
    assert dossier.venue_rejection_proven is True
    assert dossier.kill_switch_proven is True
    assert dossier.duplicate_prevention_proven is True
    assert dossier.restart_idempotence_proven is True
    assert dossier.reconciliation_proven is True
    assert (
        dossier.sandbox_adapter_status
        is WC6SandboxAdapterStatus.LOCAL_DETERMINISTIC_SANDBOX
    )
    assert dossier.external_testnet_status is WC6ExternalTestnetStatus.NOT_CONNECTED
    assert (
        dossier.partial_fill_status
        is WC6SandboxPartialFillStatus.SUPPORTED_SANDBOX_ONLY
    )
    assert dossier.network_authority is False
    assert dossier.credential_authority is False
    assert dossier.live_order_authority is False
    assert dossier.production_authority is False
    assert dossier.real_capital == REAL_CAPITAL == 0
    assert reconstruct_paper_fund_state(ledger).replayed_record_count == 1


def test_wc6_local_sandbox_restart_retry_is_idempotent_and_conflict_closed(
    tmp_path,
) -> None:
    _, accepted, conflicting, _, _, journal_path, _ = _complete(tmp_path)

    restarted = WC6LocalSandboxJournal(journal_path)
    assert restarted.append(accepted) is WC6SandboxJournalDisposition.UNCHANGED
    with pytest.raises(WC6SandboxJournalConflict, match="client-order key"):
        restarted.append(conflicting)


def test_wc6_local_sandbox_journal_rejects_update_and_delete(tmp_path) -> None:
    _, accepted, _, _, _, journal_path, _ = _complete(tmp_path)

    with sqlite3.connect(journal_path) as connection:
        for statement in (
            "UPDATE wc6_sandbox_traces SET created_at_ms = created_at_ms + 1 "
            "WHERE client_order_key = ?",
            "DELETE FROM wc6_sandbox_traces WHERE client_order_key = ?",
        ):
            with pytest.raises(
                sqlite3.IntegrityError,
                match="immutable WC6 sandbox journal",
            ):
                connection.execute(statement, (accepted.client_order_key,))


def test_wc6_local_sandbox_is_deterministic_across_fresh_journals(tmp_path) -> None:
    first = _complete(tmp_path / "first")[-1]
    second = _complete(tmp_path / "second")[-1]
    assert first == second


def test_wc6_local_sandbox_rejects_invalid_partial_fill_schedule(tmp_path) -> None:
    (
        ledger,
        state,
        _,
        enabled,
        accepted_rules,
        accepted,
        _,
        _,
    ) = _prepared(tmp_path)

    with pytest.raises(local_sandbox.WC6SandboxError, match="must sum"):
        build_local_sandbox_trace(
            paper_ledger=ledger,
            state=state,
            bound_pretrade=accepted,
            venue_rules=accepted_rules,
            authority=enabled,
            submitted_at_ms=30_000,
            acknowledgement_latency_ms=10,
            partial_fill_quantities=(Decimal("0.04"), Decimal("0.05")),
            partial_fill_latency_ms=(25, 55),
        )


def test_wc6_local_sandbox_source_has_no_network_credential_or_order_surface() -> None:
    source = inspect.getsource(local_sandbox).lower()
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
        "sandbox_client",
        "subprocess",
        "launchctl",
    )
    assert all(token not in source for token in forbidden)
    assert "not_connected" in source
    assert "supported_sandbox_only" in source
    assert local_sandbox.REAL_CAPITAL == 0
