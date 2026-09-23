from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

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
from crypto_signal.intelligence.derivatives_crowding import (
    CrowdedSide,
    DerivativesCrowdingConfig,
    DerivativesCrowdingLabel,
    DerivativesCrowdingStatus,
    build_derivatives_crowding_evidence_freeze,
)
from crypto_signal.intelligence.derivatives_dynamics import (
    build_derivatives_dynamics_evidence_freeze,
)
from crypto_signal.intelligence.liquidation_heatmap import (
    LiquidationHeatmapStatus,
    build_liquidation_heatmap_evidence_freeze,
)

AS_OF = 1_000_000
TIMES = (
    AS_OF - 50_000,
    AS_OF - 40_000,
    AS_OF - 30_000,
    AS_OF - 20_000,
    AS_OF - 1_000,
)


def _observation(
    at_ms: int,
    *,
    funding: Decimal | None,
    oi: Decimal | None,
    mark: Decimal | None,
    index: Decimal | None,
    ingested_at_ms: int | None = None,
    symbol: str = "BTCUSDT",
):
    return build_derivatives_observation(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol=symbol,
        event_at_ms=at_ms,
        funding_rate=funding,
        open_interest=oi,
        mark_price=mark,
        index_price=index,
        funding_interval_hours=8 if funding is not None else None,
        source=DataSource.REST,
        source_timestamp_ms=at_ms,
        ingested_at_ms=at_ms if ingested_at_ms is None else ingested_at_ms,
        adapter_version="m4-crowding-tests/1",
    )


def _series(mode: str = "long", *, symbol: str = "BTCUSDT"):
    if mode == "long":
        funding = ("0.0001", "0.0002", "0.0003", "0.0004", "0.0012")
        marks = ("100", "101", "102", "103", "110")
        indices = ("100", "101", "102", "103", "109.4")
        interests = ("100", "105", "110", "115", "130")
    elif mode == "short":
        funding = ("-0.0001", "-0.0002", "-0.0003", "-0.0004", "-0.0012")
        marks = ("110", "109", "108", "107", "100")
        indices = ("110", "109", "108", "107", "100.6")
        interests = ("100", "105", "110", "115", "130")
    elif mode == "deleveraging":
        funding = ("0", "0", "0", "0", "0")
        marks = ("100", "100", "100", "100", "100")
        indices = marks
        interests = ("130", "125", "120", "110", "100")
    elif mode == "balanced":
        funding = ("0.00001",) * 5
        marks = ("100",) * 5
        indices = marks
        interests = ("100", "100.2", "100.4", "100.6", "101")
    else:
        raise ValueError("unsupported fixture")
    return tuple(
        _observation(
            at_ms,
            funding=Decimal(funding[i]),
            oi=Decimal(interests[i]),
            mark=Decimal(marks[i]),
            index=Decimal(indices[i]),
            symbol=symbol,
        )
        for i, at_ms in enumerate(TIMES)
    )


def _event(
    row: int,
    *,
    side: LiquidatedPositionSide,
    bankruptcy_price: Decimal,
    size: Decimal = Decimal(2),
    ingested_at_ms: int | None = None,
    symbol: str = "BTCUSDT",
):
    at_ms = AS_OF - 10_000 + row * 100
    return build_liquidation_observation(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol=symbol,
        liquidated_position_side=side,
        size=size,
        bankruptcy_price=bankruptcy_price,
        event_at_ms=at_ms,
        source_timestamp_ms=at_ms + 10,
        ingested_at_ms=at_ms + 20 if ingested_at_ms is None else ingested_at_ms,
        source_row_index=row,
        source=DataSource.WEBSOCKET,
        adapter_version="m4-crowding-test-liquidation/1",
    )


def _liquidations(
    mark_reference,
    events=(),
    *,
    as_of_ms: int = AS_OF,
    coverage_start_ms: int | None = None,
):
    coverage = build_liquidation_feed_coverage(
        exchange=mark_reference.exchange,
        instrument_type=mark_reference.instrument_type,
        symbol=mark_reference.symbol,
        coverage_start_ms=(
            as_of_ms - 15 * 60_000
            if coverage_start_ms is None
            else coverage_start_ms
        ),
        coverage_end_ms=as_of_ms,
        observed_at_ms=as_of_ms,
        source=DataSource.WEBSOCKET,
        adapter_version="m4-crowding-test-coverage/1",
    )
    return build_liquidation_heatmap_evidence_freeze(
        events,
        coverage=coverage,
        mark_reference=mark_reference,
        as_of_ms=as_of_ms,
    )


