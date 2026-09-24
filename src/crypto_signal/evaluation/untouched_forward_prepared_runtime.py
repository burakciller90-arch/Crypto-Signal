"""Replay-safe completion of one pre-outcome WC2 prepared cycle."""
from __future__ import annotations

from dataclasses import dataclass

from crypto_signal.decision_ledger import (
    DecisionLedgerWriteDisposition,
    ImmutableDecisionEvidenceLedger,
)
from crypto_signal.evaluation.live_untouched_forward_operational import (
    issue_accepted_wc2_live_source,
)
from crypto_signal.evaluation.untouched_forward_journal import (
    WC2CohortAppendDisposition,
    WC2CohortJournal,
    build_wc2_cohort_forecast,
)
from crypto_signal.evaluation.untouched_forward_paper import (
    WC2SameCyclePaperResult,
    persist_wc2_same_cycle_hold_cash_intent,
)
from crypto_signal.evaluation.untouched_forward_policy import (
    WC2UntouchedForwardPolicy,
)
from crypto_signal.evaluation.untouched_forward_prepared import (
    WC2PreparedCycleReceipt,
)
from crypto_signal.paper.epoch2_accounting import Epoch2ActivationRecord
from crypto_signal.paper.models import PaperAction
from crypto_signal.paper.shadow_cycle_manifest import R25ShadowCycleManifest
from crypto_signal.paper.shadow_intent_journal import R25ShadowIntentJournal

WC2_PREPARED_COMPLETION_ENGINE_VERSION = "wc2-prepared-completion-v1/1"
REAL_CAPITAL = 0


@dataclass(frozen=True, slots=True)
class WC2PreparedCompletionResult:
    receipt_identity: str
    forecast_identity: str
    cohort_forecast_identity: str
    paper_intent_identity: str
    decision_ledger_disposition: DecisionLedgerWriteDisposition
    cohort_forecast_disposition: WC2CohortAppendDisposition
    cohort_intent_disposition: WC2CohortAppendDisposition
    action: PaperAction
    historical_market_read_performed: bool = False
    historical_backfill_authority: bool = False
    canonical_epoch2_mutation: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL
    engine_version: str = WC2_PREPARED_COMPLETION_ENGINE_VERSION

    def __post_init__(self) -> None:
        for value, label in (
            (self.receipt_identity, "WC2 completion receipt"),
            (self.forecast_identity, "WC2 completion forecast"),
            (self.cohort_forecast_identity, "WC2 completion cohort forecast"),
            (self.paper_intent_identity, "WC2 completion paper intent"),
        ):
            _require_sha256(value, label)
        if self.action is not PaperAction.HOLD_CASH:
            raise ValueError("WC2 prepared completion must remain HOLD_CASH")
        if (
            self.historical_market_read_performed
            or self.historical_backfill_authority
            or self.canonical_epoch2_mutation
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("WC2 prepared completion crossed authority boundary")
        if self.engine_version != WC2_PREPARED_COMPLETION_ENGINE_VERSION:
            raise ValueError("unsupported WC2 prepared completion engine")


def complete_wc2_prepared_cycle(
    receipt: WC2PreparedCycleReceipt,
    *,
    policy: WC2UntouchedForwardPolicy,
    activation: Epoch2ActivationRecord,
    decision_ledger: ImmutableDecisionEvidenceLedger,
    cohort_journal: WC2CohortJournal,
    shadow_journal: R25ShadowIntentJournal,
    shadow_manifest: R25ShadowCycleManifest,
) -> WC2PreparedCompletionResult:
    """Flush one pre-outcome receipt without any new market-data read."""
    if policy.policy_identity != receipt.policy_identity:
        raise ValueError("WC2 prepared completion policy identity mismatch")
    if activation.activation_identity != receipt.activation_identity:
        raise ValueError("WC2 prepared completion activation identity mismatch")
    if activation.activated_at_ms > receipt.issued_at_ms:
        raise ValueError("WC2 prepared completion activation is too late")

    issuance = issue_accepted_wc2_live_source(
        receipt.signal,
        receipt.source_inputs,
        issued_at_ms=receipt.issued_at_ms,
        horizon_bars=receipt.horizon_bars,
        target_label=receipt.target_label,
        base_asset=receipt.base_asset,
        ledger=decision_ledger,
    )
    cohort = build_wc2_cohort_forecast(
        policy=policy,
        issuance=issuance,
        indexed_at_ms=receipt.indexed_at_ms,
    )
    cohort_forecast_disposition = cohort_journal.append_forecast(cohort)

    paper = persist_wc2_same_cycle_hold_cash_intent(
        issuance,
        cohort,
        event_context=receipt.source_inputs.event_context,
        base_asset=receipt.base_asset,
        activation=activation,
        sizing_policy=receipt.sizing_policy,
        shadow_journal=shadow_journal,
        shadow_manifest=shadow_manifest,
        cohort_journal=cohort_journal,
        capital_assessed_at_ms=receipt.capital_assessed_at_ms,
        sized_at_ms=receipt.sized_at_ms,
        previewed_at_ms=receipt.previewed_at_ms,
        indexed_at_ms=receipt.indexed_at_ms,
    )
    _validate_paper(receipt, paper)

    return WC2PreparedCompletionResult(
        receipt_identity=receipt.receipt_identity,
        forecast_identity=issuance.forecast.forecast_identity,
        cohort_forecast_identity=cohort.cohort_forecast_identity,
        paper_intent_identity=paper.paper_intent_identity,
        decision_ledger_disposition=issuance.ledger_disposition,
        cohort_forecast_disposition=cohort_forecast_disposition,
        cohort_intent_disposition=paper.cohort_intent_disposition,
        action=paper.action,
    )


def _validate_paper(
    receipt: WC2PreparedCycleReceipt,
    paper: WC2SameCyclePaperResult,
) -> None:
    if paper.forecast_identity == "":
        raise ValueError("WC2 prepared paper lost forecast identity")
    if paper.action is not PaperAction.HOLD_CASH:
        raise ValueError("WC2 prepared paper unexpectedly created trade")
    if (
        paper.simulated_execution_created
        or paper.explicit_review_used
        or paper.canonical_epoch2_mutation
        or paper.production_authority
        or paper.real_capital != REAL_CAPITAL
    ):
        raise ValueError("WC2 prepared paper crossed authority boundary")
    if receipt.vault_id is not paper.vault_id:
        raise ValueError("WC2 prepared paper vault mismatch")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
