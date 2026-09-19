from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.methodologies.harmonic.candidates import enumerate_xabcd_candidates
from crypto_signal.methodologies.harmonic.models import HarmonicDirection
from crypto_signal.primitives.models import ConfirmedPivot, PivotKind


def pivot(kind: PivotKind, index: int, price: str) -> ConfirmedPivot:
    open_time_ms = index * 900_000
    confirmation_open_ms = (index + 1) * 900_000
    return ConfirmedPivot(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        kind=kind,
        candle_index=index,
        open_time_ms=open_time_ms,
        price=Decimal(price),
        left_bars=1,
        right_bars=1,
        market_confirmed_at_ms=confirmation_open_ms + 899_999,
        observed_at_ms=confirmation_open_ms + 900_999,
        source_candle_identity=("bybit", "spot", "BTCUSDT", "15m", open_time_ms),
        confirmation_candle_identity=(
            "bybit",
            "spot",
            "BTCUSDT",
            "15m",
            confirmation_open_ms,
        ),
    )


def test_enumerates_bullish_and_bearish_consecutive_xabcd() -> None:
    bullish = [
        pivot(PivotKind.LOW, 0, "1000"),
        pivot(PivotKind.HIGH, 2, "1100"),
        pivot(PivotKind.LOW, 4, "1040"),
        pivot(PivotKind.HIGH, 6, "1080"),
        pivot(PivotKind.LOW, 8, "1020"),
    ]
    bearish = [
        pivot(PivotKind.HIGH, 10, "1100"),
        pivot(PivotKind.LOW, 12, "1000"),
        pivot(PivotKind.HIGH, 14, "1060"),
        pivot(PivotKind.LOW, 16, "1020"),
        pivot(PivotKind.HIGH, 18, "1080"),
    ]

    bull_candidate = enumerate_xabcd_candidates(bullish)[0]
    bear_candidate = enumerate_xabcd_candidates(bearish)[0]

    assert bull_candidate.direction is HarmonicDirection.BULLISH
    assert bear_candidate.direction is HarmonicDirection.BEARISH
    assert bull_candidate.market_available_at_ms == bullish[-1].market_confirmed_at_ms
    assert bull_candidate.observed_at_ms == bullish[-1].observed_at_ms
    assert bull_candidate.pivots == tuple(bullish)


def test_sliding_window_emits_every_five_consecutive_swings() -> None:
    swings = [
        pivot(PivotKind.LOW if index % 2 == 0 else PivotKind.HIGH, index * 2, str(1000 + index))
        for index in range(7)
    ]

    candidates = enumerate_xabcd_candidates(swings)

    assert len(candidates) == 3
    assert candidates[0].x == swings[0]
    assert candidates[1].x == swings[1]
    assert candidates[2].d == swings[6]


def test_candidate_source_rejects_non_alternating_or_mixed_semantics() -> None:
    swings = [
        pivot(PivotKind.LOW, 0, "1000"),
        pivot(PivotKind.HIGH, 2, "1100"),
        pivot(PivotKind.LOW, 4, "1040"),
        pivot(PivotKind.HIGH, 6, "1080"),
        pivot(PivotKind.LOW, 8, "1020"),
    ]

    non_alternating = [*swings]
    non_alternating[2] = replace(non_alternating[2], kind=PivotKind.HIGH)
    with pytest.raises(ValueError, match="alternate"):
        enumerate_xabcd_candidates(non_alternating)

    mixed = [*swings]
    mixed[4] = replace(mixed[4], symbol="ETHUSDT")
    with pytest.raises(ValueError, match="mix pivot semantics"):
        enumerate_xabcd_candidates(mixed)
