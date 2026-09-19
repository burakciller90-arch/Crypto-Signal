from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class Exchange(StrEnum):
    BYBIT = "bybit"
    BINANCE = "binance"


class MarketType(StrEnum):
    SPOT = "spot"


class DataSource(StrEnum):
    REST = "rest"
    WEBSOCKET = "websocket"


@dataclass(frozen=True, slots=True)
class Candle:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal | None
    trade_count: int | None
    is_closed: bool
    source: DataSource
    source_timestamp_ms: int
    ingested_at_ms: int
    adapter_version: str

    def __post_init__(self) -> None:
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("symbol must be non-empty uppercase")
        if self.open_time_ms < 0 or self.close_time_ms <= self.open_time_ms:
            raise ValueError("invalid candle time bounds")
        if self.source_timestamp_ms < 0 or self.ingested_at_ms < 0:
            raise ValueError("timestamps must be non-negative")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC prices must be positive")
        if self.volume < 0 or (self.quote_volume is not None and self.quote_volume < 0):
            raise ValueError("volume must be non-negative")
        if self.trade_count is not None and self.trade_count < 0:
            raise ValueError("trade count must be non-negative")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("OHLC ordering is impossible")
        if self.low > self.high:
            raise ValueError("low cannot exceed high")

    @property
    def identity(self) -> tuple[str, str, str, str, int]:
        return (
            self.exchange.value,
            self.market_type.value,
            self.symbol,
            self.timeframe,
            self.open_time_ms,
        )
