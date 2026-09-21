from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.data.cross_market import (
    CrossMarketSeries,
    CrossMarketUnit,
    build_cross_market_daily_record,
    build_cross_market_window_observation,
)
from crypto_signal.data.models import DataSource

_DAY_MS = 24 * 60 * 60 * 1000


def _record(
    day: int,
    *,
    series: CrossMarketSeries = CrossMarketSeries.CBOE_VIX_CLOSE,
    unit: CrossMarketUnit = CrossMarketUnit.INDEX_POINTS,
    value: Decimal = Decimal("18.5"),
):
    return build_cross_market_daily_record(
        series=series,
        unit=unit,
        day_start_ms=day * _DAY_MS,
        value=value,
    )


def test_cross_market_record_identity_is_deterministic() -> None:
    first = _record(10)
    second = _record(10)

    assert first == second
    assert len(first.record_identity) == 64


def test_cross_market_record_bounds_and_units_fail_closed() -> None:
    with pytest.raises(ValueError, match="index-point"):
        _record(
            10,
            unit=CrossMarketUnit.PERCENT,
        )

    with pytest.raises(ValueError, match="positive"):
        _record(
            10,
            value=Decimal(0),
        )

    with pytest.raises(ValueError, match="percent"):
        _record(
            10,
            series=CrossMarketSeries.US_TREASURY_10Y_YIELD,
            unit=CrossMarketUnit.INDEX_POINTS,
            value=Decimal(5),
        )

    with pytest.raises(ValueError, match="bounded"):
        _record(
            10,
            series=CrossMarketSeries.US_TREASURY_10Y_YIELD,
            unit=CrossMarketUnit.PERCENT,
            value=Decimal(100),
        )


def test_cross_market_window_identity_and_ingestion_semantic_are_deterministic() -> None:
    records = tuple(_record(day) for day in range(10, 15))

    first = build_cross_market_window_observation(
        series=CrossMarketSeries.CBOE_VIX_CLOSE,
        unit=CrossMarketUnit.INDEX_POINTS,
        observed_at_ms=16 * _DAY_MS,
        records=records,
        source=DataSource.REST,
        adapter_version="cross-market-test/1",
    )
    second = build_cross_market_window_observation(
        series=CrossMarketSeries.CBOE_VIX_CLOSE,
        unit=CrossMarketUnit.INDEX_POINTS,
        observed_at_ms=16 * _DAY_MS,
        records=records,
        source=DataSource.REST,
        adapter_version="cross-market-test/1",
    )

    assert first == second
    assert first.temporal_semantic == "ingestion_time_snapshot"
    assert len(first.observation_identity) == 64


def test_cross_market_window_requires_ascending_unique_matching_records() -> None:
    first = _record(10)
    second = _record(11)

    with pytest.raises(ValueError, match="strictly ascending"):
        build_cross_market_window_observation(
            series=CrossMarketSeries.CBOE_VIX_CLOSE,
            unit=CrossMarketUnit.INDEX_POINTS,
            observed_at_ms=13 * _DAY_MS,
            records=(second, first),
            source=DataSource.REST,
            adapter_version="cross-market-test/1",
        )

    treasury = _record(
        11,
        series=CrossMarketSeries.US_TREASURY_10Y_YIELD,
        unit=CrossMarketUnit.PERCENT,
        value=Decimal("5.0"),
    )
    with pytest.raises(ValueError, match="context mismatch"):
        build_cross_market_window_observation(
            series=CrossMarketSeries.CBOE_VIX_CLOSE,
            unit=CrossMarketUnit.INDEX_POINTS,
            observed_at_ms=13 * _DAY_MS,
            records=(first, treasury),
            source=DataSource.REST,
            adapter_version="cross-market-test/1",
        )


def test_cross_market_window_rejects_incomplete_day_and_identity_tampering() -> None:
    record = _record(10)

    with pytest.raises(ValueError, match="complete"):
        build_cross_market_window_observation(
            series=CrossMarketSeries.CBOE_VIX_CLOSE,
            unit=CrossMarketUnit.INDEX_POINTS,
            observed_at_ms=10 * _DAY_MS + 1,
            records=(record,),
            source=DataSource.REST,
            adapter_version="cross-market-test/1",
        )

    observation = build_cross_market_window_observation(
        series=CrossMarketSeries.CBOE_VIX_CLOSE,
        unit=CrossMarketUnit.INDEX_POINTS,
        observed_at_ms=12 * _DAY_MS,
        records=(record,),
        source=DataSource.REST,
        adapter_version="cross-market-test/1",
    )
    with pytest.raises(ValueError, match="observation identity mismatch"):
        replace(observation, observation_identity="f" * 64)

    with pytest.raises(ValueError, match="record identity mismatch"):
        replace(record, record_identity="f" * 64)
