from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.models import DataSource, Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_sha256


class AggressorSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    price: Decimal
    size: Decimal

    def __post_init__(self) -> None:
        _require_positive_finite(self.price, "orderbook price")
        _require_positive_finite(self.size, "orderbook size")

    @property
    def notional(self) -> Decimal:
        return self.price * self.size


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    snapshot_identity: str
    exchange: Exchange
    market_type: MarketType
    symbol: str
    event_at_ms: int
    source_timestamp_ms: int
    response_time_ms: int
    ingested_at_ms: int
    update_id: int
    sequence: int
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    source: DataSource
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.snapshot_identity, "orderbook snapshot identity")
        _require_symbol(self.symbol)
        _require_time_chain(
            event_at_ms=self.event_at_ms,
            source_timestamp_ms=self.source_timestamp_ms,
            response_time_ms=self.response_time_ms,
            ingested_at_ms=self.ingested_at_ms,
        )
        if self.update_id < 0 or self.sequence < 0:
            raise ValueError("orderbook update/sequence must be non-negative")
        if not self.bids or not self.asks:
            raise ValueError("orderbook snapshot requires bids and asks")
        if any(
            left.price <= right.price
            for left, right in zip(self.bids, self.bids[1:], strict=False)
        ):
            raise ValueError("orderbook bids must be strictly descending")
        if any(
            left.price >= right.price
            for left, right in zip(self.asks, self.asks[1:], strict=False)
        ):
            raise ValueError("orderbook asks must be strictly ascending")
        if self.bids[0].price >= self.asks[0].price:
            raise ValueError("orderbook must not be crossed")
        if not self.adapter_version.strip():
            raise ValueError("orderbook adapter_version must be non-empty")
        if self.snapshot_identity != canonical_sha256(orderbook_snapshot_payload(self)):
            raise ValueError("orderbook snapshot identity mismatch")


@dataclass(frozen=True, slots=True)
class PublicTradeObservation:
    trade_identity: str
    exchange: Exchange
    market_type: MarketType
    symbol: str
    exec_id: str
    sequence: int
    aggressor_side: AggressorSide
    price: Decimal
    size: Decimal
    event_at_ms: int
    source_timestamp_ms: int
    ingested_at_ms: int
    is_block_trade: bool
    is_rpi_trade: bool
    source: DataSource
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.trade_identity, "public trade identity")
        _require_symbol(self.symbol)
        if not self.exec_id.strip():
            raise ValueError("public trade exec_id must be non-empty")
        if self.sequence < 0:
            raise ValueError("public trade sequence must be non-negative")
        _require_positive_finite(self.price, "public trade price")
        _require_positive_finite(self.size, "public trade size")
        if min(self.event_at_ms, self.source_timestamp_ms, self.ingested_at_ms) < 0:
            raise ValueError("public trade timestamps must be non-negative")
        if self.event_at_ms > self.source_timestamp_ms:
            raise ValueError("public trade event cannot postdate source timestamp")
        if not self.adapter_version.strip():
            raise ValueError("public trade adapter_version must be non-empty")
        if self.trade_identity != canonical_sha256(public_trade_payload(self)):
            raise ValueError("public trade identity mismatch")

    @property
    def notional(self) -> Decimal:
        return self.price * self.size

    @property
    def book_eligible(self) -> bool:
        return not self.is_block_trade and not self.is_rpi_trade


def build_orderbook_snapshot(
    *,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    event_at_ms: int,
    source_timestamp_ms: int,
    response_time_ms: int,
    ingested_at_ms: int,
    update_id: int,
    sequence: int,
    bids: tuple[OrderBookLevel, ...],
    asks: tuple[OrderBookLevel, ...],
    source: DataSource,
    adapter_version: str,
) -> OrderBookSnapshot:
    payload = {
        "adapter_version": adapter_version,
        "asks": [_level_payload(level) for level in asks],
        "bids": [_level_payload(level) for level in bids],
        "event_at_ms": event_at_ms,
        "exchange": exchange,
        "ingested_at_ms": ingested_at_ms,
        "market_type": market_type,
        "response_time_ms": response_time_ms,
        "sequence": sequence,
        "source": source,
        "source_timestamp_ms": source_timestamp_ms,
        "symbol": symbol,
        "update_id": update_id,
    }
    return OrderBookSnapshot(
        snapshot_identity=canonical_sha256(payload),
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        event_at_ms=event_at_ms,
        source_timestamp_ms=source_timestamp_ms,
        response_time_ms=response_time_ms,
        ingested_at_ms=ingested_at_ms,
        update_id=update_id,
        sequence=sequence,
        bids=bids,
        asks=asks,
        source=source,
        adapter_version=adapter_version,
    )


