from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from crypto_signal.confluence.adapters import (
    elliott_impulse_evidence,
    harmonic_match_evidence,
    price_action_structure_evidence,
)
from crypto_signal.confluence.models import (
    EvidenceDirection,
    EvidenceValidity,
    MethodologyKind,
)
from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.methodologies.elliott.engine import build_impulse_candidate
from crypto_signal.methodologies.harmonic.engine import evaluate_pattern
from crypto_signal.methodologies.harmonic.models import (
    HarmonicDirection,
    HarmonicMatch,
    HarmonicPatternKind,
    XABCDCandidate,
)
from crypto_signal.methodologies.price_action.analysis import analyze_price_action
from crypto_signal.methodologies.price_action.models import (
    StructureBreak,
    StructureBreakKind,
    StructureDirection,
)
from crypto_signal.primitives.models import ConfirmedPivot, PivotKind

BASE_MS = 900_000


def ms(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=UTC).timestamp() * 1000)


def candle(open_time_ms: int, index: int) -> Candle:
    block = index % 12
    center = Decimal(1000 + (index // 12) * 2)
    if block in {2, 3}:
        center += Decimal(20)
    elif block in {8, 9}:
        center -= Decimal(20)
    close = center + (Decimal(6) if index % 2 == 0 else Decimal(-6))
    high = max(center, close) + Decimal(4)
    low = min(center, close) - Decimal(4)
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + BASE_MS - 1,
        open=center,
        high=high,
        low=low,
        close=close,
        volume=Decimal(1),
        quote_volume=Decimal(1000),
        trade_count=None,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=open_time_ms + BASE_MS,
        ingested_at_ms=open_time_ms + BASE_MS + 1,
        adapter_version="test/1",
    )


def pivot(kind: PivotKind, index: int, price: Decimal) -> ConfirmedPivot:
    open_time_ms = index * BASE_MS
    confirmation_open_ms = (index + 1) * BASE_MS
    return ConfirmedPivot(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        kind=kind,
        candle_index=index,
        open_time_ms=open_time_ms,
        price=price,
        left_bars=1,
        right_bars=1,
        market_confirmed_at_ms=confirmation_open_ms + BASE_MS - 1,
        observed_at_ms=confirmation_open_ms + BASE_MS + 1,
        source_candle_identity=("bybit", "spot", "BTCUSDT", "15m", open_time_ms),
        confirmation_candle_identity=(
            "bybit",
            "spot",
            "BTCUSDT",
            "15m",
            confirmation_open_ms,
        ),
    )


def gartley_match() -> HarmonicMatch:
    xa = Decimal(100)
    x_price = Decimal(1000)
    a_price = Decimal(1100)
    b_price = a_price - Decimal("0.618") * xa
    c_price = b_price + Decimal("0.728248") * (a_price - b_price)
    d_price = a_price - Decimal("0.786") * xa
    kinds = (
        PivotKind.LOW,
        PivotKind.HIGH,
        PivotKind.LOW,
        PivotKind.HIGH,
        PivotKind.LOW,
    )
    prices = (x_price, a_price, b_price, c_price, d_price)
    points = tuple(
        pivot(kind, index * 3, price)
        for index, (kind, price) in enumerate(zip(kinds, prices, strict=True))
    )
    x, a, b, c, d = points
    candidate = XABCDCandidate(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        direction=HarmonicDirection.BULLISH,
        x=x,
        a=a,
        b=b,
        c=c,
        d=d,
        market_available_at_ms=d.market_confirmed_at_ms,
        observed_at_ms=d.observed_at_ms,
    )
    return evaluate_pattern(candidate, HarmonicPatternKind.GARTLEY)


def test_price_action_structure_maps_to_context_evidence() -> None:
    start = ms(2026, 9, 18)
    candles = [candle(start + index * BASE_MS, index) for index in range(240)]
    result = analyze_price_action(candles, as_of_ms=candles[-1].ingested_at_ms)
    pivot_value = result.structure.confirmed_pivots[-1]
    forced_break = StructureBreak(
        kind=StructureBreakKind.BOS,
        direction=StructureDirection.BULLISH,
        broken_pivot=pivot_value,
        break_candle_identity=candles[-1].identity,
        break_close=pivot_value.price + Decimal(10),
        level_price=pivot_value.price,
        distance_bps=Decimal(25),
        market_confirmed_at_ms=candles[-1].close_time_ms,
        observed_at_ms=candles[-1].ingested_at_ms,
    )
    result = replace(
        result,
        structure=replace(
            result.structure,
            current_direction=StructureDirection.BULLISH,
            structure_breaks=(forced_break,),
        ),
    )

    evidence = price_action_structure_evidence(result)

    assert evidence is not None
    assert evidence.methodology is MethodologyKind.PRICE_ACTION
    assert evidence.validity is EvidenceValidity.CONTEXT
    assert evidence.direction in {
        EvidenceDirection.BULLISH,
        EvidenceDirection.BEARISH,
    }
    assert evidence.entry_zone is None
    assert evidence.invalidation_price is None
    assert {level.label for level in evidence.key_levels} == {
        "broken_structure_level",
        "break_close",
    }
    assert evidence.observed_at_ms <= evidence.as_of_ms


def test_valid_harmonic_match_maps_geometry_without_probability() -> None:
    match = gartley_match()
    assert match.valid is True
    as_of_ms = match.candidate.observed_at_ms

    evidence = harmonic_match_evidence(
        match,
        as_of_ms=as_of_ms,
        methodology_version="harmonic-v1/1",
    )

    assert evidence.methodology is MethodologyKind.HARMONIC
    assert evidence.direction is EvidenceDirection.BULLISH
    assert evidence.validity is EvidenceValidity.VALID
    assert evidence.entry_zone is not None
    assert evidence.entry_zone.low == match.prz_low
    assert evidence.entry_zone.high == match.prz_high
    assert evidence.invalidation_price == match.invalidation_price
    assert [target.price for target in evidence.targets] == [
        match.target_1_price,
        match.target_2_price,
    ]
    assert {metric.name for metric in evidence.metrics} == {
        "mean_ratio_residual",
        "max_ratio_residual",
        "prz_width_bps",
        "fib_clustering_width_bps",
        "ab_cd_time_symmetry_error",
    }


def test_invalid_harmonic_match_is_rejected() -> None:
    match = gartley_match()
    invalid = replace(match, valid=False)

    with pytest.raises(ValueError, match="only valid Harmonic"):
        harmonic_match_evidence(
            invalid,
            as_of_ms=match.candidate.observed_at_ms,
            methodology_version="harmonic-v1/1",
        )


def test_valid_elliott_count_maps_invalidation_targets_and_ambiguity() -> None:
    points = (
        pivot(PivotKind.LOW, 0, Decimal(100)),
        pivot(PivotKind.HIGH, 2, Decimal(110)),
        pivot(PivotKind.LOW, 4, Decimal(105)),
        pivot(PivotKind.HIGH, 6, Decimal(120)),
        pivot(PivotKind.LOW, 8, Decimal(112)),
        pivot(PivotKind.HIGH, 10, Decimal(125)),
    )
    candidate = replace(
        build_impulse_candidate(points),
        competing_valid_count=3,
    )
    assert candidate.valid_so_far is True

    evidence = elliott_impulse_evidence(
        candidate,
        as_of_ms=candidate.observed_at_ms,
        methodology_version="elliott-v1/1",
    )

    assert evidence.methodology is MethodologyKind.ELLIOTT
    assert evidence.direction is EvidenceDirection.BULLISH
    assert evidence.validity is EvidenceValidity.VALID
    assert evidence.invalidation_price == candidate.structural_invalidation_price
    assert len(evidence.targets) == len(candidate.projections)
    assert evidence.ambiguity_flags == ("competing_valid_impulse_counts",)
    metrics = {metric.name: metric.value for metric in evidence.metrics}
    assert metrics["rule_support_fraction"] == Decimal(1)
    assert metrics["competing_valid_count"] == Decimal(3)


def test_invalid_elliott_count_is_rejected() -> None:
    points = (
        pivot(PivotKind.LOW, 0, Decimal(100)),
        pivot(PivotKind.HIGH, 2, Decimal(110)),
        pivot(PivotKind.LOW, 4, Decimal(105)),
        pivot(PivotKind.HIGH, 6, Decimal(120)),
        pivot(PivotKind.LOW, 8, Decimal(108)),
    )
    candidate = build_impulse_candidate(points)
    assert candidate.valid_so_far is False

    with pytest.raises(ValueError, match="invalid Elliott"):
        elliott_impulse_evidence(
            candidate,
            as_of_ms=candidate.observed_at_ms,
            methodology_version="elliott-v1/1",
        )


def test_adapter_rejects_as_of_before_observation() -> None:
    match = gartley_match()

    with pytest.raises(ValueError, match="after as_of"):
        harmonic_match_evidence(
            match,
            as_of_ms=match.candidate.observed_at_ms - 1,
            methodology_version="harmonic-v1/1",
        )
