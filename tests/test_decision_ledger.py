from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from crypto_signal.confluence.models import InvalidationTrigger, PriceZone
from crypto_signal.decision_ledger import (
    DecisionLedgerConflictError,
    DecisionLedgerWriteDisposition,
    ImmutableDecisionEvidenceLedger,
)
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
    ConfluenceMatrixResolution,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import CircuitBreakerState
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.decision_proof import (
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
    ProofEvidenceVerdict,
    build_decision_proof_evidence_slice,
    build_decision_proof_snapshot,
    build_live_intelligence_feed_event,
)
from crypto_signal.signals.models import SignalDirection, SignalState

AS_OF = 1_000_000
ISSUED_AT = AS_OF + 100


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _forecast() -> ImmutableForecast:
    signal_id = _sha("signal")
    confluence_id = _sha("confluence")
    event_id = _sha("event")
    source_ids = tuple(sorted((signal_id, confluence_id, event_id)))
    trigger_zone = PriceZone(Decimal(100), Decimal(102))
    target_zone = PriceZone(Decimal(108), Decimal(108))
    payload = {
        "asset": "BTC",
        "authority": ForecastAuthority.SHADOW,
        "calibrated_probability_0_1": None,
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
        "probability_authorization_identity": None,
        "probability_calibration_evidence_identity": None,
        "probability_scope_identity": None,
        "probability_status": R20_PROBABILITY_NOT_CALIBRATED,
        "production_authority": False,
        "real_capital": 0,
        "schema_version": R20_FORECAST_SCHEMA_VERSION,
        "signal_freeze_identity": signal_id,
        "signal_state": SignalState.ACTIVE,
        "source_as_of_ms": AS_OF,
        "source_evidence_identities": source_ids,
        "symbol": "BTCUSDT",
        "target_label": "target_1",
        "target_zone": target_zone,
        "timeframe": "4h",
        "trigger_kind": ForecastTriggerKind.ENTRY_ZONE,
        "trigger_zone": trigger_zone,
        "uncertainty_flags": ("bounded_uncertainty",),
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
        freshness_0_1=Decimal("0.95"),
        uncertainty_flags=("bounded_uncertainty",),
    )


def _available(
    domain: ProofEvidenceDomain,
    *identities: str,
    verdict: ProofEvidenceVerdict = ProofEvidenceVerdict.NEUTRAL,
):
    return build_decision_proof_evidence_slice(
        domain=domain,
        availability=ProofEvidenceAvailability.AVAILABLE,
        verdict=verdict,
        evidence_identities=tuple(identities),
        market_available_at_ms=AS_OF - 1,
        observed_at_ms=AS_OF,
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


def _proof(forecast: ImmutableForecast):
    slices = {
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
            forecast.event_context_identity,
        ),
        ProofEvidenceDomain.METHODOLOGY: _available(
            ProofEvidenceDomain.METHODOLOGY,
            forecast.signal_freeze_identity,
            forecast.confluence_identity,
            verdict=ProofEvidenceVerdict.SUPPORT,
        ),
        ProofEvidenceDomain.PROBABILITY_CALIBRATION: _missing(
            ProofEvidenceDomain.PROBABILITY_CALIBRATION
        ),
    }
    ordered = tuple(slices[domain] for domain in ProofEvidenceDomain)
    return build_decision_proof_snapshot(forecast, ordered)


def test_decision_ledger_persists_and_replays_exact_read_only_evidence(
    tmp_path,
) -> None:
    path = tmp_path / "decision_evidence.sqlite3"
    ledger = ImmutableDecisionEvidenceLedger(path)
    forecast = _forecast()
    proof = _proof(forecast)
    event = build_live_intelligence_feed_event(proof, forecast)

    assert ledger.append_forecast(forecast) is DecisionLedgerWriteDisposition.INSERTED
    assert ledger.append_proof(proof) is DecisionLedgerWriteDisposition.INSERTED
    assert ledger.append_feed_event(event) is DecisionLedgerWriteDisposition.INSERTED

    assert ledger.append_forecast(forecast) is DecisionLedgerWriteDisposition.UNCHANGED
    assert ledger.append_proof(proof) is DecisionLedgerWriteDisposition.UNCHANGED
    assert ledger.append_feed_event(event) is DecisionLedgerWriteDisposition.UNCHANGED

    status = ledger.read_status()
    assert status.forecast_count == 1
    assert status.proof_count == 1
    assert status.resolution_count == 0
    assert status.feed_event_count == 1
    assert status.latest_event_at_ms == ISSUED_AT
    assert status.read_only is True
    assert status.real_capital == 0

    stored_proof = ledger.read_proof_for_signal(forecast.signal_freeze_identity)
    assert stored_proof is not None
    assert stored_proof["proof_identity"] == proof.proof_identity
    assert stored_proof["forecast_identity"] == forecast.forecast_identity
    assert stored_proof["production_authority"] is False
    assert stored_proof["real_capital"] == 0

    feed = ledger.read_feed(limit=10)
    assert len(feed) == 1
    assert feed[0]["event_identity"] == event.event_identity
    assert feed[0]["proof_identity"] == proof.proof_identity

    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.DatabaseError, match="immutable decision evidence"):
            connection.execute(
                "UPDATE r20_forecasts SET symbol = 'ETHUSDT'"
            )


def test_query_only_reads_never_initialize_missing_decision_ledger(tmp_path) -> None:
    path = tmp_path / "missing.sqlite3"
    ledger = ImmutableDecisionEvidenceLedger(path)

    with pytest.raises(FileNotFoundError):
        ledger.read_status()
    assert not path.exists()


def test_proof_cannot_be_persisted_without_exact_forecast_parent(tmp_path) -> None:
    ledger = ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3")
    forecast = _forecast()
    proof = _proof(forecast)

    with pytest.raises(
        DecisionLedgerConflictError,
        match="unknown R20 forecast",
    ):
        ledger.append_proof(proof)
