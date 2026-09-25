from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from crypto_signal.confluence.models import InvalidationTrigger, PriceZone
from crypto_signal.forecast_stream import (
    R20_FORECAST_ENGINE_VERSION,
    R20_FORECAST_SCHEMA_VERSION,
    R20_PROBABILITY_NOT_CALIBRATED,
    ForecastAuthority,
    ForecastTriggerKind,
    ImmutableForecast,
)
from crypto_signal.intelligence.confluence_matrix_v2 import (
    M6_SCORE_SEMANTIC,
    ConfluenceFamily,
    ConfluenceMatrixResolution,
    build_confluence_family_evidence,
    build_locked_m6_policy,
    evaluate_confluence_matrix,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import CircuitBreakerState
from crypto_signal.intelligence.meta_intelligence import MetaDirection, MetaEvidenceState
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.decision_proof import (
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
    ProofEvidenceVerdict,
    build_decision_proof_evidence_slice,
    build_decision_proof_snapshot,
    build_live_intelligence_feed_event,
)
from crypto_signal.product.intelligence_stream_ledger import (
    IntelligenceStreamLedger,
    StreamLedgerConflictError,
    StreamLedgerWriteDisposition,
)
from crypto_signal.product.intelligence_stream_models import (
    build_forecast_issued_source_event,
    build_stream_activation_boundary,
    build_stream_decision_context,
)
from crypto_signal.signals.models import SignalDirection, SignalState


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _confluence(*, as_of_ms: int, seed: str):
    directions = {
        ConfluenceFamily.GEOMETRY: MetaDirection.BULLISH,
        ConfluenceFamily.LIQUIDITY: MetaDirection.BULLISH,
        ConfluenceFamily.ORDER_FLOW: MetaDirection.BULLISH,
        ConfluenceFamily.DERIVATIVES: MetaDirection.BULLISH,
        ConfluenceFamily.ONCHAIN: MetaDirection.NEUTRAL,
    }
    strengths = {
        ConfluenceFamily.GEOMETRY: Decimal(1),
        ConfluenceFamily.LIQUIDITY: Decimal(1),
        ConfluenceFamily.ORDER_FLOW: Decimal(1),
        ConfluenceFamily.DERIVATIVES: Decimal("0.8"),
        ConfluenceFamily.ONCHAIN: Decimal(0),
    }
    evidence = tuple(
        build_confluence_family_evidence(
            family=family,
            asset="BTCUSDT",
            timeframe="4h",
            regime="trend_up",
            as_of_ms=as_of_ms,
            state=MetaEvidenceState.OBSERVED,
            direction=directions[family],
            directional_strength_0_1=strengths[family],
            evidence_quality_0_1=Decimal("0.90"),
            freshness_0_1=Decimal("0.95"),
            market_available_at_ms=as_of_ms - 100,
            observed_at_ms=as_of_ms - 50,
            source_engine_ids=(f"{family.value}-engine",),
            source_evidence_identities=(_sha(f"{seed}-{family.value}-source"),),
            material_conflict_identities=(),
            uncertainty_flags=(),
        )
        for family in sorted(ConfluenceFamily, key=lambda item: item.value)
    )
    return evaluate_confluence_matrix(
        build_locked_m6_policy(),
        evidence,
        candidate_direction=MetaDirection.BULLISH,
    )


def _forecast(*, confluence, as_of_ms: int, issued_at_ms: int, seed: str):
    signal_id = _sha(f"{seed}-signal")
    event_id = _sha(f"{seed}-event")
    source_ids = tuple(
        sorted((signal_id, confluence.snapshot_identity, event_id))
    )
    trigger_zone = PriceZone(Decimal(100), Decimal(102))
    target_zone = PriceZone(Decimal(108), Decimal(108))
    payload = {
        "asset": "BTC",
        "authority": ForecastAuthority.SHADOW,
        "calibrated_probability_0_1": None,
        "condition_code": "breakout",
        "confluence_identity": confluence.snapshot_identity,
        "confluence_opposition_score_0_100": confluence.opposition_score_0_100,
        "confluence_resolution": confluence.resolution,
        "confluence_score_semantic": M6_SCORE_SEMANTIC,
        "confluence_support_score_0_100": confluence.support_score_0_100,
        "direction": SignalDirection.BULLISH,
        "engine_version": R20_FORECAST_ENGINE_VERSION,
        "event_context_identity": event_id,
        "event_context_state": CircuitBreakerState.CLEAR,
        "event_context_triggers": (),
        "freshness_0_1": confluence.freshness_0_1,
        "horizon_bars": 8,
        "immutable_pre_outcome": True,
        "invalidation_price": Decimal(95),
        "invalidation_trigger": InvalidationTrigger.TOUCH_OR_CROSS,
        "issued_at_ms": issued_at_ms,
        "probability_authorization_identity": None,
        "probability_calibration_evidence_identity": None,
        "probability_scope_identity": None,
        "probability_status": R20_PROBABILITY_NOT_CALIBRATED,
        "production_authority": False,
        "real_capital": 0,
        "schema_version": R20_FORECAST_SCHEMA_VERSION,
        "signal_freeze_identity": signal_id,
        "signal_state": SignalState.ACTIVE,
        "source_as_of_ms": as_of_ms,
        "source_evidence_identities": source_ids,
        "symbol": "BTCUSDT",
        "target_label": "target_1",
        "target_zone": target_zone,
        "timeframe": "4h",
        "trigger_kind": ForecastTriggerKind.ENTRY_ZONE,
        "trigger_zone": trigger_zone,
        "uncertainty_flags": (),
        "version_refs": (),
    }
    return ImmutableForecast(
        forecast_identity=canonical_sha256(payload),
        schema_version=R20_FORECAST_SCHEMA_VERSION,
        engine_version=R20_FORECAST_ENGINE_VERSION,
        authority=ForecastAuthority.SHADOW,
        asset="BTC",
        symbol="BTCUSDT",
        timeframe="4h",
        issued_at_ms=issued_at_ms,
        source_as_of_ms=as_of_ms,
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
        confluence_identity=confluence.snapshot_identity,
        confluence_support_score_0_100=confluence.support_score_0_100,
        confluence_opposition_score_0_100=confluence.opposition_score_0_100,
        confluence_resolution=confluence.resolution,
        confluence_score_semantic=M6_SCORE_SEMANTIC,
        calibrated_probability_0_1=None,
        probability_status=R20_PROBABILITY_NOT_CALIBRATED,
        probability_authorization_identity=None,
        probability_calibration_evidence_identity=None,
        probability_scope_identity=None,
        event_context_identity=event_id,
        event_context_state=CircuitBreakerState.CLEAR,
        event_context_triggers=(),
        source_evidence_identities=source_ids,
        version_refs=(),
        freshness_0_1=confluence.freshness_0_1,
        uncertainty_flags=(),
    )


def _available(
    domain: ProofEvidenceDomain,
    *,
    as_of_ms: int,
    identities: tuple[str, ...],
    verdict: ProofEvidenceVerdict = ProofEvidenceVerdict.NEUTRAL,
):
    return build_decision_proof_evidence_slice(
        domain=domain,
        availability=ProofEvidenceAvailability.AVAILABLE,
        verdict=verdict,
        evidence_identities=identities,
        market_available_at_ms=as_of_ms - 10,
        observed_at_ms=as_of_ms,
        freshness_0_1=Decimal("0.90"),
        source_quality="accepted_source",
        summary_codes=(f"{domain.value}_available",),
    )


def _missing(domain: ProofEvidenceDomain):
    return build_decision_proof_evidence_slice(
        domain=domain,
        availability=ProofEvidenceAvailability.INSUFFICIENT,
        verdict=ProofEvidenceVerdict.INSUFFICIENT,
        summary_codes=(f"{domain.value}_insufficient",),
    )


def _proof(forecast: ImmutableForecast, *, as_of_ms: int, seed: str):
    slices = {
        ProofEvidenceDomain.FROZEN_CHART: _available(
            ProofEvidenceDomain.FROZEN_CHART,
            as_of_ms=as_of_ms,
            identities=(_sha(f"{seed}-chart"),),
        ),
        ProofEvidenceDomain.CONSUMED_CANDLES: _available(
            ProofEvidenceDomain.CONSUMED_CANDLES,
            as_of_ms=as_of_ms,
            identities=(_sha(f"{seed}-candles"),),
        ),
        ProofEvidenceDomain.ORDER_BOOK: _missing(ProofEvidenceDomain.ORDER_BOOK),
        ProofEvidenceDomain.LIQUIDITY_MAP: _missing(
            ProofEvidenceDomain.LIQUIDITY_MAP
        ),
        ProofEvidenceDomain.LIQUIDATION_MAP: _missing(
            ProofEvidenceDomain.LIQUIDATION_MAP
        ),
        ProofEvidenceDomain.ORDER_FLOW_CVD: _missing(
            ProofEvidenceDomain.ORDER_FLOW_CVD
        ),
        ProofEvidenceDomain.DERIVATIVES: _missing(
            ProofEvidenceDomain.DERIVATIVES
        ),
        ProofEvidenceDomain.ONCHAIN: _missing(ProofEvidenceDomain.ONCHAIN),
        ProofEvidenceDomain.EVENT_CONTEXT: _available(
            ProofEvidenceDomain.EVENT_CONTEXT,
            as_of_ms=as_of_ms,
            identities=(forecast.event_context_identity,),
        ),
        ProofEvidenceDomain.METHODOLOGY: _available(
            ProofEvidenceDomain.METHODOLOGY,
            as_of_ms=as_of_ms,
            identities=(
                forecast.signal_freeze_identity,
                forecast.confluence_identity,
            ),
            verdict=ProofEvidenceVerdict.SUPPORT,
        ),
        ProofEvidenceDomain.PROBABILITY_CALIBRATION: _missing(
            ProofEvidenceDomain.PROBABILITY_CALIBRATION
        ),
    }
    return build_decision_proof_snapshot(
        forecast,
        tuple(slices[domain] for domain in ProofEvidenceDomain),
    )


def _bundle(*, as_of_ms: int, issued_at_ms: int, seed: str):
    confluence = _confluence(as_of_ms=as_of_ms, seed=seed)
    assert confluence.resolution is ConfluenceMatrixResolution.MEASURED
    forecast = _forecast(
        confluence=confluence,
        as_of_ms=as_of_ms,
        issued_at_ms=issued_at_ms,
        seed=seed,
    )
    proof = _proof(forecast, as_of_ms=as_of_ms, seed=seed)
    old_feed_event = build_live_intelligence_feed_event(proof, forecast)
    context = build_stream_decision_context(forecast, proof, confluence)
    return confluence, forecast, context, old_feed_event


def test_stream_ledger_persists_full_five_family_breakdown(tmp_path) -> None:
    _, forecast, context, old_feed_event = _bundle(
        as_of_ms=1_000_000,
        issued_at_ms=1_000_100,
        seed="first",
    )
    activation = build_stream_activation_boundary(activated_at_ms=1_000_000)
    source_event = build_forecast_issued_source_event(
        activation,
        context,
        old_feed_event,
    )
    ledger = IntelligenceStreamLedger(tmp_path / "stream.sqlite3")

    assert (
        ledger.append_activation(activation)
        is StreamLedgerWriteDisposition.INSERTED
    )
    assert (
        ledger.append_issuance_bundle(context, source_event)
        is StreamLedgerWriteDisposition.INSERTED
    )
    assert (
        ledger.append_issuance_bundle(context, source_event)
        is StreamLedgerWriteDisposition.UNCHANGED
    )

    stored = ledger.read_context_for_forecast(forecast.forecast_identity)
    assert stored is not None
    embedded = stored["confluence"]
    assert embedded["snapshot_identity"] == context.confluence_identity
    assert embedded["support_score_0_100"] == "82.00"
    assert len(embedded["contributions"]) == 5
    by_family = {
        item["family"]: item
        for item in embedded["contributions"]
    }
    assert by_family[ConfluenceFamily.GEOMETRY.value]["support_points"] == "20.00"
    assert by_family[ConfluenceFamily.LIQUIDITY.value]["support_points"] == "25.00"
    assert (
        by_family[ConfluenceFamily.ORDER_FLOW.value]["support_points"]
        == "25.00"
    )
    assert by_family[ConfluenceFamily.DERIVATIVES.value]["support_points"] == "12.00"
    assert by_family[ConfluenceFamily.ONCHAIN.value]["support_points"] == "0.00"

    events = ledger.read_events(limit=10)
    assert len(events) == 1
    assert events[0]["source_event_identity"] == old_feed_event.event_identity
    assert events[0]["decision_context_identity"] == context.context_identity
    assert events[0]["materiality_codes"] == ["new_forecast_issued"]

    status = ledger.read_status()
    assert status.decision_context_count == 1
    assert status.source_event_count == 1
    assert status.latest_event_at_ms == 1_000_100
    assert status.real_capital == 0


def test_stream_refuses_rich_event_before_activation_boundary() -> None:
    _, _, context, old_feed_event = _bundle(
        as_of_ms=1_000_000,
        issued_at_ms=1_000_100,
        seed="pre-activation",
    )
    activation = build_stream_activation_boundary(activated_at_ms=1_000_101)

    with pytest.raises(ValueError, match="before activation boundary"):
        build_forecast_issued_source_event(
            activation,
            context,
            old_feed_event,
        )


def test_stream_ledger_rejects_chronological_backfill(tmp_path) -> None:
    activation = build_stream_activation_boundary(activated_at_ms=999_000)
    ledger = IntelligenceStreamLedger(tmp_path / "stream.sqlite3")
    ledger.append_activation(activation)

    _, _, later_context, later_old_event = _bundle(
        as_of_ms=1_100_000,
        issued_at_ms=1_100_100,
        seed="later",
    )
    later_event = build_forecast_issued_source_event(
        activation,
        later_context,
        later_old_event,
    )
    ledger.append_issuance_bundle(later_context, later_event)

    _, _, earlier_context, earlier_old_event = _bundle(
        as_of_ms=1_050_000,
        issued_at_ms=1_050_100,
        seed="earlier",
    )
    earlier_event = build_forecast_issued_source_event(
        activation,
        earlier_context,
        earlier_old_event,
    )

    with pytest.raises(
        StreamLedgerConflictError,
        match="backfill or fork chronology",
    ):
        ledger.append_issuance_bundle(earlier_context, earlier_event)


def test_stream_sqlite_rows_are_immutable(tmp_path) -> None:
    _, _, context, old_feed_event = _bundle(
        as_of_ms=1_000_000,
        issued_at_ms=1_000_100,
        seed="immutable",
    )
    activation = build_stream_activation_boundary(activated_at_ms=1_000_000)
    event = build_forecast_issued_source_event(activation, context, old_feed_event)
    path = tmp_path / "stream.sqlite3"
    ledger = IntelligenceStreamLedger(path)
    ledger.append_activation(activation)
    ledger.append_issuance_bundle(context, event)

    with (
        sqlite3.connect(path) as connection,
        pytest.raises(
            sqlite3.DatabaseError,
            match="immutable intelligence stream ledger",
        ),
    ):
        connection.execute(
            "UPDATE stream_source_events SET subtype = 'tampered'"
        )


def test_query_only_stream_reads_never_initialize_missing_database(tmp_path) -> None:
    path = tmp_path / "missing-stream.sqlite3"
    ledger = IntelligenceStreamLedger(path)

    with pytest.raises(FileNotFoundError):
        ledger.read_status()
    assert not path.exists()
