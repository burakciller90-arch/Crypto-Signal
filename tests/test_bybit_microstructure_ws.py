from __future__ import annotations

import asyncio
import json
from decimal import Decimal

from websockets.asyncio.server import ServerConnection, serve

from crypto_signal.data.adapters.bybit_microstructure_ws import (
    BybitSpotPublicTradeStream,
    parse_bybit_public_trade_message,
)
from crypto_signal.data.microstructure import AggressorSide
from crypto_signal.data.models import DataSource


def payload(
    *,
    source_ms: int,
    trade_ms: int,
    exec_id: str,
    seq: int,
    side: str = "Buy",
) -> dict[str, object]:
    return {
        "topic": "publicTrade.BTCUSDT",
        "type": "snapshot",
        "ts": source_ms,
        "data": [
            {
                "T": trade_ms,
                "s": "BTCUSDT",
                "S": side,
                "v": "0.125",
                "p": "67250.5",
                "i": exec_id,
                "BT": False,
                "RPI": False,
                "seq": seq,
            }
        ],
    }


def test_parser_ignores_control_messages() -> None:
    message = json.dumps(
        {"success": True, "ret_msg": "subscribe", "op": "subscribe"}
    )
    assert parse_bybit_public_trade_message(
        message,
        symbol="BTCUSDT",
    ) == ()


def test_parser_preserves_public_trade_truth() -> None:
    message = json.dumps(
        payload(
            source_ms=1_710_000_000_100,
            trade_ms=1_710_000_000_090,
            exec_id="trade-1",
            seq=123,
        )
    )

    trades = parse_bybit_public_trade_message(
        message,
        symbol="BTCUSDT",
        ingested_at_ms=1_710_000_000_200,
    )

    assert len(trades) == 1
    trade = trades[0]
    assert trade.exec_id == "trade-1"
    assert trade.sequence == 123
    assert trade.aggressor_side is AggressorSide.BUY
    assert trade.price == Decimal("67250.5")
    assert trade.size == Decimal("0.125")
    assert trade.event_at_ms == 1_710_000_000_090
    assert trade.source_timestamp_ms == 1_710_000_000_100
    assert trade.ingested_at_ms == 1_710_000_000_200
    assert trade.source is DataSource.WEBSOCKET
    assert trade.is_block_trade is False
    assert trade.is_rpi_trade is False


def test_parser_rejects_wrong_topic_and_side() -> None:
    wrong_topic = payload(
        source_ms=2_000,
        trade_ms=1_999,
        exec_id="trade-1",
        seq=1,
    )
    wrong_topic["topic"] = "publicTrade.ETHUSDT"

    try:
        parse_bybit_public_trade_message(
            json.dumps(wrong_topic),
            symbol="BTCUSDT",
        )
    except ValueError as exc:
        assert "topic" in str(exc)
    else:
        raise AssertionError("wrong topic must fail closed")

    wrong_side = payload(
        source_ms=2_000,
        trade_ms=1_999,
        exec_id="trade-2",
        seq=2,
        side="Unknown",
    )
    try:
        parse_bybit_public_trade_message(
            json.dumps(wrong_side),
            symbol="BTCUSDT",
        )
    except ValueError as exc:
        assert "side" in str(exc)
    else:
        raise AssertionError("wrong side must fail closed")


def test_stream_reconnects_and_resubscribes_after_transient_close() -> None:
    async def run() -> tuple[str, str, int]:
        connections = 0
        subscriptions = 0

        async def handler(websocket: ServerConnection) -> None:
            nonlocal connections, subscriptions
            connections += 1
            raw = await websocket.recv()
            request = json.loads(raw)
            assert request == {
                "op": "subscribe",
                "args": ["publicTrade.BTCUSDT"],
            }
            subscriptions += 1

            await websocket.send(
                json.dumps(
                    payload(
                        source_ms=10_000 + connections,
                        trade_ms=9_990 + connections,
                        exec_id=f"trade-{connections}",
                        seq=100 + connections,
                    )
                )
            )
            if connections == 1:
                await websocket.close(
                    code=1011,
                    reason="forced transient failure",
                )
            else:
                await asyncio.sleep(0.1)

        async with serve(handler, "127.0.0.1", 0) as server:
            socket = next(iter(server.sockets))
            port = int(socket.getsockname()[1])
            stream = BybitSpotPublicTradeStream(
                url=f"ws://127.0.0.1:{port}",
                proxy=None,
            ).stream_trades(symbol="BTCUSDT")

            first = await anext(stream)
            second = await anext(stream)
            await stream.aclose()
            return first.exec_id, second.exec_id, subscriptions

    first_id, second_id, subscriptions = asyncio.run(run())

    assert first_id == "trade-1"
    assert second_id == "trade-2"
    assert subscriptions == 2
