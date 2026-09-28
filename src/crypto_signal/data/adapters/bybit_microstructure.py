from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import cast

import httpx

from crypto_signal.data.microstructure import (
    AggressorSide,
    OrderBookLevel,
    OrderBookSnapshot,
    PublicTradeObservation,
    build_orderbook_snapshot,
    build_public_trade_observation,
)
from crypto_signal.data.models import DataSource, Exchange, MarketType


@dataclass(frozen=True, slots=True)
class BybitSpotMicrostructureSourceSnapshot:
    orderbook_payload: dict[str, object]
    trade_payload: dict[str, object]
    orderbook: OrderBookSnapshot
    trades: tuple[PublicTradeObservation, ...]
    observed_at_ms: int

    def __post_init__(self) -> None:
        if self.observed_at_ms < 0:
            raise ValueError(
                "Bybit microstructure source observation cannot be negative"
            )


class BybitSpotMicrostructureAdapter:
    BASE_URL = "https://api.bybit.com"
    ADAPTER_VERSION = "bybit-v5-spot-microstructure/1"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        base_url: str | None = None,
    ) -> None:
        selected_base_url = (base_url or self.BASE_URL).rstrip("/")
        if not selected_base_url.startswith("https://"):
            raise ValueError("Bybit microstructure REST base URL must use https")
        self._client = client
        self._base_url = selected_base_url

    async def fetch_snapshot(
        self,
        *,
        symbol: str,
        book_depth: int = 25,
        trade_limit: int = 60,
    ) -> tuple[OrderBookSnapshot, tuple[PublicTradeObservation, ...]]:
        source_snapshot = await self.fetch_source_snapshot(
            symbol=symbol,
            book_depth=book_depth,
            trade_limit=trade_limit,
        )
        return source_snapshot.orderbook, source_snapshot.trades

    async def fetch_source_snapshot(
        self,
        *,
        symbol: str,
        book_depth: int = 25,
        trade_limit: int = 60,
    ) -> BybitSpotMicrostructureSourceSnapshot:
        if not symbol or symbol != symbol.upper():
            raise ValueError(
                "Bybit microstructure symbol must be non-empty uppercase"
            )
        if not 1 <= book_depth <= 1000:
            raise ValueError(
                "Bybit spot orderbook depth must be inside [1,1000]"
            )
        if not 1 <= trade_limit <= 60:
            raise ValueError(
                "Bybit spot recent-trade limit must be inside [1,60]"
            )

        book_params: dict[str, str | int] = {
            "category": "spot",
            "symbol": symbol,
            "limit": book_depth,
        }
        trade_params: dict[str, str | int] = {
            "category": "spot",
            "symbol": symbol,
            "limit": trade_limit,
        }

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            book_task = client.get(
                f"{self._base_url}/v5/market/orderbook",
                params=book_params,
            )
            trade_task = client.get(
                f"{self._base_url}/v5/market/recent-trade",
                params=trade_params,
            )
            book_response, trade_response = await asyncio.gather(
                book_task,
                trade_task,
            )
            book_response.raise_for_status()
            trade_response.raise_for_status()
            book_payload = cast(dict[str, object], book_response.json())
            trade_payload = cast(dict[str, object], trade_response.json())
            observed_at_ms = time.time_ns() // 1_000_000
        finally:
            if owns_client:
                await client.aclose()

        _require_bybit_success(book_payload, "orderbook")
        _require_bybit_success(trade_payload, "recent-trade")
        book = self._normalize_book(
            payload=book_payload,
            symbol=symbol,
            ingested_at_ms=observed_at_ms,
        )
        trades = self._normalize_trades(
            payload=trade_payload,
            symbol=symbol,
            ingested_at_ms=observed_at_ms,
        )
        return BybitSpotMicrostructureSourceSnapshot(
            orderbook_payload=book_payload,
            trade_payload=trade_payload,
            orderbook=book,
            trades=trades,
            observed_at_ms=observed_at_ms,
        )

    def _normalize_book(
        self,
        *,
        payload: dict[str, object],
        symbol: str,
        ingested_at_ms: int,
    ) -> OrderBookSnapshot:
        response_time_ms = int(cast(int | str, payload["time"]))
        result = cast(dict[str, object], payload["result"])
        if result.get("s") != symbol:
            raise ValueError("Bybit orderbook symbol mismatch")

        bids = _levels(cast(list[list[str]], result["b"]))
        asks = _levels(cast(list[list[str]], result["a"]))
        return build_orderbook_snapshot(
            exchange=Exchange.BYBIT,
            market_type=MarketType.SPOT,
            symbol=symbol,
            event_at_ms=int(cast(int | str, result["cts"])),
            source_timestamp_ms=int(cast(int | str, result["ts"])),
            response_time_ms=response_time_ms,
            ingested_at_ms=ingested_at_ms,
            update_id=int(cast(int | str, result["u"])),
            sequence=int(cast(int | str, result["seq"])),
            bids=bids,
            asks=asks,
            source=DataSource.REST,
            adapter_version=self.ADAPTER_VERSION,
        )

    def _normalize_trades(
        self,
        *,
        payload: dict[str, object],
        symbol: str,
        ingested_at_ms: int,
    ) -> tuple[PublicTradeObservation, ...]:
        source_timestamp_ms = int(cast(int | str, payload["time"]))
        result = cast(dict[str, object], payload["result"])
        if result.get("category") != "spot":
            raise ValueError("Bybit recent-trade category mismatch")

        rows = cast(list[dict[str, object]], result["list"])
        trades: list[PublicTradeObservation] = []
        seen_exec_ids: set[str] = set()
        for row in rows:
            if row.get("symbol") != symbol:
                raise ValueError("Bybit recent-trade symbol mismatch")
            exec_id = str(row["execId"])
            if exec_id in seen_exec_ids:
                raise ValueError("Bybit recent-trade payload contains duplicate execId")
            seen_exec_ids.add(exec_id)
            side_raw = str(row["side"]).lower()
            if side_raw not in {"buy", "sell"}:
                raise ValueError("Bybit recent-trade side must be Buy or Sell")
            trades.append(
                build_public_trade_observation(
                    exchange=Exchange.BYBIT,
                    market_type=MarketType.SPOT,
                    symbol=symbol,
                    exec_id=exec_id,
                    sequence=int(cast(int | str, row["seq"])),
                    aggressor_side=AggressorSide(side_raw),
                    price=Decimal(str(row["price"])),
                    size=Decimal(str(row["size"])),
                    event_at_ms=int(cast(int | str, row["time"])),
                    source_timestamp_ms=source_timestamp_ms,
                    ingested_at_ms=ingested_at_ms,
                    is_block_trade=bool(row.get("isBlockTrade", False)),
                    is_rpi_trade=bool(row.get("isRPITrade", False)),
                    source=DataSource.REST,
                    adapter_version=self.ADAPTER_VERSION,
                )
            )
        trades.sort(
            key=lambda item: (
                item.event_at_ms,
                item.sequence,
                item.exec_id,
            )
        )
        return tuple(trades)


def _levels(rows: list[list[str]]) -> tuple[OrderBookLevel, ...]:
    levels: list[OrderBookLevel] = []
    for row in rows:
        if len(row) < 2:
            raise ValueError("Bybit orderbook level is incomplete")
        levels.append(
            OrderBookLevel(
                price=Decimal(str(row[0])),
                size=Decimal(str(row[1])),
            )
        )
    return tuple(levels)


def _require_bybit_success(payload: dict[str, object], surface: str) -> None:
    if payload.get("retCode") != 0:
        raise ValueError(
            f"Bybit microstructure {surface} API error: {payload.get('retMsg')!r}"
        )
