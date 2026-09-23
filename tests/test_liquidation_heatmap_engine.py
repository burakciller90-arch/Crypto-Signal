from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.data.adapters.bybit_liquidations import (
    BYBIT_ALL_LIQUIDATION_ADAPTER_VERSION,
    parse_bybit_all_liquidation_payload,
)
from crypto_signal.data.derivatives import (
    DerivativesInstrumentType,
    build_derivatives_observation,
)
from crypto_signal.data.liquidations import (
    LiquidatedPositionSide,
    build_liquidation_feed_coverage,
    build_liquidation_observation,
)
from crypto_signal.data.models import DataSource, Exchange
from crypto_signal.intelligence.liquidation_heatmap import (
    LIQUIDATION_HEATMAP_ENGINE_VERSION,
    LIQUIDATION_HEATMAP_FREEZE_SCHEMA_VERSION,
    LiquidationEstimationStatus,
    LiquidationHeatmapConfig,
    LiquidationHeatmapStatus,
    LiquidationSourceQuality,
    ObservedLiquidationState,
    analyze_liquidation_heatmap,
    build_liquidation_heatmap_evidence_freeze,
)

AS_OF = 1_000_000
WINDOW_MS = 60_000


def _coverage(
    *,
    start_ms: int = AS_OF - WINDOW_MS,
    end_ms: int = AS_OF,
    observed_at_ms: int = AS_OF,
    symbol: str = "BTCUSDT",
):
    return build_liquidation_feed_coverage(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol=symbol,
        coverage_start_ms=start_ms,
        coverage_end_ms=end_ms,
        observed_at_ms=observed_at_ms,
        source=DataSource.WEBSOCKET,
        adapter_version=BYBIT_ALL_LIQUIDATION_ADAPTER_VERSION,
    )


def _mark(
    *,
    event_at_ms: int = AS_OF - 1_000,
    mark_price: str = "100",
    symbol: str = "BTCUSDT",
):
    return build_derivatives_observation(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol=symbol,
        event_at_ms=event_at_ms,
        funding_rate=None,
        open_interest=None,
        mark_price=Decimal(mark_price),
        index_price=Decimal(mark_price),
        funding_interval_hours=None,
        source=DataSource.REST,
        source_timestamp_ms=event_at_ms + 10,
        ingested_at_ms=event_at_ms + 20,
        adapter_version="liquidation-heatmap-test-mark/1",
    )


def _event(
    *,
    suffix: int,
    side: LiquidatedPositionSide,
    price: str,
    size: str = "2",
    event_at_ms: int | None = None,
    ingested_at_ms: int | None = None,
    symbol: str = "BTCUSDT",
):
    event_ms = AS_OF - 10_000 + suffix * 100 if event_at_ms is None else event_at_ms
    source_ms = event_ms + 10
    ingest_ms = source_ms + 10 if ingested_at_ms is None else ingested_at_ms
    return build_liquidation_observation(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol=symbol,
        liquidated_position_side=side,
        size=Decimal(size),
        bankruptcy_price=Decimal(price),
        event_at_ms=event_ms,
        source_timestamp_ms=source_ms,
        ingested_at_ms=ingest_ms,
        source_row_index=suffix,
        source=DataSource.WEBSOCKET,
        adapter_version=BYBIT_ALL_LIQUIDATION_ADAPTER_VERSION,
    )


def _config(**overrides) -> LiquidationHeatmapConfig:
    payload = {
        "lookback_ms": WINDOW_MS,
        "max_mark_age_ms": 5_000,
        "bin_width_bps": Decimal(50),
        "minimum_cluster_events": 2,
        "minimum_cluster_notional_share": Decimal("0.20"),
    }
    payload.update(overrides)
    return LiquidationHeatmapConfig(**payload)


def test_bybit_all_liquidation_parser_preserves_provider_side_semantics() -> None:
    payload = {
        "topic": "allLiquidation.BTCUSDT",
        "type": "snapshot",
        "ts": 1_000,
        "data": [
            {"T": 990, "s": "BTCUSDT", "S": "Buy", "v": "2", "p": "100"},
            {"T": 991, "s": "BTCUSDT", "S": "Sell", "v": "3", "p": "101"},
        ],
    }

    observations = parse_bybit_all_liquidation_payload(
        payload,
        expected_symbol="BTCUSDT",
        ingested_at_ms=1_010,
    )

    assert len(observations) == 2
    assert observations[0].liquidated_position_side is LiquidatedPositionSide.LONG
    assert observations[1].liquidated_position_side is LiquidatedPositionSide.SHORT
    assert observations[0].bankruptcy_notional == Decimal(200)
    assert observations[1].bankruptcy_notional == Decimal(303)
    assert observations[0].liquidation_identity != observations[1].liquidation_identity
    assert all(len(item.liquidation_identity) == 64 for item in observations)


