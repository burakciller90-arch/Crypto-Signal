from __future__ import annotations

import inspect
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from test_harmonic_analysis import candle as harmonic_candle
from test_harmonic_analysis import series as harmonic_series

from crypto_signal.confluence.adapters import (
    harmonic_result_evidence,
    price_action_structure_evidence,
)
from crypto_signal.confluence.agreement import analyze_confluence
from crypto_signal.confluence.models import EvidenceDirection
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
from crypto_signal.methodologies.elliott.analysis import analyze_elliott
from crypto_signal.methodologies.harmonic.analysis import analyze_harmonics
from crypto_signal.methodologies.price_action.analysis import analyze_price_action
from crypto_signal.methodologies.price_action.models import (
    StructureBreak,
    StructureBreakKind,
    StructureDirection,
)
from crypto_signal.product.decision_proof import (
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
)
from crypto_signal.signals.models import SignalState
from crypto_signal.signals.semantics import build_signal_decision


def _bundle():
    offset_ms = 7 * 86_400_000
    source = tuple(
        replace(
            candle,
            open_time_ms=candle.open_time_ms + offset_ms,
            close_time_ms=candle.close_time_ms + offset_ms,
            source_timestamp_ms=candle.source_timestamp_ms + offset_ms,
            ingested_at_ms=candle.ingested_at_ms + offset_ms,
        )
        for candle in (
            *harmonic_series(),
            harmonic_candle(16, 1050),
            harmonic_candle(17, 1090),
        )
    )
    as_of_ms = max(candle.ingested_at_ms for candle in source)

    harmonic = analyze_harmonics(
        source,
        left_bars=1,
        right_bars=1,
        as_of_ms=as_of_ms,
    )
    harmonic_items = harmonic_result_evidence(harmonic)
    selected_pair = next(
        (
            (match, item)
            for match, item in zip(
                harmonic.valid_matches,
                harmonic_items,
                strict=True,
            )
            if item.direction is EvidenceDirection.BULLISH
            and item.entry_zone is not None
            and item.invalidation_price is not None
            and item.targets
        ),
        None,
    )
    assert selected_pair is not None
    harmonic_match, harmonic_item = selected_pair

    price_action = analyze_price_action(
        source,
        left_bars=1,
        right_bars=1,
        as_of_ms=as_of_ms,
    )
    price_action_item = price_action_structure_evidence(price_action)
    if (
        price_action_item is None
        or price_action_item.direction is not EvidenceDirection.BULLISH
    ):
        last = source[-1]
        broken_pivot = harmonic_match.candidate.c
        break_event = StructureBreak(
            kind=StructureBreakKind.BOS,
            direction=StructureDirection.BULLISH,
            broken_pivot=broken_pivot,
            break_candle_identity=(
                last.exchange.value,
                last.market_type.value,
                last.symbol,
                last.timeframe,
                last.open_time_ms,
            ),
            break_close=last.close,
            level_price=broken_pivot.price,
            distance_bps=(
                (last.close - broken_pivot.price)
                / broken_pivot.price
                * Decimal(10_000)
            ),
            market_confirmed_at_ms=last.close_time_ms,
            observed_at_ms=last.ingested_at_ms,
        )
        structure = replace(
            price_action.structure,
            structure_breaks=(
                *price_action.structure.structure_breaks,
                break_event,
            ),
            current_direction=StructureDirection.BULLISH,
        )
        price_action = replace(
            price_action,
            structure=structure,
            summary=replace(
                price_action.summary,
                current_structure_direction=StructureDirection.BULLISH,
                structure_break_count=len(structure.structure_breaks),
            ),
        )
        price_action_item = price_action_structure_evidence(price_action)

    assert price_action_item is not None
    assert price_action_item.direction is EvidenceDirection.BULLISH

    evidence = (price_action_item, harmonic_item)
    confluence = analyze_confluence(
        evidence,
        exchange=source[0].exchange,
        market_type=source[0].market_type,
        symbol=source[0].symbol,
        timeframe=source[0].timeframe,
        as_of_ms=as_of_ms,
    )
    decision = build_signal_decision(confluence)
    assert decision.state is SignalState.ACTIVE
    assert decision.geometry is not None

    return build_decision_freeze_bundle(
        decision=decision,
        confluence=confluence,
        price_action=price_action,
        harmonic=harmonic,
        elliott=analyze_elliott(
            source,
            left_bars=1,
            right_bars=1,
            as_of_ms=as_of_ms,
        ),
        candles=source,
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
