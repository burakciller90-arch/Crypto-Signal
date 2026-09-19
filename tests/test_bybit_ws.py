import asyncio
import json
from decimal import Decimal

from websockets.asyncio.server import ServerConnection, serve

from crypto_signal.data.adapters.bybit_ws import (
    BybitSpotKlineStream,
    parse_bybit_kline_message,
)
from crypto_signal.data.models import DataSource


def payload(start_ms: int, *, source_ms: int, closed: bool = True) -> dict[str, object]:
    return {
        "topic": "kline.15.BTCUSDT",
        "type": "snapshot",
        "ts": source_ms,
        "data": [
            {
                "start": start_ms,
                "end": start_ms + 899_999,
                "interval": "15",
                "open": "100.1",
                "close": "101.5",
                "high": "102.2",
                "low": "99.9",
                "volume": "3.25",
                "turnover": "328.75",
                "confirm": closed,
                "timestamp": source_ms - 1,
            }
        ],
    }


def test_parser_ignores_control_messages() -> None:
    message = json.dumps({"success": True, "ret_msg": "subscribe", "op": "subscribe"})
    assert parse_bybit_kline_message(message, symbol="BTCUSDT", timeframe="15m") == ()


def test_parser_preserves_ws_truth() -> None:
    message = json.dumps(payload(1_710_000_000_000, source_ms=1_710_000_900_100))
    candles = parse_bybit_kline_message(
        message,
        symbol="BTCUSDT",
        timeframe="15m",
        ingested_at_ms=1_710_000_900_200,
    )

    assert len(candles) == 1
    candle = candles[0]
    assert candle.open == Decimal("100.1")
    assert candle.quote_volume == Decimal("328.75")
    assert candle.is_closed is True
    assert candle.source is DataSource.WEBSOCKET
    assert candle.source_timestamp_ms == 1_710_000_900_100
def test_stream_reconnects_and_resubscribes_after_transient_close() -> None:
    async def run() -> tuple[int, int, int]:
        connections = 0
        subscriptions = 0

        async def handler(websocket: ServerConnection) -> None:
            nonlocal connections, subscriptions
            connections += 1
            raw = await websocket.recv()
            request = json.loads(raw)
            assert request == {"op": "subscribe", "args": ["kline.15.BTCUSDT"]}
            subscriptions += 1

            start_ms = 1_710_000_000_000 + (connections - 1) * 900_000
            await websocket.send(json.dumps(payload(start_ms, source_ms=start_ms + 1000)))
            if connections == 1:
                await websocket.close(code=1011, reason="forced transient failure")
            else:
                await asyncio.sleep(0.1)

        async with serve(handler, "127.0.0.1", 0) as server:
            socket = next(iter(server.sockets))
            port = int(socket.getsockname()[1])
            stream = BybitSpotKlineStream(
                url=f"ws://127.0.0.1:{port}",
                proxy=None,
            ).stream_candles(symbol="BTCUSDT", timeframe="15m")

            first = await anext(stream)
            second = await anext(stream)
            await stream.aclose()
            return first.open_time_ms, second.open_time_ms, subscriptions

    first_open, second_open, subscriptions = asyncio.run(run())

    assert second_open - first_open == 900_000
    assert subscriptions == 2
