from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.methodologies.price_action.imbalances import (
    BPRStatus,
    FairValueGap,
    FVGDirection,
    FVGStatus,
    analyze_imbalances,
    detect_balanced_price_ranges,
    detect_fvg_formations,
    evaluate_fvg_lifecycle,
)


def candle(
    index: int,
    *,
    high: str,
    low: str,
    open_: str | None = None,
    close: str | None = None,
    ingest_delay_ms: int = 1_000,
) -> Candle:
    open_time_ms = index * 900_000
    high_value = Decimal(high)
    low_value = Decimal(low)
    midpoint = (high_value + low_value) / Decimal(2)
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + 899_999,
        open=Decimal(open_) if open_ is not None else midpoint,
        high=high_value,
        low=low_value,
        close=Decimal(close) if close is not None else midpoint,
        volume=Decimal(1),
        quote_volume=Decimal(100),
        trade_count=None,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=open_time_ms + 900_000,
        ingested_at_ms=open_time_ms + 899_999 + ingest_delay_ms,
        adapter_version="test/1",
    )


def bullish_series() -> list[Candle]:
    return [
        candle(0, high="100", low="90"),
        candle(1, high="115", low="95"),
        candle(2, high="120", low="105"),
        candle(3, high="110", low="103"),
        candle(4, high="104", low="99"),
    ]


def bearish_series() -> list[Candle]:
    return [
        candle(0, high="120", low="110"),
        candle(1, high="125", low="105"),
        candle(2, high="105", low="95"),
        candle(3, high="107", low="100"),
        candle(4, high="111", low="108"),
    ]


def test_detects_strict_bullish_and_bearish_fvg_bounds() -> None:
    bullish = detect_fvg_formations(bullish_series()[:3])
    bearish = detect_fvg_formations(bearish_series()[:3])

    assert len(bullish) == 1
    assert bullish[0].direction is FVGDirection.BULLISH
    assert bullish[0].zone_low == Decimal(100)
    assert bullish[0].zone_high == Decimal(105)
    assert bullish[0].created_at_market_ms == bullish_series()[2].close_time_ms

    assert len(bearish) == 1
    assert bearish[0].direction is FVGDirection.BEARISH
    assert bearish[0].zone_low == Decimal(105)
    assert bearish[0].zone_high == Decimal(110)


def test_equal_boundary_is_not_an_fvg() -> None:
    series = [
        candle(0, high="100", low="90"),
        candle(1, high="110", low="95"),
        candle(2, high="120", low="100"),
    ]
    assert detect_fvg_formations(series) == ()


def test_bullish_lifecycle_moves_open_to_mitigated_to_filled() -> None:
    series = bullish_series()
    raw = detect_fvg_formations(series[:3])[0]

    mitigated = evaluate_fvg_lifecycle(raw, series[:4])
    filled = evaluate_fvg_lifecycle(raw, series)

    assert mitigated.status is FVGStatus.MITIGATED
    assert mitigated.first_touch_candle_identity == series[3].identity
    assert mitigated.max_fill_fraction == Decimal("0.4")
    assert mitigated.filled_candle_identity is None

    assert filled.status is FVGStatus.FILLED
    assert filled.filled_candle_identity == series[4].identity
    assert filled.max_fill_fraction == Decimal(1)
    assert filled.first_touch_market_ms == series[3].close_time_ms
    assert filled.filled_at_market_ms == series[4].close_time_ms


def test_bearish_lifecycle_moves_open_to_mitigated_to_filled() -> None:
    series = bearish_series()
    raw = detect_fvg_formations(series[:3])[0]

    mitigated = evaluate_fvg_lifecycle(raw, series[:4])
    filled = evaluate_fvg_lifecycle(raw, series)

    assert mitigated.status is FVGStatus.MITIGATED
    assert mitigated.max_fill_fraction == Decimal("0.4")
    assert filled.status is FVGStatus.FILLED
    assert filled.max_fill_fraction == Decimal(1)


def test_gap_through_is_flagged_without_inventing_fill() -> None:
    series = bullish_series()[:3] + [
        candle(3, high="99", low="95"),
    ]
    raw = detect_fvg_formations(series[:3])[0]
    result = evaluate_fvg_lifecycle(raw, series)

    assert result.status is FVGStatus.OPEN
    assert result.gap_through_ambiguity is True
    assert result.filled_at_market_ms is None


