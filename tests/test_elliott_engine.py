from decimal import Decimal

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.methodologies.elliott.engine import (
    apply_competing_counts,
    build_abc_candidate,
    build_impulse_candidate,
    enumerate_impulse_candidates,
)
from crypto_signal.methodologies.elliott.models import (
    ElliottDirection,
    ElliottRuleStatus,
)
from crypto_signal.primitives.models import ConfirmedPivot, PivotKind


def pivot(kind: PivotKind, index: int, price: str) -> ConfirmedPivot:
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
        price=Decimal(price),
        left_bars=1,
        right_bars=1,
        market_confirmed_at_ms=confirm_open_ms + 899_999,
        observed_at_ms=confirm_open_ms + 900_999,
        source_candle_identity=("bybit", "spot", "BTCUSDT", "15m", open_time_ms),
        confirmation_candle_identity=("bybit", "spot", "BTCUSDT", "15m", confirm_open_ms),
    )


def bullish_impulse_prices() -> tuple[ConfirmedPivot, ...]:
    specs = (
        (PivotKind.LOW, 0, "100"),
        (PivotKind.HIGH, 2, "110"),
        (PivotKind.LOW, 4, "105"),
        (PivotKind.HIGH, 6, "120"),
        (PivotKind.LOW, 8, "112"),
        (PivotKind.HIGH, 10, "125"),
    )
    return tuple(pivot(*spec) for spec in specs)


def test_complete_bullish_impulse_passes_hard_rules() -> None:
    candidate = build_impulse_candidate(bullish_impulse_prices())

    assert candidate.direction is ElliottDirection.BULLISH
    assert candidate.current_wave == 5
    assert candidate.complete is True
    assert candidate.valid_so_far is True
    assert candidate.rule_support_fraction == Decimal(1)
    assert candidate.truncated_fifth is False
    assert all(
        rule.status is ElliottRuleStatus.PASS
        for rule in candidate.rules
    )
    assert candidate.structural_invalidation_price == Decimal(100)
    assert {projection.name for projection in candidate.projections} == {
        "wave5_equals_wave1",
        "wave5_0_618_wave1",
    }


def test_partial_impulse_marks_future_rules_not_applicable() -> None:
    candidate = build_impulse_candidate(bullish_impulse_prices()[:4])

    assert candidate.current_wave == 3
    assert candidate.complete is False
    assert candidate.valid_so_far is True
    assert [rule.status for rule in candidate.rules] == [
        ElliottRuleStatus.PASS,
        ElliottRuleStatus.PASS,
        ElliottRuleStatus.NOT_APPLICABLE,
        ElliottRuleStatus.NOT_APPLICABLE,
        ElliottRuleStatus.NOT_APPLICABLE,
    ]
    assert candidate.projections == ()


def test_wave4_overlap_invalidates_standard_impulse() -> None:
    points = list(bullish_impulse_prices())
    points[4] = pivot(PivotKind.LOW, 8, "108")
    candidate = build_impulse_candidate(points)

    rules = {rule.name: rule.status for rule in candidate.rules}
    assert rules["wave4_no_overlap_wave1"] is ElliottRuleStatus.FAIL
    assert candidate.valid_so_far is False


def test_wave3_cannot_be_shortest() -> None:
    points = (
        pivot(PivotKind.LOW, 0, "100"),
        pivot(PivotKind.HIGH, 2, "110"),
        pivot(PivotKind.LOW, 4, "105"),
        pivot(PivotKind.HIGH, 6, "112"),
        pivot(PivotKind.LOW, 8, "111"),
        pivot(PivotKind.HIGH, 10, "125"),
    )
    candidate = build_impulse_candidate(points)

    rules = {rule.name: rule.status for rule in candidate.rules}
    assert rules["wave3_not_shortest"] is ElliottRuleStatus.FAIL
    assert candidate.valid_so_far is False


def test_truncated_fifth_is_evidence_not_hard_failure() -> None:
    points = list(bullish_impulse_prices())
    points[5] = pivot(PivotKind.HIGH, 10, "118")
    candidate = build_impulse_candidate(points)

    assert candidate.truncated_fifth is True
    assert candidate.valid_so_far is True


def test_competing_counts_are_preserved_at_same_end_swing() -> None:
    swings = (
        *bullish_impulse_prices(),
        pivot(PivotKind.LOW, 12, "115"),
    )
    raw = enumerate_impulse_candidates(swings)
    updated, ambiguity = apply_competing_counts(raw)

    end = swings[-1].candle_index
    group = [candidate for candidate in updated if candidate.end.candle_index == end]
    summary = next(item for item in ambiguity if item.end_candle_index == end)

    assert len(group) > 1
    assert summary.candidate_count == len(group)
    assert summary.valid_impulse_count == sum(item.valid_so_far for item in group)
    assert all(item.competing_valid_count == summary.valid_impulse_count for item in group)


def test_zigzag_compatible_abc_and_equality_projection() -> None:
    points = (
        pivot(PivotKind.HIGH, 0, "120"),
        pivot(PivotKind.LOW, 2, "100"),
        pivot(PivotKind.HIGH, 4, "112"),
        pivot(PivotKind.LOW, 6, "95"),
    )
    candidate = build_abc_candidate(points)

    assert candidate.direction is ElliottDirection.BEARISH
    assert candidate.zigzag_compatible is True
    assert candidate.rule_support_fraction == Decimal(1)
    assert candidate.c_equality_projection.price == Decimal(92)
    assert candidate.c_equality_projection.actual_distance_bps is not None
