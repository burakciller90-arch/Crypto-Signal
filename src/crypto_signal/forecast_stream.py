from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from crypto_signal.confluence.models import InvalidationTrigger, PriceZone
from crypto_signal.intelligence.confluence_matrix_v2 import (
    M6_SCORE_SEMANTIC,
    ConfluenceMatrixResolution,
    ConfluenceMatrixSnapshot,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CircuitBreakerAnalysis,
    CircuitBreakerState,
)
from crypto_signal.intelligence.meta_intelligence import MetaDirection
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.outcomes.models import (
    EvidenceClass,
    OutcomeEvaluation,
    OutcomeResolutionStatus,
    OutcomeState,
)
from crypto_signal.signals.models import (
    SignalDecision,
    SignalDirection,
    SignalState,
)
if TYPE_CHECKING:
    from research.alpha_factory.probability_calibration_gate import (
        CalibratedProbabilityEvidence,
        CalibrationScope,
    )

R20_FORECAST_ENGINE_VERSION = "r20-immutable-forecast-stream-v1-slice1/1"
R20_FORECAST_SCHEMA_VERSION = "r20-immutable-forecast-v1/1"
R20_RESOLUTION_SCHEMA_VERSION = "r20-forecast-resolution-v1/1"
R20_STREAM_SCHEMA_VERSION = "r20-forecast-stream-snapshot-v1/1"
R20_PROBABILITY_NOT_CALIBRATED = "not_calibrated"
R20_PROBABILITY_CALIBRATED = "calibrated"
REAL_CAPITAL = 0


class ForecastAuthority(StrEnum):
    RESEARCH = "research"
    SHADOW = "shadow"


class ForecastTriggerKind(StrEnum):
    ENTRY_ZONE = "entry_zone"


class ForecastResolutionState(StrEnum):
    HIT_TARGET = "hit_target"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"
    AMBIGUOUS = "ambiguous"
    NOT_EVALUABLE = "not_evaluable"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ForecastVersionRef:
    component: str
    version: str

    def __post_init__(self) -> None:
        if not self.component.strip() or not self.version.strip():
            raise ValueError("forecast version reference must be non-empty")


