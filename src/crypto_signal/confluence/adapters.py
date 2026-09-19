from __future__ import annotations

from collections import Counter
from dataclasses import replace
from decimal import Decimal

from crypto_signal.confluence.models import (
    EvidenceDirection,
    EvidenceMetric,
    EvidenceValidity,
    MethodologyEvidence,
    MethodologyKind,
    NamedPrice,
    PriceZone,
)
from crypto_signal.methodologies.elliott.models import (
    ElliottAnalysisResult,
    ElliottDirection,
    ImpulseCandidate,
)
from crypto_signal.methodologies.harmonic.models import (
    HarmonicAnalysisResult,
    HarmonicDirection,
    HarmonicMatch,
)
from crypto_signal.methodologies.price_action.analysis import PriceActionAnalysisResult
from crypto_signal.methodologies.price_action.models import StructureDirection


def _pa_direction(value: StructureDirection) -> EvidenceDirection:
    if value is StructureDirection.BULLISH:
        return EvidenceDirection.BULLISH
    if value is StructureDirection.BEARISH:
        return EvidenceDirection.BEARISH
    return EvidenceDirection.UNRESOLVED


def _harmonic_direction(value: HarmonicDirection) -> EvidenceDirection:
    if value is HarmonicDirection.BULLISH:
        return EvidenceDirection.BULLISH
    return EvidenceDirection.BEARISH


def _elliott_direction(value: ElliottDirection) -> EvidenceDirection:
    if value is ElliottDirection.BULLISH:
        return EvidenceDirection.BULLISH
    return EvidenceDirection.BEARISH


def price_action_structure_evidence(
    result: PriceActionAnalysisResult,
) -> MethodologyEvidence | None:
    direction = _pa_direction(result.structure.current_direction)
    if direction is EvidenceDirection.UNRESOLVED:
        return None

    latest_break = next(
        (
            event
            for event in reversed(result.structure.structure_breaks)
            if _pa_direction(event.direction) is direction
        ),
        None,
    )
    if latest_break is None:
        raise ValueError("resolved PA direction has no matching structure break")

    return MethodologyEvidence(
        methodology=MethodologyKind.PRICE_ACTION,
        exchange=result.exchange,
        market_type=result.market_type,
        symbol=result.symbol,
        timeframe=result.timeframe,
        as_of_ms=result.as_of_ms,
        methodology_version=result.methodology_version,
        evidence_id=(
            f"pa:{result.timeframe}:{latest_break.kind.value}:"
            f"{latest_break.break_candle_identity[-1]}"
        ),
        setup_type="market_structure",
        direction=direction,
        validity=EvidenceValidity.CONTEXT,
        market_available_at_ms=latest_break.market_confirmed_at_ms,
        observed_at_ms=latest_break.observed_at_ms,
        entry_zone=None,
        invalidation_price=None,
        targets=(),
        key_levels=(
            NamedPrice("broken_structure_level", latest_break.level_price),
            NamedPrice("break_close", latest_break.break_close),
        ),
        metrics=(
            EvidenceMetric(
                "break_distance_bps",
                latest_break.distance_bps,
                "bps",
            ),
        ),
        ambiguity_flags=(
            ("ambiguous_swing_source",)
            if result.structure.ambiguous_swing_source_indices
            else ()
        ),
        contradiction_flags=(),
        evidence_summary=(
            f"current_structure={result.structure.current_direction.value}",
            f"latest_break={latest_break.kind.value}",
        ),
    )


