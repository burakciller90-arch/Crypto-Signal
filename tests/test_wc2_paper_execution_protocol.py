from __future__ import annotations

import sqlite3
from dataclasses import fields, replace
from pathlib import Path

import pytest

from crypto_signal.evaluation.untouched_forward_collection_protocol import (
    build_wc2_collection_protocol,
)
from crypto_signal.evaluation.untouched_forward_execution_protocol import (
    WC2_PAPER_EXECUTION_DECISION_MODE,
    WC2_PAPER_EXECUTION_ECONOMIC_CLAIM_RULE,
    WC2_PAPER_EXECUTION_FILL_MODE,
    WC2_PAPER_EXECUTION_REFERENCE_MODE,
    WC2_PAPER_EXECUTION_VENUE_MODE,
    WC2PaperExecutionProtocolStore,
    build_wc2_paper_execution_protocol,
)
from crypto_signal.evaluation.untouched_forward_policy import (
    build_wc2_untouched_forward_policy,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.autonomy import (
    DEFAULT_AUTONOMY_COOLDOWN_MS,
    DEFAULT_AUTONOMY_DECISION_TIMEFRAME,
    DEFAULT_AUTONOMY_MAX_POSITION_RISK_FRACTION,
    DEFAULT_AUTONOMY_MAX_SIGNAL_AGE_MS,
    DEFAULT_AUTONOMY_REQUIRED_EXCHANGES,
    PAPER_AUTONOMY_POLICY_VERSION,
)
from crypto_signal.paper.epoch2_accounting import (
    build_epoch2_activation_record,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.execution_input import PAPER_EXECUTION_INPUT_POLICY_VERSION
from crypto_signal.paper.models import PAPER_EXECUTION_POLICY_VERSION
from crypto_signal.paper.sizing import PAPER_POSITION_SIZING_POLICY_VERSION
from crypto_signal.paper.venue_rules import (
    DEFAULT_SIMULATED_FEE_RATE,
    DEFAULT_SIMULATED_SLIPPAGE_RATE,
    DEFAULT_SIMULATED_SPREAD_RATE,
    PAPER_SIMULATED_COST_POLICY_VERSION,
    PAPER_VENUE_RULE_SNAPSHOT_SCHEMA_VERSION,
)


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _policy():
    return build_wc2_untouched_forward_policy(
        preregistered_at_ms=1_000,
        collection_start_ms=2_000,
    )


def _activation():
    return build_epoch2_activation_record(
        activated_at_ms=3_000,
        epoch1_ledger_sha256=_sha("epoch1"),
    )


def _collection():
    return build_wc2_collection_protocol(
        review_policy=_policy(),
        activation=_activation(),
        preregistered_at_ms=4_000,
        collection_start_ms=5_000,
    )


def _protocol(*, preregistered_at_ms: int = 6_000, start: int = 7_000):
    return build_wc2_paper_execution_protocol(
        review_policy=_policy(),
        collection_protocol=_collection(),
        activation=_activation(),
        preregistered_at_ms=preregistered_at_ms,
        execution_start_ms=start,
    )


def test_execution_protocol_freezes_only_preaccepted_paper_contracts() -> None:
    protocol = _protocol()

    assert protocol.vault_id is PaperVaultId.CORE
    assert protocol.decision_mode == WC2_PAPER_EXECUTION_DECISION_MODE
    assert protocol.autonomy_policy_version == PAPER_AUTONOMY_POLICY_VERSION
    assert protocol.autonomy_decision_timeframe == DEFAULT_AUTONOMY_DECISION_TIMEFRAME
    assert protocol.autonomy_required_exchanges == tuple(
        item.value for item in DEFAULT_AUTONOMY_REQUIRED_EXCHANGES
    )
    assert (
        protocol.autonomy_max_position_risk_fraction
        == DEFAULT_AUTONOMY_MAX_POSITION_RISK_FRACTION
    )
    assert protocol.autonomy_cooldown_ms == DEFAULT_AUTONOMY_COOLDOWN_MS
    assert (
        protocol.autonomy_max_signal_age_ms
        == DEFAULT_AUTONOMY_MAX_SIGNAL_AGE_MS
    )
    assert (
        protocol.execution_input_policy_version
        == PAPER_EXECUTION_INPUT_POLICY_VERSION
    )
    assert protocol.execution_reference_mode == WC2_PAPER_EXECUTION_REFERENCE_MODE
    assert (
        protocol.position_sizing_policy_version
        == PAPER_POSITION_SIZING_POLICY_VERSION
    )
    assert (
        protocol.venue_rule_schema_version
        == PAPER_VENUE_RULE_SNAPSHOT_SCHEMA_VERSION
    )
    assert protocol.venue_mode == WC2_PAPER_EXECUTION_VENUE_MODE
    assert (
        protocol.simulated_cost_policy_version
        == PAPER_SIMULATED_COST_POLICY_VERSION
    )
    assert protocol.simulated_fee_rate == DEFAULT_SIMULATED_FEE_RATE
    assert protocol.simulated_spread_rate == DEFAULT_SIMULATED_SPREAD_RATE
    assert protocol.simulated_slippage_rate == DEFAULT_SIMULATED_SLIPPAGE_RATE
    assert protocol.execution_policy_version == PAPER_EXECUTION_POLICY_VERSION
    assert protocol.fill_mode == WC2_PAPER_EXECUTION_FILL_MODE
    assert protocol.economic_claim_rule == WC2_PAPER_EXECUTION_ECONOMIC_CLAIM_RULE

    assert protocol.paper_simulation_authority is True
    assert protocol.historical_backfill_authority is False
    assert protocol.automatic_promotion is False
    assert protocol.real_order_authority is False
    assert protocol.production_authority is False
    assert protocol.real_capital == 0

    field_names = {item.name for item in fields(type(protocol))}
    assert field_names.isdisjoint(
        {
            "minimum_win_rate",
            "minimum_expectancy",
            "minimum_profit_factor",
            "minimum_sharpe",
            "minimum_sortino",
            "observed_trade_count",
            "observed_profitability",
        }
    )


def test_execution_protocol_binds_existing_wc2_lineage_and_future_boundary() -> None:
    policy = _policy()
    activation = _activation()
    collection = _collection()
    protocol = build_wc2_paper_execution_protocol(
        review_policy=policy,
        collection_protocol=collection,
        activation=activation,
        preregistered_at_ms=6_000,
        execution_start_ms=7_000,
    )

    assert protocol.review_policy_identity == policy.policy_identity
    assert protocol.collection_protocol_identity == collection.protocol_identity
    assert protocol.epoch2_activation_identity == activation.activation_identity
    assert protocol.execution_start_ms > protocol.preregistered_at_ms
    assert protocol.execution_start_ms >= collection.collection_start_ms
    assert protocol.execution_start_ms >= activation.activated_at_ms


def test_execution_protocol_rejects_backdating_or_contract_mutation() -> None:
    protocol = _protocol()

    with pytest.raises(ValueError, match="preregistered before activation"):
        build_wc2_paper_execution_protocol(
            review_policy=_policy(),
            collection_protocol=_collection(),
            activation=_activation(),
            preregistered_at_ms=7_000,
            execution_start_ms=7_000,
        )

    with pytest.raises(ValueError, match="risk fraction"):
        replace(
            protocol,
            autonomy_max_position_risk_fraction=(
                DEFAULT_AUTONOMY_MAX_POSITION_RISK_FRACTION * 2
            ),
        )
    with pytest.raises(ValueError, match="fee assumption"):
        replace(
            protocol,
            simulated_fee_rate=DEFAULT_SIMULATED_FEE_RATE * 2,
        )
    with pytest.raises(ValueError, match="real authority"):
        replace(protocol, real_order_authority=True)
    with pytest.raises(ValueError, match="economic claim rule"):
        replace(protocol, economic_claim_rule="zero_trades_are_enough")


def test_execution_protocol_store_is_append_only_and_idempotent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wc2.wc2-paper-execution-protocol.sqlite3"
    store = WC2PaperExecutionProtocolStore(path)
    first = _protocol()

    assert store.append(first) is True
    assert store.append(first) is False
    assert store.latest() == first
    assert store.quick_check() is True

    second = _protocol(preregistered_at_ms=8_000, start=9_000)
    assert store.append(second) is True
    assert store.latest() == second

    backdated = _protocol(preregistered_at_ms=8_500, start=10_000)
    with pytest.raises(ValueError, match="after prior execution boundary"):
        store.append(backdated)

    with sqlite3.connect(path) as db:
        for statement in (
            "UPDATE wc2_paper_execution_protocols SET execution_start_ms=99",
            "DELETE FROM wc2_paper_execution_protocols",
        ):
            with pytest.raises(
                sqlite3.IntegrityError,
                match="append-only WC2 paper execution protocol",
            ):
                db.execute(statement)
            db.rollback()


def test_execution_protocol_refuses_unrelated_database(tmp_path: Path) -> None:
    path = tmp_path / "wc2.wc2-paper-execution-protocol.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE unrelated(value TEXT)")

    store = WC2PaperExecutionProtocolStore(path)
    with pytest.raises(ValueError, match="unrelated tables"):
        store.append(_protocol())
