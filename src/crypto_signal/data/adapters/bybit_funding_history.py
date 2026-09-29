"""Bybit V5 exact settled funding history adapter."""

from __future__ import annotations

import time
from decimal import Decimal
from typing import cast

import httpx

from crypto_signal.data.derivatives import DerivativesInstrumentType
from crypto_signal.data.funding_settlements import (
    FundingSettlementObservation,
    build_funding_settlement_observation,
)
from crypto_signal.data.models import DataSource, Exchange


class BybitFundingHistoryAdapter:
    BASE_URL = "https://api.bybit.com"
    ADAPTER_VERSION = "bybit-v5-funding-history/1"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        base_url: str | None = None,
    ) -> None:
        selected = (base_url or self.BASE_URL).rstrip("/")
        if not selected.startswith("https://"):
            raise ValueError("Bybit funding REST base URL must use https")
        self._client = client
        self._base_url = selected

    async def fetch_settlements(
        self,
        *,
        symbol: str,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = 200,
    ) -> tuple[FundingSettlementObservation, ...]:
        if not symbol or symbol != symbol.upper():
            raise ValueError("Bybit funding symbol must be non-empty uppercase")
        if not 1 <= limit <= 200:
            raise ValueError("Bybit funding limit must be between 1 and 200")
        if start_ms is not None and start_ms < 0:
            raise ValueError("start_ms must be non-negative")
        if end_ms is not None and end_ms < 0:
            raise ValueError("end_ms must be non-negative")
        if start_ms is not None and end_ms is None:
            raise ValueError("Bybit funding history does not allow start_ms alone")
        if start_ms is not None and end_ms is not None and start_ms > end_ms:
            raise ValueError("start_ms cannot exceed end_ms")

        params: dict[str, str | int] = {
            "category": "linear",
            "symbol": symbol,
            "limit": limit,
        }
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await client.get(
                f"{self._base_url}/v5/market/funding/history",
                params=params,
            )
            response.raise_for_status()
            payload = cast(dict[str, object], response.json())
            ingested_at_ms = time.time_ns() // 1_000_000
        finally:
            if owns_client:
                await client.aclose()

        return self.normalize_payload(
            payload=payload,
            symbol=symbol,
            ingested_at_ms=ingested_at_ms,
        )

    def normalize_payload(
        self,
        *,
        payload: dict[str, object],
        symbol: str,
        ingested_at_ms: int,
    ) -> tuple[FundingSettlementObservation, ...]:
        if ingested_at_ms < 0:
            raise ValueError("ingested_at_ms must be non-negative")
        _require_bybit_success(payload)
        source_timestamp_ms = int(cast(int | str, payload["time"]))
        result = cast(dict[str, object], payload["result"])
        if result.get("category") != "linear":
            raise ValueError("Bybit funding history category mismatch")
        rows = cast(list[dict[str, object]], result["list"])

        settlements: list[FundingSettlementObservation] = []
        for row in rows:
            if row.get("symbol") != symbol:
                raise ValueError("Bybit funding history symbol mismatch")
            settlements.append(
                build_funding_settlement_observation(
                    exchange=Exchange.BYBIT,
                    instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
                    symbol=symbol,
                    settlement_at_ms=int(
                        cast(int | str, row["fundingRateTimestamp"])
                    ),
                    funding_rate=Decimal(str(row["fundingRate"])),
                    source_timestamp_ms=source_timestamp_ms,
                    ingested_at_ms=ingested_at_ms,
                    source=DataSource.REST,
                    adapter_version=self.ADAPTER_VERSION,
                )
            )

        return tuple(
            sorted(
                settlements,
                key=lambda item: (
                    item.settlement_at_ms,
                    item.settlement_identity,
                ),
            )
        )


def _require_bybit_success(payload: dict[str, object]) -> None:
    if payload.get("retCode") != 0:
        raise ValueError(
            f"Bybit funding-history API error: {payload.get('retMsg')!r}"
        )


__all__ = ["BybitFundingHistoryAdapter"]
