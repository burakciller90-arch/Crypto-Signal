from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest
from test_immutable_forecast_stream import (
    AS_OF,
    HORIZON,
    ISSUED_AT,
    _calibrated_probability,
    _event_context,
    _probability_scope,
    _signal,
)

from crypto_signal.decision_ledger import (
    DecisionLedgerWriteDisposition,
    ImmutableDecisionEvidenceLedger,
)
from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamily,
    ConfluenceMatrixResolution,
    build_confluence_family_evidence,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import CircuitBreakerState
from crypto_signal.intelligence.evidence_overlap import (
    analyze_confluence_evidence_overlap,
)
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
from crypto_signal.unified_decision_runtime import issue_unified_decision


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _family_evidence(
    *,
    direction: MetaDirection = MetaDirection.BULLISH,
):
    return tuple(
        build_confluence_family_evidence(
            family=family,
            asset="BTCUSDT",
            timeframe="4h",
            regime="trend_up",
            as_of_ms=AS_OF,
            state=MetaEvidenceState.OBSERVED,
            direction=direction,
            directional_strength_0_1=Decimal("0.80"),
            evidence_quality_0_1=Decimal("0.90"),
            freshness_0_1=Decimal("0.95"),
            market_available_at_ms=AS_OF - 20,
            observed_at_ms=AS_OF - 10,
            source_engine_ids=(f"{family.value}-engine",),
            source_evidence_identities=(_sha(f"{family.value}-source"),),
            uncertainty_flags=(),
        )
        for family in sorted(ConfluenceFamily, key=lambda item: item.value)
    )


def _available(
    domain: ProofEvidenceDomain,
    *identities: str,
    verdict: ProofEvidenceVerdict = ProofEvidenceVerdict.NEUTRAL,
    observed_at_ms: int = AS_OF,
):
    return build_decision_proof_evidence_slice(
        domain=domain,
        availability=ProofEvidenceAvailability.AVAILABLE,
        verdict=verdict,
        evidence_identities=tuple(identities),
        market_available_at_ms=observed_at_ms - 1,
        observed_at_ms=observed_at_ms,
        freshness_0_1=Decimal("0.95"),
        source_quality="accepted_runtime_evidence",
        summary_codes=(f"{domain.value}_accepted",),
    )


def _missing(domain: ProofEvidenceDomain):
    return build_decision_proof_evidence_slice(
        domain=domain,
        availability=ProofEvidenceAvailability.INSUFFICIENT,
        verdict=ProofEvidenceVerdict.INSUFFICIENT,
        summary_codes=(f"{domain.value}_insufficient",),
    )


