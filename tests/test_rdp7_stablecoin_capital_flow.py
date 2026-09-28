from __future__ import annotations

from decimal import Decimal

import pytest

from crypto_signal.data.models import DataSource
from crypto_signal.data.onchain_capital_flow import (
    StablecoinSourceTimestampSemantic,
    build_stablecoin_supply_observation,
)
from crypto_signal.intelligence.stablecoin_capital_flow import (
    StablecoinCapitalFlowConfig,
    StablecoinCapitalFlowStatus,
    build_stablecoin_capital_flow_evidence_freeze,
)
from crypto_signal.ledger.serialization import canonical_sha256


def _raw_identity(label: str) -> str:
    return canonical_sha256({"raw": label})


def _observation(
    *,
    amount: str,
    timestamp_ms: int,
    asset: str = "USDT",
):
    return build_stablecoin_supply_observation(
        asset=asset,
        network_scope="all_chains",
        provider="defillama",
        provider_metric_identity="circulating.peggedUSD",
        circulating_amount=Decimal(amount),
        usd_amount=Decimal(amount),
        source=DataSource.REST,
        source_timestamp_ms=timestamp_ms,
        observed_at_ms=timestamp_ms,
        ingested_at_ms=timestamp_ms,
        adapter_version="defillama-stablecoins-public-rest/1",
        raw_identity=_raw_identity(f"{asset}-{timestamp_ms}-{amount}"),
        source_timestamp_semantic=(
            StablecoinSourceTimestampSemantic.COLLECTOR_RECEIPT
        ),
    )


def test_one_snapshot_is_partial_and_does_not_invent_zero_delta() -> None:
    current = _observation(amount="100", timestamp_ms=10_000)

    freeze = build_stablecoin_capital_flow_evidence_freeze(
        (current,),
        as_of_ms=10_100,
    )

    assert freeze.analysis.status is StablecoinCapitalFlowStatus.PARTIAL
    assert freeze.analysis.metrics is not None
    assert freeze.analysis.metrics.current_circulating_amount == Decimal(100)
    assert freeze.analysis.metrics.previous_circulating_amount is None
    assert freeze.analysis.metrics.supply_delta is None
    assert freeze.analysis.metrics.supply_delta_ratio is None
    assert "stablecoin_supply_history_insufficient_for_delta" in (
        freeze.analysis.uncertainty_flags
    )


def test_two_equal_forward_snapshots_prove_measured_zero_delta() -> None:
    first = _observation(amount="100", timestamp_ms=10_000)
    second = _observation(amount="100", timestamp_ms=20_000)

    freeze = build_stablecoin_capital_flow_evidence_freeze(
        (first, second),
        as_of_ms=20_100,
    )

    assert freeze.analysis.status is StablecoinCapitalFlowStatus.MEASURED
    assert freeze.analysis.metrics is not None
    assert freeze.analysis.metrics.supply_delta == Decimal(0)
    assert freeze.analysis.metrics.supply_delta_ratio == Decimal(0)
    assert "stablecoin_supply_delta_measured_zero" in (
        freeze.analysis.uncertainty_flags
    )


def test_supply_change_is_descriptive_and_never_directional() -> None:
    first = _observation(amount="100", timestamp_ms=10_000)
    second = _observation(amount="125", timestamp_ms=20_000)

    freeze = build_stablecoin_capital_flow_evidence_freeze(
        (first, second),
        as_of_ms=20_100,
    )

    metrics = freeze.analysis.metrics
    assert metrics is not None
    assert metrics.supply_delta == Decimal(25)
    assert metrics.supply_delta_ratio == Decimal("0.25")
    assert "stablecoin_supply_is_descriptive_not_directional" in (
        freeze.analysis.uncertainty_flags
    )
    assert "stablecoin_supply_change_is_not_risk_asset_flow" in (
        freeze.analysis.uncertainty_flags
    )
    assert "stablecoin_supply_does_not_attribute_actor_intent" in (
        freeze.analysis.uncertainty_flags
    )


