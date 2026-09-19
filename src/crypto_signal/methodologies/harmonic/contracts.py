from __future__ import annotations

from decimal import Decimal

from crypto_signal.methodologies.harmonic.models import (
    ConstraintKind,
    HarmonicPatternKind,
    PatternSpec,
    RatioConstraint,
)

TARGET_TOLERANCE = Decimal("0.03")
HARMONIC_ANCHORS = (
    Decimal("1.0"),
    Decimal("1.13"),
    Decimal("1.27"),
    Decimal("1.414"),
    Decimal("1.618"),
    Decimal("2.0"),
    Decimal("2.24"),
    Decimal("2.618"),
    Decimal("3.14"),
    Decimal("3.618"),
)


def target(name: str, value: str, tolerance: Decimal = TARGET_TOLERANCE) -> RatioConstraint:
    center = Decimal(value)
    delta = center * tolerance
    return RatioConstraint(
        name=name,
        kind=ConstraintKind.TARGET,
        minimum=center - delta,
        maximum=center + delta,
        target=center,
        relative_tolerance=tolerance,
    )


def band(name: str, minimum: str, maximum: str) -> RatioConstraint:
    return RatioConstraint(
        name=name,
        kind=ConstraintKind.RANGE,
        minimum=Decimal(minimum),
        maximum=Decimal(maximum),
    )


def minimum(name: str, value: str) -> RatioConstraint:
    return RatioConstraint(
        name=name,
        kind=ConstraintKind.MINIMUM,
        minimum=Decimal(value),
        maximum=Decimal("Infinity"),
    )


COMMON_C_AB = band("c_ab", "0.382", "0.886")

PATTERN_SPECS: dict[HarmonicPatternKind, PatternSpec] = {
    HarmonicPatternKind.GARTLEY: PatternSpec(
        kind=HarmonicPatternKind.GARTLEY,
        b_xa=target("b_xa", "0.618"),
        c_ab=COMMON_C_AB,
        d_bc=band("d_bc", "1.13", "1.618"),
        d_xa=target("d_xa", "0.786"),
        cd_ab=band("cd_ab", "1.0", "1.27"),
        cd_ab_projection_anchors=(Decimal("1.0"), Decimal("1.27")),
        invalidation_xa_ratio=Decimal("1.0"),
    ),
    HarmonicPatternKind.BAT: PatternSpec(
        kind=HarmonicPatternKind.BAT,
        b_xa=band("b_xa", "0.382", "0.50"),
        c_ab=COMMON_C_AB,
        d_bc=band("d_bc", "1.618", "2.618"),
        d_xa=target("d_xa", "0.886"),
        cd_ab=band("cd_ab", "1.0", "1.27"),
        cd_ab_projection_anchors=(Decimal("1.0"), Decimal("1.27")),
        invalidation_xa_ratio=Decimal("1.13"),
    ),
    HarmonicPatternKind.BUTTERFLY: PatternSpec(
        kind=HarmonicPatternKind.BUTTERFLY,
        b_xa=target("b_xa", "0.786"),
        c_ab=COMMON_C_AB,
        d_bc=band("d_bc", "1.618", "2.618"),
        d_xa=target("d_xa", "1.27"),
        cd_ab=band("cd_ab", "1.0", "1.27"),
        cd_ab_projection_anchors=(Decimal("1.0"), Decimal("1.27")),
        invalidation_xa_ratio=Decimal("1.414"),
    ),
    HarmonicPatternKind.CRAB: PatternSpec(
        kind=HarmonicPatternKind.CRAB,
        b_xa=band("b_xa", "0.382", "0.618"),
        c_ab=COMMON_C_AB,
        d_bc=band("d_bc", "2.618", "3.618"),
        d_xa=target("d_xa", "1.618"),
        cd_ab=minimum("cd_ab", "1.0"),
        cd_ab_projection_anchors=(
            Decimal("1.0"),
            Decimal("1.27"),
            Decimal("1.618"),
        ),
        invalidation_xa_ratio=Decimal("2.0"),
    ),
    HarmonicPatternKind.DEEP_CRAB: PatternSpec(
        kind=HarmonicPatternKind.DEEP_CRAB,
        b_xa=target("b_xa", "0.886", Decimal("0.05")),
        c_ab=COMMON_C_AB,
        d_bc=band("d_bc", "2.0", "3.618"),
        d_xa=target("d_xa", "1.618"),
        cd_ab=minimum("cd_ab", "1.0"),
        cd_ab_projection_anchors=(
            Decimal("1.0"),
            Decimal("1.27"),
            Decimal("1.618"),
        ),
        invalidation_xa_ratio=Decimal("2.0"),
    ),
}


def nearest_anchor(constraint: RatioConstraint, actual: Decimal) -> Decimal:
    candidates = tuple(
        anchor
        for anchor in HARMONIC_ANCHORS
        if constraint.minimum <= anchor <= constraint.maximum
    )
    if not candidates:
        if constraint.target is not None:
            return constraint.target
        midpoint = (constraint.minimum + constraint.maximum) / Decimal(2)
        return midpoint
    return min(candidates, key=lambda anchor: (abs(anchor - actual), anchor))
