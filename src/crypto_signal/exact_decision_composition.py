"""R25 Slice 4: exact composition of accepted evidence into one decision issuance.

This module does not create market evidence. Geometry/chart/candle proof must be
supplied by an accepted upstream adapter. Missing evidence remains missing.
"""
from __future__ import annotations

from decimal import Decimal

from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.forecast_stream import ForecastAuthority, ForecastVersionRef
from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamily,
    ConfluenceFamilyEvidence,
)
from crypto_signal.intelligence.cross_venue_quality import (
    CrossVenueQualityAssessment,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CircuitBreakerAnalysis,
)
from crypto_signal.intelligence.family_proof_adapters import (
    AcceptedFamilyAdapterBundle,
)
from crypto_signal.product.decision_proof import (
    DecisionProofEvidenceSlice,
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
    ProofEvidenceVerdict,
    build_decision_proof_evidence_slice,
)
from crypto_signal.signals.models import SignalDecision
from crypto_signal.unified_decision_runtime import (
    UnifiedDecisionIssuance,
    issue_unified_decision,
)
from research.alpha_factory.probability_calibration_gate import (
    CalibratedProbabilityEvidence,
    CalibrationScope,
)

REAL_CAPITAL = 0
_GEOMETRY_DOMAINS = {
    ProofEvidenceDomain.FROZEN_CHART,
    ProofEvidenceDomain.CONSUMED_CANDLES,
}


def compose_exact_decision(
    *,
    signal: SignalDecision,
    base_asset: str,
    regime: str,
    geometry_family: ConfluenceFamilyEvidence,
    geometry_proof_slices: tuple[DecisionProofEvidenceSlice, ...],
    accepted_m2_m5: AcceptedFamilyAdapterBundle,
    event_context: CircuitBreakerAnalysis,
    issued_at_ms: int,
    horizon_bars: int,
    target_label: str,
    ledger: ImmutableDecisionEvidenceLedger,
    authority: ForecastAuthority = ForecastAuthority.SHADOW,
    calibrated_probability: CalibratedProbabilityEvidence | None = None,
    calibration_scope: CalibrationScope | None = None,
    forecast_version_refs: tuple[ForecastVersionRef, ...] = (),
    forecast_source_evidence_identities: tuple[str, ...] = (),
    cross_venue_quality: CrossVenueQualityAssessment | None = None,
) -> UnifiedDecisionIssuance:
    """Compose exact accepted sources; no surrogate or hidden evidence creation."""
    if geometry_family.family is not ConfluenceFamily.GEOMETRY:
        raise ValueError("exact composition requires GEOMETRY family evidence")
    expected_context = (
        signal.symbol,
        signal.timeframe,
        regime,
        signal.as_of_ms,
    )
    if (
        geometry_family.asset,
        geometry_family.timeframe,
        geometry_family.regime,
        geometry_family.as_of_ms,
    ) != expected_context:
        raise ValueError("geometry family does not match signal exact PIT context")

    geometry_by_domain = {item.domain: item for item in geometry_proof_slices}
    if (
        set(geometry_by_domain) != _GEOMETRY_DOMAINS
        or len(geometry_proof_slices) != len(_GEOMETRY_DOMAINS)
    ):
        raise ValueError(
            "exact composition requires FROZEN_CHART and CONSUMED_CANDLES proof"
        )

    event_slice = _event_context_slice(event_context)
    probability_slice = _probability_slice(
        calibrated_probability=calibrated_probability,
        calibration_scope=calibration_scope,
        signal=signal,
    )

    family_evidence = tuple(
        sorted(
            (geometry_family, *accepted_m2_m5.families),
            key=lambda item: item.family.value,
        )
    )
    preflight = tuple(
        sorted(
            (
                *geometry_proof_slices,
                *accepted_m2_m5.proof_slices,
                event_slice,
                probability_slice,
            ),
            key=lambda item: item.domain.value,
        )
    )

    return issue_unified_decision(
        signal=signal,
        base_asset=base_asset,
        regime=regime,
        family_evidence=family_evidence,
        event_context=event_context,
        preflight_proof_slices=preflight,
        issued_at_ms=issued_at_ms,
        horizon_bars=horizon_bars,
        target_label=target_label,
        ledger=ledger,
        authority=authority,
        calibrated_probability=calibrated_probability,
        calibration_scope=calibration_scope,
        forecast_version_refs=forecast_version_refs,
        forecast_source_evidence_identities=(
            forecast_source_evidence_identities
        ),
        cross_venue_quality=cross_venue_quality,
    )


def _event_context_slice(
    event_context: CircuitBreakerAnalysis,
) -> DecisionProofEvidenceSlice:
    identities = [
        event_context.evidence_identity,
        event_context.event_risk_identity,
        event_context.news_evidence_identity,
    ]
    if event_context.market_quality_identity is not None:
        identities.append(event_context.market_quality_identity)
    summaries = {
        f"circuit_breaker_{event_context.state.value}",
        *event_context.triggers,
    }
    return build_decision_proof_evidence_slice(
        domain=ProofEvidenceDomain.EVENT_CONTEXT,
        availability=ProofEvidenceAvailability.AVAILABLE,
        verdict=ProofEvidenceVerdict.NEUTRAL,
        evidence_identities=tuple(identities),
        market_available_at_ms=event_context.as_of_ms,
        observed_at_ms=event_context.as_of_ms,
        freshness_0_1=Decimal(1),
        source_quality="accepted_versioned_event_context",
        summary_codes=tuple(summaries),
    )


def _probability_slice(
    *,
    calibrated_probability: CalibratedProbabilityEvidence | None,
    calibration_scope: CalibrationScope | None,
    signal: SignalDecision,
) -> DecisionProofEvidenceSlice:
    if calibrated_probability is None:
        if calibration_scope is not None:
            raise ValueError(
                "calibration scope cannot be supplied without calibrated probability"
            )
        return build_decision_proof_evidence_slice(
            domain=ProofEvidenceDomain.PROBABILITY_CALIBRATION,
            availability=ProofEvidenceAvailability.INSUFFICIENT,
            verdict=ProofEvidenceVerdict.INSUFFICIENT,
            summary_codes=("r19_probability_not_calibrated",),
        )

    if calibration_scope is None:
        raise ValueError("calibrated probability requires exact calibration scope")
    if calibrated_probability.scope_identity != calibration_scope.scope_identity:
        raise ValueError("calibrated probability/scope identity mismatch")
    if calibrated_probability.issued_at_ms > signal.as_of_ms:
        raise ValueError("calibrated probability was not available by signal as-of")

    return build_decision_proof_evidence_slice(
        domain=ProofEvidenceDomain.PROBABILITY_CALIBRATION,
        availability=ProofEvidenceAvailability.AVAILABLE,
        verdict=ProofEvidenceVerdict.NEUTRAL,
        evidence_identities=(
            calibrated_probability.authorization_identity,
            calibrated_probability.calibration_evidence_identity,
            calibrated_probability.source_forecast_identity,
            calibrated_probability.source_prediction_identity,
            calibrated_probability.walk_forward_fit_identity,
        ),
        market_available_at_ms=calibrated_probability.issued_at_ms,
        observed_at_ms=calibrated_probability.issued_at_ms,
        # This means the immutable authorization artefact itself is current at
        # issuance; it is not a market-data latency or model-accuracy claim.
        freshness_0_1=Decimal(1),
        source_quality="accepted_r19_probability_authorization",
        summary_codes=("r19_exact_scope_probability_authorized",),
    )
