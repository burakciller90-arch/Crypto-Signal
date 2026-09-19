from __future__ import annotations

from collections.abc import Sequence

from crypto_signal.data.models import Candle
from crypto_signal.methodologies.elliott.engine import (
    apply_competing_counts,
    enumerate_abc_candidates,
    enumerate_impulse_candidates,
)
from crypto_signal.methodologies.elliott.models import ElliottAnalysisResult
from crypto_signal.primitives.swings import (
    compress_alternating_pivots,
    detect_fractal_pivots,
)

METHODOLOGY_VERSION = "elliott-v1/1"


def analyze_elliott(
    candles: Sequence[Candle],
    *,
    left_bars: int = 2,
    right_bars: int = 2,
    as_of_ms: int | None = None,
) -> ElliottAnalysisResult:
    if not candles:
        raise ValueError("Elliott analysis requires candles")

    effective_as_of_ms = (
        max(candle.ingested_at_ms for candle in candles)
        if as_of_ms is None
        else as_of_ms
    )
    observed = tuple(
        candle
        for candle in candles
        if candle.close_time_ms <= effective_as_of_ms
        and candle.ingested_at_ms <= effective_as_of_ms
    )
    if not observed:
        raise ValueError("no candles were both closed and observed by as_of_ms")

    pivots = detect_fractal_pivots(
        observed,
        left_bars=left_bars,
        right_bars=right_bars,
    )
    alternating = compress_alternating_pivots(pivots)
    impulse_raw = enumerate_impulse_candidates(alternating.swings)
    impulse_candidates, ambiguity = apply_competing_counts(impulse_raw)
    abc_candidates = enumerate_abc_candidates(alternating.swings)

    first = observed[0]
    return ElliottAnalysisResult(
        exchange=first.exchange,
        market_type=first.market_type,
        symbol=first.symbol,
        timeframe=first.timeframe,
        as_of_ms=effective_as_of_ms,
        methodology_version=METHODOLOGY_VERSION,
        impulse_candidates=impulse_candidates,
        abc_candidates=abc_candidates,
        ambiguity=ambiguity,
        ambiguous_swing_source_indices=alternating.ambiguous_source_indices,
    )
