import asyncio
import json
from decimal import Decimal

from websockets.asyncio.server import ServerConnection, serve

from crypto_signal.data.adapters.binance_ws import (
    BinanceSpotKlineStream,
    parse_binance_kline_message,
)
from crypto_signal.data.models import DataSource


def payload(start_ms: int, *, source_ms: int, closed: bool = True) -> dict[str, object]:
    return {
        "e": "kline",
        "E": source_ms,
        "s": "BTCUSDT",
        "k": {
            "t": start_ms,
            "T": start_ms + 899_999,
            "s": "BTCUSDT",
            "i": "15m",
            "f": 1,
            "L": 2,
            "o": "100.1",
            "c": "101.5",
            "h": "102.2",
            "l": "99.9",
            "v": "3.25",
            "n": 42,
            "x": closed,
            "q": "328.75",
            "V": "1",
            "Q": "100",
            "B": "0",
        },
    }


def test_parser_preserves_binance_ws_truth() -> None:
    candle = parse_binance_kline_message(
        json.dumps(payload(1_710_000_000_000, source_ms=1_710_000_900_100)),
        symbol="BTCUSDT",
        timeframe="15m",
        ingested_at_ms=1_710_000_900_200,
    )

    assert candle.open == Decimal("100.1")
    assert candle.quote_volume == Decimal("328.75")
    assert candle.trade_count == 42
    assert candle.is_closed is True
    assert candle.source is DataSource.WEBSOCKET
def test_stream_reconnects_after_transient_close() -> None:
    async def run() -> tuple[int, int, int]:
        connections = 0

        async def handler(websocket: ServerConnection) -> None:
            nonlocal connections
            connections += 1
            start_ms = 1_710_000_000_000 + (connections - 1) * 900_000
            await websocket.send(json.dumps(payload(start_ms, source_ms=start_ms + 1000)))
            if connections == 1:
                await websocket.close(code=1011, reason="forced transient failure")
            else:
                await asyncio.sleep(0.1)

        async with serve(handler, "127.0.0.1", 0) as server:
            socket = next(iter(server.sockets))
            port = int(socket.getsockname()[1])
            stream = BinanceSpotKlineStream(
                url=f"ws://127.0.0.1:{port}",
                proxy=None,
            ).stream_candles(symbol="BTCUSDT", timeframe="15m")

            first = await anext(stream)
            second = await anext(stream)
            await stream.aclose()
            return first.open_time_ms, second.open_time_ms, connections

    first_open, second_open, connections = asyncio.run(run())

    assert second_open - first_open == 900_000
    assert connections == 2
