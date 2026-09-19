from decimal import Decimal

import pytest

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.methodologies.harmonic.contracts import PATTERN_SPECS
from crypto_signal.methodologies.harmonic.engine import (
    calculate_ratios,
    evaluate_pattern,
    ratio_evidence,
)
from crypto_signal.methodologies.harmonic.models import (
    HarmonicDirection,
    HarmonicPatternKind,
    XABCDCandidate,
)
from crypto_signal.primitives.models import ConfirmedPivot, PivotKind

FIXTURES = {
    HarmonicPatternKind.GARTLEY: ("0.618", "0.728248", "0.786"),
    HarmonicPatternKind.BAT: ("0.5", "0.497920", "0.886"),
    HarmonicPatternKind.BUTTERFLY: ("0.786", "0.617872", "1.27"),
    HarmonicPatternKind.CRAB: ("0.618", "0.618376", "1.618"),
    HarmonicPatternKind.DEEP_CRAB: ("0.886", "0.617872", "1.618"),
}


def pivot(kind: PivotKind, index: int, price: Decimal) -> ConfirmedPivot:
    open_time_ms = index * 900_000
    confirm_open_ms = (index + 1) * 900_000
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
        market_confirmed_at_ms=confirm_open_ms + 899_999,
        observed_at_ms=confirm_open_ms + 900_999,
        source_candle_identity=("bybit", "spot", "BTCUSDT", "15m", open_time_ms),
        confirmation_candle_identity=(
            "bybit",
            "spot",
            "BTCUSDT",
            "15m",
            confirm_open_ms,
        ),
    )


def fixture_candidate(
    pattern: HarmonicPatternKind,
    *,
    direction: HarmonicDirection = HarmonicDirection.BULLISH,
) -> XABCDCandidate:
    b_ratio, c_ratio, d_ratio = map(Decimal, FIXTURES[pattern])
    xa = Decimal(100)

    if direction is HarmonicDirection.BULLISH:
        x_price = Decimal(1000)
        a_price = Decimal(1100)
        b_price = a_price - b_ratio * xa
        c_price = b_price + c_ratio * (a_price - b_price)
        d_price = a_price - d_ratio * xa
        kinds = (PivotKind.LOW, PivotKind.HIGH, PivotKind.LOW, PivotKind.HIGH, PivotKind.LOW)
    else:
        x_price = Decimal(1100)
        a_price = Decimal(1000)
        b_price = a_price + b_ratio * xa
        c_price = b_price - c_ratio * (b_price - a_price)
        d_price = a_price + d_ratio * xa
        kinds = (PivotKind.HIGH, PivotKind.LOW, PivotKind.HIGH, PivotKind.LOW, PivotKind.HIGH)

    prices = (x_price, a_price, b_price, c_price, d_price)
    indices = (0, 3, 6, 9, 12)
    points = tuple(
        pivot(kind, index, price)
        for kind, index, price in zip(kinds, indices, prices, strict=True)
    )
    x, a, b, c, d = points
    return XABCDCandidate(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        direction=direction,
        x=x,
        a=a,
        b=b,
        c=c,
        d=d,
        market_available_at_ms=d.market_confirmed_at_ms,
        observed_at_ms=d.observed_at_ms,
    )


@pytest.mark.parametrize("pattern", list(HarmonicPatternKind))
def test_exact_contract_fixtures_validate(pattern: HarmonicPatternKind) -> None:
    candidate = fixture_candidate(pattern)
    match = evaluate_pattern(candidate, pattern)

    assert match.valid is True
    assert all(item.valid for item in match.ratio_evidence)
    assert match.max_ratio_residual >= 0
    assert match.mean_ratio_residual >= 0
    assert match.prz_low <= match.prz_high
    assert match.prz_width_bps >= 0
    assert match.fib_clustering_width_bps == match.prz_width_bps
    assert len(match.projections) == 3
    assert match.ab_cd_time_symmetry_error == Decimal(0)

    d_xa_projection = next(
        item for item in match.projections if item.source == "d_xa"
    )
    assert d_xa_projection.price == candidate.d.price
    assert d_xa_projection.actual_d_distance_bps == 0

    assert candidate.d.price < match.target_1_price < match.target_2_price < candidate.a.price
    assert match.invalidation_price < candidate.d.price


@pytest.mark.parametrize("pattern", list(HarmonicPatternKind))
def test_bearish_fixture_is_exact_mirror(pattern: HarmonicPatternKind) -> None:
    candidate = fixture_candidate(pattern, direction=HarmonicDirection.BEARISH)
    match = evaluate_pattern(candidate, pattern)

    assert match.valid is True
    assert candidate.a.price < match.target_2_price < match.target_1_price < candidate.d.price
    assert match.invalidation_price > candidate.d.price


def test_wrong_pattern_keeps_residual_evidence_without_false_validity() -> None:
    candidate = fixture_candidate(HarmonicPatternKind.GARTLEY)
    match = evaluate_pattern(candidate, HarmonicPatternKind.CRAB)

    assert match.valid is False
    assert len(match.ratio_evidence) == 5
    assert any(not item.valid for item in match.ratio_evidence)
    assert match.max_ratio_residual > 0


def test_crab_minimum_abcd_contract_has_no_artificial_upper_rejection() -> None:
    candidate = fixture_candidate(HarmonicPatternKind.CRAB)
    ratios = calculate_ratios(candidate)
    constraint = PATTERN_SPECS[HarmonicPatternKind.CRAB].cd_ab
    evidence = ratio_evidence(constraint, ratios.cd_ab)

    assert ratios.cd_ab > Decimal("1.618")
    assert evidence.valid is True
    assert evidence.residual == 0


def test_target_residual_is_relative_to_target() -> None:
    constraint = PATTERN_SPECS[HarmonicPatternKind.GARTLEY].b_xa

    exact = ratio_evidence(constraint, Decimal("0.618"))
    off = ratio_evidence(constraint, Decimal("0.60"))

    assert exact.valid is True
    assert exact.residual == 0
    assert off.residual == abs(Decimal("0.60") - Decimal("0.618")) / Decimal("0.618")


def test_nonphysical_projection_is_invalid_evidence_not_analysis_failure() -> None:
    kinds = (
        PivotKind.LOW,
        PivotKind.HIGH,
        PivotKind.LOW,
        PivotKind.HIGH,
        PivotKind.LOW,
    )
    prices = (
        Decimal(1),
        Decimal(10),
        Decimal(5),
        Decimal(7),
        Decimal(2),
    )
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

    match = evaluate_pattern(candidate, HarmonicPatternKind.CRAB)

    assert match.geometry_valid is False
    assert match.valid is False
    assert any(not projection.physical for projection in match.projections)
    assert match.prz_low <= 0
