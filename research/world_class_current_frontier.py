"""Fail-closed composition of the current WC7 evidence frontier.

The composer uses canonical WC2/WC6 adapters plus explicit accepted boundary
identities for dimensions that do not yet have a subsystem adapter. It cannot
manufacture a complete review: missing economic, durable-regime, external-venue,
or human-usability evidence remains explicit and therefore keeps machine
readiness at INSUFFICIENT_EVIDENCE.
"""

from __future__ import annotations

from dataclasses import dataclass

from crypto_signal.evaluation.untouched_forward_policy import (
    WC2ReviewReadiness,
    WC2ReviewStatus,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.execution_lab_sandbox import WC6SandboxBoundaryEvidence
from research.world_class_evidence_adapters import (
    WC7AdaptedEvidence,
    adapt_wc2_untouched_forward_readiness,
    adapt_wc6_sandbox_boundary,
)
from research.world_class_evidence_provenance import (
    WC7EvidencePacket,
    WC7EvidenceProvenance,
    WC7EvidenceSourceKind,
    build_wc7_evidence_packet,
    build_wc7_evidence_provenance,
)
from research.world_class_evidence_review import (
    REAL_CAPITAL,
    WC7EvidenceClaim,
    WC7EvidenceDimension,
    WC7EvidenceReview,
    WC7EvidenceStatus,
    WC7MachineReadiness,
    WC7ReviewConclusion,
    build_wc7_evidence_claim,
    build_wc7_evidence_review,
)

WC7_CURRENT_FRONTIER_ENGINE_VERSION = "wc7-current-frontier-packet-v1/1"
WC7_CURRENT_FRONTIER_SCHEMA_VERSION = "wc7-current-frontier-packet-schema-v1/1"


@dataclass(frozen=True, slots=True)
class WC7CurrentFrontierInputs:
    runtime_acceptance_identity: str
    abstention_transparency_identity: str
    wc4_research_cycle_identity: str
    wc2_readiness: WC2ReviewReadiness
    wc6_sandbox_boundary: WC6SandboxBoundaryEvidence
    observed_at_ms: int
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (
                self.runtime_acceptance_identity,
                "WC7 runtime acceptance identity",
            ),
            (
                self.abstention_transparency_identity,
                "WC7 abstention transparency identity",
            ),
            (
                self.wc4_research_cycle_identity,
                "WC7 WC4 research-cycle identity",
            ),
        ):
            _require_sha256(value, label)
        if self.observed_at_ms < 0:
            raise ValueError("WC7 frontier observation time must be non-negative")
        if self.wc2_readiness.real_capital != REAL_CAPITAL:
            raise ValueError("WC2 readiness violates REAL_CAPITAL=0")
        if self.wc6_sandbox_boundary.real_capital != REAL_CAPITAL:
            raise ValueError("WC6 boundary violates REAL_CAPITAL=0")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")


