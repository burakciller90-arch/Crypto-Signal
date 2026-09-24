"""Crash-safe WC2 untouched-forward forecast indexing.

Fresh source cycles may issue a new immutable R20 forecast. Replay cycles may
only recover an R20 forecast that was already persisted during its original
fresh cycle; they never recreate historical forecasts from a stored bundle.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from crypto_signal.decision_ledger import (
    DecisionLedgerWriteDisposition,
    ImmutableDecisionEvidenceLedger,
)
from crypto_signal.evaluation.live_untouched_forward_operational import (
    WC2_LIVE_SOURCE_ADAPTER_VERSION,
    WC2_UNMEASURED_REGIME,
    issue_same_cycle_untouched_forward_forecast,
)
from crypto_signal.evaluation.untouched_forward_journal import (
    WC2_COHORT_ENGINE_VERSION,
    WC2_COHORT_SCHEMA_VERSION,
    WC2CohortAppendDisposition,
    WC2CohortForecast,
    WC2CohortJournal,
    build_wc2_cohort_forecast,
)
from crypto_signal.evaluation.untouched_forward_policy import (
    WC2UntouchedForwardPolicy,
)
from crypto_signal.ledger.coverage import LiveCoverageContext
from crypto_signal.ledger.live_clock import LiveFreezeResult, LiveFreezeStatus
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.ledger.store import ImmutableSignalLedger
from crypto_signal.outcomes.models import EvidenceClass
from crypto_signal.signals.models import SignalDirection, SignalState

WC2_LIVE_RUNTIME_ENGINE_VERSION = "wc2-live-runtime-index-v1/1"
WC2_LIVE_SOURCE_VERSION_COMPONENT = "wc2_live_source_adapter"
REAL_CAPITAL = 0


class WC2LiveIndexStatus(StrEnum):
    INDEXED_FRESH = "indexed_fresh"
    INDEXED_RECOVERED = "indexed_recovered"
    ALREADY_INDEXED = "already_indexed"
    SKIPPED_BEFORE_COLLECTION = "skipped_before_collection"
    SKIPPED_INELIGIBLE_SOURCE = "skipped_ineligible_source"
    NO_PERSISTED_ISSUANCE = "no_persisted_issuance"


@dataclass(frozen=True, slots=True)
class WC2LiveIndexResult:
    status: WC2LiveIndexStatus
    signal_freeze_identity: str | None
    forecast_identity: str | None
    cohort_forecast_identity: str | None
    decision_ledger_disposition: DecisionLedgerWriteDisposition | None
    cohort_disposition: WC2CohortAppendDisposition | None
    reason_codes: tuple[str, ...]
    historical_forecast_created: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL
    engine_version: str = WC2_LIVE_RUNTIME_ENGINE_VERSION

    def __post_init__(self) -> None:
        for identity in (
            self.signal_freeze_identity,
            self.forecast_identity,
            self.cohort_forecast_identity,
        ):
            if identity is not None:
                _require_sha256(identity, "WC2 live index identity")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("WC2 live index reasons must be canonical")
        if self.historical_forecast_created:
            raise ValueError("WC2 runtime cannot create historical forecasts")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("WC2 live index cannot grant authority")
        if self.engine_version != WC2_LIVE_RUNTIME_ENGINE_VERSION:
            raise ValueError("unsupported WC2 live index engine")


def process_wc2_live_freeze(
    result: LiveFreezeResult,
    *,
    context: LiveCoverageContext,
    signal_ledger: ImmutableSignalLedger,
    policy: WC2UntouchedForwardPolicy,
    decision_ledger: ImmutableDecisionEvidenceLedger,
    cohort_journal: WC2CohortJournal,
    observed_at_ms: int,
    maximum_issuance_delay_ms: int,
    horizon_bars: int,
    base_asset: str,
) -> WC2LiveIndexResult:
    """Index one live freeze without retrospective forecast creation."""
    if observed_at_ms < 0:
        raise ValueError("WC2 runtime observation time cannot be negative")
    if maximum_issuance_delay_ms <= 0:
        raise ValueError("WC2 runtime issuance delay must be positive")
    if horizon_bars <= 0:
        raise ValueError("WC2 runtime horizon must be positive")
    if not base_asset or base_asset != base_asset.upper():
        raise ValueError("WC2 runtime base asset must be uppercase")
    if context.symbol.startswith(base_asset) is False:
        raise ValueError("WC2 runtime context/base asset mismatch")

    if result.status is LiveFreezeStatus.FROZEN:
        return _process_fresh(
            result,
            policy=policy,
            decision_ledger=decision_ledger,
            cohort_journal=cohort_journal,
            observed_at_ms=observed_at_ms,
            maximum_issuance_delay_ms=maximum_issuance_delay_ms,
            horizon_bars=horizon_bars,
            base_asset=base_asset,
        )
    if result.status is not LiveFreezeStatus.ALREADY_FROZEN:
        raise ValueError("unsupported live freeze status")
    return _recover_persisted(
        result,
        context=context,
        signal_ledger=signal_ledger,
        policy=policy,
        decision_ledger=decision_ledger,
        cohort_journal=cohort_journal,
        observed_at_ms=observed_at_ms,
    )


def _process_fresh(
    result: LiveFreezeResult,
    *,
    policy: WC2UntouchedForwardPolicy,
    decision_ledger: ImmutableDecisionEvidenceLedger,
    cohort_journal: WC2CohortJournal,
    observed_at_ms: int,
    maximum_issuance_delay_ms: int,
    horizon_bars: int,
    base_asset: str,
) -> WC2LiveIndexResult:
    if result.bundle is None or result.frozen_at_ms is None:
        raise ValueError("fresh WC2 cycle lost exact in-process bundle")
    signal = result.bundle.signal_decision
    if result.frozen_at_ms < policy.collection_start_ms:
        return _result(
            WC2LiveIndexStatus.SKIPPED_BEFORE_COLLECTION,
            signal_identity=signal.freeze_identity,
            reasons=("source_freeze_predates_collection_start",),
        )
    if observed_at_ms < policy.collection_start_ms:
        return _result(
            WC2LiveIndexStatus.SKIPPED_BEFORE_COLLECTION,
            signal_identity=signal.freeze_identity,
            reasons=("observation_predates_collection_start",),
        )
    if (
        signal.state not in {SignalState.WATCH, SignalState.ACTIVE}
        or signal.geometry is None
        or signal.direction is SignalDirection.NONE
    ):
        return _result(
            WC2LiveIndexStatus.SKIPPED_INELIGIBLE_SOURCE,
            signal_identity=signal.freeze_identity,
            reasons=("source_not_directional_with_frozen_geometry",),
        )

    issuance = issue_same_cycle_untouched_forward_forecast(
        result.bundle,
        frozen_at_ms=result.frozen_at_ms,
        issued_at_ms=observed_at_ms,
        maximum_issuance_delay_ms=maximum_issuance_delay_ms,
        horizon_bars=horizon_bars,
        base_asset=base_asset,
        ledger=decision_ledger,
    )
    existing = cohort_journal.find_forecast_identity(
        issuance.forecast.forecast_identity
    )
    if existing is not None:
        return _result(
            WC2LiveIndexStatus.ALREADY_INDEXED,
            signal_identity=signal.freeze_identity,
            forecast_identity=issuance.forecast.forecast_identity,
            cohort_identity=existing,
            decision_disposition=issuance.ledger_disposition,
            reasons=("cohort_forecast_already_persisted",),
        )

    cohort = build_wc2_cohort_forecast(
        policy=policy,
        issuance=issuance,
        indexed_at_ms=observed_at_ms,
    )
    disposition = cohort_journal.append_forecast(cohort)
    return _result(
        WC2LiveIndexStatus.INDEXED_FRESH,
        signal_identity=signal.freeze_identity,
        forecast_identity=issuance.forecast.forecast_identity,
        cohort_identity=cohort.cohort_forecast_identity,
        decision_disposition=issuance.ledger_disposition,
        cohort_disposition=disposition,
        reasons=("same_cycle_r20_and_cohort_indexed",),
    )


def _recover_persisted(
    result: LiveFreezeResult,
    *,
    context: LiveCoverageContext,
    signal_ledger: ImmutableSignalLedger,
    policy: WC2UntouchedForwardPolicy,
    decision_ledger: ImmutableDecisionEvidenceLedger,
    cohort_journal: WC2CohortJournal,
    observed_at_ms: int,
) -> WC2LiveIndexResult:
    freeze = signal_ledger.get_freeze_by_source_cutoff(
        exchange=context.exchange.value,
        market_type=context.market_type.value,
        symbol=context.symbol,
        timeframe=context.timeframe,
        source_cutoff_open_time_ms=result.source_cutoff_open_time_ms,
    )
    if freeze is None:
        raise ValueError("already-frozen WC2 source cutoff has no freeze record")
    if freeze.frozen_at_ms < policy.collection_start_ms:
        return _result(
            WC2LiveIndexStatus.SKIPPED_BEFORE_COLLECTION,
            signal_identity=freeze.signal_freeze_identity,
            reasons=("source_freeze_predates_collection_start",),
        )
    if not decision_ledger.path.is_file():
        return _result(
            WC2LiveIndexStatus.NO_PERSISTED_ISSUANCE,
            signal_identity=freeze.signal_freeze_identity,
            reasons=("decision_evidence_database_missing",),
        )

    issuance = decision_ledger.read_issuance_for_signal(
        freeze.signal_freeze_identity
    )
    if issuance is None:
        return _result(
            WC2LiveIndexStatus.NO_PERSISTED_ISSUANCE,
            signal_identity=freeze.signal_freeze_identity,
            reasons=("no_preoutcome_r20_issuance_for_source_freeze",),
        )
    forecast, proof = issuance
    forecast_identity = _raw_sha(forecast, "forecast_identity")
    existing = cohort_journal.find_forecast_identity(forecast_identity)
    if existing is not None:
        return _result(
            WC2LiveIndexStatus.ALREADY_INDEXED,
            signal_identity=freeze.signal_freeze_identity,
            forecast_identity=forecast_identity,
            cohort_identity=existing,
            reasons=("cohort_forecast_already_persisted",),
        )

    cohort = _recovered_cohort_forecast(
        policy=policy,
        forecast=forecast,
        proof=proof,
        expected_signal_identity=freeze.signal_freeze_identity,
        indexed_at_ms=observed_at_ms,
    )
    disposition = cohort_journal.append_forecast(cohort)
    return _result(
        WC2LiveIndexStatus.INDEXED_RECOVERED,
        signal_identity=freeze.signal_freeze_identity,
        forecast_identity=forecast_identity,
        cohort_identity=cohort.cohort_forecast_identity,
        cohort_disposition=disposition,
        reasons=("persisted_preoutcome_r20_recovered_without_reissuance",),
    )


def _recovered_cohort_forecast(
    *,
    policy: WC2UntouchedForwardPolicy,
    forecast: dict[str, Any],
    proof: dict[str, Any],
    expected_signal_identity: str,
    indexed_at_ms: int,
) -> WC2CohortForecast:
    if _raw_sha(forecast, "signal_freeze_identity") != expected_signal_identity:
        raise ValueError("WC2 recovered R20 signal lineage mismatch")
    forecast_identity = _raw_sha(forecast, "forecast_identity")
    if _raw_sha(proof, "forecast_identity") != forecast_identity:
        raise ValueError("WC2 recovered proof/forecast lineage mismatch")
    if _raw_sha(proof, "signal_freeze_identity") != expected_signal_identity:
        raise ValueError("WC2 recovered proof/signal lineage mismatch")

    issued_at_ms = _raw_int(forecast, "issued_at_ms")
    if issued_at_ms < policy.collection_start_ms:
        raise ValueError("WC2 recovered forecast predates collection start")
    if indexed_at_ms < issued_at_ms:
        raise ValueError("WC2 recovery index predates original issuance")
    _require_wc2_source_version(forecast)

    asset = _raw_text(forecast, "asset")
    symbol = _raw_text(forecast, "symbol")
    timeframe = _raw_text(forecast, "timeframe")
    confluence_identity = _raw_sha(forecast, "confluence_identity")
    event_context_identity = _raw_sha(forecast, "event_context_identity")
    proof_identity = _raw_sha(proof, "proof_identity")
    proof_confluence = _raw_sha(proof, "confluence_identity")
    proof_event = _raw_sha(proof, "event_context_identity")
    if proof_confluence != confluence_identity or proof_event != event_context_identity:
        raise ValueError("WC2 recovered proof context lineage mismatch")
    if _raw_int(proof, "issued_at_ms") != issued_at_ms:
        raise ValueError("WC2 recovered proof issuance time mismatch")
    if (
        _raw_text(proof, "asset") != asset
        or _raw_text(proof, "symbol") != symbol
        or _raw_text(proof, "timeframe") != timeframe
    ):
        raise ValueError("WC2 recovered proof market context mismatch")

    source_ids = _raw_identity_list(
        forecast,
        "source_evidence_identities",
    )
    sources = tuple(
        sorted(
            {
                *source_ids,
                proof_identity,
                confluence_identity,
                event_context_identity,
            }
        )
    )
    values: dict[str, object] = {
        "policy_identity": policy.policy_identity,
        "forecast_identity": forecast_identity,
        "proof_identity": proof_identity,
        "signal_freeze_identity": expected_signal_identity,
        "confluence_identity": confluence_identity,
        "event_context_identity": event_context_identity,
        "asset": asset,
        "symbol": symbol,
        "timeframe": timeframe,
        "regime": WC2_UNMEASURED_REGIME,
        "issued_at_ms": issued_at_ms,
        "indexed_at_ms": indexed_at_ms,
        "source_evidence_identities": sources,
        "evidence_class": EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        "schema_version": WC2_COHORT_SCHEMA_VERSION,
        "engine_version": WC2_COHORT_ENGINE_VERSION,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }
    return WC2CohortForecast(
        cohort_forecast_identity=canonical_sha256(values),
        policy_identity=policy.policy_identity,
        forecast_identity=forecast_identity,
        proof_identity=proof_identity,
        signal_freeze_identity=expected_signal_identity,
        confluence_identity=confluence_identity,
        event_context_identity=event_context_identity,
        asset=asset,
        symbol=symbol,
        timeframe=timeframe,
        regime=WC2_UNMEASURED_REGIME,
        issued_at_ms=issued_at_ms,
        indexed_at_ms=indexed_at_ms,
        source_evidence_identities=sources,
    )


def _require_wc2_source_version(forecast: dict[str, Any]) -> None:
    raw = forecast.get("version_refs")
    if not isinstance(raw, list):
        raise TypeError("WC2 recovered R20 version refs must be array")
    matches = [
        item
        for item in raw
        if isinstance(item, dict)
        and item.get("component") == WC2_LIVE_SOURCE_VERSION_COMPONENT
    ]
    if len(matches) != 1:
        raise ValueError("persisted R20 lacks exact WC2 live-source provenance")
    if matches[0].get("version") != WC2_LIVE_SOURCE_ADAPTER_VERSION:
        raise ValueError("persisted R20 WC2 live-source version mismatch")


def _result(
    status: WC2LiveIndexStatus,
    *,
    signal_identity: str | None,
    reasons: tuple[str, ...],
    forecast_identity: str | None = None,
    cohort_identity: str | None = None,
    decision_disposition: DecisionLedgerWriteDisposition | None = None,
    cohort_disposition: WC2CohortAppendDisposition | None = None,
) -> WC2LiveIndexResult:
    return WC2LiveIndexResult(
        status=status,
        signal_freeze_identity=signal_identity,
        forecast_identity=forecast_identity,
        cohort_forecast_identity=cohort_identity,
        decision_ledger_disposition=decision_disposition,
        cohort_disposition=cohort_disposition,
        reason_codes=tuple(sorted(set(reasons))),
    )


def _raw_text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty text")
    return value


def _raw_sha(raw: dict[str, Any], key: str) -> str:
    value = _raw_text(raw, key)
    _require_sha256(value, key)
    return value


def _raw_int(raw: dict[str, Any], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(f"{key} must be non-negative integer")
    return value


def _raw_identity_list(
    raw: dict[str, Any],
    key: str,
) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise TypeError(f"{key} must be array")
    result = tuple(str(item) for item in value)
    if result != tuple(sorted(set(result))) or not result:
        raise ValueError(f"{key} must be non-empty canonical identity list")
    for identity in result:
        _require_sha256(identity, key)
    return result


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
