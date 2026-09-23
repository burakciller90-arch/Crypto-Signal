from __future__ import annotations

from decimal import Decimal

from test_derivatives_crowding_engine import AS_OF as DERIV_AS_OF
from test_derivatives_crowding_engine import _combined
from test_large_transfer_clusters import AS_OF as TRANSFER_AS_OF
from test_large_transfer_clusters import _transfer
from test_liquidation_heatmap_engine import AS_OF as LIQUIDATION_AS_OF
from test_liquidation_heatmap_engine import _config as liquidation_config
from test_liquidation_heatmap_engine import _coverage, _event, _mark
from test_liquidity_structure_engine import _config as structure_config
from test_liquidity_structure_engine import _persistent_history
from test_liquidity_sweep_engine import _bid_sweep_trades, _depleting_books
from test_liquidity_sweep_engine import _config as sweep_config
from test_order_flow_patterns import (
    _bullish_divergence_candles,
    _bullish_divergence_trades,
    _flow_config,
)
from test_wallet_cohort_registry import _admission, _forward

from crypto_signal.data.large_transfers import TransferClusterRole
from crypto_signal.data.liquidations import LiquidatedPositionSide
from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.intelligence.family_proof_adapters import adapt_accepted_m2_m5
from crypto_signal.intelligence.large_transfer_clusters import (
    build_large_transfer_cluster_evidence_freeze,
)
from crypto_signal.intelligence.liquidation_heatmap import (
    build_liquidation_heatmap_evidence_freeze,
)
from crypto_signal.intelligence.liquidity_structure import (
    build_liquidity_structure_evidence_freeze,
)
from crypto_signal.intelligence.liquidity_sweep import (
    build_liquidity_sweep_evidence_freeze,
)
from crypto_signal.intelligence.meta_intelligence import (
    MetaDirection,
    MetaEvidenceState,
)
from crypto_signal.intelligence.order_flow_patterns import (
    DivergenceConfig,
    build_price_cvd_divergence_freeze,
)
from crypto_signal.intelligence.rich_family_proof_adapters import (
    enrich_accepted_m2_m5,
)
from crypto_signal.intelligence.temporal_order_flow import (
    build_temporal_order_flow_freeze,
)
from crypto_signal.intelligence.wallet_cohorts import (
    build_wallet_cohort_evidence_freeze,
)
from crypto_signal.product.decision_proof import (
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
)


def _base(as_of_ms: int):
    return adapt_accepted_m2_m5(
        symbol="BTCUSDT",
        base_asset="BTC",
        timeframe="4h",
        regime="trend_up",
        as_of_ms=as_of_ms,
    )


def _family(bundle, family):
    return next(item for item in bundle.families if item.family is family)


def _proof(bundle, domain):
    return next(item for item in bundle.proof_slices if item.domain is domain)


def test_persistent_liquidity_and_sweep_enrich_m2_without_direction() -> None:
    as_of = 12_050
    structure = build_liquidity_structure_evidence_freeze(
        _persistent_history(),
        as_of_ms=as_of,
        config=structure_config(),
    )
    sweep = build_liquidity_sweep_evidence_freeze(
        _depleting_books(),
        _bid_sweep_trades(),
        as_of_ms=as_of,
        config=sweep_config(),
    )
    result = enrich_accepted_m2_m5(
        base=_base(as_of),
        symbol="BTCUSDT",
        base_asset="BTC",
        timeframe="4h",
        regime="trend_up",
        as_of_ms=as_of,
        liquidity_structure=structure,
        liquidity_sweep=sweep,
    )

    family = _family(result, ConfluenceFamily.LIQUIDITY)
    assert family.state is MetaEvidenceState.OBSERVED
    assert family.direction is MetaDirection.NEUTRAL
    assert family.directional_strength_0_1 == 0
    assert set(family.source_evidence_identities) == {
        structure.freeze_identity,
        sweep.freeze_identity,
    }

    proof = _proof(result, ProofEvidenceDomain.LIQUIDITY_MAP)
    assert proof.availability is ProofEvidenceAvailability.AVAILABLE
    assert structure.freeze_identity in proof.evidence_identities
    assert sweep.freeze_identity in proof.evidence_identities
    assert "accepted_family_evidence_missing_or_stale" not in family.uncertainty_flags
    assert "liquidity_not_measured_or_stale" not in proof.summary_codes