def test_bybit_all_liquidation_parser_rejects_wrong_topic_type_side_and_symbol() -> None:
    good = {
        "topic": "allLiquidation.BTCUSDT",
        "type": "snapshot",
        "ts": 1_000,
        "data": [{"T": 990, "s": "BTCUSDT", "S": "Buy", "v": "2", "p": "100"}],
    }

    with pytest.raises(ValueError, match="topic"):
        parse_bybit_all_liquidation_payload(
            {**good, "topic": "allLiquidation.ETHUSDT"},
            expected_symbol="BTCUSDT",
            ingested_at_ms=1_010,
        )
    with pytest.raises(ValueError, match="message type"):
        parse_bybit_all_liquidation_payload(
            {**good, "type": "delta"},
            expected_symbol="BTCUSDT",
            ingested_at_ms=1_010,
        )
    with pytest.raises(ValueError, match="position side"):
        parse_bybit_all_liquidation_payload(
            {**good, "data": [{**good["data"][0], "S": "Unknown"}]},
            expected_symbol="BTCUSDT",
            ingested_at_ms=1_010,
        )
    with pytest.raises(ValueError, match="symbol mismatch"):
        parse_bybit_all_liquidation_payload(
            {**good, "data": [{**good["data"][0], "s": "ETHUSDT"}]},
            expected_symbol="BTCUSDT",
            ingested_at_ms=1_010,
        )


def test_observed_liquidations_are_binned_without_future_risk_estimation() -> None:
    events = (
        _event(suffix=1, side=LiquidatedPositionSide.LONG, price="99.80", size="5"),
        _event(suffix=2, side=LiquidatedPositionSide.LONG, price="99.75", size="4"),
        _event(suffix=3, side=LiquidatedPositionSide.SHORT, price="101.00", size="2"),
    )

    freeze = build_liquidation_heatmap_evidence_freeze(
        events,
        coverage=_coverage(),
        mark_reference=_mark(),
        as_of_ms=AS_OF,
        config=_config(),
    )
    result = freeze.analysis

    assert freeze.schema_version == LIQUIDATION_HEATMAP_FREEZE_SCHEMA_VERSION
    assert result.engine_version == LIQUIDATION_HEATMAP_ENGINE_VERSION
    assert result.status is LiquidationHeatmapStatus.MEASURED
    assert result.source_quality is LiquidationSourceQuality.GOOD
    assert result.observed_state is ObservedLiquidationState.OBSERVED
    assert result.reference_mark_price == Decimal(100)
    assert result.consumed_event_count == 3
    assert len(result.bins) == 2
    assert result.observed_cluster_count == 1

    below = result.bins[0]
    above = result.bins[1]
    assert below.lower_distance_bps == Decimal(-50)
    assert below.upper_distance_bps == Decimal(0)
    assert below.event_count == 2
    assert below.long_liquidation_count == 2
    assert below.short_liquidation_count == 0
    assert below.observed_cluster is True
    assert above.lower_distance_bps == Decimal(100)
    assert above.upper_distance_bps == Decimal(150)
    assert above.event_count == 1
    assert above.short_liquidation_count == 1

    assert (
        result.estimated_leverage_concentration_status
        is LiquidationEstimationStatus.NOT_ESTIMATED
    )
    assert (
        result.liquidation_risk_zone_status
        is LiquidationEstimationStatus.NOT_ESTIMATED
    )
    assert "observed_liquidations_are_not_future_liquidation_risk" in result.uncertainty_flags
    assert len(result.evidence_identity) == 64
    assert len(freeze.freeze_identity) == 64


def test_complete_feed_coverage_can_truthfully_measure_no_liquidations() -> None:
    result = analyze_liquidation_heatmap(
        (),
        coverage=_coverage(),
        mark_reference=_mark(),
        as_of_ms=AS_OF,
        config=_config(),
    )

    assert result.status is LiquidationHeatmapStatus.MEASURED
    assert result.observed_state is ObservedLiquidationState.NONE_OBSERVED
    assert result.consumed_event_count == 0
    assert result.total_bankruptcy_notional == Decimal(0)
    assert result.long_liquidation_notional == Decimal(0)
    assert result.short_liquidation_notional == Decimal(0)
    assert result.bins == ()


