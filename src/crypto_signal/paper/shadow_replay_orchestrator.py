"""R25 Slice 10: deterministic shadow restart/replay orchestration.

Runs the accepted immutable decision -> Capital Science -> Position Sizing ->
explicit review -> R22 preview -> isolated shadow journal path. Replaying the
same immutable inputs after process restart must reproduce the same identities
and become an idempotent journal append. No canonical paper mutation occurs.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CircuitBreakerAnalysis,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.capital_science_bridge import (
    CapitalScienceBridgeResult,
    assess_unified_decision_capital,
)
from crypto_signal.paper.epoch2_accounting import Epoch2ActivationRecord
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.position_sizing_bridge import (
    AcceptedSizingRiskInputs,
    PositionSizingBridgeResult,
    SizingBridgeState,
    assess_capital_position_sizing,
)
from crypto_signal.paper.position_sizing_intelligence import (
    PositionSizingPolicy,
    SizingMethod,
    SizingMethodStatus,
)
from crypto_signal.paper.r22_intent_preview import (
    AcceptedIntentMarketReference,
    R22IntentPreview,
    ReviewedSizingSelection,
    build_r22_intent_preview,
    build_reviewed_sizing_selection,
)
from crypto_signal.paper.shadow_intent_journal import (
    R25ShadowIntentJournal,
    ShadowIntentAppendResult,
    ShadowIntentJournalStatus,
)
from crypto_signal.paper.smart_capital_allocator import (
    OpportunityRecoveryEvidence,
    TacticalMicrostructureEvidence,
)
from crypto_signal.unified_decision_runtime import UnifiedDecisionIssuance

if TYPE_CHECKING:
    from research.alpha_factory.probability_calibration_gate import (
        CalibratedProbabilityEvidence,
    )

SHADOW_REPLAY_ENGINE_VERSION = "r25-shadow-restart-replay-v1/1"
REAL_CAPITAL = 0


@dataclass(frozen=True, slots=True)
class ShadowReplayCycleResult:
    cycle_identity: str
    forecast_identity: str
    proof_identity: str
    capital: CapitalScienceBridgeResult
    sizing: PositionSizingBridgeResult
    reviewed_selection: ReviewedSizingSelection | None
    preview: R22IntentPreview
    journal_append: ShadowIntentAppendResult
    journal_status: ShadowIntentJournalStatus
    vault_id: PaperVaultId
    reviewed_method: SizingMethod | None
    engine_version: str = SHADOW_REPLAY_ENGINE_VERSION
    canonical_epoch2_write_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.cycle_identity, "shadow replay cycle")
        if self.engine_version != SHADOW_REPLAY_ENGINE_VERSION:
            raise ValueError("unsupported shadow replay engine")
        if self.capital.forecast_identity != self.forecast_identity:
            raise ValueError("shadow replay capital/forecast mismatch")
        if self.capital.proof_identity != self.proof_identity:
            raise ValueError("shadow replay capital/proof mismatch")
        if self.sizing.forecast_identity != self.forecast_identity:
            raise ValueError("shadow replay sizing/forecast mismatch")
        if self.sizing.proof_identity != self.proof_identity:
            raise ValueError("shadow replay sizing/proof mismatch")
        if self.sizing.capital_bridge_identity != self.capital.bridge_identity:
            raise ValueError("shadow replay sizing/capital mismatch")
        if self.preview.forecast_identity != self.forecast_identity:
            raise ValueError("shadow replay preview/forecast mismatch")
        if self.preview.proof_identity != self.proof_identity:
            raise ValueError("shadow replay preview/proof mismatch")
        if self.preview.sizing_bridge_identity != self.sizing.bridge_identity:
            raise ValueError("shadow replay preview/sizing mismatch")
        if self.preview.intent.vault_id is not self.vault_id:
            raise ValueError("shadow replay preview vault mismatch")
        if self.journal_append.record.preview_identity != self.preview.preview_identity:
            raise ValueError("shadow replay journal/preview mismatch")
        if self.reviewed_selection is None:
            if self.reviewed_method is not None:
                raise ValueError("shadow replay method requires reviewed selection")
        else:
            if self.reviewed_method is None:
                raise ValueError("shadow replay selection requires reviewed method")
            if self.reviewed_selection.method is not self.reviewed_method:
                raise ValueError("shadow replay reviewed method mismatch")
        if self.journal_status.record_count <= 0:
            raise ValueError("shadow replay journal status lost appended evidence")
        if (
            self.canonical_epoch2_write_authority
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("shadow replay cannot grant canonical/production authority")
        if self.cycle_identity != canonical_sha256(_cycle_payload(self)):
            raise ValueError("shadow replay cycle identity mismatch")


def run_shadow_restart_replay_cycle(
    issuance: UnifiedDecisionIssuance,
    *,
    event_context: CircuitBreakerAnalysis,
    base_asset: str,
    activation: Epoch2ActivationRecord,
    sizing_policy: PositionSizingPolicy,
    journal: R25ShadowIntentJournal,
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
) -> ShadowReplayCycleResult:
    """Run one deterministic development/shadow cycle and append its preview."""
    capital = assess_unified_decision_capital(
        issuance,
        event_context=event_context,
        base_asset=base_asset,
        assessed_at_ms=capital_assessed_at_ms,
        tactical_microstructure=tactical_microstructure,
        opportunity_recovery=opportunity_recovery,
    )
    sizing = assess_capital_position_sizing(
        issuance,
        capital,
        policy=sizing_policy,
        sized_at_ms=sized_at_ms,
        risk_inputs=risk_inputs,
        calibrated_probability=calibrated_probability,
    )

    selection: ReviewedSizingSelection | None = None
    if reviewed_method is not None:
        if reviewed_at_ms is None:
            raise ValueError("reviewed method requires explicit review timestamp")
        vault_result = next(
            (item for item in sizing.vault_results if item.vault_id is vault_id),
            None,
        )
        if vault_result is None:
            raise ValueError("shadow replay unknown vault")
        if (
            vault_result.state is not SizingBridgeState.ASSESSED_SHADOW
            or vault_result.assessment is None
        ):
            raise ValueError("reviewed method requires assessed shadow vault")
        selected = next(
            (
                item
                for item in vault_result.assessment.results
                if item.method is reviewed_method
            ),
            None,
        )
        if selected is None:
            raise ValueError("reviewed sizing method missing from assessment")
        if selected.status is not SizingMethodStatus.AVAILABLE_SHADOW:
            raise ValueError("reviewed sizing method is not AVAILABLE_SHADOW")
        selection = build_reviewed_sizing_selection(
            sizing,
            vault_id=vault_id,
            sizing_result_identity=selected.result_identity,
            reviewed_at_ms=reviewed_at_ms,
        )
    elif reviewed_at_ms is not None:
        raise ValueError("review timestamp cannot exist without reviewed method")

    preview = build_r22_intent_preview(
        issuance,
        sizing,
        activation,
        vault_id=vault_id,
        previewed_at_ms=previewed_at_ms,
        reviewed_selection=selection,
        market_reference=market_reference,
        quantity=quantity,
        reason_codes=reason_codes,
        previous_intent_identity=previous_intent_identity,
    )
    append = journal.append(preview)
    status = journal.verify_read_only()

    payload = {
        "canonical_epoch2_write_authority": False,
        "capital_bridge_identity": capital.bridge_identity,
        "engine_version": SHADOW_REPLAY_ENGINE_VERSION,
        "forecast_identity": issuance.forecast.forecast_identity,
        "journal_record_identity": append.record.record_identity,
        "preview_identity": preview.preview_identity,
        "production_authority": False,
        "proof_identity": issuance.proof.proof_identity,
        "real_capital": REAL_CAPITAL,
        "review_selection_identity": (
            None if selection is None else selection.selection_identity
        ),
        "reviewed_method": reviewed_method,
        "sizing_bridge_identity": sizing.bridge_identity,
        "vault_id": vault_id,
    }
    return ShadowReplayCycleResult(
        cycle_identity=canonical_sha256(payload),
        forecast_identity=issuance.forecast.forecast_identity,
        proof_identity=issuance.proof.proof_identity,
        capital=capital,
        sizing=sizing,
        reviewed_selection=selection,
        preview=preview,
        journal_append=append,
        journal_status=status,
        vault_id=vault_id,
        reviewed_method=reviewed_method,
    )


def _cycle_payload(result: ShadowReplayCycleResult) -> dict[str, object]:
    return {
        "canonical_epoch2_write_authority": (
            result.canonical_epoch2_write_authority
        ),
        "capital_bridge_identity": result.capital.bridge_identity,
        "engine_version": result.engine_version,
        "forecast_identity": result.forecast_identity,
        "journal_record_identity": result.journal_append.record.record_identity,
        "preview_identity": result.preview.preview_identity,
        "production_authority": result.production_authority,
        "proof_identity": result.proof_identity,
        "real_capital": result.real_capital,
        "review_selection_identity": (
            None
            if result.reviewed_selection is None
            else result.reviewed_selection.selection_identity
        ),
        "reviewed_method": result.reviewed_method,
        "sizing_bridge_identity": result.sizing.bridge_identity,
        "vault_id": result.vault_id,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