def test_observed_liquidation_heatmap_is_real_proof_but_not_trade_direction() -> None:
    events = (
        _event(
            suffix=1,
            side=LiquidatedPositionSide.LONG,
            price="99.80",
            size="5",
        ),
        _event(
            suffix=2,
            side=LiquidatedPositionSide.SHORT,
            price="101.00",
            size="2",
        ),
    )
    freeze = build_liquidation_heatmap_evidence_freeze(
        events,
        coverage=_coverage(),
        mark_reference=_mark(),
        as_of_ms=LIQUIDATION_AS_OF,
        config=liquidation_config(),
    )
    result = enrich_accepted_m2_m5(
        base=_base(LIQUIDATION_AS_OF),
        symbol="BTCUSDT",
        base_asset="BTC",
        timeframe="4h",
        regime="trend_up",
        as_of_ms=LIQUIDATION_AS_OF,
        liquidation=freeze,
    )

    family = _family(result, ConfluenceFamily.LIQUIDITY)
    proof = _proof(result, ProofEvidenceDomain.LIQUIDATION_MAP)
    assert family.direction is MetaDirection.NEUTRAL
    assert family.directional_strength_0_1 == 0
    assert freeze.freeze_identity in family.source_evidence_identities
    assert proof.availability is ProofEvidenceAvailability.AVAILABLE
    assert proof.evidence_identities == (freeze.freeze_identity,)
    assert "estimated_leverage_concentration_not_claimed" in proof.summary_codes
    assert "retail_stop_locations_not_claimed" in proof.summary_codes


def test_bullish_divergence_remains_context_without_base_directional_consensus() -> None:
    as_of = 300_000
    flow = build_temporal_order_flow_freeze(
        _bullish_divergence_trades(),
        as_of_ms=as_of,
        config=_flow_config(),
    )
    divergence = build_price_cvd_divergence_freeze(
        _bullish_divergence_candles(),
        flow,
        as_of_ms=as_of,
        config=DivergenceConfig(
            minimum_closed_candles=5,
            pivot_radius=1,
            minimum_price_change_bps=Decimal(5),
            minimum_cvd_change_notional=Decimal(0),
            max_endpoint_trade_gap_ms=10_000,
            minimum_endpoint_trade_count=1,
        ),
    )
    base = adapt_accepted_m2_m5(
        symbol="BTCUSDT",
        base_asset="BTC",
        timeframe="4h",
        regime="trend_up",
        as_of_ms=as_of,
        temporal_flow=flow,
    )
    before = _family(base, ConfluenceFamily.ORDER_FLOW)
    assert before.direction is MetaDirection.NEUTRAL

    result = enrich_accepted_m2_m5(
        base=base,
        symbol="BTCUSDT",
        base_asset="BTC",
        timeframe="4h",
        regime="trend_up",
        as_of_ms=as_of,
        divergence=divergence,
    )
    family = _family(result, ConfluenceFamily.ORDER_FLOW)
    proof = _proof(result, ProofEvidenceDomain.ORDER_FLOW_CVD)
    assert family.direction is MetaDirection.NEUTRAL
    assert family.directional_strength_0_1 == 0
    assert divergence.freeze_identity in family.source_evidence_identities
    assert divergence.freeze_identity in proof.evidence_identities
    assert "price_cvd_divergence_candidate_present" in proof.summary_codes


def test_derivatives_crowding_is_exposed_as_neutral_context() -> None:
    crowding = _combined("long")
    result = enrich_accepted_m2_m5(
        base=_base(DERIV_AS_OF),
        symbol="BTCUSDT",
        base_asset="BTC",
        timeframe="4h",
        regime="trend_up",
        as_of_ms=DERIV_AS_OF,
        derivatives_crowding=crowding,
    )

    family = _family(result, ConfluenceFamily.DERIVATIVES)
    proof = _proof(result, ProofEvidenceDomain.DERIVATIVES)
    assert family.state is MetaEvidenceState.OBSERVED
    assert family.direction is MetaDirection.NEUTRAL
    assert family.directional_strength_0_1 == 0
    assert crowding.freeze_identity in family.source_evidence_identities
    assert crowding.freeze_identity in proof.evidence_identities
    assert "crowding_context_not_directional_rule" in proof.summary_codes


