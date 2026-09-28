from __future__ import annotations

import time
from decimal import Decimal
from typing import cast

import httpx

from crypto_signal.data.adapters.base import CandleSourceSnapshot
from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.data.timeframes import spec


class BybitSpotAdapter:
    BASE_URL = "https://api.bybit.com"
    ADAPTER_VERSION = "bybit-v5-spot/1"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        base_url: str | None = None,
    ) -> None:
        selected_base_url = (base_url or self.BASE_URL).rstrip("/")
        if not selected_base_url.startswith("https://"):
            raise ValueError("Bybit REST base URL must use https")
        self._client = client
        self._base_url = selected_base_url

    async def fetch_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> tuple[Candle, ...]:
        snapshot = await self.fetch_source_candles(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            start_ms=start_ms,
            end_ms=end_ms,
        )
        return snapshot.candles

    async def fetch_source_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> CandleSourceSnapshot:
        if symbol != symbol.upper() or not symbol:
            raise ValueError("Bybit symbol must be non-empty uppercase")
        if not 1 <= limit <= 1000:
            raise ValueError("Bybit kline limit must be between 1 and 1000")

        tf = spec(timeframe)
        params: dict[str, str | int] = {
            "category": "spot",
            "symbol": symbol,
            "interval": tf.bybit_interval,
            "limit": limit,
        }
        if start_ms is not None:
            params["start"] = start_ms
        if end_ms is not None:
            params["end"] = end_ms

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await client.get(
                f"{self._base_url}/v5/market/kline",
                params=params,
            )
            response.raise_for_status()
            payload = cast(dict[str, object], response.json())
            observed_at_ms = time.time_ns() // 1_000_000
        finally:
            if owns_client:
                await client.aclose()

        if payload.get("retCode") != 0:
            raise ValueError(f"Bybit API error: {payload.get('retMsg')!r}")

        result = cast(dict[str, object], payload["result"])
        raw_rows = cast(list[list[str]], result["list"])
        server_time_ms = int(cast(int, payload["time"]))

        candles = [
            self._normalize_row(
                row=row,
                symbol=symbol,
                timeframe=timeframe,
                duration_ms=tf.duration_ms,
                server_time_ms=server_time_ms,
                ingested_at_ms=observed_at_ms,
            )
            for row in raw_rows
        ]
        candles.sort(key=lambda candle: candle.open_time_ms)
        return CandleSourceSnapshot(
            provider=Exchange.BYBIT.value,
            source="spot_kline_rest",
            channel=f"rest.kline.{timeframe}",
            symbol=symbol,
            timeframe=timeframe,
            raw_payload={"response": payload},
            candles=tuple(candles),
            observed_at_ms=observed_at_ms,
        )

    def _normalize_row(
        self,
        *,
        row: list[str],
        symbol: str,
        timeframe: str,
        duration_ms: int,
        server_time_ms: int,
        ingested_at_ms: int,
    ) -> Candle:
        if len(row) < 7:
            raise ValueError("Bybit kline row is incomplete")

        open_time_ms = int(row[0])
        close_time_ms = open_time_ms + duration_ms - 1
        return Candle(
            exchange=Exchange.BYBIT,
            market_type=MarketType.SPOT,
            symbol=symbol,
            timeframe=timeframe,
            open_time_ms=open_time_ms,
            close_time_ms=close_time_ms,
            open=Decimal(row[1]),
            high=Decimal(row[2]),
            low=Decimal(row[3]),
            close=Decimal(row[4]),
            volume=Decimal(row[5]),
            quote_volume=Decimal(row[6]),
            trade_count=None,
            is_closed=server_time_ms > close_time_ms,
            source=DataSource.REST,
            source_timestamp_ms=server_time_ms,
            ingested_at_ms=ingested_at_ms,
            adapter_version=self.ADAPTER_VERSION,
        )
