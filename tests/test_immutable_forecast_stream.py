from __future__ import annotations

import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.confluence.models import (
    InvalidationTrigger,
    MethodologyKind,
    PriceZone,
    ScoreSemantic,
)
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.forecast_stream import (
    R20_FORECAST_ENGINE_VERSION,
    R20_PROBABILITY_NOT_CALIBRATED,
    ForecastAuthority,
    ForecastResolutionState,
    append_forecast,
    append_resolution,
    build_forecast_resolution,
    build_immutable_forecast,
    empty_forecast_stream,
)
from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamily,
    ConfluenceMatrixResolution,
    build_confluence_family_evidence,
    build_locked_m6_policy,
    evaluate_confluence_matrix,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CIRCUIT_BREAKER_ENGINE_VERSION,
    CircuitBreakerAnalysis,
    CircuitBreakerState,
)
from crypto_signal.intelligence.meta_intelligence import (
    MetaDirection,
    MetaEvidenceState,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.outcomes.models import (
    EvidenceClass,
    OutcomeAmbiguityReason,
    OutcomeCoverageStatus,
    OutcomeEvaluation,
    OutcomeNotEvaluableReason,
    OutcomeResolutionStatus,
    OutcomeState,
)
from crypto_signal.signals.models import (
    EntryReferenceModel,
    HistoricalStatsStatus,
    MethodologyVersionRef,
    ProbabilityStatus,
    RiskRewardTarget,
    SignalAgreementSummary,
    SignalDecision,
    SignalDirection,
    SignalGeometry,
    SignalState,
)
from research.alpha_factory.probability_calibration_gate import (
    R19_CALIBRATION_ENGINE_VERSION,
    R19_CALIBRATION_SCHEMA_VERSION,
    R19_PROBABILITY_SEMANTIC,
    CalibratedProbabilityEvidence,
    R19ProbabilityStatus,
    build_calibration_scope,
)

AS_OF = 1_000_000
ISSUED_AT = AS_OF + 100
HORIZON = 8
HORIZON_MS = HORIZON * 4 * 60 * 60_000


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _signal(
    *,
    direction: SignalDirection = SignalDirection.BULLISH,
    as_of_ms: int = AS_OF,
):
    geometry = SignalGeometry(
        source_evidence_id="price-action-evidence",
        source_methodology=MethodologyKind.PRICE_ACTION,
        entry_zone=PriceZone(Decimal(100), Decimal(102)),
        entry_reference_price=Decimal(101),
        entry_reference_model=EntryReferenceModel.ZONE_MIDPOINT_REFERENCE_NOT_EXECUTION,
        invalidation_price=Decimal(95),
        invalidation_trigger=InvalidationTrigger.TOUCH_OR_CROSS,
        targets=(
            RiskRewardTarget(
                label="target_1",
                target_price=Decimal(108),
                reference_rr=Decimal("1.4"),
            ),
        ),
    )
    return SignalDecision(
        freeze_identity=_sha(f"signal-{direction.value}-{as_of_ms}"),
        signal_version="signal-v1/1",
        state=SignalState.ACTIVE,
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="4h",
        as_of_ms=as_of_ms,
        direction=direction,
        setup_type="breakout",
        geometry=geometry,
        agreement=SignalAgreementSummary(
            confluence_score=Decimal(80),
            score_semantic=ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY,
            support_method_count=1,
            opposing_method_count=0,
            resolved_method_count=1,
            total_methodology_slots=3,
            pairwise_relations=(),
        ),
        selected_evidence_ids=("price-action-evidence",),
        methodology_versions=(
            MethodologyVersionRef(
                methodology=MethodologyKind.PRICE_ACTION,
                version="price-action/test",
            ),
        ),
        probability_status=ProbabilityStatus.NOT_CALIBRATED,
        historical_stats_status=HistoricalStatsStatus.NOT_EVALUATED,
        uncertainty_flags=("signal_uncertainty_example",),
        evidence_summary=(),
    )


def _confluence(
    *,
    direction: MetaDirection = MetaDirection.BULLISH,
    as_of_ms: int = AS_OF,
):
    evidence = tuple(
        build_confluence_family_evidence(
            family=family,
            asset="BTCUSDT",
            timeframe="4h",
            regime="trend_up",
            as_of_ms=as_of_ms,
            state=MetaEvidenceState.OBSERVED,
            direction=direction,
            directional_strength_0_1=Decimal("0.80"),
            evidence_quality_0_1=Decimal("0.90"),
            freshness_0_1=Decimal("0.95"),
            market_available_at_ms=as_of_ms - 20,
            observed_at_ms=as_of_ms - 10,
            source_engine_ids=(f"{family.value}-engine",),
            source_evidence_identities=(_sha(f"{family.value}-source"),),
            uncertainty_flags=(),
        )
        for family in sorted(ConfluenceFamily, key=lambda item: item.value)
    )
    return evaluate_confluence_matrix(
        build_locked_m6_policy(),
        evidence,
        candidate_direction=direction,
    )


def _event_context(
    *,
    state: CircuitBreakerState = CircuitBreakerState.CLEAR,
    as_of_ms: int = AS_OF,
    asset: str = "BTC",
):
    triggers = () if state is CircuitBreakerState.CLEAR else ("event_context_test",)
    uncertainty = (
        "circuit_breaker_has_no_trade_or_order_authority",
        "circuit_breaker_is_versioned_research_policy_not_universal_law",
    )
    payload = {
        "as_of_ms": as_of_ms,
        "asset": asset,
        "engine_version": CIRCUIT_BREAKER_ENGINE_VERSION,
        "event_risk_identity": _sha("event-risk"),
        "market_quality_identity": _sha("market-quality"),
        "news_evidence_identity": _sha("news"),
        "policy_version": "event-policy/test",
        "real_capital": 0,
        "state": state,
        "triggers": triggers,
        "uncertainty_flags": uncertainty,
    }
    return CircuitBreakerAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=CIRCUIT_BREAKER_ENGINE_VERSION,
        policy_version="event-policy/test",
        asset=asset,
        as_of_ms=as_of_ms,
        state=state,
        event_risk_identity=_sha("event-risk"),
        news_evidence_identity=_sha("news"),
        market_quality_identity=_sha("market-quality"),
        triggers=triggers,
        uncertainty_flags=uncertainty,
    )


