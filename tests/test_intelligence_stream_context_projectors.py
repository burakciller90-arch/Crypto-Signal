from __future__ import annotations

from decimal import Decimal

import pytest

from crypto_signal.confluence.models import PriceZone
from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamily,
    ConfluenceFamilyContribution,
    ConfluenceMatrixResolution,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CIRCUIT_BREAKER_ENGINE_VERSION,
    CircuitBreakerAnalysis,
    CircuitBreakerState,
)
from crypto_signal.intelligence.meta_intelligence import MetaDirection, MetaEvidenceState
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.decision_proof import DecisionProofEvidenceSummary
from crypto_signal.product.intelligence_stream_context_projectors import (
    StreamContextSourceKind,
    StreamProviderQualityState,
    build_stream_context_projector_policy,
    project_event_risk_context,
    project_provider_quality_context,
)
from crypto_signal.product.intelligence_stream_messages import (
    STREAM_FACT_BUNDLE_SCHEMA_VERSION,
    StreamFactBundle,
)
from crypto_signal.product.intelligence_stream_models import (
    REAL_CAPITAL,
    STREAM_ENGINE_VERSION,
    StreamCategory,
    StreamImportance,
    build_stream_activation_boundary,
)
from crypto_signal.product.intelligence_stream_policy import (
    StreamMateriality,
    StreamPublicationDisposition,
    StreamProjectorImplementationState,
    accepted_stream_projector_registry,
)
from crypto_signal.product.provider_divergence_runtime import (
    ProviderDivergenceRuntimeTruth,
    ProviderQualityRuntimeTruth,
)


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _contributions(seed: str) -> tuple[ConfluenceFamilyContribution, ...]:
    weights = {
        ConfluenceFamily.GEOMETRY: Decimal("0.20"),
        ConfluenceFamily.LIQUIDITY: Decimal("0.25"),
        ConfluenceFamily.ORDER_FLOW: Decimal("0.25"),
        ConfluenceFamily.DERIVATIVES: Decimal("0.15"),
        ConfluenceFamily.ONCHAIN: Decimal("0.15"),
    }
    points = {
        ConfluenceFamily.GEOMETRY: Decimal("20.00"),
        ConfluenceFamily.LIQUIDITY: Decimal("25.00"),
        ConfluenceFamily.ORDER_FLOW: Decimal("25.00"),
        ConfluenceFamily.DERIVATIVES: Decimal("12.00"),
        ConfluenceFamily.ONCHAIN: Decimal("0.00"),
    }
    return tuple(
        ConfluenceFamilyContribution(
            family=family,
            state=MetaEvidenceState.OBSERVED,
            direction=(
                MetaDirection.NEUTRAL
                if family is ConfluenceFamily.ONCHAIN
                else MetaDirection.BULLISH
            ),
            prior_weight=weights[family],
            directional_strength_0_1=(
                Decimal(0)
                if family is ConfluenceFamily.ONCHAIN
                else Decimal("0.90")
            ),
            support_points=points[family],
            opposition_points=Decimal(0),
            evidence_quality_0_1=Decimal("0.90"),
            freshness_0_1=Decimal("0.95"),
            material_conflict_count=0,
            source_evidence_identities=(_sha(f"{seed}-{family.value}"),),
        )
        for family in sorted(ConfluenceFamily, key=lambda item: item.value)
    )


