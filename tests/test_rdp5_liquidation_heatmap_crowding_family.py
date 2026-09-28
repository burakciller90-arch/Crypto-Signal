from __future__ import annotations

from decimal import Decimal

from crypto_signal.data.derivatives import (
    DerivativesInstrumentType,
    build_derivatives_observation,
)
from crypto_signal.data.liquidations import (
    LiquidatedPositionSide,
    build_liquidation_feed_coverage,
    build_liquidation_observation,
)
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.models import DataSource, Exchange
from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.product.intelligence_stream_family_sources import (
    build_market_tape_family_snapshots,
)

AS_OF_MS = 2_000_000
SYMBOL = "BTCUSDT"
LOOKBACK_MS = 15 * 60_000


def _derivative(
    *,
    event_at_ms: int,
    funding: str,
    oi: str,
    mark: str,
    index: str = "100",
):
    return build_derivatives_observation(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol=SYMBOL,
        event_at_ms=event_at_ms,
        funding_rate=Decimal(funding),
        open_interest=Decimal(oi),
        mark_price=Decimal(mark),
        index_price=Decimal(index),
        funding_interval_hours=8,
        source=DataSource.REST,
        source_timestamp_ms=event_at_ms + 1,
        ingested_at_ms=event_at_ms + 2,
        adapter_version="rdp5-c-family-test/1",
    )


def _seed_derivatives(store: MarketTapeStore) -> None:
    rows = (
        (AS_OF_MS - 180_000, "0.00010", "100", "100.00"),
        (AS_OF_MS - 120_000, "0.00011", "100.2", "100.02"),
        (AS_OF_MS - 60_000, "0.00009", "100.1", "99.99"),
        (AS_OF_MS - 1_000, "0.00010", "100.3", "100.01"),
    )
    for event_at_ms, funding, oi, mark in rows:
        store.append_derivatives(
            _derivative(
                event_at_ms=event_at_ms,
                funding=funding,
                oi=oi,
                mark=mark,
            )
        )


def _coverage(
    *,
    start_ms: int,
    end_ms: int = AS_OF_MS,
):
    return build_liquidation_feed_coverage(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol=SYMBOL,
        coverage_start_ms=start_ms,
        coverage_end_ms=end_ms,
        observed_at_ms=end_ms,
        source=DataSource.WEBSOCKET,
        adapter_version="rdp5-c-family-test/1",
    )


def _liquidation(*, event_at_ms: int = AS_OF_MS - 30_000):
    return build_liquidation_observation(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol=SYMBOL,
        liquidated_position_side=LiquidatedPositionSide.LONG,
        size=Decimal(2),
        bankruptcy_price=Decimal("99.8"),
        event_at_ms=event_at_ms,
        source_timestamp_ms=event_at_ms + 10,
        ingested_at_ms=event_at_ms + 20,
        source_row_index=0,
        source=DataSource.WEBSOCKET,
        adapter_version="rdp5-c-family-test/1",
    )


def _snapshot(path):
    snapshots = build_market_tape_family_snapshots(
        path,
        symbols=(SYMBOL,),
        as_of_ms=AS_OF_MS,
    )
    return next(
        item
        for item in snapshots
        if item.family is ConfluenceFamily.DERIVATIVES
    )


def _components(snapshot) -> dict[str, str]:
    return {
        item.name: item.value
        for item in snapshot.state_components
    }


def test_no_provider_event_coverage_never_claims_zero_liquidations(
    tmp_path,
) -> None:
    path = tmp_path / "market_tape.sqlite3"
    store = MarketTapeStore(path)
    _seed_derivatives(store)

    snapshot = _snapshot(path)
    components = _components(snapshot)

    assert components["dynamics_status"] == "measured"
    assert "liquidation_heatmap_status" not in components
    assert "crowding_status" not in components
    assert "liquidation_zero_event_claim" not in components
    assert "observed_liquidation_events" not in snapshot.evidence_domains
    assert "observed_liquidation_heatmap" not in snapshot.evidence_domains
    assert "derivatives_crowding" not in snapshot.evidence_domains
    assert (
        "liquidation_event_coverage_unavailable_or_stale"
        not in snapshot.uncertainty_flags
    )
    assert snapshot.direction is None


