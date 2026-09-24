from __future__ import annotations

import json

from crypto_signal.data.models import Exchange
from crypto_signal.data.raw_market_tape import (
    RawMarketTapeStore,
    RawMarketTapeWriteDisposition,
)


def test_raw_market_tape_is_append_only_and_replay_safe(tmp_path) -> None:
    store = RawMarketTapeStore(tmp_path / "raw_market_tape.sqlite3")
    payload = {
        "topic": "orderbook.50.BTCUSDT",
        "type": "delta",
        "ts": 1_010,
        "cts": 1_009,
        "data": {
            "s": "BTCUSDT",
            "b": [["100", "2"]],
            "a": [],
            "u": 11,
            "seq": 21,
        },
    }

    first_disposition, first = store.append(
        exchange=Exchange.BYBIT,
        channel="orderbook.50",
        symbol="BTCUSDT",
        event_kind="delta",
        source_timestamp_ms=1_010,
        event_at_ms=1_009,
        ingested_at_ms=1_020,
        sequence=21,
        update_id=11,
        payload=payload,
    )
    replay_disposition, replay = store.append(
        exchange=Exchange.BYBIT,
        channel="orderbook.50",
        symbol="BTCUSDT",
        event_kind="delta",
        source_timestamp_ms=1_010,
        event_at_ms=1_009,
        ingested_at_ms=9_999,
        sequence=21,
        update_id=11,
        payload=payload,
    )

    assert first_disposition is RawMarketTapeWriteDisposition.INSERTED
    assert replay_disposition is RawMarketTapeWriteDisposition.UNCHANGED
    assert first.event_identity == replay.event_identity
    assert store.count() == 1
    assert store.quick_check() is True
    assert store.latest_event_at_ms() == 1_009

    recent = store.recent(
        exchange=Exchange.BYBIT,
        channel="orderbook.50",
        symbol="BTCUSDT",
    )
    assert len(recent) == 1
    assert recent[0].ingested_at_ms == 1_020
    assert json.loads(recent[0].payload_json) == payload


def test_raw_market_tape_separates_changed_wire_payload(tmp_path) -> None:
    store = RawMarketTapeStore(tmp_path / "raw_market_tape.sqlite3")

    base = {
        "topic": "publicTrade.BTCUSDT",
        "type": "snapshot",
        "ts": 2_010,
        "data": [{"i": "trade-1", "p": "100"}],
    }
    changed = {
        **base,
        "data": [{"i": "trade-1", "p": "101"}],
    }

    first, _ = store.append(
        exchange=Exchange.BYBIT,
        channel="publicTrade",
        symbol="BTCUSDT",
        event_kind="trade_batch",
        source_timestamp_ms=2_010,
        event_at_ms=2_001,
        ingested_at_ms=2_020,
        sequence=100,
        update_id=0,
        payload=base,
    )
    second, _ = store.append(
        exchange=Exchange.BYBIT,
        channel="publicTrade",
        symbol="BTCUSDT",
        event_kind="trade_batch",
        source_timestamp_ms=2_010,
        event_at_ms=2_001,
        ingested_at_ms=2_021,
        sequence=100,
        update_id=0,
        payload=changed,
    )

    assert first is RawMarketTapeWriteDisposition.INSERTED
    assert second is RawMarketTapeWriteDisposition.INSERTED
    assert store.count() == 2


def test_raw_market_tape_latest_by_context_uses_persisted_ingestion_time(
    tmp_path,
) -> None:
    store = RawMarketTapeStore(tmp_path / "raw_market_tape.sqlite3")
    book_payload = {
        "topic": "orderbook.50.BTCUSDT",
        "type": "delta",
        "ts": 1_010,
        "cts": 1_009,
        "data": {"s": "BTCUSDT", "b": [], "a": [], "u": 11, "seq": 21},
    }
    _, first = store.append(
        exchange=Exchange.BYBIT,
        channel="orderbook.50",
        symbol="BTCUSDT",
        event_kind="delta",
        source_timestamp_ms=1_010,
        event_at_ms=1_009,
        ingested_at_ms=1_020,
        sequence=21,
        update_id=11,
        payload=book_payload,
    )
    replay_disposition, replay = store.append(
        exchange=Exchange.BYBIT,
        channel="orderbook.50",
        symbol="BTCUSDT",
        event_kind="delta",
        source_timestamp_ms=1_010,
        event_at_ms=1_009,
        ingested_at_ms=9_999,
        sequence=21,
        update_id=11,
        payload=book_payload,
    )
    _, trade = store.append(
        exchange=Exchange.BYBIT,
        channel="publicTrade",
        symbol="ETHUSDT",
        event_kind="trade_batch",
        source_timestamp_ms=2_010,
        event_at_ms=2_001,
        ingested_at_ms=2_020,
        sequence=100,
        update_id=0,
        payload={"topic": "publicTrade.ETHUSDT", "data": []},
    )

    latest = store.latest_by_context(exchange=Exchange.BYBIT)

    assert replay_disposition is RawMarketTapeWriteDisposition.UNCHANGED
    assert replay.event_identity == first.event_identity
    assert tuple((event.channel, event.symbol) for event in latest) == (
        ("orderbook.50", "BTCUSDT"),
        ("publicTrade", "ETHUSDT"),
    )
    assert latest[0].ingested_at_ms == 1_020
    assert latest[0].event_identity == first.event_identity
    assert latest[1].event_identity == trade.event_identity
