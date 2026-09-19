from __future__ import annotations

from decimal import Decimal

from crypto_signal.methodologies.harmonic.contracts import (
    PATTERN_SPECS,
    nearest_anchor,
)
from crypto_signal.methodologies.harmonic.models import (
    ConstraintKind,
    HarmonicDirection,
    HarmonicMatch,
    HarmonicPatternKind,
    HarmonicRatios,
    PatternSpec,
    PRZProjection,
    RatioConstraint,
    RatioEvidence,
    XABCDCandidate,
)

TEN_THOUSAND = Decimal(10_000)


def _positive_leg(left: Decimal, right: Decimal, name: str) -> Decimal:
    length = abs(right - left)
    if length <= 0:
        raise ValueError(f"{name} leg must be positive")
    return length


def calculate_ratios(candidate: XABCDCandidate) -> HarmonicRatios:
    xa = _positive_leg(candidate.x.price, candidate.a.price, "XA")
    ab = _positive_leg(candidate.a.price, candidate.b.price, "AB")
    bc = _positive_leg(candidate.b.price, candidate.c.price, "BC")
    cd = _positive_leg(candidate.c.price, candidate.d.price, "CD")
    ad = _positive_leg(candidate.a.price, candidate.d.price, "AD")

    return HarmonicRatios(
        b_xa=ab / xa,
        c_ab=bc / ab,
        d_bc=cd / bc,
        d_xa=ad / xa,
        cd_ab=cd / ab,
    )


def ratio_evidence(
    constraint: RatioConstraint,
    actual: Decimal,
) -> RatioEvidence:
    valid = constraint.minimum <= actual <= constraint.maximum
    if constraint.kind is ConstraintKind.TARGET:
        target = constraint.target
        if target is None:
            raise AssertionError("target constraint lost target")
        residual = abs(actual - target) / target
    elif constraint.kind is ConstraintKind.MINIMUM:
        residual = (
            Decimal(0)
            if actual >= constraint.minimum
            else (constraint.minimum - actual) / constraint.minimum
        )
    elif valid:
        residual = Decimal(0)
    else:
        boundary = (
            constraint.minimum
            if actual < constraint.minimum
            else constraint.maximum
        )
        residual = abs(actual - boundary) / boundary

    return RatioEvidence(
        name=constraint.name,
        actual=actual,
        valid=valid,
        residual=residual,
        minimum=constraint.minimum,
        maximum=constraint.maximum,
        target=constraint.target,
    )


def evaluate_ratio_contract(
    spec: PatternSpec,
    ratios: HarmonicRatios,
) -> tuple[RatioEvidence, ...]:
    pairs = (
        (spec.b_xa, ratios.b_xa),
        (spec.c_ab, ratios.c_ab),
        (spec.d_bc, ratios.d_bc),
        (spec.d_xa, ratios.d_xa),
        (spec.cd_ab, ratios.cd_ab),
    )
    return tuple(ratio_evidence(constraint, actual) for constraint, actual in pairs)


def _completion_sign(direction: HarmonicDirection) -> Decimal:
    return (
        Decimal(-1)
        if direction is HarmonicDirection.BULLISH
        else Decimal(1)
    )


def _distance_bps_from_reference(
    left: Decimal,
    right: Decimal,
    reference: Decimal,
) -> Decimal:
    if reference <= 0:
        raise ValueError("basis-point reference must be positive")
    return (abs(left - right) / reference) * TEN_THOUSAND
def _projection(
    *,
    source: str,
    ratio: Decimal,
    anchor: Decimal,
    leg_length: Decimal,
    sign: Decimal,
    actual_d: Decimal,
) -> PRZProjection:
    price = anchor + sign * ratio * leg_length
    return PRZProjection(
        source=source,
        ratio=ratio,
        price=price,
        actual_d_distance_bps=_distance_bps_from_reference(
            actual_d,
            price,
            actual_d,
        ),
        physical=price > 0,
    )


