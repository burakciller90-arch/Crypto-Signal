from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from crypto_signal.confluence.adapters import (
    elliott_result_evidence,
    harmonic_result_evidence,
    price_action_structure_evidence,
)
from crypto_signal.confluence.agreement import analyze_confluence
from crypto_signal.data.adapters.binance import BinanceSpotAdapter
from crypto_signal.data.adapters.bybit import BybitSpotAdapter
from crypto_signal.methodologies.elliott.analysis import analyze_elliott
from crypto_signal.methodologies.harmonic.analysis import analyze_harmonics
from crypto_signal.methodologies.price_action.analysis import analyze_price_action
from crypto_signal.signals.lifecycle import evaluate_signal_lifecycle
from crypto_signal.signals.models import LifecycleEvaluationStatus
from crypto_signal.signals.semantics import build_signal_decision


async def verify_provider(
    name: str,
    adapter: BybitSpotAdapter | BinanceSpotAdapter,
) -> None:
    raw = await adapter.fetch_candles(
        symbol="BTCUSDT",
        timeframe="15m",
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

    as_of_ms = max(
        now_ms,
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

    lifecycle = evaluate_signal_lifecycle(
        decision,
        candles,
        as_of_ms=decision.as_of_ms,
    )
    repeat = evaluate_signal_lifecycle(
        decision,
        tuple(reversed(candles)),
        as_of_ms=decision.as_of_ms,
    )

    assert lifecycle == repeat
    assert lifecycle.signal_freeze_identity == decision.freeze_identity
    assert lifecycle.current_state is decision.state
    assert lifecycle.transition is None
    assert lifecycle.status is LifecycleEvaluationStatus.NO_NEW_EVIDENCE
    assert lifecycle.missing_open_times_ms == ()

    print(
        name,
        f"closed={len(candles)}",
        f"decision_state={decision.state.value}",
        f"direction={decision.direction.value}",
        f"score={decision.agreement.confluence_score}",
        f"lifecycle={lifecycle.status.value}",
        f"skipped_partial={lifecycle.skipped_partial_decision_bucket}",
        f"freeze={decision.freeze_identity[:16]}",
    )


async def main() -> None:
    await verify_provider("bybit", BybitSpotAdapter())
    await verify_provider("binance", BinanceSpotAdapter())


if __name__ == "__main__":
    asyncio.run(main())
