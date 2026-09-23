from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.data.large_transfers import (
    TransferClusterRole,
    build_large_transfer_observation,
)
from crypto_signal.data.models import DataSource
from crypto_signal.intelligence.large_transfer_clusters import (
    LargeTransferClusterConfig,
    LargeTransferLabel,
    LargeTransferStatus,
    build_large_transfer_cluster_evidence_freeze,
)

AS_OF = 1_000_000


def _transfer(
    row: int,
    *,
    source_cluster: str,
    destination_cluster: str,
    amount: str,
    source_role: TransferClusterRole = TransferClusterRole.UNKNOWN,
    destination_role: TransferClusterRole = TransferClusterRole.UNKNOWN,
    asset: str = "BTC",
    provider_transfer_id: str | None = None,
    event_at_ms: int | None = None,
    ingested_at_ms: int | None = None,
):
    event_ms = AS_OF - 50_000 + row * 1_000 if event_at_ms is None else event_at_ms
    source_ms = event_ms + 10
    return build_large_transfer_observation(
        asset=asset,
        network="bitcoin_mainnet",
        provider_transfer_id=(
            f"provider-transfer-{row}"
            if provider_transfer_id is None
            else provider_transfer_id
        ),
        source_cluster_id=source_cluster,
        destination_cluster_id=destination_cluster,
        source_role=source_role,
        destination_role=destination_role,
        amount=Decimal(amount),
        event_at_ms=event_ms,
        source_timestamp_ms=source_ms,
        ingested_at_ms=source_ms + 10 if ingested_at_ms is None else ingested_at_ms,
        source_provider="test-transfer-provider",
        attribution_method="provider-cluster-attribution/v1",
        source=DataSource.AGGREGATED,
        adapter_version="large-transfer-test/1",
    )


def test_repeated_relationship_cluster_is_deterministic_and_size_normalized() -> None:
    events = (
        _transfer(
            1,
            source_cluster="cluster-a",
            destination_cluster="exchange-x",
            amount="100",
            destination_role=TransferClusterRole.EXCHANGE,
        ),
        _transfer(
            2,
            source_cluster="cluster-a",
            destination_cluster="exchange-x",
            amount="90",
            destination_role=TransferClusterRole.EXCHANGE,
        ),
        _transfer(
            3,
            source_cluster="cluster-a",
            destination_cluster="exchange-x",
            amount="80",
            destination_role=TransferClusterRole.EXCHANGE,
        ),
        _transfer(
            4,
            source_cluster="cluster-c",
            destination_cluster="cluster-d",
            amount="10",
        ),
        _transfer(
            5,
            source_cluster="cluster-e",
            destination_cluster="cluster-f",
            amount="20",
        ),
    )

    first = build_large_transfer_cluster_evidence_freeze(events, as_of_ms=AS_OF)
    second = build_large_transfer_cluster_evidence_freeze(
        tuple(reversed(events)),
        as_of_ms=AS_OF,
    )

    assert first == second
    analysis = first.analysis
    assert analysis.status is LargeTransferStatus.MEASURED
    assert analysis.label is LargeTransferLabel.REPEATED_RELATIONSHIP_CLUSTER
    assert analysis.metrics is not None
    assert analysis.metrics.event_count == 5
    assert analysis.metrics.exchange_attributed_event_count == 3
    assert analysis.metrics.repeated_relationship_count == 1
    assert len(analysis.relationships) == 1
    relationship = analysis.relationships[0]
    assert relationship.source_cluster_id == "cluster-a"
    assert relationship.destination_cluster_id == "exchange-x"
    assert relationship.event_count == 3
    assert relationship.total_amount == Decimal(270)
    assert relationship.amount_share == Decimal("0.9")
    assert relationship.mean_size_percentile_0_1 > Decimal("0.70")
    assert len(first.freeze_identity) == 64


