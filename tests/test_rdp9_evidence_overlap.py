from __future__ import annotations

from decimal import Decimal

from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamily,
    build_confluence_family_evidence,
    build_locked_m6_policy,
    evaluate_confluence_matrix,
)
from crypto_signal.intelligence.evidence_overlap import (
    analyze_confluence_evidence_overlap,
)
from crypto_signal.intelligence.meta_intelligence import (
    MetaDirection,
    MetaEvidenceState,
)
from crypto_signal.ledger.serialization import canonical_sha256

AS_OF = 1_000_000


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _family(
    family: ConfluenceFamily,
    *,
    sources: tuple[str, ...],
    direction: MetaDirection = MetaDirection.BULLISH,
):
    return build_confluence_family_evidence(
        family=family,
        asset="BTCUSDT",
        timeframe="4h",
        regime="trend_up",
        as_of_ms=AS_OF,
        state=MetaEvidenceState.OBSERVED,
        direction=direction,
        directional_strength_0_1=Decimal(1),
        evidence_quality_0_1=Decimal(1),
        freshness_0_1=Decimal(1),
        market_available_at_ms=AS_OF - 2,
        observed_at_ms=AS_OF - 1,
        source_engine_ids=(f"{family.value}-engine",),
        source_evidence_identities=sources,
        uncertainty_flags=(),
    )


def _evidence(
    *,
    liquidity_sources: tuple[str, ...],
    order_flow_sources: tuple[str, ...],
):
    return tuple(
        sorted(
            (
                _family(
                    ConfluenceFamily.GEOMETRY,
                    sources=(_sha("geometry"),),
                ),
                _family(
                    ConfluenceFamily.LIQUIDITY,
                    sources=liquidity_sources,
                ),
                _family(
                    ConfluenceFamily.ORDER_FLOW,
                    sources=order_flow_sources,
                ),
                _family(
                    ConfluenceFamily.DERIVATIVES,
                    sources=(_sha("derivatives"),),
                ),
                _family(
                    ConfluenceFamily.ONCHAIN,
                    sources=(_sha("onchain"),),
                ),
            ),
            key=lambda item: item.family.value,
        )
    )


def test_unique_family_sources_preserve_locked_m6_score_exactly() -> None:
    evidence = _evidence(
        liquidity_sources=(_sha("liquidity"),),
        order_flow_sources=(_sha("order-flow"),),
    )
    overlap = analyze_confluence_evidence_overlap(evidence)
    snapshot = evaluate_confluence_matrix(
        build_locked_m6_policy(),
        evidence,
        candidate_direction=MetaDirection.BULLISH,
    )

    assert overlap.has_overlap is False
    assert overlap.relations == ()
    assert overlap.lineage_identities == ()
    assert all(
        item.attribution_factor_0_1 == Decimal(1)
        for item in overlap.attributions
    )
    assert snapshot.support_score_0_100 == Decimal("100.00")


def test_exact_shared_source_is_attributed_once_not_double_counted() -> None:
    shared = _sha("shared-orderbook")
    evidence = _evidence(
        liquidity_sources=(shared,),
        order_flow_sources=(shared,),
    )
    overlap = analyze_confluence_evidence_overlap(evidence)
    snapshot = evaluate_confluence_matrix(
        build_locked_m6_policy(),
        evidence,
        candidate_direction=MetaDirection.BULLISH,
    )

    assert overlap.has_overlap is True
    assert overlap.shared_source_evidence_identities == (shared,)
    assert len(overlap.relations) == 1
    assert overlap.relations[0].family_values == (
        ConfluenceFamily.LIQUIDITY.value,
        ConfluenceFamily.ORDER_FLOW.value,
    )
    assert overlap.relations[0].attribution_per_family_0_1 == Decimal(
        "0.500000000000"
    )
    assert overlap.attribution_factor(
        ConfluenceFamily.LIQUIDITY
    ) == Decimal("0.500000000000")
    assert overlap.attribution_factor(
        ConfluenceFamily.ORDER_FLOW
    ) == Decimal("0.500000000000")
    assert len(overlap.lineage_identities) == 2

    by_family = {item.family: item for item in snapshot.contributions}
    assert by_family[ConfluenceFamily.LIQUIDITY].support_points == Decimal(
        "12.50"
    )
    assert by_family[ConfluenceFamily.ORDER_FLOW].support_points == Decimal(
        "12.50"
    )
    assert snapshot.support_score_0_100 == Decimal("75.00")


def test_partial_overlap_preserves_independent_evidence_share() -> None:
    shared = _sha("shared-orderbook")
    evidence = _evidence(
        liquidity_sources=(shared, _sha("liquidity-independent")),
        order_flow_sources=(shared, _sha("flow-independent")),
    )
    overlap = analyze_confluence_evidence_overlap(evidence)
    snapshot = evaluate_confluence_matrix(
        build_locked_m6_policy(),
        evidence,
        candidate_direction=MetaDirection.BULLISH,
    )

    assert overlap.attribution_factor(
        ConfluenceFamily.LIQUIDITY
    ) == Decimal("0.750000000000")
    assert overlap.attribution_factor(
        ConfluenceFamily.ORDER_FLOW
    ) == Decimal("0.750000000000")
    assert snapshot.support_score_0_100 == Decimal("87.50")


def test_three_family_shared_truth_gets_one_third_attribution_each() -> None:
    shared = _sha("shared-three-family")
    evidence = tuple(
        sorted(
            (
                _family(ConfluenceFamily.GEOMETRY, sources=(shared,)),
                _family(ConfluenceFamily.LIQUIDITY, sources=(shared,)),
                _family(ConfluenceFamily.ORDER_FLOW, sources=(shared,)),
                _family(
                    ConfluenceFamily.DERIVATIVES,
                    sources=(_sha("derivatives"),),
                ),
                _family(
                    ConfluenceFamily.ONCHAIN,
                    sources=(_sha("onchain"),),
                ),
            ),
            key=lambda item: item.family.value,
        )
    )
    overlap = analyze_confluence_evidence_overlap(evidence)

    assert overlap.relations[0].attribution_per_family_0_1 == Decimal(
        "0.333333333333"
    )
    assert overlap.shared_source_evidence_identities == (shared,)
    assert overlap.production_authority is False
    assert overlap.real_capital == 0