def build_prz(
    spec: PatternSpec,
    candidate: XABCDCandidate,
    ratios: HarmonicRatios,
) -> tuple[tuple[PRZProjection, ...], Decimal, Decimal, Decimal]:
    xa = _positive_leg(candidate.x.price, candidate.a.price, "XA")
    bc = _positive_leg(candidate.b.price, candidate.c.price, "BC")
    ab = _positive_leg(candidate.a.price, candidate.b.price, "AB")
    sign = _completion_sign(candidate.direction)

    if spec.d_xa.target is None:
        raise ValueError("V1 harmonic D/XA contract requires a target")

    d_bc_anchor = nearest_anchor(spec.d_bc, ratios.d_bc)
    cd_ab_anchor = min(
        spec.cd_ab_projection_anchors,
        key=lambda anchor: (abs(anchor - ratios.cd_ab), anchor),
    )
    projections = (
        _projection(
            source="d_xa",
            ratio=spec.d_xa.target,
            anchor=candidate.a.price,
            leg_length=xa,
            sign=sign,
            actual_d=candidate.d.price,
        ),
        _projection(
            source="d_bc",
            ratio=d_bc_anchor,
            anchor=candidate.c.price,
            leg_length=bc,
            sign=sign,
            actual_d=candidate.d.price,
        ),
        _projection(
            source="cd_ab",
            ratio=cd_ab_anchor,
            anchor=candidate.c.price,
            leg_length=ab,
            sign=sign,
            actual_d=candidate.d.price,
        ),
    )
    prices = tuple(item.price for item in projections)
    low = min(prices)
    high = max(prices)
    width_bps = (
        Decimal(0)
        if low == high
        else _distance_bps_from_reference(low, high, candidate.d.price)
    )
    return projections, low, high, width_bps


def _time_symmetry_error(candidate: XABCDCandidate) -> Decimal:
    ab_bars = candidate.b.candle_index - candidate.a.candle_index
    cd_bars = candidate.d.candle_index - candidate.c.candle_index
    longest = max(ab_bars, cd_bars)
    if longest <= 0:
        raise ValueError("harmonic time legs must be positive")
    return Decimal(abs(ab_bars - cd_bars)) / Decimal(longest)


def _invalidation_price(
    candidate: XABCDCandidate,
    spec: PatternSpec,
) -> Decimal:
    xa = _positive_leg(candidate.x.price, candidate.a.price, "XA")
    price = (
        candidate.a.price
        + _completion_sign(candidate.direction)
        * spec.invalidation_xa_ratio
        * xa
    )
    return price


def _reaction_target(
    candidate: XABCDCandidate,
    fraction: Decimal,
) -> Decimal:
    return candidate.d.price + fraction * (
        candidate.a.price - candidate.d.price
    )


def evaluate_pattern(
    candidate: XABCDCandidate,
    pattern: HarmonicPatternKind,
) -> HarmonicMatch:
    spec = PATTERN_SPECS[pattern]
    ratios = calculate_ratios(candidate)
    evidence = evaluate_ratio_contract(spec, ratios)
    residuals = tuple(item.residual for item in evidence)
    projections, prz_low, prz_high, prz_width_bps = build_prz(
        spec,
        candidate,
        ratios,
    )
    invalidation_price = _invalidation_price(candidate, spec)
    geometry_valid = (
        all(projection.physical for projection in projections)
        and invalidation_price > 0
    )

    return HarmonicMatch(
        pattern=pattern,
        candidate=candidate,
        ratios=ratios,
        ratio_evidence=evidence,
        geometry_valid=geometry_valid,
        valid=all(item.valid for item in evidence) and geometry_valid,
        mean_ratio_residual=sum(residuals, Decimal(0)) / Decimal(len(residuals)),
        max_ratio_residual=max(residuals),
        prz_low=prz_low,
        prz_high=prz_high,
        prz_width_bps=prz_width_bps,
        projections=projections,
        fib_clustering_width_bps=prz_width_bps,
        ab_cd_time_symmetry_error=_time_symmetry_error(candidate),
        invalidation_price=invalidation_price,
        target_1_price=_reaction_target(candidate, Decimal("0.382")),
        target_2_price=_reaction_target(candidate, Decimal("0.618")),
    )


def evaluate_all_patterns(
    candidate: XABCDCandidate,
) -> tuple[HarmonicMatch, ...]:
    return tuple(evaluate_pattern(candidate, pattern) for pattern in HarmonicPatternKind)
