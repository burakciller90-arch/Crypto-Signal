from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from decimal import Decimal

from crypto_signal.methodologies.elliott.models import (
    ABCCandidate,
    ElliottAmbiguity,
    ElliottDirection,
    ElliottProjection,
    ElliottRuleEvidence,
    ElliottRuleStatus,
    ImpulseCandidate,
)
from crypto_signal.primitives.models import ConfirmedPivot, PivotKind

TEN_THOUSAND = Decimal(10_000)


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
            raise ValueError("Elliott candidates cannot mix pivot semantics")
        if pivot.candle_index <= previous_index:
            raise ValueError("Elliott pivots must be strictly chronological")
        if previous_kind is pivot.kind:
            raise ValueError("Elliott candidate source must alternate pivot kinds")
        previous_index = pivot.candle_index
        previous_kind = pivot.kind


def _direction(points: Sequence[ConfirmedPivot]) -> ElliottDirection:
    if len(points) < 2:
        raise ValueError("direction requires at least two pivots")
    first, second = points[0], points[1]
    if first.kind is PivotKind.LOW and second.kind is PivotKind.HIGH:
        return ElliottDirection.BULLISH
    if first.kind is PivotKind.HIGH and second.kind is PivotKind.LOW:
        return ElliottDirection.BEARISH
    raise ValueError("Elliott direction requires alternating first pivots")


def _passes_progress(
    direction: ElliottDirection,
    left: Decimal,
    right: Decimal,
) -> bool:
    return (
        right > left
        if direction is ElliottDirection.BULLISH
        else right < left
    )


def _rule(name: str, applicable: bool, passed: bool, description: str) -> ElliottRuleEvidence:
    status = (
        ElliottRuleStatus.NOT_APPLICABLE
        if not applicable
        else ElliottRuleStatus.PASS
        if passed
        else ElliottRuleStatus.FAIL
    )
    return ElliottRuleEvidence(name=name, status=status, description=description)
def _support_fraction(rules: Sequence[ElliottRuleEvidence]) -> Decimal:
    applicable = tuple(
        rule for rule in rules if rule.status is not ElliottRuleStatus.NOT_APPLICABLE
    )
    if not applicable:
        return Decimal(1)
    passed = sum(rule.status is ElliottRuleStatus.PASS for rule in applicable)
    return Decimal(passed) / Decimal(len(applicable))


def _distance_bps(actual: Decimal, projected: Decimal) -> Decimal:
    if actual <= 0:
        raise ValueError("actual price must be positive")
    return abs(actual - projected) / actual * TEN_THOUSAND


def _impulse_rules(
    points: Sequence[ConfirmedPivot],
    direction: ElliottDirection,
) -> tuple[ElliottRuleEvidence, ...]:
    p = [point.price for point in points]
    current_wave = len(points) - 1

    wave2_pass = (
        _passes_progress(direction, p[0], p[2])
        if current_wave >= 2
        else False
    )
    wave3_pass = (
        _passes_progress(direction, p[1], p[3])
        if current_wave >= 3
        else False
    )
    wave4_retrace_pass = (
        _passes_progress(direction, p[2], p[4])
        if current_wave >= 4
        else False
    )
    wave4_overlap_pass = (
        _passes_progress(direction, p[1], p[4])
        if current_wave >= 4
        else False
    )
    wave3_shortest_pass = False
    if current_wave >= 5:
        wave1_length = abs(p[1] - p[0])
        wave3_length = abs(p[3] - p[2])
        wave5_length = abs(p[5] - p[4])
        wave3_shortest_pass = wave3_length >= min(wave1_length, wave5_length)

    return (
        _rule(
            "wave2_not_full_retrace",
            current_wave >= 2,
            wave2_pass,
            "Wave 2 must not retrace 100% of Wave 1.",
        ),
        _rule(
            "wave3_beyond_wave1",
            current_wave >= 3,
            wave3_pass,
            "Wave 3 must move beyond the end of Wave 1.",
        ),
        _rule(
            "wave4_not_full_retrace",
            current_wave >= 4,
            wave4_retrace_pass,
            "Wave 4 must retrace less than 100% of Wave 3.",
        ),
        _rule(
            "wave4_no_overlap_wave1",
            current_wave >= 4,
            wave4_overlap_pass,
            "Standard impulse Wave 4 must not enter Wave 1 price territory.",
        ),
        _rule(
            "wave3_not_shortest",
            current_wave >= 5,
            wave3_shortest_pass,
            "Wave 3 must not be the shortest of Waves 1, 3 and 5.",
        ),
    )
def _wave5_projections(
    points: Sequence[ConfirmedPivot],
    direction: ElliottDirection,
) -> tuple[ElliottProjection, ...]:
    current_wave = len(points) - 1
    if current_wave < 4:
        return ()

    sign = Decimal(1) if direction is ElliottDirection.BULLISH else Decimal(-1)
    wave1_length = abs(points[1].price - points[0].price)
    base = points[4].price
    actual = points[5].price if current_wave >= 5 else None

    output: list[ElliottProjection] = []
    for name, ratio in (
        ("wave5_equals_wave1", Decimal(1)),
        ("wave5_0_618_wave1", Decimal("0.618")),
    ):
        price = base + sign * ratio * wave1_length
        output.append(
            ElliottProjection(
                name=name,
                price=price,
                actual_distance_bps=(
                    None if actual is None else _distance_bps(actual, price)
                ),
            )
        )
    return tuple(output)


