from __future__ import annotations

import inspect
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from test_immutable_ledger import build_bundle, candles

from crypto_signal.confluence.agreement import analyze_confluence
from crypto_signal.confluence.models import (
    EvidenceDirection,
    EvidenceValidity,
    InvalidationTrigger,
    MethodologyEvidence,
    MethodologyKind,
    NamedPrice,
    PriceZone,
)
from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.evaluation.live_untouched_forward_operational import (
    WC2_MISSING_CONTEXT_POLICY_VERSION,
    WC2_REGIME_ENGINE_VERSION_COMPONENT,
    WC2_UNMEASURED_REGIME,
    adapt_same_cycle_legacy_bundle,
    build_missing_pit_event_context,
    issue_same_cycle_untouched_forward_forecast,
)
from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CircuitBreakerState,
)
from crypto_signal.intelligence.meta_intelligence import MetaEvidenceState
from crypto_signal.intelligence.regime import (
    REGIME_ENGINE_VERSION,
    RegimeLabel,
    build_regime_evidence_freeze,
)
from crypto_signal.ledger.bundle import build_decision_freeze_bundle
from crypto_signal.product.decision_proof import (
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
)
from crypto_signal.signals.models import SignalState
from crypto_signal.signals.semantics import build_signal_decision


def _directional_evidence(
    *,
    methodology: MethodologyKind,
    exchange,
    market_type,
    as_of_ms: int,
    evidence_id: str,
    geometry: bool,
) -> MethodologyEvidence:
    return MethodologyEvidence(
        methodology=methodology,
        exchange=exchange,
        market_type=market_type,
        symbol="BTCUSDT",
        timeframe="15m",
        as_of_ms=as_of_ms,
        methodology_version=f"{methodology.value}/wc2-test",
        evidence_id=evidence_id,
        setup_type=(
            "gartley"
            if methodology is MethodologyKind.HARMONIC
            else "directional_context"
        ),
        direction=EvidenceDirection.BULLISH,
        validity=(
            EvidenceValidity.VALID
            if methodology is MethodologyKind.HARMONIC
            else EvidenceValidity.CONTEXT
        ),
        market_available_at_ms=as_of_ms - 2,
        observed_at_ms=as_of_ms - 1,
        entry_zone=(
            PriceZone(Decimal(1000), Decimal(1002))
            if geometry
            else None
        ),
        invalidation_price=Decimal(990) if geometry else None,
        invalidation_trigger=(
            InvalidationTrigger.TOUCH_OR_CROSS if geometry else None
        ),
        targets=(
            (
                NamedPrice("target_1", Decimal(1015)),
                NamedPrice("target_2", Decimal(1025)),
            )
            if geometry
            else ()
        ),
        key_levels=(),
        metrics=(),
        ambiguity_flags=(),
        contradiction_flags=(),
        evidence_summary=("synthetic_directional_fixture",),
    )


def _bundle():
    base = build_bundle(candles())
    as_of_ms = base.signal_decision.as_of_ms
    evidence = (
        _directional_evidence(
            methodology=MethodologyKind.PRICE_ACTION,
            exchange=base.signal_decision.exchange,
            market_type=base.signal_decision.market_type,
            as_of_ms=as_of_ms,
            evidence_id="wc2-pa-directional",
            geometry=False,
        ),
        _directional_evidence(
            methodology=MethodologyKind.HARMONIC,
            exchange=base.signal_decision.exchange,
            market_type=base.signal_decision.market_type,
            as_of_ms=as_of_ms,
            evidence_id="wc2-harmonic-geometry",
            geometry=True,
        ),
    )
    confluence = analyze_confluence(
        evidence,
        exchange=base.signal_decision.exchange,
        market_type=base.signal_decision.market_type,
        symbol=base.signal_decision.symbol,
        timeframe=base.signal_decision.timeframe,
        as_of_ms=as_of_ms,
    )
    decision = build_signal_decision(confluence)
    assert decision.state is SignalState.ACTIVE
    assert decision.geometry is not None
    return build_decision_freeze_bundle(
        decision=decision,
        confluence=confluence,
        price_action=evidence[0],
        harmonic=evidence[1],
        elliott=base.elliott,
        candles=base.candles,
    )


