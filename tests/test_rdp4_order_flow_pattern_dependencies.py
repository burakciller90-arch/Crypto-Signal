from __future__ import annotations

from decimal import Decimal

import pytest

from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.microstructure import (
    AggressorSide,
    OrderBookLevel,
    build_orderbook_snapshot,
    build_public_trade_observation,
)
from crypto_signal.data.models import (
    Candle,
    DataSource,
    Exchange,
    MarketType,
)
from crypto_signal.data.store import CandleStore
from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.intelligence.liquidity_structure import (
    build_liquidity_structure_evidence_freeze,
)
from crypto_signal.intelligence.order_flow_microstructure import (
    build_order_flow_microstructure_evidence_freeze,
)
from crypto_signal.intelligence.order_flow_patterns import (
    PatternStatus,
    build_absorption_freeze,
    build_price_cvd_divergence_freeze,
)
from crypto_signal.intelligence.temporal_order_flow import (
    TemporalFlowStatus,
    build_temporal_order_flow_freeze,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.intelligence_stream_family_sources import (
    build_market_tape_family_snapshots,
)

AS_OF_MS = 2_000_000


def _book(*, index: int, event_at_ms: int):
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
        bids=tuple(
            OrderBookLevel(
                price=Decimal(100 - level),
                size=Decimal(5),
            )
            for level in range(10)
        ),
        asks=tuple(
            OrderBookLevel(
                price=Decimal(101 + level),
                size=Decimal(5),
            )
            for level in range(10)
        ),
        source=DataSource.WEBSOCKET,
        adapter_version="rdp4-pattern-family-test/1",
    )


def _trade(
    *,
    index: int,
    event_at_ms: int,
    side: AggressorSide,
):
    return build_public_trade_observation(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        exec_id=f"rdp4-pattern-{index}",
        sequence=300 + index,
        aggressor_side=side,
        price=Decimal(100),
        size=Decimal(2),
        event_at_ms=event_at_ms,
        source_timestamp_ms=event_at_ms + 1,
        ingested_at_ms=event_at_ms + 2,
        is_block_trade=False,
        is_rpi_trade=False,
        source=DataSource.WEBSOCKET,
        adapter_version="rdp4-pattern-family-test/1",
    )


def _candle() -> Candle:
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=900_000,
        close_time_ms=1_799_999,
        open=Decimal(100),
        high=Decimal(102),
        low=Decimal(99),
        close=Decimal(101),
        volume=Decimal(10),
        quote_volume=Decimal(1000),
        trade_count=None,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=1_800_000,
        ingested_at_ms=1_800_001,
        adapter_version="rdp4-pattern-family-test/1",
    )