def test_wallet_cohort_and_transfer_cluster_enrich_onchain_without_actor_intent() -> None:
    as_of = TRANSFER_AS_OF
    a = _admission("cluster-a", admitted_at_ms=1_000)
    b = _admission("cluster-b", admitted_at_ms=2_000)
    wallet = build_wallet_cohort_evidence_freeze(
        (a, b),
        (
            _forward(a, start_ms=1_000, end_ms=900_000, value="0.20"),
            _forward(b, start_ms=2_000, end_ms=900_100, value="-0.10"),
        ),
        as_of_ms=as_of,
    )
    transfers = build_large_transfer_cluster_evidence_freeze(
        (
            _transfer(
                1,
                source_cluster="cluster-a",
                destination_cluster="exchange-x",
                amount="100",
                destination_role=TransferClusterRole.EXCHANGE,
            ),
            _transfer(
                2,
                source_cluster="cluster-a",
                destination_cluster="exchange-x",
                amount="90",
                destination_role=TransferClusterRole.EXCHANGE,
            ),
            _transfer(
                3,
                source_cluster="cluster-a",
                destination_cluster="exchange-x",
                amount="80",
                destination_role=TransferClusterRole.EXCHANGE,
            ),
            _transfer(
                4,
                source_cluster="cluster-c",
                destination_cluster="cluster-d",
                amount="10",
            ),
            _transfer(
                5,
                source_cluster="cluster-e",
                destination_cluster="cluster-f",
                amount="20",
            ),
        ),
        as_of_ms=as_of,
    )
    result = enrich_accepted_m2_m5(
        base=_base(as_of),
        symbol="BTCUSDT",
        base_asset="BTC",
        timeframe="4h",
        regime="trend_up",
        as_of_ms=as_of,
        wallet_cohorts=(wallet,),
        large_transfer_clusters=(transfers,),
    )

    family = _family(result, ConfluenceFamily.ONCHAIN)
    proof = _proof(result, ProofEvidenceDomain.ONCHAIN)
    assert family.state is MetaEvidenceState.OBSERVED
    assert family.direction is MetaDirection.NEUTRAL
    assert family.directional_strength_0_1 == 0
    assert set(family.source_evidence_identities) == {
        wallet.freeze_identity,
        transfers.freeze_identity,
    }
    assert wallet.freeze_identity in proof.evidence_identities
    assert transfers.freeze_identity in proof.evidence_identities
    assert any(code.startswith("wallet_cohort_") for code in proof.summary_codes)
    assert any(code.startswith("large_transfer_") for code in proof.summary_codes)


def test_registry_only_wallet_is_visible_proof_but_not_m6_measured_vote() -> None:
    as_of = 3_000
    wallet = build_wallet_cohort_evidence_freeze(
        (
            _admission("cluster-a", admitted_at_ms=1_000),
            _admission("cluster-b", admitted_at_ms=2_000),
        ),
        as_of_ms=as_of,
    )
    result = enrich_accepted_m2_m5(
        base=_base(as_of),
        symbol="BTCUSDT",
        base_asset="BTC",
        timeframe="4h",
        regime="trend_up",
        as_of_ms=as_of,
        wallet_cohorts=(wallet,),
    )
    family = _family(result, ConfluenceFamily.ONCHAIN)
    proof = _proof(result, ProofEvidenceDomain.ONCHAIN)
    assert family.state is MetaEvidenceState.NO_EVIDENCE
    assert proof.availability is ProofEvidenceAvailability.AVAILABLE
    assert proof.evidence_identities == (wallet.freeze_identity,)
    assert "wallet_cohort_registry_only" in proof.summary_codes