def _probability_scope(
    *,
    asset: str = "BTCUSDT",
    timeframe: str = "4h",
    regime: str = "trend_up",
    horizon_ms: int = HORIZON_MS,
):
    return build_calibration_scope(
        asset=asset,
        timeframe=timeframe,
        regime=regime,
        outcome_event_definition=(
            "frozen bullish forecast reaches target before invalidation within horizon"
        ),
        horizon_ms=horizon_ms,
    )


def _calibrated_probability(
    *,
    issued_at_ms: int = AS_OF,
    probability: Decimal = Decimal("0.67"),
    scope=None,
):
    if scope is None:
        scope = _probability_scope()
    scope_identity = scope.scope_identity
    model_version = "probability-model-v1"
    calibrator_version = "calibrator-v1"
    walk_forward_fit_identity = _sha("walk-forward-fit")
    source_forecast_identity = _sha(f"r19-source-forecast-{issued_at_ms}-{probability}")
    prediction_payload = {
        "calibrator_version": calibrator_version,
        "engine_version": R19_CALIBRATION_ENGINE_VERSION,
        "issued_at_ms": issued_at_ms,
        "model_version": model_version,
        "predicted_probability_0_1": probability,
        "probability_semantic": R19_PROBABILITY_SEMANTIC,
        "production_authority": False,
        "real_capital": 0,
        "schema_version": R19_CALIBRATION_SCHEMA_VERSION,
        "scope_identity": scope_identity,
        "source_forecast_identity": source_forecast_identity,
        "walk_forward_fit_identity": walk_forward_fit_identity,
    }
    source_prediction_identity = canonical_sha256(prediction_payload)
    authorization_payload = {
        "calibration_evidence_identity": _sha("calibration-report"),
        "calibrator_version": calibrator_version,
        "engine_version": R19_CALIBRATION_ENGINE_VERSION,
        "issued_at_ms": issued_at_ms,
        "model_version": model_version,
        "probability_0_1": probability,
        "probability_semantic": R19_PROBABILITY_SEMANTIC,
        "probability_status": R19ProbabilityStatus.CALIBRATED,
        "production_authority": False,
        "real_capital": 0,
        "schema_version": R19_CALIBRATION_SCHEMA_VERSION,
        "scope_identity": scope_identity,
        "source_forecast_identity": source_forecast_identity,
        "source_prediction_identity": source_prediction_identity,
        "walk_forward_fit_identity": walk_forward_fit_identity,
    }
    return CalibratedProbabilityEvidence(
        authorization_identity=canonical_sha256(authorization_payload),
        schema_version=R19_CALIBRATION_SCHEMA_VERSION,
        engine_version=R19_CALIBRATION_ENGINE_VERSION,
        calibration_evidence_identity=_sha("calibration-report"),
        scope_identity=scope_identity,
        model_version=model_version,
        calibrator_version=calibrator_version,
        walk_forward_fit_identity=walk_forward_fit_identity,
        source_prediction_identity=source_prediction_identity,
        source_forecast_identity=source_forecast_identity,
        issued_at_ms=issued_at_ms,
        probability_0_1=probability,
        probability_status=R19ProbabilityStatus.CALIBRATED,
        probability_semantic=R19_PROBABILITY_SEMANTIC,
    )