def build_public_trade_observation(
    *,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    exec_id: str,
    sequence: int,
    aggressor_side: AggressorSide,
    price: Decimal,
    size: Decimal,
    event_at_ms: int,
    source_timestamp_ms: int,
    ingested_at_ms: int,
    is_block_trade: bool,
    is_rpi_trade: bool,
    source: DataSource,
    adapter_version: str,
) -> PublicTradeObservation:
    payload = {
        "adapter_version": adapter_version,
        "aggressor_side": aggressor_side,
        "event_at_ms": event_at_ms,
        "exchange": exchange,
        "exec_id": exec_id,
        "ingested_at_ms": ingested_at_ms,
        "is_block_trade": is_block_trade,
        "is_rpi_trade": is_rpi_trade,
        "market_type": market_type,
        "price": price,
        "sequence": sequence,
        "size": size,
        "source": source,
        "source_timestamp_ms": source_timestamp_ms,
        "symbol": symbol,
    }
    return PublicTradeObservation(
        trade_identity=canonical_sha256(payload),
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        exec_id=exec_id,
        sequence=sequence,
        aggressor_side=aggressor_side,
        price=price,
        size=size,
        event_at_ms=event_at_ms,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=ingested_at_ms,
        is_block_trade=is_block_trade,
        is_rpi_trade=is_rpi_trade,
        source=source,
        adapter_version=adapter_version,
    )


def orderbook_snapshot_payload(snapshot: OrderBookSnapshot) -> dict[str, object]:
    return {
        "adapter_version": snapshot.adapter_version,
        "asks": [_level_payload(level) for level in snapshot.asks],
        "bids": [_level_payload(level) for level in snapshot.bids],
        "event_at_ms": snapshot.event_at_ms,
        "exchange": snapshot.exchange,
        "ingested_at_ms": snapshot.ingested_at_ms,
        "market_type": snapshot.market_type,
        "response_time_ms": snapshot.response_time_ms,
        "sequence": snapshot.sequence,
        "source": snapshot.source,
        "source_timestamp_ms": snapshot.source_timestamp_ms,
        "symbol": snapshot.symbol,
        "update_id": snapshot.update_id,
    }


def public_trade_payload(trade: PublicTradeObservation) -> dict[str, object]:
    return {
        "adapter_version": trade.adapter_version,
        "aggressor_side": trade.aggressor_side,
        "event_at_ms": trade.event_at_ms,
        "exchange": trade.exchange,
        "exec_id": trade.exec_id,
        "ingested_at_ms": trade.ingested_at_ms,
        "is_block_trade": trade.is_block_trade,
        "is_rpi_trade": trade.is_rpi_trade,
        "market_type": trade.market_type,
        "price": trade.price,
        "sequence": trade.sequence,
        "size": trade.size,
        "source": trade.source,
        "source_timestamp_ms": trade.source_timestamp_ms,
        "symbol": trade.symbol,
    }


def _level_payload(level: OrderBookLevel) -> dict[str, Decimal]:
    return {"price": level.price, "size": level.size}


def _require_positive_finite(value: Decimal, label: str) -> None:
    if value.is_nan() or value.is_infinite() or value <= Decimal(0):
        raise ValueError(f"{label} must be finite and positive")


def _require_symbol(symbol: str) -> None:
    if not symbol or symbol != symbol.upper():
        raise ValueError("microstructure symbol must be non-empty uppercase")


def _require_time_chain(
    *,
    event_at_ms: int,
    source_timestamp_ms: int,
    response_time_ms: int,
    ingested_at_ms: int,
) -> None:
    if min(event_at_ms, source_timestamp_ms, response_time_ms, ingested_at_ms) < 0:
        raise ValueError("orderbook timestamps must be non-negative")
    if event_at_ms > source_timestamp_ms:
        raise ValueError("orderbook event cannot postdate source timestamp")
    if source_timestamp_ms > response_time_ms:
        raise ValueError("orderbook source timestamp cannot postdate response time")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
