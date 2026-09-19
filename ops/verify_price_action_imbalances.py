from __future__ import annotations

import asyncio
from collections import Counter

from crypto_signal.data.adapters.binance import BinanceSpotAdapter
from crypto_signal.data.adapters.bybit import BybitSpotAdapter
from crypto_signal.data.health import detect_gaps
from crypto_signal.methodologies.price_action.imbalances import (
    BPRStatus,
    FVGStatus,
    analyze_imbalances,
)


async def verify_provider(
    name: str,
    adapter: BybitSpotAdapter | BinanceSpotAdapter,
) -> None:
    recent = await adapter.fetch_candles(
        symbol="BTCUSDT",
        timeframe="15m",
        limit=902,
    )
    closed = [candle for candle in recent if candle.is_closed][-900:]
    assert len(closed) == 900
    assert detect_gaps(closed, "15m") == ()

    result = analyze_imbalances(closed)
    repeat = analyze_imbalances(closed)
    assert result == repeat
    assert len(result.fair_value_gaps) > 20

    for fvg in result.fair_value_gaps:
        assert fvg.created_at_market_ms <= fvg.observed_at_ms
        assert 0 <= fvg.max_fill_fraction <= 1
        if fvg.first_touch_market_ms is not None:
            assert fvg.first_touch_market_ms > fvg.created_at_market_ms
            assert fvg.first_touch_observed_at_ms is not None
            assert fvg.first_touch_market_ms <= fvg.first_touch_observed_at_ms
        if fvg.filled_at_market_ms is not None:
            assert fvg.status is FVGStatus.FILLED
            assert fvg.first_touch_market_ms is not None
            assert fvg.filled_at_market_ms >= fvg.first_touch_market_ms
            assert fvg.filled_observed_at_ms is not None
            assert fvg.filled_at_market_ms <= fvg.filled_observed_at_ms
    for bpr in result.balanced_price_ranges:
        assert bpr.created_at_market_ms <= bpr.observed_at_ms
        assert bpr.zone_low < bpr.zone_high
        if bpr.first_touch_market_ms is not None:
            assert bpr.first_touch_market_ms > bpr.created_at_market_ms
            assert bpr.first_touch_observed_at_ms is not None
        if bpr.traversed_at_market_ms is not None:
            assert bpr.status is BPRStatus.TRAVERSED
            assert bpr.first_touch_market_ms is not None
            assert bpr.traversed_at_market_ms >= bpr.first_touch_market_ms

    fvg_statuses = Counter(item.status.value for item in result.fair_value_gaps)
    fvg_directions = Counter(item.direction.value for item in result.fair_value_gaps)
    bpr_statuses = Counter(item.status.value for item in result.balanced_price_ranges)
    ambiguous = sum(item.gap_through_ambiguity for item in result.fair_value_gaps)

    print(
        name,
        f"closed={len(closed)}",
        f"fvgs={len(result.fair_value_gaps)}",
        f"bprs={len(result.balanced_price_ranges)}",
        f"gap_through_ambiguous={ambiguous}",
    )
    print(name, "fvg_directions", dict(fvg_directions))
    print(name, "fvg_statuses", dict(fvg_statuses))
    print(name, "bpr_statuses", dict(bpr_statuses))

    for fvg in result.fair_value_gaps[-5:]:
        print(
            name,
            "FVG",
            fvg.direction.value,
            fvg.status.value,
            f"[{fvg.zone_low},{fvg.zone_high}]",
            "fill",
            fvg.max_fill_fraction,
            "ambiguous",
            fvg.gap_through_ambiguity,
        )
    for bpr in result.balanced_price_ranges[-3:]:
        print(
            name,
            "BPR",
            bpr.status.value,
            f"[{bpr.zone_low},{bpr.zone_high}]",
            "created",
            bpr.created_at_market_ms,
        )


async def main() -> None:
    await verify_provider("bybit", BybitSpotAdapter())
    await verify_provider("binance", BinanceSpotAdapter())


if __name__ == "__main__":
    asyncio.run(main())
