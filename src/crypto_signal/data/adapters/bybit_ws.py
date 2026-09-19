from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from contextlib import suppress
from decimal import Decimal
from typing import Literal, cast

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.data.timeframes import spec


def parse_bybit_kline_message(
    message: str | bytes,
    *,
    symbol: str,
    timeframe: str,
    ingested_at_ms: int | None = None,
) -> tuple[Candle, ...]:
    if isinstance(message, bytes):
        message = message.decode("utf-8")
    payload = cast(dict[str, object], json.loads(message))

    topic = payload.get("topic")
    if topic is None:
        return ()

    tf = spec(timeframe)
    expected_topic = f"kline.{tf.bybit_interval}.{symbol}"
    if topic != expected_topic:
        raise ValueError(f"unexpected Bybit topic: {topic!r}")

    source_timestamp_ms = int(cast(int, payload["ts"]))
    raw_data = cast(list[dict[str, object]], payload["data"])
    seen_at_ms = ingested_at_ms if ingested_at_ms is not None else time.time_ns() // 1_000_000
    candles: list[Candle] = []
    for item in raw_data:
        if str(item["interval"]) != tf.bybit_interval:
            raise ValueError("Bybit kline interval does not match subscription")

        open_time_ms = int(cast(int, item["start"]))
        close_time_ms = int(cast(int, item["end"]))
        expected_close_ms = open_time_ms + tf.duration_ms - 1
        if close_time_ms != expected_close_ms:
            raise ValueError("Bybit kline bounds do not match timeframe duration")

        candles.append(
            Candle(
                exchange=Exchange.BYBIT,
                market_type=MarketType.SPOT,
                symbol=symbol,
                timeframe=timeframe,
                open_time_ms=open_time_ms,
                close_time_ms=close_time_ms,
                open=Decimal(str(item["open"])),
                high=Decimal(str(item["high"])),
                low=Decimal(str(item["low"])),
                close=Decimal(str(item["close"])),
                volume=Decimal(str(item["volume"])),
                quote_volume=Decimal(str(item["turnover"])),
                trade_count=None,
                is_closed=bool(item["confirm"]),
                source=DataSource.WEBSOCKET,
                source_timestamp_ms=source_timestamp_ms,
                ingested_at_ms=seen_at_ms,
                adapter_version=BybitSpotKlineStream.ADAPTER_VERSION,
            )
        )
    return tuple(candles)
class BybitSpotKlineStream:
    WS_URL = "wss://stream.bybit.com/v5/public/spot"
    ADAPTER_VERSION = "bybit-v5-spot-ws/1"

    def __init__(self, *, url: str | None = None, proxy: str | Literal[True] | None = True) -> None:
        self.url = url or self.WS_URL
        self.proxy = proxy

    async def stream_candles(self, *, symbol: str, timeframe: str) -> AsyncGenerator[Candle, None]:
        if not symbol or symbol != symbol.upper():
            raise ValueError("Bybit symbol must be non-empty uppercase")

        tf = spec(timeframe)
        topic = f"kline.{tf.bybit_interval}.{symbol}"
        subscription = json.dumps({"op": "subscribe", "args": [topic]})

        async for websocket in connect(
            self.url,
            ping_interval=20,
            ping_timeout=20,
            open_timeout=10,
            proxy=self.proxy,
        ):
            heartbeat = asyncio.create_task(self._heartbeat(websocket))
            try:
                await websocket.send(subscription)
                async for message in websocket:
                    for candle in parse_bybit_kline_message(
                        message,
                        symbol=symbol,
                        timeframe=timeframe,
                    ):
                        yield candle
            except ConnectionClosed:
                continue
            finally:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError, ConnectionClosed):
                    await heartbeat

    @staticmethod
    async def _heartbeat(websocket: ClientConnection) -> None:
        while True:
            await asyncio.sleep(20)
            await websocket.send(json.dumps({"op": "ping"}))
