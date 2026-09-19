from __future__ import annotations

import asyncio
from collections import Counter
from decimal import Decimal

from crypto_signal.data.adapters.binance import BinanceSpotAdapter
from crypto_signal.data.adapters.bybit import BybitSpotAdapter
from crypto_signal.data.health import detect_gaps
from crypto_signal.methodologies.price_action.liquidity import (
    LiquidityEventKind,
    LiquidityPoolStatus,
    analyze_liquidity,
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

    result = analyze_liquidity(
        closed,
        equal_tolerance_bps=Decimal(5),
    )
    repeat = analyze_liquidity(
        closed,
        equal_tolerance_bps=Decimal(5),
    )
    assert result == repeat
    assert result.equal_tolerance_bps == Decimal(5)
    assert len(result.pools) > 5

    for pool in result.pools:
        assert pool.formed_at_market_ms <= pool.formed_observed_at_ms
        assert pool.pair_distance_bps <= result.equal_tolerance_bps
        assert pool.first_anchor.kind is pool.second_anchor.kind
        if pool.event is not None:
            assert pool.event.market_confirmed_at_ms > pool.formed_at_market_ms
            assert pool.event.market_confirmed_at_ms <= pool.event.observed_at_ms
            if pool.status is LiquidityPoolStatus.SWEPT_SFP:
                assert pool.event.kind is LiquidityEventKind.SFP_REJECTION
                assert pool.event.close_recovery_bps >= 0
            elif pool.status is LiquidityPoolStatus.BROKEN_CLOSE:
                assert pool.event.kind is LiquidityEventKind.CLOSE_THROUGH
                assert pool.event.close_recovery_bps < 0

    kinds = Counter(pool.kind.value for pool in result.pools)
    statuses = Counter(pool.status.value for pool in result.pools)
    events = Counter(
        pool.event.kind.value
        for pool in result.pools
        if pool.event is not None
    )

    print(
        name,
        f"closed={len(closed)}",
        f"pools={len(result.pools)}",
        f"ambiguous_swings={len(result.ambiguous_swing_source_indices)}",
    )
    print(name, "pool_kinds", dict(kinds))
    print(name, "pool_statuses", dict(statuses))
    print(name, "events", dict(events))

    for pool in result.pools[-5:]:
        print(
            name,
            pool.kind.value,
            pool.status.value,
            f"zone=[{pool.zone_low},{pool.zone_high}]",
            f"distance_bps={pool.pair_distance_bps}",
            "event",
            None if pool.event is None else pool.event.kind.value,
        )


async def main() -> None:
    await verify_provider("bybit", BybitSpotAdapter())
    await verify_provider("binance", BinanceSpotAdapter())


if __name__ == "__main__":
    asyncio.run(main())