def _seed_market_tape(store: MarketTapeStore) -> None:
    for index, event_at_ms in enumerate(
        (1_975_000, 1_980_000, 1_985_000, 1_990_000, 1_995_000),
        start=1,
    ):
        store.append_orderbook(
            _book(index=index, event_at_ms=event_at_ms)
        )
    for index, (event_at_ms, side) in enumerate(
        zip(
            (
                1_990_000,
                1_992_000,
                1_994_000,
                1_996_000,
                1_998_000,
            ),
            (
                AggressorSide.BUY,
                AggressorSide.BUY,
                AggressorSide.BUY,
                AggressorSide.BUY,
                AggressorSide.SELL,
            ),
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


def _order_flow_family(market_path, candle_path):
    snapshots = build_market_tape_family_snapshots(
        market_path,
        symbols=("BTCUSDT",),
        as_of_ms=AS_OF_MS,
        candle_cache_path=candle_path,
    )
    matches = tuple(
        item
        for item in snapshots
        if item.family is ConfluenceFamily.ORDER_FLOW
    )
    assert len(matches) == 1
    return matches[0]


def test_absorption_and_divergence_are_dependency_proofs_not_new_families(
    tmp_path,
) -> None:
    market_path = tmp_path / "market.sqlite3"
    candle_path = tmp_path / "candles.sqlite3"
    market_store = MarketTapeStore(market_path)
    candle_store = CandleStore(candle_path)
    _seed_market_tape(market_store)
    candle_store.upsert(_candle())

    family = _order_flow_family(market_path, candle_path)
    all_families = build_market_tape_family_snapshots(
        market_path,
        symbols=("BTCUSDT",),
        as_of_ms=AS_OF_MS,
        candle_cache_path=candle_path,
    )
    assert sum(
        item.family is ConfluenceFamily.ORDER_FLOW
        for item in all_families
    ) == 1

    books = market_store.recent_orderbooks(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        limit=180,
    )
    trades = market_store.recent_trades(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        limit=1200,
    )
    micro = build_order_flow_microstructure_evidence_freeze(
        books,
        trades,
        as_of_ms=AS_OF_MS,
    )
    temporal = build_temporal_order_flow_freeze(
        trades,
        as_of_ms=AS_OF_MS,
    )
    structure = build_liquidity_structure_evidence_freeze(
        books,
        as_of_ms=AS_OF_MS,
    )
    absorption = build_absorption_freeze(
        temporal,
        structure,
        as_of_ms=AS_OF_MS,
    )
    divergence = build_price_cvd_divergence_freeze(
        candle_store.list_candles_read_only(
            exchange=Exchange.BYBIT,
            market_type=MarketType.SPOT,
            symbol="BTCUSDT",
            timeframe="15m",
        ),
        temporal,
        as_of_ms=AS_OF_MS,
    )

    assert temporal.analysis.status is TemporalFlowStatus.MEASURED
    assert absorption.analysis.status is PatternStatus.MEASURED
    assert divergence.analysis.status is PatternStatus.UNRESOLVED
    assert "insufficient_closed_candle_coverage" in (
        divergence.analysis.uncertainty_flags
    )
    assert divergence.analysis.consumed_candle_count == 0

    assert {
        micro.freeze_identity,
        temporal.freeze_identity,
        structure.freeze_identity,
        absorption.freeze_identity,
        absorption.analysis.evidence_identity,
        divergence.freeze_identity,
        divergence.analysis.evidence_identity,
    }.issubset(set(family.evidence_identities))
    assert {
        "absorption",
        "candle_15m",
        "price_cvd_divergence",
        "temporal_order_flow",
        "window_local_cvd",
    }.issubset(set(family.evidence_domains))

    components = {
        item.name: item.value for item in family.state_components
    }
    assert components["absorption_status"] == "measured"
    assert "absorption_candidate_count" in components
    assert components["price_cvd_divergence_status"] == "unresolved"
    assert (
        components["price_cvd_divergence_consumed_candle_count"]
        == "0"
    )
    assert components["price_cvd_divergence_timeframe"] == "15m"
    assert family.source_event_identity == canonical_sha256(
        {
            "absorption_freeze_identity": absorption.freeze_identity,
            "as_of_ms": AS_OF_MS,
            "microstructure_freeze_identity": micro.freeze_identity,
            "price_cvd_divergence_freeze_identity": (
                divergence.freeze_identity
            ),
            "symbol": "BTCUSDT",
            "temporal_flow_freeze_identity": temporal.freeze_identity,
            "version": "rdp4-rich-order-flow-family-v2/1",
        }
    )


def test_pattern_context_cannot_invent_order_flow_direction(tmp_path) -> None:
    market_path = tmp_path / "market.sqlite3"
    candle_path = tmp_path / "candles.sqlite3"
    market_store = MarketTapeStore(market_path)
    candle_store = CandleStore(candle_path)
    _seed_market_tape(market_store)
    candle_store.upsert(_candle())

    family = _order_flow_family(market_path, candle_path)
    components = {
        item.name: item.value for item in family.state_components
    }
    assert components["price_cvd_divergence_status"] == "unresolved"
    assert family.direction is None


def test_missing_candle_cache_fails_without_initializing_a_new_database(
    tmp_path,
) -> None:
    market_path = tmp_path / "market.sqlite3"
    missing = tmp_path / "missing-candles.sqlite3"
    market_store = MarketTapeStore(market_path)
    _seed_market_tape(market_store)

    assert not missing.exists()
    with pytest.raises(FileNotFoundError):
        _order_flow_family(market_path, missing)
    assert not missing.exists()


def test_live_clock_passes_canonical_candle_cache_to_family_projection() -> None:
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "ops"
        / "run_live_evidence_clock.py"
    ).read_text(encoding="utf-8")

    assert "candle_cache_path=candle_cache_path" in source
    assert "REAL_CAPITAL=0" in source