def _forecast(
    *,
    probability: CalibratedProbabilityEvidence | None = None,
    probability_scope=None,
    issued_at_ms: int = ISSUED_AT,
    event_state: CircuitBreakerState = CircuitBreakerState.CLEAR,
):
    if probability is not None and probability_scope is None:
        probability_scope = _probability_scope()
    return build_immutable_forecast(
        _signal(),
        _confluence(),
        _event_context(state=event_state),
        asset="BTC",
        issued_at_ms=issued_at_ms,
        horizon_bars=HORIZON,
        target_label="target_1",
        authority=ForecastAuthority.SHADOW,
        calibrated_probability=probability,
        calibration_scope=probability_scope,
    )


def _outcome(
    state: OutcomeState,
    *,
    signal_identity: str,
    evaluated_at_ms: int = ISSUED_AT + 10_000,
    horizon: int = HORIZON,
):
    if state is OutcomeState.NOT_EVALUABLE:
        resolution_status = OutcomeResolutionStatus.NOT_EVALUABLE
        not_evaluable_reason = OutcomeNotEvaluableReason.DATA_GAPS
    else:
        resolution_status = OutcomeResolutionStatus.RESOLVED
        not_evaluable_reason = None
    ambiguity_reason = (
        OutcomeAmbiguityReason.ENTRY_AND_TARGET_SAME_CANDLE
        if state is OutcomeState.AMBIGUOUS
        else None
    )
    highest_target = 1 if state in {
        OutcomeState.SUCCESS_TP1,
        OutcomeState.SUCCESS_TP2,
        OutcomeState.SUCCESS_TP3,
    } else 0
    return OutcomeEvaluation(
        outcome_identity=_sha(f"outcome-{state.value}-{evaluated_at_ms}"),
        signal_freeze_identity=signal_identity,
        evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        evaluated_as_of_ms=evaluated_at_ms,
        resolution_status=resolution_status,
        outcome_state=state,
        signal_initial_state=SignalState.ACTIVE,
        coverage_status=(
            OutcomeCoverageStatus.INCOMPLETE_GAPS
            if state is OutcomeState.NOT_EVALUABLE
            else OutcomeCoverageStatus.COMPLETE
        ),
        max_holding_bars=horizon,
        expected_bar_count=horizon,
        observed_bar_count=(horizon - 1 if state is OutcomeState.NOT_EVALUABLE else horizon),
        missing_open_times_ms=(
            (AS_OF + 4_000,) if state is OutcomeState.NOT_EVALUABLE else ()
        ),
        skipped_partial_decision_bucket=False,
        entry_observed=True,
        entry_candle_identity=("bybit", "spot", "BTCUSDT", "4h", AS_OF + 1_000),
        highest_target_index=highest_target,
        outcome_candle_identity=("bybit", "spot", "BTCUSDT", "4h", AS_OF + 8_000),
        ambiguity_reason=ambiguity_reason,
        not_evaluable_reason=not_evaluable_reason,
    )