def test_one_off_large_transfer_remains_isolated_context_not_actor_claim() -> None:
    events = (
        _transfer(1, source_cluster="a", destination_cluster="b", amount="10"),
        _transfer(2, source_cluster="c", destination_cluster="d", amount="20"),
        _transfer(3, source_cluster="e", destination_cluster="f", amount="100"),
        _transfer(4, source_cluster="g", destination_cluster="h", amount="30"),
        _transfer(5, source_cluster="i", destination_cluster="j", amount="40"),
    )
    analysis = build_large_transfer_cluster_evidence_freeze(
        events,
        as_of_ms=AS_OF,
    ).analysis

    assert analysis.label is LargeTransferLabel.ISOLATED_LARGE_TRANSFER
    assert analysis.relationships == ()
    assert analysis.metrics is not None
    assert analysis.metrics.large_event_count >= 1
    assert "provider_cluster_attribution_is_not_actor_identity" in analysis.uncertainty_flags
    assert "large_transfer_context_is_not_price_direction" in analysis.uncertainty_flags


def test_insufficient_history_fails_closed_without_zero_activity_claim() -> None:
    events = (
        _transfer(1, source_cluster="a", destination_cluster="b", amount="10"),
        _transfer(2, source_cluster="c", destination_cluster="d", amount="20"),
    )
    analysis = build_large_transfer_cluster_evidence_freeze(
        events,
        as_of_ms=AS_OF,
    ).analysis

    assert analysis.status is LargeTransferStatus.UNRESOLVED
    assert analysis.label is LargeTransferLabel.UNRESOLVED
    assert analysis.metrics is None
    assert analysis.relationships == ()
    assert analysis.uncertainty_flags == ("insufficient_large_transfer_history",)


def test_future_and_late_ingested_events_cannot_rewrite_historical_freeze() -> None:
    baseline_events = (
        _transfer(1, source_cluster="a", destination_cluster="b", amount="10"),
        _transfer(2, source_cluster="c", destination_cluster="d", amount="20"),
        _transfer(3, source_cluster="e", destination_cluster="f", amount="100"),
    )
    baseline = build_large_transfer_cluster_evidence_freeze(
        baseline_events,
        as_of_ms=AS_OF,
    )
    future = _transfer(
        8,
        source_cluster="future-a",
        destination_cluster="future-b",
        amount="999",
        event_at_ms=AS_OF + 1,
    )
    late = _transfer(
        9,
        source_cluster="late-a",
        destination_cluster="late-b",
        amount="999",
        event_at_ms=AS_OF - 1_000,
        ingested_at_ms=AS_OF + 1,
    )
    changed = build_large_transfer_cluster_evidence_freeze(
        (*baseline_events, future, late),
        as_of_ms=AS_OF,
    )

    assert changed == baseline


def test_context_duplicate_provider_id_and_identity_tampering_fail_closed() -> None:
    baseline = (
        _transfer(1, source_cluster="a", destination_cluster="b", amount="10"),
        _transfer(2, source_cluster="c", destination_cluster="d", amount="20"),
        _transfer(3, source_cluster="e", destination_cluster="f", amount="100"),
    )
    eth = _transfer(
        4,
        source_cluster="g",
        destination_cluster="h",
        amount="10",
        asset="ETH",
    )
    with pytest.raises(ValueError, match="exact source context"):
        build_large_transfer_cluster_evidence_freeze(
            (*baseline, eth),
            as_of_ms=AS_OF,
        )

    duplicate_provider = _transfer(
        4,
        source_cluster="g",
        destination_cluster="h",
        amount="30",
        provider_transfer_id=baseline[0].provider_transfer_id,
    )
    with pytest.raises(ValueError, match="duplicate provider transfer id"):
        build_large_transfer_cluster_evidence_freeze(
            (*baseline, duplicate_provider),
            as_of_ms=AS_OF,
        )

    freeze = build_large_transfer_cluster_evidence_freeze(
        baseline,
        as_of_ms=AS_OF,
    )
    with pytest.raises(ValueError, match="freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)
    with pytest.raises(ValueError, match="evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)


def test_invalid_thresholds_and_self_transfer_fail_closed() -> None:
    with pytest.raises(ValueError, match="configuration invalid"):
        LargeTransferClusterConfig(minimum_events=1)
    with pytest.raises(ValueError, match="inside"):
        LargeTransferClusterConfig(large_amount_percentile=Decimal(0))

    with pytest.raises(ValueError, match="must differ"):
        _transfer(
            1,
            source_cluster="same",
            destination_cluster="same",
            amount="10",
        )
