"""R25 Slice 13: restart-safe persisted shadow cycle composition.

This module composes the accepted deterministic shadow replay rail with the
immutable Shadow Cycle Manifest. A crash after the intent journal append but
before manifest append is recoverable by replaying the same immutable inputs:
the journal append becomes IDEMPOTENT and the missing manifest is inserted.

No canonical Epoch 2 writer or execution authority is introduced.
REAL_CAPITAL=0.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CircuitBreakerAnalysis,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.smart_capital_allocator import (
    OpportunityRecoveryEvidence,
    TacticalMicrostructureEvidence,
)
from crypto_signal.paper.epoch2_accounting import Epoch2ActivationRecord
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.position_sizing_bridge import AcceptedSizingRiskInputs
from crypto_signal.paper.position_sizing_intelligence import (
    PositionSizingPolicy,
    SizingMethod,
)
from crypto_signal.paper.r22_intent_preview import AcceptedIntentMarketReference
from crypto_signal.paper.shadow_cycle_manifest import (
    R25ShadowCycleManifest,
    ShadowCycleManifestAppendResult,
    ShadowCycleManifestStatus,
)
from crypto_signal.paper.shadow_intent_journal import R25ShadowIntentJournal
from crypto_signal.paper.shadow_replay_orchestrator import (
    ShadowReplayCycleResult,
    run_shadow_restart_replay_cycle,
)
from crypto_signal.unified_decision_runtime import UnifiedDecisionIssuance
from research.alpha_factory.probability_calibration_gate import (
    CalibratedProbabilityEvidence,
)

SHADOW_PERSISTED_CYCLE_ENGINE_VERSION = "r25-shadow-persisted-cycle-v1/1"
REAL_CAPITAL = 0


@dataclass(frozen=True, slots=True)
class PersistedShadowCycleResult:
    persisted_cycle_identity: str
    cycle: ShadowReplayCycleResult
    manifest_append: ShadowCycleManifestAppendResult
    manifest_status: ShadowCycleManifestStatus
    engine_version: str = SHADOW_PERSISTED_CYCLE_ENGINE_VERSION
    canonical_epoch2_write_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.persisted_cycle_identity, "persisted shadow cycle")
        if self.engine_version != SHADOW_PERSISTED_CYCLE_ENGINE_VERSION:
            raise ValueError("unsupported persisted shadow cycle engine")
        record = self.manifest_append.record
        if record.cycle_identity != self.cycle.cycle_identity:
            raise ValueError("persisted cycle manifest/cycle mismatch")
        if record.forecast_identity != self.cycle.forecast_identity:
            raise ValueError("persisted cycle forecast mismatch")
        if record.proof_identity != self.cycle.proof_identity:
            raise ValueError("persisted cycle proof mismatch")
        if record.capital_bridge_identity != self.cycle.capital.bridge_identity:
            raise ValueError("persisted cycle Capital Science mismatch")
        if record.sizing_bridge_identity != self.cycle.sizing.bridge_identity:
            raise ValueError("persisted cycle Position Sizing mismatch")
        if record.preview_identity != self.cycle.preview.preview_identity:
            raise ValueError("persisted cycle preview mismatch")
        if (
            record.journal_record_identity
            != self.cycle.journal_append.record.record_identity
        ):
            raise ValueError("persisted cycle journal record mismatch")
        expected_review = (
            None
            if self.cycle.reviewed_selection is None
            else self.cycle.reviewed_selection.selection_identity
        )
        if record.review_selection_identity != expected_review:
            raise ValueError("persisted cycle review mismatch")
        if record.reviewed_method is not self.cycle.reviewed_method:
            raise ValueError("persisted cycle reviewed method mismatch")
        if record.vault_id is not self.cycle.vault_id:
            raise ValueError("persisted cycle vault mismatch")
        if self.manifest_status.record_count <= 0:
            raise ValueError("persisted cycle manifest status lost evidence")
        if (
            self.canonical_epoch2_write_authority
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("persisted shadow cycle cannot grant authority")
        if self.persisted_cycle_identity != canonical_sha256(
            _persisted_cycle_payload(self)
        ):
            raise ValueError("persisted shadow cycle identity mismatch")


def run_persisted_shadow_cycle(
    issuance: UnifiedDecisionIssuance,
    *,
    event_context: CircuitBreakerAnalysis,
    base_asset: str,
    activation: Epoch2ActivationRecord,
    sizing_policy: PositionSizingPolicy,
    journal: R25ShadowIntentJournal,
    manifest: R25ShadowCycleManifest,
    vault_id: PaperVaultId,
    capital_assessed_at_ms: int,
    sized_at_ms: int,
    previewed_at_ms: int,
    risk_inputs: tuple[AcceptedSizingRiskInputs, ...] = (),
    reviewed_method: SizingMethod | None = None,
    reviewed_at_ms: int | None = None,
    market_reference: AcceptedIntentMarketReference | None = None,
    quantity: Decimal | None = None,
    calibrated_probability: CalibratedProbabilityEvidence | None = None,
    tactical_microstructure: TacticalMicrostructureEvidence | None = None,
    opportunity_recovery: OpportunityRecoveryEvidence | None = None,
    reason_codes: tuple[str, ...] = (),
    previous_intent_identity: str | None = None,
) -> PersistedShadowCycleResult:
    """Run the shadow rail and persist its exact immutable cycle manifest."""
    cycle = run_shadow_restart_replay_cycle(
        issuance,
        event_context=event_context,
        base_asset=base_asset,
        activation=activation,
        sizing_policy=sizing_policy,
        journal=journal,
        vault_id=vault_id,
        capital_assessed_at_ms=capital_assessed_at_ms,
        sized_at_ms=sized_at_ms,
        previewed_at_ms=previewed_at_ms,
        risk_inputs=risk_inputs,
        reviewed_method=reviewed_method,
        reviewed_at_ms=reviewed_at_ms,
        market_reference=market_reference,
        quantity=quantity,
        calibrated_probability=calibrated_probability,
        tactical_microstructure=tactical_microstructure,
        opportunity_recovery=opportunity_recovery,
        reason_codes=reason_codes,
        previous_intent_identity=previous_intent_identity,
    )
    manifest_append = manifest.append(cycle)
    manifest_status = manifest.verify_read_only()

    payload = {
        "canonical_epoch2_write_authority": False,
        "cycle_identity": cycle.cycle_identity,
        "engine_version": SHADOW_PERSISTED_CYCLE_ENGINE_VERSION,
        "journal_record_identity": cycle.journal_append.record.record_identity,
        "manifest_identity": manifest_append.record.manifest_identity,
        "preview_identity": cycle.preview.preview_identity,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }
    return PersistedShadowCycleResult(
        persisted_cycle_identity=canonical_sha256(payload),
        cycle=cycle,
        manifest_append=manifest_append,
        manifest_status=manifest_status,
    )


def _persisted_cycle_payload(
    result: PersistedShadowCycleResult,
) -> dict[str, object]:
    return {
        "canonical_epoch2_write_authority": (
            result.canonical_epoch2_write_authority
        ),
        "cycle_identity": result.cycle.cycle_identity,
        "engine_version": result.engine_version,
        "journal_record_identity": (
            result.cycle.journal_append.record.record_identity
        ),
        "manifest_identity": result.manifest_append.record.manifest_identity,
        "preview_identity": result.cycle.preview.preview_identity,
        "production_authority": result.production_authority,
        "real_capital": result.real_capital,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
