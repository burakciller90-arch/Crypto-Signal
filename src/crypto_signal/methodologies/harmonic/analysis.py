from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise

from crypto_signal.data.models import Candle
from crypto_signal.methodologies.harmonic.candidates import enumerate_xabcd_candidates
from crypto_signal.methodologies.harmonic.engine import evaluate_all_patterns
from crypto_signal.methodologies.harmonic.models import (
    HarmonicAnalysisResult,
    HarmonicMatch,
    XABCDCandidate,
)
from crypto_signal.primitives.swings import (
    compress_alternating_pivots,
    detect_fractal_pivots,
)

METHODOLOGY_VERSION = "harmonic-v1/1"


def _candidate_has_positive_legs(candidate: XABCDCandidate) -> bool:
    prices = tuple(pivot.price for pivot in candidate.pivots)
    return all(left != right for left, right in pairwise(prices))


def analyze_harmonics(
    candles: Sequence[Candle],
    *,
    left_bars: int = 2,
    right_bars: int = 2,
    as_of_ms: int | None = None,
) -> HarmonicAnalysisResult:
    if not candles:
        raise ValueError("harmonic analysis requires candles")

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
    candidates = enumerate_xabcd_candidates(alternating.swings)

    matches: list[HarmonicMatch] = []
    degenerate = 0
    for candidate in candidates:
        if not _candidate_has_positive_legs(candidate):
            degenerate += 1
            continue
        matches.extend(evaluate_all_patterns(candidate))

    valid_matches = tuple(match for match in matches if match.valid)
    first = observed[0]
    return HarmonicAnalysisResult(
        exchange=first.exchange,
        market_type=first.market_type,
        symbol=first.symbol,
        timeframe=first.timeframe,
        as_of_ms=effective_as_of_ms,
        methodology_version=METHODOLOGY_VERSION,
        left_bars=left_bars,
        right_bars=right_bars,
        candidates=candidates,
        matches=tuple(matches),
        valid_matches=valid_matches,
        degenerate_candidate_count=degenerate,
        ambiguous_swing_source_indices=alternating.ambiguous_source_indices,
    )
