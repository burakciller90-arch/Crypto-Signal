"""Fail-closed auxiliary evidence for forward canonical Capital Story.

The Smart Capital Allocator requires explicit Tactical and Opportunity evidence
objects even when those vaults must HOLD. This adapter builds those objects only
from the immutable Decision Proof / Event Risk context already bound to the same
UnifiedDecisionIssuance.

Missing positive measurements stay false. In particular:
- an ORDER_FLOW_CVD proof slice can establish CVD availability only;
- no accepted production absorption proof exists here, so absorption remains false;
- liquidity-take context is not relabeled as a liquidity sweep, so sweep remains false;
- no accepted recovery threshold is invented for spread/liquidity/price discovery.

Thus the adapter can explain a canonical HOLD without fabricating eligibility.
REAL_CAPITAL=0.
"""
from __future__ import annotations

from dataclasses import dataclass

from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CircuitBreakerAnalysis,
    CircuitBreakerState,
)
from crypto_signal.paper.smart_capital_allocator import (
    OpportunityRecoveryEvidence,
    TacticalMicrostructureEvidence,
    build_opportunity_recovery_evidence,
    build_tactical_microstructure_evidence,
)
from crypto_signal.product.decision_proof import (
    DecisionProofEvidenceSlice,
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
)
from crypto_signal.unified_decision_runtime import UnifiedDecisionIssuance

TACTICAL_FORWARD_TIMEFRAME = "5m"
CAPITAL_FORWARD_EVIDENCE_ADAPTER_VERSION = (
    "stream-final-f5-capital-forward-evidence-v1/1"
)
REAL_CAPITAL = 0


@dataclass(frozen=True, slots=True)
class CapitalForwardAuxiliaryEvidence:
    tactical: TacticalMicrostructureEvidence
    opportunity: OpportunityRecoveryEvidence
    adapter_version: str = CAPITAL_FORWARD_EVIDENCE_ADAPTER_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.adapter_version != CAPITAL_FORWARD_EVIDENCE_ADAPTER_VERSION:
            raise ValueError("unsupported capital forward evidence adapter")
        if self.tactical.asset != self.opportunity.asset:
            raise ValueError("capital forward auxiliary evidence asset mismatch")
        if self.tactical.as_of_ms != self.opportunity.as_of_ms:
            raise ValueError("capital forward auxiliary evidence PIT mismatch")
        if (
            self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("capital forward evidence crossed authority boundary")


def build_capital_forward_auxiliary_evidence(
    issuance: UnifiedDecisionIssuance,
    *,
    event_context: CircuitBreakerAnalysis,
) -> CapitalForwardAuxiliaryEvidence:
    proof = issuance.proof
    forecast = issuance.forecast
    if event_context.evidence_identity != forecast.event_context_identity:
        raise ValueError("capital forward Event Risk/forecast identity mismatch")
    if event_context.as_of_ms != forecast.source_as_of_ms:
        raise ValueError("capital forward Event Risk/forecast PIT mismatch")
    if proof.forecast_identity != forecast.forecast_identity:
        raise ValueError("capital forward proof/forecast identity mismatch")

    liquidity = _slice(proof.evidence_slices, ProofEvidenceDomain.LIQUIDITY_MAP)
    order_flow = _slice(proof.evidence_slices, ProofEvidenceDomain.ORDER_FLOW_CVD)
    order_book = _slice(proof.evidence_slices, ProofEvidenceDomain.ORDER_BOOK)
    frozen_chart = _slice(proof.evidence_slices, ProofEvidenceDomain.FROZEN_CHART)
    event_slice = _slice(proof.evidence_slices, ProofEvidenceDomain.EVENT_CONTEXT)

    market_quality_identity = (
        event_context.market_quality_identity
        if event_context.market_quality_identity is not None
        else event_slice.slice_identity
    )

    # Tactical eligibility remains fail-closed. A proof-domain identity is exact
    # even when availability=INSUFFICIENT; it proves the absence rather than
    # fabricating a positive measurement.
    tactical = build_tactical_microstructure_evidence(
        asset=forecast.symbol,
        timeframe=TACTICAL_FORWARD_TIMEFRAME,
        as_of_ms=forecast.source_as_of_ms,
        liquidity_evidence_identity=liquidity.slice_identity,
        order_flow_evidence_identity=order_flow.slice_identity,
        market_quality_evidence_identity=market_quality_identity,
        cvd_available=(
            order_flow.availability is ProofEvidenceAvailability.AVAILABLE
        ),
        absorption_evidence_available=False,
        liquidity_sweep_evidence_available=False,
        evidence_complete=False,
    )

    # Opportunity recovery likewise records exact source identities while
    # refusing to infer stabilization/recovery criteria that are not accepted.
    # Event Risk CLEAR implies its accepted market-quality checks passed, but
    # the other three recovery dimensions remain unproven until a dedicated
    # accepted recovery source exists.
    opportunity = build_opportunity_recovery_evidence(
        asset=forecast.symbol,
        as_of_ms=forecast.source_as_of_ms,
        spread_stabilization_identity=order_book.slice_identity,
        liquidity_recovery_identity=liquidity.slice_identity,
        price_discovery_identity=frozen_chart.slice_identity,
        feed_quality_identity=market_quality_identity,
        spread_stabilized=False,
        liquidity_recovered=False,
        price_discovery_stable=False,
        feed_quality_healthy=(
            event_context.state is CircuitBreakerState.CLEAR
            and event_context.market_quality_identity is not None
        ),
    )
    return CapitalForwardAuxiliaryEvidence(
        tactical=tactical,
        opportunity=opportunity,
    )


def _slice(
    slices: tuple[DecisionProofEvidenceSlice, ...],
    domain: ProofEvidenceDomain,
) -> DecisionProofEvidenceSlice:
    matches = tuple(item for item in slices if item.domain is domain)
    if len(matches) != 1:
        raise ValueError(
            f"capital forward requires exactly one {domain.value} proof slice"
        )
    return matches[0]
