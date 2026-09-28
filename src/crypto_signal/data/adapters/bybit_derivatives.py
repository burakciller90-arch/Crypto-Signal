from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import cast

import httpx

from crypto_signal.data.derivatives import (
    DerivativesInstrumentType,
    DerivativesObservation,
    build_derivatives_observation,
)
from crypto_signal.data.models import DataSource, Exchange


@dataclass(frozen=True, slots=True)
class BybitLinearDerivativesSourceSnapshot:
    open_interest_payload: dict[str, object]
    ticker_payload: dict[str, object]
    open_interest_observations: tuple[DerivativesObservation, ...]
    ticker_observation: DerivativesObservation
    observed_at_ms: int

    def __post_init__(self) -> None:
        if self.observed_at_ms < 0:
            raise ValueError(
                "Bybit derivatives source observation cannot be negative"
            )

    @property
    def observations(self) -> tuple[DerivativesObservation, ...]:
        return tuple(
            sorted(
                (
                    *self.open_interest_observations,
                    self.ticker_observation,
                ),
                key=lambda item: (
                    item.event_at_ms,
                    item.observation_identity,
                ),
            )
        )


class BybitLinearDerivativesAdapter:
    BASE_URL = "https://api.bybit.com"
    ADAPTER_VERSION = "bybit-v5-linear-derivatives/1"
    _OI_INTERVALS = frozenset({"5min", "15min", "30min", "1h", "4h", "1d"})

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        base_url: str | None = None,
    ) -> None:
        selected_base_url = (base_url or self.BASE_URL).rstrip("/")
        if not selected_base_url.startswith("https://"):
            raise ValueError("Bybit derivatives REST base URL must use https")
        self._client = client
        self._base_url = selected_base_url

    async def fetch_observations(
        self,
        *,
        symbol: str,
        oi_interval: str = "15min",
        oi_limit: int = 8,
        end_ms: int | None = None,
    ) -> tuple[DerivativesObservation, ...]:
        source_snapshot = await self.fetch_source_snapshot(
            symbol=symbol,
            oi_interval=oi_interval,
            oi_limit=oi_limit,
            end_ms=end_ms,
        )
        return source_snapshot.observations

    async def fetch_source_snapshot(
        self,
        *,
        symbol: str,
        oi_interval: str = "15min",
        oi_limit: int = 8,
        end_ms: int | None = None,
    ) -> BybitLinearDerivativesSourceSnapshot:
        if not symbol or symbol != symbol.upper():
            raise ValueError(
                "Bybit derivatives symbol must be non-empty uppercase"
            )
        if oi_interval not in self._OI_INTERVALS:
            raise ValueError("unsupported Bybit open-interest interval")
        if not 2 <= oi_limit <= 200:
            raise ValueError(
                "Bybit open-interest limit must be between 2 and 200"
            )
        if end_ms is not None and end_ms < 0:
            raise ValueError("end_ms must be non-negative")

        oi_params: dict[str, str | int] = {
            "category": "linear",
            "symbol": symbol,
            "intervalTime": oi_interval,
            "limit": oi_limit,
        }
        if end_ms is not None:
            oi_params["endTime"] = end_ms

        ticker_params: dict[str, str] = {
            "category": "linear",
            "symbol": symbol,
        }

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            oi_task = client.get(
                f"{self._base_url}/v5/market/open-interest",
                params=oi_params,
            )
            ticker_task = client.get(
                f"{self._base_url}/v5/market/tickers",
                params=ticker_params,
            )
            oi_response, ticker_response = await asyncio.gather(
                oi_task,
                ticker_task,
            )
            oi_response.raise_for_status()
            ticker_response.raise_for_status()
            oi_payload = cast(dict[str, object], oi_response.json())
            ticker_payload = cast(dict[str, object], ticker_response.json())
            observed_at_ms = time.time_ns() // 1_000_000
        finally:
            if owns_client:
                await client.aclose()

        _require_bybit_success(oi_payload, "open-interest")
        _require_bybit_success(ticker_payload, "tickers")

        open_interest = self._normalize_open_interest(
            payload=oi_payload,
            symbol=symbol,
            ingested_at_ms=observed_at_ms,
        )
        ticker = self._normalize_ticker(
            payload=ticker_payload,
            symbol=symbol,
            ingested_at_ms=observed_at_ms,
        )
        return BybitLinearDerivativesSourceSnapshot(
            open_interest_payload=oi_payload,
            ticker_payload=ticker_payload,
            open_interest_observations=open_interest,
            ticker_observation=ticker,
            observed_at_ms=observed_at_ms,
        )

    def _normalize_open_interest(
        self,
        *,
        payload: dict[str, object],
        symbol: str,
        ingested_at_ms: int,
    ) -> tuple[DerivativesObservation, ...]:
        source_timestamp_ms = int(cast(int | str, payload["time"]))
        result = cast(dict[str, object], payload["result"])
        if result.get("category") != "linear":
            raise ValueError("Bybit open-interest category mismatch")
        if result.get("symbol") != symbol:
            raise ValueError("Bybit open-interest symbol mismatch")

        raw_rows = cast(list[dict[str, object]], result["list"])
        normalized = tuple(
            build_derivatives_observation(
                exchange=Exchange.BYBIT,
                instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
                symbol=symbol,
                event_at_ms=int(cast(int | str, row["timestamp"])),
                funding_rate=None,
                open_interest=Decimal(str(row["openInterest"])),
                mark_price=None,
                index_price=None,
                funding_interval_hours=None,
                source=DataSource.REST,
                source_timestamp_ms=source_timestamp_ms,
                ingested_at_ms=ingested_at_ms,
                adapter_version=self.ADAPTER_VERSION,
            )
            for row in raw_rows
        )
        return normalized

    def _normalize_ticker(
        self,
        *,
        payload: dict[str, object],
        symbol: str,
        ingested_at_ms: int,
    ) -> DerivativesObservation:
        source_timestamp_ms = int(cast(int | str, payload["time"]))
        result = cast(dict[str, object], payload["result"])
        if result.get("category") != "linear":
            raise ValueError("Bybit ticker category mismatch")

        raw_rows = cast(list[dict[str, object]], result["list"])
        matches = [row for row in raw_rows if row.get("symbol") == symbol]
        if len(matches) != 1:
            raise ValueError("Bybit ticker requires exactly one matching symbol")
        row = matches[0]

        funding_interval_raw = str(row.get("fundingIntervalHour", "")).strip()
        funding_rate_raw = str(row.get("fundingRate", "")).strip()
        open_interest_raw = str(row.get("openInterest", "")).strip()
        mark_price_raw = str(row.get("markPrice", "")).strip()
        index_price_raw = str(row.get("indexPrice", "")).strip()

        return build_derivatives_observation(
            exchange=Exchange.BYBIT,
            instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
            symbol=symbol,
            event_at_ms=source_timestamp_ms,
            funding_rate=(
                Decimal(funding_rate_raw) if funding_rate_raw else None
            ),
            open_interest=(
                Decimal(open_interest_raw) if open_interest_raw else None
            ),
            mark_price=Decimal(mark_price_raw) if mark_price_raw else None,
            index_price=Decimal(index_price_raw) if index_price_raw else None,
            funding_interval_hours=(
                int(funding_interval_raw) if funding_interval_raw else None
            ),
            source=DataSource.REST,
            source_timestamp_ms=source_timestamp_ms,
            ingested_at_ms=ingested_at_ms,
            adapter_version=self.ADAPTER_VERSION,
        )


def _require_bybit_success(payload: dict[str, object], surface: str) -> None:
    if payload.get("retCode") != 0:
        raise ValueError(
            f"Bybit derivatives {surface} API error: {payload.get('retMsg')!r}"
        )
