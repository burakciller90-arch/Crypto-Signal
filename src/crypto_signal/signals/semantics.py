from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from crypto_signal.confluence.models import (
    ConfluenceAnalysisResult,
    EvidenceDirection,
    MethodologyEvidence,
    MethodologyKind,
)
from crypto_signal.signals.models import (
    EntryReferenceModel,
    HistoricalStatsStatus,
    MethodologyVersionRef,
    ProbabilityStatus,
    RiskRewardTarget,
    SignalAgreementSummary,
    SignalDecision,
    SignalDirection,
    SignalGeometry,
    SignalState,
)

SIGNAL_VERSION = "signal-v1/1"


def _signal_direction(direction: EvidenceDirection) -> SignalDirection:
    if direction is EvidenceDirection.BULLISH:
        return SignalDirection.BULLISH
    if direction is EvidenceDirection.BEARISH:
        return SignalDirection.BEARISH
    return SignalDirection.NONE


def _selected_evidence(
    confluence: ConfluenceAnalysisResult,
) -> tuple[MethodologyEvidence, ...]:
    return tuple(
        item
        for selection in confluence.selections
        for item in selection.selected
    )


def _is_complete_geometry(item: MethodologyEvidence) -> bool:
    return (
        item.entry_zone is not None
        and item.invalidation_price is not None
        and item.invalidation_trigger is not None
        and bool(item.targets)
    )


def _build_geometry(
    item: MethodologyEvidence,
    direction: SignalDirection,
) -> SignalGeometry:
    if not _is_complete_geometry(item):
        raise ValueError("signal geometry source is incomplete")
    if item.entry_zone is None:
        raise AssertionError("complete geometry lost entry zone")
    if item.invalidation_price is None:
        raise AssertionError("complete geometry lost invalidation price")
    if item.invalidation_trigger is None:
        raise AssertionError("complete geometry lost invalidation trigger")

    entry = (item.entry_zone.low + item.entry_zone.high) / Decimal(2)
    if direction is SignalDirection.BULLISH:
        risk = entry - item.invalidation_price
    elif direction is SignalDirection.BEARISH:
        risk = item.invalidation_price - entry
    else:
        raise ValueError("signal geometry requires directional signal")
    if risk <= 0:
        raise ValueError("signal geometry has non-positive reference risk")

    rr_targets: list[RiskRewardTarget] = []
    for target in item.targets:
        reward = (
            target.price - entry
            if direction is SignalDirection.BULLISH
            else entry - target.price
        )
        if reward <= 0:
            raise ValueError(
                f"signal target {target.label} has non-positive reward"
            )
        rr_targets.append(
            RiskRewardTarget(
                label=target.label,
                target_price=target.price,
                reference_rr=reward / risk,
            )
        )

    return SignalGeometry(
        source_evidence_id=item.evidence_id,
        source_methodology=item.methodology,
        entry_zone=item.entry_zone,
        entry_reference_price=entry,
        entry_reference_model=(
            EntryReferenceModel.ZONE_MIDPOINT_REFERENCE_NOT_EXECUTION
        ),
        invalidation_price=item.invalidation_price,
        invalidation_trigger=item.invalidation_trigger,
        targets=tuple(rr_targets),
    )


def _agreement_summary(
    confluence: ConfluenceAnalysisResult,
) -> SignalAgreementSummary:
    score = confluence.score
    return SignalAgreementSummary(
        confluence_score=score.value,
        score_semantic=score.semantic,
        support_method_count=score.support_method_count,
        opposing_method_count=score.opposing_method_count,
        resolved_method_count=score.resolved_method_count,
        total_methodology_slots=score.total_methodology_slots,
        pairwise_relations=confluence.pairwise_relations,
    )


def _methodology_versions(
    selected: tuple[MethodologyEvidence, ...],
) -> tuple[MethodologyVersionRef, ...]:
    versions: dict[MethodologyKind, str] = {}
    for item in selected:
        existing = versions.get(item.methodology)
        if existing is not None and existing != item.methodology_version:
            raise ValueError(
                "selected evidence mixes methodology versions at one as-of"
            )
        versions[item.methodology] = item.methodology_version
    return tuple(
        MethodologyVersionRef(methodology=methodology, version=version)
        for methodology, version in sorted(
            versions.items(),
            key=lambda pair: pair[0].value,
        )
    )


def _canonical_geometry(geometry: SignalGeometry | None) -> object:
    if geometry is None:
        return None
    return {
        "source_evidence_id": geometry.source_evidence_id,
        "source_methodology": geometry.source_methodology.value,
        "entry_zone": {
            "low": str(geometry.entry_zone.low),
            "high": str(geometry.entry_zone.high),
        },
        "entry_reference_price": str(geometry.entry_reference_price),
        "entry_reference_model": geometry.entry_reference_model.value,
        "invalidation_price": str(geometry.invalidation_price),
        "invalidation_trigger": geometry.invalidation_trigger.value,
        "targets": [
            {
                "label": target.label,
                "target_price": str(target.target_price),
                "reference_rr": str(target.reference_rr),
            }
            for target in geometry.targets
        ],
    }


