from __future__ import annotations

import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.confluence.models import InvalidationTrigger, PriceZone
from crypto_signal.forecast_stream import (
    R20_FORECAST_ENGINE_VERSION,
    R20_FORECAST_SCHEMA_VERSION,
    R20_PROBABILITY_NOT_CALIBRATED,
    R20_RESOLUTION_SCHEMA_VERSION,
    ForecastAuthority,
    ForecastResolution,
    ForecastResolutionState,
    ForecastTriggerKind,
    ImmutableForecast,
)
from crypto_signal.intelligence.confluence_matrix_v2 import (
    M6_SCORE_SEMANTIC,
    ConfluenceMatrixResolution,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import CircuitBreakerState
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.outcomes.models import EvidenceClass, OutcomeState
from crypto_signal.product.decision_proof import (
    DECISION_PROOF_ENGINE_VERSION,
    LiveFeedEventKind,
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
    ProofEvidenceVerdict,
    append_live_intelligence_feed_event,
    build_decision_proof_evidence_slice,
    build_decision_proof_snapshot,
    build_live_intelligence_feed_event,
    empty_live_intelligence_feed,
)
from crypto_signal.signals.models import SignalDirection, SignalState

AS_OF = 1_000_000
ISSUED_AT = AS_OF + 100
EVALUATED_AT = ISSUED_AT + 10_000


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _forecast(*, calibrated: bool = False) -> ImmutableForecast:
    signal_id = _sha("signal")
    confluence_id = _sha("confluence")
    event_id = _sha("event")
    source_ids = {signal_id, confluence_id, event_id}

    probability = Decimal("0.67") if calibrated else None
    probability_status = "calibrated" if calibrated else R20_PROBABILITY_NOT_CALIBRATED
    probability_authorization_identity = _sha("probability-authorization") if calibrated else None
    probability_calibration_identity = _sha("probability-calibration") if calibrated else None
    probability_scope_identity = _sha("probability-scope") if calibrated else None
    if calibrated:
        source_ids.update(
            {
                probability_authorization_identity,
                probability_calibration_identity,
                _sha("probability-source-forecast"),
                _sha("probability-source-prediction"),
                _sha("probability-walk-forward-fit"),
            }
        )

    trigger_zone = PriceZone(Decimal(100), Decimal(102))
    target_zone = PriceZone(Decimal(108), Decimal(108))
    version_refs = ()
    uncertainty = ("bounded_uncertainty",)
    ordered_source_ids = tuple(sorted(source_ids))
    payload = {
        "asset": "BTC",
        "authority": ForecastAuthority.SHADOW,
        "calibrated_probability_0_1": probability,
        "condition_code": "breakout",
        "confluence_identity": confluence_id,
        "confluence_opposition_score_0_100": Decimal("0.00"),
        "confluence_resolution": ConfluenceMatrixResolution.MEASURED,
        "confluence_score_semantic": M6_SCORE_SEMANTIC,
        "confluence_support_score_0_100": Decimal("82.00"),
        "direction": SignalDirection.BULLISH,
        "engine_version": R20_FORECAST_ENGINE_VERSION,
        "event_context_identity": event_id,
        "event_context_state": CircuitBreakerState.CLEAR,
        "event_context_triggers": (),
        "freshness_0_1": Decimal("0.95"),
        "horizon_bars": 8,
        "immutable_pre_outcome": True,
        "invalidation_price": Decimal(95),
        "invalidation_trigger": InvalidationTrigger.TOUCH_OR_CROSS,
        "issued_at_ms": ISSUED_AT,
        "probability_authorization_identity": probability_authorization_identity,
        "probability_calibration_evidence_identity": probability_calibration_identity,
        "probability_scope_identity": probability_scope_identity,
        "probability_status": probability_status,
        "production_authority": False,
        "real_capital": 0,
        "schema_version": R20_FORECAST_SCHEMA_VERSION,
        "signal_freeze_identity": signal_id,
        "signal_state": SignalState.ACTIVE,
        "source_as_of_ms": AS_OF,
        "source_evidence_identities": ordered_source_ids,
        "symbol": "BTCUSDT",
        "target_label": "target_1",
        "target_zone": target_zone,
        "timeframe": "4h",
        "trigger_kind": ForecastTriggerKind.ENTRY_ZONE,
        "trigger_zone": trigger_zone,
        "uncertainty_flags": uncertainty,
        "version_refs": version_refs,
    }
    return ImmutableForecast(
        forecast_identity=canonical_sha256(payload),
        schema_version=R20_FORECAST_SCHEMA_VERSION,
        engine_version=R20_FORECAST_ENGINE_VERSION,
        authority=ForecastAuthority.SHADOW,
        asset="BTC",
        symbol="BTCUSDT",
        timeframe="4h",
        issued_at_ms=ISSUED_AT,
        source_as_of_ms=AS_OF,
        signal_freeze_identity=signal_id,
        signal_state=SignalState.ACTIVE,
        direction=SignalDirection.BULLISH,
        condition_code="breakout",
        trigger_kind=ForecastTriggerKind.ENTRY_ZONE,
        trigger_zone=trigger_zone,
        target_label="target_1",
        target_zone=target_zone,
        invalidation_price=Decimal(95),
        invalidation_trigger=InvalidationTrigger.TOUCH_OR_CROSS,
        horizon_bars=8,
        confluence_identity=confluence_id,
        confluence_support_score_0_100=Decimal("82.00"),
        confluence_opposition_score_0_100=Decimal("0.00"),
        confluence_resolution=ConfluenceMatrixResolution.MEASURED,
        confluence_score_semantic=M6_SCORE_SEMANTIC,
        calibrated_probability_0_1=probability,
        probability_status=probability_status,
        probability_authorization_identity=probability_authorization_identity,
        probability_calibration_evidence_identity=probability_calibration_identity,
        probability_scope_identity=probability_scope_identity,
        event_context_identity=event_id,
        event_context_state=CircuitBreakerState.CLEAR,
        event_context_triggers=(),
        source_evidence_identities=ordered_source_ids,
        version_refs=version_refs,
        freshness_0_1=Decimal("0.95"),
        uncertainty_flags=uncertainty,
    )


def _available(
    domain: ProofEvidenceDomain,
    *ids: str,
    verdict: ProofEvidenceVerdict = ProofEvidenceVerdict.NEUTRAL,
    observed_at_ms: int = AS_OF,
):
    return build_decision_proof_evidence_slice(
        domain=domain,
        availability=ProofEvidenceAvailability.AVAILABLE,
        verdict=verdict,
        evidence_identities=tuple(ids),
        market_available_at_ms=observed_at_ms - 1,
        observed_at_ms=observed_at_ms,
        freshness_0_1=Decimal("0.90"),
        source_quality="accepted_source",
        summary_codes=(f"{domain.value}_available",),
    )


def _missing(
    domain: ProofEvidenceDomain,
    *,
    unsupported: bool = False,
):
    return build_decision_proof_evidence_slice(
        domain=domain,
        availability=(
            ProofEvidenceAvailability.UNSUPPORTED
            if unsupported
            else ProofEvidenceAvailability.INSUFFICIENT
        ),
        verdict=ProofEvidenceVerdict.INSUFFICIENT,
        summary_codes=(
            f"{domain.value}_{'unsupported' if unsupported else 'insufficient'}",
        ),
    )


def _slices(forecast: ImmutableForecast):
    extra_probability_ids = {
        _sha("probability-source-forecast"),
        _sha("probability-source-prediction"),
        _sha("probability-walk-forward-fit"),
    }
    probability_ids: tuple[str, ...] = ()
    if forecast.calibrated_probability_0_1 is not None:
        assert forecast.probability_authorization_identity is not None
        assert forecast.probability_calibration_evidence_identity is not None
        probability_ids = tuple(
            sorted(
                {
                    forecast.probability_authorization_identity,
                    forecast.probability_calibration_evidence_identity,
                    *extra_probability_ids,
                }
            )
        )

    rows = {
        ProofEvidenceDomain.FROZEN_CHART: _available(
            ProofEvidenceDomain.FROZEN_CHART,
            _sha("chart"),
        ),
        ProofEvidenceDomain.CONSUMED_CANDLES: _available(
            ProofEvidenceDomain.CONSUMED_CANDLES,
            _sha("candles"),
        ),
        ProofEvidenceDomain.ORDER_BOOK: _missing(ProofEvidenceDomain.ORDER_BOOK),
        ProofEvidenceDomain.LIQUIDITY_MAP: _missing(
            ProofEvidenceDomain.LIQUIDITY_MAP,
        ),
        ProofEvidenceDomain.LIQUIDATION_MAP: _missing(
            ProofEvidenceDomain.LIQUIDATION_MAP,
            unsupported=True,
        ),
        ProofEvidenceDomain.ORDER_FLOW_CVD: _missing(
            ProofEvidenceDomain.ORDER_FLOW_CVD,
        ),
        ProofEvidenceDomain.DERIVATIVES: _missing(
            ProofEvidenceDomain.DERIVATIVES,
        ),
        ProofEvidenceDomain.ONCHAIN: _missing(ProofEvidenceDomain.ONCHAIN),
        ProofEvidenceDomain.EVENT_CONTEXT: _available(
            ProofEvidenceDomain.EVENT_CONTEXT,
            forecast.event_context_identity,
            verdict=ProofEvidenceVerdict.NEUTRAL,
        ),
        ProofEvidenceDomain.METHODOLOGY: _available(
            ProofEvidenceDomain.METHODOLOGY,
            forecast.signal_freeze_identity,
            forecast.confluence_identity,
            verdict=ProofEvidenceVerdict.SUPPORT,
        ),
        ProofEvidenceDomain.PROBABILITY_CALIBRATION: (
            _available(
                ProofEvidenceDomain.PROBABILITY_CALIBRATION,
                *probability_ids,
                verdict=ProofEvidenceVerdict.SUPPORT,
            )
            if probability_ids
            else _missing(ProofEvidenceDomain.PROBABILITY_CALIBRATION)
        ),
    }
    return tuple(rows[domain] for domain in ProofEvidenceDomain)


def _resolution(forecast: ImmutableForecast) -> ForecastResolution:
    payload = {
        "engine_version": R20_FORECAST_ENGINE_VERSION,
        "evaluated_at_ms": EVALUATED_AT,
        "evidence_class": EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        "forecast_identity": forecast.forecast_identity,
        "original_forecast_unchanged": True,
        "production_authority": False,
        "real_capital": 0,
        "reason_codes": ("source_outcome_success_tp1",),
        "schema_version": R20_RESOLUTION_SCHEMA_VERSION,
        "signal_freeze_identity": forecast.signal_freeze_identity,
        "source_outcome_identity": _sha("resolved-outcome"),
        "source_outcome_state": OutcomeState.SUCCESS_TP1,
        "state": ForecastResolutionState.HIT_TARGET,
    }
    return ForecastResolution(
        resolution_identity=canonical_sha256(payload),
        schema_version=R20_RESOLUTION_SCHEMA_VERSION,
        engine_version=R20_FORECAST_ENGINE_VERSION,
        forecast_identity=forecast.forecast_identity,
        signal_freeze_identity=forecast.signal_freeze_identity,
        source_outcome_identity=_sha("resolved-outcome"),
        evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        evaluated_at_ms=EVALUATED_AT,
        state=ForecastResolutionState.HIT_TARGET,
        source_outcome_state=OutcomeState.SUCCESS_TP1,
        reason_codes=("source_outcome_success_tp1",),
    )


def test_decision_proof_requires_exact_canonical_domain_set() -> None:
    forecast = _forecast()
    slices = _slices(forecast)

    proof = build_decision_proof_snapshot(forecast, slices)
    assert tuple(item.domain for item in proof.evidence_slices) == tuple(
        sorted(ProofEvidenceDomain, key=lambda item: item.value)
    )
    assert proof.evidence_summary.total_domain_count == len(ProofEvidenceDomain)
    assert proof.evidence_summary.available_count == 4
    assert proof.private_reasoning_exposed is False
    assert proof.read_only is True
    assert proof.production_authority is False
    assert proof.real_capital == 0

    with pytest.raises(ValueError, match="one evidence slice per domain"):
        build_decision_proof_snapshot(forecast, slices[:-1])


def test_unavailable_evidence_is_explicit_and_cannot_carry_hidden_measurements() -> None:
    missing = _missing(ProofEvidenceDomain.ORDER_BOOK)
    assert missing.availability is ProofEvidenceAvailability.INSUFFICIENT
    assert missing.verdict is ProofEvidenceVerdict.INSUFFICIENT
    assert missing.evidence_identities == ()

    with pytest.raises(ValueError, match="cannot carry evidence identities"):
        build_decision_proof_evidence_slice(
            domain=ProofEvidenceDomain.ORDER_BOOK,
            availability=ProofEvidenceAvailability.INSUFFICIENT,
            verdict=ProofEvidenceVerdict.INSUFFICIENT,
            evidence_identities=(_sha("hidden-order-book"),),
            summary_codes=("bad",),
        )


def test_forecast_source_lineage_must_be_covered_in_correct_domains() -> None:
    forecast = _forecast()
    slices = list(_slices(forecast))

    event_index = next(
        index
        for index, item in enumerate(slices)
        if item.domain is ProofEvidenceDomain.EVENT_CONTEXT
    )
    slices[event_index] = _available(
        ProofEvidenceDomain.EVENT_CONTEXT,
        _sha("wrong-event"),
    )
    with pytest.raises(ValueError, match="does not cover all forecast source"):
        build_decision_proof_snapshot(forecast, tuple(slices))

    slices = list(_slices(forecast))
    methodology_index = next(
        index
        for index, item in enumerate(slices)
        if item.domain is ProofEvidenceDomain.METHODOLOGY
    )
    slices[methodology_index] = _available(
        ProofEvidenceDomain.METHODOLOGY,
        forecast.confluence_identity,
    )
    with pytest.raises(ValueError, match="does not cover all forecast source"):
        build_decision_proof_snapshot(forecast, tuple(slices))


def test_future_evidence_cannot_enter_issuance_time_proof() -> None:
    forecast = _forecast()
    slices = list(_slices(forecast))
    chart_index = next(
        index
        for index, item in enumerate(slices)
        if item.domain is ProofEvidenceDomain.FROZEN_CHART
    )
    slices[chart_index] = _available(
        ProofEvidenceDomain.FROZEN_CHART,
        _sha("future-chart"),
        observed_at_ms=AS_OF + 1,
    )

    with pytest.raises(ValueError, match="observed after source as-of"):
        build_decision_proof_snapshot(forecast, tuple(slices))


def test_conditional_thesis_is_deterministic_and_never_increases_certainty() -> None:
    forecast = _forecast()
    first = build_decision_proof_snapshot(forecast, _slices(forecast))
    second = build_decision_proof_snapshot(
        forecast,
        tuple(reversed(_slices(forecast))),
    )

    assert first == second
    assert first.conditional_thesis == (
        "If BTCUSDT enters 100-102 while breakout remains valid, "
        "BULLISH target 108 remains valid unless invalidated at 95 within 8 bars."
    )
    assert "guarantee" not in first.conditional_thesis.lower()
    assert "certain" not in first.conditional_thesis.lower()


def test_uncalibrated_forecast_keeps_probability_explicitly_unavailable() -> None:
    forecast = _forecast(calibrated=False)
    proof = build_decision_proof_snapshot(forecast, _slices(forecast))
    probability_slice = next(
        item
        for item in proof.evidence_slices
        if item.domain is ProofEvidenceDomain.PROBABILITY_CALIBRATION
    )

    assert proof.probability_status == R20_PROBABILITY_NOT_CALIBRATED
    assert proof.calibrated_probability_0_1 is None
    assert probability_slice.availability is ProofEvidenceAvailability.INSUFFICIENT

    bad = list(_slices(forecast))
    index = next(
        i
        for i, item in enumerate(bad)
        if item.domain is ProofEvidenceDomain.PROBABILITY_CALIBRATION
    )
    bad[index] = _available(
        ProofEvidenceDomain.PROBABILITY_CALIBRATION,
        _sha("fabricated-probability"),
    )
    with pytest.raises(ValueError, match="uncalibrated Decision Proof"):
        build_decision_proof_snapshot(forecast, tuple(bad))


def test_calibrated_forecast_requires_exact_r19_probability_domain_lineage() -> None:
    forecast = _forecast(calibrated=True)
    proof = build_decision_proof_snapshot(forecast, _slices(forecast))
    probability_slice = next(
        item
        for item in proof.evidence_slices
        if item.domain is ProofEvidenceDomain.PROBABILITY_CALIBRATION
    )
    assert proof.calibrated_probability_0_1 == Decimal("0.67")
    assert probability_slice.availability is ProofEvidenceAvailability.AVAILABLE
    assert forecast.probability_authorization_identity in probability_slice.evidence_identities
    assert (
        forecast.probability_calibration_evidence_identity
        in probability_slice.evidence_identities
    )

    bad = list(_slices(forecast))
    index = next(
        i
        for i, item in enumerate(bad)
        if item.domain is ProofEvidenceDomain.PROBABILITY_CALIBRATION
    )
    bad[index] = _available(
        ProofEvidenceDomain.PROBABILITY_CALIBRATION,
        _sha("probability-source-forecast"),
        _sha("probability-source-prediction"),
        _sha("probability-walk-forward-fit"),
    )
    with pytest.raises(ValueError, match="does not cover all forecast source"):
        build_decision_proof_snapshot(forecast, tuple(bad))


def test_live_feed_issuance_and_resolution_are_read_only_state_transitions() -> None:
    forecast = _forecast()
    proof = build_decision_proof_snapshot(forecast, _slices(forecast))
    issuance = build_live_intelligence_feed_event(proof, forecast)
    resolution = _resolution(forecast)
    resolved = build_live_intelligence_feed_event(
        proof,
        forecast,
        resolution=resolution,
    )

    assert issuance.kind is LiveFeedEventKind.FORECAST_ISSUED
    assert issuance.event_at_ms == forecast.issued_at_ms
    assert issuance.state == forecast.signal_state.value
    assert issuance.resolution_identity is None
    assert resolved.kind is LiveFeedEventKind.FORECAST_RESOLVED
    assert resolved.event_at_ms == resolution.evaluated_at_ms
    assert resolved.state == ForecastResolutionState.HIT_TARGET.value
    assert resolved.resolution_identity == resolution.resolution_identity
    assert resolved.proof_identity == issuance.proof_identity
    assert proof.forecast_identity == forecast.forecast_identity


def test_live_feed_is_append_only_unique_and_chronological() -> None:
    forecast = _forecast()
    proof = build_decision_proof_snapshot(forecast, _slices(forecast))
    issuance = build_live_intelligence_feed_event(proof, forecast)
    resolved = build_live_intelligence_feed_event(
        proof,
        forecast,
        resolution=_resolution(forecast),
    )

    empty = empty_live_intelligence_feed()
    issued = append_live_intelligence_feed_event(empty, issuance)
    complete = append_live_intelligence_feed_event(issued, resolved)

    assert empty.events == ()
    assert issued.events == (issuance,)
    assert complete.events == (issuance, resolved)

    with pytest.raises(ValueError, match="already exists|already contains"):
        append_live_intelligence_feed_event(issued, issuance)
    with pytest.raises(ValueError, match="requires prior forecast issuance"):
        append_live_intelligence_feed_event(empty_live_intelligence_feed(), resolved)


def test_identity_tampering_fails_closed() -> None:
    forecast = _forecast()
    slices = _slices(forecast)
    proof = build_decision_proof_snapshot(forecast, slices)
    event = build_live_intelligence_feed_event(proof, forecast)
    feed = append_live_intelligence_feed_event(
        empty_live_intelligence_feed(),
        event,
    )

    with pytest.raises(ValueError, match="slice identity mismatch"):
        replace(slices[0], summary_codes=("tampered",))
    with pytest.raises(ValueError, match="Decision Proof identity mismatch"):
        replace(proof, conditional_thesis="tampered")
    with pytest.raises(ValueError, match="event identity mismatch"):
        replace(event, state="tampered")
    with pytest.raises(ValueError, match="snapshot identity mismatch"):
        replace(feed, snapshot_identity="f" * 64)


def test_decision_proof_surface_has_no_private_reasoning_execution_or_write_authority() -> None:
    from crypto_signal.product import decision_proof

    source = inspect.getsource(decision_proof).lower()
    forbidden = (
        "chain_of_thought",
        "chain-of-thought",
        "private reasoning:",
        "sqlite3",
        "write_text",
        "write_bytes",
        "import requests",
        "import httpx",
        "import urllib",
        "import socket",
        "place_order",
        "submit_order",
        "simulate_paper_fill",
        "launchctl",
        "subprocess",
    )
    assert all(token not in source for token in forbidden)
    assert decision_proof.REAL_CAPITAL == 0
