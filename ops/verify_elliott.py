from __future__ import annotations

import asyncio
from collections import Counter
from datetime import UTC, datetime

from crypto_signal.data.adapters.base import MarketDataAdapter
from crypto_signal.data.adapters.binance import BinanceSpotAdapter
from crypto_signal.data.adapters.bybit import BybitSpotAdapter
from crypto_signal.data.health import detect_gaps
from crypto_signal.data.models import Candle
from crypto_signal.methodologies.elliott.analysis import analyze_elliott
from crypto_signal.methodologies.elliott.models import ElliottRuleStatus

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


def validate_result(result: object, as_of_ms: int) -> None:
    from crypto_signal.methodologies.elliott.models import ElliottAnalysisResult

    assert isinstance(result, ElliottAnalysisResult)
    assert result.impulse_candidates
    assert result.abc_candidates
    assert result.ambiguity

    for candidate in result.impulse_candidates:
        assert candidate.market_available_at_ms <= candidate.observed_at_ms <= as_of_ms
        assert 1 <= candidate.current_wave <= 5
        assert 0 <= candidate.rule_support_fraction <= 1
        assert candidate.structural_invalidation_price > 0
        if candidate.valid_so_far:
            assert all(
                rule.status is not ElliottRuleStatus.FAIL
                for rule in candidate.rules
            )

    for candidate in result.abc_candidates:
        assert candidate.market_available_at_ms <= candidate.observed_at_ms <= as_of_ms
        assert 0 <= candidate.rule_support_fraction <= 1
        if candidate.zigzag_compatible:
            assert all(
                rule.status is ElliottRuleStatus.PASS
                for rule in candidate.zigzag_rules
            )


async def verify_long(
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
    result = analyze_elliott(candles, as_of_ms=as_of_ms)
    repeat = analyze_elliott(candles, as_of_ms=as_of_ms)
    assert result == repeat
    validate_result(result, as_of_ms)

    complete = [
        candidate for candidate in result.impulse_candidates if candidate.complete
    ]
    valid_complete = [candidate for candidate in complete if candidate.valid_so_far]
    valid_truncated = [
        candidate for candidate in valid_complete if candidate.truncated_fifth
    ]
    zigzags = [
        candidate for candidate in result.abc_candidates if candidate.zigzag_compatible
    ]
    current_wave_counts = Counter(
        candidate.current_wave for candidate in result.impulse_candidates
    )
    ambiguous_ends = sum(
        item.valid_impulse_count > 1 for item in result.ambiguity
    )

    print(
        name,
        f"candles={len(candles)}",
        f"impulse_candidates={len(result.impulse_candidates)}",
        f"complete={len(complete)}",
        f"valid_complete={len(valid_complete)}",
        f"valid_truncated={len(valid_truncated)}",
        f"abc={len(result.abc_candidates)}",
        f"zigzag_compatible={len(zigzags)}",
        f"ambiguous_ends={ambiguous_ends}",
    )
    print(name, "current_wave_counts", dict(sorted(current_wave_counts.items())))


async def verify_timeframes(
    name: str,
    adapter: BybitSpotAdapter | BinanceSpotAdapter,
) -> None:
    for timeframe in ("15m", "1h", "4h", "1D", "1W"):
        raw = await adapter.fetch_candles(
            symbol="BTCUSDT",
            timeframe=timeframe,
            limit=500,
        )
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        candles = tuple(
            candle
            for candle in raw
            if candle.is_closed
            and candle.close_time_ms <= now_ms
            and candle.ingested_at_ms <= now_ms
        )
        assert len(candles) >= 100
        result = analyze_elliott(candles, as_of_ms=now_ms)
        assert result == analyze_elliott(candles, as_of_ms=now_ms)
        validate_result(result, now_ms)
        valid_complete = sum(
            candidate.complete and candidate.valid_so_far
            for candidate in result.impulse_candidates
        )
        zigzags = sum(
            candidate.zigzag_compatible for candidate in result.abc_candidates
        )
        print(
            name,
            timeframe,
            f"closed={len(candles)}",
            f"valid_complete={valid_complete}",
            f"zigzag_compatible={zigzags}",
        )


async def main() -> None:
    providers = {
        "bybit": BybitSpotAdapter(),
        "binance": BinanceSpotAdapter(),
    }
    for name, adapter in providers.items():
        await verify_long(name, adapter)
    for name, adapter in providers.items():
        await verify_timeframes(name, adapter)


if __name__ == "__main__":
    asyncio.run(main())
