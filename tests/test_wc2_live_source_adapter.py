from __future__ import annotations

import inspect
from dataclasses import replace
from pathlib import Path

import pytest
from test_immutable_ledger import build_bundle, candles

from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.evaluation.live_untouched_forward_operational import (
    WC2_MISSING_CONTEXT_POLICY_VERSION,
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
from crypto_signal.product.decision_proof import (
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
)
from crypto_signal.signals.models import SignalState


def _bundle():
    bundle = build_bundle(candles())
    assert bundle.signal_decision.state in {SignalState.WATCH, SignalState.ACTIVE}
    assert bundle.signal_decision.geometry is not None
    return bundle


def test_live_source_adapter_preserves_exact_bundle_and_missing_domains() -> None:
    bundle = _bundle()
    signal = bundle.signal_decision

    adapted = adapt_same_cycle_legacy_bundle(bundle, base_asset="BTC")

    assert adapted.bundle_identity == bundle.bundle_identity
    assert adapted.regime == WC2_UNMEASURED_REGIME
    assert adapted.geometry_family.family is ConfluenceFamily.GEOMETRY
    assert bundle.bundle_identity in (
        adapted.geometry_family.source_evidence_identities
    )
    assert adapted.consumed_candles_identity in (
        adapted.geometry_family.source_evidence_identities
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
    ].evidence_identities == (adapted.consumed_candles_identity,)

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
    assert issuance.confluence.regime == WC2_UNMEASURED_REGIME
    assert issuance.production_authority is False
    assert issuance.real_capital == 0

    status = ledger.read_status()
    assert status.forecast_count == 1
    assert status.proof_count == 1
    assert status.feed_event_count == 1
    assert status.resolution_count == 0


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