def _combined(
    mode: str,
    events=(),
    *,
    history=None,
    as_of_ms: int = AS_OF,
    coverage_start_ms: int | None = None,
):
    samples = _series(mode) if history is None else history
    derivatives = build_derivatives_dynamics_evidence_freeze(
        samples,
        as_of_ms=as_of_ms,
    )
    mark_reference = max(
        (
            item
            for item in samples
            if item.mark_price is not None
            and max(item.event_at_ms, item.source_timestamp_ms, item.ingested_at_ms)
            <= as_of_ms
        ),
        key=lambda item: (item.event_at_ms, item.observation_identity),
    )
    liquidation = _liquidations(
        mark_reference,
        events,
        as_of_ms=as_of_ms,
        coverage_start_ms=coverage_start_ms,
    )
    return build_derivatives_crowding_evidence_freeze(derivatives, liquidation)


def test_observed_long_crowding_and_squeeze_risk_are_bounded_and_replay_stable() -> None:
    events = (
        _event(1, side=LiquidatedPositionSide.LONG, bankruptcy_price=Decimal("109.8"), size=Decimal(5)),
        _event(2, side=LiquidatedPositionSide.LONG, bankruptcy_price=Decimal("109.7"), size=Decimal(4)),
        _event(3, side=LiquidatedPositionSide.SHORT, bankruptcy_price=Decimal("110.2")),
    )
    first = _combined("long", events)
    second = _combined("long", tuple(reversed(events)), history=tuple(reversed(_series("long"))))
    assert first == second
    assert first.analysis.status is DerivativesCrowdingStatus.MEASURED
    assert first.analysis.label is DerivativesCrowdingLabel.SQUEEZE_RISK
    assert first.analysis.crowded_side is CrowdedSide.LONG
    assert first.analysis.squeeze_risk_side is CrowdedSide.LONG
    metrics = first.analysis.metrics
    assert metrics is not None
    assert metrics.mark_return_count == 4
    assert metrics.mean_abs_mark_return_bps is not None
    assert metrics.mean_abs_mark_return_bps >= Decimal(100)
    assert metrics.long_liquidation_share is not None
    assert metrics.long_liquidation_share > Decimal("0.60")
    assert "squeeze_risk_is_context_not_forecast" in first.analysis.uncertainty_flags
    assert len(first.analysis.evidence_identity) == 64
    assert len(first.freeze_identity) == 64


def test_complete_feed_with_zero_events_does_not_invent_liquidations() -> None:
    result = _combined("long")
    assert result.liquidation_freeze.analysis.status is LiquidationHeatmapStatus.MEASURED
    assert result.analysis.label is DerivativesCrowdingLabel.LONG_CROWDING
    assert result.analysis.crowded_side is CrowdedSide.LONG
    assert result.analysis.squeeze_risk_side is CrowdedSide.NONE
    assert result.analysis.metrics is not None
    assert result.analysis.metrics.total_liquidation_notional == Decimal(0)
    assert result.analysis.metrics.long_liquidation_share is None


def test_observed_short_side_context_is_not_a_short_order() -> None:
    events = (
        _event(1, side=LiquidatedPositionSide.SHORT, bankruptcy_price=Decimal("100.2"), size=Decimal(6)),
        _event(2, side=LiquidatedPositionSide.SHORT, bankruptcy_price=Decimal("100.3"), size=Decimal(4)),
        _event(3, side=LiquidatedPositionSide.LONG, bankruptcy_price=Decimal("99.8")),
    )
    analysis = _combined("short", events).analysis
    assert analysis.label is DerivativesCrowdingLabel.SQUEEZE_RISK
    assert analysis.crowded_side is CrowdedSide.SHORT
    assert analysis.squeeze_risk_side is CrowdedSide.SHORT
    assert analysis.metrics is not None
    assert analysis.metrics.funding_percentile_0_1 == Decimal(1) / Decimal(5)
    assert analysis.metrics.basis_bps is not None
    assert analysis.metrics.basis_bps < Decimal(-25)


def test_oi_contraction_with_observed_liquidations_is_deleveraging_context() -> None:
    event = _event(
        1,
        side=LiquidatedPositionSide.LONG,
        bankruptcy_price=Decimal("99.8"),
    )
    analysis = _combined("deleveraging", (event,)).analysis
    assert analysis.label is DerivativesCrowdingLabel.DELEVERAGING
    assert analysis.crowded_side is CrowdedSide.NONE
    assert analysis.squeeze_risk_side is CrowdedSide.NONE
    assert analysis.metrics is not None
    assert analysis.metrics.open_interest_change_fraction is not None
    assert analysis.metrics.open_interest_change_fraction < Decimal("-0.05")


