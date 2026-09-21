from __future__ import annotations

import time
from decimal import Decimal
from typing import cast

import httpx

from crypto_signal.data.models import DataSource
from crypto_signal.data.onchain import (
    BitcoinBlockRecord,
    BitcoinBlockWindowObservation,
    BitcoinNetwork,
    build_bitcoin_block_record,
    build_bitcoin_block_window_observation,
)


class BlockstreamBitcoinNetworkAdapter:
    BASE_URL = "https://blockstream.info/api"
    ADAPTER_VERSION = "blockstream-esplora-bitcoin-mainnet/1"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def fetch_block_window(
        self,
        *,
        start_height: int | None = None,
    ) -> BitcoinBlockWindowObservation:
        if start_height is not None and start_height < 0:
            raise ValueError("bitcoin start_height must be non-negative")

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            if start_height is None:
                tip_response = await client.get(f"{self.BASE_URL}/blocks/tip/height")
                tip_response.raise_for_status()
                selected_height = int(tip_response.text.strip())
            else:
                selected_height = start_height

            blocks_response = await client.get(
                f"{self.BASE_URL}/blocks/{selected_height}"
            )
            blocks_response.raise_for_status()
            raw_blocks = cast(list[dict[str, object]], blocks_response.json())
            observed_at_ms = time.time_ns() // 1_000_000
        finally:
            if owns_client:
                await client.aclose()

        if not raw_blocks:
            raise ValueError("Blockstream block window response is empty")
        blocks = tuple(self._normalize_block(item) for item in raw_blocks)
        if blocks[0].height != selected_height:
            raise ValueError("Blockstream block window does not start at requested height")

        return build_bitcoin_block_window_observation(
            network=BitcoinNetwork.MAINNET,
            observed_at_ms=observed_at_ms,
            tip_height=blocks[0].height,
            tip_hash=blocks[0].block_hash,
            blocks=blocks,
            source=DataSource.REST,
            adapter_version=self.ADAPTER_VERSION,
        )

    @staticmethod
    def _normalize_block(item: dict[str, object]) -> BitcoinBlockRecord:
        return build_bitcoin_block_record(
            block_hash=str(item["id"]),
            height=int(cast(int | str, item["height"])),
            header_timestamp_ms=int(cast(int | str, item["timestamp"])) * 1000,
            median_time_ms=int(cast(int | str, item["mediantime"])) * 1000,
            tx_count=int(cast(int | str, item["tx_count"])),
            size_bytes=int(cast(int | str, item["size"])),
            weight_units=int(cast(int | str, item["weight"])),
            difficulty=Decimal(str(item["difficulty"])),
            previous_block_hash=str(item["previousblockhash"]),
        )
