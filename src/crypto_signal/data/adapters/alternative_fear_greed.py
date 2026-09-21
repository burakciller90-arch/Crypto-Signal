from __future__ import annotations

import time
from typing import ClassVar, cast

import httpx

from crypto_signal.data.models import DataSource
from crypto_signal.data.sentiment_attention import (
    FearGreedSnapshot,
    SentimentClassification,
    SentimentScope,
    build_fear_greed_snapshot,
)


class AlternativeFearGreedAdapter:
    BASE_URL = "https://api.alternative.me"
    ADAPTER_VERSION = "alternative-fng-bitcoin/1"
    USER_AGENT = (
        "Crypto-Signal/1.0 "
        "(public market intelligence; github.com/burakciller90-arch/Crypto-Signal)"
    )
    _CLASSIFICATIONS: ClassVar[dict[str, SentimentClassification]] = {
        "Extreme Fear": SentimentClassification.EXTREME_FEAR,
        "Fear": SentimentClassification.FEAR,
        "Neutral": SentimentClassification.NEUTRAL,
        "Greed": SentimentClassification.GREED,
        "Extreme Greed": SentimentClassification.EXTREME_GREED,
    }

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def fetch_snapshot(self) -> FearGreedSnapshot:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await client.get(
                f"{self.BASE_URL}/fng/",
                params={"limit": 1, "format": "json"},
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

        metadata = cast(dict[str, object], payload.get("metadata", {}))
        if metadata.get("error") is not None:
            raise ValueError(
                f"Alternative Fear & Greed API error: {metadata.get('error')!r}"
            )
        raw_rows = cast(list[dict[str, object]], payload.get("data", []))
        if len(raw_rows) != 1:
            raise ValueError("Alternative Fear & Greed requires exactly one latest row")
        row = raw_rows[0]
        raw_classification = str(row["value_classification"])
        try:
            classification = self._CLASSIFICATIONS[raw_classification]
        except KeyError as exc:
            raise ValueError(
                "unsupported Alternative Fear & Greed classification"
            ) from exc

        return build_fear_greed_snapshot(
            scope=SentimentScope.BITCOIN,
            value=int(cast(int | str, row["value"])),
            classification=classification,
            provider_timestamp_ms=int(cast(int | str, row["timestamp"])) * 1000,
            observed_at_ms=observed_at_ms,
            source=DataSource.REST,
            adapter_version=self.ADAPTER_VERSION,
        )
