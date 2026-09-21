from __future__ import annotations

import hashlib
import inspect
from decimal import Decimal

import pytest

from crypto_signal.intelligence import meta_intelligence
from crypto_signal.intelligence.meta_intelligence import (
    META_SCORE_SEMANTIC,
    PROBABILITY_STATUS,
    MetaCorrelationGroup,
    MetaDirection,
    MetaEvidenceState,
    MetaRelationKind,
    MetaResolution,
    MetaWeightRule,
    build_meta_observation,
    build_meta_relation,
    build_meta_weight_policy,
    evaluate_meta_intelligence,
)


def _sha(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def _observed(
    engine_id: str,
    direction: MetaDirection,
    *,
    regime: str = "trend_up",
    suffix: str = "",
):
    return build_meta_observation(
        source_engine_id=engine_id,
        source_engine_version=f"{engine_id}-v1/1",
        asset="BTCUSDT",
        timeframe="4h",
        regime=regime,
        as_of_ms=1_000,
        market_available_at_ms=900,
        observed_at_ms=950,
        state=MetaEvidenceState.OBSERVED,
        direction=direction,
        source_evidence_identities=(_sha(f"{engine_id}{suffix}-evidence"),),
        uncertainty_flags=(),
    )


def test_policy_identity_is_canonical_and_shadow_only() -> None:
    left = build_meta_weight_policy(
        policy_version="meta-policy-v1/1",
        rules=(
            MetaWeightRule("trend", "trend_up", Decimal("0.7")),
            MetaWeightRule("breakout", "trend_up", Decimal("0.5")),
        ),
        correlation_groups=(
            MetaCorrelationGroup(
                group_id="directional",
                engine_ids=("breakout", "trend"),
                max_total_weight=Decimal("0.8"),
            ),
        ),
    )
    right = build_meta_weight_policy(
        policy_version="meta-policy-v1/1",
        rules=(
            MetaWeightRule("breakout", "trend_up", Decimal("0.5")),
            MetaWeightRule("trend", "trend_up", Decimal("0.7")),
        ),
        correlation_groups=(
            MetaCorrelationGroup(
                group_id="directional",
                engine_ids=("trend", "breakout"),
                max_total_weight=Decimal("0.8"),
            ),
        ),
    )

    assert left == right
    assert left.policy_identity == right.policy_identity
    assert left.shadow_only is True
    assert left.production_contribution == 0
    assert left.production_authority is False
    assert left.automatic_promotion is False
    assert left.deploy_authority is False
    assert left.probability_status == PROBABILITY_STATUS
    assert left.real_capital == 0


def test_correlated_evidence_is_capped_without_double_counting_and_is_permutation_invariant() -> None:
    trend = _observed("trend", MetaDirection.BULLISH)
    breakout = _observed("breakout", MetaDirection.BULLISH)
    abstain = build_meta_observation(
        source_engine_id="sentiment",
        source_engine_version="sentiment-v1/1",
        asset="BTCUSDT",
        timeframe="4h",
        regime="trend_up",
        as_of_ms=1_000,
        market_available_at_ms=900,
        observed_at_ms=950,
        state=MetaEvidenceState.ABSTAIN,
        direction=None,
        source_evidence_identities=(_sha("sentiment-abstain"),),
        uncertainty_flags=("conflicting_sources",),
    )
    policy = build_meta_weight_policy(
        policy_version="meta-policy-v1/1",
        rules=(
            MetaWeightRule("breakout", "trend_up", Decimal("0.8")),
            MetaWeightRule("trend", "trend_up", Decimal("0.8")),
        ),
        correlation_groups=(
            MetaCorrelationGroup(
                group_id="directional",
                engine_ids=("breakout", "trend"),
                max_total_weight=Decimal("0.8"),
            ),
        ),
    )

    first = evaluate_meta_intelligence(
        policy,
        (trend, breakout, abstain),
    )
    second = evaluate_meta_intelligence(
        policy,
        (abstain, breakout, trend),
    )

    assert first == second
    assert first.snapshot_identity == second.snapshot_identity
    assert first.redundancy_scaled_group_count == 1
    assert first.total_effective_weight == Decimal("0.8")
    assert first.bullish_weight == Decimal("0.8")
    assert first.bearish_weight == 0
    assert first.signed_balance == Decimal("0.8")
    assert first.resolution is MetaResolution.BULLISH_LEAN
    assert first.state_counts == (("abstain", 1), ("observed", 2))
    assert first.score_semantic == META_SCORE_SEMANTIC
    assert first.probability_status == "not_calibrated"
    assert first.production_contribution == 0


def test_uncovered_redundancy_relation_fails_closed() -> None:
    trend = _observed("trend", MetaDirection.BULLISH)
    breakout = _observed("breakout", MetaDirection.BULLISH)
    relation = build_meta_relation(
        trend.observation_identity,
        breakout.observation_identity,
        relation=MetaRelationKind.REDUNDANT,
        basis_evidence_identity=_sha("redundancy-basis"),
    )
    policy = build_meta_weight_policy(
        policy_version="meta-policy-v1/1",
        rules=(
            MetaWeightRule("breakout", "trend_up", Decimal("0.5")),
            MetaWeightRule("trend", "trend_up", Decimal("0.5")),
        ),
    )

    snapshot = evaluate_meta_intelligence(
        policy,
        (trend, breakout),
        (relation,),
    )

    assert snapshot.resolution is MetaResolution.POLICY_INCOMPLETE
    assert snapshot.signed_balance is None
    assert snapshot.policy_gap_engine_ids == ()
    assert snapshot.uncovered_correlation_relation_ids == (
        relation.relation_identity,
    )
    assert snapshot.production_contribution == 0


def test_explicit_contradiction_and_directional_conflict_are_first_class() -> None:
    trend = _observed("trend", MetaDirection.BULLISH)
    mean_reversion = _observed("mean_reversion", MetaDirection.BEARISH)
    relation = build_meta_relation(
        trend.observation_identity,
        mean_reversion.observation_identity,
        relation=MetaRelationKind.CONTRADICTORY,
        basis_evidence_identity=_sha("contradiction-basis"),
    )
    policy = build_meta_weight_policy(
        policy_version="meta-policy-v1/1",
        rules=(
            MetaWeightRule("mean_reversion", "trend_up", Decimal("0.5")),
            MetaWeightRule("trend", "trend_up", Decimal("0.5")),
        ),
    )

    snapshot = evaluate_meta_intelligence(
        policy,
        (trend, mean_reversion),
        (relation,),
    )

    assert snapshot.resolution is MetaResolution.CONTRADICTORY
    assert snapshot.explicit_contradiction_count == 1
    assert snapshot.directional_conflict is True
    assert snapshot.bullish_weight == Decimal("0.5")
    assert snapshot.bearish_weight == Decimal("0.5")
    assert snapshot.signed_balance == 0
    assert snapshot.relation_counts == (("contradictory", 1),)
    assert snapshot.probability_status == "not_calibrated"


def test_abstention_no_evidence_and_not_evaluable_do_not_invent_contribution() -> None:
    abstain = build_meta_observation(
        source_engine_id="sentiment",
        source_engine_version="sentiment-v1/1",
        asset="BTCUSDT",
        timeframe="4h",
        regime="transition",
        as_of_ms=1_000,
        market_available_at_ms=900,
        observed_at_ms=950,
        state=MetaEvidenceState.ABSTAIN,
        direction=None,
        source_evidence_identities=(_sha("abstain-evidence"),),
        uncertainty_flags=("source_disagreement",),
    )
    no_evidence = build_meta_observation(
        source_engine_id="onchain",
        source_engine_version="onchain-v1/1",
        asset="BTCUSDT",
        timeframe="4h",
        regime="transition",
        as_of_ms=1_000,
        market_available_at_ms=None,
        observed_at_ms=None,
        state=MetaEvidenceState.NO_EVIDENCE,
        direction=None,
        source_evidence_identities=(),
        uncertainty_flags=("provider_unavailable",),
    )
    policy = build_meta_weight_policy(
        policy_version="meta-policy-v1/1",
        rules=(MetaWeightRule("sentiment", "transition", Decimal("0.4")),),
    )

    snapshot = evaluate_meta_intelligence(policy, (no_evidence, abstain))

    assert snapshot.resolution is MetaResolution.ABSTAIN_ONLY
    assert snapshot.signed_balance == 0
    assert snapshot.total_effective_weight == 0
    assert snapshot.state_counts == (("abstain", 1), ("no_evidence", 1))
    assert all(item.effective_weight == 0 for item in snapshot.contributions)

    not_evaluable = build_meta_observation(
        source_engine_id="cross_market",
        source_engine_version="cross-market-v1/1",
        asset="BTCUSDT",
        timeframe="4h",
        regime="transition",
        as_of_ms=1_000,
        market_available_at_ms=None,
        observed_at_ms=None,
        state=MetaEvidenceState.NOT_EVALUABLE,
        direction=None,
        source_evidence_identities=(),
        uncertainty_flags=("required_context_missing",),
    )
    snapshot_ne = evaluate_meta_intelligence(
        policy,
        (no_evidence, not_evaluable),
    )
    assert snapshot_ne.resolution is MetaResolution.NOT_EVALUABLE
    assert snapshot_ne.signed_balance == 0


def test_regime_specific_policy_changes_only_shadow_weight() -> None:
    policy = build_meta_weight_policy(
        policy_version="meta-policy-v1/1",
        rules=(
            MetaWeightRule("trend", "range", Decimal("0.2")),
            MetaWeightRule("trend", "trend_up", Decimal("0.8")),
        ),
    )
    trend_context = _observed(
        "trend",
        MetaDirection.BULLISH,
        regime="trend_up",
        suffix="-trend",
    )
    range_context = _observed(
        "trend",
        MetaDirection.BULLISH,
        regime="range",
        suffix="-range",
    )

    trend_snapshot = evaluate_meta_intelligence(policy, (trend_context,))
    range_snapshot = evaluate_meta_intelligence(policy, (range_context,))

    assert trend_snapshot.signed_balance == Decimal("0.8")
    assert range_snapshot.signed_balance == Decimal("0.2")
    assert trend_snapshot.policy_identity == range_snapshot.policy_identity
    assert trend_snapshot.production_contribution == 0
    assert range_snapshot.production_contribution == 0
    assert trend_snapshot.shadow_only is True
    assert range_snapshot.shadow_only is True


def test_missing_weight_rule_fails_closed_without_partial_balance() -> None:
    breakout = _observed("breakout", MetaDirection.BULLISH)
    policy = build_meta_weight_policy(
        policy_version="meta-policy-v1/1",
        rules=(MetaWeightRule("trend", "trend_up", Decimal("0.5")),),
    )

    snapshot = evaluate_meta_intelligence(policy, (breakout,))

    assert snapshot.resolution is MetaResolution.POLICY_INCOMPLETE
    assert snapshot.policy_gap_engine_ids == ("breakout",)
    assert snapshot.signed_balance is None
    assert snapshot.total_effective_weight == 0
    assert snapshot.production_contribution == 0


def test_observation_rejects_future_or_inconsistent_pit_evidence() -> None:
    with pytest.raises(ValueError, match="after as_of"):
        build_meta_observation(
            source_engine_id="trend",
            source_engine_version="trend-v1/1",
            asset="BTCUSDT",
            timeframe="4h",
            regime="trend_up",
            as_of_ms=1_000,
            market_available_at_ms=900,
            observed_at_ms=1_001,
            state=MetaEvidenceState.OBSERVED,
            direction=MetaDirection.BULLISH,
            source_evidence_identities=(_sha("future"),),
        )

    with pytest.raises(ValueError, match="before availability"):
        build_meta_observation(
            source_engine_id="trend",
            source_engine_version="trend-v1/1",
            asset="BTCUSDT",
            timeframe="4h",
            regime="trend_up",
            as_of_ms=1_000,
            market_available_at_ms=950,
            observed_at_ms=900,
            state=MetaEvidenceState.OBSERVED,
            direction=MetaDirection.BULLISH,
            source_evidence_identities=(_sha("time-order"),),
        )


def test_duplicate_engine_or_context_mismatch_is_rejected() -> None:
    first = _observed("trend", MetaDirection.BULLISH, suffix="-a")
    duplicate = _observed("trend", MetaDirection.BULLISH, suffix="-b")
    other_regime = _observed(
        "breakout",
        MetaDirection.BULLISH,
        regime="range",
    )
    policy = build_meta_weight_policy(
        policy_version="meta-policy-v1/1",
        rules=(
            MetaWeightRule("breakout", "range", Decimal("0.4")),
            MetaWeightRule("trend", "trend_up", Decimal("0.4")),
        ),
    )

    with pytest.raises(ValueError, match="one observation per source engine"):
        evaluate_meta_intelligence(policy, (first, duplicate))

    with pytest.raises(ValueError, match="share exact context"):
        evaluate_meta_intelligence(policy, (first, other_regime))


def test_meta_engine_has_no_production_or_external_action_surface() -> None:
    source = inspect.getsource(meta_intelligence).lower()

    assert "crypto_signal.paper" not in source
    assert "crypto_signal.signals" not in source
    assert "requests" not in source
    assert "subprocess" not in source
    assert "socket" not in source
    assert "broker" not in source
    assert meta_intelligence.REAL_CAPITAL == 0
    assert meta_intelligence.PROBABILITY_STATUS == "not_calibrated"
