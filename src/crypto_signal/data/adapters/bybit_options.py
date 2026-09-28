from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import cast

import httpx

from crypto_signal.data.models import DataSource, Exchange
from crypto_signal.data.options import (
    OptionContractQuote,
    OptionInstrumentSpec,
    OptionSurfaceObservation,
    OptionType,
    build_option_contract_quote,
    build_option_instrument_metadata_identity,
    build_option_instrument_spec,
    build_option_surface_observation,
)


@dataclass(frozen=True, slots=True)
class BybitOptionSurfaceSourceSnapshot:
    base_coin: str
    instrument_payloads: tuple[dict[str, object], ...]
    ticker_payload: dict[str, object]
    instrument_specs: tuple[OptionInstrumentSpec, ...]
    surface: OptionSurfaceObservation
    observed_at_ms: int

    def __post_init__(self) -> None:
        if self.base_coin not in {"BTC", "ETH"}:
            raise ValueError("unsupported Bybit option base coin")
        if not self.instrument_payloads:
            raise ValueError("Bybit option snapshot requires instrument payload")
        if self.observed_at_ms < 0:
            raise ValueError("Bybit option snapshot observation cannot be negative")


class BybitOptionsAdapter:
    BASE_URL = "https://api.bybit.com"
    ADAPTER_VERSION = "bybit-v5-options-rest/1"
    SUPPORTED_BASE_COINS = frozenset({"BTC", "ETH"})

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        base_url: str | None = None,
    ) -> None:
        selected_base_url = (base_url or self.BASE_URL).rstrip("/")
        if not selected_base_url.startswith("https://"):
            raise ValueError("Bybit options REST base URL must use https")
        self._client = client
        self._base_url = selected_base_url

    async def fetch_source_snapshot(
        self,
        *,
        base_coin: str,
    ) -> BybitOptionSurfaceSourceSnapshot:
        self._require_base_coin(base_coin)
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            instrument_payloads = await self._fetch_instrument_payloads(
                client=client,
                base_coin=base_coin,
            )
            ticker_response = await client.get(
                f"{self._base_url}/v5/market/tickers",
                params={"category": "option", "baseCoin": base_coin},
            )
            ticker_response.raise_for_status()
            ticker_payload = cast(dict[str, object], ticker_response.json())
            observed_at_ms = time.time_ns() // 1_000_000
        finally:
            if owns_client:
                await client.aclose()

        for payload in instrument_payloads:
            _require_bybit_success(payload, "instruments-info")
        _require_bybit_success(ticker_payload, "tickers")

        instrument_specs = self._normalize_instrument_specs(
            payloads=instrument_payloads,
            base_coin=base_coin,
            observed_at_ms=observed_at_ms,
        )
        quotes = self._normalize_ticker_quotes(
            payload=ticker_payload,
            base_coin=base_coin,
            instrument_specs=instrument_specs,
            observed_at_ms=observed_at_ms,
        )
        metadata_identity = build_option_instrument_metadata_identity(
            exchange=Exchange.BYBIT,
            base_coin=base_coin,
            instrument_specs=instrument_specs,
        )
        ticker_source_ms = _payload_time(ticker_payload, "tickers")
        surface = build_option_surface_observation(
            exchange=Exchange.BYBIT,
            base_coin=base_coin,
            instrument_metadata_identity=metadata_identity,
            contracts=quotes,
            source=DataSource.REST,
            source_timestamp_ms=ticker_source_ms,
            observed_at_ms=observed_at_ms,
            ingested_at_ms=observed_at_ms,
            adapter_version=self.ADAPTER_VERSION,
        )
        return BybitOptionSurfaceSourceSnapshot(
            base_coin=base_coin,
            instrument_payloads=instrument_payloads,
            ticker_payload=ticker_payload,
            instrument_specs=instrument_specs,
            surface=surface,
            observed_at_ms=observed_at_ms,
        )

    async def _fetch_instrument_payloads(
        self,
        *,
        client: httpx.AsyncClient,
        base_coin: str,
    ) -> tuple[dict[str, object], ...]:
        cursor = ""
        payloads: list[dict[str, object]] = []
        while True:
            params: dict[str, str | int] = {
                "category": "option",
                "baseCoin": base_coin,
                "limit": 1000,
            }
            if cursor:
                params["cursor"] = cursor
            response = await client.get(
                f"{self._base_url}/v5/market/instruments-info",
                params=params,
            )
            response.raise_for_status()
            payload = cast(dict[str, object], response.json())
            _require_bybit_success(payload, "instruments-info")
            payloads.append(payload)

            result = cast(dict[str, object], payload.get("result"))
            next_cursor = str(result.get("nextPageCursor", "")).strip()
            if not next_cursor:
                break
            if next_cursor == cursor:
                raise ValueError("Bybit option instrument cursor did not advance")
            cursor = next_cursor
        return tuple(payloads)

    def _normalize_instrument_specs(
        self,
        *,
        payloads: tuple[dict[str, object], ...],
        base_coin: str,
        observed_at_ms: int,
    ) -> tuple[OptionInstrumentSpec, ...]:
        normalized: list[OptionInstrumentSpec] = []
        seen_symbols: set[str] = set()
        for payload in payloads:
            source_timestamp_ms = _payload_time(payload, "instruments-info")
            result = cast(dict[str, object], payload.get("result"))
            if result.get("category") != "option":
                raise ValueError("Bybit option instrument category mismatch")
            rows = cast(list[dict[str, object]], result.get("list", []))
            for row in rows:
                row_base = str(row.get("baseCoin", "")).strip()
                if row_base != base_coin:
                    raise ValueError("Bybit option instrument base coin mismatch")
                symbol = str(row.get("symbol", "")).strip()
                if symbol in seen_symbols:
                    raise ValueError("Bybit option instrument symbol duplicated")
                seen_symbols.add(symbol)
                option_type, strike = _option_terms(row=row, base_coin=base_coin)
                normalized.append(
                    build_option_instrument_spec(
                        exchange=Exchange.BYBIT,
                        symbol=symbol,
                        base_coin=row_base,
                        quote_coin=str(row.get("quoteCoin", "")).strip(),
                        settle_coin=str(row.get("settleCoin", "")).strip(),
                        option_type=option_type,
                        strike=strike,
                        expiry_at_ms=int(cast(str | int, row["deliveryTime"])),
                        status=str(row.get("status", "")).strip(),
                        source=DataSource.REST,
                        source_timestamp_ms=source_timestamp_ms,
                        observed_at_ms=observed_at_ms,
                        ingested_at_ms=observed_at_ms,
                        adapter_version=self.ADAPTER_VERSION,
                    )
                )
        if not normalized:
            raise ValueError("Bybit option instrument snapshot is empty")
        return tuple(sorted(normalized, key=lambda item: item.symbol))

    def _normalize_ticker_quotes(
        self,
        *,
        payload: dict[str, object],
        base_coin: str,
        instrument_specs: tuple[OptionInstrumentSpec, ...],
        observed_at_ms: int,
    ) -> tuple[OptionContractQuote, ...]:
        result = cast(dict[str, object], payload.get("result"))
        if result.get("category") != "option":
            raise ValueError("Bybit option ticker category mismatch")
        source_timestamp_ms = _payload_time(payload, "tickers")
        by_symbol = {item.symbol: item for item in instrument_specs}
        rows = cast(list[dict[str, object]], result.get("list", []))
        quotes: list[OptionContractQuote] = []
        seen_symbols: set[str] = set()
        for row in rows:
            symbol = str(row.get("symbol", "")).strip()
            if not symbol.startswith(f"{base_coin}-"):
                raise ValueError("Bybit option ticker base coin mismatch")
            instrument = by_symbol.get(symbol)
            if instrument is None:
                raise ValueError(
                    "Bybit option ticker missing exact instrument metadata"
                )
            if symbol in seen_symbols:
                raise ValueError("Bybit option ticker symbol duplicated")
            seen_symbols.add(symbol)
            quotes.append(
                build_option_contract_quote(
                    instrument=instrument,
                    mark_iv=_decimal_or_none(row.get("markIv")),
                    bid_iv=_decimal_or_none(row.get("bid1Iv")),
                    ask_iv=_decimal_or_none(row.get("ask1Iv")),
                    mark_price=_decimal_or_none(row.get("markPrice")),
                    index_price=_decimal_or_none(row.get("indexPrice")),
                    underlying_price=_decimal_or_none(row.get("underlyingPrice")),
                    delta=_decimal_or_none(row.get("delta")),
                    gamma=_decimal_or_none(row.get("gamma")),
                    vega=_decimal_or_none(row.get("vega")),
                    theta=_decimal_or_none(row.get("theta")),
                    open_interest=_decimal_or_none(row.get("openInterest")),
                    volume_24h=_decimal_or_none(row.get("volume24h")),
                    turnover_24h=_decimal_or_none(row.get("turnover24h")),
                    source=DataSource.REST,
                    source_timestamp_ms=source_timestamp_ms,
                    observed_at_ms=observed_at_ms,
                    ingested_at_ms=observed_at_ms,
                    adapter_version=self.ADAPTER_VERSION,
                )
            )
        if not quotes:
            raise ValueError("Bybit option ticker surface is empty")
        return tuple(sorted(quotes, key=lambda item: item.symbol))

    @classmethod
    def _require_base_coin(cls, base_coin: str) -> None:
        if base_coin not in cls.SUPPORTED_BASE_COINS:
            raise ValueError("Bybit options base coin must be BTC or ETH")