def _preflight(
    family_evidence,
    event_context,
    *,
    calibrated_probability=None,
):
    source_by_family = {
        item.family: item.source_evidence_identities[0]
        for item in family_evidence
    }
    if calibrated_probability is None:
        probability = _missing(ProofEvidenceDomain.PROBABILITY_CALIBRATION)
    else:
        probability = _available(
            ProofEvidenceDomain.PROBABILITY_CALIBRATION,
            calibrated_probability.authorization_identity,
            calibrated_probability.calibration_evidence_identity,
            calibrated_probability.source_forecast_identity,
            calibrated_probability.source_prediction_identity,
            calibrated_probability.walk_forward_fit_identity,
            verdict=ProofEvidenceVerdict.SUPPORT,
        )
    rows = {
        ProofEvidenceDomain.FROZEN_CHART: _available(
            ProofEvidenceDomain.FROZEN_CHART,
            source_by_family[ConfluenceFamily.GEOMETRY],
            verdict=ProofEvidenceVerdict.SUPPORT,
        ),
        ProofEvidenceDomain.CONSUMED_CANDLES: _missing(
            ProofEvidenceDomain.CONSUMED_CANDLES
        ),
        ProofEvidenceDomain.ORDER_BOOK: _missing(
            ProofEvidenceDomain.ORDER_BOOK
        ),
        ProofEvidenceDomain.LIQUIDITY_MAP: _available(
            ProofEvidenceDomain.LIQUIDITY_MAP,
            source_by_family[ConfluenceFamily.LIQUIDITY],
            verdict=ProofEvidenceVerdict.SUPPORT,
        ),
        ProofEvidenceDomain.LIQUIDATION_MAP: _missing(
            ProofEvidenceDomain.LIQUIDATION_MAP
        ),
        ProofEvidenceDomain.ORDER_FLOW_CVD: _available(
            ProofEvidenceDomain.ORDER_FLOW_CVD,
            source_by_family[ConfluenceFamily.ORDER_FLOW],
            verdict=ProofEvidenceVerdict.SUPPORT,
        ),
        ProofEvidenceDomain.DERIVATIVES: _available(
            ProofEvidenceDomain.DERIVATIVES,
            source_by_family[ConfluenceFamily.DERIVATIVES],
            verdict=ProofEvidenceVerdict.SUPPORT,
        ),
        ProofEvidenceDomain.ONCHAIN: _available(
            ProofEvidenceDomain.ONCHAIN,
            source_by_family[ConfluenceFamily.ONCHAIN],
            verdict=ProofEvidenceVerdict.SUPPORT,
        ),
        ProofEvidenceDomain.EVENT_CONTEXT: _available(
            ProofEvidenceDomain.EVENT_CONTEXT,
            event_context.evidence_identity,
        ),
        ProofEvidenceDomain.PROBABILITY_CALIBRATION: probability,
    }
    return tuple(
        rows[domain]
        for domain in ProofEvidenceDomain
        if domain is not ProofEvidenceDomain.METHODOLOGY
    )


def _issue(tmp_path, *, event_state=CircuitBreakerState.CLEAR, calibrated=False):
    signal = _signal()
    family = _family_evidence()
    event = _event_context(state=event_state)
    probability = _calibrated_probability() if calibrated else None
    scope = _probability_scope() if calibrated else None
    ledger = ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3")
    result = issue_unified_decision(
        signal=signal,
        base_asset="BTC",
        regime="trend_up",
        family_evidence=family,
        event_context=event,
        preflight_proof_slices=_preflight(
            family,
            event,
            calibrated_probability=probability,
        ),
        issued_at_ms=ISSUED_AT,
        horizon_bars=HORIZON,
        target_label="target_1",
        ledger=ledger,
        calibrated_probability=probability,
        calibration_scope=scope,
    )
    return ledger, result


def test_unified_runtime_builds_m6_forecast_proof_feed_and_persists_atomically(
    tmp_path,
) -> None:
    ledger, result = _issue(tmp_path)

    assert result.confluence.resolution is ConfluenceMatrixResolution.MEASURED
    assert result.confluence.support_score_0_100 == Decimal("80.00")
    assert result.confluence.opposition_score_0_100 == Decimal("0.00")
    assert result.forecast.confluence_identity == result.confluence.snapshot_identity
    assert result.forecast.probability_status == "not_calibrated"
    assert result.proof.forecast_identity == result.forecast.forecast_identity
    assert result.feed_event.proof_identity == result.proof.proof_identity
    assert result.ledger_disposition is DecisionLedgerWriteDisposition.INSERTED
    assert result.production_authority is False
    assert result.real_capital == 0

    methodology = next(
        item
        for item in result.proof.evidence_slices
        if item.domain is ProofEvidenceDomain.METHODOLOGY
    )
    assert methodology.verdict is ProofEvidenceVerdict.SUPPORT
    assert result.forecast.signal_freeze_identity in methodology.evidence_identities
    assert result.confluence.snapshot_identity in methodology.evidence_identities

    status = ledger.read_status()
    assert status.forecast_count == 1
    assert status.proof_count == 1
    assert status.feed_event_count == 1
    assert status.resolution_count == 0


def test_unified_runtime_is_idempotent_for_exact_same_issuance(tmp_path) -> None:
    ledger, first = _issue(tmp_path)

    signal = _signal()
    family = _family_evidence()
    event = _event_context()
    second = issue_unified_decision(
        signal=signal,
        base_asset="BTC",
        regime="trend_up",
        family_evidence=family,
        event_context=event,
        preflight_proof_slices=_preflight(family, event),
        issued_at_ms=ISSUED_AT,
        horizon_bars=HORIZON,
        target_label="target_1",
        ledger=ledger,
    )

    assert second.forecast == first.forecast
    assert second.proof == first.proof
    assert second.feed_event == first.feed_event
    assert second.ledger_disposition is DecisionLedgerWriteDisposition.UNCHANGED