def test_positive_event_without_provider_coverage_is_visible_but_unresolved(
    tmp_path,
) -> None:
    path = tmp_path / "market_tape.sqlite3"
    store = MarketTapeStore(path)
    _seed_derivatives(store)
    event = _liquidation()
    store.append_liquidation(event)

    snapshot = _snapshot(path)
    components = _components(snapshot)

    assert components["observed_liquidation_event_count"] == "1"
    assert components["observed_long_liquidation_count"] == "1"
    assert components["observed_short_liquidation_count"] == "0"
    assert components["liquidation_heatmap_status"] == "unavailable"
    assert components["crowding_status"] == "unavailable"
    assert components["liquidation_zero_event_claim"] == "unavailable"
    assert event.liquidation_identity in snapshot.evidence_identities
    assert "observed_liquidation_events" in snapshot.evidence_domains
    assert "observed_liquidation_heatmap" not in snapshot.evidence_domains
    assert "derivatives_crowding" not in snapshot.evidence_domains
    assert (
        "liquidation_event_coverage_unavailable_or_stale"
        in snapshot.uncertainty_flags
    )
    assert snapshot.direction is None


def test_positive_event_is_visible_but_incomplete_coverage_fails_closed(
    tmp_path,
) -> None:
    path = tmp_path / "market_tape.sqlite3"
    store = MarketTapeStore(path)
    _seed_derivatives(store)
    event = _liquidation()
    store.append_liquidation(event)
    store.append_liquidation_coverage(
        _coverage(start_ms=AS_OF_MS - 60_000)
    )

    snapshot = _snapshot(path)
    components = _components(snapshot)

    assert components["observed_liquidation_event_count"] == "1"
    assert components["observed_long_liquidation_count"] == "1"
    assert components["observed_short_liquidation_count"] == "0"
    assert components["liquidation_heatmap_status"] == "unresolved"
    assert components["liquidation_observed_state"] == "unavailable"
    assert components["crowding_status"] == "unresolved"
    assert components["crowding_label"] == "unresolved"
    assert (
        components["liquidation_zero_event_claim"]
        == "unavailable_incomplete_coverage"
    )
    assert components["estimated_leverage_concentration_status"] == "not_estimated"
    assert components["liquidation_risk_zone_status"] == "not_estimated"
    assert event.liquidation_identity in snapshot.evidence_identities
    assert "observed_liquidation_events" in snapshot.evidence_domains
    assert "observed_liquidation_heatmap" in snapshot.evidence_domains
    assert "derivatives_crowding" in snapshot.evidence_domains
    assert "incomplete_feed_coverage_start" in snapshot.uncertainty_flags
    assert "liquidation_upstream_unresolved" in snapshot.uncertainty_flags
    assert snapshot.direction is None



def test_provider_coverage_observed_after_source_end_is_pit_safe(
    tmp_path,
) -> None:
    path = tmp_path / "market_tape.sqlite3"
    store = MarketTapeStore(path)
    _seed_derivatives(store)
    coverage = build_liquidation_feed_coverage(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol=SYMBOL,
        coverage_start_ms=AS_OF_MS - LOOKBACK_MS,
        coverage_end_ms=AS_OF_MS,
        observed_at_ms=AS_OF_MS + 20,
        source=DataSource.WEBSOCKET,
        adapter_version="rdp5-c-family-test/1",
    )
    store.append_liquidation_coverage(coverage)

    snapshots = build_market_tape_family_snapshots(
        path,
        symbols=(SYMBOL,),
        as_of_ms=AS_OF_MS + 20,
    )
    snapshot = next(
        item
        for item in snapshots
        if item.family is ConfluenceFamily.DERIVATIVES
    )
    components = _components(snapshot)

    assert components["liquidation_analysis_as_of_ms"] == str(
        coverage.observed_at_ms
    )
    assert components["liquidation_heatmap_status"] == "unresolved"
    assert (
        components["liquidation_zero_event_claim"]
        == "unavailable_incomplete_coverage"
    )
    assert "incomplete_feed_coverage_end" in snapshot.uncertainty_flags
    assert coverage.coverage_identity in snapshot.evidence_identities
    assert snapshot.direction is None


