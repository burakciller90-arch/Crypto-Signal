from __future__ import annotations

from decimal import Decimal

import pytest
from test_derivatives_dynamics_engine import history as derivatives_history
from test_exchange_flow_engine import _AS_OF as EXCHANGE_AS_OF
from test_exchange_flow_engine import _series
from test_liquidity_dynamics_engine import _config as liquidity_config
from test_liquidity_dynamics_engine import _history as liquidity_history
from test_order_flow_microstructure_engine import _book as flow_book
from test_order_flow_microstructure_engine import _config as micro_config
from test_order_flow_microstructure_engine import _trade as micro_trade
from test_temporal_order_flow import _config as temporal_config
from test_temporal_order_flow import _trades

from crypto_signal.data.microstructure import AggressorSide
from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.intelligence.derivatives_dynamics import (
    build_derivatives_dynamics_evidence_freeze,
)
from crypto_signal.intelligence.exchange_flow import build_exchange_flow_evidence_freeze
from crypto_signal.intelligence.family_proof_adapters import adapt_accepted_m2_m5
from crypto_signal.intelligence.liquidity_dynamics import (
    build_liquidity_dynamics_evidence_freeze,
)
from crypto_signal.intelligence.meta_intelligence import MetaDirection, MetaEvidenceState
from crypto_signal.intelligence.order_flow_microstructure import (
    build_order_flow_microstructure_evidence_freeze,
)
from crypto_signal.intelligence.temporal_order_flow import (
    build_temporal_order_flow_freeze,
)
from crypto_signal.product.decision_proof import (
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
)

SYMBOL = "BTCUSDT"
BASE = "BTC"
TIMEFRAME = "4h"
REGIME = "trend_up"
AS_OF = 12_100


def _adapt(as_of_ms: int = AS_OF, **kwargs):
    return adapt_accepted_m2_m5(
        symbol=SYMBOL, base_asset=BASE, timeframe=TIMEFRAME,
        regime=REGIME, as_of_ms=as_of_ms, **kwargs,
    )


def _family(bundle, family):
    return next(x for x in bundle.families if x.family is family)


def _domain(bundle, domain):
    return next(x for x in bundle.proof_slices if x.domain is domain)


def _micro():
    trades = (
        micro_trade("b1", event_at_ms=11_600, side=AggressorSide.BUY),
        micro_trade("b2", event_at_ms=11_650, side=AggressorSide.BUY),
        micro_trade("b3", event_at_ms=11_700, side=AggressorSide.BUY),
        micro_trade("b4", event_at_ms=11_750, side=AggressorSide.BUY),
        micro_trade(
            "s1", event_at_ms=11_800,
            side=AggressorSide.SELL, size=Decimal("0.2"),
        ),
    )
    return build_order_flow_microstructure_evidence_freeze(
        (flow_book(event_at_ms=11_500),),
        trades,
        as_of_ms=AS_OF,
        config=micro_config(max_book_age_ms=1_000),
    )


def _temporal():
    return build_temporal_order_flow_freeze(
        _trades(), as_of_ms=AS_OF, config=temporal_config(),
    )


def test_missing_inputs_do_not_manufacture_any_observation_or_probability():
    bundle = _adapt()
    assert len(bundle.families) == 4
    assert len(bundle.proof_slices) == 6
    assert all(item.state is MetaEvidenceState.NO_EVIDENCE for item in bundle.families)
    assert all(
        item.availability is ProofEvidenceAvailability.INSUFFICIENT
        for item in bundle.proof_slices
    )
    assert all(item.source_evidence_identities == () for item in bundle.families)
    assert bundle.production_authority is False
    assert bundle.real_capital == 0


