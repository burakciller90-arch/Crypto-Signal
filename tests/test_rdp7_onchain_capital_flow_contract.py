from __future__ import annotations

from decimal import Decimal

import pytest

from crypto_signal.data.models import DataSource
from crypto_signal.data.onchain_capital_flow import (
    OnchainEventCoverageState,
    build_onchain_event_coverage,
    build_stablecoin_supply_observation,
)


def _sha(character: str) -> str:
    return character * 64


def test_complete_event_coverage_requires_exact_lineage_and_allows_zero_claim() -> None:
    coverage = build_onchain_event_coverage(
        provider="provider-x",
        source="public_rest",
        channel="large_transfer_window",
        asset="BTC",
        network="bitcoin",
        event_kind="large_transfer",
        coverage_start_ms=1_000,
        coverage_end_ms=2_000,
        observed_at_ms=2_100,
        ingested_at_ms=2_200,
        state=OnchainEventCoverageState.COMPLETE,
        source_envelope_identity=_sha("a"),
        raw_identity=_sha("b"),
        reason_codes=("provider_window_complete",),
    )

    replay = build_onchain_event_coverage(
        provider="provider-x",
        source="public_rest",
        channel="large_transfer_window",
        asset="BTC",
        network="bitcoin",
        event_kind="large_transfer",
        coverage_start_ms=1_000,
        coverage_end_ms=2_000,
        observed_at_ms=2_100,
        ingested_at_ms=2_200,
        state=OnchainEventCoverageState.COMPLETE,
        source_envelope_identity=_sha("a"),
        raw_identity=_sha("b"),
        reason_codes=("provider_window_complete",),
    )

    assert replay == coverage
    assert coverage.can_assert_zero_events is True
    assert coverage.production_authority is False
    assert coverage.real_capital == 0


def test_partial_gap_and_unavailable_coverage_never_claim_zero_events() -> None:
    partial = build_onchain_event_coverage(
        provider="provider-x",
        source="public_rest",
        channel="transfer_window",
        asset="ETH",
        network="ethereum",
        event_kind="stablecoin_transfer",
        coverage_start_ms=1_000,
        coverage_end_ms=2_000,
        observed_at_ms=2_100,
        ingested_at_ms=2_200,
        state=OnchainEventCoverageState.PARTIAL,
        source_envelope_identity=_sha("c"),
        raw_identity=_sha("d"),
        reason_codes=("provider_window_partial",),
    )
    gap = build_onchain_event_coverage(
        provider="provider-x",
        source="public_rest",
        channel="transfer_window",
        asset="ETH",
        network="ethereum",
        event_kind="stablecoin_transfer",
        coverage_start_ms=2_000,
        coverage_end_ms=3_000,
        observed_at_ms=3_100,
        ingested_at_ms=3_200,
        state=OnchainEventCoverageState.GAP,
        source_envelope_identity=None,
        raw_identity=None,
        reason_codes=("provider_request_failed",),
    )
    unavailable = build_onchain_event_coverage(
        provider="provider-x",
        source="public_rest",
        channel="transfer_window",
        asset="ETH",
        network="ethereum",
        event_kind="stablecoin_transfer",
        coverage_start_ms=3_000,
        coverage_end_ms=4_000,
        observed_at_ms=4_100,
        ingested_at_ms=4_200,
        state=OnchainEventCoverageState.UNAVAILABLE,
        source_envelope_identity=None,
        raw_identity=None,
        reason_codes=("provider_entitlement_missing",),
    )

    assert partial.can_assert_zero_events is False
    assert gap.can_assert_zero_events is False
    assert unavailable.can_assert_zero_events is False


def test_observed_event_coverage_rejects_missing_lineage() -> None:
    with pytest.raises(ValueError, match="requires exact source lineage"):
        build_onchain_event_coverage(
            provider="provider-x",
            source="public_rest",
            channel="large_transfer_window",
            asset="BTC",
            network="bitcoin",
            event_kind="large_transfer",
            coverage_start_ms=1_000,
            coverage_end_ms=2_000,
            observed_at_ms=2_100,
            ingested_at_ms=2_200,
            state=OnchainEventCoverageState.COMPLETE,
            source_envelope_identity=None,
            raw_identity=None,
            reason_codes=("provider_window_complete",),
        )


