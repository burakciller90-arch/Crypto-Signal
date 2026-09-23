"""R25 Slice 6: exact Unified Decision -> Smart Capital Allocator bridge.

This bridge carries accepted decision evidence into the existing Epoch 2 capital
research envelope. It does not select a sizing method, notional, trade, fill,
or mutate canonical accounting.
"""
from __future__ import annotations

from dataclasses import dataclass

from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CircuitBreakerAnalysis,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.smart_capital_allocator import (
    OpportunityRecoveryEvidence,
    SmartCapitalAllocationAssessment,
    SmartCapitalCandidate,
    TacticalMicrostructureEvidence,
    assess_smart_capital_candidate,
    build_smart_capital_candidate,
)
from crypto_signal.product.decision_proof import (
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
)
from crypto_signal.unified_decision_runtime import UnifiedDecisionIssuance

CAPITAL_SCIENCE_BRIDGE_VERSION = "r25-capital-science-bridge-v1/1"
REAL_CAPITAL = 0


@dataclass(frozen=True, slots=True)
class CapitalScienceBridgeResult:
    bridge_identity: str
    forecast_identity: str
    proof_identity: str
    confluence_identity: str
    event_risk_identity: str
    candidate: SmartCapitalCandidate
    allocation: SmartCapitalAllocationAssessment
    assessed_at_ms: int
    bridge_version: str = CAPITAL_SCIENCE_BRIDGE_VERSION
    automatic_sizing_authority: bool = False
    automatic_trade_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.bridge_version != CAPITAL_SCIENCE_BRIDGE_VERSION:
            raise ValueError("unsupported capital-science bridge version")
        if self.assessed_at_ms < self.candidate.as_of_ms:
            raise ValueError("capital-science assessment predates decision evidence")
        if self.allocation.candidate_identity != self.candidate.candidate_identity:
            raise ValueError("capital-science allocation/candidate lineage mismatch")
        if self.candidate.confluence is None:
            raise ValueError("capital-science candidate requires exact M6 confluence")
        if self.candidate.confluence.snapshot_identity != self.confluence_identity:
            raise ValueError("capital-science confluence lineage mismatch")
        if self.candidate.event_risk.evidence_identity != self.event_risk_identity:
            raise ValueError("capital-science Event Risk lineage mismatch")
        if (
            self.automatic_sizing_authority
            or self.automatic_trade_authority
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("capital-science bridge cannot grant execution authority")
        if self.bridge_identity != canonical_sha256(_bridge_payload(self)):
            raise ValueError("capital-science bridge identity mismatch")


def assess_unified_decision_capital(
    issuance: UnifiedDecisionIssuance,
    *,
    event_context: CircuitBreakerAnalysis,
    base_asset: str,
    assessed_at_ms: int,
    tactical_microstructure: TacticalMicrostructureEvidence | None = None,
    opportunity_recovery: OpportunityRecoveryEvidence | None = None,
) -> CapitalScienceBridgeResult:
    """Evaluate existing capital policy against exact immutable decision lineage."""
    forecast = issuance.forecast
    proof = issuance.proof
    confluence = issuance.confluence

    if not base_asset or base_asset != base_asset.upper():
        raise ValueError("capital-science base asset must be uppercase")
    if forecast.symbol != confluence.asset:
        raise ValueError("capital-science forecast/M6 market mismatch")
    if forecast.source_as_of_ms != confluence.as_of_ms:
        raise ValueError("capital-science forecast/M6 as-of mismatch")
    if event_context.asset != base_asset:
        raise ValueError("capital-science Event Risk/base asset mismatch")
    if event_context.as_of_ms != forecast.source_as_of_ms:
        raise ValueError("capital-science Event Risk/forecast as-of mismatch")
    if event_context.evidence_identity != forecast.event_context_identity:
        raise ValueError("capital-science forecast/Event Risk identity mismatch")
    if proof.forecast_identity != forecast.forecast_identity:
        raise ValueError("capital-science proof/forecast lineage mismatch")
    if proof.confluence_identity != confluence.snapshot_identity:
        raise ValueError("capital-science proof/M6 lineage mismatch")

    event_slice = next(
        (
            item
            for item in proof.evidence_slices
            if item.domain is ProofEvidenceDomain.EVENT_CONTEXT
        ),
        None,
    )
    if (
        event_slice is None
        or event_slice.availability is not ProofEvidenceAvailability.AVAILABLE
        or event_context.evidence_identity not in event_slice.evidence_identities
    ):
        raise ValueError(
            "capital-science Decision Proof lacks exact Event Risk evidence"
        )

    if tactical_microstructure is not None:
        if tactical_microstructure.asset != forecast.symbol:
            raise ValueError("capital-science tactical market mismatch")
        if tactical_microstructure.as_of_ms != forecast.source_as_of_ms:
            raise ValueError("capital-science tactical as-of mismatch")
    if opportunity_recovery is not None:
        if opportunity_recovery.asset != forecast.symbol:
            raise ValueError("capital-science recovery market mismatch")
        if opportunity_recovery.as_of_ms != forecast.source_as_of_ms:
            raise ValueError("capital-science recovery as-of mismatch")

    candidate = build_smart_capital_candidate(
        asset=forecast.symbol,
        as_of_ms=forecast.source_as_of_ms,
        event_risk=event_context,
        confluence=confluence,
        tactical_microstructure=tactical_microstructure,
        opportunity_recovery=opportunity_recovery,
    )
    allocation = assess_smart_capital_candidate(
        candidate,
        assessed_at_ms=assessed_at_ms,
    )

    payload = {
        "assessed_at_ms": assessed_at_ms,
        "automatic_sizing_authority": False,
        "automatic_trade_authority": False,
        "bridge_version": CAPITAL_SCIENCE_BRIDGE_VERSION,
        "candidate_identity": candidate.candidate_identity,
        "capital_assessment_identity": allocation.assessment_identity,
        "confluence_identity": confluence.snapshot_identity,
        "event_risk_identity": event_context.evidence_identity,
        "forecast_identity": forecast.forecast_identity,
        "production_authority": False,
        "proof_identity": proof.proof_identity,
        "real_capital": REAL_CAPITAL,
    }
    return CapitalScienceBridgeResult(
        bridge_identity=canonical_sha256(payload),
        forecast_identity=forecast.forecast_identity,
        proof_identity=proof.proof_identity,
        confluence_identity=confluence.snapshot_identity,
        event_risk_identity=event_context.evidence_identity,
        candidate=candidate,
        allocation=allocation,
        assessed_at_ms=assessed_at_ms,
    )


def _bridge_payload(result: CapitalScienceBridgeResult) -> dict[str, object]:
    return {
        "assessed_at_ms": result.assessed_at_ms,
        "automatic_sizing_authority": result.automatic_sizing_authority,
        "automatic_trade_authority": result.automatic_trade_authority,
        "bridge_version": result.bridge_version,
        "candidate_identity": result.candidate.candidate_identity,
        "capital_assessment_identity": result.allocation.assessment_identity,
        "confluence_identity": result.confluence_identity,
        "event_risk_identity": result.event_risk_identity,
        "forecast_identity": result.forecast_identity,
        "production_authority": result.production_authority,
        "proof_identity": result.proof_identity,
        "real_capital": result.real_capital,
    }
