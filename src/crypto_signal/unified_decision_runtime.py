from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from crypto_signal.decision_ledger import (
    DecisionLedgerWriteDisposition,
    ImmutableDecisionEvidenceLedger,
)
from crypto_signal.forecast_stream import (
    ForecastAuthority,
    ForecastVersionRef,
    ImmutableForecast,
    build_immutable_forecast,
)
from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamily,
    ConfluenceFamilyEvidence,
    ConfluenceMatrixPolicy,
    ConfluenceMatrixResolution,
    ConfluenceMatrixSnapshot,
    build_locked_m6_policy,
    evaluate_confluence_matrix,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import CircuitBreakerAnalysis
from crypto_signal.intelligence.evidence_overlap import (
    analyze_confluence_evidence_overlap,
)
from crypto_signal.intelligence.meta_intelligence import MetaDirection
from crypto_signal.product.decision_proof import (
    DecisionProofEvidenceSlice,
    DecisionProofSnapshot,
    LiveIntelligenceFeedEvent,
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
    ProofEvidenceVerdict,
    build_decision_proof_evidence_slice,
    build_decision_proof_snapshot,
    build_live_intelligence_feed_event,
)
from crypto_signal.signals.models import SignalDecision, SignalDirection

if TYPE_CHECKING:
    from research.alpha_factory.probability_calibration_gate import (
        CalibratedProbabilityEvidence,
        CalibrationScope,
    )

REAL_CAPITAL = 0

PREFLIGHT_PROOF_DOMAINS = tuple(
    domain
    for domain in ProofEvidenceDomain
    if domain is not ProofEvidenceDomain.METHODOLOGY
)

FAMILY_PROOF_DOMAINS: dict[ConfluenceFamily, tuple[ProofEvidenceDomain, ...]] = {
    ConfluenceFamily.GEOMETRY: (
        ProofEvidenceDomain.FROZEN_CHART,
        ProofEvidenceDomain.CONSUMED_CANDLES,
    ),
    ConfluenceFamily.LIQUIDITY: (
        ProofEvidenceDomain.ORDER_BOOK,
        ProofEvidenceDomain.LIQUIDITY_MAP,
        ProofEvidenceDomain.LIQUIDATION_MAP,
    ),
    ConfluenceFamily.ORDER_FLOW: (
        ProofEvidenceDomain.ORDER_BOOK,
        ProofEvidenceDomain.ORDER_FLOW_CVD,
    ),
    ConfluenceFamily.DERIVATIVES: (ProofEvidenceDomain.DERIVATIVES,),
    ConfluenceFamily.ONCHAIN: (ProofEvidenceDomain.ONCHAIN,),
}


@dataclass(frozen=True, slots=True)
class UnifiedDecisionIssuance:
    confluence: ConfluenceMatrixSnapshot
    forecast: ImmutableForecast
    proof: DecisionProofSnapshot
    feed_event: LiveIntelligenceFeedEvent
    ledger_disposition: DecisionLedgerWriteDisposition
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.forecast.confluence_identity != self.confluence.snapshot_identity:
            raise ValueError("unified runtime forecast/confluence lineage mismatch")
        if self.proof.forecast_identity != self.forecast.forecast_identity:
            raise ValueError("unified runtime proof/forecast lineage mismatch")
        if self.feed_event.forecast_identity != self.forecast.forecast_identity:
            raise ValueError("unified runtime feed/forecast lineage mismatch")
        if self.feed_event.proof_identity != self.proof.proof_identity:
            raise ValueError("unified runtime feed/proof lineage mismatch")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("unified runtime has no production or real-capital authority")