def build_impulse_candidate(
    points: Sequence[ConfirmedPivot],
) -> ImpulseCandidate:
    if not 2 <= len(points) <= 6:
        raise ValueError("impulse candidate requires 2 through 6 pivots")

    direction = _direction(points)
    rules = _impulse_rules(points, direction)
    valid_so_far = all(
        rule.status is not ElliottRuleStatus.FAIL for rule in rules
    )
    current_wave = len(points) - 1
    p0 = points[0].price
    invalidation = points[1].price if current_wave == 4 else p0

    truncated: bool | None = None
    if current_wave == 5:
        if direction is ElliottDirection.BULLISH:
            truncated = points[5].price <= points[3].price
        else:
            truncated = points[5].price >= points[3].price

    last = points[-1]
    first = points[0]
    return ImpulseCandidate(
        exchange=first.exchange,
        market_type=first.market_type,
        symbol=first.symbol,
        timeframe=first.timeframe,
        direction=direction,
        points=tuple(points),
        current_wave=current_wave,
        complete=current_wave == 5,
        rules=rules,
        valid_so_far=valid_so_far,
        rule_support_fraction=_support_fraction(rules),
        competing_valid_count=0,
        structural_invalidation_price=invalidation,
        projections=_wave5_projections(points, direction),
        truncated_fifth=truncated,
        market_available_at_ms=last.market_confirmed_at_ms,
        observed_at_ms=last.observed_at_ms,
    )


def enumerate_impulse_candidates(
    swings: Sequence[ConfirmedPivot],
) -> tuple[ImpulseCandidate, ...]:
    _validate_swings(swings)
    output: list[ImpulseCandidate] = []
    for length in range(2, 7):
        for start in range(len(swings) - length + 1):
            output.append(build_impulse_candidate(swings[start : start + length]))
    return tuple(output)
def build_abc_candidate(
    points: Sequence[ConfirmedPivot],
) -> ABCCandidate:
    if len(points) != 4:
        raise ValueError("ABC candidate requires four pivots")

    direction = _direction(points)
    start, a, b, c = points

    b_before_origin = _passes_progress(direction, start.price, b.price)
    c_beyond_a = _passes_progress(direction, a.price, c.price)
    rules = (
        _rule(
            "zigzag_b_before_a_origin",
            True,
            b_before_origin,
            "Zigzag-compatible B must terminate before the start of A.",
        ),
        _rule(
            "zigzag_c_beyond_a",
            True,
            c_beyond_a,
            "Zigzag-compatible C must progress beyond the end of A.",
        ),
    )
    sign = Decimal(1) if direction is ElliottDirection.BULLISH else Decimal(-1)
    projection_price = b.price + sign * abs(a.price - start.price)

    return ABCCandidate(
        exchange=start.exchange,
        market_type=start.market_type,
        symbol=start.symbol,
        timeframe=start.timeframe,
        direction=direction,
        start=start,
        a=a,
        b=b,
        c=c,
        zigzag_rules=rules,
        zigzag_compatible=all(
            rule.status is ElliottRuleStatus.PASS for rule in rules
        ),
        rule_support_fraction=_support_fraction(rules),
        c_equality_projection=ElliottProjection(
            name="c_equals_a",
            price=projection_price,
            actual_distance_bps=_distance_bps(c.price, projection_price),
        ),
        market_available_at_ms=c.market_confirmed_at_ms,
        observed_at_ms=c.observed_at_ms,
    )


def enumerate_abc_candidates(
    swings: Sequence[ConfirmedPivot],
) -> tuple[ABCCandidate, ...]:
    _validate_swings(swings)
    if len(swings) < 4:
        return ()
    return tuple(
        build_abc_candidate(swings[index : index + 4])
        for index in range(len(swings) - 3)
    )
def apply_competing_counts(
    candidates: Sequence[ImpulseCandidate],
) -> tuple[tuple[ImpulseCandidate, ...], tuple[ElliottAmbiguity, ...]]:
    grouped: dict[int, list[ImpulseCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.end.candle_index, []).append(candidate)

    ambiguity: list[ElliottAmbiguity] = []
    updated: list[ImpulseCandidate] = []
    for end_index in sorted(grouped):
        group = grouped[end_index]
        valid_count = sum(candidate.valid_so_far for candidate in group)
        ambiguity.append(
            ElliottAmbiguity(
                end_candle_index=end_index,
                valid_impulse_count=valid_count,
                candidate_count=len(group),
            )
        )
        updated.extend(
            replace(candidate, competing_valid_count=valid_count)
            for candidate in group
        )

    updated.sort(
        key=lambda candidate: (
            candidate.end.candle_index,
            candidate.current_wave,
            candidate.start.candle_index,
        )
    )
    return tuple(updated), tuple(ambiguity)
