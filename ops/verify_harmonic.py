from __future__ import annotations

import asyncio
from collections import Counter
from datetime import UTC, datetime

from crypto_signal.data.adapters.base import MarketDataAdapter
from crypto_signal.data.adapters.binance import BinanceSpotAdapter
from crypto_signal.data.adapters.bybit import BybitSpotAdapter
from crypto_signal.data.health import detect_gaps
from crypto_signal.data.models import Candle
from crypto_signal.methodologies.harmonic.analysis import analyze_harmonics
from crypto_signal.methodologies.harmonic.models import HarmonicDirection

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
    assert output
    assert len({candle.open_time_ms for candle in output}) == len(output)
    assert detect_gaps(output, "15m") == ()
    assert all(candle.is_closed for candle in output)
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
    end_exclusive_ms = int(current_open.timestamp() * 1000)
    start_ms = int(datetime(2026, 8, 1, tzinfo=UTC).timestamp() * 1000)

    candles = await fetch_range(
        adapter,
        start_ms=start_ms,
        end_exclusive_ms=end_exclusive_ms,
    )
    as_of_ms = max(
        int(datetime.now(UTC).timestamp() * 1000),
        max(candle.ingested_at_ms for candle in candles),
    )

    result = analyze_harmonics(candles, as_of_ms=as_of_ms)
    repeat = analyze_harmonics(candles, as_of_ms=as_of_ms)
    assert result == repeat
    assert len(result.candidates) > 50
    assert len(result.matches) == (
        len(result.candidates) - result.degenerate_candidate_count
    ) * 5
    assert all(
        candidate.market_available_at_ms <= candidate.observed_at_ms <= as_of_ms
        for candidate in result.candidates
    )

    for match in result.valid_matches:
        assert match.valid is True
        assert all(item.valid for item in match.ratio_evidence)
        assert match.prz_low <= match.prz_high
        assert match.prz_width_bps >= 0
        assert match.fib_clustering_width_bps == match.prz_width_bps
        assert match.max_ratio_residual >= match.mean_ratio_residual >= 0
        if match.candidate.direction is HarmonicDirection.BULLISH:
            assert match.invalidation_price < match.candidate.d.price
            assert (
                match.candidate.d.price
                < match.target_1_price
                < match.target_2_price
                < match.candidate.a.price
            )
        else:
            assert match.invalidation_price > match.candidate.d.price
            assert (
                match.candidate.a.price
                < match.target_2_price
                < match.target_1_price
                < match.candidate.d.price
            )

    valid_kinds = Counter(match.pattern.value for match in result.valid_matches)
    candidate_directions = Counter(
        candidate.direction.value for candidate in result.candidates
    )

    print(
        name,
        f"candles={len(candles)}",
        f"candidates={len(result.candidates)}",
        f"matches={len(result.matches)}",
        f"valid={len(result.valid_matches)}",
        f"degenerate={result.degenerate_candidate_count}",
        f"ambiguous_swings={len(result.ambiguous_swing_source_indices)}",
    )
    print(name, "candidate_directions", dict(candidate_directions))
    print(name, "valid_patterns", dict(valid_kinds))

    ranked = sorted(
        result.matches,
        key=lambda match: (
            not match.valid,
            match.max_ratio_residual,
            match.mean_ratio_residual,
        ),
    )[:8]
    for match in ranked:
        print(
            name,
            match.pattern.value,
            "valid",
            match.valid,
            "max_residual",
            match.max_ratio_residual,
            "prz_bps",
            match.prz_width_bps,
            "symmetry",
            match.ab_cd_time_symmetry_error,
        )


async def main() -> None:
    await verify_provider("bybit", BybitSpotAdapter())
    await verify_provider("binance", BinanceSpotAdapter())


if __name__ == "__main__":
    asyncio.run(main())
