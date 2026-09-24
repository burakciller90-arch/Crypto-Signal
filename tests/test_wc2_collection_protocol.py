from __future__ import annotations

import sqlite3
from dataclasses import fields, replace
from pathlib import Path

import pytest

from crypto_signal.evaluation.untouched_forward_collection_protocol import (
    WC2_COLLECTION_HORIZON_BARS_BY_TIMEFRAME,
    WC2_COLLECTION_MAXIMUM_ISSUANCE_DELAY_MS,
    WC2_COLLECTION_PAPER_ACTION_MODE,
    WC2_COLLECTION_PROBABILITY_MODE,
    WC2CollectionProtocolStore,
    build_wc2_collection_protocol,
    current_wc2_collection_context_identities,
)
from crypto_signal.evaluation.untouched_forward_policy import (
    build_wc2_untouched_forward_policy,
)
from crypto_signal.ledger.coverage import LiveCoveragePlan
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.epoch2_accounting import (
    build_epoch2_activation_record,
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


def _protocol(*, preregistered_at_ms: int = 4_000, start: int = 5_000):
    return build_wc2_collection_protocol(
        review_policy=_policy(),
        activation=_activation(),
        preregistered_at_ms=preregistered_at_ms,
        collection_start_ms=start,
    )


def test_collection_protocol_freezes_current_pilot_before_results() -> None:
    protocol = _protocol()
    plan = LiveCoveragePlan.current_pilot()

    assert protocol.coverage_plan_version == plan.version
    assert protocol.coverage_context_identities == (
        current_wc2_collection_context_identities()
    )
    assert len(protocol.coverage_context_identities) == 18
    assert protocol.maximum_issuance_delay_ms == 120_000
    assert protocol.maximum_issuance_delay_ms == (
        WC2_COLLECTION_MAXIMUM_ISSUANCE_DELAY_MS
    )
    assert protocol.horizon_bars_by_timeframe == (
        ("15m", 4),
        ("1h", 4),
        ("4h", 4),
    )
    assert protocol.horizon_bars_by_timeframe == (
        WC2_COLLECTION_HORIZON_BARS_BY_TIMEFRAME
    )
    assert protocol.horizon_bars_for("15m") == 4
    assert protocol.horizon_bars_for("1h") == 4
    assert protocol.horizon_bars_for("4h") == 4
    assert protocol.paper_action_mode == WC2_COLLECTION_PAPER_ACTION_MODE
    assert protocol.probability_mode == WC2_COLLECTION_PROBABILITY_MODE
    assert protocol.historical_backfill_authority is False
    assert protocol.automatic_promotion is False
    assert protocol.production_authority is False
    assert protocol.real_capital == 0

    field_names = {item.name for item in fields(type(protocol))}
    assert field_names.isdisjoint(
        {
            "minimum_accuracy",
            "minimum_win_rate",
            "minimum_expectancy",
            "minimum_profit_factor",
            "minimum_sharpe",
            "minimum_sortino",
        }
    )


def test_collection_protocol_binds_review_policy_and_epoch2() -> None:
    policy = _policy()
    activation = _activation()
    protocol = build_wc2_collection_protocol(
        review_policy=policy,
        activation=activation,
        preregistered_at_ms=4_000,
        collection_start_ms=5_000,
    )

    assert protocol.review_policy_identity == policy.policy_identity
    assert protocol.review_policy_collection_start_ms == (
        policy.collection_start_ms
    )
    assert protocol.epoch2_activation_identity == activation.activation_identity
    assert protocol.epoch2_activated_at_ms == activation.activated_at_ms


def test_collection_protocol_cannot_backdate_or_change_locked_parameters() -> None:
    policy = _policy()
    activation = _activation()

    with pytest.raises(ValueError, match="Epoch2 activation"):
        build_wc2_collection_protocol(
            review_policy=policy,
            activation=activation,
            preregistered_at_ms=2_500,
            collection_start_ms=2_900,
        )

    protocol = _protocol()
    with pytest.raises(ValueError, match="issuance-delay"):
        replace(protocol, maximum_issuance_delay_ms=120_001)
    with pytest.raises(ValueError, match="horizon"):
        replace(
            protocol,
            horizon_bars_by_timeframe=(
                ("15m", 5),
                ("1h", 4),
                ("4h", 4),
            ),
        )
    with pytest.raises(ValueError, match="does not authorize"):
        protocol.horizon_bars_for("1D")


def test_collection_protocol_store_is_append_only_and_idempotent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wc2.wc2-collection-protocol.sqlite3"
    store = WC2CollectionProtocolStore(path)
    first = _protocol()

    assert store.append(first) is True
    assert store.append(first) is False
    assert store.latest() == first
    assert store.quick_check() is True

    second = _protocol(preregistered_at_ms=6_000, start=7_000)
    assert store.append(second) is True
    assert store.latest() == second

    backdated = _protocol(preregistered_at_ms=6_500, start=8_000)
    with pytest.raises(ValueError, match="after prior collection boundary"):
        store.append(backdated)

    with sqlite3.connect(path) as db:
        for statement in (
            "UPDATE wc2_collection_protocols SET collection_start_ms=9",
            "DELETE FROM wc2_collection_protocols",
        ):
            with pytest.raises(
                sqlite3.IntegrityError,
                match="append-only WC2 collection protocol",
            ):
                db.execute(statement)
            db.rollback()


def test_collection_protocol_refuses_unrelated_database(tmp_path: Path) -> None:
    path = tmp_path / "wc2.wc2-collection-protocol.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE unrelated(value TEXT)")

    store = WC2CollectionProtocolStore(path)
    with pytest.raises(ValueError, match="other tables"):
        store.append(_protocol())