def _fact(*, event_at_ms: int = 1_000_000, seed: str = "fact") -> StreamFactBundle:
    contributions = _contributions(seed)
    trigger_zone = PriceZone(Decimal(100), Decimal(102))
    target_zone = PriceZone(Decimal(108), Decimal(110))
    summary = DecisionProofEvidenceSummary(
        support_count=2,
        contradict_count=0,
        neutral_count=1,
        insufficient_count=2,
        available_count=3,
        total_domain_count=5,
    )
    values = {
        "stream_event_identity": _sha(f"{seed}-stream-event"),
        "source_event_identity": _sha(f"{seed}-source-event"),
        "story_identity": _sha(f"{seed}-story"),
        "decision_context_identity": _sha(f"{seed}-context"),
        "forecast_identity": _sha(f"{seed}-forecast"),
        "proof_identity": _sha(f"{seed}-proof"),
    }
    payload = {
        "asset": "BTC",
        "available_evidence_domains": ("consumed_candles", "frozen_chart"),
        "calibrated_probability_0_1": None,
        "confluence_opposition_score_0_100": Decimal("0.00"),
        "confluence_resolution": ConfluenceMatrixResolution.MEASURED,
        "confluence_support_score_0_100": Decimal("82.00"),
        "decision_context_identity": values["decision_context_identity"],
        "decision_source_as_of_ms": event_at_ms - 100,
        "decision_state": "active",
        "direction": "bullish",
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": event_at_ms,
        "event_context_state": CircuitBreakerState.CLEAR.value,
        "evidence_summary": summary,
        "family_contributions": contributions,
        "forecast_identity": values["forecast_identity"],
        "freshness_0_1": Decimal("0.95"),
        "invalidation_price": Decimal(95),
        "market": "BTCUSDT",
        "outcome_evidence_class": None,
        "probability_status": "NOT_CALIBRATED",
        "production_authority": False,
        "proof_identity": values["proof_identity"],
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "resolution_identity": None,
        "resolution_reason_codes": (),
        "resolution_state": None,
        "schema_version": STREAM_FACT_BUNDLE_SCHEMA_VERSION,
        "source_as_of_ms": event_at_ms - 100,
        "source_event_identity": values["source_event_identity"],
        "source_outcome_identity": None,
        "source_outcome_state": None,
        "story_identity": values["story_identity"],
        "stream_event_identity": values["stream_event_identity"],
        "symbol": "BTCUSDT",
        "target_zone": target_zone,
        "timeframe": "4h",
        "trigger_zone": trigger_zone,
        "uncertainty_flags": (),
    }
    return StreamFactBundle(
        fact_bundle_identity=canonical_sha256(payload),
        stream_event_identity=values["stream_event_identity"],
        source_event_identity=values["source_event_identity"],
        story_identity=values["story_identity"],
        decision_context_identity=values["decision_context_identity"],
        forecast_identity=values["forecast_identity"],
        proof_identity=values["proof_identity"],
        resolution_identity=None,
        source_outcome_identity=None,
        asset="BTC",
        symbol="BTCUSDT",
        market="BTCUSDT",
        timeframe="4h",
        event_at_ms=event_at_ms,
        source_as_of_ms=event_at_ms - 100,
        decision_source_as_of_ms=event_at_ms - 100,
        decision_state="active",
        direction="bullish",
        confluence_support_score_0_100=Decimal("82.00"),
        confluence_opposition_score_0_100=Decimal("0.00"),
        confluence_resolution=ConfluenceMatrixResolution.MEASURED,
        family_contributions=contributions,
        event_context_state=CircuitBreakerState.CLEAR.value,
        trigger_zone=trigger_zone,
        target_zone=target_zone,
        invalidation_price=Decimal(95),
        probability_status="NOT_CALIBRATED",
        calibrated_probability_0_1=None,
        freshness_0_1=Decimal("0.95"),
        uncertainty_flags=(),
        available_evidence_domains=("consumed_candles", "frozen_chart"),
        evidence_summary=summary,
        resolution_state=None,
        source_outcome_state=None,
        outcome_evidence_class=None,
        resolution_reason_codes=(),
    )


def _risk(
    *,
    state: CircuitBreakerState,
    as_of_ms: int,
    seed: str,
) -> CircuitBreakerAnalysis:
    event_risk_identity = _sha(f"{seed}-event-risk")
    news_identity = _sha(f"{seed}-news")
    market_identity = _sha(f"{seed}-market")
    triggers = (
        ()
        if state is CircuitBreakerState.CLEAR
        else (f"test_{state.value}",)
    )
    payload = {
        "as_of_ms": as_of_ms,
        "asset": "BTC",
        "engine_version": CIRCUIT_BREAKER_ENGINE_VERSION,
        "event_risk_identity": event_risk_identity,
        "market_quality_identity": market_identity,
        "news_evidence_identity": news_identity,
        "policy_version": "test-event-risk-policy/1",
        "real_capital": REAL_CAPITAL,
        "state": state,
        "triggers": triggers,
        "uncertainty_flags": (),
    }
    return CircuitBreakerAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=CIRCUIT_BREAKER_ENGINE_VERSION,
        policy_version="test-event-risk-policy/1",
        asset="BTC",
        as_of_ms=as_of_ms,
        state=state,
        event_risk_identity=event_risk_identity,
        news_evidence_identity=news_identity,
        market_quality_identity=market_identity,
        triggers=triggers,
        uncertainty_flags=(),
    )