def issue_unified_decision(
    *,
    signal: SignalDecision,
    base_asset: str,
    regime: str,
    family_evidence: tuple[ConfluenceFamilyEvidence, ...],
    event_context: CircuitBreakerAnalysis,
    preflight_proof_slices: tuple[DecisionProofEvidenceSlice, ...],
    issued_at_ms: int,
    horizon_bars: int,
    target_label: str,
    ledger: ImmutableDecisionEvidenceLedger,
    authority: ForecastAuthority = ForecastAuthority.SHADOW,
    m6_policy: ConfluenceMatrixPolicy | None = None,
    calibrated_probability: CalibratedProbabilityEvidence | None = None,
    calibration_scope: CalibrationScope | None = None,
    forecast_version_refs: tuple[ForecastVersionRef, ...] = (),
    forecast_source_evidence_identities: tuple[str, ...] = (),
) -> UnifiedDecisionIssuance:
    """Compose one exact-PIT shadow/research decision and persist it atomically.

    Upstream engines remain responsible for producing accepted evidence freezes.
    This runtime joins their already-versioned evidence into M6, Event Risk, R20
    and R20.5 without inventing missing measurements or granting order authority.
    """
    _validate_market_identity(
        signal=signal,
        base_asset=base_asset,
        regime=regime,
        family_evidence=family_evidence,
        event_context=event_context,
    )
    _validate_preflight_slices(
        signal=signal,
        event_context=event_context,
        calibrated_probability=calibrated_probability,
        slices=preflight_proof_slices,
    )
    _validate_family_proof_coverage(
        family_evidence=family_evidence,
        slices=preflight_proof_slices,
    )

    direction = _meta_direction(signal.direction)
    policy = m6_policy or build_locked_m6_policy()
    overlap_analysis = analyze_confluence_evidence_overlap(family_evidence)
    overlap_lineage = overlap_analysis.lineage_identities
    decision_lineage = tuple(
        sorted(
            {
                *forecast_source_evidence_identities,
                *overlap_lineage,
            }
        )
    )
    confluence = evaluate_confluence_matrix(
        policy,
        family_evidence,
        candidate_direction=direction,
    )
    if confluence.regime != regime:
        raise ValueError("unified runtime M6 regime mismatch")

    forecast = build_immutable_forecast(
        signal,
        confluence,
        event_context,
        asset=base_asset,
        issued_at_ms=issued_at_ms,
        horizon_bars=horizon_bars,
        target_label=target_label,
        authority=authority,
        calibrated_probability=calibrated_probability,
        calibration_scope=calibration_scope,
        extra_version_refs=forecast_version_refs,
        extra_source_evidence_identities=decision_lineage,
    )

    methodology = _methodology_slice(
        signal,
        confluence,
        extra_lineage_identities=decision_lineage,
    )
    proof = build_decision_proof_snapshot(
        forecast,
        (*preflight_proof_slices, methodology),
    )
    feed_event = build_live_intelligence_feed_event(proof, forecast)
    disposition = ledger.append_issuance_bundle(forecast, proof, feed_event)
    return UnifiedDecisionIssuance(
        confluence=confluence,
        forecast=forecast,
        proof=proof,
        feed_event=feed_event,
        ledger_disposition=disposition,
    )


def _validate_market_identity(
    *,
    signal: SignalDecision,
    base_asset: str,
    regime: str,
    family_evidence: tuple[ConfluenceFamilyEvidence, ...],
    event_context: CircuitBreakerAnalysis,
) -> None:
    if not base_asset or base_asset != base_asset.upper():
        raise ValueError("unified runtime base asset must be uppercase")
    if not regime.strip():
        raise ValueError("unified runtime regime must be non-empty")
    if not signal.symbol.startswith(base_asset):
        raise ValueError("unified runtime signal/base asset mismatch")
    if event_context.asset != base_asset:
        raise ValueError("unified runtime event/base asset mismatch")
    if event_context.as_of_ms != signal.as_of_ms:
        raise ValueError("unified runtime event/signal as-of mismatch")
    if len(family_evidence) != len(ConfluenceFamily):
        raise ValueError("unified runtime requires exactly five M6 families")
    by_family = {item.family: item for item in family_evidence}
    if len(by_family) != len(ConfluenceFamily) or set(by_family) != set(
        ConfluenceFamily
    ):
        raise ValueError("unified runtime requires one evidence item per M6 family")
    expected = (signal.symbol, signal.timeframe, regime, signal.as_of_ms)
    for item in family_evidence:
        actual = (item.asset, item.timeframe, item.regime, item.as_of_ms)
        if actual != expected:
            raise ValueError("unified runtime family evidence context mismatch")


