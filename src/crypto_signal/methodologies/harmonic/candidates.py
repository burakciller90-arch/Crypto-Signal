from __future__ import annotations

from collections.abc import Sequence

from crypto_signal.methodologies.harmonic.models import (
    HarmonicDirection,
    XABCDCandidate,
)
from crypto_signal.primitives.models import ConfirmedPivot, PivotKind

BULLISH_KINDS = (
    PivotKind.LOW,
    PivotKind.HIGH,
    PivotKind.LOW,
    PivotKind.HIGH,
    PivotKind.LOW,
)
BEARISH_KINDS = (
    PivotKind.HIGH,
    PivotKind.LOW,
    PivotKind.HIGH,
    PivotKind.LOW,
    PivotKind.HIGH,
)


def _validate_swings(swings: Sequence[ConfirmedPivot]) -> None:
    if not swings:
        return
    first = swings[0]
    previous_index = -1
    previous_kind: PivotKind | None = None
    for pivot in swings:
        if (
            pivot.exchange != first.exchange
            or pivot.market_type != first.market_type
            or pivot.symbol != first.symbol
            or pivot.timeframe != first.timeframe
        ):
            raise ValueError("harmonic candidates cannot mix pivot semantics")
        if pivot.candle_index <= previous_index:
            raise ValueError("harmonic pivots must be strictly chronological")
        if previous_kind is pivot.kind:
            raise ValueError("harmonic candidate source must alternate pivot kinds")
        previous_index = pivot.candle_index
        previous_kind = pivot.kind


def enumerate_xabcd_candidates(
    swings: Sequence[ConfirmedPivot],
) -> tuple[XABCDCandidate, ...]:
    _validate_swings(swings)
    if len(swings) < 5:
        return ()

    output: list[XABCDCandidate] = []
    first = swings[0]

    for index in range(len(swings) - 4):
        points = tuple(swings[index : index + 5])
        kinds = tuple(pivot.kind for pivot in points)
        if kinds == BULLISH_KINDS:
            direction = HarmonicDirection.BULLISH
        elif kinds == BEARISH_KINDS:
            direction = HarmonicDirection.BEARISH
        else:
            raise ValueError("five alternating pivots have impossible kind sequence")

        x, a, b, c, d = points
        output.append(
            XABCDCandidate(
                exchange=first.exchange,
                market_type=first.market_type,
                symbol=first.symbol,
                timeframe=first.timeframe,
                direction=direction,
                x=x,
                a=a,
                b=b,
                c=c,
                d=d,
                market_available_at_ms=d.market_confirmed_at_ms,
                observed_at_ms=d.observed_at_ms,
            )
        )

    return tuple(output)
