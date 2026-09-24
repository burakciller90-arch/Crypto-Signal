"""Replay-safe completion of one pre-outcome WC2 prepared cycle."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.decision_ledger import (
    DecisionLedgerWriteDisposition,
    ImmutableDecisionEvidenceLedger,
)
from crypto_signal.evaluation.live_untouched_forward_operational import (
    issue_accepted_wc2_live_source,
)
from crypto_signal.evaluation.untouched_forward_collection_protocol import (
    WC2CollectionProtocol,
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
    WC2PreparedCycleJournal,
    WC2PreparedCycleReceipt,
    build_wc2_prepared_cycle_receipt,
)
from crypto_signal.ledger.coverage import LiveCoverageContext
from crypto_signal.ledger.live_clock import LiveFreezeResult, LiveFreezeStatus
from crypto_signal.ledger.store import ImmutableSignalLedger
from crypto_signal.paper.epoch2_accounting import Epoch2ActivationRecord
from crypto_signal.paper.models import PaperAction
from crypto_signal.paper.shadow_cycle_manifest import R25ShadowCycleManifest
from crypto_signal.paper.shadow_intent_journal import R25ShadowIntentJournal
from crypto_signal.signals.models import SignalDirection, SignalState

WC2_PREPARED_COMPLETION_ENGINE_VERSION = "wc2-prepared-completion-v1/1"
REAL_CAPITAL = 0


class WC2PreparedLiveStatus(StrEnum):
    COMPLETED_FRESH = "completed_fresh"
    COMPLETED_RECOVERED = "completed_recovered"
    SKIPPED_BEFORE_COLLECTION = "skipped_before_collection"
    SKIPPED_BEFORE_ACTIVATION = "skipped_before_activation"
    SKIPPED_INELIGIBLE_SOURCE = "skipped_ineligible_source"
    NO_PREPARED_RECEIPT = "no_prepared_receipt"


@dataclass(frozen=True, slots=True)
class WC2PreparedLiveResult:
    status: WC2PreparedLiveStatus
    signal_freeze_identity: str | None
    receipt_identity: str | None
    forecast_identity: str | None
    cohort_forecast_identity: str | None
    paper_intent_identity: str | None
    reason_codes: tuple[str, ...]
    historical_market_read_performed: bool = False
    historical_backfill_authority: bool = False
    canonical_epoch2_mutation: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.signal_freeze_identity, "WC2 prepared live signal"),
            (self.receipt_identity, "WC2 prepared live receipt"),
            (self.forecast_identity, "WC2 prepared live forecast"),
            (
                self.cohort_forecast_identity,
                "WC2 prepared live cohort forecast",
            ),
            (self.paper_intent_identity, "WC2 prepared live paper intent"),
        ):
            if value is not None:
                _require_sha256(value, label)
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("WC2 prepared live reasons must be canonical")
        if (
            self.historical_market_read_performed
            or self.historical_backfill_authority
            or self.canonical_epoch2_mutation
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("WC2 prepared live result crossed authority boundary")


def process_wc2_prepared_live_freeze(
    result: LiveFreezeResult,
    *,
    context: LiveCoverageContext,
    signal_ledger: ImmutableSignalLedger,
    policy: WC2UntouchedForwardPolicy,
    activation: Epoch2ActivationRecord,
    protocol: WC2CollectionProtocol,
    prepared_journal: WC2PreparedCycleJournal,
    decision_ledger: ImmutableDecisionEvidenceLedger,
    cohort_journal: WC2CohortJournal,
    shadow_journal: R25ShadowIntentJournal,
    shadow_manifest: R25ShadowCycleManifest,
    observed_at_ms: int,
    base_asset: str,
) -> WC2PreparedLiveResult:
    """Process one live freeze with durable pre-R20 crash recovery."""
    if observed_at_ms < 0:
        raise ValueError("WC2 prepared live observation cannot be negative")
    if protocol.review_policy_identity != policy.policy_identity:
        raise ValueError("WC2 prepared live protocol/policy mismatch")
    if protocol.epoch2_activation_identity != activation.activation_identity:
        raise ValueError("WC2 prepared live protocol/Epoch2 mismatch")
    if context.identity not in protocol.coverage_context_identities:
        raise ValueError("WC2 prepared live context is outside protocol")
    if not base_asset or base_asset != base_asset.upper():
        raise ValueError("WC2 prepared live base asset must be uppercase")
    if not context.symbol.startswith(base_asset):
        raise ValueError("WC2 prepared live context/base asset mismatch")

    if result.status is LiveFreezeStatus.FROZEN:
        return _process_fresh_prepared(
            result,
            policy=policy,
            activation=activation,
            protocol=protocol,
            prepared_journal=prepared_journal,
            decision_ledger=decision_ledger,
            cohort_journal=cohort_journal,
            shadow_journal=shadow_journal,
            shadow_manifest=shadow_manifest,
            observed_at_ms=observed_at_ms,
            base_asset=base_asset,
        )
    if result.status is LiveFreezeStatus.ALREADY_FROZEN:
        return _process_replay_prepared(
            result,
            context=context,
            signal_ledger=signal_ledger,
            policy=policy,
            activation=activation,
            protocol=protocol,
            prepared_journal=prepared_journal,
            decision_ledger=decision_ledger,
            cohort_journal=cohort_journal,
            shadow_journal=shadow_journal,
            shadow_manifest=shadow_manifest,
        )
    raise ValueError("unsupported WC2 prepared live freeze status")


def _process_fresh_prepared(
    result: LiveFreezeResult,
    *,
    policy: WC2UntouchedForwardPolicy,
    activation: Epoch2ActivationRecord,
    protocol: WC2CollectionProtocol,
    prepared_journal: WC2PreparedCycleJournal,
    decision_ledger: ImmutableDecisionEvidenceLedger,
    cohort_journal: WC2CohortJournal,
    shadow_journal: R25ShadowIntentJournal,
    shadow_manifest: R25ShadowCycleManifest,
    observed_at_ms: int,
    base_asset: str,
) -> WC2PreparedLiveResult:
    if result.bundle is None or result.frozen_at_ms is None:
        raise ValueError("fresh WC2 prepared cycle lost exact in-process bundle")
    signal = result.bundle.signal_decision
    if result.frozen_at_ms < protocol.collection_start_ms:
        return _prepared_live_result(
            WC2PreparedLiveStatus.SKIPPED_BEFORE_COLLECTION,
            signal_identity=signal.freeze_identity,
            reasons=("source_freeze_predates_collection_start",),
        )
    if observed_at_ms < protocol.collection_start_ms:
        return _prepared_live_result(
            WC2PreparedLiveStatus.SKIPPED_BEFORE_COLLECTION,
            signal_identity=signal.freeze_identity,
            reasons=("observation_predates_collection_start",),
        )
    if result.frozen_at_ms < activation.activated_at_ms:
        return _prepared_live_result(
            WC2PreparedLiveStatus.SKIPPED_BEFORE_ACTIVATION,
            signal_identity=signal.freeze_identity,
            reasons=("source_freeze_predates_epoch2_activation",),
        )
    if (
        signal.state not in {SignalState.WATCH, SignalState.ACTIVE}
        or signal.direction is SignalDirection.NONE
        or signal.geometry is None
    ):
        return _prepared_live_result(
            WC2PreparedLiveStatus.SKIPPED_INELIGIBLE_SOURCE,
            signal_identity=signal.freeze_identity,
            reasons=("source_not_directional_with_frozen_geometry",),
        )

    receipt = build_wc2_prepared_cycle_receipt(
        result.bundle,
        policy=policy,
        activation=activation,
        protocol=protocol,
        sizing_policy=None,
        source_frozen_at_ms=result.frozen_at_ms,
        issued_at_ms=observed_at_ms,
        base_asset=base_asset,
        capital_assessed_at_ms=observed_at_ms,
        sized_at_ms=observed_at_ms,
        previewed_at_ms=observed_at_ms,
        indexed_at_ms=observed_at_ms,
    )
    prepared_journal.append(receipt)
    completion = complete_wc2_prepared_cycle(
        receipt,
        policy=policy,
        activation=activation,
        protocol=protocol,
        decision_ledger=decision_ledger,
        cohort_journal=cohort_journal,
        shadow_journal=shadow_journal,
        shadow_manifest=shadow_manifest,
    )
    return _prepared_completion_result(
        WC2PreparedLiveStatus.COMPLETED_FRESH,
        signal_identity=signal.freeze_identity,
        receipt=receipt,
        completion=completion,
        reasons=("prepared_before_r20_then_completed",),
    )


def _process_replay_prepared(
    result: LiveFreezeResult,
    *,
    context: LiveCoverageContext,
    signal_ledger: ImmutableSignalLedger,
    policy: WC2UntouchedForwardPolicy,
    activation: Epoch2ActivationRecord,
    protocol: WC2CollectionProtocol,
    prepared_journal: WC2PreparedCycleJournal,
    decision_ledger: ImmutableDecisionEvidenceLedger,
    cohort_journal: WC2CohortJournal,
    shadow_journal: R25ShadowIntentJournal,
    shadow_manifest: R25ShadowCycleManifest,
) -> WC2PreparedLiveResult:
    freeze = signal_ledger.get_freeze_by_source_cutoff(
        exchange=context.exchange.value,
        market_type=context.market_type.value,
        symbol=context.symbol,
        timeframe=context.timeframe,
        source_cutoff_open_time_ms=result.source_cutoff_open_time_ms,
    )
    if freeze is None:
        raise ValueError(
            "already-frozen WC2 prepared source cutoff has no freeze record"
        )
    if freeze.frozen_at_ms < protocol.collection_start_ms:
        return _prepared_live_result(
            WC2PreparedLiveStatus.SKIPPED_BEFORE_COLLECTION,
            signal_identity=freeze.signal_freeze_identity,
            reasons=("source_freeze_predates_collection_start",),
        )
    if freeze.frozen_at_ms < activation.activated_at_ms:
        return _prepared_live_result(
            WC2PreparedLiveStatus.SKIPPED_BEFORE_ACTIVATION,
            signal_identity=freeze.signal_freeze_identity,
            reasons=("source_freeze_predates_epoch2_activation",),
        )
    receipt = prepared_journal.read_for_signal(
        freeze.signal_freeze_identity
    )
    if receipt is None:
        return _prepared_live_result(
            WC2PreparedLiveStatus.NO_PREPARED_RECEIPT,
            signal_identity=freeze.signal_freeze_identity,
            reasons=("no_preoutcome_prepared_receipt_for_source_freeze",),
        )
    if receipt.source_cutoff_open_time_ms != result.source_cutoff_open_time_ms:
        raise ValueError("WC2 prepared receipt/source cutoff mismatch")
    if receipt.collection_protocol_identity != protocol.protocol_identity:
        raise ValueError("WC2 prepared receipt/protocol identity mismatch")
    completion = complete_wc2_prepared_cycle(
        receipt,
        policy=policy,
        activation=activation,
        protocol=protocol,
        decision_ledger=decision_ledger,
        cohort_journal=cohort_journal,
        shadow_journal=shadow_journal,
        shadow_manifest=shadow_manifest,
    )
    return _prepared_completion_result(
        WC2PreparedLiveStatus.COMPLETED_RECOVERED,
        signal_identity=freeze.signal_freeze_identity,
        receipt=receipt,
        completion=completion,
        reasons=("prepared_receipt_recovered_without_market_read",),
    )


def _prepared_completion_result(
    status: WC2PreparedLiveStatus,
    *,
    signal_identity: str,
    receipt: WC2PreparedCycleReceipt,
    completion: WC2PreparedCompletionResult,
    reasons: tuple[str, ...],
) -> WC2PreparedLiveResult:
    return WC2PreparedLiveResult(
        status=status,
        signal_freeze_identity=signal_identity,
        receipt_identity=receipt.receipt_identity,
        forecast_identity=completion.forecast_identity,
        cohort_forecast_identity=completion.cohort_forecast_identity,
        paper_intent_identity=completion.paper_intent_identity,
        reason_codes=tuple(sorted(set(reasons))),
    )


def _prepared_live_result(
    status: WC2PreparedLiveStatus,
    *,
    signal_identity: str | None,
    reasons: tuple[str, ...],
) -> WC2PreparedLiveResult:
    return WC2PreparedLiveResult(
        status=status,
        signal_freeze_identity=signal_identity,
        receipt_identity=None,
        forecast_identity=None,
        cohort_forecast_identity=None,
        paper_intent_identity=None,
        reason_codes=tuple(sorted(set(reasons))),
    )


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
    protocol: WC2CollectionProtocol,
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
    if protocol.protocol_identity != receipt.collection_protocol_identity:
        raise ValueError("WC2 prepared completion protocol identity mismatch")
    if protocol.review_policy_identity != policy.policy_identity:
        raise ValueError("WC2 prepared completion protocol/policy mismatch")
    if protocol.epoch2_activation_identity != activation.activation_identity:
        raise ValueError("WC2 prepared completion protocol/Epoch2 mismatch")
    if (
        receipt.maximum_issuance_delay_ms
        != protocol.maximum_issuance_delay_ms
    ):
        raise ValueError("WC2 prepared receipt issuance-delay mismatch")
    if receipt.horizon_bars != protocol.horizon_bars_for(
        receipt.signal.timeframe
    ):
        raise ValueError("WC2 prepared receipt horizon mismatch")
    if receipt.source_frozen_at_ms < protocol.collection_start_ms:
        raise ValueError("WC2 prepared receipt predates protocol collection")
    if receipt.issued_at_ms < protocol.collection_start_ms:
        raise ValueError("WC2 prepared issuance predates protocol collection")
    if activation.activated_at_ms > receipt.issued_at_ms:
        raise ValueError("WC2 prepared completion activation is too late")

    issuance = issue_accepted_wc2_live_source(
        receipt.signal,
        receipt.source_inputs,
        issued_at_ms=receipt.issued_at_ms,
        horizon_bars=receipt.horizon_bars,
        target_label=receipt.target_label,
        base_asset=receipt.base_asset,
        collection_protocol_identity=protocol.protocol_identity,
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
    if (
        receipt.sizing_policy is None
        and (paper.explicit_review_used or paper.simulated_execution_created)
    ):
        raise ValueError(
            "policy-free WC2 completion cannot create reviewed execution"
        )

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
