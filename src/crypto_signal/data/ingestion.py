from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass

from crypto_signal.data.models import Candle
from crypto_signal.data.store import CandleStore, WriteDisposition


@dataclass(frozen=True, slots=True)
class IngestResult:
    candle: Candle
    disposition: WriteDisposition


class CandleIngestor:
    def __init__(self, store: CandleStore) -> None:
        self.store = store

    async def ingest(self, candles: AsyncIterator[Candle]) -> AsyncGenerator[IngestResult, None]:
        async for candle in candles:
            yield IngestResult(
                candle=candle,
                disposition=self.store.upsert(candle),
            )
