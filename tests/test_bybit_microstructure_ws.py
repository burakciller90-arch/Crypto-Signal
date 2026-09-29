from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest

from crypto_signal.data.adapters.bybit_microstructure_ws import (
    BybitSpotMicrostructureStream,
    BybitSpotOrderBookState,
    parse_bybit_public_trade_payload,
)
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.market_tape_collection import persist_market_tape_stream
from crypto_signal.data.microstructure import (
    AggressorSide,
    OrderBookSnapshot,
    PublicTradeObservation,
)
from crypto_signal.data.models import DataSource

ADAPTER_VERSION = BybitSpotMicrostructureStream.ADAPTER_VERSION


def _snapshot_payload(
    *,
    update_id: int = 10,
    sequence: int = 20,
) -> dict[str, object]:
    return {
        "topic": "orderbook.50.BTCUSDT",
        "type": "snapshot",
        "ts": 1_010,
        "cts": 1_009,
        "data": {
            "s": "BTCUSDT",
            "b": [["100", "2"], ["99", "3"]],
            "a": [["101", "2.5"], ["102", "4"]],
            "u": update_id,
            "seq": sequence,
        },
    }


def _delta_payload(
    *,
    update_id: int = 11,
    sequence: int = 21,
) -> dict[str, object]:
    return {
        "topic": "orderbook.50.BTCUSDT",
        "type": "delta",
        "ts": 1_020,
        "cts": 1_019,
        "data": {
            "s": "BTCUSDT",
            "b": [["100", "0"], ["99.5", "1.25"]],
            "a": [["101", "5"], ["102", "0"], ["103", "1"]],
            "u": update_id,
            "seq": sequence,
        },
    }


def _trade_payload() -> dict[str, object]:
    return {
        "topic": "publicTrade.BTCUSDT",
        "type": "snapshot",
        "ts": 2_010,
        "data": [
            {
                "T": 2_001,
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
                "T": 2_002,
                "s": "BTCUSDT",
                "S": "Sell",
                "v": "0.10",
                "p": "100.4",
                "i": "trade-2",
                "BT": True,
                "RPI": False,
                "seq": 100,
            },
        ],
    }


def test_bybit_orderbook_state_applies_snapshot_and_delta() -> None:
    state = BybitSpotOrderBookState(
        symbol="BTCUSDT",
        depth=50,
        adapter_version=ADAPTER_VERSION,
    )

    first = state.apply_payload(_snapshot_payload(), ingested_at_ms=1_011)
    second = state.apply_payload(_delta_payload(), ingested_at_ms=1_021)

    assert first.source is DataSource.WEBSOCKET
    assert first.update_id == 10
    assert first.sequence == 20
    assert tuple((level.price, level.size) for level in first.bids) == (
        (Decimal(100), Decimal(2)),
        (Decimal(99), Decimal(3)),
    )
    assert tuple((level.price, level.size) for level in second.bids) == (
        (Decimal("99.5"), Decimal("1.25")),
        (Decimal(99), Decimal(3)),
    )
    assert tuple((level.price, level.size) for level in second.asks) == (
        (Decimal(101), Decimal(5)),
        (Decimal(103), Decimal(1)),
    )


def test_bybit_orderbook_delta_requires_snapshot() -> None:
    state = BybitSpotOrderBookState(
        symbol="BTCUSDT",
        depth=50,
        adapter_version=ADAPTER_VERSION,
    )
    with pytest.raises(ValueError, match="delta arrived before snapshot"):
        state.apply_payload(_delta_payload(), ingested_at_ms=1_021)


def test_bybit_orderbook_rejects_sequence_regression() -> None:
    state = BybitSpotOrderBookState(
        symbol="BTCUSDT",
        depth=50,
        adapter_version=ADAPTER_VERSION,
    )
    state.apply_payload(_snapshot_payload(sequence=20), ingested_at_ms=1_011)
    with pytest.raises(ValueError, match="sequence regressed"):
        state.apply_payload(
            _delta_payload(update_id=11, sequence=19),
            ingested_at_ms=1_021,
        )


def test_bybit_orderbook_update_id_one_resets_state() -> None:
    state = BybitSpotOrderBookState(
        symbol="BTCUSDT",
        depth=50,
        adapter_version=ADAPTER_VERSION,
    )
    state.apply_payload(_snapshot_payload(), ingested_at_ms=1_011)

    reset_payload = {
        "topic": "orderbook.50.BTCUSDT",
        "type": "delta",
        "ts": 1_030,
        "cts": 1_029,
        "data": {
            "s": "BTCUSDT",
            "b": [["98", "7"]],
            "a": [["104", "8"]],
            "u": 1,
            "seq": 30,
        },
    }
    reset = state.apply_payload(reset_payload, ingested_at_ms=1_031)

    assert tuple((level.price, level.size) for level in reset.bids) == (
        (Decimal(98), Decimal(7)),
    )
    assert tuple((level.price, level.size) for level in reset.asks) == (
        (Decimal(104), Decimal(8)),
    )


def test_bybit_public_trade_payload_normalizes_taker_evidence() -> None:
    trades = parse_bybit_public_trade_payload(
        _trade_payload(),
        expected_symbol="BTCUSDT",
        adapter_version=ADAPTER_VERSION,
        ingested_at_ms=2_011,
    )

    assert len(trades) == 2
    assert trades[0].exec_id == "trade-1"
    assert trades[0].aggressor_side is AggressorSide.BUY
    assert trades[0].book_eligible is True
    assert trades[0].source is DataSource.WEBSOCKET
    assert trades[1].aggressor_side is AggressorSide.SELL
    assert trades[1].is_block_trade is True
    assert trades[1].book_eligible is False


async def _events() -> AsyncIterator[OrderBookSnapshot | PublicTradeObservation]:
    state = BybitSpotOrderBookState(
        symbol="BTCUSDT",
        depth=50,
        adapter_version=ADAPTER_VERSION,
    )
    yield state.apply_payload(_snapshot_payload(), ingested_at_ms=1_011)
    for trade in parse_bybit_public_trade_payload(
        _trade_payload(),
        expected_symbol="BTCUSDT",
        adapter_version=ADAPTER_VERSION,
        ingested_at_ms=2_011,
    ):
        yield trade


@pytest.mark.anyio
async def test_market_tape_stream_persistence_is_bounded_and_append_only(tmp_path) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")

    result = await persist_market_tape_stream(
        store=store,
        events=_events(),
        max_events=3,
    )

    assert result.observed_events == 3
    assert result.orderbooks_inserted == 1
    assert result.trades_inserted == 2
    assert result.inserted_total == 3
    assert store.counts().orderbooks == 1
    assert store.counts().trades == 2
    assert store.quick_check() is True


def test_bybit_microstructure_accepts_explicit_regional_ws_url() -> None:
    stream = BybitSpotMicrostructureStream(
        url="wss://stream.bybit.tr/v5/public/spot",
        proxy=None,
    )

    assert stream.url == "wss://stream.bybit.tr/v5/public/spot"
    assert stream.proxy is None
