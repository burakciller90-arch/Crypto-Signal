from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.intelligence.confluence_matrix_v2 import (
    LOCKED_M6_THRESHOLD_HYPOTHESES,
    M6_PROBABILITY_STATUS,
    M6_SCORE_SEMANTIC,
    ConfluenceFamily,
    ConfluenceMatrixResolution,
    build_confluence_family_evidence,
    build_locked_m6_policy,
    evaluate_confluence_matrix,
)
from crypto_signal.intelligence.meta_intelligence import (
    MetaDirection,
    MetaEvidenceState,
)
from crypto_signal.ledger.serialization import canonical_sha256

AS_OF = 1_000_000
FAMILIES = tuple(sorted(ConfluenceFamily, key=lambda item: item.value))


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _observed(
    family: ConfluenceFamily,
    direction: MetaDirection,
    *,
    strength: str = "1",
    quality: str = "0.90",
    freshness: str = "0.95",
    conflicts: tuple[str, ...] = (),
):
    return build_confluence_family_evidence(
        family=family,
        asset="BTCUSDT",
        timeframe="4h",
        regime="trend_up",
        as_of_ms=AS_OF,
        state=MetaEvidenceState.OBSERVED,
        direction=direction,
        directional_strength_0_1=Decimal(strength),
        evidence_quality_0_1=Decimal(quality),
        freshness_0_1=Decimal(freshness),
        market_available_at_ms=AS_OF - 100,
        observed_at_ms=AS_OF - 50,
        source_engine_ids=(f"{family.value}-engine",),
        source_evidence_identities=(_sha(f"{family.value}-source"),),
        material_conflict_identities=tuple(sorted(conflicts)),
        uncertainty_flags=(),
    )


def _unavailable(
    family: ConfluenceFamily,
    state: MetaEvidenceState,
):
    return build_confluence_family_evidence(
        family=family,
        asset="BTCUSDT",
        timeframe="4h",
        regime="trend_up",
        as_of_ms=AS_OF,
        state=state,
        direction=None,
        directional_strength_0_1=None,
        evidence_quality_0_1=None,
        freshness_0_1=None,
        market_available_at_ms=None,
        observed_at_ms=None,
        source_engine_ids=(),
        source_evidence_identities=(),
        uncertainty_flags=("family_evidence_unavailable",),
    )


def _abstain(family: ConfluenceFamily):
    return build_confluence_family_evidence(
        family=family,
        asset="BTCUSDT",
        timeframe="4h",
        regime="trend_up",
        as_of_ms=AS_OF,
        state=MetaEvidenceState.ABSTAIN,
        direction=None,
        directional_strength_0_1=Decimal(0),
        evidence_quality_0_1=Decimal("0.50"),
        freshness_0_1=Decimal("0.90"),
        market_available_at_ms=AS_OF - 100,
        observed_at_ms=AS_OF - 50,
        source_engine_ids=(f"{family.value}-engine",),
        source_evidence_identities=(_sha(f"{family.value}-abstain"),),
        uncertainty_flags=("family_abstain",),
    )


def test_locked_policy_priors_and_threshold_hypotheses_are_exact() -> None:
    policy = build_locked_m6_policy()

    weights = {item.family: item.weight for item in policy.priors}
    assert weights == {
        ConfluenceFamily.GEOMETRY: Decimal("0.20"),
        ConfluenceFamily.LIQUIDITY: Decimal("0.25"),
        ConfluenceFamily.ORDER_FLOW: Decimal("0.25"),
        ConfluenceFamily.DERIVATIVES: Decimal("0.15"),
        ConfluenceFamily.ONCHAIN: Decimal("0.15"),
    }
    assert sum(weights.values(), start=Decimal(0)) == Decimal(1)
    assert policy.threshold_hypotheses == LOCKED_M6_THRESHOLD_HYPOTHESES
    assert policy.threshold_hypotheses == (
        Decimal("70"),
        Decimal("75"),
        Decimal("80"),
        Decimal("85"),
    )
    assert policy.event_risk_outside_matrix is True
    assert policy.automatic_activation is False
    assert policy.automatic_promotion is False
    assert policy.production_authority is False
    assert policy.probability_status == "not_calibrated"
    assert policy.real_capital == 0


