from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import cast

import httpx

from crypto_signal.data.onchain_capital_flow import (
    StablecoinSourceTimestampSemantic,
)

DEFILLAMA_STABLECOIN_TIMESTAMP_SEMANTIC = (
    StablecoinSourceTimestampSemantic.COLLECTOR_RECEIPT
)


@dataclass(frozen=True, slots=True)
class DefiLlamaStablecoinSourceSnapshot:
    asset: str
    provider_asset_id: str
    asset_payload: dict[str, object]
    circulating_amount: Decimal
    source_timestamp_ms: int
    observed_at_ms: int
    ingested_at_ms: int
    source_timestamp_semantic: StablecoinSourceTimestampSemantic

    def __post_init__(self) -> None:
        if self.asset not in {"USDT", "USDC"}:
            raise ValueError("unsupported DefiLlama stablecoin asset")
        if not self.provider_asset_id.strip():
            raise ValueError("DefiLlama stablecoin asset id must be non-empty")
        if not self.asset_payload:
            raise ValueError("DefiLlama stablecoin source payload is empty")
        if self.circulating_amount.is_nan() or (
            self.circulating_amount.is_infinite()
        ) or self.circulating_amount < Decimal(0):
            raise ValueError(
                "DefiLlama circulating supply must be finite and non-negative"
            )
        if min(
            self.source_timestamp_ms,
            self.observed_at_ms,
            self.ingested_at_ms,
        ) < 0:
            raise ValueError("DefiLlama stablecoin timestamps cannot be negative")
        if self.source_timestamp_ms != self.observed_at_ms:
            raise ValueError(
                "DefiLlama list response has no provider timestamp; "
                "source time must equal collector observation time"
            )
        if self.ingested_at_ms < self.observed_at_ms:
            raise ValueError(
                "DefiLlama stablecoin ingestion cannot predate observation"
            )
        if (
            self.source_timestamp_semantic
            is not StablecoinSourceTimestampSemantic.COLLECTOR_RECEIPT
        ):
            raise ValueError(
                "DefiLlama stablecoin timestamp semantic must be collector receipt"
            )


class DefiLlamaStablecoinAdapter:
    BASE_URL = "https://stablecoins.llama.fi"
    ADAPTER_VERSION = "defillama-stablecoins-rest/1"
    SUPPORTED_ASSETS = ("USDT", "USDC")

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        base_url: str | None = None,
    ) -> None:
        selected = (base_url or self.BASE_URL).rstrip("/")
        if not selected.startswith("https://"):
            raise ValueError("DefiLlama stablecoin REST base URL must use https")
        self._client = client
        self._base_url = selected

    async def fetch_source_snapshots(
        self,
        *,
        assets: tuple[str, ...] = SUPPORTED_ASSETS,
    ) -> tuple[DefiLlamaStablecoinSourceSnapshot, ...]:
        selected_assets = tuple(dict.fromkeys(assets))
        if not selected_assets or any(
            asset not in self.SUPPORTED_ASSETS for asset in selected_assets
        ):
            raise ValueError(
                "DefiLlama stablecoin assets must be a non-empty subset "
                "of USDT/USDC"
            )
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=20.0)
        try:
            response = await client.get(
                f"{self._base_url}/stablecoins",
                params={"includePrices": "true"},
                headers={"User-Agent": "Crypto-Signal-RDP7/1"},
            )
            response.raise_for_status()
            payload = cast(dict[str, object], response.json())
            observed_at_ms = time.time_ns() // 1_000_000
        finally:
            if owns_client:
                await client.aclose()

        rows = payload.get("peggedAssets")
        if not isinstance(rows, list) or not rows:
            raise ValueError(
                "DefiLlama stablecoin response requires peggedAssets rows"
            )

        by_asset: dict[str, dict[str, object]] = {}
        for value in rows:
            if not isinstance(value, dict):
                raise TypeError(
                    "DefiLlama stablecoin asset row must be an object"
                )
            row = cast(dict[str, object], value)
            symbol = str(row.get("symbol", "")).strip().upper()
            if symbol not in selected_assets:
                continue
            if symbol in by_asset:
                raise ValueError(
                    f"DefiLlama stablecoin response duplicated {symbol}"
                )
            by_asset[symbol] = row

        missing = tuple(
            asset for asset in selected_assets if asset not in by_asset
        )
        if missing:
            raise ValueError(
                "DefiLlama stablecoin response missing required assets: "
                + ",".join(missing)
            )

        return tuple(
            self._normalize_row(
                asset=asset,
                row=by_asset[asset],
                observed_at_ms=observed_at_ms,
            )
            for asset in selected_assets
        )

    def _normalize_row(
        self,
        *,
        asset: str,
        row: dict[str, object],
        observed_at_ms: int,
    ) -> DefiLlamaStablecoinSourceSnapshot:
        provider_asset_id = str(row.get("id", "")).strip()
        if not provider_asset_id:
            raise ValueError("DefiLlama stablecoin row requires id")
        circulating = row.get("circulating")
        if not isinstance(circulating, dict):
            raise TypeError(
                "DefiLlama stablecoin circulating field must be an object"
            )
        raw_amount = circulating.get("peggedUSD")
        if raw_amount is None:
            raise ValueError(
                "DefiLlama USD stablecoin row requires circulating.peggedUSD"
            )
        amount = Decimal(str(raw_amount))
        if amount.is_nan() or amount.is_infinite() or amount < Decimal(0):
            raise ValueError(
                "DefiLlama stablecoin circulating amount is invalid"
            )
        chain_circulating = row.get("chainCirculating")
        if not isinstance(chain_circulating, dict):
            raise TypeError(
                "DefiLlama stablecoin row requires chainCirculating object"
            )
        return DefiLlamaStablecoinSourceSnapshot(
            asset=asset,
            provider_asset_id=provider_asset_id,
            asset_payload=row,
            circulating_amount=amount,
            source_timestamp_ms=observed_at_ms,
            observed_at_ms=observed_at_ms,
            ingested_at_ms=observed_at_ms,
            source_timestamp_semantic=DEFILLAMA_STABLECOIN_TIMESTAMP_SEMANTIC,
        )