def _provider(
    *,
    observed_at_ms: int,
    stale: bool,
    seed: str,
) -> ProviderDivergenceRuntimeTruth:
    freshness = ("source_stale",) if stale else ()
    left = ProviderQualityRuntimeTruth(
        exchange="binance",
        available=True,
        consumed_closed_candles=1,
        latest_open_time_ms=observed_at_ms - 1_000,
        latest_source_age_ms=10_000 if stale else 100,
        latest_closed_age_ms=10_000 if stale else 100,
        stale=stale,
        freshness_reasons=freshness,
        gap_count=0,
        gap_missing_candles=0,
    )
    right = ProviderQualityRuntimeTruth(
        exchange="bybit",
        available=True,
        consumed_closed_candles=1,
        latest_open_time_ms=observed_at_ms - 1_000,
        latest_source_age_ms=100,
        latest_closed_age_ms=100,
        stale=False,
        freshness_reasons=(),
        gap_count=0,
        gap_missing_candles=0,
    )
    return ProviderDivergenceRuntimeTruth(
        snapshot_identity=_sha(f"{seed}-provider-snapshot"),
        semantic="spot_candle_close_grid_divergence",
        market_type="spot",
        symbol="BTCUSDT",
        timeframe="4h",
        observed_at_ms=observed_at_ms,
        observation_age_ms=0,
        lookback_limit=1,
        left_exchange="binance",
        right_exchange="bybit",
        left_quality=left,
        right_quality=right,
        left_source_evidence_identities=(_sha(f"{seed}-left"),),
        right_source_evidence_identities=(_sha(f"{seed}-right"),),
        overlap_count=1,
        left_only_open_times_ms=(),
        right_only_open_times_ms=(),
        latest_overlap_open_time_ms=observed_at_ms - 1_000,
        latest_close_spread_bps=Decimal("0.25"),
        median_absolute_close_spread_bps=Decimal("0.25"),
        max_absolute_close_spread_bps=Decimal("0.25"),
        grid_state="full_overlap",
    )


def test_event_risk_projector_publishes_block_and_recovery_deterministically() -> None:
    fact = _fact(event_at_ms=1_000_000, seed="risk-fact")
    activation = build_stream_activation_boundary(activated_at_ms=900_000)
    policy = build_stream_context_projector_policy()
    clear = _risk(
        state=CircuitBreakerState.CLEAR,
        as_of_ms=1_100_000,
        seed="risk-clear",
    )
    blocked = _risk(
        state=CircuitBreakerState.EVENT_BLOCK,
        as_of_ms=1_200_000,
        seed="risk-block",
    )
    recovered = _risk(
        state=CircuitBreakerState.CLEAR,
        as_of_ms=1_300_000,
        seed="risk-recovery",
    )

    first = project_event_risk_context(
        policy,
        activation,
        fact,
        blocked,
        previous=clear,
    )
    replay = project_event_risk_context(
        policy,
        activation,
        fact,
        blocked,
        previous=clear,
    )
    assert first == replay
    assert first.candidate.source_kind is StreamContextSourceKind.EVENT_RISK
    assert first.candidate.disposition is StreamPublicationDisposition.PUBLISH
    assert first.candidate.materiality is StreamMateriality.MATERIAL
    assert first.candidate.subtype == "event_risk_block"
    assert first.candidate.importance is StreamImportance.CRITICAL
    assert first.candidate.previous_state == "clear"
    assert first.candidate.current_state == "event_block"
    assert first.candidate.reason_codes == ("event_risk_entered_blocking_state",)
    assert first.source_event is not None
    assert first.source_event.category is StreamCategory.RISK
    assert first.source_event.forecast_identity == fact.forecast_identity
    assert first.source_event.proof_identity == fact.proof_identity
    assert (
        first.source_event.decision_context_identity
        == fact.decision_context_identity
    )

    same_state = _risk(
        state=CircuitBreakerState.EVENT_BLOCK,
        as_of_ms=1_250_000,
        seed="risk-block-same",
    )
    silent = project_event_risk_context(
        policy,
        activation,
        fact,
        same_state,
        previous=blocked,
    )
    assert silent.candidate.disposition is StreamPublicationDisposition.SILENT
    assert silent.candidate.materiality is StreamMateriality.ROUTINE
    assert silent.source_event is None
    assert silent.candidate.reason_codes == (
        "no_material_event_risk_state_transition",
    )

    recovery = project_event_risk_context(
        policy,
        activation,
        fact,
        recovered,
        previous=blocked,
    )
    assert recovery.candidate.disposition is StreamPublicationDisposition.PUBLISH
    assert recovery.candidate.subtype == "event_risk_recovery"
    assert recovery.candidate.importance is StreamImportance.IMPORTANT
    assert recovery.candidate.current_state == "clear"
    assert recovery.source_event is not None


