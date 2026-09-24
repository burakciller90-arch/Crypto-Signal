"""WC2 same-cycle paper-decision linkage on the accepted R25 shadow rail.

This module does not select a sizing winner, does not fabricate risk inputs and
does not write canonical Epoch2 accounting. It binds every accepted WC2
forecast to an explicit HOLD_CASH paper intent unless a later separately
accepted program supplies an explicit reviewed trade selection.
REAL_CAPITAL=0.
"""
from __future__ import annotations

from dataclasses import dataclass

from crypto_signal.evaluation.untouched_forward_journal import (
    WC2CohortAppendDisposition,
    WC2CohortForecast,
    WC2CohortIntent,
    WC2CohortJournal,
    build_wc2_cohort_intent,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CircuitBreakerAnalysis,
)
from crypto_signal.paper.epoch2_accounting import Epoch2ActivationRecord
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import PaperAction
from crypto_signal.paper.position_sizing_intelligence import PositionSizingPolicy
from crypto_signal.paper.shadow_cycle_manifest import R25ShadowCycleManifest
from crypto_signal.paper.shadow_cycle_runtime import (
    PersistedShadowCycleResult,
    run_persisted_shadow_cycle,
)
from crypto_signal.paper.shadow_intent_journal import R25ShadowIntentJournal
from crypto_signal.unified_decision_runtime import UnifiedDecisionIssuance

WC2_SAME_CYCLE_PAPER_ENGINE_VERSION = "wc2-same-cycle-paper-v1/1"
REAL_CAPITAL = 0


