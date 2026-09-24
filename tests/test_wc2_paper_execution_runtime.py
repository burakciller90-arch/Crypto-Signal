from __future__ import annotations

import inspect
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.data.models import Exchange
from crypto_signal.evaluation import untouched_forward_execution_runtime as runtime_module
from crypto_signal.evaluation.untouched_forward_collection_protocol import (
    build_wc2_collection_protocol,
)
from crypto_signal.evaluation.untouched_forward_execution_journal import (
    WC2PaperExecutionDecisionStatus,
    build_wc2_paper_execution_decision,
    compute_wc2_cost_evidence_identity,
    compute_wc2_paper_execution_event_identity,
)
from crypto_signal.evaluation.untouched_forward_execution_protocol import (
    build_wc2_paper_execution_protocol,
)
from crypto_signal.evaluation.untouched_forward_execution_runtime import (
    WC2_EXECUTION_RUNTIME_MAX_DECISION_DELAY_MS,
    WC2PaperExecutionRuntimeStore,
    build_wc2_execution_runtime_activation,
    replay_wc2_execution_state,
)
from crypto_signal.evaluation.untouched_forward_policy import (
    build_wc2_untouched_forward_policy,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.epoch2_accounting import (
    build_epoch2_activation_record,
    build_initial_epoch2_vault_snapshot,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import PaperAction, PaperSymbol


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _policy():
    return build_wc2_untouched_forward_policy(
        preregistered_at_ms=1_000,
        collection_start_ms=2_000,
    )


def _epoch2_activation():
    return build_epoch2_activation_record(
        activated_at_ms=3_000,
        epoch1_ledger_sha256=_sha("epoch1"),
    )


def _collection():
    return build_wc2_collection_protocol(
        review_policy=_policy(),
        activation=_epoch2_activation(),
        preregistered_at_ms=4_000,
        collection_start_ms=5_000,
    )


def _protocol():
    return build_wc2_paper_execution_protocol(
        review_policy=_policy(),
        collection_protocol=_collection(),
        activation=_epoch2_activation(),
        preregistered_at_ms=6_000,
        execution_start_ms=7_000,
    )


def _runtime_activation():
    return build_wc2_execution_runtime_activation(
        protocol=_protocol(),
        registered_at_ms=8_000,
        collection_start_ms=9_000,
    )


def _decision(
    *,
    seed: str,
    core_identity: str,
    action: PaperAction,
    quantity: Decimal | None = None,
    reference_price: Decimal | None = None,
    fill_price: Decimal | None = None,
    fee: Decimal = Decimal(0),
    spread: Decimal = Decimal(0),
    slippage: Decimal = Decimal(0),
):
    protocol = _protocol()
    freezes = (_sha(f"{seed}-binance"), _sha(f"{seed}-bybit"))
    event = compute_wc2_paper_execution_event_identity(
        execution_protocol_identity=protocol.protocol_identity,
        symbol=PaperSymbol.BTCUSDT,
        source_cutoff_open_time_ms=10_100,
        source_exchanges=(Exchange.BINANCE.value, Exchange.BYBIT.value),
        source_freeze_identities=freezes,
    )
    common = {
        "event_identity": event,
        "execution_protocol_identity": protocol.protocol_identity,
        "execution_start_ms": 9_000,
        "source_exchanges": (Exchange.BINANCE.value, Exchange.BYBIT.value),
        "source_freeze_identities": freezes,
        "source_forecast_identities": (
            _sha(f"{seed}-forecast-a"),
            _sha(f"{seed}-forecast-b"),
        ),
        "source_cohort_forecast_identities": (
            _sha(f"{seed}-cohort-a"),
            _sha(f"{seed}-cohort-b"),
        ),
        "source_signal_as_of_ms": (10_000, 10_000),
        "source_frozen_at_ms": (10_010, 10_011),
        "source_forecast_issued_at_ms": (10_020, 10_021),
        "source_cutoff_open_time_ms": 10_100,
        "symbol": PaperSymbol.BTCUSDT,
        "epoch2_core_snapshot_identity": core_identity,
        "decided_at_ms": 10_200,
        "autonomy_policy_version": "paper_autonomy_policy.v2",
    }
    if action is PaperAction.HOLD_CASH:
        return build_wc2_paper_execution_decision(
            **common,
            status=WC2PaperExecutionDecisionStatus.HOLD_CASH,
            action=action,
            reason_code="signal_not_active",
        )
    assert quantity is not None
    assert reference_price is not None
    assert fill_price is not None
    fill_identity = _sha(f"{seed}-fill")
    venue_reference = "binance_spot|paper-only"
    return build_wc2_paper_execution_decision(
        **common,
        status=WC2PaperExecutionDecisionStatus.EXECUTED,
        action=action,
        reason_code="paper_autonomy_trade_executed",
        execution_input_identity=_sha(f"{seed}-input"),
        sizing_identity=_sha(f"{seed}-sizing"),
        venue_rule_snapshot_identity=_sha(f"{seed}-rules"),
        pretrade_identity=_sha(f"{seed}-pretrade"),
        plan_identity=_sha(f"{seed}-plan"),
        fill_identity=fill_identity,
        cost_evidence_identity=compute_wc2_cost_evidence_identity(
            fill_identity=fill_identity,
            fee_usdt=fee,
            spread_usdt=spread,
            slippage_usdt=slippage,
            execution_policy_version="paper_execution_policy.v1",
            venue_reference=venue_reference,
        ),
        quantity=quantity,
        reference_price=reference_price,
        simulated_fill_price=fill_price,
        fee_usdt=fee,
        spread_usdt=spread,
        slippage_usdt=slippage,
        venue_reference=venue_reference,
    )


def test_runtime_activation_is_future_bound_and_append_only(tmp_path: Path) -> None:
    activation = _runtime_activation()
    assert activation.collection_start_ms > activation.registered_at_ms
    assert activation.collection_start_ms >= _protocol().execution_start_ms
    assert (
        activation.maximum_decision_delay_ms
        == WC2_EXECUTION_RUNTIME_MAX_DECISION_DELAY_MS
    )
    assert activation.historical_backfill_authority is False
    assert activation.production_authority is False
    assert activation.real_capital == 0

    path = tmp_path / "run.wc2-paper-execution-runtime.sqlite3"
    store = WC2PaperExecutionRuntimeStore(path)
    assert store.append(activation) is True
    assert store.append(activation) is False
    assert store.latest() == activation

    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute(
                "UPDATE wc2_paper_execution_runtime_activation "
                "SET collection_start_ms=1"
            )


def test_runtime_activation_rejects_protocol_backdating() -> None:
    with pytest.raises(ValueError, match="cannot predate execution protocol"):
        build_wc2_execution_runtime_activation(
            protocol=_protocol(),
            registered_at_ms=6_100,
            collection_start_ms=6_500,
        )


def test_execution_state_replay_uses_actual_fill_economics() -> None:
    activation = _epoch2_activation()
    core = build_initial_epoch2_vault_snapshot(activation, PaperVaultId.CORE)
    hold = _decision(
        seed="hold",
        core_identity=core.snapshot_identity,
        action=PaperAction.HOLD_CASH,
    )
    buy = _decision(
        seed="buy",
        core_identity=core.snapshot_identity,
        action=PaperAction.BUY,
        quantity=Decimal("1"),
        reference_price=Decimal("10"),
        fill_price=Decimal("10.01"),
        fee=Decimal("0.01"),
        spread=Decimal("0.005"),
        slippage=Decimal("0.005"),
    )
    state = replay_wc2_execution_state(
        core,
        (hold, buy),
        activation.activated_at_ms,
    )
    assert state.cash_usdt == Decimal("589.98")
    assert state.positions[0].symbol is PaperSymbol.BTCUSDT
    assert state.positions[0].quantity == Decimal("1")
    assert state.replayed_record_count == 1
    assert state.last_mutation_identity == buy.fill_identity


def test_replay_refuses_cross_core_or_impossible_cash() -> None:
    activation = _epoch2_activation()
    core = build_initial_epoch2_vault_snapshot(activation, PaperVaultId.CORE)
    wrong = _decision(
        seed="wrong",
        core_identity=_sha("different-core"),
        action=PaperAction.HOLD_CASH,
    )
    with pytest.raises(ValueError, match="CORE snapshot lineage"):
        replay_wc2_execution_state(core, (wrong,), activation.activated_at_ms)

    too_large = _decision(
        seed="large",
        core_identity=core.snapshot_identity,
        action=PaperAction.BUY,
        quantity=Decimal("100"),
        reference_price=Decimal("10"),
        fill_price=Decimal("10.01"),
        fee=Decimal("1"),
        spread=Decimal("0.5"),
        slippage=Decimal("0.5"),
    )
    with pytest.raises(ValueError, match="BUY exceeds cash"):
        replay_wc2_execution_state(core, (too_large,), activation.activated_at_ms)


def test_runtime_source_has_no_network_or_real_order_surface() -> None:
    source = inspect.getsource(runtime_module).lower()
    forbidden = (
        "import httpx",
        "import requests",
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
    assert runtime_module.REAL_CAPITAL == 0
