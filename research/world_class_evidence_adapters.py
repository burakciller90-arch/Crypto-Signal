"""Typed, conservative WC7 adapters for accepted evidence artifacts.

These adapters intentionally preserve blockers. An engineering artifact is not
silently upgraded into proof of durable edge, and a fail-closed WC6 boundary is
not relabelled as venue execution evidence.
"""

from __future__ import annotations

from research.alpha_factory.champion_challenger_cycle import (
    WC4ChampionChallengerCycle,
)
from research.world_class_evidence_review import (
    WC7EvidenceClaim,
    WC7EvidenceDimension,
    WC7EvidenceStatus,
    build_wc7_evidence_claim,
)
from crypto_signal.paper.execution_lab_sandbox import (
    WC6SandboxBoundaryEvidence,
    WC6SandboxDispatchStatus,
    WC6SandboxEvidenceSemantic,
)


def build_wc7_regime_claim_from_wc4_cycle(
    cycle: WC4ChampionChallengerCycle,
) -> WC7EvidenceClaim:
    """Bind WC4 engineering provenance without claiming durable regime edge."""

    if cycle.performance_winner_declared:
        raise ValueError("WC7 cannot accept WC4 cycle with declared winner")
    if cycle.champion_state_mutation_performed:
        raise ValueError("WC7 cannot accept mutated champion state")
    if cycle.automatic_promotion or cycle.deploy_authority:
        raise ValueError("WC7 cannot accept promoted/deployable WC4 cycle")
    if cycle.production_authority or cycle.real_capital != 0:
        raise ValueError("WC7 WC4 provenance must remain research-only")

    return build_wc7_evidence_claim(
        dimension=WC7EvidenceDimension.REGIME_ROBUSTNESS,
        status=WC7EvidenceStatus.MISSING,
        evidence_identity=cycle.cycle_identity,
        evidence_note=(
            "WC4 champion/challenger engineering cycle is provenance for "
            "walk-forward, cost-stress and robustness machinery, but it does "
            "not establish durable regime-specific edge. Regime robustness "
            "remains a WC7 evidence blocker."
        ),
    )


def build_wc7_execution_claim_from_wc6_boundary(
    evidence: WC6SandboxBoundaryEvidence,
) -> WC7EvidenceClaim:
    """Bind accepted WC6 boundary while preserving missing real venue evidence."""

    if evidence.semantic is not (
        WC6SandboxEvidenceSemantic.REQUEST_PREPARED_NO_DISPATCH_NO_VENUE_EVIDENCE
    ):
        raise ValueError("WC7 requires fail-closed WC6 sandbox evidence semantic")
    if evidence.dispatch_status is not (
        WC6SandboxDispatchStatus.BLOCKED_NOT_CONFIGURED
    ):
        raise ValueError("WC7 requires blocked WC6 sandbox dispatch")
    if evidence.dispatch_attempted:
        raise ValueError("WC7 cannot accept attempted dispatch as blocked evidence")
    if evidence.venue_acknowledgement_identity is not None:
        raise ValueError("WC7 blocked boundary cannot claim venue acknowledgement")
    if evidence.venue_fill_identities:
        raise ValueError("WC7 blocked boundary cannot claim venue fills")
    if (
        evidence.endpoint_bound
        or evidence.credential_bound
        or evidence.transport_bound
        or evidence.network_authority
        or evidence.live_order_authority
        or evidence.production_authority
        or evidence.real_capital != 0
    ):
        raise ValueError("WC7 WC6 boundary must remain authority-isolated")

    return build_wc7_evidence_claim(
        dimension=WC7EvidenceDimension.CAPITAL_EXECUTION_LINEAGE,
        status=WC7EvidenceStatus.EXTERNAL_DEPENDENCY,
        evidence_identity=evidence.evidence_identity,
        evidence_note=(
            "WC6 fail-closed sandbox boundary proves request/idempotency "
            "lineage and authority isolation, but no configured transport, "
            "venue acknowledgement, venue fill or recovery evidence exists. "
            "Capital/execution lineage remains an external-dependency blocker."
        ),
    )