def test_low_pressure_complete_zero_event_window_is_balanced() -> None:
    analysis = _combined("balanced").analysis
    assert analysis.status is DerivativesCrowdingStatus.MEASURED
    assert analysis.label is DerivativesCrowdingLabel.BALANCED
    assert analysis.uncertainty_flags == ()


def test_missing_coverage_and_unmeasured_derivatives_fail_closed() -> None:
    coverage_start = AS_OF - 15 * 60_000 + 1
    incomplete = _combined("long", coverage_start_ms=coverage_start)
    assert incomplete.analysis.status is DerivativesCrowdingStatus.UNRESOLVED
    assert incomplete.analysis.label is DerivativesCrowdingLabel.UNRESOLVED
    assert incomplete.analysis.metrics is None
    assert incomplete.analysis.crowded_side is CrowdedSide.UNAVAILABLE
    assert "liquidation_upstream_unresolved" in incomplete.analysis.uncertainty_flags

    partial = (
        _observation(AS_OF - 2_000, funding=None, oi=Decimal(100), mark=None, index=None),
        _observation(AS_OF - 1_000, funding=None, oi=Decimal(110), mark=None, index=None),
    )
    derivatives = build_derivatives_dynamics_evidence_freeze(partial, as_of_ms=AS_OF)
    liquidation = _liquidations(_series("long")[-1])
    result = build_derivatives_crowding_evidence_freeze(derivatives, liquidation)
    assert result.analysis.status is DerivativesCrowdingStatus.UNRESOLVED
    assert "derivatives_upstream_unresolved" in result.analysis.uncertainty_flags


def test_future_and_late_evidence_cannot_rewrite_combined_freeze() -> None:
    baseline_events = (
        _event(1, side=LiquidatedPositionSide.LONG, bankruptcy_price=Decimal("109.8")),
    )
    baseline = _combined("long", baseline_events)
    future = _observation(
        AS_OF + 1, funding=Decimal("0.1"), oi=Decimal(500),
        mark=Decimal(500), index=Decimal(100),
    )
    late = _observation(
        AS_OF - 5_000, funding=Decimal("-0.1"), oi=Decimal(1),
        mark=Decimal(50), index=Decimal(100), ingested_at_ms=AS_OF + 1,
    )
    late_event = _event(
        2, side=LiquidatedPositionSide.SHORT,
        bankruptcy_price=Decimal(111), ingested_at_ms=AS_OF + 1,
    )
    changed = _combined(
        "long", (*baseline_events, late_event),
        history=(*_series("long"), future, late),
    )
    assert changed == baseline


def test_upstream_market_and_as_of_must_match_exactly() -> None:
    derivatives = build_derivatives_dynamics_evidence_freeze(_series("long"), as_of_ms=AS_OF)
    eth_mark = _series("long", symbol="ETHUSDT")[-1]
    eth_liquidations = _liquidations(eth_mark)
    with pytest.raises(ValueError, match="market context mismatch"):
        build_derivatives_crowding_evidence_freeze(derivatives, eth_liquidations)

    early = build_derivatives_dynamics_evidence_freeze(
        _series("long"), as_of_ms=AS_OF - 1,
    )
    with pytest.raises(ValueError, match="as-of mismatch"):
        build_derivatives_crowding_evidence_freeze(
            early, _liquidations(_series("long")[-1]),
        )


def test_tampering_and_invalid_research_thresholds_fail_closed() -> None:
    freeze = _combined("long")
    with pytest.raises(ValueError, match="freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)
    with pytest.raises(ValueError, match="evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)
    assert freeze.analysis.metrics is not None
    with pytest.raises(ValueError, match="negative"):
        replace(freeze.analysis.metrics, total_liquidation_notional=Decimal(-1))
    with pytest.raises(ValueError, match="below high"):
        DerivativesCrowdingConfig(funding_percentile_low=Decimal("0.95"))
    with pytest.raises(ValueError, match="inside"):
        DerivativesCrowdingConfig(liquidation_dominance_share=Decimal("1.1"))


def test_measured_but_nonaligned_components_remain_mixed_context() -> None:
    result = build_derivatives_crowding_evidence_freeze(
        build_derivatives_dynamics_evidence_freeze(_series("long"), as_of_ms=AS_OF),
        _liquidations(_series("long")[-1]),
        config=DerivativesCrowdingConfig(funding_extreme_bps=Decimal(20)),
    )
    assert result.analysis.status is DerivativesCrowdingStatus.MEASURED
    assert result.analysis.label is DerivativesCrowdingLabel.MIXED
    assert result.analysis.crowded_side is CrowdedSide.NONE
    assert result.analysis.squeeze_risk_side is CrowdedSide.NONE
    assert (
        "derivatives_components_not_aligned_for_strong_label"
        in result.analysis.uncertainty_flags
    )