def test_unified_runtime_rejects_proof_not_bound_to_exact_m6_family_sources(
    tmp_path,
) -> None:
    signal = _signal()
    family = _family_evidence()
    event = _event_context()
    slices = list(_preflight(family, event))
    index = next(
        i
        for i, item in enumerate(slices)
        if item.domain is ProofEvidenceDomain.LIQUIDITY_MAP
    )
    slices[index] = _available(
        ProofEvidenceDomain.LIQUIDITY_MAP,
        _sha("unrelated-liquidity-evidence"),
    )

    with pytest.raises(ValueError, match="exact M6 family source evidence"):
        issue_unified_decision(
            signal=signal,
            base_asset="BTC",
            regime="trend_up",
            family_evidence=family,
            event_context=event,
            preflight_proof_slices=tuple(slices),
            issued_at_ms=ISSUED_AT,
            horizon_bars=HORIZON,
            target_label="target_1",
            ledger=ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3"),
        )


def test_unified_runtime_rejects_future_preflight_evidence(tmp_path) -> None:
    signal = _signal()
    family = _family_evidence()
    event = _event_context()
    slices = list(_preflight(family, event))
    index = next(
        i
        for i, item in enumerate(slices)
        if item.domain is ProofEvidenceDomain.ONCHAIN
    )
    onchain_id = family[-1].source_evidence_identities[0]
    slices[index] = _available(
        ProofEvidenceDomain.ONCHAIN,
        onchain_id,
        observed_at_ms=AS_OF + 1,
    )

    with pytest.raises(ValueError, match="future evidence"):
        issue_unified_decision(
            signal=signal,
            base_asset="BTC",
            regime="trend_up",
            family_evidence=family,
            event_context=event,
            preflight_proof_slices=tuple(slices),
            issued_at_ms=ISSUED_AT,
            horizon_bars=HORIZON,
            target_label="target_1",
            ledger=ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3"),
        )


def test_unified_runtime_preserves_event_block_without_granting_capital_authority(
    tmp_path,
) -> None:
    _, result = _issue(tmp_path, event_state=CircuitBreakerState.EVENT_BLOCK)

    assert result.forecast.event_context_state is CircuitBreakerState.EVENT_BLOCK
    assert "event_context_event_block" in result.forecast.uncertainty_flags
    assert result.proof.production_authority is False
    assert result.feed_event.production_authority is False
    assert result.real_capital == 0


def test_unified_runtime_accepts_only_exact_pre_asof_r19_probability_lineage(
    tmp_path,
) -> None:
    _, result = _issue(tmp_path, calibrated=True)

    assert result.forecast.probability_status == "calibrated"
    assert result.forecast.calibrated_probability_0_1 == Decimal("0.67")
    probability_slice = next(
        item
        for item in result.proof.evidence_slices
        if item.domain is ProofEvidenceDomain.PROBABILITY_CALIBRATION
    )
    assert probability_slice.availability is ProofEvidenceAvailability.AVAILABLE
    assert result.forecast.probability_authorization_identity in (
        probability_slice.evidence_identities
    )