@dataclass(frozen=True, slots=True)
class WC2SameCyclePaperResult:
    forecast_identity: str
    cohort_forecast_identity: str
    paper_intent_identity: str
    intent_link_identity: str
    persisted_shadow_cycle_identity: str
    shadow_manifest_identity: str
    cohort_intent_disposition: WC2CohortAppendDisposition
    action: PaperAction
    vault_id: PaperVaultId
    simulated_execution_created: bool = False
    explicit_review_used: bool = False
    canonical_epoch2_mutation: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL
    engine_version: str = WC2_SAME_CYCLE_PAPER_ENGINE_VERSION

    def __post_init__(self) -> None:
        for value, label in (
            (self.forecast_identity, "WC2 paper forecast"),
            (self.cohort_forecast_identity, "WC2 paper cohort forecast"),
            (self.paper_intent_identity, "WC2 paper intent"),
            (self.intent_link_identity, "WC2 cohort intent link"),
            (
                self.persisted_shadow_cycle_identity,
                "WC2 persisted shadow cycle",
            ),
            (self.shadow_manifest_identity, "WC2 shadow manifest"),
        ):
            _require_sha256(value, label)
        if self.action is not PaperAction.HOLD_CASH:
            raise ValueError("WC2 Slice1 same-cycle paper decision must HOLD_CASH")
        if self.vault_id is not PaperVaultId.CORE:
            raise ValueError("WC2 Slice1 paper decision is bound to CORE vault")
        if (
            self.simulated_execution_created
            or self.explicit_review_used
            or self.canonical_epoch2_mutation
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("WC2 same-cycle paper result crossed authority boundary")
        if self.engine_version != WC2_SAME_CYCLE_PAPER_ENGINE_VERSION:
            raise ValueError("unsupported WC2 same-cycle paper engine")


def persist_wc2_same_cycle_hold_cash_intent(
    issuance: UnifiedDecisionIssuance,
    cohort_forecast: WC2CohortForecast,
    *,
    event_context: CircuitBreakerAnalysis,
    base_asset: str,
    activation: Epoch2ActivationRecord,
    sizing_policy: PositionSizingPolicy | None,
    shadow_journal: R25ShadowIntentJournal,
    shadow_manifest: R25ShadowCycleManifest,
    cohort_journal: WC2CohortJournal,
    capital_assessed_at_ms: int,
    sized_at_ms: int,
    previewed_at_ms: int,
    indexed_at_ms: int,
) -> WC2SameCyclePaperResult:
    """Persist one explicit HOLD_CASH paper decision for a WC2 forecast.

    Risk inputs, reviewed sizing selection, market reference and quantity are
    deliberately absent. The accepted R25 rail therefore records the decision
    without inventing measurements or creating a simulated fill.
    """
    forecast = issuance.forecast
    if cohort_forecast.forecast_identity != forecast.forecast_identity:
        raise ValueError("WC2 paper cohort/forecast lineage mismatch")
    if cohort_forecast.proof_identity != issuance.proof.proof_identity:
        raise ValueError("WC2 paper cohort/proof lineage mismatch")
    if activation.activated_at_ms > forecast.issued_at_ms:
        raise ValueError(
            "WC2 paper Epoch2 activation must predate forecast issuance"
        )
    if event_context.evidence_identity != forecast.event_context_identity:
        raise ValueError("WC2 paper event context/forecast lineage mismatch")
    if event_context.as_of_ms != forecast.source_as_of_ms:
        raise ValueError("WC2 paper event context PIT mismatch")
    if indexed_at_ms < previewed_at_ms:
        raise ValueError("WC2 cohort intent index cannot predate preview")
    if not base_asset or base_asset != base_asset.upper():
        raise ValueError("WC2 paper base asset must be uppercase")
    if not forecast.symbol.startswith(base_asset):
        raise ValueError("WC2 paper base asset/forecast mismatch")

    persisted = run_persisted_shadow_cycle(
        issuance,
        event_context=event_context,
        base_asset=base_asset,
        activation=activation,
        sizing_policy=sizing_policy,
        journal=shadow_journal,
        manifest=shadow_manifest,
        vault_id=PaperVaultId.CORE,
        capital_assessed_at_ms=capital_assessed_at_ms,
        sized_at_ms=sized_at_ms,
        previewed_at_ms=previewed_at_ms,
        risk_inputs=(),
        reviewed_method=None,
        reviewed_at_ms=None,
        market_reference=None,
        quantity=None,
        calibrated_probability=None,
        tactical_microstructure=None,
        opportunity_recovery=None,
        reason_codes=(
            "wc2_explicit_hold_cash_without_reviewed_sizing",
            "wc2_no_fabricated_risk_or_execution_evidence",
            (
                "wc2_no_numeric_sizing_policy_applicable"
                if sizing_policy is None
                else "wc2_explicit_sizing_policy_present"
            ),
        ),
    )
    if persisted.cycle.preview.intent.action is not PaperAction.HOLD_CASH:
        raise ValueError("WC2 unreviewed paper rail must resolve to HOLD_CASH")
    if persisted.cycle.reviewed_selection is not None:
        raise ValueError("WC2 Slice1 cannot fabricate reviewed sizing selection")
    if persisted.cycle.preview.decision is not None:
        raise ValueError("WC2 HOLD_CASH preview cannot carry trade decision")

    intent = build_wc2_cohort_intent(
        cohort_forecast,
        persisted,
        indexed_at_ms=indexed_at_ms,
    )
    disposition = cohort_journal.append_intent(intent)
    _validate_intent(intent, persisted)

    return WC2SameCyclePaperResult(
        forecast_identity=forecast.forecast_identity,
        cohort_forecast_identity=cohort_forecast.cohort_forecast_identity,
        paper_intent_identity=intent.paper_intent_identity,
        intent_link_identity=intent.intent_link_identity,
        persisted_shadow_cycle_identity=persisted.persisted_cycle_identity,
        shadow_manifest_identity=(
            persisted.manifest_append.record.manifest_identity
        ),
        cohort_intent_disposition=disposition,
        action=intent.action,
        vault_id=intent.vault_id,
    )


def _validate_intent(
    intent: WC2CohortIntent,
    persisted: PersistedShadowCycleResult,
) -> None:
    if intent.action is not PaperAction.HOLD_CASH:
        raise ValueError("WC2 same-cycle intent must remain HOLD_CASH")
    if intent.vault_id is not PaperVaultId.CORE:
        raise ValueError("WC2 same-cycle intent must use CORE vault")
    if intent.paper_intent_identity != persisted.cycle.preview.intent.intent_identity:
        raise ValueError("WC2 cohort intent/paper intent identity mismatch")
    if intent.persisted_cycle_identity != persisted.persisted_cycle_identity:
        raise ValueError("WC2 cohort intent/persisted cycle mismatch")
    if (
        intent.production_authority
        or intent.real_capital != REAL_CAPITAL
        or persisted.production_authority
        or persisted.real_capital != REAL_CAPITAL
    ):
        raise ValueError("WC2 same-cycle intent cannot grant authority")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
