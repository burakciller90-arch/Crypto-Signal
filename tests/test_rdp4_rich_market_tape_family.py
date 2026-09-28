from __future__ import annotations

from decimal import Decimal

from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.microstructure import (
    AggressorSide,
    OrderBookLevel,
    build_orderbook_snapshot,
    build_public_trade_observation,
)
from crypto_signal.data.models import DataSource, Exchange, MarketType
from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.intelligence.liquidity_dynamics import (
    build_liquidity_dynamics_evidence_freeze,
)
from crypto_signal.intelligence.liquidity_structure import (
    LiquidityStructureStatus,
    build_liquidity_structure_evidence_freeze,
)
from crypto_signal.intelligence.liquidity_sweep import (
    LiquiditySweepState,
    LiquiditySweepStatus,
    build_liquidity_sweep_evidence_freeze,
)
from crypto_signal.intelligence.order_flow_microstructure import (
    OrderFlowMicrostructureLabel,
    build_order_flow_microstructure_evidence_freeze,
)
from crypto_signal.intelligence.temporal_order_flow import (
    TemporalFlowStatus,
    build_temporal_order_flow_freeze,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.intelligence_stream_family_sources import (
    build_market_tape_family_snapshots,
)


AS_OF_MS = 200_000


def _book(*, index: int, event_at_ms: int):
    bids = tuple(
        OrderBookLevel(
            price=Decimal(100 - level),
            size=Decimal(5),
        )
        for level in range(10)
    )
    asks = tuple(
        OrderBookLevel(
            price=Decimal(101 + level),
            size=Decimal(5),
        )
        for level in range(10)
    )
    return build_orderbook_snapshot(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        event_at_ms=event_at_ms,
        source_timestamp_ms=event_at_ms + 1,
        response_time_ms=event_at_ms + 2,
        ingested_at_ms=event_at_ms + 3,
        update_id=100 + index,
        sequence=200 + index,
        bids=bids,
        asks=asks,
        source=DataSource.WEBSOCKET,
        adapter_version="rdp4-rich-family-test/1",
    )


def _trade(
    *,
    index: int,
    event_at_ms: int,
    side: AggressorSide,
    size: str = "2",
    ingested_at_ms: int | None = None,
):
    return build_public_trade_observation(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        exec_id=f"rdp4-{index}",
        sequence=300 + index,
        aggressor_side=side,
        price=Decimal(100),
        size=Decimal(size),
        event_at_ms=event_at_ms,
        source_timestamp_ms=event_at_ms + 1,
        ingested_at_ms=(
            event_at_ms + 2
            if ingested_at_ms is None
            else ingested_at_ms
        ),
        is_block_trade=False,
        is_rpi_trade=False,
        source=DataSource.WEBSOCKET,
        adapter_version="rdp4-rich-family-test/1",
    )


def _seed(store: MarketTapeStore) -> None:
    for index, event_at_ms in enumerate(
        (175_000, 180_000, 185_000, 190_000, 195_000),
        start=1,
    ):
        store.append_orderbook(
            _book(index=index, event_at_ms=event_at_ms)
        )

    sides = (
        AggressorSide.BUY,
        AggressorSide.BUY,
        AggressorSide.BUY,
        AggressorSide.BUY,
        AggressorSide.SELL,
    )
    for index, (event_at_ms, side) in enumerate(
        zip(
            (190_000, 192_000, 194_000, 196_000, 198_000),
            sides,
            strict=True,
        ),
        start=1,
    ):
        store.append_trade(
            _trade(
                index=index,
                event_at_ms=event_at_ms,
                side=side,
            )
        )


def _families(path):
    snapshots = build_market_tape_family_snapshots(
        path,
        symbols=("BTCUSDT",),
        as_of_ms=AS_OF_MS,
    )
    return {
        item.family: item
        for item in snapshots
        if item.family
        in {
            ConfluenceFamily.LIQUIDITY,
            ConfluenceFamily.ORDER_FLOW,
        }
    }


def test_rich_liquidity_and_order_flow_share_existing_family_slots(
    tmp_path,
) -> None:
    path = tmp_path / "market_tape.sqlite3"
    store = MarketTapeStore(path)
    _seed(store)

    families = _families(path)
    assert set(families) == {
        ConfluenceFamily.LIQUIDITY,
        ConfluenceFamily.ORDER_FLOW,
    }

    books = store.recent_orderbooks(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        limit=180,
    )
    trades = store.recent_trades(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        limit=1200,
    )

    dynamics = build_liquidity_dynamics_evidence_freeze(
        books,
        as_of_ms=AS_OF_MS,
    )
    structure = build_liquidity_structure_evidence_freeze(
        books,
        as_of_ms=AS_OF_MS,
    )
    sweep = build_liquidity_sweep_evidence_freeze(
        books,
        trades,
        as_of_ms=AS_OF_MS,
    )
    assert structure.analysis.status is LiquidityStructureStatus.MEASURED
    assert sweep.analysis.status is LiquiditySweepStatus.MEASURED
    assert sweep.analysis.sweep_state is LiquiditySweepState.NONE

    liquidity = families[ConfluenceFamily.LIQUIDITY]
    assert {
        dynamics.freeze_identity,
        dynamics.analysis.evidence_identity,
        structure.freeze_identity,
        structure.analysis.evidence_identity,
        sweep.freeze_identity,
        sweep.analysis.evidence_identity,
    }.issubset(set(liquidity.evidence_identities))
    assert {
        "liquidity_structure",
        "liquidity_sweep",
        "order_book",
        "public_trades",
    }.issubset(set(liquidity.evidence_domains))
    assert liquidity.source_event_identity == canonical_sha256(
        {
            "as_of_ms": AS_OF_MS,
            "dynamics_freeze_identity": dynamics.freeze_identity,
            "structure_freeze_identity": structure.freeze_identity,
            "sweep_freeze_identity": sweep.freeze_identity,
            "symbol": "BTCUSDT",
            "version": "rdp4-rich-liquidity-family-v1/1",
        }
    )
    liquidity_components = {
        item.name: item.value for item in liquidity.state_components
    }
    assert liquidity_components["structure_status"] == "measured"
    assert liquidity_components["sweep_status"] == "measured"
    assert liquidity_components["sweep_state"] == "none"
    assert "persistent_pool_candidate_count" in liquidity_components
    assert "spoofing_candidate_count" in liquidity_components
    assert "hidden_liquidity_candidate_count" in liquidity_components
    assert liquidity.direction is None

    micro = build_order_flow_microstructure_evidence_freeze(
        books,
        trades,
        as_of_ms=AS_OF_MS,
    )
    temporal = build_temporal_order_flow_freeze(
        trades,
        as_of_ms=AS_OF_MS,
    )
    assert temporal.analysis.status is TemporalFlowStatus.MEASURED
    assert temporal.analysis.metrics is not None
    assert temporal.analysis.metrics.delta_notional > 0
    assert micro.analysis.label is OrderFlowMicrostructureLabel.MIXED

    order_flow = families[ConfluenceFamily.ORDER_FLOW]
    assert {
        micro.freeze_identity,
        micro.analysis.evidence_identity,
        temporal.freeze_identity,
        temporal.analysis.evidence_identity,
    }.issubset(set(order_flow.evidence_identities))
    assert {
        "temporal_order_flow",
        "window_local_cvd",
        "public_trades",
    }.issubset(set(order_flow.evidence_domains))
    assert order_flow.source_event_identity == canonical_sha256(
        {
            "as_of_ms": AS_OF_MS,
            "microstructure_freeze_identity": micro.freeze_identity,
            "symbol": "BTCUSDT",
            "temporal_flow_freeze_identity": temporal.freeze_identity,
            "version": "rdp4-rich-order-flow-family-v1/1",
        }
    )
    order_flow_components = {
        item.name: item.value for item in order_flow.state_components
    }
    assert order_flow_components["temporal_status"] == "measured"
    assert order_flow_components["temporal_quality"] == "good"
    assert Decimal(order_flow_components["delta_notional"]) > 0
    assert "cvd_window_end_notional" in order_flow_components
    assert "trade_velocity_per_second" in order_flow_components
    assert order_flow.direction is None
    assert order_flow_components["label"] == "mixed"


def test_future_and_late_market_tape_cannot_rewrite_rich_family_pit(
    tmp_path,
) -> None:
    path = tmp_path / "market_tape.sqlite3"
    store = MarketTapeStore(path)
    _seed(store)
    baseline = _families(path)

    store.append_orderbook(
        _book(index=99, event_at_ms=AS_OF_MS + 1_000)
    )
    store.append_trade(
        _trade(
            index=99,
            event_at_ms=AS_OF_MS + 1_000,
            side=AggressorSide.BUY,
            size="100",
        )
    )
    store.append_trade(
        _trade(
            index=100,
            event_at_ms=197_000,
            side=AggressorSide.SELL,
            size="100",
            ingested_at_ms=AS_OF_MS + 1_000,
        )
    )

    replay = _families(path)
    assert replay == baseline


def test_rdp4_family_wiring_uses_candidate_semantics_not_actor_claims() -> None:
    source = (
        __import__(
            "crypto_signal.product.intelligence_stream_family_sources",
            fromlist=["__file__"],
        ).__file__
    )
    assert source is not None
    text = open(source, encoding="utf-8").read().lower()
    assert "institutional actor confirmed" not in text
    assert "market maker manipulation proven" not in text
    assert "stop hunt proven" not in text
    assert "spoofing confirmed" not in text
