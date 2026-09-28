from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import cast

import httpx

from crypto_signal.data.adapters.base import CandleSourceSnapshot
from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.data.timeframes import spec


class BinanceSpotAdapter:
    BASE_URL = "https://api.binance.com"
    REGIONAL_TR_BASE_URL = "https://api.binance.me"
    ADAPTER_VERSION = "binance-spot/1"
    REGIONAL_TR_ADAPTER_VERSION = "binance-tr-main-market-data/1"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        base_url: str | None = None,
        api_variant: str = "global",
    ) -> None:
        if api_variant not in {"global", "tr_main"}:
            raise ValueError("unsupported Binance API variant")
        selected_base_url = (base_url or self.BASE_URL).rstrip("/")
        if not selected_base_url.startswith("https://"):
            raise ValueError("Binance REST base URL must use https")
        self._client = client
        self._base_url = selected_base_url
        self._api_variant = api_variant

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
        if not symbol or symbol != symbol.upper():
            raise ValueError("Binance symbol must be non-empty uppercase")
        if not 1 <= limit <= 1000:
            raise ValueError("Binance kline limit must be between 1 and 1000")

        tf = spec(timeframe)
        params: dict[str, str | int] = {
            "symbol": symbol,
            "interval": tf.binance_interval,
            "limit": limit,
        }
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=10.0)
        raw_payload: dict[str, object]
        try:
            if self._api_variant == "tr_main":
                response = await client.get(
                    f"{self._base_url}/api/v1/klines",
                    params=params,
                )
                response.raise_for_status()
                payload = response.json()
                observed_at_ms = time.time_ns() // 1_000_000
                if isinstance(payload, dict):
                    if int(cast(int | str, payload.get("code", -1))) != 0:
                        raise ValueError(
                            f"Binance TR API error: {payload.get('msg')!r}"
                        )
                    data = payload.get("data")
                    if not isinstance(data, list):
                        raise TypeError("Binance TR kline data must be array")
                    raw_rows = cast(list[list[object]], data)
                    server_time_ms = int(
                        cast(int | str, payload["timestamp"])
                    )
                    raw_payload = {"response": payload}
                elif isinstance(payload, list):
                    raw_rows = cast(list[list[object]], payload)
                    server_time_ms = self._http_source_time_ms(
                        response,
                        fallback_ms=observed_at_ms,
                    )
                    raw_payload = {
                        "response": payload,
                        "http_date": response.headers.get("date"),
                    }
                else:
                    raise TypeError(
                        "Binance TR kline response must be object or array"
                    )
            else:
                klines_task = client.get(
                    f"{self._base_url}/api/v3/klines",
                    params=params,
                )
                time_task = client.get(f"{self._base_url}/api/v3/time")
                klines_response, time_response = await asyncio.gather(
                    klines_task,
                    time_task,
                )
                klines_response.raise_for_status()
                time_response.raise_for_status()
                klines_payload = klines_response.json()
                time_payload = cast(
                    dict[str, object],
                    time_response.json(),
                )
                raw_rows = cast(list[list[object]], klines_payload)
                server_time_raw = time_payload["serverTime"]
                server_time_ms = int(cast(int | str, server_time_raw))
                observed_at_ms = time.time_ns() // 1_000_000
                raw_payload = {
                    "klines_response": klines_payload,
                    "time_response": time_payload,
                }
        finally:
            if owns_client:
                await client.aclose()

        candles = [
            self._normalize_row(
                row=row,
                symbol=symbol,
                timeframe=timeframe,
                server_time_ms=server_time_ms,
                ingested_at_ms=observed_at_ms,
            )
            for row in raw_rows
        ]
        candles.sort(key=lambda candle: candle.open_time_ms)
        return CandleSourceSnapshot(
            provider=Exchange.BINANCE.value,
            source=(
                "spot_kline_rest_tr_main"
                if self._api_variant == "tr_main"
                else "spot_kline_rest_global"
            ),
            channel=f"rest.kline.{timeframe}",
            symbol=symbol,
            timeframe=timeframe,
            raw_payload=raw_payload,
            candles=tuple(candles),
            source_timestamp_ms=server_time_ms,
            observed_at_ms=observed_at_ms,
        )

    @staticmethod
    def _http_source_time_ms(
        response: httpx.Response,
        *,
        fallback_ms: int,
    ) -> int:
        date_header = response.headers.get("date")
        if date_header:
            try:
                parsed = parsedate_to_datetime(date_header)
                return int(parsed.timestamp() * 1_000)
            except (TypeError, ValueError, OverflowError):
                pass
        return fallback_ms

    def _normalize_row(
        self,
        *,
        row: list[object],
        symbol: str,
        timeframe: str,
        server_time_ms: int,
        ingested_at_ms: int,
    ) -> Candle:
        if len(row) < 12:
            raise ValueError("Binance kline row is incomplete")

        open_time_ms = int(cast(int | str, row[0]))
        close_time_ms = int(cast(int | str, row[6]))
        return Candle(
            exchange=Exchange.BINANCE,
            market_type=MarketType.SPOT,
            symbol=symbol,
            timeframe=timeframe,
            open_time_ms=open_time_ms,
            close_time_ms=close_time_ms,
            open=Decimal(str(row[1])),
            high=Decimal(str(row[2])),
            low=Decimal(str(row[3])),
            close=Decimal(str(row[4])),
            volume=Decimal(str(row[5])),
            quote_volume=Decimal(str(row[7])),
            trade_count=int(cast(int | str, row[8])),
            is_closed=server_time_ms > close_time_ms,
            source=DataSource.REST,
            source_timestamp_ms=server_time_ms,
            ingested_at_ms=ingested_at_ms,
            adapter_version=(
                self.REGIONAL_TR_ADAPTER_VERSION
                if self._api_variant == "tr_main"
                else self.ADAPTER_VERSION
            ),
        )
