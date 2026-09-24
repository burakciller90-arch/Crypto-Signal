from __future__ import annotations

from pathlib import Path

import pytest

from crypto_signal.evaluation.untouched_forward_collection_protocol import (
    build_wc2_collection_protocol,
)
from crypto_signal.evaluation.untouched_forward_policy import (
    build_wc2_untouched_forward_policy,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.epoch2_accounting import build_epoch2_activation_record
from ops.register_wc2_paper_execution_protocol import (
    FIFTEEN_MINUTES_MS,
    register_or_reuse_execution_protocol,
)


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _policy(*, start: int = 2_000):
    return build_wc2_untouched_forward_policy(
        preregistered_at_ms=1_000,
        collection_start_ms=start,
    )


def _activation(*, activated_at_ms: int = 3_000):
    return build_epoch2_activation_record(
        activated_at_ms=activated_at_ms,
        epoch1_ledger_sha256=_sha("epoch1"),
    )


def _collection():
    return build_wc2_collection_protocol(
        review_policy=_policy(),
        activation=_activation(),
        preregistered_at_ms=4_000,
        collection_start_ms=5_000,
    )


def test_execution_registration_is_future_bounded_and_exactly_bound(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wc2.wc2-paper-execution-protocol.sqlite3"
    policy = _policy()
    activation = _activation()
    collection = _collection()
    now_ms = 6_000

    result = register_or_reuse_execution_protocol(
        protocol_path=path,
        review_policy=policy,
        collection_protocol=collection,
        activation=activation,
        now_ms=now_ms,
    )

    expected_start = (
        (
            max(
                now_ms,
                policy.collection_start_ms,
                collection.collection_start_ms,
                activation.activated_at_ms,
            )
            // FIFTEEN_MINUTES_MS
        )
        + 2
    ) * FIFTEEN_MINUTES_MS
    assert result.inserted is True
    assert result.protocol.preregistered_at_ms == now_ms
    assert result.protocol.execution_start_ms == expected_start
    assert result.protocol.execution_start_ms > now_ms
    assert result.protocol.review_policy_identity == policy.policy_identity
    assert (
        result.protocol.collection_protocol_identity
        == collection.protocol_identity
    )
    assert (
        result.protocol.epoch2_activation_identity
        == activation.activation_identity
    )
    assert result.protocol.paper_simulation_authority is True
    assert result.protocol.historical_backfill_authority is False
    assert result.protocol.real_order_authority is False
    assert result.protocol.production_authority is False
    assert result.protocol.real_capital == 0


def test_execution_registration_replay_is_byte_stable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wc2.wc2-paper-execution-protocol.sqlite3"
    policy = _policy()
    activation = _activation()
    collection = _collection()

    first = register_or_reuse_execution_protocol(
        protocol_path=path,
        review_policy=policy,
        collection_protocol=collection,
        activation=activation,
        now_ms=6_000,
    )
    before = path.read_bytes()
    replay = register_or_reuse_execution_protocol(
        protocol_path=path,
        review_policy=policy,
        collection_protocol=collection,
        activation=activation,
        now_ms=99_999_999,
    )

    assert first.inserted is True
    assert replay.inserted is False
    assert replay.protocol == first.protocol
    assert path.read_bytes() == before


def test_execution_registration_fails_closed_on_lineage_mismatch(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wc2.wc2-paper-execution-protocol.sqlite3"
    policy = _policy()
    activation = _activation()
    collection = _collection()
    register_or_reuse_execution_protocol(
        protocol_path=path,
        review_policy=policy,
        collection_protocol=collection,
        activation=activation,
        now_ms=6_000,
    )

    different_policy = build_wc2_untouched_forward_policy(
        preregistered_at_ms=7_000,
        collection_start_ms=8_000,
    )
    with pytest.raises(ValueError, match="review policy mismatch"):
        register_or_reuse_execution_protocol(
            protocol_path=path,
            review_policy=different_policy,
            collection_protocol=collection,
            activation=activation,
            now_ms=9_000,
        )

    different_collection = build_wc2_collection_protocol(
        review_policy=policy,
        activation=activation,
        preregistered_at_ms=8_000,
        collection_start_ms=9_000,
    )
    with pytest.raises(ValueError, match="collection mismatch"):
        register_or_reuse_execution_protocol(
            protocol_path=path,
            review_policy=policy,
            collection_protocol=different_collection,
            activation=activation,
            now_ms=10_000,
        )

    different_activation = _activation(activated_at_ms=11_000)
    with pytest.raises(ValueError, match="Epoch2 mismatch"):
        register_or_reuse_execution_protocol(
            protocol_path=path,
            review_policy=policy,
            collection_protocol=collection,
            activation=different_activation,
            now_ms=12_000,
        )
