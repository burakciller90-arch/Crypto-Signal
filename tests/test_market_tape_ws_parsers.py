from __future__ import annotations

import json
from decimal import Decimal

import pytest

from crypto_signal.data.adapters.market_tape_ws import (
    parse_binance_agg_trade_message,
    parse_binance_depth_message,
    parse_bybit_orderbook_message,
    parse_bybit_public_trade_message,
)
from crypto_signal.data.market_tape_stream import MarketTapeChannel
from crypto_signal.data.microstructure import AggressorSide
from crypto_signal.data.models import DataSource, Exchange


def test_parse_binance_agg_trade_preserves_raw_and_normalized_truth() -> None:
    payload = {
        "e": "aggTrade",
        "E": 1_700_000_000_100,
        "s": "BTCUSDT",
        "a": 5933014,
        "p": "42000.50",
        "q": "0.125",
        "f": 100,
        "l": 103,
        "T": 1_700_000_000_090,
        "m": False,
        "M": True,
    }

    raw, trade = parse_binance_agg_trade_message(
        json.dumps(payload),
        symbol="BTCUSDT",
        ingested_at_ms=1_700_000_000_110,
    )

    assert raw.exchange is Exchange.BINANCE
    assert raw.channel is MarketTapeChannel.PUBLIC_TRADE
    assert raw.first_sequence == 100
    assert raw.last_sequence == 103
    assert raw.source is DataSource.WEBSOCKET
    assert trade.exec_id == "5933014"
    assert trade.sequence == 5933014
    assert trade.aggressor_side is AggressorSide.BUY
    assert trade.price == Decimal("42000.50")
    assert trade.size == Decimal("0.125")


def test_parse_binance_agg_trade_buyer_maker_means_sell_aggressor() -> None:
    payload = {
        "e": "aggTrade",
        "E": 1_010,
        "s": "BTCUSDT",
        "a": 11,
        "p": "100",
        "q": "2",
        "f": 20,
        "l": 21,
        "T": 1_000,
        "m": True,
        "M": True,
    }
    _, trade = parse_binance_agg_trade_message(
        json.dumps(payload),
        symbol="BTCUSDT",
        ingested_at_ms=1_020,
    )
    assert trade.aggressor_side is AggressorSide.SELL


def test_parse_binance_depth_accepts_zero_size_delete_and_sequence_range() -> None:
    payload = {
        "e": "depthUpdate",
        "E": 2_000,
        "s": "ETHUSDT",
        "U": 200,
        "u": 205,
        "b": [["2500.00", "1.5"], ["2499.50", "0"]],
        "a": [["2501.00", "2.0"]],
    }

    raw = parse_binance_depth_message(
        json.dumps(payload),
        symbol="ETHUSDT",
        ingested_at_ms=2_010,
    )

    assert raw.channel is MarketTapeChannel.ORDERBOOK_DELTA
    assert raw.first_sequence == 200
    assert raw.last_sequence == 205
    assert raw.event_at_ms == 2_000


def test_parse_binance_depth_rejects_negative_size() -> None:
    payload = {
        "e": "depthUpdate",
        "E": 2_000,
        "s": "ETHUSDT",
        "U": 200,
        "u": 205,
        "b": [["2500.00", "-1"]],
        "a": [],
    }
    with pytest.raises(ValueError, match="non-negative"):
        parse_binance_depth_message(json.dumps(payload), symbol="ETHUSDT")


def test_parse_bybit_public_trade_preserves_flags_and_sort_order() -> None:
    payload = {
        "topic": "publicTrade.SOLUSDT",
        "type": "snapshot",
        "ts": 3_100,
        "data": [
            {
                "T": 3_010,
                "s": "SOLUSDT",
                "S": "Sell",
                "v": "4.0",
                "p": "150.20",
                "i": "exec-b",
                "BT": True,
                "RPI": False,
                "seq": 202,
            },
            {
                "T": 3_000,
                "s": "SOLUSDT",
                "S": "Buy",
                "v": "2.0",
                "p": "150.00",
                "i": "exec-a",
                "BT": False,
                "RPI": True,
                "seq": 201,
            },
        ],
    }

    raw, trades = parse_bybit_public_trade_message(
        json.dumps(payload),
        symbol="SOLUSDT",
        ingested_at_ms=3_110,
    )

    assert raw.exchange is Exchange.BYBIT
    assert raw.channel is MarketTapeChannel.PUBLIC_TRADE
    assert raw.first_sequence is None
    assert raw.last_sequence is None
    assert raw.event_at_ms == 3_010
    assert tuple(item.exec_id for item in trades) == ("exec-a", "exec-b")
    assert trades[0].aggressor_side is AggressorSide.BUY
    assert trades[0].is_rpi_trade is True
    assert trades[1].aggressor_side is AggressorSide.SELL
    assert trades[1].is_block_trade is True


def test_parse_bybit_public_trade_rejects_duplicate_exec_id() -> None:
    row = {
        "T": 3_000,
        "s": "SOLUSDT",
        "S": "Buy",
        "v": "2.0",
        "p": "150.00",
        "i": "same",
        "seq": 201,
    }
    payload = {
        "topic": "publicTrade.SOLUSDT",
        "type": "snapshot",
        "ts": 3_100,
        "data": [row, dict(row)],
    }

    with pytest.raises(ValueError, match="unique"):
        parse_bybit_public_trade_message(json.dumps(payload), symbol="SOLUSDT")


def test_parse_bybit_orderbook_uses_update_id_for_stream_sequence() -> None:
    payload = {
        "topic": "orderbook.50.BTCUSDT",
        "type": "delta",
        "ts": 4_100,
        "cts": 4_090,
        "data": {
            "s": "BTCUSDT",
            "b": [["42000.0", "1.0"], ["41999.0", "0"]],
            "a": [["42001.0", "3.0"]],
            "u": 999,
            "seq": 123456,
        },
    }

    raw = parse_bybit_orderbook_message(
        json.dumps(payload),
        symbol="BTCUSDT",
        depth=50,
        ingested_at_ms=4_110,
    )

    assert raw.exchange is Exchange.BYBIT
    assert raw.channel is MarketTapeChannel.ORDERBOOK_DELTA
    assert raw.first_sequence == 999
    assert raw.last_sequence == 999
    assert raw.event_at_ms == 4_090
    assert raw.source_timestamp_ms == 4_100


def test_market_ws_parsers_reject_symbol_mismatch() -> None:
    payload = {
        "e": "aggTrade",
        "E": 1_010,
        "s": "ETHUSDT",
        "a": 11,
        "p": "100",
        "q": "2",
        "f": 20,
        "l": 21,
        "T": 1_000,
        "m": False,
        "M": True,
    }
    with pytest.raises(ValueError, match="symbol"):
        parse_binance_agg_trade_message(json.dumps(payload), symbol="BTCUSDT")