def _validate_preflight_slices(
    *,
    signal: SignalDecision,
    event_context: CircuitBreakerAnalysis,
    calibrated_probability: CalibratedProbabilityEvidence | None,
    slices: tuple[DecisionProofEvidenceSlice, ...],
) -> None:
    by_domain = {item.domain: item for item in slices}
    if len(by_domain) != len(PREFLIGHT_PROOF_DOMAINS) or set(by_domain) != set(
        PREFLIGHT_PROOF_DOMAINS
    ):
        raise ValueError(
            "unified runtime requires exactly one preflight proof slice per non-methodology domain"
        )

    for item in slices:
        if (
            item.availability is ProofEvidenceAvailability.AVAILABLE
            and item.observed_at_ms is not None
            and item.observed_at_ms > signal.as_of_ms
        ):
            raise ValueError(
                "unified runtime preflight proof cannot observe future evidence"
            )

    event_slice = by_domain[ProofEvidenceDomain.EVENT_CONTEXT]
    if (
        event_slice.availability is not ProofEvidenceAvailability.AVAILABLE
        or event_context.evidence_identity not in event_slice.evidence_identities
    ):
        raise ValueError(
            "unified runtime Event Risk proof must bind exact event context identity"
        )

    probability_slice = by_domain[ProofEvidenceDomain.PROBABILITY_CALIBRATION]
    if calibrated_probability is None:
        if probability_slice.availability is ProofEvidenceAvailability.AVAILABLE:
            raise ValueError(
                "uncalibrated unified runtime cannot expose probability evidence"
            )
    else:
        required_probability_ids = {
            calibrated_probability.authorization_identity,
            calibrated_probability.calibration_evidence_identity,
            calibrated_probability.source_forecast_identity,
            calibrated_probability.source_prediction_identity,
            calibrated_probability.walk_forward_fit_identity,
        }
        if calibrated_probability.issued_at_ms > signal.as_of_ms:
            raise ValueError(
                "unified runtime calibrated probability must exist by source as-of"
            )
        if (
            probability_slice.availability is not ProofEvidenceAvailability.AVAILABLE
            or not required_probability_ids.issubset(
                set(probability_slice.evidence_identities)
            )
        ):
            raise ValueError(
                "unified runtime probability proof must bind exact R19 lineage"
            )


def _validate_family_proof_coverage(
    *,
    family_evidence: tuple[ConfluenceFamilyEvidence, ...],
    slices: tuple[DecisionProofEvidenceSlice, ...],
) -> None:
    by_domain = {item.domain: item for item in slices}
    for family_item in family_evidence:
        required_ids = set(family_item.source_evidence_identities)
        if not required_ids:
            continue
        covered_ids: set[str] = set()
        for domain in FAMILY_PROOF_DOMAINS[family_item.family]:
            covered_ids.update(by_domain[domain].evidence_identities)
        if not required_ids.issubset(covered_ids):
            raise ValueError(
                "unified runtime proof does not cover exact M6 family source evidence"
            )


def _methodology_slice(
    signal: SignalDecision,
    confluence: ConfluenceMatrixSnapshot,
    *,
    extra_lineage_identities: tuple[str, ...] = (),
) -> DecisionProofEvidenceSlice:
    if confluence.freshness_0_1 is None:
        raise ValueError(
            "unified runtime requires measured M6 freshness for methodology proof"
        )
    verdict = _methodology_verdict(confluence)
    evidence_identities = tuple(
        sorted(
            {
                signal.freeze_identity,
                confluence.snapshot_identity,
                *extra_lineage_identities,
            }
        )
    )
    summary_codes = {
        f"m6_resolution_{confluence.resolution.value}",
        f"signal_state_{signal.state.value}",
    }
    if extra_lineage_identities:
        summary_codes.add("extra_forecast_source_lineage_bound")
    return build_decision_proof_evidence_slice(
        domain=ProofEvidenceDomain.METHODOLOGY,
        availability=ProofEvidenceAvailability.AVAILABLE,
        verdict=verdict,
        evidence_identities=evidence_identities,
        market_available_at_ms=signal.as_of_ms,
        observed_at_ms=signal.as_of_ms,
        freshness_0_1=confluence.freshness_0_1,
        source_quality=(
            "accepted_signal_plus_m6_plus_operational_lineage"
            if extra_lineage_identities
            else "accepted_signal_plus_m6"
        ),
        summary_codes=tuple(sorted(summary_codes)),
    )


def _methodology_verdict(
    confluence: ConfluenceMatrixSnapshot,
) -> ProofEvidenceVerdict:
    if confluence.resolution in {
        ConfluenceMatrixResolution.ABSTAIN,
        ConfluenceMatrixResolution.CONFLICT,
    }:
        return ProofEvidenceVerdict.CONTRADICT
    if confluence.resolution in {
        ConfluenceMatrixResolution.PARTIAL,
        ConfluenceMatrixResolution.NOT_EVALUABLE,
    }:
        return ProofEvidenceVerdict.NEUTRAL
    if (
        confluence.support_score_0_100
        > confluence.opposition_score_0_100
    ):
        return ProofEvidenceVerdict.SUPPORT
    if (
        confluence.opposition_score_0_100
        > confluence.support_score_0_100
    ):
        return ProofEvidenceVerdict.CONTRADICT
    return ProofEvidenceVerdict.NEUTRAL


def _meta_direction(direction: SignalDirection) -> MetaDirection:
    if direction is SignalDirection.BULLISH:
        return MetaDirection.BULLISH
    if direction is SignalDirection.BEARISH:
        return MetaDirection.BEARISH
    raise ValueError("unified runtime requires directional signal")