def test_confluence_82_can_coexist_with_probability_not_calibrated() -> None:
    evidence = (
        _observed(ConfluenceFamily.GEOMETRY, MetaDirection.BULLISH),
        _observed(ConfluenceFamily.LIQUIDITY, MetaDirection.BULLISH),
        _observed(ConfluenceFamily.ORDER_FLOW, MetaDirection.BULLISH),
        _observed(
            ConfluenceFamily.DERIVATIVES,
            MetaDirection.BULLISH,
            strength="0.8",
        ),
        _observed(ConfluenceFamily.ONCHAIN, MetaDirection.NEUTRAL),
    )
    first = evaluate_confluence_matrix(
        build_locked_m6_policy(),
        evidence,
        candidate_direction=MetaDirection.BULLISH,
    )
    second = evaluate_confluence_matrix(
        build_locked_m6_policy(),
        tuple(reversed(evidence)),
        candidate_direction=MetaDirection.BULLISH,
    )

    assert first == second
    assert first.resolution is ConfluenceMatrixResolution.MEASURED
    assert first.support_score_0_100 == Decimal("82.00")
    assert first.opposition_score_0_100 == Decimal("0.00")
    assert first.evidence_coverage_0_100 == Decimal("100.00")
    assert first.probability_status == M6_PROBABILITY_STATUS
    assert first.probability_status == "not_calibrated"
    assert first.score_semantic == M6_SCORE_SEMANTIC
    assert first.event_risk_outside_matrix is True
    assert first.automatic_activation is False
    assert first.production_authority is False
    assert first.real_capital == 0


def test_support_and_opposition_are_kept_separate() -> None:
    evidence = (
        _observed(ConfluenceFamily.GEOMETRY, MetaDirection.BULLISH),
        _observed(ConfluenceFamily.LIQUIDITY, MetaDirection.BULLISH),
        _observed(ConfluenceFamily.ORDER_FLOW, MetaDirection.BEARISH),
        _observed(ConfluenceFamily.DERIVATIVES, MetaDirection.BULLISH),
        _observed(ConfluenceFamily.ONCHAIN, MetaDirection.NEUTRAL),
    )
    snapshot = evaluate_confluence_matrix(
        build_locked_m6_policy(),
        evidence,
        candidate_direction=MetaDirection.BULLISH,
    )

    assert snapshot.support_score_0_100 == Decimal("60.00")
    assert snapshot.opposition_score_0_100 == Decimal("25.00")
    assert snapshot.resolution is ConfluenceMatrixResolution.MEASURED
    order_flow = next(
        item
        for item in snapshot.contributions
        if item.family is ConfluenceFamily.ORDER_FLOW
    )
    assert order_flow.support_points == 0
    assert order_flow.opposition_points == Decimal("25.00")


def test_material_independent_conflict_vetoes_high_arithmetic_support() -> None:
    conflict = _sha("material-independent-conflict")
    evidence = (
        _observed(ConfluenceFamily.GEOMETRY, MetaDirection.BULLISH),
        _observed(ConfluenceFamily.LIQUIDITY, MetaDirection.BULLISH),
        _observed(ConfluenceFamily.ORDER_FLOW, MetaDirection.BULLISH),
        _observed(ConfluenceFamily.DERIVATIVES, MetaDirection.BULLISH),
        _observed(
            ConfluenceFamily.ONCHAIN,
            MetaDirection.BULLISH,
            conflicts=(conflict,),
        ),
    )
    snapshot = evaluate_confluence_matrix(
        build_locked_m6_policy(),
        evidence,
        candidate_direction=MetaDirection.BULLISH,
    )

    assert snapshot.support_score_0_100 == Decimal("100.00")
    assert snapshot.material_conflict_identities == (conflict,)
    assert snapshot.resolution is ConfluenceMatrixResolution.CONFLICT
    assert snapshot.automatic_activation is False


def test_abstaining_family_has_precedence_over_score_and_conflict() -> None:
    conflict = _sha("conflict-under-abstain")
    evidence = (
        _observed(
            ConfluenceFamily.GEOMETRY,
            MetaDirection.BULLISH,
            conflicts=(conflict,),
        ),
        _observed(ConfluenceFamily.LIQUIDITY, MetaDirection.BULLISH),
        _observed(ConfluenceFamily.ORDER_FLOW, MetaDirection.BULLISH),
        _observed(ConfluenceFamily.DERIVATIVES, MetaDirection.BULLISH),
        _abstain(ConfluenceFamily.ONCHAIN),
    )
    snapshot = evaluate_confluence_matrix(
        build_locked_m6_policy(),
        evidence,
        candidate_direction=MetaDirection.BULLISH,
    )

    assert snapshot.resolution is ConfluenceMatrixResolution.ABSTAIN
    assert snapshot.material_conflict_identities == (conflict,)
    assert snapshot.support_score_0_100 == Decimal("85.00")