def test_stale_latest_snapshot_fails_closed_without_metrics() -> None:
    first = _observation(amount="100", timestamp_ms=10_000)
    second = _observation(amount="101", timestamp_ms=20_000)
    config = StablecoinCapitalFlowConfig(
        max_observation_age_ms=1_000,
        minimum_observations=2,
        lookback_observations=8,
    )

    freeze = build_stablecoin_capital_flow_evidence_freeze(
        (first, second),
        as_of_ms=21_001,
        config=config,
    )

    assert freeze.analysis.status is StablecoinCapitalFlowStatus.STALE
    assert freeze.analysis.metrics is None
    assert "stale_stablecoin_supply_observation" in (
        freeze.analysis.uncertainty_flags
    )


def test_future_ingestion_is_excluded_by_pit_boundary() -> None:
    visible = _observation(amount="100", timestamp_ms=10_000)
    future = build_stablecoin_supply_observation(
        asset="USDT",
        network_scope="all_chains",
        provider="defillama",
        provider_metric_identity="circulating.peggedUSD",
        circulating_amount=Decimal(120),
        usd_amount=Decimal(120),
        source=DataSource.REST,
        source_timestamp_ms=11_000,
        observed_at_ms=11_000,
        ingested_at_ms=30_000,
        adapter_version="defillama-stablecoins-public-rest/1",
        raw_identity=_raw_identity("future"),
        source_timestamp_semantic=(
            StablecoinSourceTimestampSemantic.COLLECTOR_RECEIPT
        ),
    )

    freeze = build_stablecoin_capital_flow_evidence_freeze(
        (visible, future),
        as_of_ms=20_000,
    )

    assert freeze.observations == (visible,)
    assert freeze.analysis.status is StablecoinCapitalFlowStatus.PARTIAL
    assert freeze.analysis.metrics is not None
    assert freeze.analysis.metrics.supply_delta is None


def test_mixed_asset_or_timestamp_semantics_fail_closed() -> None:
    usdt = _observation(amount="100", timestamp_ms=10_000)
    usdc = _observation(
        amount="100",
        timestamp_ms=20_000,
        asset="USDC",
    )

    with pytest.raises(ValueError, match="exact source context"):
        build_stablecoin_capital_flow_evidence_freeze(
            (usdt, usdc),
            as_of_ms=20_100,
        )

    provider_timestamp = build_stablecoin_supply_observation(
        asset="USDT",
        network_scope="all_chains",
        provider="defillama",
        provider_metric_identity="circulating.peggedUSD",
        circulating_amount=Decimal(100),
        usd_amount=Decimal(100),
        source=DataSource.REST,
        source_timestamp_ms=20_000,
        observed_at_ms=20_000,
        ingested_at_ms=20_000,
        adapter_version="defillama-stablecoins-public-rest/1",
        raw_identity=_raw_identity("provider-time"),
        source_timestamp_semantic=(
            StablecoinSourceTimestampSemantic.PROVIDER_TIMESTAMP
        ),
    )
    with pytest.raises(ValueError, match="exact source context"):
        build_stablecoin_capital_flow_evidence_freeze(
            (usdt, provider_timestamp),
            as_of_ms=20_100,
        )


def test_freeze_identity_is_deterministic() -> None:
    first = _observation(amount="100", timestamp_ms=10_000)
    second = _observation(amount="110", timestamp_ms=20_000)

    left = build_stablecoin_capital_flow_evidence_freeze(
        (first, second),
        as_of_ms=20_100,
    )
    right = build_stablecoin_capital_flow_evidence_freeze(
        (first, second),
        as_of_ms=20_100,
    )

    assert left == right
    assert len(left.freeze_identity) == 64
    assert left.analysis.evidence_identity == right.analysis.evidence_identity