def test_atomic_issuance_bundle_rolls_back_all_rows_on_final_insert_failure(
    tmp_path,
) -> None:
    signal = _signal()
    family = _family_evidence()
    event = _event_context()
    scratch = ImmutableDecisionEvidenceLedger(tmp_path / "scratch.sqlite3")
    result = issue_unified_decision(
        signal=signal,
        base_asset="BTC",
        regime="trend_up",
        family_evidence=family,
        event_context=event,
        preflight_proof_slices=_preflight(family, event),
        issued_at_ms=ISSUED_AT,
        horizon_bars=HORIZON,
        target_label="target_1",
        ledger=scratch,
    )

    path = tmp_path / "atomic.sqlite3"
    ledger = ImmutableDecisionEvidenceLedger(path)
    ledger.initialize()
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_issuance_event
            BEFORE INSERT ON r20_5_live_feed_events
            BEGIN
                SELECT RAISE(ABORT, 'forced issuance failure');
            END
            """
        )

    with pytest.raises(sqlite3.DatabaseError, match="forced issuance failure"):
        ledger.append_issuance_bundle(
            result.forecast,
            result.proof,
            result.feed_event,
        )

    status = ledger.read_status()
    assert status.forecast_count == 0
    assert status.proof_count == 0
    assert status.feed_event_count == 0


def test_unified_runtime_fails_closed_on_market_context_mismatch(tmp_path) -> None:
    family = list(_family_evidence())
    original = family[-1]
    family[-1] = build_confluence_family_evidence(
        family=original.family,
        asset=original.asset,
        timeframe=original.timeframe,
        regime=original.regime,
        as_of_ms=AS_OF - 1,
        state=original.state,
        direction=original.direction,
        directional_strength_0_1=original.directional_strength_0_1,
        evidence_quality_0_1=original.evidence_quality_0_1,
        freshness_0_1=original.freshness_0_1,
        market_available_at_ms=AS_OF - 21,
        observed_at_ms=AS_OF - 11,
        source_engine_ids=original.source_engine_ids,
        source_evidence_identities=original.source_evidence_identities,
        material_conflict_identities=original.material_conflict_identities,
        uncertainty_flags=original.uncertainty_flags,
    )

    with pytest.raises(ValueError, match="family evidence context mismatch"):
        issue_unified_decision(
            signal=_signal(),
            base_asset="BTC",
            regime="trend_up",
            family_evidence=tuple(family),
            event_context=_event_context(),
            preflight_proof_slices=_preflight(_family_evidence(), _event_context()),
            issued_at_ms=ISSUED_AT,
            horizon_bars=HORIZON,
            target_label="target_1",
            ledger=ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3"),
        )


def test_unified_runtime_freezes_exact_overlap_lineage_and_adjusted_score(
    tmp_path,
) -> None:
    signal = _signal()
    original = list(_family_evidence())
    shared = _sha("rdp9-shared-family-source")

    for index, item in enumerate(original):
        if item.family not in {
            ConfluenceFamily.LIQUIDITY,
            ConfluenceFamily.ORDER_FLOW,
        }:
            continue
        original[index] = build_confluence_family_evidence(
            family=item.family,
            asset=item.asset,
            timeframe=item.timeframe,
            regime=item.regime,
            as_of_ms=item.as_of_ms,
            state=item.state,
            direction=item.direction,
            directional_strength_0_1=item.directional_strength_0_1,
            evidence_quality_0_1=item.evidence_quality_0_1,
            freshness_0_1=item.freshness_0_1,
            market_available_at_ms=item.market_available_at_ms,
            observed_at_ms=item.observed_at_ms,
            source_engine_ids=item.source_engine_ids,
            source_evidence_identities=(shared,),
            material_conflict_identities=item.material_conflict_identities,
            uncertainty_flags=item.uncertainty_flags,
        )

    family = tuple(original)
    event = _event_context()
    overlap = analyze_confluence_evidence_overlap(family)
    result = issue_unified_decision(
        signal=signal,
        base_asset="BTC",
        regime="trend_up",
        family_evidence=family,
        event_context=event,
        preflight_proof_slices=_preflight(family, event),
        issued_at_ms=ISSUED_AT,
        horizon_bars=HORIZON,
        target_label="target_1",
        ledger=ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3"),
    )

    assert overlap.has_overlap
    assert result.confluence.support_score_0_100 == Decimal("60.00")
    assert set(overlap.lineage_identities).issubset(
        set(result.forecast.source_evidence_identities)
    )
    methodology = next(
        item
        for item in result.proof.evidence_slices
        if item.domain is ProofEvidenceDomain.METHODOLOGY
    )
    assert set(overlap.lineage_identities).issubset(
        set(methodology.evidence_identities)
    )
    assert result.production_authority is False
    assert result.real_capital == 0