def _option_terms(
    *,
    row: dict[str, object],
    base_coin: str,
) -> tuple[OptionType, Decimal]:
    symbol = str(row.get("symbol", "")).strip()
    parts = symbol.split("-")
    if len(parts) not in {4, 5} or parts[0] != base_coin:
        raise ValueError("unsupported Bybit option symbol format")
    strike = Decimal(parts[2])
    side_code = parts[3]
    provider_type = str(row.get("optionsType", "")).strip()
    if provider_type == "Call":
        option_type = OptionType.CALL
        expected_code = "C"
    elif provider_type == "Put":
        option_type = OptionType.PUT
        expected_code = "P"
    else:
        raise ValueError("unsupported Bybit option type")
    if side_code != expected_code:
        raise ValueError("Bybit option symbol/type mismatch")
    return option_type, strike


def _payload_time(payload: dict[str, object], surface: str) -> int:
    raw = payload.get("time")
    if raw is None:
        raise ValueError(f"Bybit option {surface} response requires time")
    value = int(cast(str | int, raw))
    if value < 0:
        raise ValueError(f"Bybit option {surface} time cannot be negative")
    return value


def _decimal_or_none(value: object) -> Decimal | None:
    text = "" if value is None else str(value).strip()
    return None if not text else Decimal(text)


def _require_bybit_success(payload: dict[str, object], surface: str) -> None:
    if payload.get("retCode") != 0:
        raise ValueError(
            f"Bybit options {surface} API error: {payload.get('retMsg')!r}"
        )