def test_gap_coverage_rejects_source_data_substitution() -> None:
    with pytest.raises(ValueError, match="cannot substitute source data"):
        build_onchain_event_coverage(
            provider="provider-x",
            source="public_rest",
            channel="large_transfer_window",
            asset="BTC",
            network="bitcoin",
            event_kind="large_transfer",
            coverage_start_ms=1_000,
            coverage_end_ms=2_000,
            observed_at_ms=2_100,
            ingested_at_ms=2_200,
            state=OnchainEventCoverageState.GAP,
            source_envelope_identity=_sha("e"),
            raw_identity=_sha("f"),
            reason_codes=("provider_request_failed",),
        )


def test_event_coverage_cannot_be_observed_before_window_end() -> None:
    with pytest.raises(ValueError, match="before interval end"):
        build_onchain_event_coverage(
            provider="provider-x",
            source="public_rest",
            channel="large_transfer_window",
            asset="BTC",
            network="bitcoin",
            event_kind="large_transfer",
            coverage_start_ms=1_000,
            coverage_end_ms=2_000,
            observed_at_ms=1_999,
            ingested_at_ms=2_100,
            state=OnchainEventCoverageState.GAP,
            source_envelope_identity=None,
            raw_identity=None,
            reason_codes=("provider_request_failed",),
        )


def test_stablecoin_supply_is_deterministic_descriptive_source_truth() -> None:
    observation = build_stablecoin_supply_observation(
        asset="USDT",
        network_scope="all_chains",
        provider="defillama",
        provider_metric_identity="stablecoins/circulating",
        circulating_amount=Decimal("1000000.25"),
        usd_amount=Decimal("1000000.25"),
        source=DataSource.REST,
        source_timestamp_ms=10_000,
        observed_at_ms=10_100,
        ingested_at_ms=10_200,
        adapter_version="rdp7-test/1",
        raw_identity=_sha("1"),
        source_envelope_identity=_sha("2"),
    )
    replay = build_stablecoin_supply_observation(
        asset="USDT",
        network_scope="all_chains",
        provider="defillama",
        provider_metric_identity="stablecoins/circulating",
        circulating_amount=Decimal("1000000.25"),
        usd_amount=Decimal("1000000.25"),
        source=DataSource.REST,
        source_timestamp_ms=10_000,
        observed_at_ms=10_100,
        ingested_at_ms=10_200,
        adapter_version="rdp7-test/1",
        raw_identity=_sha("1"),
        source_envelope_identity=_sha("2"),
    )

    assert replay == observation
    assert observation.production_authority is False
    assert observation.real_capital == 0


def test_stablecoin_supply_accepts_measured_zero_but_not_missing_or_negative() -> None:
    zero = build_stablecoin_supply_observation(
        asset="USDC",
        network_scope="ethereum",
        provider="provider-y",
        provider_metric_identity="circulating_supply",
        circulating_amount=Decimal(0),
        usd_amount=None,
        source=DataSource.REST,
        source_timestamp_ms=20_000,
        observed_at_ms=20_100,
        ingested_at_ms=20_200,
        adapter_version="rdp7-test/1",
        raw_identity=_sha("3"),
        source_envelope_identity=_sha("4"),
    )
    assert zero.circulating_amount == Decimal(0)

    with pytest.raises(ValueError, match="finite and non-negative"):
        build_stablecoin_supply_observation(
            asset="USDC",
            network_scope="ethereum",
            provider="provider-y",
            provider_metric_identity="circulating_supply",
            circulating_amount=Decimal(-1),
            usd_amount=None,
            source=DataSource.REST,
            source_timestamp_ms=20_000,
            observed_at_ms=20_100,
            ingested_at_ms=20_200,
            adapter_version="rdp7-test/1",
            raw_identity=_sha("3"),
            source_envelope_identity=_sha("4"),
        )


def test_stablecoin_supply_requires_pit_timestamp_order() -> None:
    with pytest.raises(ValueError, match="cannot predate source timestamp"):
        build_stablecoin_supply_observation(
            asset="USDT",
            network_scope="all_chains",
            provider="defillama",
            provider_metric_identity="stablecoins/circulating",
            circulating_amount=Decimal(100),
            usd_amount=Decimal(100),
            source=DataSource.REST,
            source_timestamp_ms=10_000,
            observed_at_ms=9_999,
            ingested_at_ms=10_100,
            adapter_version="rdp7-test/1",
            raw_identity=_sha("5"),
            source_envelope_identity=_sha("6"),
        )
