from __future__ import annotations

import json
from dataclasses import dataclass

from crypto_signal.confluence.models import InvalidationTrigger, PriceZone
from crypto_signal.data.aggregation import aggregate_closed_15m
from crypto_signal.data.models import Candle
from crypto_signal.data.store import CandleStore
from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.evaluation.untouched_forward_journal import (
    WC2CohortAppendDisposition,
    WC2CohortForecast,
    WC2CohortJournal,
    build_wc2_cohort_resolution,
)
from crypto_signal.forecast_stream import (
    ForecastAuthority,
    ForecastResolution,
    ForecastResolutionState,
    ForecastTriggerKind,
    ForecastVersionRef,
    ImmutableForecast,
    build_forecast_resolution,
)
from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceMatrixResolution,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CircuitBreakerState,
)
from crypto_signal.ledger.deserialization import (
    parse_outcome_evaluation,
    parse_signal_decision,
    require_bool,
    require_decimal,
    require_int,
    require_list,
    require_mapping,
    require_str,
)
from crypto_signal.ledger.serialization import sha256_text
from crypto_signal.ledger.store import ImmutableSignalLedger
from crypto_signal.outcomes.evaluator import (
    evaluate_outcome,
    verify_outcome_identity,
)
from crypto_signal.outcomes.models import (
    EvidenceClass,
    OutcomeResolutionStatus,
    OutcomeState,
)
from crypto_signal.signals.models import SignalDecision, SignalDirection, SignalState

REAL_CAPITAL = 0
_SUPPORTED_OUTCOME_TIMEFRAMES = {"15m", "1h", "4h"}


@dataclass(frozen=True, slots=True)
class WC2OutcomeResolutionCycle:
    scanned: int
    pending: int
    resolved_fresh: int
    recovered: int
    cohort_idempotent: int
    historical_backfill_performed: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        counts = (
            self.scanned,
            self.pending,
            self.resolved_fresh,
            self.recovered,
            self.cohort_idempotent,
        )
        if min(counts) < 0:
            raise ValueError("WC2 outcome cycle counts cannot be negative")
        if self.scanned != self.pending + self.resolved_fresh + self.recovered:
            raise ValueError("WC2 outcome cycle accounting mismatch")
        if self.historical_backfill_performed:
            raise ValueError("WC2 outcome resolution cannot backfill history")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("WC2 outcome resolution cannot grant authority")


def resolve_wc2_outcomes_once(
    *,
    signal_ledger: ImmutableSignalLedger,
    candle_store: CandleStore,
    decision_ledger: ImmutableDecisionEvidenceLedger,
    cohort_journal: WC2CohortJournal,
    observed_at_ms: int,
    limit: int = 1000,
) -> WC2OutcomeResolutionCycle:
    """Resolve matured untouched-forward forecasts from already persisted evidence.

    This function performs no market-data fetch or historical backfill. It reads
    the exact persisted freeze and candle cache, persists only non-pending
    LIVE_UNTOUCHED_FORWARD outcome snapshots, and links them append-only into
    R20 and the WC2 cohort journal.
    """
    if observed_at_ms < 0:
        raise ValueError("WC2 outcome observation time cannot be negative")

    unresolved = cohort_journal.read_unresolved_forecasts(limit=limit)
    pending = 0
    resolved_fresh = 0
    recovered = 0
    cohort_idempotent = 0

    for cohort_forecast in unresolved:
        forecast = _read_exact_forecast(
            decision_ledger,
            cohort_forecast,
        )

        persisted_resolution = decision_ledger.read_resolution_for_forecast(
            forecast.forecast_identity
        )
        if persisted_resolution is not None:
            resolution = _parse_resolution(persisted_resolution)
            _require_resolution_outcome_lineage(
                signal_ledger,
                forecast=forecast,
                resolution=resolution,
            )
            disposition = cohort_journal.append_resolution(
                build_wc2_cohort_resolution(
                    cohort_forecast,
                    resolution,
                    indexed_at_ms=observed_at_ms,
                )
            )
            recovered += 1
            cohort_idempotent += (
                disposition is WC2CohortAppendDisposition.IDEMPOTENT
            )
            continue

        persisted_outcome = signal_ledger.read_closed_outcome_record(
            forecast.signal_freeze_identity,
            evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD.value,
            max_holding_bars=forecast.horizon_bars,
        )
        if persisted_outcome is not None:
            outcome = parse_outcome_evaluation(
                json.loads(persisted_outcome.outcome_json)
            )
            verify_outcome_identity(outcome)
            resolution = build_forecast_resolution(forecast, outcome)
            decision_ledger.append_resolution(resolution)
            disposition = cohort_journal.append_resolution(
                build_wc2_cohort_resolution(
                    cohort_forecast,
                    resolution,
                    indexed_at_ms=observed_at_ms,
                )
            )
            recovered += 1
            cohort_idempotent += (
                disposition is WC2CohortAppendDisposition.IDEMPOTENT
            )
            continue

        decision = _read_exact_signal_decision(
            signal_ledger,
            cohort_forecast,
        )
        outcome = evaluate_outcome(
            decision,
            _outcome_candles(
                candle_store,
                decision=decision,
                observed_at_ms=observed_at_ms,
            ),
            as_of_ms=observed_at_ms,
            evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
            max_holding_bars=forecast.horizon_bars,
        )
        if outcome.resolution_status is OutcomeResolutionStatus.PENDING:
            pending += 1
            continue

        signal_ledger.append_outcome_evaluation(
            outcome,
            appended_at_ms=observed_at_ms,
        )
        resolution = build_forecast_resolution(forecast, outcome)
        decision_ledger.append_resolution(resolution)
        disposition = cohort_journal.append_resolution(
            build_wc2_cohort_resolution(
                cohort_forecast,
                resolution,
                indexed_at_ms=observed_at_ms,
            )
        )
        resolved_fresh += 1
        cohort_idempotent += (
            disposition is WC2CohortAppendDisposition.IDEMPOTENT
        )

    return WC2OutcomeResolutionCycle(
        scanned=len(unresolved),
        pending=pending,
        resolved_fresh=resolved_fresh,
        recovered=recovered,
        cohort_idempotent=cohort_idempotent,
    )


