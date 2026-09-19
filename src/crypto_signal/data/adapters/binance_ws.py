from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator
from decimal import Decimal
from typing import Literal, cast

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.data.timeframes import spec


def parse_binance_kline_message(
    message: str | bytes,
    *,
    symbol: str,
    timeframe: str,
    ingested_at_ms: int | None = None,
) -> Candle:
    if isinstance(message, bytes):
        message = message.decode("utf-8")
    payload = cast(dict[str, object], json.loads(message))
    if payload.get("e") != "kline":
        raise ValueError("unexpected Binance WebSocket event")
    if payload.get("s") != symbol:
        raise ValueError("unexpected Binance symbol")

    kline = cast(dict[str, object], payload["k"])
    tf = spec(timeframe)
    if str(kline["i"]) != tf.binance_interval:
        raise ValueError("Binance kline interval does not match subscription")

    open_time_ms = int(cast(int, kline["t"]))
    close_time_ms = int(cast(int, kline["T"]))
    expected_close_ms = open_time_ms + tf.duration_ms - 1
    if close_time_ms != expected_close_ms:
        raise ValueError("Binance kline bounds do not match timeframe duration")

    seen_at_ms = ingested_at_ms if ingested_at_ms is not None else time.time_ns() // 1_000_000
    return Candle(
        exchange=Exchange.BINANCE,
        market_type=MarketType.SPOT,
        symbol=symbol,
        timeframe=timeframe,
        open_time_ms=open_time_ms,
        close_time_ms=close_time_ms,
        open=Decimal(str(kline["o"])),
        high=Decimal(str(kline["h"])),
        low=Decimal(str(kline["l"])),
        close=Decimal(str(kline["c"])),
        volume=Decimal(str(kline["v"])),
        quote_volume=Decimal(str(kline["q"])),
        trade_count=int(cast(int, kline["n"])),
        is_closed=bool(kline["x"]),
        source=DataSource.WEBSOCKET,
        source_timestamp_ms=int(cast(int, payload["E"])),
        ingested_at_ms=seen_at_ms,
        adapter_version=BinanceSpotKlineStream.ADAPTER_VERSION,
    )


class BinanceSpotKlineStream:
    WS_BASE = "wss://stream.binance.com:9443/ws"
    ADAPTER_VERSION = "binance-spot-ws/1"

    def __init__(self, *, url: str | None = None, proxy: str | Literal[True] | None = True) -> None:
        self.url = url
        self.proxy = proxy
    async def stream_candles(self, *, symbol: str, timeframe: str) -> AsyncGenerator[Candle, None]:
        if not symbol or symbol != symbol.upper():
            raise ValueError("Binance symbol must be non-empty uppercase")

        tf = spec(timeframe)
        url = self.url or f"{self.WS_BASE}/{symbol.lower()}@kline_{tf.binance_interval}"

        async for websocket in connect(
            url,
            ping_interval=20,
            ping_timeout=20,
            open_timeout=10,
            proxy=self.proxy,
        ):
            try:
                async for message in websocket:
                    yield parse_binance_kline_message(
                        message,
                        symbol=symbol,
                        timeframe=timeframe,
                    )
            except ConnectionClosed:
                continue
