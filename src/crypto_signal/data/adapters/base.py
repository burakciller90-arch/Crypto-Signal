from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from crypto_signal.data.models import Candle


class MarketDataAdapter(Protocol):
    async def fetch_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> Sequence[Candle]: ...