def _read_exact_forecast(
    decision_ledger: ImmutableDecisionEvidenceLedger,
    cohort_forecast: WC2CohortForecast,
) -> ImmutableForecast:
    issuance = decision_ledger.read_issuance_for_signal(
        cohort_forecast.signal_freeze_identity
    )
    if issuance is None:
        raise ValueError("WC2 cohort forecast missing persisted R20 issuance")
    forecast = _parse_forecast(issuance[0])
    if forecast.forecast_identity != cohort_forecast.forecast_identity:
        raise ValueError("WC2 cohort/R20 forecast identity mismatch")
    if forecast.signal_freeze_identity != cohort_forecast.signal_freeze_identity:
        raise ValueError("WC2 cohort/R20 signal identity mismatch")
    if forecast.symbol != cohort_forecast.symbol:
        raise ValueError("WC2 cohort/R20 symbol mismatch")
    if forecast.timeframe != cohort_forecast.timeframe:
        raise ValueError("WC2 cohort/R20 timeframe mismatch")
    return forecast


def _read_exact_signal_decision(
    signal_ledger: ImmutableSignalLedger,
    cohort_forecast: WC2CohortForecast,
) -> SignalDecision:
    freeze = signal_ledger.read_freeze_by_signal(
        cohort_forecast.signal_freeze_identity
    )
    if freeze is None:
        raise ValueError("WC2 outcome source freeze is missing")
    if sha256_text(freeze.bundle_json) != freeze.bundle_identity:
        raise ValueError("WC2 outcome source bundle digest mismatch")
    raw = json.loads(freeze.bundle_json)
    root = require_mapping(raw, "WC2 frozen bundle")
    decision = parse_signal_decision(root.get("signal_decision"))
    if decision.freeze_identity != cohort_forecast.signal_freeze_identity:
        raise ValueError("WC2 outcome freeze/signal identity mismatch")
    if (
        decision.exchange.value != freeze.exchange
        or decision.market_type.value != freeze.market_type
        or decision.symbol != freeze.symbol
        or decision.timeframe != freeze.timeframe
        or decision.as_of_ms != freeze.as_of_ms
    ):
        raise ValueError("WC2 outcome freeze market lineage mismatch")
    if decision.symbol != cohort_forecast.symbol:
        raise ValueError("WC2 outcome cohort/signal symbol mismatch")
    if decision.timeframe != cohort_forecast.timeframe:
        raise ValueError("WC2 outcome cohort/signal timeframe mismatch")
    return decision


