from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from test_family_proof_adapters import _micro, _temporal
from test_immutable_forecast_stream import (
    HORIZON,
    _calibrated_probability,
    _event_context,
    _probability_scope,
    _signal,
)

from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.exact_decision_composition import compose_exact_decision
from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamily,
    ConfluenceMatrixResolution,
    build_confluence_family_evidence,
)
from crypto_signal.intelligence.family_proof_adapters import adapt_accepted_m2_m5
from crypto_signal.intelligence.meta_intelligence import (
    MetaDirection,
    MetaEvidenceState,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.decision_proof import (
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
    ProofEvidenceVerdict,
    build_decision_proof_evidence_slice,
)
from crypto_signal.product.web import create_app


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _geometry():
    chart_id = _sha("exact-frozen-chart")
    candles_id = _sha("exact-consumed-candles")
    family = build_confluence_family_evidence(
        family=ConfluenceFamily.GEOMETRY,
        asset="BTCUSDT",
        timeframe="4h",
        regime="trend_up",
        as_of_ms=AS_OF,
        state=MetaEvidenceState.OBSERVED,
        direction=MetaDirection.BULLISH,
        directional_strength_0_1=Decimal("0.80"),
        evidence_quality_0_1=Decimal("0.90"),
        freshness_0_1=Decimal("0.95"),
        market_available_at_ms=AS_OF - 20,
        observed_at_ms=AS_OF - 10,
        source_engine_ids=("accepted-geometry-freeze",),
        source_evidence_identities=(chart_id, candles_id),
        uncertainty_flags=("geometry_is_evidence_not_probability",),
    )
    chart = build_decision_proof_evidence_slice(
        domain=ProofEvidenceDomain.FROZEN_CHART,
        availability=ProofEvidenceAvailability.AVAILABLE,
        verdict=ProofEvidenceVerdict.SUPPORT,
        evidence_identities=(chart_id,),
        market_available_at_ms=AS_OF - 20,
        observed_at_ms=AS_OF - 10,
        freshness_0_1=Decimal("0.95"),
        source_quality="accepted_frozen_chart",
        summary_codes=("exact_issuance_chart",),
    )
    candles = build_decision_proof_evidence_slice(
        domain=ProofEvidenceDomain.CONSUMED_CANDLES,
        availability=ProofEvidenceAvailability.AVAILABLE,
        verdict=ProofEvidenceVerdict.SUPPORT,
        evidence_identities=(candles_id,),
        market_available_at_ms=AS_OF - 20,
        observed_at_ms=AS_OF - 10,
        freshness_0_1=Decimal("0.95"),
        source_quality="accepted_consumed_candles",
        summary_codes=("exact_consumed_candle_bundle",),
    )
    return family, (chart, candles), chart_id, candles_id


def _accepted_m3_only():
    micro = _micro()
    temporal = _temporal()
    bundle = adapt_accepted_m2_m5(
        symbol="BTCUSDT",
        base_asset="BTC",
        timeframe="4h",
        regime="trend_up",
        as_of_ms=AS_OF,
        microstructure=micro,
        temporal_flow=temporal,
    )
    return bundle, micro, temporal


def test_exact_composition_replays_source_ids_to_ledger_and_product_api(
    tmp_path,
) -> None:
    signal = _signal(as_of_ms=AS_OF)
    geometry, geometry_proofs, chart_id, candles_id = _geometry()
    bundle, micro, temporal = _accepted_m3_only()
    event = _event_context(as_of_ms=AS_OF)
    decision_path = tmp_path / "decision.sqlite3"
    ledger = ImmutableDecisionEvidenceLedger(decision_path)

    result = compose_exact_decision(
        signal=signal,
        base_asset="BTC",
        regime="trend_up",
        geometry_family=geometry,
        geometry_proof_slices=geometry_proofs,
        accepted_m2_m5=bundle,
        event_context=event,
        issued_at_ms=ISSUED_AT,
        horizon_bars=HORIZON,
        target_label="target_1",
        ledger=ledger,
    )

    assert result.confluence.resolution is ConfluenceMatrixResolution.PARTIAL
    assert result.forecast.probability_status == "not_calibrated"
    assert result.production_authority is False
    assert result.real_capital == 0

    proof_by_domain = {
        item.domain: item
        for item in result.proof.evidence_slices
    }
    assert proof_by_domain[
        ProofEvidenceDomain.FROZEN_CHART
    ].evidence_identities == (chart_id,)
    assert proof_by_domain[
        ProofEvidenceDomain.CONSUMED_CANDLES
    ].evidence_identities == (candles_id,)
    assert micro.freeze_identity in proof_by_domain[
        ProofEvidenceDomain.ORDER_BOOK
    ].evidence_identities
    assert temporal.freeze_identity in proof_by_domain[
        ProofEvidenceDomain.ORDER_FLOW_CVD
    ].evidence_identities
    assert proof_by_domain[
        ProofEvidenceDomain.DERIVATIVES
    ].availability is ProofEvidenceAvailability.INSUFFICIENT
    assert proof_by_domain[
        ProofEvidenceDomain.ONCHAIN
    ].availability is ProofEvidenceAvailability.INSUFFICIENT
    assert proof_by_domain[
        ProofEvidenceDomain.PROBABILITY_CALIBRATION
    ].availability is ProofEvidenceAvailability.INSUFFICIENT

    event_ids = set(
        proof_by_domain[
            ProofEvidenceDomain.EVENT_CONTEXT
        ].evidence_identities
    )
    assert event.evidence_identity in event_ids
    assert event.event_risk_identity in event_ids
    assert event.news_evidence_identity in event_ids

    status = ledger.read_status()
    assert status.forecast_count == 1
    assert status.proof_count == 1
    assert status.feed_event_count == 1

    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            decision_evidence_path=decision_path,
        )
    )
    body = client.get(
        f"/api/decision-proof/{signal.freeze_identity}"
    ).json()
    assert body["status"] == "ready"
    assert body["proof"]["proof_identity"] == result.proof.proof_identity
    api_domains = {
        item["domain"]: item
        for item in body["proof"]["evidence_slices"]
    }
    assert chart_id in api_domains["frozen_chart"]["evidence_identities"]
    assert micro.freeze_identity in api_domains["order_book"]["evidence_identities"]
    assert temporal.freeze_identity in api_domains[
        "order_flow_cvd"
    ]["evidence_identities"]
    assert body["read_only"] is True
    assert body["real_capital"] == 0