def test_m3_direction_requires_agreement_of_book_taker_and_window_local_cvd():
    micro = _micro()
    temporal = _temporal()
    bundle = _adapt(microstructure=micro, temporal_flow=temporal)
    flow = _family(bundle, ConfluenceFamily.ORDER_FLOW)
    assert flow.state is MetaEvidenceState.OBSERVED
    assert flow.direction is MetaDirection.BULLISH
    assert Decimal(0) < flow.directional_strength_0_1 <= Decimal(1)
    assert micro.orderbook is not None
    assert set(flow.source_evidence_identities) == {
        micro.freeze_identity,
        micro.orderbook.snapshot_identity,
        temporal.freeze_identity,
    }
    assert micro.freeze_identity in _domain(
        bundle, ProofEvidenceDomain.ORDER_BOOK
    ).evidence_identities
    assert temporal.freeze_identity in _domain(
        bundle, ProofEvidenceDomain.ORDER_FLOW_CVD
    ).evidence_identities
    assert _domain(
        bundle, ProofEvidenceDomain.ORDER_FLOW_CVD
    ).verdict.value == "neutral"
    assert _domain(
        bundle, ProofEvidenceDomain.LIQUIDATION_MAP
    ).availability is ProofEvidenceAvailability.INSUFFICIENT


def test_m3_temporal_only_is_observed_neutral_not_forced_bullish():
    temporal = _temporal()
    bundle = _adapt(temporal_flow=temporal)
    flow = _family(bundle, ConfluenceFamily.ORDER_FLOW)
    assert flow.state is MetaEvidenceState.OBSERVED
    assert flow.direction is MetaDirection.NEUTRAL
    assert flow.directional_strength_0_1 == 0
    assert flow.source_evidence_identities == (temporal.freeze_identity,)
    assert _domain(
        bundle, ProofEvidenceDomain.ORDER_BOOK
    ).availability is ProofEvidenceAvailability.INSUFFICIENT


def test_liquidity_freeze_is_context_without_liquidation_or_direction():
    as_of = 10_100
    liq = build_liquidity_dynamics_evidence_freeze(
        liquidity_history(), as_of_ms=as_of, config=liquidity_config()
    )
    bundle = _adapt(as_of, liquidity=liq)
    family = _family(bundle, ConfluenceFamily.LIQUIDITY)
    assert family.state is MetaEvidenceState.OBSERVED
    assert family.direction is MetaDirection.NEUTRAL
    assert family.directional_strength_0_1 == 0
    assert liq.freeze_identity in _domain(
        bundle, ProofEvidenceDomain.LIQUIDITY_MAP
    ).evidence_identities
    assert _domain(
        bundle, ProofEvidenceDomain.LIQUIDATION_MAP
    ).availability is ProofEvidenceAvailability.INSUFFICIENT


def test_derivatives_oi_price_is_neutral_context_not_a_price_forecast():
    deriv = build_derivatives_dynamics_evidence_freeze(
        derivatives_history(), as_of_ms=3_100,
    )
    bundle = _adapt(3_100, derivatives=deriv)
    family = _family(bundle, ConfluenceFamily.DERIVATIVES)
    assert family.state is MetaEvidenceState.OBSERVED
    assert family.direction is MetaDirection.NEUTRAL
    assert family.directional_strength_0_1 == 0
    assert _domain(
        bundle, ProofEvidenceDomain.DERIVATIVES
    ).evidence_identities == (deriv.freeze_identity,)


def test_exchange_flow_is_neutral_onchain_context_not_actor_intent():
    flows = _series(
        ("10", "10", "10", "10", "100"),
        ("10", "10", "10", "10", "1"),
    )
    freeze = build_exchange_flow_evidence_freeze(flows, as_of_ms=EXCHANGE_AS_OF)
    bundle = _adapt(EXCHANGE_AS_OF, exchange_flow=freeze)
    family = _family(bundle, ConfluenceFamily.ONCHAIN)
    assert family.state is MetaEvidenceState.OBSERVED
    assert family.direction is MetaDirection.NEUTRAL
    assert family.directional_strength_0_1 == 0
    assert _domain(
        bundle, ProofEvidenceDomain.ONCHAIN
    ).evidence_identities == (freeze.freeze_identity,)


def test_future_or_wrong_context_is_rejected_before_confluence():
    with pytest.raises(ValueError, match="market/PIT context mismatch"):
        _adapt(AS_OF + 1, temporal_flow=_temporal())
    with pytest.raises(ValueError, match="onchain asset/PIT context mismatch"):
        freeze = build_exchange_flow_evidence_freeze(
            _series(("10",) * 5, ("10",) * 5),
            as_of_ms=EXCHANGE_AS_OF,
        )
        _adapt(EXCHANGE_AS_OF - 1, exchange_flow=freeze)