@dataclass(frozen=True, slots=True)
class ImmutableForecast:
    forecast_identity: str
    schema_version: str
    engine_version: str
    authority: ForecastAuthority
    asset: str
    symbol: str
    timeframe: str
    issued_at_ms: int
    source_as_of_ms: int
    signal_freeze_identity: str
    signal_state: SignalState
    direction: SignalDirection
    condition_code: str
    trigger_kind: ForecastTriggerKind
    trigger_zone: PriceZone
    target_label: str
    target_zone: PriceZone
    invalidation_price: Decimal
    invalidation_trigger: InvalidationTrigger
    horizon_bars: int
    confluence_identity: str
    confluence_support_score_0_100: Decimal
    confluence_opposition_score_0_100: Decimal
    confluence_resolution: ConfluenceMatrixResolution
    confluence_score_semantic: str
    calibrated_probability_0_1: Decimal | None
    probability_status: str
    probability_authorization_identity: str | None
    probability_calibration_evidence_identity: str | None
    probability_scope_identity: str | None
    event_context_identity: str
    event_context_state: CircuitBreakerState
    event_context_triggers: tuple[str, ...]
    source_evidence_identities: tuple[str, ...]
    version_refs: tuple[ForecastVersionRef, ...]
    freshness_0_1: Decimal | None
    uncertainty_flags: tuple[str, ...]
    immutable_pre_outcome: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for identity, label in (
            (self.forecast_identity, "R20 forecast identity"),
            (self.signal_freeze_identity, "R20 signal freeze identity"),
            (self.confluence_identity, "R20 confluence identity"),
            (self.event_context_identity, "R20 event context identity"),
        ):
            _require_sha256(identity, label)
        if self.schema_version != R20_FORECAST_SCHEMA_VERSION:
            raise ValueError("unsupported R20 forecast schema")
        if self.engine_version != R20_FORECAST_ENGINE_VERSION:
            raise ValueError("unsupported R20 forecast engine")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("R20 asset must be non-empty uppercase")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("R20 symbol must be non-empty uppercase")
        if not self.symbol.startswith(self.asset):
            raise ValueError("R20 symbol must be compatible with base asset")
        if not self.timeframe.strip() or not self.condition_code.strip():
            raise ValueError("R20 timeframe/condition must be non-empty")
        if min(self.issued_at_ms, self.source_as_of_ms) < 0:
            raise ValueError("R20 forecast timestamps must be non-negative")
        if self.issued_at_ms < self.source_as_of_ms:
            raise ValueError("R20 forecast cannot be issued before source as-of")
        if self.signal_state not in {SignalState.WATCH, SignalState.ACTIVE}:
            raise ValueError("R20 forecast requires WATCH or ACTIVE signal")
        if self.direction is SignalDirection.NONE:
            raise ValueError("R20 forecast requires directional signal")
        if not self.target_label.strip():
            raise ValueError("R20 target label must be non-empty")
        if self.invalidation_price <= Decimal(0):
            raise ValueError("R20 invalidation price must be positive")
        if self.horizon_bars <= 0:
            raise ValueError("R20 horizon must be positive")
        for score in (
            self.confluence_support_score_0_100,
            self.confluence_opposition_score_0_100,
        ):
            if score < Decimal(0) or score > Decimal(100):
                raise ValueError("R20 confluence score must be inside [0,100]")
        if self.confluence_score_semantic != M6_SCORE_SEMANTIC:
            raise ValueError("R20 confluence semantic mismatch")
        if self.freshness_0_1 is not None:
            _require_unit_interval(self.freshness_0_1, "R20 freshness")

        probability_ids = (
            self.probability_authorization_identity,
            self.probability_calibration_evidence_identity,
            self.probability_scope_identity,
        )
        if self.calibrated_probability_0_1 is None:
            if self.probability_status != R20_PROBABILITY_NOT_CALIBRATED:
                raise ValueError("R20 uncalibrated forecast status mismatch")
            if any(value is not None for value in probability_ids):
                raise ValueError("R20 uncalibrated forecast cannot carry probability IDs")
        else:
            _require_unit_interval(
                self.calibrated_probability_0_1,
                "R20 calibrated probability",
            )
            if self.probability_status != R20_PROBABILITY_CALIBRATED:
                raise ValueError("R20 calibrated forecast status mismatch")
            if any(value is None for value in probability_ids):
                raise ValueError("R20 calibrated forecast requires exact R19 identities")
            for value in probability_ids:
                assert value is not None
                _require_sha256(value, "R20 probability identity")

        _require_identity_tuple(
            self.source_evidence_identities,
            "R20 source evidence identity",
        )
        if not self.source_evidence_identities:
            raise ValueError("R20 forecast requires source evidence")
        if tuple(sorted(set(self.event_context_triggers))) != self.event_context_triggers:
            raise ValueError("R20 event triggers must be unique and sorted")
        if tuple(sorted(set(self.uncertainty_flags))) != self.uncertainty_flags:
            raise ValueError("R20 uncertainty flags must be unique and sorted")
        if tuple(sorted(self.version_refs, key=lambda item: item.component)) != (
            self.version_refs
        ):
            raise ValueError("R20 version refs must be canonical by component")
        components = tuple(item.component for item in self.version_refs)
        if len(set(components)) != len(components):
            raise ValueError("R20 version refs must be unique by component")
        if not self.immutable_pre_outcome:
            raise ValueError("R20 forecast must remain immutable pre-outcome")
        if self.production_authority:
            raise ValueError("R20 forecast has no production/order authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.forecast_identity != canonical_sha256(_forecast_payload(self)):
            raise ValueError("R20 forecast identity mismatch")


@dataclass(frozen=True, slots=True)
class ForecastResolution:
    resolution_identity: str
    schema_version: str
    engine_version: str
    forecast_identity: str
    signal_freeze_identity: str
    source_outcome_identity: str
    evidence_class: EvidenceClass
    evaluated_at_ms: int
    state: ForecastResolutionState
    source_outcome_state: OutcomeState
    reason_codes: tuple[str, ...]
    original_forecast_unchanged: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for identity, label in (
            (self.resolution_identity, "R20 resolution identity"),
            (self.forecast_identity, "R20 resolution forecast identity"),
            (self.signal_freeze_identity, "R20 resolution signal identity"),
            (self.source_outcome_identity, "R20 resolution outcome identity"),
        ):
            _require_sha256(identity, label)
        if self.schema_version != R20_RESOLUTION_SCHEMA_VERSION:
            raise ValueError("unsupported R20 resolution schema")
        if self.engine_version != R20_FORECAST_ENGINE_VERSION:
            raise ValueError("unsupported R20 resolution engine")
        if self.evaluated_at_ms < 0:
            raise ValueError("R20 resolution timestamp must be non-negative")
        if tuple(sorted(set(self.reason_codes))) != self.reason_codes:
            raise ValueError("R20 resolution reasons must be unique and sorted")
        if not self.reason_codes:
            raise ValueError("R20 resolution requires reason code")
        if not self.original_forecast_unchanged:
            raise ValueError("R20 resolution cannot rewrite original forecast")
        if self.production_authority:
            raise ValueError("R20 resolution has no production/order authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.resolution_identity != canonical_sha256(_resolution_payload(self)):
            raise ValueError("R20 forecast resolution identity mismatch")


@dataclass(frozen=True, slots=True)
class ForecastStreamSnapshot:
    stream_identity: str
    schema_version: str
    engine_version: str
    forecasts: tuple[ImmutableForecast, ...]
    resolutions: tuple[ForecastResolution, ...]
    append_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.stream_identity, "R20 stream identity")
        if self.schema_version != R20_STREAM_SCHEMA_VERSION:
            raise ValueError("unsupported R20 stream schema")
        if self.engine_version != R20_FORECAST_ENGINE_VERSION:
            raise ValueError("unsupported R20 stream engine")
        forecast_ids = tuple(item.forecast_identity for item in self.forecasts)
        if len(set(forecast_ids)) != len(forecast_ids):
            raise ValueError("R20 stream forecast identities must be unique")
        forecast_keys = tuple(
            (item.issued_at_ms, item.forecast_identity)
            for item in self.forecasts
        )
        if forecast_keys != tuple(sorted(forecast_keys)):
            raise ValueError("R20 forecasts must be append-ordered")
        resolution_ids = tuple(item.resolution_identity for item in self.resolutions)
        if len(set(resolution_ids)) != len(resolution_ids):
            raise ValueError("R20 stream resolution identities must be unique")
        resolved_forecast_ids = tuple(
            item.forecast_identity for item in self.resolutions
        )
        if len(set(resolved_forecast_ids)) != len(resolved_forecast_ids):
            raise ValueError("R20 stream permits at most one resolution per forecast")
        if any(item.forecast_identity not in forecast_ids for item in self.resolutions):
            raise ValueError("R20 resolution references unknown forecast")
        resolution_keys = tuple(
            (item.evaluated_at_ms, item.resolution_identity)
            for item in self.resolutions
        )
        if resolution_keys != tuple(sorted(resolution_keys)):
            raise ValueError("R20 resolutions must be append-ordered")
        if not self.append_only:
            raise ValueError("R20 stream must remain append-only")
        if self.production_authority:
            raise ValueError("R20 stream has no production/order authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.stream_identity != canonical_sha256(_stream_payload(self)):
            raise ValueError("R20 stream identity mismatch")


def build_immutable_forecast(
    signal: SignalDecision,
    confluence: ConfluenceMatrixSnapshot,
    event_context: CircuitBreakerAnalysis,
    *,
    asset: str,
    issued_at_ms: int,
    horizon_bars: int,
    target_label: str,
    authority: ForecastAuthority = ForecastAuthority.SHADOW,
    calibrated_probability: CalibratedProbabilityEvidence | None = None,
    calibration_scope: CalibrationScope | None = None,
) -> ImmutableForecast:
    if signal.state not in {SignalState.WATCH, SignalState.ACTIVE}:
        raise ValueError("R20 forecast requires WATCH or ACTIVE signal")
    if signal.geometry is None:
        raise ValueError("R20 forecast requires frozen signal geometry")
    if signal.direction is SignalDirection.NONE:
        raise ValueError("R20 forecast requires directional signal")
    if signal.as_of_ms != confluence.as_of_ms or signal.as_of_ms != event_context.as_of_ms:
        raise ValueError("R20 signal/confluence/event context must share exact as-of")
    if signal.symbol != confluence.asset:
        raise ValueError("R20 signal symbol/confluence asset mismatch")
    if event_context.asset != asset:
        raise ValueError("R20 event context/base asset mismatch")
    if not signal.symbol.startswith(asset):
        raise ValueError("R20 signal symbol/base asset mismatch")

    expected_direction = (
        MetaDirection.BULLISH
        if signal.direction is SignalDirection.BULLISH
        else MetaDirection.BEARISH
    )
    if confluence.candidate_direction is not expected_direction:
        raise ValueError("R20 signal/confluence direction mismatch")
    if issued_at_ms < signal.as_of_ms:
        raise ValueError("R20 forecast issue time cannot predate source as-of")
    if horizon_bars <= 0:
        raise ValueError("R20 horizon must be positive")

    target = next(
        (item for item in signal.geometry.targets if item.label == target_label),
        None,
    )
    if target is None:
        raise ValueError("R20 target must exist in frozen signal geometry")

    probability_value: Decimal | None = None
    probability_status = R20_PROBABILITY_NOT_CALIBRATED
    probability_authorization_identity: str | None = None
    probability_calibration_identity: str | None = None
    probability_scope_identity: str | None = None
    if calibrated_probability is None and calibration_scope is not None:
        raise ValueError("R20 calibration scope requires probability evidence")
    if calibrated_probability is not None:
        if calibration_scope is None:
            raise ValueError("R20 calibrated probability requires exact R19 scope")
        if calibrated_probability.probability_status.value != R20_PROBABILITY_CALIBRATED:
            raise ValueError("R20 probability input must be R19 CALIBRATED")
        if calibrated_probability.issued_at_ms > issued_at_ms:
            raise ValueError("R20 probability evidence cannot come from the future")
        if calibration_scope.scope_identity != calibrated_probability.scope_identity:
            raise ValueError("R20 probability authorization/scope identity mismatch")
        if calibration_scope.asset != signal.symbol:
            raise ValueError("R20 probability scope asset mismatch")
        if calibration_scope.timeframe != signal.timeframe:
            raise ValueError("R20 probability scope timeframe mismatch")
        if calibration_scope.regime != confluence.regime:
            raise ValueError("R20 probability scope regime mismatch")
        expected_horizon_ms = horizon_bars * _timeframe_duration_ms(signal.timeframe)
        if calibration_scope.horizon_ms != expected_horizon_ms:
            raise ValueError("R20 probability scope horizon mismatch")
        probability_value = calibrated_probability.probability_0_1
        probability_status = calibrated_probability.probability_status.value
        probability_authorization_identity = calibrated_probability.authorization_identity
        probability_calibration_identity = (
            calibrated_probability.calibration_evidence_identity
        )
        probability_scope_identity = calibrated_probability.scope_identity

    uncertainty = set(signal.uncertainty_flags)
    uncertainty.update(event_context.uncertainty_flags)
    if confluence.freshness_0_1 is None:
        uncertainty.add("confluence_freshness_unavailable")
    if confluence.resolution is not ConfluenceMatrixResolution.MEASURED:
        uncertainty.add(f"confluence_resolution_{confluence.resolution.value}")
    if event_context.state is not CircuitBreakerState.CLEAR:
        uncertainty.add(f"event_context_{event_context.state.value}")

    evidence_ids = {
        signal.freeze_identity,
        confluence.snapshot_identity,
        event_context.evidence_identity,
    }
    if calibrated_probability is not None:
        evidence_ids.update(
            {
                calibrated_probability.authorization_identity,
                calibrated_probability.calibration_evidence_identity,
                calibrated_probability.source_forecast_identity,
                calibrated_probability.source_prediction_identity,
                calibrated_probability.walk_forward_fit_identity,
            }
        )

    version_refs = [
        ForecastVersionRef("event_circuit_engine", event_context.engine_version),
        ForecastVersionRef("event_circuit_policy", event_context.policy_version),
        ForecastVersionRef("forecast_engine", R20_FORECAST_ENGINE_VERSION),
        ForecastVersionRef("m6_confluence_engine", confluence.engine_version),
        ForecastVersionRef("signal", signal.signal_version),
    ]
    if calibrated_probability is not None:
        version_refs.extend(
            (
                ForecastVersionRef(
                    "probability_calibrator",
                    calibrated_probability.calibrator_version,
                ),
                ForecastVersionRef(
                    "probability_model",
                    calibrated_probability.model_version,
                ),
            )
        )
    ordered_versions = tuple(sorted(version_refs, key=lambda item: item.component))
    ordered_evidence = tuple(sorted(evidence_ids))
    ordered_uncertainty = tuple(sorted(uncertainty))
    ordered_event_triggers = tuple(sorted(event_context.triggers))
    target_zone = PriceZone(target.target_price, target.target_price)

    draft_payload = {
        "asset": asset,
        "authority": authority,
        "calibrated_probability_0_1": probability_value,
        "condition_code": signal.setup_type,
        "confluence_identity": confluence.snapshot_identity,
        "confluence_opposition_score_0_100": confluence.opposition_score_0_100,
        "confluence_resolution": confluence.resolution,
        "confluence_score_semantic": confluence.score_semantic,
        "confluence_support_score_0_100": confluence.support_score_0_100,
        "direction": signal.direction,
        "engine_version": R20_FORECAST_ENGINE_VERSION,
        "event_context_identity": event_context.evidence_identity,
        "event_context_state": event_context.state,
        "event_context_triggers": ordered_event_triggers,
        "freshness_0_1": confluence.freshness_0_1,
        "horizon_bars": horizon_bars,
        "immutable_pre_outcome": True,
        "invalidation_price": signal.geometry.invalidation_price,
        "invalidation_trigger": signal.geometry.invalidation_trigger,
        "issued_at_ms": issued_at_ms,
        "probability_authorization_identity": probability_authorization_identity,
        "probability_calibration_evidence_identity": probability_calibration_identity,
        "probability_scope_identity": probability_scope_identity,
        "probability_status": probability_status,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": R20_FORECAST_SCHEMA_VERSION,
        "signal_freeze_identity": signal.freeze_identity,
        "signal_state": signal.state,
        "source_as_of_ms": signal.as_of_ms,
        "source_evidence_identities": ordered_evidence,
        "symbol": signal.symbol,
        "target_label": target.label,
        "target_zone": target_zone,
        "timeframe": signal.timeframe,
        "trigger_kind": ForecastTriggerKind.ENTRY_ZONE,
        "trigger_zone": signal.geometry.entry_zone,
        "uncertainty_flags": ordered_uncertainty,
        "version_refs": ordered_versions,
    }
    return ImmutableForecast(
        forecast_identity=canonical_sha256(draft_payload),
        schema_version=R20_FORECAST_SCHEMA_VERSION,
        engine_version=R20_FORECAST_ENGINE_VERSION,
        authority=authority,
        asset=asset,
        symbol=signal.symbol,
        timeframe=signal.timeframe,
        issued_at_ms=issued_at_ms,
        source_as_of_ms=signal.as_of_ms,
        signal_freeze_identity=signal.freeze_identity,
        signal_state=signal.state,
        direction=signal.direction,
        condition_code=signal.setup_type,
        trigger_kind=ForecastTriggerKind.ENTRY_ZONE,
        trigger_zone=signal.geometry.entry_zone,
        target_label=target.label,
        target_zone=target_zone,
        invalidation_price=signal.geometry.invalidation_price,
        invalidation_trigger=signal.geometry.invalidation_trigger,
        horizon_bars=horizon_bars,
        confluence_identity=confluence.snapshot_identity,
        confluence_support_score_0_100=confluence.support_score_0_100,
        confluence_opposition_score_0_100=confluence.opposition_score_0_100,
        confluence_resolution=confluence.resolution,
        confluence_score_semantic=confluence.score_semantic,
        calibrated_probability_0_1=probability_value,
        probability_status=probability_status,
        probability_authorization_identity=probability_authorization_identity,
        probability_calibration_evidence_identity=probability_calibration_identity,
        probability_scope_identity=probability_scope_identity,
        event_context_identity=event_context.evidence_identity,
        event_context_state=event_context.state,
        event_context_triggers=ordered_event_triggers,
        source_evidence_identities=ordered_evidence,
        version_refs=ordered_versions,
        freshness_0_1=confluence.freshness_0_1,
        uncertainty_flags=ordered_uncertainty,
    )


def build_forecast_resolution(
    forecast: ImmutableForecast,
    outcome: OutcomeEvaluation,
) -> ForecastResolution:
    if outcome.signal_freeze_identity != forecast.signal_freeze_identity:
        raise ValueError("R20 outcome/forecast signal lineage mismatch")
    if outcome.resolution_status is OutcomeResolutionStatus.PENDING:
        raise ValueError("R20 cannot append pending outcome as resolution")
    if outcome.evaluated_as_of_ms < forecast.issued_at_ms:
        raise ValueError("R20 outcome cannot predate forecast issuance")
    if outcome.max_holding_bars != forecast.horizon_bars:
        raise ValueError("R20 outcome horizon does not match forecast")
    if outcome.outcome_state is None:
        raise ValueError("R20 closed outcome must carry state")

    state = _resolution_state(outcome.outcome_state)
    reasons = {f"source_outcome_{outcome.outcome_state.value}"}
    if outcome.ambiguity_reason is not None:
        reasons.add(f"ambiguity_{outcome.ambiguity_reason.value}")
    if outcome.not_evaluable_reason is not None:
        reasons.add(f"not_evaluable_{outcome.not_evaluable_reason.value}")
    ordered_reasons = tuple(sorted(reasons))
    payload = {
        "engine_version": R20_FORECAST_ENGINE_VERSION,
        "evaluated_at_ms": outcome.evaluated_as_of_ms,
        "evidence_class": outcome.evidence_class,
        "forecast_identity": forecast.forecast_identity,
        "original_forecast_unchanged": True,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "reason_codes": ordered_reasons,
        "schema_version": R20_RESOLUTION_SCHEMA_VERSION,
        "signal_freeze_identity": forecast.signal_freeze_identity,
        "source_outcome_identity": outcome.outcome_identity,
        "source_outcome_state": outcome.outcome_state,
        "state": state,
    }
    return ForecastResolution(
        resolution_identity=canonical_sha256(payload),
        schema_version=R20_RESOLUTION_SCHEMA_VERSION,
        engine_version=R20_FORECAST_ENGINE_VERSION,
        forecast_identity=forecast.forecast_identity,
        signal_freeze_identity=forecast.signal_freeze_identity,
        source_outcome_identity=outcome.outcome_identity,
        evidence_class=outcome.evidence_class,
        evaluated_at_ms=outcome.evaluated_as_of_ms,
        state=state,
        source_outcome_state=outcome.outcome_state,
        reason_codes=ordered_reasons,
    )


def empty_forecast_stream() -> ForecastStreamSnapshot:
    payload = {
        "append_only": True,
        "engine_version": R20_FORECAST_ENGINE_VERSION,
        "forecasts": (),
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "resolutions": (),
        "schema_version": R20_STREAM_SCHEMA_VERSION,
    }
    return ForecastStreamSnapshot(
        stream_identity=canonical_sha256(payload),
        schema_version=R20_STREAM_SCHEMA_VERSION,
        engine_version=R20_FORECAST_ENGINE_VERSION,
        forecasts=(),
        resolutions=(),
    )


def append_forecast(
    stream: ForecastStreamSnapshot,
    forecast: ImmutableForecast,
) -> ForecastStreamSnapshot:
    if any(
        item.forecast_identity == forecast.forecast_identity
        for item in stream.forecasts
    ):
        raise ValueError("R20 forecast already exists in stream")
    if stream.forecasts:
        last = stream.forecasts[-1]
        if (forecast.issued_at_ms, forecast.forecast_identity) <= (
            last.issued_at_ms,
            last.forecast_identity,
        ):
            raise ValueError("R20 forecast append would violate chronological order")
    return _stream((*stream.forecasts, forecast), stream.resolutions)


def append_resolution(
    stream: ForecastStreamSnapshot,
    resolution: ForecastResolution,
) -> ForecastStreamSnapshot:
    forecast = next(
        (
            item
            for item in stream.forecasts
            if item.forecast_identity == resolution.forecast_identity
        ),
        None,
    )
    if forecast is None:
        raise ValueError("R20 resolution references unknown forecast")
    if forecast.signal_freeze_identity != resolution.signal_freeze_identity:
        raise ValueError("R20 resolution/forecast signal lineage mismatch")
    if any(
        item.forecast_identity == resolution.forecast_identity
        for item in stream.resolutions
    ):
        raise ValueError("R20 forecast already has a resolution")
    if stream.resolutions:
        last = stream.resolutions[-1]
        if (resolution.evaluated_at_ms, resolution.resolution_identity) <= (
            last.evaluated_at_ms,
            last.resolution_identity,
        ):
            raise ValueError("R20 resolution append would violate chronological order")
    return _stream(stream.forecasts, (*stream.resolutions, resolution))


def _stream(
    forecasts: tuple[ImmutableForecast, ...],
    resolutions: tuple[ForecastResolution, ...],
) -> ForecastStreamSnapshot:
    payload = {
        "append_only": True,
        "engine_version": R20_FORECAST_ENGINE_VERSION,
        "forecasts": forecasts,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "resolutions": resolutions,
        "schema_version": R20_STREAM_SCHEMA_VERSION,
    }
    return ForecastStreamSnapshot(
        stream_identity=canonical_sha256(payload),
        schema_version=R20_STREAM_SCHEMA_VERSION,
        engine_version=R20_FORECAST_ENGINE_VERSION,
        forecasts=forecasts,
        resolutions=resolutions,
    )


def _resolution_state(outcome_state: OutcomeState) -> ForecastResolutionState:
    if outcome_state in {
        OutcomeState.SUCCESS_TP1,
        OutcomeState.SUCCESS_TP2,
        OutcomeState.SUCCESS_TP3,
    }:
        return ForecastResolutionState.HIT_TARGET
    if outcome_state in {OutcomeState.FAIL_SL, OutcomeState.INVALIDATED}:
        return ForecastResolutionState.INVALIDATED
    if outcome_state is OutcomeState.TIMEOUT:
        return ForecastResolutionState.EXPIRED
    if outcome_state is OutcomeState.AMBIGUOUS:
        return ForecastResolutionState.AMBIGUOUS
    if outcome_state is OutcomeState.NOT_EVALUABLE:
        return ForecastResolutionState.NOT_EVALUABLE
    if outcome_state is OutcomeState.CANCELLED:
        return ForecastResolutionState.CANCELLED
    raise ValueError("unsupported R20 outcome state")


def _forecast_payload(forecast: ImmutableForecast) -> dict[str, object]:
    return {
        "asset": forecast.asset,
        "authority": forecast.authority,
        "calibrated_probability_0_1": forecast.calibrated_probability_0_1,
        "condition_code": forecast.condition_code,
        "confluence_identity": forecast.confluence_identity,
        "confluence_opposition_score_0_100": (
            forecast.confluence_opposition_score_0_100
        ),
        "confluence_resolution": forecast.confluence_resolution,
        "confluence_score_semantic": forecast.confluence_score_semantic,
        "confluence_support_score_0_100": forecast.confluence_support_score_0_100,
        "direction": forecast.direction,
        "engine_version": forecast.engine_version,
        "event_context_identity": forecast.event_context_identity,
        "event_context_state": forecast.event_context_state,
        "event_context_triggers": forecast.event_context_triggers,
        "freshness_0_1": forecast.freshness_0_1,
        "horizon_bars": forecast.horizon_bars,
        "immutable_pre_outcome": forecast.immutable_pre_outcome,
        "invalidation_price": forecast.invalidation_price,
        "invalidation_trigger": forecast.invalidation_trigger,
        "issued_at_ms": forecast.issued_at_ms,
        "probability_authorization_identity": (
            forecast.probability_authorization_identity
        ),
        "probability_calibration_evidence_identity": (
            forecast.probability_calibration_evidence_identity
        ),
        "probability_scope_identity": forecast.probability_scope_identity,
        "probability_status": forecast.probability_status,
        "production_authority": forecast.production_authority,
        "real_capital": forecast.real_capital,
        "schema_version": forecast.schema_version,
        "signal_freeze_identity": forecast.signal_freeze_identity,
        "signal_state": forecast.signal_state,
        "source_as_of_ms": forecast.source_as_of_ms,
        "source_evidence_identities": forecast.source_evidence_identities,
        "symbol": forecast.symbol,
        "target_label": forecast.target_label,
        "target_zone": forecast.target_zone,
        "timeframe": forecast.timeframe,
        "trigger_kind": forecast.trigger_kind,
        "trigger_zone": forecast.trigger_zone,
        "uncertainty_flags": forecast.uncertainty_flags,
        "version_refs": forecast.version_refs,
    }


def _resolution_payload(resolution: ForecastResolution) -> dict[str, object]:
    return {
        "engine_version": resolution.engine_version,
        "evaluated_at_ms": resolution.evaluated_at_ms,
        "evidence_class": resolution.evidence_class,
        "forecast_identity": resolution.forecast_identity,
        "original_forecast_unchanged": resolution.original_forecast_unchanged,
        "production_authority": resolution.production_authority,
        "real_capital": resolution.real_capital,
        "reason_codes": resolution.reason_codes,
        "schema_version": resolution.schema_version,
        "signal_freeze_identity": resolution.signal_freeze_identity,
        "source_outcome_identity": resolution.source_outcome_identity,
        "source_outcome_state": resolution.source_outcome_state,
        "state": resolution.state,
    }


def _stream_payload(stream: ForecastStreamSnapshot) -> dict[str, object]:
    return {
        "append_only": stream.append_only,
        "engine_version": stream.engine_version,
        "forecasts": stream.forecasts,
        "production_authority": stream.production_authority,
        "real_capital": stream.real_capital,
        "resolutions": stream.resolutions,
        "schema_version": stream.schema_version,
    }


def _timeframe_duration_ms(timeframe: str) -> int:
    if len(timeframe) < 2:
        raise ValueError("R20 probability scope requires fixed-duration timeframe")
    unit = timeframe[-1].lower()
    try:
        count = int(timeframe[:-1])
    except ValueError as exc:
        raise ValueError(
            "R20 probability scope requires fixed-duration timeframe"
        ) from exc
    if count <= 0:
        raise ValueError("R20 timeframe duration must be positive")
    multipliers = {
        "m": 60_000,
        "h": 60 * 60_000,
        "d": 24 * 60 * 60_000,
        "w": 7 * 24 * 60 * 60_000,
    }
    multiplier = multipliers.get(unit)
    if multiplier is None:
        raise ValueError("R20 probability scope requires fixed-duration timeframe")
    return count * multiplier


def _require_identity_tuple(values: tuple[str, ...], label: str) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        _require_sha256(value, label)


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")


def _require_unit_interval(value: Decimal, label: str) -> None:
    if (
        value.is_nan()
        or value.is_infinite()
        or value < Decimal(0)
        or value > Decimal(1)
    ):
        raise ValueError(f"{label} must be inside [0,1]")