def test_forecast_freezes_required_r20_truth_without_inventing_probability() -> None:
    forecast = _forecast()

    assert forecast.engine_version == R20_FORECAST_ENGINE_VERSION
    assert forecast.asset == "BTC"
    assert forecast.symbol == "BTCUSDT"
    assert forecast.timeframe == "4h"
    assert forecast.direction is SignalDirection.BULLISH
    assert forecast.condition_code == "breakout"
    assert forecast.trigger_zone == PriceZone(Decimal(100), Decimal(102))
    assert forecast.target_zone == PriceZone(Decimal(108), Decimal(108))
    assert forecast.invalidation_price == Decimal(95)
    assert forecast.horizon_bars == HORIZON
    assert forecast.confluence_resolution is ConfluenceMatrixResolution.MEASURED
    assert forecast.confluence_support_score_0_100 == Decimal("80.00")
    assert forecast.confluence_opposition_score_0_100 == Decimal("0.00")
    assert forecast.calibrated_probability_0_1 is None
    assert forecast.probability_status == R20_PROBABILITY_NOT_CALIBRATED
    assert forecast.probability_authorization_identity is None
    assert forecast.event_context_state is CircuitBreakerState.CLEAR
    assert forecast.event_context_triggers == ()
    assert forecast.freshness_0_1 == Decimal("0.9500")
    assert "signal_uncertainty_example" in forecast.uncertainty_flags
    assert (
        "circuit_breaker_has_no_trade_or_order_authority"
        in forecast.uncertainty_flags
    )
    assert forecast.immutable_pre_outcome is True
    assert forecast.production_authority is False
    assert forecast.real_capital == 0
    assert len(forecast.forecast_identity) == 64


def test_forecast_probability_requires_exact_r19_authorization_and_preserves_provenance() -> None:
    probability = _calibrated_probability()
    forecast = _forecast(probability=probability)

    assert forecast.calibrated_probability_0_1 == Decimal("0.67")
    assert forecast.probability_status == "calibrated"
    assert (
        forecast.probability_authorization_identity
        == probability.authorization_identity
    )
    assert (
        forecast.probability_calibration_evidence_identity
        == probability.calibration_evidence_identity
    )
    assert forecast.probability_scope_identity == probability.scope_identity
    assert probability.authorization_identity in forecast.source_evidence_identities
    assert probability.calibration_evidence_identity in forecast.source_evidence_identities
    assert probability.source_prediction_identity in forecast.source_evidence_identities
    components = {item.component for item in forecast.version_refs}
    assert "probability_model" in components
    assert "probability_calibrator" in components

    with pytest.raises(ValueError, match="cannot come from the future"):
        _forecast(
            probability=_calibrated_probability(issued_at_ms=ISSUED_AT + 1),
        )