def test_provider_projector_publishes_only_degradation_and_recovery() -> None:
    fact = _fact(event_at_ms=2_000_000, seed="provider-fact")
    activation = build_stream_activation_boundary(activated_at_ms=1_900_000)
    policy = build_stream_context_projector_policy()
    healthy = _provider(
        observed_at_ms=2_100_000,
        stale=False,
        seed="provider-healthy",
    )
    degraded = _provider(
        observed_at_ms=2_200_000,
        stale=True,
        seed="provider-degraded",
    )
    recovered = _provider(
        observed_at_ms=2_300_000,
        stale=False,
        seed="provider-recovered",
    )

    degradation = project_provider_quality_context(
        policy,
        activation,
        fact,
        degraded,
        previous=healthy,
    )
    assert degradation.candidate.source_kind is StreamContextSourceKind.PROVIDER_QUALITY
    assert degradation.candidate.disposition is StreamPublicationDisposition.PUBLISH
    assert degradation.candidate.subtype == "data_quality_degraded"
    assert degradation.candidate.importance is StreamImportance.CRITICAL
    assert degradation.candidate.previous_state is StreamProviderQualityState.HEALTHY.value
    assert degradation.candidate.current_state is StreamProviderQualityState.DEGRADED.value
    assert degradation.candidate.reason_codes == (
        "left_provider_stale",
        "provider_quality_degraded",
    )
    assert degradation.candidate.evidence_identities == (
        degraded.snapshot_identity,
    )
    assert degradation.source_event is not None
    assert degradation.source_event.category is StreamCategory.SYSTEM
    assert "consensus" not in " ".join(degradation.candidate.reason_codes)
    assert "direction" not in " ".join(degradation.candidate.reason_codes)

    same = _provider(
        observed_at_ms=2_250_000,
        stale=True,
        seed="provider-degraded-same",
    )
    silent = project_provider_quality_context(
        policy,
        activation,
        fact,
        same,
        previous=degraded,
    )
    assert silent.candidate.disposition is StreamPublicationDisposition.SILENT
    assert silent.source_event is None

    recovery = project_provider_quality_context(
        policy,
        activation,
        fact,
        recovered,
        previous=degraded,
    )
    assert recovery.candidate.disposition is StreamPublicationDisposition.PUBLISH
    assert recovery.candidate.subtype == "data_quality_recovered"
    assert recovery.candidate.importance is StreamImportance.IMPORTANT
    assert recovery.candidate.reason_codes == ("provider_quality_recovered",)
    assert recovery.source_event is not None


def test_initial_healthy_context_is_silent_but_initial_material_risk_publishes() -> None:
    fact = _fact(event_at_ms=3_000_000, seed="initial-fact")
    activation = build_stream_activation_boundary(activated_at_ms=2_900_000)
    policy = build_stream_context_projector_policy()

    healthy = _provider(
        observed_at_ms=3_100_000,
        stale=False,
        seed="initial-provider",
    )
    provider_projection = project_provider_quality_context(
        policy,
        activation,
        fact,
        healthy,
    )
    assert provider_projection.candidate.disposition is StreamPublicationDisposition.SILENT
    assert provider_projection.source_event is None
    assert provider_projection.candidate.reason_codes == (
        "initial_provider_quality_healthy",
    )

    caution = _risk(
        state=CircuitBreakerState.CAUTION,
        as_of_ms=3_100_000,
        seed="initial-caution",
    )
    risk_projection = project_event_risk_context(
        policy,
        activation,
        fact,
        caution,
    )
    assert risk_projection.candidate.disposition is StreamPublicationDisposition.PUBLISH
    assert risk_projection.candidate.subtype == "event_risk_change"
    assert risk_projection.candidate.reason_codes == (
        "initial_event_risk_caution",
    )


def test_context_projectors_reject_future_or_wrong_market_joins() -> None:
    fact = _fact(event_at_ms=4_000_000, seed="join-fact")
    activation = build_stream_activation_boundary(activated_at_ms=3_900_000)
    policy = build_stream_context_projector_policy()

    too_old = _risk(
        state=CircuitBreakerState.CAUTION,
        as_of_ms=3_950_000,
        seed="too-old",
    )
    with pytest.raises(ValueError, match="predates target decision fact"):
        project_event_risk_context(
            policy,
            activation,
            fact,
            too_old,
        )

    provider = _provider(
        observed_at_ms=4_100_000,
        stale=True,
        seed="wrong-provider",
    )
    wrong_fact = _fact(event_at_ms=4_000_000, seed="wrong-fact")
    object.__setattr__(wrong_fact, "symbol", "ETHUSDT")
    with pytest.raises(ValueError, match="symbol/decision mismatch"):
        project_provider_quality_context(
            policy,
            activation,
            wrong_fact,
            provider,
        )


def test_s4_registry_marks_event_risk_and_provider_projectors_implemented() -> None:
    registry = {
        item.projector_id: item
        for item in accepted_stream_projector_registry()
    }
    assert (
        registry["event_risk_change"].implementation_state
        is StreamProjectorImplementationState.IMPLEMENTED
    )
    assert registry["event_risk_change"].target_phase == "S4"
    assert (
        registry["provider_quality_change"].implementation_state
        is StreamProjectorImplementationState.IMPLEMENTED
    )
    assert registry["provider_quality_change"].target_phase == "S4"
