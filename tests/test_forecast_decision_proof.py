from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.confluence.adapters import (
    elliott_result_evidence,
    harmonic_result_evidence,
    price_action_structure_evidence,
)
from crypto_signal.confluence.agreement import analyze_confluence
from crypto_signal.confluence.models import InvalidationTrigger, PriceZone
from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.evaluation.aggregate import confluence_score_bucket
from crypto_signal.evaluation.calibration import (
    CalibratedProbability,
    CalibrationScope,
    ProbabilitySemantic,
)
from crypto_signal.forecast.builders import (
    build_conditional_forecast,
    build_decision_proof,
    build_forecast_resolution,
    verify_decision_proof_identity,
    verify_forecast_identity,
    verify_forecast_resolution_identity,
)
from crypto_signal.forecast.models import DecisionProofAuthority
from crypto_signal.forecast.store import (
    ForecastLedgerConflictError,
    ForecastLedgerWriteDisposition,
    ImmutableForecastLedger,
)
from crypto_signal.ledger.bundle import (
    DecisionFreezeBundle,
    build_decision_freeze_bundle,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.ledger.store import ImmutableSignalLedger
from crypto_signal.methodologies.elliott.analysis import analyze_elliott
from crypto_signal.methodologies.harmonic.analysis import analyze_harmonics
from crypto_signal.methodologies.price_action.analysis import analyze_price_action
from crypto_signal.outcomes.evaluator import evaluate_outcome
from crypto_signal.outcomes.models import EvidenceClass
from crypto_signal.signals.models import (
    EntryReferenceModel,
    RiskRewardTarget,
    SignalDirection,
    SignalGeometry,
    SignalState,
)
from crypto_signal.signals.semantics import build_signal_decision

BASE_MS = 900_000
START_MS = int(datetime(2026, 9, 1, tzinfo=UTC).timestamp() * 1000)


def _candles() -> tuple[Candle, ...]:
    output: list[Candle] = []
    for index in range(96):
        block = index % 16
        base = Decimal(1000 + (index // 16) * 3)
        if block in {3, 4, 5}:
            base += Decimal(24)
        elif block in {10, 11, 12}:
            base -= Decimal(22)
        close = base + (Decimal(4) if index % 2 == 0 else Decimal(-4))
        open_time_ms = START_MS + index * BASE_MS
        close_time_ms = open_time_ms + BASE_MS - 1
        output.append(
            Candle(
                exchange=Exchange.BYBIT,
                market_type=MarketType.SPOT,
                symbol="BTCUSDT",
                timeframe="15m",
                open_time_ms=open_time_ms,
                close_time_ms=close_time_ms,
                open=base,
                high=max(base, close) + Decimal(3),
                low=min(base, close) - Decimal(3),
                close=close,
                volume=Decimal(1),
                quote_volume=Decimal(1000),
                trade_count=None,
                is_closed=True,
                source=DataSource.REST,
                source_timestamp_ms=close_time_ms + 1,
                ingested_at_ms=close_time_ms + 2,
                adapter_version="forecast-test/1",
            )
        )
    return tuple(output)


def _base_bundle() -> DecisionFreezeBundle:
    source = _candles()
    as_of_ms = max(candle.ingested_at_ms for candle in source)
    pa = analyze_price_action(source, as_of_ms=as_of_ms)
    harmonic = analyze_harmonics(source, as_of_ms=as_of_ms)
    elliott = analyze_elliott(source, as_of_ms=as_of_ms)

    evidence = []
    pa_item = price_action_structure_evidence(pa)
    if pa_item is not None:
        evidence.append(pa_item)
    evidence.extend(harmonic_result_evidence(harmonic))
    evidence.extend(elliott_result_evidence(elliott))
    confluence = analyze_confluence(
        evidence,
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        as_of_ms=as_of_ms,
    )
    decision = build_signal_decision(confluence)
    return build_decision_freeze_bundle(
        decision=decision,
        confluence=confluence,
        price_action=pa,
        harmonic=harmonic,
        elliott=elliott,
        candles=source,
    )


def _geometry_bundle(*, active: bool = False) -> DecisionFreezeBundle:
    base = _base_bundle()
    assert base.selected_evidence
    source = base.selected_evidence[0]
    geometry = SignalGeometry(
        source_evidence_id=source.evidence_id,
        source_methodology=source.methodology,
        entry_zone=PriceZone(low=Decimal(1000), high=Decimal(1010)),
        entry_reference_price=Decimal(1005),
        entry_reference_model=(
            EntryReferenceModel.ZONE_MIDPOINT_REFERENCE_NOT_EXECUTION
        ),
        invalidation_price=Decimal(980),
        invalidation_trigger=InvalidationTrigger.TOUCH_OR_CROSS,
        targets=(
            RiskRewardTarget(
                label="TP1",
                target_price=Decimal(1030),
                reference_rr=Decimal("1.25"),
            ),
            RiskRewardTarget(
                label="TP2",
                target_price=Decimal(1050),
                reference_rr=Decimal("2.25"),
            ),
        ),
    )
    decision = replace(
        base.signal_decision,
        freeze_identity=canonical_sha256(
            {
                "kind": "forecast-test-signal",
                "base": base.bundle_identity,
                "active": active,
            }
        ),
        state=SignalState.ACTIVE if active else SignalState.WATCH,
        direction=SignalDirection.BULLISH,
        setup_type="forecast-test-setup",
        geometry=geometry,
    )
    return build_decision_freeze_bundle(
        decision=decision,
        confluence=base.confluence,
        price_action=base.price_action,
        harmonic=base.harmonic,
        elliott=base.elliott,
        candles=base.candles,
    )


def _forecast(
    bundle: DecisionFreezeBundle,
    *,
    horizon_bars: int = 4,
    probability: CalibratedProbability | None = None,
):
    return build_conditional_forecast(
        bundle,
        issued_at_ms=bundle.signal_decision.as_of_ms + 100,
        horizon_bars=horizon_bars,
        target_label="TP1",
        calibrated_probability=probability,
    )


def _accepted_probability(
    bundle: DecisionFreezeBundle,
    *,
    horizon_bars: int = 4,
) -> CalibratedProbability:
    decision = bundle.signal_decision
    return CalibratedProbability(
        model_version="forecast-test-calibration/1",
        semantic=ProbabilitySemantic.CALIBRATED_TARGET_SUCCESS_BEFORE_FAIL_SL,
        scope=CalibrationScope(
            symbol=decision.symbol,
            timeframe=decision.timeframe,
            direction=decision.direction,
            setup_type=decision.setup_type,
            max_holding_bars=horizon_bars,
        ),
        score_bucket=confluence_score_bucket(
            decision.agreement.confluence_score
        ),
        probability=Decimal("0.62"),
        train_n=60,
        holdout_n=30,
        brier_score=Decimal("0.20"),
        brier_skill_score=Decimal("0.10"),
        expected_calibration_error=Decimal("0.05"),
        trained_through_as_of_ms=decision.as_of_ms - 2_000,
        evaluated_through_as_of_ms=decision.as_of_ms - 1_000,
    )


def test_conditional_forecast_is_geometry_bound_and_deterministic() -> None:
    bundle = _geometry_bundle()
    first = _forecast(bundle)
    second = _forecast(bundle)

    assert first == second
    assert first.trigger_zone == bundle.signal_decision.geometry.entry_zone
    assert first.target_label == "TP1"
    assert first.target_price == Decimal(1030)
    assert first.invalidation_price == Decimal(980)
    assert first.calibrated_probability is None
    verify_forecast_identity(first)


def test_conditional_forecast_rejects_non_frozen_target_and_missing_geometry() -> None:
    bundle = _geometry_bundle()
    with pytest.raises(ValueError, match="target must exist"):
        build_conditional_forecast(
            bundle,
            issued_at_ms=bundle.signal_decision.as_of_ms + 100,
            horizon_bars=4,
            target_label="TP9",
        )

    no_geometry = replace(
        bundle.signal_decision,
        freeze_identity="1" * 64,
        geometry=None,
    )
    no_geometry_bundle = build_decision_freeze_bundle(
        decision=no_geometry,
        confluence=bundle.confluence,
        price_action=bundle.price_action,
        harmonic=bundle.harmonic,
        elliott=bundle.elliott,
        candles=bundle.candles,
    )
    with pytest.raises(ValueError, match="requires frozen signal geometry"):
        _forecast(no_geometry_bundle)


def test_probability_snapshot_requires_exact_scope_and_past_cutoff() -> None:
    bundle = _geometry_bundle(active=True)
    probability = _accepted_probability(bundle)
    forecast = _forecast(bundle, probability=probability)

    assert forecast.calibrated_probability == Decimal("0.62")
    assert forecast.probability_train_n == 60
    assert forecast.probability_holdout_n == 30

    future = replace(
        probability,
        evaluated_through_as_of_ms=bundle.signal_decision.as_of_ms + 1,
    )
    with pytest.raises(ValueError, match="evaluation cutoff postdates"):
        _forecast(bundle, probability=future)

    wrong_scope = replace(
        probability,
        scope=replace(probability.scope, max_holding_bars=8),
    )
    with pytest.raises(ValueError, match="scope does not match"):
        _forecast(bundle, probability=wrong_scope)


def test_decision_proof_uses_same_frozen_evidence_for_simple_and_technical() -> None:
    bundle = _geometry_bundle()
    forecast = _forecast(bundle)
    proof = build_decision_proof(
        bundle,
        forecast,
        authority=DecisionProofAuthority.RESEARCH,
        created_at_ms=forecast.issued_at_ms + 1,
        snapshot_refs=("market-tape-ref-1",),
    )

    classified = (
        set(proof.supporting_evidence_ids)
        | set(proof.opposing_evidence_ids)
        | set(proof.ambiguous_evidence_ids)
    )
    assert classified == {
        item.evidence_id for item in bundle.selected_evidence
    }
    assert "olasılık değildir" in proof.simple_explanation_tr
    assert "probability=NOT_CALIBRATED" in proof.technical_explanation
    assert proof.snapshot_refs == (
        bundle.bundle_identity,
        "market-tape-ref-1",
    )
    verify_decision_proof_identity(proof)


def test_forecast_resolution_reuses_existing_outcome_identity() -> None:
    bundle = _geometry_bundle(active=True)
    forecast = _forecast(bundle)
    outcome = evaluate_outcome(
        bundle.signal_decision,
        bundle.candles,
        as_of_ms=bundle.signal_decision.as_of_ms,
        evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        max_holding_bars=4,
    )

    resolution = build_forecast_resolution(forecast, outcome)

    assert resolution.outcome_identity == outcome.outcome_identity
    assert resolution.signal_freeze_identity == (
        bundle.signal_decision.freeze_identity
    )
    assert resolution.horizon_bars == 4
    verify_forecast_resolution_identity(resolution)

    wrong_horizon = evaluate_outcome(
        bundle.signal_decision,
        bundle.candles,
        as_of_ms=bundle.signal_decision.as_of_ms,
        evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        max_holding_bars=8,
    )
    with pytest.raises(ValueError, match="horizon mismatch"):
        build_forecast_resolution(forecast, wrong_horizon)


def test_forecast_ledger_requires_parent_and_is_idempotent(tmp_path: Path) -> None:
    bundle = _geometry_bundle(active=True)
    forecast = _forecast(bundle)
    proof = build_decision_proof(
        bundle,
        forecast,
        authority=DecisionProofAuthority.RESEARCH,
        created_at_ms=forecast.issued_at_ms + 1,
    )
    path = tmp_path / "ledger.sqlite3"
    forecast_ledger = ImmutableForecastLedger(path)

    with pytest.raises(ForecastLedgerConflictError, match="unknown signal freeze"):
        forecast_ledger.append_forecast(
            forecast,
            appended_at_ms=forecast.issued_at_ms + 1,
        )

    signal_ledger = ImmutableSignalLedger(path)
    signal_ledger.freeze(
        bundle,
        frozen_at_ms=forecast.issued_at_ms,
    )

    assert (
        forecast_ledger.append_forecast(
            forecast,
            appended_at_ms=forecast.issued_at_ms + 1,
        )
        is ForecastLedgerWriteDisposition.INSERTED
    )
    assert (
        forecast_ledger.append_forecast(
            forecast,
            appended_at_ms=forecast.issued_at_ms + 2,
        )
        is ForecastLedgerWriteDisposition.UNCHANGED
    )
    assert (
        forecast_ledger.append_proof(
            proof,
            appended_at_ms=proof.created_at_ms + 1,
        )
        is ForecastLedgerWriteDisposition.INSERTED
    )

    outcome = evaluate_outcome(
        bundle.signal_decision,
        bundle.candles,
        as_of_ms=bundle.signal_decision.as_of_ms,
        evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        max_holding_bars=4,
    )
    resolution = build_forecast_resolution(forecast, outcome)
    with pytest.raises(ForecastLedgerConflictError, match="unknown outcome"):
        forecast_ledger.append_resolution(
            resolution,
            appended_at_ms=resolution.evaluated_as_of_ms + 1,
        )

    signal_ledger.append_outcome_evaluation(
        outcome,
        appended_at_ms=outcome.evaluated_as_of_ms + 1,
    )
    assert (
        forecast_ledger.append_resolution(
            resolution,
            appended_at_ms=resolution.evaluated_as_of_ms + 2,
        )
        is ForecastLedgerWriteDisposition.INSERTED
    )
    assert (
        forecast_ledger.append_resolution(
            resolution,
            appended_at_ms=resolution.evaluated_as_of_ms + 3,
        )
        is ForecastLedgerWriteDisposition.UNCHANGED
    )

    counts = forecast_ledger.counts()
    assert counts.forecasts == 1
    assert counts.proofs == 1
    assert counts.resolutions == 1


def test_forecast_ledger_tables_are_sql_immutable(tmp_path: Path) -> None:
    bundle = _geometry_bundle(active=True)
    forecast = _forecast(bundle)
    proof = build_decision_proof(
        bundle,
        forecast,
        authority=DecisionProofAuthority.RESEARCH,
        created_at_ms=forecast.issued_at_ms + 1,
    )
    outcome = evaluate_outcome(
        bundle.signal_decision,
        bundle.candles,
        as_of_ms=bundle.signal_decision.as_of_ms,
        evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        max_holding_bars=4,
    )
    resolution = build_forecast_resolution(forecast, outcome)

    path = tmp_path / "ledger.sqlite3"
    signal_ledger = ImmutableSignalLedger(path)
    signal_ledger.freeze(bundle, frozen_at_ms=forecast.issued_at_ms)
    signal_ledger.append_outcome_evaluation(
        outcome,
        appended_at_ms=outcome.evaluated_as_of_ms + 1,
    )
    ledger = ImmutableForecastLedger(path)
    ledger.append_forecast(
        forecast,
        appended_at_ms=forecast.issued_at_ms + 1,
    )
    ledger.append_proof(
        proof,
        appended_at_ms=proof.created_at_ms + 1,
    )
    ledger.append_resolution(
        resolution,
        appended_at_ms=resolution.evaluated_as_of_ms + 2,
    )

    with sqlite3.connect(path) as connection:
        for statement in (
            "UPDATE conditional_forecasts SET target_label = 'x'",
            "DELETE FROM decision_proofs",
            "DELETE FROM forecast_resolutions",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="immutable forecast ledger"):
                connection.execute(statement)