def _outcome_candles(
    candle_store: CandleStore,
    *,
    decision: SignalDecision,
    observed_at_ms: int,
) -> tuple[Candle, ...]:
    if decision.timeframe not in _SUPPORTED_OUTCOME_TIMEFRAMES:
        raise ValueError("WC2 outcome timeframe is outside preregistered scope")

    base = candle_store.list_candles_read_only(
        exchange=decision.exchange,
        market_type=decision.market_type,
        symbol=decision.symbol,
        timeframe="15m",
    )
    observed_base = tuple(
        candle
        for candle in base
        if (
            candle.is_closed
            and candle.close_time_ms <= observed_at_ms
            and candle.ingested_at_ms <= observed_at_ms
        )
    )
    if decision.timeframe == "15m":
        return observed_base

    aggregation = aggregate_closed_15m(
        observed_base,
        target_timeframe=decision.timeframe,
    )
    return aggregation.candles


def _require_resolution_outcome_lineage(
    signal_ledger: ImmutableSignalLedger,
    *,
    forecast: ImmutableForecast,
    resolution: ForecastResolution,
) -> None:
    if resolution.forecast_identity != forecast.forecast_identity:
        raise ValueError("persisted WC2 resolution forecast mismatch")
    record = signal_ledger.read_closed_outcome_record(
        forecast.signal_freeze_identity,
        evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD.value,
        max_holding_bars=forecast.horizon_bars,
    )
    if record is None:
        raise ValueError("persisted WC2 resolution missing source outcome")
    outcome = parse_outcome_evaluation(json.loads(record.outcome_json))
    verify_outcome_identity(outcome)
    if outcome.outcome_identity != resolution.source_outcome_identity:
        raise ValueError("persisted WC2 resolution/source outcome mismatch")


def _parse_forecast(value: object) -> ImmutableForecast:
    raw = require_mapping(value, "persisted R20 forecast")
    trigger = require_mapping(raw.get("trigger_zone"), "R20 trigger zone")
    target = require_mapping(raw.get("target_zone"), "R20 target zone")
    calibrated_raw = raw.get("calibrated_probability_0_1")
    freshness_raw = raw.get("freshness_0_1")
    return ImmutableForecast(
        forecast_identity=require_str(raw.get("forecast_identity"), "forecast identity"),
        schema_version=require_str(raw.get("schema_version"), "forecast schema"),
        engine_version=require_str(raw.get("engine_version"), "forecast engine"),
        authority=ForecastAuthority(
            require_str(raw.get("authority"), "forecast authority")
        ),
        asset=require_str(raw.get("asset"), "forecast asset"),
        symbol=require_str(raw.get("symbol"), "forecast symbol"),
        timeframe=require_str(raw.get("timeframe"), "forecast timeframe"),
        issued_at_ms=require_int(raw.get("issued_at_ms"), "forecast issued at"),
        source_as_of_ms=require_int(raw.get("source_as_of_ms"), "forecast source as-of"),
        signal_freeze_identity=require_str(
            raw.get("signal_freeze_identity"),
            "forecast signal identity",
        ),
        signal_state=SignalState(
            require_str(raw.get("signal_state"), "forecast signal state")
        ),
        direction=SignalDirection(
            require_str(raw.get("direction"), "forecast direction")
        ),
        condition_code=require_str(raw.get("condition_code"), "forecast condition"),
        trigger_kind=ForecastTriggerKind(
            require_str(raw.get("trigger_kind"), "forecast trigger kind")
        ),
        trigger_zone=PriceZone(
            low=require_decimal(trigger.get("low"), "forecast trigger low"),
            high=require_decimal(trigger.get("high"), "forecast trigger high"),
        ),
        target_label=require_str(raw.get("target_label"), "forecast target label"),
        target_zone=PriceZone(
            low=require_decimal(target.get("low"), "forecast target low"),
            high=require_decimal(target.get("high"), "forecast target high"),
        ),
        invalidation_price=require_decimal(
            raw.get("invalidation_price"),
            "forecast invalidation",
        ),
        invalidation_trigger=InvalidationTrigger(
            require_str(
                raw.get("invalidation_trigger"),
                "forecast invalidation trigger",
            )
        ),
        horizon_bars=require_int(raw.get("horizon_bars"), "forecast horizon"),
        confluence_identity=require_str(
            raw.get("confluence_identity"),
            "forecast confluence identity",
        ),
        confluence_support_score_0_100=require_decimal(
            raw.get("confluence_support_score_0_100"),
            "forecast confluence support",
        ),
        confluence_opposition_score_0_100=require_decimal(
            raw.get("confluence_opposition_score_0_100"),
            "forecast confluence opposition",
        ),
        confluence_resolution=ConfluenceMatrixResolution(
            require_str(
                raw.get("confluence_resolution"),
                "forecast confluence resolution",
            )
        ),
        confluence_score_semantic=require_str(
            raw.get("confluence_score_semantic"),
            "forecast confluence semantic",
        ),
        calibrated_probability_0_1=(
            None
            if calibrated_raw is None
            else require_decimal(calibrated_raw, "forecast calibrated probability")
        ),
        probability_status=require_str(
            raw.get("probability_status"),
            "forecast probability status",
        ),
        probability_authorization_identity=_optional_text(
            raw.get("probability_authorization_identity")
        ),
        probability_calibration_evidence_identity=_optional_text(
            raw.get("probability_calibration_evidence_identity")
        ),
        probability_scope_identity=_optional_text(
            raw.get("probability_scope_identity")
        ),
        event_context_identity=require_str(
            raw.get("event_context_identity"),
            "forecast event context identity",
        ),
        event_context_state=CircuitBreakerState(
            require_str(
                raw.get("event_context_state"),
                "forecast event context state",
            )
        ),
        event_context_triggers=tuple(
            require_str(item, "forecast event trigger")
            for item in require_list(
                raw.get("event_context_triggers"),
                "forecast event triggers",
            )
        ),
        source_evidence_identities=tuple(
            require_str(item, "forecast source evidence")
            for item in require_list(
                raw.get("source_evidence_identities"),
                "forecast source evidence",
            )
        ),
        version_refs=tuple(
            ForecastVersionRef(
                component=require_str(
                    require_mapping(item, "forecast version ref").get("component"),
                    "forecast version component",
                ),
                version=require_str(
                    require_mapping(item, "forecast version ref").get("version"),
                    "forecast version",
                ),
            )
            for item in require_list(
                raw.get("version_refs"),
                "forecast version refs",
            )
        ),
        freshness_0_1=(
            None
            if freshness_raw is None
            else require_decimal(freshness_raw, "forecast freshness")
        ),
        uncertainty_flags=tuple(
            require_str(item, "forecast uncertainty flag")
            for item in require_list(
                raw.get("uncertainty_flags"),
                "forecast uncertainty flags",
            )
        ),
        immutable_pre_outcome=require_bool(
            raw.get("immutable_pre_outcome"),
            "forecast immutable pre-outcome",
        ),
        production_authority=require_bool(
            raw.get("production_authority"),
            "forecast production authority",
        ),
        real_capital=require_int(raw.get("real_capital"), "forecast real capital"),
    )