@pytest.mark.parametrize(
    ("scope", "message"),
    [
        (_probability_scope(asset="ETHUSDT"), "scope asset mismatch"),
        (_probability_scope(timeframe="1h"), "scope timeframe mismatch"),
        (_probability_scope(regime="range"), "scope regime mismatch"),
        (_probability_scope(horizon_ms=HORIZON_MS + 1), "scope horizon mismatch"),
    ],
)
def test_calibrated_probability_must_match_exact_forecast_scope(
    scope,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _forecast(
            probability=_calibrated_probability(scope=scope),
            probability_scope=scope,
        )


def test_probability_authorization_and_scope_identity_must_match() -> None:
    with pytest.raises(
        ValueError,
        match="authorization/scope identity mismatch",
    ):
        _forecast(
            probability=_calibrated_probability(),
            probability_scope=_probability_scope(regime="range"),
        )


def test_probability_scope_without_probability_evidence_fails_closed() -> None:
    with pytest.raises(ValueError, match="scope requires probability evidence"):
        _forecast(probability_scope=_probability_scope())


def test_non_clear_event_context_is_preserved_not_hidden() -> None:
    forecast = _forecast(event_state=CircuitBreakerState.CAUTION)

    assert forecast.event_context_state is CircuitBreakerState.CAUTION
    assert forecast.event_context_triggers == ("event_context_test",)
    assert "event_context_caution" in forecast.uncertainty_flags


def test_source_context_direction_and_asof_mismatches_fail_closed() -> None:
    with pytest.raises(ValueError, match="direction mismatch"):
        build_immutable_forecast(
            _signal(direction=SignalDirection.BULLISH),
            _confluence(direction=MetaDirection.BEARISH),
            _event_context(),
            asset="BTC",
            issued_at_ms=ISSUED_AT,
            horizon_bars=HORIZON,
            target_label="target_1",
        )

    with pytest.raises(ValueError, match="share exact as-of"):
        build_immutable_forecast(
            _signal(),
            _confluence(as_of_ms=AS_OF - 1),
            _event_context(),
            asset="BTC",
            issued_at_ms=ISSUED_AT,
            horizon_bars=HORIZON,
            target_label="target_1",
        )

    with pytest.raises(ValueError, match="event context/base asset mismatch"):
        build_immutable_forecast(
            _signal(),
            _confluence(),
            _event_context(asset="ETH"),
            asset="BTC",
            issued_at_ms=ISSUED_AT,
            horizon_bars=HORIZON,
            target_label="target_1",
        )


@pytest.mark.parametrize(
    ("outcome_state", "expected"),
    [
        (OutcomeState.SUCCESS_TP1, ForecastResolutionState.HIT_TARGET),
        (OutcomeState.SUCCESS_TP3, ForecastResolutionState.HIT_TARGET),
        (OutcomeState.FAIL_SL, ForecastResolutionState.INVALIDATED),
        (OutcomeState.INVALIDATED, ForecastResolutionState.INVALIDATED),
        (OutcomeState.TIMEOUT, ForecastResolutionState.EXPIRED),
        (OutcomeState.AMBIGUOUS, ForecastResolutionState.AMBIGUOUS),
        (OutcomeState.NOT_EVALUABLE, ForecastResolutionState.NOT_EVALUABLE),
        (OutcomeState.CANCELLED, ForecastResolutionState.CANCELLED),
    ],
)
def test_later_outcome_maps_to_separate_append_resolution(
    outcome_state: OutcomeState,
    expected: ForecastResolutionState,
) -> None:
    forecast = _forecast()
    resolution = build_forecast_resolution(
        forecast,
        _outcome(outcome_state, signal_identity=forecast.signal_freeze_identity),
    )

    assert resolution.forecast_identity == forecast.forecast_identity
    assert resolution.signal_freeze_identity == forecast.signal_freeze_identity
    assert resolution.state is expected
    assert resolution.original_forecast_unchanged is True
    assert resolution.production_authority is False
    assert resolution.real_capital == 0


def test_stream_is_functional_append_only_and_resolution_never_rewrites_forecast() -> None:
    forecast = _forecast()
    empty = empty_forecast_stream()
    issued = append_forecast(empty, forecast)
    original_identity = issued.forecasts[0].forecast_identity
    resolution = build_forecast_resolution(
        forecast,
        _outcome(OutcomeState.SUCCESS_TP1, signal_identity=forecast.signal_freeze_identity),
    )
    resolved = append_resolution(issued, resolution)

    assert empty.forecasts == ()
    assert issued.resolutions == ()
    assert resolved.forecasts == issued.forecasts
    assert resolved.forecasts[0].forecast_identity == original_identity
    assert resolved.resolutions == (resolution,)
    assert resolved.stream_identity != issued.stream_identity

    with pytest.raises(ValueError, match="already exists"):
        append_forecast(issued, forecast)
    with pytest.raises(ValueError, match="already has a resolution"):
        append_resolution(resolved, resolution)


def test_resolution_rejects_wrong_lineage_horizon_or_pending_outcome() -> None:
    forecast = _forecast()

    with pytest.raises(ValueError, match="signal lineage mismatch"):
        build_forecast_resolution(
            forecast,
            _outcome(
                OutcomeState.SUCCESS_TP1,
                signal_identity=_sha("wrong-signal"),
            ),
        )

    with pytest.raises(ValueError, match="horizon does not match"):
        build_forecast_resolution(
            forecast,
            _outcome(
                OutcomeState.SUCCESS_TP1,
                signal_identity=forecast.signal_freeze_identity,
                horizon=HORIZON + 1,
            ),
        )

    pending = OutcomeEvaluation(
        outcome_identity=_sha("pending-outcome"),
        signal_freeze_identity=forecast.signal_freeze_identity,
        evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        evaluated_as_of_ms=ISSUED_AT + 1_000,
        resolution_status=OutcomeResolutionStatus.PENDING,
        outcome_state=None,
        signal_initial_state=SignalState.ACTIVE,
        coverage_status=OutcomeCoverageStatus.NO_NEW_EVIDENCE,
        max_holding_bars=HORIZON,
        expected_bar_count=HORIZON,
        observed_bar_count=0,
        missing_open_times_ms=(),
        skipped_partial_decision_bucket=False,
        entry_observed=False,
        entry_candle_identity=None,
        highest_target_index=0,
        outcome_candle_identity=None,
        ambiguity_reason=None,
        not_evaluable_reason=None,
    )
    with pytest.raises(ValueError, match="cannot append pending"):
        build_forecast_resolution(forecast, pending)


def test_forecast_resolution_and_stream_identity_tampering_fail_closed() -> None:
    forecast = _forecast()
    resolution = build_forecast_resolution(
        forecast,
        _outcome(OutcomeState.SUCCESS_TP1, signal_identity=forecast.signal_freeze_identity),
    )
    stream = append_resolution(
        append_forecast(empty_forecast_stream(), forecast),
        resolution,
    )

    with pytest.raises(ValueError, match="forecast identity mismatch"):
        replace(forecast, target_label="tampered")
    with pytest.raises(ValueError, match="resolution identity mismatch"):
        replace(resolution, state=ForecastResolutionState.EXPIRED)
    with pytest.raises(ValueError, match="stream identity mismatch"):
        replace(stream, stream_identity="f" * 64)


def test_r20_stream_has_no_outcome_rewrite_execution_or_private_reasoning_surface() -> None:
    import crypto_signal.forecast_stream as forecast_stream

    source = inspect.getsource(forecast_stream).lower()
    forbidden = (
        "sqlite3",
        "paperfundledger",
        "write_text",
        "write_bytes",
        "import requests",
        "import httpx",
        "import urllib",
        "import socket",
        "place_order",
        "submit_order",
        "simulate_paper_fill",
        "chain_of_thought",
        "chain-of-thought",
        "private reasoning",
        "launchctl",
        "subprocess",
    )
    assert all(token not in source for token in forbidden)
    assert forecast_stream.REAL_CAPITAL == 0
