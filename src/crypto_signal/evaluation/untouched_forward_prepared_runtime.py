"""Replay-safe completion of one pre-outcome WC2 prepared cycle."""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

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
    WC2PreparedCycleJournal,
    WC2PreparedCycleReceipt,
    build_wc2_prepared_cycle_receipt,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import CircuitBreakerAnalysis
from crypto_signal.ledger.coverage import LiveCoverageContext
from crypto_signal.ledger.deserialization import parse_signal_decision
from crypto_signal.ledger.live_clock import LiveFreezeResult, LiveFreezeStatus
from crypto_signal.ledger.store import FreezeRecord, ImmutableSignalLedger
from crypto_signal.paper.epoch2_accounting import Epoch2ActivationRecord
from crypto_signal.paper.models import PaperAction
from crypto_signal.paper.shadow_cycle_manifest import R25ShadowCycleManifest
from crypto_signal.paper.shadow_intent_journal import R25ShadowIntentJournal
from crypto_signal.signals.models import SignalDecision, SignalDirection, SignalState
from crypto_signal.unified_decision_runtime import UnifiedDecisionIssuance

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


class WC2CapitalIssuanceHook(Protocol):
    def __call__(
        self,
        issuance: UnifiedDecisionIssuance,
        *,
        event_context: CircuitBreakerAnalysis,
        base_asset: str,
        assessed_at_ms: int,
    ) -> object: ...


def process_wc2_prepared_live_freeze(
    result: LiveFreezeResult,
    *,
    context: LiveCoverageContext,
    signal_ledger: ImmutableSignalLedger,
    policy: WC2UntouchedForwardPolicy,
    activation: Epoch2ActivationRecord,
    prepared_journal: WC2PreparedCycleJournal,
    decision_ledger: ImmutableDecisionEvidenceLedger,
    cohort_journal: WC2CohortJournal,
    shadow_journal: R25ShadowIntentJournal,
    shadow_manifest: R25ShadowCycleManifest,
    observed_at_ms: int,
    maximum_issuance_delay_ms: int,
    horizon_bars: int,
    base_asset: str,
    collection_protocol_identity: str,
    collection_start_ms: int | None = None,
    issuance_hook: Callable[[UnifiedDecisionIssuance], object] | None = None,
    capital_hook: WC2CapitalIssuanceHook | None = None,
) -> WC2PreparedLiveResult:
    """Process one live freeze with durable pre-R20 crash recovery."""
    if observed_at_ms < 0:
        raise ValueError("WC2 prepared live observation cannot be negative")
    if maximum_issuance_delay_ms <= 0:
        raise ValueError("WC2 prepared live issuance delay must be positive")
    if horizon_bars <= 0:
        raise ValueError("WC2 prepared live horizon must be positive")
    if not base_asset or base_asset != base_asset.upper():
        raise ValueError("WC2 prepared live base asset must be uppercase")
    if not context.symbol.startswith(base_asset):
        raise ValueError("WC2 prepared live context/base asset mismatch")
    _require_sha256(
        collection_protocol_identity,
        "WC2 prepared live collection protocol",
    )
    effective_collection_start_ms = (
        policy.collection_start_ms
        if collection_start_ms is None
        else collection_start_ms
    )
    if effective_collection_start_ms < policy.collection_start_ms:
        raise ValueError(
            "WC2 operational collection cannot predate review-policy collection"
        )

    if result.status is LiveFreezeStatus.FROZEN:
        return _process_fresh_prepared(
            result,
            policy=policy,
            activation=activation,
            prepared_journal=prepared_journal,
            decision_ledger=decision_ledger,
            cohort_journal=cohort_journal,
            shadow_journal=shadow_journal,
            shadow_manifest=shadow_manifest,
            observed_at_ms=observed_at_ms,
            maximum_issuance_delay_ms=maximum_issuance_delay_ms,
            horizon_bars=horizon_bars,
            base_asset=base_asset,
            collection_protocol_identity=collection_protocol_identity,
            collection_start_ms=effective_collection_start_ms,
            issuance_hook=issuance_hook,
            capital_hook=capital_hook,
        )
    if result.status is LiveFreezeStatus.ALREADY_FROZEN:
        return _process_replay_prepared(
            result,
            context=context,
            signal_ledger=signal_ledger,
            policy=policy,
            activation=activation,
            prepared_journal=prepared_journal,
            decision_ledger=decision_ledger,
            cohort_journal=cohort_journal,
            shadow_journal=shadow_journal,
            shadow_manifest=shadow_manifest,
            collection_protocol_identity=collection_protocol_identity,
            collection_start_ms=effective_collection_start_ms,
            issuance_hook=issuance_hook,
            capital_hook=capital_hook,
        )
    raise ValueError("unsupported WC2 prepared live freeze status")


