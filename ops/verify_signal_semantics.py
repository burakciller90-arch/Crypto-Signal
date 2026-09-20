from __future__ import annotations

import asyncio
from collections import Counter
from datetime import UTC, datetime

from crypto_signal.confluence.adapters import (
    elliott_result_evidence,
    harmonic_result_evidence,
    price_action_structure_evidence,
)
from crypto_signal.confluence.agreement import analyze_confluence
from crypto_signal.data.adapters.base import MarketDataAdapter
from crypto_signal.data.adapters.binance import BinanceSpotAdapter
from crypto_signal.data.adapters.bybit import BybitSpotAdapter
from crypto_signal.data.health import detect_gaps
from crypto_signal.data.models import Candle
from crypto_signal.methodologies.elliott.analysis import analyze_elliott
from crypto_signal.methodologies.harmonic.analysis import analyze_harmonics
from crypto_signal.methodologies.price_action.analysis import analyze_price_action
from crypto_signal.signals.models import (
    HistoricalStatsStatus,
    ProbabilityStatus,
    SignalDirection,
    SignalState,
)
from crypto_signal.signals.semantics import build_signal_decision

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

    pa = analyze_price_action(candles, as_of_ms=as_of_ms)
    harmonic = analyze_harmonics(candles, as_of_ms=as_of_ms)
    elliott = analyze_elliott(candles, as_of_ms=as_of_ms)

    evidence = []
    pa_item = price_action_structure_evidence(pa)
    if pa_item is not None:
        evidence.append(pa_item)
    evidence.extend(harmonic_result_evidence(harmonic))
    evidence.extend(elliott_result_evidence(elliott))

    confluence = analyze_confluence(
        evidence,
        exchange=candles[0].exchange,
        market_type=candles[0].market_type,
        symbol=candles[0].symbol,
        timeframe=candles[0].timeframe,
        as_of_ms=as_of_ms,
    )
    decision = build_signal_decision(confluence)
    repeat = build_signal_decision(confluence)

    assert decision == repeat
    assert decision.state is not SignalState.INVALIDATED
    assert decision.probability_status is ProbabilityStatus.NOT_CALIBRATED
    assert (
        decision.historical_stats_status
        is HistoricalStatsStatus.NOT_EVALUATED
    )
    assert len(decision.freeze_identity) == 64

    if decision.state is SignalState.ACTIVE:
        assert decision.direction is not SignalDirection.NONE
        assert decision.geometry is not None
        assert decision.agreement.support_method_count >= 2
        assert decision.agreement.opposing_method_count == 0
    if decision.geometry is not None:
        assert all(
            target.reference_rr > 0
            for target in decision.geometry.targets
        )

    counts = Counter(item.methodology.value for item in evidence)
    print(
        name,
        f"candles={len(candles)}",
        f"state={decision.state.value}",
        f"direction={decision.direction.value}",
        f"setup={decision.setup_type}",
        f"score={decision.agreement.confluence_score}",
        f"geometry={'yes' if decision.geometry is not None else 'no'}",
        f"freeze={decision.freeze_identity[:16]}",
    )
    print(name, "evidence_counts", dict(counts))
    print(name, "uncertainty_flags", decision.uncertainty_flags)


async def main() -> None:
    await verify_provider("bybit", BybitSpotAdapter())
    await verify_provider("binance", BinanceSpotAdapter())


if __name__ == "__main__":
    asyncio.run(main())