def _parse_resolution(value: object) -> ForecastResolution:
    raw = require_mapping(value, "persisted R20 resolution")
    return ForecastResolution(
        resolution_identity=require_str(
            raw.get("resolution_identity"),
            "resolution identity",
        ),
        schema_version=require_str(raw.get("schema_version"), "resolution schema"),
        engine_version=require_str(raw.get("engine_version"), "resolution engine"),
        forecast_identity=require_str(
            raw.get("forecast_identity"),
            "resolution forecast",
        ),
        signal_freeze_identity=require_str(
            raw.get("signal_freeze_identity"),
            "resolution signal",
        ),
        source_outcome_identity=require_str(
            raw.get("source_outcome_identity"),
            "resolution source outcome",
        ),
        evidence_class=EvidenceClass(
            require_str(raw.get("evidence_class"), "resolution evidence class")
        ),
        evaluated_at_ms=require_int(
            raw.get("evaluated_at_ms"),
            "resolution evaluated at",
        ),
        state=ForecastResolutionState(
            require_str(raw.get("state"), "resolution state")
        ),
        source_outcome_state=OutcomeState(
            require_str(
                raw.get("source_outcome_state"),
                "resolution source outcome state",
            )
        ),
        reason_codes=tuple(
            require_str(item, "resolution reason")
            for item in require_list(raw.get("reason_codes"), "resolution reasons")
        ),
        original_forecast_unchanged=require_bool(
            raw.get("original_forecast_unchanged"),
            "resolution original forecast unchanged",
        ),
        production_authority=require_bool(
            raw.get("production_authority"),
            "resolution production authority",
        ),
        real_capital=require_int(raw.get("real_capital"), "resolution real capital"),
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return require_str(value, "optional text")