@pytest.mark.parametrize(
    ("coverage", "mark", "expected_flag"),
    [
        (
            _coverage(start_ms=AS_OF - WINDOW_MS + 1),
            _mark(),
            "incomplete_feed_coverage_start",
        ),
        (
            _coverage(end_ms=AS_OF - 1, observed_at_ms=AS_OF),
            _mark(),
            "incomplete_feed_coverage_end",
        ),
        (
            _coverage(),
            _mark(event_at_ms=AS_OF - 10_000),
            "stale_mark_reference",
        ),
    ],
)
def test_incomplete_coverage_or_stale_mark_fails_closed(
    coverage,
    mark,
    expected_flag: str,
) -> None:
    result = analyze_liquidation_heatmap(
        (_event(suffix=1, side=LiquidatedPositionSide.LONG, price="99.8"),),
        coverage=coverage,
        mark_reference=mark,
        as_of_ms=AS_OF,
        config=_config(),
    )

    assert result.status is LiquidationHeatmapStatus.UNRESOLVED
    assert result.source_quality is LiquidationSourceQuality.DEGRADED
    assert result.observed_state is ObservedLiquidationState.UNAVAILABLE
    assert result.bins == ()
    assert expected_flag in result.uncertainty_flags
    assert (
        result.liquidation_risk_zone_status
        is LiquidationEstimationStatus.NOT_ESTIMATED
    )


def test_future_or_late_ingested_liquidation_cannot_rewrite_freeze() -> None:
    baseline_events = (
        _event(suffix=1, side=LiquidatedPositionSide.LONG, price="99.8"),
        _event(suffix=2, side=LiquidatedPositionSide.SHORT, price="100.8"),
    )
    baseline = build_liquidation_heatmap_evidence_freeze(
        baseline_events,
        coverage=_coverage(),
        mark_reference=_mark(),
        as_of_ms=AS_OF,
        config=_config(),
    )
    future = _event(
        suffix=9,
        side=LiquidatedPositionSide.LONG,
        price="80",
        event_at_ms=AS_OF + 1,
        ingested_at_ms=AS_OF + 3,
    )
    late = _event(
        suffix=10,
        side=LiquidatedPositionSide.LONG,
        price="80",
        event_at_ms=AS_OF - 5_000,
        ingested_at_ms=AS_OF + 1,
    )

    changed = build_liquidation_heatmap_evidence_freeze(
        (*reversed(baseline_events), future, late),
        coverage=_coverage(),
        mark_reference=_mark(),
        as_of_ms=AS_OF,
        config=_config(),
    )

    assert changed == baseline
    assert future not in changed.events
    assert late not in changed.events


def test_duplicate_mixed_context_and_identity_tampering_fail_closed() -> None:
    event = _event(suffix=1, side=LiquidatedPositionSide.LONG, price="99.8")
    with pytest.raises(ValueError, match="duplicate liquidation event identity"):
        analyze_liquidation_heatmap(
            (event, event),
            coverage=_coverage(),
            mark_reference=_mark(),
            as_of_ms=AS_OF,
            config=_config(),
        )

    eth = _event(
        suffix=2,
        side=LiquidatedPositionSide.SHORT,
        price="101",
        symbol="ETHUSDT",
    )
    with pytest.raises(ValueError, match="event context mismatch"):
        analyze_liquidation_heatmap(
            (event, eth),
            coverage=_coverage(),
            mark_reference=_mark(),
            as_of_ms=AS_OF,
            config=_config(),
        )

    freeze = build_liquidation_heatmap_evidence_freeze(
        (event,),
        coverage=_coverage(),
        mark_reference=_mark(),
        as_of_ms=AS_OF,
        config=_config(),
    )
    with pytest.raises(ValueError, match="freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)
    with pytest.raises(ValueError, match="evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)


def test_slice4_source_does_not_estimate_future_liquidation_risk() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "src/crypto_signal/intelligence/liquidation_heatmap.py"
    ).read_text(encoding="utf-8").lower()

    assert "guaranteed liquidation" not in source
    assert "exact retail stops" not in source
    assert "market maker liquidation target" not in source
    assert "institutional liquidation target" not in source
