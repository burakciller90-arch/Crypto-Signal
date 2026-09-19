from __future__ import annotations

import asyncio
from datetime import UTC, datetime, time

from crypto_signal.data.adapters.base import MarketDataAdapter
from crypto_signal.data.adapters.binance import BinanceSpotAdapter
from crypto_signal.data.adapters.bybit import BybitSpotAdapter
from crypto_signal.data.health import detect_gaps
from crypto_signal.data.models import Candle
from crypto_signal.methodologies.price_action.levels import (
    PreviousPeriodKind,
    SessionSpec,
    analyze_period_session_levels,
)

BASE_MS = 900_000


async def fetch_range(
    adapter: MarketDataAdapter,
    *,
    start_ms: int,
    end_exclusive_ms: int,
) -> tuple[Candle, ...]:
    output: list[Candle] = []
    current = start_ms

    while current < end_exclusive_ms:
        remaining = (end_exclusive_ms - current) // BASE_MS
        limit = min(1000, remaining)
        page_end = current + limit * BASE_MS - 1
        page = await adapter.fetch_candles(
            symbol="BTCUSDT",
            timeframe="15m",
            limit=limit,
            start_ms=current,
            end_ms=page_end,
        )
        output.extend(page)
        current += limit * BASE_MS

    output.sort(key=lambda candle: candle.open_time_ms)
    assert len({candle.open_time_ms for candle in output}) == len(output)
    assert detect_gaps(output, "15m") == ()
    return tuple(output)


async def verify_provider(
    name: str,
    adapter: BybitSpotAdapter | BinanceSpotAdapter,
) -> None:
    wall_now = datetime.now(UTC)
    current_open = wall_now.replace(
        minute=(wall_now.minute // 15) * 15,
        second=0,
        microsecond=0,
    )
    end_exclusive = int(current_open.timestamp() * 1000)
    start = datetime(2026, 8, 1, tzinfo=UTC)
    start_ms = int(start.timestamp() * 1000)

    candles = await fetch_range(
        adapter,
        start_ms=start_ms,
        end_exclusive_ms=end_exclusive,
    )
    assert candles
    assert all(candle.is_closed for candle in candles)

    as_of_ms = max(
        int(datetime.now(UTC).timestamp() * 1000),
        max(candle.ingested_at_ms for candle in candles),
    )
    session = SessionSpec(
        name="verification_istanbul_09_11",
        timezone="Europe/Istanbul",
        start_local=time(9, 0),
        end_local=time(11, 0),
    )
    result = analyze_period_session_levels(
        candles,
        sessions=(session,),
        as_of_ms=as_of_ms,
    )
    repeat = analyze_period_session_levels(
        candles,
        sessions=(session,),
        as_of_ms=as_of_ms,
    )
    assert result == repeat

    periods = dict(result.previous_periods)
    for kind in PreviousPeriodKind:
        evidence = periods[kind]
        assert evidence.complete is True
        assert evidence.high is not None
        assert evidence.low is not None
        assert evidence.high >= evidence.low
        assert evidence.observed_count == evidence.expected_count
        assert evidence.missing_open_times_ms == ()

    session_evidence = result.sessions[0]
    assert session_evidence.complete is True
    assert session_evidence.expected_count == 8
    assert session_evidence.observed_count == 8
    print(name, "candles", len(candles))
    for kind in PreviousPeriodKind:
        evidence = periods[kind]
        print(
            name,
            kind.value,
            f"count={evidence.observed_count}",
            f"high={evidence.high}",
            f"low={evidence.low}",
            f"window={evidence.start_ms}->{evidence.end_exclusive_ms}",
        )
    print(
        name,
        session_evidence.label,
        f"high={session_evidence.high}",
        f"low={session_evidence.low}",
        f"window={session_evidence.start_ms}->{session_evidence.end_exclusive_ms}",
    )


async def main() -> None:
    await verify_provider("bybit", BybitSpotAdapter())
    await verify_provider("binance", BinanceSpotAdapter())


if __name__ == "__main__":
    asyncio.run(main())