def _process_fresh_prepared(
    result: LiveFreezeResult,
    *,
    policy: WC2UntouchedForwardPolicy,
    activation: Epoch2ActivationRecord,
    prepared_journal: WC2PreparedCycleJournal,
    decision_ledger: ImmutableDecisionEvidenceLedger,
    cohort_journal: WC2CohortJournal,
    shadow_journal: R25ShadowIntentJournal,
    shadow_manifest: R25ShadowCycleManifest,
    observed_at_ms: int,
    maximum_issuance_delay_ms: int,
    horizon_bars: int,
    base_asset: str,
    collection_protocol_identity: str,
    collection_start_ms: int,
    issuance_hook: Callable[[UnifiedDecisionIssuance], object] | None,
    capital_hook: WC2CapitalIssuanceHook | None,
) -> WC2PreparedLiveResult:
    if result.bundle is None or result.frozen_at_ms is None:
        raise ValueError("fresh WC2 prepared cycle lost exact in-process bundle")
    signal = result.bundle.signal_decision
    if result.frozen_at_ms < collection_start_ms:
        return _prepared_live_result(
            WC2PreparedLiveStatus.SKIPPED_BEFORE_COLLECTION,
            signal_identity=signal.freeze_identity,
            reasons=("source_freeze_predates_collection_start",),
        )
    if observed_at_ms < collection_start_ms:
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
    if not _source_is_prepared_eligible(signal):
        return _prepared_live_result(
            WC2PreparedLiveStatus.SKIPPED_INELIGIBLE_SOURCE,
            signal_identity=signal.freeze_identity,
            reasons=("source_not_directional_with_frozen_geometry",),
        )

    receipt = build_wc2_prepared_cycle_receipt(
        result.bundle,
        policy=policy,
        activation=activation,
        collection_protocol_identity=collection_protocol_identity,
        sizing_policy=None,
        source_frozen_at_ms=result.frozen_at_ms,
        issued_at_ms=observed_at_ms,
        maximum_issuance_delay_ms=maximum_issuance_delay_ms,
        horizon_bars=horizon_bars,
        base_asset=base_asset,
        capital_assessed_at_ms=observed_at_ms + 1,
        sized_at_ms=observed_at_ms + 2,
        previewed_at_ms=observed_at_ms + 3,
        indexed_at_ms=observed_at_ms + 4,
    )
    prepared_journal.append(receipt)
    completion = complete_wc2_prepared_cycle(
        receipt,
        policy=policy,
        activation=activation,
        decision_ledger=decision_ledger,
        cohort_journal=cohort_journal,
        shadow_journal=shadow_journal,
        shadow_manifest=shadow_manifest,
        issuance_hook=issuance_hook,
        capital_hook=capital_hook,
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
    prepared_journal: WC2PreparedCycleJournal,
    decision_ledger: ImmutableDecisionEvidenceLedger,
    cohort_journal: WC2CohortJournal,
    shadow_journal: R25ShadowIntentJournal,
    shadow_manifest: R25ShadowCycleManifest,
    collection_protocol_identity: str,
    collection_start_ms: int,
    issuance_hook: Callable[[UnifiedDecisionIssuance], object] | None,
    capital_hook: WC2CapitalIssuanceHook | None,
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
    if freeze.frozen_at_ms < collection_start_ms:
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
    signal = _signal_from_freeze_record(freeze)
    if not _source_is_prepared_eligible(signal):
        return _prepared_live_result(
            WC2PreparedLiveStatus.SKIPPED_INELIGIBLE_SOURCE,
            signal_identity=freeze.signal_freeze_identity,
            reasons=("source_not_directional_with_frozen_geometry",),
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
    if receipt.collection_protocol_identity != collection_protocol_identity:
        raise ValueError(
            "WC2 prepared receipt/collection protocol identity mismatch"
        )
    completion = complete_wc2_prepared_cycle(
        receipt,
        policy=policy,
        activation=activation,
        decision_ledger=decision_ledger,
        cohort_journal=cohort_journal,
        shadow_journal=shadow_journal,
        shadow_manifest=shadow_manifest,
        issuance_hook=issuance_hook,
        capital_hook=capital_hook,
    )
    return _prepared_completion_result(
        WC2PreparedLiveStatus.COMPLETED_RECOVERED,
        signal_identity=freeze.signal_freeze_identity,
        receipt=receipt,
        completion=completion,
        reasons=("prepared_receipt_recovered_without_market_read",),
    )


def _source_is_prepared_eligible(signal: SignalDecision) -> bool:
    return (
        signal.state in {SignalState.WATCH, SignalState.ACTIVE}
        and signal.direction is not SignalDirection.NONE
        and signal.geometry is not None
    )


def _signal_from_freeze_record(freeze: FreezeRecord) -> SignalDecision:
    raw = json.loads(freeze.bundle_json)
    if not isinstance(raw, dict):
        raise TypeError("WC2 replay freeze bundle must be an object")
    signal = parse_signal_decision(raw.get("signal_decision"))
    expected = (
        freeze.signal_freeze_identity,
        freeze.exchange,
        freeze.market_type,
        freeze.symbol,
        freeze.timeframe,
        freeze.as_of_ms,
        freeze.signal_state,
        freeze.direction,
    )
    actual = (
        signal.freeze_identity,
        signal.exchange.value,
        signal.market_type.value,
        signal.symbol,
        signal.timeframe,
        signal.as_of_ms,
        signal.state.value,
        signal.direction.value,
    )
    if actual != expected:
        raise ValueError("WC2 replay freeze row/bundle signal mismatch")
    return signal


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
    decision_ledger: ImmutableDecisionEvidenceLedger,
    cohort_journal: WC2CohortJournal,
    shadow_journal: R25ShadowIntentJournal,
    shadow_manifest: R25ShadowCycleManifest,
    issuance_hook: Callable[[UnifiedDecisionIssuance], object] | None = None,
    capital_hook: WC2CapitalIssuanceHook | None = None,
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
        collection_protocol_identity=(
            receipt.collection_protocol_identity
        ),
    )
    protocol_ref = next(
        (
            item
            for item in issuance.forecast.version_refs
            if item.component == "wc2_collection_protocol"
        ),
        None,
    )
    if (
        protocol_ref is None
        or protocol_ref.version != receipt.collection_protocol_identity
    ):
        raise ValueError("WC2 R20 collection protocol lineage mismatch")
    if (
        receipt.collection_protocol_identity
        not in issuance.forecast.source_evidence_identities
    ):
        raise ValueError("WC2 R20 protocol source evidence missing")

    cohort = build_wc2_cohort_forecast(
        policy=policy,
        issuance=issuance,
        indexed_at_ms=receipt.indexed_at_ms,
    )
    if (
        receipt.collection_protocol_identity
        not in cohort.source_evidence_identities
    ):
        raise ValueError("WC2 cohort protocol source evidence missing")
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
    if issuance_hook is not None:
        issuance_hook(issuance)
    if capital_hook is not None:
        capital_hook(
            issuance,
            event_context=receipt.source_inputs.event_context,
            base_asset=receipt.base_asset,
            assessed_at_ms=receipt.capital_assessed_at_ms,
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