def test_live_source_adapter_preserves_exact_bundle_and_missing_domains() -> None:
    bundle = _bundle()
    signal = bundle.signal_decision

    adapted = adapt_same_cycle_legacy_bundle(bundle, base_asset="BTC")

    assert adapted.bundle_identity == bundle.bundle_identity
    regime_freeze = build_regime_evidence_freeze(
        bundle.candles,
        as_of_ms=signal.as_of_ms,
    )
    assert adapted.regime == regime_freeze.analysis.label.value
    assert adapted.regime != WC2_UNMEASURED_REGIME
    assert adapted.regime in {
        label.value
        for label in RegimeLabel
        if label is not RegimeLabel.UNRESOLVED
    }
    assert adapted.geometry_family.family is ConfluenceFamily.GEOMETRY
    assert bundle.bundle_identity in (
        adapted.geometry_family.source_evidence_identities
    )
    assert adapted.consumed_candles_identity in (
        adapted.geometry_family.source_evidence_identities
    )
    assert regime_freeze.freeze_identity in (
        adapted.geometry_family.source_evidence_identities
    )
    assert f"regime:{REGIME_ENGINE_VERSION}" in (
        adapted.geometry_family.source_engine_ids
    )
    assert adapted.geometry_family.as_of_ms == signal.as_of_ms
    assert adapted.geometry_family.asset == signal.symbol
    assert adapted.geometry_family.timeframe == signal.timeframe

    if signal.agreement.opposing_method_count:
        assert adapted.geometry_family.state is MetaEvidenceState.ABSTAIN
        assert adapted.geometry_family.direction is None
        assert (
            "legacy_methodology_opposition_forces_geometry_abstain"
            in adapted.geometry_family.uncertainty_flags
        )
    else:
        assert adapted.geometry_family.state is MetaEvidenceState.OBSERVED
        assert adapted.geometry_family.direction is not None

    geometry_proof = {
        item.domain: item for item in adapted.geometry_proof_slices
    }
    assert geometry_proof[
        ProofEvidenceDomain.FROZEN_CHART
    ].evidence_identities == (bundle.bundle_identity,)
    assert geometry_proof[
        ProofEvidenceDomain.CONSUMED_CANDLES
    ].evidence_identities == tuple(
        sorted(
            (
                adapted.consumed_candles_identity,
                regime_freeze.freeze_identity,
            )
        )
    )
    assert (
        "pit_regime_freeze_derived_from_consumed_candles"
        in geometry_proof[
            ProofEvidenceDomain.CONSUMED_CANDLES
        ].summary_codes
    )

    assert all(
        item.state is MetaEvidenceState.NO_EVIDENCE
        for item in adapted.accepted_m2_m5.families
    )
    assert all(
        item.availability is ProofEvidenceAvailability.INSUFFICIENT
        for item in adapted.accepted_m2_m5.proof_slices
    )
    assert adapted.production_authority is False
    assert adapted.real_capital == 0


def test_missing_event_context_is_degraded_without_numeric_threshold_claim() -> None:
    bundle = _bundle()
    signal = bundle.signal_decision

    event = build_missing_pit_event_context(
        asset="BTC",
        as_of_ms=signal.as_of_ms,
    )

    assert event.state is CircuitBreakerState.DEGRADED_DATA
    assert event.policy_version == WC2_MISSING_CONTEXT_POLICY_VERSION
    assert event.market_quality_identity is None
    assert event.triggers == tuple(
        sorted(
            (
                "event_risk_degraded_data",
                "market_quality_unavailable",
                "news_evidence_unresolved",
            )
        )
    )
    assert "no_quantitative_market_quality_threshold_asserted" in (
        event.uncertainty_flags
    )
    assert event.real_capital == 0


