from __future__ import annotations

from collections.abc import Sequence

from crypto_signal.confluence.models import (
    EvidenceDirection,
    MethodologyEvidence,
    MethodologyKind,
    MethodologySelection,
)

METHOD_ORDER = (
    MethodologyKind.PRICE_ACTION,
    MethodologyKind.HARMONIC,
    MethodologyKind.ELLIOTT,
)


def select_latest_for_methodology(
    evidence: Sequence[MethodologyEvidence],
    methodology: MethodologyKind,
) -> MethodologySelection:
    source = tuple(
        item for item in evidence if item.methodology is methodology
    )
    if not source:
        return MethodologySelection(
            methodology=methodology,
            source_count=0,
            selected=(),
            latest_market_available_at_ms=None,
            resolved_direction=EvidenceDirection.UNRESOLVED,
            has_internal_direction_conflict=False,
        )

    latest = max(item.market_available_at_ms for item in source)
    selected = tuple(
        sorted(
            (
                item
                for item in source
                if item.market_available_at_ms == latest
            ),
            key=lambda item: item.evidence_id,
        )
    )
    directions = {
        item.direction
        for item in selected
        if item.direction
        in {EvidenceDirection.BULLISH, EvidenceDirection.BEARISH}
    }
    conflict = len(directions) > 1
    resolved = (
        next(iter(directions))
        if len(directions) == 1
        else EvidenceDirection.UNRESOLVED
    )

    return MethodologySelection(
        methodology=methodology,
        source_count=len(source),
        selected=selected,
        latest_market_available_at_ms=latest,
        resolved_direction=resolved,
        has_internal_direction_conflict=conflict,
    )


def build_methodology_selections(
    evidence: Sequence[MethodologyEvidence],
) -> tuple[MethodologySelection, ...]:
    return tuple(
        select_latest_for_methodology(evidence, methodology)
        for methodology in METHOD_ORDER
    )
