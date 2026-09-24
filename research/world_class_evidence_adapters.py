"""Read-only WC7 adapters from accepted subsystem boundaries to blockers.

The source boundary identity is preserved separately from WC7 evidence artifact
identity. This lets WC7 prove *why* a blocker exists without relabelling the
boundary artifact as satisfied review evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.execution_lab_sandbox import (
    WC6SandboxBoundaryEvidence,
    WC6SandboxDispatchStatus,
    WC6SandboxEvidenceSemantic,
)
from research.alpha_factory.champion_challenger_cycle import (
    WC4ChampionChallengerCycle,
)
from research.world_class_evidence_provenance import (
    WC7EvidenceProvenance,
    WC7EvidenceSourceKind,
    build_wc7_evidence_provenance,
)
from research.world_class_evidence_review import (
    REAL_CAPITAL,
    WC7EvidenceClaim,
    WC7EvidenceDimension,
    WC7EvidenceStatus,
    build_wc7_evidence_claim,
)

WC7_ADAPTER_ENGINE_VERSION = "wc7-canonical-blocker-adapters-v1/1"
WC7_ADAPTER_SCHEMA_VERSION = "wc7-canonical-blocker-adapters-schema-v1/1"


class WC7BoundarySourceKind(StrEnum):
    WC4_CHAMPION_CHALLENGER_CYCLE = "wc4_champion_challenger_cycle"
    WC6_SANDBOX_NOT_CONFIGURED_BOUNDARY = "wc6_sandbox_not_configured_boundary"


@dataclass(frozen=True, slots=True)
class WC7AdaptedBlocker:
    adapter_identity: str
    schema_version: str
    engine_version: str
    source_boundary_kind: WC7BoundarySourceKind
    source_boundary_identity: str
    claim: WC7EvidenceClaim
    provenance: WC7EvidenceProvenance
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.adapter_identity, "WC7 adapter identity")
        _require_sha256(
            self.source_boundary_identity,
            "WC7 source-boundary identity",
        )
        if self.schema_version != WC7_ADAPTER_SCHEMA_VERSION:
            raise ValueError("unsupported WC7 blocker-adapter schema")
        if self.engine_version != WC7_ADAPTER_ENGINE_VERSION:
            raise ValueError("unsupported WC7 blocker-adapter engine")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.claim.evidence_identity is not None:
            raise ValueError("WC7 blocker claim cannot carry evidence artifact")
        if self.provenance.source_artifact_identity is not None:
            raise ValueError("WC7 blocker provenance cannot carry evidence artifact")
        if self.provenance.claim_identity != self.claim.claim_identity:
            raise ValueError("WC7 adapter claim/provenance identity mismatch")
        if self.provenance.dimension is not self.claim.dimension:
            raise ValueError("WC7 adapter claim/provenance dimension mismatch")
        if self.provenance.claim_status is not self.claim.status:
            raise ValueError("WC7 adapter claim/provenance status mismatch")
        expected_prefix = (
            f"{self.source_boundary_kind.value}:"
            f"{self.source_boundary_identity}:"
        )
        if not self.provenance.source_reference.startswith(expected_prefix):
            raise ValueError("WC7 adapter lost exact source-boundary reference")
        _validate_adapter_semantics(self)
        if self.adapter_identity != canonical_sha256(_adapter_payload(self)):
            raise ValueError("WC7 blocker-adapter identity mismatch")


def adapt_wc4_cycle_to_regime_blocker(
    cycle: WC4ChampionChallengerCycle,
    *,
    observed_at_ms: int,
) -> WC7AdaptedBlocker:
    """Preserve WC4 process provenance without claiming durable regime edge."""

    if (
        cycle.performance_winner_declared
        or cycle.champion_state_mutation_performed
        or cycle.automatic_promotion
        or cycle.deploy_authority
        or cycle.production_authority
        or cycle.real_capital != REAL_CAPITAL
    ):
        raise ValueError("WC7 requires authority-closed WC4 cycle")
    claim = build_wc7_evidence_claim(
        dimension=WC7EvidenceDimension.REGIME_ROBUSTNESS,
        status=WC7EvidenceStatus.MISSING,
        evidence_identity=None,
        evidence_note=(
            "Accepted WC4 research-cycle machinery exists, including robustness "
            "lineage, but the cycle does not establish durable regime edge."
        ),
    )
    source_reference = (
        f"{WC7BoundarySourceKind.WC4_CHAMPION_CHALLENGER_CYCLE.value}:"
        f"{cycle.cycle_identity}:"
        "engineering-cycle-present-durable-regime-edge-not-established"
    )
    provenance = build_wc7_evidence_provenance(
        claim,
        source_kind=WC7EvidenceSourceKind.MISSING_REQUIRED_EVIDENCE,
        source_reference=source_reference,
        observed_at_ms=observed_at_ms,
    )
    return _build_adapter(
        source_boundary_kind=(
            WC7BoundarySourceKind.WC4_CHAMPION_CHALLENGER_CYCLE
        ),
        source_boundary_identity=cycle.cycle_identity,
        claim=claim,
        provenance=provenance,
    )


def adapt_wc6_boundary_to_execution_blocker(
    evidence: WC6SandboxBoundaryEvidence,
    *,
    observed_at_ms: int,
) -> WC7AdaptedBlocker:
    """Preserve WC6 boundary provenance while real venue evidence is absent."""

    if evidence.semantic is not (
        WC6SandboxEvidenceSemantic.REQUEST_PREPARED_NO_DISPATCH_NO_VENUE_EVIDENCE
    ):
        raise ValueError("WC7 requires accepted fail-closed WC6 semantic")
    if evidence.dispatch_status is not (
        WC6SandboxDispatchStatus.BLOCKED_NOT_CONFIGURED
    ):
        raise ValueError("WC7 requires WC6 dispatch blocked-not-configured")
    if (
        evidence.dispatch_attempted
        or evidence.venue_acknowledgement_identity is not None
        or evidence.venue_fill_identities
        or evidence.endpoint_bound
        or evidence.credential_bound
        or evidence.transport_bound
        or evidence.network_authority
        or evidence.live_order_authority
        or evidence.production_authority
        or evidence.real_capital != REAL_CAPITAL
    ):
        raise ValueError("WC7 requires authority-isolated WC6 boundary")
    claim = build_wc7_evidence_claim(
        dimension=WC7EvidenceDimension.CAPITAL_EXECUTION_LINEAGE,
        status=WC7EvidenceStatus.EXTERNAL_DEPENDENCY,
        evidence_identity=None,
        evidence_note=(
            "WC6 request/idempotency lineage is accepted up to the sandbox "
            "boundary, but configured transport plus venue acknowledgement, "
            "fill and recovery evidence remain external/missing."
        ),
    )
    source_reference = (
        f"{WC7BoundarySourceKind.WC6_SANDBOX_NOT_CONFIGURED_BOUNDARY.value}:"
        f"{evidence.evidence_identity}:"
        "blocked-not-configured-no-venue-evidence"
    )
    provenance = build_wc7_evidence_provenance(
        claim,
        source_kind=WC7EvidenceSourceKind.EXTERNAL_DEPENDENCY_BOUNDARY,
        source_reference=source_reference,
        observed_at_ms=observed_at_ms,
    )
    return _build_adapter(
        source_boundary_kind=(
            WC7BoundarySourceKind.WC6_SANDBOX_NOT_CONFIGURED_BOUNDARY
        ),
        source_boundary_identity=evidence.evidence_identity,
        claim=claim,
        provenance=provenance,
    )


def _build_adapter(
    *,
    source_boundary_kind: WC7BoundarySourceKind,
    source_boundary_identity: str,
    claim: WC7EvidenceClaim,
    provenance: WC7EvidenceProvenance,
) -> WC7AdaptedBlocker:
    payload = {
        "claim": claim,
        "engine_version": WC7_ADAPTER_ENGINE_VERSION,
        "provenance": provenance,
        "real_capital": REAL_CAPITAL,
        "schema_version": WC7_ADAPTER_SCHEMA_VERSION,
        "source_boundary_identity": source_boundary_identity,
        "source_boundary_kind": source_boundary_kind,
    }
    return WC7AdaptedBlocker(
        adapter_identity=canonical_sha256(payload),
        schema_version=WC7_ADAPTER_SCHEMA_VERSION,
        engine_version=WC7_ADAPTER_ENGINE_VERSION,
        source_boundary_kind=source_boundary_kind,
        source_boundary_identity=source_boundary_identity,
        claim=claim,
        provenance=provenance,
        real_capital=REAL_CAPITAL,
    )


def _validate_adapter_semantics(adapter: WC7AdaptedBlocker) -> None:
    if adapter.source_boundary_kind is (
        WC7BoundarySourceKind.WC4_CHAMPION_CHALLENGER_CYCLE
    ):
        if adapter.claim.dimension is not WC7EvidenceDimension.REGIME_ROBUSTNESS:
            raise ValueError("WC4 adapter must target regime robustness")
        if adapter.claim.status is not WC7EvidenceStatus.MISSING:
            raise ValueError("WC4 adapter must preserve missing regime evidence")
        if adapter.provenance.source_kind is not (
            WC7EvidenceSourceKind.MISSING_REQUIRED_EVIDENCE
        ):
            raise ValueError("WC4 adapter must preserve missing-evidence source")
    elif adapter.source_boundary_kind is (
        WC7BoundarySourceKind.WC6_SANDBOX_NOT_CONFIGURED_BOUNDARY
    ):
        if adapter.claim.dimension is not (
            WC7EvidenceDimension.CAPITAL_EXECUTION_LINEAGE
        ):
            raise ValueError("WC6 adapter must target capital/execution lineage")
        if adapter.claim.status is not WC7EvidenceStatus.EXTERNAL_DEPENDENCY:
            raise ValueError("WC6 adapter must preserve external dependency")
        if adapter.provenance.source_kind is not (
            WC7EvidenceSourceKind.EXTERNAL_DEPENDENCY_BOUNDARY
        ):
            raise ValueError("WC6 adapter must preserve external-dependency source")
    else:
        raise ValueError("unsupported WC7 blocker adapter source kind")


def _adapter_payload(adapter: WC7AdaptedBlocker) -> dict[str, object]:
    return {
        "claim": adapter.claim,
        "engine_version": adapter.engine_version,
        "provenance": adapter.provenance,
        "real_capital": adapter.real_capital,
        "schema_version": adapter.schema_version,
        "source_boundary_identity": adapter.source_boundary_identity,
        "source_boundary_kind": adapter.source_boundary_kind,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