def _freeze_identity(
    *,
    confluence: ConfluenceAnalysisResult,
    state: SignalState,
    direction: SignalDirection,
    setup_type: str,
    geometry: SignalGeometry | None,
    evidence_ids: tuple[str, ...],
    versions: tuple[MethodologyVersionRef, ...],
    flags: tuple[str, ...],
) -> str:
    payload = {
        "signal_version": SIGNAL_VERSION,
        "exchange": confluence.exchange.value,
        "market_type": confluence.market_type.value,
        "symbol": confluence.symbol,
        "timeframe": confluence.timeframe,
        "as_of_ms": confluence.as_of_ms,
        "state": state.value,
        "direction": direction.value,
        "setup_type": setup_type,
        "geometry": _canonical_geometry(geometry),
        "selected_evidence_ids": list(evidence_ids),
        "methodology_versions": [
            {
                "methodology": item.methodology.value,
                "version": item.version,
            }
            for item in versions
        ],
        "confluence": {
            "score": str(confluence.score.value),
            "semantic": confluence.score.semantic.value,
            "support": confluence.score.support_method_count,
            "opposition": confluence.score.opposing_method_count,
            "resolved": confluence.score.resolved_method_count,
            "slots": confluence.score.total_methodology_slots,
        },
        "uncertainty_flags": list(flags),
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def build_signal_decision(
    confluence: ConfluenceAnalysisResult,
) -> SignalDecision:
    selected = _selected_evidence(confluence)
    directional_selected = any(
        item.direction
        in {EvidenceDirection.BULLISH, EvidenceDirection.BEARISH}
        for item in selected
    )
    dominant = confluence.dominant_direction
    direction = _signal_direction(dominant)
    flags = list(confluence.flags)

    geometry: SignalGeometry | None = None
    setup_type: str

    if direction is SignalDirection.NONE:
        state = (
            SignalState.NEUTRAL
            if directional_selected
            else SignalState.NO_SIGNAL
        )
        setup_type = state.value
    else:
        geometry_candidates = tuple(
            item
            for item in selected
            if item.direction is dominant and _is_complete_geometry(item)
        )
        if len(geometry_candidates) == 1:
            geometry = _build_geometry(
                geometry_candidates[0],
                direction,
            )
            setup_type = geometry_candidates[0].setup_type
        else:
            setup_type = "confluence_watch"
            if not geometry_candidates:
                flags.append("no_complete_geometry")
            else:
                flags.append("multiple_complete_geometry_candidates")

        if confluence.score.support_method_count < 2:
            flags.append("insufficient_independent_support")
        if confluence.score.opposing_method_count > 0:
            flags.append("opposing_methodology_vote")

        active = (
            confluence.score.support_method_count >= 2
            and confluence.score.opposing_method_count == 0
            and geometry is not None
        )
        state = SignalState.ACTIVE if active else SignalState.WATCH

    evidence_ids = tuple(
        sorted(item.evidence_id for item in selected)
    )
    versions = _methodology_versions(selected)
    uncertainty_flags = tuple(dict.fromkeys(flags))
    evidence_summary = tuple(
        f"{item.methodology.value}:{item.setup_type}:"
        f"{item.direction.value}:{item.validity.value}"
        for item in sorted(selected, key=lambda value: value.evidence_id)
    )
    agreement = _agreement_summary(confluence)

    freeze_identity = _freeze_identity(
        confluence=confluence,
        state=state,
        direction=direction,
        setup_type=setup_type,
        geometry=geometry,
        evidence_ids=evidence_ids,
        versions=versions,
        flags=uncertainty_flags,
    )

    return SignalDecision(
        freeze_identity=freeze_identity,
        signal_version=SIGNAL_VERSION,
        state=state,
        exchange=confluence.exchange,
        market_type=confluence.market_type,
        symbol=confluence.symbol,
        timeframe=confluence.timeframe,
        as_of_ms=confluence.as_of_ms,
        direction=direction,
        setup_type=setup_type,
        geometry=geometry,
        agreement=agreement,
        selected_evidence_ids=evidence_ids,
        methodology_versions=versions,
        probability_status=ProbabilityStatus.NOT_CALIBRATED,
        historical_stats_status=HistoricalStatsStatus.NOT_EVALUATED,
        uncertainty_flags=uncertainty_flags,
        evidence_summary=evidence_summary,
    )