def make_fvg(
    *,
    direction: FVGDirection,
    confirmation_index: int,
    zone_low: str,
    zone_high: str,
    filled_at_market_ms: int | None = None,
) -> FairValueGap:
    first = candle(confirmation_index - 2, high="130", low="70")
    middle = candle(confirmation_index - 1, high="130", low="70")
    confirmation = candle(confirmation_index, high="130", low="70")
    low = Decimal(zone_low)
    high = Decimal(zone_high)
    return FairValueGap(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        direction=direction,
        confirmation_index=confirmation_index,
        first_candle_identity=first.identity,
        middle_candle_identity=middle.identity,
        confirmation_candle_identity=confirmation.identity,
        zone_low=low,
        zone_high=high,
        size_bps=((high - low) / ((high + low) / Decimal(2))) * Decimal(10_000),
        created_at_market_ms=confirmation.close_time_ms,
        observed_at_ms=confirmation.ingested_at_ms,
        status=FVGStatus.FILLED if filled_at_market_ms is not None else FVGStatus.OPEN,
        filled_at_market_ms=filled_at_market_ms,
        filled_candle_identity=(
            candle(confirmation_index + 1, high="130", low="70").identity
            if filled_at_market_ms is not None
            else None
        ),
        filled_observed_at_ms=(
            filled_at_market_ms + 1 if filled_at_market_ms is not None else None
        ),
        max_fill_fraction=Decimal(1) if filled_at_market_ms is not None else Decimal(0),
    )


def test_bpr_requires_positive_opposing_overlap_and_tracks_lifecycle() -> None:
    series = [
        candle(index, high="130", low="70")
        for index in range(8)
    ]
    series[6] = candle(6, high="108", low="107")
    series[7] = candle(7, high="111", low="104")

    bullish = make_fvg(
        direction=FVGDirection.BULLISH,
        confirmation_index=2,
        zone_low="100",
        zone_high="110",
    )
    bearish = make_fvg(
        direction=FVGDirection.BEARISH,
        confirmation_index=5,
        zone_low="105",
        zone_high="115",
    )

    bprs = detect_balanced_price_ranges([bullish, bearish], series)

    assert len(bprs) == 1
    bpr = bprs[0]
    assert bpr.zone_low == Decimal(105)
    assert bpr.zone_high == Decimal(110)
    assert bpr.status is BPRStatus.TRAVERSED
    assert bpr.first_touch_candle_identity == series[6].identity
    assert bpr.traversed_candle_identity == series[7].identity


def test_bpr_is_not_created_if_earlier_fvg_was_already_filled() -> None:
    series = [candle(index, high="130", low="70") for index in range(6)]
    later = make_fvg(
        direction=FVGDirection.BEARISH,
        confirmation_index=5,
        zone_low="105",
        zone_high="115",
    )
    earlier = make_fvg(
        direction=FVGDirection.BULLISH,
        confirmation_index=2,
        zone_low="100",
        zone_high="110",
        filled_at_market_ms=candle(4, high="130", low="70").close_time_ms,
    )

    assert detect_balanced_price_ranges([earlier, later], series) == ()


def test_as_of_does_not_reveal_fvg_before_confirmation_is_observed() -> None:
    series = bullish_series()[:3]
    before = analyze_imbalances(
        series,
        as_of_ms=series[1].ingested_at_ms,
    )
    after = analyze_imbalances(
        series,
        as_of_ms=series[2].ingested_at_ms,
    )

    assert before.fair_value_gaps == ()
    assert len(after.fair_value_gaps) == 1


def test_open_or_gapped_series_is_rejected() -> None:
    series = bullish_series()
    with pytest.raises(ValueError, match="closed candles"):
        detect_fvg_formations([*series[:-1], replace(series[-1], is_closed=False)])

    with pytest.raises(ValueError, match="gapless chronological"):
        detect_fvg_formations([series[0], series[2], series[3]])


def test_fvg_lifecycle_rejects_mixed_semantics() -> None:
    series = bullish_series()
    raw = detect_fvg_formations(series[:3])[0]
    mismatched = replace(raw, symbol="ETHUSDT")

    with pytest.raises(ValueError, match="cannot mix candle semantics"):
        evaluate_fvg_lifecycle(mismatched, series)


def test_bpr_rejects_duplicate_fvg_identity() -> None:
    series = [candle(index, high="130", low="70") for index in range(6)]
    bullish = make_fvg(
        direction=FVGDirection.BULLISH,
        confirmation_index=2,
        zone_low="100",
        zone_high="110",
    )

    with pytest.raises(ValueError, match="duplicate FVG identities"):
        detect_balanced_price_ranges([bullish, bullish], series)