@dataclass(frozen=True, slots=True)
class WC7CurrentFrontierSnapshot:
    snapshot_identity: str
    schema_version: str
    engine_version: str
    review: WC7EvidenceReview
    packet: WC7EvidencePacket
    current_conclusion: WC7ReviewConclusion
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.snapshot_identity, "WC7 frontier snapshot identity")
        if self.schema_version != WC7_CURRENT_FRONTIER_SCHEMA_VERSION:
            raise ValueError("unsupported WC7 frontier snapshot schema")
        if self.engine_version != WC7_CURRENT_FRONTIER_ENGINE_VERSION:
            raise ValueError("unsupported WC7 frontier snapshot engine")
        if self.packet.review_identity != self.review.review_identity:
            raise ValueError("WC7 frontier packet/review identity mismatch")
        if self.review.machine_readiness is not (
            WC7MachineReadiness.INSUFFICIENT_EVIDENCE
        ):
            raise ValueError("WC7 current frontier must remain insufficient")
        if self.review.machine_conclusion is not (
            WC7ReviewConclusion.INSUFFICIENT_EVIDENCE
        ):
            raise ValueError("WC7 current frontier machine conclusion mismatch")
        if self.current_conclusion is not (
            WC7ReviewConclusion.INSUFFICIENT_EVIDENCE
        ):
            raise ValueError("WC7 current frontier cannot claim EDGE_* verdict")
        if self.review.automatic_edge_verdict or self.packet.automatic_edge_verdict:
            raise ValueError("WC7 current frontier cannot auto-select edge verdict")
        if self.review.production_authority or self.packet.production_authority:
            raise ValueError("WC7 current frontier grants no production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.snapshot_identity != canonical_sha256(_snapshot_payload(self)):
            raise ValueError("WC7 current-frontier snapshot identity mismatch")


def build_wc7_current_frontier_snapshot(
    inputs: WC7CurrentFrontierInputs,
) -> WC7CurrentFrontierSnapshot:
    """Compose the accepted current evidence state without filling blockers."""

    adapted_wc2 = adapt_wc2_untouched_forward_readiness(
        inputs.wc2_readiness,
        observed_at_ms=inputs.observed_at_ms,
    )
    adapted_wc6 = adapt_wc6_sandbox_boundary(
        inputs.wc6_sandbox_boundary,
        observed_at_ms=inputs.observed_at_ms,
    )

    runtime = _evidenced_claim(
        dimension=WC7EvidenceDimension.PRODUCTION_RUNTIME_RELIABILITY,
        source_kind=WC7EvidenceSourceKind.RUNTIME_ACCEPTANCE,
        artifact_identity=inputs.runtime_acceptance_identity,
        note="accepted production/runtime reliability evidence",
        source_reference=(
            "accepted-runtime:"
            f"{inputs.runtime_acceptance_identity}"
        ),
        observed_at_ms=inputs.observed_at_ms,
    )

    probability_boundary_identity = canonical_sha256(
        {
            "engine_version": WC7_CURRENT_FRONTIER_ENGINE_VERSION,
            "probability_claims_used": False,
            "scope": "wc7-current-frontier",
        }
    )
    probability_claim = build_wc7_evidence_claim(
        dimension=WC7EvidenceDimension.PROBABILITY_CALIBRATION_WHERE_USED,
        status=WC7EvidenceStatus.NOT_APPLICABLE,
        evidence_note=(
            "current WC7 frontier does not use probability claims; "
            "calibration is therefore explicitly not applicable"
        ),
        evidence_identity=probability_boundary_identity,
    )
    probability = WC7AdaptedEvidence(
        claim=probability_claim,
        provenance=build_wc7_evidence_provenance(
            probability_claim,
            source_kind=WC7EvidenceSourceKind.PROBABILITY_NOT_USED_BOUNDARY,
            source_artifact_identity=probability_boundary_identity,
            source_reference=(
                "wc7-current-frontier:probability_claims_used=false"
            ),
            observed_at_ms=inputs.observed_at_ms,
        ),
        real_capital=REAL_CAPITAL,
    )

    wc2_blocker_identity = inputs.wc2_readiness.readiness_identity
    cost = _blocker_claim(
        dimension=WC7EvidenceDimension.COST_ADJUSTED_EXPECTANCY,
        status=WC7EvidenceStatus.MISSING,
        source_kind=WC7EvidenceSourceKind.MISSING_REQUIRED_EVIDENCE,
        note=(
            "cost-adjusted expectancy conclusion is not available; "
            "WC3 economic review has not produced accepted evidence"
        ),
        source_reference=(
            "wc3-cost-adjusted-economics:not-available:"
            f"wc2-readiness={wc2_blocker_identity}"
        ),
        observed_at_ms=inputs.observed_at_ms,
        blocker_boundary_identity=_derived_blocker_boundary_identity(
            dimension=WC7EvidenceDimension.COST_ADJUSTED_EXPECTANCY,
            source_identity=wc2_blocker_identity,
            semantic="wc3_cost_adjusted_economics_not_available",
        ),
    )
    drawdown = _blocker_claim(
        dimension=WC7EvidenceDimension.CONTROLLED_DRAWDOWN,
        status=WC7EvidenceStatus.MISSING,
        source_kind=WC7EvidenceSourceKind.MISSING_REQUIRED_EVIDENCE,
        note=(
            "controlled-drawdown conclusion is not available; "
            "WC3 economic review has not produced accepted evidence"
        ),
        source_reference=(
            "wc3-drawdown:not-available:"
            f"wc2-readiness={wc2_blocker_identity}"
        ),
        observed_at_ms=inputs.observed_at_ms,
        blocker_boundary_identity=_derived_blocker_boundary_identity(
            dimension=WC7EvidenceDimension.CONTROLLED_DRAWDOWN,
            source_identity=wc2_blocker_identity,
            semantic="wc3_drawdown_evidence_not_available",
        ),
    )
    regime = _blocker_claim(
        dimension=WC7EvidenceDimension.REGIME_ROBUSTNESS,
        status=WC7EvidenceStatus.MISSING,
        source_kind=WC7EvidenceSourceKind.MISSING_REQUIRED_EVIDENCE,
        note=(
            "WC4 research-cycle engineering is accepted, but durable "
            "regime-specific edge evidence has not been established"
        ),
        source_reference=(
            "wc4-research-cycle:"
            f"{inputs.wc4_research_cycle_identity}:engineering-only"
        ),
        observed_at_ms=inputs.observed_at_ms,
        blocker_boundary_identity=_derived_blocker_boundary_identity(
            dimension=WC7EvidenceDimension.REGIME_ROBUSTNESS,
            source_identity=inputs.wc4_research_cycle_identity,
            semantic="wc4_engineering_only_durable_regime_edge_not_established",
        ),
    )

    abstention = _evidenced_claim(
        dimension=WC7EvidenceDimension.ABSTENTION_FAILURE_TRANSPARENCY,
        source_kind=WC7EvidenceSourceKind.FAIL_CLOSED_TRANSPARENCY,
        artifact_identity=inputs.abstention_transparency_identity,
        note="accepted fail-closed abstention/failure transparency evidence",
        source_reference=(
            "accepted-fail-closed-transparency:"
            f"{inputs.abstention_transparency_identity}"
        ),
        observed_at_ms=inputs.observed_at_ms,
    )

    usability = _blocker_claim(
        dimension=WC7EvidenceDimension.USABILITY_WITHOUT_HIDDEN_UNCERTAINTY,
        status=WC7EvidenceStatus.NOT_MEASURED,
        source_kind=WC7EvidenceSourceKind.NOT_MEASURED_BOUNDARY,
        note=(
            "human <=10-second comprehension/usability has not been measured"
        ),
        source_reference="wc5-human-usability:not-measured",
        observed_at_ms=inputs.observed_at_ms,
        blocker_boundary_identity=_derived_blocker_boundary_identity(
            dimension=(
                WC7EvidenceDimension.USABILITY_WITHOUT_HIDDEN_UNCERTAINTY
            ),
            source_identity=inputs.abstention_transparency_identity,
            semantic="wc5_human_ten_second_usability_not_measured",
        ),
    )

    adapted = (
        runtime,
        adapted_wc2,
        probability,
        cost,
        drawdown,
        regime,
        abstention,
        adapted_wc6,
        usability,
    )
    claims = tuple(item.claim for item in adapted)
    provenances = tuple(item.provenance for item in adapted)

    review = build_wc7_evidence_review(
        claims=claims,
        probability_claims_used=False,
    )
    packet = build_wc7_evidence_packet(
        review,
        provenances=provenances,
    )
    expected_blockers = (
        WC7EvidenceDimension.CAPITAL_EXECUTION_LINEAGE,
        WC7EvidenceDimension.CONTROLLED_DRAWDOWN,
        WC7EvidenceDimension.COST_ADJUSTED_EXPECTANCY,
        WC7EvidenceDimension.REGIME_ROBUSTNESS,
        WC7EvidenceDimension.USABILITY_WITHOUT_HIDDEN_UNCERTAINTY,
    )
    if inputs.wc2_readiness.status is WC2ReviewStatus.INSUFFICIENT_EVIDENCE:
        expected_blockers = tuple(
            sorted(
                (
                    *expected_blockers,
                    WC7EvidenceDimension.UNTOUCHED_FORWARD_HISTORY,
                ),
                key=lambda item: item.value,
            )
        )
    else:
        expected_blockers = tuple(
            sorted(expected_blockers, key=lambda item: item.value)
        )
    if review.blocking_dimensions != expected_blockers:
        raise ValueError("WC7 current-frontier blocker set mismatch")

    values = {
        "current_conclusion": WC7ReviewConclusion.INSUFFICIENT_EVIDENCE,
        "engine_version": WC7_CURRENT_FRONTIER_ENGINE_VERSION,
        "packet_identity": packet.packet_identity,
        "real_capital": REAL_CAPITAL,
        "review_identity": review.review_identity,
        "schema_version": WC7_CURRENT_FRONTIER_SCHEMA_VERSION,
    }
    return WC7CurrentFrontierSnapshot(
        snapshot_identity=canonical_sha256(values),
        schema_version=WC7_CURRENT_FRONTIER_SCHEMA_VERSION,
        engine_version=WC7_CURRENT_FRONTIER_ENGINE_VERSION,
        review=review,
        packet=packet,
        current_conclusion=WC7ReviewConclusion.INSUFFICIENT_EVIDENCE,
        real_capital=REAL_CAPITAL,
    )


def _evidenced_claim(
    *,
    dimension: WC7EvidenceDimension,
    source_kind: WC7EvidenceSourceKind,
    artifact_identity: str,
    note: str,
    source_reference: str,
    observed_at_ms: int,
) -> WC7AdaptedEvidence:
    _require_sha256(artifact_identity, "WC7 frontier evidence artifact")
    claim = build_wc7_evidence_claim(
        dimension=dimension,
        status=WC7EvidenceStatus.SATISFIED,
        evidence_note=note,
        evidence_identity=artifact_identity,
    )
    return WC7AdaptedEvidence(
        claim=claim,
        provenance=build_wc7_evidence_provenance(
            claim,
            source_kind=source_kind,
            source_artifact_identity=artifact_identity,
            source_reference=source_reference,
            observed_at_ms=observed_at_ms,
        ),
        real_capital=REAL_CAPITAL,
    )


def _blocker_claim(
    *,
    dimension: WC7EvidenceDimension,
    status: WC7EvidenceStatus,
    source_kind: WC7EvidenceSourceKind,
    note: str,
    source_reference: str,
    observed_at_ms: int,
    blocker_boundary_identity: str | None,
) -> WC7AdaptedEvidence:
    if blocker_boundary_identity is not None:
        _require_sha256(
            blocker_boundary_identity,
            "WC7 frontier blocker boundary",
        )
    claim = build_wc7_evidence_claim(
        dimension=dimension,
        status=status,
        evidence_note=note,
        evidence_identity=None,
    )
    return WC7AdaptedEvidence(
        claim=claim,
        provenance=build_wc7_evidence_provenance(
            claim,
            source_kind=source_kind,
            blocker_boundary_identity=blocker_boundary_identity,
            source_reference=source_reference,
            observed_at_ms=observed_at_ms,
        ),
        real_capital=REAL_CAPITAL,
    )



def _derived_blocker_boundary_identity(
    *,
    dimension: WC7EvidenceDimension,
    source_identity: str,
    semantic: str,
) -> str:
    _require_sha256(source_identity, "WC7 blocker source identity")
    if not semantic.strip():
        raise ValueError("WC7 blocker semantic must be non-empty")
    return canonical_sha256(
        {
            "dimension": dimension,
            "engine_version": WC7_CURRENT_FRONTIER_ENGINE_VERSION,
            "semantic": semantic,
            "source_identity": source_identity,
        }
    )

def _snapshot_payload(
    snapshot: WC7CurrentFrontierSnapshot,
) -> dict[str, object]:
    return {
        "current_conclusion": snapshot.current_conclusion,
        "engine_version": snapshot.engine_version,
        "packet_identity": snapshot.packet.packet_identity,
        "real_capital": snapshot.real_capital,
        "review_identity": snapshot.review.review_identity,
        "schema_version": snapshot.schema_version,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