def test_same_cycle_issuance_is_not_calibrated_and_uses_first_frozen_target(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    signal = bundle.signal_decision
    frozen_at = signal.as_of_ms + 10
    issued_at = frozen_at + 20
    ledger = ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3")

    issuance = issue_same_cycle_untouched_forward_forecast(
        bundle,
        frozen_at_ms=frozen_at,
        issued_at_ms=issued_at,
        maximum_issuance_delay_ms=100,
        horizon_bars=4,
        base_asset="BTC",
        ledger=ledger,
    )

    assert issuance.forecast.issued_at_ms == issued_at
    assert issuance.forecast.target_label == signal.geometry.targets[0].label
    assert issuance.forecast.probability_status == "not_calibrated"
    assert issuance.forecast.calibrated_probability_0_1 is None
    assert issuance.forecast.event_context_state is (
        CircuitBreakerState.DEGRADED_DATA
    )
    expected_regime = build_regime_evidence_freeze(
        bundle.candles,
        as_of_ms=signal.as_of_ms,
    )
    assert issuance.confluence.regime == expected_regime.analysis.label.value
    assert issuance.confluence.regime != WC2_UNMEASURED_REGIME
    assert expected_regime.freeze_identity in (
        issuance.forecast.source_evidence_identities
    )
    refs = {
        item.component: item.version
        for item in issuance.forecast.version_refs
    }
    assert refs[WC2_REGIME_ENGINE_VERSION_COMPONENT] == REGIME_ENGINE_VERSION
    assert issuance.production_authority is False
    assert issuance.real_capital == 0

    status = ledger.read_status()
    assert status.forecast_count == 1
    assert status.proof_count == 1
    assert status.feed_event_count == 1
    assert status.resolution_count == 0


def test_same_cycle_issuance_binds_exact_collection_protocol_lineage(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    signal = bundle.signal_decision
    frozen_at = signal.as_of_ms + 10
    issued_at = frozen_at + 20
    protocol_identity = "f" * 64

    issuance = issue_same_cycle_untouched_forward_forecast(
        bundle,
        frozen_at_ms=frozen_at,
        issued_at_ms=issued_at,
        maximum_issuance_delay_ms=100,
        horizon_bars=4,
        base_asset="BTC",
        ledger=ImmutableDecisionEvidenceLedger(
            tmp_path / "protocol-lineage.sqlite3"
        ),
        collection_protocol_identity=protocol_identity,
    )

    assert protocol_identity in (
        issuance.forecast.source_evidence_identities
    )
    refs = {
        item.component: item.version
        for item in issuance.forecast.version_refs
    }
    assert refs["wc2_collection_protocol"] == protocol_identity
    assert refs[WC2_REGIME_ENGINE_VERSION_COMPONENT] == REGIME_ENGINE_VERSION
    regime_freeze = build_regime_evidence_freeze(
        bundle.candles,
        as_of_ms=signal.as_of_ms,
    )
    assert regime_freeze.freeze_identity in (
        issuance.forecast.source_evidence_identities
    )
    methodology = next(
        item
        for item in issuance.proof.evidence_slices
        if item.domain is ProofEvidenceDomain.METHODOLOGY
    )
    assert protocol_identity in methodology.evidence_identities
    assert "extra_forecast_source_lineage_bound" in methodology.summary_codes


def test_same_cycle_issuance_rejects_backdating_and_stale_delay(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    signal = bundle.signal_decision
    frozen_at = signal.as_of_ms + 100

    with pytest.raises(ValueError, match="backdated"):
        issue_same_cycle_untouched_forward_forecast(
            bundle,
            frozen_at_ms=frozen_at,
            issued_at_ms=frozen_at - 1,
            maximum_issuance_delay_ms=100,
            horizon_bars=4,
            base_asset="BTC",
            ledger=ImmutableDecisionEvidenceLedger(
                tmp_path / "backdated.sqlite3"
            ),
        )

    with pytest.raises(ValueError, match="exceeded preregistered"):
        issue_same_cycle_untouched_forward_forecast(
            bundle,
            frozen_at_ms=frozen_at,
            issued_at_ms=frozen_at + 101,
            maximum_issuance_delay_ms=100,
            horizon_bars=4,
            base_asset="BTC",
            ledger=ImmutableDecisionEvidenceLedger(
                tmp_path / "stale.sqlite3"
            ),
        )

    assert not (tmp_path / "backdated.sqlite3").exists()
    assert not (tmp_path / "stale.sqlite3").exists()


def test_operational_issuance_has_no_hidden_policy_defaults() -> None:
    signature = inspect.signature(issue_same_cycle_untouched_forward_forecast)

    assert signature.parameters["maximum_issuance_delay_ms"].default is (
        inspect.Parameter.empty
    )
    assert signature.parameters["horizon_bars"].default is (
        inspect.Parameter.empty
    )
    assert signature.parameters["base_asset"].default is inspect.Parameter.empty
    assert "calibrated_probability" not in signature.parameters
    assert "outcome" not in signature.parameters


def test_tampered_bundle_is_rejected_before_decision_ledger_creation(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    tampered = replace(bundle, bundle_identity="0" * 64)
    decision_path = tmp_path / "decision.sqlite3"

    with pytest.raises(ValueError, match="bundle identity mismatch"):
        issue_same_cycle_untouched_forward_forecast(
            tampered,
            frozen_at_ms=bundle.signal_decision.as_of_ms + 1,
            issued_at_ms=bundle.signal_decision.as_of_ms + 2,
            maximum_issuance_delay_ms=100,
            horizon_bars=4,
            base_asset="BTC",
            ledger=ImmutableDecisionEvidenceLedger(decision_path),
        )

    assert not decision_path.exists()