def harmonic_match_evidence(
    match: HarmonicMatch,
    *,
    as_of_ms: int,
    methodology_version: str,
) -> MethodologyEvidence:
    if not match.valid:
        raise ValueError("only valid Harmonic matches may become confluence evidence")
    if as_of_ms < match.candidate.observed_at_ms:
        raise ValueError("Harmonic evidence cannot be observed after as_of")

    candidate = match.candidate
    return MethodologyEvidence(
        methodology=MethodologyKind.HARMONIC,
        exchange=candidate.exchange,
        market_type=candidate.market_type,
        symbol=candidate.symbol,
        timeframe=candidate.timeframe,
        as_of_ms=as_of_ms,
        methodology_version=methodology_version,
        evidence_id=(
            f"harmonic:{match.pattern.value}:"
            + ":".join(str(pivot.open_time_ms) for pivot in candidate.pivots)
        ),
        setup_type=match.pattern.value,
        direction=_harmonic_direction(candidate.direction),
        validity=EvidenceValidity.VALID,
        market_available_at_ms=candidate.market_available_at_ms,
        observed_at_ms=candidate.observed_at_ms,
        entry_zone=PriceZone(match.prz_low, match.prz_high),
        invalidation_price=match.invalidation_price,
        targets=(
            NamedPrice("target_1", match.target_1_price),
            NamedPrice("target_2", match.target_2_price),
        ),
        key_levels=tuple(
            NamedPrice(label, pivot.price)
            for label, pivot in zip(
                ("x", "a", "b", "c", "d"),
                candidate.pivots,
                strict=True,
            )
        ),
        metrics=(
            EvidenceMetric(
                "mean_ratio_residual",
                match.mean_ratio_residual,
                "ratio",
            ),
            EvidenceMetric(
                "max_ratio_residual",
                match.max_ratio_residual,
                "ratio",
            ),
            EvidenceMetric("prz_width_bps", match.prz_width_bps, "bps"),
            EvidenceMetric(
                "fib_clustering_width_bps",
                match.fib_clustering_width_bps,
                "bps",
            ),
            EvidenceMetric(
                "ab_cd_time_symmetry_error",
                match.ab_cd_time_symmetry_error,
                "ratio",
            ),
        ),
        ambiguity_flags=(),
        contradiction_flags=(),
        evidence_summary=(
            f"pattern={match.pattern.value}",
            "ratio_contract=valid",
            "geometry=valid",
        ),
    )


def harmonic_result_evidence(
    result: HarmonicAnalysisResult,
) -> tuple[MethodologyEvidence, ...]:
    counts = Counter(match.candidate.identity for match in result.valid_matches)
    items = []
    for match in result.valid_matches:
        evidence = harmonic_match_evidence(
            match,
            as_of_ms=result.as_of_ms,
            methodology_version=result.methodology_version,
        )
        if counts[match.candidate.identity] > 1:
            evidence = replace(
                evidence,
                ambiguity_flags=("multiple_valid_patterns_same_xabcd",),
            )
        items.append(evidence)
    return tuple(items)


def elliott_impulse_evidence(
    candidate: ImpulseCandidate,
    *,
    as_of_ms: int,
    methodology_version: str,
) -> MethodologyEvidence:
    if not candidate.valid_so_far:
        raise ValueError("invalid Elliott counts cannot become confluence evidence")
    if as_of_ms < candidate.observed_at_ms:
        raise ValueError("Elliott evidence cannot be observed after as_of")

    ambiguity = (
        ("competing_valid_impulse_counts",)
        if candidate.competing_valid_count > 1
        else ()
    )
    summary = [f"current_wave={candidate.current_wave}"]
    if candidate.truncated_fifth is True:
        summary.append("truncated_fifth=true")
    elif candidate.truncated_fifth is False:
        summary.append("truncated_fifth=false")
    return MethodologyEvidence(
        methodology=MethodologyKind.ELLIOTT,
        exchange=candidate.exchange,
        market_type=candidate.market_type,
        symbol=candidate.symbol,
        timeframe=candidate.timeframe,
        as_of_ms=as_of_ms,
        methodology_version=methodology_version,
        evidence_id=(
            f"elliott:impulse:{candidate.current_wave}:"
            + ":".join(str(point.open_time_ms) for point in candidate.points)
        ),
        setup_type=f"impulse_wave_{candidate.current_wave}",
        direction=_elliott_direction(candidate.direction),
        validity=(
            EvidenceValidity.VALID
            if candidate.complete
            else EvidenceValidity.VALID_SO_FAR
        ),
        market_available_at_ms=candidate.market_available_at_ms,
        observed_at_ms=candidate.observed_at_ms,
        entry_zone=None,
        invalidation_price=candidate.structural_invalidation_price,
        targets=tuple(
            NamedPrice(projection.name, projection.price)
            for projection in candidate.projections
            if projection.price > 0
        ),
        key_levels=tuple(
            NamedPrice(f"wave_{index}", point.price)
            for index, point in enumerate(candidate.points)
        ),
        metrics=(
            EvidenceMetric(
                "rule_support_fraction",
                candidate.rule_support_fraction,
                "fraction",
            ),
            EvidenceMetric(
                "competing_valid_count",
                Decimal(candidate.competing_valid_count),
                "count",
            ),
        ),
        ambiguity_flags=ambiguity,
        contradiction_flags=(),
        evidence_summary=tuple(summary),
    )


def elliott_result_evidence(
    result: ElliottAnalysisResult,
) -> tuple[MethodologyEvidence, ...]:
    return tuple(
        elliott_impulse_evidence(
            candidate,
            as_of_ms=result.as_of_ms,
            methodology_version=result.methodology_version,
        )
        for candidate in result.impulse_candidates
        if candidate.valid_so_far
    )