def test_complete_zero_event_coverage_can_measure_balanced_context(
    tmp_path,
) -> None:
    path = tmp_path / "market_tape.sqlite3"
    store = MarketTapeStore(path)
    _seed_derivatives(store)
    coverage = _coverage(start_ms=AS_OF_MS - LOOKBACK_MS)
    store.append_liquidation_coverage(coverage)

    snapshot = _snapshot(path)
    components = _components(snapshot)

    assert components["liquidation_heatmap_status"] == "measured"
    assert components["liquidation_observed_state"] == "none_observed"
    assert components["liquidation_cluster_count"] == "0"
    assert components["liquidation_zero_event_claim"] == "verified_complete_coverage"
    assert components["crowding_status"] == "measured"
    assert components["crowding_label"] == "balanced"
    assert "observed_liquidation_events" not in snapshot.evidence_domains
    assert "observed_liquidation_heatmap" in snapshot.evidence_domains
    assert "derivatives_crowding" in snapshot.evidence_domains
    assert coverage.coverage_identity in snapshot.evidence_identities
    assert snapshot.direction is None


def test_complete_coverage_with_observed_event_never_becomes_zero_claim(
    tmp_path,
) -> None:
    path = tmp_path / "market_tape.sqlite3"
    store = MarketTapeStore(path)
    _seed_derivatives(store)
    event = _liquidation()
    coverage = _coverage(start_ms=AS_OF_MS - LOOKBACK_MS)
    store.append_liquidation(event)
    store.append_liquidation_coverage(coverage)

    snapshot = _snapshot(path)
    components = _components(snapshot)

    assert components["liquidation_heatmap_status"] == "measured"
    assert components["liquidation_observed_state"] == "observed"
    assert components["observed_liquidation_event_count"] == "1"
    assert (
        components["liquidation_zero_event_claim"]
        == "not_applicable_observed_events"
    )
    assert components["crowding_status"] == "measured"
    assert components["crowding_label"] == "mixed"
    assert event.liquidation_identity in snapshot.evidence_identities
    assert snapshot.direction is None


def test_future_or_late_liquidation_event_is_not_presented_as_observed(
    tmp_path,
) -> None:
    path = tmp_path / "market_tape.sqlite3"
    store = MarketTapeStore(path)
    _seed_derivatives(store)

    future = _liquidation(event_at_ms=AS_OF_MS + 1)
    late = build_liquidation_observation(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol=SYMBOL,
        liquidated_position_side=LiquidatedPositionSide.SHORT,
        size=Decimal(2),
        bankruptcy_price=Decimal("100.2"),
        event_at_ms=AS_OF_MS - 30_000,
        source_timestamp_ms=AS_OF_MS - 29_990,
        ingested_at_ms=AS_OF_MS + 1,
        source_row_index=1,
        source=DataSource.WEBSOCKET,
        adapter_version="rdp5-c-family-test/1",
    )
    store.append_liquidation(future)
    store.append_liquidation(late)

    snapshot = _snapshot(path)
    components = _components(snapshot)

    assert "observed_liquidation_event_count" not in components
    assert future.liquidation_identity not in snapshot.evidence_identities
    assert late.liquidation_identity not in snapshot.evidence_identities
    assert snapshot.direction is None
