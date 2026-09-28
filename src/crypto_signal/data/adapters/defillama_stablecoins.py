from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import cast

import httpx


@dataclass(frozen=True, slots=True)
class DefiLlamaStablecoinAssetSnapshot:
    symbol: str
    provider_asset_id: str
    circulating_pegged_usd: Decimal
    price_usd: Decimal | None
    chain_count: int
    raw_payload: dict[str, object]

    def __post_init__(self) -> None:
        if self.symbol not in {"USDT", "USDC"}:
            raise ValueError("unsupported DefiLlama stablecoin symbol")
        if not self.provider_asset_id.strip():
            raise ValueError("DefiLlama stablecoin asset id must be non-empty")
        _require_non_negative(
            self.circulating_pegged_usd,
            "DefiLlama circulating peggedUSD",
        )
        if self.price_usd is not None:
            _require_non_negative(self.price_usd, "DefiLlama stablecoin price")
        if self.chain_count <= 0:
            raise ValueError("DefiLlama stablecoin requires chain distribution")
        if not self.raw_payload:
            raise ValueError("DefiLlama stablecoin raw payload cannot be empty")


@dataclass(frozen=True, slots=True)
class DefiLlamaStablecoinSourceSnapshot:
    assets: tuple[DefiLlamaStablecoinAssetSnapshot, ...]
    observed_at_ms: int

    def __post_init__(self) -> None:
        if self.observed_at_ms < 0:
            raise ValueError("DefiLlama observation time cannot be negative")
        symbols = tuple(item.symbol for item in self.assets)
        if symbols != ("USDC", "USDT"):
            raise ValueError(
                "DefiLlama snapshot requires canonical USDC/USDT assets"
            )


class DefiLlamaStablecoinsAdapter:
    BASE_URL = "https://stablecoins.llama.fi"
    ADAPTER_VERSION = "defillama-stablecoins-public-rest/1"
    USER_AGENT = (
        "Crypto-Signal/1.0 "
        "(public market intelligence; github.com/burakciller90-arch/Crypto-Signal)"
    )
    SUPPORTED_SYMBOLS = frozenset({"USDT", "USDC"})

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        base_url: str | None = None,
    ) -> None:
        selected = (base_url or self.BASE_URL).rstrip("/")
        if not selected.startswith("https://"):
            raise ValueError("DefiLlama stablecoin base URL must use https")
        self._client = client
        self._base_url = selected

    async def fetch_snapshot(self) -> DefiLlamaStablecoinSourceSnapshot:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=20.0)
        try:
            response = await client.get(
                f"{self._base_url}/stablecoins",
                params={"includePrices": "true"},
                headers={
                    "Accept": "application/json",
                    "User-Agent": self.USER_AGENT,
                },
            )
            response.raise_for_status()
            payload = cast(dict[str, object], response.json())
            observed_at_ms = time.time_ns() // 1_000_000
        finally:
            if owns_client:
                await client.aclose()

        raw_assets = payload.get("peggedAssets")
        if not isinstance(raw_assets, list) or not raw_assets:
            raise ValueError(
                "DefiLlama stablecoin response requires peggedAssets"
            )

        selected: dict[str, DefiLlamaStablecoinAssetSnapshot] = {}
        for raw in raw_assets:
            if not isinstance(raw, dict):
                continue
            item = cast(dict[str, object], raw)
            symbol = str(item.get("symbol", "")).upper().strip()
            if symbol not in self.SUPPORTED_SYMBOLS:
                continue
            if symbol in selected:
                raise ValueError(
                    "DefiLlama stablecoin response duplicated tracked symbol"
                )
            selected[symbol] = _normalize_asset(item, symbol=symbol)

        if set(selected) != self.SUPPORTED_SYMBOLS:
            raise ValueError(
                "DefiLlama stablecoin response requires USDT and USDC"
            )
        assets = tuple(selected[symbol] for symbol in sorted(selected))
        return DefiLlamaStablecoinSourceSnapshot(
            assets=assets,
            observed_at_ms=observed_at_ms,
        )


def _normalize_asset(
    payload: dict[str, object],
    *,
    symbol: str,
) -> DefiLlamaStablecoinAssetSnapshot:
    circulating = payload.get("circulating")
    if not isinstance(circulating, dict):
        raise TypeError(
            "DefiLlama stablecoin circulating value must be an object"
        )
    raw_amount = circulating.get("peggedUSD")
    if raw_amount is None:
        raise ValueError(
            "DefiLlama stablecoin circulating requires peggedUSD"
        )
    amount = _decimal(raw_amount, "circulating peggedUSD")

    raw_price = payload.get("price")
    price = (
        None
        if raw_price is None
        else _decimal(raw_price, "stablecoin price")
    )
    chains = payload.get("chainCirculating")
    if not isinstance(chains, dict) or not chains:
        raise ValueError(
            "DefiLlama stablecoin requires chainCirculating"
        )
    return DefiLlamaStablecoinAssetSnapshot(
        symbol=symbol,
        provider_asset_id=str(payload.get("id", "")).strip(),
        circulating_pegged_usd=amount,
        price_usd=price,
        chain_count=len(chains),
        raw_payload=dict(payload),
    )


def _decimal(value: object, label: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"invalid DefiLlama {label}") from exc
    _require_non_negative(parsed, f"DefiLlama {label}")
    return parsed


def _require_non_negative(value: Decimal, label: str) -> None:
    if value.is_nan() or value.is_infinite() or value < Decimal(0):
        raise ValueError(f"{label} must be finite and non-negative")
