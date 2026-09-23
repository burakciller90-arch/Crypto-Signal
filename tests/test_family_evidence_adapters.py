from __future__ import annotations

from decimal import Decimal

import pytest
from test_derivatives_crowding_engine import _combined as derivatives_combined
from test_immutable_forecast_stream import (
    HORIZON,
    _event_context,
    _signal,
)
from test_immutable_ledger import build_bundle, candles
from test_large_transfer_clusters import _transfer
from test_liquidity_sweep_engine import (
    _book as liquidity_book,
    _config as liquidity_config,
    _structure_config,
    _trade as liquidity_trade,
)
from test_order_flow_microstructure_engine import (
    _book as flow_book,
    _config as flow_config,
    _trade as flow_trade,
)
from test_wallet_cohort_registry import _admission, _forward

from crypto_signal.data.exchange_flows import build_exchange_flow_observation
from crypto_signal.data.microstructure import AggressorSide
from crypto_signal.data.models import DataSource
from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.family_evidence_adapters import (
    FamilyEvidenceAdapterResult,
    ProofEvidenceFragment,
    adapt_derivatives_evidence,
    adapt_geometry_bundle,
    adapt_liquidity_evidence,
    adapt_onchain_evidence,
    adapt_order_flow_evidence,
    build_event_context_fragment,
    compose_decision_proof_slices,
)
from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamily,
    build_confluence_family_evidence,
)
from crypto_signal.intelligence.exchange_flow import (
    build_exchange_flow_evidence_freeze,
)
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
from crypto_signal.intelligence.order_flow_microstructure import (
    OrderFlowMicrostructureLabel,
    build_order_flow_microstructure_evidence_freeze,
)
from crypto_signal.intelligence.temporal_order_flow import (
    build_temporal_order_flow_freeze,
)
from crypto_signal.intelligence.wallet_cohorts import (
    build_wallet_cohort_evidence_freeze,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.decision_proof import (
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
    ProofEvidenceVerdict,
)
from crypto_signal.unified_decision_runtime import issue_unified_decision

AS_OF = 1_000_000
REGIME = "trend_up"
TIMEFRAME = "4h"


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _liquidity_sources():
    shift = AS_OF - 12_050
    sizes = ("10", "8", "5", "2", "1")
    books = tuple(
        liquidity_book(
            event_at_ms=8_000 + shift + index * 1_000,
            sequence=index + 1,
            bid_size=size,
        )
        for index, size in enumerate(sizes)
    )
    trades = (
        liquidity_trade(
            event_at_ms=10_300 + shift,
            sequence=1,
            side=AggressorSide.SELL,
            price="100",
            size="4",
        ),
        liquidity_trade(
            event_at_ms=10_500 + shift,
            sequence=2,
            side=AggressorSide.SELL,
            price="99.70",
            size="4",
        ),
        liquidity_trade(
            event_at_ms=10_700 + shift,
            sequence=3,
            side=AggressorSide.SELL,
            price="99.40",
            size="4",
        ),
        liquidity_trade(
            event_at_ms=10_900 + shift,
            sequence=4,
            side=AggressorSide.SELL,
            price="99.20",
            size="3",
        ),
        liquidity_trade(
            event_at_ms=11_200 + shift,
            sequence=5,
            side=AggressorSide.BUY,
            price="100.05",
            size="1",
        ),
    )
    structure = build_liquidity_structure_evidence_freeze(
        books,
        as_of_ms=AS_OF,
        config=_structure_config(),
    )
    sweep = build_liquidity_sweep_evidence_freeze(
        books,
        trades,
        as_of_ms=AS_OF,
        config=liquidity_config(),
    )
    derivatives = derivatives_combined("long")
    liquidation = derivatives.liquidation_freeze
    return structure, sweep, liquidation


def _order_flow_sources():
    book = flow_book(event_at_ms=AS_OF - 500)
    trades = (
        flow_trade(
            "b1",
            event_at_ms=AS_OF - 400,
            side=AggressorSide.BUY,
        ),
        flow_trade(
            "b2",
            event_at_ms=AS_OF - 350,
            side=AggressorSide.BUY,
        ),
        flow_trade(
            "b3",
            event_at_ms=AS_OF - 300,
            side=AggressorSide.BUY,
        ),
        flow_trade(
            "b4",
            event_at_ms=AS_OF - 250,
            side=AggressorSide.BUY,
        ),
        flow_trade(
            "s1",
            event_at_ms=AS_OF - 200,
            side=AggressorSide.SELL,
            size=Decimal("0.2"),
        ),
    )
    micro = build_order_flow_microstructure_evidence_freeze(
        (book,),
        trades,
        as_of_ms=AS_OF,
        config=flow_config(),
    )
    temporal = build_temporal_order_flow_freeze(trades, as_of_ms=AS_OF)
    return micro, temporal


def _exchange_flow_freeze():
    values = (
        ("10", "30"),
        ("12", "25"),
        ("14", "20"),
        ("16", "15"),
        ("30", "10"),
    )
    observations = []
    for index, (inflow, outflow) in enumerate(values):
        end_ms = AS_OF - (5 - index) * 60_000
        observations.append(
            build_exchange_flow_observation(
                asset="BTC",
                exchange_scope="all_exchanges",
                window_start_ms=end_ms - 60_000,
                window_end_ms=end_ms,
                inflow_amount=Decimal(inflow),
                outflow_amount=Decimal(outflow),
                source_provider="adapter-test-provider",
                attribution_method="provider-labeled-clusters/v1",
                source=DataSource.AGGREGATED,
                source_timestamp_ms=end_ms + 10,
                ingested_at_ms=end_ms + 20,
                adapter_version="family-adapter-test/1",
            )
        )
    return build_exchange_flow_evidence_freeze(
        tuple(observations),
        as_of_ms=AS_OF,
    )


def _onchain_supplements():
    first = _admission("cluster-a", admitted_at_ms=100_000)
    second = _admission("cluster-b", admitted_at_ms=200_000)
    wallet = build_wallet_cohort_evidence_freeze(
        (first, second),
        (
            _forward(
                first,
                start_ms=100_000,
                end_ms=800_000,
                value="0.10",
            ),
            _forward(
                second,
                start_ms=200_000,
                end_ms=850_000,
                value="-0.05",
            ),
        ),
        as_of_ms=AS_OF,
    )
    transfers = build_large_transfer_cluster_evidence_freeze(
        tuple(
            _transfer(
                index,
                source_cluster="cluster-a",
                destination_cluster="exchange-x",
                amount=str(100 - index * 5),
                event_at_ms=900_000 + index * 1_000,
            )
            for index in range(1, 6)
        ),
        as_of_ms=AS_OF,
    )
    return wallet, transfers


def _synthetic_geometry_result() -> FamilyEvidenceAdapterResult:
    identity = _sha("geometry-family-source")
    family = build_confluence_family_evidence(
        family=ConfluenceFamily.GEOMETRY,
        asset="BTCUSDT",
        timeframe=TIMEFRAME,
        regime=REGIME,
        as_of_ms=AS_OF,
        state=MetaEvidenceState.OBSERVED,
        direction=MetaDirection.BULLISH,
        directional_strength_0_1=Decimal("0.80"),
        evidence_quality_0_1=Decimal("0.90"),
        freshness_0_1=Decimal("0.95"),
        market_available_at_ms=AS_OF - 20,
        observed_at_ms=AS_OF - 10,
        source_engine_ids=("geometry-test",),
        source_evidence_identities=(identity,),
    )
    return FamilyEvidenceAdapterResult(
        family,
        (
            ProofEvidenceFragment(
                domain=ProofEvidenceDomain.FROZEN_CHART,
                evidence_identities=(identity,),
                market_available_at_ms=AS_OF - 20,
                observed_at_ms=AS_OF - 10,
                freshness_0_1=Decimal("0.95"),
                source_quality="geometry-test",
                verdict=ProofEvidenceVerdict.SUPPORT,
                summary_codes=("geometry_test_exact",),
            ),
            ProofEvidenceFragment(
                domain=ProofEvidenceDomain.CONSUMED_CANDLES,
                evidence_identities=(_sha("geometry-candles"),),
                market_available_at_ms=AS_OF - 20,
                observed_at_ms=AS_OF - 10,
                freshness_0_1=Decimal("0.95"),
                source_quality="geometry-test",
                verdict=ProofEvidenceVerdict.NEUTRAL,
                summary_codes=("geometry_candles_test_exact",),
            ),
        ),
    )


def test_geometry_adapter_uses_exact_immutable_decision_bundle() -> None:
    bundle = build_bundle(candles())
    result = adapt_geometry_bundle(
        bundle,
        regime="test_regime",
        evidence_quality_0_1=Decimal("0.90"),
        freshness_0_1=Decimal("0.95"),
    )

    assert result.family_evidence.family is ConfluenceFamily.GEOMETRY
    assert result.family_evidence.source_evidence_identities == (
        bundle.bundle_identity,
    )
    assert result.family_evidence.direction in {
        MetaDirection.BULLISH,
        MetaDirection.BEARISH,
    }
    assert {item.domain for item in result.proof_fragments} == {
        ProofEvidenceDomain.FROZEN_CHART,
        ProofEvidenceDomain.CONSUMED_CANDLES,
    }
    assert all(
        bundle.bundle_identity in item.evidence_identities
        for item in result.proof_fragments
    )


def test_liquidity_adapter_preserves_context_without_inventing_direction() -> None:
    structure, sweep, liquidation = _liquidity_sources()
    result = adapt_liquidity_evidence(
        structure,
        sweep,
        timeframe=TIMEFRAME,
        regime=REGIME,
        liquidation=liquidation,
    )

    assert result.family_evidence.family is ConfluenceFamily.LIQUIDITY
    assert result.family_evidence.state is MetaEvidenceState.ABSTAIN
    assert result.family_evidence.direction is None
    assert result.family_evidence.directional_strength_0_1 == Decimal(0)
    assert {
        ProofEvidenceDomain.ORDER_BOOK,
        ProofEvidenceDomain.LIQUIDITY_MAP,
        ProofEvidenceDomain.LIQUIDATION_MAP,
    }.issubset({item.domain for item in result.proof_fragments})
    assert any(
        "sweep_candidate_not_trade_direction" in item.summary_codes
        for item in result.proof_fragments
    )


def test_order_flow_adapter_carries_only_resolved_book_plus_taker_direction() -> None:
    micro, temporal = _order_flow_sources()
    assert micro.analysis.label is OrderFlowMicrostructureLabel.BUY_PRESSURE

    result = adapt_order_flow_evidence(
        micro,
        temporal,
        timeframe=TIMEFRAME,
        regime=REGIME,
        candidate_direction=MetaDirection.BULLISH,
    )

    assert result.family_evidence.family is ConfluenceFamily.ORDER_FLOW
    assert result.family_evidence.state is MetaEvidenceState.OBSERVED
    assert result.family_evidence.direction is MetaDirection.BULLISH
    assert Decimal(0) < result.family_evidence.directional_strength_0_1 <= Decimal(1)
    orderbook = next(
        item
        for item in result.proof_fragments
        if item.domain is ProofEvidenceDomain.ORDER_BOOK
    )
    assert orderbook.verdict is ProofEvidenceVerdict.SUPPORT
    assert "direction_only_from_resolved_book_plus_taker_state" in (
        orderbook.summary_codes
    )


def test_derivatives_adapter_is_measured_context_not_long_short_vote() -> None:
    result = adapt_derivatives_evidence(
        derivatives_combined("long"),
        timeframe=TIMEFRAME,
        regime=REGIME,
    )

    assert result.family_evidence.family is ConfluenceFamily.DERIVATIVES
    assert result.family_evidence.state is MetaEvidenceState.ABSTAIN
    assert result.family_evidence.direction is None
    assert result.family_evidence.directional_strength_0_1 == Decimal(0)
    assert result.proof_fragments[0].domain is ProofEvidenceDomain.DERIVATIVES
    assert result.proof_fragments[0].verdict is ProofEvidenceVerdict.NEUTRAL
    assert "crowding_context_not_trade_direction" in (
        result.proof_fragments[0].summary_codes
    )


def test_onchain_adapter_keeps_flow_wallet_and_large_transfer_context_neutral() -> None:
    wallet, transfers = _onchain_supplements()
    result = adapt_onchain_evidence(
        _exchange_flow_freeze(),
        market_symbol="BTCUSDT",
        timeframe=TIMEFRAME,
        regime=REGIME,
        wallet_cohort=wallet,
        large_transfers=transfers,
    )

    assert result.family_evidence.family is ConfluenceFamily.ONCHAIN
    assert result.family_evidence.state is MetaEvidenceState.ABSTAIN
    assert result.family_evidence.direction is None
    assert result.proof_fragments[0].domain is ProofEvidenceDomain.ONCHAIN
    assert result.proof_fragments[0].verdict is ProofEvidenceVerdict.NEUTRAL
    assert len(result.proof_fragments[0].evidence_identities) == 3
    assert "exchange_flow_context_not_price_direction" in (
        result.proof_fragments[0].summary_codes
    )


def test_family_adapters_compose_into_exact_unified_runtime_preflight(
    tmp_path,
) -> None:
    geometry = _synthetic_geometry_result()
    structure, sweep, liquidation = _liquidity_sources()
    liquidity = adapt_liquidity_evidence(
        structure,
        sweep,
        timeframe=TIMEFRAME,
        regime=REGIME,
        liquidation=liquidation,
    )
    micro, temporal = _order_flow_sources()
    order_flow = adapt_order_flow_evidence(
        micro,
        temporal,
        timeframe=TIMEFRAME,
        regime=REGIME,
        candidate_direction=MetaDirection.BULLISH,
    )
    derivatives = adapt_derivatives_evidence(
        derivatives_combined("long"),
        timeframe=TIMEFRAME,
        regime=REGIME,
    )
    wallet, transfers = _onchain_supplements()
    onchain = adapt_onchain_evidence(
        _exchange_flow_freeze(),
        market_symbol="BTCUSDT",
        timeframe=TIMEFRAME,
        regime=REGIME,
        wallet_cohort=wallet,
        large_transfers=transfers,
    )
    event = _event_context(as_of_ms=AS_OF)
    results = (geometry, liquidity, order_flow, derivatives, onchain)
    slices = compose_decision_proof_slices(
        results,
        extra_fragments=(build_event_context_fragment(event),),
    )

    assert len(slices) == len(ProofEvidenceDomain) - 1
    by_domain = {item.domain: item for item in slices}
    assert by_domain[ProofEvidenceDomain.ORDER_BOOK].availability is (
        ProofEvidenceAvailability.AVAILABLE
    )
    assert set(by_domain[ProofEvidenceDomain.ORDER_BOOK].evidence_identities) == {
        structure.freeze_identity,
        micro.freeze_identity,
    }
    assert by_domain[ProofEvidenceDomain.PROBABILITY_CALIBRATION].availability is (
        ProofEvidenceAvailability.INSUFFICIENT
    )
    assert by_domain[ProofEvidenceDomain.EVENT_CONTEXT].evidence_identities[0]

    issuance = issue_unified_decision(
        signal=_signal(as_of_ms=AS_OF),
        base_asset="BTC",
        regime=REGIME,
        family_evidence=tuple(
            result.family_evidence
            for result in sorted(
                results,
                key=lambda item: item.family_evidence.family.value,
            )
        ),
        event_context=event,
        preflight_proof_slices=slices,
        issued_at_ms=AS_OF + 100,
        horizon_bars=HORIZON,
        target_label="target_1",
        ledger=ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3"),
    )

    assert issuance.proof.evidence_summary.available_count >= 9
    assert issuance.forecast.production_authority is False
    assert issuance.proof.real_capital == 0


def test_adapter_context_mismatch_fails_closed() -> None:
    micro, temporal = _order_flow_sources()
    with pytest.raises(ValueError, match="context mismatch"):
        adapt_order_flow_evidence(
            micro,
            build_temporal_order_flow_freeze(
                temporal.trades,
                as_of_ms=AS_OF - 1,
            ),
            timeframe=TIMEFRAME,
            regime=REGIME,
            candidate_direction=MetaDirection.BULLISH,
        )