def test_exact_composition_rejects_geometry_source_not_present_in_proof(
    tmp_path,
) -> None:
    signal = _signal(as_of_ms=AS_OF)
    geometry, geometry_proofs, _, _ = _geometry()
    bundle, _, _ = _accepted_m3_only()
    wrong_chart = build_decision_proof_evidence_slice(
        domain=ProofEvidenceDomain.FROZEN_CHART,
        availability=ProofEvidenceAvailability.AVAILABLE,
        verdict=ProofEvidenceVerdict.SUPPORT,
        evidence_identities=(_sha("wrong-chart"),),
        market_available_at_ms=AS_OF - 20,
        observed_at_ms=AS_OF - 10,
        freshness_0_1=Decimal("0.95"),
        source_quality="accepted_frozen_chart",
        summary_codes=("wrong_source_for_test",),
    )

    with pytest.raises(ValueError, match="exact M6 family source evidence"):
        compose_exact_decision(
            signal=signal,
            base_asset="BTC",
            regime="trend_up",
            geometry_family=geometry,
            geometry_proof_slices=(wrong_chart, geometry_proofs[1]),
            accepted_m2_m5=bundle,
            event_context=_event_context(as_of_ms=AS_OF),
            issued_at_ms=ISSUED_AT,
            horizon_bars=HORIZON,
            target_label="target_1",
            ledger=ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3"),
        )


def test_exact_composition_rejects_missing_geometry_domain(tmp_path) -> None:
    geometry, geometry_proofs, _, _ = _geometry()
    bundle, _, _ = _accepted_m3_only()

    with pytest.raises(ValueError, match="FROZEN_CHART and CONSUMED_CANDLES"):
        compose_exact_decision(
            signal=_signal(as_of_ms=AS_OF),
            base_asset="BTC",
            regime="trend_up",
            geometry_family=geometry,
            geometry_proof_slices=(geometry_proofs[0],),
            accepted_m2_m5=bundle,
            event_context=_event_context(as_of_ms=AS_OF),
            issued_at_ms=ISSUED_AT,
            horizon_bars=HORIZON,
            target_label="target_1",
            ledger=ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3"),
        )


def test_exact_composition_accepts_only_exact_r19_scope(tmp_path) -> None:
    geometry, geometry_proofs, _, _ = _geometry()
    bundle, _, _ = _accepted_m3_only()
    probability = _calibrated_probability(issued_at_ms=AS_OF)
    scope = _probability_scope()

    result = compose_exact_decision(
        signal=_signal(as_of_ms=AS_OF),
        base_asset="BTC",
        regime="trend_up",
        geometry_family=geometry,
        geometry_proof_slices=geometry_proofs,
        accepted_m2_m5=bundle,
        event_context=_event_context(as_of_ms=AS_OF),
        issued_at_ms=ISSUED_AT,
        horizon_bars=HORIZON,
        target_label="target_1",
        ledger=ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3"),
        calibrated_probability=probability,
        calibration_scope=scope,
    )
    assert result.forecast.probability_status == "calibrated"
    probability_slice = next(
        item for item in result.proof.evidence_slices
        if item.domain is ProofEvidenceDomain.PROBABILITY_CALIBRATION
    )
    assert probability.authorization_identity in probability_slice.evidence_identities
    assert probability.calibration_evidence_identity in (
        probability_slice.evidence_identities
    )


def test_exact_composition_never_creates_probability_from_scope_alone(
    tmp_path,
) -> None:
    geometry, geometry_proofs, _, _ = _geometry()
    bundle, _, _ = _accepted_m3_only()

    with pytest.raises(
        ValueError,
        match="scope cannot be supplied without calibrated probability",
    ):
        compose_exact_decision(
            signal=_signal(as_of_ms=AS_OF),
            base_asset="BTC",
            regime="trend_up",
            geometry_family=geometry,
            geometry_proof_slices=geometry_proofs,
            accepted_m2_m5=bundle,
            event_context=_event_context(as_of_ms=AS_OF),
            issued_at_ms=ISSUED_AT,
            horizon_bars=HORIZON,
            target_label="target_1",
            ledger=ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3"),
            calibration_scope=_probability_scope(),
        )
