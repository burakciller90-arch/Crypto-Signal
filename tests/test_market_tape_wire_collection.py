from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from crypto_signal.data.adapters.bybit_microstructure_ws import (
    BybitMicrostructureWireEvent,
    BybitSpotMicrostructureStream,
    BybitSpotOrderBookState,
    parse_bybit_public_trade_payload,
)
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.market_tape_wire_collection import persist_bybit_wire_stream
from crypto_signal.data.raw_market_tape import RawMarketTapeStore

ADAPTER_VERSION = BybitSpotMicrostructureStream.ADAPTER_VERSION


def _book_payload(
    *,
    kind: str,
    ts: int,
    cts: int,
    update_id: int,
    sequence: int,
    bids: list[list[str]],
    asks: list[list[str]],
) -> dict[str, object]:
    return {
        "topic": "orderbook.50.BTCUSDT",
        "type": kind,
        "ts": ts,
        "cts": cts,
        "data": {
            "s": "BTCUSDT",
            "b": bids,
            "a": asks,
            "u": update_id,
            "seq": sequence,
        },
    }


def _trade_payload() -> dict[str, object]:
    return {
        "topic": "publicTrade.BTCUSDT",
        "type": "snapshot",
        "ts": 2_510,
        "data": [
            {
                "T": 2_501,
                "s": "BTCUSDT",
                "S": "Buy",
                "v": "0.25",
                "p": "100.5",
                "i": "trade-1",
                "BT": False,
                "RPI": False,
                "seq": 100,
            },
            {
                "T": 2_502,
                "s": "BTCUSDT",
                "S": "Sell",
                "v": "0.10",
                "p": "100.4",
                "i": "trade-2",
                "BT": False,
                "RPI": False,
                "seq": 100,
            },
        ],
    }


async def _wire_events() -> AsyncIterator[BybitMicrostructureWireEvent]:
    state = BybitSpotOrderBookState(
        symbol="BTCUSDT",
        depth=50,
        adapter_version=ADAPTER_VERSION,
    )
    payloads = (
        _book_payload(
            kind="snapshot",
            ts=1_010,
            cts=1_009,
            update_id=10,
            sequence=20,
            bids=[["100", "2"], ["99", "3"]],
            asks=[["101", "2"], ["102", "3"]],
        ),
        _book_payload(
            kind="delta",
            ts=1_210,
            cts=1_209,
            update_id=11,
            sequence=21,
            bids=[["100", "2.5"]],
            asks=[],
        ),
        _book_payload(
            kind="delta",
            ts=1_510,
            cts=1_509,
            update_id=12,
            sequence=22,
            bids=[],
            asks=[["101", "2.5"]],
        ),
        _book_payload(
            kind="delta",
            ts=2_110,
            cts=2_109,
            update_id=13,
            sequence=23,
            bids=[["99.5", "1"]],
            asks=[],
        ),
    )

    for index, payload in enumerate(payloads):
        snapshot = state.apply_payload(
            payload,
            ingested_at_ms=1_020 + index * 300,
        )
        data = payload["data"]
        assert isinstance(data, dict)
        yield BybitMicrostructureWireEvent(
            symbol="BTCUSDT",
            channel="orderbook.50",
            event_kind=str(payload["type"]),
            source_timestamp_ms=int(payload["ts"]),
            event_at_ms=int(payload["cts"]),
            ingested_at_ms=1_020 + index * 300,
            sequence=int(data["seq"]),
            update_id=int(data["u"]),
            raw_payload=payload,
            orderbook=snapshot,
        )

    trade_payload = _trade_payload()
    trades = parse_bybit_public_trade_payload(
        trade_payload,
        expected_symbol="BTCUSDT",
        adapter_version=ADAPTER_VERSION,
        ingested_at_ms=2_520,
    )
    yield BybitMicrostructureWireEvent(
        symbol="BTCUSDT",
        channel="publicTrade",
        event_kind="trade_batch",
        source_timestamp_ms=2_510,
        event_at_ms=2_502,
        ingested_at_ms=2_520,
        sequence=100,
        update_id=0,
        raw_payload=trade_payload,
        trades=trades,
    )


@pytest.mark.asyncio
async def test_wire_collection_keeps_raw_deltas_and_bounds_snapshots(tmp_path) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    raw_store = RawMarketTapeStore(tmp_path / "raw_market_tape.sqlite3")

    result = await persist_bybit_wire_stream(
        store=store,
        raw_store=raw_store,
        events=_wire_events(),
        orderbook_snapshot_interval_ms=1_000,
    )

    assert result.observed_messages == 5
    assert result.raw_inserted == 5
    assert result.raw_unchanged == 0
    assert result.orderbooks_inserted == 2
    assert result.orderbooks_skipped_by_cadence == 2
    assert result.trades_inserted == 2
    assert result.normalized_inserted_total == 4
    assert raw_store.count() == 5
    assert store.counts().orderbooks == 2
    assert store.counts().trades == 2
    assert raw_store.quick_check() is True
    assert store.quick_check() is True


@pytest.mark.asyncio
async def test_wire_collection_can_bound_wire_messages(tmp_path) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    raw_store = RawMarketTapeStore(tmp_path / "raw_market_tape.sqlite3")

    result = await persist_bybit_wire_stream(
        store=store,
        raw_store=raw_store,
        events=_wire_events(),
        orderbook_snapshot_interval_ms=1_000,
        max_messages=2,
    )

    assert result.observed_messages == 2
    assert raw_store.count() == 2
    assert store.counts().orderbooks == 1
    assert result.orderbooks_skipped_by_cadence == 1


@pytest.mark.asyncio
async def test_wire_collection_rejects_non_positive_cadence(tmp_path) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    raw_store = RawMarketTapeStore(tmp_path / "raw_market_tape.sqlite3")

    with pytest.raises(ValueError, match="snapshot interval"):
        await persist_bybit_wire_stream(
            store=store,
            raw_store=raw_store,
            events=_wire_events(),
            orderbook_snapshot_interval_ms=0,
        )

@pytest.mark.asyncio
async def test_bounded_wire_collection_closes_async_generator(tmp_path) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    raw_store = RawMarketTapeStore(tmp_path / "raw_market_tape.sqlite3")
    closed = False

    async def closable_events() -> AsyncIterator[BybitMicrostructureWireEvent]:
        nonlocal closed
        try:
            async for event in _wire_events():
                yield event
        finally:
            closed = True

    result = await persist_bybit_wire_stream(
        store=store,
        raw_store=raw_store,
        events=closable_events(),
        orderbook_snapshot_interval_ms=1_000,
        max_messages=2,
    )

    assert result.observed_messages == 2
    assert closed is True