def test_missing_family_is_explicit_partial_and_reduces_coverage() -> None:
    evidence = (
        _observed(ConfluenceFamily.GEOMETRY, MetaDirection.BULLISH),
        _observed(ConfluenceFamily.LIQUIDITY, MetaDirection.BULLISH),
        _observed(ConfluenceFamily.ORDER_FLOW, MetaDirection.BULLISH),
        _observed(ConfluenceFamily.DERIVATIVES, MetaDirection.BULLISH),
        _unavailable(ConfluenceFamily.ONCHAIN, MetaEvidenceState.NO_EVIDENCE),
    )
    snapshot = evaluate_confluence_matrix(
        build_locked_m6_policy(),
        evidence,
        candidate_direction=MetaDirection.BULLISH,
    )

    assert snapshot.resolution is ConfluenceMatrixResolution.PARTIAL
    assert snapshot.evidence_coverage_0_100 == Decimal("85.00")
    assert snapshot.support_score_0_100 == Decimal("85.00")


def test_not_evaluable_family_is_not_silently_downgraded_to_no_evidence() -> None:
    evidence = (
        _observed(ConfluenceFamily.GEOMETRY, MetaDirection.BULLISH),
        _observed(ConfluenceFamily.LIQUIDITY, MetaDirection.BULLISH),
        _observed(ConfluenceFamily.ORDER_FLOW, MetaDirection.BULLISH),
        _unavailable(
            ConfluenceFamily.DERIVATIVES,
            MetaEvidenceState.NOT_EVALUABLE,
        ),
        _observed(ConfluenceFamily.ONCHAIN, MetaDirection.BULLISH),
    )
    snapshot = evaluate_confluence_matrix(
        build_locked_m6_policy(),
        evidence,
        candidate_direction=MetaDirection.BULLISH,
    )

    assert snapshot.resolution is ConfluenceMatrixResolution.NOT_EVALUABLE
    assert snapshot.evidence_coverage_0_100 == Decimal("85.00")


def test_quality_and_freshness_are_separate_from_support_score() -> None:
    evidence = (
        _observed(
            ConfluenceFamily.GEOMETRY,
            MetaDirection.BULLISH,
            quality="0.50",
            freshness="0.60",
        ),
        _observed(
            ConfluenceFamily.LIQUIDITY,
            MetaDirection.BULLISH,
            quality="0.70",
            freshness="0.80",
        ),
        _observed(
            ConfluenceFamily.ORDER_FLOW,
            MetaDirection.BULLISH,
            quality="0.90",
            freshness="1.00",
        ),
        _observed(
            ConfluenceFamily.DERIVATIVES,
            MetaDirection.BULLISH,
            quality="0.40",
            freshness="0.50",
        ),
        _observed(
            ConfluenceFamily.ONCHAIN,
            MetaDirection.BULLISH,
            quality="1.00",
            freshness="0.70",
        ),
    )
    snapshot = evaluate_confluence_matrix(
        build_locked_m6_policy(),
        evidence,
        candidate_direction=MetaDirection.BULLISH,
    )

    assert snapshot.support_score_0_100 == Decimal("100.00")
    assert snapshot.evidence_quality_0_1 == Decimal("0.7100")
    assert snapshot.freshness_0_1 == Decimal("0.7500")


def test_context_duplicates_tampering_and_invalid_measures_fail_closed() -> None:
    policy = build_locked_m6_policy()
    evidence = [
        _observed(family, MetaDirection.BULLISH)
        for family in FAMILIES
    ]

    duplicate = tuple(evidence[:-1] + [evidence[-2]])
    with pytest.raises(ValueError, match="exactly one evidence object per family"):
        evaluate_confluence_matrix(
            policy,
            duplicate,
            candidate_direction=MetaDirection.BULLISH,
        )

    wrong_context = list(evidence)
    original = wrong_context[-1]
    wrong_context[-1] = build_confluence_family_evidence(
        family=original.family,
        asset="ETHUSDT",
        timeframe=original.timeframe,
        regime=original.regime,
        as_of_ms=original.as_of_ms,
        state=original.state,
        direction=original.direction,
        directional_strength_0_1=original.directional_strength_0_1,
        evidence_quality_0_1=original.evidence_quality_0_1,
        freshness_0_1=original.freshness_0_1,
        market_available_at_ms=original.market_available_at_ms,
        observed_at_ms=original.observed_at_ms,
        source_engine_ids=original.source_engine_ids,
        source_evidence_identities=original.source_evidence_identities,
    )
    with pytest.raises(ValueError, match="share exact context"):
        evaluate_confluence_matrix(
            policy,
            tuple(wrong_context),
            candidate_direction=MetaDirection.BULLISH,
        )

    snapshot = evaluate_confluence_matrix(
        policy,
        tuple(evidence),
        candidate_direction=MetaDirection.BULLISH,
    )
    with pytest.raises(ValueError, match="snapshot identity mismatch"):
        replace(snapshot, support_score_0_100=Decimal("99"))

    with pytest.raises(ValueError, match="inside"):
        _observed(
            ConfluenceFamily.GEOMETRY,
            MetaDirection.BULLISH,
            quality="1.1",
        )
